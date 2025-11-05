"""
Analytics Service - Main Entry Point

Servicio dedicado para cálculos avanzados de indicadores:
- RVOL por slots (siguiendo lógica de PineScript)
- Indicadores técnicos
- Análisis de liquidez
"""

import asyncio
from datetime import datetime
from typing import Dict, Optional
from zoneinfo import ZoneInfo
import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from shared.config.settings import settings
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import configure_logging, get_logger
from rvol_calculator import RVOLCalculator

# Configurar logger
configure_logging(service_name="analytics")
logger = get_logger(__name__)

# ============================================================================
# Global State
# ============================================================================

redis_client: Optional[RedisClient] = None
timescale_client: Optional[TimescaleClient] = None
rvol_calculator: Optional[RVOLCalculator] = None
background_task: Optional[asyncio.Task] = None


# ============================================================================
# Lifecycle Management
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida de la aplicación"""
    global redis_client, timescale_client, rvol_calculator, background_task
    
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
    NUEVO: Procesamiento basado en snapshot cache (no streams)
    
    - Lee snapshot completo de Redis key
    - Calcula RVOL para todos los tickers
    - Guarda snapshot enriquecido en otro key
    
    Esto evita backlog y asegura sincronización con Scanner
    """
    logger.info("analytics_processing_started (snapshot cache mode)")
    
    last_processed_timestamp = None
    
    last_slot = -1
    current_date = datetime.now(ZoneInfo("America/New_York")).date()
    
    while True:
        try:
            # Detectar cambio de día (SIEMPRE usar America/New_York)
            now = datetime.now(ZoneInfo("America/New_York"))
            if now.date() != current_date:
                logger.info("new_trading_day_detected", new_date=str(now.date()))
                
                # (Compute-only) No persistimos slots desde Analytics
                # Resetear caché
                await rvol_calculator.reset_for_new_day()
                
                current_date = now.date()
                last_slot = -1
            
            # Detectar cambio de slot
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
                ttl=60
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


@app.post("/admin/save-slots")
async def admin_save_slots():
    """
    Endpoint de administración: forzar guardado de slots
    (Solo para testing/debugging)
    """
    if not rvol_calculator:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    current_date = datetime.now().date()
    await rvol_calculator.save_today_slots_to_db(current_date)
    
    return {
        "status": "success",
        "message": "Slots saved to database",
        "date": str(current_date),
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

