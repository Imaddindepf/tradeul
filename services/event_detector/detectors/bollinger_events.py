"""
Bollinger Band Event Detector

Detects when price crosses Bollinger Band boundaries.

Events detected:
- BB_UPPER_BREAKOUT  [BBU] - Price crosses above upper Bollinger Band
- BB_LOWER_BREAKDOWN [BBD] - Price crosses below lower Bollinger Band

Bollinger Bands = EMA(20) ± 2σ from 1-minute bars (BarEngine).
A breakout above the upper band signals extreme overbought / momentum.
A breakdown below the lower band signals extreme oversold / momentum.

Data source: Intraday BB values from BarEngine via enriched snapshot.
"""

from typing import Optional, List
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class BollingerEventsDetector(BaseEventDetector):
    """Detects Bollinger Band breakout/breakdown events."""

    COOLDOWNS = {
        EventType.BB_UPPER_BREAKOUT: 120,  # 2 min
        EventType.BB_LOWER_BREAKDOWN: 120,
    }

    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events = []

        if not self._has_min_volume(current):
            return events

        if previous is None:
            return events

        # --- Upper Band Breakout ---
        bb_upper = current.bb_upper
        if bb_upper and bb_upper > 0:
            if previous.price <= bb_upper < current.price:
                et = EventType.BB_UPPER_BREAKOUT
                if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                    self._record_fire(et, current.symbol)
                    events.append(self._make_event(
                        et, current,
                        prev_value=bb_upper,
                        new_value=current.price,
                        details={
                            "bb_upper": round(bb_upper, 2),
                            "bb_lower": round(current.bb_lower, 2) if current.bb_lower else None,
                            "ema_20": round(current.ema_20, 2) if current.ema_20 else None,
                        },
                    ))

        # --- Lower Band Breakdown ---
        bb_lower = current.bb_lower
        if bb_lower and bb_lower > 0:
            if previous.price >= bb_lower > current.price:
                et = EventType.BB_LOWER_BREAKDOWN
                if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                    self._record_fire(et, current.symbol)
                    events.append(self._make_event(
                        et, current,
                        prev_value=bb_lower,
                        new_value=current.price,
                        details={
                            "bb_upper": round(bb_upper, 2) if bb_upper else None,
                            "bb_lower": round(bb_lower, 2),
                            "ema_20": round(current.ema_20, 2) if current.ema_20 else None,
                        },
                    ))

        return events
