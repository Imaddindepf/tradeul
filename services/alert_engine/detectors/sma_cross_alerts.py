"""
SMA Cross Alert Detector - All three TI families.

Family 1: 5/8 SMA cross [X5A8_N / X5B8_N] - 7 timeframes
Family 2: 8/20 SMA cross [ECAY_N / ECBY_N] - 3 timeframes
Family 3: 20/200 SMA cross [YCAD_N / YCBD_N] - 3 timeframes

TI: End-of-candle crossover. No custom settings, quality = 0.
"""

from collections import deque
from datetime import datetime, time
from typing import Optional, List, Dict, NamedTuple
from dataclasses import dataclass, field

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord

MARKET_OPEN = time(9, 30)


class _CrossCfg(NamedTuple):
    fast: int
    slow: int
    bar_min: int
    above_type: AlertType
    below_type: AlertType


_CFGS: List[_CrossCfg] = [
    _CrossCfg(5, 8, 1, AlertType.SMA5_ABOVE_SMA8_1M, AlertType.SMA5_BELOW_SMA8_1M),
    _CrossCfg(5, 8, 2, AlertType.SMA5_ABOVE_SMA8_2M, AlertType.SMA5_BELOW_SMA8_2M),
    _CrossCfg(5, 8, 4, AlertType.SMA5_ABOVE_SMA8_4M, AlertType.SMA5_BELOW_SMA8_4M),
    _CrossCfg(5, 8, 5, AlertType.SMA5_ABOVE_SMA8_5M, AlertType.SMA5_BELOW_SMA8_5M),
    _CrossCfg(5, 8, 10, AlertType.SMA5_ABOVE_SMA8_10M, AlertType.SMA5_BELOW_SMA8_10M),
    _CrossCfg(5, 8, 20, AlertType.SMA5_ABOVE_SMA8_20M, AlertType.SMA5_BELOW_SMA8_20M),
    _CrossCfg(5, 8, 30, AlertType.SMA5_ABOVE_SMA8_30M, AlertType.SMA5_BELOW_SMA8_30M),
    _CrossCfg(8, 20, 2, AlertType.SMA8_ABOVE_SMA20_2M, AlertType.SMA8_BELOW_SMA20_2M),
    _CrossCfg(8, 20, 5, AlertType.SMA8_ABOVE_SMA20_5M, AlertType.SMA8_BELOW_SMA20_5M),
    _CrossCfg(8, 20, 15, AlertType.SMA8_ABOVE_SMA20_15M, AlertType.SMA8_BELOW_SMA20_15M),
    _CrossCfg(20, 200, 2, AlertType.SMA20_ABOVE_SMA200_2M, AlertType.SMA20_BELOW_SMA200_2M),
    _CrossCfg(20, 200, 5, AlertType.SMA20_ABOVE_SMA200_5M, AlertType.SMA20_BELOW_SMA200_5M),
    _CrossCfg(20, 200, 15, AlertType.SMA20_ABOVE_SMA200_15M, AlertType.SMA20_BELOW_SMA200_15M),
]


@dataclass
class _BarSt:
    bars: deque
    bar_start: Optional[datetime] = None
    close: float = 0.0
    prev_fast: Optional[float] = None
    prev_slow: Optional[float] = None


def _sma(vals, period: int) -> Optional[float]:
    n = len(vals)
    if n < period:
        return None
    t = 0.0
    for i in range(n - period, n):
        t += vals[i]
    return t / period


def _bar_start(ts: datetime, pm: int) -> datetime:
    m = ts.hour * 60 + ts.minute
    idx = m // pm
    bm = idx * pm
    return ts.replace(hour=bm // 60, minute=bm % 60, second=0, microsecond=0)


class SMACrossAlertDetector(BaseAlertDetector):

    def __init__(self):
        super().__init__()
        self._st: Dict[str, Dict[str, _BarSt]] = {}

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
        if ts.time() < MARKET_OPEN:
            return out

        price = current.price
        ss = self._st.setdefault(sym, {})

        for cfg in _CFGS:
            k = f"{cfg.fast}_{cfg.slow}_{cfg.bar_min}"
            bs = ss.get(k)
            if bs is None:
                bs = _BarSt(bars=deque(maxlen=cfg.slow + 2))
                ss[k] = bs

            bst = _bar_start(ts, cfg.bar_min)

            if bs.bar_start is None:
                bs.bar_start = bst
                bs.close = price
                continue

            if bst > bs.bar_start:
                bs.bars.append(bs.close)
                bs.bar_start = bst
                bs.close = price
            else:
                bs.close = price
                continue

            if len(bs.bars) < cfg.slow:
                continue

            fast = _sma(bs.bars, cfg.fast)
            slow = _sma(bs.bars, cfg.slow)
            if fast is None or slow is None:
                continue

            pf = bs.prev_fast
            ps = bs.prev_slow
            bs.prev_fast = fast
            bs.prev_slow = slow

            if pf is None or ps is None:
                continue

            if pf <= ps and fast > slow:
                out.append(self._make_alert(
                    cfg.above_type, current, quality=0.0,
                    description=(
                        f"{cfg.fast} Crossed Above "
                        f"{cfg.slow} ({cfg.bar_min} Minute)"
                    ),
                    prev_value=round(pf, 4),
                    new_value=round(fast, 4),
                    details={
                        "fast": cfg.fast, "slow": cfg.slow,
                        "tf": cfg.bar_min,
                        "fast_sma": round(fast, 4),
                        "slow_sma": round(slow, 4),
                    },
                ))

            if pf >= ps and fast < slow:
                out.append(self._make_alert(
                    cfg.below_type, current, quality=0.0,
                    description=(
                        f"{cfg.fast} Crossed Below "
                        f"{cfg.slow} ({cfg.bar_min} Minute)"
                    ),
                    prev_value=round(pf, 4),
                    new_value=round(fast, 4),
                    details={
                        "fast": cfg.fast, "slow": cfg.slow,
                        "tf": cfg.bar_min,
                        "fast_sma": round(fast, 4),
                        "slow_sma": round(slow, 4),
                    },
                ))

        return out

    def reset_daily(self) -> None:
        super().reset_daily()
        self._st.clear()

    def cleanup_old_symbols(self, active: set) -> int:
        rm = sum(1 for s in list(self._st) if s not in active)
        self._st = {s: v for s, v in self._st.items() if s in active}
        return rm + super().cleanup_old_symbols(active)
