"""Tests for core.metrics – compute_core_metrics & compute_advanced_metrics."""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from core.metrics import compute_core_metrics, compute_advanced_metrics
from core.models import TradeRecord


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_trade(
    trade_id: int,
    return_pct: float,
    pnl: float | None = None,
    entry_price: float = 100.0,
    holding_bars: int = 3,
    day: int | None = None,
) -> TradeRecord:
    """Build a minimal TradeRecord for metrics tests."""
    if day is None:
        day = trade_id
    shares = 100.0
    position_value = entry_price * shares
    if pnl is None:
        pnl = position_value * return_pct / 100.0
    exit_price = entry_price * (1 + return_pct / 100.0)
    return TradeRecord(
        trade_id=trade_id,
        ticker="TEST",
        direction="long",
        entry_date=date(2024, 1, day),
        entry_price=entry_price,
        entry_fill_price=entry_price,
        exit_date=date(2024, 1, day + holding_bars),
        exit_price=round(exit_price, 4),
        exit_fill_price=round(exit_price, 4),
        shares=shares,
        position_value=position_value,
        pnl=round(pnl, 2),
        return_pct=return_pct,
        holding_bars=holding_bars,
        slippage_cost=0.0,
        commission_cost=0.0,
    )


def _rising_equity(n: int = 100, start: float = 100_000.0) -> np.ndarray:
    """Equity curve that steadily rises ~0.1 % per bar."""
    rng = np.random.default_rng(42)
    returns = rng.normal(0.001, 0.002, size=n)
    returns = np.abs(returns)  # ensure all positive
    return start * np.cumprod(np.concatenate([[1.0], 1 + returns]))


def _falling_equity(n: int = 100, start: float = 100_000.0) -> np.ndarray:
    """Equity curve that steadily falls."""
    rng = np.random.default_rng(42)
    returns = rng.normal(-0.001, 0.002, size=n)
    returns = -np.abs(returns)  # ensure all negative
    return start * np.cumprod(np.concatenate([[1.0], 1 + returns]))


# ── Tests ────────────────────────────────────────────────────────────────


class TestSharpeRatio:
    def test_sharpe_ratio_positive(self):
        """Consistently profitable trades + rising equity -> positive Sharpe."""
        trades = [_make_trade(i + 1, return_pct=2.0, day=i + 1) for i in range(20)]
        equity = _rising_equity(100)
        metrics = compute_core_metrics(trades, equity, initial_capital=100_000.0)
        assert metrics.sharpe_ratio > 0

    def test_sharpe_ratio_negative(self):
        """Consistently losing trades + falling equity -> negative Sharpe."""
        trades = [_make_trade(i + 1, return_pct=-2.0, day=i + 1) for i in range(20)]
        equity = _falling_equity(100)
        metrics = compute_core_metrics(trades, equity, initial_capital=100_000.0)
        assert metrics.sharpe_ratio < 0


class TestWinRate:
    def test_win_rate_calculation(self):
        """6 winners + 4 losers = 60 % win rate."""
        trades = (
            [_make_trade(i + 1, return_pct=3.0, day=i + 1) for i in range(6)]
            + [_make_trade(i + 7, return_pct=-2.0, day=i + 7) for i in range(4)]
        )
        equity = _rising_equity(50)
        metrics = compute_core_metrics(trades, equity, initial_capital=100_000.0)
        assert metrics.win_rate == pytest.approx(0.6)


class TestProfitFactor:
    def test_profit_factor(self):
        """profit_factor = sum(winner returns) / |sum(loser returns)|."""
        winners = [_make_trade(i + 1, return_pct=5.0, day=i + 1) for i in range(3)]
        losers = [_make_trade(i + 4, return_pct=-2.0, day=i + 4) for i in range(3)]
        trades = winners + losers
        equity = _rising_equity(50)
        metrics = compute_core_metrics(trades, equity, initial_capital=100_000.0)
        expected = (3 * 5.0) / (3 * 2.0)
        assert metrics.profit_factor == pytest.approx(expected, rel=1e-6)


class TestMaxDrawdown:
    def test_max_drawdown(self):
        """Known equity curve: peak 110, trough 90 -> dd = (90-110)/110 ≈ -18.18 %."""
        equity = np.array([100.0, 110.0, 90.0, 95.0, 100.0])
        trades = [_make_trade(1, return_pct=0.0, day=1)]
        metrics = compute_core_metrics(trades, equity, initial_capital=100.0)
        assert metrics.max_drawdown_pct == pytest.approx(-20.0 / 110.0, abs=1e-4)


class TestZeroTrades:
    def test_zero_trades_raises(self):
        """Empty trade list must raise ValueError."""
        equity = np.array([100_000.0])
        with pytest.raises(ValueError, match="zero trades"):
            compute_core_metrics([], equity, initial_capital=100_000.0)


class TestAdvancedMetrics:
    def _build_context(self):
        trades = [_make_trade(i + 1, return_pct=1.5, day=i + 1) for i in range(25)]
        equity = _rising_equity(200)
        core = compute_core_metrics(trades, equity, initial_capital=100_000.0)
        return trades, equity, core

    def test_advanced_metrics_dsr(self):
        """Deflated Sharpe Ratio should be between 0 and 1."""
        trades, equity, core = self._build_context()
        adv = compute_advanced_metrics(
            trades, equity, observed_sharpe=core.sharpe_ratio, n_trials=1,
        )
        assert 0.0 <= adv.deflated_sharpe_ratio <= 1.0

    def test_advanced_metrics_psr(self):
        """Probabilistic Sharpe Ratio should be between 0 and 1."""
        trades, equity, core = self._build_context()
        adv = compute_advanced_metrics(
            trades, equity, observed_sharpe=core.sharpe_ratio, n_trials=1,
        )
        assert 0.0 <= adv.probabilistic_sharpe_ratio <= 1.0


class TestRecoveryFactor:
    def test_recovery_factor(self):
        """recovery_factor = total_return / |max_drawdown|."""
        equity = np.array([100.0, 120.0, 100.0, 130.0])
        trades = [
            _make_trade(1, return_pct=5.0, day=1),
            _make_trade(2, return_pct=-3.0, day=2),
            _make_trade(3, return_pct=8.0, day=3),
        ]
        metrics = compute_core_metrics(trades, equity, initial_capital=100.0)
        expected = metrics.total_return_pct / abs(metrics.max_drawdown_pct)
        assert metrics.recovery_factor == pytest.approx(expected, rel=1e-6)


class TestTailRatio:
    def test_tail_ratio(self):
        """With enough trades tail_ratio = |P95| / |P5| and should be > 0."""
        rng = np.random.default_rng(42)
        trades = [
            _make_trade(i + 1, return_pct=float(rng.normal(1.0, 3.0)), day=i + 1)
            for i in range(25)
        ]
        equity = _rising_equity(100)
        metrics = compute_core_metrics(trades, equity, initial_capital=100_000.0)
        assert metrics.tail_ratio > 0
