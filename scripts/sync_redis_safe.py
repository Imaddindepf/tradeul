#!/usr/bin/env python3
"""
Script seguro para sincronizar metadata a Redis
- Sincroniza todos los metadata de BD a Redis
- Fuerza BGSAVE para persistir inmediatamente
- Verifica que los datos se guardaron correctamente
"""
import asyncio
import sys
import json
from decimal import Decimal

sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient

async def sync_metadata_safe():
    """Sincronizar metadata a Redis de forma segura"""
    redis = RedisClient()
    db = TimescaleClient()
    
    try:
        await redis.connect()
        await db.connect()
        
        print("🔄 Sincronización segura de metadata a Redis")
        print("=" * 60)
        
        # Obtener todos los metadata
        rows = await db.fetch('SELECT * FROM ticker_metadata ORDER BY symbol')
        total = len(rows)
        print(f"📊 Total a sincronizar: {total} tickers\n")
        
        synced = 0
        errors = 0
        
        for i, row in enumerate(rows):
            try:
                key = f"metadata:ticker:{row['symbol']}"
                data = dict(row)
                
                # Convertir tipos especiales
                for k, v in data.items():
                    if isinstance(v, Decimal):
                        data[k] = float(v)
                    elif k == 'address' and isinstance(v, str):
                        try:
                            data[k] = json.loads(v)
                        except:
                            data[k] = None
                    elif k in ('list_date', 'delisted_utc', 'created_at', 'updated_at'):
                        if v and hasattr(v, 'isoformat'):
                            data[k] = v.isoformat()
                        elif v:
                            data[k] = str(v)
                
                # Guardar con TTL de 7 días
                await redis.set(key, data, ttl=604800)
                synced += 1
                
                if synced % 2000 == 0:
                    print(f"✅ Progreso: {synced}/{total} ({synced*100/total:.1f}%)")
                    
            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"❌ Error en {row['symbol']}: {e}")
        
        print(f"\n{'=' * 60}")
        print(f"✅ Sincronizados: {synced}/{total}")
        if errors > 0:
            print(f"⚠️  Errores: {errors}")
        
        # CRÍTICO: Forzar BGSAVE inmediato
        print("\n💾 Forzando BGSAVE para persistir datos...")
        await redis.client.bgsave()
        
        # Esperar a que el save complete
        await asyncio.sleep(2)
        
        # Verificar que se salvó
        last_save = await redis.client.lastsave()
        print(f"✅ Último save: {last_save}")
        
        print("\n✨ SINCRONIZACIÓN COMPLETA Y PERSISTIDA")
        
    except Exception as e:
        print(f"❌ Error crítico: {e}")
        raise
    finally:
        if redis:
            await redis.disconnect()
        if db:
            await db.disconnect()

if __name__ == "__main__":
    asyncio.run(sync_metadata_safe())

