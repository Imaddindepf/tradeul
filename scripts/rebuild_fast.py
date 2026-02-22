#!/usr/bin/env python3
"""
rebuild_fast.py — Full rebuild of snapshot:enriched hashes.

Merges three authoritative data sources, ALL from Polygon:
  1. snapshot:polygon:latest      → real-time: price, volume, change%, OHLC, bid/ask
  2. metadata:ticker:*            → fundamentals: market_cap, float, sector, industry
  3. screener:daily_indicators    → daily technicals (DuckDB over Polygon FLATS parquets):
     change_1d/3d/5d/10d/20d, avg_volume_5/10/20d, SMA 20/50/200, RSI,
     ATR%, ADX, BB, 52w high/low, dist_sma, gap%

All daily indicators are computed by the screener service from Polygon day_aggs
parquet files (252 trading days, split-adjusted via FLATS S3).

Usage:
  export $(grep -E '^REDIS_PASSWORD=' /opt/tradeul/.env)
  REDIS_URL="redis://:$REDIS_PASSWORD@localhost:6379" python3 -u scripts/rebuild_fast.py
"""
import asyncio
import json as stdlib_json
import os
import sys
from datetime import datetime

try:
    import orjson
    dumps = lambda o: orjson.dumps(o).decode()
    loads = orjson.loads
except ImportError:
    dumps = lambda o: stdlib_json.dumps(o, default=str)
    loads = stdlib_json.loads

import redis.asyncio as aioredis

POLY_KEY = "snapshot:polygon:latest"
ENRICHED_KEY = "snapshot:enriched:latest"
LAST_CLOSE_KEY = "snapshot:enriched:last_close"
SCREENER_DAILY_KEY = "screener:daily_indicators:latest"


def sf(val):
    """Safe float: convert to float, return None for NaN/Inf/None."""
    if val is None:
        return None
    try:
        f = float(val)
        return f if f == f and f != float('inf') and f != float('-inf') else None
    except (ValueError, TypeError):
        return None


async def main():
    pwd = os.environ.get("REDIS_PASSWORD", "")
    url = os.environ.get("REDIS_URL", f"redis://:{pwd}@localhost:6379")
    r = aioredis.from_url(url, decode_responses=False)
    await r.ping()
    print("[1/6] Redis OK")

    # ── 1. Polygon snapshot (real-time prices) ──────────────────────
    raw = await r.get(POLY_KEY)
    if not raw:
        print("[FAIL] No polygon snapshot in Redis")
        return 1
    tickers_raw = loads(raw).get("tickers", [])
    print(f"[2/6] Polygon snapshot: {len(tickers_raw)} tickers")
    if len(tickers_raw) < 2000:
        print("[FAIL] Too few tickers in polygon snapshot")
        return 1

    # ── 2. Metadata (fundamentals) ─────────────────────────────────
    symbols = [t.get("ticker") for t in tickers_raw if t.get("ticker")]
    meta_keys = [f"metadata:ticker:{s}".encode() for s in symbols]
    metadata = {}
    BATCH = 1000
    for i in range(0, len(meta_keys), BATCH):
        vals = await r.mget(*meta_keys[i:i + BATCH])
        for k, v in zip(symbols[i:i + BATCH], vals):
            if v:
                try:
                    metadata[k] = loads(v)
                except Exception:
                    pass
    print(f"[3/6] Metadata: {len(metadata)} tickers")

    # ── 3. Daily indicators from screener (DuckDB over Polygon FLATS) ──
    daily_raw = await r.get(SCREENER_DAILY_KEY)
    daily_cache = {}
    if daily_raw:
        raw_str = daily_raw.decode("utf-8") if isinstance(daily_raw, bytes) else daily_raw
        daily_data = stdlib_json.loads(raw_str)
        daily_tickers = daily_data.get("tickers", {})
        print(f"[4/6] Screener daily indicators: {len(daily_tickers)} tickers "
              f"(updated: {daily_data.get('updated_at', '?')})")
        for sym, ind in daily_tickers.items():
            if not isinstance(ind, dict):
                continue
            daily_cache[sym] = {
                "daily_sma_20": sf(ind.get("sma_20")),
                "daily_sma_50": sf(ind.get("sma_50")),
                "daily_sma_200": sf(ind.get("sma_200")),
                "daily_rsi": sf(ind.get("rsi")),
                "daily_adx_14": sf(ind.get("adx_14")),
                "daily_bb_upper": sf(ind.get("bb_upper")),
                "daily_bb_lower": sf(ind.get("bb_lower")),
                "daily_bb_position": sf(ind.get("bb_position")),
                "high_52w": sf(ind.get("high_52w")),
                "low_52w": sf(ind.get("low_52w")),
                "from_52w_high": sf(ind.get("from_52w_high")),
                "from_52w_low": sf(ind.get("from_52w_low")),
                "daily_atr_percent": sf(ind.get("atr_percent")),
                "change_1d": sf(ind.get("change_1d")),
                "change_3d": sf(ind.get("change_3d")),
                "change_5d": sf(ind.get("change_5d")),
                "change_10d": sf(ind.get("change_10d")),
                "change_20d": sf(ind.get("change_20d")),
                "daily_gap_percent": sf(ind.get("gap_percent")),
                "avg_volume_5d": sf(ind.get("avg_volume_5")),
                "avg_volume_10d": sf(ind.get("avg_volume_10")),
                "avg_volume_20d": sf(ind.get("avg_volume_20")),
                "dist_daily_sma_20": sf(ind.get("dist_sma_20")),
                "dist_daily_sma_50": sf(ind.get("dist_sma_50")),
            }
    else:
        print("[4/6] WARNING: screener:daily_indicators:latest NOT found in Redis!")
        print("  → Trigger refresh: docker exec tradeul_screener curl -s http://localhost:8000/refresh")

    # ── 4. Build enriched hash ─────────────────────────────────────
    enriched = {}
    skipped = 0
    for t in tickers_raw:
        sym = t.get("ticker")
        if not sym:
            skipped += 1
            continue

        lt = t.get("lastTrade") or {}
        dy = t.get("day") or {}
        pd_ = t.get("prevDay") or {}
        mn = t.get("min") or {}

        price = lt.get("p") or dy.get("c")
        if not price or price <= 0:
            skipped += 1
            continue

        vol = mn.get("av") or dy.get("v") or 0
        chg = t.get("todaysChangePerc")
        meta = metadata.get(sym, {})
        di = daily_cache.get(sym, {})

        day_open = dy.get("o")
        prev_close = pd_.get("c")
        day_high = dy.get("h")
        day_low = dy.get("l")
        day_vwap = dy.get("vw")
        fs = meta.get("free_float") or meta.get("float_shares")

        # Derived fields
        gap = round((day_open - prev_close) / prev_close * 100, 2) if day_open and prev_close and prev_close > 0 else None
        dvol = round(price * vol) if price and vol else None
        dvwap = round((price - day_vwap) / day_vwap * 100, 2) if price and day_vwap and day_vwap > 0 else None

        lq = t.get("lastQuote") or {}
        bid = lq.get("p")
        ask = lq.get("P")
        bsz = lq.get("s", 0) * 100 if lq.get("s") else None
        asz = lq.get("S", 0) * 100 if lq.get("S") else None
        bar = round(bsz / asz, 2) if bsz and asz and asz > 0 else None
        fto = round(vol / fs * 100, 2) if fs and fs > 0 and vol else None

        h = day_high
        l = day_low
        pir = round((price - l) / (h - l) * 100, 2) if h and l and h > l else None
        rng = round((h - l) / l * 100, 2) if h and l and l > 0 else None

        avg_vol_10d = di.get("avg_volume_10d")
        day_vol = dy.get("v")
        vol_today_pct = round((day_vol / avg_vol_10d) * 100, 1) if day_vol and avg_vol_10d and avg_vol_10d > 0 else None

        price_from_high = round((price - day_high) / day_high * 100, 2) if price and day_high and day_high > 0 else None

        # Distance from NBBO
        dist_nbbo = None
        if price and bid and ask and bid > 0 and ask > 0:
            if bid <= price <= ask:
                dist_nbbo = 0.0
            elif price < bid:
                dist_nbbo = round((bid - price) / bid * 100, 2)
            else:
                dist_nbbo = round((price - ask) / ask * 100, 2)

        rec = {
            "ticker": sym,
            "price": price,
            "current_price": price,
            "change_percent": chg,
            "todaysChangePerc": chg,
            "volume": vol,
            "current_volume": vol,
            # Fundamentals (metadata)
            "market_cap": meta.get("market_cap"),
            "security_type": meta.get("type") or meta.get("security_type"),
            "float_shares": fs,
            "shares_outstanding": meta.get("shares_outstanding"),
            "sector": meta.get("sector"),
            "industry": meta.get("industry"),
            # Polygon nested (kept for downstream compat)
            "lastTrade": {"p": lt.get("p"), "t": lt.get("t")} if lt.get("p") else None,
            "day": dy or None,
            "prevDay": {"c": prev_close, "v": pd_.get("v")} if prev_close else None,
            "min": {"av": mn.get("av"), "v": mn.get("v"), "vw": mn.get("vw"),
                     "o": mn.get("o"), "h": mn.get("h"), "l": mn.get("l"),
                     "c": mn.get("c"), "t": mn.get("t")} if mn.get("av") else None,
            # Derived intraday
            "gap_percent": gap,
            "dollar_volume": dvol,
            "vwap": day_vwap,
            "dist_from_vwap": dvwap,
            "bid": bid,
            "ask": ask,
            "bid_size": bsz,
            "ask_size": asz,
            "bid_ask_ratio": bar,
            "float_turnover": fto,
            "pos_in_range": pir,
            "todays_range_pct": rng,
            "todays_range": round(h - l, 4) if h and l else None,
            "intraday_high": day_high,
            "intraday_low": day_low,
            "volume_today_pct": vol_today_pct,
            "price_from_high": price_from_high,
            "distance_from_nbbo": dist_nbbo,
            "change_from_close": round(price - prev_close, 4) if price and prev_close else None,
            "prev_day_volume": pd_.get("v"),
            "minute_volume": int(mn.get("v")) if mn.get("v") else None,
            # ═══════════════════════════════════════════════════════════
            # DAILY indicators (from screener — computed via DuckDB over
            # Polygon FLATS parquets, 252 trading days, all split-adjusted)
            # ═══════════════════════════════════════════════════════════
            "change_1d": di.get("change_1d"),
            "change_3d": di.get("change_3d"),
            "change_5d": di.get("change_5d"),
            "change_10d": di.get("change_10d"),
            "change_20d": di.get("change_20d"),
            "avg_volume_5d": di.get("avg_volume_5d"),
            "avg_volume_10d": avg_vol_10d,
            "avg_volume_20d": di.get("avg_volume_20d"),
            "high_52w": di.get("high_52w"),
            "low_52w": di.get("low_52w"),
            "from_52w_high": di.get("from_52w_high"),
            "from_52w_low": di.get("from_52w_low"),
            "daily_sma_20": di.get("daily_sma_20"),
            "daily_sma_50": di.get("daily_sma_50"),
            "daily_sma_200": di.get("daily_sma_200"),
            "dist_daily_sma_20": di.get("dist_daily_sma_20"),
            "dist_daily_sma_50": di.get("dist_daily_sma_50"),
            "daily_atr_percent": di.get("daily_atr_percent"),
            "daily_rsi": di.get("daily_rsi"),
            "daily_adx_14": di.get("daily_adx_14"),
            "daily_bb_upper": di.get("daily_bb_upper"),
            "daily_bb_lower": di.get("daily_bb_lower"),
            "daily_bb_position": di.get("daily_bb_position"),
            "daily_gap_percent": di.get("daily_gap_percent"),
            # ═══════════════════════════════════════════════════════════
            # INTRADAY indicators — only available during live market session.
            # BarEngine (talipp) computes these from 1-min WebSocket bars.
            # Set to None for last_close snapshot (market closed).
            # ═══════════════════════════════════════════════════════════
            "rvol": None,
            "atr": None,
            "atr_percent": None,
            "rsi_14": None,
            "ema_9": None, "ema_20": None, "ema_50": None,
            "sma_5": None, "sma_8": None, "sma_20": None,
            "sma_50": None, "sma_200": None,
            "adx_14": None,
            "macd_line": None, "macd_signal": None, "macd_hist": None,
            "bb_upper": None, "bb_mid": None, "bb_lower": None,
            "stoch_k": None, "stoch_d": None,
            "chg_1min": None, "chg_5min": None, "chg_10min": None,
            "chg_15min": None, "chg_30min": None, "chg_60min": None,
            "vol_1min": None, "vol_5min": None, "vol_10min": None,
            "vol_15min": None, "vol_30min": None, "vol_60min": None,
            "trades_today": None, "avg_trades_5d": None,
            "trades_z_score": None, "is_trade_anomaly": False,
        }
        enriched[sym] = dumps(rec)

    with_daily = sum(1 for s in enriched if s in daily_cache)
    print(f"[5/6] Enriched: {len(enriched)} tickers "
          f"({with_daily} with daily indicators, {skipped} skipped)")
    if len(enriched) < 2000:
        print("[FAIL] Too few enriched tickers")
        return 1

    # ── 5. Write to Redis atomically ───────────────────────────────
    meta_json = dumps({
        "timestamp": datetime.now().isoformat(),
        "count": len(enriched),
        "changed": len(enriched),
        "version": 2,
        "source": "rebuild_fast.py",
    })

    # Write to snapshot:enriched:latest only.
    # last_close is NOT overwritten here because this script lacks intraday
    # indicators (BarEngine runs in the analytics container). Use
    # enrich_last_close.py to rebuild last_close with full indicators.
    targets = [(ENRICHED_KEY, 600)]
    
    # Only write last_close if it doesn't already exist or --force-last-close
    existing_lc = await r.hlen(LAST_CLOSE_KEY)
    if existing_lc == 0 or "--force-last-close" in sys.argv:
        targets.append((LAST_CLOSE_KEY, 604800))
        if existing_lc > 0:
            print(f"  WARNING: overwriting last_close ({existing_lc} fields) with --force-last-close")
    else:
        print(f"  Skipping last_close (already has {existing_lc} fields with intraday indicators)")
        print(f"  Use --force-last-close to overwrite, or enrich_last_close.py to rebuild properly")
    
    for target, ttl in targets:
        tmp = f"{target}:_rebuild_tmp"
        pipe = r.pipeline()
        syms = list(enriched.keys())
        for i in range(0, len(syms), 500):
            batch = {s: enriched[s] for s in syms[i:i + 500]}
            pipe.hset(tmp, mapping=batch)
        pipe.hset(tmp, "__meta__", meta_json)
        pipe.expire(tmp, ttl)
        await pipe.execute()
        await r.rename(tmp, target)
        n = await r.hlen(target)
        t = await r.ttl(target)
        print(f"  {target}: {n} fields, TTL={t}s")

    print(f"[6/6] DONE — {len(enriched)} tickers ({with_daily} with full daily indicators)")
    await r.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
