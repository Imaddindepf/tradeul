"""
Stochastic Events Detector

Detects Stochastic %K/%D crosses and zone entries.

Events detected:
- STOCH_CROSS_BULLISH  [STBU]  — %K crosses above %D from oversold zone (<30)
- STOCH_CROSS_BEARISH  [STBD]  — %K crosses below %D from overbought zone (>70)
- STOCH_OVERSOLD       [STOS]  — %K enters oversold zone (<20)
- STOCH_OVERBOUGHT     [STOB]  — %K enters overbought zone (>80)

Data source:
  Stochastic(14,3) from BarEngine via enriched snapshot (1-min bars).
"""

from typing import Optional, List
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class StochasticEventsDetector(BaseEventDetector):
    """Detects Stochastic oscillator crosses and zone entries."""

    # Zone thresholds
    OVERSOLD_ENTRY = 20     # %K enters < 20
    OVERSOLD_CROSS = 30     # %K must be < 30 for bullish cross to count
    OVERBOUGHT_ENTRY = 80   # %K enters > 80
    OVERBOUGHT_CROSS = 70   # %K must be > 70 for bearish cross to count

    COOLDOWNS = {
        EventType.STOCH_CROSS_BULLISH: 300,    # 5 min
        EventType.STOCH_CROSS_BEARISH: 300,
        EventType.STOCH_OVERSOLD: 600,         # 10 min
        EventType.STOCH_OVERBOUGHT: 600,
    }

    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events: List[EventRecord] = []

        if not self._has_min_volume(current):
            return events

        if previous is None:
            return events

        k = current.stoch_k
        d = current.stoch_d
        prev_k = previous.stoch_k
        prev_d = previous.stoch_d

        if any(v is None for v in (k, d, prev_k, prev_d)):
            return events

        # ── %K / %D crosses ──────────────────────────────────────────
        # Bullish: %K crosses above %D while in oversold zone
        if prev_k <= prev_d and k > d and k < self.OVERSOLD_CROSS:
            et = EventType.STOCH_CROSS_BULLISH
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=prev_k,
                    new_value=k,
                    details={
                        "stoch_k": round(k, 2),
                        "stoch_d": round(d, 2),
                        "zone": "oversold",
                    },
                ))

        # Bearish: %K crosses below %D while in overbought zone
        elif prev_k >= prev_d and k < d and k > self.OVERBOUGHT_CROSS:
            et = EventType.STOCH_CROSS_BEARISH
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=prev_k,
                    new_value=k,
                    details={
                        "stoch_k": round(k, 2),
                        "stoch_d": round(d, 2),
                        "zone": "overbought",
                    },
                ))

        # ── Zone entries ─────────────────────────────────────────────
        # Oversold entry: %K crosses below 20
        if prev_k >= self.OVERSOLD_ENTRY and k < self.OVERSOLD_ENTRY:
            et = EventType.STOCH_OVERSOLD
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=prev_k,
                    new_value=k,
                    details={"stoch_k": round(k, 2), "zone": "oversold"},
                ))

        # Overbought entry: %K crosses above 80
        if prev_k <= self.OVERBOUGHT_ENTRY and k > self.OVERBOUGHT_ENTRY:
            et = EventType.STOCH_OVERBOUGHT
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current,
                    prev_value=prev_k,
                    new_value=k,
                    details={"stoch_k": round(k, 2), "zone": "overbought"},
                ))

        return events
