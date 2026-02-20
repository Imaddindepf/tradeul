"""Tests for engine signal evaluation, fill model, and Monte Carlo."""
from __future__ import annotations
from datetime import date
import numpy as np
import pandas as pd
import pytest
from core.engine import evaluate_entries, _evaluate_signal
from core.fill_model import estimate_fill
from core.models import Signal, SignalOperator, SlippageModel, TradeRecord
from analysis.monte_carlo import MonteCarloAnalyzer


def _make_trade(tid: int, return_pct: float) -> TradeRecord:
    entry = 100.0
    shares = 100.0
    pnl = entry * shares * return_pct / 100.0
    exit_p = entry * (1 + return_pct / 100.0)
    return TradeRecord(
        trade_id=tid, ticker="TEST", direction="long",
        entry_date=date(2024, 1, tid), entry_price=entry,
        entry_fill_price=entry, exit_date=date(2024, 1, tid + 3),
        exit_price=round(exit_p, 4), exit_fill_price=round(exit_p, 4),
        shares=shares, position_value=entry * shares,
        pnl=round(pnl, 2), return_pct=return_pct,
        holding_bars=3, slippage_cost=0.0, commission_cost=0.0,
    )


class TestEvaluateSignal:
    def test_evaluate_gt_signal(self):
        df = pd.DataFrame({"close": [90.0, 100.0, 110.0, 120.0]})
        sig = Signal(indicator="close", operator=SignalOperator.GT, value=100.0)
        result = _evaluate_signal(df, sig)
        expected = pd.Series([False, False, True, True])
        pd.testing.assert_series_equal(result.reset_index(drop=True), expected, check_names=False)

    def test_evaluate_crosses_above(self):
        df = pd.DataFrame({"close": [95.0, 98.0, 105.0, 110.0], "sma_20": [100.0, 100.0, 100.0, 100.0]})
        sig = Signal(indicator="close", operator=SignalOperator.CROSSES_ABOVE, value="sma_20")
        result = _evaluate_signal(df, sig)
        assert result.iloc[0] == False
        assert result.iloc[1] == False
        assert result.iloc[2] == True
        assert result.iloc[3] == False


class TestEvaluateEntries:
    def test_evaluate_entries_multiple_signals(self):
        df = pd.DataFrame({"close": [90.0, 105.0, 110.0, 120.0], "volume": [500000, 1500000, 2000000, 800000]})
        signals = [
            Signal(indicator="close", operator=SignalOperator.GT, value=100.0),
            Signal(indicator="volume", operator=SignalOperator.GT, value=1000000.0),
        ]
        result = evaluate_entries(df, signals)
        expected = pd.Series([False, True, True, False])
        pd.testing.assert_series_equal(result.reset_index(drop=True), expected, check_names=False)


class TestFillModel:
    def test_fill_model_fixed_bps(self):
        fill = estimate_fill(
            side="buy", reference_price=100.0, bar_volume=1000000,
            bar_vwap=100.0, order_size_dollars=10000.0,
            model=SlippageModel.FIXED_BPS, slippage_bps=10.0,
        )
        assert fill.fill_price == pytest.approx(100.10, rel=1e-6)
        assert fill.fill_pct == 1.0

    def test_fill_model_volume_based(self):
        fill = estimate_fill(
            side="buy", reference_price=100.0, bar_volume=1000000,
            bar_vwap=100.0, order_size_dollars=100000.0,
            model=SlippageModel.VOLUME_BASED, impact_coefficient=0.1,
        )
        assert fill.fill_price > 100.0
        assert fill.slippage_cost > 0.0


class TestMonteCarlo:
    def test_monte_carlo_basic(self):
        trades = [_make_trade(i + 1, return_pct=float(r)) for i, r in enumerate(np.random.default_rng(42).normal(1.0, 3.0, size=10))]
        mc = MonteCarloAnalyzer()
        result = mc.simulate(trades, n_simulations=100, initial_capital=100000.0)
        assert result.n_simulations == 100
        assert 0.0 <= result.prob_profit <= 1.0
