"""
Financial Repository
Persiste y recupera financial statements de BD
"""

import sys
sys.path.append('/app')

from typing import List, Optional
from datetime import date

from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

from models.financial_models import FinancialStatement, FinancialStatementCreate

logger = get_logger(__name__)


class FinancialRepository:
    """Repository para financial statements"""
    
    def __init__(self, db: TimescaleClient):
        self.db = db
    
    async def save_batch(self, statements: List[FinancialStatementCreate]) -> int:
        """
        Guardar múltiples financial statements
        
        Returns:
            Número de statements guardados
        """
        if not statements:
            return 0
        
        try:
            query = """
            INSERT INTO financial_statements (
                ticker, period_date, period_type, fiscal_year,
                total_assets, total_liabilities, stockholders_equity,
                cash_and_equivalents, short_term_investments, total_debt,
                total_current_assets, total_current_liabilities,
                revenue, gross_profit, operating_income, net_income,
                eps_basic, eps_diluted,
                operating_cash_flow, investing_cash_flow, financing_cash_flow, free_cash_flow,
                shares_outstanding, weighted_avg_shares_basic, weighted_avg_shares_diluted,
                source
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26)
            ON CONFLICT (ticker, period_date, period_type) DO UPDATE SET
                total_assets = EXCLUDED.total_assets,
                total_liabilities = EXCLUDED.total_liabilities,
                stockholders_equity = EXCLUDED.stockholders_equity,
                cash_and_equivalents = EXCLUDED.cash_and_equivalents,
                short_term_investments = EXCLUDED.short_term_investments,
                total_debt = EXCLUDED.total_debt,
                revenue = EXCLUDED.revenue,
                net_income = EXCLUDED.net_income,
                operating_cash_flow = EXCLUDED.operating_cash_flow,
                free_cash_flow = EXCLUDED.free_cash_flow,
                shares_outstanding = EXCLUDED.shares_outstanding,
                fetched_at = NOW()
            """
            
            count = 0
            for stmt in statements:
                await self.db.execute(
                    query,
                    stmt.ticker,
                    stmt.period_date,
                    stmt.period_type.value,
                    stmt.fiscal_year,
                    stmt.total_assets,
                    stmt.total_liabilities,
                    stmt.stockholders_equity,
                    stmt.cash_and_equivalents,
                    stmt.short_term_investments,
                    stmt.total_debt,
                    stmt.total_current_assets,
                    stmt.total_current_liabilities,
                    stmt.revenue,
                    stmt.gross_profit,
                    stmt.operating_income,
                    stmt.net_income,
                    stmt.eps_basic,
                    stmt.eps_diluted,
                    stmt.operating_cash_flow,
                    stmt.investing_cash_flow,
                    stmt.financing_cash_flow,
                    stmt.free_cash_flow,
                    stmt.shares_outstanding,
                    stmt.weighted_avg_shares_basic,
                    stmt.weighted_avg_shares_diluted,
                    stmt.source
                )
                count += 1
            
            logger.info("financial_statements_saved", count=count, ticker=statements[0].ticker)
            return count
            
        except Exception as e:
            logger.error("save_financial_statements_failed", error=str(e))
            return 0
    
    async def get_by_ticker(
        self,
        ticker: str,
        limit: int = 20
    ) -> List[dict]:
        """Obtener financial statements de un ticker"""
        try:
            query = """
            SELECT *
            FROM financial_statements
            WHERE ticker = $1
            ORDER BY period_date DESC
            LIMIT $2
            """
            
            results = await self.db.fetch(query, ticker.upper(), limit)
            return [dict(r) for r in results] if results else []
            
        except Exception as e:
            logger.error("get_financials_failed", ticker=ticker, error=str(e))
            return []
    
    async def get_latest(self, ticker: str) -> Optional[dict]:
        """Obtener el financial statement más reciente"""
        results = await self.get_by_ticker(ticker, limit=1)
        return results[0] if results else None

