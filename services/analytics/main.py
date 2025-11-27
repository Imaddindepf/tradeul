"""
Analytics Service - Main Entry Point

Servicio dedicado para cálculos avanzados de indicadores:
- RVOL por slots (siguiendo lógica de PineScript)
- Indicadores técnicos
- Análisis de liquidez

ARQUITECTURA EVENT-DRIVEN:
- Se suscribe a DAY_CHANGED del EventBus (market_session es la fuente de verdad)
- NO detecta días nuevos por sí mismo
- Verifica festivos antes de resetear cachés
"""

import asyncio
from datetime import datetime, date
from typing import Dict, Optional
from zoneinfo import ZoneInfo
import structlog
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from shared.config.settings import settings
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import configure_logging, get_logger
from shared.events import EventBus, EventType, Event
from rvol_calculator import RVOLCalculator
from shared.utils.atr_calculator import ATRCalculator
from intraday_tracker import IntradayTracker

# Configurar logger
configure_logging(service_name="analytics")
logger = get_logger(__name__)

# ============================================================================
# Global State
# ============================================================================

redis_client: Optional[RedisClient] = None
timescale_client: Optional[TimescaleClient] = None
rvol_calculator: Optional[RVOLCalculator] = None
atr_calculator: Optional[ATRCalculator] = None
intraday_tracker: Optional[IntradayTracker] = None
event_bus: Optional[EventBus] = None
background_task: Optional[asyncio.Task] = None

# Estado de mercado (se actualiza via EventBus, no en cada iteración)
is_holiday_mode: bool = False
current_trading_date: Optional[date] = None


# ============================================================================
# Market Status (Event-Driven)
# ============================================================================

async def check_initial_market_status() -> None:
    """
    Lee el estado del mercado UNA VEZ al iniciar.
    Determina si es día festivo para evitar resetear cachés.
    """
    global is_holiday_mode, current_trading_date
    
    try:
        status_data = await redis_client.get(f"{settings.key_prefix_market}:session:status")
        
        if status_data:
            is_holiday = status_data.get('is_holiday', False)
            is_trading_day = status_data.get('is_trading_day', True)
            trading_date_str = status_data.get('trading_date')
            
            is_holiday_mode = is_holiday or not is_trading_day
            
            if trading_date_str:
                current_trading_date = date.fromisoformat(trading_date_str)
            
            logger.info(
                "📅 market_status_checked",
                is_holiday=is_holiday,
                is_trading_day=is_trading_day,
                holiday_mode=is_holiday_mode,
                trading_date=trading_date_str
            )
            
            if is_holiday_mode:
                logger.warning(
                    "🚨 HOLIDAY_MODE_ACTIVE - No se resetearán cachés",
                    reason="Market is closed for holiday"
                )
        else:
            logger.warning("market_status_not_found_in_redis")
            is_holiday_mode = False
    
    except Exception as e:
        logger.error("error_checking_market_status", error=str(e))
        is_holiday_mode = False


async def handle_day_changed(event: Event) -> None:
    """
    Handler para el evento DAY_CHANGED.
    Se ejecuta cuando market_session detecta un nuevo día de trading.
    
    IMPORTANTE: Solo resetea cachés si NO es día festivo.
    """
    global is_holiday_mode, current_trading_date
    
    new_date_str = event.data.get('new_date')
    logger.info("📆 day_changed_event_received", new_date=new_date_str)
    
    # Re-verificar estado del mercado
    await check_initial_market_status()
    
    # Solo resetear si NO es festivo
    if not is_holiday_mode:
        logger.info("🔄 resetting_analytics_caches", reason="new_trading_day")
        
        if rvol_calculator:
            await rvol_calculator.reset_for_new_day()
        
        if intraday_tracker:
            intraday_tracker.clear_for_new_day()
    else:
        logger.info(
            "⏭️ skipping_cache_reset",
            reason="holiday_mode_active",
            date=new_date_str
        )


# ============================================================================
# Lifecycle Management
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida de la aplicación"""
    global redis_client, timescale_client, rvol_calculator, atr_calculator, intraday_tracker, event_bus, background_task
    
    logger.info("analytics_service_starting")
    
    # Inicializar clientes
    redis_client = RedisClient()
    await redis_client.connect()
    
    timescale_client = TimescaleClient()
    await timescale_client.connect()
    
    # Inicializar calculador de RVOL (con soporte de pre/post market)
    rvol_calculator = RVOLCalculator(
        redis_client=redis_client,
        timescale_client=timescale_client,
        slot_size_minutes=5,
        lookback_days=5,
        include_extended_hours=True  # ✅ Incluye pre-market y post-market
    )
    
    # Inicializar calculador de ATR
    atr_calculator = ATRCalculator(
        redis_client=redis_client,
        timescale_client=timescale_client,
        period=14,
        use_ema=True
    )
    
    # Inicializar IntradayTracker (high/low intradiario)
    intraday_tracker = IntradayTracker(
        polygon_api_key=settings.POLYGON_API_KEY
    )
    
    # 📅 Verificar estado del mercado UNA VEZ al iniciar
    await check_initial_market_status()
    
    # 🔔 Inicializar EventBus y suscribirse a DAY_CHANGED
    event_bus = EventBus(redis_client, "analytics")
    event_bus.subscribe(EventType.DAY_CHANGED, handle_day_changed)
    await event_bus.start_listening()
    logger.info("✅ EventBus initialized - subscribed to DAY_CHANGED")
    
    # 🔄 RECUPERAR DATOS INTRADIARIOS AL INICIAR (solo si NO es festivo)
    if not is_holiday_mode:
        try:
            # Obtener símbolos activos desde snapshot más reciente
            snapshot_data = await redis_client.get("snapshot:polygon:latest")
            if snapshot_data:
                tickers_data = snapshot_data.get('tickers', [])
                # Filtrar símbolos con volumen > 0
                active_symbols = [
                    t.get('ticker') for t in tickers_data
                    if t.get('ticker') and (
                        (t.get('min', {}).get('av', 0) > 0) or 
                        (t.get('day', {}).get('v', 0) > 0)
                    )
                ]
                
                if active_symbols:
                    logger.info("recovering_intraday_data", symbols_count=len(active_symbols))
                    recovered_count = await intraday_tracker.recover_active_symbols(
                        active_symbols=active_symbols,
                        max_symbols=100  # Limitar para no saturar API
                    )
                    logger.info("intraday_recovery_complete", recovered=recovered_count)
                else:
                    logger.info("no_active_symbols_for_recovery")
            else:
                logger.info("no_snapshot_available_for_recovery")
        except Exception as e:
            logger.warning("intraday_recovery_failed", error=str(e))
            # No es crítico, continuamos sin datos recuperados
    else:
        logger.info("⏭️ skipping_intraday_recovery", reason="holiday_mode_active")
    
    # Iniciar procesamiento en background
    background_task = asyncio.create_task(run_analytics_processing())
    
    logger.info("analytics_service_started")
    
    yield
    
    # Shutdown
    logger.info("analytics_service_shutting_down")
    
    if background_task:
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            pass
    
    # 🔔 Stop EventBus
    if event_bus:
        await event_bus.stop_listening()
        logger.info("✅ EventBus stopped")
    
    # 🚀 FIX: Cerrar HTTP client global
    if rvol_calculator:
        await rvol_calculator.close()
    
    if redis_client:
        await redis_client.disconnect()
    
    if timescale_client:
        await timescale_client.disconnect()
    
    logger.info("analytics_service_stopped")


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Analytics Service",
    description="Cálculos avanzados de indicadores (RVOL, indicadores técnicos)",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================================
# Background Processing
# ============================================================================

async def run_analytics_processing():
    """
    Procesamiento basado en snapshot cache (no streams)
    
    - Lee snapshot completo de Redis key
    - Calcula RVOL para todos los tickers
    - Guarda snapshot enriquecido en otro key
    
    NOTA: El reset de cachés por nuevo día se maneja via EventBus (DAY_CHANGED),
    NO en este loop. Esto evita duplicación y asegura verificación de festivos.
    """
    logger.info("analytics_processing_started (snapshot cache mode)")
    
    last_processed_timestamp = None
    last_slot = -1
    
    while True:
        try:
            # 🚨 HOLIDAY MODE: Procesar menos frecuente en festivos
            if is_holiday_mode:
                await asyncio.sleep(60)  # Sleep largo, no hay datos nuevos
                continue
            
            now = datetime.now(ZoneInfo("America/New_York"))
            
            # Detectar cambio de slot (para logging)
            current_slot = rvol_calculator.slot_manager.get_current_slot(now)
            
            if current_slot >= 0 and current_slot != last_slot:
                logger.info(
                    "new_slot_detected",
                    slot=current_slot,
                    slot_info=rvol_calculator.slot_manager.format_slot_info(current_slot)
                )
                last_slot = current_slot
            
            # NUEVO: Leer snapshot completo desde cache
            snapshot_data = await redis_client.get("snapshot:polygon:latest")
            
            if not snapshot_data:
                await asyncio.sleep(1)  # Esperar nuevo snapshot
                continue
            
            # Verificar si ya procesamos este snapshot
            snapshot_timestamp = snapshot_data.get('timestamp')
            if snapshot_timestamp == last_processed_timestamp:
                await asyncio.sleep(0.5)  # Ya procesado, esperar nuevo
                continue
            
            # Procesar snapshot COMPLETO
            tickers_data = snapshot_data.get('tickers', [])
            
            if not tickers_data:
                await asyncio.sleep(1)
                continue
            
            logger.info(f"Processing complete snapshot", 
                       tickers=len(tickers_data), 
                       timestamp=snapshot_timestamp)
            
            # Enriquecer TODOS los tickers del snapshot
            enriched_tickers = []
            rvol_mapping = {}
            
            # Obtener ATR para todos los símbolos en batch (desde Redis cache)
            symbols = [t.get('ticker') for t in tickers_data if t.get('ticker')]
            current_prices = {
                t.get('ticker'): t.get('lastTrade', {}).get('p') or t.get('day', {}).get('c')
                for t in tickers_data if t.get('ticker')
            }
            atr_data = await atr_calculator._get_batch_from_cache(symbols)
            
            # Actualizar atr_percent con precios actuales
            for symbol, atr_info in atr_data.items():
                if atr_info and symbol in current_prices:
                    price = current_prices[symbol]
                    if price and price > 0:
                        atr_info['atr_percent'] = round((atr_info['atr'] / price) * 100, 2)
            
            # DEBUG: Log primeros 3 tickers
            for idx, ticker_data in enumerate(tickers_data):
                try:
                    symbol = ticker_data.get('ticker')
                    
                    # Volumen acumulado (priority: min.av > day.v)
                    # min.av = volumen acumulado del minuto (perfecto para premarket/postmarket)
                    # day.v = volumen del día completo
                    min_data = ticker_data.get('min', {})
                    day_data = ticker_data.get('day', {})
                    
                    volume = 0
                    if min_data and min_data.get('av'):
                        volume = min_data.get('av', 0)
                    elif day_data and day_data.get('v'):
                        volume = day_data.get('v', 0)
                    
                    if not symbol:
                        continue
                    

                    
                    # NUEVO: Siempre agregar el ticker (aunque volumen sea 0)
                    # Si tiene volumen, calcular RVOL
                    rvol = None
                    
                    if volume > 0:
                        # ACTUALIZAR INTRADAY HIGH/LOW
                        # Obtener precio actual para tracking
                        current_price = ticker_data.get('lastTrade', {}).get('p')
                        if not current_price:
                            current_price = day_data.get('c') if day_data else None
                        
                        if current_price and current_price > 0:
                            intraday_tracker.update(symbol, current_price)
                        # Actualizar volumen
                        await rvol_calculator.update_volume_for_symbol(
                            symbol=symbol,
                            volume_accumulated=volume,
                            timestamp=now
                        )
                        
                        # Calcular RVOL
                        rvol = await rvol_calculator.calculate_rvol(symbol, timestamp=now)
                        
                        if rvol and rvol > 0:
                            ticker_data['rvol'] = round(rvol, 2)
                            rvol_mapping[symbol] = str(round(rvol, 2))
                    
                    # Agregar ticker (con o sin RVOL)
                    if 'rvol' not in ticker_data:
                        ticker_data['rvol'] = None
                    
                    # Añadir ATR si está disponible en caché
                    if symbol in atr_data and atr_data[symbol]:
                        ticker_data['atr'] = atr_data[symbol]['atr']
                        ticker_data['atr_percent'] = atr_data[symbol]['atr_percent']
                    else:
                        ticker_data['atr'] = None
                        ticker_data['atr_percent'] = None
                    
                    # 🔄 AÑADIR INTRADAY HIGH/LOW
                    intraday_data = intraday_tracker.get(symbol)
                    if intraday_data:
                        ticker_data['intraday_high'] = intraday_data.get('high')
                        ticker_data['intraday_low'] = intraday_data.get('low')
                    else:
                        # Fallback a day.h/day.l si no hay datos intradiarios
                        ticker_data['intraday_high'] = day_data.get('h') if day_data else None
                        ticker_data['intraday_low'] = day_data.get('l') if day_data else None
                    
                    enriched_tickers.append(ticker_data)
                
                except Exception as e:
                    logger.error(f"Error enriching ticker", symbol=symbol, error=str(e))
            
            # Guardar snapshot ENRIQUECIDO completo
            enriched_snapshot = {
                "timestamp": snapshot_timestamp,
                "count": len(enriched_tickers),
                "tickers": enriched_tickers
            }
            
            await redis_client.set(
                "snapshot:enriched:latest",
                enriched_snapshot,
                ttl=600  # 10 minutos (suficiente para fin de semana)
            )
            
            # Guardar RVOLs en hash
            if rvol_mapping:
                await redis_client.client.hset("rvol:current_slot", mapping=rvol_mapping)
                await redis_client.client.expire("rvol:current_slot", 300)
            
            last_processed_timestamp = snapshot_timestamp
            
            logger.info("Snapshot enriched", 
                       total=len(enriched_tickers),
                       slot=current_slot)
        
        except asyncio.CancelledError:
            logger.info("analytics_processing_cancelled")
            raise
        
        except Exception as e:
            logger.error(
                "analytics_processing_error",
                error=str(e),
                error_type=type(e).__name__
            )
            await asyncio.sleep(5)


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "analytics",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/stats")
async def get_stats():
    """Obtiene estadísticas del servicio"""
    if not rvol_calculator:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    stats = rvol_calculator.get_cache_stats()
    
    return JSONResponse(content=stats)


@app.get("/rvol/{symbol}")
async def get_rvol(symbol: str):
    """
    Obtiene el RVOL actual de un símbolo
    
    Args:
        symbol: Ticker symbol (ej: AAPL)
    
    Returns:
        RVOL calculado
    """
    if not rvol_calculator:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    symbol = symbol.upper()
    
    # Obtener RVOL directamente del hash de Redis (ya calculado en background)
    rvol_str = await redis_client.client.hget("rvol:current_slot", symbol)
    
    if rvol_str is None:
        raise HTTPException(
            status_code=404,
            detail=f"No RVOL data available for {symbol}"
        )
    
    rvol = float(rvol_str)
    
    current_slot = rvol_calculator.slot_manager.get_current_slot()
    slot_info = rvol_calculator.slot_manager.format_slot_info(current_slot)
    
    return {
        "symbol": symbol,
        "rvol": round(rvol, 2),
        "slot": current_slot,
        "slot_info": slot_info,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/rvol/batch")
async def get_rvol_batch(symbols: list[str]):
    """
    Obtiene el RVOL para múltiples símbolos
    
    Args:
        symbols: Lista de ticker symbols
    
    Returns:
        Dict con RVOL de cada símbolo
    """
    if not rvol_calculator:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    symbols = [s.upper() for s in symbols]
    
    rvols = await rvol_calculator.calculate_rvol_batch(symbols)
    
    current_slot = rvol_calculator.slot_manager.get_current_slot()
    
    return {
        "results": rvols,
        "slot": current_slot,
        "count": len(rvols),
        "timestamp": datetime.now().isoformat()
    }


@app.post("/admin/reset")
async def admin_reset():
    """
    Endpoint de administración: resetear caché
    (Solo para testing/debugging)
    """
    if not rvol_calculator:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    await rvol_calculator.reset_for_new_day()
    
    return {
        "status": "success",
        "message": "Cache reset completed",
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "services.analytics.main:app",
        host="0.0.0.0",
        port=8007,
        reload=False,
        log_config=None  # Usar nuestro logger personalizado
    )

