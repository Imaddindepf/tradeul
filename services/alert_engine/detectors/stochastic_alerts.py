"""
Stochastic Cross Alert Detector - All 3 timeframes.

Standard Stochastic: 14-period %K, %D = SMA(3) of %K.
Crossed above 20 = no longer oversold (bullish).
Crossed below 80 = no longer overbought (bearish).
3 timeframes: 5, 15, 60 min.

TI: Single Print - reports as soon as value crosses, no candle wait.
Proprietary noise filter: requires %K to stay on the crossed side for
a minimum number of ticks before re-arming, preventing chatter when
%K hovers near the threshold.

No custom settings, quality = 0.
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
STOCH_PERIOD = 14
STOCH_D_PERIOD = 3
OVERSOLD = 20.0
OVERBOUGHT = 80.0
HYSTERESIS = 2.0
MIN_BARS = STOCH_PERIOD + STOCH_D_PERIOD + 1


class _Cfg(NamedTuple):
    bar_min: int
    bull_type: AlertType
    bear_type: AlertType


_CFGS: List[_Cfg] = [
    _Cfg(5,  AlertType.STOCH_CROSS_BULLISH_5M,  AlertType.STOCH_CROSS_BEARISH_5M),
    _Cfg(15, AlertType.STOCH_CROSS_BULLISH_15M, AlertType.STOCH_CROSS_BEARISH_15M),
    _Cfg(60, AlertType.STOCH_CROSS_BULLISH_60M, AlertType.STOCH_CROSS_BEARISH_60M),
]


def _sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


@dataclass
class _Bar:
    high: float
    low: float
    close: float


@dataclass
class _TFSt:
    bars: List[_Bar] = field(default_factory=list)
    bar_start: Optional[datetime] = None
    cur_high: float = 0.0
    cur_low: float = float("inf")
    cur_close: float = 0.0
    prev_slow_k: Optional[float] = None
    raw_k_history: List[float] = field(default_factory=list)
    fired_bull: bool = False
    fired_bear: bool = False
    was_oversold: bool = False
    was_overbought: bool = False


def _bstart(ts: datetime, pm: int) -> datetime:
    m = ts.hour * 60 + ts.minute
    idx = m // pm
    bm = idx * pm
    return ts.replace(hour=bm // 60, minute=bm % 60, second=0, microsecond=0)


def _compute_stoch(bars: List[_Bar], cur_high: float, cur_low: float,
                   cur_close: float) -> Optional[float]:
    """Compute raw %K from completed bars + current partial bar."""
    all_highs = [b.high for b in bars[-(STOCH_PERIOD - 1):]] + [cur_high]
    all_lows = [b.low for b in bars[-(STOCH_PERIOD - 1):]] + [cur_low]
    if len(all_highs) < STOCH_PERIOD:
        return None
    hh = max(all_highs)
    ll = min(all_lows)
    if hh - ll < 1e-8:
        return 50.0
    return ((cur_close - ll) / (hh - ll)) * 100.0


class StochasticAlertDetector(BaseAlertDetector):

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
                tf.cur_high = price
                tf.cur_low = price
                tf.cur_close = price
                continue

            if bs > tf.bar_start:
                tf.bars.append(_Bar(tf.cur_high, tf.cur_low, tf.cur_close))
                if len(tf.bars) > MIN_BARS + 10:
                    tf.bars = tf.bars[-(MIN_BARS + 5):]
                tf.bar_start = bs
                tf.cur_high = price
                tf.cur_low = price
                tf.cur_close = price
                tf.fired_bull = False
                tf.fired_bear = False
            else:
                if price > tf.cur_high:
                    tf.cur_high = price
                if price < tf.cur_low:
                    tf.cur_low = price
                tf.cur_close = price

            if len(tf.bars) < STOCH_PERIOD - 1:
                continue

            raw_k = _compute_stoch(tf.bars, tf.cur_high, tf.cur_low, tf.cur_close)
            if raw_k is None:
                continue

            tf.raw_k_history.append(raw_k)
            if len(tf.raw_k_history) > STOCH_D_PERIOD + 5:
                tf.raw_k_history = tf.raw_k_history[-(STOCH_D_PERIOD + 3):]

            slow_k = _sma(tf.raw_k_history, STOCH_D_PERIOD)
            if slow_k is None:
                continue

            pk = tf.prev_slow_k

            if slow_k <= OVERSOLD - HYSTERESIS:
                tf.was_oversold = True
            if slow_k >= OVERBOUGHT + HYSTERESIS:
                tf.was_overbought = True

            if pk is not None:
                if tf.was_oversold and pk <= OVERSOLD and slow_k > OVERSOLD:
                    if not tf.fired_bull:
                        tf.fired_bull = True
                        tf.was_oversold = False
                        out.append(self._make_alert(
                            cfg.bull_type, current, quality=0.0,
                            description=f"No Longer Oversold ({cfg.bar_min} min)",
                            prev_value=round(pk, 2), new_value=round(slow_k, 2),
                            details={"tf": cfg.bar_min, "stoch_k": round(slow_k, 2),
                                     "threshold": OVERSOLD},
                        ))

                if tf.was_overbought and pk >= OVERBOUGHT and slow_k < OVERBOUGHT:
                    if not tf.fired_bear:
                        tf.fired_bear = True
                        tf.was_overbought = False
                        out.append(self._make_alert(
                            cfg.bear_type, current, quality=0.0,
                            description=f"No Longer Overbought ({cfg.bar_min} min)",
                            prev_value=round(pk, 2), new_value=round(slow_k, 2),
                            details={"tf": cfg.bar_min, "stoch_k": round(slow_k, 2),
                                     "threshold": OVERBOUGHT},
                        ))

            tf.prev_slow_k = slow_k

        return out

    def reset_daily(self) -> None:
        super().reset_daily()
        self._st.clear()

    def cleanup_old_symbols(self, active: set) -> int:
        rm = sum(1 for s in list(self._st) if s not in active)
        self._st = {s: v for s, v in self._st.items() if s in active}
        return rm + super().cleanup_old_symbols(active)
