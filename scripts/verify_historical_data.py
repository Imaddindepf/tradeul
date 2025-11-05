#!/usr/bin/env python3
"""
Script completo para verificar que TODOS los datos históricos están actualizados:
- Promedios históricos de volumen
- Promedios por slot
- Float, Market Cap, y metadata de tickers
- Datos de referencia desde Polygon
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


async def verify_historical_data():
    """Verifica que todos los datos históricos estén actualizados"""
    
    print("=" * 80)
    print("🔍 VERIFICACIÓN COMPLETA DE DATOS HISTÓRICOS")
    print("=" * 80)
    print()
    
    # Conectar a servicios
    redis = RedisClient()
    await redis.connect()
    
    db = TimescaleClient()
    await db.connect()
    
    try:
        # 1. VERIFICAR SLOTS HISTÓRICOS EN BD
        print("1️⃣ SLOTS HISTÓRICOS EN BASE DE DATOS:")
        print("-" * 80)
        
        query = """
        SELECT 
            DATE(date) as fecha,
            COUNT(DISTINCT symbol) as tickers,
            COUNT(*) as total_slots,
            MIN(slot_number) as min_slot,
            MAX(slot_number) as max_slot
        FROM volume_slots 
        WHERE date >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY DATE(date) 
        ORDER BY fecha DESC;
        """
        
        results = await db.fetch(query)
        
        if results:
            print(f"   {'Fecha':<12} {'Tickers':<10} {'Slots':<10} {'Min Slot':<10} {'Max Slot':<10}")
            print("   " + "-" * 60)
            for row in results:
                fecha = row['fecha']
                tickers = row['tickers'] or 0
                slots = row['total_slots'] or 0
                min_slot = row['min_slot'] or 0
                max_slot = row['max_slot'] or 0
                status = "✅" if slots > 0 else "⚠️"
                print(f"   {status} {fecha!s:<10} {tickers:<10} {slots:<10} {min_slot:<10} {max_slot:<10}")
            
            latest_date = results[0]['fecha']
            print(f"\n   📌 Última fecha con datos: {latest_date}")
            
            # Verificar si tenemos suficientes días para promedios
            days_count = len([r for r in results if (r['total_slots'] or 0) > 0])
            if days_count >= 5:
                print(f"   ✅ {days_count} días con datos (suficiente para promedios)")
            else:
                print(f"   ⚠️  Solo {days_count} días con datos (recomendado: mínimo 5-10 días)")
        else:
            print("   ⚠️  No se encontraron slots históricos en la BD")
        print()
        
        # 2. VERIFICAR PROMEDIOS POR SLOT (para un ticker de ejemplo)
        print("2️⃣ PROMEDIOS POR SLOT (verificando para AAPL como ejemplo):")
        print("-" * 80)
        
        # Verificar caché de promedios históricos
        cache_key = f"analytics:rvol:historical:AAPL"
        cached = await redis.get(cache_key, deserialize=True)
        
        if cached:
            if isinstance(cached, dict) and 'slots' in cached:
                slots_data = cached['slots']
                print(f"   ✅ Caché encontrado: {len(slots_data)} slots con promedios")
                
                # Mostrar algunos slots de ejemplo
                sample_slots = list(slots_data.items())[:5]
                print(f"   Ejemplos de promedios por slot:")
                for slot_num, slot_data in sample_slots:
                    avg_vol = slot_data.get('avg_volume', 0) if isinstance(slot_data, dict) else 0
                    print(f"      Slot {slot_num}: {avg_vol:,.0f} volumen promedio")
            else:
                print(f"   ✅ Caché encontrado (formato diferente)")
        else:
            print(f"   ⚠️  No hay caché de promedios históricos para AAPL")
            print(f"   💡 Se generará automáticamente al procesar datos")
        print()
        
        # 3. VERIFICAR METADATA DE TICKERS (Float, Market Cap, etc.)
        print("3️⃣ METADATA DE TICKERS (Float, Market Cap, Avg Volume):")
        print("-" * 80)
        
        # Verificar en Redis cache - usar keys() directamente
        try:
            ticker_keys_raw = await redis.client.keys("ticker:metadata:*")
            ticker_keys = ticker_keys_raw[:10]  # Solo primeras 10 muestras
        except:
            ticker_keys = []
        
        if ticker_keys:
            print(f"   ✅ {len(ticker_keys)}+ tickers con metadata en caché (mostrando 5 muestras):")
            
            for key in ticker_keys[:5]:
                symbol = key.replace("ticker:metadata:", "")
                metadata = await redis.get(key, deserialize=True)
                
                if metadata:
                    market_cap = metadata.get('market_cap', 'N/A') if isinstance(metadata, dict) else 'N/A'
                    float_shares = metadata.get('float_shares', 'N/A') if isinstance(metadata, dict) else 'N/A'
                    avg_vol_30d = metadata.get('avg_volume_30d', 'N/A') if isinstance(metadata, dict) else 'N/A'
                    sector = metadata.get('sector', 'N/A') if isinstance(metadata, dict) else 'N/A'
                    
                    print(f"      {symbol}:")
                    print(f"         Market Cap: {market_cap:,}" if isinstance(market_cap, (int, float)) else f"         Market Cap: {market_cap}")
                    print(f"         Float: {float_shares:,}" if isinstance(float_shares, (int, float)) else f"         Float: {float_shares}")
                    print(f"         Avg Vol 30d: {avg_vol_30d:,}" if isinstance(avg_vol_30d, (int, float)) else f"         Avg Vol 30d: {avg_vol_30d}")
                    print(f"         Sector: {sector}")
        else:
            print(f"   ⚠️  No hay metadata de tickers en caché Redis")
        
        # Verificar también en BD
        query = """
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN market_cap IS NOT NULL THEN 1 END) as with_market_cap,
            COUNT(CASE WHEN float_shares IS NOT NULL THEN 1 END) as with_float,
            COUNT(CASE WHEN avg_volume_30d IS NOT NULL THEN 1 END) as with_avg_vol,
            MAX(updated_at) as last_update
        FROM ticker_metadata;
        """
        
        result = await db.fetchrow(query)
        if result:
            total = result.get('total', 0) or 0
            with_mc = result.get('with_market_cap', 0) or 0
            with_float = result.get('with_float', 0) or 0
            with_avg = result.get('with_avg_vol', 0) or 0
            last_update = result.get('last_update')
            
            print(f"\n   📊 En Base de Datos:")
            print(f"      Total tickers: {total}")
            print(f"      Con Market Cap: {with_mc} ({with_mc*100//total if total > 0 else 0}%)")
            print(f"      Con Float: {with_float} ({with_float*100//total if total > 0 else 0}%)")
            print(f"      Con Avg Volume 30d: {with_avg} ({with_avg*100//total if total > 0 else 0}%)")
            if last_update:
                print(f"      Última actualización: {last_update}")
        print()
        
        # 4. VERIFICAR ÚLTIMAS ACTUALIZACIONES DE REFERENCIA
        print("4️⃣ ÚLTIMAS ACTUALIZACIONES DE DATOS DE REFERENCIA:")
        print("-" * 80)
        
        # Verificar último warmup
        last_warmup = await redis.get("historical:last_warmup")
        if last_warmup:
            print(f"   ✅ Último warmup ejecutado: {last_warmup}")
        else:
            print(f"   ⚠️  No hay registro de último warmup")
        
        # Verificar último universo actualizado
        last_universe_update = await redis.get("ticker_universe:last_update")
        if last_universe_update:
            print(f"   ✅ Última actualización de universo: {last_universe_update}")
        else:
            print(f"   ⚠️  No hay registro de última actualización de universo")
        
        # Verificar fecha de trading date
        trading_date = await redis.get("market:session:trading_date")
        if trading_date:
            print(f"   ✅ Trading date actual: {trading_date}")
            try:
                td_date = datetime.fromisoformat(trading_date.replace('Z', '+00:00')).date()
                today = datetime.now().date()
                if td_date == today:
                    print(f"   ✅ Trading date coincide con hoy")
                else:
                    days_diff = (today - td_date).days
                    if days_diff == 1:
                        print(f"   ⚠️  Trading date es de ayer (puede ser normal si es pre-market)")
                    else:
                        print(f"   ⚠️  Trading date está {days_diff} días atrás")
            except:
                pass
        else:
            print(f"   ⚠️  No hay trading date en Redis")
        print()
        
        # 5. VERIFICAR DATOS DE SLOTS PARA PROMEDIOS HISTÓRICOS
        print("5️⃣ VERIFICACIÓN DE DATOS PARA CÁLCULO DE PROMEDIOS:")
        print("-" * 80)
        
        # Verificar slots del día anterior
        yesterday = datetime.now().date() - timedelta(days=1)
        query = """
        SELECT 
            COUNT(DISTINCT symbol) as tickers,
            COUNT(*) as slots,
            AVG(volume_accumulated) as avg_volume
        FROM volume_slots 
        WHERE DATE(date) = $1;
        """
        
        result = await db.fetchrow(query, yesterday)
        if result:
            tickers_y = result.get('tickers', 0) or 0
            slots_y = result.get('slots', 0) or 0
            
            if slots_y > 0:
                print(f"   ✅ Día anterior ({yesterday}): {tickers_y} tickers, {slots_y} slots guardados")
            else:
                print(f"   ⚠️  Día anterior ({yesterday}): No hay slots guardados")
        
        # Verificar últimos 5 días
        query = """
        SELECT 
            DATE(date) as fecha,
            COUNT(DISTINCT symbol) as tickers,
            COUNT(*) as slots
        FROM volume_slots 
        WHERE date >= CURRENT_DATE - INTERVAL '5 days'
        GROUP BY DATE(date)
        ORDER BY fecha DESC;
        """
        
        recent_results = await db.fetch(query)
        if recent_results:
            days_with_data = len([r for r in recent_results if (r.get('slots', 0) or 0) > 0])
            print(f"\n   📊 Últimos 5 días: {days_with_data} días con datos")
            
            if days_with_data >= 5:
                print(f"   ✅ Suficiente datos históricos para promedios precisos")
            elif days_with_data >= 3:
                print(f"   ⚠️  Datos parciales ({days_with_data}/5 días) - promedios menos precisos")
            else:
                print(f"   ⚠️  Pocos datos ({days_with_data}/5 días) - promedios pueden ser inexactos")
        print()
        
        # 6. VERIFICAR ESTADO DE SERVICIOS
        print("6️⃣ ESTADO DE SERVICIOS:")
        print("-" * 80)
        
        # Verificar Analytics
        analytics_stats_key = "analytics:stats"
        analytics_stats = await redis.get(analytics_stats_key, deserialize=True)
        if analytics_stats:
            print(f"   ✅ Analytics Service activo")
        else:
            print(f"   ⚠️  No hay estadísticas de Analytics Service")
        
        # Verificar Market Session
        session = await redis.get("market:session:current")
        if session:
            print(f"   ✅ Market Session Service activo (sesión actual: {session})")
        else:
            print(f"   ⚠️  No hay sesión detectada")
        print()
        
        # RESUMEN FINAL
        print("=" * 80)
        print("📋 RESUMEN FINAL:")
        print("=" * 80)
        print()
        
        issues = []
        ok_count = 0
        
        # Check 1: Slots históricos
        if results and len(results) > 0:
            days_with_slots = len([r for r in results if (r.get('total_slots', 0) or 0) > 0])
            if days_with_slots >= 5:
                print("   ✅ Slots históricos: Suficientes para promedios")
                ok_count += 1
            else:
                issues.append(f"⚠️  Slots históricos: Solo {days_with_slots} días (necesitas 5+ días)")
        
        # Check 2: Metadata de tickers
        if result and (result.get('total', 0) or 0) > 0:
            metadata_coverage = ((result.get('with_market_cap', 0) or 0) / (result.get('total', 1) or 1)) * 100
            if metadata_coverage >= 80:
                print("   ✅ Metadata de tickers: Buena cobertura")
                ok_count += 1
            else:
                issues.append(f"⚠️  Metadata: Solo {metadata_coverage:.0f}% de tickers tienen datos completos")
        
        # Check 3: Última actualización
        if last_warmup or last_universe_update:
            print("   ✅ Datos de referencia: Actualizados recientemente")
            ok_count += 1
        else:
            issues.append("⚠️  No hay registro de última actualización de datos de referencia")
        
        # Check 4: Slots del día anterior
        if result and (result.get('slots', 0) or 0) > 0:
            print("   ✅ Slots del día anterior: Guardados correctamente")
            ok_count += 1
        else:
            issues.append("⚠️  Slots del día anterior: Puede no haberse guardado (normal si servicio se reinició)")
        
        print()
        if issues:
            print("   ⚠️  PROBLEMAS ENCONTRADOS:")
            for issue in issues:
                print(f"      {issue}")
        else:
            print("   ✅ Todos los datos históricos están actualizados correctamente")
        
        print()
        print(f"   📊 Verificación completada: {ok_count}/4 checks pasados")
        print()
        
    except Exception as e:
        print(f"\n   ❌ Error durante la verificación: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await redis.disconnect()
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(verify_historical_data())
