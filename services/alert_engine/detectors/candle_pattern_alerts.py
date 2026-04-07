"""
Candle Pattern Alert Detector.

Families: Doji, Hammer, Hanging Man, Bullish/Bearish Engulfing,
Piercing Pattern, Dark Cloud Cover, Bottoming/Topping Tail,
Narrow Range Buy/Sell Bar, Red/Green Bar Reversal,
1-2-3 Continuation Buy/Sell Signal.

Most patterns are End-of-Candle: evaluated only when a new bar starts
(meaning the previous bar just closed).

1-2-3 Continuation is Single Print: evaluated on every tick once the
two-bar setup is complete.
"""

from datetime import datetime, time, timezone
from typing import Optional, List, Dict, NamedTuple, Tuple
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord

_ET = ZoneInfo("America/New_York")
# Session boundaries in ET — used as fallback when market_session is unavailable
_SESSION_START_ET = time(4, 0)    # Pre-market opens 4:00 AM ET
_SESSION_END_ET = time(20, 0)     # Post-market closes 8:00 PM ET
TREND_BARS = 5


@dataclass
class _Bar:
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0


@dataclass
class _TFSt:
    bars: List[_Bar] = field(default_factory=list)
    bar_start: Optional[datetime] = None
    cur: _Bar = field(default_factory=_Bar)
    first_tick: bool = True


def _bstart(ts: datetime, pm: int) -> datetime:
    m = ts.hour * 60 + ts.minute
    idx = m // pm
    bm = idx * pm
    return ts.replace(hour=bm // 60, minute=bm % 60, second=0, microsecond=0)


def _body(b: _Bar) -> float:
    return abs(b.close - b.open)


def _range(b: _Bar) -> float:
    return b.high - b.low


def _upper_wick(b: _Bar) -> float:
    return b.high - max(b.open, b.close)


def _lower_wick(b: _Bar) -> float:
    return min(b.open, b.close) - b.low


def _is_bullish(b: _Bar) -> bool:
    return b.close > b.open


def _is_bearish(b: _Bar) -> bool:
    return b.close < b.open


def _trend(bars: List[_Bar], n: int) -> float:
    """Return average close change over last n bars. Positive = uptrend."""
    if len(bars) < n + 1:
        return 0.0
    total = 0.0
    for i in range(-n, 0):
        total += bars[i].close - bars[i - 1].close
    return total / n


def _check_doji(b: _Bar) -> bool:
    r = _range(b)
    if r < 0.001:
        return False
    return _body(b) / r <= 0.1


def _check_hammer(b: _Bar, bars: List[_Bar]) -> float:
    r = _range(b)
    if r < 0.01:
        return 0.0
    body = _body(b)
    uw = _upper_wick(b)
    lw = _lower_wick(b)
    if lw < body * 1.5:
        return 0.0
    if _trend(bars, TREND_BARS) >= 0:
        return 0.0
    body_ratio = max(0, 1.0 - body / r * 3)
    uw_penalty = max(0, 1.0 - uw / r * 5)
    lw_bonus = min(1.0, lw / r * 1.5)
    return min(100.0, (body_ratio * 0.3 + uw_penalty * 0.3 + lw_bonus * 0.4) * 100)


def _check_hanging_man(b: _Bar, bars: List[_Bar]) -> float:
    r = _range(b)
    if r < 0.01:
        return 0.0
    body = _body(b)
    uw = _upper_wick(b)
    lw = _lower_wick(b)
    if lw < body * 1.5:
        return 0.0
    if _trend(bars, TREND_BARS) <= 0:
        return 0.0
    body_ratio = max(0, 1.0 - body / r * 3)
    uw_penalty = max(0, 1.0 - uw / r * 5)
    lw_bonus = min(1.0, lw / r * 1.5)
    return min(100.0, (body_ratio * 0.3 + uw_penalty * 0.3 + lw_bonus * 0.4) * 100)


def _check_engulfing_bull(cur: _Bar, prev: _Bar) -> float:
    if not _is_bearish(prev) or not _is_bullish(cur):
        return 0.0
    if cur.open >= prev.close or cur.close <= prev.open:
        return 0.0
    prev_body = _body(prev)
    cur_body = _body(cur)
    if prev_body < 0.001:
        return 0.0
    ratio = cur_body / prev_body
    return min(100.0, max(0.0, (ratio - 1.0) * 50 + 50))


def _check_engulfing_bear(cur: _Bar, prev: _Bar) -> float:
    if not _is_bullish(prev) or not _is_bearish(cur):
        return 0.0
    if cur.open <= prev.close or cur.close >= prev.open:
        return 0.0
    prev_body = _body(prev)
    cur_body = _body(cur)
    if prev_body < 0.001:
        return 0.0
    ratio = cur_body / prev_body
    return min(100.0, max(0.0, (ratio - 1.0) * 50 + 50))


def _check_piercing(cur: _Bar, prev: _Bar) -> float:
    if not _is_bearish(prev) or not _is_bullish(cur):
        return 0.0
    if cur.open >= prev.close:
        return 0.0
    prev_mid = (prev.open + prev.close) / 2
    if cur.close <= prev_mid:
        return 0.0
    prev_body = _body(prev)
    if prev_body < 0.001:
        return 0.0
    penetration = (cur.close - prev_mid) / prev_body
    return min(100.0, max(0.0, penetration * 100 + 30))


def _check_dark_cloud(cur: _Bar, prev: _Bar) -> float:
    if not _is_bullish(prev) or not _is_bearish(cur):
        return 0.0
    if cur.open <= prev.close:
        return 0.0
    prev_mid = (prev.open + prev.close) / 2
    if cur.close >= prev_mid:
        return 0.0
    prev_body = _body(prev)
    if prev_body < 0.001:
        return 0.0
    penetration = (prev_mid - cur.close) / prev_body
    return min(100.0, max(0.0, penetration * 100 + 30))


MIN_PRECEDING = 3
NR_LOOKBACK = 5
NR_THRESHOLD = 0.25
MIN_CONSEC_REVERSAL = 3


def _check_bottoming_tail(b: _Bar, bars: List[_Bar]) -> float:
    """Bottoming tail: small bullish body, long lower wick, after 3+ bearish bars."""
    if not _is_bullish(b):
        return 0.0
    r = _range(b)
    if r < 0.01:
        return 0.0
    lw = _lower_wick(b)
    body = _body(b)
    if lw < body * 1.5:
        return 0.0
    if len(bars) < MIN_PRECEDING:
        return 0.0
    preceding = bars[-MIN_PRECEDING:]
    if not all(_is_bearish(p) for p in preceding):
        return 0.0
    body_ratio = max(0, 1.0 - body / r * 3)
    lw_bonus = min(1.0, lw / r * 1.5)
    uw = _upper_wick(b)
    uw_penalty = max(0, 1.0 - uw / r * 5)
    return min(100.0, (body_ratio * 0.25 + lw_bonus * 0.45 + uw_penalty * 0.3) * 100)


def _check_topping_tail(b: _Bar, bars: List[_Bar]) -> float:
    """Topping tail: small bearish body, long upper wick, after 3+ bullish bars."""
    if not _is_bearish(b):
        return 0.0
    r = _range(b)
    if r < 0.01:
        return 0.0
    uw = _upper_wick(b)
    body = _body(b)
    if uw < body * 1.5:
        return 0.0
    if len(bars) < MIN_PRECEDING:
        return 0.0
    preceding = bars[-MIN_PRECEDING:]
    if not all(_is_bullish(p) for p in preceding):
        return 0.0
    body_ratio = max(0, 1.0 - body / r * 3)
    uw_bonus = min(1.0, uw / r * 1.5)
    lw = _lower_wick(b)
    lw_penalty = max(0, 1.0 - lw / r * 5)
    return min(100.0, (body_ratio * 0.25 + uw_bonus * 0.45 + lw_penalty * 0.3) * 100)


def _check_narrow_range_buy(b: _Bar, bars: List[_Bar]) -> float:
    """Narrow range buy bar: 3+ green bars then a bar < 25% of avg range of past 5."""
    if len(bars) < NR_LOOKBACK:
        return 0.0
    recent = bars[-MIN_PRECEDING:]
    if not all(_is_bullish(c) for c in recent):
        return 0.0
    avg_range = sum(_range(c) for c in bars[-NR_LOOKBACK:]) / NR_LOOKBACK
    if avg_range < 0.001:
        return 0.0
    cur_range = _range(b)
    if cur_range >= avg_range * NR_THRESHOLD:
        return 0.0
    ratio = 1.0 - (cur_range / (avg_range * NR_THRESHOLD)) if avg_range * NR_THRESHOLD > 0 else 1.0
    return min(100.0, max(10.0, ratio * 100))


def _check_narrow_range_sell(b: _Bar, bars: List[_Bar]) -> float:
    """Narrow range sell bar: 3+ red bars then a bar < 25% of avg range of past 5."""
    if len(bars) < NR_LOOKBACK:
        return 0.0
    recent = bars[-MIN_PRECEDING:]
    if not all(_is_bearish(c) for c in recent):
        return 0.0
    avg_range = sum(_range(c) for c in bars[-NR_LOOKBACK:]) / NR_LOOKBACK
    if avg_range < 0.001:
        return 0.0
    cur_range = _range(b)
    if cur_range >= avg_range * NR_THRESHOLD:
        return 0.0
    ratio = 1.0 - (cur_range / (avg_range * NR_THRESHOLD)) if avg_range * NR_THRESHOLD > 0 else 1.0
    return min(100.0, max(10.0, ratio * 100))


def _count_consec_bullish(bars: List[_Bar]) -> int:
    """Count consecutive bullish bars from the end of the list."""
    count = 0
    for b in reversed(bars):
        if _is_bullish(b):
            count += 1
        else:
            break
    return count


def _count_consec_bearish(bars: List[_Bar]) -> int:
    """Count consecutive bearish bars from the end of the list."""
    count = 0
    for b in reversed(bars):
        if _is_bearish(b):
            count += 1
        else:
            break
    return count


_DOJ_CFGS = [
    (5,  AlertType.DOJI_5M),  (10, AlertType.DOJI_10M),
    (15, AlertType.DOJI_15M), (30, AlertType.DOJI_30M),
    (60, AlertType.DOJI_60M),
]

_HMR_CFGS = [
    (2,  AlertType.HAMMER_2M),  (5,  AlertType.HAMMER_5M),
    (10, AlertType.HAMMER_10M), (15, AlertType.HAMMER_15M),
    (30, AlertType.HAMMER_30M), (60, AlertType.HAMMER_60M),
]

_HGM_CFGS = [
    (2,  AlertType.HANGING_MAN_2M),  (5,  AlertType.HANGING_MAN_5M),
    (10, AlertType.HANGING_MAN_10M), (15, AlertType.HANGING_MAN_15M),
    (30, AlertType.HANGING_MAN_30M), (60, AlertType.HANGING_MAN_60M),
]

_NGU_CFGS = [
    (5,  AlertType.ENGULF_BULL_5M),  (10, AlertType.ENGULF_BULL_10M),
    (15, AlertType.ENGULF_BULL_15M), (30, AlertType.ENGULF_BULL_30M),
]

_NGD_CFGS = [
    (5,  AlertType.ENGULF_BEAR_5M),  (10, AlertType.ENGULF_BEAR_10M),
    (15, AlertType.ENGULF_BEAR_15M), (30, AlertType.ENGULF_BEAR_30M),
]

_PP_CFGS = [
    (5,  AlertType.PIERCING_5M),  (10, AlertType.PIERCING_10M),
    (15, AlertType.PIERCING_15M), (30, AlertType.PIERCING_30M),
]

_DCC_CFGS = [
    (5,  AlertType.DARK_CLOUD_5M),  (10, AlertType.DARK_CLOUD_10M),
    (15, AlertType.DARK_CLOUD_15M), (30, AlertType.DARK_CLOUD_30M),
]

_BT_CFGS = [
    (2,  AlertType.BOTTOMING_TAIL_2M),  (5,  AlertType.BOTTOMING_TAIL_5M),
    (10, AlertType.BOTTOMING_TAIL_10M), (15, AlertType.BOTTOMING_TAIL_15M),
    (30, AlertType.BOTTOMING_TAIL_30M), (60, AlertType.BOTTOMING_TAIL_60M),
]

_TT_CFGS = [
    (2,  AlertType.TOPPING_TAIL_2M),  (5,  AlertType.TOPPING_TAIL_5M),
    (10, AlertType.TOPPING_TAIL_10M), (15, AlertType.TOPPING_TAIL_15M),
    (30, AlertType.TOPPING_TAIL_30M), (60, AlertType.TOPPING_TAIL_60M),
]

_NRBB_CFGS = [
    (5,  AlertType.NARROW_RANGE_BUY_5M),  (10, AlertType.NARROW_RANGE_BUY_10M),
    (15, AlertType.NARROW_RANGE_BUY_15M), (30, AlertType.NARROW_RANGE_BUY_30M),
]

_NRSB_CFGS = [
    (5,  AlertType.NARROW_RANGE_SELL_5M),  (10, AlertType.NARROW_RANGE_SELL_10M),
    (15, AlertType.NARROW_RANGE_SELL_15M), (30, AlertType.NARROW_RANGE_SELL_30M),
]

_RBR_CFGS = [
    (2,  AlertType.RED_BAR_REV_2M),  (5,  AlertType.RED_BAR_REV_5M),
    (15, AlertType.RED_BAR_REV_15M), (60, AlertType.RED_BAR_REV_60M),
]

_GBR_CFGS = [
    (2,  AlertType.GREEN_BAR_REV_2M),  (5,  AlertType.GREEN_BAR_REV_5M),
    (15, AlertType.GREEN_BAR_REV_15M), (60, AlertType.GREEN_BAR_REV_60M),
]

_C1U_CFGS = [
    (2,  AlertType.CONT_123_BUY_2M),  (5,  AlertType.CONT_123_BUY_5M),
    (15, AlertType.CONT_123_BUY_15M), (60, AlertType.CONT_123_BUY_60M),
]

_C1D_CFGS = [
    (2,  AlertType.CONT_123_SELL_2M),  (5,  AlertType.CONT_123_SELL_5M),
    (15, AlertType.CONT_123_SELL_15M), (60, AlertType.CONT_123_SELL_60M),
]

ALL_TFS = sorted(set(
    [t for t, _ in _DOJ_CFGS] + [t for t, _ in _HMR_CFGS] +
    [t for t, _ in _NGU_CFGS] + [t for t, _ in _PP_CFGS] +
    [t for t, _ in _BT_CFGS] + [t for t, _ in _NRBB_CFGS] +
    [t for t, _ in _RBR_CFGS] + [t for t, _ in _C1U_CFGS]
))


@dataclass
class _C123St:
    """State for 1-2-3 continuation pattern tracking per symbol+timeframe."""
    bar1: Optional[_Bar] = None
    bar2: Optional[_Bar] = None
    setup_high: float = 0.0
    setup_low: float = float("inf")
    fired_buy: bool = False
    fired_sell: bool = False


class CandlePatternAlertDetector(BaseAlertDetector):

    def __init__(self):
        super().__init__()
        self._st: Dict[str, Dict[int, _TFSt]] = {}
        self._c123: Dict[str, Dict[int, _C123St]] = {}

    def detect(
        self, current: AlertState, previous: Optional[AlertState]
    ) -> List[AlertRecord]:
        out: List[AlertRecord] = []
        if current.price is None or current.price <= 0:
            return out

        sym = current.symbol
        ts = current.timestamp
        # Convert to Eastern Time for bar-boundary calculations (regardless of session)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_et = ts.astimezone(_ET).replace(tzinfo=None)

        # Use EventBus session (authoritative: driven by Polygon + market_session service).
        # Active sessions: PRE_MARKET, MARKET_OPEN, POST_MARKET.
        # If session is unknown/None, fall back to ET time range 4:00–20:00.
        session = current.market_session
        if session == "CLOSED":
            return out
        if session is None:
            if ts_et.time() < _SESSION_START_ET or ts_et.time() >= _SESSION_END_ET:
                return out

        ts = ts_et

        price = current.price
        ss = self._st.setdefault(sym, {})

        for tf_min in ALL_TFS:
            tf = ss.get(tf_min)
            if tf is None:
                tf = _TFSt()
                ss[tf_min] = tf

            bs = _bstart(ts, tf_min)

            if tf.bar_start is None:
                tf.bar_start = bs
                tf.cur = _Bar(price, price, price, price)
                tf.first_tick = True
                continue

            if bs > tf.bar_start:
                tf.bars.append(tf.cur)
                max_keep = max(TREND_BARS, MIN_PRECEDING, NR_LOOKBACK) + 5
                if len(tf.bars) > max_keep:
                    tf.bars = tf.bars[-(max_keep - 2):]

                closed = tf.cur
                prev_bar = tf.bars[-2] if len(tf.bars) >= 2 else None

                self._eval_patterns(
                    sym, tf_min, closed, prev_bar, tf.bars, current, out
                )
                self._update_c123_on_close(sym, tf_min, closed, tf.bars)

                tf.bar_start = bs
                tf.cur = _Bar(price, price, price, price)
                tf.first_tick = True
            else:
                if price > tf.cur.high:
                    tf.cur.high = price
                if price < tf.cur.low:
                    tf.cur.low = price
                tf.cur.close = price
                tf.first_tick = False

            self._eval_c123_tick(sym, tf_min, price, current, out)

        return out

    def _eval_patterns(
        self, sym: str, tf_min: int, closed: _Bar,
        prev_bar: Optional[_Bar], bars: List[_Bar],
        current: AlertState, out: List[AlertRecord]
    ) -> None:
        for t, at in _DOJ_CFGS:
            if t == tf_min and _check_doji(closed):
                out.append(self._make_alert(
                    at, current, quality=0.0,
                    description=f"{t} Minute Doji",
                    details={"tf": t, "open": closed.open, "close": closed.close,
                             "high": closed.high, "low": closed.low}))

        for t, at in _HMR_CFGS:
            if t == tf_min:
                grade = _check_hammer(closed, bars)
                if grade > 0:
                    out.append(self._make_alert(
                        at, current, quality=round(grade, 1),
                        description=f"{t} Minute Hammer (grade {grade:.0f})",
                        details={"tf": t, "grade": round(grade, 1)}))

        for t, at in _HGM_CFGS:
            if t == tf_min:
                grade = _check_hanging_man(closed, bars)
                if grade > 0:
                    out.append(self._make_alert(
                        at, current, quality=round(grade, 1),
                        description=f"{t} Minute Hanging Man (grade {grade:.0f})",
                        details={"tf": t, "grade": round(grade, 1)}))

        if prev_bar is not None:
            for t, at in _NGU_CFGS:
                if t == tf_min:
                    grade = _check_engulfing_bull(closed, prev_bar)
                    if grade > 0:
                        out.append(self._make_alert(
                            at, current, quality=round(grade, 1),
                            description=f"{t} Minute Bullish Engulfing (grade {grade:.0f})",
                            details={"tf": t, "grade": round(grade, 1)}))

            for t, at in _NGD_CFGS:
                if t == tf_min:
                    grade = _check_engulfing_bear(closed, prev_bar)
                    if grade > 0:
                        out.append(self._make_alert(
                            at, current, quality=round(grade, 1),
                            description=f"{t} Minute Bearish Engulfing (grade {grade:.0f})",
                            details={"tf": t, "grade": round(grade, 1)}))

            for t, at in _PP_CFGS:
                if t == tf_min:
                    grade = _check_piercing(closed, prev_bar)
                    if grade > 0:
                        out.append(self._make_alert(
                            at, current, quality=round(grade, 1),
                            description=f"{t} Minute Piercing Pattern (grade {grade:.0f})",
                            details={"tf": t, "grade": round(grade, 1)}))

            for t, at in _DCC_CFGS:
                if t == tf_min:
                    grade = _check_dark_cloud(closed, prev_bar)
                    if grade > 0:
                        out.append(self._make_alert(
                            at, current, quality=round(grade, 1),
                            description=f"{t} Minute Dark Cloud Cover (grade {grade:.0f})",
                            details={"tf": t, "grade": round(grade, 1)}))

        for t, at in _BT_CFGS:
            if t == tf_min:
                grade = _check_bottoming_tail(closed, bars)
                if grade > 0:
                    out.append(self._make_alert(
                        at, current, quality=round(grade, 1),
                        description=f"{t} Minute Bottoming Tail (grade {grade:.0f})",
                        details={"tf": t, "grade": round(grade, 1)}))

        for t, at in _TT_CFGS:
            if t == tf_min:
                grade = _check_topping_tail(closed, bars)
                if grade > 0:
                    out.append(self._make_alert(
                        at, current, quality=round(grade, 1),
                        description=f"{t} Minute Topping Tail (grade {grade:.0f})",
                        details={"tf": t, "grade": round(grade, 1)}))

        preceding = bars[:-1]

        for t, at in _NRBB_CFGS:
            if t == tf_min:
                grade = _check_narrow_range_buy(closed, preceding)
                if grade > 0:
                    out.append(self._make_alert(
                        at, current, quality=round(grade, 1),
                        description=f"{t} Minute Narrow Range Buy Bar (grade {grade:.0f})",
                        details={"tf": t, "grade": round(grade, 1)}))

        for t, at in _NRSB_CFGS:
            if t == tf_min:
                grade = _check_narrow_range_sell(closed, preceding)
                if grade > 0:
                    out.append(self._make_alert(
                        at, current, quality=round(grade, 1),
                        description=f"{t} Minute Narrow Range Sell Bar (grade {grade:.0f})",
                        details={"tf": t, "grade": round(grade, 1)}))
        for t, at in _RBR_CFGS:
            if t == tf_min and _is_bearish(closed):
                consec = _count_consec_bullish(preceding)
                if consec >= MIN_CONSEC_REVERSAL:
                    out.append(self._make_alert(
                        at, current, quality=float(consec),
                        description=f"{t} Minute Red Bar Reversal ({consec} green bars)",
                        details={"tf": t, "consecutive_green": consec}))

        for t, at in _GBR_CFGS:
            if t == tf_min and _is_bullish(closed):
                consec = _count_consec_bearish(preceding)
                if consec >= MIN_CONSEC_REVERSAL:
                    out.append(self._make_alert(
                        at, current, quality=float(consec),
                        description=f"{t} Minute Green Bar Reversal ({consec} red bars)",
                        details={"tf": t, "consecutive_red": consec}))

    def _update_c123_on_close(
        self, sym: str, tf_min: int, closed: _Bar, bars: List[_Bar]
    ) -> None:
        """Track 1-2-3 continuation setup on bar close."""
        cs = self._c123.setdefault(sym, {})
        st = cs.get(tf_min)
        if st is None:
            st = _C123St()
            cs[tf_min] = st

        if _is_bullish(closed) and _body(closed) > 0.001:
            if st.bar1 is not None and _is_bullish(st.bar1):
                if _body(closed) < _body(st.bar1) * 0.8:
                    st.bar2 = closed
                    st.setup_high = max(st.bar1.high, closed.high)
                    st.fired_buy = False
                else:
                    st.bar1 = closed
                    st.bar2 = None
                    st.fired_buy = False
            else:
                st.bar1 = closed
                st.bar2 = None
                st.fired_buy = False

        if _is_bearish(closed) and _body(closed) > 0.001:
            if st.bar1 is not None and _is_bearish(st.bar1):
                if _body(closed) < _body(st.bar1) * 0.8:
                    st.bar2 = closed
                    st.setup_low = min(st.bar1.low, closed.low)
                    st.fired_sell = False
                else:
                    st.bar1 = closed
                    st.bar2 = None
                    st.fired_sell = False
            else:
                st.bar1 = closed
                st.bar2 = None
                st.fired_sell = False

    def _eval_c123_tick(
        self, sym: str, tf_min: int, price: float,
        current: AlertState, out: List[AlertRecord]
    ) -> None:
        """Single-print evaluation for 1-2-3 continuation."""
        cs = self._c123.get(sym)
        if cs is None:
            return
        st = cs.get(tf_min)
        if st is None or st.bar1 is None or st.bar2 is None:
            return

        if _is_bullish(st.bar1) and _is_bullish(st.bar2) and not st.fired_buy:
            if price > st.setup_high:
                for t, at in _C1U_CFGS:
                    if t == tf_min:
                        out.append(self._make_alert(
                            at, current, quality=0.0,
                            description=f"{t} Minute 1-2-3 Continuation Buy Signal",
                            details={"tf": t, "breakout_level": st.setup_high,
                                     "stop_loss": st.bar2.low}))
                        st.fired_buy = True
                        break

        if _is_bearish(st.bar1) and _is_bearish(st.bar2) and not st.fired_sell:
            if price < st.setup_low:
                for t, at in _C1D_CFGS:
                    if t == tf_min:
                        out.append(self._make_alert(
                            at, current, quality=0.0,
                            description=f"{t} Minute 1-2-3 Continuation Sell Signal",
                            details={"tf": t, "breakdown_level": st.setup_low,
                                     "stop_loss": st.bar2.high}))
                        st.fired_sell = True
                        break

    def reset_daily(self) -> None:
        super().reset_daily()
        self._st.clear()
        self._c123.clear()

    def cleanup_old_symbols(self, active: set) -> int:
        rm = sum(1 for s in list(self._st) if s not in active)
        self._st = {s: v for s, v in self._st.items() if s in active}
        self._c123 = {s: v for s, v in self._c123.items() if s in active}
        return rm + super().cleanup_old_symbols(active)
