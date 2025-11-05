#!/usr/bin/env python3
"""
CARGA MASIVA DE ATR - Pre-cálculo diario para todos los tickers

Este script:
1. Obtiene el universo completo de tickers activos
2. Fetch últimos 14 días de datos OHLC desde Polygon (daily bars)
3. Calcula ATR(14) para cada ticker
4. Guarda en Redis: atr:daily:{symbol} con TTL 24h

Ejecutar 1 vez al día antes de market open (ej: 8:00 AM ET)
Tiempo estimado: ~5-10 minutos para 11K tickers
"""

import asyncio
import sys
sys.path.append('/app')

from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import httpx
from typing import List, Dict, Set
import time as time_module
import os

# Importar calculadora y clientes
sys.path.insert(0, '/app/services/analytics')
from atr_calculator import ATRCalculator
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient

# Configuración
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "vjzI76TMiepqrMZKphpfs3SA54JFkhEx")
TIMEZONE = ZoneInfo("America/New_York")

# Concurrencia
MAX_CONCURRENT_TICKERS = 500   # 500 tickers a la vez
MAX_CONCURRENT_REQUESTS = 5000  # 5K requests simultáneos

# Festivos 2025
MARKET_HOLIDAYS = {
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18),
    date(2025, 5, 26), date(2025, 7, 4), date(2025, 9, 1), date(2025, 11, 27), date(2025, 12, 25)
}

# Stats globales
stats = {
    "total": 0,
    "done": 0,
    "success": 0,
    "failed": 0,
    "cached": 0,
    "start": 0
}


def get_trading_days(lookback: int = 20) -> List[date]:
    """
    Obtener últimos N días hábiles (excluye weekends y festivos)
    Pedimos 20 días para asegurar tener 14 días completos
    """
    trading_days = []
    today = date.today()
    days_back = 1
    
    while len(trading_days) < lookback:
        check_date = today - timedelta(days=days_back)
        # Excluir fines de semana Y festivos
        if check_date.weekday() < 5 and check_date not in MARKET_HOLIDAYS:
            trading_days.append(check_date)
        days_back += 1
    
    return list(reversed(trading_days))  # Orden cronológico


async def fetch_daily_bars(
    client: httpx.AsyncClient,
    symbol: str,
    start_date: date,
    end_date: date
) -> List[Dict]:
    """
    Fetch barras diarias desde Polygon
    
    Endpoint: /v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}
    """
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}"
    
    try:
        resp = await client.get(
            url,
            params={
                "adjusted": "true",
                "sort": "asc",
                "limit": 50,
                "apiKey": POLYGON_API_KEY
            }
        )
        
        if resp.status_code == 200:
            data = resp.json()
            results = data.get('results', [])
            
            # Convertir a formato esperado por ATRCalculator
            bars = []
            for bar in results:
                bars.append({
                    'high': bar['h'],
                    'low': bar['l'],
                    'close': bar['c'],
                    'timestamp': bar['t']
                })
            
            return bars
            
    except Exception as e:
        pass
    
    return []


async def process_ticker(
    client: httpx.AsyncClient,
    atr_calculator: ATRCalculator,
    symbol: str,
    trading_days: List[date]
) -> bool:
    """
    Procesa un ticker: fetch datos, calcula ATR, guarda en Redis
    
    Returns:
        True si se calculó y guardó exitosamente
    """
    try:
        # Fetch últimos 20 días (para asegurar 14 días completos)
        start_date = trading_days[0]
        end_date = trading_days[-1]
        
        bars = await fetch_daily_bars(client, symbol, start_date, end_date)
        
        if len(bars) < 14:
            # No hay suficientes datos
            stats["failed"] += 1
            return False
        
        # Calcular ATR usando el calculador
        result = atr_calculator.calculate_atr_from_bars(bars)
        
        if not result:
            stats["failed"] += 1
            return False
        
        # Guardar en Redis
        await atr_calculator._save_to_cache(symbol, result)
        
        stats["success"] += 1
        return True
        
    except Exception as e:
        stats["failed"] += 1
        return False
    finally:
        stats["done"] += 1


async def process_batch(
    client: httpx.AsyncClient,
    atr_calculator: ATRCalculator,
    symbols: List[str],
    trading_days: List[date],
    semaphore: asyncio.Semaphore
):
    """Procesa un batch de tickers con semáforo de concurrencia"""
    async with semaphore:
        tasks = [
            process_ticker(client, atr_calculator, symbol, trading_days)
            for symbol in symbols
        ]
        await asyncio.gather(*tasks, return_exceptions=True)


async def main():
    print("\n" + "="*90)
    print("📊 CARGA MASIVA DE ATR - Pre-cálculo diario")
    print("="*90)
    print()
    
    # Conectar a Redis y TimescaleDB
    redis_client = RedisClient()
    await redis_client.connect()
    
    db = TimescaleClient()
    await db.connect()
    
    # Inicializar calculadora de ATR
    atr_calculator = ATRCalculator(
        redis_client=redis_client,
        timescale_client=db,
        period=14,
        use_ema=True
    )
    
    print("✅ Conectado a Redis y TimescaleDB")
    print()
    
    # Obtener días de trading
    trading_days = get_trading_days(20)
    print(f"📅 Días de trading para ATR (últimos 20 días hábiles):")
    print(f"   Desde: {trading_days[0]} ({trading_days[0].strftime('%A')})")
    print(f"   Hasta: {trading_days[-1]} ({trading_days[-1].strftime('%A')})")
    print(f"   Total: {len(trading_days)} días")
    print()
    
    # Obtener universo de tickers desde Polygon
    print("📡 Obteniendo universo de tickers desde Polygon...")
    async with httpx.AsyncClient(timeout=30) as temp_client:
        base_url = "https://api.polygon.io/v3/reference/tickers"
        params = {
            "market": "stocks",
            "active": "true",
            "limit": 1000,
            "apiKey": POLYGON_API_KEY
        }
        
        polygon_tickers = []
        next_url = None
        page = 0
        
        try:
            while True:
                page += 1
                if next_url:
                    resp = await temp_client.get(next_url, params={"apiKey": POLYGON_API_KEY})
                else:
                    resp = await temp_client.get(base_url, params=params)
                
                if resp.status_code != 200:
                    break
                
                data = resp.json()
                results = data.get('results', [])
                
                if not results:
                    break
                
                polygon_tickers.extend([t.get('ticker') for t in results if t.get('ticker')])
                
                next_url = data.get('next_url')
                if not next_url:
                    break
                
                print(f"   Página {page}: {len(polygon_tickers):,} tickers...", end='\r')
            
            if not polygon_tickers:
                # Fallback a BD si Polygon falla
                print("\n⚠️  Polygon falló, usando BD local...")
                rows = await db.fetch("SELECT symbol FROM ticker_universe WHERE is_active = true ORDER BY symbol")
                polygon_tickers = [r['symbol'] for r in rows]
        
        except Exception as e:
            print(f"\n⚠️  Error obteniendo de Polygon: {e}")
            print("   Usando BD local...")
            rows = await db.fetch("SELECT symbol FROM ticker_universe WHERE is_active = true ORDER BY symbol")
            polygon_tickers = [r['symbol'] for r in rows]
    
    print(f"\n   Total: {len(polygon_tickers):,} tickers")
    print()
    
    # Filtrar tickers que ya tienen ATR en caché (opcional: forzar recálculo)
    print("🔍 Verificando caché existente...")
    cached_count = 0
    
    # Podemos verificar cuántos ya están en caché
    # Por ahora, recalculamos todos para asegurar datos frescos
    
    stats["total"] = len(polygon_tickers)
    stats["start"] = time_module.time()
    
    print(f"⚡ Configuración:")
    print(f"   Tickers: {len(polygon_tickers):,}")
    print(f"   Período ATR: 14 días")
    print(f"   Concurrencia tickers: {MAX_CONCURRENT_TICKERS}")
    print(f"   Concurrencia requests: {MAX_CONCURRENT_REQUESTS}")
    print(f"   Tiempo estimado: {len(polygon_tickers)/100/60:.1f} minutos (a 100 tickers/seg)")
    print()
    
    # HTTP client con alta concurrencia
    limits = httpx.Limits(max_connections=2000, max_keepalive_connections=1000)
    client = httpx.AsyncClient(timeout=60.0, limits=limits)
    
    print("🚀 Procesando...")
    print()
    
    # Semáforo para controlar concurrencia
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TICKERS)
    
    # Dividir en batches
    batch_size = 100
    batches = [
        polygon_tickers[i:i + batch_size]
        for i in range(0, len(polygon_tickers), batch_size)
    ]
    
    # Procesar batches con progreso
    for i, batch in enumerate(batches):
        await process_batch(client, atr_calculator, batch, trading_days, semaphore)
        
        # Mostrar progreso
        elapsed = time_module.time() - stats["start"]
        rate = stats["done"] / elapsed if elapsed > 0 else 0
        percent = (stats["done"] / stats["total"]) * 100 if stats["total"] else 0
        
        print(
            f"📊 Progreso: {stats['done']:,}/{stats['total']:,} "
            f"({percent:.1f}%) | "
            f"✅ {stats['success']:,} | "
            f"❌ {stats['failed']:,} | "
            f"⚡ {rate:.1f} tickers/seg",
            end='\r'
        )
    
    await client.aclose()
    
    # Resumen final
    elapsed = time_module.time() - stats["start"]
    print("\n")
    print("="*90)
    print("✅ CARGA COMPLETADA")
    print("="*90)
    print(f"   Total tickers: {stats['total']:,}")
    print(f"   Exitosos: {stats['success']:,} ({stats['success']/stats['total']*100:.1f}%)")
    print(f"   Fallidos: {stats['failed']:,} ({stats['failed']/stats['total']*100:.1f}%)")
    print(f"   Tiempo total: {elapsed/60:.1f} minutos")
    print(f"   Velocidad: {stats['done']/elapsed:.1f} tickers/seg")
    print()
    print(f"💾 ATR guardado en Redis con TTL de 24 horas")
    print(f"   Key pattern: atr:daily:{{symbol}}")
    print()
    
    await redis_client.close()
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())

