"""
Baseline Loader - Pre-market job that computes historical baselines.

Loads from TimescaleDB:
  1. Daily extremes (high/low/close) for lookback-based alerts
  2. Volatility baselines (sigma of 1m/5m/15m price changes)

Stores in Redis hashes with 24h TTL.
"""

import asyncio
import json
import logging
import math
import time
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from models.alert_state import DailyExtreme, VolatilityBaseline

logger = logging.getLogger("alert-engine.baseline")

MAX_LOOKBACK_DAYS = 366
VOLATILITY_DAILY_LOOKBACK = 252
VOLATILITY_INTRADAY_LOOKBACK = 10


def _std(values: list) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)


class BaselineLoader:

    def __init__(self, timescale_client, raw_redis):
        self.ts = timescale_client
        self.redis = raw_redis
        self._extremes_cache: Dict[str, List[DailyExtreme]] = {}
        self._volatility_cache: Dict[str, VolatilityBaseline] = {}

    async def load_all(self, symbols: List[str], trading_date: Optional[date] = None) -> Dict[str, int]:
        if not trading_date:
            trading_date = date.today()

        t0 = time.monotonic()
        stats = {"symbols": len(symbols), "extremes_loaded": 0, "volatility_loaded": 0, "errors": 0}

        batch_size = 200
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            tasks = [self._load_symbol(sym, trading_date) for sym in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for sym, result in zip(batch, results):
                if isinstance(result, Exception):
                    stats["errors"] += 1
                else:
                    has_ext, has_vol = result
                    if has_ext:
                        stats["extremes_loaded"] += 1
                    if has_vol:
                        stats["volatility_loaded"] += 1

        elapsed = time.monotonic() - t0
        logger.info(
            f"Baseline load: {stats['extremes_loaded']} extremes, "
            f"{stats['volatility_loaded']} volatility in {elapsed:.1f}s"
        )

        try:
            await self.redis.set("baseline:last_loaded", datetime.utcnow().isoformat())
        except Exception:
            pass

        return stats

    async def _load_symbol(self, symbol: str, trading_date: date) -> Tuple[bool, bool]:
        has_ext = await self._load_daily_extremes(symbol, trading_date)
        has_vol = await self._load_volatility(symbol, trading_date)
        return has_ext, has_vol

    async def _load_daily_extremes(self, symbol: str, trading_date: date) -> bool:
        try:
            start_date = trading_date - timedelta(days=MAX_LOOKBACK_DAYS + 30)
            rows = await self.ts.fetch(
                """
                SELECT trading_date, high, low, close
                FROM market_data_daily
                WHERE symbol = $1 AND trading_date >= $2 AND trading_date < $3
                ORDER BY trading_date DESC LIMIT $4
                """,
                symbol, start_date, trading_date, MAX_LOOKBACK_DAYS
            )
            if not rows:
                return False

            extremes: List[DailyExtreme] = []
            redis_data = {}
            for i, row in enumerate(rows):
                td = row["trading_date"]
                if isinstance(td, datetime):
                    td = td.date()
                ext = DailyExtreme(
                    trading_date=td, days_ago=i + 1,
                    high=float(row["high"]), low=float(row["low"]), close=float(row["close"]),
                )
                extremes.append(ext)
                redis_data[td.isoformat()] = json.dumps({"h": ext.high, "l": ext.low, "c": ext.close, "d": ext.days_ago})

            self._extremes_cache[symbol] = extremes
            if redis_data:
                key = f"baseline:daily_extremes:{symbol}"
                await self.redis.delete(key)
                await self.redis.hset(key, mapping=redis_data)
                await self.redis.expire(key, 86400)
            return True
        except Exception as e:
            logger.debug(f"Daily extremes failed for {symbol}: {e}")
            return False

    async def _load_volatility(self, symbol: str, trading_date: date) -> bool:
        try:
            vol_data = await self._compute_intraday_volatility(symbol, trading_date)
            daily_vol = await self._compute_daily_volatility(symbol, trading_date)
            avg_daily_volume = await self._compute_avg_daily_volume(symbol, trading_date)

            if vol_data is None and daily_vol is None:
                return False

            baseline = VolatilityBaseline(
                intraday_vol_1m=vol_data[0] if vol_data else 0.0,
                intraday_vol_5m=vol_data[1] if vol_data else 0.0,
                intraday_vol_15m=vol_data[2] if vol_data else 0.0,
                daily_vol_annual=daily_vol if daily_vol else 0.0,
                avg_dollar_move_1m=vol_data[3] if vol_data else 0.0,
                avg_daily_volume=avg_daily_volume or 0.0,
            )
            self._volatility_cache[symbol] = baseline

            key = f"baseline:volatility:{symbol}"
            await self.redis.hset(key, mapping={
                "vol_1m": str(baseline.intraday_vol_1m),
                "vol_5m": str(baseline.intraday_vol_5m),
                "vol_15m": str(baseline.intraday_vol_15m),
                "vol_daily": str(baseline.daily_vol_annual),
                "avg_move_1m": str(baseline.avg_dollar_move_1m),
                "avg_daily_vol": str(baseline.avg_daily_volume),
            })
            await self.redis.expire(key, 86400)
            return True
        except Exception as e:
            logger.debug(f"Volatility failed for {symbol}: {e}")
            return False

    async def _compute_intraday_volatility(self, symbol, trading_date):
        start = trading_date - timedelta(days=VOLATILITY_INTRADAY_LOOKBACK + 5)
        start_ms = int(datetime.combine(start, datetime.min.time()).timestamp() * 1000)
        end_ms = int(datetime.combine(trading_date, datetime.min.time()).timestamp() * 1000)
        rows = await self.ts.fetch(
            "SELECT ts, close FROM minute_bars WHERE symbol = $1 AND ts >= $2 AND ts < $3 AND close > 0 ORDER BY ts ASC",
            symbol, start_ms, end_ms
        )
        if not rows or len(rows) < 30:
            return None

        closes = [float(r["close"]) for r in rows]
        log_ret_1m, dollar_moves = [], []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0:
                log_ret_1m.append(math.log(closes[i] / closes[i - 1]))
                dollar_moves.append(abs(closes[i] - closes[i - 1]))
        if len(log_ret_1m) < 20:
            return None

        vol_1m = _std(log_ret_1m)
        avg_move = sum(dollar_moves) / len(dollar_moves) if dollar_moves else 0.0

        log_ret_5m = [math.log(closes[i] / closes[i - 5]) for i in range(5, len(closes), 5) if closes[i - 5] > 0]
        vol_5m = _std(log_ret_5m) if len(log_ret_5m) >= 10 else vol_1m * math.sqrt(5)

        log_ret_15m = [math.log(closes[i] / closes[i - 15]) for i in range(15, len(closes), 15) if closes[i - 15] > 0]
        vol_15m = _std(log_ret_15m) if len(log_ret_15m) >= 5 else vol_1m * math.sqrt(15)

        return (vol_1m, vol_5m, vol_15m, avg_move)

    async def _compute_daily_volatility(self, symbol, trading_date):
        start = trading_date - timedelta(days=VOLATILITY_DAILY_LOOKBACK + 60)
        rows = await self.ts.fetch(
            "SELECT close FROM market_data_daily WHERE symbol = $1 AND trading_date >= $2 AND trading_date < $3 AND close > 0 ORDER BY trading_date ASC",
            symbol, start, trading_date
        )
        if not rows or len(rows) < 20:
            return None
        closes = [float(r["close"]) for r in rows]
        log_ret = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
        if len(log_ret) < 20:
            return None
        return _std(log_ret) * math.sqrt(252)

    async def _compute_avg_daily_volume(self, symbol, trading_date):
        start = trading_date - timedelta(days=40)
        row = await self.ts.fetchrow(
            "SELECT AVG(volume) as avg_vol FROM market_data_daily WHERE symbol = $1 AND trading_date >= $2 AND trading_date < $3 AND volume > 0",
            symbol, start, trading_date
        )
        return float(row["avg_vol"]) if row and row["avg_vol"] else None

    def get_daily_extremes(self, symbol: str) -> Optional[List[DailyExtreme]]:
        return self._extremes_cache.get(symbol)

    def get_volatility(self, symbol: str) -> Optional[VolatilityBaseline]:
        return self._volatility_cache.get(symbol)

    def get_max_high(self, symbol: str, lookback_days: int) -> Optional[float]:
        extremes = self._extremes_cache.get(symbol)
        if not extremes:
            return None
        relevant = [e for e in extremes if e.days_ago <= lookback_days]
        return max(e.high for e in relevant) if relevant else None

    def get_min_low(self, symbol: str, lookback_days: int) -> Optional[float]:
        extremes = self._extremes_cache.get(symbol)
        if not extremes:
            return None
        relevant = [e for e in extremes if e.days_ago <= lookback_days]
        return min(e.low for e in relevant) if relevant else None

    def get_max_high_for_all_lookbacks(self, symbol: str) -> Dict[int, float]:
        """Pre-compute max high for all lookback windows (1..90 days)."""
        extremes = self._extremes_cache.get(symbol)
        if not extremes:
            return {}
        sorted_ext = sorted(extremes, key=lambda e: e.days_ago)
        result = {}
        running_max = float('-inf')
        for ext in sorted_ext:
            running_max = max(running_max, ext.high)
            result[ext.days_ago] = running_max
        return result

    def get_min_low_for_all_lookbacks(self, symbol: str) -> Dict[int, float]:
        """Pre-compute min low for all lookback windows (1..90 days)."""
        extremes = self._extremes_cache.get(symbol)
        if not extremes:
            return {}
        sorted_ext = sorted(extremes, key=lambda e: e.days_ago)
        result = {}
        running_min = float('inf')
        for ext in sorted_ext:
            running_min = min(running_min, ext.low)
            result[ext.days_ago] = running_min
        return result
