"""
TradeUL Professional Backtester Service

Standalone microservice for strategy backtesting via Polygon FLATS data.
Split-adjusted, vectorized, with walk-forward and Monte Carlo analysis.
"""
import os as _os
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

    # ── Validación de frontera (Fase 1 §5.2-①): 422 con la lista exacta.
    # El motor vectorizado solo ejecuta su subconjunto; lo que no conozca
    # NO se convierte en una máscara vacía nunca más.
    from core.event_translator import is_event_supported, get_supported_events
    from core.filter_evaluator import get_supported_filters
    _s = request.strategy
    _unknown_events = sorted({
        e for e in [*(_s.entry_events or []), *(_s.exit_events or [])]
        if not is_event_supported(e)
    })
    _legacy_keys = set()
    for _f in get_supported_filters():
        _legacy_keys.add(_f["min_key"])
        _legacy_keys.add(_f["max_key"])
    _unknown_filters = sorted(
        k for k in {**(_s.entry_filters or {}), **(_s.universe_filters or {})}
        if k not in _legacy_keys
    )
    if _unknown_events or _unknown_filters:
        raise HTTPException(422, detail={
            "error": "unsupported_by_backtester",
            "unknown_events": _unknown_events,
            "unknown_filters": _unknown_filters,
            "supported_events": get_supported_events(),
            "supported_filters": sorted(_legacy_keys),
        })

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


# /api/v1/execute (ejecucion ad-hoc de codigo) ELIMINADO 2026-08-02:
# RCE sin autenticacion (auditoria F0) y CERO consumidores medidos en todo el
# repo. El camino legitimo de backtests por codigo sigue siendo la cola de
# jobs (job_type="code" -> application/run_backtest_sync.py).


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


# Eventos que el traductor registra pero que NO miden lo que su nombre promete.
# Se sirven aparte para que la UI pueda ofrecerlos degradados en vez de
# presentarlos como equivalentes a los correctos. Medido 2026-08-01.
_DEGRADED_EVENTS: dict[str, str] = {
    "block_trade": "dispara en el 100% de las barras",
    "gap_reversal": "no comprueba el cruce, solo el signo del gap",
    "running_up_confirmed": "no confirma por volumen",
    "running_down_confirmed": "no confirma por volumen",
    "running_up_sustained": "no confirma por volumen",
    "running_down_sustained": "no confirma por volumen",
}


@app.post("/api/v1/backtest/triggers")
async def analyze_triggers(request: dict):
    """Análisis de disparos L0 (Fase 1 §7.1): eventos REALES del lake.

    Request: {"strategy": {"event_types": [...], ...filtros BUILD},
              "date_from": "YYYY-MM-DD", "date_to": "YYYY-MM-DD"}
    422 con listas exactas si algo no se reconoce. El resultado lleva
    warnings y estado por día (snapshot, data_holes) — la honestidad es
    parte del contrato, la UI debe renderizarlos siempre.
    """
    import json as _json
    import os as _os

    import anyio

    from analysis.triggers import TriggerAnalyzer
    from matching import boundary

    strategy = request.get("strategy") or {}
    date_from = request.get("date_from")
    date_to = request.get("date_to")
    if not strategy or not date_from or not date_to:
        raise HTTPException(422, detail={"error": "strategy, date_from y date_to son obligatorios"})

    problems = boundary.validate_strategy(strategy)
    if problems["unknown_events"] or problems["unknown_filters"]:
        raise HTTPException(422, detail={"error": "unknown_vocabulary", **problems})

    analyzer = TriggerAnalyzer(
        lake_dir=_os.getenv("LAKE_DIR", "/data/lake"),
        minute_dir=_os.getenv("MINUTE_AGGS_DIR", "/data/polygon/minute_aggs"),
    )
    try:
        return await anyio.to_thread.run_sync(
            lambda: analyzer.run(strategy, str(date_from), str(date_to))
        )
    except ValueError as exc:
        try:
            raise HTTPException(422, detail=_json.loads(str(exc)))
        except _json.JSONDecodeError:
            raise HTTPException(422, detail={"error": str(exc)})



def _dt_dir_range(root, prefix="dt="):
    """Rango medido de particiones dt= de un directorio del lake (o None)."""
    try:
        days = sorted(d[len(prefix):] for d in _os.listdir(root) if d.startswith(prefix))
    except OSError:
        return None
    if not days:
        return None
    return {"from": days[0], "to": days[-1], "days": len(days)}


def _flatfile_range(root):
    """Rango medido de flat files fechados YYYY-MM-DD.* (minuto de Polygon)."""
    try:
        names = sorted(f[:10] for f in _os.listdir(root) if f[:4].isdigit())
    except OSError:
        return None
    if not names:
        return None
    return {"from": names[0], "to": names[-1], "days": len(names)}


_SOURCE_SEMANTICS = {
    "event":    {"support": "exact",
                 "note": "viaja en el payload del evento: valor point-in-time del disparo"},
    "clock":    {"support": "exact",
                 "note": "derivado del timestamp del evento"},
    "snapshot": {"support": "degraded",
                 "note": "aproximado con el slow snapshot del CIERRE del día; días sin snapshot se omiten con aviso"},
    "index":    {"support": "degraded",
                 "note": "barras 1-min de SPY/QQQ/DIA en el instante del disparo (el vivo usa ventanas de 1 s)"},
    "quality":  {"support": "conditional",
                 "note": "aq: solo en días cuyas particiones persisten quality; el resto se omite con aviso"},
}


def _trigger_analysis_capabilities() -> dict:
    """Capacidades del análisis de disparos L0: vocabulario BUILD completo."""
    import json as _json

    from matching import boundary

    events = sorted(boundary.valid_event_types())

    cat_path = _os.path.join(
        _os.getenv("SHARED_CONFIG_DIR", "/app/shared/config"), "filter_catalog.json")
    filters_by_semantics: dict = {}
    try:
        cat = _json.loads(open(cat_path, encoding="utf-8").read())
        keys = []
        for e in cat["filters"]:
            if "events" not in e.get("scopes", []):
                continue
            for side in ("paramMin", "paramMax"):
                if e.get(side):
                    keys.append(e[side])
        sources = boundary.classify_filters({k: 1 for k in keys})
        for k in keys:
            src = sources.get(k, "snapshot")
            sem = _SOURCE_SEMANTICS[src]["support"]
            filters_by_semantics.setdefault(f"{sem}:{src}", []).append(k)
        for v in filters_by_semantics.values():
            v.sort()
    except OSError:
        filters_by_semantics = {"error": "filter_catalog.json no accesible"}

    return {
        "engine": "L0 — eventos reales del lake, matcher portado (paridad verificada)",
        "endpoint": "/api/v1/backtest/triggers",
        "events": {
            "supported": events,
            "count": len(events),
            "note": "TODOS los tipos de BUILD: los disparos son alertas reales grabadas, no hay traducción",
        },
        "filters": {
            "all_build_filters_supported": True,
            "by_semantics": filters_by_semantics,
            "aq": _SOURCE_SEMANTICS["quality"],
            "semantics": _SOURCE_SEMANTICS,
        },
    }


@app.get("/api/v1/backtest/capabilities")
async def list_capabilities():
    """
    Qué puede ejecutar de verdad este motor.

    Existía desde siempre en `get_supported_events()` / `get_supported_filters()`
    y no lo llamaba nadie: la UI ofrecía los 158 eventos del catálogo de alertas
    y `translate_event` devolvía todo-False para los ~85 que no están
    registrados, sin avisar. Con esto el frontend puede decir la verdad.
    """
    from core.event_translator import get_supported_events
    from core.filter_evaluator import get_supported_filters
    from core.models import ExitType, SlippageModel, Timeframe, UniverseMethod

    supported = get_supported_events()
    filters = get_supported_filters()

    return {
        "events": {
            "supported": supported,
            "degraded": {k: v for k, v in _DEGRADED_EVENTS.items() if k in supported},
            "count": len(supported),
        },
        "filters": {
            # `min_<key>` / `max_<key>` es el contrato que espera entry_filters.
            "keys": [f["min_key"][4:] for f in filters],
            "meta": filters,
            "count": len(filters),
        },
        "timeframes": {
            "supported": [t.value for t in Timeframe],
            # El motor no reagrupa barras: pedir 1min y 1h devuelve lo mismo.
            # Hasta que exista el resample, solo el diario es de fiar.
            "resampled": ["1d"],
        },
        "universe_methods": [m.value for m in UniverseMethod],
        "exit_types": [e.value for e in ExitType],
        "slippage_models": [s.value for s in SlippageModel],
        # Reglas de validación que StrategyConfig aplica y la UI debería
        # comprobar antes de mandar, en vez de comerse un 422.
        "limits": {"min_days_daily": 30, "min_days_intraday": 5},
        # ── Eje temporal (§5.2-②/§7.3): qué es exacto, aproximado o imposible
        # y DESDE CUÁNDO. Medido de las particiones reales en cada request.
        # ── Capacidades POR PRODUCTO. Los campos legacy de arriba (events 73,
        # filters 34) describen SOLO el simulador vectorizado viejo; el
        # análisis de disparos L0 soporta el vocabulario COMPLETO de BUILD por
        # construcción (eventos = alertas reales grabadas; filtros = matcher
        # portado). La UI debe etiquetar contra el producto que use.
        "trigger_analysis": _trigger_analysis_capabilities(),
        "data_axis": {
            "events_lake": {
                "range": _dt_dir_range(_os.path.join(_os.getenv("LAKE_DIR", "/data/lake"), "events")),
                "semantics": "exact",
                "note": "disparos L0 = alertas reales grabadas; la familia de quotes solo existe aquí y es irreproducible antes del inicio del lake",
            },
            "slow_snapshot": {
                "range": _dt_dir_range(_os.path.join(_os.getenv("LAKE_DIR", "/data/lake"), "reference", "enriched_close")),
                "semantics": "degraded",
                "note": "filtros de snapshot en L0: aproximados con el enriched del cierre del día; los días sin snapshot se omiten con aviso",
            },
            "reference_pit": {
                "range": _dt_dir_range(_os.path.join(_os.getenv("LAKE_DIR", "/data/lake"), "reference", "metadata")),
                "semantics": "exact",
                "note": "metadata point-in-time de todos los tickers (vivos y muertos); antes de su inicio hay sesgo de supervivencia",
            },
            "minute_raw": {
                "range": _flatfile_range(_os.getenv("MINUTE_AGGS_DIR", "/data/polygon/minute_aggs")),
                "semantics": "exact",
                "note": "OHLCV 1-min sesión extendida; sustrato de forward returns y del futuro replay L1",
            },
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
