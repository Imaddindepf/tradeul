#!/usr/bin/env python3
"""
Script para repoblar Redis con metadatos de tickers desde TimescaleDB
Útil después de un flushdb o cuando expiran los datos del cache
"""

import asyncio
import asyncpg
import redis.asyncio as redis
import json
import os
from datetime import datetime

async def main():
    # Configuración desde variables de entorno
    REDIS_HOST = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    
    TIMESCALE_HOST = os.getenv("TIMESCALE_HOST", "timescaledb")
    TIMESCALE_PORT = int(os.getenv("TIMESCALE_PORT", "5432"))
    TIMESCALE_USER = os.getenv("TIMESCALE_USER", "tradeul_user")
    TIMESCALE_PASSWORD = os.getenv("TIMESCALE_PASSWORD", "")
    TIMESCALE_DB = os.getenv("TIMESCALE_DB", "tradeul")
    
    # TTL para el cache (86400 segundos = 24 horas)
    CACHE_TTL = 86400
    
    print("🚀 Iniciando repoblación de Redis con metadatos de tickers...")
    print(f"📊 Conectando a TimescaleDB: {TIMESCALE_HOST}:{TIMESCALE_PORT}")
    
    # Conectar a TimescaleDB
    conn = await asyncpg.connect(
        host=TIMESCALE_HOST,
        port=TIMESCALE_PORT,
        user=TIMESCALE_USER,
        password=TIMESCALE_PASSWORD,
        database=TIMESCALE_DB
    )
    
    # Conectar a Redis
    print(f"🔴 Conectando a Redis: {REDIS_HOST}:{REDIS_PORT}")
    redis_client = await redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD if REDIS_PASSWORD else None,
        db=REDIS_DB,
        decode_responses=True
    )
    
    try:
        # Obtener todos los tickers activos de la tabla unificada
        query = """
            SELECT 
                symbol,
                company_name,
                exchange,
                sector,
                industry,
                market_cap,
                float_shares,
                shares_outstanding,
                avg_volume_30d,
                avg_volume_10d,
                avg_price_30d,
                beta,
                is_etf,
                is_actively_trading,
                updated_at
            FROM tickers_unified
            WHERE is_active = true
            ORDER BY symbol
        """
        
        print("📥 Obteniendo tickers de TimescaleDB...")
        rows = await conn.fetch(query)
        total = len(rows)
        print(f"✅ Se encontraron {total} tickers activos")
        
        # Insertar en Redis con pipeline para mayor eficiencia
        print("💾 Insertando metadatos en Redis...")
        
        inserted = 0
        batch_size = 100
        
        for i in range(0, total, batch_size):
            batch = rows[i:i+batch_size]
            pipe = redis_client.pipeline()
            
            for row in batch:
                # Convertir row a dict
                data = dict(row)
                
                # Convertir datetime a string ISO
                if data.get('updated_at'):
                    data['updated_at'] = data['updated_at'].isoformat()
                
                # Crear key
                key = f"metadata:ticker:{data['symbol']}"
                
                # Serializar a JSON
                value = json.dumps(data)
                
                # Agregar al pipeline con TTL
                pipe.setex(key, CACHE_TTL, value)
                inserted += 1
            
            # Ejecutar batch
            await pipe.execute()
            
            # Mostrar progreso
            if (i + batch_size) % 1000 == 0:
                print(f"  ⏳ Procesados {min(i + batch_size, total)}/{total} tickers...")
        
        print(f"\n✅ ¡Completado! Se insertaron {inserted} metadatos en Redis")
        print(f"⏰ TTL configurado: {CACHE_TTL} segundos ({CACHE_TTL/3600:.1f} horas)")
        
        # Verificar algunas claves
        print("\n🔍 Verificando algunos tickers de ejemplo:")
        for symbol in ['AAPL', 'TSLA', 'MSFT', 'NVDA']:
            key = f"metadata:ticker:{symbol}"
            exists = await redis_client.exists(key)
            if exists:
                ttl = await redis_client.ttl(key)
                print(f"  ✓ {symbol}: OK (TTL: {ttl}s / {ttl/3600:.1f}h)")
            else:
                print(f"  ✗ {symbol}: NO ENCONTRADO")
        
    finally:
        # Cerrar conexiones
        await conn.close()
        await redis_client.close()
        print("\n🏁 Script finalizado")

if __name__ == "__main__":
    asyncio.run(main())


