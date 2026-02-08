"""
VWAP Event Detectors

Detects:
- VWAP_CROSS_UP [CAVC] - Price crosses above VWAP
- VWAP_CROSS_DOWN [CBVC] - Price crosses below VWAP

VWAP crossing is one of the most important intraday signals.
Unlike new_high/new_low, VWAP is a moving average so standard
crossing logic works: previous_price <= vwap < current_price.
"""

from typing import Optional, List
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class VWAPEventsDetector(BaseEventDetector):
    """Detects VWAP crossing events."""
    
    COOLDOWNS = {
        EventType.VWAP_CROSS_UP: 60,
        EventType.VWAP_CROSS_DOWN: 60,
    }
    
    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events = []
        
        if previous is None:
            return events
        
        if not self._has_min_volume(current):
            return events
        
        vwap = current.vwap
        if vwap is None or vwap <= 0:
            return events
        
        prev_price = previous.price
        curr_price = current.price
        
        # Crossed ABOVE VWAP: was <= vwap, now > vwap
        if prev_price <= vwap < curr_price:
            et = EventType.VWAP_CROSS_UP
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=vwap,
                    new_value=curr_price,
                    details={"vwap": vwap, "direction": "up"},
                ))
        
        # Crossed BELOW VWAP: was >= vwap, now < vwap
        elif prev_price >= vwap > curr_price:
            et = EventType.VWAP_CROSS_DOWN
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=vwap,
                    new_value=curr_price,
                    details={"vwap": vwap, "direction": "down"},
                ))
        
        return events
