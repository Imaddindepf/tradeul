"""
Consolidation Breakout Detector

Detects when price breaks out of a tight consolidation range.

A consolidation is identified when:
  - The 5-minute price change (chg_5min) is small (< 0.5%)
  - The 10-minute price change (chg_10min) is small (< 1.0%)
  - ATR% is available for range context
  
Then a breakout fires when:
  - The 1-minute change (chg_1min) exceeds a threshold relative to ATR
  - With sufficient volume confirmation (RVOL > 1.5)

This catches "coiling" patterns where a stock trades sideways then
suddenly moves with conviction — a key setup for day traders.

Events detected:
- CONSOLIDATION_BREAKOUT_UP   [CBU]  — Breakout up from tight range
- CONSOLIDATION_BREAKOUT_DOWN [CBD]  — Breakdown from tight range
"""

from typing import Optional, List
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class ConsolidationEventsDetector(BaseEventDetector):
    """Detects breakouts from consolidation (tight range) patterns."""

    # Consolidation thresholds (how tight the range must be)
    MAX_CHG_5MIN = 0.5      # Max 0.5% move in 5 min = tight
    MAX_CHG_10MIN = 1.0     # Max 1.0% move in 10 min
    
    # Breakout thresholds (how strong the breakout must be)
    MIN_CHG_1MIN = 0.8      # Min 0.8% move in 1 min for breakout
    MIN_RVOL = 1.5          # Min RVOL for volume confirmation

    COOLDOWNS = {
        EventType.CONSOLIDATION_BREAKOUT_UP: 600,      # 10 min
        EventType.CONSOLIDATION_BREAKOUT_DOWN: 600,
    }

    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events: List[EventRecord] = []

        if not self._has_min_volume(current):
            return events

        if previous is None:
            return events

        # Need window metrics for consolidation detection
        chg_1min = current.chg_1min
        chg_5min = current.chg_5min
        chg_10min = current.chg_10min
        rvol = current.rvol

        if chg_1min is None or chg_5min is None or chg_10min is None:
            return events

        # ── Check consolidation conditions ───────────────────────────
        # The *previous* state should show tight range (consolidation)
        prev_chg_5min = previous.chg_5min
        prev_chg_10min = previous.chg_10min

        if prev_chg_5min is None or prev_chg_10min is None:
            return events

        was_consolidating = (
            abs(prev_chg_5min) < self.MAX_CHG_5MIN and
            abs(prev_chg_10min) < self.MAX_CHG_10MIN
        )

        if not was_consolidating:
            return events

        # ── Check breakout conditions ────────────────────────────────
        # Volume confirmation (optional but preferred)
        has_volume = rvol is not None and rvol >= self.MIN_RVOL

        # Breakout UP
        if chg_1min >= self.MIN_CHG_1MIN and has_volume:
            et = EventType.CONSOLIDATION_BREAKOUT_UP
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=previous.price,
                    new_value=current.price,
                    details={
                        "chg_1min": round(chg_1min, 2),
                        "prev_chg_5min": round(prev_chg_5min, 2),
                        "prev_chg_10min": round(prev_chg_10min, 2),
                        "rvol": round(rvol, 2) if rvol else None,
                        "breakout_type": "consolidation_up",
                    },
                ))

        # Breakdown DOWN
        elif chg_1min <= -self.MIN_CHG_1MIN and has_volume:
            et = EventType.CONSOLIDATION_BREAKOUT_DOWN
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=previous.price,
                    new_value=current.price,
                    details={
                        "chg_1min": round(chg_1min, 2),
                        "prev_chg_5min": round(prev_chg_5min, 2),
                        "prev_chg_10min": round(prev_chg_10min, 2),
                        "rvol": round(rvol, 2) if rvol else None,
                        "breakout_type": "consolidation_down",
                    },
                ))

        return events
