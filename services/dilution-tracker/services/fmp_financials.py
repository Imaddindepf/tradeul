"""
FMP Financials Service
Obtiene financial statements (Balance Sheet, Income Statement, Cash Flow) desde FMP
"""

import sys
sys.path.append('/app')

from typing import Optional, List, Dict
from datetime import date, datetime
from decimal import Decimal

from shared.utils.logger import get_logger
from services.base_fmp_service import BaseFMPService
from models.financial_models import FinancialStatementCreate, FinancialPeriod

logger = get_logger(__name__)


class FMPFinancialsService(BaseFMPService):
    """
    Servicio para obtener financial statements desde FMP
    """
    
    async def get_financial_statements(
        self,
        ticker: str,
        period: str = "quarter",  # 'quarter' o 'annual'
        limit: int = 40
    ) -> Optional[List[FinancialStatementCreate]]:
        """
        Obtener financial statements completos (todos los statements combinados)
        
        Args:
            ticker: Símbolo del ticker
            period: 'quarter' o 'annual'
            limit: Número de períodos a obtener
        
        Returns:
            Lista de financial statements o None
        """
        try:
            # Obtener los 3 tipos de statements
            balance_sheets = await self.get_balance_sheets(ticker, period, limit)
            income_statements = await self.get_income_statements(ticker, period, limit)
            cash_flows = await self.get_cash_flows(ticker, period, limit)
            
            if not balance_sheets:
                logger.warning("no_balance_sheets", ticker=ticker)
                return None
            
            # Combinar statements por fecha
            combined = {}
            
            # Procesar balance sheets
            for bs in balance_sheets:
                period_date = bs['date']
                combined[period_date] = {
                    'period_date': period_date,
                    'balance_sheet': bs,
                    'income_statement': None,
                    'cash_flow': None
                }
            
            # Agregar income statements
            if income_statements:
                for income in income_statements:
                    period_date = income['date']
                    if period_date in combined:
                        combined[period_date]['income_statement'] = income
            
            # Agregar cash flows
            if cash_flows:
                for cf in cash_flows:
                    period_date = cf['date']
                    if period_date in combined:
                        combined[period_date]['cash_flow'] = cf
            
            # Convertir a FinancialStatementCreate
            statements = []
            for period_date, data in combined.items():
                statement = self._build_financial_statement(
                    ticker=ticker,
                    period_date=period_date,
                    balance_sheet=data.get('balance_sheet'),
                    income_statement=data.get('income_statement'),
                    cash_flow=data.get('cash_flow')
                )
                
                if statement:
                    statements.append(statement)
            
            logger.info(
                "financial_statements_fetched",
                ticker=ticker,
                count=len(statements),
                period=period
            )
            
            return statements
            
        except Exception as e:
            logger.error(
                "get_financial_statements_failed",
                ticker=ticker,
                error=str(e)
            )
            return None
    
    async def get_balance_sheets(
        self,
        ticker: str,
        period: str = "quarter",
        limit: int = 40
    ) -> Optional[List[Dict]]:
        """Obtener balance sheets"""
        endpoint = f"balance-sheet-statement/{ticker}"
        params = {"period": period, "limit": limit}
        
        result = await self._get(endpoint, params)
        return result if result else None
    
    async def get_income_statements(
        self,
        ticker: str,
        period: str = "quarter",
        limit: int = 40
    ) -> Optional[List[Dict]]:
        """Obtener income statements"""
        endpoint = f"income-statement/{ticker}"
        params = {"period": period, "limit": limit}
        
        result = await self._get(endpoint, params)
        return result if result else None
    
    async def get_cash_flows(
        self,
        ticker: str,
        period: str = "quarter",
        limit: int = 40
    ) -> Optional[List[Dict]]:
        """Obtener cash flow statements"""
        endpoint = f"cash-flow-statement/{ticker}"
        params = {"period": period, "limit": limit}
        
        result = await self._get(endpoint, params)
        return result if result else None
    
    def _build_financial_statement(
        self,
        ticker: str,
        period_date: str,
        balance_sheet: Optional[Dict],
        income_statement: Optional[Dict],
        cash_flow: Optional[Dict]
    ) -> Optional[FinancialStatementCreate]:
        """
        Construir FinancialStatementCreate desde raw data de FMP
        """
        try:
            # Parsear fecha
            parsed_date = datetime.strptime(period_date, "%Y-%m-%d").date()
            
            # Determinar period type (Q1, Q2, Q3, Q4, FY)
            period_type = self._determine_period_type(
                balance_sheet or income_statement or cash_flow
            )
            
            # Extract fiscal year
            fiscal_year = None
            if balance_sheet:
                fiscal_year = balance_sheet.get('calendarYear')
            elif income_statement:
                fiscal_year = income_statement.get('calendarYear')
            
            # Build financial statement
            statement = FinancialStatementCreate(
                ticker=ticker,
                period_date=parsed_date,
                period_type=period_type,
                fiscal_year=fiscal_year,
                
                # Balance Sheet
                total_assets=self._to_decimal(balance_sheet, 'totalAssets') if balance_sheet else None,
                total_liabilities=self._to_decimal(balance_sheet, 'totalLiabilities') if balance_sheet else None,
                stockholders_equity=self._to_decimal(balance_sheet, 'totalStockholdersEquity') if balance_sheet else None,
                cash_and_equivalents=self._to_decimal(balance_sheet, 'cashAndCashEquivalents') if balance_sheet else None,
                short_term_investments=self._to_decimal(balance_sheet, 'shortTermInvestments') if balance_sheet else None,
                total_debt=self._to_decimal(balance_sheet, 'totalDebt') if balance_sheet else None,
                total_current_assets=self._to_decimal(balance_sheet, 'totalCurrentAssets') if balance_sheet else None,
                total_current_liabilities=self._to_decimal(balance_sheet, 'totalCurrentLiabilities') if balance_sheet else None,
                
                # Income Statement
                revenue=self._to_decimal(income_statement, 'revenue') if income_statement else None,
                gross_profit=self._to_decimal(income_statement, 'grossProfit') if income_statement else None,
                operating_income=self._to_decimal(income_statement, 'operatingIncome') if income_statement else None,
                net_income=self._to_decimal(income_statement, 'netIncome') if income_statement else None,
                eps_basic=self._to_decimal(income_statement, 'eps') if income_statement else None,
                eps_diluted=self._to_decimal(income_statement, 'epsdiluted') if income_statement else None,
                
                # Cash Flow
                operating_cash_flow=self._to_decimal(cash_flow, 'operatingCashFlow') if cash_flow else None,
                investing_cash_flow=self._to_decimal(cash_flow, 'netCashUsedForInvestingActivites') if cash_flow else None,
                financing_cash_flow=self._to_decimal(cash_flow, 'netCashUsedProvidedByFinancingActivities') if cash_flow else None,
                free_cash_flow=self._to_decimal(cash_flow, 'freeCashFlow') if cash_flow else None,
                
                # Shares
                shares_outstanding=self._to_int(balance_sheet, 'commonStock') if balance_sheet else None,
                weighted_avg_shares_basic=self._to_int(income_statement, 'weightedAverageShsOut') if income_statement else None,
                weighted_avg_shares_diluted=self._to_int(income_statement, 'weightedAverageShsOutDil') if income_statement else None,
                
                source="fmp"
            )
            
            return statement
            
        except Exception as e:
            logger.error(
                "build_financial_statement_failed",
                ticker=ticker,
                period_date=period_date,
                error=str(e)
            )
            return None
    
    def _determine_period_type(self, statement: Optional[Dict]) -> FinancialPeriod:
        """Determinar el tipo de período (Q1, Q2, Q3, Q4, FY)"""
        if not statement:
            return FinancialPeriod.FY
        
        period = statement.get('period', '')
        
        if period == 'Q1':
            return FinancialPeriod.Q1
        elif period == 'Q2':
            return FinancialPeriod.Q2
        elif period == 'Q3':
            return FinancialPeriod.Q3
        elif period == 'Q4':
            return FinancialPeriod.Q4
        else:
            return FinancialPeriod.FY
    
    def _to_decimal(self, data: Optional[Dict], key: str) -> Optional[Decimal]:
        """Convert value to Decimal safely"""
        if not data:
            return None
        
        value = data.get(key)
        if value is None:
            return None
        
        try:
            return Decimal(str(value))
        except:
            return None
    
    def _to_int(self, data: Optional[Dict], key: str) -> Optional[int]:
        """Convert value to int safely"""
        if not data:
            return None
        
        value = data.get(key)
        if value is None:
            return None
        
        try:
            return int(value)
        except:
            return None

