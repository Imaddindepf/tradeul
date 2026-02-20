"""
TradeUL Professional Backtester Service

Standalone microservice for strategy backtesting via Polygon FLATS data.
Split-adjusted, vectorized, with walk-forward and Monte Carlo analysis.
"""
from contextlib import asynccontextmanager
from typing import Optional

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from core.data_layer import DataLayer
from core.engine import BacktestEngine
from core.metrics import compute_advanced_metrics
from core.models import BacktestRequest, BacktestResponse
from core.split_adjuster import SplitAdjuster
from core.charts import generate_full_dashboard
from analysis.walk_forward import WalkForwardAnalyzer
from analysis.monte_carlo import MonteCarloAnalyzer

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger(__name__)

data_layer: Optional[DataLayer] = None
engine: Optional[BacktestEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global data_layer, engine

    logger.info("backtester_starting", data_dir=str(settings.polygon_data_dir))

    adjuster = SplitAdjuster(
        polygon_api_key=settings.polygon_api_key,
        cache_dir=settings.splits_cache_dir,
        cache_ttl_hours=settings.splits_cache_ttl_hours,
    )
    data_layer = DataLayer(
        polygon_data_dir=settings.polygon_data_dir,
        split_adjuster=adjuster,
    )
    engine = BacktestEngine(data_layer)

    logger.info("backtester_ready")
    yield

    if data_layer:
        data_layer.close()
    logger.info("backtester_stopped")


app = FastAPI(
    title="TradeUL Backtester",
    description="Professional backtesting engine with split-adjusted Polygon FLATS",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.service_name, "version": "1.0.0"}


@app.post("/api/v1/backtest", response_model=BacktestResponse)
async def run_backtest(request: BacktestRequest):
    if engine is None:
        raise HTTPException(503, "Service not ready")
    try:
        result = await engine.run(request.strategy)

        if request.include_advanced_metrics:
            import numpy as np
            eq_arr = np.array([e[1] for e in result.equity_curve])
            result.advanced_metrics = compute_advanced_metrics(
                result.trades, eq_arr,
                result.core_metrics.sharpe_ratio,
                request.strategy.risk_free_rate,
                request.n_trials_for_dsr,
            )

        if request.include_walk_forward and data_layer:
            wf = WalkForwardAnalyzer(engine)
            bars = await data_layer.load_day_bars_adjusted(
                request.strategy.start_date,
                request.strategy.end_date,
                request.strategy.universe.tickers,
            )
            bars = data_layer.add_indicators_sql(bars)
            result.walk_forward = await wf.analyze(
                request.strategy, bars, request.walk_forward_splits)

        if request.include_monte_carlo:
            mc = MonteCarloAnalyzer()
            result.monte_carlo = mc.simulate(
                result.trades, request.monte_carlo_simulations,
                request.strategy.initial_capital)

        charts = generate_full_dashboard(result)
        return BacktestResponse(status="success", result=result)

    except ValueError as e:
        return BacktestResponse(status="error", error=str(e))
    except Exception as e:
        logger.error("backtest_failed", error=str(e))
        return BacktestResponse(status="error", error=f"Internal error: {str(e)}")


@app.get("/api/v1/backtest/indicators")
async def list_indicators():
    return {
        "indicators": [
            {"name": "close", "description": "Close price"},
            {"name": "open", "description": "Open price"},
            {"name": "high", "description": "High price"},
            {"name": "low", "description": "Low price"},
            {"name": "volume", "description": "Volume"},
            {"name": "vwap", "description": "VWAP"},
            {"name": "gap_pct", "description": "Gap percentage from prev close"},
            {"name": "rvol", "description": "Relative volume (vs 20d avg)"},
            {"name": "rsi_14", "description": "RSI 14-period"},
            {"name": "sma_20", "description": "Simple Moving Average 20"},
            {"name": "sma_50", "description": "Simple Moving Average 50"},
            {"name": "atr_14", "description": "Average True Range 14"},
            {"name": "range_pct", "description": "Bar range percentage"},
            {"name": "avg_volume_20d", "description": "20-day average volume"},
            {"name": "prev_close", "description": "Previous bar close"},
            {"name": "high_20d", "description": "20-day rolling high"},
            {"name": "low_20d", "description": "20-day rolling low"},
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
