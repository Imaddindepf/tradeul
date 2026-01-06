#!/usr/bin/env python3
"""
Refresh Shares Outstanding from Polygon API
============================================

Script para actualizar shares_outstanding y market_cap de todos los tickers
activos usando Polygon API con alta concurrencia.

Uso:
    python refresh_shares_outstanding.py [--limit N] [--concurrency N]
"""

import asyncio
import os
import sys
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import httpx

# Setup path
sys.path.append('/app')

# Configuración desde variables de entorno
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "vjzI76TMiepqrMZKphpfs3SA54JFkhEx")

# Construir URL de Postgres desde variables individuales
PG_HOST = os.getenv("POSTGRES_HOST", "timescaledb")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_USER = os.getenv("POSTGRES_USER", "tradeul_user")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "tradeul_password_secure_123")
PG_DB = os.getenv("POSTGRES_DB", "tradeul")
POSTGRES_URL = f"postgresql://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"

# Construir URL de Redis desde variables individuales
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_PASS = os.getenv("REDIS_PASSWORD", "tradeul_redis_secure_2024")
REDIS_DB = os.getenv("REDIS_DB", "0")
REDIS_URL = f"redis://:{REDIS_PASS}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# Parsear argumentos
parser = argparse.ArgumentParser(description='Refresh shares_outstanding from Polygon')
parser.add_argument('--limit', type=int, default=0, help='Limit number of tickers (0 = all)')
parser.add_argument('--concurrency', type=int, default=100, help='Max concurrent requests')
parser.add_argument('--dry-run', action='store_true', help='Only fetch, do not update DB')
args = parser.parse_args()


class SharesRefresher:
    def __init__(self, concurrency: int = 100):
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        self.stats = {
            "total": 0,
            "updated": 0,
            "unchanged": 0,
            "errors": 0,
            "not_found": 0,
        }
        self.updates: List[Tuple] = []
        
    async def run(self, limit: int = 0, dry_run: bool = False):
        """Ejecutar actualización completa"""
        print(f"=" * 60)
        print(f"REFRESH SHARES OUTSTANDING FROM POLYGON")
        print(f"=" * 60)
        print(f"Concurrency: {self.concurrency}")
        print(f"Limit: {limit if limit > 0 else 'ALL'}")
        print(f"Dry run: {dry_run}")
        print()
        
        start_time = datetime.now()
        
        # 1. Obtener símbolos de la BD
        symbols = await self._get_active_symbols(limit)
        self.stats["total"] = len(symbols)
        print(f"📊 Tickers a procesar: {len(symbols)}")
        print()
        
        # 2. Fetch de Polygon en paralelo
        print("🔄 Consultando Polygon API...")
        async with httpx.AsyncClient(timeout=15.0) as client:
            tasks = [self._fetch_ticker(client, symbol) for symbol in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 3. Procesar resultados
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                self.stats["errors"] += 1
            elif result is None:
                self.stats["not_found"] += 1
            elif result.get("changed"):
                self.stats["updated"] += 1
                self.updates.append((
                    symbol,
                    result.get("shares_outstanding"),
                    result.get("market_cap"),
                    result.get("weighted_shares_outstanding"),
                ))
            else:
                self.stats["unchanged"] += 1
        
        print()
        print(f"📈 Resultados del fetch:")
        print(f"   Total procesados: {self.stats['total']}")
        print(f"   Con cambios: {self.stats['updated']}")
        print(f"   Sin cambios: {self.stats['unchanged']}")
        print(f"   No encontrados: {self.stats['not_found']}")
        print(f"   Errores: {self.stats['errors']}")
        print()
        
        # 4. Actualizar BD si no es dry run
        if not dry_run and self.updates:
            print(f"💾 Actualizando {len(self.updates)} registros en BD...")
            await self._update_database()
            print(f"✅ BD actualizada")
            
            # 5. Actualizar Redis
            print(f"🔄 Actualizando Redis...")
            await self._update_redis()
            print(f"✅ Redis actualizado")
        elif dry_run:
            print("⚠️  DRY RUN - No se actualizó la BD")
            if self.updates[:10]:
                print("\nPrimeros 10 cambios detectados:")
                for symbol, shares, mcap, weighted in self.updates[:10]:
                    shares_str = f"{shares:,}" if shares else "N/A"
                    mcap_str = f"{mcap:,}" if mcap else "N/A"
                    print(f"   {symbol}: shares={shares_str}, mcap={mcap_str}")
        
        duration = (datetime.now() - start_time).total_seconds()
        print()
        print(f"⏱️  Tiempo total: {duration:.1f}s")
        print(f"=" * 60)
        
        return self.stats
    
    async def _get_active_symbols(self, limit: int = 0) -> List[str]:
        """Obtener símbolos activos de la BD"""
        import asyncpg
        
        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            query = """
                SELECT symbol 
                FROM tickers_unified 
                WHERE is_actively_trading = true
                ORDER BY symbol
            """
            if limit > 0:
                query += f" LIMIT {limit}"
            
            rows = await conn.fetch(query)
            return [row['symbol'] for row in rows]
        finally:
            await conn.close()
    
    async def _fetch_ticker(self, client: httpx.AsyncClient, symbol: str) -> Optional[Dict]:
        """Fetch datos de un ticker desde Polygon"""
        async with self.semaphore:
            try:
                url = f"https://api.polygon.io/v3/reference/tickers/{symbol}"
                resp = await client.get(url, params={"apiKey": POLYGON_API_KEY})
                
                if resp.status_code == 404:
                    return None
                
                if resp.status_code == 429:
                    # Rate limited - esperar y reintentar
                    await asyncio.sleep(1)
                    resp = await client.get(url, params={"apiKey": POLYGON_API_KEY})
                
                if resp.status_code != 200:
                    return None
                
                data = resp.json().get("results", {})
                
                shares = (
                    data.get("share_class_shares_outstanding") or 
                    data.get("weighted_shares_outstanding")
                )
                market_cap = data.get("market_cap")
                weighted = data.get("weighted_shares_outstanding")
                
                # Consideramos cambio si tenemos datos
                return {
                    "shares_outstanding": int(shares) if shares else None,
                    "market_cap": int(market_cap) if market_cap else None,
                    "weighted_shares_outstanding": int(weighted) if weighted else None,
                    "changed": shares is not None or market_cap is not None
                }
                
            except Exception as e:
                return None
    
    async def _update_database(self):
        """Actualizar BD con los cambios"""
        import asyncpg
        
        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            # Batch update
            query = """
                UPDATE tickers_unified
                SET 
                    shares_outstanding = $2,
                    market_cap = $3,
                    updated_at = NOW()
                WHERE symbol = $1
            """
            
            batch_size = 500
            for i in range(0, len(self.updates), batch_size):
                batch = self.updates[i:i + batch_size]
                for symbol, shares, mcap, _ in batch:
                    if shares is not None or mcap is not None:
                        await conn.execute(
                            query,
                            symbol,
                            shares,
                            mcap
                        )
                
                print(f"   Procesados: {min(i + batch_size, len(self.updates))}/{len(self.updates)}")
                
        finally:
            await conn.close()
    
    async def _update_redis(self):
        """Actualizar Redis con datos frescos"""
        import redis.asyncio as redis
        
        r = redis.from_url(REDIS_URL)
        try:
            # Limpiar caches relacionados con metadata
            patterns = [
                "ticker:metadata:*",
                "screener:metadata:*",
            ]
            
            for pattern in patterns:
                cursor = 0
                deleted = 0
                while True:
                    cursor, keys = await r.scan(cursor, match=pattern, count=1000)
                    if keys:
                        await r.delete(*keys)
                        deleted += len(keys)
                    if cursor == 0:
                        break
                if deleted > 0:
                    print(f"   Eliminadas {deleted} keys de {pattern}")
            
            # Publicar evento de actualización
            await r.publish("maintenance:metadata_refreshed", "shares_outstanding_updated")
            
        finally:
            await r.close()


async def main():
    refresher = SharesRefresher(concurrency=args.concurrency)
    await refresher.run(limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())

