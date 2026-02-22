"""
Code Executor — LLM-generated strategy execution harness.

Runs Python code produced by the LLM in a restricted environment with
injected market data.  The generated code must define a `strategy(bars)`
function that returns a list of trade dicts.

Security: restricted builtins, no I/O, no imports beyond the allow-list.
"""
from __future__ import annotations

import math
import time
import traceback
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import structlog

from .fill_model import estimate_fill
from .metrics import compute_core_metrics
from .models import (
    BacktestResult,
    CoreMetrics,
    SlippageModel,
    StrategyConfig,
    Timeframe,
    TradeRecord,
)

logger = structlog.get_logger(__name__)

# ── Allowed builtins (no file/network/exec) ─────────────────────────────

_ALLOWED_MODULES = {
    "math": math,
    "numpy": np,
    "np": np,
    "pandas": pd,
    "pd": pd,
    "datetime": __import__("datetime"),
    "collections": __import__("collections"),
}


def _safe_import(name, *args, **kwargs):
    if name in _ALLOWED_MODULES:
        return _ALLOWED_MODULES[name]
    raise ImportError(f"Import of '{name}' is not allowed in strategy code")


_SAFE_BUILTINS = {
    "__import__": _safe_import,
    "abs": abs, "all": all, "any": any, "bool": bool,
    "dict": dict, "enumerate": enumerate, "filter": filter,
    "float": float, "frozenset": frozenset, "getattr": getattr,
    "hasattr": hasattr, "hash": hash, "int": int, "isinstance": isinstance,
    "issubclass": issubclass, "iter": iter, "len": len, "list": list,
    "map": map, "max": max, "min": min, "next": next, "None": None,
    "True": True, "False": False, "print": lambda *a, **kw: None,
    "range": range, "reversed": reversed, "round": round, "set": set,
    "slice": slice, "sorted": sorted, "str": str, "sum": sum,
    "tuple": tuple, "type": type, "zip": zip,
    "ValueError": ValueError, "TypeError": TypeError,
    "KeyError": KeyError, "IndexError": IndexError,
    "RuntimeError": RuntimeError, "Exception": Exception,
}


def _make_globals(bars: pd.DataFrame) -> dict[str, Any]:
    """Build the restricted global namespace for strategy execution."""
    return {
        "__builtins__": _SAFE_BUILTINS,
        "pd": pd,
        "np": np,
        "math": math,
        "datetime": datetime,
        "date": date,
        "timedelta": timedelta,
        "bars": bars,
    }


# ── Trade-dict → TradeRecord conversion ─────────────────────────────────

def _trades_to_records(
    raw: list[dict],
    initial_capital: float,
    slippage_bps: float = 10.0,
    commission: float = 0.0,
) -> tuple[list[TradeRecord], list[tuple[str, float]], list[str]]:
    """Convert raw trade dicts from generated code into TradeRecords + equity curve."""
    records: list[TradeRecord] = []
    equity = initial_capital
    eq_points: list[tuple[str, float]] = []
    warnings: list[str] = []
    tid = 0

    for t in raw:
        try:
            ticker = str(t.get("ticker", "UNK"))
            direction = str(t.get("direction", "long"))
            entry_price = float(t["entry_price"])
            exit_price = float(t["exit_price"])

            entry_time = t.get("entry_time") or t.get("entry_date")
            exit_time = t.get("exit_time") or t.get("exit_date")

            shares = float(t.get("shares", 0))
            if shares <= 0:
                position_value = equity * float(t.get("position_pct", 0.10))
                if position_value <= 0:
                    continue
                shares = position_value / entry_price if entry_price > 0 else 0
            position_value = shares * entry_price

            slip_frac = slippage_bps / 10_000
            entry_fill = entry_price * (1 + slip_frac) if direction == "long" else entry_price * (1 - slip_frac)
            exit_fill = exit_price * (1 - slip_frac) if direction == "long" else exit_price * (1 + slip_frac)

            slip_cost = abs(entry_fill - entry_price) * shares + abs(exit_fill - exit_price) * shares

            if direction == "long":
                pnl = (exit_fill - entry_fill) * shares
            else:
                pnl = (entry_fill - exit_fill) * shares
            pnl -= 2 * commission

            ret = pnl / position_value if position_value > 0 else 0.0

            entry_dt = pd.Timestamp(entry_time)
            exit_dt = pd.Timestamp(exit_time)
            holding = max(1, int((exit_dt - entry_dt).total_seconds() / 300))

            records.append(TradeRecord(
                trade_id=tid,
                ticker=ticker,
                direction=direction,
                entry_date=entry_dt,
                entry_price=entry_price,
                entry_fill_price=entry_fill,
                exit_date=exit_dt,
                exit_price=exit_price,
                exit_fill_price=exit_fill,
                shares=shares,
                position_value=position_value,
                pnl=pnl,
                return_pct=ret,
                holding_bars=holding,
                slippage_cost=slip_cost,
                commission_cost=2 * commission,
            ))
            tid += 1
            equity += pnl
            eq_points.append((str(exit_dt)[:10], equity))

        except Exception as exc:
            warnings.append(f"Skipped trade {tid}: {exc}")
            continue

    return records, eq_points, warnings


# ── Main executor ────────────────────────────────────────────────────────

class CodeExecutor:
    """Execute LLM-generated strategy code against market data."""

    def __init__(self, timeout_seconds: int = 30):
        self._timeout = timeout_seconds

    def execute(
        self,
        code: str,
        bars: pd.DataFrame,
        initial_capital: float = 100_000.0,
        slippage_bps: float = 10.0,
        commission: float = 0.0,
        risk_free_rate: float = 0.05,
        strategy_name: str = "LLM Strategy",
        strategy_description: str = "",
    ) -> BacktestResult:
        """
        Execute generated Python code and return a BacktestResult.

        The code must define a `strategy(bars)` function returning
        a list of trade dicts with keys:
            ticker, direction, entry_time, entry_price, exit_time, exit_price
        Optional keys: shares, position_pct
        """
        t0 = time.time()

        globs = _make_globals(bars.copy())

        try:
            exec(compile(code, "<strategy>", "exec"), globs)
        except SyntaxError as e:
            raise ValueError(f"Syntax error in generated code: {e}") from e
        except Exception as e:
            raise ValueError(f"Error loading strategy code: {e}") from e

        strategy_fn = globs.get("strategy")
        if not callable(strategy_fn):
            raise ValueError(
                "Generated code must define a callable `strategy(bars)` function"
            )

        try:
            import signal

            def _timeout_handler(signum, frame):
                raise TimeoutError("execution_timeout")

            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(self._timeout)
            try:
                raw_trades = strategy_fn(bars.copy())
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        except TimeoutError:
            raise ValueError(
                f"Strategy execution timed out after {self._timeout}s. "
                f"The code is too slow for {len(bars)} bars. "
                f"Try fewer tickers or a shorter date range."
            )
        except Exception as e:
            tb = traceback.format_exc()
            logger.error("strategy_execution_failed", error=str(e), traceback=tb)
            raise ValueError(f"Strategy execution error: {e}") from e

        if not isinstance(raw_trades, list):
            raise ValueError(
                f"strategy() must return a list of trade dicts, got {type(raw_trades).__name__}"
            )

        logger.info("code_strategy_executed",
                     raw_trades=len(raw_trades),
                     elapsed_ms=int((time.time() - t0) * 1000))

        date_col = "timestamp" if "timestamp" in bars.columns else "date"

        if not raw_trades:
            raise ValueError(
                f"Strategy produced zero trades. "
                f"Data: {len(bars)} bars, {bars['ticker'].nunique()} symbols, "
                f"{bars[date_col].min()} to {bars[date_col].max()}. "
                f"Review entry conditions."
            )

        n_tickers = bars["ticker"].nunique()
        n_days = max(1, (pd.Timestamp(bars[date_col].max()) - pd.Timestamp(bars[date_col].min())).days)
        max_reasonable = n_tickers * n_days * 10
        if len(raw_trades) > max_reasonable:
            logger.warning("excessive_trades_capped",
                           raw=len(raw_trades), cap=max_reasonable)
            raw_trades = raw_trades[:max_reasonable]

        records, eq_points, warnings = _trades_to_records(
            raw_trades, initial_capital, slippage_bps, commission)

        if not records:
            raise ValueError(
                f"All {len(raw_trades)} trades were invalid after processing. "
                f"Warnings: {'; '.join(warnings[:5])}"
            )

        eq_df = pd.DataFrame(eq_points, columns=["date", "equity"])
        eq_df = eq_df.groupby("date")["equity"].last().reset_index()
        eq_arr = eq_df["equity"].values.astype(float)
        if len(eq_arr) < 2:
            eq_arr = np.array([initial_capital, initial_capital])

        core = compute_core_metrics(records, eq_arr, initial_capital, risk_free_rate)

        monthly: dict[str, float] = {}
        if len(eq_df) > 1:
            tmp = eq_df.copy()
            tmp["date"] = pd.to_datetime(tmp["date"])
            tmp = tmp.set_index("date")
            meq = tmp["equity"].resample("ME").last().dropna()
            mret = meq.pct_change().dropna()
            monthly = {d.strftime("%Y-%m"): float(v) for d, v in mret.items()}

        rmax = np.maximum.accumulate(eq_arr)
        dd_arr = np.where(rmax > 0, (eq_arr - rmax) / rmax, 0.0)
        dates_list = eq_df["date"].astype(str).tolist()

        elapsed_ms = int((time.time() - t0) * 1000)

        date_col = "timestamp" if "timestamp" in bars.columns else "date"
        timeframe = "5min" if "timestamp" in bars.columns else "1d"
        start_d = pd.Timestamp(bars[date_col].min()).date()
        end_d = pd.Timestamp(bars[date_col].max()).date()

        strat_config = StrategyConfig(
            name=strategy_name,
            description=strategy_description,
            entry_signals=[],
            exit_rules=[],
            timeframe=Timeframe(timeframe),
            start_date=start_d,
            end_date=max(end_d, start_d + timedelta(days=5)),
        )

        return BacktestResult(
            strategy=strat_config,
            core_metrics=core,
            trades=records,
            equity_curve=list(zip(dates_list, eq_arr.tolist())),
            drawdown_curve=list(zip(dates_list, dd_arr.tolist())),
            monthly_returns=monthly,
            execution_time_ms=elapsed_ms,
            symbols_tested=bars["ticker"].nunique(),
            bars_processed=len(bars),
            warnings=warnings,
        )
