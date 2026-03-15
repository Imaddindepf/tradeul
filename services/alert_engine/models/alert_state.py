"""
Alert State — Extended ticker state with volatility baselines and historical levels.

AlertState = TickerState + per-ticker volatility + daily extremes for lookback.
Built once per tick from multiple Redis sources, consumed by all detectors.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, Dict, List, Any


@dataclass
class DailyExtreme:
    """One day's high/low/close from historical data."""
    trading_date: date
    days_ago: int
    high: float
    low: float
    close: float


@dataclass
class VolatilityBaseline:
    """Per-ticker volatility computed pre-market from historical data."""
    intraday_vol_1m: float      # σ of 1-minute price changes (2 weeks of minute bars)
    intraday_vol_5m: float      # σ of 5-minute price changes
    intraday_vol_15m: float     # σ of 15-minute price changes
    daily_vol_annual: float     # annualized daily σ (1 year of daily bars)
    avg_dollar_move_1m: float   # average |Δprice| per minute
    avg_daily_volume: float     # average daily volume (recent days)


@dataclass
class AlertState:
    """
    Complete state for alert detection on a single ticker at a point in time.

    Extends the concept of TickerState with volatility baselines and bid/ask tracking.
    All fields populated from existing Redis data sources — no new infrastructure needed.
    """

    # ── Identity ──
    symbol: str
    timestamp: datetime

    # ── Real-time price (from aggregate stream or enriched snapshot) ──
    price: float
    volume: int
    minute_volume: Optional[int] = None
    last_trade_size: Optional[int] = None

    # ── Bid/Ask (from enriched snapshot — Polygon NBBO) ──
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_size: Optional[int] = None
    ask_size: Optional[int] = None
    spread: Optional[float] = None

    # ── VWAP ──
    vwap: Optional[float] = None

    # ── Intraday extremes ──
    intraday_high: Optional[float] = None
    intraday_low: Optional[float] = None

    # ── Reference prices ──
    prev_close: Optional[float] = None
    prev_open: Optional[float] = None
    open_price: Optional[float] = None
    prev_day_high: Optional[float] = None
    prev_day_low: Optional[float] = None

    # ── Computed changes ──
    change_percent: Optional[float] = None
    gap_percent: Optional[float] = None
    change_from_open: Optional[float] = None

    # ── Window metrics (from enriched snapshot) ──
    chg_1min: Optional[float] = None
    chg_5min: Optional[float] = None
    chg_10min: Optional[float] = None
    chg_15min: Optional[float] = None
    chg_30min: Optional[float] = None
    chg_60min: Optional[float] = None
    vol_1min: Optional[int] = None
    vol_5min: Optional[int] = None
    vol_1min_pct: Optional[float] = None
    vol_5min_pct: Optional[float] = None

    # ── Average daily volume (from screener, fallback when baseline unavailable) ──
    avg_daily_volume: Optional[float] = None

    # ── Relative volume ──
    rvol: Optional[float] = None

    # ── Volatility / ATR ──
    atr: Optional[float] = None
    atr_percent: Optional[float] = None
    trades_z_score: Optional[float] = None

    # ── Technical indicators (1-min from BarEngine) ──
    sma_5: Optional[float] = None
    sma_8: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    rsi: Optional[float] = None
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None
    adx_14: Optional[float] = None

    # ── Daily indicators (from screener via enriched) ──
    daily_sma_20: Optional[float] = None
    daily_sma_50: Optional[float] = None
    daily_sma_200: Optional[float] = None

    # ── 52-week ──
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None

    # ── Fundamentals ──
    market_cap: Optional[float] = None
    float_shares: Optional[float] = None
    shares_outstanding: Optional[int] = None
    security_type: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None

    # ── Session / Exchange ──
    market_session: Optional[str] = None
    exchange: Optional[str] = None

    # ── Multi-timeframe indicators (5m from BarEngine) ──
    sma_8_5m: Optional[float] = None
    sma_20_5m: Optional[float] = None
    macd_line_5m: Optional[float] = None
    macd_signal_5m: Optional[float] = None
    stoch_k_5m: Optional[float] = None
    stoch_d_5m: Optional[float] = None

    # ── N-minute candle data (from BarEngine, for IDH/IDL alerts) ──
    prev_bar_high_5m: Optional[float] = None
    prev_bar_low_5m: Optional[float] = None
    cur_bar_high_5m: Optional[float] = None
    cur_bar_low_5m: Optional[float] = None
    prev_bar_high_10m: Optional[float] = None
    prev_bar_low_10m: Optional[float] = None
    cur_bar_high_10m: Optional[float] = None
    cur_bar_low_10m: Optional[float] = None
    prev_bar_high_15m: Optional[float] = None
    prev_bar_low_15m: Optional[float] = None
    cur_bar_high_15m: Optional[float] = None
    cur_bar_low_15m: Optional[float] = None
    prev_bar_high_30m: Optional[float] = None
    prev_bar_low_30m: Optional[float] = None
    cur_bar_high_30m: Optional[float] = None
    cur_bar_low_30m: Optional[float] = None
    prev_bar_high_60m: Optional[float] = None
    prev_bar_low_60m: Optional[float] = None
    cur_bar_high_60m: Optional[float] = None
    cur_bar_low_60m: Optional[float] = None

    # ── PRE-LOADED BASELINES (from Redis, loaded at engine start + refreshed) ──
    volatility: Optional[VolatilityBaseline] = None
    daily_extremes: Optional[List[DailyExtreme]] = None


class AlertStateCache:
    """
    Cache of previous AlertState per symbol for cross-detection.

    Same pattern as TickerStateCache but for AlertState.
    """

    def __init__(self, max_age_seconds: int = 300):
        self._states: Dict[str, AlertState] = {}
        self._max_age = max_age_seconds

    def get(self, symbol: str) -> Optional[AlertState]:
        state = self._states.get(symbol)
        if state is None:
            return None
        age = (datetime.utcnow() - state.timestamp.replace(tzinfo=None)).total_seconds()
        if age > self._max_age:
            del self._states[symbol]
            return None
        return state

    def set(self, symbol: str, state: AlertState) -> None:
        self._states[symbol] = state

    def clear(self) -> None:
        self._states.clear()

    def cleanup_old(self) -> int:
        now = datetime.utcnow()
        stale = [
            s for s, st in self._states.items()
            if (now - st.timestamp.replace(tzinfo=None)).total_seconds() > self._max_age
        ]
        for s in stale:
            del self._states[s]
        return len(stale)

    @property
    def size(self) -> int:
        return len(self._states)
