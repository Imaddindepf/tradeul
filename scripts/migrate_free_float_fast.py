#!/usr/bin/env python3
"""
Migrate Free Float - FAST VERSION
==================================

Versión optimizada para planes Polygon pagados (sin rate limit).
Usa batches de 50 con requests paralelos.
"""

import os
import sys
import asyncio
from typing import Optional, Dict, List
from datetime import datetime

import httpx

sys.path.insert(0, '/app')

from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
BATCH_SIZE = 50  # 50 requests paralelos
BATCH_DELAY = 0.2  # Solo 200ms entre batches


async def get_free_float(client: httpx.AsyncClient, ticker: str) -> tuple[str, Optional[Dict]]:
    """Obtener free float de Polygon - retorna (ticker, data)"""
    url = "https://api.polygon.io/stocks/vX/float"
    params = {"ticker": ticker, "apiKey": POLYGON_API_KEY}
    
    try:
        response = await client.get(url, params=params)
        if response.status_code != 200:
            return ticker, None
        
        data = response.json()
        results = data.get("results", [])
        return ticker, results[0] if results else None
    except Exception:
        return ticker, None


async def main():
    if not POLYGON_API_KEY:
        print("ERROR: POLYGON_API_KEY not set")
        sys.exit(1)
    
    print("=" * 60)
    print("🚀 FAST Free Float Migration (50 parallel requests)")
    print("=" * 60)
    print(f"Started at: {datetime.now().isoformat()}")
    
    db = TimescaleClient()
    await db.connect()
    print("✅ Connected to database")
    
    # Get pending tickers
    rows = await db.fetch("""
        SELECT symbol FROM tickers_unified 
        WHERE is_actively_trading = true AND type = 'CS' AND free_float IS NULL
        ORDER BY market_cap DESC NULLS LAST
    """)
    tickers = [r['symbol'] for r in rows]
    
    print(f"\n📊 {len(tickers)} CS tickers pending")
    
    if not tickers:
        print("Nothing to do!")
        await db.disconnect()
        return
    
    stats = {"updated": 0, "no_data": 0}
    start_time = asyncio.get_event_loop().time()
    
    async with httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=100)) as client:
        for batch_start in range(0, len(tickers), BATCH_SIZE):
            batch = tickers[batch_start:batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            total_batches = (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE
            
            # Fetch all in parallel
            tasks = [get_free_float(client, t) for t in batch]
            results = await asyncio.gather(*tasks)
            
            # Update DB
            for ticker, data in results:
                if data and data.get("free_float"):
                    await db.execute("""
                        UPDATE tickers_unified SET free_float = $1, updated_at = NOW()
                        WHERE symbol = $2
                    """, data["free_float"], ticker)
                    stats["updated"] += 1
                else:
                    stats["no_data"] += 1
            
            # Progress
            processed = min(batch_start + BATCH_SIZE, len(tickers))
            elapsed = asyncio.get_event_loop().time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = (len(tickers) - processed) / rate if rate > 0 else 0
            
            print(f"[{batch_num}/{total_batches}] {processed}/{len(tickers)} | {rate:.0f}/sec | ~{remaining:.0f}s remaining | ✅{stats['updated']} ⚠️{stats['no_data']}")
            
            await asyncio.sleep(BATCH_DELAY)
    
    elapsed = asyncio.get_event_loop().time() - start_time
    print("\n" + "=" * 60)
    print("✅ MIGRATION COMPLETE")
    print("=" * 60)
    print(f"Updated:      {stats['updated']}")
    print(f"No data:      {stats['no_data']}")
    print(f"Time:         {elapsed:.1f} seconds")
    print(f"Finished at:  {datetime.now().isoformat()}")
    
    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

