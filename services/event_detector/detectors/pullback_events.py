"""
Pullback Event Detectors

Detects:
- PULLBACK_75_FROM_HIGH [PFH75] - Price retraces 75% from high toward low
- PULLBACK_25_FROM_HIGH [PFH25] - Price retraces 25% from high toward low
- PULLBACK_75_FROM_LOW [PFL75] - Price bounces 75% from low toward high
- PULLBACK_25_FROM_LOW [PFL25] - Price bounces 25% from low toward high

Pullback level = how far price has retraced within the day's range.

Range = intraday_high - intraday_low
PFH75: price drops to high - 0.75 * range (near the low)
PFH25: price drops to high - 0.25 * range (small pullback)
PFL75: price rises to low + 0.75 * range (near the high)
PFL25: price rises to low + 0.25 * range (small bounce)
"""

from typing import Optional, List, Dict
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class PullbackEventsDetector(BaseEventDetector):
    """Detects pullback events from intraday highs/lows."""
    
    COOLDOWNS = {
        EventType.PULLBACK_75_FROM_HIGH: 300,    # 5 min
        EventType.PULLBACK_25_FROM_HIGH: 300,
        EventType.PULLBACK_75_FROM_LOW: 300,
        EventType.PULLBACK_25_FROM_LOW: 300,
    }
    
    # Minimum range as % of price to avoid noise on tight-range days
    MIN_RANGE_PERCENT = 1.0  # At least 1% range
    
    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events = []
        
        if previous is None:
            return events
        
        if not self._has_min_volume(current):
            return events
        
        # Need intraday extremes
        high = current.intraday_high
        low = current.intraday_low
        if high is None or low is None:
            return events
        
        range_val = high - low
        if range_val <= 0:
            return events
        
        # Skip if range is too small (noise)
        range_pct = (range_val / high) * 100
        if range_pct < self.MIN_RANGE_PERCENT:
            return events
        
        curr_price = current.price
        prev_price = previous.price
        
        # ====== PULLBACKS FROM HIGH (price falling toward low) ======
        
        # 25% pullback level: high - 0.25 * range
        pf25_level = high - 0.25 * range_val
        if prev_price >= pf25_level > curr_price:
            et = EventType.PULLBACK_25_FROM_HIGH
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=pf25_level,
                    new_value=curr_price,
                    details={"level": pf25_level, "high": high, "low": low, "pullback_pct": 25},
                ))
        
        # 75% pullback level: high - 0.75 * range (near the low)
        pf75_level = high - 0.75 * range_val
        if prev_price >= pf75_level > curr_price:
            et = EventType.PULLBACK_75_FROM_HIGH
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=pf75_level,
                    new_value=curr_price,
                    details={"level": pf75_level, "high": high, "low": low, "pullback_pct": 75},
                ))
        
        # ====== PULLBACKS FROM LOW (price rising toward high) ======
        
        # 25% bounce: low + 0.25 * range
        pl25_level = low + 0.25 * range_val
        if prev_price <= pl25_level < curr_price:
            et = EventType.PULLBACK_25_FROM_LOW
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=pl25_level,
                    new_value=curr_price,
                    details={"level": pl25_level, "high": high, "low": low, "bounce_pct": 25},
                ))
        
        # 75% bounce: low + 0.75 * range (near the high)
        pl75_level = low + 0.75 * range_val
        if prev_price <= pl75_level < curr_price:
            et = EventType.PULLBACK_75_FROM_LOW
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=pl75_level,
                    new_value=curr_price,
                    details={"level": pl75_level, "high": high, "low": low, "bounce_pct": 75},
                ))
        
        return events
