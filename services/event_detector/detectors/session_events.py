"""
Pre-Market / Post-Market High/Low Detectors

Detects new highs and lows during extended-hours sessions:
  - PRE_MARKET_HIGH  [HPRE]  - New high during pre-market (4:00 AM - 9:30 AM ET)
  - PRE_MARKET_LOW   [LPRE]  - New low during pre-market
  - POST_MARKET_HIGH [HPOST] - New high during post-market (4:00 PM - 8:00 PM ET)
  - POST_MARKET_LOW  [LPOST] - New low during post-market

Session state comes from TickerState.market_session, populated by
the event engine from the market_session service via EventBus.

IMPORTANT: These only fire during their respective sessions.
When the session changes, tracked extremes for the OLD session are cleared.
"""

from typing import Optional, List, Dict
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class SessionEventsDetector(BaseEventDetector):
    """Detects new highs/lows in pre-market and post-market sessions."""

    COOLDOWNS = {
        EventType.PRE_MARKET_HIGH: 30,     # 30s (same as NHP)
        EventType.PRE_MARKET_LOW: 30,
        EventType.POST_MARKET_HIGH: 30,
        EventType.POST_MARKET_LOW: 30,
    }

    # Which sessions map to which events
    _SESSION_MAP = {
        "PRE_MARKET": (EventType.PRE_MARKET_HIGH, EventType.PRE_MARKET_LOW),
        "POST_MARKET": (EventType.POST_MARKET_HIGH, EventType.POST_MARKET_LOW),
    }

    def __init__(self):
        super().__init__()
        # Track session extremes per symbol: { symbol: { "high": float, "low": float } }
        self._pre_extremes: Dict[str, Dict[str, float]] = {}
        self._post_extremes: Dict[str, Dict[str, float]] = {}
        # Track last known session to detect transitions
        self._last_session: Optional[str] = None

    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events: List[EventRecord] = []

        session = current.market_session
        if session not in self._SESSION_MAP:
            return events

        if not self._has_min_volume(current):
            return events

        # Detect session transition → clear old tracking
        if self._last_session != session:
            self._on_session_change(session)
            self._last_session = session

        # Select the right extremes dict
        extremes = self._pre_extremes if session == "PRE_MARKET" else self._post_extremes
        et_high, et_low = self._SESSION_MAP[session]

        symbol = current.symbol
        price = current.price

        # First time seeing this symbol in this session
        if symbol not in extremes:
            extremes[symbol] = {"high": price, "low": price}
            return events

        tracked = extremes[symbol]

        # ── New Session High ──
        if price > tracked["high"]:
            old_high = tracked["high"]
            tracked["high"] = price
            if self._can_fire(et_high, symbol, self.COOLDOWNS[et_high]):
                self._record_fire(et_high, symbol)
                events.append(self._make_event(
                    et_high, current,
                    prev_value=old_high,
                    new_value=price,
                    details={
                        "session": session,
                        "session_high": round(price, 4),
                        "session_low": round(tracked["low"], 4),
                    },
                ))

        # ── New Session Low ──
        if price < tracked["low"]:
            old_low = tracked["low"]
            tracked["low"] = price
            if self._can_fire(et_low, symbol, self.COOLDOWNS[et_low]):
                self._record_fire(et_low, symbol)
                events.append(self._make_event(
                    et_low, current,
                    prev_value=old_low,
                    new_value=price,
                    details={
                        "session": session,
                        "session_high": round(tracked["high"], 4),
                        "session_low": round(price, 4),
                    },
                ))

        return events

    def _on_session_change(self, new_session: str) -> None:
        """Clear tracking data when session changes."""
        if new_session == "PRE_MARKET":
            self._pre_extremes.clear()
        elif new_session == "POST_MARKET":
            self._post_extremes.clear()
        # When MARKET_OPEN starts, clear both (fresh day)
        elif new_session == "MARKET_OPEN":
            self._post_extremes.clear()

    def cleanup_old_symbols(self, active_symbols: set) -> int:
        base_removed = super().cleanup_old_symbols(active_symbols)
        removed = 0
        for extremes in (self._pre_extremes, self._post_extremes):
            old = [s for s in extremes if s not in active_symbols]
            for s in old:
                del extremes[s]
                removed += 1
        return base_removed + removed

    def reset_daily(self) -> None:
        super().reset_daily()
        self._pre_extremes.clear()
        self._post_extremes.clear()
        self._last_session = None
