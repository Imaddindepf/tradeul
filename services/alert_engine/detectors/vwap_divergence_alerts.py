"""
VWAP Divergence Detector.

TI behavior:
  VDU — Positive VWAP Divergence: price is N integer % above VWAP.
  VDD — Negative VWAP Divergence: price is N integer % below VWAP.

  "This will notify you when the price moves an integer number of
   percentage points above/below the VWAP."
  "This will also tell you when the price crosses the VWAP."
  "This alert will typically go off only once at each integer percent level.
   However, if a price moves one way, then back the other way, the alerts
   will notify you of the return trip."

Quality = the integer % distance from VWAP. Reports each integer level
once, but re-fires if price returns from the other side.
"""

from typing import Optional, List, Dict

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord


class VWAPDivergenceAlertDetector(BaseAlertDetector):

    def __init__(self):
        super().__init__()
        self._vdu_fired: Dict[str, int] = {}
        self._vdd_fired: Dict[str, int] = {}

    def detect(self, current: AlertState, previous: Optional[AlertState]) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if not self._has_min_volume(current):
            return alerts

        price = current.price
        vwap = current.vwap
        if not vwap or vwap <= 0 or not price or price <= 0:
            return alerts

        sym = current.symbol
        pct = ((price - vwap) / vwap) * 100.0

        if pct >= 0:
            self._vdd_fired.pop(sym, None)
            level = int(pct)
            if level >= 1:
                fired = self._vdu_fired.get(sym, 0)
                if level > fired:
                    self._vdu_fired[sym] = level
                    alerts.append(self._make_alert(
                        AlertType.VWAP_DIVERGENCE_UP, current,
                        quality=float(level),
                        description=f"Trading {level}% above VWAP (${vwap:.2f})",
                        prev_value=vwap, new_value=price,
                        details={"pct_from_vwap": round(pct, 2), "level": level, "vwap": vwap},
                    ))
        else:
            self._vdu_fired.pop(sym, None)
            level = int(abs(pct))
            if level >= 1:
                fired = self._vdd_fired.get(sym, 0)
                if level > fired:
                    self._vdd_fired[sym] = level
                    alerts.append(self._make_alert(
                        AlertType.VWAP_DIVERGENCE_DOWN, current,
                        quality=float(level),
                        description=f"Trading {level}% below VWAP (${vwap:.2f})",
                        prev_value=vwap, new_value=price,
                        details={"pct_from_vwap": round(pct, 2), "level": level, "vwap": vwap},
                    ))

        return alerts

    def reset_daily(self):
        super().reset_daily()
        self._vdu_fired.clear()
        self._vdd_fired.clear()
