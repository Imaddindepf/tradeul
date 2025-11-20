"""
Cleanup Old Data Task
Limpia datos históricos antiguos para prevenir crecimiento infinito de BD
"""

import sys
sys.path.append('/app')

from datetime import date, timedelta
from typing import Dict

from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class CleanupOldDataTask:
    """
    Tarea: Limpiar datos históricos antiguos
    
    Basado en PineScript RVOL original:
    - period = 5 días de TRADING (no calendario)
    - "The more recent the data is, the more relevant it is"
    
    Considerando festivos/fines de semana:
    - 5 días trading = ~10 días calendario normales
    - + Festivos (Thanksgiving, Christmas, New Year) = +5 días
    - = 15 días calendario seguro
    
    Limpia:
    - volume_slots > 15 días calendario (garantiza 5+ días trading)
    - market_data_daily > 2 años (opcional, comentado)
    
    Impacto:
    - Cada día = 600K rows × 11K tickers = ~38MB
    - 15 días = ~570MB (óptimo con margen de seguridad)
    - 21 días actual = ~800MB
    - Sin cleanup: +1.1GB/mes → 14GB/año
    - Con cleanup 15d: Estable en ~570MB (-73% vs 2.1GB)
    """
    
    name = "cleanup_old_data"
    
    def __init__(self, timescale_client: TimescaleClient):
        self.db = timescale_client
    
    async def execute(self, target_date: date) -> Dict:
        """
        Ejecutar limpieza de datos antiguos
        
        Solo se ejecuta 1 vez por semana para no impactar performance
        """
        try:
            logger.info("cleanup_task_starting", target_date=str(target_date))
            
            # Solo ejecutar los domingos (día 6)
            if target_date.weekday() != 6:
                logger.info("cleanup_skipped_not_sunday", weekday=target_date.weekday())
                return {
                    "success": True,
                    "message": "Cleanup only runs on Sundays",
                    "rows_deleted": 0
                }
            
            total_deleted = 0
            
            # 1. Limpiar volume_slots > 15 días calendario
            # RVOL necesita 5 días de TRADING
            # 5 días trading = ~10 días calendario + 5 días buffer festivos = 15 días
            # Esto garantiza que SIEMPRE haya suficientes días de trading disponibles
            cutoff_date = target_date - timedelta(days=15)
            
            logger.info("cleanup_volume_slots_starting", cutoff_date=str(cutoff_date))
            
            query_count = """
                SELECT COUNT(*) as count 
                FROM volume_slots 
                WHERE date < $1
            """
            
            result = await self.db.fetchrow(query_count, cutoff_date)
            rows_to_delete = result['count'] if result else 0
            
            if rows_to_delete > 0:
                logger.info("volume_slots_to_delete", count=rows_to_delete, cutoff=str(cutoff_date))
                
                query_delete = """
                    DELETE FROM volume_slots 
                    WHERE date < $1
                """
                
                await self.db.execute(query_delete, cutoff_date)
                total_deleted += rows_to_delete
                
                logger.info("volume_slots_cleaned", deleted=rows_to_delete)
            else:
                logger.info("no_old_volume_slots_to_clean")
            
            # 2. Limpieza opcional: market_data_daily > 2 años (comentado por ahora)
            # cutoff_ohlc = target_date - timedelta(days=730)
            # ...
            
            logger.info(
                "cleanup_task_completed",
                total_deleted=total_deleted,
                cutoff_date=str(cutoff_date)
            )
            
            return {
                "success": True,
                "rows_deleted": total_deleted,
                "cutoff_date": str(cutoff_date),
                "message": f"Deleted {total_deleted} old rows"
            }
        
        except Exception as e:
            logger.error("cleanup_task_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "rows_deleted": 0
            }

