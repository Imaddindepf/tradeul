"""
Moving Average Cross Detector

Detects when price crosses above or below daily Simple Moving Averages.

Events detected:
- CROSSED_ABOVE_SMA20  [CA20]  - Price crosses above 20-day SMA
- CROSSED_BELOW_SMA20  [CB20]  - Price crosses below 20-day SMA
- CROSSED_ABOVE_SMA50  [CA50]  - Price crosses above 50-day SMA
- CROSSED_BELOW_SMA50  [CB50]  - Price crosses below 50-day SMA
- CROSSED_ABOVE_SMA200 [CA200] - Price crosses above 200-day SMA
- CROSSED_BELOW_SMA200 [CB200] - Price crosses below 200-day SMA

Data source: Daily SMA values from screener service via Redis bridge.
SMA values are static during the day (computed from daily closes).
The cross is detected when real-time price moves through the level.
"""

from typing import Optional, List
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class MACrossEventsDetector(BaseEventDetector):
    """Detects price crosses above/below daily moving averages."""

    # (EventType above, EventType below, TickerState field name)
    _MA_PAIRS = [
        (EventType.CROSSED_ABOVE_SMA20,  EventType.CROSSED_BELOW_SMA20,  "sma_20"),
        (EventType.CROSSED_ABOVE_SMA50,  EventType.CROSSED_BELOW_SMA50,  "sma_50"),
        (EventType.CROSSED_ABOVE_SMA200, EventType.CROSSED_BELOW_SMA200, "sma_200"),
    ]

    # Cooldowns — longer for higher-period MAs (they cross less often)
    COOLDOWNS = {
        EventType.CROSSED_ABOVE_SMA20: 180,   # 3 min
        EventType.CROSSED_BELOW_SMA20: 180,
        EventType.CROSSED_ABOVE_SMA50: 300,   # 5 min
        EventType.CROSSED_BELOW_SMA50: 300,
        EventType.CROSSED_ABOVE_SMA200: 600,  # 10 min
        EventType.CROSSED_BELOW_SMA200: 600,
    }

    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events = []

        if not self._has_min_volume(current):
            return events

        if previous is None:
            return events

        for et_above, et_below, field in self._MA_PAIRS:
            ma_val = getattr(current, field, None)
            if ma_val is None or ma_val <= 0:
                continue

            # Cross ABOVE: previous price was at or below MA, current is above
            if previous.price <= ma_val < current.price:
                if self._can_fire(et_above, current.symbol, self.COOLDOWNS[et_above]):
                    self._record_fire(et_above, current.symbol)
                    events.append(self._make_event(
                        et_above, current,
                        prev_value=ma_val,
                        new_value=current.price,
                        details={"ma_period": field.split("_")[1], "ma_value": round(ma_val, 2)},
                    ))

            # Cross BELOW: previous price was at or above MA, current is below
            if previous.price >= ma_val > current.price:
                if self._can_fire(et_below, current.symbol, self.COOLDOWNS[et_below]):
                    self._record_fire(et_below, current.symbol)
                    events.append(self._make_event(
                        et_below, current,
                        prev_value=ma_val,
                        new_value=current.price,
                        details={"ma_period": field.split("_")[1], "ma_value": round(ma_val, 2)},
                    ))

        return events
