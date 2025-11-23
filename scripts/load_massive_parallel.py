#!/usr/bin/env python3
"""
CARGA MASIVA ULTRA-RÁPIDA - 100 tickers/segundo
Sin rate limits, máxima concurrencia, batch inserts masivos

Según PineScript:
- Volumen ACUMULADO del día minuto a minuto
- cvol = volumen acumulado hasta el minuto actual
- hvol = promedio de cvol del mismo minuto histórico
- RVOL = cvol / hvol
"""

import asyncio
import sys
sys.path.append('/app')

from shared.utils.timescale_client import TimescaleClient
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import httpx
from typing import List, Dict, Tuple, Set
import time as time_module

POLYGON_API_KEY = "vjzI76TMiepqrMZKphpfs3SA54JFkhEx"
TIMEZONE = ZoneInfo("America/New_York")

# MÁXIMA CONCURRENCIA
MAX_CONCURRENT_TICKERS = 1000   # 1000 tickers a la vez
MAX_CONCURRENT_REQUESTS = 10000  # 10K requests simultáneos
BATCH_INSERT_SIZE = 1000         # Inserts en batches de 1K (progreso más frecuente)

# Festivos 2025
MARKET_HOLIDAYS = {
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18),
    date(2025, 5, 26), date(2025, 7, 4), date(2025, 9, 1), date(2025, 11, 27), date(2025, 12, 25)
}

# Stats
stats = {"total": 0, "done": 0, "slots": 0, "start": 0}


def get_trading_days(lookback: int = 10) -> List[date]:
    """Obtener días hábiles siguiendo lógica PineScript"""
    trading_days = []
    today = date.today()
    days_back = 1
    
    while len(trading_days) < lookback:
        check_date = today - timedelta(days=days_back)
        # Excluir fines de semana Y festivos
        if check_date.weekday() < 5 and check_date not in MARKET_HOLIDAYS:
            trading_days.append(check_date)
        days_back += 1
    
    return trading_days


async def fetch_day(client: httpx.AsyncClient, symbol: str, trade_date: date) -> List[Dict]:
    """Fetch un día de datos (aggs 1m)"""
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{trade_date}/{trade_date}"
    try:
        resp = await client.get(url, params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": POLYGON_API_KEY})
        if resp.status_code == 200:
            return resp.json().get('results', [])
    except Exception:
        pass
    return []


async def fetch_range(client: httpx.AsyncClient, symbol: str, start_date: date, end_date: date) -> List[Dict]:
    """Fetch multi-día (aggs 1m) en una sola petición"""
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{start_date}/{end_date}"
    try:
        resp = await client.get(url, params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": POLYGON_API_KEY})
        if resp.status_code == 200:
            return resp.json().get('results', [])
    except Exception:
        pass
    return []


def bars_to_slots(bars: List[Dict], symbol: str, trade_date: date) -> List[Tuple]:
    """Convertir barras a slots con acumulación PineScript"""
    if not bars:
        return []
    
    accumulated = 0
    slots_dict = {}
    
    for bar in sorted(bars, key=lambda x: x['t']):
        dt = datetime.fromtimestamp(bar['t'] / 1000, tz=TIMEZONE)
        accumulated += bar['v']  # ACUMULAR como PineScript
        
        if dt.hour < 4 or dt.hour >= 20:
            continue
        
        slot_num = ((dt.hour - 4) * 60 + dt.minute) // 5
        slot_h = 4 + (slot_num * 5) // 60
        slot_m = (slot_num * 5) % 60
        
        # (date, symbol, slot_number, slot_time, volume_accumulated, trades_count, avg_price)
        slots_dict[slot_num] = (
            trade_date,
            symbol,
            slot_num,
            time(slot_h, slot_m),
            accumulated,  # VOLUMEN ACUMULADO
            bar.get('n', 0),
            bar.get('c', 0.0)
        )
    
    return list(slots_dict.values())


def bars_to_slots_multi(bars: List[Dict], symbol: str, include_dates: Set[date]) -> List[Tuple]:
    """Convertir barras multi-día a slots acumulados por DÍA, filtrando fechas a incluir."""
    if not bars:
        return []
    accumulated = 0
    current_day: date | None = None
    slots_dict: Dict[Tuple[date, int], Tuple] = {}
    for bar in sorted(bars, key=lambda x: x['t']):
        dt = datetime.fromtimestamp(bar['t'] / 1000, tz=TIMEZONE)
        day = dt.date()
        # Reset acumulado al cambiar de día
        if current_day != day:
            current_day = day
            accumulated = 0
        accumulated += bar.get('v', 0)
        if dt.hour < 4 or dt.hour >= 20:
            continue
        if include_dates and day not in include_dates:
            continue
        slot_num = ((dt.hour - 4) * 60 + dt.minute) // 5
        slot_h = 4 + (slot_num * 5) // 60
        slot_m = (slot_num * 5) % 60
        slots_dict[(day, slot_num)] = (
            day,
            symbol,
            slot_num,
            time(slot_h, slot_m),
            accumulated,
            0,
            bar.get('c', 0.0)
        )
    return list(slots_dict.values())


async def process_ticker(
    client: httpx.AsyncClient,
    symbol: str,
    trading_days: List[date],
    batch_buffer: List[Tuple],
    lock: asyncio.Lock
):
    """Procesar ticker completo - todos los días en paralelo"""
    try:
        # Descargar TODOS los días de una sola vez (rango multi‑día) y convertir a slots
        all_slots: List[Tuple] = []
        start_d = min(trading_days)
        end_d = max(trading_days)
        bars = await fetch_range(client, symbol, start_d, end_d)
        all_slots = bars_to_slots_multi(bars, symbol, set(trading_days))

        # Fallback: si el rango devolvió vacío, intentar día por día
        if not all_slots:
            tasks = [fetch_day(client, symbol, d) for d in trading_days]
            day_bars = await asyncio.gather(*tasks)
            for bars, trade_date in zip(day_bars, trading_days):
                slots = bars_to_slots(bars, symbol, trade_date)
                all_slots.extend(slots)
        
        # Agregar al buffer global para batch insert
        if all_slots:
            async with lock:
                batch_buffer.extend(all_slots)
                stats["slots"] += len(all_slots)
        
        stats["done"] += 1
        
    except:
        stats["done"] += 1


async def batch_inserter(db: TimescaleClient, batch_buffer: List[Tuple], lock: asyncio.Lock):
    """Worker que hace batch inserts masivos"""
    while stats["done"] < stats["total"]:
        await asyncio.sleep(2)  # Cada 2 segundos
        
        async with lock:
            if len(batch_buffer) >= BATCH_INSERT_SIZE:
                to_insert = batch_buffer[:BATCH_INSERT_SIZE]
                batch_buffer[:BATCH_INSERT_SIZE] = []
                
                try:
                    await db.executemany("""
                        INSERT INTO volume_slots (date, symbol, slot_number, slot_time, volume_accumulated, trades_count, avg_price)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (date, symbol, slot_number) DO UPDATE SET volume_accumulated = EXCLUDED.volume_accumulated
                    """, to_insert)
                    
                    elapsed = time_module.time() - stats["start"]
                    rate = stats["done"] / elapsed if elapsed > 0 else 0
                    percent = (stats["done"] / stats["total"]) * 100 if stats["total"] else 0
                    print(f"💾 Batch: {len(to_insert)} slots | {stats['done']}/{stats['total']} tickers ({percent:.1f}% | {rate:.1f}/seg) | {stats['slots']:,} slots totales")
                
                except Exception as e:
                    print(f"❌ Error batch: {e}")


# Nota: ya no calculamos días faltantes; insertamos el histórico completo por rango


async def main():
    print("\n" + "="*90)
    print("⚡ CARGA MASIVA ULTRA-RÁPIDA - MÉTODO PINESCRIPT - SIN LÍMITES")
    print("="*90)
    print()
    
    db = TimescaleClient()
    await db.connect()
    
    # Días hábiles (excluye fines de semana Y festivos)
    all_trading_days = get_trading_days(10)
    print(f"📅 Días de trading potenciales ({len(all_trading_days)}):")
    for d in all_trading_days:
        print(f"   {d} ({d.strftime('%A')})")
    print()
    
    # 🔍 DETECTAR QUÉ DÍAS YA EXISTEN EN LA BD
    print("🔍 Detectando días ya cargados en BD...")
    existing_dates_query = """
        SELECT DISTINCT date 
        FROM volume_slots 
        WHERE date >= $1 
        ORDER BY date DESC
    """
    oldest_date = min(all_trading_days)
    existing_rows = await db.fetch(existing_dates_query, oldest_date)
    existing_dates = {row['date'] for row in existing_rows}
    
    # Filtrar solo los días FALTANTES
    trading_days = [d for d in all_trading_days if d not in existing_dates]
    
    if existing_dates:
        print(f"   ✅ Ya existen: {len(existing_dates)} días")
        for d in sorted(existing_dates, reverse=True)[:5]:
            print(f"      - {d}")
    
    if not trading_days:
        print()
        print("="*90)
        print("✅ TODOS LOS DÍAS YA ESTÁN CARGADOS - NO HAY NADA QUE HACER")
        print("="*90)
        await db.disconnect()
        return
    
    print(f"   ⚠️  Faltan: {len(trading_days)} días")
    for d in sorted(trading_days, reverse=True):
        print(f"      - {d} ({d.strftime('%A')})")
    print()
    
    # Obtener UNIVERSO COMPLETO de Polygon (con paginación)
    print("📡 Obteniendo universo desde Polygon...")
    async with httpx.AsyncClient(timeout=30) as temp_client:
        base_url = "https://api.polygon.io/v3/reference/tickers"
        params = {"market": "stocks", "active": "true", "limit": 1000, "apiKey": POLYGON_API_KEY}
        polygon_tickers = []
        next_url = None
        page = 0
        try:
            while True:
                page += 1
                if next_url:
                    # next_url suele venir sin apiKey; añadirlo explícitamente
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
            if not polygon_tickers:
                # Fallback a BD si Polygon falla
                rows = await db.fetch("SELECT symbol FROM tickers_unified WHERE is_actively_trading = true ORDER BY symbol")
                polygon_tickers = [r['symbol'] for r in rows]
        except Exception:
            rows = await db.fetch("SELECT symbol FROM tickers_unified WHERE is_actively_trading = true ORDER BY symbol")
            polygon_tickers = [r['symbol'] for r in rows]
    
    print(f"   Total: {len(polygon_tickers):,} tickers")
    print()
    
    stats["total"] = len(polygon_tickers)
    stats["start"] = time_module.time()
    
    print(f"⚡ Configuración ULTRA-RÁPIDA:")
    print(f"   Tickers: {len(polygon_tickers):,}")
    print(f"   Días por ticker: {len(trading_days)}")
    print(f"   Total peticiones: {len(polygon_tickers) * len(trading_days):,}")
    print(f"   Concurrencia tickers: {MAX_CONCURRENT_TICKERS}")
    print(f"   Concurrencia requests: {MAX_CONCURRENT_REQUESTS}")
    print(f"   Batch inserts: {BATCH_INSERT_SIZE}")
    print(f"   Tiempo estimado: {len(polygon_tickers)/100/60:.1f} minutos (a 100 tickers/seg)")
    print()
    
    # NO borrar datos - solo actualizar/agregar
    print("📝 Modo actualización (no borra datos existentes)")
    print()
    
    # Batch buffer
    batch_buffer = []
    lock = asyncio.Lock()
    
    # HTTP client ultra-potente
    limits = httpx.Limits(max_connections=2000, max_keepalive_connections=1000)
    client = httpx.AsyncClient(timeout=60.0, limits=limits)
    
    # Iniciar batch inserter
    inserter_task = asyncio.create_task(batch_inserter(db, batch_buffer, lock))
    
    print("🚀 Procesando...")
    print()
    
    # Procesar TODO en paralelo masivo
    sem_ticker = asyncio.Semaphore(MAX_CONCURRENT_TICKERS)
    
    async def process_with_sem(symbol):
        async with sem_ticker:
            await process_ticker(client, symbol, trading_days, batch_buffer, lock)
    
    tasks = [process_with_sem(t) for t in polygon_tickers]
    await asyncio.gather(*tasks)
    
    # Flush buffer final (troceado en bloques de BATCH_INSERT_SIZE)
    print("\n💾 Guardando slots restantes...")
    async with lock:
        remaining = len(batch_buffer)
        idx = 0
        while batch_buffer:
            to_insert = batch_buffer[:BATCH_INSERT_SIZE]
            del batch_buffer[:BATCH_INSERT_SIZE]
            try:
                await db.executemany("""
                    INSERT INTO volume_slots (date, symbol, slot_number, slot_time, volume_accumulated, trades_count, avg_price)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (date, symbol, slot_number) DO UPDATE SET volume_accumulated = EXCLUDED.volume_accumulated
                """, to_insert)
                idx += len(to_insert)
                print(f"   ✅ Flush: {idx}/{remaining} slots guardados")
            except Exception as e:
                print(f"❌ Error en flush final: {e}")
                break
    
    inserter_task.cancel()
    
    elapsed = time_module.time() - stats["start"]
    
    print()
    print("="*90)
    print("✅ CARGA COMPLETADA")
    print("="*90)
    print(f"   Tickers: {stats['done']:,}/{stats['total']:,}")
    print(f"   Slots: {stats['slots']:,}")
    print(f"   Tiempo: {elapsed/60:.1f} minutos")
    print(f"   Velocidad: {stats['done']/(elapsed/60):.0f} tickers/min = {stats['done']/elapsed:.1f} tickers/seg")
    print()
    
    # Verificar tickers clave
    for sym in ['AAPL', 'RDDT', 'TSLA', 'NVDA']:
        row = await db.fetchrow(f"SELECT COUNT(*) as cnt, COUNT(DISTINCT date) as days FROM volume_slots WHERE symbol = '{sym}'")
        print(f"   {sym}: {row['cnt']} slots en {row['days']} días")
    
    await client.aclose()
    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

