"""
Opening Range Breakout (ORB) Detector

Detects when price breaks above/below the opening range defined by the
first N minutes of the regular trading session (9:30 ET).

The opening range is defined as [low, high] of the first 5 minutes after open.
This is the most popular ORB period (5-min ORB). The range is established
automatically from intraday_high/intraday_low during the first 5 minutes,
then locked in for the rest of the day.

Events detected:
- ORB_BREAKOUT_UP   [ORBU]  — Price breaks above the opening range high
- ORB_BREAKOUT_DOWN [ORBD]  — Price breaks below the opening range low

Data source:
  Price, open_price, intraday_high/low from TickerState (enriched snapshot).
  Range is captured from the first ~5 bar closes (5 minutes).
"""

from typing import Optional, List, Dict
from datetime import datetime, time
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class ORBEventsDetector(BaseEventDetector):
    """Detects Opening Range Breakout (5-minute ORB) events."""

    # How many minutes after open to define the opening range
    ORB_WINDOW_MINUTES = 5

    # Eastern time market open/close (naive, adjusted by caller)
    MARKET_OPEN = time(9, 30)
    ORB_LOCK_TIME = time(9, 35)   # 5 min after open

    COOLDOWNS = {
        EventType.ORB_BREAKOUT_UP: 600,    # 10 min — one ORB break per direction
        EventType.ORB_BREAKOUT_DOWN: 600,
    }

    def __init__(self):
        super().__init__()
        # Per-symbol opening range cache
        self._orb_ranges: Dict[str, Dict] = {}

    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events: List[EventRecord] = []

        if not self._has_min_volume(current):
            return events

        price = current.price
        symbol = current.symbol
        ih = current.intraday_high
        il = current.intraday_low
        open_price = current.open_price

        if open_price is None or ih is None or il is None:
            return events

        # ── Build / update the opening range ─────────────────────────
        # We derive time of day from the TickerState timestamp.
        # During the first ORB_WINDOW_MINUTES, we track the range.
        ts = current.timestamp
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)

        current_time = ts.time()

        orb = self._orb_ranges.get(symbol)

        # Reset at market open (new day or if timestamp < 9:31)
        if orb is None or current_time < time(9, 31):
            # Initialize with current intraday extremes
            self._orb_ranges[symbol] = {
                "high": ih,
                "low": il,
                "locked": False,
            }
            return events  # Don't fire during range building

        # Update range during the ORB window (before lock time)
        if not orb["locked"]:
            if current_time < self.ORB_LOCK_TIME:
                # Still building the range
                if ih > orb["high"]:
                    orb["high"] = ih
                if il < orb["low"]:
                    orb["low"] = il
                return events  # Don't fire yet
            else:
                # Lock the range
                orb["locked"] = True
                if ih > orb["high"]:
                    orb["high"] = ih
                if il < orb["low"]:
                    orb["low"] = il

        # ── Detect breakouts from locked range ───────────────────────
        orb_high = orb["high"]
        orb_low = orb["low"]

        # Sanity: range must have meaningful width (> 0.1%)
        if orb_high <= orb_low or (orb_high - orb_low) / orb_low < 0.001:
            return events

        if previous is None:
            return events

        # Break above ORB high
        if previous.price <= orb_high < price:
            et = EventType.ORB_BREAKOUT_UP
            if self._can_fire(et, symbol, self.COOLDOWNS[et]):
                self._record_fire(et, symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=orb_high,
                    new_value=price,
                    details={
                        "orb_high": round(orb_high, 2),
                        "orb_low": round(orb_low, 2),
                        "orb_range_pct": round((orb_high - orb_low) / orb_low * 100, 2),
                    },
                ))

        # Break below ORB low
        if previous.price >= orb_low > price:
            et = EventType.ORB_BREAKOUT_DOWN
            if self._can_fire(et, symbol, self.COOLDOWNS[et]):
                self._record_fire(et, symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=orb_low,
                    new_value=price,
                    details={
                        "orb_high": round(orb_high, 2),
                        "orb_low": round(orb_low, 2),
                        "orb_range_pct": round((orb_high - orb_low) / orb_low * 100, 2),
                    },
                ))

        return events

    def reset(self) -> None:
        """Reset all ORB ranges (called on new trading day)."""
        self._orb_ranges.clear()
