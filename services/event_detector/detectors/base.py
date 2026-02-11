"""
Base Detector - Abstract base class for event detector plugins.

Each detector plugin handles a CATEGORY of events (e.g., price events, volume events).
A single plugin can detect multiple event types within its category.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, List, Dict, Any
from models import EventRecord, EventType, TickerState


class CooldownTracker:
    """
    Tracks cooldowns for event types per symbol.
    
    Prevents the same event from firing too frequently for the same stock.
    Key: (event_type_value, symbol) → last_fired_time
    """
    
    def __init__(self):
        self._last_fired: Dict[str, Dict[str, datetime]] = {}
    
    def can_fire(self, event_type: str, symbol: str, cooldown_seconds: int) -> bool:
        """Check if enough time has passed since last fire."""
        if cooldown_seconds <= 0:
            return True
        last_time = self._last_fired.get(event_type, {}).get(symbol)
        if last_time is None:
            return True
        elapsed = (datetime.utcnow() - last_time).total_seconds()
        return elapsed >= cooldown_seconds
    
    def record_fire(self, event_type: str, symbol: str) -> None:
        """Record that an event was fired."""
        if event_type not in self._last_fired:
            self._last_fired[event_type] = {}
        self._last_fired[event_type][symbol] = datetime.utcnow()
    
    def cleanup_symbols(self, active_symbols: set) -> int:
        """Remove cooldown data for inactive symbols."""
        removed = 0
        for event_type in list(self._last_fired.keys()):
            old = [s for s in self._last_fired[event_type] if s not in active_symbols]
            for s in old:
                del self._last_fired[event_type][s]
                removed += 1
        return removed
    
    def reset(self) -> None:
        """Clear all cooldown data (for daily reset)."""
        self._last_fired.clear()


class BaseEventDetector(ABC):
    """
    Base class for all event detector plugins.
    
    Subclasses implement detect() to check for specific event patterns.
    The base provides cooldown management and event creation helpers.
    """
    
    # Minimum volume to trigger ANY event (filter noise)
    MIN_VOLUME = 10_000
    
    def __init__(self):
        self.cooldowns = CooldownTracker()
    
    @abstractmethod
    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        """
        Detect events by comparing current state against previous state.
        
        Args:
            current: Current ticker state
            previous: Previous ticker state (None if first time seeing this symbol)
        
        Returns:
            List of EventRecord for each detected event (can be empty)
        """
        pass
    
    def _can_fire(self, event_type: EventType, symbol: str, cooldown_seconds: int) -> bool:
        """Check if this event type can fire for this symbol (respects cooldown)."""
        return self.cooldowns.can_fire(event_type.value, symbol, cooldown_seconds)
    
    def _record_fire(self, event_type: EventType, symbol: str) -> None:
        """Record that this event fired (starts cooldown)."""
        self.cooldowns.record_fire(event_type.value, symbol)
    
    def _has_min_volume(self, state: TickerState) -> bool:
        """Check if ticker has minimum volume to be relevant."""
        return state.volume >= self.MIN_VOLUME
    
    def _make_event(
        self,
        event_type: EventType,
        current: TickerState,
        prev_value: Optional[float] = None,
        new_value: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> EventRecord:
        """Create an EventRecord with full context from TickerState."""
        delta = None
        delta_percent = None
        
        if prev_value is not None and new_value is not None:
            delta = new_value - prev_value
            if prev_value != 0:
                delta_percent = (delta / abs(prev_value)) * 100
        
        return EventRecord(
            event_type=event_type,
            rule_id=f"event:system:{event_type.value}",
            symbol=current.symbol,
            timestamp=current.timestamp,
            price=current.price,
            prev_value=prev_value,
            new_value=new_value,
            delta=delta,
            delta_percent=delta_percent,
            # Full context snapshot at event time
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
            # Time-window changes
            chg_1min=getattr(current, 'chg_1min', None),
            chg_5min=getattr(current, 'chg_5min', None),
            chg_10min=getattr(current, 'chg_10min', None),
            chg_15min=getattr(current, 'chg_15min', None),
            chg_30min=getattr(current, 'chg_30min', None),
            vol_1min=getattr(current, 'vol_1min', None),
            vol_5min=getattr(current, 'vol_5min', None),
            # Technical indicators
            float_shares=getattr(current, 'float_shares', None),
            rsi=getattr(current, 'rsi', None),
            ema_20=getattr(current, 'ema_20', None),
            ema_50=getattr(current, 'ema_50', None),
            # Fundamentals (from metadata via enriched)
            security_type=getattr(current, 'security_type', None),
            sector=getattr(current, 'sector', None),
            details=details,
        )
    
    def cleanup_old_symbols(self, active_symbols: set) -> int:
        """Clean up tracking data for inactive symbols. Override for custom cleanup."""
        return self.cooldowns.cleanup_symbols(active_symbols)
    
    def reset_daily(self) -> None:
        """Reset all tracking data for a new trading day. Override for custom reset."""
        self.cooldowns.reset()
