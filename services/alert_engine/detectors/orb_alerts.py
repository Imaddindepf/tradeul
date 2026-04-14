"""
Opening Range Breakout (ORB) Detector — All 7 Tradeul timeframes.

Tradeul codes: ORU1/ORD1, ORU2/ORD2, ORU5/ORD5, ORU10/ORD10,
                   ORU15/ORD15, ORU30/ORD30, ORU60/ORD60.

The opening range is defined as [low, high] of the first N minutes
after the stock's first print of the day. The range is built during
the window, then locked. A breakout fires the FIRST time price
crosses above the range high (or below the range low) for the day.

Quality = the % width of the opening range. Wider range = higher
quality breakout because the stock had to overcome more resistance.

Per Tradeul: "1 minute does not mean one minute after the bell.
Each stock has its own clock. We start the clock when a stock has
its first print of the day."

We approximate this by using the market open time (9:30 ET) since
we receive aggregates per-symbol only after their first trade.
"""

from datetime import datetime, time, timedelta
from typing import Optional, List, Dict

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord


ORB_WINDOWS = {
    1:  (AlertType.ORB_UP_1M,  AlertType.ORB_DOWN_1M),
    2:  (AlertType.ORB_UP_2M,  AlertType.ORB_DOWN_2M),
    5:  (AlertType.ORB_UP_5M,  AlertType.ORB_DOWN_5M),
    10: (AlertType.ORB_UP_10M, AlertType.ORB_DOWN_10M),
    15: (AlertType.ORB_UP_15M, AlertType.ORB_DOWN_15M),
    30: (AlertType.ORB_UP_30M, AlertType.ORB_DOWN_30M),
    60: (AlertType.ORB_UP_60M, AlertType.ORB_DOWN_60M),
}

MARKET_OPEN_DT = datetime(2000, 1, 1, 9, 30)


def _lock_time_for_window(window_min: int) -> time:
    """Compute lock time safely, handling windows that cross the hour boundary."""
    dt = MARKET_OPEN_DT + timedelta(minutes=window_min)
    return dt.time()


class ORBAlertDetector(BaseAlertDetector):

    COOLDOWN = 86400

    def __init__(self):
        super().__init__()
        self._orb_ranges: Dict[str, Dict] = {}

    def detect(self, current: AlertState, previous: Optional[AlertState]) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if not self._has_min_volume(current) or previous is None:
            return alerts

        price = current.price
        sym = current.symbol
        ih = current.intraday_high
        il = current.intraday_low
        op = current.open_price

        if op is None or ih is None or il is None:
            return alerts

        ts = current.timestamp
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        ct = ts.time()

        if ct < time(9, 30):
            return alerts

        for window_min, (up_type, dn_type) in ORB_WINDOWS.items():
            lock_t = _lock_time_for_window(window_min)
            key = f"{sym}:{window_min}"
            orb = self._orb_ranges.get(key)

            if orb is None:
                self._orb_ranges[key] = {
                    "high": ih, "low": il,
                    "locked": False, "fired_up": False, "fired_down": False,
                }
                continue

            if orb["locked"] and orb["fired_up"] and orb["fired_down"]:
                continue

            if not orb["locked"]:
                if ct < lock_t:
                    orb["high"] = max(orb["high"], ih)
                    orb["low"] = min(orb["low"], il)
                    continue
                else:
                    orb["locked"] = True
                    orb["high"] = max(orb["high"], ih)
                    orb["low"] = min(orb["low"], il)

            orb_high = orb["high"]
            orb_low = orb["low"]

            if orb_high <= orb_low:
                continue
            range_pct = round((orb_high - orb_low) / orb_low * 100, 2)
            if range_pct < 0.01:
                continue

            if not orb["fired_up"] and previous.price <= orb_high < price:
                orb["fired_up"] = True
                if self._can_fire(up_type, sym, self.COOLDOWN):
                    self._record_fire(up_type, sym)
                    alerts.append(self._make_alert(
                        up_type, current, quality=range_pct,
                        description=f"Opening Range Breakout ({window_min} minutes)",
                        prev_value=orb_high, new_value=price,
                        details={
                            "orb_high": round(orb_high, 4),
                            "orb_low": round(orb_low, 4),
                            "range_pct": range_pct,
                            "window_min": window_min,
                        },
                    ))

            if not orb["fired_down"] and previous.price >= orb_low > price:
                orb["fired_down"] = True
                if self._can_fire(dn_type, sym, self.COOLDOWN):
                    self._record_fire(dn_type, sym)
                    alerts.append(self._make_alert(
                        dn_type, current, quality=range_pct,
                        description=f"Opening Range Breakdown ({window_min} minutes)",
                        prev_value=orb_low, new_value=price,
                        details={
                            "orb_high": round(orb_high, 4),
                            "orb_low": round(orb_low, 4),
                            "range_pct": range_pct,
                            "window_min": window_min,
                        },
                    ))

        return alerts

    def reset_daily(self):
        super().reset_daily()
        self._orb_ranges.clear()

    def cleanup_old_symbols(self, active: set) -> int:
        stale = [k for k in self._orb_ranges if k.split(":")[0] not in active]
        for k in stale:
            del self._orb_ranges[k]
        return len(stale) + super().cleanup_old_symbols(active)
