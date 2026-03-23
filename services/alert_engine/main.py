"""
Alert Engine Service - Main entry point.
Professional alert detection: Generate once, filter N times.
"""

import asyncio
import json
import logging
import os
import signal
import time
from datetime import datetime, date
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import redis.asyncio as aioredis

PARTITION_ID = int(os.environ.get("PARTITION_ID", "0"))
NUM_PARTITIONS = int(os.environ.get("NUM_PARTITIONS", "4"))

from shared.config.settings import settings
from shared.utils.redis_client import RedisClient
from shared.events import EventBus, EventType as BusEventType, Event

from models import AlertType, AlertState, AlertStateCache, AlertRecord
from baseline import BaselineLoader
from detectors import ALL_DETECTOR_CLASSES
from detectors.price_alerts import PriceAlertDetector
from persistence import AlertWriter

ET = ZoneInfo("America/New_York")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("alert-engine")

STREAM_ALERTS = "stream:alerts:market"

redis_client: Optional[RedisClient] = None
event_bus: Optional[EventBus] = None
engine: Optional["AlertEngine"] = None
is_holiday_mode: bool = False
current_trading_date: Optional[date] = None
current_market_session: str = "UNKNOWN"


async def check_initial_market_status():
    global is_holiday_mode, current_trading_date, current_market_session
    try:
        status = await redis_client.get(f"{settings.key_prefix_market}:session:status")
        if status:
            is_holiday_mode = status.get("is_holiday", False) or not status.get("is_trading_day", True)
            td = status.get("trading_date")
            if td:
                current_trading_date = date.fromisoformat(td)
            current_market_session = status.get("current_session", "UNKNOWN")
            logger.info(f"Market: holiday={is_holiday_mode}, date={td}, session={current_market_session}")
        else:
            is_holiday_mode = False
    except Exception as e:
        logger.error(f"Market status error: {e}")
        is_holiday_mode = False


async def handle_day_changed(event: Event):
    global is_holiday_mode, current_trading_date
    logger.info(f"DAY_CHANGED: {event.data.get('new_date')}")
    await check_initial_market_status()
    if not is_holiday_mode and engine:
        await engine.reset_for_new_day()


async def handle_session_changed(event: Event):
    global current_market_session
    current_market_session = event.data.get("new_session") or event.data.get("to_session") or "?"
    logger.info(f"Session -> {current_market_session}")


class AlertEngine:

    _ENRICHED_FLOAT_KEYS = [
        "rvol", "vwap", "atr", "atr_percent", "bid", "ask", "spread",
        "chg_1min", "chg_5min", "chg_10min", "chg_15min", "chg_30min", "chg_60min",
        "vol_1min_pct", "vol_5min_pct", "rsi_14", "ema_20", "ema_50",
        "sma_5", "sma_8", "sma_20", "sma_50", "sma_200",
        "macd_line", "macd_signal", "macd_hist", "bb_upper", "bb_lower",
        "adx_14", "stoch_k", "stoch_d",
        "daily_sma_20", "daily_sma_50", "daily_sma_200",
        "high_52w", "low_52w", "market_cap", "float_shares",
        "trades_z_score", "gap_percent", "change_from_open",
        "sma_8_5m", "sma_20_5m", "macd_line_5m", "macd_signal_5m", "stoch_k_5m", "stoch_d_5m",
        "avg_volume_10d",
        "prev_bar_high_5m", "prev_bar_low_5m", "cur_bar_high_5m", "cur_bar_low_5m",
        "prev_bar_high_10m", "prev_bar_low_10m", "cur_bar_high_10m", "cur_bar_low_10m",
        "prev_bar_high_15m", "prev_bar_low_15m", "cur_bar_high_15m", "cur_bar_low_15m",
        "prev_bar_high_30m", "prev_bar_low_30m", "cur_bar_high_30m", "cur_bar_low_30m",
        "prev_bar_high_60m", "prev_bar_low_60m", "cur_bar_high_60m", "cur_bar_low_60m",
    ]
    _ENRICHED_INT_KEYS = ["vol_1min", "vol_5min", "bid_size", "ask_size", "shares_outstanding", "minute_volume"]

    def __init__(self, redis_cl, baseline_loader=None, alert_writer=None):
        self.redis = redis_cl
        self.raw_redis: Optional[aioredis.Redis] = None
        self.running = False
        self.baseline = baseline_loader
        self.alert_writer: Optional[AlertWriter] = alert_writer
        self.state_cache = AlertStateCache(max_age_seconds=3600)
        self._enriched_cache: Dict[str, Dict] = {}
        self.detectors = [cls() for cls in ALL_DETECTOR_CLASSES]
        if self.baseline:
            for d in self.detectors:
                d.set_baseline(self.baseline)
        self.price_detector: Optional[PriceAlertDetector] = None
        for d in self.detectors:
            if isinstance(d, PriceAlertDetector):
                self.price_detector = d
                break
        self._stats = {"alerts": 0, "ticks": 0, "last_alerts": 0, "last_ticks": 0, "tick_times": []}
        logger.info(f"[P{PARTITION_ID}] Loaded {len(self.detectors)} detectors: {[d.__class__.__name__ for d in self.detectors]}")

    async def start(self):
        logger.info(f"Starting Alert Engine worker (partition={PARTITION_ID}/{NUM_PARTITIONS})...")
        self.raw_redis = self.redis.client
        self.running = True
        await self._refresh_enriched_cache()
        logger.info(f"Enriched cache: {len(self._enriched_cache)} tickers")
        if self.price_detector:
            self._init_extremes()
        tasks = [
            asyncio.create_task(self._consume_aggregates()),
            asyncio.create_task(self._consume_halts()),
            asyncio.create_task(self._enriched_loop()),
            asyncio.create_task(self._cleanup_loop()),
            asyncio.create_task(self._stats_loop()),
        ]
        if self.alert_writer:
            tasks.append(asyncio.create_task(self.alert_writer.run()))
        await asyncio.gather(*tasks)

    async def stop(self):
        self.running = False

    async def reset_for_new_day(self):
        logger.info("Daily reset...")
        for d in self.detectors:
            d.reset_daily()
        self.state_cache.clear()
        self._stats = {"alerts": 0, "ticks": 0}
        try:
            await self.raw_redis.xtrim(STREAM_ALERTS, maxlen=0)
        except Exception as e:
            logger.error(f"Trim error: {e}")
        await self._refresh_enriched_cache()
        if self.baseline:
            syms = list(self._enriched_cache.keys())
            await self.baseline.load_all(syms, current_trading_date)
            for d in self.detectors:
                d.set_baseline(self.baseline)
        if self.price_detector:
            self._init_extremes()
        logger.info("Daily reset complete")

    async def _consume_aggregates(self):
        stream = f"stream:agg:p{PARTITION_ID}"
        group = f"alert_engine_p{PARTITION_ID}"
        consumer = f"worker_{PARTITION_ID}"
        logger.info(f"Consuming partition {PARTITION_ID} from {stream}")
        try:
            await self.raw_redis.xgroup_create(stream, group, id="$", mkstream=True)
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                logger.error(f"Consumer group error: {e}")
        while self.running:
            try:
                if is_holiday_mode:
                    await asyncio.sleep(30)
                    continue
                msgs = await self.raw_redis.xreadgroup(group, consumer, {stream: ">"}, count=100, block=1000)
                if not msgs:
                    continue
                ids = []
                for _, entries in msgs:
                    for mid, data in entries:
                        ids.append(mid)
                        await self._process_aggregate(data)
                if ids:
                    await self.raw_redis.xack(stream, group, *ids)
            except Exception as e:
                if "NOGROUP" in str(e):
                    try:
                        await self.raw_redis.xgroup_create(stream, group, id="0", mkstream=True)
                        continue
                    except Exception:
                        pass
                logger.error(f"Agg consumer error: {e}")
                await asyncio.sleep(1)

    async def _consume_halts(self):
        stream = "stream:halt:events"
        group, consumer = "alert_engine_halts", "ae_1"
        try:
            await self.raw_redis.xgroup_create(stream, group, id="$", mkstream=True)
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                logger.error(f"Halt group error: {e}")
        while self.running:
            try:
                msgs = await self.raw_redis.xreadgroup(group, consumer, {stream: ">"}, count=100, block=1000)
                if not msgs:
                    continue
                ids = []
                for _, entries in msgs:
                    for mid, data in entries:
                        ids.append(mid)
                        await self._process_halt(data)
                if ids:
                    await self.raw_redis.xack(stream, group, *ids)
            except Exception as e:
                if "NOGROUP" in str(e):
                    try:
                        await self.raw_redis.xgroup_create(stream, group, id="0", mkstream=True)
                        continue
                    except Exception:
                        pass
                logger.error(f"Halt consumer error: {e}")
                await asyncio.sleep(1)

    async def _process_aggregate(self, data: Dict):
        try:
            t0 = time.monotonic()
            symbol = data.get("sym") or data.get("symbol")
            if not symbol:
                return
            current = await self._build_state(symbol, data)
            if current is None:
                return
            previous = self.state_cache.get(symbol)
            if previous is None:
                previous = AlertState(symbol=symbol, price=current.price, volume=0,
                                      timestamp=current.timestamp, rvol=0.0, change_percent=0.0)
            all_alerts: List[AlertRecord] = []
            for det in self.detectors:
                try:
                    all_alerts.extend(det.detect(current, previous))
                except Exception as e:
                    logger.error(f"{det.__class__.__name__} error {symbol}: {e}")
            self.state_cache.set(symbol, current)
            self._stats["ticks"] += 1
            if all_alerts:
                pipe = self.raw_redis.pipeline(transaction=False)
                enriched = self._enriched_cache.get(symbol)
                for a in all_alerts:
                    d = a.to_dict()
                    pipe.xadd(STREAM_ALERTS, d, maxlen=100000)
                    if self.alert_writer:
                        self.alert_writer.buffer_alert(d, enriched)
                await pipe.execute()
                self._stats["alerts"] += len(all_alerts)
            elapsed_ms = (time.monotonic() - t0) * 1000
            tick_times = self._stats["tick_times"]
            tick_times.append(elapsed_ms)
            if len(tick_times) > 1000:
                del tick_times[:500]
        except Exception as e:
            logger.error(f"Aggregate error: {e}")

    async def _process_halt(self, data: Dict):
        try:
            et_raw = data.get("event_type", "").upper()
            symbol = data.get("symbol", "")
            logger.info(f"[P{PARTITION_ID}] Halt event: {et_raw} {symbol}")
            if not symbol or et_raw not in ("HALT", "RESUME"):
                return
            enriched = self._enriched_cache.get(symbol, {})
            rvol = await self._get_rvol(symbol)
            halt_data = {}
            raw_d = data.get("data")
            if raw_d:
                try:
                    halt_data = json.loads(raw_d) if isinstance(raw_d, str) else raw_d
                except Exception:
                    pass
            price = enriched.get("current_price") or halt_data.get("pause_threshold_price") or 0
            if price is None:
                price = 0
            price = float(price)
            volume = enriched.get("current_volume")
            if volume is not None:
                volume = int(volume)
            change_pct = enriched.get("change_percent")
            if change_pct is not None:
                change_pct = float(change_pct)
            mcap = enriched.get("market_cap")
            if mcap is not None:
                mcap = float(mcap)
            at = AlertType.HALT if et_raw == "HALT" else AlertType.RESUME
            details = {}
            hr = halt_data.get("halt_reason")
            if hr is not None:
                details["halt_reason"] = str(hr)
            hrd = halt_data.get("halt_reason_desc")
            if hrd is not None:
                details["halt_reason_desc"] = str(hrd)
            alert = AlertRecord(
                alert_type=at, symbol=symbol, timestamp=datetime.utcnow(), price=price,
                quality=0.0, description=f"Trading {'halted' if at == AlertType.HALT else 'resumed'}",
                change_percent=change_pct, rvol=rvol,
                volume=volume, market_cap=mcap,
                details=details if details else None,
            )
            await self._publish(alert)
            logger.info(f"[P{PARTITION_ID}] Halt published: {symbol} {at.value} price={price}")
            if self.alert_writer:
                enriched_data = self._enriched_cache.get(symbol, {})
                self.alert_writer.buffer_alert(alert.to_dict(), enriched_data)
        except Exception as e:
            logger.error(f"Halt error [{symbol if 'symbol' in dir() else '?'}]: {e}", exc_info=True)

    async def _build_state(self, symbol, data) -> Optional[AlertState]:
        try:
            price = float(data.get("c", 0) or data.get("close", 0))
            if price <= 0:
                return None
            volume = int(data.get("volume_accumulated", 0) or data.get("av", 0) or 0)
            minute_vol = int(data.get("volume", 0) or data.get("v", 0) or 0) or None
            e = self._enriched_cache.get(symbol, {})
            rvol = await self._get_rvol(symbol)
            vwap = e.get("vwap")
            if vwap is None:
                raw_vw = data.get("vw") or data.get("vwap")
                vwap = float(raw_vw) if raw_vw else None
            op = e.get("open_price")
            pc = e.get("prev_close")
            chg_pct = ((price - pc) / pc) * 100 if pc and pc > 0 else e.get("change_percent")
            gap = ((op - pc) / pc) * 100 if op and pc and pc > 0 else None
            cfo = ((price - op) / op) * 100 if op and op > 0 else None
            vol = self.baseline.get_volatility(symbol) if self.baseline else None
            ext = self.baseline.get_daily_extremes(symbol) if self.baseline else None
            def _f(k):
                v = e.get(k)
                return float(v) if v is not None else None
            def _i(k):
                v = e.get(k)
                return int(float(v)) if v is not None else None
            adv = _f("avg_volume_10d")
            if adv is None and vol:
                adv = vol.avg_daily_volume if vol.avg_daily_volume else None
            return AlertState(
                symbol=symbol, timestamp=datetime.utcnow(), price=price, volume=volume, minute_volume=minute_vol,
                bid=_f("bid"), ask=_f("ask"), bid_size=_i("bid_size"), ask_size=_i("ask_size"), spread=_f("spread"),
                vwap=vwap, intraday_high=_f("intraday_high"), intraday_low=_f("intraday_low"),
                prev_close=pc, prev_open=_f("prev_open"), open_price=op,
                prev_day_high=e.get("day_high"), prev_day_low=e.get("day_low"),
                last_trade_size=_i("last_trade_size"),
                exchange=e.get("primary_exchange") or e.get("last_trade_exchange"),
                avg_daily_volume=adv,
                change_percent=chg_pct, gap_percent=gap, change_from_open=cfo,
                chg_1min=_f("chg_1min"), chg_5min=_f("chg_5min"), chg_10min=_f("chg_10min"),
                chg_15min=_f("chg_15min"), chg_30min=_f("chg_30min"), chg_60min=_f("chg_60min"),
                vol_1min=_i("vol_1min"), vol_5min=_i("vol_5min"),
                vol_1min_pct=_f("vol_1min_pct"), vol_5min_pct=_f("vol_5min_pct"),
                rvol=rvol if rvol else _f("rvol"), atr=_f("atr"), atr_percent=_f("atr_percent"),
                trades_z_score=_f("trades_z_score"),
                sma_5=_f("sma_5"), sma_8=_f("sma_8"), sma_20=_f("sma_20"), sma_50=_f("sma_50"), sma_200=_f("sma_200"),
                ema_20=_f("ema_20"), ema_50=_f("ema_50"), bb_upper=_f("bb_upper"), bb_lower=_f("bb_lower"),
                rsi=_f("rsi_14"), macd_line=_f("macd_line"), macd_signal=_f("macd_signal"), macd_hist=_f("macd_hist"),
                stoch_k=_f("stoch_k"), stoch_d=_f("stoch_d"), adx_14=_f("adx_14"),
                daily_sma_20=_f("daily_sma_20"), daily_sma_50=_f("daily_sma_50"), daily_sma_200=_f("daily_sma_200"),
                high_52w=_f("high_52w"), low_52w=_f("low_52w"),
                market_cap=_f("market_cap"), float_shares=_f("float_shares"),
                security_type=e.get("security_type"), sector=e.get("sector"), industry=e.get("industry"),
                market_session=current_market_session,
                sma_8_5m=_f("sma_8_5m"), sma_20_5m=_f("sma_20_5m"),
                macd_line_5m=_f("macd_line_5m"), macd_signal_5m=_f("macd_signal_5m"),
                stoch_k_5m=_f("stoch_k_5m"), stoch_d_5m=_f("stoch_d_5m"),
                prev_bar_high_5m=_f("prev_bar_high_5m"), prev_bar_low_5m=_f("prev_bar_low_5m"),
                cur_bar_high_5m=_f("cur_bar_high_5m"), cur_bar_low_5m=_f("cur_bar_low_5m"),
                prev_bar_high_10m=_f("prev_bar_high_10m"), prev_bar_low_10m=_f("prev_bar_low_10m"),
                cur_bar_high_10m=_f("cur_bar_high_10m"), cur_bar_low_10m=_f("cur_bar_low_10m"),
                prev_bar_high_15m=_f("prev_bar_high_15m"), prev_bar_low_15m=_f("prev_bar_low_15m"),
                cur_bar_high_15m=_f("cur_bar_high_15m"), cur_bar_low_15m=_f("cur_bar_low_15m"),
                prev_bar_high_30m=_f("prev_bar_high_30m"), prev_bar_low_30m=_f("prev_bar_low_30m"),
                cur_bar_high_30m=_f("cur_bar_high_30m"), cur_bar_low_30m=_f("cur_bar_low_30m"),
                prev_bar_high_60m=_f("prev_bar_high_60m"), prev_bar_low_60m=_f("prev_bar_low_60m"),
                cur_bar_high_60m=_f("cur_bar_high_60m"), cur_bar_low_60m=_f("cur_bar_low_60m"),
                volatility=vol, daily_extremes=ext,
            )
        except Exception as e:
            logger.error(f"Build state error {symbol}: {e}")
            return None

    async def _publish(self, alert: AlertRecord):
        d = alert.to_dict()
        try:
            await self.raw_redis.xadd(STREAM_ALERTS, d, maxlen=100000)
            self._stats["alerts"] += 1
        except Exception as e:
            logger.error(f"Publish error: {e}")

    async def _get_rvol(self, symbol):
        try:
            v = await self.raw_redis.hget("rvol:current_slot", symbol)
            return float(v) if v else None
        except Exception:
            return None

    async def _refresh_enriched_cache(self):
        try:
            raw = await self.raw_redis.hgetall("snapshot:enriched:latest")
            if not raw:
                return
            raw.pop(b"__meta__", None)
            raw.pop("__meta__", None)
            cache: Dict[str, Dict] = {}
            for sk, tj in raw.items():
                try:
                    t = json.loads(tj if isinstance(tj, str) else tj.decode())
                except Exception:
                    continue
                sym = t.get("ticker") or t.get("symbol", "")
                if not sym:
                    continue
                day = t.get("day") or {}
                pd = t.get("prevDay") or {}
                lt = t.get("lastTrade") or {}
                entry = {
                    "change_percent": t.get("todaysChangePerc"),
                    "open_price": day.get("o") if isinstance(day, dict) else None,
                    "prev_close": pd.get("c") if isinstance(pd, dict) else None,
                    "prev_open": pd.get("o") if isinstance(pd, dict) else None,
                    "day_high": day.get("h") if isinstance(day, dict) else None,
                    "day_low": day.get("l") if isinstance(day, dict) else None,
                    "intraday_high": t.get("intraday_high"),
                    "intraday_low": t.get("intraday_low"),
                    "current_price": t.get("current_price"),
                    "current_volume": t.get("current_volume"),
                    "last_trade_size": lt.get("s") if isinstance(lt, dict) else None,
                    "last_trade_exchange": lt.get("x") if isinstance(lt, dict) else None,
                    "primary_exchange": t.get("primary_exchange"),
                }
                for key in self._ENRICHED_FLOAT_KEYS:
                    if key in entry:
                        continue
                    rv = t.get(key)
                    if rv is not None:
                        try:
                            entry[key] = float(rv)
                        except (ValueError, TypeError):
                            pass
                for key in self._ENRICHED_INT_KEYS:
                    rv = t.get(key)
                    if rv is not None:
                        try:
                            entry[key] = int(float(rv))
                        except (ValueError, TypeError):
                            pass
                for key in ("security_type", "sector", "industry"):
                    rv = t.get(key)
                    if rv and rv != "":
                        entry[key] = str(rv)
                cache[sym] = entry
            self._enriched_cache = cache
        except Exception as e:
            logger.error(f"Enriched cache error: {e}")

    def _init_extremes(self):
        if not self.price_detector:
            return
        n = 0
        for sym, d in self._enriched_cache.items():
            h, lo, p = d.get("intraday_high"), d.get("intraday_low"), d.get("current_price")
            if h is not None and lo is not None:
                self.price_detector.initialize_extremes(sym, float(h), float(lo))
                n += 1
            elif p is not None:
                self.price_detector.initialize_extremes(sym, float(p), float(p))
                n += 1
        logger.info(f"Initialized extremes for {n} symbols")

    async def _snapshot_loop(self):
        await asyncio.sleep(5)
        logger.info("Snapshot evaluation loop started")
        prev_snap: Dict[str, Dict] = {}
        while self.running:
            try:
                if is_holiday_mode:
                    await asyncio.sleep(30)
                    continue
                raw = await self.raw_redis.hgetall("snapshot:enriched:latest")
                if not raw:
                    await asyncio.sleep(2)
                    continue
                for sk, tj in raw.items():
                    sym = sk.decode() if isinstance(sk, bytes) else sk
                    if sym == "__meta__":
                        continue
                    try:
                        cur = json.loads(tj if isinstance(tj, str) else tj.decode())
                    except Exception:
                        continue
                    p = cur.get("current_price")
                    if not p or p <= 0:
                        continue
                    prev = prev_snap.get(sym)
                    prev_snap[sym] = cur
                    if prev is None:
                        continue
                    cs = self._raw_to_state(sym, cur)
                    ps = self._raw_to_state(sym, prev)
                    if cs is None or ps is None:
                        continue
                    for det in self.detectors:
                        try:
                            for a in det.detect(cs, ps):
                                await self._publish(a)
                        except Exception as e:
                            logger.error(f"Snapshot detector {det.__class__.__name__} error {sym}: {e}")
            except Exception as e:
                logger.error(f"Snapshot eval error: {e}")
            await asyncio.sleep(2)

    def _raw_to_state(self, symbol, raw) -> Optional[AlertState]:
        p = raw.get("current_price")
        if not p or p <= 0:
            return None
        try:
            day = raw.get("day") or {}
            pd = raw.get("prevDay") or {}
            lt = raw.get("lastTrade") or {}
            def _f(k):
                v = raw.get(k)
                return float(v) if v is not None else None
            def _i(k):
                v = raw.get(k)
                return int(float(v)) if v is not None else None
            price = float(p)
            pc = pd.get("c") if isinstance(pd, dict) else None
            op = day.get("o") if isinstance(day, dict) else None
            gap = ((op - pc) / pc) * 100 if op and pc and pc > 0 else None
            cfo = ((price - op) / op) * 100 if op and op > 0 else None
            vol = self.baseline.get_volatility(symbol) if self.baseline else None
            ext = self.baseline.get_daily_extremes(symbol) if self.baseline else None
            adv = _f("avg_volume_10d")
            if adv is None and vol:
                adv = vol.avg_daily_volume if vol.avg_daily_volume else None
            return AlertState(
                symbol=symbol, timestamp=datetime.utcnow(), price=price,
                volume=int(raw.get("current_volume", 0) or 0),
                minute_volume=_i("minute_volume"),
                last_trade_size=int(float(lt.get("s"))) if isinstance(lt, dict) and lt.get("s") is not None else None,
                bid=_f("bid"), ask=_f("ask"), bid_size=_i("bid_size"), ask_size=_i("ask_size"),
                spread=_f("spread"),
                vwap=_f("vwap"), intraday_high=_f("intraday_high"), intraday_low=_f("intraday_low"),
                prev_close=pc,
                prev_open=pd.get("o") if isinstance(pd, dict) else None,
                open_price=op,
                prev_day_high=day.get("h") if isinstance(day, dict) else None,
                prev_day_low=day.get("l") if isinstance(day, dict) else None,
                exchange=raw.get("primary_exchange") or (lt.get("x") if isinstance(lt, dict) else None),
                avg_daily_volume=adv,
                change_percent=raw.get("todaysChangePerc"),
                gap_percent=gap, change_from_open=cfo,
                chg_1min=_f("chg_1min"), chg_5min=_f("chg_5min"), chg_10min=_f("chg_10min"),
                chg_15min=_f("chg_15min"), chg_30min=_f("chg_30min"), chg_60min=_f("chg_60min"),
                vol_1min=_i("vol_1min"), vol_5min=_i("vol_5min"),
                vol_1min_pct=_f("vol_1min_pct"), vol_5min_pct=_f("vol_5min_pct"),
                rvol=_f("rvol"), atr=_f("atr"), atr_percent=_f("atr_percent"),
                trades_z_score=_f("trades_z_score"),
                sma_5=_f("sma_5"), sma_8=_f("sma_8"), sma_20=_f("sma_20"),
                sma_50=_f("sma_50"), sma_200=_f("sma_200"),
                ema_20=_f("ema_20"), ema_50=_f("ema_50"),
                bb_upper=_f("bb_upper"), bb_lower=_f("bb_lower"),
                rsi=_f("rsi_14"),
                macd_line=_f("macd_line"), macd_signal=_f("macd_signal"), macd_hist=_f("macd_hist"),
                stoch_k=_f("stoch_k"), stoch_d=_f("stoch_d"), adx_14=_f("adx_14"),
                daily_sma_20=_f("daily_sma_20"), daily_sma_50=_f("daily_sma_50"),
                daily_sma_200=_f("daily_sma_200"),
                high_52w=_f("high_52w"), low_52w=_f("low_52w"),
                market_cap=_f("market_cap"), float_shares=_f("float_shares"),
                security_type=raw.get("security_type"), sector=raw.get("sector"), industry=raw.get("industry"),
                market_session=current_market_session,
                sma_8_5m=_f("sma_8_5m"), sma_20_5m=_f("sma_20_5m"),
                macd_line_5m=_f("macd_line_5m"), macd_signal_5m=_f("macd_signal_5m"),
                stoch_k_5m=_f("stoch_k_5m"), stoch_d_5m=_f("stoch_d_5m"),
                prev_bar_high_5m=_f("prev_bar_high_5m"), prev_bar_low_5m=_f("prev_bar_low_5m"),
                cur_bar_high_5m=_f("cur_bar_high_5m"), cur_bar_low_5m=_f("cur_bar_low_5m"),
                prev_bar_high_10m=_f("prev_bar_high_10m"), prev_bar_low_10m=_f("prev_bar_low_10m"),
                cur_bar_high_10m=_f("cur_bar_high_10m"), cur_bar_low_10m=_f("cur_bar_low_10m"),
                prev_bar_high_15m=_f("prev_bar_high_15m"), prev_bar_low_15m=_f("prev_bar_low_15m"),
                cur_bar_high_15m=_f("cur_bar_high_15m"), cur_bar_low_15m=_f("cur_bar_low_15m"),
                prev_bar_high_30m=_f("prev_bar_high_30m"), prev_bar_low_30m=_f("prev_bar_low_30m"),
                cur_bar_high_30m=_f("cur_bar_high_30m"), cur_bar_low_30m=_f("cur_bar_low_30m"),
                prev_bar_high_60m=_f("prev_bar_high_60m"), prev_bar_low_60m=_f("prev_bar_low_60m"),
                cur_bar_high_60m=_f("cur_bar_high_60m"), cur_bar_low_60m=_f("cur_bar_low_60m"),
                volatility=vol, daily_extremes=ext,
            )
        except Exception:
            return None

    async def _enriched_loop(self):
        while self.running:
            await asyncio.sleep(30)
            await self._refresh_enriched_cache()

    async def _cleanup_loop(self):
        while self.running:
            await asyncio.sleep(300)
            self.state_cache.cleanup_old()
            active = set(self.state_cache._states.keys())
            for d in self.detectors:
                d.cleanup_old_symbols(active)

    async def _stats_loop(self):
        while self.running:
            await asyncio.sleep(30)
            ticks = self._stats["ticks"]
            alerts = self._stats["alerts"]
            delta_ticks = ticks - self._stats["last_ticks"]
            delta_alerts = alerts - self._stats["last_alerts"]
            self._stats["last_ticks"] = ticks
            self._stats["last_alerts"] = alerts
            tps = delta_ticks / 30.0
            aps = delta_alerts / 30.0
            tt = self._stats["tick_times"]
            if tt:
                tt_sorted = sorted(tt)
                p50 = tt_sorted[len(tt_sorted) // 2]
                p99 = tt_sorted[int(len(tt_sorted) * 0.99)]
                logger.info(
                    f"[P{PARTITION_ID}] ticks/s={tps:.0f} alerts/s={aps:.0f} "
                    f"p50={p50:.1f}ms p99={p99:.1f}ms "
                    f"total_ticks={ticks} total_alerts={alerts} "
                    f"symbols={len(self.state_cache._states)}"
                )
            else:
                logger.info(f"[P{PARTITION_ID}] ticks/s={tps:.0f} alerts/s={aps:.0f} total={ticks}/{alerts}")


async def main():
    global redis_client, event_bus, engine
    logger.info("Starting Alert Engine Service...")
    redis_client = RedisClient()
    await redis_client.connect()
    logger.info("Redis connected")
    await check_initial_market_status()
    event_bus = EventBus(redis_client, "alert_engine")
    event_bus.subscribe(BusEventType.DAY_CHANGED, handle_day_changed)
    event_bus.subscribe(BusEventType.SESSION_CHANGED, handle_session_changed)
    await event_bus.start_listening()
    logger.info("EventBus initialized")
    baseline_loader = None
    alert_writer = None
    try:
        from shared.utils.timescale_client import TimescaleClient
        ts_client = TimescaleClient()
        await ts_client.connect(min_size=2, max_size=5)
        logger.info("TimescaleDB connected")
        baseline_loader = BaselineLoader(ts_client, redis_client.client)
        all_keys = await redis_client.client.hkeys("snapshot:enriched:latest")
        symbols = [k.decode() if isinstance(k, bytes) else k for k in all_keys if k not in (b"__meta__", "__meta__")]
        if symbols:
            await baseline_loader.load_all(symbols, current_trading_date)
            logger.info(f"Baselines loaded for {len(symbols)} symbols")
        alert_writer = AlertWriter(ts_client)
        logger.info(f"AlertWriter enabled on partition {PARTITION_ID} (COPY protocol)")
    except Exception as e:
        logger.warning(f"TimescaleDB unavailable, no baselines: {e}")
    engine = AlertEngine(redis_client, baseline_loader=baseline_loader, alert_writer=alert_writer)
    loop = asyncio.get_event_loop()
    for sig_name in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig_name, lambda: asyncio.create_task(engine.stop()))
    await engine.start()


if __name__ == "__main__":
    asyncio.run(main())
