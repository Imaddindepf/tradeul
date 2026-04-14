"""
Ad-Hoc Code Executor — general-purpose Python sandbox for the code_exec agent.

Provides market data helpers injected into the execution namespace:

  historical_query(ticker, start, end, interval="1d")
    → pandas DataFrame: date/timestamp, open, high, low, close, volume + indicators

  live_quote(ticker)
    → dict: price, change_pct, volume, rvol, vwap, gap_pct, ...

  run_sql(query)
    → pandas DataFrame (DuckDB against any registered DataFrame)

  register_df(name, df)
    → registers a DataFrame so DuckDB can query it by name

  save_output(data, label="result")
    → persists dict / DataFrame as output (returned to agent)

  save_chart(fig, label="chart")
    → saves matplotlib / plotly figure as base64 PNG

Security model (same as CodeExecutor):
  - __builtins__ replaced with a whitelist (no open, socket, subprocess, os)
  - Import whitelist: math, numpy, pandas, datetime, collections, itertools, etc.
  - Text scan for known Python escape patterns before execution
  - Thread-based timeout (SIGALRM alternative, works cross-platform)

Appropriate for authenticated users in a containerised environment.
"""
from __future__ import annotations

import asyncio
import base64
import io
import math
import re
import threading
import time
import traceback
from datetime import date, datetime, timedelta
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

# ── Dangerous pattern scan ────────────────────────────────────────────────

_ESCAPE_PATTERNS = re.compile(
    r"__class__|__bases__|__subclasses__|__mro__|"
    r"__globals__|__code__|__closure__|__builtins__|"
    r"importlib|ctypes|subprocess|os\.system|os\.popen|"
    r"compile\s*\(|eval\s*\(|exec\s*\("
)


def _check_code_safety(code: str) -> None:
    """Raise ValueError if code contains known sandbox-escape patterns."""
    match = _ESCAPE_PATTERNS.search(code)
    if match:
        raise ValueError(
            f"Code contains disallowed pattern: '{match.group()}'. "
            "Use the provided helper functions instead."
        )


# ── Allowed builtins / imports ────────────────────────────────────────────

_MODULE_WHITELIST = {
    "math", "numpy", "np", "pandas", "pd",
    "datetime", "time", "calendar", "collections", "itertools", "functools",
    "statistics", "decimal", "fractions", "re", "json",
    "matplotlib", "matplotlib.pyplot", "matplotlib.figure",
    "matplotlib.axes", "matplotlib.patches", "matplotlib.lines",
    "plotly", "plotly.graph_objects", "plotly.express",
    "plotly.subplots",
    "scipy", "scipy.stats", "scipy.signal", "scipy.optimize",
}


def _safe_import(name: str, *args, **kwargs):
    if name in _MODULE_WHITELIST:
        # Handle dotted imports like matplotlib.pyplot
        parts = name.split(".")
        mod = __import__(name, fromlist=parts[1:] if len(parts) > 1 else [])
        return mod
    raise ImportError(f"Import of '{name}' is not allowed in sandbox code")


def _make_safe_builtins(print_fn) -> dict:
    return {
        "__import__": _safe_import,
        "abs": abs, "all": all, "any": any, "bool": bool,
        "dict": dict, "enumerate": enumerate, "filter": filter,
        "float": float, "frozenset": frozenset, "getattr": getattr,
        "hasattr": hasattr, "hash": hash, "int": int, "isinstance": isinstance,
        "issubclass": issubclass, "iter": iter, "len": len, "list": list,
        "map": map, "max": max, "min": min, "next": next, "None": None,
        "True": True, "False": False,
        "print": print_fn,
        "range": range, "reversed": reversed, "round": round, "set": set,
        "slice": slice, "sorted": sorted, "str": str, "sum": sum,
        "tuple": tuple, "type": type, "zip": zip,
        "ValueError": ValueError, "TypeError": TypeError,
        "KeyError": KeyError, "IndexError": IndexError, "AttributeError": AttributeError,
        "RuntimeError": RuntimeError, "Exception": Exception,
        "StopIteration": StopIteration, "NotImplementedError": NotImplementedError,
        "OverflowError": OverflowError, "ZeroDivisionError": ZeroDivisionError,
    }


# ── Async helper runners ──────────────────────────────────────────────────

def _run_async_in_thread(coro):
    """Run an async coroutine from a synchronous context (safe in worker threads)."""
    return asyncio.run(coro)


# ── Helper factories ──────────────────────────────────────────────────────

def _make_historical_query(data_layer):
    """Return a sync historical_query function backed by the DataLayer."""

    def historical_query(
        ticker: str | list[str],
        start: str | date,
        end: str | date,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Fetch historical OHLCV bars + indicators for one or more tickers.

        Args:
            ticker: single ticker or list of tickers (e.g. "AAPL" or ["AAPL", "TSLA"])
            start: start date as "YYYY-MM-DD" string or date object
            end:   end date as "YYYY-MM-DD" string or date object
            interval: "1d" (daily) | "5min" | "1min"

        Returns:
            DataFrame with columns: ticker, date/timestamp, open, high, low,
            close, volume, + pre-computed indicators (sma_20, rsi_14, etc.)
        """
        if isinstance(ticker, str):
            tickers = [ticker.upper()]
        else:
            tickers = [t.upper() for t in ticker]

        if isinstance(start, str):
            start = date.fromisoformat(start)
        if isinstance(end, str):
            end = date.fromisoformat(end)

        if interval == "1d":
            bars = _run_async_in_thread(
                data_layer.load_day_bars_adjusted(start, end, tickers)
            )
        else:
            bars = _run_async_in_thread(
                data_layer.load_minute_bars_adjusted(start, end, tickers)
            )

        if bars.empty:
            return bars

        bars = data_layer.add_indicators_sql(bars)
        return bars

    return historical_query


def _make_live_quote(redis_url: str, snapshot_url: str | None = None):
    """Return a sync live_quote function backed by Redis snapshots (DB 0)."""
    # Snapshots always live in DB 0 — use dedicated URL if provided,
    # otherwise swap the DB in the jobs URL.
    if snapshot_url:
        _snap_url = snapshot_url
    else:
        # Replace trailing /N with /0 or append /0
        import re as _re
        _snap_url = _re.sub(r"/\d+$", "/0", redis_url)
        if not _snap_url.endswith("/0"):
            _snap_url = redis_url.rstrip("/") + "/0"

    async def _fetch(ticker: str) -> dict:
        import redis.asyncio as aioredis
        import orjson

        r = aioredis.from_url(_snap_url, decode_responses=True, max_connections=2)
        try:
            raw = await r.hget("snapshot:enriched:latest", ticker.upper())
            if not raw:
                raw = await r.hget("snapshot:enriched:last_close", ticker.upper())
            if not raw:
                return {"ticker": ticker, "error": "No live data available"}
            data = orjson.loads(raw)
            prev_close = (data.get("prevDay") or {}).get("c")
            day = data.get("day") or {}
            return {
                "ticker": ticker.upper(),
                "price": data.get("current_price") or data.get("lastTrade", {}).get("p"),
                "change_pct": data.get("todaysChangePerc") or data.get("chg_pct"),
                "change": data.get("todaysChange"),
                "volume": data.get("current_volume"),
                "rvol": data.get("rvol"),
                "vwap": data.get("vwap"),
                "gap_pct": data.get("gap_pct"),
                "high": data.get("intraday_high") or day.get("h"),
                "low": data.get("intraday_low") or day.get("l"),
                "open": day.get("o"),
                "prev_close": prev_close,
                "atr": data.get("atr"),
                "atr_pct": data.get("atr_percent"),
                "vol_5min": data.get("vol_5min"),
                "vol_30min": data.get("vol_30min"),
                "chg_5min": data.get("chg_5min"),
            }
        finally:
            await r.aclose()

    def live_quote(ticker: str) -> dict:
        """Get the current live snapshot for a ticker from the analytics pipeline.

        Returns a dict with: ticker, price, change_pct, volume, rvol, vwap,
        gap_pct, high, low, open, prev_close. Returns error key if not found.
        """
        return _run_async_in_thread(_fetch(ticker))

    return live_quote


# ── Main executor ─────────────────────────────────────────────────────────

class AdHocExecutor:
    """Execute ad-hoc LLM-generated Python code with market data helpers."""

    def __init__(
        self,
        data_layer,
        redis_url: str = "redis://redis:6379",
        redis_snapshot_url: str | None = None,
        timeout_seconds: int = 30,
    ):
        self._data_layer = data_layer
        self._redis_url = redis_url
        self._redis_snapshot_url = redis_snapshot_url
        self._timeout = timeout_seconds

    def execute(self, code: str) -> dict[str, Any]:
        """
        Execute user/LLM code in a restricted sandbox.

        Returns:
            {
                "status": "success" | "error",
                "outputs": {label: data, ...},
                "charts": {label: "<base64-png>", ...},
                "prints": ["line", ...],
                "error": str | None,
                "traceback": str | None,
                "execution_ms": int,
            }
        """
        t0 = time.time()

        try:
            _check_code_safety(code)
            compile(code, "<adhoc>", "exec")  # syntax check before threading
        except SyntaxError as e:
            return _error_result(f"Syntax error: {e}", t0=t0)
        except ValueError as e:
            return _error_result(str(e), t0=t0)

        # Per-execution accumulators
        outputs: dict[str, Any] = {}
        charts: dict[str, str] = {}
        prints: list[str] = []
        duck = duckdb.connect(":memory:")

        def _print(*args, **kwargs):
            line = " ".join(str(a) for a in args)
            prints.append(line)
            if len(prints) <= 200:  # cap noise
                logger.debug("sandbox_print", line=line)

        def save_output(data: Any, label: str = "result") -> None:
            """Persist any data as output (returned to the agent after execution)."""
            if isinstance(data, pd.DataFrame):
                outputs[label] = data.head(500).to_dict(orient="records")
            elif isinstance(data, np.ndarray):
                outputs[label] = data.tolist()
            else:
                outputs[label] = data

        def register_df(name: str, df: pd.DataFrame) -> None:
            """Register a DataFrame so run_sql() can query it by name."""
            duck.register(name, df)

        def run_sql(query: str) -> pd.DataFrame:
            """Run a DuckDB SQL query against any registered DataFrame."""
            return duck.execute(query).df()

        def save_chart(fig: Any, label: str = "chart") -> None:
            """Save a matplotlib or plotly figure as a base64 PNG."""
            buf = io.BytesIO()
            try:
                if hasattr(fig, "savefig"):  # matplotlib
                    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
                elif hasattr(fig, "to_image"):  # plotly
                    buf.write(fig.to_image(format="png"))
                else:
                    _print(f"[save_chart] Unrecognized figure type: {type(fig)}")
                    return
                charts[label] = base64.b64encode(buf.getvalue()).decode()
            except Exception as exc:
                _print(f"[save_chart] Failed to encode chart '{label}': {exc}")

        import matplotlib
        matplotlib.use("Agg")  # non-interactive backend, safe in threads
        import matplotlib.pyplot as plt
        try:
            import plotly.graph_objects as go
            import plotly.express as px
            _plotly_available = True
        except ImportError:
            _plotly_available = False

        globs: dict[str, Any] = {
            "__builtins__": _make_safe_builtins(_print),
            # Standard libraries
            "pd": pd,
            "np": np,
            "math": math,
            "datetime": datetime,
            "date": date,
            "timedelta": timedelta,
            # Visualization — pre-injected so users can use directly without import
            "plt": plt,
            "matplotlib": matplotlib,
            # Market data helpers
            "historical_query": _make_historical_query(self._data_layer),
            "live_quote": _make_live_quote(self._redis_url, self._redis_snapshot_url),
            # Analysis helpers
            "run_sql": run_sql,
            "register_df": register_df,
            "save_output": save_output,
            "save_chart": save_chart,
        }
        if _plotly_available:
            globs["go"] = go
            globs["px"] = px

        exec_result: dict[str, Any] = {}

        def _runner():
            try:
                exec(compile(code, "<adhoc>", "exec"), globs)  # noqa: S102
                exec_result["ok"] = True
            except Exception as exc:
                exec_result["error"] = str(exc)
                exec_result["traceback"] = traceback.format_exc()

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=self._timeout)

        elapsed_ms = int((time.time() - t0) * 1000)

        if thread.is_alive():
            # Thread leaked — we can't kill it but we can return a clear error.
            logger.warning("adhoc_execution_timeout", timeout_s=self._timeout)
            return {
                "status": "error",
                "outputs": outputs,
                "charts": charts,
                "prints": prints,
                "error": (
                    f"Execution timed out after {self._timeout}s. "
                    "Try: fewer tickers, shorter date ranges, or vectorized pandas instead of loops."
                ),
                "traceback": None,
                "execution_ms": elapsed_ms,
            }

        if "error" in exec_result:
            logger.warning("adhoc_execution_error", error=exec_result["error"])
            return {
                "status": "error",
                "outputs": outputs,
                "charts": charts,
                "prints": prints,
                "error": exec_result["error"],
                "traceback": exec_result.get("traceback"),
                "execution_ms": elapsed_ms,
            }

        logger.info(
            "adhoc_execution_success",
            outputs=list(outputs.keys()),
            charts=list(charts.keys()),
            elapsed_ms=elapsed_ms,
        )
        return {
            "status": "success",
            "outputs": outputs,
            "charts": charts,
            "prints": prints,
            "error": None,
            "traceback": None,
            "execution_ms": elapsed_ms,
        }


def _error_result(msg: str, t0: float) -> dict[str, Any]:
    return {
        "status": "error",
        "outputs": {},
        "charts": {},
        "prints": [],
        "error": msg,
        "traceback": None,
        "execution_ms": int((time.time() - t0) * 1000),
    }
