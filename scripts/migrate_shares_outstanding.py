"""
Script para corregir shares_outstanding en BD usando Polygon API.

Solo corrige tickers donde el ratio está muy desviado (< 0.5 o > 2.0).
Ejecutar dentro del contenedor data_maintenance.
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import List, Optional, Tuple
import httpx

sys.path.insert(0, '/app')
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://tradeul_user:tradeul_password_secure_123@timescaledb:5432/tradeul")

BATCH_SIZE = 100
CONCURRENT_REQUESTS = 20


async def get_polygon_shares_outstanding(client: httpx.AsyncClient, ticker: str) -> Optional[int]:
    """Obtener share_class_shares_outstanding de Polygon"""
    try:
        url = f"https://api.polygon.io/v3/reference/tickers/{ticker}"
        params = {"apiKey": POLYGON_API_KEY}
        
        response = await client.get(url, params=params, timeout=10.0)
        if response.status_code == 200:
            data = response.json().get("results", {})
            return data.get("share_class_shares_outstanding")
        return None
    except Exception as e:
        logger.debug(f"Error fetching {ticker}: {e}")
        return None


async def get_tickers_needing_correction(db: TimescaleClient) -> List[Tuple[str, int]]:
    """
    Obtener tickers CS activos con shares_outstanding.
    Verificaremos contra Polygon cuáles necesitan corrección.
    """
    query = """
        SELECT symbol, shares_outstanding
        FROM tickers_unified
        WHERE is_actively_trading = true
          AND type = 'CS'
          AND shares_outstanding IS NOT NULL
    """
    rows = await db.fetch(query)
    return [(r['symbol'], r['shares_outstanding']) for r in rows]


async def update_shares_outstanding(db: TimescaleClient, ticker: str, shares: int):
    """Actualizar shares_outstanding en BD"""
    query = """
        UPDATE tickers_unified
        SET shares_outstanding = $1, updated_at = NOW()
        WHERE symbol = $2
    """
    await db.execute(query, shares, ticker)


async def check_and_correct_ticker(
    db: TimescaleClient, 
    client: httpx.AsyncClient, 
    symbol: str, 
    db_value: int
) -> str:
    """
    Verifica un ticker y lo corrige si es necesario.
    Returns: "correct", "corrected", "no_data", "error"
    """
    try:
        polygon_value = await get_polygon_shares_outstanding(client, symbol)
        
        if polygon_value is None:
            return "no_data"
        
        if db_value == 0:
            await update_shares_outstanding(db, symbol, polygon_value)
            return "corrected"
        
        # Calcular ratio
        ratio = db_value / polygon_value if polygon_value > 0 else 0
        
        # Solo corregir si ratio < 0.5 o > 2.0 (diferencia significativa)
        if 0.5 <= ratio <= 2.0:
            return "correct"
        
        # Corregir
        await update_shares_outstanding(db, symbol, polygon_value)
        logger.info(f"Corrected {symbol}: {db_value:,} -> {polygon_value:,} (ratio was {ratio:.2f})")
        return "corrected"
        
    except Exception as e:
        logger.error(f"Error checking {symbol}: {e}")
        return "error"


async def process_batch(
    db: TimescaleClient, 
    client: httpx.AsyncClient, 
    batch: List[Tuple[str, int]]
) -> Tuple[int, int, int, int]:
    """Procesar un batch de tickers concurrentemente"""
    tasks = [check_and_correct_ticker(db, client, symbol, db_val) for symbol, db_val in batch]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    correct = sum(1 for r in results if r == "correct")
    corrected = sum(1 for r in results if r == "corrected")
    no_data = sum(1 for r in results if r == "no_data")
    errors = sum(1 for r in results if isinstance(r, Exception) or r == "error")
    
    return correct, corrected, no_data, errors


async def main(dry_run: bool = False, limit: Optional[int] = None):
    db = TimescaleClient(database_url=DATABASE_URL)
    await db.connect()
    
    logger.info(f"Shares Outstanding Migration", dry_run=dry_run, limit=limit)
    
    tickers = await get_tickers_needing_correction(db)
    if limit:
        tickers = tickers[:limit]
    
    total = len(tickers)
    logger.info(f"📊 Found {total} CS tickers to check")
    
    if dry_run:
        logger.info("Dry run - no changes will be made")
        await db.disconnect()
        return
    
    total_correct = 0
    total_corrected = 0
    total_no_data = 0
    total_errors = 0
    
    async with httpx.AsyncClient(
        timeout=30.0, 
        limits=httpx.Limits(max_connections=CONCURRENT_REQUESTS)
    ) as client:
        for i in range(0, total, BATCH_SIZE):
            batch = tickers[i:i + BATCH_SIZE]
            correct, corrected, no_data, errors = await process_batch(db, client, batch)
            
            total_correct += correct
            total_corrected += corrected
            total_no_data += no_data
            total_errors += errors
            
            progress = min(i + BATCH_SIZE, total)
            print(f"Progress: {progress}/{total} | Correct: {total_correct} | Corrected: {total_corrected} | NoData: {total_no_data}")
    
    logger.info(
        "MIGRATION COMPLETE",
        total_checked=total,
        correct=total_correct,
        corrected=total_corrected,
        no_data=total_no_data,
        errors=total_errors
    )
    
    await db.disconnect()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    
    start = datetime.now()
    asyncio.run(main(dry_run=args.dry_run, limit=args.limit))
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n✅ Completed in {elapsed:.1f} seconds")

