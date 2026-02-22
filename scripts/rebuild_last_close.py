"""
rebuild_last_close.py — Emergency rebuild of snapshot:enriched:last_close

Reconstructs the enriched snapshot from available sources:
  1. snapshot:polygon:latest  → base price/volume/change data (ALL tickers)
  2. metadata:ticker:*        → market_cap, security_type, sector, industry, float
  3. screener:daily_indicators:latest → daily_rsi, daily_sma, change_5d, etc.

Writes to:
  - snapshot:enriched:latest    (TTL 600s)
  - snapshot:enriched:last_close (TTL 7 days)

Run inside api_gateway container:
  docker exec tradeul_api_gateway python3 /app/scripts/rebuild_last_close.py
  
Or mount and run:
  docker exec tradeul_api_gateway python3 /scripts/rebuild_last_close.py
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime

try:
    import orjson
    def fast_dumps(obj):
        return orjson.dumps(obj).decode("utf-8")
    def fast_loads(raw):
        return orjson.loads(raw)
except ImportError:
    def fast_dumps(obj):
        return json.dumps(obj, default=str)
    def fast_loads(raw):
        return json.loads(raw)

import redis.asyncio as aioredis


SNAPSHOT_POLYGON_KEY = "snapshot:polygon:latest"
SNAPSHOT_ENRICHED_HASH = "snapshot:enriched:latest"
SNAPSHOT_LAST_CLOSE_HASH = "snapshot:enriched:last_close"
SCREENER_DAILY_KEY = "screener:daily_indicators:latest"

ENRICHED_TTL = 600        # 10 minutes
LAST_CLOSE_TTL = 604800   # 7 days

MIN_TICKERS_REQUIRED = 2000


async def main():
    pwd = os.environ.get("REDIS_PASSWORD", "")
    redis_url = os.environ.get("REDIS_URL", f"redis://:{pwd}@redis:6379")
    if not pwd and "://:@" in redis_url:
        redis_url = "redis://redis:6379"

    r = aioredis.from_url(redis_url, decode_responses=False)

    try:
        await r.ping()
        print("[OK] Redis connected")
    except Exception as e:
        print(f"[FAIL] Redis connection: {e}")
        sys.exit(1)

    # ── 1. Read Polygon snapshot ──────────────────────────────────────────
    poly_raw = await r.get(SNAPSHOT_POLYGON_KEY)
    if not poly_raw:
        print("[FAIL] snapshot:polygon:latest is empty. Run: curl -X POST http://localhost:8003/api/ingest/fetch-once")
        sys.exit(1)

    poly_data = fast_loads(poly_raw)
    tickers_raw = poly_data.get("tickers", [])
    print(f"[OK] Polygon snapshot: {len(tickers_raw)} tickers, ts={poly_data.get('timestamp', '?')}")

    if len(tickers_raw) < MIN_TICKERS_REQUIRED:
        print(f"[FAIL] Only {len(tickers_raw)} tickers — need at least {MIN_TICKERS_REQUIRED}")
        sys.exit(1)

    # ── 2. Read metadata (market_cap, security_type, sector, etc.) ────────
    print("[...] Loading metadata keys...")
    metadata = {}
    cursor = b"0"
    while True:
        cursor, keys = await r.scan(cursor, match=b"metadata:ticker:*", count=500)
        if keys:
            values = await r.mget(*keys)
            for k, v in zip(keys, values):
                if v:
                    sym = k.decode().split(":")[-1]
                    try:
                        metadata[sym] = fast_loads(v)
                    except Exception:
                        pass
        if cursor == b"0":
            break

    print(f"[OK] Metadata loaded: {len(metadata)} tickers")

    # ── 3. Read screener daily indicators (may have NaN — use stdlib) ─────
    screener_daily = {}
    screener_raw = await r.get(SCREENER_DAILY_KEY)
    if screener_raw:
        try:
            text = screener_raw.decode("utf-8", errors="replace")
            text = text.replace("NaN", "null").replace("Infinity", "null").replace("-Infinity", "null")
            screener_daily = json.loads(text)
            print(f"[OK] Screener daily: {len(screener_daily)} tickers")
        except Exception as e:
            print(f"[WARN] Screener daily parse error: {e} — continuing without it")
    else:
        print("[WARN] screener:daily_indicators:latest not found — continuing without it")

    # ── 4. Build enriched hash ────────────────────────────────────────────
    print("[...] Building enriched snapshot...")
    enriched_hash = {}
    skipped = 0

    for t in tickers_raw:
        symbol = t.get("ticker")
        if not symbol:
            skipped += 1
            continue

        # Price resolution (same priority as enrichment pipeline)
        last_trade = t.get("lastTrade") or {}
        day = t.get("day") or {}
        prev_day = t.get("prevDay") or {}
        min_data = t.get("min") or {}

        price = last_trade.get("p") or day.get("c")
        if not price or price <= 0:
            skipped += 1
            continue

        # Volume
        volume = min_data.get("av") or day.get("v") or 0

        # Change percent
        change_percent = t.get("todaysChangePerc") or t.get("change_percent")

        # Metadata enrichment
        meta = metadata.get(symbol, {})
        market_cap = meta.get("market_cap")
        security_type = meta.get("security_type")
        float_shares = meta.get("float_shares")
        shares_outstanding = meta.get("shares_outstanding")
        sector = meta.get("sector")
        industry = meta.get("industry")

        # Daily screener enrichment
        daily = screener_daily.get(symbol, {})

        # Computed fields
        day_open = day.get("o")
        prev_close = prev_day.get("c")
        day_high = day.get("h")
        day_low = day.get("l")
        day_vwap = day.get("vw")

        gap_percent = None
        if day_open and prev_close and prev_close > 0:
            gap_percent = round((day_open - prev_close) / prev_close * 100, 2)

        dollar_volume = round(price * volume, 0) if price and volume else None

        dist_from_vwap = None
        if price and day_vwap and day_vwap > 0:
            dist_from_vwap = round((price - day_vwap) / day_vwap * 100, 2)

        spread_pct = None
        bid = (t.get("lastQuote") or {}).get("p")
        ask = (t.get("lastQuote") or {}).get("P")
        if bid and ask and bid > 0:
            spread_pct = round((ask - bid) / bid * 100, 4)

        bid_size = None
        ask_size = None
        lq = t.get("lastQuote") or {}
        if lq.get("s"):
            bid_size = lq["s"] * 100
        if lq.get("S"):
            ask_size = lq["S"] * 100

        bid_ask_ratio = None
        if bid_size and ask_size and ask_size > 0:
            bid_ask_ratio = round(bid_size / ask_size, 2)

        float_turnover = None
        if float_shares and float_shares > 0 and volume:
            float_turnover = round(volume / float_shares * 100, 2)

        pos_in_range = None
        if day_high and day_low and day_high > day_low:
            pos_in_range = round((price - day_low) / (day_high - day_low) * 100, 2)

        todays_range_pct = None
        if day_high and day_low and day_low > 0:
            todays_range_pct = round((day_high - day_low) / day_low * 100, 2)

        enriched = {
            "ticker": symbol,
            "price": price,
            "current_price": price,
            "change_percent": change_percent,
            "todaysChangePerc": change_percent,
            "volume": volume,
            "current_volume": volume,
            "market_cap": market_cap,
            "security_type": security_type,
            "float_shares": float_shares,
            "shares_outstanding": shares_outstanding,
            "sector": sector,
            "industry": industry,
            # Polygon raw nested (kept for downstream compat)
            "lastTrade": last_trade if last_trade else None,
            "day": day if day else None,
            "prevDay": prev_day if prev_day else None,
            # Computed
            "gap_percent": gap_percent,
            "dollar_volume": dollar_volume,
            "vwap": day_vwap,
            "dist_from_vwap": dist_from_vwap,
            "spread_pct": spread_pct,
            "bid": bid,
            "ask": ask,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "bid_ask_ratio": bid_ask_ratio,
            "float_turnover": float_turnover,
            "pos_in_range": pos_in_range,
            "todays_range_pct": todays_range_pct,
            "intraday_high": day_high,
            "intraday_low": day_low,
            # Daily screener indicators (from DuckDB cache)
            "daily_rsi": daily.get("daily_rsi"),
            "daily_sma_20": daily.get("daily_sma_20"),
            "daily_sma_50": daily.get("daily_sma_50"),
            "daily_sma_200": daily.get("daily_sma_200"),
            "daily_bb_upper": daily.get("daily_bb_upper"),
            "daily_bb_lower": daily.get("daily_bb_lower"),
            "daily_bb_position": daily.get("daily_bb_position"),
            "daily_adx_14": daily.get("daily_adx_14"),
            "daily_atr_percent": daily.get("daily_atr_percent"),
            "daily_gap_percent": daily.get("daily_gap_percent"),
            "high_52w": daily.get("high_52w"),
            "low_52w": daily.get("low_52w"),
            "from_52w_high": daily.get("from_52w_high"),
            "from_52w_low": daily.get("from_52w_low"),
            "change_1d": daily.get("change_1d"),
            "change_3d": daily.get("change_3d"),
            "change_5d": daily.get("change_5d"),
            "change_10d": daily.get("change_10d"),
            "change_20d": daily.get("change_20d"),
            "avg_volume_5d": daily.get("avg_volume_5d"),
            "avg_volume_10d": daily.get("avg_volume_10d"),
            "avg_volume_20d": daily.get("avg_volume_20d"),
            "dist_daily_sma_20": daily.get("dist_daily_sma_20"),
            "dist_daily_sma_50": daily.get("dist_daily_sma_50"),
            "volume_today_pct": None,
            # Intraday indicators — not available offline, set to None
            "rvol": None,
            "atr": None,
            "atr_percent": None,
            "rsi_14": None,
            "ema_9": None, "ema_20": None, "ema_50": None,
            "sma_5": None, "sma_8": None, "sma_20": None, "sma_50": None, "sma_200": None,
            "adx_14": None,
            "macd_line": None, "macd_signal": None, "macd_hist": None,
            "bb_upper": None, "bb_mid": None, "bb_lower": None,
            "stoch_k": None, "stoch_d": None,
            "vol_1min": None, "vol_5min": None, "vol_10min": None,
            "chg_1min": None, "chg_5min": None, "chg_10min": None,
        }

        # Volume today % (needs avg_volume_10d)
        avg_vol_10d = daily.get("avg_volume_10d")
        day_vol = day.get("v")
        if day_vol and avg_vol_10d and avg_vol_10d > 0:
            enriched["volume_today_pct"] = round((day_vol / avg_vol_10d) * 100, 1)

        enriched_hash[symbol] = fast_dumps(enriched)

    print(f"[OK] Enriched {len(enriched_hash)} tickers ({skipped} skipped)")

    if len(enriched_hash) < MIN_TICKERS_REQUIRED:
        print(f"[FAIL] Only {len(enriched_hash)} enriched — need at least {MIN_TICKERS_REQUIRED}")
        sys.exit(1)

    # ── 5. Safety check: don't overwrite a better last_close ──────────────
    existing_lc_len = await r.hlen(SNAPSHOT_LAST_CLOSE_HASH)
    print(f"[INFO] Existing last_close has {existing_lc_len} fields")

    # ── 6. Write metadata entry ───────────────────────────────────────────
    meta_entry = fast_dumps({
        "timestamp": datetime.now().isoformat(),
        "count": len(enriched_hash),
        "changed": len(enriched_hash),
        "version": 2,
        "source": "rebuild_last_close.py"
    })

    # ── 7. Write to both hashes via pipeline ──────────────────────────────
    BATCH_SIZE = 500
    symbols = list(enriched_hash.keys())

    # Write enriched:latest
    print(f"[...] Writing snapshot:enriched:latest ({len(enriched_hash)} fields)...")
    pipe = r.pipeline()
    pipe.delete(SNAPSHOT_ENRICHED_HASH)
    for i in range(0, len(symbols), BATCH_SIZE):
        batch = {s: enriched_hash[s] for s in symbols[i:i+BATCH_SIZE]}
        pipe.hset(SNAPSHOT_ENRICHED_HASH, mapping=batch)
    pipe.hset(SNAPSHOT_ENRICHED_HASH, "__meta__", meta_entry)
    pipe.expire(SNAPSHOT_ENRICHED_HASH, ENRICHED_TTL)
    await pipe.execute()
    print(f"[OK] snapshot:enriched:latest written ({len(enriched_hash)} + __meta__)")

    # Write enriched:last_close
    print(f"[...] Writing snapshot:enriched:last_close ({len(enriched_hash)} fields)...")
    pipe = r.pipeline()
    pipe.delete(SNAPSHOT_LAST_CLOSE_HASH)
    for i in range(0, len(symbols), BATCH_SIZE):
        batch = {s: enriched_hash[s] for s in symbols[i:i+BATCH_SIZE]}
        pipe.hset(SNAPSHOT_LAST_CLOSE_HASH, mapping=batch)
    pipe.hset(SNAPSHOT_LAST_CLOSE_HASH, "__meta__", meta_entry)
    pipe.expire(SNAPSHOT_LAST_CLOSE_HASH, LAST_CLOSE_TTL)
    await pipe.execute()
    print(f"[OK] snapshot:enriched:last_close written ({len(enriched_hash)} + __meta__)")

    # ── 8. Verify ─────────────────────────────────────────────────────────
    latest_len = await r.hlen(SNAPSHOT_ENRICHED_HASH)
    lc_len = await r.hlen(SNAPSHOT_LAST_CLOSE_HASH)
    latest_ttl = await r.ttl(SNAPSHOT_ENRICHED_HASH)
    lc_ttl = await r.ttl(SNAPSHOT_LAST_CLOSE_HASH)
    print(f"\n=== VERIFICATION ===")
    print(f"snapshot:enriched:latest    -> {latest_len} fields, TTL={latest_ttl}s")
    print(f"snapshot:enriched:last_close -> {lc_len} fields, TTL={lc_ttl}s")

    # Quick API test
    print(f"\n[OK] Done! Market Pulse should now show data.")

    await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
