"""
Price Alert Detector - New Highs/Lows with lookback-based quality.

Trade Ideas spec coverage:
  NHP/NLP:   quality = lookback_days (0-366). Regular hours only. Reset daily.
  NHPF/NLPF: filtered (rate-limited by volatility). Same quality as NHP/NLP.
  NHA/NLB:   quality = lookback_days. Custom = min shares. Blackout 30s/60s open.
  NHAF/NLBF: filtered NHA/NLB with rate-limiting.
  NHB/NLA:   bid high / ask low. Quality = shares (NHB) / lookback (NLA). Blackout.
  NHBF/NLAF: filtered NHB/NLA with rate-limiting.
  HPRE/LPRE: pre-market only highs/lows. Quality = lookback_days.
  CDHR/CDLS: crosses previous day's high/low.
"""

from datetime import time as dtime
from typing import Optional, List, Dict, Tuple

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState, DailyExtreme
from models.alert_record import AlertRecord

MARKET_OPEN = dtime(9, 30, 0)
BLACKOUT_START = dtime(9, 29, 30)
BLACKOUT_END = dtime(9, 31, 0)


class PriceAlertDetector(BaseAlertDetector):

    COOLDOWN_NEW_EXTREME = 30
    FILTERED_BASE_COOLDOWN = 60
    FILTERED_MIN_COOLDOWN = 10

    def __init__(self):
        super().__init__()
        self._tracked_highs: Dict[str, float] = {}
        self._tracked_lows: Dict[str, float] = {}
        self._tracked_ask_highs: Dict[str, float] = {}
        self._tracked_bid_lows: Dict[str, float] = {}
        self._tracked_bid_highs: Dict[str, float] = {}
        self._tracked_ask_lows: Dict[str, float] = {}
        self._tracked_pre_highs: Dict[str, float] = {}
        self._tracked_pre_lows: Dict[str, float] = {}
        self._tracked_post_highs: Dict[str, float] = {}
        self._tracked_post_lows: Dict[str, float] = {}
        self._last_filtered_price: Dict[str, float] = {}
        self._cdhr_last_lookback: Dict[str, int] = {}
        self._cdls_last_lookback: Dict[str, int] = {}

    def detect(self, current: AlertState, previous: Optional[AlertState]) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if not self._has_min_volume(current):
            return alerts

        is_regular = current.market_session in ("REGULAR", "MARKET_HOURS", "MARKET_OPEN", None)
        is_pre = current.market_session in ("PRE_MARKET", "PREMARKET", "PRE")

        if is_regular:
            self._detect_new_high(current, previous, alerts)
            self._detect_new_low(current, previous, alerts)
            self._detect_new_high_ask(current, previous, alerts)
            self._detect_new_low_bid(current, previous, alerts)
            self._detect_new_high_bid(current, previous, alerts)
            self._detect_new_low_ask(current, previous, alerts)
            self._detect_crossed_daily_highs(current, alerts)
            self._detect_crossed_daily_lows(current, alerts)

        if is_pre:
            self._detect_pre_market_high(current, previous, alerts)
            self._detect_pre_market_low(current, previous, alerts)

        is_post = current.market_session in ("POST_MARKET", "POSTMARKET", "POST")
        if is_post:
            self._detect_post_market_high(current, previous, alerts)
            self._detect_post_market_low(current, previous, alerts)

        return alerts

    def _detect_new_high(self, current, previous, alerts):
        sym = current.symbol
        price = current.price
        prev_tracked = self._tracked_highs.get(sym)
        if current.intraday_high is not None:
            self._tracked_highs[sym] = current.intraday_high
        if prev_tracked is None or price <= prev_tracked:
            return
        self._tracked_highs[sym] = price

        lookback, resistance_day, resistance_price = self._compute_lookback_high(sym, price)

        if self._can_fire(AlertType.NEW_HIGH, sym, self.COOLDOWN_NEW_EXTREME):
            self._record_fire(AlertType.NEW_HIGH, sym)
            desc = self._build_high_description(price, lookback, resistance_day, resistance_price)
            alerts.append(self._make_alert(
                AlertType.NEW_HIGH, current, quality=float(lookback),
                description=desc, prev_value=prev_tracked, new_value=price,
                details={"lookback_days": lookback,
                         "resistance_date": resistance_day,
                         "resistance_price": resistance_price},
            ))

        cd = self._filtered_cooldown(sym, price)
        if self._can_fire(AlertType.NEW_HIGH_FILTERED, sym, cd):
            self._record_fire(AlertType.NEW_HIGH_FILTERED, sym)
            self._last_filtered_price[f"{sym}:H"] = price
            desc = self._build_high_description(price, lookback, resistance_day, resistance_price)
            alerts.append(self._make_alert(
                AlertType.NEW_HIGH_FILTERED, current, quality=float(lookback),
                description=desc,
                prev_value=prev_tracked, new_value=price,
                details={"lookback_days": lookback,
                         "resistance_date": resistance_day,
                         "resistance_price": resistance_price},
            ))

    def _detect_new_low(self, current, previous, alerts):
        sym = current.symbol
        price = current.price
        prev_tracked = self._tracked_lows.get(sym)
        if current.intraday_low is not None:
            self._tracked_lows[sym] = current.intraday_low
        if prev_tracked is None or price >= prev_tracked:
            return
        self._tracked_lows[sym] = price

        lookback, support_day, support_price = self._compute_lookback_low(sym, price)

        if self._can_fire(AlertType.NEW_LOW, sym, self.COOLDOWN_NEW_EXTREME):
            self._record_fire(AlertType.NEW_LOW, sym)
            desc = self._build_low_description(price, lookback, support_day, support_price)
            alerts.append(self._make_alert(
                AlertType.NEW_LOW, current, quality=float(lookback),
                description=desc, prev_value=prev_tracked, new_value=price,
                details={"lookback_days": lookback,
                         "support_date": support_day,
                         "support_price": support_price},
            ))

        cd = self._filtered_cooldown(sym, price)
        if self._can_fire(AlertType.NEW_LOW_FILTERED, sym, cd):
            self._record_fire(AlertType.NEW_LOW_FILTERED, sym)
            self._last_filtered_price[f"{sym}:L"] = price
            desc = self._build_low_description(price, lookback, support_day, support_price)
            alerts.append(self._make_alert(
                AlertType.NEW_LOW_FILTERED, current, quality=float(lookback),
                description=desc,
                prev_value=prev_tracked, new_value=price,
                details={"lookback_days": lookback,
                         "support_date": support_day,
                         "support_price": support_price},
            ))

    @staticmethod
    def _in_open_blackout(ts) -> bool:
        """TI: NHA/NLB are never reported 30s before or 60s after the open."""
        if ts is None:
            return False
        t = ts.time() if hasattr(ts, 'time') else ts
        return BLACKOUT_START <= t <= BLACKOUT_END

    def _detect_new_high_ask(self, current, previous, alerts):
        sym = current.symbol
        ask = current.ask
        if ask is None or ask <= 0:
            return
        if self._in_open_blackout(current.timestamp):
            return
        prev_tracked = self._tracked_ask_highs.get(sym)
        self._tracked_ask_highs[sym] = max(self._tracked_ask_highs.get(sym, 0), ask)
        if prev_tracked is None or ask <= prev_tracked:
            return

        lookback, res_day, res_price = self._compute_lookback_high(sym, ask)
        ask_size = current.ask_size or 0

        if self._can_fire(AlertType.NEW_HIGH_ASK, sym, self.COOLDOWN_NEW_EXTREME):
            self._record_fire(AlertType.NEW_HIGH_ASK, sym)
            desc = f"New high ask ${ask:.2f}"
            if lookback > 0:
                desc += f" ({lookback}-day)"
            if res_price:
                desc += f", resistance ${res_price:.2f}"
            if ask_size > 0:
                desc += f", {ask_size:,} shares on ask"
            alerts.append(self._make_alert(
                AlertType.NEW_HIGH_ASK, current, quality=float(lookback),
                description=desc, prev_value=prev_tracked, new_value=ask,
                details={"lookback_days": lookback, "ask": ask,
                         "ask_size": ask_size},
            ))

        cd = self._filtered_cooldown(sym, ask)
        if self._can_fire(AlertType.NEW_HIGH_ASK_FILTERED, sym, cd):
            self._record_fire(AlertType.NEW_HIGH_ASK_FILTERED, sym)
            self._last_filtered_price[f"{sym}:HA"] = ask
            desc = f"New high ask ${ask:.2f}"
            if lookback > 0:
                desc += f" ({lookback}-day)"
            if ask_size > 0:
                desc += f", {ask_size:,} shares on ask"
            alerts.append(self._make_alert(
                AlertType.NEW_HIGH_ASK_FILTERED, current, quality=float(lookback),
                description=desc, prev_value=prev_tracked, new_value=ask,
                details={"lookback_days": lookback, "ask": ask,
                         "ask_size": ask_size},
            ))

    def _detect_new_low_bid(self, current, previous, alerts):
        sym = current.symbol
        bid = current.bid
        if bid is None or bid <= 0:
            return
        if self._in_open_blackout(current.timestamp):
            return
        prev_tracked = self._tracked_bid_lows.get(sym)
        if prev_tracked is None:
            self._tracked_bid_lows[sym] = bid
            return
        self._tracked_bid_lows[sym] = min(self._tracked_bid_lows[sym], bid)
        if bid >= prev_tracked:
            return

        lookback, sup_day, sup_price = self._compute_lookback_low(sym, bid)
        bid_size = current.bid_size or 0

        if self._can_fire(AlertType.NEW_LOW_BID, sym, self.COOLDOWN_NEW_EXTREME):
            self._record_fire(AlertType.NEW_LOW_BID, sym)
            desc = f"New low bid ${bid:.2f}"
            if lookback > 0:
                desc += f" ({lookback}-day)"
            if sup_price:
                desc += f", support ${sup_price:.2f}"
            if bid_size > 0:
                desc += f", {bid_size:,} shares on bid"
            alerts.append(self._make_alert(
                AlertType.NEW_LOW_BID, current, quality=float(lookback),
                description=desc, prev_value=prev_tracked, new_value=bid,
                details={"lookback_days": lookback, "bid": bid,
                         "bid_size": bid_size},
            ))

        cd = self._filtered_cooldown(sym, bid)
        if self._can_fire(AlertType.NEW_LOW_BID_FILTERED, sym, cd):
            self._record_fire(AlertType.NEW_LOW_BID_FILTERED, sym)
            self._last_filtered_price[f"{sym}:LB"] = bid
            desc = f"New low bid ${bid:.2f}"
            if lookback > 0:
                desc += f" ({lookback}-day)"
            if bid_size > 0:
                desc += f", {bid_size:,} shares on bid"
            alerts.append(self._make_alert(
                AlertType.NEW_LOW_BID_FILTERED, current, quality=float(lookback),
                description=desc, prev_value=prev_tracked, new_value=bid,
                details={"lookback_days": lookback, "bid": bid,
                         "bid_size": bid_size},
            ))

    def _detect_new_high_bid(self, current, previous, alerts):
        """NHB: bid price reaches new intraday high. NHBF: filtered version.
        TI: blackout 30s pre / 60s post open. Quality = shares on bid."""
        sym = current.symbol
        bid = current.bid
        if bid is None or bid <= 0:
            return
        if self._in_open_blackout(current.timestamp):
            return
        prev_tracked = self._tracked_bid_highs.get(sym)
        self._tracked_bid_highs[sym] = max(self._tracked_bid_highs.get(sym, 0), bid)
        if prev_tracked is None or bid <= prev_tracked:
            return

        bid_size = current.bid_size or 0

        if self._can_fire(AlertType.NEW_HIGH_BID, sym, self.COOLDOWN_NEW_EXTREME):
            self._record_fire(AlertType.NEW_HIGH_BID, sym)
            desc = f"New high bid ${bid:.2f}"
            if bid_size > 0:
                desc += f", {bid_size:,} shares on bid"
            alerts.append(self._make_alert(
                AlertType.NEW_HIGH_BID, current, quality=float(bid_size),
                description=desc, prev_value=prev_tracked, new_value=bid,
                details={"bid": bid, "bid_size": bid_size},
            ))

        cd = self._filtered_cooldown(sym, bid)
        if self._can_fire(AlertType.NEW_HIGH_BID_FILTERED, sym, cd):
            self._record_fire(AlertType.NEW_HIGH_BID_FILTERED, sym)
            self._last_filtered_price[f"{sym}:HB"] = bid
            desc = f"New high bid ${bid:.2f}"
            if bid_size > 0:
                desc += f", {bid_size:,} shares on bid"
            alerts.append(self._make_alert(
                AlertType.NEW_HIGH_BID_FILTERED, current, quality=float(bid_size),
                description=desc, prev_value=prev_tracked, new_value=bid,
                details={"bid": bid, "bid_size": bid_size},
            ))

    def _detect_new_low_ask(self, current, previous, alerts):
        """NLA: ask price reaches new intraday low. NLAF: filtered version.
        TI: blackout 30s pre / 60s post open. Quality = lookback days."""
        sym = current.symbol
        ask = current.ask
        if ask is None or ask <= 0:
            return
        if self._in_open_blackout(current.timestamp):
            return
        prev_tracked = self._tracked_ask_lows.get(sym)
        if prev_tracked is None:
            self._tracked_ask_lows[sym] = ask
            return
        self._tracked_ask_lows[sym] = min(self._tracked_ask_lows[sym], ask)
        if ask >= prev_tracked:
            return

        lookback, sup_day, sup_price = self._compute_lookback_low(sym, ask)
        ask_size = current.ask_size or 0

        if self._can_fire(AlertType.NEW_LOW_ASK, sym, self.COOLDOWN_NEW_EXTREME):
            self._record_fire(AlertType.NEW_LOW_ASK, sym)
            desc = f"New low ask ${ask:.2f}"
            if lookback > 0:
                desc += f" ({lookback}-day)"
            if ask_size > 0:
                desc += f", {ask_size:,} shares on ask"
            alerts.append(self._make_alert(
                AlertType.NEW_LOW_ASK, current, quality=float(lookback),
                description=desc, prev_value=prev_tracked, new_value=ask,
                details={"lookback_days": lookback, "ask": ask, "ask_size": ask_size},
            ))

        cd = self._filtered_cooldown(sym, ask)
        if self._can_fire(AlertType.NEW_LOW_ASK_FILTERED, sym, cd):
            self._record_fire(AlertType.NEW_LOW_ASK_FILTERED, sym)
            self._last_filtered_price[f"{sym}:LA"] = ask
            desc = f"New low ask ${ask:.2f}"
            if lookback > 0:
                desc += f" ({lookback}-day)"
            if ask_size > 0:
                desc += f", {ask_size:,} shares on ask"
            alerts.append(self._make_alert(
                AlertType.NEW_LOW_ASK_FILTERED, current, quality=float(lookback),
                description=desc, prev_value=prev_tracked, new_value=ask,
                details={"lookback_days": lookback, "ask": ask, "ask_size": ask_size},
            ))

    def _detect_pre_market_high(self, current, previous, alerts):
        """HPRE: new high during pre-market only. Quality = lookback days."""
        sym = current.symbol
        price = current.price
        prev_tracked = self._tracked_pre_highs.get(sym)
        self._tracked_pre_highs[sym] = max(self._tracked_pre_highs.get(sym, 0), price)
        if prev_tracked is None or price <= prev_tracked:
            return

        lookback, res_day, res_price = self._compute_lookback_high(sym, price)

        if self._can_fire(AlertType.PRE_MARKET_HIGH, sym, self.COOLDOWN_NEW_EXTREME):
            self._record_fire(AlertType.PRE_MARKET_HIGH, sym)
            desc = f"Pre-market high ${price:.2f}"
            if lookback > 0:
                desc += f" ({lookback}-day)"
            if res_price:
                desc += f". Resistance {res_day} at ${res_price:.2f}"
            alerts.append(self._make_alert(
                AlertType.PRE_MARKET_HIGH, current, quality=float(lookback),
                description=desc, prev_value=prev_tracked, new_value=price,
                details={"lookback_days": lookback,
                         "resistance_date": res_day,
                         "resistance_price": res_price},
            ))

    def _detect_pre_market_low(self, current, previous, alerts):
        """LPRE: new low during pre-market only. Quality = lookback days."""
        sym = current.symbol
        price = current.price
        prev_tracked = self._tracked_pre_lows.get(sym)
        if prev_tracked is None:
            self._tracked_pre_lows[sym] = price
            return
        self._tracked_pre_lows[sym] = min(self._tracked_pre_lows[sym], price)
        if price >= prev_tracked:
            return

        lookback, sup_day, sup_price = self._compute_lookback_low(sym, price)

        if self._can_fire(AlertType.PRE_MARKET_LOW, sym, self.COOLDOWN_NEW_EXTREME):
            self._record_fire(AlertType.PRE_MARKET_LOW, sym)
            desc = f"Pre-market low ${price:.2f}"
            if lookback > 0:
                desc += f" ({lookback}-day)"
            if sup_price:
                desc += f". Support {sup_day} at ${sup_price:.2f}"
            alerts.append(self._make_alert(
                AlertType.PRE_MARKET_LOW, current, quality=float(lookback),
                description=desc, prev_value=prev_tracked, new_value=price,
                details={"lookback_days": lookback,
                         "support_date": sup_day,
                         "support_price": sup_price},
            ))

    def _detect_post_market_high(self, current, previous, alerts):
        """HPOST: new high during post-market. Quality = lookback days.
        TI: lookback counts from today's close, so days_ago=1 means above today's high."""
        sym = current.symbol
        price = current.price
        prev_tracked = self._tracked_post_highs.get(sym)
        self._tracked_post_highs[sym] = max(self._tracked_post_highs.get(sym, 0), price)
        if prev_tracked is None or price <= prev_tracked:
            return

        lookback = self._compute_lookback_post_high(sym, price, current)

        if self._can_fire(AlertType.POST_MARKET_HIGH, sym, self.COOLDOWN_NEW_EXTREME):
            self._record_fire(AlertType.POST_MARKET_HIGH, sym)
            desc = f"Post-market high ${price:.2f}"
            if lookback > 0:
                desc += f" ({lookback}-day)"
            alerts.append(self._make_alert(
                AlertType.POST_MARKET_HIGH, current, quality=float(lookback),
                description=desc, prev_value=prev_tracked, new_value=price,
                details={"lookback_days": lookback},
            ))

    def _detect_post_market_low(self, current, previous, alerts):
        """LPOST: new low during post-market. Quality = lookback days."""
        sym = current.symbol
        price = current.price
        prev_tracked = self._tracked_post_lows.get(sym)
        if prev_tracked is None:
            self._tracked_post_lows[sym] = price
            return
        self._tracked_post_lows[sym] = min(self._tracked_post_lows[sym], price)
        if price >= prev_tracked:
            return

        lookback = self._compute_lookback_post_low(sym, price, current)

        if self._can_fire(AlertType.POST_MARKET_LOW, sym, self.COOLDOWN_NEW_EXTREME):
            self._record_fire(AlertType.POST_MARKET_LOW, sym)
            desc = f"Post-market low ${price:.2f}"
            if lookback > 0:
                desc += f" ({lookback}-day)"
            alerts.append(self._make_alert(
                AlertType.POST_MARKET_LOW, current, quality=float(lookback),
                description=desc, prev_value=prev_tracked, new_value=price,
                details={"lookback_days": lookback},
            ))

    def _detect_crossed_daily_highs(self, current, alerts):
        """CDHR: fires only when the lookback level increases (new resistance broken).
        TI: 'This alert only reports when the number of days in the new high changes.'
        Reuses _compute_lookback_high which scans all daily highs from baseline."""
        sym = current.symbol
        price = current.price

        lookback, res_date, res_price = self._compute_lookback_high(sym, price)
        prev_lookback = self._cdhr_last_lookback.get(sym, -1)

        if lookback > prev_lookback:
            self._cdhr_last_lookback[sym] = lookback
            desc = f"Crossed {lookback}-day high resistance"
            if res_price is not None:
                desc += f" (next resistance ${res_price:.2f}"
                if res_date:
                    desc += f" on {res_date}"
                desc += ")"
            alerts.append(self._make_alert(
                AlertType.CROSSED_DAILY_HIGH_RESISTANCE, current, quality=float(lookback),
                description=desc, prev_value=0.0, new_value=price,
                details={"lookback_days": lookback, "resistance_date": res_date,
                         "resistance_price": res_price},
            ))

    def _detect_crossed_daily_lows(self, current, alerts):
        """CDLS: fires only when the lookback level increases (new support broken).
        TI: 'This alert only reports when the number of days in the new low changes.'"""
        sym = current.symbol
        price = current.price

        lookback, sup_date, sup_price = self._compute_lookback_low(sym, price)
        prev_lookback = self._cdls_last_lookback.get(sym, -1)

        if lookback > prev_lookback:
            self._cdls_last_lookback[sym] = lookback
            desc = f"Crossed {lookback}-day low support"
            if sup_price is not None:
                desc += f" (next support ${sup_price:.2f}"
                if sup_date:
                    desc += f" on {sup_date}"
                desc += ")"
            alerts.append(self._make_alert(
                AlertType.CROSSED_DAILY_LOW_SUPPORT, current, quality=float(lookback),
                description=desc, prev_value=0.0, new_value=price,
                details={"lookback_days": lookback, "support_date": sup_date,
                         "support_price": sup_price},
            ))

    # ── Lookback computation ──

    def _compute_lookback_high(self, symbol, price) -> Tuple[int, Optional[str], Optional[float]]:
        """Returns (lookback_days, resistance_date_str, resistance_price).

        Trade Ideas: quality = max days for which this is a new high.
        Description: the most recent day before today when price was higher.
        """
        if not self.baseline:
            return (0, None, None)

        extremes = self.baseline.get_daily_extremes(symbol)
        if not extremes:
            return (0, None, None)

        max_lookback = 0
        resistance_date = None
        resistance_price = None

        for ext in sorted(extremes, key=lambda e: e.days_ago):
            if price > ext.high:
                max_lookback = ext.days_ago
            else:
                resistance_date = ext.trading_date.isoformat() if hasattr(ext.trading_date, 'isoformat') else str(ext.trading_date)
                resistance_price = ext.high
                break

        return (max_lookback, resistance_date, resistance_price)

    def _compute_lookback_low(self, symbol, price) -> Tuple[int, Optional[str], Optional[float]]:
        """Returns (lookback_days, support_date_str, support_price)."""
        if not self.baseline:
            return (0, None, None)

        extremes = self.baseline.get_daily_extremes(symbol)
        if not extremes:
            return (0, None, None)

        max_lookback = 0
        support_date = None
        support_price = None

        for ext in sorted(extremes, key=lambda e: e.days_ago):
            if price < ext.low:
                max_lookback = ext.days_ago
            else:
                support_date = ext.trading_date.isoformat() if hasattr(ext.trading_date, 'isoformat') else str(ext.trading_date)
                support_price = ext.low
                break

        return (max_lookback, support_date, support_price)

    def _compute_lookback_post_high(self, symbol, price, current) -> int:
        """Post-market: lookback counts from today's close.
        days_ago=0 includes today's intraday high, so 1 = above today's high."""
        today_high = current.intraday_high
        if today_high and price <= today_high:
            return 0

        if not self.baseline:
            return 1 if (today_high and price > today_high) else 0

        extremes = self.baseline.get_daily_extremes(symbol)
        if not extremes:
            return 1 if (today_high and price > today_high) else 0

        lookback = 1 if (today_high and price > today_high) else 0
        for ext in sorted(extremes, key=lambda e: e.days_ago):
            if price > ext.high:
                lookback = ext.days_ago + 1
            else:
                break
        return lookback

    def _compute_lookback_post_low(self, symbol, price, current) -> int:
        """Post-market: lookback counts from today's close."""
        today_low = current.intraday_low
        if today_low and price >= today_low:
            return 0

        if not self.baseline:
            return 1 if (today_low and price < today_low) else 0

        extremes = self.baseline.get_daily_extremes(symbol)
        if not extremes:
            return 1 if (today_low and price < today_low) else 0

        lookback = 1 if (today_low and price < today_low) else 0
        for ext in sorted(extremes, key=lambda e: e.days_ago):
            if price < ext.low:
                lookback = ext.days_ago + 1
            else:
                break
        return lookback

    def _build_high_description(self, price, lookback, resistance_day, resistance_price):
        """Trade Ideas style: 'New high $X. Last higher: MM/DD at $Y' """
        desc = f"New high ${price:.2f}"
        if lookback == 0:
            pass
        elif lookback == 1:
            desc = f"New high ${price:.2f}, above yesterday's high"
        else:
            desc = f"New {lookback}-day high ${price:.2f}"
        if resistance_price is not None and resistance_day is not None:
            desc += f". Resistance {resistance_day} at ${resistance_price:.2f}"
        return desc

    def _build_low_description(self, price, lookback, support_day, support_price):
        desc = f"New low ${price:.2f}"
        if lookback == 0:
            pass
        elif lookback == 1:
            desc = f"New low ${price:.2f}, below yesterday's low"
        else:
            desc = f"New {lookback}-day low ${price:.2f}"
        if support_price is not None and support_day is not None:
            desc += f". Support {support_day} at ${support_price:.2f}"
        return desc

    def _filtered_cooldown(self, symbol: str, price: float) -> int:
        """TI: 1 alert/min by default, but if price moves more basis points
        than expected (based on volatility), allow more frequent alerts.

        Returns adaptive cooldown in seconds (60 down to 10).
        """
        if not self.baseline:
            return self.FILTERED_BASE_COOLDOWN

        vol = self.baseline.get_volatility(symbol)
        if vol is None or vol.avg_dollar_move_1m <= 0:
            return self.FILTERED_BASE_COOLDOWN

        last_key_h = f"{symbol}:H"
        last_key_l = f"{symbol}:L"
        last_price = self._last_filtered_price.get(last_key_h) or self._last_filtered_price.get(last_key_l)
        if last_price is None or last_price <= 0:
            return self.FILTERED_BASE_COOLDOWN

        move_bps = abs(price - last_price) / last_price * 10_000
        expected_bps = vol.avg_dollar_move_1m / last_price * 10_000 if last_price > 0 else 50

        if expected_bps <= 0:
            return self.FILTERED_BASE_COOLDOWN

        ratio = move_bps / expected_bps
        if ratio >= 3.0:
            return self.FILTERED_MIN_COOLDOWN
        elif ratio >= 2.0:
            return 20
        elif ratio >= 1.5:
            return 30
        else:
            return self.FILTERED_BASE_COOLDOWN

    def initialize_extremes(self, symbol, high, low):
        self._tracked_highs[symbol] = high
        self._tracked_lows[symbol] = low

    def cleanup_old_symbols(self, active: set) -> int:
        removed = 0
        for d in (self._tracked_highs, self._tracked_lows,
                  self._tracked_ask_highs, self._tracked_bid_lows,
                  self._tracked_bid_highs, self._tracked_ask_lows,
                  self._tracked_pre_highs, self._tracked_pre_lows,
                  self._tracked_post_highs, self._tracked_post_lows,
                  self._cdhr_last_lookback, self._cdls_last_lookback):
            stale = [s for s in d if s not in active]
            for s in stale:
                del d[s]
            removed += len(stale)
        fp_stale = [k for k in self._last_filtered_price
                     if k.split(":")[0] not in active]
        for k in fp_stale:
            del self._last_filtered_price[k]
        removed += len(fp_stale)
        return removed + super().cleanup_old_symbols(active)

    def reset_daily(self):
        super().reset_daily()
        self._tracked_highs.clear()
        self._tracked_lows.clear()
        self._tracked_ask_highs.clear()
        self._tracked_bid_lows.clear()
        self._tracked_bid_highs.clear()
        self._tracked_ask_lows.clear()
        self._tracked_pre_highs.clear()
        self._tracked_pre_lows.clear()
        self._tracked_post_highs.clear()
        self._tracked_post_lows.clear()
        self._last_filtered_price.clear()
        self._cdhr_last_lookback.clear()
        self._cdls_last_lookback.clear()