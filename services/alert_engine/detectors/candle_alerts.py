"""
N-Minute High/Low Detector — Traditional candlestick analysis.

Trade Ideas spec:
  IDH5/IDL5 through IDH60/IDL60.
  "Look at the current candle that is building for a stock, and compare that
   to the previous candle. The first time that the current candle goes above
   the high of the previous candle, we report a new high."
  - Strictly price and time, no volume/spread/volatility filtering.
  - Ignores candles with no volume (bar_engine already handles this).
  - Single print per candle transition (fires once per direction per candle).
  - No custom settings.
  - Quality = 0 (no custom setting, TI shows no quality column).
"""

from typing import Optional, List, Dict, Tuple

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord

_TF_CONFIG: List[Tuple[int, str, str, str, str, AlertType, AlertType]] = [
    # (period, prev_high_attr, prev_low_attr, cur_high_attr, cur_low_attr, high_type, low_type)
    (5, "prev_bar_high_5m", "prev_bar_low_5m", "cur_bar_high_5m", "cur_bar_low_5m",
     AlertType.INTRADAY_HIGH_5M, AlertType.INTRADAY_LOW_5M),
    (10, "prev_bar_high_10m", "prev_bar_low_10m", "cur_bar_high_10m", "cur_bar_low_10m",
     AlertType.INTRADAY_HIGH_10M, AlertType.INTRADAY_LOW_10M),
    (15, "prev_bar_high_15m", "prev_bar_low_15m", "cur_bar_high_15m", "cur_bar_low_15m",
     AlertType.INTRADAY_HIGH_15M, AlertType.INTRADAY_LOW_15M),
    (30, "prev_bar_high_30m", "prev_bar_low_30m", "cur_bar_high_30m", "cur_bar_low_30m",
     AlertType.INTRADAY_HIGH_30M, AlertType.INTRADAY_LOW_30M),
    (60, "prev_bar_high_60m", "prev_bar_low_60m", "cur_bar_high_60m", "cur_bar_low_60m",
     AlertType.INTRADAY_HIGH_60M, AlertType.INTRADAY_LOW_60M),
]


class CandleAlertDetector(BaseAlertDetector):
    """
    Detects N-minute new highs/lows using traditional candlestick comparison.

    Fires once per direction per candle period. Resets when prev_bar changes
    (new candle boundary), allowing the alert to fire again for the next candle.
    """

    def __init__(self):
        super().__init__()
        self._fired_high: Dict[str, Dict[int, float]] = {}
        self._fired_low: Dict[str, Dict[int, float]] = {}

    def detect(self, current: AlertState, previous: Optional[AlertState]) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        sym = current.symbol

        for period, ph_attr, pl_attr, ch_attr, cl_attr, high_type, low_type in _TF_CONFIG:
            prev_high = getattr(current, ph_attr, None)
            prev_low = getattr(current, pl_attr, None)
            cur_high = getattr(current, ch_attr, None)
            cur_low = getattr(current, cl_attr, None)

            if prev_high is None or prev_high <= 0 or cur_high is None:
                continue
            if prev_low is None or prev_low <= 0 or cur_low is None:
                continue

            fired_h = self._fired_high.setdefault(sym, {})
            fired_l = self._fired_low.setdefault(sym, {})

            if cur_high > prev_high:
                last_prev_h = fired_h.get(period)
                if last_prev_h != prev_high:
                    fired_h[period] = prev_high
                    alerts.append(self._make_alert(
                        high_type, current, quality=0.0,
                        description=f"New {period} minute high",
                        prev_value=prev_high, new_value=cur_high,
                        details={"timeframe": period, "prev_candle_high": prev_high,
                                 "cur_candle_high": cur_high},
                    ))

            if cur_low < prev_low:
                last_prev_l = fired_l.get(period)
                if last_prev_l != prev_low:
                    fired_l[period] = prev_low
                    alerts.append(self._make_alert(
                        low_type, current, quality=0.0,
                        description=f"New {period} minute low",
                        prev_value=prev_low, new_value=cur_low,
                        details={"timeframe": period, "prev_candle_low": prev_low,
                                 "cur_candle_low": cur_low},
                    ))

        return alerts

    def reset_daily(self):
        super().reset_daily()
        self._fired_high.clear()
        self._fired_low.clear()
