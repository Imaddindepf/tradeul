"""
MACD Events Detector

Detects MACD signal line crosses and zero-line crosses.

Events detected:
- MACD_CROSS_BULLISH   [MACDU]  — MACD line crosses above signal line
- MACD_CROSS_BEARISH   [MACDD]  — MACD line crosses below signal line
- MACD_ZERO_CROSS_UP   [MZU]   — MACD line crosses above zero
- MACD_ZERO_CROSS_DOWN [MZD]   — MACD line crosses below zero

Data source:
  MACD(12,26,9) from BarEngine via enriched snapshot (1-min bars).
"""

from typing import Optional, List
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class MACDEventsDetector(BaseEventDetector):
    """Detects MACD signal crosses and zero-line crosses."""

    COOLDOWNS = {
        EventType.MACD_CROSS_BULLISH: 300,    # 5 min
        EventType.MACD_CROSS_BEARISH: 300,
        EventType.MACD_ZERO_CROSS_UP: 600,    # 10 min
        EventType.MACD_ZERO_CROSS_DOWN: 600,
    }

    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events: List[EventRecord] = []

        if not self._has_min_volume(current):
            return events

        if previous is None:
            return events

        macd_l = current.macd_line
        macd_s = current.macd_signal
        prev_macd_l = previous.macd_line
        prev_macd_s = previous.macd_signal

        if any(v is None for v in (macd_l, macd_s, prev_macd_l, prev_macd_s)):
            return events

        # ── Signal cross ─────────────────────────────────────────────
        # Bullish: MACD crosses above signal
        if prev_macd_l <= prev_macd_s and macd_l > macd_s:
            et = EventType.MACD_CROSS_BULLISH
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=prev_macd_l,
                    new_value=macd_l,
                    details={
                        "macd_line": round(macd_l, 4),
                        "macd_signal": round(macd_s, 4),
                        "histogram": round(macd_l - macd_s, 4),
                    },
                ))

        # Bearish: MACD crosses below signal
        elif prev_macd_l >= prev_macd_s and macd_l < macd_s:
            et = EventType.MACD_CROSS_BEARISH
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=prev_macd_l,
                    new_value=macd_l,
                    details={
                        "macd_line": round(macd_l, 4),
                        "macd_signal": round(macd_s, 4),
                        "histogram": round(macd_l - macd_s, 4),
                    },
                ))

        # ── Zero cross ───────────────────────────────────────────────
        if prev_macd_l <= 0 < macd_l:
            et = EventType.MACD_ZERO_CROSS_UP
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=prev_macd_l,
                    new_value=macd_l,
                    details={"macd_line": round(macd_l, 4), "direction": "bullish"},
                ))

        elif prev_macd_l >= 0 > macd_l:
            et = EventType.MACD_ZERO_CROSS_DOWN
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=prev_macd_l,
                    new_value=macd_l,
                    details={"macd_line": round(macd_l, 4), "direction": "bearish"},
                ))

        return events
