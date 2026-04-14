"""
Base Alert Detector - Abstract base for all alert detector plugins.

Key difference from old EventDetector: every alert MUST produce:
  - quality: float (meaning depends on alert type)
  - description: str (human-readable, like Tradeul description column)

The base provides cooldown management, alert creation helpers, and
access to the baseline loader for historical data.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, List, Dict, Any

from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord
from baseline.loader import BaselineLoader


class CooldownTracker:
    """Per (event_type, symbol) cooldown enforcement."""

    def __init__(self):
        self._last_fired: Dict[str, Dict[str, datetime]] = {}

    def can_fire(self, alert_type: str, symbol: str, cooldown_seconds: int) -> bool:
        if cooldown_seconds <= 0:
            return True
        last = self._last_fired.get(alert_type, {}).get(symbol)
        if last is None:
            return True
        return (datetime.utcnow() - last).total_seconds() >= cooldown_seconds

    def record_fire(self, alert_type: str, symbol: str) -> None:
        if alert_type not in self._last_fired:
            self._last_fired[alert_type] = {}
        self._last_fired[alert_type][symbol] = datetime.utcnow()

    def cleanup_symbols(self, active: set) -> int:
        removed = 0
        for at in list(self._last_fired.keys()):
            old = [s for s in self._last_fired[at] if s not in active]
            for s in old:
                del self._last_fired[at][s]
                removed += 1
        return removed

    def reset(self) -> None:
        self._last_fired.clear()


class BaseAlertDetector(ABC):
    """
    Base class for all alert detector plugins.

    Subclasses implement detect() to check for alert conditions.
    Every alert emitted MUST have a quality value and description.
    """

    MIN_VOLUME = 5_000

    def __init__(self):
        self.cooldowns = CooldownTracker()
        self.baseline: Optional[BaselineLoader] = None

    def set_baseline(self, baseline: BaselineLoader) -> None:
        self.baseline = baseline

    @abstractmethod
    def detect(self, current: AlertState, previous: Optional[AlertState]) -> List[AlertRecord]:
        pass

    def _can_fire(self, alert_type: AlertType, symbol: str, cooldown_seconds: int) -> bool:
        return self.cooldowns.can_fire(alert_type.value, symbol, cooldown_seconds)

    def _record_fire(self, alert_type: AlertType, symbol: str) -> None:
        self.cooldowns.record_fire(alert_type.value, symbol)

    def _has_min_volume(self, state: AlertState) -> bool:
        return state.volume >= self.MIN_VOLUME

    def _make_alert(
        self,
        alert_type: AlertType,
        current: AlertState,
        quality: float,
        description: str,
        prev_value: Optional[float] = None,
        new_value: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AlertRecord:
        """Create an AlertRecord with full context from AlertState."""
        return AlertRecord(
            alert_type=alert_type,
            symbol=current.symbol,
            timestamp=current.timestamp,
            price=current.price,
            quality=quality,
            description=description,
            prev_value=prev_value,
            new_value=new_value,
            change_percent=current.change_percent,
            rvol=current.rvol,
            volume=current.volume,
            market_cap=current.market_cap,
            gap_percent=current.gap_percent,
            change_from_open=current.change_from_open,
            open_price=current.open_price,
            prev_close=current.prev_close,
            vwap=current.vwap,
            atr_percent=current.atr_percent,
            intraday_high=current.intraday_high,
            intraday_low=current.intraday_low,
            chg_1min=current.chg_1min,
            chg_5min=current.chg_5min,
            chg_10min=current.chg_10min,
            chg_15min=current.chg_15min,
            chg_30min=current.chg_30min,
            vol_1min=current.vol_1min,
            vol_5min=current.vol_5min,
            vol_1min_pct=current.vol_1min_pct,
            vol_5min_pct=current.vol_5min_pct,
            float_shares=current.float_shares,
            rsi=current.rsi,
            ema_20=current.ema_20,
            ema_50=current.ema_50,
            bid=current.bid,
            ask=current.ask,
            bid_size=current.bid_size,
            ask_size=current.ask_size,
            security_type=current.security_type,
            sector=current.sector,
            details=details,
        )

    def cleanup_old_symbols(self, active: set) -> int:
        return self.cooldowns.cleanup_symbols(active)

    def reset_daily(self) -> None:
        self.cooldowns.reset()
