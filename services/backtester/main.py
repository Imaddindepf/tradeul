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
from core.models import BacktestRequest, BacktestResponse, CodeBacktestRequest
from core.code_executor import CodeExecutor
from core.adhoc_executor import AdHocExecutor
from core.charts import generate_full_dashboard
from analysis.walk_forward import WalkForwardAnalyzer
from analysis.monte_carlo import MonteCarloAnalyzer
from infrastructure.job_repository import RedisJobRepository
from infrastructure.queue import RedisJobQueue
from api.routes.jobs import router as jobs_router

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

    rest_cache = settings.splits_cache_dir.parent / "rest_cache"
    data_layer = DataLayer(
        polygon_data_dir=settings.polygon_data_dir,
        polygon_api_key=settings.polygon_api_key,
        rest_cache_dir=rest_cache,
        minute_aggs_dir=settings.minute_aggs_dir,
    )
    engine = BacktestEngine(data_layer)

    try:
        repo = RedisJobRepository(settings.redis_url, settings.job_result_ttl_seconds)
        queue = RedisJobQueue(settings.redis_url, settings.jobs_queue_name)
        app.state.job_repository = repo
        app.state.job_queue = queue
    except Exception as e:
        logger.warning("jobs_not_available", error=str(e))
        app.state.job_repository = None
        app.state.job_queue = None

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

app.include_router(jobs_router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.service_name, "version": "1.0.0"}


@app.post("/api/v1/backtest")
async def run_backtest(request: BacktestRequest):
    if engine is None:
        raise HTTPException(503, "Service not ready")
    try:
        from datetime import timedelta
        s = request.strategy
        is_intraday = s.timeframe in ("1min", "5min", "15min", "30min", "1h")
        if is_intraday:
            max_days = 60
            delta = (s.end_date - s.start_date).days
            if delta > max_days:
                logger.warning("intraday_range_capped", original_days=delta, max_days=max_days)
                s.start_date = s.end_date - timedelta(days=max_days)

        result = await engine.run(request.strategy)

        if request.include_advanced_metrics:
            try:
                import numpy as np
                eq_arr = np.array([e[1] for e in result.equity_curve])
                result.advanced_metrics = compute_advanced_metrics(
                    result.trades, eq_arr,
                    result.core_metrics.sharpe_ratio,
                    request.strategy.risk_free_rate,
                    request.n_trials_for_dsr,
                )
            except Exception as exc:
                logger.warning("advanced_metrics_skipped", error=str(exc))

        if request.include_walk_forward and data_layer:
            try:
                wf = WalkForwardAnalyzer(engine)
                bars = await data_layer.load_day_bars_adjusted(
                    request.strategy.start_date,
                    request.strategy.end_date,
                    request.strategy.universe.tickers,
                )
                bars = data_layer.add_indicators_sql(bars)
                result.walk_forward = await wf.analyze(
                    request.strategy, bars, request.walk_forward_splits)
            except Exception as exc:
                logger.warning("walk_forward_skipped", error=str(exc))

        if request.include_monte_carlo:
            try:
                mc = MonteCarloAnalyzer()
                result.monte_carlo = mc.simulate(
                    result.trades, request.monte_carlo_simulations,
                    request.strategy.initial_capital)
            except Exception as exc:
                logger.warning("monte_carlo_skipped", error=str(exc))

        return _sanitize_response(BacktestResponse(status="success", result=result))

    except ValueError as e:
        return BacktestResponse(status="error", error=str(e))
    except Exception as e:
        logger.error("backtest_failed", error=str(e))
        return BacktestResponse(status="error", error=f"Internal error: {str(e)}")


def _sanitize_response(resp: BacktestResponse) -> dict:
    """Replace NaN/Inf with None so JSON serialization succeeds."""
    import math

    raw = resp.model_dump()

    def _fix(obj):
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return None
        if isinstance(obj, dict):
            return {k: _fix(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_fix(v) for v in obj]
        return obj

    return _fix(raw)


@app.post("/api/v1/backtest/code")
async def run_code_backtest(request: CodeBacktestRequest):
    """Execute LLM-generated Python strategy code against market data."""
    if data_layer is None:
        raise HTTPException(503, "Service not ready")
    try:
        if request.timeframe == "1d":
            bars = await data_layer.load_day_bars_adjusted(
                request.start_date, request.end_date, request.tickers)
        else:
            bars = await data_layer.load_minute_bars_adjusted(
                request.start_date, request.end_date, request.tickers)

        if bars.empty:
            return BacktestResponse(
                status="error",
                error=f"No data for {request.tickers} "
                      f"between {request.start_date} and {request.end_date}",
            )

        logger.info("code_backtest_data_loaded", rows=len(bars),
                     tickers=bars["ticker"].nunique())

        bars = data_layer.add_indicators_sql(bars)

        executor = CodeExecutor(timeout_seconds=300)
        result = executor.execute(
            code=request.code,
            bars=bars,
            initial_capital=request.initial_capital,
            slippage_bps=request.slippage_bps,
            commission=request.commission_per_trade,
            risk_free_rate=request.risk_free_rate,
            strategy_name=request.strategy_name,
            strategy_description=request.strategy_description,
        )

        if request.include_advanced_metrics:
            try:
                import numpy as np
                eq_arr = np.array([e[1] for e in result.equity_curve])
                result.advanced_metrics = compute_advanced_metrics(
                    result.trades, eq_arr,
                    result.core_metrics.sharpe_ratio,
                    request.risk_free_rate, 1)
            except Exception as exc:
                logger.warning("advanced_metrics_skipped", error=str(exc))

        if request.include_monte_carlo and result.trades:
            try:
                mc = MonteCarloAnalyzer()
                result.monte_carlo = mc.simulate(
                    result.trades, request.monte_carlo_simulations,
                    request.initial_capital)
            except Exception as exc:
                logger.warning("monte_carlo_skipped", error=str(exc))

        return _sanitize_response(BacktestResponse(status="success", result=result))

    except ValueError as e:
        return BacktestResponse(status="error", error=str(e))
    except Exception as e:
        logger.error("code_backtest_failed", error=str(e))
        return BacktestResponse(status="error", error=f"Internal error: {str(e)}")


@app.post("/api/v1/execute")
async def execute_adhoc(request: dict):
    """
    Execute ad-hoc Python code in a sandboxed environment with market data helpers.

    Request body:
        {
          "code": "...",          // Python code to execute
          "timeout_seconds": 30   // optional, default 30, max 60
        }

    Injected helpers available in the code:
        historical_query(ticker, start, end, interval="1d") -> DataFrame
        live_quote(ticker) -> dict
        run_sql(query) -> DataFrame
        register_df(name, df) -> None
        save_output(data, label="result") -> None
        save_chart(fig, label="chart") -> None

    Returns:
        {
          "status": "success" | "error",
          "outputs": {label: data},
          "charts": {label: "<base64-png>"},
          "prints": ["..."],
          "error": str | null,
          "traceback": str | null,
          "execution_ms": int
        }
    """
    if data_layer is None:
        raise HTTPException(503, "Service not ready")

    code = request.get("code", "").strip()
    if not code:
        raise HTTPException(400, "Field 'code' is required and cannot be empty")

    timeout = min(int(request.get("timeout_seconds", 30)), 60)

    executor = AdHocExecutor(
        data_layer=data_layer,
        redis_url=settings.redis_url,
        redis_snapshot_url=settings.redis_snapshot_url or None,
        timeout_seconds=timeout,
    )

    try:
        result = executor.execute(code)
    except Exception as exc:
        logger.error("adhoc_execute_failed", error=str(exc))
        return {
            "status": "error",
            "outputs": {},
            "charts": {},
            "prints": [],
            "error": f"Internal error: {exc}",
            "traceback": None,
            "execution_ms": 0,
        }

    return result


@app.post("/api/v1/backtest/natural")
async def backtest_natural_stub():
    """Natural language backtest: use the AI Agent instead.
    POST to Agent: /api/backtest/submit-natural with { \"prompt\", \"tickers\" } to get job_id.
    Then poll GET /api/v1/jobs/{job_id} on this backtester."""
    raise HTTPException(
        501,
        detail=(
            "Use the AI Agent for natural language: POST /api/backtest/submit-natural "
            "with body { \"prompt\": \"...\", \"tickers\": [\"SPY\"] }. "
            "Agent returns job_id; poll GET /api/v1/jobs/{job_id} on this service."
        ),
    )


@app.get("/api/v1/backtest/indicators")
async def list_indicators():
    return {
        "indicators": [
            {"name": "close", "description": "Close price"},
            {"name": "open", "description": "Open price"},
            {"name": "high", "description": "High price"},
            {"name": "low", "description": "Low price"},
            {"name": "volume", "description": "Volume"},
            {"name": "high_20d", "description": "20-day rolling high"},
            {"name": "low_20d", "description": "20-day rolling low"},
            {"name": "gap_pct", "description": "Gap percentage from prev close"},
            {"name": "rvol", "description": "Relative volume (vs 20d avg)"},
            {"name": "rsi_14", "description": "RSI 14-period"},
            {"name": "sma_20", "description": "Simple Moving Average 20"},
            {"name": "sma_50", "description": "Simple Moving Average 50"},
            {"name": "sma_200", "description": "Simple Moving Average 200"},
            {"name": "atr_14", "description": "Average True Range 14"},
            {"name": "range_pct", "description": "Bar range percentage"},
            {"name": "avg_volume_20d", "description": "20-day average volume"},
            {"name": "prev_close", "description": "Previous bar close"},
            {"name": "ema_9", "description": "Exponential Moving Average 9"},
            {"name": "ema_21", "description": "Exponential Moving Average 21"},
            {"name": "vwap", "description": "Volume-Weighted Average Price"},        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
