"""
Gap Event Detectors

Detects:
- GAP_UP_REVERSAL [GUR] - Gapped up but now selling off (bearish)
- GAP_DOWN_REVERSAL [GDR] - Gapped down but now recovering (bullish)

A gap reversal occurs when:
- Gap Up Reversal: stock opened above prev close (gap up >= 2%)
  but current price has fallen back below the open (filling the gap)
- Gap Down Reversal: stock opened below prev close (gap down >= 2%)
  but current price has risen back above the open (filling the gap)
"""

from typing import Optional, List
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class GapEventsDetector(BaseEventDetector):
    """Detects gap reversal events."""
    
    COOLDOWNS = {
        EventType.GAP_UP_REVERSAL: 600,     # 10 min (rare event)
        EventType.GAP_DOWN_REVERSAL: 600,
    }
    
    # Minimum gap % to qualify
    MIN_GAP_PERCENT = 2.0
    
    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events = []
        
        if previous is None:
            return events
        
        if not self._has_min_volume(current):
            return events
        
        open_price = current.open_price
        prev_close = current.prev_close
        
        if open_price is None or prev_close is None or prev_close <= 0 or open_price <= 0:
            return events
        
        gap_percent = ((open_price - prev_close) / prev_close) * 100
        
        # ====== GAP UP REVERSAL ======
        # Gap up >= 2%, and price crosses below the open (filling gap)
        if gap_percent >= self.MIN_GAP_PERCENT:
            if previous.price >= open_price > current.price:
                et = EventType.GAP_UP_REVERSAL
                if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                    self._record_fire(et, current.symbol)
                    events.append(self._make_event(
                        et, current,
                        prev_value=open_price,
                        new_value=current.price,
                        details={
                            "gap_percent": round(gap_percent, 2),
                            "open": open_price,
                            "prev_close": prev_close,
                        },
                    ))
        
        # ====== GAP DOWN REVERSAL ======
        # Gap down >= 2%, and price crosses above the open (filling gap)
        if gap_percent <= -self.MIN_GAP_PERCENT:
            if previous.price <= open_price < current.price:
                et = EventType.GAP_DOWN_REVERSAL
                if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                    self._record_fire(et, current.symbol)
                    events.append(self._make_event(
                        et, current,
                        prev_value=open_price,
                        new_value=current.price,
                        details={
                            "gap_percent": round(gap_percent, 2),
                            "open": open_price,
                            "prev_close": prev_close,
                        },
                    ))
        
        return events
