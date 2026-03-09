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
from .event_translator import translate_event, translate_events
from .fill_model import FillResult, estimate_fill
from .filter_evaluator import evaluate_bar_filters, evaluate_universe_filters
from .metrics import compute_core_metrics
from .models import (
    BacktestResult,
    DailyStats,
    DayStreak,
    ExitType,
    OptimizationBreakdown,
    OptimizationBucket,
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


def _compute_daily_stats(
    trades: list[TradeRecord],
    eq_arr: np.ndarray,
    dates_list: list[str],
    strategy: StrategyConfig,
) -> tuple[list[DailyStats], dict]:
    """Compute per-day stats, streaks, and biggest winning/losing days."""
    from collections import defaultdict

    by_exit_date: dict[str, list[TradeRecord]] = defaultdict(list)
    for t in trades:
        d = str(t.exit_date)[:10]
        by_exit_date[d].append(t)

    eq_by_date = {}
    for i, d in enumerate(dates_list):
        eq_by_date[d] = eq_arr[i]

    daily: list[DailyStats] = []
    all_dates = sorted(set(dates_list) | set(by_exit_date.keys()))

    cum_equity = strategy.initial_capital
    for d in all_dates:
        day_trades = by_exit_date.get(d, [])
        pnl = sum(t.pnl for t in day_trades)
        winners = sum(1 for t in day_trades if t.pnl > 0)
        losers = len(day_trades) - winners
        wr = winners / len(day_trades) if day_trades else 0.0
        avg_g = pnl / len(day_trades) if day_trades else 0.0
        bp = sum(t.position_value for t in day_trades)
        cum_equity += pnl
        gross_eq = cum_equity + sum(
            t.slippage_cost + t.commission_cost for t in day_trades
        )
        daily.append(DailyStats(
            date=d, pnl=round(pnl, 2), trades_count=len(day_trades),
            winners=winners, losers=losers, win_rate=round(wr, 4),
            avg_gain=round(avg_g, 2), buying_power=round(bp, 2),
            gross_equity=round(gross_eq, 2), net_equity=round(cum_equity, 2),
        ))

    win_streak = lose_streak = max_win = max_lose = 0
    cur_win = cur_lose = 0
    biggest_win: DayStreak | None = None
    biggest_loss: DayStreak | None = None

    for ds in daily:
        if ds.trades_count == 0:
            continue
        if ds.pnl > 0:
            cur_win += 1
            cur_lose = 0
            max_win = max(max_win, cur_win)
            if biggest_win is None or ds.pnl > biggest_win.pnl:
                biggest_win = DayStreak(date=ds.date, pnl=ds.pnl)
        elif ds.pnl < 0:
            cur_lose += 1
            cur_win = 0
            max_lose = max(max_lose, cur_lose)
            if biggest_loss is None or ds.pnl < biggest_loss.pnl:
                biggest_loss = DayStreak(date=ds.date, pnl=ds.pnl)
        else:
            cur_win = cur_lose = 0

    streaks = {
        "most_winning_days_in_row": max_win,
        "most_losing_days_in_row": max_lose,
        "biggest_winning_day": biggest_win,
        "biggest_losing_day": biggest_loss,
    }
    return daily, streaks


def _compute_optimization(
    trades: list[TradeRecord],
) -> dict[str, OptimizationBreakdown]:
    """Compute optimization breakdowns by price and symbol."""
    if not trades:
        return {}

    result: dict[str, OptimizationBreakdown] = {}

    def _make_buckets(
        groups: dict[str, list[TradeRecord]], total_trades: int,
    ) -> list[OptimizationBucket]:
        buckets = []
        for label, group in sorted(groups.items()):
            if not group:
                continue
            wins = [t for t in group if t.pnl > 0]
            losses = [t for t in group if t.pnl <= 0]
            gross_profit = sum(t.pnl for t in wins)
            gross_loss = abs(sum(t.pnl for t in losses))
            pf = gross_profit / gross_loss if gross_loss > 0 else (
                10.0 if gross_profit > 0 else 0.0
            )
            wr = len(wins) / len(group) if group else 0
            total_g = sum(t.pnl for t in group)
            avg_g = total_g / len(group) if group else 0
            buckets.append(OptimizationBucket(
                label=label,
                profit_factor=round(pf, 2),
                win_rate=round(wr * 100, 1),
                avg_gain=round(avg_g, 2),
                total_gain=round(total_g, 2),
                trades=len(group),
                pct_of_total=round(len(group) / total_trades * 100, 1)
                if total_trades > 0 else 0,
            ))
        return buckets

    total = len(trades)

    prices = [t.entry_fill_price for t in trades]
    if prices:
        mn, mx = min(prices), max(prices)
        interval = max(1.0, round((mx - mn) / 12, 2))
        price_groups: dict[str, list[TradeRecord]] = {}
        for t in trades:
            lo = int((t.entry_fill_price - mn) / interval) * interval + mn
            hi = lo + interval
            key = f"${lo:.2f}-${hi:.2f}"
            price_groups.setdefault(key, []).append(t)
        result["price"] = OptimizationBreakdown(
            filter_name="Price", interval=interval,
            buckets=_make_buckets(price_groups, total),
        )

    sym_groups: dict[str, list[TradeRecord]] = {}
    for t in trades:
        sym_groups.setdefault(t.ticker, []).append(t)
    result["symbol"] = OptimizationBreakdown(
        filter_name="Symbol", interval=0,
        buckets=_make_buckets(sym_groups, total),
    )

    time_groups: dict[str, list[TradeRecord]] = {}
    for t in trades:
        entry_str = str(t.entry_date)
        if "T" in entry_str or " " in entry_str:
            parts = entry_str.replace("T", " ").split(" ")
            if len(parts) > 1:
                hm = parts[1][:5]
                h = int(hm.split(":")[0])
                bucket_h = h
                key = f"{bucket_h:02d}:00-{bucket_h:02d}:59"
            else:
                key = "all-day"
        else:
            key = "all-day"
        time_groups.setdefault(key, []).append(t)
    if len(time_groups) > 1:
        result["time_of_day"] = OptimizationBreakdown(
            filter_name="Time of Day", interval=60,
            buckets=_make_buckets(time_groups, total),
        )

    return result


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
            tickers_str = ", ".join(strategy.universe.tickers or ["(all)"])
            raise ValueError(
                f"No data available for {tickers_str} between "
                f"{strategy.start_date} and {strategy.end_date}. "
                f"Verify the tickers exist and the date range is valid."
            )

        _p("Filtrando universo...", 0.10)
        if strategy.universe.sql_where:
            valid = self._data.filter_universe_sql(bars_df, strategy.universe.sql_where)
            bars_df = bars_df[bars_df["ticker"].isin(valid)]

        date_col = "date" if "date" in bars_df.columns else "timestamp"

        _p("Calculando indicadores...", 0.15)
        bars_df = self._data.add_indicators_sql(bars_df)

        # Universe pre-filtering via filter parameters
        if strategy.universe_filters:
            _p("Aplicando filtros de universo...", 0.18)
            valid_tickers = evaluate_universe_filters(bars_df, strategy.universe_filters)
            bars_df = bars_df[bars_df["ticker"].isin(valid_tickers)]
            if bars_df.empty:
                raise ValueError(
                    "No tickers passed universe filters. "
                    "Try relaxing filter parameters."
                )

        symbols_tested = bars_df["ticker"].nunique()
        bars_processed = len(bars_df)

        _p("Evaluando senales...", 0.25)
        # Classic indicator-based signals (ANDed together)
        signal_mask = evaluate_entries(bars_df, strategy.entry_signals)

        # Event-based entry signals
        if strategy.entry_events:
            _p("Traduciendo eventos de entrada...", 0.27)
            event_mask = translate_events(
                bars_df, strategy.entry_events, strategy.entry_events_combine)
            if strategy.entry_signals:
                entry_mask = signal_mask & event_mask
            else:
                entry_mask = event_mask
        else:
            entry_mask = signal_mask

        # Per-bar filter conditions as additional entry requirements
        if strategy.entry_filters:
            _p("Aplicando filtros por barra...", 0.29)
            filter_mask = evaluate_bar_filters(bars_df, strategy.entry_filters)
            entry_mask = entry_mask & filter_mask

        # Exit signals: classic + event-based
        exit_sig = None
        for r in strategy.exit_rules:
            if r.type == ExitType.SIGNAL and r.signal:
                exit_sig = _evaluate_signal(bars_df, r.signal)
                break

        if strategy.exit_events:
            _p("Traduciendo eventos de salida...", 0.30)
            exit_event_mask = translate_events(bars_df, strategy.exit_events, "or")
            exit_sig = exit_event_mask if exit_sig is None else (exit_sig | exit_event_mask)

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
            date_col = "date" if "date" in bars_df.columns else "timestamp"
            actual_start = bars_df[date_col].min()
            actual_end = bars_df[date_col].max()
            entry_desc = ", ".join(
                f"{s.indicator} {s.operator.value} {s.value}" for s in strategy.entry_signals
            )
            raise ValueError(
                f"Zero trades generated. Data loaded: {bars_processed} bars from "
                f"{actual_start} to {actual_end} for {symbols_tested} symbols. "
                f"Entry conditions ({entry_desc}) were never triggered. "
                f"Consider relaxing signal thresholds or expanding the date range."
            )

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

        _p("Calculando estadisticas diarias...", 0.92)
        daily, streaks = _compute_daily_stats(trades, eq_arr, dates_list, strategy)
        optimization = _compute_optimization(trades)

        elapsed = int((time.time() - t0) * 1000)
        _p(f"Completado: {len(trades)} trades en {elapsed}ms", 1.0)

        return BacktestResult(
            strategy=strategy, core_metrics=core, trades=trades,
            equity_curve=list(zip(dates_list, eq_arr.tolist())),
            drawdown_curve=list(zip(dates_list, dd_arr.tolist())),
            monthly_returns=monthly,
            daily_stats=daily,
            optimization=optimization,
            execution_time_ms=elapsed,
            symbols_tested=symbols_tested, bars_processed=bars_processed,
            warnings=warnings,
            **streaks)

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
