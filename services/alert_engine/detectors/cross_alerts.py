"""
Cross Alert Detector - Price crossing reference levels.

Covers: CAO/CBO, CAC/CBC, CAOC/CBOC/CACC/CBCC (confirmed),
        CAVC/CBVC (VWAP), CA20/CB20/CA50/CB50/CA200/CB200 (daily MAs).

TI behavior for MA and VWAP crosses:
  "requires statistical confirmation before it appears. This filters out noise,
   but requires a slight delay. This analysis involves price, time, and volume.
   If the price continues to move around the MA, this alert may never appear."
  CAVC uses "the same statistical analysis" as confirmed crosses.
"""

import time
from typing import Optional, List, Dict

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord


class CrossAlertDetector(BaseAlertDetector):
    """TI cross alerts with volume-confirmed mechanism for MA and VWAP."""

    CONFIRM_TARGET_VOLUME_MINUTES = 15.0
    CONFIRM_MAX_WALL_SECONDS = 120

    def __init__(self):
        super().__init__()
        self._pending_confirms: Dict[str, Dict[str, dict]] = {}
        self._open_cross: Dict[str, dict] = {}
        self._close_cross: Dict[str, dict] = {}
        self._ma_last_side: Dict[str, Dict[str, str]] = {}

    def detect(self, current: AlertState, previous: Optional[AlertState]) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if not self._has_min_volume(current):
            return alerts
        if previous is None:
            return alerts
        self._detect_open_crosses(current, previous, alerts)
        self._detect_close_crosses(current, previous, alerts)
        self._detect_confirmed_crosses(current, alerts)
        self._detect_vwap_crosses(current, previous, alerts)
        self._detect_daily_ma_crosses(current, previous, alerts)
        return alerts

    def _get_open_ref(self, current):
        is_pre = current.market_session in ("PRE_MARKET", "PREMARKET", "PRE")
        if is_pre:
            return getattr(current, 'prev_open', None) or current.open_price
        return current.open_price

    def _detect_open_crosses(self, current, previous, alerts):
        """CAO/CBO: shared timer on the open level.
        TI: single print triggers. Quality = seconds since crossed.
        First cross always fires. Subsequent crosses only fire after price
        stays on one side for the user-configured time (anti-whipsaw).
        Crossing above and below share the same timer."""
        sym = current.symbol
        price = current.price
        prev_price = previous.price
        op = self._get_open_ref(current)
        if not op or op <= 0:
            return
        st = self._open_cross.get(sym)
        now = time.monotonic()
        crossed_above = prev_price <= op < price
        crossed_below = prev_price >= op > price
        if not crossed_above and not crossed_below:
            if st and st.get("side"):
                same_side = (st["side"] == "above" and price > op) or \
                            (st["side"] == "below" and price < op)
                if same_side:
                    st["stable_since"] = st.get("stable_since") or now
                else:
                    st["stable_since"] = None
            return
        if not st:
            st = {"last_cross_time": 0, "side": None, "stable_since": None, "fired_first": False}
            self._open_cross[sym] = st
        can_fire = False
        if not st["fired_first"]:
            can_fire = True
            st["fired_first"] = True
        elif st["stable_since"] and (now - st["stable_since"]) > 0:
            can_fire = True
        seconds_since = round(now - st["last_cross_time"], 0) if st["last_cross_time"] > 0 else 0.0
        if crossed_above and can_fire:
            st["side"] = "above"
            st["last_cross_time"] = now
            st["stable_since"] = None
            alerts.append(self._make_alert(
                AlertType.CROSSED_ABOVE_OPEN, current, quality=seconds_since,
                description=f"Crossed above open ${op:.2f}",
                prev_value=prev_price, new_value=price,
                details={"open_price": op, "seconds_since_crossed": seconds_since},
            ))
            self._start_confirm(sym, "above_open", price, now, current)
        if crossed_below and can_fire:
            st["side"] = "below"
            st["last_cross_time"] = now
            st["stable_since"] = None
            alerts.append(self._make_alert(
                AlertType.CROSSED_BELOW_OPEN, current, quality=seconds_since,
                description=f"Crossed below open ${op:.2f}",
                prev_value=prev_price, new_value=price,
                details={"open_price": op, "seconds_since_crossed": seconds_since},
            ))
            self._start_confirm(sym, "below_open", price, now, current)

    def _detect_close_crosses(self, current, previous, alerts):
        """CAC/CBC: shared timer on the close level.
        TI: same behavior as CAO/CBO. Quality = seconds since crossed."""
        sym = current.symbol
        price = current.price
        prev_price = previous.price
        pc = current.prev_close
        if not pc or pc <= 0:
            return
        st = self._close_cross.get(sym)
        now = time.monotonic()
        crossed_above = prev_price <= pc < price
        crossed_below = prev_price >= pc > price
        if not crossed_above and not crossed_below:
            if st and st.get("side"):
                same_side = (st["side"] == "above" and price > pc) or \
                            (st["side"] == "below" and price < pc)
                if same_side:
                    st["stable_since"] = st.get("stable_since") or now
                else:
                    st["stable_since"] = None
            return
        if not st:
            st = {"last_cross_time": 0, "side": None, "stable_since": None, "fired_first": False}
            self._close_cross[sym] = st
        can_fire = False
        if not st["fired_first"]:
            can_fire = True
            st["fired_first"] = True
        elif st["stable_since"] and (now - st["stable_since"]) > 0:
            can_fire = True
        seconds_since = round(now - st["last_cross_time"], 0) if st["last_cross_time"] > 0 else 0.0
        if crossed_above and can_fire:
            st["side"] = "above"
            st["last_cross_time"] = now
            st["stable_since"] = None
            alerts.append(self._make_alert(
                AlertType.CROSSED_ABOVE_CLOSE, current, quality=seconds_since,
                description=f"Crossed above prev close ${pc:.2f}",
                prev_value=prev_price, new_value=price,
                details={"prev_close": pc, "seconds_since_crossed": seconds_since},
            ))
            self._start_confirm(sym, "above_close", price, now, current)
        if crossed_below and can_fire:
            st["side"] = "below"
            st["last_cross_time"] = now
            st["stable_since"] = None
            alerts.append(self._make_alert(
                AlertType.CROSSED_BELOW_CLOSE, current, quality=seconds_since,
                description=f"Crossed below prev close ${pc:.2f}",
                prev_value=prev_price, new_value=price,
                details={"prev_close": pc, "seconds_since_crossed": seconds_since},
            ))
            self._start_confirm(sym, "below_close", price, now, current)

    def _detect_confirmed_crosses(self, current, alerts):
        """CAOC/CBOC/CACC/CBCC + MA/VWAP volume-confirmed crosses.
        TI: statistical confirmation involving price, time, and volume."""
        sym = current.symbol
        price = current.price
        now = time.monotonic()
        pending = self._pending_confirms.get(sym, {})
        to_remove = []
        cur_vol = current.volume or 0
        for key, state in pending.items():
            elapsed = now - state["start_time"]
            still_on_side = self._check_confirm_side(key, price, current)
            if not still_on_side:
                state["against_count"] = state.get("against_count", 0) + 1
                if state["against_count"] > 3 or elapsed > self.CONFIRM_MAX_WALL_SECONDS:
                    to_remove.append(key)
                continue
            state["against_count"] = 0
            vol_since = max(cur_vol - state["start_volume"], 0)
            avg_vol_per_min = state["avg_vol_per_min"]
            if avg_vol_per_min > 0:
                effective_minutes = vol_since / avg_vol_per_min
            else:
                effective_minutes = elapsed / 60.0
            if effective_minutes >= self.CONFIRM_TARGET_VOLUME_MINUTES or \
               elapsed >= self.CONFIRM_MAX_WALL_SECONDS:
                to_remove.append(key)
                alert_type = state.get("alert_type")
                if alert_type:
                    desc = state.get("description", f"Crossed {key.replace('_', ' ')} (confirmed)")
                    alerts.append(self._make_alert(
                        alert_type, current, quality=0.0,
                        description=desc,
                        prev_value=state["cross_price"], new_value=price,
                        details={"elapsed_seconds": round(elapsed, 0),
                                 "effective_minutes": round(effective_minutes, 1),
                                 "volume_since_cross": vol_since},
                    ))
        for key in to_remove:
            pending.pop(key, None)

    def _check_confirm_side(self, key, price, current):
        """Check if price is still on the correct side for a pending confirmation."""
        if key == "above_open":
            ref = self._get_open_ref(current)
            return ref and price > ref
        elif key == "below_open":
            ref = self._get_open_ref(current)
            return ref and price < ref
        elif key == "above_close" and current.prev_close:
            return price > current.prev_close
        elif key == "below_close" and current.prev_close:
            return price < current.prev_close
        elif key == "above_vwap" and current.vwap:
            return price > current.vwap
        elif key == "below_vwap" and current.vwap:
            return price < current.vwap
        elif key.startswith("above_sma_"):
            ma_val = self._get_ma_value(current, key.replace("above_sma_", ""))
            return ma_val and price > ma_val
        elif key.startswith("below_sma_"):
            ma_val = self._get_ma_value(current, key.replace("below_sma_", ""))
            return ma_val and price < ma_val
        return False

    @staticmethod
    def _get_ma_value(current, ma_key):
        ma_map = {"20": current.daily_sma_20, "50": current.daily_sma_50, "200": current.daily_sma_200}
        return ma_map.get(ma_key)

    def _detect_vwap_crosses(self, current, previous, alerts):
        """CAVC/CBVC: TI uses same statistical analysis as confirmed crosses."""
        sym = current.symbol
        price = current.price
        prev_price = previous.price
        vwap = current.vwap
        prev_vwap = previous.vwap
        if not vwap or vwap <= 0 or not prev_vwap:
            return
        now = time.monotonic()
        if prev_price <= prev_vwap and price > vwap:
            self._start_confirm(sym, "above_vwap", price, now, current,
                                alert_type=AlertType.CROSSED_ABOVE_VWAP,
                                ref_value=vwap,
                                description=f"Crossed above VWAP ${vwap:.2f}")
        if prev_price >= prev_vwap and price < vwap:
            self._start_confirm(sym, "below_vwap", price, now, current,
                                alert_type=AlertType.CROSSED_BELOW_VWAP,
                                ref_value=vwap,
                                description=f"Crossed below VWAP ${vwap:.2f}")

    def _detect_daily_ma_crosses(self, current, previous, alerts):
        """CA20/CB20/CA50/CB50/CA200/CB200: volume-confirmed MA crosses.
        Only fires once per direction until price crosses back."""
        sym = current.symbol
        price = current.price
        prev_price = previous.price
        now = time.monotonic()
        if sym not in self._ma_last_side:
            self._ma_last_side[sym] = {}
        ma_checks = [
            (current.daily_sma_20, previous.daily_sma_20,
             AlertType.CROSSED_ABOVE_SMA20_DAILY, AlertType.CROSSED_BELOW_SMA20_DAILY,
             "20 day moving average", "20"),
            (current.daily_sma_50, previous.daily_sma_50,
             AlertType.CROSSED_ABOVE_SMA50_DAILY, AlertType.CROSSED_BELOW_SMA50_DAILY,
             "50 day moving average", "50"),
            (current.daily_sma_200, previous.daily_sma_200,
             AlertType.CROSSED_ABOVE_SMA200, AlertType.CROSSED_BELOW_SMA200,
             "200 day moving average", "200"),
        ]
        for ma_val, prev_ma, up_type, dn_type, name, ma_key in ma_checks:
            if not ma_val or ma_val <= 0 or not prev_ma or prev_ma <= 0:
                continue
            last_side = self._ma_last_side[sym].get(ma_key)
            if prev_price <= prev_ma and price > ma_val:
                if last_side != "above":
                    self._ma_last_side[sym][ma_key] = "above"
                    confirm_key = f"above_sma_{ma_key}"
                    self._start_confirm(sym, confirm_key, price, now, current,
                                        alert_type=up_type, ref_value=ma_val,
                                        description=f"Crossed above {name} ${ma_val:.2f}")
            elif prev_price >= prev_ma and price < ma_val:
                if last_side != "below":
                    self._ma_last_side[sym][ma_key] = "below"
                    confirm_key = f"below_sma_{ma_key}"
                    self._start_confirm(sym, confirm_key, price, now, current,
                                        alert_type=dn_type, ref_value=ma_val,
                                        description=f"Crossed below {name} ${ma_val:.2f}")

    def _start_confirm(self, symbol, key, price, timestamp, current=None,
                       alert_type=None, ref_value=None, description=None):
        if symbol not in self._pending_confirms:
            self._pending_confirms[symbol] = {}
        if alert_type is None:
            at_map = {
                "above_open": AlertType.CROSSED_ABOVE_OPEN_CONFIRMED,
                "below_open": AlertType.CROSSED_BELOW_OPEN_CONFIRMED,
                "above_close": AlertType.CROSSED_ABOVE_CLOSE_CONFIRMED,
                "below_close": AlertType.CROSSED_BELOW_CLOSE_CONFIRMED,
            }
            alert_type = at_map.get(key)
            if not description:
                description = f"Crossed {key.replace('_', ' ')} (confirmed by volume)"
        start_vol = (current.volume or 0) if current else 0
        avg_vol_per_min = 0.0
        if self.baseline and current:
            vb = self.baseline.get_volatility(symbol)
            if vb and vb.avg_daily_volume > 0:
                avg_vol_per_min = vb.avg_daily_volume / 390.0
        self._pending_confirms[symbol][key] = {
            "cross_price": price,
            "start_time": timestamp,
            "start_volume": start_vol,
            "avg_vol_per_min": avg_vol_per_min,
            "against_count": 0,
            "alert_type": alert_type,
            "ref_value": ref_value,
            "description": description,
        }

    def reset_daily(self):
        super().reset_daily()
        self._pending_confirms.clear()
        self._open_cross.clear()
        self._close_cross.clear()
        self._ma_last_side.clear()
