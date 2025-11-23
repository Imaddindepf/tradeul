#!/usr/bin/env python3
"""
Script para repoblar TODOS los metadatos con los campos expandidos de Polygon

Este script:
1. Obtiene todos los símbolos activos de ticker_universe
2. Fuerza refresh de metadata desde Polygon API
3. Respeta rate limits (5 req/seg = 200ms entre requests)
4. Reporta progreso y errores

Uso:
    python scripts/repopulate_metadata.py
    
    # O con límite:
    python scripts/repopulate_metadata.py --limit 100
"""

import asyncio
import sys
import os
from datetime import datetime
from typing import List, Dict
import asyncpg
import httpx

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.utils.logger import get_logger

logger = get_logger(__name__)

# =============================================
# CONFIGURACIÓN
# =============================================

DB_HOST = os.getenv("TIMESCALE_HOST", "localhost")
DB_PORT = int(os.getenv("TIMESCALE_PORT", "5432"))
DB_NAME = os.getenv("TIMESCALE_DB", "tradeul")
DB_USER = os.getenv("TIMESCALE_USER", "tradeul_user")
DB_PASSWORD = os.getenv("TIMESCALE_PASSWORD", "tradeul_password_secure_123")

METADATA_SERVICE_URL = "http://localhost:8010"
RATE_LIMIT_DELAY = 0.2  # 200ms entre requests = 5 req/seg
CONCURRENT_LIMIT = 3  # Max requests concurrentes


class MetadataRepopulator:
    """Repoblador de metadatos"""
    
    def __init__(self):
        self.db_pool = None
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "start_time": None,
            "end_time": None
        }
    
    async def connect_db(self):
        """Conectar a TimescaleDB"""
        try:
            self.db_pool = await asyncpg.create_pool(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                min_size=2,
                max_size=10
            )
            logger.info("database_connected")
        except Exception as e:
            logger.error("database_connection_failed", error=str(e))
            raise
    
    async def disconnect_db(self):
        """Desconectar de la base de datos"""
        if self.db_pool:
            await self.db_pool.close()
            logger.info("database_disconnected")
    
    async def get_active_symbols(self, limit: int = None) -> List[str]:
        """Obtener símbolos activos del universo"""
        try:
            query = """
                SELECT symbol 
                FROM tickers_unified 
                WHERE is_actively_trading = true
                ORDER BY symbol
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(query)
                symbols = [row['symbol'] for row in rows]
                
            logger.info("symbols_loaded", count=len(symbols))
            return symbols
        
        except Exception as e:
            logger.error("failed_to_load_symbols", error=str(e))
            return []
    
    async def refresh_metadata(self, client: httpx.AsyncClient, symbol: str) -> bool:
        """Refrescar metadata de un símbolo"""
        try:
            url = f"{METADATA_SERVICE_URL}/api/v1/metadata/{symbol}"
            params = {"force_refresh": "true"}
            
            response = await client.get(url, params=params, timeout=10.0)
            
            if response.status_code == 200:
                return True
            elif response.status_code == 404:
                logger.warning("symbol_not_found", symbol=symbol)
                self.stats["skipped"] += 1
                return False
            else:
                logger.error(
                    "refresh_failed",
                    symbol=symbol,
                    status_code=response.status_code
                )
                self.stats["failed"] += 1
                return False
        
        except httpx.TimeoutException:
            logger.error("refresh_timeout", symbol=symbol)
            self.stats["failed"] += 1
            return False
        
        except Exception as e:
            logger.error("refresh_error", symbol=symbol, error=str(e))
            self.stats["failed"] += 1
            return False
    
    async def process_batch(self, symbols: List[str]):
        """Procesar un lote de símbolos"""
        self.stats["total"] = len(symbols)
        self.stats["start_time"] = datetime.now()
        
        async with httpx.AsyncClient() as client:
            semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
            
            async def refresh_with_limits(symbol: str, index: int):
                """Refresh con rate limiting"""
                async with semaphore:
                    # Rate limiting
                    await asyncio.sleep(RATE_LIMIT_DELAY)
                    
                    success = await self.refresh_metadata(client, symbol)
                    
                    if success:
                        self.stats["success"] += 1
                    
                    # Reportar progreso cada 10 símbolos
                    if (index + 1) % 10 == 0:
                        progress_pct = ((index + 1) / len(symbols)) * 100
                        elapsed = (datetime.now() - self.stats["start_time"]).total_seconds()
                        rate = (index + 1) / elapsed if elapsed > 0 else 0
                        
                        logger.info(
                            "progress_update",
                            processed=index + 1,
                            total=len(symbols),
                            progress_pct=f"{progress_pct:.1f}%",
                            success=self.stats["success"],
                            failed=self.stats["failed"],
                            rate_per_sec=f"{rate:.2f}"
                        )
            
            tasks = [
                refresh_with_limits(symbol, i) 
                for i, symbol in enumerate(symbols)
            ]
            
            await asyncio.gather(*tasks)
        
        self.stats["end_time"] = datetime.now()
    
    def print_summary(self):
        """Imprimir resumen final"""
        duration = (self.stats["end_time"] - self.stats["start_time"]).total_seconds()
        success_rate = (self.stats["success"] / self.stats["total"] * 100) if self.stats["total"] > 0 else 0
        
        print("\n" + "="*60)
        print("RESUMEN DE REPOBLACIÓN DE METADATOS")
        print("="*60)
        print(f"Total de símbolos:       {self.stats['total']}")
        print(f"Actualizados con éxito:  {self.stats['success']}")
        print(f"Fallidos:                {self.stats['failed']}")
        print(f"Omitidos (no existen):   {self.stats['skipped']}")
        print(f"Tasa de éxito:           {success_rate:.1f}%")
        print(f"Duración total:          {duration:.1f}s")
        print(f"Velocidad promedio:      {self.stats['success'] / duration:.2f} símbolos/seg")
        print("="*60 + "\n")
        
        logger.info(
            "repopulation_completed",
            total=self.stats['total'],
            success=self.stats['success'],
            failed=self.stats['failed'],
            skipped=self.stats['skipped'],
            duration_seconds=round(duration, 1),
            success_rate_pct=round(success_rate, 1)
        )


async def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Repoblar metadatos de tickers")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Límite de símbolos a procesar (default: todos)"
    )
    
    args = parser.parse_args()
    
    repopulator = MetadataRepopulator()
    
    try:
        print("\n🚀 Iniciando repoblación de metadatos...\n")
        
        # Conectar a BD
        await repopulator.connect_db()
        
        # Obtener símbolos
        symbols = await repopulator.get_active_symbols(limit=args.limit)
        
        if not symbols:
            print("❌ No se encontraron símbolos para procesar")
            return
        
        print(f"📊 Procesando {len(symbols)} símbolos...")
        print(f"⚙️  Rate limit: {1/RATE_LIMIT_DELAY:.1f} req/seg")
        print(f"⚙️  Concurrencia: {CONCURRENT_LIMIT} requests paralelos\n")
        
        # Procesar
        await repopulator.process_batch(symbols)
        
        # Mostrar resumen
        repopulator.print_summary()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Proceso interrumpido por el usuario")
        if repopulator.stats["start_time"]:
            repopulator.stats["end_time"] = datetime.now()
            repopulator.print_summary()
    
    except Exception as e:
        logger.error("repopulation_failed", error=str(e))
        print(f"\n❌ Error: {e}")
    
    finally:
        await repopulator.disconnect_db()


if __name__ == "__main__":
    asyncio.run(main())

