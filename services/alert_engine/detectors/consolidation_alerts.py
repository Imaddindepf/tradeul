"""
Consolidation / Channel Alert Detector.

[C] Consolidation: stock price changing significantly less than normal.
    TI: quality = Z-score (2-10). Uses historical volatility to determine
    expected range. Reports when actual range is statistically narrow.

[CHBO/CHBD] Channel Breakout/Breakdown: fast, ~1 min, no volume confirmation.
    TI: "attempts to notify the user as quickly as possible". Pays attention
    to order book and precise support/resistance. Quality = Z-score of the
    consolidation pattern that was broken (2=min, 5=tight, 10=best).

[CHBOC/CHBDC] Channel Breakout/Breakdown (confirmed): volume confirmed, ~15 min.
    TI: "transitions directly from consolidating to running state". Requires
    volume + price action. Quality = momentum/vol ratio (1=min, 5+=briskly, 10=top 1%).

[CBO5/CBD5..CBO30/CBD30] Fixed-timeframe consolidation breakout/breakdown.
    TI: "traditional methods of analysis", fixed N-min candlestick timeframe
    (41 periods). Single print can trigger. Quality = $ above/below channel.
    No volume confirmation. Reports additional alerts if price keeps moving.
"""

import math
from typing import Optional, List, Dict

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord


class ConsolidationAlertDetector(BaseAlertDetector):

    MAX_CHG_5MIN = 0.5
    MIN_CHG_1MIN_FAST = 0.3
    MIN_RVOL = 1.0

    CONSOL_MIN_QUALITY = 2
    CONSOL_MAX_QUALITY = 10
    CONSOL_TIGHT_QUALITY = 5

    COOLDOWN_CONFIRMED = 180

    TIMEFRAME_CONFIGS = [
        (5,  "chg_5min",  AlertType.CONSOL_BREAKOUT_5M,  AlertType.CONSOL_BREAKDOWN_5M),
        (10, "chg_10min", AlertType.CONSOL_BREAKOUT_10M, AlertType.CONSOL_BREAKDOWN_10M),
        (15, "chg_15min", AlertType.CONSOL_BREAKOUT_15M, AlertType.CONSOL_BREAKDOWN_15M),
        (30, "chg_30min", AlertType.CONSOL_BREAKOUT_30M, AlertType.CONSOL_BREAKDOWN_30M),
    ]

    COOLDOWN_TF_BREAKOUT = 60

    def __init__(self):
        super().__init__()
        self._consol_state: Dict[str, dict] = {}
        self._tf_last_dollar: Dict[str, Dict[str, float]] = {}

    def detect(self, current: AlertState, previous: Optional[AlertState]) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if not self._has_min_volume(current) or previous is None:
            return alerts

        self._detect_consolidation(current, alerts)
        self._detect_channel_breakout_fast(current, previous, alerts)
        self._detect_channel_breakout_confirmed(current, previous, alerts)
        self._detect_fixed_tf_breakouts(current, previous, alerts)

        return alerts

    def _detect_consolidation(self, current, alerts):
        """[C] Consolidation: price range is statistically narrow.
        TI: Z-score comparing actual range to expected range from volatility.
        Quality 2=min, 5=tight, 10=range is zero."""
        sym = current.symbol
        chg_5 = current.chg_5min
        if chg_5 is None:
            return

        if not self.baseline:
            return
        vol = self.baseline.get_volatility(sym)
        if vol is None or vol.intraday_vol_5m <= 0:
            return

        actual_move = abs(chg_5)
        expected_move = vol.intraday_vol_5m * 100.0

        if expected_move <= 0:
            return

        ratio = actual_move / expected_move
        if ratio >= 0.5:
            if sym in self._consol_state:
                del self._consol_state[sym]
            return

        z_raw = 1.0 - ratio
        quality = round(
            self.CONSOL_MIN_QUALITY +
            z_raw * (self.CONSOL_MAX_QUALITY - self.CONSOL_MIN_QUALITY),
            1,
        )
        quality = max(self.CONSOL_MIN_QUALITY, min(self.CONSOL_MAX_QUALITY, quality))

        st = self._consol_state.get(sym)
        if st and st.get("last_quality", 0) >= quality:
            return

        self._consol_state[sym] = {"last_quality": quality}

        tight = " (tight)" if quality >= self.CONSOL_TIGHT_QUALITY else ""
        desc = (
            f"Consolidation{tight}: moved {actual_move:.2f}% vs "
            f"expected {expected_move:.2f}% over 5 min"
        )

        vol_info = current.volume or 0
        if vol_info:
            desc += f", {vol_info:,} shares"

        alerts.append(self._make_alert(
            AlertType.CONSOLIDATION, current, quality=quality,
            description=desc, prev_value=expected_move, new_value=actual_move,
            details={
                "actual_move_pct": round(actual_move, 4),
                "expected_move_pct": round(expected_move, 4),
                "z_quality": quality,
                "volume": vol_info,
            },
        ))

    def _detect_channel_breakout_fast(self, current, previous, alerts):
        """[CHBO/CHBD] Fast channel breakout/breakdown. ~1 min timescale.
        TI: quality = Z-score of the consolidation pattern being broken.
        Fires when price moves quickly out of a tight range."""
        chg_1 = current.chg_1min
        chg_5 = current.chg_5min
        if chg_1 is None or chg_5 is None:
            return

        prev_5 = previous.chg_5min
        if prev_5 is None:
            return

        was_tight = abs(prev_5) < self.MAX_CHG_5MIN
        if not was_tight:
            return

        sym = current.symbol
        consol = self._consol_state.get(sym)
        consol_quality = consol["last_quality"] if consol else self.CONSOL_MIN_QUALITY

        if chg_1 >= self.MIN_CHG_1MIN_FAST:
            if self._can_fire(AlertType.CHANNEL_BREAKOUT, sym, 300):
                self._record_fire(AlertType.CHANNEL_BREAKOUT, sym)
                alerts.append(self._make_alert(
                    AlertType.CHANNEL_BREAKOUT, current, quality=round(consol_quality, 1),
                    description=f"Channel breakout at ${current.price:.2f} "
                                f"(consolidation quality {consol_quality:.0f})",
                    prev_value=previous.price, new_value=current.price,
                    details={"chg_1min": chg_1, "consol_quality": consol_quality},
                ))

        elif chg_1 <= -self.MIN_CHG_1MIN_FAST:
            if self._can_fire(AlertType.CHANNEL_BREAKDOWN, sym, 300):
                self._record_fire(AlertType.CHANNEL_BREAKDOWN, sym)
                alerts.append(self._make_alert(
                    AlertType.CHANNEL_BREAKDOWN, current, quality=round(consol_quality, 1),
                    description=f"Channel breakdown at ${current.price:.2f} "
                                f"(consolidation quality {consol_quality:.0f})",
                    prev_value=previous.price, new_value=current.price,
                    details={"chg_1min": chg_1, "consol_quality": consol_quality},
                ))

    def _detect_channel_breakout_confirmed(self, current, previous, alerts):
        """[CHBOC/CHBDC] Volume confirmed channel breakout/breakdown.
        TI: transitions from consolidating to running. ~15 min timeframe.
        Quality = momentum/vol ratio (1=min, 5+=briskly, 10=top 1%)."""
        chg_15 = current.chg_15min
        chg_5 = current.chg_5min
        if chg_15 is None or chg_5 is None:
            return

        prev_5 = previous.chg_5min
        if prev_5 is None:
            return

        was_consolidating = abs(prev_5) < self.MAX_CHG_5MIN
        if not was_consolidating:
            return

        sym = current.symbol
        rvol = current.rvol
        has_vol = rvol is not None and rvol >= self.MIN_RVOL
        if not has_vol:
            return

        vol_15m = None
        if self.baseline:
            vb = self.baseline.get_volatility(sym)
            if vb and vb.intraday_vol_5m > 0:
                vol_15m = vb.intraday_vol_5m * math.sqrt(3)
        if not vol_15m or vol_15m <= 0:
            return

        momentum = abs(chg_15 / 100.0)
        quality = momentum / vol_15m
        if quality < 1.0:
            return

        label = "briskly " if quality >= 5.0 else ""
        dollar_move = momentum * current.price

        if chg_15 > 0:
            prev_chg = previous.chg_15min if previous else 0.0
            if prev_chg and prev_chg > 0:
                prev_q = abs(prev_chg / 100.0) / vol_15m
                if prev_q >= 1.0:
                    return
            if self._can_fire(AlertType.CHANNEL_BREAKOUT_CONFIRMED, sym, self.COOLDOWN_CONFIRMED):
                self._record_fire(AlertType.CHANNEL_BREAKOUT_CONFIRMED, sym)
                alerts.append(self._make_alert(
                    AlertType.CHANNEL_BREAKOUT_CONFIRMED, current,
                    quality=round(quality, 2),
                    description=f"Channel breakout {label}${dollar_move:.2f} (+{chg_15:.1f}%)",
                    prev_value=previous.price, new_value=current.price,
                    details={"chg_15min": chg_15, "quality_ratio": round(quality, 2), "rvol": rvol},
                ))

        elif chg_15 < 0:
            prev_chg = previous.chg_15min if previous else 0.0
            if prev_chg and prev_chg < 0:
                prev_q = abs(prev_chg / 100.0) / vol_15m
                if prev_q >= 1.0:
                    return
            if self._can_fire(AlertType.CHANNEL_BREAKDOWN_CONFIRMED, sym, self.COOLDOWN_CONFIRMED):
                self._record_fire(AlertType.CHANNEL_BREAKDOWN_CONFIRMED, sym)
                alerts.append(self._make_alert(
                    AlertType.CHANNEL_BREAKDOWN_CONFIRMED, current,
                    quality=round(quality, 2),
                    description=f"Channel breakdown {label}${dollar_move:.2f} ({chg_15:.1f}%)",
                    prev_value=previous.price, new_value=current.price,
                    details={"chg_15min": chg_15, "quality_ratio": round(quality, 2), "rvol": rvol},
                ))

    def _detect_fixed_tf_breakouts(self, current, previous, alerts):
        """[CBO5..CBO30/CBD5..CBD30] Fixed-timeframe consolidation breakout/breakdown.

        TI: Uses traditional candlestick analysis on a fixed N-min timeframe
        (41 periods). No volume confirmation needed; a single print can trigger.
        Quality = dollars above/below the consolidation channel top/bottom.

        We estimate the channel as the expected N-min range from historical
        volatility. A breakout fires when the actual move exceeds the expected
        range. Additional alerts fire as the price continues to move further
        (each additional $0.10 increment for stocks <$20, $0.25 for others).
        """
        sym = current.symbol
        price = current.price
        if price is None or price <= 0:
            return

        if not self.baseline:
            return
        vb = self.baseline.get_volatility(sym)
        if vb is None or vb.intraday_vol_5m <= 0:
            return

        base_vol = vb.intraday_vol_5m

        for tf_min, chg_attr, up_type, down_type in self.TIMEFRAME_CONFIGS:
            chg = getattr(current, chg_attr, None)
            if chg is None:
                continue

            prev_chg = getattr(previous, chg_attr, None)
            if prev_chg is None:
                continue

            scale = math.sqrt(tf_min / 5.0)
            expected_range_pct = base_vol * scale * 100.0
            if expected_range_pct <= 0:
                continue

            actual_pct = abs(chg)
            if actual_pct <= expected_range_pct:
                key = f"{sym}:{chg_attr}"
                self._tf_last_dollar.pop(key, None)
                continue

            excess_pct = actual_pct - expected_range_pct
            excess_dollars = round(excess_pct / 100.0 * price, 4)
            if excess_dollars < 0.01:
                continue

            key = f"{sym}:{chg_attr}"
            step = 0.10 if price < 20.0 else 0.25
            last_fired = self._tf_last_dollar.get(key, 0.0)

            next_threshold = last_fired + step if last_fired > 0 else 0.0
            if excess_dollars < next_threshold:
                continue

            alert_type = up_type if chg > 0 else down_type
            direction = "above" if chg > 0 else "below"

            if not self._can_fire(alert_type, sym, self.COOLDOWN_TF_BREAKOUT):
                continue

            self._record_fire(alert_type, sym)
            self._tf_last_dollar[key] = excess_dollars

            quality = round(excess_dollars, 2)

            alerts.append(self._make_alert(
                alert_type, current,
                quality=quality,
                description=(
                    f"{tf_min} min consolidation {'breakout' if chg > 0 else 'breakdown'}: "
                    f"${excess_dollars:.2f} {direction} channel"
                ),
                prev_value=expected_range_pct,
                new_value=actual_pct,
                details={
                    "timeframe_min": tf_min,
                    "excess_dollars": excess_dollars,
                    "expected_range_pct": round(expected_range_pct, 4),
                    "actual_pct": round(actual_pct, 4),
                },
            ))

    def reset_daily(self):
        super().reset_daily()
        self._consol_state.clear()
        self._tf_last_dollar.clear()
