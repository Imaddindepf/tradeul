#!/usr/bin/env python3
"""
Bootstrap Ticker Chain
======================

Script standalone para poblar el hash Redis `ticker:chain` por primera vez.
Usa la misma lógica que BuildTickerChainTask.

Uso:
    cd /opt/tradeul && docker exec -it data_maintenance python /app/scripts/bootstrap_ticker_chain.py

O directamente:
    cd /opt/tradeul && python scripts/bootstrap_ticker_chain.py
"""

import asyncio
import os
import sys
import time

# Add project paths
sys.path.insert(0, '/app')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date


async def main():
    print("=" * 60)
    print("BOOTSTRAP TICKER CHAIN")
    print("=" * 60)
    
    # Try to import from project, fallback to inline
    try:
        from shared.utils.redis_client import RedisClient
        from services.data_maintenance.tasks.build_ticker_chain import BuildTickerChainTask
        
        redis = RedisClient()
        await redis.connect()
        
        task = BuildTickerChainTask(redis)
        result = await task.execute(date.today())
        
        print(f"\nResult: {result}")
        
        # Show some examples
        chain_count = await redis.client.hlen("ticker:chain")
        print(f"\nTotal chains in Redis: {chain_count}")
        
        # Show specific examples
        for ticker in ["META", "DJT", "INEO", "AAPL"]:
            chain = await redis.hget("ticker:chain", ticker)
            print(f"  {ticker}: {chain}")
        
        await redis.disconnect()
        
    except ImportError:
        print("Running in standalone mode (outside Docker)...")
        await _standalone_bootstrap()


async def _standalone_bootstrap():
    """Standalone mode: connect to Redis directly and use httpx."""
    import httpx
    
    try:
        import redis.asyncio as aioredis
    except ImportError:
        print("ERROR: pip install redis")
        return
    
    try:
        import orjson
    except ImportError:
        import json as orjson
    
    POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "vjzI76TMiepqrMZKphpfs3SA54JFkhEx")
    REDIS_URL = os.getenv("REDIS_URL", "redis://:Tr4d3ul_R3d1s_2024!@157.180.45.153:6379/0")
    
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    await r.ping()
    print(f"Connected to Redis")
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Fetch all tickers
        print("\n[1/3] Fetching all active tickers from Polygon...")
        all_tickers = []
        next_url = None
        page = 1
        
        while page <= 20:
            if next_url:
                url = next_url
            else:
                url = (
                    f"https://api.polygon.io/v3/reference/tickers"
                    f"?market=stocks&locale=us&active=true&limit=1000"
                    f"&apiKey={POLYGON_API_KEY}"
                )
            
            resp = await client.get(url)
            if resp.status_code != 200:
                break
            
            data = resp.json()
            results = data.get("results", [])
            if not results:
                break
            
            all_tickers.extend(r_item["ticker"] for r_item in results)
            
            next_url = data.get("next_url")
            if not next_url:
                break
            if "apiKey" not in next_url:
                next_url = f"{next_url}&apiKey={POLYGON_API_KEY}"
            
            page += 1
            await asyncio.sleep(0.15)
        
        print(f"  Found {len(all_tickers)} tickers")
        
        # 2. Scan events
        print(f"\n[2/3] Scanning ticker events (concurrency=50)...")
        chains = {}
        semaphore = asyncio.Semaphore(50)
        scanned = 0
        errors = 0
        start = time.time()
        
        async def check_ticker(ticker):
            nonlocal scanned, errors
            async with semaphore:
                try:
                    url = (
                        f"https://api.polygon.io/vX/reference/tickers/{ticker}/events"
                        f"?types=ticker_change&apiKey={POLYGON_API_KEY}"
                    )
                    resp = await client.get(url)
                    scanned += 1
                    
                    if scanned % 1000 == 0:
                        elapsed = time.time() - start
                        print(f"  Scanned {scanned}/{len(all_tickers)} ({elapsed:.0f}s)")
                    
                    if resp.status_code != 200:
                        return
                    
                    data_resp = resp.json()
                    events = data_resp.get("results", {}).get("events", [])
                    
                    if not events:
                        return
                    
                    # Build ordered chain
                    changes = []
                    for event in events:
                        tc = event.get("ticker_change", {})
                        old_ticker = tc.get("ticker", "")
                        event_date = event.get("date", "")
                        if old_ticker and event_date:
                            changes.append((event_date, old_ticker))
                    
                    if changes:
                        changes.sort(key=lambda x: x[0])
                        chain = [c[1] for c in changes]
                        if ticker not in chain:
                            chain.append(ticker)
                        elif chain[-1] != ticker:
                            chain.remove(ticker)
                            chain.append(ticker)
                        
                        if len(chain) > 1:
                            chains[ticker] = chain
                            
                except Exception:
                    errors += 1
        
        tasks = [check_ticker(t) for t in all_tickers]
        await asyncio.gather(*tasks)
        
        elapsed = time.time() - start
        print(f"  Done! {len(chains)} chains found in {elapsed:.1f}s ({errors} errors)")
        
        # 3. Populate Redis
        print(f"\n[3/3] Populating Redis hash ticker:chain...")
        await r.delete("ticker:chain")
        
        pipe = r.pipeline()
        for symbol, chain in chains.items():
            if hasattr(orjson, 'dumps'):
                pipe.hset("ticker:chain", symbol, orjson.dumps(chain).decode())
            else:
                import json
                pipe.hset("ticker:chain", symbol, json.dumps(chain))
        
        if chains:
            await pipe.execute()
        
        # Verify
        count = await r.hlen("ticker:chain")
        print(f"  Stored {count} chains in Redis")
        
        # Examples
        print(f"\nExamples:")
        for ticker in ["META", "DJT", "INEO", "AAPL", "LLY"]:
            val = await r.hget("ticker:chain", ticker)
            print(f"  {ticker}: {val}")
        
        await r.aclose()
    
    print(f"\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
