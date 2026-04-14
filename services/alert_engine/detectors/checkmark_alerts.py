"""
Check Mark Alert Detector - CMU (bullish) and CMD (bearish) continuation patterns.

Tradeul spec:
  CMU: higher highs -> pullback -> even higher highs (continuation up)
  CMD: lower lows -> bounce -> even lower lows (continuation down)

  Based on daily highs and lows (intraday extremes).
  Never reported before open or in first 3 minutes after open.
  No custom settings. No quality column documented.
"""

from datetime import time as dtime
from typing import Optional, List, Dict

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord

EARLIEST_FIRE = dtime(9, 33, 0)


class CheckMarkAlertDetector(BaseAlertDetector):

    COOLDOWN = 600

    def __init__(self):
        super().__init__()
        self._high_seq: Dict[str, List[float]] = {}
        self._low_seq: Dict[str, List[float]] = {}

    def detect(self, current: AlertState, previous: Optional[AlertState]) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if not self._has_min_volume(current) or previous is None:
            return alerts

        self._track(current)

        if current.timestamp and current.timestamp.time() < EARLIEST_FIRE:
            return alerts

        self._detect_cmu(current, alerts)
        self._detect_cmd(current, alerts)
        return alerts

    def _track(self, current):
        """Track sequence of intraday highs and lows for pattern detection."""
        sym = current.symbol
        high = current.intraday_high
        low = current.intraday_low

        if high:
            if sym not in self._high_seq:
                self._high_seq[sym] = []
            seq = self._high_seq[sym]
            if not seq or high != seq[-1]:
                seq.append(high)
                if len(seq) > 10:
                    self._high_seq[sym] = seq[-10:]

        if low:
            if sym not in self._low_seq:
                self._low_seq[sym] = []
            seq = self._low_seq[sym]
            if not seq or low != seq[-1]:
                seq.append(low)
                if len(seq) > 10:
                    self._low_seq[sym] = seq[-10:]

    def _detect_cmu(self, current, alerts):
        """CMU: higher highs -> pullback (lower high) -> price breaks above prior high."""
        sym = current.symbol
        seq = self._high_seq.get(sym)
        if not seq or len(seq) < 3:
            return

        h1, h2, h3 = seq[-3], seq[-2], seq[-1]
        if not (h2 > h1 and h3 < h2):
            return

        price = current.price
        if price <= h2:
            return

        if self._can_fire(AlertType.CHECK_MARK_UP, sym, self.COOLDOWN):
            self._record_fire(AlertType.CHECK_MARK_UP, sym)
            move_pct = round((price - h3) / h3 * 100, 2) if h3 > 0 else 0
            alerts.append(self._make_alert(
                AlertType.CHECK_MARK_UP, current, quality=move_pct,
                description=(
                    f"Check mark: highs ${h1:.2f} -> ${h2:.2f}, "
                    f"pullback to ${h3:.2f}, new high ${price:.2f}"
                ),
                prev_value=h2, new_value=price,
                details={"h1": h1, "h2": h2, "pullback": h3, "breakout": price},
            ))

    def _detect_cmd(self, current, alerts):
        """CMD: lower lows -> bounce (higher low) -> price breaks below prior low."""
        sym = current.symbol
        seq = self._low_seq.get(sym)
        if not seq or len(seq) < 3:
            return

        l1, l2, l3 = seq[-3], seq[-2], seq[-1]
        if not (l2 < l1 and l3 > l2):
            return

        price = current.price
        if price >= l2:
            return

        if self._can_fire(AlertType.CHECK_MARK_DOWN, sym, self.COOLDOWN):
            self._record_fire(AlertType.CHECK_MARK_DOWN, sym)
            move_pct = round((l3 - price) / l3 * 100, 2) if l3 > 0 else 0
            alerts.append(self._make_alert(
                AlertType.CHECK_MARK_DOWN, current, quality=move_pct,
                description=(
                    f"Inverted check mark: lows ${l1:.2f} -> ${l2:.2f}, "
                    f"bounce to ${l3:.2f}, new low ${price:.2f}"
                ),
                prev_value=l2, new_value=price,
                details={"l1": l1, "l2": l2, "bounce": l3, "breakdown": price},
            ))

    def reset_daily(self):
        super().reset_daily()
        self._high_seq.clear()
        self._low_seq.clear()
