"""
Session Alert Detector - Pre/Post market highs and lows.

Quality = lookback_days (same as regular new high/low).
"""

from typing import Optional, List, Dict

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord


class SessionAlertDetector(BaseAlertDetector):

    COOLDOWN = 30

    def __init__(self):
        super().__init__()
        self._pre_highs: Dict[str, float] = {}
        self._pre_lows: Dict[str, float] = {}
        self._post_highs: Dict[str, float] = {}
        self._post_lows: Dict[str, float] = {}

    def detect(self, current: AlertState, previous: Optional[AlertState]) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if not self._has_min_volume(current):
            return alerts

        session = current.market_session
        if session == "PRE_MARKET":
            self._detect_session_extremes(current, alerts,
                self._pre_highs, self._pre_lows,
                AlertType.PRE_MARKET_HIGH, AlertType.PRE_MARKET_LOW, "Pre-market")
        elif session == "POST_MARKET":
            self._detect_session_extremes(current, alerts,
                self._post_highs, self._post_lows,
                AlertType.POST_MARKET_HIGH, AlertType.POST_MARKET_LOW, "Post-market")

        return alerts

    def _detect_session_extremes(self, current, alerts, highs, lows, high_type, low_type, label):
        sym = current.symbol
        price = current.price
        prev_high = highs.get(sym)
        prev_low = lows.get(sym)

        if prev_high is None:
            highs[sym] = price
            lows[sym] = price
            return

        if price > prev_high:
            highs[sym] = price
            if self._can_fire(high_type, sym, self.COOLDOWN):
                self._record_fire(high_type, sym)
                lookback = 1
                if self.baseline:
                    from detectors.price_alerts import PriceAlertDetector
                    lookback, _, _ = PriceAlertDetector._compute_lookback_high(self, sym, price)
                alerts.append(self._make_alert(
                    high_type, current, quality=float(lookback),
                    description=f"{label} new high ${price:.2f}",
                    prev_value=prev_high, new_value=price,
                    details={"lookback_days": lookback, "session": label.lower()},
                ))

        if price < prev_low:
            lows[sym] = price
            if self._can_fire(low_type, sym, self.COOLDOWN):
                self._record_fire(low_type, sym)
                lookback = 1
                if self.baseline:
                    from detectors.price_alerts import PriceAlertDetector
                    lookback, _, _ = PriceAlertDetector._compute_lookback_low(self, sym, price)
                alerts.append(self._make_alert(
                    low_type, current, quality=float(lookback),
                    description=f"{label} new low ${price:.2f}",
                    prev_value=prev_low, new_value=price,
                    details={"lookback_days": lookback, "session": label.lower()},
                ))

    def reset_daily(self):
        super().reset_daily()
        self._pre_highs.clear()
        self._pre_lows.clear()
        self._post_highs.clear()
        self._post_lows.clear()
