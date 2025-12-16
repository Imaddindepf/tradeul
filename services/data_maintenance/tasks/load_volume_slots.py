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

# Importar desde shared/utils
from shared.utils.trading_days import get_trading_days
from shared.config.settings import settings

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
            # Obtener últimos 10 días de trading potenciales
            all_trading_days = get_trading_days(10)
            
            # 🔍 DETECTAR QUÉ DÍAS ESTÁN COMPLETOS (umbral dinámico basado en histórico)
            COMPLETENESS_THRESHOLD = 0.70  # 70% del promedio histórico
            MIN_ABSOLUTE_RECORDS = 50000   # Mínimo absoluto para evitar falsos positivos en días sin histórico
            
            # Consultar conteo de registros por día
            records_per_day_query = """
                SELECT date, COUNT(*) as record_count
                FROM volume_slots 
                WHERE date >= $1 
                GROUP BY date
                ORDER BY date DESC
            """
            oldest_date = min(all_trading_days)
            day_counts = await self.db.fetch(records_per_day_query, oldest_date)
            
            # Inicializar umbral con valor mínimo
            dynamic_threshold = MIN_ABSOLUTE_RECORDS
            complete_dates = set()
            incomplete_dates = {}
            
            if not day_counts:
                # Sin datos históricos, cargar todo
                logger.info("no_historical_data_found", message="Loading all days")
            else:
                # Calcular umbral dinámico basado en los mejores días
                all_counts = [row['record_count'] for row in day_counts]
                
                # Usar percentil 75 de los días existentes como referencia (ignora outliers bajos)
                sorted_counts = sorted(all_counts, reverse=True)
                top_days = sorted_counts[:max(1, len(sorted_counts) // 2)]  # Top 50% de días
                avg_complete_day = sum(top_days) / len(top_days) if top_days else 0
                
                # Umbral dinámico: 70% del promedio de días buenos
                dynamic_threshold = max(MIN_ABSOLUTE_RECORDS, int(avg_complete_day * COMPLETENESS_THRESHOLD))
                
                logger.info(
                    "detecting_complete_days_in_db",
                    avg_records_top_days=int(avg_complete_day),
                    dynamic_threshold=dynamic_threshold,
                    completeness_percent=int(COMPLETENESS_THRESHOLD * 100)
                )
                
                # Separar días completos vs incompletos
                for row in day_counts:
                    day = row['date']
                    count = row['record_count']
                    if count >= dynamic_threshold:
                        complete_dates.add(day)
                    else:
                        incomplete_dates[day] = count
            
            # Log días incompletos que serán recargados
            if incomplete_dates:
                logger.warning(
                    "incomplete_days_found_will_reload",
                    incomplete_count=len(incomplete_dates),
                    threshold_used=dynamic_threshold,
                    details={d.isoformat(): c for d, c in incomplete_dates.items()}
                )
                # Eliminar datos parciales antes de recargar
                for incomplete_day in incomplete_dates.keys():
                    delete_query = "DELETE FROM volume_slots WHERE date = $1"
                    await self.db.execute(delete_query, incomplete_day)
                    logger.info("deleted_incomplete_day", date=incomplete_day.isoformat(), 
                               records_deleted=incomplete_dates[incomplete_day])
            
            # Filtrar solo los días FALTANTES (no completos)
            trading_days = [d for d in all_trading_days if d not in complete_dates]
            existing_dates = complete_dates  # Para compatibilidad con código posterior
            
            if complete_dates:
                logger.info(
                    "complete_days_found",
                    complete_count=len(complete_dates),
                    last_3_dates=sorted([d.isoformat() for d in complete_dates], reverse=True)[:3]
                )
            
            if not trading_days:
                logger.info("all_days_complete", message="Todos los días tienen datos completos")
                return {
                    "success": True,
                    "message": "All days already complete",
                    "symbols_processed": 0,
                    "records_inserted": 0,
                    "days_complete": len(complete_dates)
                }
            
            logger.info(
                "missing_days_detected",
                missing_count=len(trading_days),
                missing_dates=[d.isoformat() for d in sorted(trading_days, reverse=True)]
            )
            
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
                days_to_load=len(trading_days)
            )
            
            # Procesar en paralelo
            async with httpx.AsyncClient() as client:
                records_inserted = 0
                semaphore = asyncio.Semaphore(200)  # Max 200 concurrent (servicio sin rate limits)
                
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
                records_inserted=records_inserted,
                days_loaded=len(trading_days),
                days_skipped=len(existing_dates)
            )
            
            # 🔥 VALIDACIÓN: Verificar datos
            # Si ya tenemos suficientes días completos, consideramos éxito
            MIN_COMPLETE_DAYS = 5  # Necesitamos al menos 5 días para RVOL
            
            if len(existing_dates) >= MIN_COMPLETE_DAYS:
                logger.info(
                    "volume_slots_validation_passed",
                    complete_days=len(existing_dates),
                    new_records=records_inserted,
                    message="Sufficient historical data available"
                )
            elif records_inserted == 0 and len(trading_days) > 0:
                logger.warning(
                    "volume_slots_no_new_data",
                    days_attempted=len(trading_days),
                    days_complete=len(existing_dates),
                    message="No new data, may be normal for current day"
                )
            
            # Solo falla si no tenemos suficientes días históricos
            if len(existing_dates) < MIN_COMPLETE_DAYS and records_inserted == 0:
                logger.error(
                    "insufficient_volume_slots_history",
                    expected_min_days=MIN_COMPLETE_DAYS,
                    actual_days=len(existing_dates)
                )
                return {
                    "success": False,
                    "error": f"Insufficient history: {len(existing_dates)} days, need >= {MIN_COMPLETE_DAYS}",
                    "symbols_processed": len(symbols),
                    "records_inserted": records_inserted,
                    "days_loaded": len(trading_days),
                    "days_skipped": len(existing_dates)
                }
            
            return {
                "success": True,
                "symbols_processed": len(symbols),
                "records_inserted": records_inserted,
                "days_loaded": len(trading_days),
                "days_skipped": len(existing_dates)
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
                FROM tickers_unified 
                WHERE is_actively_trading = true
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
                    "apiKey": settings.POLYGON_API_KEY
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
        """
        Convertir agregados de 1 min a slots de 5 min con VOLUMEN ACUMULADO
        
        MÉTODO PINESCRIPT (igual que load_massive_parallel.py):
        - Acumula BARRA POR BARRA (minuto a minuto)
        - Mantiene el último valor acumulado de cada slot
        - Extended hours: 4:00-20:00 ET (192 slots)
        """
        from zoneinfo import ZoneInfo
        from datetime import time
        
        if not aggs:
            return []
        
        TIMEZONE = ZoneInfo("America/New_York")
        accumulated = 0
        slots_dict = {}
        
        # 🔥 ACUMULACIÓN PINESCRIPT: barra por barra
        for bar in sorted(aggs, key=lambda x: x['t']):
            dt = datetime.fromtimestamp(bar['t'] / 1000, tz=TIMEZONE)
            accumulated += bar.get('v', 0)  # ACUMULAR como PineScript
            
            # Extended hours: 4:00-20:00 ET
            if dt.hour < 4 or dt.hour >= 20:
                continue
            
            # Calcular slot (0-191): desde 4:00 AM
            slot_num = ((dt.hour - 4) * 60 + dt.minute) // 5
            slot_h = 4 + (slot_num * 5) // 60
            slot_m = (slot_num * 5) % 60
            
            # Guardar el ÚLTIMO valor acumulado de cada slot
            # (sobreescribe si hay múltiples barras en el mismo slot)
            slots_dict[slot_num] = {
                "slot_index": slot_num,
                "slot_time": time(slot_h, slot_m, 0),  # ← OBJETO time, no string
                "volume_accumulated": accumulated,  # ← VOLUMEN ACUMULADO total
                "trades_count": bar.get('n', 0),
                "avg_price": bar.get('c', 0.0)
            }
        
        return list(slots_dict.values())
    
    async def _insert_slots(self, symbol: str, day: date, slots: List[Dict]) -> int:
        """
        Insertar slots en la base de datos con volumen ACUMULADO
        
        IMPORTANTE: volume_accumulated es el volumen total desde inicio del día
        hasta ese slot, NO solo el volumen de ese slot de 5 minutos.
        """
        if not slots:
            return 0
        
        query = """
            INSERT INTO volume_slots (date, symbol, slot_number, slot_time, volume_accumulated, trades_count, avg_price)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (date, symbol, slot_number)
            DO UPDATE SET 
                volume_accumulated = EXCLUDED.volume_accumulated,
                trades_count = EXCLUDED.trades_count,
                avg_price = EXCLUDED.avg_price
        """
        
        records = [
            (
                day,
                symbol,
                slot["slot_index"],
                slot["slot_time"],
                slot["volume_accumulated"],
                slot.get("trades_count", 0),
                slot.get("avg_price", 0.0)
            )
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

