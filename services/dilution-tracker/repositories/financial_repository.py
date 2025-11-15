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
                -- Balance Sheet - Assets
                total_assets, total_current_assets, cash_and_equivalents, short_term_investments,
                receivables, inventories, other_current_assets,
                property_plant_equipment_net, goodwill, intangible_assets_net, other_noncurrent_assets,
                -- Balance Sheet - Liabilities
                total_liabilities, total_current_liabilities, accounts_payable, debt_current,
                accrued_liabilities, deferred_revenue_current, long_term_debt, other_noncurrent_liabilities, total_debt,
                -- Balance Sheet - Equity
                stockholders_equity, common_stock, additional_paid_in_capital, treasury_stock,
                retained_earnings, accumulated_other_comprehensive_income,
                -- Income Statement
                revenue, cost_of_revenue, gross_profit, research_development, selling_general_administrative,
                other_operating_expenses, total_operating_expenses, operating_income,
                interest_expense, interest_income, other_income_expense,
                income_before_taxes, income_taxes, net_income, eps_basic, eps_diluted, ebitda,
                -- Cash Flow
                operating_cash_flow, depreciation_amortization, stock_based_compensation,
                change_in_working_capital, other_operating_activities,
                investing_cash_flow, capital_expenditures, acquisitions, other_investing_activities,
                financing_cash_flow, debt_issuance_repayment, dividends_paid, stock_repurchased,
                other_financing_activities, change_in_cash, free_cash_flow,
                -- Shares
                shares_outstanding, weighted_avg_shares_basic, weighted_avg_shares_diluted,
                source
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, 
                    $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32, $33, $34, $35, $36, $37, $38,
                    $39, $40, $41, $42, $43, $44, $45, $46, $47, $48, $49, $50, $51, $52, $53, $54, $55, $56,
                    $57, $58, $59, $60, $61, $62, $63, $64, $65, $66, $67)
            ON CONFLICT (ticker, period_date, period_type) DO UPDATE SET
                total_assets = EXCLUDED.total_assets,
                revenue = EXCLUDED.revenue,
                cost_of_revenue = EXCLUDED.cost_of_revenue,
                research_development = EXCLUDED.research_development,
                selling_general_administrative = EXCLUDED.selling_general_administrative,
                ebitda = EXCLUDED.ebitda,
                net_income = EXCLUDED.net_income,
                operating_cash_flow = EXCLUDED.operating_cash_flow,
                free_cash_flow = EXCLUDED.free_cash_flow,
                fetched_at = NOW()
            """
            
            count = 0
            for stmt in statements:
                await self.db.execute(
                    query,
                    # Basic
                    stmt.ticker, stmt.period_date, stmt.period_type.value, stmt.fiscal_year,
                    # Balance Sheet - Assets
                    stmt.total_assets, stmt.total_current_assets, stmt.cash_and_equivalents, stmt.short_term_investments,
                    stmt.receivables, stmt.inventories, stmt.other_current_assets,
                    stmt.property_plant_equipment_net, stmt.goodwill, stmt.intangible_assets_net, stmt.other_noncurrent_assets,
                    # Balance Sheet - Liabilities
                    stmt.total_liabilities, stmt.total_current_liabilities, stmt.accounts_payable, stmt.debt_current,
                    stmt.accrued_liabilities, stmt.deferred_revenue_current, stmt.long_term_debt, stmt.other_noncurrent_liabilities, stmt.total_debt,
                    # Balance Sheet - Equity
                    stmt.stockholders_equity, stmt.common_stock, stmt.additional_paid_in_capital, stmt.treasury_stock,
                    stmt.retained_earnings, stmt.accumulated_other_comprehensive_income,
                    # Income Statement
                    stmt.revenue, stmt.cost_of_revenue, stmt.gross_profit, stmt.research_development, stmt.selling_general_administrative,
                    stmt.other_operating_expenses, stmt.total_operating_expenses, stmt.operating_income,
                    stmt.interest_expense, stmt.interest_income, stmt.other_income_expense,
                    stmt.income_before_taxes, stmt.income_taxes, stmt.net_income, stmt.eps_basic, stmt.eps_diluted, stmt.ebitda,
                    # Cash Flow
                    stmt.operating_cash_flow, stmt.depreciation_amortization, stmt.stock_based_compensation,
                    stmt.change_in_working_capital, stmt.other_operating_activities,
                    stmt.investing_cash_flow, stmt.capital_expenditures, stmt.acquisitions, stmt.other_investing_activities,
                    stmt.financing_cash_flow, stmt.debt_issuance_repayment, stmt.dividends_paid, stmt.stock_repurchased,
                    stmt.other_financing_activities, stmt.change_in_cash, stmt.free_cash_flow,
                    # Shares
                    stmt.shares_outstanding, stmt.weighted_avg_shares_basic, stmt.weighted_avg_shares_diluted,
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

