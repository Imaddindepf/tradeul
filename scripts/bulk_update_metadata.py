#!/usr/bin/env python3
"""
Bulk Update Metadata - Actualización paralela y profesional
============================================================

Actualiza TODOS los tickers en ticker_universe con metadata completa desde Polygon.
Usa máxima paralelización respetando rate limits.

Características:
- Asyncio + httpx para máxima velocidad
- Semáforo para controlar concurrencia (20 concurrent requests)
- Progreso en tiempo real
- Manejo robusto de errores
- Respeta rate limits de Polygon (5 req/seg con burst)
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import List, Dict, Tuple

# Añadir path del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import httpx
    from shared.utils.timescale_client import TimescaleClient
    from shared.utils.logger import get_logger
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    print("Make sure you're running this from the Docker container")
    sys.exit(1)

logger = get_logger(__name__)

# Configuración
TICKER_METADATA_SERVICE_URL = os.getenv("TICKER_METADATA_SERVICE_URL", "http://localhost:8010")
TIMESCALE_HOST = os.getenv("TIMESCALE_HOST", "localhost")
TIMESCALE_PORT = int(os.getenv("TIMESCALE_PORT", "5432"))
TIMESCALE_USER = os.getenv("TIMESCALE_USER", "tradeul_user")
TIMESCALE_PASSWORD = os.getenv("TIMESCALE_PASSWORD", "tradeul_password_secure_123")
TIMESCALE_DB = os.getenv("TIMESCALE_DB", "tradeul")

# Parámetros de paralelización
MAX_CONCURRENT = 20  # Máximo de requests simultáneas
BATCH_SIZE = 100     # Tamaño de batch para logging
TIMEOUT = 30.0       # Timeout por request


class BulkUpdater:
    """Actualizador masivo de metadata con paralelización"""
    
    def __init__(self):
        self.db = None
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "start_time": None,
            "end_time": None,
        }
        self.failed_symbols = []
    
    async def connect_db(self):
        """Conectar a TimescaleDB"""
        db_url = f"postgresql://{TIMESCALE_USER}:{TIMESCALE_PASSWORD}@{TIMESCALE_HOST}:{TIMESCALE_PORT}/{TIMESCALE_DB}"
        self.db = TimescaleClient(database_url=db_url)
        await self.db.connect(min_size=2, max_size=10)
        logger.info("database_connected")
    
    async def get_all_symbols(self) -> List[str]:
        """Obtener todos los símbolos activos de ticker_universe"""
        query = """
            SELECT symbol 
            FROM ticker_universe 
            WHERE is_active = true
            ORDER BY symbol
        """
        rows = await self.db.fetch(query)
        symbols = [row['symbol'] for row in rows]
        logger.info("symbols_fetched", count=len(symbols))
        return symbols
    
    async def update_single_ticker(
        self, 
        client: httpx.AsyncClient, 
        symbol: str,
        semaphore: asyncio.Semaphore
    ) -> Tuple[str, bool, str]:
        """
        Actualizar un solo ticker usando el servicio
        
        Returns:
            Tuple de (symbol, success, message)
        """
        async with semaphore:
            try:
                url = f"{TICKER_METADATA_SERVICE_URL}/api/v1/metadata/{symbol}"
                params = {"force_refresh": "true"}
                
                response = await client.get(url, params=params, timeout=TIMEOUT)
                
                if response.status_code == 200:
                    return (symbol, True, "OK")
                elif response.status_code == 404:
                    return (symbol, False, "Not found in Polygon")
                else:
                    return (symbol, False, f"HTTP {response.status_code}")
                    
            except httpx.TimeoutException:
                return (symbol, False, "Timeout")
            except httpx.ConnectError:
                return (symbol, False, "Connection error")
            except Exception as e:
                return (symbol, False, str(e))
    
    async def update_batch(
        self,
        client: httpx.AsyncClient,
        symbols: List[str],
        semaphore: asyncio.Semaphore,
        batch_num: int
    ):
        """Actualizar un batch de símbolos"""
        tasks = [
            self.update_single_ticker(client, symbol, semaphore)
            for symbol in symbols
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Procesar resultados
        for result in results:
            if isinstance(result, Exception):
                self.stats["failed"] += 1
                logger.error("batch_exception", error=str(result))
            else:
                symbol, success, message = result
                if success:
                    self.stats["success"] += 1
                else:
                    self.stats["failed"] += 1
                    self.failed_symbols.append((symbol, message))
        
        # Log de progreso
        progress = (self.stats["success"] + self.stats["failed"]) / self.stats["total"] * 100
        elapsed = (datetime.now() - self.stats["start_time"]).total_seconds()
        rate = (self.stats["success"] + self.stats["failed"]) / elapsed if elapsed > 0 else 0
        
        logger.info(
            "batch_completed",
            batch=batch_num,
            progress=f"{progress:.1f}%",
            success=self.stats["success"],
            failed=self.stats["failed"],
            rate=f"{rate:.1f}/s"
        )
        
        # Print para feedback visual
        print(f"[{batch_num}] Progress: {progress:.1f}% | "
              f"✓ {self.stats['success']} | ✗ {self.stats['failed']} | "
              f"Rate: {rate:.1f}/s")
    
    async def run(self):
        """Ejecutar actualización completa"""
        print("\n" + "="*70)
        print("BULK METADATA UPDATE - Actualización Masiva Paralela")
        print("="*70 + "\n")
        
        try:
            # Conectar a DB
            print("📊 Conectando a TimescaleDB...")
            await self.connect_db()
            
            # Obtener símbolos
            print("📋 Obteniendo símbolos activos...")
            symbols = await self.get_all_symbols()
            self.stats["total"] = len(symbols)
            self.stats["start_time"] = datetime.now()
            
            print(f"✅ {self.stats['total']} símbolos a actualizar\n")
            print(f"⚙️  Configuración:")
            print(f"   - Concurrencia máxima: {MAX_CONCURRENT}")
            print(f"   - Batch size: {BATCH_SIZE}")
            print(f"   - Timeout: {TIMEOUT}s")
            print(f"   - Service URL: {TICKER_METADATA_SERVICE_URL}\n")
            
            print("🚀 Iniciando actualización paralela en 3 segundos...\n")
            await asyncio.sleep(3)
            
            # Crear semáforo para controlar concurrencia
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)
            
            # Crear cliente HTTP con keep-alive
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(TIMEOUT),
                limits=httpx.Limits(
                    max_keepalive_connections=MAX_CONCURRENT,
                    max_connections=MAX_CONCURRENT * 2
                )
            ) as client:
                # Procesar en batches para logging
                batch_num = 0
                for i in range(0, len(symbols), BATCH_SIZE):
                    batch = symbols[i:i + BATCH_SIZE]
                    batch_num += 1
                    await self.update_batch(client, batch, semaphore, batch_num)
            
            # Finalizar
            self.stats["end_time"] = datetime.now()
            elapsed = (self.stats["end_time"] - self.stats["start_time"]).total_seconds()
            
            print("\n" + "="*70)
            print("ACTUALIZACIÓN COMPLETADA")
            print("="*70)
            print(f"\n📊 Estadísticas Finales:")
            print(f"   Total procesados: {self.stats['total']}")
            print(f"   ✅ Exitosos: {self.stats['success']} ({self.stats['success']/self.stats['total']*100:.1f}%)")
            print(f"   ❌ Fallidos: {self.stats['failed']} ({self.stats['failed']/self.stats['total']*100:.1f}%)")
            print(f"   ⏱️  Tiempo total: {elapsed:.1f}s")
            print(f"   📈 Tasa promedio: {self.stats['total']/elapsed:.1f} tickers/s")
            
            if self.failed_symbols:
                print(f"\n❌ Símbolos fallidos ({len(self.failed_symbols)}):")
                for symbol, reason in self.failed_symbols[:20]:  # Mostrar primeros 20
                    print(f"   - {symbol}: {reason}")
                if len(self.failed_symbols) > 20:
                    print(f"   ... y {len(self.failed_symbols) - 20} más")
            
            print("\n✅ ¡Actualización completada!\n")
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Actualización interrumpida por el usuario")
            logger.warning("update_interrupted_by_user")
        except Exception as e:
            print(f"\n\n❌ Error fatal: {e}")
            logger.error("fatal_error", error=str(e), exc_info=True)
        finally:
            if self.db:
                await self.db.disconnect()
                logger.info("database_disconnected")


async def main():
    """Entry point"""
    updater = BulkUpdater()
    await updater.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bye!")
        sys.exit(0)

