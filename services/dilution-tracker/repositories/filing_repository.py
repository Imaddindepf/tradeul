"""
Filing Repository
Persiste y recupera SEC filings de BD
"""

import sys
sys.path.append('/app')

from typing import List, Optional

from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

from models.filing_models import SECFilingCreate

logger = get_logger(__name__)


class FilingRepository:
    """Repository para SEC filings"""
    
    def __init__(self, db: TimescaleClient):
        self.db = db
    
    async def save_batch(self, filings: List[SECFilingCreate]) -> int:
        """Guardar múltiples filings"""
        if not filings:
            return 0
        
        try:
            query = """
            INSERT INTO sec_filings (
                ticker, filing_type, filing_date, report_date,
                accession_number, title, description, url,
                category, is_offering_related, is_dilutive
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (ticker, accession_number) DO UPDATE SET
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                url = EXCLUDED.url,
                fetched_at = NOW()
            """
            
            count = 0
            for filing in filings:
                await self.db.execute(
                    query,
                    filing.ticker,
                    filing.filing_type,
                    filing.filing_date,
                    filing.report_date,
                    filing.accession_number,
                    filing.title,
                    filing.description,
                    filing.url,
                    filing.category.value if filing.category else None,
                    filing.is_offering_related,
                    filing.is_dilutive
                )
                count += 1
            
            logger.info("filings_saved", count=count, ticker=filings[0].ticker)
            return count
            
        except Exception as e:
            logger.error("save_filings_failed", error=str(e))
            return 0
    
    async def get_by_ticker(
        self,
        ticker: str,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[dict]:
        """Obtener filings de un ticker"""
        try:
            if category:
                query = """
                SELECT *
                FROM sec_filings
                WHERE ticker = $1 AND category = $2
                ORDER BY filing_date DESC
                LIMIT $3
                """
                results = await self.db.fetch(query, ticker.upper(), category, limit)
            else:
                query = """
                SELECT *
                FROM sec_filings
                WHERE ticker = $1
                ORDER BY filing_date DESC
                LIMIT $2
                """
                results = await self.db.fetch(query, ticker.upper(), limit)
            
            return [dict(r) for r in results] if results else []
            
        except Exception as e:
            logger.error("get_filings_failed", ticker=ticker, error=str(e))
            return []

