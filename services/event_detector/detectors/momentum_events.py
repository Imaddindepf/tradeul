"""
Momentum Event Detectors

Detects:
- RUNNING_UP [RUN] - Stock moving up rapidly (chg_5min > 2%)
- RUNNING_DOWN [RDN] - Stock moving down rapidly (chg_5min < -2%)
- PERCENT_UP_5 [PUD] - Change% crosses above +5% for the day
- PERCENT_DOWN_5 [PDD] - Change% crosses below -5% for the day
- PERCENT_UP_10 - Change% crosses above +10% for the day
- PERCENT_DOWN_10 - Change% crosses below -10% for the day

Momentum events capture rapid price movement and big daily moves.
"""

from typing import Optional, List
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class MomentumEventsDetector(BaseEventDetector):
    """Detects momentum-based events."""
    
    COOLDOWNS = {
        EventType.RUNNING_UP: 120,          # 2 min (rapid events)
        EventType.RUNNING_DOWN: 120,
        EventType.PERCENT_UP_5: 300,        # 5 min (daily threshold)
        EventType.PERCENT_DOWN_5: 300,
        EventType.PERCENT_UP_10: 300,
        EventType.PERCENT_DOWN_10: 300,
    }
    
    # Thresholds
    RUNNING_CHG_5MIN = 2.0      # 2% move in 5 minutes
    RUNNING_MIN_VOLUME = 50_000
    
    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events = []
        
        if previous is None:
            return events
        
        if not self._has_min_volume(current):
            return events
        
        events.extend(self._check_running(current, previous))
        events.extend(self._check_percent_day(current, previous))
        
        return events
    
    def _check_running(self, current: TickerState, previous: TickerState) -> List[EventRecord]:
        """Running up/down: rapid movement in last 5 minutes."""
        events = []
        
        if current.volume < self.RUNNING_MIN_VOLUME:
            return events
        
        chg = current.chg_5min
        prev_chg = previous.chg_5min
        
        if chg is None or prev_chg is None:
            return events
        
        threshold = self.RUNNING_CHG_5MIN
        
        # Running UP: chg_5min crosses above +2%
        if prev_chg <= threshold < chg:
            et = EventType.RUNNING_UP
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=prev_chg,
                    new_value=chg,
                    details={"chg_5min": chg, "threshold": threshold},
                ))
        
        # Running DOWN: chg_5min crosses below -2%
        if prev_chg >= -threshold > chg:
            et = EventType.RUNNING_DOWN
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=prev_chg,
                    new_value=chg,
                    details={"chg_5min": chg, "threshold": -threshold},
                ))
        
        return events
    
    def _check_percent_day(self, current: TickerState, previous: TickerState) -> List[EventRecord]:
        """Check daily change% crossing key thresholds (5%, 10%)."""
        events = []
        
        curr_chg = current.change_percent
        prev_chg = previous.change_percent
        
        if curr_chg is None or prev_chg is None:
            return events
        
        # +5% threshold
        if prev_chg <= 5.0 < curr_chg:
            et = EventType.PERCENT_UP_5
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(et, current, prev_value=prev_chg, new_value=curr_chg))
        
        # -5% threshold
        if prev_chg >= -5.0 > curr_chg:
            et = EventType.PERCENT_DOWN_5
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(et, current, prev_value=prev_chg, new_value=curr_chg))
        
        # +10% threshold
        if prev_chg <= 10.0 < curr_chg:
            et = EventType.PERCENT_UP_10
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(et, current, prev_value=prev_chg, new_value=curr_chg))
        
        # -10% threshold
        if prev_chg >= -10.0 > curr_chg:
            et = EventType.PERCENT_DOWN_10
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(et, current, prev_value=prev_chg, new_value=curr_chg))
        
        return events
