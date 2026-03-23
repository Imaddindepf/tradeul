"""
Volume Alert Detector - HRV, SV, VS1, UNOP, BP with ratio-based quality.

Trade Ideas behavior:
  - HRV "High Relative Volume": quality = current_volume / historical_avg_volume
    for the same 5-minute slot. User sets minimum ratio (e.g., 2.0 = only show
    when volume is 2x normal). Default fires at 1.5x (50% above normal).
    Description shows duration of high volume period.
  - SV "Strong Volume": total volume today / avg daily volume. Fires at each
    integer multiple (1x, 2x, 3x...). Once per level per day.
  - VS1 "1 Minute Volume Spike": quality = vol_1min / avg_1min_volume.
  - UNOP "Unusual Number of Prints": quality = trades_z_score.
  - BP "Block Trade": quality = number of shares in the block.

Quality semantics: volume_ratio (float) or min_shares (int).
"""

from typing import Optional, List

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord


class VolumeAlertDetector(BaseAlertDetector):

    COOLDOWN_HRV = 300
    COOLDOWN_VS1 = 120
    COOLDOWN_BP = 60

    HRV_MIN_RATIO = 1.5
    HRV_MIN_VOLUME = 20_000
    VS1_MIN_1MIN_VOL = 5_000
    UNOP_MIN_RATIO = 5.0
    BP_MIN_SHARES = 5_000

    def __init__(self):
        super().__init__()
        self._sv_fired: dict = {}
        self._unop_fired: dict = {}

    def detect(self, current: AlertState, previous: Optional[AlertState]) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if not self._has_min_volume(current):
            return alerts

        self._detect_hrv(current, previous, alerts)
        self._detect_strong_volume(current, alerts)
        self._detect_vs1(current, previous, alerts)
        self._detect_unop(current, previous, alerts)
        self._detect_block_trade(current, previous, alerts)

        return alerts

    def _detect_hrv(self, current, previous, alerts):
        sym = current.symbol
        rvol = current.rvol
        if rvol is None:
            return

        prev_rvol = previous.rvol if previous else 0.0

        if rvol >= self.HRV_MIN_RATIO and current.volume >= self.HRV_MIN_VOLUME:
            if prev_rvol is None or prev_rvol < self.HRV_MIN_RATIO:
                if self._can_fire(AlertType.HIGH_RELATIVE_VOLUME, sym, self.COOLDOWN_HRV):
                    self._record_fire(AlertType.HIGH_RELATIVE_VOLUME, sym)
                    desc = f"High relative volume {rvol:.1f}x"
                    if rvol >= 3.0:
                        desc = f"Very high relative volume {rvol:.1f}x"
                    alerts.append(self._make_alert(
                        AlertType.HIGH_RELATIVE_VOLUME, current, quality=round(rvol, 2),
                        description=desc, prev_value=prev_rvol, new_value=rvol,
                        details={"rvol_ratio": round(rvol, 2), "volume": current.volume},
                    ))

    def _detect_strong_volume(self, current, alerts):
        """SV: total volume today vs avg daily volume. Fires at each integer
        multiple (1x, 2x, 3x...). Once per level per day."""
        sym = current.symbol
        total_vol = current.volume
        if not total_vol or total_vol <= 0:
            return

        avg_daily = 0.0
        if self.baseline:
            vb = self.baseline.get_volatility(sym)
            if vb and vb.avg_daily_volume > 0:
                avg_daily = vb.avg_daily_volume
        if avg_daily <= 0 and hasattr(current, 'avg_daily_volume'):
            avg_daily = current.avg_daily_volume or 0.0
        if avg_daily <= 0:
            return

        ratio = total_vol / avg_daily
        level = int(ratio)
        if level < 1:
            return

        fired = self._sv_fired.get(sym, 0)
        if level <= fired:
            return

        self._sv_fired[sym] = level
        desc = f"Strong volume: {level}x average daily volume ({total_vol:,} shares)"
        alerts.append(self._make_alert(
            AlertType.STRONG_VOLUME, current, quality=round(ratio, 1),
            description=desc, prev_value=avg_daily, new_value=float(total_vol),
            details={"ratio": round(ratio, 1), "level": level,
                     "total_volume": total_vol, "avg_daily_volume": round(avg_daily)},
        ))

    def _detect_vs1(self, current, previous, alerts):
        sym = current.symbol
        vol_1 = current.vol_1min
        vol_5 = current.vol_5min
        if not vol_1 or not vol_5 or vol_5 <= 0:
            return

        avg_1min = vol_5 / 5
        if avg_1min < 100:
            return

        ratio = vol_1 / avg_1min
        if vol_1 >= self.VS1_MIN_1MIN_VOL and ratio >= 3.0:
            prev_vol_1 = previous.vol_1min if previous else None
            if prev_vol_1 and prev_vol_1 > avg_1min * 3:
                return
            if self._can_fire(AlertType.VOLUME_SPIKE_1MIN, sym, self.COOLDOWN_VS1):
                self._record_fire(AlertType.VOLUME_SPIKE_1MIN, sym)
                alerts.append(self._make_alert(
                    AlertType.VOLUME_SPIKE_1MIN, current, quality=round(ratio, 1),
                    description=f"1-min volume spike {ratio:.1f}x ({vol_1:,} shares)",
                    prev_value=avg_1min, new_value=float(vol_1),
                    details={"ratio": round(ratio, 1), "vol_1min": vol_1, "avg_1min": round(avg_1min)},
                ))

    def _detect_unop(self, current, previous, alerts):
        """UNOP: prints at >= 5x normal rate for this time of day.
        Quality = ratio rounded down to nearest multiple of 5.
        Re-fires only if ratio increases to next multiple of 5."""
        sym = current.symbol
        z = current.trades_z_score
        if z is None:
            return

        ratio = z
        if ratio < self.UNOP_MIN_RATIO:
            self._unop_fired.pop(sym, None)
            return

        level = int(ratio // 5) * 5
        if level < 5:
            level = 5

        fired = self._unop_fired.get(sym, 0)
        if level <= fired:
            return

        self._unop_fired[sym] = level
        alerts.append(self._make_alert(
            AlertType.UNUSUAL_PRINTS, current, quality=float(level),
            description=f"Unusual number of prints: {ratio:.0f}x normal rate",
            prev_value=float(fired), new_value=ratio,
            details={"ratio": round(ratio, 1), "level": level},
        ))

    def _detect_block_trade(self, current, previous, alerts):
        """[BP] Block Trade: single trade of 20K+ shares (high vol) or 5K+ (low vol).
        TI: quality = number of shares. Description includes bid/ask context
        and exchange name when available."""
        sym = current.symbol
        trade_size = current.last_trade_size
        if trade_size is None:
            trade_size = current.minute_volume
        if trade_size is None or trade_size < self.BP_MIN_SHARES:
            return

        is_high_vol = False
        if self.baseline:
            vb = self.baseline.get_volatility(sym)
            if vb and vb.avg_daily_volume and vb.avg_daily_volume > 500_000:
                is_high_vol = True
        threshold = 20_000 if is_high_vol else self.BP_MIN_SHARES
        if trade_size < threshold:
            return

        prev_size = None
        if previous:
            prev_size = previous.last_trade_size or previous.minute_volume
        if prev_size and prev_size >= threshold:
            return

        if not self._can_fire(AlertType.BLOCK_TRADE, sym, self.COOLDOWN_BP):
            return

        price = current.price
        bid = current.bid
        ask = current.ask

        context = ""
        if bid is not None and ask is not None and bid > 0 and ask > 0:
            if abs(price - ask) < 0.005:
                context = "At the ask"
            elif abs(price - bid) < 0.005:
                context = "At the bid"
            elif price > ask:
                context = "Trading above"
            elif price < bid:
                context = "Trading below"
            else:
                context = "Trading between"

        exchange = str(current.exchange or "")

        parts = [f"Block trade {trade_size:,} shares @ ${price:.2f}"]
        if context:
            parts.append(context)
        if exchange:
            parts.append(exchange)
        desc = ". ".join(parts)

        self._record_fire(AlertType.BLOCK_TRADE, sym)
        alerts.append(self._make_alert(
            AlertType.BLOCK_TRADE, current, quality=float(trade_size),
            description=desc,
            prev_value=float(prev_size or 0), new_value=float(trade_size),
            details={
                "shares": trade_size,
                "context": context,
                "exchange": exchange,
            },
        ))

    def reset_daily(self):
        super().reset_daily()
        self._sv_fired.clear()
        self._unop_fired.clear()
