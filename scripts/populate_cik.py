#!/usr/bin/env python3
"""
Script para poblar CIK desde Polygon API
"""
import asyncio
import os
import httpx
import asyncpg

DB_HOST = os.getenv("TIMESCALE_HOST", "timescaledb")
DB_PORT = int(os.getenv("TIMESCALE_PORT", "5432"))
DB_NAME = os.getenv("TIMESCALE_DB", "tradeul")
DB_USER = os.getenv("TIMESCALE_USER", "tradeul_user")
DB_PASSWORD = os.getenv("TIMESCALE_PASSWORD", "tradeul_password_secure_123")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "vjzI76TMiepqrMZKphpfs3SA54JFkhEx")

async def get_cik_from_polygon(symbol: str, session: httpx.AsyncClient):
    """Obtener CIK desde Polygon"""
    try:
        url = f"https://api.polygon.io/v3/reference/tickers/{symbol}"
        params = {"apiKey": POLYGON_API_KEY}
        response = await session.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            result = data.get("results", {})
            cik = result.get("cik")
            return cik if cik else None
    except Exception as e:
        print(f"Error fetching CIK for {symbol}: {e}")
    return None

async def main():
    conn = await asyncpg.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=DB_PASSWORD
    )
    
    # Obtener tickers con metadata pero sin CIK
    query = """
    SELECT symbol FROM ticker_metadata 
    WHERE (cik IS NULL OR cik = '') 
    AND company_name IS NOT NULL
    ORDER BY market_cap DESC NULLS LAST
    LIMIT 2000
    """
    rows = await conn.fetch(query)
    symbols = [row["symbol"] for row in rows]
    
    print(f"📊 Poblando CIK para {len(symbols)} tickers...")
    
    success = 0
    failed = 0
    
    async with httpx.AsyncClient() as session:
        for i, symbol in enumerate(symbols, 1):
            try:
                cik = await get_cik_from_polygon(symbol, session)
                
                if cik:
                    await conn.execute(
                        "UPDATE ticker_metadata SET cik = $1, updated_at = NOW() WHERE symbol = $2",
                        cik, symbol
                    )
                    success += 1
                    print(f"✅ {i}/{len(symbols)}: {symbol} - CIK: {cik}")
                else:
                    failed += 1
                    if i % 100 == 0:
                        print(f"⚠️  {i}/{len(symbols)}: {symbol} - Sin CIK")
                
                await asyncio.sleep(0.15)  # Rate limit
                
                if i % 50 == 0:
                    print(f"\n📈 Progreso: {i}/{len(symbols)} ({(i/len(symbols)*100):.1f}%) | ✅ {success} | ❌ {failed}\n")
                    
            except Exception as e:
                print(f"⚠️  Error {symbol}: {e}")
                failed += 1
    
    await conn.close()
    
    print(f"\n✨ Completado:")
    print(f"   Exitosos: {success}")
    print(f"   Sin CIK: {failed}")

if __name__ == "__main__":
    asyncio.run(main())

