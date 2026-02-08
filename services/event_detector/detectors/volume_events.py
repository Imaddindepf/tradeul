"""
Volume Event Detectors

Detects:
- RVOL_SPIKE [HRV] - Relative volume crosses above 3x
- VOLUME_SURGE - Relative volume crosses above 5x
- VOLUME_SPIKE_1MIN [VS1] - 1-minute volume exceeds threshold
- UNUSUAL_PRINTS [UNOP] - Trades Z-score crosses above 3.0
- BLOCK_TRADE [BP] - Large single-minute volume (>50K shares in 1 bar)

Volume events indicate institutional activity, unusual interest, or
potential momentum shifts.
"""

from typing import Optional, List
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class VolumeEventsDetector(BaseEventDetector):
    """Detects volume-based events."""
    
    COOLDOWNS = {
        EventType.RVOL_SPIKE: 300,          # 5 min cooldown
        EventType.VOLUME_SURGE: 600,         # 10 min cooldown
        EventType.VOLUME_SPIKE_1MIN: 120,    # 2 min cooldown
        EventType.UNUSUAL_PRINTS: 300,       # 5 min cooldown
        EventType.BLOCK_TRADE: 60,           # 1 min cooldown
    }
    
    # Thresholds
    RVOL_SPIKE_THRESHOLD = 3.0
    VOLUME_SURGE_THRESHOLD = 5.0
    VOLUME_SPIKE_1MIN_MIN = 50_000          # 50K shares in 1 minute
    UNUSUAL_PRINTS_ZSCORE = 3.0
    BLOCK_TRADE_MIN_SHARES = 50_000         # 50K shares in 1 minute bar
    
    # Minimum total volume for relevance
    RVOL_MIN_VOLUME = 50_000
    SURGE_MIN_VOLUME = 100_000
    
    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events = []
        
        if previous is None:
            return events
        
        events.extend(self._check_rvol_spike(current, previous))
        events.extend(self._check_volume_surge(current, previous))
        events.extend(self._check_volume_spike_1min(current, previous))
        events.extend(self._check_unusual_prints(current, previous))
        events.extend(self._check_block_trade(current, previous))
        
        return events
    
    def _check_rvol_spike(self, current: TickerState, previous: TickerState) -> List[EventRecord]:
        """RVOL crosses above 3x."""
        if current.volume < self.RVOL_MIN_VOLUME:
            return []
        if current.rvol is None or previous.rvol is None:
            return []
        
        threshold = self.RVOL_SPIKE_THRESHOLD
        if previous.rvol <= threshold < current.rvol:
            et = EventType.RVOL_SPIKE
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                return [self._make_event(
                    et, current,
                    prev_value=previous.rvol,
                    new_value=current.rvol,
                    details={"threshold": threshold},
                )]
        return []
    
    def _check_volume_surge(self, current: TickerState, previous: TickerState) -> List[EventRecord]:
        """RVOL crosses above 5x."""
        if current.volume < self.SURGE_MIN_VOLUME:
            return []
        if current.rvol is None or previous.rvol is None:
            return []
        
        threshold = self.VOLUME_SURGE_THRESHOLD
        if previous.rvol <= threshold < current.rvol:
            et = EventType.VOLUME_SURGE
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                return [self._make_event(
                    et, current,
                    prev_value=previous.rvol,
                    new_value=current.rvol,
                    details={"threshold": threshold},
                )]
        return []
    
    def _check_volume_spike_1min(self, current: TickerState, previous: TickerState) -> List[EventRecord]:
        """1-minute volume exceeds threshold."""
        vol_1min = current.vol_1min
        if vol_1min is None or vol_1min < self.VOLUME_SPIKE_1MIN_MIN:
            return []
        
        prev_vol = previous.vol_1min
        if prev_vol is None:
            return []
        
        # Only fire when crossing the threshold
        if prev_vol < self.VOLUME_SPIKE_1MIN_MIN <= vol_1min:
            et = EventType.VOLUME_SPIKE_1MIN
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                return [self._make_event(
                    et, current,
                    prev_value=float(prev_vol),
                    new_value=float(vol_1min),
                    details={"threshold": self.VOLUME_SPIKE_1MIN_MIN},
                )]
        return []
    
    def _check_unusual_prints(self, current: TickerState, previous: TickerState) -> List[EventRecord]:
        """Trades Z-score crosses above 3.0."""
        if current.trades_z_score is None or previous.trades_z_score is None:
            return []
        if not self._has_min_volume(current):
            return []
        
        threshold = self.UNUSUAL_PRINTS_ZSCORE
        if previous.trades_z_score <= threshold < current.trades_z_score:
            et = EventType.UNUSUAL_PRINTS
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                return [self._make_event(
                    et, current,
                    prev_value=previous.trades_z_score,
                    new_value=current.trades_z_score,
                    details={"threshold": threshold},
                )]
        return []
    
    def _check_block_trade(self, current: TickerState, previous: TickerState) -> List[EventRecord]:
        """Large minute-bar volume indicating block trade."""
        min_vol = current.minute_volume
        if min_vol is None or min_vol < self.BLOCK_TRADE_MIN_SHARES:
            return []
        
        prev_min_vol = previous.minute_volume
        if prev_min_vol is None:
            prev_min_vol = 0
        
        # Fire when minute volume crosses threshold
        if prev_min_vol < self.BLOCK_TRADE_MIN_SHARES <= min_vol:
            et = EventType.BLOCK_TRADE
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                return [self._make_event(
                    et, current,
                    prev_value=float(prev_min_vol),
                    new_value=float(min_vol),
                    details={"threshold": self.BLOCK_TRADE_MIN_SHARES},
                )]
        return []
