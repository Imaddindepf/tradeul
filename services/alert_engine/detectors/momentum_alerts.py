"""
Momentum Alert Detector - Running Up/Down, % Change, Std Dev Breakout.

Trade Ideas behavior:
  - RUN "Running Up Now": ~1 min chart, no confirmation, single print trigger.
    Quality = size of the move in dollars. User filters by min dollar move.
  - RU "Running Up": ~1 min, statistically validated, NBBO confirmed.
    Quality = momentum/volatility ratio (1=min, 4=top 1/3, 10=top 1%).
  - RUI "Running Up (intermediate)": ~5 min (proxy for TI's ~25 min of 30s candles).
    Spread-adjusted, NBBO-sensitive. Quality = actual_speed / expected_speed. Min 2x.
  - RUC "Running Up (confirmed)": ~15 min, volume confirmed.
    Quality = momentum/vol ratio. 1.0=min, 5.0+=briskly, 4=top 1/3, 10=top 1%.
  - PUD "% Up for the Day": quality = the actual % change. Integer levels.
  - BBU "Standard Deviation Breakout": quality = number of standard deviations.
"""

import math
from typing import Optional, List

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord


class MomentumAlertDetector(BaseAlertDetector):

    COOLDOWN_RUNNING_NOW = 120
    COOLDOWN_RUNNING = 120
    COOLDOWN_RUNNING_INTERMEDIATE = 120
    COOLDOWN_RUNNING_CONFIRMED = 180

    RUN_MIN_CHG_1MIN = 0.2
    RUI_MIN_QUALITY = 2.0
    MIN_MOMENTUM_VOLUME = 20_000

    def __init__(self):
        super().__init__()
        self._pud_fired: dict = {}
        self._pdd_fired: dict = {}
        self._bbu_fired: dict = {}
        self._bbd_fired: dict = {}

    def detect(self, current: AlertState, previous: Optional[AlertState]) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if not self._has_min_volume(current):
            return alerts

        self._detect_running_now(current, previous, alerts)
        self._detect_running_sustained(current, previous, alerts)
        self._detect_running_intermediate(current, previous, alerts)
        self._detect_running_confirmed(current, previous, alerts)
        self._detect_percent_change(current, previous, alerts)
        self._detect_std_dev(current, previous, alerts)

        return alerts

    def _detect_running_now(self, current, previous, alerts):
        """RUN/RDN: ~1 min timeframe, no confirmation, single print can trigger.
        Quality = size of the move in dollars."""
        sym = current.symbol
        chg_1 = current.chg_1min
        if chg_1 is None or current.volume < self.MIN_MOMENTUM_VOLUME:
            return

        price = current.price
        dollar_move = abs(chg_1 / 100.0) * price

        if chg_1 >= self.RUN_MIN_CHG_1MIN:
            prev_chg = previous.chg_1min if previous else 0.0
            if prev_chg is None or prev_chg < self.RUN_MIN_CHG_1MIN:
                if self._can_fire(AlertType.RUNNING_UP_NOW, sym, self.COOLDOWN_RUNNING_NOW):
                    self._record_fire(AlertType.RUNNING_UP_NOW, sym)
                    alerts.append(self._make_alert(
                        AlertType.RUNNING_UP_NOW, current, quality=round(dollar_move, 2),
                        description=f"Running up now ${dollar_move:.2f} (+{chg_1:.1f}%)",
                        prev_value=prev_chg, new_value=chg_1,
                        details={"chg_1min": chg_1, "dollar_move": round(dollar_move, 2)},
                    ))

        if chg_1 <= -self.RUN_MIN_CHG_1MIN:
            prev_chg = previous.chg_1min if previous else 0.0
            if prev_chg is None or prev_chg > -self.RUN_MIN_CHG_1MIN:
                if self._can_fire(AlertType.RUNNING_DOWN_NOW, sym, self.COOLDOWN_RUNNING_NOW):
                    self._record_fire(AlertType.RUNNING_DOWN_NOW, sym)
                    alerts.append(self._make_alert(
                        AlertType.RUNNING_DOWN_NOW, current, quality=round(dollar_move, 2),
                        description=f"Running down now ${dollar_move:.2f} ({chg_1:.1f}%)",
                        prev_value=prev_chg, new_value=chg_1,
                        details={"chg_1min": chg_1, "dollar_move": round(dollar_move, 2)},
                    ))

    def _detect_running_sustained(self, current, previous, alerts):
        """RU/RD: ~1 min timeframe, statistically validated, NBBO confirmed.
        Quality = momentum/volatility ratio (1=min, 4=top 1/3, 10=top 1%)."""
        sym = current.symbol
        chg_1 = current.chg_1min
        if chg_1 is None:
            return

        vol_1m = None
        if self.baseline:
            vb = self.baseline.get_volatility(sym)
            if vb and vb.intraday_vol_5m > 0:
                vol_1m = vb.intraday_vol_5m / math.sqrt(5)
        if not vol_1m or vol_1m <= 0:
            return

        momentum = abs(chg_1 / 100.0)
        quality = momentum / vol_1m
        if quality < 1.0:
            return

        price = current.price
        dollar_move = momentum * price
        prev_chg = previous.chg_1min if previous else 0.0

        if chg_1 > 0:
            if prev_chg is not None and prev_chg > 0:
                prev_q = abs(prev_chg / 100.0) / vol_1m
                if prev_q >= 1.0:
                    return
            if self._can_fire(AlertType.RUNNING_UP, sym, self.COOLDOWN_RUNNING):
                self._record_fire(AlertType.RUNNING_UP, sym)
                alerts.append(self._make_alert(
                    AlertType.RUNNING_UP, current, quality=round(quality, 2),
                    description=f"Running up ${dollar_move:.2f} (+{chg_1:.1f}%)",
                    prev_value=prev_chg, new_value=chg_1,
                    details={"chg_1min": chg_1, "quality_ratio": round(quality, 2)},
                ))

        elif chg_1 < 0:
            if prev_chg is not None and prev_chg < 0:
                prev_q = abs(prev_chg / 100.0) / vol_1m
                if prev_q >= 1.0:
                    return
            if self._can_fire(AlertType.RUNNING_DOWN, sym, self.COOLDOWN_RUNNING):
                self._record_fire(AlertType.RUNNING_DOWN, sym)
                alerts.append(self._make_alert(
                    AlertType.RUNNING_DOWN, current, quality=round(quality, 2),
                    description=f"Running down ${dollar_move:.2f} ({chg_1:.1f}%)",
                    prev_value=prev_chg, new_value=chg_1,
                    details={"chg_1min": chg_1, "quality_ratio": round(quality, 2)},
                ))

    def _detect_running_intermediate(self, current, previous, alerts):
        """RUI/RDI: ~5 min timeframe (proxy for TI's ~25 min of 30s candles).
        Spread-adjusted, NBBO-sensitive. Quality = actual_speed / expected_speed.
        Min 2x expected movement. TI: 30% at 2.4x, 50% at 2.9x, 90% at 6.6x."""
        sym = current.symbol
        chg_5 = current.chg_5min
        if chg_5 is None:
            return

        vol_5m = None
        if self.baseline:
            vb = self.baseline.get_volatility(sym)
            if vb and vb.intraday_vol_5m > 0:
                vol_5m = vb.intraday_vol_5m
        if not vol_5m or vol_5m <= 0:
            return

        momentum = abs(chg_5 / 100.0)
        quality = momentum / vol_5m
        if quality < self.RUI_MIN_QUALITY:
            return

        price = current.price
        dollar_move = momentum * price
        prev_chg = previous.chg_5min if previous else 0.0

        if chg_5 > 0:
            if prev_chg is not None and prev_chg > 0:
                prev_q = abs(prev_chg / 100.0) / vol_5m
                if prev_q >= self.RUI_MIN_QUALITY:
                    return
            if self._can_fire(AlertType.RUNNING_UP_INTERMEDIATE, sym, self.COOLDOWN_RUNNING_INTERMEDIATE):
                self._record_fire(AlertType.RUNNING_UP_INTERMEDIATE, sym)
                alerts.append(self._make_alert(
                    AlertType.RUNNING_UP_INTERMEDIATE, current, quality=round(quality, 1),
                    description=f"Running up ${dollar_move:.2f} in ~5 min (+{chg_5:.1f}%)",
                    prev_value=prev_chg, new_value=chg_5,
                    details={"chg_5min": chg_5, "quality_ratio": round(quality, 1)},
                ))

        elif chg_5 < 0:
            if prev_chg is not None and prev_chg < 0:
                prev_q = abs(prev_chg / 100.0) / vol_5m
                if prev_q >= self.RUI_MIN_QUALITY:
                    return
            if self._can_fire(AlertType.RUNNING_DOWN_INTERMEDIATE, sym, self.COOLDOWN_RUNNING_INTERMEDIATE):
                self._record_fire(AlertType.RUNNING_DOWN_INTERMEDIATE, sym)
                alerts.append(self._make_alert(
                    AlertType.RUNNING_DOWN_INTERMEDIATE, current, quality=round(quality, 1),
                    description=f"Running down ${dollar_move:.2f} in ~5 min ({chg_5:.1f}%)",
                    prev_value=prev_chg, new_value=chg_5,
                    details={"chg_5min": chg_5, "quality_ratio": round(quality, 1)},
                ))

    def _detect_running_confirmed(self, current, previous, alerts):
        """RUC/RDC: ~15 min timeframe, volume confirmed. Quality = momentum/vol ratio.
        TI: 1.0=min, 5.0+=briskly, 4=top 1/3, 10=top 1%."""
        sym = current.symbol
        chg_15 = current.chg_15min
        if chg_15 is None:
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

        price = current.price
        dollar_move = momentum * price
        prev_chg = previous.chg_15min if previous else 0.0
        label = "briskly " if quality >= 5.0 else ""

        if chg_15 > 0:
            if prev_chg is not None and prev_chg > 0:
                prev_q = abs(prev_chg / 100.0) / vol_15m
                if prev_q >= 1.0:
                    return
            if self._can_fire(AlertType.RUNNING_UP_CONFIRMED, sym, self.COOLDOWN_RUNNING_CONFIRMED):
                self._record_fire(AlertType.RUNNING_UP_CONFIRMED, sym)
                alerts.append(self._make_alert(
                    AlertType.RUNNING_UP_CONFIRMED, current, quality=round(quality, 2),
                    description=f"Running up {label}${dollar_move:.2f} (+{chg_15:.1f}%)",
                    prev_value=prev_chg, new_value=chg_15,
                    details={"chg_15min": chg_15, "quality_ratio": round(quality, 2)},
                ))

        elif chg_15 < 0:
            if prev_chg is not None and prev_chg < 0:
                prev_q = abs(prev_chg / 100.0) / vol_15m
                if prev_q >= 1.0:
                    return
            if self._can_fire(AlertType.RUNNING_DOWN_CONFIRMED, sym, self.COOLDOWN_RUNNING_CONFIRMED):
                self._record_fire(AlertType.RUNNING_DOWN_CONFIRMED, sym)
                alerts.append(self._make_alert(
                    AlertType.RUNNING_DOWN_CONFIRMED, current, quality=round(quality, 2),
                    description=f"Running down {label}${dollar_move:.2f} ({chg_15:.1f}%)",
                    prev_value=prev_chg, new_value=chg_15,
                    details={"chg_15min": chg_15, "quality_ratio": round(quality, 2)},
                ))

    def _detect_percent_change(self, current, previous, alerts):
        """PUD/PDD: % up/down for the day.
        TI: reports each integer value (3,4,5,...), once per level per day.
        Min 3%. Based on official prints only. Quality = the % change."""
        sym = current.symbol
        chg = current.change_percent
        if chg is None:
            return

        is_regular = current.market_session in ("REGULAR", "MARKET_HOURS", None)
        if not is_regular:
            return

        if chg >= 3.0:
            level = int(chg)
            fired = self._pud_fired.get(sym, 0)
            if level > fired:
                self._pud_fired[sym] = level
                alerts.append(self._make_alert(
                    AlertType.PERCENT_UP_DAY, current, quality=round(chg, 1),
                    description=f"Up {level}% for the day",
                    prev_value=float(fired) if fired else 0.0, new_value=chg,
                    details={"change_percent": round(chg, 2), "level_crossed": level},
                ))

        if chg <= -3.0:
            level = int(abs(chg))
            fired = self._pdd_fired.get(sym, 0)
            if level > fired:
                self._pdd_fired[sym] = level
                alerts.append(self._make_alert(
                    AlertType.PERCENT_DOWN_DAY, current, quality=round(abs(chg), 1),
                    description=f"Down {level}% for the day",
                    prev_value=float(fired) if fired else 0.0, new_value=chg,
                    details={"change_percent": round(chg, 2), "level_crossed": level},
                ))

    def _detect_std_dev(self, current, previous, alerts):
        """BBU/BBD: price moves N daily standard deviations from prev close.
        TI: uses 1 year of daily vol data, scaled to 1 day. Reports each integer
        sigma level once per day. Min/default = 1 sigma."""
        sym = current.symbol
        price = current.price
        prev_close = current.prev_close
        if not prev_close or prev_close <= 0:
            return

        if not self.baseline:
            return
        vol = self.baseline.get_volatility(sym)
        if vol is None or vol.daily_vol_annual <= 0:
            return

        daily_sigma = prev_close * vol.daily_vol_annual / math.sqrt(252)
        if daily_sigma <= 0:
            return

        move = price - prev_close
        sigmas_up = move / daily_sigma if move > 0 else 0
        sigmas_down = -move / daily_sigma if move < 0 else 0

        if sigmas_up >= 1.0:
            level = int(sigmas_up)
            fired = self._bbu_fired.get(sym, 0)
            if level > fired:
                self._bbu_fired[sym] = level
                alerts.append(self._make_alert(
                    AlertType.STD_DEV_BREAKOUT, current, quality=round(sigmas_up, 1),
                    description=f"Std dev breakout: {level} sigma above close",
                    prev_value=prev_close, new_value=price,
                    details={"sigmas": round(sigmas_up, 1), "level": level,
                             "daily_sigma": round(daily_sigma, 4), "prev_close": prev_close},
                ))

        if sigmas_down >= 1.0:
            level = int(sigmas_down)
            fired = self._bbd_fired.get(sym, 0)
            if level > fired:
                self._bbd_fired[sym] = level
                alerts.append(self._make_alert(
                    AlertType.STD_DEV_BREAKDOWN, current, quality=round(sigmas_down, 1),
                    description=f"Std dev breakdown: {level} sigma below close",
                    prev_value=prev_close, new_value=price,
                    details={"sigmas": round(sigmas_down, 1), "level": level,
                             "daily_sigma": round(daily_sigma, 4), "prev_close": prev_close},
                ))

    def reset_daily(self):
        super().reset_daily()
        self._pud_fired.clear()
        self._pdd_fired.clear()
        self._bbu_fired.clear()
        self._bbd_fired.clear()
