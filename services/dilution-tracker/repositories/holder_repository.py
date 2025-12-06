"""
Holder Repository
Persiste y recupera institutional holders de BD
"""

import sys
sys.path.append('/app')

from typing import List, Optional

from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

from models.holder_models import InstitutionalHolderCreate

logger = get_logger(__name__)


class HolderRepository:
    """Repository para institutional holders"""
    
    def __init__(self, db: TimescaleClient):
        self.db = db
    
    async def save_batch(self, holders: List[InstitutionalHolderCreate]) -> int:
        """Guardar múltiples holders"""
        if not holders:
            return 0
        
        try:
            query = """
            INSERT INTO institutional_holders (
                ticker, holder_name, report_date,
                shares_held, position_value, ownership_percent,
                position_change, position_change_percent,
                filing_date, form_type, cik
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (ticker, holder_name, report_date) DO UPDATE SET
                shares_held = EXCLUDED.shares_held,
                position_value = EXCLUDED.position_value,
                ownership_percent = EXCLUDED.ownership_percent,
                position_change = EXCLUDED.position_change,
                position_change_percent = EXCLUDED.position_change_percent,
                fetched_at = NOW()
            """
            
            count = 0
            for holder in holders:
                await self.db.execute(
                    query,
                    holder.ticker,
                    holder.holder_name,
                    holder.report_date,
                    holder.shares_held,
                    holder.position_value,
                    holder.ownership_percent,
                    holder.position_change,
                    holder.position_change_percent,
                    holder.filing_date,
                    holder.form_type,
                    holder.cik
                )
                count += 1
            
            logger.info("holders_saved", count=count, ticker=holders[0].ticker)
            return count
            
        except Exception as e:
            logger.error("save_holders_failed", error=str(e))
            return 0
    
    async def get_by_ticker(self, ticker: str, limit: int = 50) -> List[dict]:
        """
        Obtener holders de un ticker.
        Devuelve el reporte más reciente de CADA holder (no la fecha global más reciente)
        ya que cada institución reporta en diferentes fechas trimestrales.
        """
        try:
            # Obtener el reporte más reciente de cada holder usando ROW_NUMBER
            query = """
            WITH latest_reports AS (
                SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY holder_name ORDER BY report_date DESC) as rn
                FROM institutional_holders
                WHERE ticker = $1
                AND shares_held > 0
            )
            SELECT *
            FROM latest_reports
            WHERE rn = 1
            ORDER BY shares_held DESC
            LIMIT $2
            """
            
            results = await self.db.fetch(query, ticker.upper(), limit)
            return [dict(r) for r in results] if results else []
            
        except Exception as e:
            logger.error("get_holders_failed", ticker=ticker, error=str(e))
            return []

