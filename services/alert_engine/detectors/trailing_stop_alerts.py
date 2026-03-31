"""
Trailing Stop Alert Detector.

[TSPU] Trailing stop, % up:   price moves up from local low.
       First alert at 0.5% from low, re-fire every 0.25%.
[TSPD] Trailing stop, % down: price moves down from local high.
       First alert at 0.5% from high, re-fire every 0.25%.
[TSSU] Trailing stop, volatility up:   same as TSPU but scaled by volatility.
       One "bar" = typical 15-min bar move. First at 1 bar, re-fire every 0.5 bar.
[TSSD] Trailing stop, volatility down: same as TSPD but scaled by volatility.
       First at 1 bar, re-fire every 0.5 bar.

TI behavior:
  - Any single print can serve as the turning point (no volume confirmation).
  - Turning point resets when price makes a new extreme in the opposite direction.
  - Quality = % move from turning point (TSPU/TSPD) or bars from turning point (TSSU/TSSD).
  - Custom setting = period multiplier. E.g. filter=2 means alerts at 2%, 4%, 6%...
    The server generates at default granularity; the websocket_server filters by quality >= aq.
"""

from typing import Optional, List, Dict
from dataclasses import dataclass, field

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord


PCT_INITIAL_THRESHOLD = 0.5   # 0.5% first trigger
PCT_STEP = 0.25               # 0.25% re-fire step
VOL_INITIAL_BARS = 1.0        # 1 bar first trigger
VOL_STEP_BARS = 0.5           # 0.5 bar re-fire step


@dataclass
class _SymbolState:
    """Per-symbol trailing stop tracking."""
    local_high: float = 0.0
    local_low: float = float("inf")
    last_pct_up_level: int = 0     # last fired level for TSPU
    last_pct_down_level: int = 0   # last fired level for TSPD
    last_vol_up_level: int = 0     # last fired level for TSSU
    last_vol_down_level: int = 0   # last fired level for TSSD


class TrailingStopAlertDetector(BaseAlertDetector):

    def __init__(self):
        super().__init__()
        self._states: Dict[str, _SymbolState] = {}

    # ── public interface ─────────────────────────────────────────────

    def detect(
        self, current: AlertState, previous: Optional[AlertState]
    ) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if current.price is None or current.price <= 0:
            return alerts

        sym = current.symbol
        price = current.price
        st = self._states.get(sym)

        if st is None:
            st = _SymbolState(local_high=price, local_low=price)
            self._states[sym] = st
            return alerts

        if price > st.local_high:
            st.local_high = price
            st.last_pct_down_level = 0
            st.last_vol_down_level = 0

        if price < st.local_low:
            st.local_low = price
            st.last_pct_up_level = 0
            st.last_vol_up_level = 0

        self._check_pct_up(current, st, alerts)
        self._check_pct_down(current, st, alerts)
        self._check_vol_up(current, st, alerts)
        self._check_vol_down(current, st, alerts)

        return alerts

    # ── percentage variants ──────────────────────────────────────────

    def _check_pct_up(
        self, cur: AlertState, st: _SymbolState, out: List[AlertRecord]
    ) -> None:
        if st.local_low <= 0:
            return
        pct = ((cur.price - st.local_low) / st.local_low) * 100.0
        if pct < PCT_INITIAL_THRESHOLD:
            return
        level = 1 + int((pct - PCT_INITIAL_THRESHOLD) / PCT_STEP)
        if level <= st.last_pct_up_level:
            return
        st.last_pct_up_level = level
        out.append(self._make_alert(
            AlertType.TRAILING_STOP_PCT_UP, cur,
            quality=round(pct, 2),
            description=f"Trailing stop: +{pct:.2f}% from low ${st.local_low:.2f}",
            prev_value=st.local_low,
            new_value=cur.price,
            details={
                "pct_from_low": round(pct, 2),
                "local_low": round(st.local_low, 4),
                "level": level,
            },
        ))

    def _check_pct_down(
        self, cur: AlertState, st: _SymbolState, out: List[AlertRecord]
    ) -> None:
        if st.local_high <= 0:
            return
        pct = ((st.local_high - cur.price) / st.local_high) * 100.0
        if pct < PCT_INITIAL_THRESHOLD:
            return
        level = 1 + int((pct - PCT_INITIAL_THRESHOLD) / PCT_STEP)
        if level <= st.last_pct_down_level:
            return
        st.last_pct_down_level = level
        out.append(self._make_alert(
            AlertType.TRAILING_STOP_PCT_DOWN, cur,
            quality=round(pct, 2),
            description=f"Trailing stop: -{pct:.2f}% from high ${st.local_high:.2f}",
            prev_value=st.local_high,
            new_value=cur.price,
            details={
                "pct_from_high": round(pct, 2),
                "local_high": round(st.local_high, 4),
                "level": level,
            },
        ))

    # ── volatility variants ──────────────────────────────────────────

    def _check_vol_up(
        self, cur: AlertState, st: _SymbolState, out: List[AlertRecord]
    ) -> None:
        if st.local_low <= 0:
            return
        bar = self._bar_size(cur.symbol, st)
        if bar is None or bar <= 0:
            return
        dollar_move = cur.price - st.local_low
        bars = dollar_move / bar
        if bars < VOL_INITIAL_BARS:
            return
        level = 1 + int((bars - VOL_INITIAL_BARS) / VOL_STEP_BARS)
        if level <= st.last_vol_up_level:
            return
        st.last_vol_up_level = level
        out.append(self._make_alert(
            AlertType.TRAILING_STOP_VOL_UP, cur,
            quality=round(bars, 2),
            description=(
                f"Trailing stop: +{bars:.1f} vol bars from low "
                f"${st.local_low:.2f} (bar=${bar:.4f})"
            ),
            prev_value=st.local_low,
            new_value=cur.price,
            details={
                "bars_from_low": round(bars, 2),
                "local_low": round(st.local_low, 4),
                "bar_size": round(bar, 4),
                "level": level,
            },
        ))

    def _check_vol_down(
        self, cur: AlertState, st: _SymbolState, out: List[AlertRecord]
    ) -> None:
        if st.local_high <= 0:
            return
        bar = self._bar_size(cur.symbol, st)
        if bar is None or bar <= 0:
            return
        dollar_move = st.local_high - cur.price
        bars = dollar_move / bar
        if bars < VOL_INITIAL_BARS:
            return
        level = 1 + int((bars - VOL_INITIAL_BARS) / VOL_STEP_BARS)
        if level <= st.last_vol_down_level:
            return
        st.last_vol_down_level = level
        out.append(self._make_alert(
            AlertType.TRAILING_STOP_VOL_DOWN, cur,
            quality=round(bars, 2),
            description=(
                f"Trailing stop: -{bars:.1f} vol bars from high "
                f"${st.local_high:.2f} (bar=${bar:.4f})"
            ),
            prev_value=st.local_high,
            new_value=cur.price,
            details={
                "bars_from_high": round(bars, 2),
                "local_high": round(st.local_high, 4),
                "bar_size": round(bar, 4),
                "level": level,
            },
        ))

    # ── helpers ───────────────────────────────────────────────────────

    def _bar_size(self, symbol: str, st: _SymbolState) -> Optional[float]:
        """TI 'bar' = typical price move in one 15-min bar.
        intraday_vol_15m is sigma of returns, so bar = sigma * midpoint_price."""
        if not self.baseline:
            return None
        vb = self.baseline.get_volatility(symbol)
        if vb is None or vb.intraday_vol_15m <= 0:
            return None
        mid = (st.local_high + st.local_low) / 2.0
        if mid <= 0:
            return None
        return vb.intraday_vol_15m * mid

    def reset_daily(self) -> None:
        super().reset_daily()
        self._states.clear()

    def cleanup_old_symbols(self, active: set) -> int:
        removed = sum(1 for s in list(self._states) if s not in active)
        self._states = {s: v for s, v in self._states.items() if s in active}
        return removed + super().cleanup_old_symbols(active)
