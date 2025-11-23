#!/usr/bin/env python3
"""
Script simplificado para poblar metadata básica sin campos expandidos
Compatible con el schema actual de ticker_metadata
"""

import asyncio
import sys
import os
import httpx
import asyncpg
from datetime import datetime

# Configuración
DB_HOST = os.getenv("TIMESCALE_HOST", "timescaledb")
DB_PORT = int(os.getenv("TIMESCALE_PORT", "5432"))
DB_NAME = os.getenv("TIMESCALE_DB", "tradeul")
DB_USER = os.getenv("TIMESCALE_USER", "tradeul_user")
DB_PASSWORD = os.getenv("TIMESCALE_PASSWORD", "tradeul_password_secure_123")
FMP_API_KEY = os.getenv("FMP_API_KEY", "")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")

RATE_LIMIT_DELAY = 0.2  # 200ms entre requests

async def get_metadata_from_fmp(symbol: str, session: httpx.AsyncClient) -> dict:
    """Obtener metadata desde FMP API"""
    try:
        url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}"
        params = {"apikey": FMP_API_KEY}
        response = await session.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                profile = data[0]
                return {
                    "symbol": symbol,
                    "company_name": profile.get("companyName"),
                    "exchange": profile.get("exchange"),
                    "sector": profile.get("sector"),
                    "industry": profile.get("industry"),
                    "market_cap": profile.get("mktCap"),
                    "shares_outstanding": profile.get("sharesOutstanding"),
                    "avg_volume_30d": profile.get("volAvg"),
                    "beta": profile.get("beta"),
                    "is_etf": profile.get("isEtf", False),
                    "is_actively_trading": profile.get("isActivelyTrading", True)
                }
    except Exception as e:
        print(f"Error fetching {symbol} from FMP: {e}")
    
    return None

async def save_metadata(conn: asyncpg.Connection, metadata: dict):
    """Guardar metadata en la base de datos"""
    query = """
    INSERT INTO tickers_unified (
        symbol, company_name, exchange, sector, industry,
        market_cap, float_shares, shares_outstanding,
        avg_volume_30d, avg_volume_10d, avg_price_30d, beta,
        is_etf, is_actively_trading, updated_at
    ) VALUES (
        $1, $2, $3, $4, $5, $6, NULL, $7, $8, NULL, NULL, $9, $10, $11, NOW()
    )
    ON CONFLICT (symbol) DO UPDATE SET
        company_name = EXCLUDED.company_name,
        exchange = EXCLUDED.exchange,
        sector = EXCLUDED.sector,
        industry = EXCLUDED.industry,
        market_cap = EXCLUDED.market_cap,
        shares_outstanding = EXCLUDED.shares_outstanding,
        avg_volume_30d = EXCLUDED.avg_volume_30d,
        beta = EXCLUDED.beta,
        is_etf = EXCLUDED.is_etf,
        is_actively_trading = EXCLUDED.is_actively_trading,
        updated_at = NOW()
    """
    
    await conn.execute(
        query,
        metadata["symbol"],
        metadata.get("company_name"),
        metadata.get("exchange"),
        metadata.get("sector"),
        metadata.get("industry"),
        metadata.get("market_cap"),
        metadata.get("shares_outstanding"),
        metadata.get("avg_volume_30d"),
        metadata.get("beta"),
        metadata.get("is_etf", False),
        metadata.get("is_actively_trading", True)
    )

async def main():
    # Conectar a la base de datos
    conn = await asyncpg.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    
    # Obtener símbolos activos que AÚN NO tienen metadata
    symbols_query = """
        SELECT symbol 
        FROM tickers_unified
        WHERE is_actively_trading = true
        WHERE tu.is_active = true AND tm.symbol IS NULL
        ORDER BY tu.symbol
        LIMIT 5000
    """
    rows = await conn.fetch(symbols_query)
    symbols = [row["symbol"] for row in rows]
    
    print(f"📊 Poblando metadata para {len(symbols)} tickers...")
    
    # Procesar símbolos
    success = 0
    failed = 0
    
    async with httpx.AsyncClient() as session:
        for i, symbol in enumerate(symbols, 1):
            try:
                metadata = await get_metadata_from_fmp(symbol, session)
                
                if metadata:
                    await save_metadata(conn, metadata)
                    success += 1
                    print(f"✅ {i}/{len(symbols)}: {symbol} - Success")
                else:
                    failed += 1
                    print(f"❌ {i}/{len(symbols)}: {symbol} - No data")
                
                # Rate limit
                await asyncio.sleep(RATE_LIMIT_DELAY)
                
                # Progress
                if i % 50 == 0:
                    print(f"\n📈 Progreso: {i}/{len(symbols)} ({(i/len(symbols)*100):.1f}%) | ✅ {success} | ❌ {failed}\n")
                    
            except Exception as e:
                print(f"⚠️  Error processing {symbol}: {e}")
                failed += 1
    
    await conn.close()
    
    print(f"\n✨ Completado:")
    print(f"   Exitosos: {success}")
    print(f"   Fallidos: {failed}")
    print(f"   Total: {len(symbols)}")

if __name__ == "__main__":
    asyncio.run(main())

