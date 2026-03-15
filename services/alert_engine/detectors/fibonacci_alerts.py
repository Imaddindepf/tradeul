"""
Fibonacci Retracement Alert Detector.

[FU38/FD38] 38% buy/sell signal
[FU50/FD50] 50% buy/sell signal
[FU62/FD62] 62% buy/sell signal
[FU79/FD79] 79% buy/sell signal

TI three-point pattern with decreasing volume confirmation:
  Point 1 (far left): strong volume-confirmed pivot, similar to geometric
           pattern algorithms. Requires volume BEFORE the pattern to ensure
           we start at a real pivot, not mid-pattern.
  Point 2 (middle):   support/resistance level with moderate volume
           confirmation, similar to S/R line algorithms.
  Point 3 (final):    single print crossing the Fibonacci level triggers
           the alert. After firing, trend is monitored; if most prints
           don't confirm the direction, the alert resets.

Buy signal (FU): price goes UP, turns, retraces DOWN through the Fib level.
  Interpretation: reversal (bullish). Green icon.
Sell signal (FD): price goes DOWN, turns, retraces UP through the Fib level.
  Interpretation: reversal (bearish). Red icon.

Quality = hours of the pattern (volume-weighted for pre/post market).
Custom setting = min hours.
"""

from datetime import datetime, time
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord


FIB_LEVELS: List[Tuple[int, AlertType, AlertType]] = [
    (38, AlertType.FIB_BUY_38, AlertType.FIB_SELL_38),
    (50, AlertType.FIB_BUY_50, AlertType.FIB_SELL_50),
    (62, AlertType.FIB_BUY_62, AlertType.FIB_SELL_62),
    (79, AlertType.FIB_BUY_79, AlertType.FIB_SELL_79),
]

MIN_PIVOT_VOLUME = 10_000
MIN_SR_VOLUME = 5_000
MIN_RANGE_PCT = 0.3
CONFIRM_PRINTS = 5
CONFIRM_RATIO = 0.6
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
HOURS_PER_PREPOST_VOLUME_UNIT = 1.0 / 6.5


@dataclass
class _Pivot:
    """Volume-confirmed turning point (Point 1)."""
    price: float
    timestamp: datetime
    is_high: bool
    volume: int


@dataclass
class _FibSwing:
    """A complete swing from pivot to extreme, tracking Fib level crosses."""
    pivot: _Pivot
    extreme_price: float
    extreme_ts: datetime
    extreme_volume: int
    fired: Dict[int, bool] = field(default_factory=dict)
    confirm_count: Dict[int, int] = field(default_factory=dict)
    confirm_total: Dict[int, int] = field(default_factory=dict)


@dataclass
class _SymbolState:
    trend_dir: int = 0
    extreme_price: float = 0.0
    extreme_ts: Optional[datetime] = None
    extreme_volume: int = 0
    prev_extreme_price: float = 0.0
    prev_extreme_ts: Optional[datetime] = None
    cum_volume: int = 0
    swings: List[_FibSwing] = field(default_factory=list)


class FibonacciAlertDetector(BaseAlertDetector):

    COOLDOWN = 300
    MAX_SWINGS = 4

    def __init__(self):
        super().__init__()
        self._states: Dict[str, _SymbolState] = {}

    def detect(
        self, current: AlertState, previous: Optional[AlertState]
    ) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if current.price is None or current.price <= 0:
            return alerts
        if previous is None or previous.price is None:
            return alerts
        if not self._has_min_volume(current):
            return alerts

        sym = current.symbol
        price = current.price
        prev_price = previous.price
        vol = current.volume or 0
        st = self._states.get(sym)

        if st is None:
            st = _SymbolState(
                extreme_price=price,
                extreme_ts=current.timestamp,
                extreme_volume=vol,
            )
            self._states[sym] = st
            return alerts

        st.cum_volume += vol

        new_high = price > st.extreme_price and st.trend_dir >= 0
        new_low = price < st.extreme_price and st.trend_dir <= 0

        if new_high:
            if st.trend_dir <= 0 and st.extreme_price > 0:
                self._maybe_register_pivot(st, current, is_high=False)
            st.trend_dir = 1
            st.extreme_price = price
            st.extreme_ts = current.timestamp
            st.extreme_volume = vol

        elif new_low:
            if st.trend_dir >= 0 and st.extreme_price > 0:
                self._maybe_register_pivot(st, current, is_high=True)
            st.trend_dir = -1
            st.extreme_price = price
            st.extreme_ts = current.timestamp
            st.extreme_volume = vol

        elif st.trend_dir == 0:
            st.extreme_price = price
            st.extreme_ts = current.timestamp
            return alerts

        for swing in st.swings:
            self._check_fib_levels(swing, current, prev_price, alerts)

        self._confirm_pending(st, current)

        return alerts

    def _maybe_register_pivot(
        self, st: _SymbolState, current: AlertState, is_high: bool
    ) -> None:
        """Register a volume-confirmed pivot (Point 1) and create swing."""
        if st.cum_volume < MIN_PIVOT_VOLUME:
            return
        if st.extreme_ts is None:
            return

        pivot = _Pivot(
            price=st.extreme_price,
            timestamp=st.extreme_ts,
            is_high=is_high,
            volume=st.cum_volume,
        )

        st.prev_extreme_price = st.extreme_price
        st.prev_extreme_ts = st.extreme_ts
        st.cum_volume = 0

        self._update_swings_with_new_extreme(st, pivot, current)

    def _update_swings_with_new_extreme(
        self, st: _SymbolState, pivot: _Pivot, current: AlertState
    ) -> None:
        """When we see a new pivot, we can create a swing from the PREVIOUS pivot
        to the extreme that just ended."""
        if not st.swings and pivot.volume >= MIN_PIVOT_VOLUME:
            swing = _FibSwing(
                pivot=pivot,
                extreme_price=current.price,
                extreme_ts=current.timestamp,
                extreme_volume=current.volume or 0,
            )
            st.swings.append(swing)
            if len(st.swings) > self.MAX_SWINGS:
                st.swings.pop(0)
            return

        for swing in st.swings:
            if pivot.is_high and current.price > swing.extreme_price:
                swing.extreme_price = current.price
                swing.extreme_ts = current.timestamp
                swing.extreme_volume = current.volume or 0
            elif not pivot.is_high and current.price < swing.extreme_price:
                swing.extreme_price = current.price
                swing.extreme_ts = current.timestamp
                swing.extreme_volume = current.volume or 0

        if pivot.volume >= MIN_PIVOT_VOLUME:
            swing = _FibSwing(
                pivot=pivot,
                extreme_price=current.price,
                extreme_ts=current.timestamp,
                extreme_volume=current.volume or 0,
            )
            st.swings.append(swing)
            if len(st.swings) > self.MAX_SWINGS:
                st.swings.pop(0)

    def _check_fib_levels(
        self,
        swing: _FibSwing,
        current: AlertState,
        prev_price: float,
        out: List[AlertRecord],
    ) -> None:
        p1 = swing.pivot.price
        p2 = swing.extreme_price
        swing_range = abs(p2 - p1)
        if swing_range <= 0:
            return
        if p1 <= 0:
            return
        range_pct = (swing_range / p1) * 100.0
        if range_pct < MIN_RANGE_PCT:
            return

        price = current.price
        sym = current.symbol

        for level_pct, buy_type, sell_type in FIB_LEVELS:
            fib_ratio = level_pct / 100.0

            if swing.pivot.is_high:
                fib_price = p2 + swing_range * fib_ratio
                if prev_price < fib_price <= price:
                    self._try_fire(
                        swing, level_pct, sell_type, current, fib_price,
                        p1, p2, swing_range, out,
                    )
            else:
                fib_price = p2 - swing_range * fib_ratio
                if prev_price > fib_price >= price:
                    self._try_fire(
                        swing, level_pct, buy_type, current, fib_price,
                        p1, p2, swing_range, out,
                    )

    def _try_fire(
        self,
        swing: _FibSwing,
        level_pct: int,
        alert_type: AlertType,
        current: AlertState,
        fib_price: float,
        p1: float,
        p2: float,
        swing_range: float,
        out: List[AlertRecord],
    ) -> None:
        key = level_pct
        if swing.fired.get(key, False):
            return
        if not self._can_fire(alert_type, current.symbol, self.COOLDOWN):
            return

        hours = self._pattern_hours(swing, current)
        swing.fired[key] = True
        swing.confirm_count[key] = 0
        swing.confirm_total[key] = 0
        self._record_fire(alert_type, current.symbol)

        direction = "buy" if "buy" in alert_type.value else "sell"
        out.append(self._make_alert(
            alert_type, current,
            quality=round(hours, 2),
            description=(
                f"Fibonacci {level_pct}% {direction} signal: "
                f"${p1:.2f} -> ${p2:.2f}, "
                f"retracement to ${fib_price:.2f} "
                f"(started {swing.pivot.timestamp.strftime('%H:%M')})"
            ),
            prev_value=p2,
            new_value=current.price,
            details={
                "fib_level": level_pct,
                "pivot_price": round(p1, 4),
                "extreme_price": round(p2, 4),
                "fib_price": round(fib_price, 4),
                "swing_range": round(swing_range, 4),
                "pattern_hours": round(hours, 2),
                "pivot_volume": swing.pivot.volume,
            },
        ))

    def _confirm_pending(self, st: _SymbolState, current: AlertState) -> None:
        """Post-alert trend confirmation. If most prints after firing don't
        confirm the direction, reset the fired flag so it can re-trigger."""
        price = current.price
        to_remove = []

        for swing in st.swings:
            for level_pct in list(swing.fired.keys()):
                if not swing.fired[level_pct]:
                    continue
                total = swing.confirm_total.get(level_pct, 0)
                if total >= CONFIRM_PRINTS:
                    count = swing.confirm_count.get(level_pct, 0)
                    if count / total < CONFIRM_RATIO:
                        swing.fired[level_pct] = False
                    swing.confirm_count.pop(level_pct, None)
                    swing.confirm_total.pop(level_pct, None)
                    continue

                swing.confirm_total[level_pct] = total + 1
                fib_ratio = level_pct / 100.0
                p1 = swing.pivot.price
                p2 = swing.extreme_price
                swing_range = abs(p2 - p1)

                if swing.pivot.is_high:
                    fib_price = p2 + swing_range * fib_ratio
                    if price >= fib_price:
                        swing.confirm_count[level_pct] = (
                            swing.confirm_count.get(level_pct, 0) + 1
                        )
                else:
                    fib_price = p2 - swing_range * fib_ratio
                    if price <= fib_price:
                        swing.confirm_count[level_pct] = (
                            swing.confirm_count.get(level_pct, 0) + 1
                        )

    def _pattern_hours(self, swing: _FibSwing, current: AlertState) -> float:
        """Volume-weighted hours since the pattern started.
        TI: pre/post market volume counts as ~1 hour for NQ100 stocks.
        We approximate by using elapsed wall-clock hours, weighted down
        for pre/post market periods."""
        start = swing.pivot.timestamp
        end = current.timestamp
        if start >= end:
            return 0.0

        delta = (end - start).total_seconds() / 3600.0

        start_t = start.time()
        end_t = end.time()
        in_market = (
            MARKET_OPEN <= start_t <= MARKET_CLOSE
            and MARKET_OPEN <= end_t <= MARKET_CLOSE
        )
        if in_market:
            return delta

        return delta * 0.15

    def reset_daily(self) -> None:
        super().reset_daily()
        self._states.clear()

    def cleanup_old_symbols(self, active: set) -> int:
        removed = sum(1 for s in list(self._states) if s not in active)
        self._states = {s: v for s, v in self._states.items() if s in active}
        return removed + super().cleanup_old_symbols(active)
