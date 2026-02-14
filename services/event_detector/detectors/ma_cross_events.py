"""
Moving Average Cross Detector

Detects when price crosses above or below moving averages (SMA + EMA).

Intraday SMA crosses are aligned with Trade Ideas:
  - SMA(8), SMA(20), SMA(50) from BarEngine 1-min bars
  - SMA(8) cross SMA(20) (golden/death cross intraday)

Legacy EMA crosses kept for backward compatibility:
  - EMA(20), EMA(50) from BarEngine 1-min bars

Daily SMA(200) — future (requires historical daily bars).

Events detected:
  Price vs SMA:
  - CROSSED_ABOVE_SMA8   / CROSSED_BELOW_SMA8    [CAS8/CBS8]
  - CROSSED_ABOVE_SMA20  / CROSSED_BELOW_SMA20   [CAS20/CBS20]
  - CROSSED_ABOVE_SMA50  / CROSSED_BELOW_SMA50   [CAS50/CBS50]
  
  SMA vs SMA:
  - SMA_8_CROSS_ABOVE_20 / SMA_8_CROSS_BELOW_20  [SXU/SXD]
  
  Price vs EMA (legacy):
  - CROSSED_ABOVE_EMA20  / CROSSED_BELOW_EMA20   [CA20/CB20]
  - CROSSED_ABOVE_EMA50  / CROSSED_BELOW_EMA50   [CA50/CB50]
"""

from typing import Optional, List
from models import EventRecord, EventType, TickerState
from detectors.base import BaseEventDetector


class MACrossEventsDetector(BaseEventDetector):
    """Detects price crosses above/below moving averages (SMA primary, EMA legacy)."""

    # ── Price vs MA crosses ──────────────────────────────────────────
    # (EventType above, EventType below, TickerState field name)
    _PRICE_VS_MA = [
        # SMA — primary (Trade Ideas alignment)
        (EventType.CROSSED_ABOVE_SMA8,   EventType.CROSSED_BELOW_SMA8,   "sma_8"),
        (EventType.CROSSED_ABOVE_SMA20,  EventType.CROSSED_BELOW_SMA20,  "sma_20"),
        (EventType.CROSSED_ABOVE_SMA50,  EventType.CROSSED_BELOW_SMA50,  "sma_50"),
        # EMA — legacy (kept for backward compatibility)
        (EventType.CROSSED_ABOVE_EMA20,  EventType.CROSSED_BELOW_EMA20,  "ema_20"),
        (EventType.CROSSED_ABOVE_EMA50,  EventType.CROSSED_BELOW_EMA50,  "ema_50"),
        # Daily SMA(200) — "crossed above/below 200 day moving average"
        # Source: screener:daily_indicators:latest → enriched → daily_sma_200
        (EventType.CROSSED_ABOVE_SMA200, EventType.CROSSED_BELOW_SMA200, "daily_sma_200"),
    ]

    # Cooldowns — longer for higher-period MAs (they cross less often)
    COOLDOWNS = {
        # SMA
        EventType.CROSSED_ABOVE_SMA8: 120,    # 2 min
        EventType.CROSSED_BELOW_SMA8: 120,
        EventType.CROSSED_ABOVE_SMA20: 180,   # 3 min
        EventType.CROSSED_BELOW_SMA20: 180,
        EventType.CROSSED_ABOVE_SMA50: 300,   # 5 min
        EventType.CROSSED_BELOW_SMA50: 300,
        # SMA vs SMA
        EventType.SMA_8_CROSS_ABOVE_20: 300,  # 5 min
        EventType.SMA_8_CROSS_BELOW_20: 300,
        # EMA (legacy)
        EventType.CROSSED_ABOVE_EMA20: 180,   # 3 min
        EventType.CROSSED_BELOW_EMA20: 180,
        EventType.CROSSED_ABOVE_EMA50: 300,   # 5 min
        EventType.CROSSED_BELOW_EMA50: 300,
        # Daily SMA200 (future)
        EventType.CROSSED_ABOVE_SMA200: 600,  # 10 min
        EventType.CROSSED_BELOW_SMA200: 600,
    }

    def detect(self, current: TickerState, previous: Optional[TickerState]) -> List[EventRecord]:
        events: List[EventRecord] = []

        if not self._has_min_volume(current):
            return events

        if previous is None:
            return events

        # ── Price vs MA crosses ──────────────────────────────────────
        for et_above, et_below, field in self._PRICE_VS_MA:
            ma_val = getattr(current, field, None)
            if ma_val is None or ma_val <= 0:
                continue

            # Cross ABOVE: previous price was at or below MA, current is above
            if previous.price <= ma_val < current.price:
                if self._can_fire(et_above, current.symbol, self.COOLDOWNS[et_above]):
                    self._record_fire(et_above, current.symbol)
                    events.append(self._make_event(
                        et_above, current,
                        prev_value=ma_val,
                        new_value=current.price,
                        details={"ma_type": field, "ma_value": round(ma_val, 2)},
                    ))

            # Cross BELOW: previous price was at or above MA, current is below
            if previous.price >= ma_val > current.price:
                if self._can_fire(et_below, current.symbol, self.COOLDOWNS[et_below]):
                    self._record_fire(et_below, current.symbol)
                    events.append(self._make_event(
                        et_below, current,
                        prev_value=ma_val,
                        new_value=current.price,
                        details={"ma_type": field, "ma_value": round(ma_val, 2)},
                    ))

        # ── SMA(8) cross SMA(20) — intraday golden/death cross ──────
        sma_8_cur = getattr(current, "sma_8", None)
        sma_20_cur = getattr(current, "sma_20", None)
        sma_8_prev = getattr(previous, "sma_8", None)
        sma_20_prev = getattr(previous, "sma_20", None)

        if all(v is not None and v > 0 for v in (sma_8_cur, sma_20_cur, sma_8_prev, sma_20_prev)):
            # Bullish: SMA(8) crosses above SMA(20)
            if sma_8_prev <= sma_20_prev and sma_8_cur > sma_20_cur:
                et = EventType.SMA_8_CROSS_ABOVE_20
                if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                    self._record_fire(et, current.symbol)
                    events.append(self._make_event(
                        et, current,
                        prev_value=sma_8_prev,
                        new_value=sma_8_cur,
                        details={
                            "sma_8": round(sma_8_cur, 2),
                            "sma_20": round(sma_20_cur, 2),
                            "cross_type": "golden",
                        },
                    ))

            # Bearish: SMA(8) crosses below SMA(20)
            if sma_8_prev >= sma_20_prev and sma_8_cur < sma_20_cur:
                et = EventType.SMA_8_CROSS_BELOW_20
                if self._can_fire(et, current.symbol, self.COOLDOWNS[et]):
                    self._record_fire(et, current.symbol)
                    events.append(self._make_event(
                        et, current,
                        prev_value=sma_8_prev,
                        new_value=sma_8_cur,
                        details={
                            "sma_8": round(sma_8_cur, 2),
                            "sma_20": round(sma_20_cur, 2),
                            "cross_type": "death",
                        },
                    ))

        return events
