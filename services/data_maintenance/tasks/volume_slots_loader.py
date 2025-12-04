"""
Volume Slots Loader
===================

Carga datos de volume slots (5-minutos) de Polygon API para una fecha específica.

Cada día debería tener aproximadamente:
- Pre-market (4:00-9:30): 66 slots x N símbolos
- Market (9:30-16:00): 78 slots x N símbolos
- Post-market (16:00-20:00): 48 slots x N símbolos
Total: ~192 slots por símbolo

Con ~3000 símbolos activos: ~500,000 registros por día.

Lógica:
1. Verificar si el día ya tiene datos completos (>= 400,000 registros)
2. Si sí: skip
3. Si no: cargar desde Polygon API
"""

import asyncio
from datetime import date, datetime, time
from typing import Dict, List
import httpx

import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger
from shared.config.settings import settings

logger = get_logger(__name__)

# Mínimo de registros para considerar un día "completo"
MIN_RECORDS_COMPLETE = 400000


class VolumeSlotsLoader:
    """
    Cargador de volume slots (5-minutos)
    """
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
    
    async def load_day(self, target_date: date) -> Dict:
        """
        Cargar volume slots para un día específico
        
        Args:
            target_date: Fecha a cargar
            
        Returns:
            Dict con resultado
        """
        logger.info("volume_slots_loader_starting", target_date=str(target_date))
        
        # 1. Verificar si ya está completo
        existing_count = await self._count_existing(target_date)
        
        if existing_count >= MIN_RECORDS_COMPLETE:
            logger.info(
                "volume_slots_day_already_complete",
                target_date=str(target_date),
                existing_count=existing_count
            )
            return {
                "success": True,
                "action": "skipped",
                "reason": "Day already complete",
                "existing_count": existing_count
            }
        
        # Si hay datos parciales, mejor eliminarlos y recargar
        if existing_count > 0:
            logger.info(
                "volume_slots_deleting_partial_data",
                target_date=str(target_date),
                partial_count=existing_count
            )
            await self._delete_day(target_date)
        
        # 2. Obtener lista de símbolos activos
        symbols = await self._get_active_symbols()
        
        if not symbols:
            return {
                "success": False,
                "error": "No active symbols found"
            }
        
        logger.info(
            "volume_slots_loading_day",
            target_date=str(target_date),
            symbols_count=len(symbols)
        )
        
        # 3. Cargar datos desde Polygon
        inserted = 0
        symbols_processed = 0
        symbols_failed = 0
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            semaphore = asyncio.Semaphore(15)  # Menos concurrencia porque son más datos
            
            async def load_symbol(symbol: str) -> int:
                async with semaphore:
                    return await self._load_symbol_slots(client, symbol, target_date)
            
            # Procesar en chunks para evitar timeout
            chunk_size = 500
            for i in range(0, len(symbols), chunk_size):
                chunk = symbols[i:i + chunk_size]
                
                tasks = [load_symbol(sym) for sym in chunk]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, Exception):
                        symbols_failed += 1
                    elif isinstance(result, int):
                        inserted += result
                        if result > 0:
                            symbols_processed += 1
                    else:
                        symbols_failed += 1
                
                # Log progreso
                if (i + chunk_size) % 1000 == 0:
                    logger.info(
                        "volume_slots_progress",
                        processed=i + chunk_size,
                        total=len(symbols),
                        inserted=inserted
                    )
        
        # 4. Verificar resultado
        final_count = await self._count_existing(target_date)
        success = final_count >= MIN_RECORDS_COMPLETE * 0.5  # Más permisivo para dias con menos volumen
        
        logger.info(
            "volume_slots_loader_completed",
            target_date=str(target_date),
            records_inserted=inserted,
            symbols_processed=symbols_processed,
            symbols_failed=symbols_failed,
            final_count=final_count,
            success=success
        )
        
        return {
            "success": success,
            "records_inserted": inserted,
            "symbols_processed": symbols_processed,
            "symbols_failed": symbols_failed,
            "final_count": final_count,
            "target_date": str(target_date)
        }
    
    async def _count_existing(self, target_date: date) -> int:
        """Contar registros existentes para una fecha"""
        query = """
            SELECT COUNT(*) as count
            FROM volume_slots
            WHERE trading_date = $1
        """
        rows = await self.db.fetch(query, target_date)
        return rows[0]["count"] if rows else 0
    
    async def _delete_day(self, target_date: date):
        """Eliminar todos los registros de un día"""
        query = "DELETE FROM volume_slots WHERE trading_date = $1"
        await self.db.execute(query, target_date)
    
    async def _get_active_symbols(self) -> List[str]:
        """Obtener símbolos activos"""
        query = """
            SELECT symbol
            FROM tickers_unified
            WHERE is_actively_trading = true
            ORDER BY symbol
        """
        rows = await self.db.fetch(query)
        return [row["symbol"] for row in rows]
    
    async def _load_symbol_slots(
        self,
        client: httpx.AsyncClient,
        symbol: str,
        target_date: date
    ) -> int:
        """Cargar volume slots para un símbolo"""
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/5/minute/{target_date}/{target_date}"
        
        try:
            resp = await client.get(
                url,
                params={
                    "adjusted": "true",
                    "sort": "asc",
                    "limit": 500,  # Más que suficiente para un día
                    "apiKey": settings.POLYGON_API_KEY
                }
            )
            
            if resp.status_code != 200:
                return 0
            
            data = resp.json()
            results = data.get("results", [])
            
            if not results:
                return 0
            
            # Preparar batch insert
            values = []
            for bar in results:
                ts = datetime.fromtimestamp(bar["t"] / 1000)
                slot_time = ts.time()
                
                values.append((
                    target_date,
                    symbol,
                    slot_time,
                    bar["o"],
                    bar["h"],
                    bar["l"],
                    bar["c"],
                    bar["v"],
                    bar.get("vw"),
                    bar.get("n", 0)
                ))
            
            if not values:
                return 0
            
            # Batch insert
            query = """
                INSERT INTO volume_slots 
                (trading_date, symbol, slot_time, open, high, low, close, volume, vwap, trades_count)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (trading_date, symbol, slot_time) DO NOTHING
            """
            
            await self.db.executemany(query, values)
            
            return len(values)
            
        except Exception as e:
            logger.debug(f"Failed to load slots for {symbol}: {e}")
            return 0

