"""
Confirmed Cross Detectors

Detects price crosses that HOLD for a confirmation period (30 seconds).
Unlike instant crosses (CAO/CBO/CAC/CBC), confirmed crosses require
the price to stay on the correct side of the level for CONFIRM_SECONDS
before firing. This filters out noise and whipsaws.

Events detected:
  - CROSSED_ABOVE_OPEN_CONFIRMED   [CAOC] - Price above open for 30s
  - CROSSED_BELOW_OPEN_CONFIRMED   [CBOC] - Price below open for 30s
  - CROSSED_ABOVE_CLOSE_CONFIRMED  [CACC] - Price above prev close for 30s
  - CROSSED_BELOW_CLOSE_CONFIRMED  [CBCC] - Price below prev close for 30s
"""

from datetime import datetime
from typing import Optional, List, Dict, Tuple
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class ConfirmedCrossEventsDetector(BaseEventDetector):
    """Detects confirmed price crosses (price sustains beyond a level for N seconds)."""

    CONFIRM_SECONDS = 30  # Price must stay on the correct side for this long

    COOLDOWNS = {
        EventType.CROSSED_ABOVE_OPEN_CONFIRMED: 300,    # 5 min
        EventType.CROSSED_BELOW_OPEN_CONFIRMED: 300,
        EventType.CROSSED_ABOVE_CLOSE_CONFIRMED: 300,
        EventType.CROSSED_BELOW_CLOSE_CONFIRMED: 300,
    }

    # (above EventType, below EventType, TickerState field for the level)
    _LEVELS = [
        (EventType.CROSSED_ABOVE_OPEN_CONFIRMED,
         EventType.CROSSED_BELOW_OPEN_CONFIRMED,
         "open_price"),
        (EventType.CROSSED_ABOVE_CLOSE_CONFIRMED,
         EventType.CROSSED_BELOW_CLOSE_CONFIRMED,
         "prev_close"),
    ]

    def __init__(self):
        super().__init__()
        # Pending confirmations:
        # { symbol: { event_type_value: (cross_time, level_value) } }
        self._pending: Dict[str, Dict[str, Tuple[datetime, float]]] = {}

    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events: List[EventRecord] = []

        if previous is None or not self._has_min_volume(current):
            return events

        now = current.timestamp
        # Ensure naive UTC
        if now.tzinfo is not None:
            now = now.replace(tzinfo=None)

        symbol = current.symbol
        if symbol not in self._pending:
            self._pending[symbol] = {}

        pending = self._pending[symbol]

        for et_above, et_below, level_field in self._LEVELS:
            level = getattr(current, level_field, None)
            if level is None or level <= 0:
                continue

            above_key = et_above.value
            below_key = et_below.value

            price = current.price
            prev_price = previous.price

            # ── Detect new CROSS ABOVE ──
            if prev_price <= level < price:
                # Fresh cross above — start confirmation timer
                if above_key not in pending:
                    pending[above_key] = (now, level)
                # Cancel any pending below confirmation (direction reversed)
                pending.pop(below_key, None)

            # ── Detect new CROSS BELOW ──
            elif prev_price >= level > price:
                # Fresh cross below — start confirmation timer
                if below_key not in pending:
                    pending[below_key] = (now, level)
                # Cancel any pending above confirmation
                pending.pop(above_key, None)

            # ── Check pending ABOVE confirmation ──
            if above_key in pending:
                cross_time, cross_level = pending[above_key]
                if price <= cross_level:
                    # Price fell back — cancel
                    del pending[above_key]
                else:
                    elapsed = (now - cross_time).total_seconds()
                    if elapsed >= self.CONFIRM_SECONDS:
                        # Confirmed! Fire if cooldown allows
                        if self._can_fire(et_above, symbol, self.COOLDOWNS[et_above]):
                            self._record_fire(et_above, symbol)
                            events.append(self._make_event(
                                et_above, current,
                                prev_value=cross_level,
                                new_value=price,
                                details={
                                    "level_type": level_field,
                                    "level_value": round(cross_level, 4),
                                    "confirm_seconds": round(elapsed, 1),
                                },
                            ))
                        # Either way, clear the pending (don't re-fire)
                        del pending[above_key]

            # ── Check pending BELOW confirmation ──
            if below_key in pending:
                cross_time, cross_level = pending[below_key]
                if price >= cross_level:
                    # Price bounced back — cancel
                    del pending[below_key]
                else:
                    elapsed = (now - cross_time).total_seconds()
                    if elapsed >= self.CONFIRM_SECONDS:
                        if self._can_fire(et_below, symbol, self.COOLDOWNS[et_below]):
                            self._record_fire(et_below, symbol)
                            events.append(self._make_event(
                                et_below, current,
                                prev_value=cross_level,
                                new_value=price,
                                details={
                                    "level_type": level_field,
                                    "level_value": round(cross_level, 4),
                                    "confirm_seconds": round(elapsed, 1),
                                },
                            ))
                        del pending[below_key]

        return events

    def cleanup_old_symbols(self, active_symbols: set) -> int:
        base_removed = super().cleanup_old_symbols(active_symbols)
        old = [s for s in self._pending if s not in active_symbols]
        for s in old:
            del self._pending[s]
        return base_removed + len(old)

    def reset_daily(self) -> None:
        super().reset_daily()
        self._pending.clear()
