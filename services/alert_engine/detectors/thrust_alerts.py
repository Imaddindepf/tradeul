"""
SMA Thrust Alert Detector (Upward / Downward).

[SMAU2/SMAD2]   2-minute upward/downward thrust
[SMAU5/SMAD5]   5-minute upward/downward thrust
[SMAU15/SMAD15] 15-minute upward/downward thrust

TI behavior:
  - 8-period SMA and 20-period SMA both going same direction for
    last 5 consecutive periods => first alert.
  - Re-fires at Fibonacci intervals: 8, 13, 21, 34, 55 periods.
  - Quality = suddenness (0-100). The flatter the 200-period SMA,
    the closer to 100. Most alerts above 90.
  - Custom setting = min suddenness value.
  - End-of-candle alert: evaluated when a new bar closes.
"""

from collections import deque
from datetime import datetime, time
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord


FIRE_LEVELS = [5, 8, 13, 21, 34, 55, 89]
SMA_SHORT = 8
SMA_LONG = 20
SMA_TREND = 200
MAX_BARS = SMA_TREND + 2
MARKET_OPEN = time(9, 30)


@dataclass
class _TFState:
    bars: deque = field(default_factory=lambda: deque(maxlen=MAX_BARS))
    current_bar_start: Optional[datetime] = None
    current_close: float = 0.0
    consecutive_up: int = 0
    consecutive_down: int = 0
    last_fired_up: int = 0
    last_fired_down: int = 0


_TF_CONFIG: List[Tuple[int, AlertType, AlertType]] = [
    (2, AlertType.SMA_THRUST_UP_2M, AlertType.SMA_THRUST_DOWN_2M),
    (5, AlertType.SMA_THRUST_UP_5M, AlertType.SMA_THRUST_DOWN_5M),
    (15, AlertType.SMA_THRUST_UP_15M, AlertType.SMA_THRUST_DOWN_15M),
]


def _sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _bar_start(ts: datetime, period_min: int) -> datetime:
    minutes = ts.hour * 60 + ts.minute
    idx = minutes // period_min
    m = idx * period_min
    return ts.replace(hour=m // 60, minute=m % 60, second=0, microsecond=0)


def _next_fire_level(last_fired: int) -> Optional[int]:
    for lvl in FIRE_LEVELS:
        if lvl > last_fired:
            return lvl
    return None


class ThrustAlertDetector(BaseAlertDetector):

    COOLDOWN = 0

    def __init__(self):
        super().__init__()
        self._states: Dict[str, Dict[int, _TFState]] = {}

    def detect(
        self, current: AlertState, previous: Optional[AlertState]
    ) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if current.price is None or current.price <= 0:
            return alerts
        if not self._has_min_volume(current):
            return alerts

        sym = current.symbol
        ts = current.timestamp
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        if ts.time() < MARKET_OPEN:
            return alerts

        price = current.price
        sym_st = self._states.setdefault(sym, {})

        for period_min, up_type, dn_type in _TF_CONFIG:
            tf = sym_st.get(period_min)
            if tf is None:
                tf = _TFState()
                sym_st[period_min] = tf

            bs = _bar_start(ts, period_min)

            if tf.current_bar_start is None:
                tf.current_bar_start = bs
                tf.current_close = price
                continue

            if bs > tf.current_bar_start:
                tf.bars.append(tf.current_close)
                tf.current_bar_start = bs
                tf.current_close = price
            else:
                tf.current_close = price
                continue

            closes = list(tf.bars)
            if len(closes) < SMA_LONG + 1:
                continue

            sma8_now = _sma(closes, SMA_SHORT)
            sma20_now = _sma(closes, SMA_LONG)
            sma8_prev = _sma(closes[:-1], SMA_SHORT)
            sma20_prev = _sma(closes[:-1], SMA_LONG)

            if None in (sma8_now, sma20_now, sma8_prev, sma20_prev):
                continue

            both_up = sma8_now > sma8_prev and sma20_now > sma20_prev
            both_down = sma8_now < sma8_prev and sma20_now < sma20_prev

            if both_up:
                tf.consecutive_up += 1
                tf.consecutive_down = 0
                tf.last_fired_down = 0
            elif both_down:
                tf.consecutive_down += 1
                tf.consecutive_up = 0
                tf.last_fired_up = 0
            else:
                tf.consecutive_up = 0
                tf.consecutive_down = 0
                tf.last_fired_up = 0
                tf.last_fired_down = 0

            suddenness = self._suddenness(closes)

            if tf.consecutive_up > 0:
                nxt = _next_fire_level(tf.last_fired_up)
                if nxt and tf.consecutive_up >= nxt:
                    tf.last_fired_up = nxt
                    alerts.append(self._make_alert(
                        up_type, current,
                        quality=round(suddenness, 1),
                        description=(
                            f"Upward thrust ({period_min} minute): "
                            f"SMA(8) and SMA(20) both up for "
                            f"{tf.consecutive_up} periods"
                        ),
                        prev_value=round(sma8_prev, 4),
                        new_value=round(sma8_now, 4),
                        details={
                            "timeframe": period_min,
                            "consecutive": tf.consecutive_up,
                            "sma8": round(sma8_now, 4),
                            "sma20": round(sma20_now, 4),
                            "suddenness": round(suddenness, 1),
                            "fire_level": nxt,
                        },
                    ))

            if tf.consecutive_down > 0:
                nxt = _next_fire_level(tf.last_fired_down)
                if nxt and tf.consecutive_down >= nxt:
                    tf.last_fired_down = nxt
                    alerts.append(self._make_alert(
                        dn_type, current,
                        quality=round(suddenness, 1),
                        description=(
                            f"Downward thrust ({period_min} minute): "
                            f"SMA(8) and SMA(20) both down for "
                            f"{tf.consecutive_down} periods"
                        ),
                        prev_value=round(sma8_prev, 4),
                        new_value=round(sma8_now, 4),
                        details={
                            "timeframe": period_min,
                            "consecutive": tf.consecutive_down,
                            "sma8": round(sma8_now, 4),
                            "sma20": round(sma20_now, 4),
                            "suddenness": round(suddenness, 1),
                            "fire_level": nxt,
                        },
                    ))

        return alerts

    def _suddenness(self, closes: List[float]) -> float:
        """TI: how flat is the 200 SMA relative to price range.
        Flat 200 SMA + big price move = high suddenness (near 100)."""
        n = min(len(closes), SMA_TREND)
        if n < 20:
            return 95.0

        window = closes[-n:]
        price_range = max(window) - min(window)
        if price_range <= 0:
            return 100.0

        sma_first = sum(window[:n // 2]) / (n // 2)
        sma_last = sum(window[n // 2:]) / (n - n // 2)
        sma_move = abs(sma_last - sma_first)

        ratio = sma_move / price_range
        return max(0.0, min(100.0, (1.0 - ratio) * 100.0))

    def reset_daily(self) -> None:
        super().reset_daily()
        self._states.clear()

    def cleanup_old_symbols(self, active: set) -> int:
        removed = sum(1 for s in list(self._states) if s not in active)
        self._states = {s: v for s, v in self._states.items() if s in active}
        return removed + super().cleanup_old_symbols(active)
