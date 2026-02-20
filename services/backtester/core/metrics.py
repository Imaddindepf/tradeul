"""
Professional-Grade Backtesting Metrics.

Includes:
  • Standard: Sharpe, Sortino, Calmar, Max DD, Win Rate, Profit Factor
  • Advanced: Deflated Sharpe Ratio (López de Prado), PSR, MinTRL
  • Auxiliary: Ulcer Index, Tail Ratio, Recovery Factor, Common Sense Ratio
"""
from __future__ import annotations

import math

import numpy as np
from scipy.stats import norm, skew, kurtosis as scipy_kurtosis

from .models import CoreMetrics, AdvancedMetrics, TradeRecord


# ── Helpers ──────────────────────────────────────────────────────────────

TRADING_DAYS_PER_YEAR = 252


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b != 0 else default


# ── Core Metrics ─────────────────────────────────────────────────────────

def compute_core_metrics(
    trades: list[TradeRecord],
    equity_curve: np.ndarray,
    initial_capital: float,
    risk_free_rate: float = 0.05,
) -> CoreMetrics:
    """
    Compute all standard + auxiliary backtest metrics.

    Args:
        trades:          List of closed trades
        equity_curve:    Daily equity values (one per bar)
        initial_capital: Starting capital
        risk_free_rate:  Annual risk-free rate for Sharpe/Sortino
    """
    n_trades = len(trades)
    if n_trades == 0:
        raise ValueError("Cannot compute metrics with zero trades")

    returns = np.array([t.return_pct for t in trades])
    pnls = np.array([t.pnl for t in trades])

    winners = returns[returns > 0]
    losers = returns[returns <= 0]

    # ── Basic stats ──
    win_rate = len(winners) / n_trades
    total_pnl = float(np.sum(pnls))
    total_return_pct = total_pnl / initial_capital

    # ── Annualized return ──
    n_bars = len(equity_curve)
    years = max(n_bars / TRADING_DAYS_PER_YEAR, 1 / TRADING_DAYS_PER_YEAR)
    final_equity = equity_curve[-1] if len(equity_curve) > 0 else initial_capital
    annualized_return = (final_equity / initial_capital) ** (1 / years) - 1

    # ── Daily returns from equity curve ──
    daily_returns = np.diff(equity_curve) / equity_curve[:-1] if len(equity_curve) > 1 else np.array([0.0])
    daily_mean = float(np.mean(daily_returns))
    daily_std = float(np.std(daily_returns, ddof=1)) if len(daily_returns) > 1 else 0.0

    ann_std = daily_std * math.sqrt(TRADING_DAYS_PER_YEAR)
    rf_daily = (1 + risk_free_rate) ** (1 / TRADING_DAYS_PER_YEAR) - 1

    # ── Sharpe ──
    sharpe = _safe_div(annualized_return - risk_free_rate, ann_std)

    # ── Sortino ──
    downside = daily_returns[daily_returns < rf_daily] - rf_daily
    downside_std = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
    ann_downside_std = downside_std * math.sqrt(TRADING_DAYS_PER_YEAR)
    sortino = _safe_div(annualized_return - risk_free_rate, ann_downside_std)

    # ── Drawdown ──
    running_max = np.maximum.accumulate(equity_curve)
    drawdown = (equity_curve - running_max) / running_max
    max_dd = float(np.min(drawdown))

    # Max drawdown duration (in bars)
    in_dd = drawdown < 0
    if np.any(in_dd):
        changes = np.diff(in_dd.astype(int))
        starts = np.where(changes == 1)[0] + 1
        ends = np.where(changes == -1)[0] + 1
        if in_dd[0]:
            starts = np.insert(starts, 0, 0)
        if in_dd[-1]:
            ends = np.append(ends, len(in_dd))
        durations = ends[:len(starts)] - starts[:len(ends)]
        max_dd_duration = int(np.max(durations)) if len(durations) > 0 else 0
    else:
        max_dd_duration = 0

    # ── Calmar ──
    calmar = _safe_div(annualized_return, abs(max_dd))

    # ── Trade metrics ──
    avg_return = float(np.mean(returns))
    median_return = float(np.median(returns))
    std_return = float(np.std(returns, ddof=1)) if n_trades > 1 else 0.0

    avg_winner = float(np.mean(winners)) if len(winners) > 0 else 0.0
    avg_loser = float(np.mean(losers)) if len(losers) > 0 else 0.0
    best_trade = float(np.max(returns))
    worst_trade = float(np.min(returns))

    gross_profit = float(np.sum(winners))
    gross_loss = float(abs(np.sum(losers)))
    profit_factor = _safe_div(gross_profit, gross_loss)

    expectancy = win_rate * avg_winner - (1 - win_rate) * abs(avg_loser)
    avg_holding = float(np.mean([t.holding_bars for t in trades]))

    # ── Recovery Factor ──
    recovery_factor = _safe_div(total_return_pct, abs(max_dd))

    # ── Ulcer Index ──
    ulcer_index = float(np.sqrt(np.mean(drawdown ** 2)))

    # ── Tail Ratio: |P95 / P5| of returns ──
    p5 = float(np.percentile(returns, 5)) if n_trades >= 20 else worst_trade
    p95 = float(np.percentile(returns, 95)) if n_trades >= 20 else best_trade
    tail_ratio = _safe_div(abs(p95), abs(p5), default=1.0)

    common_sense_ratio = profit_factor * tail_ratio

    return CoreMetrics(
        total_return_pct=total_return_pct,
        annualized_return_pct=annualized_return,
        total_pnl=total_pnl,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=calmar,
        max_drawdown_pct=max_dd,
        max_drawdown_duration_days=max_dd_duration,
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        avg_return_per_trade=avg_return,
        median_return_per_trade=median_return,
        std_return_per_trade=std_return,
        avg_winner_pct=avg_winner,
        avg_loser_pct=avg_loser,
        best_trade_pct=best_trade,
        worst_trade_pct=worst_trade,
        total_trades=n_trades,
        avg_holding_bars=avg_holding,
        recovery_factor=recovery_factor,
        ulcer_index=ulcer_index,
        tail_ratio=tail_ratio,
        common_sense_ratio=common_sense_ratio,
    )


# ── Advanced Metrics ─────────────────────────────────────────────────────

def _expected_max_sr(n_trials: int) -> float:
    """
    Expected maximum Sharpe Ratio from N independent trials (SR=0 under H₀).
    Euler–Mascheroni approximation.
    """
    if n_trials <= 1:
        return 0.0
    z = math.sqrt(2 * math.log(n_trials))
    return z - (math.log(math.log(n_trials)) + math.log(4 * math.pi)) / (2 * z)


def compute_advanced_metrics(
    trades: list[TradeRecord],
    equity_curve: np.ndarray,
    observed_sharpe: float,
    risk_free_rate: float = 0.05,
    n_trials: int = 1,
) -> AdvancedMetrics:
    """
    López de Prado advanced metrics for multiple-testing correction.

    Args:
        trades:          Closed trades
        equity_curve:    Daily equity values
        observed_sharpe: Sharpe ratio from core metrics
        risk_free_rate:  Annual risk-free rate
        n_trials:        Number of strategy variations tested (for DSR)
    """
    daily_returns = np.diff(equity_curve) / equity_curve[:-1] if len(equity_curve) > 1 else np.array([0.0])

    T = len(daily_returns)
    sk = float(skew(daily_returns)) if T > 2 else 0.0
    kurt = float(scipy_kurtosis(daily_returns, fisher=False)) if T > 2 else 3.0

    # ── Standard error of SR estimator ──
    sr_var_numer = 1 - sk * observed_sharpe + ((kurt - 1) / 4) * observed_sharpe ** 2
    sr_std = math.sqrt(max(sr_var_numer, 0.0) / max(T, 1))

    # ── Probabilistic Sharpe Ratio (PSR) ──
    # P(true SR > 0 | observed SR)
    psr = float(norm.cdf(observed_sharpe / sr_std)) if sr_std > 0 else 0.5

    # ── Deflated Sharpe Ratio (DSR) ──
    # Adjusts for the maximum expected SR from n_trials
    sr_benchmark = _expected_max_sr(n_trials)
    if sr_std > 0:
        dsr = float(norm.cdf((observed_sharpe - sr_benchmark) / sr_std))
    else:
        dsr = 0.5

    # ── Minimum Track Record Length (MinTRL) ──
    # Months needed for observed SR to be statistically significant at 95%
    z_95 = 1.645
    if observed_sharpe > 0:
        # MinTRL in observations
        min_obs = (z_95 ** 2 * sr_var_numer) / (observed_sharpe ** 2)
        # Convert to months (≈21 trading days/month)
        min_trl_months = max(1, int(math.ceil(min_obs / 21)))
    else:
        min_trl_months = 9999  # not achievable

    return AdvancedMetrics(
        deflated_sharpe_ratio=dsr,
        probabilistic_sharpe_ratio=psr,
        min_track_record_length=min_trl_months,
        skewness=sk,
        kurtosis=kurt,
    )
