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
from http_clients import http_clients
from volume_window_tracker import VolumeWindowTracker, VolumeWindowResult
from price_window_tracker import PriceWindowTracker, PriceChangeResult
from trades_anomaly_detector import TradesAnomalyDetector, AnomalyResult
from trades_count_tracker import TradesCountTracker

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
volume_window_tracker: Optional[VolumeWindowTracker] = None
price_window_tracker: Optional[PriceWindowTracker] = None
trades_anomaly_detector: Optional[TradesAnomalyDetector] = None
trades_count_tracker: Optional[TradesCountTracker] = None
event_bus: Optional[EventBus] = None
background_task: Optional[asyncio.Task] = None
vwap_consumer_task: Optional[asyncio.Task] = None
volume_tracker_task: Optional[asyncio.Task] = None
price_tracker_task: Optional[asyncio.Task] = None
trades_tracker_task: Optional[asyncio.Task] = None

# Estado de mercado (se actualiza via EventBus, no en cada iteración)
is_holiday_mode: bool = False
current_trading_date: Optional[date] = None

# 🔄 VWAP Cache - mantiene último VWAP conocido desde WebSocket aggregates
# El VWAP persiste hasta que llega un nuevo valor válido (no se borra si viene 0)
vwap_cache: Dict[str, float] = {}


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
        
        # 🔄 Reset VWAP cache para nuevo día
        global vwap_cache
        old_size = len(vwap_cache)
        vwap_cache.clear()
        logger.info("vwap_cache_reset", old_size=old_size)
        
        # 🔄 Reset Volume Window Tracker para nuevo día
        if volume_window_tracker:
            cleared = volume_window_tracker.clear_all()
            logger.info("volume_window_tracker_reset", symbols_cleared=cleared)
        
        # 🔄 Reset Price Window Tracker para nuevo día
        if price_window_tracker:
            cleared = price_window_tracker.clear_all()
            logger.info("price_window_tracker_reset", symbols_cleared=cleared)
        
        # 🔄 Reset Trades Anomaly Detector para nuevo día
        if trades_anomaly_detector:
            await trades_anomaly_detector.reset_for_new_day()
            logger.info("trades_anomaly_detector_reset")
        
        # 🔄 Reset Trades Count Tracker para nuevo día
        if trades_count_tracker:
            trades_count_tracker.reset_for_new_day()
            logger.info("trades_count_tracker_reset")
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
    global redis_client, timescale_client, rvol_calculator, atr_calculator, intraday_tracker, volume_window_tracker, price_window_tracker, trades_anomaly_detector, trades_count_tracker, event_bus, background_task, volume_tracker_task, price_tracker_task, trades_tracker_task
    
    logger.info("analytics_service_starting")
    
    # Inicializar clientes
    redis_client = RedisClient()
    await redis_client.connect()
    
    timescale_client = TimescaleClient()
    await timescale_client.connect()
    
    # Initialize HTTP clients with connection pooling
    await http_clients.initialize(polygon_api_key=settings.POLYGON_API_KEY)
    logger.info("http_clients_initialized_with_pooling")
    
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
    
    # Inicializar VolumeWindowTracker (vol_1min, vol_5min, etc.)
    volume_window_tracker = VolumeWindowTracker()
    logger.info("volume_window_tracker_initialized", stats=volume_window_tracker.get_stats())
    
    # Inicializar PriceWindowTracker (chg_1min, chg_5min, etc.)
    price_window_tracker = PriceWindowTracker()
    logger.info("price_window_tracker_initialized", stats=price_window_tracker.get_stats())
    
    # Inicializar TradesAnomalyDetector (Z-Score de trades para anomalías)
    # NOTA: Los baselines son pre-calculados por data_maintenance y almacenados en Redis
    trades_anomaly_detector = TradesAnomalyDetector(
        redis_client=redis_client,
        lookback_days=5,
        z_score_threshold=3.0
    )
    logger.info("trades_anomaly_detector_initialized", stats=trades_anomaly_detector.get_stats())
    
    # Inicializar TradesCountTracker (acumula trades del día desde WebSocket aggregates)
    trades_count_tracker = TradesCountTracker(redis_client=redis_client)
    logger.info("trades_count_tracker_initialized")
    
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
        logger.info("⏭skipping_intraday_recovery", reason="holiday_mode_active")
    
    # Iniciar procesamiento en background
    background_task = asyncio.create_task(run_analytics_processing())
    
    # Iniciar consumer de VWAP desde aggregates
    vwap_consumer_task = asyncio.create_task(consume_aggregates_for_vwap())
    
    # Iniciar consumer de Volume Windows desde aggregates
    volume_tracker_task = asyncio.create_task(consume_aggregates_for_volume_windows())
    
    # Iniciar consumer de Price Windows desde aggregates
    price_tracker_task = asyncio.create_task(consume_aggregates_for_price_windows())
    
    # Iniciar consumer de Trades Count desde aggregates
    trades_tracker_task = asyncio.create_task(trades_count_tracker.run_consumer())
    
    logger.info("analytics_service_started", vwap_consumer_enabled=True, volume_tracker_enabled=True, price_tracker_enabled=True, trades_tracker_enabled=True)
    
    yield
    
    # Shutdown
    logger.info("analytics_service_shutting_down")
    
    if background_task:
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            pass
    
    #  Stop VWAP consumer
    if vwap_consumer_task:
        vwap_consumer_task.cancel()
        try:
            await vwap_consumer_task
        except asyncio.CancelledError:
            pass
        logger.info("vwap_consumer_stopped")
    
    # Stop Volume Tracker consumer
    if volume_tracker_task:
        volume_tracker_task.cancel()
        try:
            await volume_tracker_task
        except asyncio.CancelledError:
            pass
        logger.info("volume_tracker_consumer_stopped")
    
    # Stop Price Tracker consumer
    if price_tracker_task:
        price_tracker_task.cancel()
        try:
            await price_tracker_task
        except asyncio.CancelledError:
            pass
        logger.info("price_tracker_consumer_stopped")
    
    # Stop Trades Count Tracker
    if trades_tracker_task:
        trades_tracker_task.cancel()
        try:
            await trades_tracker_task
        except asyncio.CancelledError:
            pass
    if trades_count_tracker:
        await trades_count_tracker.stop()
        logger.info("trades_count_tracker_stopped")
    
    # 🔔 Stop EventBus
    if event_bus:
        await event_bus.stop_listening()
        logger.info("✅ EventBus stopped")
    
    # 🚀 FIX: Cerrar HTTP client global
    if rvol_calculator:
        await rvol_calculator.close()
    
    # Cerrar HTTP client de TradesAnomalyDetector
    if trades_anomaly_detector:
        await trades_anomaly_detector.close()
    
    # Close HTTP clients
    await http_clients.close()
    
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
# VWAP Consumer (desde WebSocket aggregates)
# ============================================================================

async def consume_aggregates_for_vwap():
    """
    Consume stream de aggregates SOLO para mantener VWAPs actualizados.
    
    IMPORTANTE: Si el VWAP viene vacío o 0, mantiene el último valor conocido.
    Esto evita que el VWAP "desaparezca" en el frontend.
    
    El VWAP del WebSocket (agg.a) es "Today's VWAP" - exactamente lo que necesitamos.
    """
    global vwap_cache
    
    stream_name = "stream:realtime:aggregates"
    consumer_group = "analytics_vwap_consumer"
    consumer_name = "analytics_vwap_1"
    
    logger.info("vwap_consumer_started", stream=stream_name)
    
    # Crear consumer group si no existe
    try:
        await redis_client.create_consumer_group(
            stream_name,
            consumer_group,
            mkstream=True
        )
        logger.info("vwap_consumer_group_created", group=consumer_group)
    except Exception as e:
        logger.debug("vwap_consumer_group_exists", error=str(e))
    
    while True:
        try:
            # Leer mensajes en batch para eficiencia
            messages = await redis_client.read_stream(
                stream_name=stream_name,
                consumer_group=consumer_group,
                consumer_name=consumer_name,
                count=500,  # Batch grande - solo extraemos vwap
                block=1000  # 1 segundo
            )
            
            if messages:
                message_ids_to_ack = []
                vwap_updates = 0
                
                for stream, stream_messages in messages:
                    for message_id, data in stream_messages:
                        symbol = data.get('symbol')
                        vwap_str = data.get('vwap')
                        
                        if symbol and vwap_str:
                            try:
                                vwap = float(vwap_str)
                                # Solo actualizar si es válido (> 0)
                                # Si viene 0 o vacío, mantener último valor conocido
                                if vwap > 0:
                                    vwap_cache[symbol] = vwap
                                    vwap_updates += 1
                            except (ValueError, TypeError):
                                pass  # Mantener último valor conocido
                        
                        message_ids_to_ack.append(message_id)
                
                # ACK mensajes procesados
                if message_ids_to_ack:
                    try:
                        await redis_client.xack(
                            stream_name,
                            consumer_group,
                            *message_ids_to_ack
                        )
                    except Exception as e:
                        logger.error("vwap_xack_error", error=str(e))
                
                if vwap_updates > 0:
                    logger.debug(
                        "vwap_cache_updated",
                        updates=vwap_updates,
                        cache_size=len(vwap_cache)
                    )
        
        except asyncio.CancelledError:
            logger.info("vwap_consumer_cancelled")
            raise
        
        except Exception as e:
            # Auto-healing: recrear consumer group si fue borrado
            if 'NOGROUP' in str(e):
                logger.warn("vwap_consumer_group_missing_recreating")
                try:
                    await redis_client.create_consumer_group(
                        stream_name,
                        consumer_group,
                        start_id="0",
                        mkstream=True
                    )
                    continue
                except Exception:
                    pass
            
            logger.error("vwap_consumer_error", error=str(e))
            await asyncio.sleep(1)


# ============================================================================
# Volume Window Tracker Consumer
# ============================================================================

async def consume_aggregates_for_volume_windows():
    """
    Consume stream de aggregates para mantener el VolumeWindowTracker actualizado.
    
    Usa el campo 'av' (accumulated volume today) de cada aggregate.
    Este es el volumen acumulado del día, que usamos para calcular vol_Nmin.
    
    Fórmula: vol_5min = av[now] - av[5 min ago]
    """
    stream_name = "stream:realtime:aggregates"
    consumer_group = "analytics_volume_window_consumer"
    consumer_name = "analytics_volume_window_1"
    
    logger.info("volume_window_consumer_started", stream=stream_name)
    
    # Crear consumer group si no existe
    try:
        await redis_client.create_consumer_group(
            stream_name,
            consumer_group,
            mkstream=True
        )
        logger.info("volume_window_consumer_group_created", group=consumer_group)
    except Exception as e:
        logger.debug("volume_window_consumer_group_exists", error=str(e))
    
    update_count = 0
    last_stats_log = datetime.now()
    
    while True:
        try:
            # Skip en holiday mode
            if is_holiday_mode:
                await asyncio.sleep(30)
                continue
            
            # Leer mensajes en batch
            messages = await redis_client.read_stream(
                stream_name=stream_name,
                consumer_group=consumer_group,
                consumer_name=consumer_name,
                count=500,  # Batch grande
                block=1000  # 1 segundo
            )
            
            if messages:
                message_ids_to_ack = []
                batch_updates = 0
                
                for stream, stream_messages in messages:
                    for message_id, data in stream_messages:
                        symbol = data.get('symbol')
                        # Campo puede ser 'av' (Polygon raw) o 'volume_accumulated' (transformado)
                        av_str = data.get('volume_accumulated') or data.get('av')
                        # Usar timestamp REAL del aggregate (en ms), no datetime.now()
                        ts_end_str = data.get('timestamp_end')
                        
                        if symbol and av_str:
                            try:
                                av = int(float(av_str))
                                # Convertir timestamp de ms a segundos
                                agg_ts = int(int(ts_end_str) / 1000) if ts_end_str else int(datetime.now().timestamp())
                                if av > 0:
                                    volume_window_tracker.update(symbol, av, agg_ts)
                                    batch_updates += 1
                            except (ValueError, TypeError):
                                pass
                        
                        message_ids_to_ack.append(message_id)
                
                # ACK mensajes
                if message_ids_to_ack:
                    try:
                        await redis_client.xack(
                            stream_name,
                            consumer_group,
                            *message_ids_to_ack
                        )
                    except Exception as e:
                        logger.error("volume_window_xack_error", error=str(e))
                
                update_count += batch_updates
                
                # Log stats cada 30 segundos
                now = datetime.now()
                if (now - last_stats_log).total_seconds() >= 30:
                    stats = volume_window_tracker.get_stats()
                    logger.info(
                        "volume_window_tracker_stats",
                        updates_since_last=update_count,
                        symbols_active=stats["symbols_active"],
                        memory_mb=stats["memory_mb"]
                    )
                    update_count = 0
                    last_stats_log = now
        
        except asyncio.CancelledError:
            logger.info("volume_window_consumer_cancelled")
            raise
        
        except Exception as e:
            # Auto-healing
            if 'NOGROUP' in str(e):
                logger.warn("volume_window_consumer_group_missing_recreating")
                try:
                    await redis_client.create_consumer_group(
                        stream_name,
                        consumer_group,
                        start_id="0",
                        mkstream=True
                    )
                    continue
                except Exception:
                    pass
            
            logger.error("volume_window_consumer_error", error=str(e))
            await asyncio.sleep(1)


# ============================================================================
# Price Window Tracker Consumer
# ============================================================================

async def consume_aggregates_for_price_windows():
    """
    Consume stream de aggregates para mantener el PriceWindowTracker actualizado.
    
    Usa el campo 'close' o 'c' (precio de cierre del minuto/segundo) de cada aggregate.
    Este es el precio más reciente que usamos para calcular chg_Nmin.
    
    Fórmula: chg_5min = ((price_now - price_5min_ago) / price_5min_ago) * 100
    """
    stream_name = "stream:realtime:aggregates"
    consumer_group = "analytics_price_window_consumer"
    consumer_name = "analytics_price_window_1"
    
    logger.info("price_window_consumer_started", stream=stream_name)
    
    # Crear consumer group si no existe
    try:
        await redis_client.create_consumer_group(
            stream_name,
            consumer_group,
            mkstream=True
        )
        logger.info("price_window_consumer_group_created", group=consumer_group)
    except Exception as e:
        logger.debug("price_window_consumer_group_exists", error=str(e))
    
    update_count = 0
    last_stats_log = datetime.now()
    
    while True:
        try:
            # Skip en holiday mode
            if is_holiday_mode:
                await asyncio.sleep(30)
                continue
            
            # Leer mensajes en batch
            messages = await redis_client.read_stream(
                stream_name=stream_name,
                consumer_group=consumer_group,
                consumer_name=consumer_name,
                count=500,  # Batch grande
                block=1000  # 1 segundo
            )
            
            if messages:
                message_ids_to_ack = []
                batch_updates = 0
                
                for stream, stream_messages in messages:
                    for message_id, data in stream_messages:
                        symbol = data.get('symbol')
                        # Campo puede ser 'close' (Polygon raw) o 'c' (transformado)
                        price_str = data.get('close') or data.get('c')
                        # Usar timestamp REAL del aggregate (en ms), no datetime.now()
                        ts_end_str = data.get('timestamp_end')
                        
                        if symbol and price_str:
                            try:
                                price = float(price_str)
                                # Convertir timestamp de ms a segundos
                                agg_ts = int(int(ts_end_str) / 1000) if ts_end_str else int(datetime.now().timestamp())
                                if price > 0:
                                    price_window_tracker.update(symbol, price, agg_ts)
                                    batch_updates += 1
                            except (ValueError, TypeError):
                                pass
                        
                        message_ids_to_ack.append(message_id)
                
                # ACK mensajes
                if message_ids_to_ack:
                    try:
                        await redis_client.xack(
                            stream_name,
                            consumer_group,
                            *message_ids_to_ack
                        )
                    except Exception as e:
                        logger.error("price_window_xack_error", error=str(e))
                
                update_count += batch_updates
                
                # Log stats cada 30 segundos
                now = datetime.now()
                if (now - last_stats_log).total_seconds() >= 30:
                    stats = price_window_tracker.get_stats()
                    logger.info(
                        "price_window_tracker_stats",
                        updates_since_last=update_count,
                        symbols_active=stats["symbols_active"],
                        memory_mb=stats["memory_mb"]
                    )
                    update_count = 0
                    last_stats_log = now
        
        except asyncio.CancelledError:
            logger.info("price_window_consumer_cancelled")
            raise
        
        except Exception as e:
            # Auto-healing
            if 'NOGROUP' in str(e):
                logger.warn("price_window_consumer_group_missing_recreating")
                try:
                    await redis_client.create_consumer_group(
                        stream_name,
                        consumer_group,
                        start_id="0",
                        mkstream=True
                    )
                    continue
                except Exception:
                    pass
            
            logger.error("price_window_consumer_error", error=str(e))
            await asyncio.sleep(1)


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
                    
                    # 🔄 AÑADIR VWAP (prioridad: day.vw > cache de aggregates)
                    # El VWAP del snapshot puede estar vacío en pre/post market
                    # El cache mantiene el último VWAP conocido del WebSocket
                    day_vwap = day_data.get('vw') if day_data else None
                    if day_vwap and day_vwap > 0:
                        ticker_data['vwap'] = day_vwap
                    elif symbol in vwap_cache and vwap_cache[symbol] > 0:
                        ticker_data['vwap'] = vwap_cache[symbol]
                    # Si no hay VWAP en snapshot ni cache, mantener el existente o None
                    elif 'vwap' not in ticker_data or not ticker_data.get('vwap'):
                        ticker_data['vwap'] = None
                    
                    # 🔄 AÑADIR VOLUME WINDOWS (vol_1min, vol_5min, etc.)
                    if volume_window_tracker:
                        vol_windows = volume_window_tracker.get_all_windows(symbol)
                        ticker_data['vol_1min'] = vol_windows.vol_1min
                        ticker_data['vol_5min'] = vol_windows.vol_5min
                        ticker_data['vol_10min'] = vol_windows.vol_10min
                        ticker_data['vol_15min'] = vol_windows.vol_15min
                        ticker_data['vol_30min'] = vol_windows.vol_30min
                    
                    # 🔄 AÑADIR PRICE CHANGE WINDOWS (chg_1min, chg_5min, etc.)
                    if price_window_tracker:
                        price_windows = price_window_tracker.get_all_windows(symbol)
                        ticker_data['chg_1min'] = price_windows.chg_1min
                        ticker_data['chg_5min'] = price_windows.chg_5min
                        ticker_data['chg_10min'] = price_windows.chg_10min
                        ticker_data['chg_15min'] = price_windows.chg_15min
                        ticker_data['chg_30min'] = price_windows.chg_30min
                    
                    # 🔥 AÑADIR TRADES ANOMALY DETECTION (Z-Score)
                    # Obtener trades de hoy desde el tracker (acumulado desde WebSocket aggregates)
                    trades_today = 0
                    if trades_count_tracker:
                        trades_today = trades_count_tracker.get_trades_today(symbol) or 0
                    if trades_anomaly_detector and trades_today > 0:
                        anomaly_result = await trades_anomaly_detector.detect_anomaly(
                            symbol=symbol,
                            trades_today=trades_today
                        )
                        if anomaly_result:
                            ticker_data['trades_today'] = anomaly_result.trades_today
                            ticker_data['avg_trades_5d'] = round(anomaly_result.avg_trades_5d, 0)
                            ticker_data['trades_z_score'] = round(anomaly_result.z_score, 2)
                            ticker_data['is_trade_anomaly'] = anomaly_result.is_anomaly
                        else:
                            ticker_data['trades_today'] = trades_today
                            ticker_data['avg_trades_5d'] = None
                            ticker_data['trades_z_score'] = None
                            ticker_data['is_trade_anomaly'] = False
                    else:
                        ticker_data['trades_today'] = trades_today if trades_today > 0 else None
                        ticker_data['avg_trades_5d'] = None
                        ticker_data['trades_z_score'] = None
                        ticker_data['is_trade_anomaly'] = False
                    
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

