"""
API Gateway Client
Cliente HTTP para consumir financieros desde API Gateway (fuente unificada)
"""

import sys
sys.path.append('/app')

import httpx
from typing import Optional, List, Dict, Any
from datetime import datetime

from shared.utils.logger import get_logger
from models.financial_models import FinancialStatementCreate

logger = get_logger(__name__)


class APIGatewayClient:
    """
    Cliente para consumir datos financieros desde API Gateway.
    Evita duplicar llamadas a FMP - usa la misma fuente que el comando FA.
    """
    
    def __init__(self, base_url: str = "http://api_gateway:8000"):
        self.base_url = base_url
        self.timeout = 60.0
    
    async def get_financials(
        self,
        ticker: str,
        period: str = "quarter",
        limit: int = 20
    ) -> Optional[List[FinancialStatementCreate]]:
        """
        Obtener financieros desde API Gateway.
        
        Args:
            ticker: Símbolo del ticker
            period: 'quarter' o 'annual'
            limit: Número de períodos
            
        Returns:
            Lista de FinancialStatementCreate
        """
        try:
            ticker = ticker.upper()
            url = f"{self.base_url}/api/v1/financials/{ticker}"
            params = {"period": period, "limit": limit}
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Convertir respuesta de API Gateway a nuestro modelo
                    statements = self._convert_to_statements(ticker, data)
                    
                    logger.info(
                        "api_gateway_financials_fetched",
                        ticker=ticker,
                        count=len(statements) if statements else 0
                    )
                    
                    return statements
                
                elif response.status_code == 404:
                    logger.warning("api_gateway_ticker_not_found", ticker=ticker)
                    return None
                
                else:
                    logger.error(
                        "api_gateway_error",
                        ticker=ticker,
                        status=response.status_code
                    )
                    return None
                    
        except Exception as e:
            logger.error("api_gateway_exception", ticker=ticker, error=str(e))
            return None
    
    def _convert_to_statements(
        self,
        ticker: str,
        data: Dict[str, Any]
    ) -> Optional[List[FinancialStatementCreate]]:
        """
        Convertir respuesta de API Gateway a FinancialStatementCreate.
        Combina income_statements, balance_sheets y cash_flows por fecha.
        """
        if not data:
            return None
        
        income_map = {i['period']['date']: i for i in data.get('income_statements', [])}
        balance_map = {b['period']['date']: b for b in data.get('balance_sheets', [])}
        cashflow_map = {c['period']['date']: c for c in data.get('cash_flows', [])}
        ratios_map = {r['period_date']: r for r in data.get('ratios', [])}
        
        # Usar balance_sheets como base (tiene todos los períodos)
        statements = []
        
        for period_date in sorted(balance_map.keys(), reverse=True):
            balance = balance_map.get(period_date, {})
            income = income_map.get(period_date, {})
            cashflow = cashflow_map.get(period_date, {})
            ratios = ratios_map.get(period_date, {})
            
            period_info = balance.get('period', income.get('period', cashflow.get('period', {})))
            
            try:
                statement = FinancialStatementCreate(
                    ticker=ticker,
                    period_date=datetime.strptime(period_date, '%Y-%m-%d').date(),
                    period_type=period_info.get('period', 'Q'),
                    fiscal_year=int(period_info.get('fiscal_year', 0)) if period_info.get('fiscal_year') else None,
                    source='gateway',  # max_length=10
                    
                    # Balance Sheet - Assets
                    total_assets=balance.get('total_assets'),
                    total_current_assets=balance.get('current_assets'),
                    cash_and_equivalents=balance.get('cash_and_equivalents'),
                    short_term_investments=balance.get('short_term_investments'),
                    receivables=balance.get('receivables'),
                    inventories=balance.get('inventory'),
                    other_current_assets=balance.get('other_current_assets'),
                    property_plant_equipment_net=balance.get('property_plant_equipment'),
                    goodwill=balance.get('goodwill'),
                    intangible_assets_net=balance.get('intangible_assets'),
                    other_noncurrent_assets=balance.get('other_noncurrent_assets'),
                    
                    # Balance Sheet - Liabilities
                    total_liabilities=balance.get('total_liabilities'),
                    total_current_liabilities=balance.get('current_liabilities'),
                    accounts_payable=balance.get('accounts_payable'),
                    debt_current=balance.get('short_term_debt'),
                    accrued_liabilities=balance.get('other_current_liabilities'),
                    deferred_revenue_current=balance.get('deferred_revenue'),
                    long_term_debt=balance.get('long_term_debt'),
                    other_noncurrent_liabilities=balance.get('other_noncurrent_liabilities'),
                    total_debt=balance.get('total_debt'),
                    
                    # Balance Sheet - Equity
                    stockholders_equity=balance.get('total_equity'),
                    common_stock=balance.get('common_stock'),
                    retained_earnings=balance.get('retained_earnings'),
                    treasury_stock=balance.get('treasury_stock'),
                    accumulated_other_comprehensive_income=balance.get('accumulated_other_income'),
                    
                    # Income Statement
                    revenue=income.get('revenue'),
                    cost_of_revenue=income.get('cost_of_revenue'),
                    gross_profit=income.get('gross_profit'),
                    research_development=income.get('research_development'),
                    selling_general_administrative=income.get('selling_general_admin'),
                    total_operating_expenses=income.get('operating_expenses'),
                    operating_income=income.get('operating_income'),
                    interest_expense=income.get('interest_expense'),
                    interest_income=income.get('interest_income'),
                    other_income_expense=income.get('other_income_expense'),
                    income_before_taxes=income.get('income_before_tax'),
                    income_taxes=income.get('income_tax'),
                    net_income=income.get('net_income'),
                    eps_basic=income.get('eps'),
                    eps_diluted=income.get('eps_diluted'),
                    ebitda=income.get('ebitda'),
                    
                    # Cash Flow
                    operating_cash_flow=cashflow.get('operating_cash_flow'),
                    depreciation_amortization=cashflow.get('depreciation'),
                    stock_based_compensation=cashflow.get('stock_compensation'),
                    change_in_working_capital=cashflow.get('change_working_capital'),
                    investing_cash_flow=cashflow.get('investing_cash_flow'),
                    capital_expenditures=cashflow.get('capex'),
                    acquisitions=cashflow.get('acquisitions'),
                    financing_cash_flow=cashflow.get('financing_cash_flow'),
                    debt_issuance_repayment=cashflow.get('debt_issued'),
                    dividends_paid=cashflow.get('dividends_paid'),
                    stock_repurchased=cashflow.get('stock_repurchased'),
                    change_in_cash=cashflow.get('net_change_cash'),
                    free_cash_flow=cashflow.get('free_cash_flow'),
                    
                    # Shares
                    shares_outstanding=int(income.get('shares_outstanding')) if income.get('shares_outstanding') else None,
                    weighted_avg_shares_basic=int(income.get('shares_outstanding')) if income.get('shares_outstanding') else None,
                    weighted_avg_shares_diluted=int(income.get('shares_diluted')) if income.get('shares_diluted') else None,
                    
                    # Ratios (from API Gateway)
                    current_ratio=ratios.get('current_ratio'),
                    debt_to_equity_ratio=ratios.get('debt_to_equity'),
                    working_capital=ratios.get('working_capital'),
                )
                
                statements.append(statement)
                
            except Exception as e:
                logger.warning("convert_statement_error", period_date=period_date, error=str(e))
                continue
        
        return statements if statements else None

