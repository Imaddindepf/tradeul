"""
Geometric Pattern Alert Detector.

All geometric patterns share the same turning-point infrastructure.
Volume-confirmed local highs and lows are tracked per symbol, then
classified into one of the following shapes:

[GBBOT/GBTOP] Broadening: higher highs AND lower lows (expanding range).
[GTBOT/GTTOP] Triangle:   lower highs AND higher lows (converging range).
[GRBOT/GRTOP] Rectangle:  highs ~same price AND lows ~same price.
[GDBOT/GDTOP] Double:     2+ lows (or highs) at ~same price with significant
              separation.  Can also report triple/quadruple.
[GHASI/GHAS]  Head & Shoulders: exactly 5 points with specific symmetry.

All patterns require at least 5 volume-confirmed turning points (except
Head & Shoulders which requires exactly 5).

Quality = hours of the pattern (volume-weighted for pre/post market).
Custom setting = min hours.
"""

from datetime import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass, field

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord


@dataclass
class TurningPoint:
    price: float
    timestamp: datetime
    is_high: bool
    volume: int = 0


@dataclass
class PatternScan:
    points: List[TurningPoint] = field(default_factory=list)
    trend_dir: int = 0
    extreme_price: float = 0.0
    extreme_ts: Optional[datetime] = None
    confirm_volume: int = 0
    last_fired: Dict[str, Optional[datetime]] = field(default_factory=dict)


class GeometricAlertDetector(BaseAlertDetector):

    MIN_TURNING_POINTS = 5
    COOLDOWN = 300
    MIN_REVERSAL_PCT = 0.3
    RECT_TOLERANCE_PCT = 0.5
    DOUBLE_TOLERANCE_PCT = 0.8

    def __init__(self):
        super().__init__()
        self._scans: Dict[str, PatternScan] = {}
        self._bar_count: Dict[str, int] = {}

    def detect(self, current: AlertState, previous: Optional[AlertState]) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if not self._has_min_volume(current) or previous is None:
            return alerts
        self._update_turning_points(current, previous)
        sym = current.symbol
        scan = self._scans.get(sym)
        if scan is None or len(scan.points) < self.MIN_TURNING_POINTS:
            return alerts

        self._check_broadening(current, scan, alerts)
        self._check_triangle(current, scan, alerts)
        self._check_rectangle(current, scan, alerts)
        self._check_double(current, scan, alerts)
        self._check_head_and_shoulders(current, scan, alerts)

        return alerts

    def _update_turning_points(self, current, previous):
        sym = current.symbol
        price = current.price
        prev_price = previous.price
        if price is None or prev_price is None or price <= 0:
            return

        scan = self._scans.get(sym)
        if scan is None:
            scan = PatternScan()
            self._scans[sym] = scan

        self._bar_count[sym] = self._bar_count.get(sym, 0) + 1
        move_pct = ((price - prev_price) / prev_price) * 100.0 if prev_price > 0 else 0.0
        vol = current.volume or 0

        if scan.trend_dir == 0:
            if move_pct > self.MIN_REVERSAL_PCT:
                scan.trend_dir = 1
                scan.extreme_price = price
                scan.extreme_ts = current.timestamp
                scan.confirm_volume = vol
            elif move_pct < -self.MIN_REVERSAL_PCT:
                scan.trend_dir = -1
                scan.extreme_price = price
                scan.extreme_ts = current.timestamp
                scan.confirm_volume = vol
            return

        if scan.trend_dir == 1:
            if price > scan.extreme_price:
                scan.extreme_price = price
                scan.extreme_ts = current.timestamp
                scan.confirm_volume += vol
            elif move_pct < -self.MIN_REVERSAL_PCT:
                self._register_tp(scan, is_high=True, vol=scan.confirm_volume)
                scan.trend_dir = -1
                scan.extreme_price = price
                scan.extreme_ts = current.timestamp
                scan.confirm_volume = vol
        else:
            if price < scan.extreme_price:
                scan.extreme_price = price
                scan.extreme_ts = current.timestamp
                scan.confirm_volume += vol
            elif move_pct > self.MIN_REVERSAL_PCT:
                self._register_tp(scan, is_high=False, vol=scan.confirm_volume)
                scan.trend_dir = 1
                scan.extreme_price = price
                scan.extreme_ts = current.timestamp
                scan.confirm_volume = vol

    @staticmethod
    def _register_tp(scan: PatternScan, is_high: bool, vol: int):
        tp = TurningPoint(
            price=scan.extreme_price,
            timestamp=scan.extreme_ts or datetime.utcnow(),
            is_high=is_high,
            volume=vol,
        )
        scan.points.append(tp)
        if len(scan.points) > 30:
            scan.points = scan.points[-30:]

    # ── Pattern hours ──

    @staticmethod
    def _pattern_hours(points: List[TurningPoint]) -> float:
        if len(points) < 2:
            return 0.0
        delta = (points[-1].timestamp - points[0].timestamp).total_seconds()
        return round(delta / 3600.0, 1)

    # ── Emit helper ──

    def _emit(self, alert_type, current, scan, points, label, alerts):
        sym = current.symbol
        fire_key = alert_type.value
        last = scan.last_fired.get(fire_key)
        if last is not None and points[-1].timestamp <= last:
            return
        if not self._can_fire(alert_type, sym, self.COOLDOWN):
            return

        self._record_fire(alert_type, sym)
        scan.last_fired[fire_key] = current.timestamp

        hours = self._pattern_hours(points)
        price_list = ", ".join(
            f"{'H' if p.is_high else 'L'} ${p.price:.2f}" for p in points[-self.MIN_TURNING_POINTS:]
        )
        first_ts = points[0].timestamp
        last_ts = points[-1].timestamp
        time_range = f"{first_ts.strftime('%H:%M')}-{last_ts.strftime('%H:%M')}"
        desc = f"{label}: {price_list}. {time_range} ({hours:.1f}h)"

        alerts.append(self._make_alert(
            alert_type, current,
            quality=hours,
            description=desc,
            prev_value=points[0].price,
            new_value=points[-1].price,
            details={
                "turning_points": [
                    {"price": p.price, "is_high": p.is_high,
                     "time": p.timestamp.isoformat(), "volume": p.volume}
                    for p in points[-self.MIN_TURNING_POINTS:]
                ],
                "hours": hours,
                "time_range": time_range,
            },
        ))

    # ── BROADENING: higher highs AND lower lows ──

    def _check_broadening(self, current, scan, alerts):
        pts = scan.points
        if not self._is_broadening(pts):
            return
        last_pt = pts[-1]
        if not last_pt.is_high and scan.trend_dir == 1:
            self._emit(AlertType.BROADENING_BOTTOM, current, scan, pts,
                       "Broadening bottom", alerts)
        elif last_pt.is_high and scan.trend_dir == -1:
            self._emit(AlertType.BROADENING_TOP, current, scan, pts,
                       "Broadening top", alerts)

    @staticmethod
    def _is_broadening(points: List[TurningPoint]) -> bool:
        highs = [p for p in points if p.is_high]
        lows = [p for p in points if not p.is_high]
        if len(highs) < 2 or len(lows) < 2:
            return False
        recent_highs = highs[-3:] if len(highs) >= 3 else highs[-2:]
        for i in range(1, len(recent_highs)):
            if recent_highs[i].price <= recent_highs[i - 1].price:
                return False
        recent_lows = lows[-3:] if len(lows) >= 3 else lows[-2:]
        for i in range(1, len(recent_lows)):
            if recent_lows[i].price >= recent_lows[i - 1].price:
                return False
        return True

    # ── TRIANGLE: lower highs AND higher lows (converging) ──

    def _check_triangle(self, current, scan, alerts):
        pts = scan.points
        if not self._is_triangle(pts):
            return
        first_pt = pts[0]
        last_pt = pts[-1]
        if not first_pt.is_high and scan.trend_dir == 1:
            self._emit(AlertType.TRIANGLE_BOTTOM, current, scan, pts,
                       "Triangle bottom", alerts)
        elif first_pt.is_high and scan.trend_dir == -1:
            self._emit(AlertType.TRIANGLE_TOP, current, scan, pts,
                       "Triangle top", alerts)

    @staticmethod
    def _is_triangle(points: List[TurningPoint]) -> bool:
        highs = [p for p in points if p.is_high]
        lows = [p for p in points if not p.is_high]
        if len(highs) < 2 or len(lows) < 2:
            return False
        recent_highs = highs[-3:] if len(highs) >= 3 else highs[-2:]
        for i in range(1, len(recent_highs)):
            if recent_highs[i].price >= recent_highs[i - 1].price:
                return False
        recent_lows = lows[-3:] if len(lows) >= 3 else lows[-2:]
        for i in range(1, len(recent_lows)):
            if recent_lows[i].price <= recent_lows[i - 1].price:
                return False
        return True

    # ── RECTANGLE: highs ~same AND lows ~same ──

    def _check_rectangle(self, current, scan, alerts):
        pts = scan.points
        if not self._is_rectangle(pts):
            return
        last_pt = pts[-1]
        if not last_pt.is_high:
            self._emit(AlertType.RECTANGLE_BOTTOM, current, scan, pts,
                       "Rectangle bottom", alerts)
        else:
            self._emit(AlertType.RECTANGLE_TOP, current, scan, pts,
                       "Rectangle top", alerts)

    def _is_rectangle(self, points: List[TurningPoint]) -> bool:
        highs = [p.price for p in points if p.is_high]
        lows = [p.price for p in points if not p.is_high]
        if len(highs) < 2 or len(lows) < 2:
            return False
        avg_high = sum(highs) / len(highs)
        avg_low = sum(lows) / len(lows)
        if avg_high <= avg_low:
            return False
        range_size = avg_high - avg_low
        if range_size <= 0:
            return False
        tol = range_size * self.RECT_TOLERANCE_PCT
        for h in highs:
            if abs(h - avg_high) > tol:
                return False
        for lo in lows:
            if abs(lo - avg_low) > tol:
                return False
        return True

    # ── DOUBLE BOTTOM/TOP: 2+ lows (or highs) at ~same price ──

    def _check_double(self, current, scan, alerts):
        pts = scan.points
        lows = [p for p in pts if not p.is_high]
        if len(lows) >= 2:
            groups = self._group_same_price(lows)
            for group in groups:
                if len(group) >= 2 and self._has_significant_separation(group):
                    last_in_group = group[-1]
                    if last_in_group == pts[-1] or (
                        pts[-1].timestamp - last_in_group.timestamp
                    ).total_seconds() < 60:
                        count = len(group)
                        label = self._double_label(count, "bottom")
                        self._emit(AlertType.DOUBLE_BOTTOM, current, scan,
                                   [group[0], group[-1]], label, alerts)
                        break

        highs = [p for p in pts if p.is_high]
        if len(highs) >= 2:
            groups = self._group_same_price(highs)
            for group in groups:
                if len(group) >= 2 and self._has_significant_separation(group):
                    last_in_group = group[-1]
                    if last_in_group == pts[-1] or (
                        pts[-1].timestamp - last_in_group.timestamp
                    ).total_seconds() < 60:
                        count = len(group)
                        label = self._double_label(count, "top")
                        self._emit(AlertType.DOUBLE_TOP, current, scan,
                                   [group[0], group[-1]], label, alerts)
                        break

    def _group_same_price(self, points: List[TurningPoint]) -> List[List[TurningPoint]]:
        if not points:
            return []
        avg_price = sum(p.price for p in points) / len(points)
        range_est = max(p.price for p in points) - min(p.price for p in points)
        tol = max(range_est * self.DOUBLE_TOLERANCE_PCT, avg_price * 0.005)

        groups: List[List[TurningPoint]] = []
        used = set()
        for i, anchor in enumerate(points):
            if i in used:
                continue
            group = [anchor]
            used.add(i)
            for j in range(i + 1, len(points)):
                if j in used:
                    continue
                if abs(points[j].price - anchor.price) <= tol:
                    group.append(points[j])
                    used.add(j)
            if len(group) >= 2:
                groups.append(group)
        return groups

    @staticmethod
    def _has_significant_separation(group: List[TurningPoint]) -> bool:
        if len(group) < 2:
            return False
        total_seconds = (group[-1].timestamp - group[0].timestamp).total_seconds()
        total_volume = sum(p.volume for p in group)
        return total_seconds >= 300 or total_volume >= 50_000

    @staticmethod
    def _double_label(count: int, side: str) -> str:
        names = {2: "Double", 3: "Triple", 4: "Quadruple"}
        prefix = names.get(count, f"{count}x")
        return f"{prefix} {side}"

    # ── HEAD & SHOULDERS: exactly 5 points with symmetry ──

    def _check_head_and_shoulders(self, current, scan, alerts):
        pts = scan.points
        if len(pts) < 5:
            return
        last5 = pts[-5:]
        self._check_inv_has(current, scan, last5, alerts)
        self._check_has(current, scan, last5, alerts)

    def _check_inv_has(self, current, scan, pts5, alerts):
        """GHASI: L H L H L where 3rd is lowest, 1st~5th, 2nd~4th."""
        p1, p2, p3, p4, p5 = pts5
        if p1.is_high or not p2.is_high or p3.is_high or not p4.is_high or p5.is_high:
            return
        if p3.price >= p1.price or p3.price >= p5.price:
            return
        pattern_range = max(p.price for p in pts5) - min(p.price for p in pts5)
        if pattern_range <= 0:
            return
        tol = pattern_range * 0.3
        if abs(p1.price - p5.price) > tol:
            return
        if abs(p2.price - p4.price) > tol:
            return
        self._emit(AlertType.HEAD_AND_SHOULDERS_INV, current, scan, list(pts5),
                   "Inverted head and shoulders", alerts)

    def _check_has(self, current, scan, pts5, alerts):
        """GHAS: H L H L H where 3rd is highest, 1st~5th, 2nd~4th."""
        p1, p2, p3, p4, p5 = pts5
        if not p1.is_high or p2.is_high or not p3.is_high or p4.is_high or not p5.is_high:
            return
        if p3.price <= p1.price or p3.price <= p5.price:
            return
        pattern_range = max(p.price for p in pts5) - min(p.price for p in pts5)
        if pattern_range <= 0:
            return
        tol = pattern_range * 0.3
        if abs(p1.price - p5.price) > tol:
            return
        if abs(p2.price - p4.price) > tol:
            return
        self._emit(AlertType.HEAD_AND_SHOULDERS, current, scan, list(pts5),
                   "Head and shoulders", alerts)

    def reset_daily(self):
        super().reset_daily()
        self._scans.clear()
        self._bar_count.clear()
