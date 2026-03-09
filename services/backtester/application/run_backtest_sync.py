"""Execute a single backtest job (template or code). Async, used by worker with asyncio.run()."""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable

import numpy as np
import structlog

from core.code_executor import CodeExecutor
from core.data_layer import DataLayer
from core.engine import BacktestEngine
from core.metrics import compute_advanced_metrics
from core.models import BacktestRequest, BacktestResponse, CodeBacktestRequest
from analysis.walk_forward import WalkForwardAnalyzer
from analysis.monte_carlo import MonteCarloAnalyzer

logger = structlog.get_logger(__name__)


def _sanitize_response(resp: BacktestResponse) -> BacktestResponse:
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

    return BacktestResponse.model_validate(_fix(raw))


def _noop_progress(_m: str, _p: float) -> None:
    pass


async def execute_backtest_job(
    job_type: str,
    payload: dict[str, Any],
    data_layer: DataLayer,
    engine: BacktestEngine | None,
    progress_callback: Callable[[str, float], None] | None = None,
) -> BacktestResponse:
    _p = progress_callback if progress_callback is not None else _noop_progress
    if job_type == "template":
        req = BacktestRequest.model_validate(payload)
        return await _run_template(req, data_layer, engine, _p)
    if job_type == "code":
        req = CodeBacktestRequest.model_validate(payload)
        return await _run_code(req, data_layer)
    raise ValueError(f"Unknown job_type: {job_type}")


async def _run_template(
    request: BacktestRequest,
    data_layer: DataLayer,
    engine: BacktestEngine | None,
) -> BacktestResponse:
    if engine is None:
        raise RuntimeError("Engine not available")
    try:
        s = request.strategy
        is_intraday = s.timeframe in ("1min", "5min", "15min", "30min", "1h")
        if is_intraday:
            max_days = 60
            delta = (s.end_date - s.start_date).days
            if delta > max_days:
                logger.warning("intraday_range_capped", original_days=delta, max_days=max_days)
                s = s.model_copy(update={"start_date": s.end_date - timedelta(days=max_days)})

        result = await engine.run(s, progress_callback=progress_callback)

        if request.include_advanced_metrics:
            try:
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


async def _run_code(request: CodeBacktestRequest, data_layer: DataLayer) -> BacktestResponse:
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
                error=f"No data for {request.tickers} between {request.start_date} and {request.end_date}",
            )

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
