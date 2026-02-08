"""
Price Event Detectors

Detects:
- NEW_HIGH [NHP] - Price exceeds tracked intraday high
- NEW_LOW [NLP] - Price drops below tracked intraday low
- CROSSED_ABOVE_OPEN [CAO] - Price crosses above today's open
- CROSSED_BELOW_OPEN [CBO] - Price crosses below today's open
- CROSSED_ABOVE_PREV_CLOSE [CAC] - Price crosses above previous close
- CROSSED_BELOW_PREV_CLOSE [CBC] - Price crosses below previous close

CRITICAL: For new_high/new_low, we track our OWN extremes because the enriched
snapshot's intraday_high/low already includes the current price, making direct
comparison impossible (price == intraday_high is always true AT the high).
"""

from typing import Optional, List, Dict
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class PriceEventsDetector(BaseEventDetector):
    """Detects price crossing events."""
    
    # Cooldowns per event type (seconds)
    COOLDOWNS = {
        EventType.NEW_HIGH: 30,
        EventType.NEW_LOW: 30,
        EventType.CROSSED_ABOVE_OPEN: 120,
        EventType.CROSSED_BELOW_OPEN: 120,
        EventType.CROSSED_ABOVE_PREV_CLOSE: 120,
        EventType.CROSSED_BELOW_PREV_CLOSE: 120,
    }
    
    def __init__(self):
        super().__init__()
        # Track our own high/low per symbol for accurate new_high/new_low
        self._tracked_extremes: Dict[str, Dict[str, float]] = {}
    
    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events = []
        
        if not self._has_min_volume(current):
            return events
        
        if previous is None:
            # First time: initialize tracking
            self._init_tracking(current)
            return events
        
        # Check each price event
        events.extend(self._check_new_high(current, previous))
        events.extend(self._check_new_low(current, previous))
        events.extend(self._check_crossed_open(current, previous))
        events.extend(self._check_crossed_prev_close(current, previous))
        
        # Update tracked extremes AFTER checking (so next tick sees updated values)
        self._update_tracking(current)
        
        return events
    
    # ========================================================================
    # NEW HIGH / NEW LOW
    # ========================================================================
    
    def _check_new_high(self, current: TickerState, previous: TickerState) -> List[EventRecord]:
        tracked = self._tracked_extremes.get(current.symbol)
        if tracked is None:
            self._init_tracking_from_previous(current, previous)
            tracked = self._tracked_extremes.get(current.symbol)
            if tracked is None:
                return []
        
        tracked_high = tracked["high"]
        if current.price > tracked_high:
            et = EventType.NEW_HIGH
            if not self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                return []
            self._record_fire(et, current.symbol)
            return [self._make_event(et, current, prev_value=tracked_high, new_value=current.price)]
        
        return []
    
    def _check_new_low(self, current: TickerState, previous: TickerState) -> List[EventRecord]:
        tracked = self._tracked_extremes.get(current.symbol)
        if tracked is None:
            self._init_tracking_from_previous(current, previous)
            tracked = self._tracked_extremes.get(current.symbol)
            if tracked is None:
                return []
        
        tracked_low = tracked["low"]
        if current.price < tracked_low:
            et = EventType.NEW_LOW
            if not self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                return []
            self._record_fire(et, current.symbol)
            return [self._make_event(et, current, prev_value=tracked_low, new_value=current.price)]
        
        return []
    
    # ========================================================================
    # CROSSED ABOVE/BELOW OPEN
    # ========================================================================
    
    def _check_crossed_open(self, current: TickerState, previous: TickerState) -> List[EventRecord]:
        events = []
        open_price = current.open_price
        if open_price is None or open_price <= 0:
            return events
        
        # Crossed ABOVE open: was <= open, now > open
        if previous.price <= open_price < current.price:
            et = EventType.CROSSED_ABOVE_OPEN
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(et, current, prev_value=open_price, new_value=current.price))
        
        # Crossed BELOW open: was >= open, now < open
        if previous.price >= open_price > current.price:
            et = EventType.CROSSED_BELOW_OPEN
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(et, current, prev_value=open_price, new_value=current.price))
        
        return events
    
    # ========================================================================
    # CROSSED ABOVE/BELOW PREVIOUS CLOSE
    # ========================================================================
    
    def _check_crossed_prev_close(self, current: TickerState, previous: TickerState) -> List[EventRecord]:
        events = []
        prev_close = current.prev_close
        if prev_close is None or prev_close <= 0:
            return events
        
        # Crossed ABOVE prev close
        if previous.price <= prev_close < current.price:
            et = EventType.CROSSED_ABOVE_PREV_CLOSE
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(et, current, prev_value=prev_close, new_value=current.price))
        
        # Crossed BELOW prev close
        if previous.price >= prev_close > current.price:
            et = EventType.CROSSED_BELOW_PREV_CLOSE
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(et, current, prev_value=prev_close, new_value=current.price))
        
        return events
    
    # ========================================================================
    # TRACKING HELPERS
    # ========================================================================
    
    def _init_tracking(self, state: TickerState) -> None:
        """Initialize tracked extremes from current state."""
        high = state.intraday_high if state.intraday_high else state.price
        low = state.intraday_low if state.intraday_low else state.price
        self._tracked_extremes[state.symbol] = {"high": high, "low": low}
    
    def _init_tracking_from_previous(self, current: TickerState, previous: TickerState) -> None:
        """Initialize from previous state (fallback)."""
        high = previous.intraday_high if previous.intraday_high else previous.price
        low = previous.intraday_low if previous.intraday_low else previous.price
        self._tracked_extremes[current.symbol] = {"high": high, "low": low}
    
    def _update_tracking(self, state: TickerState) -> None:
        """Update tracked extremes with current price."""
        tracked = self._tracked_extremes.get(state.symbol)
        if tracked is None:
            self._init_tracking(state)
            return
        if state.price > tracked["high"]:
            tracked["high"] = state.price
        if state.price < tracked["low"]:
            tracked["low"] = state.price
    
    def initialize_extremes(self, symbol: str, high: float, low: float) -> None:
        """Initialize extremes from enriched cache (called at startup)."""
        self._tracked_extremes[symbol] = {"high": high, "low": low}
    
    def cleanup_old_symbols(self, active_symbols: set) -> int:
        """Remove tracked data for inactive symbols."""
        base_removed = super().cleanup_old_symbols(active_symbols)
        old = [s for s in self._tracked_extremes if s not in active_symbols]
        for s in old:
            del self._tracked_extremes[s]
        return base_removed + len(old)
    
    def reset_daily(self) -> None:
        """Reset tracked extremes for new trading day."""
        self._tracked_extremes.clear()
