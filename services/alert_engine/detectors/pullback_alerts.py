"""
Pullback Alert Detector - 8 pullback variants (Close + Open x High/Low x 75%/25%).

Trade Ideas spec:
  PFL75C: Start at prev_close, stock goes DOWN to today's low, bounces 75% back toward close. direction=+
  PFL25C: Same but 25% bounce. direction=+
  PFH75C: Start at prev_close, stock goes UP to today's high, pulls back 75% toward close. direction=-
  PFH25C: Same but 25% pullback. direction=-
  PFL75O: Start at today's open, stock goes DOWN to low, bounces 75% back toward open. direction=+
  PFL25O: Same but 25%. direction=+
  PFH75O: Start at today's open, stock goes UP to high, pulls back 75% toward open. direction=-
  PFH25O: Same but 25%. direction=-

Quality = initial move size (% from anchor to extreme).
Custom setting = MIN_PERCENT (minimum initial move size to trigger).
Can fire more than once per day.
Reports on every print, no confirmation wait.
"""

from typing import Optional, List, Tuple

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord

FIXED_ANCHOR_VARIANTS = [
    ("close", "prev_close",
     AlertType.PULLBACK_75_FROM_LOW_CLOSE, AlertType.PULLBACK_25_FROM_LOW_CLOSE,
     AlertType.PULLBACK_75_FROM_HIGH_CLOSE, AlertType.PULLBACK_25_FROM_HIGH_CLOSE),
    ("open", "open_price",
     AlertType.PULLBACK_75_FROM_LOW_OPEN, AlertType.PULLBACK_25_FROM_LOW_OPEN,
     AlertType.PULLBACK_75_FROM_HIGH_OPEN, AlertType.PULLBACK_25_FROM_HIGH_OPEN),
]

AUTO_ANCHOR_TYPES = (
    AlertType.PULLBACK_75_FROM_LOW, AlertType.PULLBACK_25_FROM_LOW,
    AlertType.PULLBACK_75_FROM_HIGH, AlertType.PULLBACK_25_FROM_HIGH,
)


class PullbackAlertDetector(BaseAlertDetector):

    COOLDOWN = 60
    MIN_INITIAL_MOVE_PCT = 0.3

    def detect(self, current: AlertState, previous: Optional[AlertState]) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if not self._has_min_volume(current) or previous is None:
            return alerts

        price = current.price
        prev_price = previous.price
        high = current.intraday_high
        low = current.intraday_low

        if not high or not low or high <= low:
            return alerts

        for anchor_name, anchor_attr, pfl75, pfl25, pfh75, pfh25 in FIXED_ANCHOR_VARIANTS:
            anchor = getattr(current, anchor_attr, None)
            if anchor is None or anchor <= 0:
                continue
            self._check_pullback_from_lows(
                current, prev_price, price, low, anchor, anchor_name,
                pfl75, pfl25, alerts)
            self._check_pullback_from_highs(
                current, prev_price, price, high, anchor, anchor_name,
                pfh75, pfh25, alerts)

        self._check_auto_anchor(current, prev_price, price, high, low, alerts)

        return alerts

    def _check_auto_anchor(self, current, prev_price, price, high, low, alerts):
        """PFL75/PFL25/PFH75/PFH25: automatically picks whichever of open vs
        prev_close produces the bigger pattern (Fibonacci popular)."""
        open_p = current.open_price
        close_p = current.prev_close
        if not open_p or open_p <= 0:
            open_p = None
        if not close_p or close_p <= 0:
            close_p = None
        if open_p is None and close_p is None:
            return

        pfl75, pfl25, pfh75, pfh25 = AUTO_ANCHOR_TYPES

        for direction in ("low", "high"):
            if direction == "low":
                anchor_open = (open_p - low) if open_p else 0
                anchor_close = (close_p - low) if close_p else 0
            else:
                anchor_open = (high - open_p) if open_p else 0
                anchor_close = (high - close_p) if close_p else 0

            if anchor_open >= anchor_close and open_p:
                anchor, anchor_name = open_p, "auto/open"
            elif close_p:
                anchor, anchor_name = close_p, "auto/close"
            else:
                continue

            if direction == "low":
                self._check_pullback_from_lows(
                    current, prev_price, price, low, anchor, anchor_name,
                    pfl75, pfl25, alerts)
            else:
                self._check_pullback_from_highs(
                    current, prev_price, price, high, anchor, anchor_name,
                    pfh75, pfh25, alerts)

    def _check_pullback_from_lows(self, current, prev_price, price, low, anchor,
                                   anchor_name, type_75, type_25, alerts):
        """TI: Start at anchor (close/open). Stock goes DOWN to today's low.
        Report when stock returns X% of the way from low back to anchor."""
        sym = current.symbol
        initial_move = anchor - low
        if initial_move <= 0:
            return
        initial_move_pct = round(initial_move / anchor * 100, 2)
        if initial_move_pct < self.MIN_INITIAL_MOVE_PCT:
            return

        level_75 = low + 0.75 * initial_move
        level_25 = low + 0.25 * initial_move

        if prev_price < level_75 <= price:
            if self._can_fire(type_75, sym, self.COOLDOWN):
                self._record_fire(type_75, sym)
                alerts.append(self._make_alert(
                    type_75, current, quality=initial_move_pct,
                    description=f"75% pullback from lows ({anchor_name.capitalize()}), initial move {initial_move_pct}%",
                    prev_value=prev_price, new_value=price,
                    details={"initial_move_pct": initial_move_pct,
                             "level": round(level_75, 2),
                             "anchor": anchor_name, "anchor_price": anchor,
                             "extreme": low},
                ))

        if prev_price < level_25 <= price:
            if self._can_fire(type_25, sym, self.COOLDOWN):
                self._record_fire(type_25, sym)
                alerts.append(self._make_alert(
                    type_25, current, quality=initial_move_pct,
                    description=f"25% pullback from lows ({anchor_name.capitalize()}), initial move {initial_move_pct}%",
                    prev_value=prev_price, new_value=price,
                    details={"initial_move_pct": initial_move_pct,
                             "level": round(level_25, 2),
                             "anchor": anchor_name, "anchor_price": anchor,
                             "extreme": low},
                ))

    def _check_pullback_from_highs(self, current, prev_price, price, high, anchor,
                                    anchor_name, type_75, type_25, alerts):
        """TI: Start at anchor (close/open). Stock goes UP to today's high.
        Report when stock returns X% of the way from high back to anchor."""
        sym = current.symbol
        initial_move = high - anchor
        if initial_move <= 0:
            return
        initial_move_pct = round(initial_move / anchor * 100, 2)
        if initial_move_pct < self.MIN_INITIAL_MOVE_PCT:
            return

        level_75 = high - 0.75 * initial_move
        level_25 = high - 0.25 * initial_move

        if prev_price > level_75 >= price:
            if self._can_fire(type_75, sym, self.COOLDOWN):
                self._record_fire(type_75, sym)
                alerts.append(self._make_alert(
                    type_75, current, quality=initial_move_pct,
                    description=f"75% pullback from highs ({anchor_name.capitalize()}), initial move {initial_move_pct}%",
                    prev_value=prev_price, new_value=price,
                    details={"initial_move_pct": initial_move_pct,
                             "level": round(level_75, 2),
                             "anchor": anchor_name, "anchor_price": anchor,
                             "extreme": high},
                ))

        if prev_price > level_25 >= price:
            if self._can_fire(type_25, sym, self.COOLDOWN):
                self._record_fire(type_25, sym)
                alerts.append(self._make_alert(
                    type_25, current, quality=initial_move_pct,
                    description=f"25% pullback from highs ({anchor_name.capitalize()}), initial move {initial_move_pct}%",
                    prev_value=prev_price, new_value=price,
                    details={"initial_move_pct": initial_move_pct,
                             "level": round(level_25, 2),
                             "anchor": anchor_name, "anchor_price": anchor,
                             "extreme": high},
                ))
