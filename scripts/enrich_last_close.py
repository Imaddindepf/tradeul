#!/usr/bin/env python3
"""
enrich_last_close.py — Enrich snapshot:enriched:last_close with intraday indicators.

Reads last trading day's minute bars from TimescaleDB, feeds them through
BarEngine in batches to compute RSI, EMA, SMA, MACD, BB, ATR, ADX, Stoch,
and merges the results into the existing last_close snapshot in Redis.

Run inside the analytics container (needs talipp + bar_engine):
  docker cp scripts/enrich_last_close.py tradeul_analytics:/app/scripts/
  docker exec tradeul_analytics python3 /app/scripts/enrich_last_close.py
"""
import asyncio
import gc
import os
import sys
import time
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

try:
    import orjson
    dumps = lambda o: orjson.dumps(o).decode()
    loads = orjson.loads
except ImportError:
    import json
    dumps = lambda o: json.dumps(o, default=str)
    loads = json.loads

import asyncpg
import redis.asyncio as aioredis

sys.path.insert(0, "/app")
from bar_engine import BarEngine

NY = ZoneInfo("America/New_York")
LAST_CLOSE_KEY = "snapshot:enriched:last_close"
LAST_CLOSE_TTL = 604800
ATR_DAILY_KEY = "atr:daily"

BATCH_SIZE = 3000  # Symbols per BarEngine batch (memory-safe)


def get_last_trading_day() -> date:
    today = datetime.now(NY).date()
    d = today
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    if d == today and datetime.now(NY).hour < 4:
        d -= timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    return d


def extract_indicators(engine: BarEngine, sym: str) -> dict:
    """Extract all indicator values from BarEngine for a symbol."""
    result = {}
    indicators = engine.get_indicators(sym)
    if indicators is None:
        return result
    
    result['rsi_14'] = indicators.rsi_14
    result['ema_9'] = indicators.ema_9
    result['ema_20'] = indicators.ema_20
    result['ema_50'] = indicators.ema_50
    result['sma_5'] = indicators.sma_5
    result['sma_8'] = indicators.sma_8
    result['sma_20'] = indicators.sma_20
    result['sma_50'] = indicators.sma_50
    result['sma_200'] = indicators.sma_200
    result['macd_line'] = indicators.macd_line
    result['macd_signal'] = indicators.macd_signal
    result['macd_hist'] = indicators.macd_hist
    result['bb_upper'] = indicators.bb_upper
    result['bb_mid'] = indicators.bb_mid
    result['bb_lower'] = indicators.bb_lower
    result['atr_14'] = indicators.atr_14
    result['adx_14'] = indicators.adx_14
    result['stoch_k'] = indicators.stoch_k
    result['stoch_d'] = indicators.stoch_d
    result['chg_1min'] = indicators.chg_1m
    result['chg_5min'] = indicators.chg_5m
    result['chg_10min'] = indicators.chg_10m
    result['chg_15min'] = indicators.chg_15m
    result['chg_30min'] = indicators.chg_30m
    result['chg_60min'] = indicators.chg_60m
    result['vol_1min'] = indicators.vol_1m
    result['vol_5min'] = indicators.vol_5m
    result['vol_10min'] = indicators.vol_10m
    result['vol_15min'] = indicators.vol_15m
    result['vol_30min'] = indicators.vol_30m
    result['vol_60min'] = indicators.vol_60m
    
    if indicators.tf:
        for tf_period, tf_ind in indicators.tf.items():
            suffix = f"_{tf_period}m"
            for key, val in tf_ind.items():
                if key != 'bar_count' and val is not None:
                    result[key + suffix] = val
    
    return result


async def load_bars_for_symbols(pool, symbols: list, ts_start: int, ts_end: int) -> dict:
    """Load minute bars from TimescaleDB for a batch of symbols."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT symbol, ts, open, high, low, close, volume
            FROM minute_bars
            WHERE symbol = ANY($1) AND ts >= $2 AND ts <= $3
            ORDER BY symbol, ts ASC
            """,
            symbols, ts_start, ts_end
        )
    
    bars_by_symbol = {}
    for row in rows:
        sym = row['symbol']
        if sym not in bars_by_symbol:
            bars_by_symbol[sym] = []
        bars_by_symbol[sym].append({
            'ts': row['ts'],
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
            'volume': int(row['volume']),
            'av': 0,
            'vw': 0,
        })
    
    # Compute accumulated volume
    for sym, bars in bars_by_symbol.items():
        cumvol = 0
        for bar in bars:
            cumvol += bar['volume']
            bar['av'] = cumvol
    
    return bars_by_symbol


async def main():
    t0 = time.time()
    
    redis_pwd = os.environ.get("REDIS_PASSWORD", "")
    redis_url = os.environ.get("REDIS_URL", f"redis://:{redis_pwd}@redis:6379")
    r = aioredis.from_url(redis_url, decode_responses=False)
    await r.ping()
    
    db_host = os.environ.get("POSTGRES_HOST", os.environ.get("DB_HOST", "timescaledb"))
    db_port = int(os.environ.get("POSTGRES_PORT", os.environ.get("DB_PORT", "5432")))
    db_name = os.environ.get("POSTGRES_DB", os.environ.get("DB_NAME", "tradeul"))
    db_user = os.environ.get("POSTGRES_USER", os.environ.get("DB_USER", "tradeul_user"))
    db_pass = os.environ.get("POSTGRES_PASSWORD", os.environ.get("DB_PASSWORD", ""))
    
    pool = await asyncpg.create_pool(
        host=db_host, port=db_port, database=db_name,
        user=db_user, password=db_pass, min_size=2, max_size=5
    )
    print(f"[1/7] Connected to Redis + TimescaleDB")
    
    trading_day = get_last_trading_day()
    day_start = datetime(trading_day.year, trading_day.month, trading_day.day, 4, 0, tzinfo=NY)
    day_end = datetime(trading_day.year, trading_day.month, trading_day.day, 20, 0, tzinfo=NY)
    ts_start = int(day_start.timestamp() * 1000)
    ts_end = int(day_end.timestamp() * 1000)
    print(f"[2/7] Trading day: {trading_day} ({day_start.strftime('%Y-%m-%d %H:%M %Z')} → {day_end.strftime('%H:%M %Z')})")
    
    # Get all symbols that have bars
    async with pool.acquire() as conn:
        all_symbols_rows = await conn.fetch(
            "SELECT DISTINCT symbol FROM minute_bars WHERE ts >= $1 AND ts <= $2",
            ts_start, ts_end
        )
    all_symbols = [row['symbol'] for row in all_symbols_rows]
    print(f"[3/7] Found {len(all_symbols):,} symbols with minute bars")
    
    # ATR cache
    atr_cache = {}
    try:
        atr_raw = await r.hgetall(ATR_DAILY_KEY)
        for sym_bytes, val_bytes in atr_raw.items():
            sym = sym_bytes.decode() if isinstance(sym_bytes, bytes) else sym_bytes
            try:
                atr_cache[sym] = loads(val_bytes)
            except Exception:
                pass
        print(f"[3.5/7] ATR cache: {len(atr_cache):,} symbols")
    except Exception as e:
        print(f"[3.5/7] WARNING: ATR cache unavailable: {e}")
    
    # Trades anomaly data from volume_slots
    trades_data = {}
    try:
        hist_start = trading_day - timedelta(days=10)
        async with pool.acquire() as conn:
            today_rows = await conn.fetch(
                "SELECT symbol, SUM(trades_count) as total FROM volume_slots WHERE date = $1 GROUP BY symbol",
                trading_day
            )
            trades_today_map = {row['symbol']: int(row['total']) for row in today_rows}
            
            hist_rows = await conn.fetch("""
                SELECT symbol, AVG(dt) as avg_t, STDDEV(dt) as std_t
                FROM (
                    SELECT symbol, date, SUM(trades_count) as dt
                    FROM volume_slots WHERE date >= $1 AND date < $2
                    GROUP BY symbol, date
                ) sub GROUP BY symbol
            """, hist_start, trading_day)
            hist_map = {row['symbol']: (float(row['avg_t']), float(row['std_t'] or 0)) for row in hist_rows}
        
        for sym, trades in trades_today_map.items():
            avg, std = hist_map.get(sym, (0, 0))
            z = (trades - avg) / std if std > 0 else 0
            trades_data[sym] = {
                'trades_today': trades,
                'avg_trades_5d': round(avg, 0) if avg else None,
                'trades_z_score': round(z, 2),
                'is_trade_anomaly': z > 3.0,
            }
        print(f"[3.6/7] Trades anomaly: {len(trades_data):,} symbols")
    except Exception as e:
        print(f"[3.6/7] WARNING: Trades data unavailable: {e}")
    
    # Process in batches
    indicator_results = {}  # sym -> {indicator_name: value}
    total_batches = (len(all_symbols) + BATCH_SIZE - 1) // BATCH_SIZE
    
    for batch_idx in range(total_batches):
        start_i = batch_idx * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, len(all_symbols))
        batch_symbols = all_symbols[start_i:end_i]
        
        bt0 = time.time()
        bars_by_symbol = await load_bars_for_symbols(pool, batch_symbols, ts_start, ts_end)
        
        engine = BarEngine(ring_size=210)
        warmed = 0
        for sym, bars in bars_by_symbol.items():
            if len(bars) >= 5:
                engine.warmup(sym, bars)
                warmed += 1
        engine.warmup_complete()
        
        for sym in bars_by_symbol:
            if engine.has_data(sym):
                ind = extract_indicators(engine, sym)
                if ind:
                    indicator_results[sym] = ind
        
        del engine
        del bars_by_symbol
        gc.collect()
        
        bt = time.time() - bt0
        print(f"  Batch {batch_idx+1}/{total_batches}: {warmed:,} symbols, {len(indicator_results):,} enriched ({bt:.1f}s)")
    
    print(f"[4/7] BarEngine computed indicators for {len(indicator_results):,} symbols")
    
    # Read current last_close
    all_data = await r.hgetall(LAST_CLOSE_KEY)
    if not all_data:
        print("[FAIL] No last_close data in Redis")
        return 1
    
    meta_key = b"__meta__" if b"__meta__" in all_data else "__meta__"
    meta_raw = all_data.pop(meta_key, None)
    ticker_count = len(all_data)
    print(f"[5/7] Read last_close: {ticker_count:,} tickers")
    
    # Merge indicators
    enriched_count = 0
    updated = {}
    
    for sym_raw, val_raw in all_data.items():
        sym = sym_raw.decode() if isinstance(sym_raw, bytes) else sym_raw
        
        try:
            ticker_data = loads(val_raw)
        except Exception:
            updated[sym_raw] = val_raw
            continue
        
        modified = False
        
        if sym in indicator_results:
            ind = indicator_results[sym]
            
            for key, val in ind.items():
                ticker_data[key] = val
            
            # ATR from BarEngine
            atr_val = ind.get('atr_14')
            if atr_val is not None:
                ticker_data['atr'] = round(atr_val, 4)
                price = ticker_data.get('price') or ticker_data.get('current_price')
                if price and price > 0:
                    ticker_data['atr_percent'] = round(atr_val / price * 100, 2)
            
            modified = True
            enriched_count += 1
        
        # ATR fallback from daily cache
        if ticker_data.get('atr') is None and sym in atr_cache:
            atr_entry = atr_cache[sym]
            if isinstance(atr_entry, dict):
                ticker_data['atr'] = atr_entry.get('atr')
                ticker_data['atr_percent'] = atr_entry.get('atr_percent')
                modified = True
        
        # Trades anomaly data from volume_slots
        if sym in trades_data:
            td = trades_data[sym]
            ticker_data['trades_today'] = td['trades_today']
            ticker_data['avg_trades_5d'] = td['avg_trades_5d']
            ticker_data['trades_z_score'] = td['trades_z_score']
            ticker_data['is_trade_anomaly'] = td['is_trade_anomaly']
            modified = True
        
        # rvol_slot mirrors rvol (scanner uses them interchangeably)
        rvol_val = ticker_data.get('rvol')
        if rvol_val is not None:
            ticker_data['rvol_slot'] = rvol_val
            modified = True
        
        updated[sym_raw] = dumps(ticker_data) if modified else val_raw
    
    print(f"[6/7] Enriched {enriched_count:,} / {ticker_count:,} tickers")
    
    # Write back atomically
    meta_json = dumps({
        "timestamp": datetime.now().isoformat(),
        "count": ticker_count,
        "changed": enriched_count,
        "version": 2,
        "source": "enrich_last_close.py",
        "trading_day": str(trading_day),
    })
    
    tmp_key = f"{LAST_CLOSE_KEY}:_enrich_tmp"
    pipe = r.pipeline()
    syms = list(updated.keys())
    for i in range(0, len(syms), 500):
        batch = {s: updated[s] for s in syms[i:i + 500]}
        pipe.hset(tmp_key, mapping=batch)
    pipe.hset(tmp_key, "__meta__", meta_json)
    pipe.expire(tmp_key, LAST_CLOSE_TTL)
    await pipe.execute()
    
    await r.rename(tmp_key, LAST_CLOSE_KEY)
    final_count = await r.hlen(LAST_CLOSE_KEY)
    final_ttl = await r.ttl(LAST_CLOSE_KEY)
    
    elapsed = time.time() - t0
    print(f"[7/7] DONE — {final_count:,} fields, TTL={final_ttl}s ({round(final_ttl/86400,1)}d), {elapsed:.1f}s")
    
    # Verify
    for check_sym in ['AAPL', 'TSLA', 'NVDA']:
        sample_raw = await r.hget(LAST_CLOSE_KEY, check_sym)
        if sample_raw:
            sample = loads(sample_raw)
            fields = ['rsi_14', 'ema_9', 'ema_50', 'atr', 'atr_percent', 'chg_1min', 'vol_1min', 'sma_20', 'macd_line', 'adx_14', 'rvol_slot', 'trades_today', 'avg_trades_5d', 'trades_z_score']
            vals = [f"{f}={'OK' if sample.get(f) is not None else 'None'}" for f in fields]
            print(f"  {check_sym}: {', '.join(vals)}")
    
    await pool.close()
    await r.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
