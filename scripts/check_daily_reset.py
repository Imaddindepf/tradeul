#!/usr/bin/env python3
"""
Script para verificar que el sistema ha detectado cambios de día
y guardado los slots correctamente
"""

import asyncio
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.config.settings import settings


async def check_daily_reset():
    """Verifica el estado del reseteo diario"""
    
    print("=" * 60)
    print("🔍 VERIFICACIÓN DE RESETEO DIARIO")
    print("=" * 60)
    print()
    
    # Conectar a servicios
    redis = RedisClient()
    await redis.connect()
    
    db = TimescaleClient()
    await db.connect()
    
    try:
        # 1. Verificar sesión actual en Redis
        print("1️⃣ SESIÓN ACTUAL (Redis):")
        current_session = await redis.get("market:session:current")
        trading_date = await redis.get("market:session:trading_date")
        print(f"   Sesión: {current_session or 'No encontrada'}")
        print(f"   Trading Date: {trading_date or 'No encontrada'}")
        print()
        
        # 2. Verificar slots guardados en BD
        print("2️⃣ SLOTS GUARDADOS EN BD (últimos 7 días):")
        query = """
        SELECT 
            DATE(date) as fecha,
            COUNT(DISTINCT symbol) as tickers,
            COUNT(*) as total_slots,
            MIN(slot_number) as min_slot,
            MAX(slot_number) as max_slot,
            AVG(volume_accumulated) as avg_volume
        FROM volume_slots 
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY DATE(date) 
        ORDER BY fecha DESC;
        """
        
        results = await db.fetch(query)
        
        if results:
            print(f"   {'Fecha':<12} {'Tickers':<10} {'Slots':<10} {'Min':<6} {'Max':<6} {'Avg Vol':<15}")
            print("   " + "-" * 70)
            for row in results:
                fecha = row['fecha']
                tickers = row['tickers'] or 0
                slots = row['total_slots'] or 0
                min_slot = row['min_slot'] or 0
                max_slot = row['max_slot'] or 0
                avg_vol = row['avg_volume'] or 0
                print(f"   {fecha!s:<12} {tickers:<10} {slots:<10} {min_slot:<6} {max_slot:<6} {avg_vol:<15.0f}")
        else:
            print("   ⚠️  No se encontraron slots guardados")
        print()
        
        # 3. Verificar si hay slots del día anterior
        yesterday = (datetime.now().date() - timedelta(days=1))
        print(f"3️⃣ SLOTS DEL DÍA ANTERIOR ({yesterday}):")
        query = """
        SELECT 
            COUNT(DISTINCT symbol) as tickers,
            COUNT(*) as slots
        FROM volume_slots 
        WHERE DATE(date) = $1;
        """
        
        result = await db.fetch_one(query, yesterday)
        
        if result:
            tickers = result.get('tickers', 0) or 0
            slots = result.get('slots', 0) or 0
            if slots > 0:
                print(f"   ✅ {tickers} tickers con {slots} slots guardados")
            else:
                print(f"   ⚠️  No hay slots guardados para el día anterior")
        else:
            print(f"   ⚠️  No se encontraron datos")
        print()
        
        # 4. Verificar slots de hoy
        today = datetime.now().date()
        print(f"4️⃣ SLOTS DE HOY ({today}):")
        query = """
        SELECT 
            COUNT(DISTINCT symbol) as tickers,
            COUNT(*) as slots
        FROM volume_slots 
        WHERE DATE(date) = $1;
        """
        
        result = await db.fetch_one(query, today)
        
        if result:
            tickers = result.get('tickers', 0) or 0
            slots = result.get('slots', 0) or 0
            print(f"   {tickers} tickers con {slots} slots acumulados hoy")
        else:
            print(f"   Aún no hay slots de hoy (normal si es temprano)")
        print()
        
        # 5. Verificar caché histórico en Redis
        print("5️⃣ CACHÉ HISTÓRICO (Redis):")
        pattern = "analytics:rvol:historical:*"
        keys = []
        async for key in redis.scan_iter(pattern):
            keys.append(key)
        
        if keys:
            print(f"   ✅ {len(keys)} claves de caché histórico encontradas")
            # Mostrar algunas muestras
            sample_keys = keys[:5]
            for key in sample_keys:
                symbol = key.split(":")[-1] if ":" in key else key
                cached = await redis.get(key, deserialize=True)
                if cached:
                    print(f"      - {symbol}: {len(cached) if isinstance(cached, (list, dict)) else 'cached'}")
        else:
            print(f"   ⚠️  No hay caché histórico (se generará al procesar datos)")
        print()
        
        # 6. Resumen y recomendaciones
        print("=" * 60)
        print("📊 RESUMEN:")
        print("=" * 60)
        
        if results and len(results) > 0:
            latest_date = results[0]['fecha']
            latest_slots = results[0]['total_slots'] or 0
            
            if latest_date == yesterday:
                print(f"   ✅ Slots del día anterior ({yesterday}) guardados: {latest_slots} slots")
            elif latest_date < yesterday:
                print(f"   ⚠️  Últimos slots guardados son del {latest_date} (más antiguos que ayer)")
            else:
                print(f"   ℹ️  Últimos slots guardados son de hoy ({latest_date})")
            
            # Verificar si hay datos para calcular promedios
            query = """
            SELECT COUNT(DISTINCT DATE(date)) as days_with_data
            FROM volume_slots 
            WHERE date >= CURRENT_DATE - INTERVAL '30 days';
            """
            result = await db.fetch_one(query)
            days_count = result.get('days_with_data', 0) or 0 if result else 0
            
            if days_count >= 5:
                print(f"   ✅ {days_count} días con datos históricos (suficiente para promedios)")
            else:
                print(f"   ⚠️  Solo {days_count} días con datos (necesitas al menos 5 para promedios precisos)")
        else:
            print("   ⚠️  No se encontraron slots guardados en la BD")
            print("   💡 El sistema necesita acumular datos durante el día para guardarlos")
        
        print()
        
    finally:
        await redis.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(check_daily_reset())
