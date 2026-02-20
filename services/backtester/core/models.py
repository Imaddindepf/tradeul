"""
Pydantic v2 models for the professional backtester.

All inputs, outputs, and intermediate representations.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ── Enums ────────────────────────────────────────────────────────────────

class Timeframe(str, Enum):
    MIN_1 = "1min"
    MIN_5 = "5min"
    MIN_15 = "15min"
    MIN_30 = "30min"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"


class SignalOperator(str, Enum):
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"


class ExitType(str, Enum):
    TIME = "time"
    TARGET = "target"
    STOP_LOSS = "stop_loss"
    TRAILING_STOP = "trailing_stop"
    SIGNAL = "signal"
    EOD = "eod"


class UniverseMethod(str, Enum):
    ALL_US = "all_us"
    SECTOR = "sector"
    INDUSTRY = "industry"
    TICKER_LIST = "ticker_list"
    SQL_FILTER = "sql_filter"


class SlippageModel(str, Enum):
    FIXED_BPS = "fixed_bps"
    VOLUME_BASED = "volume_based"
    SPREAD_BASED = "spread_based"


# ── Strategy Definition ──────────────────────────────────────────────────

class Signal(BaseModel):
    indicator: str = Field(..., description="e.g. 'gap_pct', 'rsi_14', 'close', 'volume'")
    operator: SignalOperator
    value: float | str = Field(..., description="Numeric threshold or indicator name for crossovers")
    lookback: int | None = Field(None, description="Lookback period if indicator needs one")


class ExitRule(BaseModel):
    type: ExitType
    value: float | None = Field(None, description="Days for TIME, pct for TARGET/STOP_LOSS/TRAILING")
    signal: Signal | None = None


class UniverseFilter(BaseModel):
    method: UniverseMethod = UniverseMethod.ALL_US
    criteria: dict[str, Any] = Field(default_factory=dict)
    tickers: list[str] | None = None
    sql_where: str | None = Field(None, description="Raw SQL WHERE clause for DuckDB")


class StrategyConfig(BaseModel):
    """Complete strategy configuration parsed from natural language."""

    name: str = "Untitled Strategy"
    description: str = ""

    universe: UniverseFilter = Field(default_factory=UniverseFilter)
    entry_signals: list[Signal] = Field(..., min_length=1)
    entry_timing: Literal["open", "close", "next_open"] = "next_open"

    exit_rules: list[ExitRule] = Field(..., min_length=1)

    timeframe: Timeframe = Timeframe.DAY_1
    start_date: date
    end_date: date

    initial_capital: float = 100_000.0
    max_positions: int = 10
    position_size_pct: float = 0.10
    direction: Literal["long", "short", "both"] = "long"

    slippage_model: SlippageModel = SlippageModel.FIXED_BPS
    slippage_bps: float = 10.0
    commission_per_trade: float = 0.0

    risk_free_rate: float = 0.05

    @model_validator(mode="after")
    def validate_dates(self) -> "StrategyConfig":
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        if (self.end_date - self.start_date).days < 30:
            raise ValueError("Backtest period must be at least 30 days")
        return self


# ── Split Data ───────────────────────────────────────────────────────────

class SplitRecord(BaseModel):
    ticker: str
    execution_date: date
    split_from: float
    split_to: float

    @property
    def ratio(self) -> float:
        """Forward split ratio (e.g., 4.0 for a 4:1 split)."""
        return self.split_to / self.split_from if self.split_from else 1.0

    @property
    def price_factor(self) -> float:
        """Factor to multiply old prices by to get adjusted prices."""
        return self.split_from / self.split_to if self.split_to else 1.0


# ── Trade Records ────────────────────────────────────────────────────────

class TradeRecord(BaseModel):
    trade_id: int
    ticker: str
    direction: Literal["long", "short"]

    entry_date: date
    entry_price: float
    entry_fill_price: float

    exit_date: date
    exit_price: float
    exit_fill_price: float

    shares: float
    position_value: float
    pnl: float
    return_pct: float
    holding_bars: int

    slippage_cost: float
    commission_cost: float

    @property
    def is_winner(self) -> bool:
        return self.pnl > 0

    @property
    def gross_return_pct(self) -> float:
        return self.return_pct + (self.slippage_cost + self.commission_cost) / self.position_value


# ── Metrics ──────────────────────────────────────────────────────────────

class CoreMetrics(BaseModel):
    total_return_pct: float
    annualized_return_pct: float
    total_pnl: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown_pct: float
    max_drawdown_duration_days: int
    win_rate: float
    profit_factor: float
    expectancy: float
    avg_return_per_trade: float
    median_return_per_trade: float
    std_return_per_trade: float
    avg_winner_pct: float
    avg_loser_pct: float
    best_trade_pct: float
    worst_trade_pct: float
    total_trades: int
    avg_holding_bars: float
    recovery_factor: float
    ulcer_index: float
    tail_ratio: float
    common_sense_ratio: float


class AdvancedMetrics(BaseModel):
    deflated_sharpe_ratio: float = Field(
        ..., description="Lopez de Prado DSR accounting for multiple testing"
    )
    probabilistic_sharpe_ratio: float
    min_track_record_length: int = Field(
        ..., description="Months needed for statistical significance"
    )
    skewness: float
    kurtosis: float


class WalkForwardSplit(BaseModel):
    split_idx: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    train_sharpe: float
    test_sharpe: float
    train_trades: int
    test_trades: int
    degradation_pct: float


class WalkForwardResult(BaseModel):
    n_splits: int
    splits: list[WalkForwardSplit]
    mean_train_sharpe: float
    mean_test_sharpe: float
    mean_degradation_pct: float
    overfitting_probability: float = Field(
        ..., description="Probability that IS performance doesn't hold OOS"
    )


class MonteCarloResult(BaseModel):
    n_simulations: int
    median_final_equity: float
    mean_final_equity: float
    prob_profit: float
    prob_loss: float
    percentile_5_equity: float
    percentile_25_equity: float
    percentile_75_equity: float
    percentile_95_equity: float
    mean_max_drawdown_pct: float
    worst_max_drawdown_pct: float
    best_max_drawdown_pct: float


# ── Complete Result ──────────────────────────────────────────────────────

class BacktestResult(BaseModel):
    strategy: StrategyConfig
    core_metrics: CoreMetrics
    advanced_metrics: AdvancedMetrics | None = None
    walk_forward: WalkForwardResult | None = None
    monte_carlo: MonteCarloResult | None = None

    trades: list[TradeRecord]
    equity_curve: list[tuple[str, float]]
    drawdown_curve: list[tuple[str, float]]
    monthly_returns: dict[str, float]

    execution_time_ms: int
    symbols_tested: int
    bars_processed: int
    warnings: list[str] = Field(default_factory=list)


# ── API Models ───────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    strategy: StrategyConfig
    include_walk_forward: bool = True
    walk_forward_splits: int = 5
    include_monte_carlo: bool = True
    monte_carlo_simulations: int = 1000
    include_advanced_metrics: bool = True
    n_trials_for_dsr: int = 1


class BacktestResponse(BaseModel):
    status: Literal["success", "error"]
    result: BacktestResult | None = None
    error: str | None = None
