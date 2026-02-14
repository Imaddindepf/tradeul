"""
Pullback Event Detectors

Original pullbacks (range = intraday_high - intraday_low):
- PULLBACK_75_FROM_HIGH [PFH75] - Price retraces 75% from high toward low
- PULLBACK_25_FROM_HIGH [PFH25] - Price retraces 25% from high toward low
- PULLBACK_75_FROM_LOW [PFL75] - Price bounces 75% from low toward high
- PULLBACK_25_FROM_LOW [PFL25] - Price bounces 25% from low toward high

Variants with Close reference (range = intraday_high - close OR close - intraday_low):
- PFH75C / PFH25C / PFL75C / PFL25C

Variants with Open reference (range = intraday_high - open OR open - intraday_low):
- PFH75O / PFH25O / PFL75O / PFL25O
"""

from typing import Optional, List
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class PullbackEventsDetector(BaseEventDetector):
    """Detects pullback events from intraday highs/lows with multiple reference modes."""

    COOLDOWNS = {
        # Original (full range: high-low)
        EventType.PULLBACK_75_FROM_HIGH: 300,    # 5 min
        EventType.PULLBACK_25_FROM_HIGH: 300,
        EventType.PULLBACK_75_FROM_LOW: 300,
        EventType.PULLBACK_25_FROM_LOW: 300,
        # Close reference
        EventType.PULLBACK_75_FROM_HIGH_CLOSE: 300,
        EventType.PULLBACK_25_FROM_HIGH_CLOSE: 300,
        EventType.PULLBACK_75_FROM_LOW_CLOSE: 300,
        EventType.PULLBACK_25_FROM_LOW_CLOSE: 300,
        # Open reference
        EventType.PULLBACK_75_FROM_HIGH_OPEN: 300,
        EventType.PULLBACK_25_FROM_HIGH_OPEN: 300,
        EventType.PULLBACK_75_FROM_LOW_OPEN: 300,
        EventType.PULLBACK_25_FROM_LOW_OPEN: 300,
    }

    # Minimum range as % of price to avoid noise on tight-range days
    MIN_RANGE_PERCENT = 1.0  # At least 1% range

    # Pullback specs: (pct, "from_high" EventType, "from_low" EventType)
    # This drives the detection loop for each reference mode
    _PCT_LEVELS = [
        (0.25, "high", "low"),
        (0.75, "high", "low"),
    ]

    # (pct, et_from_high, et_from_low, label_suffix, range_source)
    _ALL_PULLBACKS = [
        # Original: range = high - low
        (0.25, EventType.PULLBACK_25_FROM_HIGH, EventType.PULLBACK_25_FROM_LOW, "full_range", "low"),
        (0.75, EventType.PULLBACK_75_FROM_HIGH, EventType.PULLBACK_75_FROM_LOW, "full_range", "low"),
        # Close reference: range anchored on prev_close
        (0.25, EventType.PULLBACK_25_FROM_HIGH_CLOSE, EventType.PULLBACK_25_FROM_LOW_CLOSE, "close_ref", "close"),
        (0.75, EventType.PULLBACK_75_FROM_HIGH_CLOSE, EventType.PULLBACK_75_FROM_LOW_CLOSE, "close_ref", "close"),
        # Open reference: range anchored on open
        (0.25, EventType.PULLBACK_25_FROM_HIGH_OPEN, EventType.PULLBACK_25_FROM_LOW_OPEN, "open_ref", "open"),
        (0.75, EventType.PULLBACK_75_FROM_HIGH_OPEN, EventType.PULLBACK_75_FROM_LOW_OPEN, "open_ref", "open"),
    ]

    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events = []

        if previous is None or not self._has_min_volume(current):
            return events

        high = current.intraday_high
        low = current.intraday_low
        if high is None or low is None:
            return events

        curr_price = current.price
        prev_price = previous.price

        # Get reference points for different modes
        ref_prices = {
            "low": low,
            "close": current.prev_close,
            "open": current.open_price,
        }

        for pct, et_high, et_low, label, ref_key in self._ALL_PULLBACKS:
            ref = ref_prices.get(ref_key)
            if ref is None or ref <= 0:
                continue

            # FROM HIGH direction: range = high - ref
            range_h = high - ref
            if range_h > 0:
                range_pct_h = (range_h / high) * 100
                if range_pct_h >= self.MIN_RANGE_PERCENT:
                    level = high - pct * range_h
                    if prev_price >= level > curr_price:
                        if self._can_fire(et_high, current.symbol, self.COOLDOWNS[et_high]):
                            self._record_fire(et_high, current.symbol)
                            events.append(self._make_event(
                                et_high, current,
                                prev_value=level,
                                new_value=curr_price,
                                details={
                                    "level": round(level, 4),
                                    "high": high, "ref": round(ref, 4),
                                    "ref_type": ref_key,
                                    "pullback_pct": int(pct * 100),
                                },
                            ))

            # FROM LOW direction: range = ref - low
            range_l = ref - low
            if range_l > 0:
                range_pct_l = (range_l / ref) * 100 if ref > 0 else 0
                if range_pct_l >= self.MIN_RANGE_PERCENT:
                    level = low + pct * range_l
                    if prev_price <= level < curr_price:
                        if self._can_fire(et_low, current.symbol, self.COOLDOWNS[et_low]):
                            self._record_fire(et_low, current.symbol)
                            events.append(self._make_event(
                                et_low, current,
                                prev_value=level,
                                new_value=curr_price,
                                details={
                                    "level": round(level, 4),
                                    "low": low, "ref": round(ref, 4),
                                    "ref_type": ref_key,
                                    "bounce_pct": int(pct * 100),
                                },
                            ))

        return events
