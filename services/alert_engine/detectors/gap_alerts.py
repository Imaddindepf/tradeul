"""
Gap Alert Detector - Gap reversals and false gap retracements.

TI behavior:
  GDR -- Gap Down Reversal: stock gaps down, then price crosses prev_close
         from below for the first time. Quality = total retracement (gap + continuation).
  GUR -- Gap Up Reversal: stock gaps up, then price crosses prev_close
         from above for the first time. Quality = total retracement.

  FGUR -- False Gap Up Retracement: stock gaps up, price partially fills
          the gap (drops below open but stays above prev_close), then price
          rises back above open. Horseshoe pattern. Quality = % of gap filled.
  FGDR -- False Gap Down Retracement: stock gaps down, price partially fills
          the gap (rises above open but stays below prev_close), then price
          drops back below open. Quality = % of gap filled.
"""

from typing import Optional, List, Dict

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord


class GapAlertDetector(BaseAlertDetector):

    MIN_GAP_DOLLARS = 0.01

    def __init__(self):
        super().__init__()
        self._gur_fired: Dict[str, bool] = {}
        self._gdr_fired: Dict[str, bool] = {}
        self._fgur_state: Dict[str, dict] = {}
        self._fgdr_state: Dict[str, dict] = {}
        self._gap_continuation: Dict[str, float] = {}

    def detect(self, current: AlertState, previous: Optional[AlertState]) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if not self._has_min_volume(current) or previous is None:
            return alerts

        sym = current.symbol
        price = current.price
        prev_price = previous.price
        op = current.open_price
        pc = current.prev_close

        if not op or not pc or pc <= 0 or op <= 0:
            return alerts

        gap_dollars = op - pc

        if abs(gap_dollars) < self.MIN_GAP_DOLLARS:
            return alerts

        if gap_dollars > 0:
            self._detect_gap_up(sym, price, prev_price, op, pc, gap_dollars, current, alerts)
        elif gap_dollars < 0:
            self._detect_gap_down(sym, price, prev_price, op, pc, gap_dollars, current, alerts)

        return alerts

    def _detect_gap_up(self, sym, price, prev_price, op, pc, gap_dollars, current, alerts):
        high = current.intraday_high or price
        continuation = max(high - op, 0.0)
        cont_key = f"{sym}_up"
        prev_cont = self._gap_continuation.get(cont_key, 0.0)
        if continuation > prev_cont:
            self._gap_continuation[cont_key] = continuation

        if prev_price >= pc and price < pc:
            if not self._gur_fired.get(sym):
                self._gur_fired[sym] = True
                actual_cont = self._gap_continuation.get(cont_key, 0.0)
                total_retrace = gap_dollars + actual_cont
                gap_pct = (gap_dollars / pc) * 100
                alerts.append(self._make_alert(
                    AlertType.GAP_UP_REVERSAL, current,
                    quality=round(total_retrace, 2),
                    description=f"Gap up reversal: gap ${gap_dollars:.2f} (+{gap_pct:.1f}%), "
                                f"continuation ${actual_cont:.2f}, "
                                f"total retracement ${total_retrace:.2f}",
                    prev_value=prev_price, new_value=price,
                    details={"gap_dollars": round(gap_dollars, 2),
                             "gap_pct": round(gap_pct, 1),
                             "continuation": round(actual_cont, 2),
                             "total_retracement": round(total_retrace, 2)},
                ))

        st = self._fgur_state.get(sym)
        if st is None:
            st = {"phase": "watching", "min_below_open": None, "fired": False}
            self._fgur_state[sym] = st

        if st["fired"]:
            return

        if price < op and price > pc:
            if st["min_below_open"] is None or price < st["min_below_open"]:
                st["min_below_open"] = price
            st["phase"] = "filled"
        elif price <= pc:
            st["phase"] = "overfilled"

        if st["phase"] == "filled" and st["min_below_open"] is not None:
            if prev_price <= op and price > op:
                fill_amount = op - st["min_below_open"]
                fill_pct = (fill_amount / gap_dollars) * 100.0
                st["fired"] = True
                gap_pct = (gap_dollars / pc) * 100
                alerts.append(self._make_alert(
                    AlertType.FALSE_GAP_UP_RETRACEMENT, current,
                    quality=round(fill_pct, 0),
                    description=f"False gap up retracement: gap ${gap_dollars:.2f} (+{gap_pct:.1f}%), "
                                f"{fill_pct:.0f}% filled then continued",
                    prev_value=prev_price, new_value=price,
                    details={"gap_dollars": round(gap_dollars, 2),
                             "gap_pct": round(gap_pct, 1),
                             "fill_pct": round(fill_pct, 1),
                             "min_price": st["min_below_open"]},
                ))

    def _detect_gap_down(self, sym, price, prev_price, op, pc, gap_dollars, current, alerts):
        low = current.intraday_low or price
        continuation = max(op - low, 0.0)
        cont_key = f"{sym}_dn"
        prev_cont = self._gap_continuation.get(cont_key, 0.0)
        if continuation > prev_cont:
            self._gap_continuation[cont_key] = continuation

        if prev_price <= pc and price > pc:
            if not self._gdr_fired.get(sym):
                self._gdr_fired[sym] = True
                actual_cont = self._gap_continuation.get(cont_key, 0.0)
                total_retrace = abs(gap_dollars) + actual_cont
                gap_pct = (gap_dollars / pc) * 100
                alerts.append(self._make_alert(
                    AlertType.GAP_DOWN_REVERSAL, current,
                    quality=round(total_retrace, 2),
                    description=f"Gap down reversal: gap ${abs(gap_dollars):.2f} ({gap_pct:.1f}%), "
                                f"continuation ${actual_cont:.2f}, "
                                f"total retracement ${total_retrace:.2f}",
                    prev_value=prev_price, new_value=price,
                    details={"gap_dollars": round(gap_dollars, 2),
                             "gap_pct": round(gap_pct, 1),
                             "continuation": round(actual_cont, 2),
                             "total_retracement": round(total_retrace, 2)},
                ))

        st = self._fgdr_state.get(sym)
        if st is None:
            st = {"phase": "watching", "max_above_open": None, "fired": False}
            self._fgdr_state[sym] = st

        if st["fired"]:
            return

        if price > op and price < pc:
            if st["max_above_open"] is None or price > st["max_above_open"]:
                st["max_above_open"] = price
            st["phase"] = "filled"
        elif price >= pc:
            st["phase"] = "overfilled"

        if st["phase"] == "filled" and st["max_above_open"] is not None:
            if prev_price >= op and price < op:
                fill_amount = st["max_above_open"] - op
                fill_pct = (fill_amount / abs(gap_dollars)) * 100.0
                st["fired"] = True
                gap_pct = (gap_dollars / pc) * 100
                alerts.append(self._make_alert(
                    AlertType.FALSE_GAP_DOWN_RETRACEMENT, current,
                    quality=round(fill_pct, 0),
                    description=f"False gap down retracement: gap ${abs(gap_dollars):.2f} ({gap_pct:.1f}%), "
                                f"{fill_pct:.0f}% filled then continued",
                    prev_value=prev_price, new_value=price,
                    details={"gap_dollars": round(gap_dollars, 2),
                             "gap_pct": round(gap_pct, 1),
                             "fill_pct": round(fill_pct, 1),
                             "max_price": st["max_above_open"]},
                ))

    def reset_daily(self):
        super().reset_daily()
        self._gur_fired.clear()
        self._gdr_fired.clear()
        self._fgur_state.clear()
        self._fgdr_state.clear()
        self._gap_continuation.clear()
