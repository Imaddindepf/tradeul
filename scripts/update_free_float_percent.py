#!/usr/bin/env python3
"""
Actualiza free_float_percent desde Polygon para todos los tickers con free_float
"""
import asyncio
import os
import sys
import httpx

sys.path.insert(0, '/opt/tradeul')

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://tradeul_user:tradeul_password_secure_123@timescaledb:5432/tradeul")

async def get_free_float_data(client: httpx.AsyncClient, ticker: str):
    """Obtiene free_float y free_float_percent de Polygon"""
    url = f"https://api.polygon.io/stocks/vX/float?ticker={ticker}&apiKey={POLYGON_API_KEY}"
    try:
        resp = await client.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("results"):
                r = data["results"][0]
                return r.get("free_float"), r.get("free_float_percent")
    except:
        pass
    return None, None

async def main():
    import asyncpg
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    # Obtener tickers CS activos
    rows = await conn.fetch("""
        SELECT symbol FROM tickers_unified 
        WHERE is_actively_trading = true AND type = 'CS'
        ORDER BY market_cap DESC NULLS LAST
    """)
    
    tickers = [r['symbol'] for r in rows]
    total = len(tickers)
    print(f"📊 Procesando {total} tickers CS activos...")
    
    updated = 0
    errors = 0
    
    async with httpx.AsyncClient() as client:
        batch_size = 50
        for i in range(0, total, batch_size):
            batch = tickers[i:i+batch_size]
            tasks = [get_free_float_data(client, t) for t in batch]
            results = await asyncio.gather(*tasks)
            
            for ticker, (ff, ffp) in zip(batch, results):
                if ff is not None and ffp is not None:
                    try:
                        await conn.execute("""
                            UPDATE tickers_unified 
                            SET free_float = $1, free_float_percent = $2, updated_at = NOW()
                            WHERE symbol = $3
                        """, ff, ffp, ticker)
                        updated += 1
                    except Exception as e:
                        errors += 1
            
            print(f"  Progreso: {min(i+batch_size, total)}/{total} - Actualizados: {updated}")
            await asyncio.sleep(1.0)
    
    await conn.close()
    print(f"\n✅ Completado: {updated} actualizados, {errors} errores")

if __name__ == "__main__":
    asyncio.run(main())

