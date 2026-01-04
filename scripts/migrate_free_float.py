#!/usr/bin/env python3
"""
Migrate Free Float
==================

Script para poblar la columna free_float en tickers_unified
usando el endpoint /stocks/vX/float de Polygon.

Solo procesa Common Stock (type='CS') ya que el endpoint
no aplica para ETFs, Warrants, Units, etc.

Uso:
    python migrate_free_float.py [--limit N] [--dry-run]
"""

import os
import sys
import time
import argparse
import requests
from typing import Optional, Dict, List
import psycopg2
from psycopg2.extras import execute_batch

# Config
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "tradeul"),
    "user": os.getenv("DB_USER", "tradeul_user"),
    "password": os.getenv("DB_PASSWORD", "tradeul_password_secure_123"),
}

# Rate limiting
REQUESTS_PER_SECOND = 5  # Conservative to avoid hitting limits
REQUEST_DELAY = 1.0 / REQUESTS_PER_SECOND


def get_free_float(ticker: str) -> Optional[Dict]:
    """Obtener free float de Polygon"""
    url = f"https://api.polygon.io/stocks/vX/float"
    params = {"ticker": ticker, "apiKey": POLYGON_API_KEY}
    
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code != 200:
            return None
        
        data = response.json()
        results = data.get("results", [])
        
        if not results:
            return None
        
        return results[0]
    except Exception as e:
        print(f"  Error fetching {ticker}: {e}")
        return None


def get_cs_tickers_without_free_float(conn, limit: int = None) -> List[str]:
    """Obtener tickers CS que no tienen free_float"""
    cursor = conn.cursor()
    
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
    
    cursor.execute(query)
    return [row[0] for row in cursor.fetchall()]


def update_free_float(conn, ticker: str, free_float: int, free_float_percent: float, dry_run: bool = False):
    """Actualizar free_float en la BD"""
    if dry_run:
        print(f"  [DRY-RUN] Would update {ticker}: free_float={free_float:,}")
        return
    
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tickers_unified 
        SET free_float = %s, updated_at = NOW()
        WHERE symbol = %s
    """, (free_float, ticker))
    conn.commit()


def main():
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
    print(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    print(f"Dry run: {args.dry_run}")
    print()
    
    # Connect to DB
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("✅ Connected to database")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        sys.exit(1)
    
    # Get tickers to process
    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = get_cs_tickers_without_free_float(conn, args.limit)
    
    print(f"\n📊 Found {len(tickers)} CS tickers to process")
    
    if not tickers:
        print("Nothing to do!")
        return
    
    # Process tickers
    stats = {
        "processed": 0,
        "updated": 0,
        "no_data": 0,
        "errors": 0,
    }
    
    start_time = time.time()
    
    for i, ticker in enumerate(tickers, 1):
        print(f"\n[{i}/{len(tickers)}] Processing {ticker}...")
        
        # Get free float from Polygon
        data = get_free_float(ticker)
        stats["processed"] += 1
        
        if data and data.get("free_float"):
            free_float = data["free_float"]
            free_float_pct = data.get("free_float_percent", 0)
            
            print(f"  ✅ free_float={free_float:,} ({free_float_pct}%)")
            
            update_free_float(conn, ticker, free_float, free_float_pct, args.dry_run)
            stats["updated"] += 1
        else:
            print(f"  ⚠️ No free float data available")
            stats["no_data"] += 1
        
        # Rate limiting
        time.sleep(REQUEST_DELAY)
        
        # Progress update every 100 tickers
        if i % 100 == 0:
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            remaining = (len(tickers) - i) / rate if rate > 0 else 0
            print(f"\n--- Progress: {i}/{len(tickers)} ({i*100//len(tickers)}%) | {rate:.1f} tickers/sec | ~{remaining/60:.1f} min remaining ---\n")
    
    # Summary
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)
    print(f"Total processed: {stats['processed']}")
    print(f"Updated:         {stats['updated']}")
    print(f"No data:         {stats['no_data']}")
    print(f"Errors:          {stats['errors']}")
    print(f"Time elapsed:    {elapsed/60:.1f} minutes")
    print()
    
    conn.close()


if __name__ == "__main__":
    main()

