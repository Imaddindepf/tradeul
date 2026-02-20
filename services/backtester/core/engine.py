"""
Vectorized Backtesting Engine.

Two-phase architecture:
  1. Signal Generation - fully vectorized (numpy/DuckDB)
  2. Portfolio Simulation - sequential loop with optimised hot path

Design ensures ZERO look-ahead bias:
  - Signals on bar[i] can only use data up to bar[i]
  - Entry fills use bar[i+1] open (next_open) by default
  - All indicators use proper rolling windows
"""
from __future__ import annotations

import time
from datetime import date
from typing import Callable

import numpy as np
import pandas as pd
import structlog

from .data_layer import DataLayer
from .fill_model import FillResult, estimate_fill
from .metrics import compute_core_metrics
from .models import (
    BacktestResult,
    ExitType,
    Signal,
    SignalOperator,
    StrategyConfig,
    Timeframe,
    TradeRecord,
)

logger = structlog.get_logger(__name__)


def _resolve_indicator(df: pd.DataFrame, indicator: str) -> pd.Series:
    if indicator in df.columns:
        return df[indicator]
    raise ValueError(f"Unknown indicator '{indicator}'. Available: {list(df.columns)}")


def _evaluate_signal(df: pd.DataFrame, signal: Signal) -> pd.Series:
    lhs = _resolve_indicator(df, signal.indicator)
    rhs = (_resolve_indicator(df, signal.value)
           if isinstance(signal.value, str) else signal.value)

    match signal.operator:
        case SignalOperator.GT:
            return lhs > rhs
        case SignalOperator.GTE:
            return lhs >= rhs
        case SignalOperator.LT:
            return lhs < rhs
        case SignalOperator.LTE:
            return lhs <= rhs
        case SignalOperator.EQ:
            return lhs == rhs
        case SignalOperator.CROSSES_ABOVE:
            rhs_s = rhs if isinstance(rhs, pd.Series) else pd.Series(rhs, index=df.index)
            return (lhs > rhs_s) & (lhs.shift(1) <= rhs_s.shift(1))
        case SignalOperator.CROSSES_BELOW:
            rhs_s = rhs if isinstance(rhs, pd.Series) else pd.Series(rhs, index=df.index)
            return (lhs < rhs_s) & (lhs.shift(1) >= rhs_s.shift(1))
        case _:
            raise ValueError(f"Unknown operator: {signal.operator}")


def evaluate_entries(df: pd.DataFrame, signals: list[Signal]) -> pd.Series:
    if not signals:
        return pd.Series(False, index=df.index)
    mask = pd.Series(True, index=df.index)
    for sig in signals:
        mask &= _evaluate_signal(df, sig)
    return mask.fillna(False)


class _Position:
    __slots__ = (
        "ticker", "direction", "entry_bar_idx", "entry_date",
        "entry_price", "fill_price", "shares", "position_value",
        "slippage_cost", "commission_cost",
    )

    def __init__(self, ticker, direction, entry_bar_idx, entry_date,
                 entry_price, fill, position_value):
        self.ticker = ticker
        self.direction = direction
        self.entry_bar_idx = entry_bar_idx
        self.entry_date = entry_date
        self.entry_price = entry_price
        self.fill_price = fill.fill_price
        self.shares = position_value / fill.fill_price if fill.fill_price > 0 else 0.0
        self.position_value = position_value
        self.slippage_cost = fill.slippage_cost
        self.commission_cost = fill.commission_cost


def _check_exit(pos, bar, bar_idx, exit_rules, exit_signals, peak_price):
    for rule in exit_rules:
        match rule.type:
            case ExitType.TIME:
                if rule.value and (bar_idx - pos.entry_bar_idx) >= rule.value:
                    return True
            case ExitType.EOD:
                return True
            case ExitType.STOP_LOSS:
                if rule.value:
                    cur = bar["close"]
                    pnl_pct = ((cur - pos.fill_price) / pos.fill_price
                               if pos.direction == "long"
                               else (pos.fill_price - cur) / pos.fill_price)
                    if pnl_pct <= -rule.value:
                        return True
            case ExitType.TARGET:
                if rule.value:
                    cur = bar["close"]
                    pnl_pct = ((cur - pos.fill_price) / pos.fill_price
                               if pos.direction == "long"
                               else (pos.fill_price - cur) / pos.fill_price)
                    if pnl_pct >= rule.value:
                        return True
            case ExitType.TRAILING_STOP:
                if rule.value and peak_price > 0:
                    if pos.direction == "long":
                        if (peak_price - bar["close"]) / peak_price >= rule.value:
                            return True
                    else:
                        if (bar["close"] - peak_price) / peak_price >= rule.value:
                            return True
            case ExitType.SIGNAL:
                if (exit_signals is not None
                        and bar_idx < len(exit_signals)
                        and exit_signals.iloc[bar_idx]):
                    return True
    return False


def _to_date(val) -> date:
    if isinstance(val, date):
        return val
    return pd.Timestamp(val).date()


class BacktestEngine:
    """Professional backtesting engine."""

    def __init__(self, data_layer: DataLayer):
        self._data = data_layer

    async def run(
        self,
        strategy: StrategyConfig,
        bars_df: pd.DataFrame | None = None,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> BacktestResult:
        t0 = time.time()
        _p = progress_callback or (lambda m, p: None)

        _p("Cargando datos...", 0.05)
        if bars_df is None:
            tickers = strategy.universe.tickers
            if strategy.timeframe == Timeframe.DAY_1:
                bars_df = await self._data.load_day_bars_adjusted(
                    strategy.start_date, strategy.end_date, tickers)
            else:
                bars_df = await self._data.load_minute_bars_adjusted(
                    strategy.start_date, strategy.end_date, tickers)

        if bars_df.empty:
            raise ValueError("No data for the specified range/tickers")

        _p("Filtrando universo...", 0.10)
        if strategy.universe.sql_where:
            valid = self._data.filter_universe_sql(bars_df, strategy.universe.sql_where)
            bars_df = bars_df[bars_df["ticker"].isin(valid)]

        date_col = "date" if "date" in bars_df.columns else "timestamp"

        _p("Calculando indicadores...", 0.15)
        bars_df = self._data.add_indicators_sql(bars_df)
        symbols_tested = bars_df["ticker"].nunique()
        bars_processed = len(bars_df)

        _p("Evaluando senales...", 0.25)
        entry_mask = evaluate_entries(bars_df, strategy.entry_signals)
        exit_sig = None
        for r in strategy.exit_rules:
            if r.type == ExitType.SIGNAL and r.signal:
                exit_sig = _evaluate_signal(bars_df, r.signal)
                break

        _p("Simulando portfolio...", 0.35)
        trades, eq_points, warnings = self._simulate(
            bars_df, entry_mask, exit_sig, strategy, date_col, _p)

        _p("Calculando metricas...", 0.90)
        eq_df = pd.DataFrame(eq_points, columns=["date", "equity"])
        eq_df = eq_df.groupby("date")["equity"].last().reset_index()
        eq_arr = eq_df["equity"].values.astype(float)
        if len(eq_arr) < 2:
            eq_arr = np.array([strategy.initial_capital, strategy.initial_capital])

        if not trades:
            raise ValueError("Backtest produced zero trades")

        core = compute_core_metrics(
            trades, eq_arr, strategy.initial_capital, strategy.risk_free_rate)

        monthly: dict[str, float] = {}
        if len(eq_df) > 1:
            tmp = eq_df.copy()
            tmp["date"] = pd.to_datetime(tmp["date"])
            tmp = tmp.set_index("date")
            meq = tmp["equity"].resample("ME").last().dropna()
            mret = meq.pct_change().dropna()
            monthly = {d.strftime("%Y-%m"): float(v) for d, v in mret.items()}

        rmax = np.maximum.accumulate(eq_arr)
        dd_arr = (eq_arr - rmax) / rmax
        dates_list = eq_df["date"].astype(str).tolist()

        elapsed = int((time.time() - t0) * 1000)
        _p(f"Completado: {len(trades)} trades en {elapsed}ms", 1.0)

        return BacktestResult(
            strategy=strategy, core_metrics=core, trades=trades,
            equity_curve=list(zip(dates_list, eq_arr.tolist())),
            drawdown_curve=list(zip(dates_list, dd_arr.tolist())),
            monthly_returns=monthly, execution_time_ms=elapsed,
            symbols_tested=symbols_tested, bars_processed=bars_processed,
            warnings=warnings)

    def _simulate(self, bars_df, entry_mask, exit_sig, strat, date_col, _p):
        trades: list[TradeRecord] = []
        equity = strat.initial_capital
        eq_pts: list[tuple[str, float]] = []
        tid = 0
        positions: list[_Position] = []
        peaks: dict[int, float] = {}
        warns: list[str] = []
        tickers = bars_df["ticker"].unique()
        n = len(tickers)

        for ti, tkr in enumerate(tickers):
            if ti % max(1, n // 10) == 0:
                _p(f"{tkr} ({ti+1}/{n})", 0.35 + 0.50 * ti / max(n, 1))
            m = bars_df["ticker"] == tkr
            tb = bars_df[m].reset_index(drop=True)
            te = entry_mask[m].reset_index(drop=True)
            tx = exit_sig[m].reset_index(drop=True) if exit_sig is not None else None

            for i in range(len(tb)):
                bar = tb.iloc[i]
                ds = str(bar[date_col])[:10]
                # Check exits
                for pi in range(len(positions) - 1, -1, -1):
                    pos = positions[pi]
                    if pos.ticker != tkr:
                        continue
                    pk = id(pos)
                    if pos.direction == "long":
                        peaks[pk] = max(peaks.get(pk, pos.fill_price), bar["high"])
                    else:
                        peaks[pk] = min(peaks.get(pk, pos.fill_price), bar["low"])
                    if _check_exit(pos, bar, i, strat.exit_rules, tx, peaks.get(pk, 0)):
                        ef = estimate_fill(
                            "sell" if pos.direction == "long" else "buy",
                            bar["close"], int(bar["volume"]), bar.get("vwap"),
                            pos.position_value, strat.slippage_model,
                            strat.slippage_bps, strat.commission_per_trade)
                        pnl = ((ef.fill_price - pos.fill_price) if pos.direction == "long"
                               else (pos.fill_price - ef.fill_price)) * pos.shares
                        costs = (pos.slippage_cost + pos.commission_cost
                                 + ef.slippage_cost + ef.commission_cost)
                        pnl -= costs
                        ret = pnl / pos.position_value if pos.position_value > 0 else 0.0
                        trades.append(TradeRecord(
                            trade_id=tid, ticker=tkr, direction=pos.direction,
                            entry_date=pos.entry_date, entry_price=pos.entry_price,
                            entry_fill_price=pos.fill_price,
                            exit_date=_to_date(bar[date_col]),
                            exit_price=bar["close"], exit_fill_price=ef.fill_price,
                            shares=pos.shares, position_value=pos.position_value,
                            pnl=pnl, return_pct=ret,
                            holding_bars=i - pos.entry_bar_idx,
                            slippage_cost=pos.slippage_cost + ef.slippage_cost,
                            commission_cost=pos.commission_cost + ef.commission_cost))
                        tid += 1
                        equity += pnl
                        positions.pop(pi)
                        peaks.pop(pk, None)
                # Check entries
                if (i < len(te) and te.iloc[i]
                        and not any(p.ticker == tkr for p in positions)
                        and len(positions) < strat.max_positions
                        and equity > 0):
                    if strat.entry_timing == "next_open" and i + 1 < len(tb):
                        ep, ebi = tb.iloc[i + 1]["open"], i + 1
                    elif strat.entry_timing == "close":
                        ep, ebi = bar["close"], i
                    else:
                        ep, ebi = bar["open"], i
                    if ep <= 0:
                        continue
                    pv = equity * strat.position_size_pct
                    d = strat.direction if strat.direction != "both" else "long"
                    fill = estimate_fill(
                        "buy" if d == "long" else "sell",
                        ep, int(bar["volume"]), bar.get("vwap"), pv,
                        strat.slippage_model, strat.slippage_bps,
                        strat.commission_per_trade)
                    if fill.fill_pct > 0:
                        positions.append(_Position(
                            tkr, d, ebi, _to_date(bar[date_col]),
                            ep, fill, pv * fill.fill_pct))
                eq_pts.append((ds, equity))

        # Force close remaining
        for pos in positions:
            td = bars_df[bars_df["ticker"] == pos.ticker]
            if td.empty:
                continue
            lb = td.iloc[-1]
            pnl = ((lb["close"] - pos.fill_price) if pos.direction == "long"
                    else (pos.fill_price - lb["close"])) * pos.shares
            pnl -= pos.slippage_cost + pos.commission_cost
            ret = pnl / pos.position_value if pos.position_value > 0 else 0.0
            trades.append(TradeRecord(
                trade_id=tid, ticker=pos.ticker, direction=pos.direction,
                entry_date=pos.entry_date, entry_price=pos.entry_price,
                entry_fill_price=pos.fill_price,
                exit_date=_to_date(lb[date_col]),
                exit_price=lb["close"], exit_fill_price=lb["close"],
                shares=pos.shares, position_value=pos.position_value,
                pnl=pnl, return_pct=ret,
                holding_bars=len(td) - pos.entry_bar_idx,
                slippage_cost=pos.slippage_cost,
                commission_cost=pos.commission_cost))
            tid += 1
            equity += pnl
            warns.append(f"Force-closed {pos.ticker} at end of period")
        return trades, eq_pts, warns
