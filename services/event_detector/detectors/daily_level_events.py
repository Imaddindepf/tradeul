"""
Daily Level Cross Detector

Detects when price crosses key daily reference levels.

Events detected:
- CROSSED_DAILY_HIGH_RESISTANCE [CDHR] - Price crosses above previous day's high
- CROSSED_DAILY_LOW_SUPPORT     [CDLS] - Price crosses below previous day's low
- FALSE_GAP_UP_RETRACEMENT      [FGUR] - Gap up stock retraces fully to prev close
- FALSE_GAP_DOWN_RETRACEMENT    [FGDR] - Gap down stock retraces fully to prev close

Also detects sustained/confirmed running momentum:
- RUNNING_UP_SUSTAINED   [RU]  - Up >3% in 10 min
- RUNNING_DOWN_SUSTAINED  [RD]  - Down >3% in 10 min
- RUNNING_UP_CONFIRMED   [RUC] - Up >2% in 5 min AND >4% in 15 min
- RUNNING_DOWN_CONFIRMED  [RDC] - Down >2% in 5 min AND >4% in 15 min
"""

from typing import Optional, List
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class DailyLevelEventsDetector(BaseEventDetector):
    """Detects crosses of daily levels and momentum confirmations."""

    COOLDOWNS = {
        EventType.CROSSED_DAILY_HIGH_RESISTANCE: 300,
        EventType.CROSSED_DAILY_LOW_SUPPORT: 300,
        EventType.FALSE_GAP_UP_RETRACEMENT: 600,
        EventType.FALSE_GAP_DOWN_RETRACEMENT: 600,
        EventType.RUNNING_UP_SUSTAINED: 120,
        EventType.RUNNING_DOWN_SUSTAINED: 120,
        EventType.RUNNING_UP_CONFIRMED: 180,
        EventType.RUNNING_DOWN_CONFIRMED: 180,
    }

    # Min gap % for false gap retracement events
    MIN_GAP_PCT = 2.0

    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events = []

        if not self._has_min_volume(current):
            return events

        if previous is None:
            return events

        events.extend(self._check_daily_high_low(current, previous))
        events.extend(self._check_false_gap(current, previous))
        events.extend(self._check_running_sustained(current, previous))
        events.extend(self._check_running_confirmed(current, previous))

        return events

    # ========================================================================
    # Daily High/Low Cross (resistance/support)
    # ========================================================================

    def _check_daily_high_low(self, current: TickerState, previous: TickerState) -> List[EventRecord]:
        events = []

        # Cross above previous day's high (resistance break)
        prev_high = current.prev_day_high
        if prev_high and prev_high > 0:
            if previous.price <= prev_high < current.price:
                et = EventType.CROSSED_DAILY_HIGH_RESISTANCE
                if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                    self._record_fire(et, current.symbol)
                    events.append(self._make_event(
                        et, current, prev_value=prev_high, new_value=current.price,
                        details={"level": "prev_day_high", "level_price": round(prev_high, 2)},
                    ))

        # Cross below previous day's low (support break)
        prev_low = current.prev_day_low
        if prev_low and prev_low > 0:
            if previous.price >= prev_low > current.price:
                et = EventType.CROSSED_DAILY_LOW_SUPPORT
                if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                    self._record_fire(et, current.symbol)
                    events.append(self._make_event(
                        et, current, prev_value=prev_low, new_value=current.price,
                        details={"level": "prev_day_low", "level_price": round(prev_low, 2)},
                    ))

        return events

    # ========================================================================
    # False Gap Retracement
    # ========================================================================

    def _check_false_gap(self, current: TickerState, previous: TickerState) -> List[EventRecord]:
        """
        Detect when a gap fully retraces back to prev close.
        Gap up + price drops to prev_close = False gap up (bearish).
        Gap down + price rises to prev_close = False gap down (bullish).
        """
        events = []
        gap = current.gap_percent
        prev_close = current.prev_close

        if gap is None or prev_close is None or prev_close <= 0:
            return events

        # False Gap Up: gapped up but price dropped back to prev close
        if gap >= self.MIN_GAP_PCT:
            if previous.price >= prev_close > current.price:
                et = EventType.FALSE_GAP_UP_RETRACEMENT
                if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                    self._record_fire(et, current.symbol)
                    events.append(self._make_event(
                        et, current, prev_value=prev_close, new_value=current.price,
                        details={"gap_percent": round(gap, 2)},
                    ))

        # False Gap Down: gapped down but price rose back to prev close
        if gap <= -self.MIN_GAP_PCT:
            if previous.price <= prev_close < current.price:
                et = EventType.FALSE_GAP_DOWN_RETRACEMENT
                if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                    self._record_fire(et, current.symbol)
                    events.append(self._make_event(
                        et, current, prev_value=prev_close, new_value=current.price,
                        details={"gap_percent": round(gap, 2)},
                    ))

        return events

    # ========================================================================
    # Running Up/Down Sustained (10 min window)
    # ========================================================================

    def _check_running_sustained(self, current: TickerState, previous: TickerState) -> List[EventRecord]:
        events = []
        THRESHOLD = 3.0  # 3% in 10 minutes

        chg_10 = current.chg_10min
        prev_chg_10 = previous.chg_10min
        if chg_10 is None or prev_chg_10 is None:
            return events

        # Running Up Sustained: chg_10min crosses above +3%
        if prev_chg_10 <= THRESHOLD < chg_10:
            et = EventType.RUNNING_UP_SUSTAINED
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current, prev_value=prev_chg_10, new_value=chg_10,
                    details={"window": "10min", "threshold": THRESHOLD},
                ))

        # Running Down Sustained: chg_10min crosses below -3%
        if prev_chg_10 >= -THRESHOLD > chg_10:
            et = EventType.RUNNING_DOWN_SUSTAINED
            if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                self._record_fire(et, current.symbol)
                events.append(self._make_event(
                    et, current, prev_value=prev_chg_10, new_value=chg_10,
                    details={"window": "10min", "threshold": THRESHOLD},
                ))

        return events

    # ========================================================================
    # Running Up/Down Confirmed (multi-window confirmation)
    # ========================================================================

    def _check_running_confirmed(self, current: TickerState, previous: TickerState) -> List[EventRecord]:
        """
        Confirmed running: momentum visible across multiple windows.
        Up: chg_5min > +2% AND chg_15min > +4%
        Down: chg_5min < -2% AND chg_15min < -4%
        """
        events = []

        chg_5 = current.chg_5min
        chg_15 = current.chg_15min
        prev_chg_5 = previous.chg_5min

        if chg_5 is None or chg_15 is None or prev_chg_5 is None:
            return events

        # Running Up Confirmed
        if chg_5 > 2.0 and chg_15 > 4.0:
            # Trigger when chg_5min first crosses above 2% (with 15min already > 4%)
            if prev_chg_5 <= 2.0:
                et = EventType.RUNNING_UP_CONFIRMED
                if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                    self._record_fire(et, current.symbol)
                    events.append(self._make_event(
                        et, current, prev_value=prev_chg_5, new_value=chg_5,
                        details={"chg_5min": round(chg_5, 2), "chg_15min": round(chg_15, 2)},
                    ))

        # Running Down Confirmed
        if chg_5 < -2.0 and chg_15 < -4.0:
            prev_chg_15 = previous.chg_15min
            if prev_chg_5 >= -2.0:
                et = EventType.RUNNING_DOWN_CONFIRMED
                if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                    self._record_fire(et, current.symbol)
                    events.append(self._make_event(
                        et, current, prev_value=prev_chg_5, new_value=chg_5,
                        details={"chg_5min": round(chg_5, 2), "chg_15min": round(chg_15, 2)},
                    ))

        return events
