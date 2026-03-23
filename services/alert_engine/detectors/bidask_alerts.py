"""
Bid/Ask Microstructure Alert Detector.

Covers: LBS, LAS, MC, MCU, MCD, ML, LSP.

Trade Ideas behavior:
  - MC "Market Crossed": ask < bid. Quality = cents crossed (bid - ask).
    Reports first crossing in each group. New alert only if cross grows
    or market uncrossed for several minutes.
  - LBS/LAS: Quality = number of shares on the bid/ask.
  - LSP: Quality = spread in cents.
"""

import time
from typing import Optional, List, Dict

from detectors.base import BaseAlertDetector
from models.alert_types import AlertType
from models.alert_state import AlertState
from models.alert_record import AlertRecord


class BidAskAlertDetector(BaseAlertDetector):

    COOLDOWN_LOCKED = 300
    COOLDOWN_SPREAD = 120

    MAX_AVG_DAILY_VOL = 3_000_000
    LBS_TIER_LOW_VOL = 1_000_000
    LBS_MIN_LOW = 6_000
    LBS_MIN_HIGH = 10_000

    LSP_MIN_CENTS = 50

    def __init__(self):
        super().__init__()
        self._last_cross_size: Dict[str, float] = {}
        self._last_uncross_time: Dict[str, float] = {}
        self._lbs_state: Dict[str, dict] = {}
        self._las_state: Dict[str, dict] = {}
        self._tra_state: Dict[str, dict] = {}
        self._trb_state: Dict[str, dict] = {}
        self._tras_state: Dict[str, dict] = {}
        self._trbs_state: Dict[str, dict] = {}

    LISTED_EXCHANGES = {"NYSE", "AMEX", "NYE", "ASE", "XNYS", "XASE"}

    def detect(self, current: AlertState, previous: Optional[AlertState]) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if not self._has_min_volume(current):
            return alerts

        self._detect_market_crossed(current, previous, alerts)
        self._detect_market_locked(current, previous, alerts)
        self._detect_large_bid_size(current, alerts)
        self._detect_large_ask_size(current, alerts)
        self._detect_large_spread(current, previous, alerts)
        self._detect_trading_above(current, alerts)
        self._detect_trading_below(current, alerts)

        is_listed = str(current.exchange or "").upper() in self.LISTED_EXCHANGES
        is_regular = current.market_session in ("REGULAR", "MARKET_HOURS", None)
        if is_listed and is_regular:
            self._detect_trading_above_specialist(current, alerts)
            self._detect_trading_below_specialist(current, alerts)

        return alerts

    def _detect_market_crossed(self, current, previous, alerts):
        """MC/MCU/MCD: ask < bid = crossed market.
        TI: reports first crossing in each group. New alert only if cross grows
        or market uncrossed for several minutes before crossing again.
        MC fires on every qualifying cross. MCU/MCD fire additionally when
        direction can be determined (bid > prev_close = up, ask < prev_close = down)."""
        sym = current.symbol
        bid = current.bid
        ask = current.ask
        if bid is None or ask is None or bid <= 0 or ask <= 0:
            return

        now = time.monotonic()

        if ask < bid:
            cross_cents = round((bid - ask) * 100, 1)
            prev_cross = self._last_cross_size.get(sym, 0)

            should_fire = False
            if prev_cross == 0:
                should_fire = True
            elif cross_cents > prev_cross:
                should_fire = True
            else:
                last_uncross = self._last_uncross_time.get(sym, 0)
                if last_uncross > 0 and (now - last_uncross) > 120:
                    should_fire = True

            if should_fire:
                self._last_cross_size[sym] = cross_cents
                base_details = {"cross_cents": cross_cents, "bid": bid, "ask": ask}

                alerts.append(self._make_alert(
                    AlertType.MARKET_CROSSED, current, quality=cross_cents,
                    description=f"Market crossed ({cross_cents:.1f} cents)",
                    prev_value=ask, new_value=bid, details=base_details,
                ))

                direction = ""
                if current.prev_close and current.prev_close > 0:
                    if bid > current.prev_close:
                        direction = "up"
                    elif ask < current.prev_close:
                        direction = "down"

                if direction == "up":
                    alerts.append(self._make_alert(
                        AlertType.MARKET_CROSSED_UP, current, quality=cross_cents,
                        description=f"Market crossed up ({cross_cents:.1f} cents)",
                        prev_value=ask, new_value=bid,
                        details={**base_details, "direction": "up"},
                    ))
                elif direction == "down":
                    alerts.append(self._make_alert(
                        AlertType.MARKET_CROSSED_DOWN, current, quality=cross_cents,
                        description=f"Market crossed down ({cross_cents:.1f} cents)",
                        prev_value=ask, new_value=bid,
                        details={**base_details, "direction": "down"},
                    ))
        else:
            if self._last_cross_size.get(sym, 0) > 0:
                self._last_uncross_time[sym] = now
                self._last_cross_size[sym] = 0

    def _detect_market_locked(self, current, previous, alerts):
        sym = current.symbol
        bid = current.bid
        ask = current.ask
        if bid is None or ask is None:
            return
        if bid == ask and bid > 0:
            prev_bid = previous.bid if previous else None
            prev_ask = previous.ask if previous else None
            if prev_bid != prev_ask:
                if self._can_fire(AlertType.MARKET_LOCKED, sym, self.COOLDOWN_LOCKED):
                    self._record_fire(AlertType.MARKET_LOCKED, sym)
                    alerts.append(self._make_alert(
                        AlertType.MARKET_LOCKED, current, quality=0.0,
                        description=f"Market locked at ${bid:.2f}",
                        prev_value=prev_bid, new_value=bid,
                    ))

    def _get_min_shares(self, current) -> int:
        """TI: only for avg daily vol < 3M.
        < 1M → 6,000 shares min. 1M-3M → 10,000 shares min."""
        adv = 0.0
        if self.baseline:
            vol = self.baseline.get_volatility(current.symbol)
            if vol:
                adv = vol.avg_daily_volume
        if not adv and hasattr(current, 'avg_daily_volume'):
            adv = current.avg_daily_volume or 0.0
        if adv >= self.MAX_AVG_DAILY_VOL:
            return 0
        if adv < self.LBS_TIER_LOW_VOL:
            return self.LBS_MIN_LOW
        return self.LBS_MIN_HIGH

    def _detect_large_bid_size(self, current, alerts):
        """LBS: large bid size with size-increasing and price-change tracking.
        TI: anti-repeat when best bid returns to same large level without real change."""
        sym = current.symbol
        bid = current.bid
        bs = current.bid_size
        if bid is None or bs is None or bid <= 0:
            return

        min_shares = self._get_min_shares(current)
        if min_shares == 0:
            return

        st = self._lbs_state.get(sym)

        if bs < min_shares:
            if st:
                st["active"] = False
            return

        if not st:
            st = {"active": False, "size": 0, "price": 0.0, "reported_size": 0, "reported_price": 0.0}
            self._lbs_state[sym] = st

        label = ""
        should_fire = False

        if not st["active"]:
            should_fire = True
            label = ""
        elif bs > st["reported_size"]:
            should_fire = True
            label = " (Size increasing)"
        elif bid != st["reported_price"] and bs >= min_shares:
            if bid == st["price"]:
                pass
            else:
                should_fire = True
                label = " (Price rising)" if bid > st["reported_price"] else " (Price dropping)"

        st["size"] = bs
        st["price"] = bid

        if should_fire:
            st["active"] = True
            st["reported_size"] = bs
            st["reported_price"] = bid
            desc = f"Large bid size {bs:,} shares @ ${bid:.2f}{label}"
            alerts.append(self._make_alert(
                AlertType.LARGE_BID_SIZE, current, quality=float(bs),
                description=desc, prev_value=st.get("reported_size", 0), new_value=float(bs),
                details={"shares": bs, "bid": bid, "label": label.strip(" ()")},
            ))

    def _detect_large_ask_size(self, current, alerts):
        """LAS: large ask size with size-increasing and price-change tracking."""
        sym = current.symbol
        ask = current.ask
        as_ = current.ask_size
        if ask is None or as_ is None or ask <= 0:
            return

        min_shares = self._get_min_shares(current)
        if min_shares == 0:
            return

        st = self._las_state.get(sym)

        if as_ < min_shares:
            if st:
                st["active"] = False
            return

        if not st:
            st = {"active": False, "size": 0, "price": 0.0, "reported_size": 0, "reported_price": 0.0}
            self._las_state[sym] = st

        label = ""
        should_fire = False

        if not st["active"]:
            should_fire = True
            label = ""
        elif as_ > st["reported_size"]:
            should_fire = True
            label = " (Size increasing)"
        elif ask != st["reported_price"] and as_ >= min_shares:
            if ask == st["price"]:
                pass
            else:
                should_fire = True
                label = " (Price rising)" if ask > st["reported_price"] else " (Price dropping)"

        st["size"] = as_
        st["price"] = ask

        if should_fire:
            st["active"] = True
            st["reported_size"] = as_
            st["reported_price"] = ask
            desc = f"Large ask size {as_:,} shares @ ${ask:.2f}{label}"
            alerts.append(self._make_alert(
                AlertType.LARGE_ASK_SIZE, current, quality=float(as_),
                description=desc, prev_value=st.get("reported_size", 0), new_value=float(as_),
                details={"shares": as_, "ask": ask, "label": label.strip(" ()")},
            ))

    def _detect_large_spread(self, current, previous, alerts):
        sym = current.symbol
        bid = current.bid
        ask = current.ask
        if bid is None or ask is None or bid <= 0 or ask <= 0:
            return
        spread_cents = round((ask - bid) * 100, 1)
        if spread_cents < self.LSP_MIN_CENTS:
            return
        prev_spread = 0
        if previous and previous.bid and previous.ask:
            prev_spread = round((previous.ask - previous.bid) * 100, 1)
        if prev_spread >= self.LSP_MIN_CENTS:
            return
        if self._can_fire(AlertType.LARGE_SPREAD, sym, self.COOLDOWN_SPREAD):
            self._record_fire(AlertType.LARGE_SPREAD, sym)
            alerts.append(self._make_alert(
                AlertType.LARGE_SPREAD, current, quality=spread_cents,
                description=f"Large spread {spread_cents:.0f} cents (bid ${bid:.2f} ask ${ask:.2f})",
                prev_value=prev_spread, new_value=spread_cents,
                details={"spread_cents": spread_cents, "bid": bid, "ask": ask},
            ))

    # ── TRA / TRB ─────────────────────────────────────────────────────

    TRADE_THROUGH_GROUP_GAP = 5.0

    def _detect_trading_above(self, current, alerts):
        """TRA: print > best ask. Groups consecutive events.
        TI: quality = count of grouped prints above the ask.
        Description: 'Trading above N times' or 'Trading above' for single."""
        sym = current.symbol
        price = current.price
        ask = current.ask
        if ask is None or ask <= 0 or price <= ask:
            self._tra_expire(sym)
            return

        now = time.monotonic()
        st = self._tra_state.get(sym)

        if st and (now - st["last_time"]) < self.TRADE_THROUGH_GROUP_GAP:
            st["count"] += 1
            st["last_time"] = now
        else:
            st = {"count": 1, "last_time": now, "last_reported": 0}
            self._tra_state[sym] = st

        if st["count"] > st["last_reported"]:
            st["last_reported"] = st["count"]
            n = st["count"]
            desc = f"Trading above {n} times" if n > 1 else "Trading above"
            alerts.append(self._make_alert(
                AlertType.TRADING_ABOVE, current, quality=float(n),
                description=desc, prev_value=ask, new_value=price,
                details={"times": n, "ask": ask, "price": price},
            ))

    def _detect_trading_below(self, current, alerts):
        """TRB: print < best bid. Groups consecutive events.
        TI: quality = count of grouped prints below the bid."""
        sym = current.symbol
        price = current.price
        bid = current.bid
        if bid is None or bid <= 0 or price >= bid:
            self._trb_expire(sym)
            return

        now = time.monotonic()
        st = self._trb_state.get(sym)

        if st and (now - st["last_time"]) < self.TRADE_THROUGH_GROUP_GAP:
            st["count"] += 1
            st["last_time"] = now
        else:
            st = {"count": 1, "last_time": now, "last_reported": 0}
            self._trb_state[sym] = st

        if st["count"] > st["last_reported"]:
            st["last_reported"] = st["count"]
            n = st["count"]
            desc = f"Trading below {n} times" if n > 1 else "Trading below"
            alerts.append(self._make_alert(
                AlertType.TRADING_BELOW, current, quality=float(n),
                description=desc, prev_value=bid, new_value=price,
                details={"times": n, "bid": bid, "price": price},
            ))

    def _tra_expire(self, sym):
        st = self._tra_state.get(sym)
        if st:
            if (time.monotonic() - st["last_time"]) >= self.TRADE_THROUGH_GROUP_GAP:
                del self._tra_state[sym]

    def _trb_expire(self, sym):
        st = self._trb_state.get(sym)
        if st:
            if (time.monotonic() - st["last_time"]) >= self.TRADE_THROUGH_GROUP_GAP:
                del self._trb_state[sym]

    # ── TRAS / TRBS — Specialist variants (NYSE/AMEX, regular hours only) ──

    def _detect_trading_above_specialist(self, current, alerts):
        """TRAS: print > specialist's offer (ask). Same grouping as TRA.
        TI: subset of TRA, only NYSE/AMEX, regular hours."""
        sym = current.symbol
        price = current.price
        ask = current.ask
        if ask is None or ask <= 0 or price <= ask:
            self._tras_expire(sym)
            return

        now = time.monotonic()
        st = self._tras_state.get(sym)

        if st and (now - st["last_time"]) < self.TRADE_THROUGH_GROUP_GAP:
            st["count"] += 1
            st["last_time"] = now
        else:
            st = {"count": 1, "last_time": now, "last_reported": 0}
            self._tras_state[sym] = st

        if st["count"] > st["last_reported"]:
            st["last_reported"] = st["count"]
            n = st["count"]
            desc = f"Trading above specialist {n} times" if n > 1 else "Trading above specialist"
            alerts.append(self._make_alert(
                AlertType.TRADING_ABOVE_SPECIALIST, current, quality=float(n),
                description=desc, prev_value=ask, new_value=price,
                details={"times": n, "ask": ask, "price": price},
            ))

    def _detect_trading_below_specialist(self, current, alerts):
        """TRBS: print < specialist's bid. Same grouping as TRB.
        TI: subset of TRB, only NYSE/AMEX, regular hours."""
        sym = current.symbol
        price = current.price
        bid = current.bid
        if bid is None or bid <= 0 or price >= bid:
            self._trbs_expire(sym)
            return

        now = time.monotonic()
        st = self._trbs_state.get(sym)

        if st and (now - st["last_time"]) < self.TRADE_THROUGH_GROUP_GAP:
            st["count"] += 1
            st["last_time"] = now
        else:
            st = {"count": 1, "last_time": now, "last_reported": 0}
            self._trbs_state[sym] = st

        if st["count"] > st["last_reported"]:
            st["last_reported"] = st["count"]
            n = st["count"]
            desc = f"Trading below specialist {n} times" if n > 1 else "Trading below specialist"
            alerts.append(self._make_alert(
                AlertType.TRADING_BELOW_SPECIALIST, current, quality=float(n),
                description=desc, prev_value=bid, new_value=price,
                details={"times": n, "bid": bid, "price": price},
            ))

    def _tras_expire(self, sym):
        st = self._tras_state.get(sym)
        if st:
            if (time.monotonic() - st["last_time"]) >= self.TRADE_THROUGH_GROUP_GAP:
                del self._tras_state[sym]

    def _trbs_expire(self, sym):
        st = self._trbs_state.get(sym)
        if st:
            if (time.monotonic() - st["last_time"]) >= self.TRADE_THROUGH_GROUP_GAP:
                del self._trbs_state[sym]

    def reset_daily(self):
        super().reset_daily()
        self._last_cross_size.clear()
        self._last_uncross_time.clear()
        self._lbs_state.clear()
        self._las_state.clear()
        self._tra_state.clear()
        self._trb_state.clear()
        self._tras_state.clear()
        self._trbs_state.clear()