"""
Alert Record — The output of the alert engine.

Extends EventRecord with:
  - quality: universal numeric field whose meaning depends on the alert type
  - description: human-readable text (like Trade Ideas description column)
  - quality_context: additional metadata for the quality value
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any

from models.alert_types import AlertType


@dataclass
class AlertRecord:
    """
    A discrete market alert that occurred at a specific moment.

    The `quality` field is the key innovation: it's a single numeric value
    whose meaning varies by alert type (lookback days, momentum ratio,
    volume multiple, shares, dollars, sigma, seconds, cents).
    The WebSocket server uses it for per-user filtering:
        event.quality >= subscription.alert_quality[event_type]
    """

    alert_type: AlertType
    symbol: str
    timestamp: datetime
    price: float

    quality: float
    description: str

    # Event-specific transition values
    prev_value: Optional[float] = None
    new_value: Optional[float] = None

    # Context snapshot at alert time
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

    # Window changes
    chg_1min: Optional[float] = None
    chg_5min: Optional[float] = None
    chg_10min: Optional[float] = None
    chg_15min: Optional[float] = None
    chg_30min: Optional[float] = None
    vol_1min: Optional[int] = None
    vol_5min: Optional[int] = None
    vol_1min_pct: Optional[float] = None
    vol_5min_pct: Optional[float] = None

    # Technical
    float_shares: Optional[float] = None
    rsi: Optional[float] = None
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None

    # Bid/Ask
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_size: Optional[int] = None
    ask_size: Optional[int] = None

    # Fundamentals
    security_type: Optional[str] = None
    sector: Optional[str] = None

    # Metadata
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    rule_id: str = ""
    details: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if not self.rule_id:
            self.rule_id = f"alert:system:{self.alert_type.value}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to flat dict for Redis XADD (no None values)."""
        result = {
            "id": self.id,
            "event_type": self.alert_type.value,
            "rule_id": self.rule_id,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "price": self.price,
            "quality": self.quality,
            "description": self.description,
        }

        optional_floats = {
            "prev_value": self.prev_value,
            "new_value": self.new_value,
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
            "chg_1min": self.chg_1min,
            "chg_5min": self.chg_5min,
            "chg_10min": self.chg_10min,
            "chg_15min": self.chg_15min,
            "chg_30min": self.chg_30min,
            "vol_1min_pct": self.vol_1min_pct,
            "vol_5min_pct": self.vol_5min_pct,
            "float_shares": self.float_shares,
            "rsi": self.rsi,
            "ema_20": self.ema_20,
            "ema_50": self.ema_50,
            "bid": self.bid,
            "ask": self.ask,
        }
        for k, v in optional_floats.items():
            if v is not None:
                result[k] = v

        optional_ints = {
            "volume": self.volume,
            "vol_1min": self.vol_1min,
            "vol_5min": self.vol_5min,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
        }
        for k, v in optional_ints.items():
            if v is not None:
                result[k] = v

        if self.security_type is not None:
            result["security_type"] = self.security_type
        if self.sector is not None:
            result["sector"] = self.sector

        if self.details:
            result["details"] = json.dumps(self.details) if isinstance(self.details, dict) else str(self.details)

        return result
