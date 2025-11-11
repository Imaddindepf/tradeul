"""
Load Volume Slots Task
Carga volume slots de 5 minutos para cálculo de RVOL
"""

import asyncio
import sys
sys.path.append('/app')

from datetime import date, datetime, timedelta
from typing import Dict, List
import httpx

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

# Importar lógica del script existente
from scripts.load_massive_parallel import (
    get_trading_days,
    POLYGON_API_KEY
)

logger = get_logger(__name__)


class LoadVolumeSlotsTask:
    """
    Tarea: Cargar volume slots de 5 minutos
    
    - Carga últimos 10 días de agregados de 1 minuto
    - Convierte a slots de 5 minutos
    - Actualiza volume_slots en TimescaleDB para RVOL
    """
    
    name = "volume_slots"
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
    
    async def execute(self, target_date: date) -> Dict:
        """
        Ejecutar carga de volume slots
        
        Args:
            target_date: Fecha objetivo
        
        Returns:
            Dict con resultado
        """
        logger.info(
            "volume_slots_task_starting",
            target_date=target_date.isoformat()
        )
        
        try:
            # Obtener últimos 10 días de trading
            trading_days = get_trading_days(10)
            
            # Obtener símbolos activos
            symbols = await self._get_active_symbols()
            
            if not symbols:
                logger.warning("no_symbols_found")
                return {
                    "success": False,
                    "error": "No symbols found"
                }
            
            logger.info(
                "volume_slots_symbols_loaded",
                count=len(symbols),
                days=len(trading_days)
            )
            
            # Procesar en paralelo
            async with httpx.AsyncClient() as client:
                records_inserted = 0
                semaphore = asyncio.Semaphore(10)
                
                async def load_with_semaphore(symbol: str):
                    async with semaphore:
                        return await self._load_symbol_slots(client, symbol, trading_days)
                
                tasks = [load_with_semaphore(sym) for sym in symbols]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, int):
                        records_inserted += result
            
            logger.info(
                "volume_slots_task_completed",
                symbols_processed=len(symbols),
                records_inserted=records_inserted
            )
            
            return {
                "success": True,
                "symbols_processed": len(symbols),
                "records_inserted": records_inserted
            }
        
        except Exception as e:
            logger.error(
                "volume_slots_task_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _get_active_symbols(self) -> List[str]:
        """Obtener símbolos activos"""
        try:
            query = """
                SELECT DISTINCT symbol 
                FROM ticker_universe 
                WHERE status = 'active'
                ORDER BY symbol
            """
            rows = await self.db.fetch(query)
            return [row['symbol'] for row in rows]
        except Exception as e:
            logger.error("failed_to_get_symbols", error=str(e))
            return []
    
    async def _load_symbol_slots(
        self,
        client: httpx.AsyncClient,
        symbol: str,
        trading_days: List[date]
    ) -> int:
        """Cargar volume slots para un símbolo"""
        total_inserted = 0
        
        for day in trading_days:
            try:
                # Fetch 1-minute aggregates
                aggs = await self._fetch_minute_aggs(client, symbol, day)
                if not aggs:
                    continue
                
                # Convert to 5-minute slots
                slots = self._convert_to_5min_slots(aggs, day)
                if not slots:
                    continue
                
                # Insert into database
                inserted = await self._insert_slots(symbol, day, slots)
                total_inserted += inserted
            
            except Exception as e:
                logger.debug(f"Error loading {symbol} {day}: {e}")
                continue
        
        return total_inserted
    
    async def _fetch_minute_aggs(
        self,
        client: httpx.AsyncClient,
        symbol: str,
        day: date
    ) -> List[Dict]:
        """Obtener agregados de 1 minuto de Polygon"""
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{day}/{day}"
        
        try:
            resp = await client.get(
                url,
                params={
                    "adjusted": "true",
                    "sort": "asc",
                    "limit": 50000,
                    "apiKey": POLYGON_API_KEY
                },
                timeout=15.0
            )
            
            if resp.status_code == 200:
                data = resp.json()
                return data.get('results', [])
        
        except Exception as e:
            logger.debug(f"Error fetching {symbol} {day}: {e}")
        
        return []
    
    def _convert_to_5min_slots(self, aggs: List[Dict], day: date) -> List[Dict]:
        """Convertir agregados de 1 min a slots de 5 min"""
        from collections import defaultdict
        
        # Agrupar por slot de 5 minutos
        slots_data = defaultdict(lambda: {"volume": 0, "count": 0})
        
        for agg in aggs:
            # Convertir timestamp a hora ET
            ts = datetime.fromtimestamp(agg['t'] / 1000)
            
            # Calcular slot (0-77)
            # Pre-market: 4:00-9:30 AM = 66 slots (5 min cada uno)
            # Market: 9:30-16:00 = 78 slots
            # Usar simplificación: minutos desde medianoche / 5
            minutes_since_midnight = ts.hour * 60 + ts.minute
            slot_index = minutes_since_midnight // 5
            
            # Acumular volumen
            slots_data[slot_index]["volume"] += agg.get('v', 0)
            slots_data[slot_index]["count"] += 1
        
        # Convertir a lista
        slots = []
        for slot_idx, data in slots_data.items():
            if data["volume"] > 0:
                slots.append({
                    "slot_index": slot_idx,
                    "volume": data["volume"]
                })
        
        return slots
    
    async def _insert_slots(self, symbol: str, day: date, slots: List[Dict]) -> int:
        """Insertar slots en la base de datos"""
        if not slots:
            return 0
        
        query = """
            INSERT INTO volume_slots (date, symbol, slot_index, volume)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (date, symbol, slot_index)
            DO UPDATE SET volume = EXCLUDED.volume
        """
        
        records = [
            (day, symbol, slot["slot_index"], slot["volume"])
            for slot in slots
        ]
        
        try:
            await self.db.executemany(query, records)
            return len(records)
        except Exception as e:
            logger.error(
                "failed_to_insert_slots",
                symbol=symbol,
                date=day.isoformat(),
                error=str(e)
            )
            return 0

