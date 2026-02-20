"""
Shared fixtures for backtester test suite.

All fixtures produce synthetic data so tests never depend on real FLATS files
or external services.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure the backtester package root is importable
_backtester_root = Path(__file__).resolve().parent.parent
if str(_backtester_root) not in sys.path:
    sys.path.insert(0, str(_backtester_root))

from core.models import (
    ExitRule,
    ExitType,
    Signal,
    SignalOperator,
    StrategyConfig,
    TradeRecord,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def sample_bars_df() -> pd.DataFrame:
    """DataFrame with 2 tickers (AAPL, TSLA), 100 trading days each."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2024-01-01", periods=100, freq="B")

    rows: list[dict] = []
    for ticker, start_price in [("AAPL", 150.0), ("TSLA", 250.0)]:
        price = start_price
        for d in dates:
            change = rng.normal(0, 0.015) * price
            open_ = price
            close = price + change
            high = max(open_, close) + abs(rng.normal(0, 0.005) * price)
            low = min(open_, close) - abs(rng.normal(0, 0.005) * price)
            volume = int(rng.integers(100_000, 1_000_001))
            vwap = (open_ + high + low + close) / 4.0
            transactions = int(rng.integers(500, 5_000))
            rows.append(
                {
                    "ticker": ticker,
                    "date": d,
                    "open": round(open_, 4),
                    "high": round(high, 4),
                    "low": round(low, 4),
                    "close": round(close, 4),
                    "volume": volume,
                    "vwap": round(vwap, 4),
                    "transactions": transactions,
                }
            )
            price = close

    df = pd.DataFrame(rows)
    return df


@pytest.fixture()
def sample_trades() -> list[TradeRecord]:
    """20 TradeRecord objects — mix of winners and losers."""
    rng = np.random.default_rng(42)
    trades: list[TradeRecord] = []

    tickers = ["AAPL", "TSLA", "MSFT", "GOOG", "AMZN"]
    for i in range(20):
        ticker = tickers[i % len(tickers)]
        entry_price = float(rng.uniform(100, 400))
        # Alternate winners / losers: roughly 60 % winners
        if rng.random() < 0.6:
            return_pct = float(rng.uniform(0.5, 8.0))
        else:
            return_pct = float(rng.uniform(-8.0, -0.5))

        pnl = entry_price * 100 * return_pct / 100.0
        exit_price = entry_price * (1 + return_pct / 100.0)
        slippage = float(rng.uniform(0.5, 3.0))
        commission = 1.0
        holding = int(rng.integers(1, 15))

        trades.append(
            TradeRecord(
                trade_id=i + 1,
                ticker=ticker,
                direction="long",
                entry_date=date(2024, 1, 2 + i),
                entry_price=round(entry_price, 2),
                entry_fill_price=round(entry_price * 1.001, 2),
                exit_date=date(2024, 1, 2 + i + holding),
                exit_price=round(exit_price, 2),
                exit_fill_price=round(exit_price * 0.999, 2),
                shares=100.0,
                position_value=round(entry_price * 100, 2),
                pnl=round(pnl, 2),
                return_pct=round(return_pct, 4),
                holding_bars=holding,
                slippage_cost=round(slippage, 2),
                commission_cost=commission,
            )
        )

    return trades


@pytest.fixture()
def sample_equity_curve() -> np.ndarray:
    """200-point equity curve starting at 100 000 with small daily returns."""
    rng = np.random.default_rng(42)
    daily_returns = rng.normal(0.0003, 0.01, size=200)
    equity = 100_000.0 * np.cumprod(1 + daily_returns)
    # Prepend the initial capital so length is 201 — first value is exactly 100k
    equity = np.insert(equity, 0, 100_000.0)
    return equity


@pytest.fixture()
def sample_strategy() -> StrategyConfig:
    """Minimal valid StrategyConfig for testing."""
    return StrategyConfig(
        name="Test Gap Strategy",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 6, 1),
        entry_signals=[
            Signal(
                indicator="gap_pct",
                operator=SignalOperator.GT,
                value=2.0,
            ),
        ],
        exit_rules=[
            ExitRule(type=ExitType.TIME, value=5),
        ],
    )
