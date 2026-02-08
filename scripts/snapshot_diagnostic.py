"""
Snapshot Diagnostic Tool - READ ONLY
Measures actual sizes, serialization costs, and data patterns
without modifying anything in Redis.

Usage: python scripts/snapshot_diagnostic.py
"""

import asyncio
import json
import time
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import Counter, defaultdict


async def main():
    import redis.asyncio as aioredis
    
    # Connect directly to Redis (no framework dependency)
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    redis = aioredis.from_url(redis_url, decode_responses=True)
    
    print("=" * 80)
    print("SNAPSHOT DIAGNOSTIC TOOL - READ ONLY")
    print("=" * 80)
    
    # =========================================================================
    # TEST 1: Actual Redis key sizes
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 1: Redis Key Sizes (actual bytes in Redis)")
    print("=" * 80)
    
    keys_to_check = [
        "snapshot:polygon:latest",
        "snapshot:enriched:latest",
        "snapshot:enriched:last_close",
        "snapshot:full:latest",
        "snapshot:delta:latest",
    ]
    
    for key in keys_to_check:
        try:
            mem = await redis.memory_usage(key)
            strlen_val = await redis.strlen(key)
            ttl = await redis.ttl(key)
            if mem:
                print(f"  {key}:")
                print(f"    Memory usage: {mem / 1024 / 1024:.2f} MB ({mem:,} bytes)")
                print(f"    String length: {strlen_val / 1024 / 1024:.2f} MB ({strlen_val:,} bytes)")
                print(f"    TTL: {ttl}s")
            else:
                print(f"  {key}: NOT FOUND")
        except Exception as e:
            print(f"  {key}: ERROR - {e}")
    
    # =========================================================================
    # TEST 2: Snapshot structure analysis
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 2: Snapshot Structure Analysis")
    print("=" * 80)
    
    raw_enriched = await redis.get("snapshot:enriched:latest")
    if not raw_enriched:
        print("  ERROR: No enriched snapshot found!")
        await redis.close()
        return
    
    # Measure deserialization time with stdlib json
    t0 = time.perf_counter()
    data = json.loads(raw_enriched)
    t_json_loads = (time.perf_counter() - t0) * 1000
    
    tickers = data.get("tickers", [])
    print(f"  Timestamp: {data.get('timestamp')}")
    print(f"  Ticker count: {data.get('count')} (actual: {len(tickers)})")
    print(f"  JSON string size: {len(raw_enriched) / 1024 / 1024:.2f} MB")
    print(f"  json.loads time: {t_json_loads:.1f} ms")
    
    # Measure serialization time with stdlib json
    t0 = time.perf_counter()
    re_serialized = json.dumps(data)
    t_json_dumps = (time.perf_counter() - t0) * 1000
    print(f"  json.dumps time: {t_json_dumps:.1f} ms")
    print(f"  Re-serialized size: {len(re_serialized) / 1024 / 1024:.2f} MB")
    
    # Try orjson if available
    try:
        import orjson
        t0 = time.perf_counter()
        data_orjson = orjson.loads(raw_enriched)
        t_orjson_loads = (time.perf_counter() - t0) * 1000
        
        t0 = time.perf_counter()
        orjson_bytes = orjson.dumps(data_orjson)
        t_orjson_dumps = (time.perf_counter() - t0) * 1000
        
        print(f"\n  orjson.loads time: {t_orjson_loads:.1f} ms (vs json: {t_json_loads/t_orjson_loads:.1f}x faster)")
        print(f"  orjson.dumps time: {t_orjson_dumps:.1f} ms (vs json: {t_json_dumps/t_orjson_dumps:.1f}x faster)")
        print(f"  orjson output size: {len(orjson_bytes) / 1024 / 1024:.2f} MB")
    except ImportError:
        print("\n  orjson: NOT INSTALLED")
    
    # Try msgpack if available
    try:
        import msgpack
        t0 = time.perf_counter()
        packed = msgpack.packb(data, use_bin_type=True)
        t_msgpack_pack = (time.perf_counter() - t0) * 1000
        
        t0 = time.perf_counter()
        unpacked = msgpack.unpackb(packed, raw=False)
        t_msgpack_unpack = (time.perf_counter() - t0) * 1000
        
        print(f"\n  msgpack.packb time: {t_msgpack_pack:.1f} ms")
        print(f"  msgpack.unpackb time: {t_msgpack_unpack:.1f} ms")
        print(f"  msgpack size: {len(packed) / 1024 / 1024:.2f} MB ({(1 - len(packed)/len(raw_enriched))*100:.1f}% smaller than JSON)")
    except ImportError:
        print("\n  msgpack: NOT INSTALLED")
    
    # Try msgspec if available
    try:
        import msgspec as ms
        
        t0 = time.perf_counter()
        data_msgspec = ms.json.decode(raw_enriched.encode())
        t_msgspec_loads = (time.perf_counter() - t0) * 1000
        
        t0 = time.perf_counter()
        msgspec_bytes = ms.json.encode(data_msgspec)
        t_msgspec_dumps = (time.perf_counter() - t0) * 1000
        
        print(f"\n  msgspec.json.decode time: {t_msgspec_loads:.1f} ms (vs json: {t_json_loads/t_msgspec_loads:.1f}x faster)")
        print(f"  msgspec.json.encode time: {t_msgspec_dumps:.1f} ms (vs json: {t_json_dumps/t_msgspec_dumps:.1f}x faster)")
    except ImportError:
        print("\n  msgspec: NOT INSTALLED")
    
    # =========================================================================
    # TEST 3: Per-ticker field analysis
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 3: Per-Ticker Field Analysis")
    print("=" * 80)
    
    if tickers:
        # Sample first ticker
        sample = tickers[0]
        sample_json = json.dumps(sample)
        print(f"\n  Sample ticker ({sample.get('ticker')}):")
        print(f"    Fields: {len(sample)} top-level keys")
        print(f"    JSON size: {len(sample_json)} bytes")
        
        # Average size
        total_size = sum(len(json.dumps(t)) for t in tickers[:100])
        avg_size = total_size / min(100, len(tickers))
        print(f"\n  Average ticker size (first 100): {avg_size:.0f} bytes")
        print(f"  Estimated total tickers payload: {avg_size * len(tickers) / 1024 / 1024:.2f} MB")
        
        # Field presence analysis
        field_counts = Counter()
        null_counts = Counter()
        for t in tickers:
            for key, val in t.items():
                field_counts[key] += 1
                if val is None:
                    null_counts[key] += 1
        
        print(f"\n  Field presence across all {len(tickers)} tickers:")
        print(f"  {'Field':<25} {'Present':>8} {'Null':>8} {'Null%':>8}")
        print(f"  {'-'*25} {'-'*8} {'-'*8} {'-'*8}")
        for field, count in sorted(field_counts.items(), key=lambda x: -null_counts.get(x[0], 0)):
            nulls = null_counts.get(field, 0)
            null_pct = (nulls / count * 100) if count > 0 else 0
            print(f"  {field:<25} {count:>8} {nulls:>8} {null_pct:>7.1f}%")
    
    # =========================================================================
    # TEST 4: Data that NEVER changes intraday
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 4: Static vs Dynamic Data Size")
    print("=" * 80)
    
    static_fields = {'prevDay', 'fmv'}  # Never change intraday
    rarely_fields = {'atr', 'atr_percent'}  # Change ~1x/day
    
    static_bytes = 0
    rarely_bytes = 0
    dynamic_bytes = 0
    null_bytes = 0
    
    for t in tickers:
        for key, val in t.items():
            val_json = json.dumps({key: val})
            val_size = len(val_json)
            
            if val is None:
                null_bytes += val_size
            elif key in static_fields:
                static_bytes += val_size
            elif key in rarely_fields:
                rarely_bytes += val_size
            else:
                dynamic_bytes += val_size
    
    total = static_bytes + rarely_bytes + dynamic_bytes + null_bytes
    print(f"  Static data (prevDay, fmv):       {static_bytes/1024/1024:.2f} MB ({static_bytes/total*100:.1f}%)")
    print(f"  Rarely changing (atr):             {rarely_bytes/1024/1024:.2f} MB ({rarely_bytes/total*100:.1f}%)")
    print(f"  Dynamic data (everything else):    {dynamic_bytes/1024/1024:.2f} MB ({dynamic_bytes/total*100:.1f}%)")
    print(f"  Null values:                       {null_bytes/1024/1024:.2f} MB ({null_bytes/total*100:.1f}%)")
    print(f"  TOTAL:                             {total/1024/1024:.2f} MB")
    
    # =========================================================================
    # TEST 5: Enriched fields analysis (vol_Xmin, chg_Xmin availability)
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 5: Enriched Fields Availability (vol_Xmin, chg_Xmin, rvol)")
    print("=" * 80)
    
    enriched_fields = [
        'rvol', 'atr', 'atr_percent', 'vwap', 
        'intraday_high', 'intraday_low',
        'vol_1min', 'vol_5min', 'vol_10min', 'vol_15min', 'vol_30min',
        'chg_1min', 'chg_5min', 'chg_10min', 'chg_15min', 'chg_30min',
        'trades_today', 'avg_trades_5d', 'trades_z_score', 'is_trade_anomaly'
    ]
    
    print(f"\n  {'Field':<20} {'Has Value':>10} {'None/0':>10} {'Coverage':>10}")
    print(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*10}")
    
    for field in enriched_fields:
        has_value = sum(1 for t in tickers if t.get(field) is not None and t.get(field) != 0)
        no_value = len(tickers) - has_value
        coverage = has_value / len(tickers) * 100
        print(f"  {field:<20} {has_value:>10} {no_value:>10} {coverage:>9.1f}%")
    
    # =========================================================================
    # TEST 6: Compare polygon raw vs enriched (what Analytics adds)
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 6: Raw Polygon vs Enriched (what Analytics adds)")
    print("=" * 80)
    
    raw_polygon = await redis.get("snapshot:polygon:latest")
    if raw_polygon:
        raw_data = json.loads(raw_polygon)
        raw_tickers = raw_data.get("tickers", [])
        
        print(f"  Raw polygon snapshot: {len(raw_polygon)/1024/1024:.2f} MB ({len(raw_tickers)} tickers)")
        print(f"  Enriched snapshot:    {len(raw_enriched)/1024/1024:.2f} MB ({len(tickers)} tickers)")
        print(f"  Enrichment overhead:  {(len(raw_enriched) - len(raw_polygon))/1024/1024:.2f} MB (+{((len(raw_enriched)/len(raw_polygon))-1)*100:.1f}%)")
        
        # Compare fields
        if raw_tickers:
            raw_fields = set(raw_tickers[0].keys())
            enriched_fields_set = set(tickers[0].keys()) if tickers else set()
            added_fields = enriched_fields_set - raw_fields
            print(f"\n  Fields in raw polygon: {sorted(raw_fields)}")
            print(f"\n  Fields ADDED by analytics: {sorted(added_fields)}")
            
            # Size of added fields
            added_bytes = 0
            for t in tickers:
                for field in added_fields:
                    if field in t:
                        added_bytes += len(json.dumps({field: t[field]}))
            print(f"\n  Total size of enriched-only fields: {added_bytes/1024/1024:.2f} MB")
    else:
        print("  Raw polygon snapshot: NOT FOUND")
    
    # =========================================================================
    # TEST 7: Snapshot comparison (what would change between cycles)
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 7: What Would Change Between Snapshots")
    print("=" * 80)
    print("  NOTE: Weekend data - Polygon snapshots are identical.")
    print("  Comparing enriched vs raw to estimate change patterns.")
    
    if tickers:
        # Analyze 'updated' timestamps to see which tickers have recent activity
        updated_values = Counter()
        volume_nonzero = 0
        has_last_trade = 0
        has_recent_trade = 0  # updated in last hour
        
        for t in tickers:
            updated = t.get('updated')
            if updated:
                updated_values['has_updated'] += 1
            else:
                updated_values['no_updated'] += 1
            
            # Check volume
            day = t.get('day', {}) or {}
            min_data = t.get('min', {}) or {}
            vol = min_data.get('av') or day.get('v') or 0
            if vol > 0:
                volume_nonzero += 1
            
            # Check last trade
            lt = t.get('lastTrade', {}) or {}
            if lt.get('p') and lt['p'] > 0:
                has_last_trade += 1
        
        print(f"\n  Tickers with 'updated' timestamp: {updated_values.get('has_updated', 0)}")
        print(f"  Tickers without 'updated':        {updated_values.get('no_updated', 0)}")
        print(f"  Tickers with volume > 0:          {volume_nonzero}")
        print(f"  Tickers with lastTrade price > 0: {has_last_trade}")
        
        # Check unique 'updated' values (same timestamp = same data)
        unique_updated = set()
        for t in tickers:
            u = t.get('updated')
            if u:
                unique_updated.add(u)
        print(f"  Unique 'updated' timestamps:      {len(unique_updated)}")
        if len(unique_updated) <= 20:
            print(f"    (Few unique values = many tickers share the same update time)")
    
    # =========================================================================
    # TEST 8: Hash approach simulation
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 8: Redis Hash Simulation (HSET per ticker)")
    print("=" * 80)
    
    if tickers:
        # Simulate: what if each ticker were a field in a hash?
        per_ticker_sizes = []
        for t in tickers:
            sym = t.get('ticker', '')
            ticker_json = json.dumps(t)
            per_ticker_sizes.append((sym, len(ticker_json)))
        
        total_field_bytes = sum(s for _, s in per_ticker_sizes)
        avg_field_size = total_field_bytes / len(per_ticker_sizes)
        max_field = max(per_ticker_sizes, key=lambda x: x[1])
        min_field = min(per_ticker_sizes, key=lambda x: x[1])
        
        print(f"  If each ticker = 1 hash field:")
        print(f"    Total fields: {len(per_ticker_sizes)}")
        print(f"    Total field data: {total_field_bytes/1024/1024:.2f} MB")
        print(f"    Average field size: {avg_field_size:.0f} bytes")
        print(f"    Largest field: {max_field[0]} = {max_field[1]:,} bytes")
        print(f"    Smallest field: {min_field[0]} = {min_field[1]:,} bytes")
        
        # Simulate: with 10% tickers changing, how much would we write?
        for pct in [5, 10, 20, 50]:
            n_changed = int(len(tickers) * pct / 100)
            changed_bytes = sum(s for _, s in per_ticker_sizes[:n_changed])
            print(f"\n    If {pct}% tickers changed ({n_changed} tickers):")
            print(f"      HSET would write: {changed_bytes/1024/1024:.2f} MB (vs {total_field_bytes/1024/1024:.2f} MB full)")
            print(f"      Savings: {(1 - changed_bytes/total_field_bytes)*100:.1f}%")
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  Total enriched snapshot size: {len(raw_enriched)/1024/1024:.2f} MB")
    print(f"  json.loads time: {t_json_loads:.1f} ms")
    print(f"  json.dumps time: {t_json_dumps:.1f} ms")
    print(f"  Write frequency: every ~5s (2 writes: latest + last_close)")
    print(f"  Read frequency: Scanner 10s + EventDetector ~5s + API on-demand")
    print(f"  Estimated serialization throughput: ~{(len(raw_enriched)*2/1024/1024/5 + len(raw_enriched)*3/1024/1024/5):.1f} MB/s")
    
    await redis.close()
    print("\nDone! No data was modified.")


if __name__ == "__main__":
    asyncio.run(main())
