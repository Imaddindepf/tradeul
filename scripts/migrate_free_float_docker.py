#!/usr/bin/env python3
"""
Migrate Free Float (Docker version)
====================================

Script para poblar la columna free_float en tickers_unified
usando el endpoint /stocks/vX/float de Polygon.

Diseñado para ejecutarse dentro del contenedor data_maintenance.

Uso:
    docker exec tradeul_data_maintenance python3 /app/scripts/migrate_free_float_docker.py [--limit N] [--dry-run]
"""

import os
import sys
import asyncio
import argparse
from typing import Optional, Dict, List
from datetime import datetime

import httpx

# Add app path
sys.path.insert(0, '/app')

from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Config
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")

# Rate limiting - 5 requests per second
BATCH_SIZE = 5
BATCH_DELAY = 1.0  # 1 second between batches


async def get_free_float(client: httpx.AsyncClient, ticker: str) -> Optional[Dict]:
    """Obtener free float de Polygon"""
    url = "https://api.polygon.io/stocks/vX/float"
    params = {"ticker": ticker, "apiKey": POLYGON_API_KEY}
    
    try:
        response = await client.get(url, params=params)
        if response.status_code != 200:
            return None
        
        data = response.json()
        results = data.get("results", [])
        
        if not results:
            return None
        
        return results[0]
    except Exception as e:
        logger.warning(f"Error fetching {ticker}: {e}")
        return None


async def get_cs_tickers_to_update(db: TimescaleClient, limit: int = None) -> List[str]:
    """Obtener tickers CS que necesitan free_float"""
    query = """
        SELECT symbol 
        FROM tickers_unified 
        WHERE is_actively_trading = true 
          AND type = 'CS'
          AND free_float IS NULL
        ORDER BY market_cap DESC NULLS LAST
    """
    
    if limit:
        query += f" LIMIT {limit}"
    
    rows = await db.fetch(query)
    return [row['symbol'] for row in rows]


async def update_free_float(db: TimescaleClient, ticker: str, free_float: int):
    """Actualizar free_float en la BD"""
    await db.execute("""
        UPDATE tickers_unified 
        SET free_float = $1, updated_at = NOW()
        WHERE symbol = $2
    """, free_float, ticker)


async def main():
    parser = argparse.ArgumentParser(description="Migrate free_float from Polygon")
    parser.add_argument("--limit", type=int, help="Limit number of tickers to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually update DB")
    parser.add_argument("--ticker", type=str, help="Process single ticker")
    args = parser.parse_args()
    
    if not POLYGON_API_KEY:
        print("ERROR: POLYGON_API_KEY not set")
        sys.exit(1)
    
    print("=" * 60)
    print("Free Float Migration Script")
    print("=" * 60)
    print(f"Polygon API Key: {POLYGON_API_KEY[:10]}...")
    print(f"Dry run: {args.dry_run}")
    print(f"Started at: {datetime.now().isoformat()}")
    print()
    
    # Connect to DB
    db = TimescaleClient()
    await db.connect()
    print("✅ Connected to database")
    
    # Get tickers to process
    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = await get_cs_tickers_to_update(db, args.limit)
    
    print(f"\n📊 Found {len(tickers)} CS tickers to process")
    
    if not tickers:
        print("Nothing to do!")
        await db.disconnect()
        return
    
    # Process tickers in batches
    stats = {
        "processed": 0,
        "updated": 0,
        "no_data": 0,
        "errors": 0,
    }
    
    start_time = asyncio.get_event_loop().time()
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        for batch_start in range(0, len(tickers), BATCH_SIZE):
            batch = tickers[batch_start:batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            total_batches = (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE
            
            print(f"\n[Batch {batch_num}/{total_batches}] Processing {len(batch)} tickers...")
            
            # Process batch concurrently
            tasks = [get_free_float(client, ticker) for ticker in batch]
            results = await asyncio.gather(*tasks)
            
            for ticker, data in zip(batch, results):
                stats["processed"] += 1
                
                if data and data.get("free_float"):
                    free_float = data["free_float"]
                    free_float_pct = data.get("free_float_percent", 0)
                    
                    print(f"  ✅ {ticker}: free_float={free_float:,} ({free_float_pct}%)")
                    
                    if not args.dry_run:
                        await update_free_float(db, ticker, free_float)
                    
                    stats["updated"] += 1
                else:
                    print(f"  ⚠️ {ticker}: No data")
                    stats["no_data"] += 1
            
            # Rate limiting between batches
            if batch_start + BATCH_SIZE < len(tickers):
                await asyncio.sleep(BATCH_DELAY)
            
            # Progress update every 20 batches
            if batch_num % 20 == 0:
                elapsed = asyncio.get_event_loop().time() - start_time
                rate = stats["processed"] / elapsed if elapsed > 0 else 0
                remaining = (len(tickers) - stats["processed"]) / rate if rate > 0 else 0
                print(f"\n--- Progress: {stats['processed']}/{len(tickers)} | {rate:.1f}/sec | ~{remaining/60:.1f} min remaining ---\n")
    
    # Summary
    elapsed = asyncio.get_event_loop().time() - start_time
    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)
    print(f"Total processed: {stats['processed']}")
    print(f"Updated:         {stats['updated']}")
    print(f"No data:         {stats['no_data']}")
    print(f"Errors:          {stats['errors']}")
    print(f"Time elapsed:    {elapsed/60:.1f} minutes")
    print(f"Finished at:     {datetime.now().isoformat()}")
    print()
    
    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

