#!/usr/bin/env python3
"""
Carga datos OHLC diarios desde Polygon a TimescaleDB
Para cálculo de ATR y otros indicadores técnicos
"""

import asyncio
import sys
sys.path.append('/app')

from shared.utils.timescale_client import TimescaleClient
from datetime import datetime, date, timedelta
import httpx
from typing import List, Dict
import time as time_module

POLYGON_API_KEY = "vjzI76TMiepqrMZKphpfs3SA54JFkhEx"

# Festivos 2025
MARKET_HOLIDAYS = {
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18),
    date(2025, 5, 26), date(2025, 7, 4), date(2025, 9, 1), date(2025, 11, 27), date(2025, 12, 25)
}

def get_trading_days(lookback: int = 30) -> List[date]:
    """Obtener últimos N días de trading"""
    trading_days = []
    today = date.today()
    days_back = 1
    
    while len(trading_days) < lookback:
        check_date = today - timedelta(days=days_back)
        if check_date.weekday() < 5 and check_date not in MARKET_HOLIDAYS:
            trading_days.append(check_date)
        days_back += 1
    
    return list(reversed(trading_days))


async def fetch_daily_bars(client: httpx.AsyncClient, symbol: str, start_date: date, end_date: date) -> List[Dict]:
    """Obtener barras diarias de Polygon"""
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}"
    try:
        resp = await client.get(url, params={"adjusted": "true", "sort": "asc", "apiKey": POLYGON_API_KEY}, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('results', [])
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
    return []


async def load_symbol(client: httpx.AsyncClient, db: TimescaleClient, symbol: str, trading_days: List[date]):
    """Cargar datos OHLC diarios para un símbolo"""
    start_date = trading_days[0]
    end_date = trading_days[-1]
    
    bars = await fetch_daily_bars(client, symbol, start_date, end_date)
    if not bars:
        return 0
    
    # Preparar datos para inserción batch
    records = []
    for bar in bars:
        bar_date = date.fromtimestamp(bar['t'] / 1000)
        records.append((
            bar_date,
            symbol,
            bar['o'],  # open
            bar['h'],  # high
            bar['l'],  # low
            bar['c'],  # close
            bar['v'],  # volume
            bar.get('vw'),  # vwap
            bar.get('n')   # trades_count
        ))
    
    # Inserción batch
    query = """
        INSERT INTO market_data_daily 
        (trading_date, symbol, open, high, low, close, volume, vwap, trades_count)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (trading_date, symbol) 
        DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            vwap = EXCLUDED.vwap,
            trades_count = EXCLUDED.trades_count
    """
    
    try:
        await db.executemany(query, records)
        return len(records)
    except Exception as e:
        print(f"Error inserting {symbol}: {e}")
        return 0


async def main():
    """Proceso principal"""
    print("=== Carga de datos OHLC diarios ===")
    
    # Conectar a TimescaleDB
    db_url = "postgresql://tradeul_user:tradeul_password_secure_123@timescaledb:5432/tradeul"
    db = TimescaleClient(database_url=db_url)
    await db.connect()
    print("✅ Conectado a TimescaleDB")
    
    # Obtener días de trading
    trading_days = get_trading_days(lookback=30)
    print(f"📅 Cargando últimos {len(trading_days)} días de trading")
    print(f"   Desde: {trading_days[0]} hasta: {trading_days[-1]}")
    
    # Obtener lista de símbolos
    symbols_query = "SELECT DISTINCT symbol FROM ticker_metadata ORDER BY symbol"
    rows = await db.fetch(symbols_query)
    symbols = [row['symbol'] for row in rows]
    print(f"📊 {len(symbols)} símbolos a procesar")
    
    if not symbols:
        print("❌ No hay símbolos en ticker_metadata")
        return
    
    # Procesar en batches
    start_time = time_module.time()
    total_records = 0
    processed = 0
    
    async with httpx.AsyncClient() as client:
        # Procesar de 50 en 50
        batch_size = 50
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            tasks = [load_symbol(client, db, sym, trading_days) for sym in batch]
            results = await asyncio.gather(*tasks)
            
            batch_records = sum(results)
            total_records += batch_records
            processed += len(batch)
            
            elapsed = time_module.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            
            print(f"⏳ Procesados: {processed}/{len(symbols)} símbolos | "
                  f"Registros: {total_records} | "
                  f"Velocidad: {rate:.1f} símbolos/s")
            
            # Pequeña pausa para no saturar Polygon
            await asyncio.sleep(0.5)
    
    elapsed = time_module.time() - start_time
    print(f"\n✅ Completado en {elapsed:.1f}s")
    print(f"📊 Total de registros insertados: {total_records}")
    print(f"⚡ Velocidad promedio: {processed/elapsed:.1f} símbolos/s")
    
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())

