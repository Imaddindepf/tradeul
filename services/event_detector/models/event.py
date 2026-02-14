"""
Event Models - Core data structures for market events.

Events are discrete occurrences that happen at a specific moment in time.
Unlike strategies (which evaluate current state), events capture "what happened and when".

Each EventType corresponds to a specific detector plugin.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
import uuid


class EventType(str, Enum):
    """
    Types of market events that can be detected.
    
    Organized by phase and category. Codes in comments are short codes
    used in the Alert Registry (Trade Ideas-style).
    
    Phase 1: Live (tick-based detectors)
    Phase 2: Daily indicators + confirmed crosses
    Phase 3+: Requires bar builder (future)
    """
    
    # ═══════════════════════════════════════════════════════════════════
    # PHASE 1 — LIVE (tick-based detectors)
    # ═══════════════════════════════════════════════════════════════════
    
    # --- Price Events ---
    NEW_HIGH = "new_high"                              # [NHP]
    NEW_LOW = "new_low"                                # [NLP]
    CROSSED_ABOVE_OPEN = "crossed_above_open"          # [CAO]
    CROSSED_BELOW_OPEN = "crossed_below_open"          # [CBO]
    CROSSED_ABOVE_PREV_CLOSE = "crossed_above_prev_close"  # [CAC]
    CROSSED_BELOW_PREV_CLOSE = "crossed_below_prev_close"  # [CBC]
    
    # --- VWAP Events ---
    VWAP_CROSS_UP = "vwap_cross_up"                    # [CAVC]
    VWAP_CROSS_DOWN = "vwap_cross_down"                # [CBVC]
    
    # --- Volume Events ---
    RVOL_SPIKE = "rvol_spike"                          # [HRV] RVOL > 3x
    VOLUME_SURGE = "volume_surge"                      # [SV] RVOL > 5x
    VOLUME_SPIKE_1MIN = "volume_spike_1min"            # [VS1]
    UNUSUAL_PRINTS = "unusual_prints"                  # [UNOP]
    BLOCK_TRADE = "block_trade"                        # [BP]
    
    # --- Momentum Events ---
    RUNNING_UP = "running_up"                          # [RUN]
    RUNNING_DOWN = "running_down"                      # [RDN]
    PERCENT_UP_5 = "percent_up_5"                      # [PUD] crosses +5%
    PERCENT_DOWN_5 = "percent_down_5"                  # [PDD] crosses -5%
    PERCENT_UP_10 = "percent_up_10"                    # [PU10] crosses +10%
    PERCENT_DOWN_10 = "percent_down_10"                # [PD10] crosses -10%
    
    # --- Pullback Events ---
    PULLBACK_75_FROM_HIGH = "pullback_75_from_high"    # [PFH75]
    PULLBACK_25_FROM_HIGH = "pullback_25_from_high"    # [PFH25]
    PULLBACK_75_FROM_LOW = "pullback_75_from_low"      # [PFL75]
    PULLBACK_25_FROM_LOW = "pullback_25_from_low"      # [PFL25]
    
    # --- Pullback Variants (Open/Close reference) ---
    PULLBACK_75_FROM_HIGH_CLOSE = "pullback_75_from_high_close"  # [PFH75C]
    PULLBACK_25_FROM_HIGH_CLOSE = "pullback_25_from_high_close"  # [PFH25C]
    PULLBACK_75_FROM_LOW_CLOSE = "pullback_75_from_low_close"    # [PFL75C]
    PULLBACK_25_FROM_LOW_CLOSE = "pullback_25_from_low_close"    # [PFL25C]
    PULLBACK_75_FROM_HIGH_OPEN = "pullback_75_from_high_open"    # [PFH75O]
    PULLBACK_25_FROM_HIGH_OPEN = "pullback_25_from_high_open"    # [PFH25O]
    PULLBACK_75_FROM_LOW_OPEN = "pullback_75_from_low_open"      # [PFL75O]
    PULLBACK_25_FROM_LOW_OPEN = "pullback_25_from_low_open"      # [PFL25O]
    
    # --- Gap Events ---
    GAP_UP_REVERSAL = "gap_up_reversal"                # [GUR]
    GAP_DOWN_REVERSAL = "gap_down_reversal"            # [GDR]
    
    # --- Halt Events ---
    HALT = "halt"                                      # [HALT]
    RESUME = "resume"                                  # [RESUME]
    
    # ═══════════════════════════════════════════════════════════════════
    # PHASE 1B — SNAPSHOT-DRIVEN (full market, detected from enriched snapshot)
    # ═══════════════════════════════════════════════════════════════════
    
    # --- DEPRECATED: Price vs Intraday SMA/EMA (1-min bars) ---
    # These don't exist in Trade Ideas. TI uses DAILY MAs for price-vs-MA alerts.
    # Kept for backward compat with stored events; NO LONGER EMITTED.
    CROSSED_ABOVE_EMA20 = "crossed_above_ema20"        # DEPRECATED — use daily
    CROSSED_BELOW_EMA20 = "crossed_below_ema20"        # DEPRECATED
    CROSSED_ABOVE_EMA50 = "crossed_above_ema50"        # DEPRECATED
    CROSSED_BELOW_EMA50 = "crossed_below_ema50"        # DEPRECATED
    CROSSED_ABOVE_SMA8 = "crossed_above_sma8"          # DEPRECATED — TI has no equivalent
    CROSSED_BELOW_SMA8 = "crossed_below_sma8"          # DEPRECATED
    CROSSED_ABOVE_SMA20 = "crossed_above_sma20"        # DEPRECATED — use daily
    CROSSED_BELOW_SMA20 = "crossed_below_sma20"        # DEPRECATED
    CROSSED_ABOVE_SMA50 = "crossed_above_sma50"        # DEPRECATED — use daily
    CROSSED_BELOW_SMA50 = "crossed_below_sma50"        # DEPRECATED
    
    # --- DEPRECATED: 1-min MA-to-MA / MACD / Stoch (replaced by 5-min) ---
    SMA_8_CROSS_ABOVE_20 = "sma_8_cross_above_20"      # DEPRECATED — use 5m
    SMA_8_CROSS_BELOW_20 = "sma_8_cross_below_20"      # DEPRECATED
    MACD_CROSS_BULLISH = "macd_cross_bullish"           # DEPRECATED — use 5m
    MACD_CROSS_BEARISH = "macd_cross_bearish"           # DEPRECATED
    MACD_ZERO_CROSS_UP = "macd_zero_cross_up"           # DEPRECATED — use 5m
    MACD_ZERO_CROSS_DOWN = "macd_zero_cross_down"       # DEPRECATED
    STOCH_CROSS_BULLISH = "stoch_cross_bullish"         # DEPRECATED — use 5m
    STOCH_CROSS_BEARISH = "stoch_cross_bearish"         # DEPRECATED
    STOCH_OVERSOLD = "stoch_oversold"                   # DEPRECATED — use 5m
    STOCH_OVERBOUGHT = "stoch_overbought"               # DEPRECATED
    
    # --- Daily SMA Crosses (what Trade Ideas CA20/CA50 actually are) ---
    CROSSED_ABOVE_SMA20_DAILY = "crossed_above_sma20_daily"  # [CA20] Daily SMA(20)
    CROSSED_BELOW_SMA20_DAILY = "crossed_below_sma20_daily"  # [CB20] Daily SMA(20)
    CROSSED_ABOVE_SMA50_DAILY = "crossed_above_sma50_daily"  # [CA50] Daily SMA(50)
    CROSSED_BELOW_SMA50_DAILY = "crossed_below_sma50_daily"  # [CB50] Daily SMA(50)
    
    # --- 5-min MA-to-MA Crosses (Trade Ideas ECAY5/ECBY5) ---
    SMA8_ABOVE_SMA20_5M = "sma8_above_sma20_5min"     # [ECAY5] SMA(8) crosses SMA(20) on 5m
    SMA8_BELOW_SMA20_5M = "sma8_below_sma20_5min"     # [ECBY5]
    
    # --- 5-min MACD Crosses (Trade Ideas MDAS5/MDBS5/MDAZ5/MDBZ5) ---
    MACD_ABOVE_SIGNAL_5M = "macd_above_signal_5min"    # [MDAS5]
    MACD_BELOW_SIGNAL_5M = "macd_below_signal_5min"    # [MDBS5]
    MACD_ABOVE_ZERO_5M = "macd_above_zero_5min"        # [MDAZ5]
    MACD_BELOW_ZERO_5M = "macd_below_zero_5min"        # [MDBZ5]
    
    # --- 5-min Stochastic (Trade Ideas SC20_5/SC80_5) ---
    STOCH_CROSS_BULLISH_5M = "stoch_cross_bullish_5min"    # %K crosses above %D (oversold, 5m)
    STOCH_CROSS_BEARISH_5M = "stoch_cross_bearish_5min"    # %K crosses below %D (overbought, 5m)
    STOCH_OVERSOLD_5M = "stoch_oversold_5min"              # %K < 20 on 5m
    STOCH_OVERBOUGHT_5M = "stoch_overbought_5min"          # %K > 80 on 5m
    
    # --- Opening Range Breakout ---
    ORB_BREAKOUT_UP = "orb_breakout_up"                # [ORBU] Price breaks above first N-min range
    ORB_BREAKOUT_DOWN = "orb_breakout_down"            # [ORBD] Price breaks below first N-min range
    
    # --- Consolidation Breakout ---
    CONSOLIDATION_BREAKOUT_UP = "consolidation_breakout_up"    # [CBU]
    CONSOLIDATION_BREAKOUT_DOWN = "consolidation_breakout_down"  # [CBD]
    
    # --- Bollinger Band Events ---
    BB_UPPER_BREAKOUT = "bb_upper_breakout"            # [BBU]
    BB_LOWER_BREAKDOWN = "bb_lower_breakdown"          # [BBD]
    
    # --- Daily Support/Resistance ---
    CROSSED_DAILY_HIGH_RESISTANCE = "crossed_daily_high_resistance"  # [CDHR]
    CROSSED_DAILY_LOW_SUPPORT = "crossed_daily_low_support"          # [CDLS]
    
    # --- Gap Variants ---
    FALSE_GAP_UP_RETRACEMENT = "false_gap_up_retracement"    # [FGUR]
    FALSE_GAP_DOWN_RETRACEMENT = "false_gap_down_retracement"  # [FGDR]
    
    # --- Momentum Variants (time-window based) ---
    RUNNING_UP_SUSTAINED = "running_up_sustained"      # [RU] chg_10min > 3%
    RUNNING_DOWN_SUSTAINED = "running_down_sustained"  # [RD] chg_10min < -3%
    RUNNING_UP_CONFIRMED = "running_up_confirmed"      # [RUC] chg_5min>2% AND chg_15min>4%
    RUNNING_DOWN_CONFIRMED = "running_down_confirmed"  # [RDC] chg_5min<-2% AND chg_15min<-4%
    
    # ═══════════════════════════════════════════════════════════════════
    # PHASE 2 — FUTURE (requires additional data / infrastructure)
    # ═══════════════════════════════════════════════════════════════════
    
    # --- Daily SMA Crosses (requires historical daily bars) ---
    CROSSED_ABOVE_SMA200 = "crossed_above_sma200"      # [CA200] Daily SMA(200)
    CROSSED_BELOW_SMA200 = "crossed_below_sma200"      # [CB200] Daily SMA(200)
    
    # --- Pre/Post Market ---
    PRE_MARKET_HIGH = "pre_market_high"                # [HPRE]
    PRE_MARKET_LOW = "pre_market_low"                  # [LPRE]
    POST_MARKET_HIGH = "post_market_high"              # [HPOST]
    POST_MARKET_LOW = "post_market_low"                # [LPOST]
    
    # --- Confirmed Crosses (requires confirmation timer) ---
    CROSSED_ABOVE_OPEN_CONFIRMED = "crossed_above_open_confirmed"    # [CAOC]
    CROSSED_BELOW_OPEN_CONFIRMED = "crossed_below_open_confirmed"    # [CBOC]
    CROSSED_ABOVE_CLOSE_CONFIRMED = "crossed_above_close_confirmed"  # [CACC]
    CROSSED_BELOW_CLOSE_CONFIRMED = "crossed_below_close_confirmed"  # [CBCC]
    
    # --- VWAP Divergence (requires price lows/highs tracking) ---
    VWAP_DIVERGENCE_UP = "vwap_divergence_up"          # [VDU]
    VWAP_DIVERGENCE_DOWN = "vwap_divergence_down"      # [VDD]


# Mapping: event_type string → EventType enum (for fast lookup)
EVENT_TYPE_MAP: Dict[str, EventType] = {e.value: e for e in EventType}


@dataclass
class EventRecord:
    """
    A discrete market event that occurred at a specific moment.
    
    This is the core output of the Event Detector - each instance represents
    something that HAPPENED (past tense) rather than a current condition.
    """
    
    event_type: EventType
    rule_id: str
    symbol: str
    timestamp: datetime
    price: float
    
    # Event-specific values
    prev_value: Optional[float] = None
    new_value: Optional[float] = None
    delta: Optional[float] = None
    delta_percent: Optional[float] = None
    
    # Context at event time (snapshot of key metrics when event fired)
    change_percent: Optional[float] = None
    rvol: Optional[float] = None
    volume: Optional[int] = None
    market_cap: Optional[float] = None
    gap_percent: Optional[float] = None
    change_from_open: Optional[float] = None
    open_price: Optional[float] = None
    prev_close: Optional[float] = None
    vwap: Optional[float] = None
    atr_percent: Optional[float] = None
    intraday_high: Optional[float] = None
    intraday_low: Optional[float] = None
    
    # Time-window changes (from analytics enrichment)
    chg_1min: Optional[float] = None
    chg_5min: Optional[float] = None
    chg_10min: Optional[float] = None
    chg_15min: Optional[float] = None
    chg_30min: Optional[float] = None
    vol_1min: Optional[int] = None
    vol_5min: Optional[int] = None
    
    # Technical indicators (from BarEngine via enriched)
    float_shares: Optional[float] = None
    rsi: Optional[float] = None
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    
    # Fundamentals (from metadata via enriched)
    security_type: Optional[str] = None     # CS, ETF, PFD, WARRANT, ADRC, etc.
    sector: Optional[str] = None            # Technology, Healthcare, etc.
    
    # Metadata
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization (Redis-safe: no None values)."""
        import json
        result = {
            "id": self.id,
            "event_type": self.event_type.value,
            "rule_id": self.rule_id,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "price": self.price,
        }
        
        # Only include optional fields if they have values (Redis doesn't accept None)
        optional_floats = {
            "prev_value": self.prev_value,
            "new_value": self.new_value,
            "delta": self.delta,
            "delta_percent": self.delta_percent,
            "change_percent": self.change_percent,
            "rvol": self.rvol,
            "market_cap": self.market_cap,
            "gap_percent": self.gap_percent,
            "change_from_open": self.change_from_open,
            "open_price": self.open_price,
            "prev_close": self.prev_close,
            "vwap": self.vwap,
            "atr_percent": self.atr_percent,
            "intraday_high": self.intraday_high,
            "intraday_low": self.intraday_low,
            # Time-window changes
            "chg_1min": self.chg_1min,
            "chg_5min": self.chg_5min,
            "chg_10min": self.chg_10min,
            "chg_15min": self.chg_15min,
            "chg_30min": self.chg_30min,
            # Technical indicators
            "float_shares": self.float_shares,
            "rsi": self.rsi,
            "ema_20": self.ema_20,
            "ema_50": self.ema_50,
        }
        for key, val in optional_floats.items():
            if val is not None:
                result[key] = val

        # Integer optional fields
        if self.volume is not None:
            result["volume"] = self.volume
        if self.vol_1min is not None:
            result["vol_1min"] = self.vol_1min
        if self.vol_5min is not None:
            result["vol_5min"] = self.vol_5min
        # String optional fields
        if self.security_type is not None:
            result["security_type"] = self.security_type
        if self.sector is not None:
            result["sector"] = self.sector
        
        if self.details:
            result["details"] = json.dumps(self.details) if isinstance(self.details, dict) else str(self.details)
            
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventRecord":
        """Create from dictionary."""

        def _float(key: str) -> Optional[float]:
            v = data.get(key)
            return float(v) if v is not None and v != "" else None

        def _int(key: str) -> Optional[int]:
            v = data.get(key)
            return int(v) if v is not None and v != "" else None

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            event_type=EventType(data["event_type"]),
            rule_id=data["rule_id"],
            symbol=data["symbol"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            price=float(data["price"]),
            prev_value=_float("prev_value"),
            new_value=_float("new_value"),
            delta=_float("delta"),
            delta_percent=_float("delta_percent"),
            change_percent=_float("change_percent"),
            rvol=_float("rvol"),
            volume=_int("volume"),
            market_cap=_float("market_cap"),
            gap_percent=_float("gap_percent"),
            change_from_open=_float("change_from_open"),
            open_price=_float("open_price"),
            prev_close=_float("prev_close"),
            vwap=_float("vwap"),
            atr_percent=_float("atr_percent"),
            intraday_high=_float("intraday_high"),
            intraday_low=_float("intraday_low"),
            # Time-window changes
            chg_1min=_float("chg_1min"),
            chg_5min=_float("chg_5min"),
            chg_10min=_float("chg_10min"),
            chg_15min=_float("chg_15min"),
            chg_30min=_float("chg_30min"),
            vol_1min=_int("vol_1min"),
            vol_5min=_int("vol_5min"),
            # Technical indicators
            float_shares=_float("float_shares"),
            rsi=_float("rsi"),
            ema_20=_float("ema_20"),
            ema_50=_float("ema_50"),
            # Fundamentals
            security_type=data.get("security_type"),
            sector=data.get("sector"),
            details=data.get("details"),
        )
