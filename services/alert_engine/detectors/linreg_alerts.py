"""
Linear Regression Trend Alert Detector.

[PEU5/PED5]   5-minute linear regression up/down trend
[PEU15/PED15] 15-minute linear regression up/down trend
[PEU30/PED30] 30-minute linear regression up/down trend
[PEU90/PED90] 90-minute linear regression up/down trend

TI behavior:
  - Long-term linear regression forms a channel (trend + width).
  - Short-term linear regression shows current momentum.
  - Alert fires when short-term momentum crosses from one side of the
    channel to the other (upward cross = uptrend, downward = downtrend).
  - Quality = dollars per share of room left in the channel.
  - Custom setting = min $/share forecast.

Implementation:
  We maintain a rolling buffer of close prices per N-minute bar.
  Long-term regression uses ~20 bars, short-term uses ~5 bars.
  Channel width = 2 * standard error of the long-term regression.
  Signal fires when short-term slope crosses zero relative to the
  channel midline, and price is within the channel.
"""

import math
from datetime import datetime, time
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field
from collections import deque

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord


LONG_PERIOD = 20
SHORT_PERIOD = 5
MARKET_OPEN = time(9, 30)


@dataclass
class _BarData:
    close: float
    high: float
    low: float
    timestamp: datetime


@dataclass
class _TFState:
    bars: deque = field(default_factory=lambda: deque(maxlen=LONG_PERIOD + 2))
    current_bar_start: Optional[datetime] = None
    current_high: float = 0.0
    current_low: float = float("inf")
    current_close: float = 0.0
    prev_short_slope: float = 0.0
    fired_up: bool = False
    fired_down: bool = False


@dataclass
class _SymbolState:
    timeframes: Dict[int, _TFState] = field(default_factory=dict)


_TF_CONFIG: List[Tuple[int, AlertType, AlertType]] = [
    (5, AlertType.LINREG_UP_5M, AlertType.LINREG_DOWN_5M),
    (15, AlertType.LINREG_UP_15M, AlertType.LINREG_DOWN_15M),
    (30, AlertType.LINREG_UP_30M, AlertType.LINREG_DOWN_30M),
    (90, AlertType.LINREG_UP_90M, AlertType.LINREG_DOWN_90M),
]


def _linreg(values: List[float]) -> Tuple[float, float, float]:
    """Returns (slope, intercept, std_error) for y = slope*x + intercept."""
    n = len(values)
    if n < 3:
        return 0.0, 0.0, 0.0
    sx = n * (n - 1) / 2.0
    sx2 = n * (n - 1) * (2 * n - 1) / 6.0
    sy = sum(values)
    sxy = sum(i * v for i, v in enumerate(values))

    denom = n * sx2 - sx * sx
    if abs(denom) < 1e-12:
        return 0.0, sy / n, 0.0

    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n

    sse = sum((v - (slope * i + intercept)) ** 2 for i, v in enumerate(values))
    std_err = math.sqrt(sse / (n - 2)) if n > 2 else 0.0

    return slope, intercept, std_err


def _bar_start(ts: datetime, period_min: int) -> datetime:
    """Compute the start of the bar containing this timestamp."""
    minutes_since_midnight = ts.hour * 60 + ts.minute
    bar_idx = minutes_since_midnight // period_min
    bar_minute = bar_idx * period_min
    return ts.replace(hour=bar_minute // 60, minute=bar_minute % 60, second=0, microsecond=0)


class LinRegAlertDetector(BaseAlertDetector):

    COOLDOWN = 300

    def __init__(self):
        super().__init__()
        self._states: Dict[str, _SymbolState] = {}

    def detect(
        self, current: AlertState, previous: Optional[AlertState]
    ) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if current.price is None or current.price <= 0:
            return alerts
        if not self._has_min_volume(current):
            return alerts

        sym = current.symbol
        st = self._states.get(sym)
        if st is None:
            st = _SymbolState()
            self._states[sym] = st

        ts = current.timestamp
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)

        if ts.time() < MARKET_OPEN:
            return alerts

        price = current.price

        for period_min, up_type, dn_type in _TF_CONFIG:
            tf = st.timeframes.get(period_min)
            if tf is None:
                tf = _TFState()
                st.timeframes[period_min] = tf

            bs = _bar_start(ts, period_min)

            if tf.current_bar_start is None:
                tf.current_bar_start = bs
                tf.current_high = price
                tf.current_low = price
                tf.current_close = price
                continue

            if bs > tf.current_bar_start:
                tf.bars.append(_BarData(
                    close=tf.current_close,
                    high=tf.current_high,
                    low=tf.current_low,
                    timestamp=tf.current_bar_start,
                ))
                tf.current_bar_start = bs
                tf.current_high = price
                tf.current_low = price
                tf.current_close = price
                tf.fired_up = False
                tf.fired_down = False
            else:
                tf.current_high = max(tf.current_high, price)
                tf.current_low = min(tf.current_low, price)
                tf.current_close = price

            if len(tf.bars) < SHORT_PERIOD + 1:
                continue

            closes = [b.close for b in tf.bars]
            closes.append(tf.current_close)

            long_data = closes[-LONG_PERIOD:] if len(closes) >= LONG_PERIOD else closes
            short_data = closes[-SHORT_PERIOD:]

            long_slope, long_intercept, long_stderr = _linreg(long_data)
            short_slope, _, _ = _linreg(short_data)

            if long_stderr <= 0:
                tf.prev_short_slope = short_slope
                continue

            channel_top = (long_slope * (len(long_data) - 1) + long_intercept) + 2 * long_stderr
            channel_bot = (long_slope * (len(long_data) - 1) + long_intercept) - 2 * long_stderr
            channel_mid = (channel_top + channel_bot) / 2.0

            room_up = max(0.0, channel_top - price)
            room_down = max(0.0, price - channel_bot)

            crossed_up = tf.prev_short_slope <= 0 < short_slope
            crossed_down = tf.prev_short_slope >= 0 > short_slope

            if crossed_up and not tf.fired_up and price <= channel_top:
                tf.fired_up = True
                if self._can_fire(up_type, sym, self.COOLDOWN):
                    self._record_fire(up_type, sym)
                    alerts.append(self._make_alert(
                        up_type, current,
                        quality=round(room_up, 2),
                        description=(
                            f"{period_min} minute linear regression up trend "
                            f"(channel ${channel_bot:.2f}-${channel_top:.2f})"
                        ),
                        prev_value=channel_mid,
                        new_value=price,
                        details={
                            "timeframe": period_min,
                            "long_slope": round(long_slope, 6),
                            "short_slope": round(short_slope, 6),
                            "channel_top": round(channel_top, 4),
                            "channel_bot": round(channel_bot, 4),
                            "room_up": round(room_up, 2),
                            "std_error": round(long_stderr, 4),
                        },
                    ))

            if crossed_down and not tf.fired_down and price >= channel_bot:
                tf.fired_down = True
                if self._can_fire(dn_type, sym, self.COOLDOWN):
                    self._record_fire(dn_type, sym)
                    alerts.append(self._make_alert(
                        dn_type, current,
                        quality=round(room_down, 2),
                        description=(
                            f"{period_min} minute linear regression down trend "
                            f"(channel ${channel_bot:.2f}-${channel_top:.2f})"
                        ),
                        prev_value=channel_mid,
                        new_value=price,
                        details={
                            "timeframe": period_min,
                            "long_slope": round(long_slope, 6),
                            "short_slope": round(short_slope, 6),
                            "channel_top": round(channel_top, 4),
                            "channel_bot": round(channel_bot, 4),
                            "room_down": round(room_down, 2),
                            "std_error": round(long_stderr, 4),
                        },
                    ))

            tf.prev_short_slope = short_slope

        return alerts

    def reset_daily(self) -> None:
        super().reset_daily()
        self._states.clear()

    def cleanup_old_symbols(self, active: set) -> int:
        removed = sum(1 for s in list(self._states) if s not in active)
        self._states = {s: v for s, v in self._states.items() if s in active}
        return removed + super().cleanup_old_symbols(active)
