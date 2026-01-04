#!/usr/bin/env python3
"""
Script para llenar free_float faltantes usando FMP como fuente.
Sin dependencias de shared/utils - conexión directa a BD.
"""

import os
import sys
import httpx
import asyncpg
import asyncio
from datetime import datetime

# Configuration
FMP_API_KEY = os.getenv("FMP_API_KEY", "CKIRTsvk5eIpetoB8FbvOuw2wW8kNJ5B")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5433")
DB_USER = os.getenv("POSTGRES_USER", "tradeul_user")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "tradeul_password")
DB_NAME = os.getenv("POSTGRES_DB", "tradeul")

# Stats
stats = {"total": 0, "updated": 0, "no_data": 0, "errors": 0}


async def get_fmp_free_float(client: httpx.AsyncClient, symbol: str) -> dict:
    """Obtener free float desde FMP"""
    url = "https://financialmodelingprep.com/stable/shares-float"
    params = {"symbol": symbol, "apikey": FMP_API_KEY}
    
    try:
        resp = await client.get(url, params=params, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list) and len(data) > 0:
                result = data[0]
                return {
                    "free_float": int(result.get("floatShares")) if result.get("floatShares") else None,
                    "free_float_percent": float(result.get("freeFloat")) if result.get("freeFloat") else None,
                    "shares_outstanding": int(result.get("outstandingShares")) if result.get("outstandingShares") else None
                }
        return {}
    except Exception as e:
        return {}


async def main():
    global stats
    
    print(f"{'='*60}")
    print("LLENANDO FREE_FLOAT FALTANTES CON FMP")
    print(f"{'='*60}")
    print(f"Inicio: {datetime.now().isoformat()}")
    print(f"DB: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    
    # Conectar a BD con pool
    pool = await asyncpg.create_pool(
        host=DB_HOST,
        port=int(DB_PORT),
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        min_size=5,
        max_size=20
    )
    
    # Obtener tickers sin free_float
    query = """
        SELECT symbol, type
        FROM tickers_unified
        WHERE is_actively_trading = true
          AND free_float IS NULL
        ORDER BY type, symbol
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
    stats["total"] = len(rows)
    
    print(f"\nTickers sin free_float: {stats['total']}")
    
    # Agrupar por tipo
    by_type = {}
    for row in rows:
        t = row['type'] or 'NULL'
        by_type[t] = by_type.get(t, 0) + 1
    print("\nPor tipo:")
    for t, count in sorted(by_type.items(), key=lambda x: -x[1])[:10]:
        print(f"  {t}: {count}")
    
    # Procesar con concurrencia limitada
    print(f"\nProcesando con 15 conexiones concurrentes...")
    
    semaphore = asyncio.Semaphore(15)
    processed = 0
    
    async def process_ticker(client: httpx.AsyncClient, symbol: str):
        nonlocal processed
        async with semaphore:
            data = await get_fmp_free_float(client, symbol)
            
            if data and data.get("free_float"):
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE tickers_unified
                        SET 
                            free_float = COALESCE($2, free_float),
                            free_float_percent = COALESCE($3, free_float_percent),
                            shares_outstanding = COALESCE($4, shares_outstanding),
                            updated_at = NOW()
                        WHERE symbol = $1
                    """, symbol, data.get("free_float"), data.get("free_float_percent"), data.get("shares_outstanding"))
                stats["updated"] += 1
            else:
                stats["no_data"] += 1
            
            processed += 1
            if processed % 200 == 0:
                print(f"  Progreso: {processed}/{stats['total']} - Actualizados: {stats['updated']} - Sin datos: {stats['no_data']}")
    
    async with httpx.AsyncClient() as client:
        tasks = [process_ticker(client, row['symbol']) for row in rows]
        await asyncio.gather(*tasks)
    
    print(f"  Final: {processed}/{stats['total']} - Actualizados: {stats['updated']} - Sin datos: {stats['no_data']}")
    
    await pool.close()
    
    print(f"\n{'='*60}")
    print("RESUMEN")
    print(f"{'='*60}")
    print(f"Total procesados: {stats['total']}")
    print(f"Actualizados: {stats['updated']}")
    print(f"Sin datos en FMP: {stats['no_data']}")
    print(f"Fin: {datetime.now().isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
