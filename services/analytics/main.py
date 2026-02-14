"""
Analytics Service - Main Entry Point

SLIM orchestrator: lifecycle management, event handling, and API endpoints.
All processing logic is delegated to specialized modules:

- enrichment/pipeline.py: Enrichment loop + change detection + Redis Hash write
- bar_engine.py: In-memory minute bars + talipp streaming indicators (RSI, MACD, etc.)
- consumers/: Stream consumers (VWAP, volume windows, price windows, minute bars)
- timescale_bar_writer.py: Async persistence of minute bars to TimescaleDB
- indicators/: Indicator interface and registry (extensible)

ARCHITECTURE:
    snapshot:polygon:latest (JSON STRING) 
        → EnrichmentPipeline → snapshot:enriched:latest (Redis HASH, incremental)
    
    stream:realtime:aggregates (A.* per-second, ~643 subscribed tickers)
        → VwapConsumer → vwap_cache (in-memory)
        → VolumeWindowConsumer → VolumeWindowTracker (NumPy buffers)
        → PriceWindowConsumer → PriceWindowTracker (NumPy buffers)
        → TradesCountTracker (in-memory accumulator)
    
    stream:market:minutes (AM.* per-minute, entire market ~11K tickers)
        → MinuteBarConsumer → BarEngine (talipp indicators, ring buffers)
        → TimescaleBarWriter → minute_bars table (async, fire-and-forget)
    
    Priority: A.* per-second > AM.* per-minute for vol/chg windows.
    BarEngine provides: RSI, EMA, MACD, BB, ADX, Stoch for 100% of market.

EVENT-DRIVEN:
- Subscribes to DAY_CHANGED and SESSION_CHANGED via EventBus
- Resets caches + BarEngine on new trading day (DAY_CHANGED)
- Writes last_close snapshot on market close (SESSION_CHANGED)
"""

import asyncio
from datetime import datetime, date
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
from shared.events import EventBus, EventType, Event

# Existing indicator implementations
from rvol_calculator import RVOLCalculator
from shared.utils.atr_calculator import ATRCalculator
from intraday_tracker import IntradayTracker
from http_clients import http_clients
from volume_window_tracker import VolumeWindowTracker
from price_window_tracker import PriceWindowTracker
from trades_anomaly_detector import TradesAnomalyDetector
from trades_count_tracker import TradesCountTracker

# New modular components
from enrichment.pipeline import EnrichmentPipeline
from consumers.vwap_consumer import VwapConsumer
from consumers.volume_window_consumer import VolumeWindowConsumer
from consumers.price_window_consumer import PriceWindowConsumer
from consumers.minute_bar_consumer import MinuteBarConsumer
from bar_engine import BarEngine
from timescale_bar_writer import TimescaleBarWriter

# Configure logger
configure_logging(service_name="analytics")
logger = get_logger(__name__)


# ============================================================================
# Global State
# ============================================================================

redis_client: Optional[RedisClient] = None
timescale_client: Optional[TimescaleClient] = None
event_bus: Optional[EventBus] = None

# Indicator instances
rvol_calculator: Optional[RVOLCalculator] = None
atr_calculator: Optional[ATRCalculator] = None
intraday_tracker: Optional[IntradayTracker] = None
volume_window_tracker: Optional[VolumeWindowTracker] = None
price_window_tracker: Optional[PriceWindowTracker] = None
trades_anomaly_detector: Optional[TradesAnomalyDetector] = None
trades_count_tracker: Optional[TradesCountTracker] = None

# Pipeline and consumer instances
enrichment_pipeline: Optional[EnrichmentPipeline] = None
vwap_consumer: Optional[VwapConsumer] = None
volume_consumer: Optional[VolumeWindowConsumer] = None
price_consumer: Optional[PriceWindowConsumer] = None
bar_engine: Optional[BarEngine] = None
minute_bar_consumer: Optional[MinuteBarConsumer] = None
timescale_bar_writer: Optional[TimescaleBarWriter] = None

# Background tasks
pipeline_task: Optional[asyncio.Task] = None
vwap_consumer_task: Optional[asyncio.Task] = None
volume_consumer_task: Optional[asyncio.Task] = None
price_consumer_task: Optional[asyncio.Task] = None
trades_tracker_task: Optional[asyncio.Task] = None
minute_bar_consumer_task: Optional[asyncio.Task] = None
timescale_writer_task: Optional[asyncio.Task] = None

# Market state (updated via EventBus)
is_holiday_mode: bool = False
current_trading_date: Optional[date] = None

# Shared VWAP cache (written by VwapConsumer, read by EnrichmentPipeline)
vwap_cache: Dict[str, float] = {}


# ============================================================================
# Market Status (Event-Driven)
# ============================================================================

async def check_initial_market_status() -> None:
    """Read market state ONCE on startup."""
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
                "market_status_checked",
                is_holiday=is_holiday,
                is_trading_day=is_trading_day,
                holiday_mode=is_holiday_mode,
                trading_date=trading_date_str
            )
        else:
            logger.warning("market_status_not_found_in_redis")
            is_holiday_mode = False
    except Exception as e:
        logger.error("error_checking_market_status", error=str(e))
        is_holiday_mode = False


async def handle_day_changed(event: Event) -> None:
    """Handler for DAY_CHANGED event. Resets all caches if not holiday."""
    global is_holiday_mode, current_trading_date, vwap_cache
    
    new_date_str = event.data.get('new_date')
    logger.info("day_changed_event_received", new_date=new_date_str)
    
    await check_initial_market_status()
    
    # Sync pipeline's holiday mode with global state
    if enrichment_pipeline:
        enrichment_pipeline.is_holiday_mode = is_holiday_mode
    
    if not is_holiday_mode:
        logger.info("resetting_analytics_caches", reason="new_trading_day")
        
        if rvol_calculator:
            await rvol_calculator.reset_for_new_day()
        if intraday_tracker:
            intraday_tracker.clear_for_new_day()
        
        old_vwap_size = len(vwap_cache)
        vwap_cache.clear()
        logger.info("vwap_cache_reset", old_size=old_vwap_size)
        
        if volume_window_tracker:
            cleared = volume_window_tracker.clear_all()
            logger.info("volume_window_tracker_reset", symbols_cleared=cleared)
        if price_window_tracker:
            cleared = price_window_tracker.clear_all()
            logger.info("price_window_tracker_reset", symbols_cleared=cleared)
        if trades_anomaly_detector:
            await trades_anomaly_detector.reset_for_new_day()
            logger.info("trades_anomaly_detector_reset")
        if trades_count_tracker:
            trades_count_tracker.reset_for_new_day()
            logger.info("trades_count_tracker_reset")
        if bar_engine:
            bar_engine.reset()
            logger.info("bar_engine_reset")
        if enrichment_pipeline:
            enrichment_pipeline.clear_change_detector()
            logger.info("change_detector_reset")
    else:
        logger.info("skipping_cache_reset", reason="holiday_mode_active", date=new_date_str)


async def handle_session_changed(event: Event) -> None:
    """
    Handler for SESSION_CHANGED event.
    Writes last_close snapshot ONCE when market closes.
    """
    new_session = event.data.get('new_session')
    old_session = event.data.get('old_session')
    
    logger.info(
        "session_changed_event_received",
        old_session=old_session,
        new_session=new_session
    )
    
    # Write last_close when transitioning to POST_MARKET or CLOSED
    if new_session in ('POST_MARKET', 'CLOSED') and enrichment_pipeline:
        logger.info("writing_last_close_snapshot", trigger=f"{old_session}→{new_session}")
        await enrichment_pipeline.write_last_close_snapshot()


# ============================================================================
# Lifecycle
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    global redis_client, timescale_client, event_bus
    global rvol_calculator, atr_calculator, intraday_tracker
    global volume_window_tracker, price_window_tracker
    global trades_anomaly_detector, trades_count_tracker
    global enrichment_pipeline, vwap_consumer, volume_consumer, price_consumer
    global bar_engine, minute_bar_consumer, timescale_bar_writer
    global pipeline_task, vwap_consumer_task, volume_consumer_task
    global price_consumer_task, trades_tracker_task
    global minute_bar_consumer_task, timescale_writer_task
    
    logger.info("analytics_service_starting")
    
    # --- Initialize clients ---
    redis_client = RedisClient()
    await redis_client.connect()
    
    timescale_client = TimescaleClient()
    await timescale_client.connect()
    
    await http_clients.initialize(polygon_api_key=settings.POLYGON_API_KEY)
    
    # --- Initialize indicators ---
    rvol_calculator = RVOLCalculator(
        redis_client=redis_client,
        timescale_client=timescale_client,
        slot_size_minutes=5,
        lookback_days=5,
        include_extended_hours=True
    )
    atr_calculator = ATRCalculator(
        redis_client=redis_client,
        timescale_client=timescale_client,
        period=14, use_ema=True
    )
    intraday_tracker = IntradayTracker(polygon_api_key=settings.POLYGON_API_KEY)
    volume_window_tracker = VolumeWindowTracker()
    price_window_tracker = PriceWindowTracker()
    trades_anomaly_detector = TradesAnomalyDetector(
        redis_client=redis_client, lookback_days=5, z_score_threshold=3.0
    )
    trades_count_tracker = TradesCountTracker(redis_client=redis_client)
    
    logger.info("indicators_initialized")
    
    # --- Check market status ---
    await check_initial_market_status()
    
    # --- Initialize EventBus ---
    event_bus = EventBus(redis_client, "analytics")
    event_bus.subscribe(EventType.DAY_CHANGED, handle_day_changed)
    event_bus.subscribe(EventType.SESSION_CHANGED, handle_session_changed)
    await event_bus.start_listening()
    logger.info("eventbus_initialized", events=["DAY_CHANGED", "SESSION_CHANGED"])
    
    # --- Recover intraday data ---
    if not is_holiday_mode:
        try:
            snapshot_data = await redis_client.get("snapshot:polygon:latest")
            if snapshot_data:
                tickers_data = snapshot_data.get('tickers', [])
                active_symbols = [
                    t.get('ticker') for t in tickers_data
                    if t.get('ticker') and (
                        (t.get('min', {}).get('av', 0) > 0) or
                        (t.get('day', {}).get('v', 0) > 0)
                    )
                ]
                if active_symbols:
                    recovered = await intraday_tracker.recover_active_symbols(
                        active_symbols=active_symbols, max_symbols=100
                    )
                    logger.info("intraday_recovery_complete", recovered=recovered)
        except Exception as e:
            logger.warning("intraday_recovery_failed", error=str(e))
    
    # --- Initialize BarEngine (AM.* minute bars + streaming indicators) ---
    bar_engine = BarEngine()  # Uses DEFAULT_RING_SIZE (210)
    
    # --- Warmup BarEngine from TimescaleDB (load last 200 1-min bars) ---
    timescale_bar_writer = TimescaleBarWriter(
        timescale_client=timescale_client,
        bar_engine=bar_engine,
        persist_interval=60,
        warmup_minutes=200,
    )
    if not is_holiday_mode:
        try:
            warmup_bars = await timescale_bar_writer.warmup()
            logger.info("bar_engine_warmup_done", bars_loaded=warmup_bars)
        except Exception as e:
            logger.warning("bar_engine_warmup_failed", error=str(e))
    
    # --- Create enrichment pipeline (with BarEngine reference) ---
    enrichment_pipeline = EnrichmentPipeline(
        redis_client=redis_client,
        rvol_calculator=rvol_calculator,
        atr_calculator=atr_calculator,
        intraday_tracker=intraday_tracker,
        volume_window_tracker=volume_window_tracker,
        price_window_tracker=price_window_tracker,
        trades_anomaly_detector=trades_anomaly_detector,
        trades_count_tracker=trades_count_tracker,
        vwap_cache=vwap_cache,
        bar_engine=bar_engine,
    )
    enrichment_pipeline.is_holiday_mode = is_holiday_mode
    
    # --- Create consumers ---
    vwap_consumer = VwapConsumer(redis_client, vwap_cache)
    volume_consumer = VolumeWindowConsumer(
        redis_client, volume_window_tracker,
        is_holiday_check=lambda: is_holiday_mode
    )
    price_consumer = PriceWindowConsumer(
        redis_client, price_window_tracker,
        is_holiday_check=lambda: is_holiday_mode
    )
    minute_bar_consumer = MinuteBarConsumer(
        redis_client=redis_client,
        bar_engine=bar_engine,
    )
    
    # --- Start background tasks ---
    pipeline_task = asyncio.create_task(enrichment_pipeline.run_loop())
    vwap_consumer_task = asyncio.create_task(vwap_consumer.run())
    volume_consumer_task = asyncio.create_task(volume_consumer.run())
    price_consumer_task = asyncio.create_task(price_consumer.run())
    trades_tracker_task = asyncio.create_task(trades_count_tracker.run_consumer())
    minute_bar_consumer_task = asyncio.create_task(minute_bar_consumer.run())
    timescale_writer_task = asyncio.create_task(timescale_bar_writer.run())
    
    logger.info(
        "analytics_service_started",
        tasks=["pipeline", "vwap", "volume_windows", "price_windows", "trades",
               "minute_bar_consumer", "timescale_writer"],
        bar_engine_symbols=bar_engine.symbol_count,
    )
    
    yield
    
    # --- Shutdown ---
    logger.info("analytics_service_shutting_down")
    
    for task_name, task in [
        ("pipeline", pipeline_task),
        ("vwap_consumer", vwap_consumer_task),
        ("volume_consumer", volume_consumer_task),
        ("price_consumer", price_consumer_task),
        ("trades_tracker", trades_tracker_task),
        ("minute_bar_consumer", minute_bar_consumer_task),
        ("timescale_writer", timescale_writer_task),
    ]:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info(f"{task_name}_stopped")
    
    if trades_count_tracker:
        await trades_count_tracker.stop()
    if event_bus:
        await event_bus.stop_listening()
    if rvol_calculator:
        await rvol_calculator.close()
    if trades_anomaly_detector:
        await trades_anomaly_detector.close()
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
    description="Enrichment pipeline with incremental Redis Hash writes",
    version="2.0.0",
    lifespan=lifespan
)


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "analytics",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/stats")
async def get_stats():
    """Get service statistics including pipeline and change detection stats."""
    if not rvol_calculator:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    stats = {
        "rvol": rvol_calculator.get_cache_stats(),
        "pipeline": enrichment_pipeline.get_stats() if enrichment_pipeline else None,
        "bar_engine": bar_engine.get_stats() if bar_engine else None,
        "minute_bar_consumer": minute_bar_consumer.get_stats() if minute_bar_consumer else None,
        "timescale_writer": timescale_bar_writer.get_stats() if timescale_bar_writer else None,
        "volume_tracker": volume_window_tracker.get_stats() if volume_window_tracker else None,
        "price_tracker": price_window_tracker.get_stats() if price_window_tracker else None,
        "vwap_cache_size": len(vwap_cache),
        "is_holiday_mode": is_holiday_mode,
    }
    
    return JSONResponse(content=stats)


@app.get("/rvol/{symbol}")
async def get_rvol(symbol: str):
    """Get current RVOL for a symbol."""
    if not rvol_calculator:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    symbol = symbol.upper()
    rvol_str = await redis_client.client.hget("rvol:current_slot", symbol)
    
    if rvol_str is None:
        raise HTTPException(status_code=404, detail=f"No RVOL data for {symbol}")
    
    current_slot = rvol_calculator.slot_manager.get_current_slot()
    
    return {
        "symbol": symbol,
        "rvol": round(float(rvol_str), 2),
        "slot": current_slot,
        "slot_info": rvol_calculator.slot_manager.format_slot_info(current_slot),
        "timestamp": datetime.now().isoformat()
    }


@app.post("/rvol/batch")
async def get_rvol_batch(symbols: list[str]):
    """Get RVOL for multiple symbols."""
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
    """Reset caches (admin/debug only)."""
    if not rvol_calculator:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    await rvol_calculator.reset_for_new_day()
    return {"status": "success", "message": "Cache reset completed"}


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
        log_config=None
    )
