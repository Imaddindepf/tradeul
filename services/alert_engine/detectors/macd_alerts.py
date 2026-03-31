"""
MACD Cross Alert Detector - All 5 timeframes.

Standard MACD: EMA(12), EMA(26), Signal = EMA(9) of MACD line.
Two cross types: MACD vs Signal, MACD vs Zero.
5 timeframes: 5, 10, 15, 30, 60 min.

TI: Single Print - reports as soon as value crosses, no candle wait.
No custom settings, quality = 0.

EMAs are updated incrementally O(1) per tick. Seeded with SMA of the
first `period` bars to match Trade Ideas behavior.
"""

from datetime import datetime, time
from typing import Optional, List, Dict, NamedTuple
from dataclasses import dataclass, field

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord

MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
EMA_FAST = 12
EMA_SLOW = 26
EMA_SIGNAL = 9
K_FAST = 2.0 / (EMA_FAST + 1)
K_SLOW = 2.0 / (EMA_SLOW + 1)
K_SIGNAL = 2.0 / (EMA_SIGNAL + 1)
MIN_BARS_SLOW = EMA_SLOW
MIN_BARS_SIGNAL = MIN_BARS_SLOW + EMA_SIGNAL


class _Cfg(NamedTuple):
    bar_min: int
    above_sig: AlertType
    below_sig: AlertType
    above_zero: AlertType
    below_zero: AlertType


_CFGS: List[_Cfg] = [
    _Cfg(5,  AlertType.MACD_ABOVE_SIGNAL_5M,  AlertType.MACD_BELOW_SIGNAL_5M,
             AlertType.MACD_ABOVE_ZERO_5M,     AlertType.MACD_BELOW_ZERO_5M),
    _Cfg(10, AlertType.MACD_ABOVE_SIGNAL_10M, AlertType.MACD_BELOW_SIGNAL_10M,
             AlertType.MACD_ABOVE_ZERO_10M,    AlertType.MACD_BELOW_ZERO_10M),
    _Cfg(15, AlertType.MACD_ABOVE_SIGNAL_15M, AlertType.MACD_BELOW_SIGNAL_15M,
             AlertType.MACD_ABOVE_ZERO_15M,    AlertType.MACD_BELOW_ZERO_15M),
    _Cfg(30, AlertType.MACD_ABOVE_SIGNAL_30M, AlertType.MACD_BELOW_SIGNAL_30M,
             AlertType.MACD_ABOVE_ZERO_30M,    AlertType.MACD_BELOW_ZERO_30M),
    _Cfg(60, AlertType.MACD_ABOVE_SIGNAL_60M, AlertType.MACD_BELOW_SIGNAL_60M,
             AlertType.MACD_ABOVE_ZERO_60M,    AlertType.MACD_BELOW_ZERO_60M),
]


@dataclass
class _TFSt:
    bar_start: Optional[datetime] = None
    bar_close: float = 0.0
    bar_count: int = 0
    closes_buffer: List[float] = field(default_factory=list)
    ema_fast: Optional[float] = None
    ema_slow: Optional[float] = None
    ema_signal: Optional[float] = None
    macd_buffer: List[float] = field(default_factory=list)
    prev_macd: Optional[float] = None
    prev_signal: Optional[float] = None
    fired_as: bool = False
    fired_bs: bool = False
    fired_az: bool = False
    fired_bz: bool = False


def _bstart(ts: datetime, pm: int) -> datetime:
    m = ts.hour * 60 + ts.minute
    idx = m // pm
    bm = idx * pm
    return ts.replace(hour=bm // 60, minute=bm % 60, second=0, microsecond=0)


class MACDAlertDetector(BaseAlertDetector):

    def __init__(self):
        super().__init__()
        self._st: Dict[str, Dict[int, _TFSt]] = {}

    def detect(
        self, current: AlertState, previous: Optional[AlertState]
    ) -> List[AlertRecord]:
        out: List[AlertRecord] = []
        if current.price is None or current.price <= 0:
            return out
        if not self._has_min_volume(current):
            return out

        sym = current.symbol
        ts = current.timestamp
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        if ts.time() < MARKET_OPEN or ts.time() >= MARKET_CLOSE:
            return out

        price = current.price
        ss = self._st.setdefault(sym, {})

        for cfg in _CFGS:
            tf = ss.get(cfg.bar_min)
            if tf is None:
                tf = _TFSt()
                ss[cfg.bar_min] = tf

            bs = _bstart(ts, cfg.bar_min)

            if tf.bar_start is None:
                tf.bar_start = bs
                tf.bar_close = price
                continue

            if bs > tf.bar_start:
                close = tf.bar_close
                tf.bar_count += 1
                tf.bar_start = bs
                tf.bar_close = price
                tf.fired_as = False
                tf.fired_bs = False
                tf.fired_az = False
                tf.fired_bz = False

                self._update_emas_on_close(tf, close)
            else:
                tf.bar_close = price

            if tf.ema_signal is None:
                continue

            m_now = self._live_macd(tf, price)
            s_now = self._live_signal(tf, m_now)

            pm = tf.prev_macd
            ps = tf.prev_signal
            tf.prev_macd = m_now
            tf.prev_signal = s_now

            if pm is None or ps is None:
                continue

            if pm <= ps and m_now > s_now and not tf.fired_as:
                tf.fired_as = True
                out.append(self._make_alert(
                    cfg.above_sig, current, quality=0.0,
                    description=f"{cfg.bar_min} Minute MACD Crossed Above Signal Line",
                    prev_value=round(pm, 6), new_value=round(m_now, 6),
                    details={"tf": cfg.bar_min, "macd": round(m_now, 6),
                             "signal": round(s_now, 6)},
                ))

            if pm >= ps and m_now < s_now and not tf.fired_bs:
                tf.fired_bs = True
                out.append(self._make_alert(
                    cfg.below_sig, current, quality=0.0,
                    description=f"{cfg.bar_min} Minute MACD Crossed Below Signal Line",
                    prev_value=round(pm, 6), new_value=round(m_now, 6),
                    details={"tf": cfg.bar_min, "macd": round(m_now, 6),
                             "signal": round(s_now, 6)},
                ))

            if pm <= 0 and m_now > 0 and not tf.fired_az:
                tf.fired_az = True
                out.append(self._make_alert(
                    cfg.above_zero, current, quality=0.0,
                    description=f"{cfg.bar_min} Minute MACD Crossed Above Zero",
                    prev_value=round(pm, 6), new_value=round(m_now, 6),
                    details={"tf": cfg.bar_min, "macd": round(m_now, 6)},
                ))

            if pm >= 0 and m_now < 0 and not tf.fired_bz:
                tf.fired_bz = True
                out.append(self._make_alert(
                    cfg.below_zero, current, quality=0.0,
                    description=f"{cfg.bar_min} Minute MACD Crossed Below Zero",
                    prev_value=round(pm, 6), new_value=round(m_now, 6),
                    details={"tf": cfg.bar_min, "macd": round(m_now, 6)},
                ))

        return out

    @staticmethod
    def _update_emas_on_close(tf: _TFSt, close: float) -> None:
        """Update EMAs incrementally on bar close. SMA-seeded."""
        if tf.bar_count <= EMA_SLOW:
            tf.closes_buffer.append(close)

        if tf.ema_fast is None:
            if tf.bar_count >= EMA_FAST:
                if tf.bar_count == EMA_FAST:
                    tf.ema_fast = sum(tf.closes_buffer[:EMA_FAST]) / EMA_FAST
                else:
                    tf.ema_fast = close * K_FAST + tf.ema_fast * (1 - K_FAST)
        else:
            tf.ema_fast = close * K_FAST + tf.ema_fast * (1 - K_FAST)

        if tf.ema_slow is None:
            if tf.bar_count >= EMA_SLOW:
                tf.ema_slow = sum(tf.closes_buffer[:EMA_SLOW]) / EMA_SLOW
                tf.closes_buffer = []
        else:
            tf.ema_slow = close * K_SLOW + tf.ema_slow * (1 - K_SLOW)

        if tf.ema_fast is not None and tf.ema_slow is not None:
            macd_val = tf.ema_fast - tf.ema_slow
            tf.macd_buffer.append(macd_val)

            if tf.ema_signal is None:
                if len(tf.macd_buffer) >= EMA_SIGNAL:
                    tf.ema_signal = sum(tf.macd_buffer[:EMA_SIGNAL]) / EMA_SIGNAL
                    tf.macd_buffer = []
            else:
                tf.ema_signal = macd_val * K_SIGNAL + tf.ema_signal * (1 - K_SIGNAL)
                tf.macd_buffer = []

    @staticmethod
    def _live_macd(tf: _TFSt, price: float) -> float:
        """Compute live MACD using current tick price without mutating stored EMAs."""
        ef = price * K_FAST + tf.ema_fast * (1 - K_FAST)
        es = price * K_SLOW + tf.ema_slow * (1 - K_SLOW)
        return ef - es

    @staticmethod
    def _live_signal(tf: _TFSt, live_macd: float) -> float:
        """Compute live signal from live MACD without mutating stored EMA."""
        return live_macd * K_SIGNAL + tf.ema_signal * (1 - K_SIGNAL)

    def reset_daily(self) -> None:
        super().reset_daily()
        self._st.clear()

    def cleanup_old_symbols(self, active: set) -> int:
        rm = sum(1 for s in list(self._st) if s not in active)
        self._st = {s: v for s, v in self._st.items() if s in active}
        return rm + super().cleanup_old_symbols(active)
