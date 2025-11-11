"""
Enrich Stale Metadata Task

Tarea de background para enriquecer metadata obsoleto (> 7 días).
Puede ejecutarse periódicamente via scheduler externo o manualmente.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List

import sys
sys.path.append('/app')

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class EnrichStaleMetadataTask:
    """
    Tarea para enriquecer metadata obsoleto
    """
    
    def __init__(self, metadata_manager):
        self.manager = metadata_manager
        self.stale_days = 7  # Metadata > 7 días se considera obsoleto
    
    async def execute(self, max_symbols: int = 100) -> dict:
        """
        Ejecuta enrichment de metadata obsoleto
        
        Args:
            max_symbols: Máximo de symbols a procesar
        
        Returns:
            Dict con resultados
        """
        logger.info("enrich_stale_task_starting", max_symbols=max_symbols)
        
        try:
            # 1. Obtener symbols con metadata obsoleto
            stale_symbols = await self._get_stale_symbols(max_symbols)
            
            if not stale_symbols:
                logger.info("no_stale_metadata_found")
                return {
                    "success": True,
                    "processed": 0,
                    "enriched": 0,
                    "failed": 0,
                    "message": "No stale metadata found"
                }
            
            logger.info("found_stale_metadata", count=len(stale_symbols))
            
            # 2. Enriquecer en batch
            results = await self.manager.bulk_enrich(stale_symbols, max_concurrent=5)
            
            enriched = sum(1 for success in results.values() if success)
            failed = len(stale_symbols) - enriched
            
            logger.info(
                "enrich_stale_task_completed",
                processed=len(stale_symbols),
                enriched=enriched,
                failed=failed
            )
            
            return {
                "success": True,
                "processed": len(stale_symbols),
                "enriched": enriched,
                "failed": failed,
                "results": results
            }
        
        except Exception as e:
            logger.error("enrich_stale_task_failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _get_stale_symbols(self, limit: int) -> List[str]:
        """
        Obtiene lista de symbols con metadata obsoleto
        """
        cutoff_date = datetime.now() - timedelta(days=self.stale_days)
        
        query = """
            SELECT symbol
            FROM ticker_metadata
            WHERE updated_at < $1
               OR updated_at IS NULL
            ORDER BY updated_at ASC NULLS FIRST
            LIMIT $2
        """
        
        rows = await self.manager.db.fetch(query, cutoff_date, limit)
        
        return [row["symbol"] for row in rows]

