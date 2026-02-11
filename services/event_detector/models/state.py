"""
Ticker State - Tracks current and previous state for event detection.

The Event Detector compares current state vs previous state to detect
when thresholds are crossed (triggers).

Fields are populated from two sources:
1. Real-time aggregates (price, volume, minute_volume) - every ~1 second
2. Enriched snapshot cache (RVOL, change%, window metrics, etc.) - every ~30 seconds
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class TickerState:
    """
    Current state of a ticker at a point in time.
    
    Used to compare against previous state to detect events.
    """
    
    # ===== IDENTITY =====
    symbol: str
    timestamp: datetime
    
    # ===== REAL-TIME (from aggregate stream) =====
    price: float                            # Current price (aggregate close)
    volume: int                             # Accumulated volume today
    minute_volume: Optional[int] = None     # Volume in current minute bar
    
    # ===== VWAP =====
    vwap: Optional[float] = None            # Daily VWAP
    
    # ===== INTRADAY EXTREMES =====
    intraday_high: Optional[float] = None   # Day's high so far (includes pre/post)
    intraday_low: Optional[float] = None    # Day's low so far (includes pre/post)
    
    # ===== REFERENCE PRICES =====
    prev_close: Optional[float] = None      # Previous day's close
    open_price: Optional[float] = None      # Today's open price
    day_high: Optional[float] = None        # Regular session high
    day_low: Optional[float] = None         # Regular session low
    
    # ===== COMPUTED CHANGES =====
    change_percent: Optional[float] = None  # % change from prev close
    gap_percent: Optional[float] = None     # % gap = (open - prev_close) / prev_close
    change_from_open: Optional[float] = None  # % change from open = (price - open) / open
    
    # ===== WINDOW METRICS (from enriched) =====
    chg_1min: Optional[float] = None        # Price change % last 1 min
    chg_5min: Optional[float] = None        # Price change % last 5 min
    chg_10min: Optional[float] = None       # Price change % last 10 min
    chg_15min: Optional[float] = None       # Price change % last 15 min
    chg_30min: Optional[float] = None       # Price change % last 30 min
    vol_1min: Optional[int] = None          # Volume last 1 min
    vol_5min: Optional[int] = None          # Volume last 5 min
    
    # ===== RELATIVE VOLUME =====
    rvol: Optional[float] = None            # Relative volume
    
    # ===== TECHNICAL (from analytics enriched cache) =====
    atr: Optional[float] = None             # Average True Range (14-period)
    atr_percent: Optional[float] = None     # ATR as % of price
    trades_z_score: Optional[float] = None  # Z-Score of trades count
    
    # ===== TECHNICAL INDICATORS (from BarEngine / enriched cache) =====
    # EMA (kept for Bollinger context and legacy)
    ema_20: Optional[float] = None          # Intraday EMA(20) from 1-min bars
    ema_50: Optional[float] = None          # Intraday EMA(50) from 1-min bars
    # SMA — aligned with Trade Ideas (intraday from 1-min bars)
    sma_5: Optional[float] = None           # Intraday SMA(5)
    sma_8: Optional[float] = None           # Intraday SMA(8)
    sma_20: Optional[float] = None          # Intraday SMA(20)
    sma_50: Optional[float] = None          # Intraday SMA(50)
    sma_200: Optional[float] = None         # Intraday SMA(200)
    # Bollinger Bands
    bb_upper: Optional[float] = None        # Bollinger Band upper (EMA20 + 2σ)
    bb_lower: Optional[float] = None        # Bollinger Band lower (EMA20 - 2σ)
    # Oscillators
    rsi: Optional[float] = None             # RSI (14-period, from 1-min bars)
    macd_line: Optional[float] = None       # MACD line (12-26)
    macd_signal: Optional[float] = None     # MACD signal (9)
    macd_hist: Optional[float] = None       # MACD histogram
    stoch_k: Optional[float] = None         # Stochastic %K (14,3)
    stoch_d: Optional[float] = None         # Stochastic %D (smoothed)
    adx_14: Optional[float] = None          # ADX (14) — trend strength
    # Historical levels
    high_52w: Optional[float] = None        # 52-week high
    low_52w: Optional[float] = None         # 52-week low
    prev_day_high: Optional[float] = None   # Previous day's high
    prev_day_low: Optional[float] = None    # Previous day's low
    
    # ===== DAILY INDICATORS (from screener via enriched) =====
    daily_sma_200: Optional[float] = None   # Daily SMA(200) — for "crossed above 200-day MA"
    
    # ===== FUNDAMENTALS (from metadata via enriched) =====
    market_cap: Optional[float] = None      # Market capitalization
    float_shares: Optional[float] = None    # Free float shares
    security_type: Optional[str] = None     # CS, ETF, PFD, WARRANT, ADRC, etc.
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for condition evaluation."""
        result = {
            "symbol": self.symbol,
            "price": self.price,
            "volume": self.volume,
            "timestamp": self.timestamp.isoformat(),
        }
        # Include all optional fields that have values
        optional = {
            "minute_volume": self.minute_volume,
            "vwap": self.vwap,
            "intraday_high": self.intraday_high,
            "intraday_low": self.intraday_low,
            "prev_close": self.prev_close,
            "open_price": self.open_price,
            "day_high": self.day_high,
            "day_low": self.day_low,
            "change_percent": self.change_percent,
            "gap_percent": self.gap_percent,
            "change_from_open": self.change_from_open,
            "chg_1min": self.chg_1min,
            "chg_5min": self.chg_5min,
            "chg_10min": self.chg_10min,
            "chg_15min": self.chg_15min,
            "chg_30min": self.chg_30min,
            "vol_1min": self.vol_1min,
            "vol_5min": self.vol_5min,
            "rvol": self.rvol,
            "atr": self.atr,
            "atr_percent": self.atr_percent,
            "trades_z_score": self.trades_z_score,
            "ema_20": self.ema_20,
            "ema_50": self.ema_50,
            "sma_5": self.sma_5,
            "sma_8": self.sma_8,
            "sma_20": self.sma_20,
            "sma_50": self.sma_50,
            "sma_200": self.sma_200,
            "bb_upper": self.bb_upper,
            "bb_lower": self.bb_lower,
            "rsi": self.rsi,
            "macd_line": self.macd_line,
            "macd_signal": self.macd_signal,
            "macd_hist": self.macd_hist,
            "stoch_k": self.stoch_k,
            "stoch_d": self.stoch_d,
            "adx_14": self.adx_14,
            "high_52w": self.high_52w,
            "low_52w": self.low_52w,
            "prev_day_high": self.prev_day_high,
            "prev_day_low": self.prev_day_low,
            "daily_sma_200": self.daily_sma_200,
            "market_cap": self.market_cap,
            "float_shares": self.float_shares,
            "security_type": self.security_type,
        }
        for key, val in optional.items():
            if val is not None:
                result[key] = val
        return result


class TickerStateCache:
    """
    Cache of ticker states for comparison.
    
    Stores the previous state for each symbol so we can detect
    when values cross thresholds.
    """
    
    def __init__(self, max_age_seconds: int = 300):
        self._states: Dict[str, TickerState] = {}
        self._max_age_seconds = max_age_seconds
    
    def get(self, symbol: str) -> Optional[TickerState]:
        """Get previous state for a symbol."""
        state = self._states.get(symbol)
        if state:
            now = datetime.utcnow()
            ts = state.timestamp
            if ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)
            age = (now - ts).total_seconds()
            if age > self._max_age_seconds:
                del self._states[symbol]
                return None
        return state
    
    def set(self, symbol: str, state: TickerState) -> None:
        """Store state for a symbol."""
        self._states[symbol] = state
    
    def clear(self) -> None:
        """Clear all cached states."""
        self._states.clear()
    
    def cleanup_old(self) -> int:
        """Remove states older than max age. Returns count removed."""
        now = datetime.utcnow()
        old_symbols = []
        for s, state in self._states.items():
            ts = state.timestamp
            if ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)
            if (now - ts).total_seconds() > self._max_age_seconds:
                old_symbols.append(s)
        for symbol in old_symbols:
            del self._states[symbol]
        return len(old_symbols)
    
    @property
    def size(self) -> int:
        return len(self._states)
