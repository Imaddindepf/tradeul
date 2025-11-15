"""
Polygon Financials Service
Obtiene financial statements desde Polygon API v1 (endpoints específicos)
"""

import sys
sys.path.append('/app')

import httpx
from typing import Optional, List, Dict
from datetime import datetime
from decimal import Decimal

from shared.utils.logger import get_logger
from models.financial_models import FinancialStatementCreate, FinancialPeriod

logger = get_logger(__name__)


class PolygonFinancialsService:
    """
    Servicio para obtener financial statements desde Polygon API v1
    
    Endpoints:
    - /v1/balance-sheets
    - /v1/income-statements  
    - /v1/cash-flow-statements
    """
    
    BASE_URL = "https://api.polygon.io/stocks/financials/v1"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.timeout = 30.0
    
    async def get_financial_statements(
        self,
        ticker: str,
        timeframe: str = "quarterly",
        limit: int = 40
    ) -> Optional[List[FinancialStatementCreate]]:
        """
        Obtener financial statements completos combinando 3 endpoints
        """
        try:
            # Fetch los 3 tipos de statements
            balance_sheets = await self._fetch_endpoint(
                "balance-sheets",
                ticker,
                timeframe,
                limit
            )
            income_statements = await self._fetch_endpoint(
                "income-statements",
                ticker,
                timeframe,
                limit
            )
            cash_flows = await self._fetch_endpoint(
                "cash-flow-statements",
                ticker,
                timeframe,
                limit
            )
            
            if not balance_sheets and not income_statements:
                logger.warning("no_polygon_data", ticker=ticker)
                return None
            
            # Combinar por period_end
            combined = {}
            
            # Procesar balance sheets
            for bs in (balance_sheets or []):
                period_end = bs.get('period_end')
                if period_end:
                    combined[period_end] = {
                        'balance_sheet': bs,
                        'income_statement': None,
                        'cash_flow': None
                    }
            
            # Agregar income statements
            for income in (income_statements or []):
                period_end = income.get('period_end')
                if period_end:
                    if period_end not in combined:
                        combined[period_end] = {
                            'balance_sheet': None,
                            'income_statement': income,
                            'cash_flow': None
                        }
                    else:
                        combined[period_end]['income_statement'] = income
            
            # Agregar cash flows
            for cf in (cash_flows or []):
                period_end = cf.get('period_end')
                if period_end and period_end in combined:
                    combined[period_end]['cash_flow'] = cf
            
            # Convertir a FinancialStatementCreate
            statements = []
            for period_end in sorted(combined.keys(), reverse=True):
                data = combined[period_end]
                statement = self._build_financial_statement(ticker, period_end, data)
                if statement:
                    statements.append(statement)
            
            logger.info(
                "polygon_financials_success",
                ticker=ticker,
                count=len(statements)
            )
            
            return statements if statements else None
            
        except Exception as e:
            logger.error("get_polygon_financials_failed", ticker=ticker, error=str(e))
            return None
    
    async def _fetch_endpoint(
        self,
        endpoint: str,
        ticker: str,
        timeframe: str,
        limit: int
    ) -> Optional[List[Dict]]:
        """Fetch desde un endpoint específico de Polygon"""
        url = f"{self.BASE_URL}/{endpoint}"
        params = {
            'tickers': ticker,
            'timeframe': timeframe,
            'limit': limit,
            'sort': 'period_end.desc',  # Más recientes primero
            'apiKey': self.api_key
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    results = data.get('results', [])
                    return results if results else None
                
                logger.warning(
                    "polygon_endpoint_error",
                    endpoint=endpoint,
                    ticker=ticker,
                    status=response.status_code
                )
                return None
                
        except Exception as e:
            logger.error(
                "polygon_fetch_failed",
                endpoint=endpoint,
                ticker=ticker,
                error=str(e)
            )
            return None
    
    def _build_financial_statement(
        self,
        ticker: str,
        period_end: str,
        data: Dict
    ) -> Optional[FinancialStatementCreate]:
        """
        Construir FinancialStatementCreate desde datos de Polygon v1
        
        Estructura PLANA - campos directos sin nesting
        """
        try:
            parsed_date = datetime.strptime(period_end, "%Y-%m-%d").date()
            
            bs = data.get('balance_sheet') or {}
            income = data.get('income_statement') or {}
            cf = data.get('cash_flow') or {}
            
            # Fiscal info (puede venir de cualquiera)
            fiscal_year = bs.get('fiscal_year') or income.get('fiscal_year')
            fiscal_quarter = bs.get('fiscal_quarter') or income.get('fiscal_quarter')
            period_type = self._map_fiscal_quarter(fiscal_quarter)
            
            # Calcular total debt
            debt_current = bs.get('debt_current') or 0
            long_term_debt = bs.get('long_term_debt_and_capital_lease_obligations') or 0
            total_debt = (debt_current + long_term_debt) if (debt_current or long_term_debt) else None
            
            # Calcular FCF
            operating_cf = cf.get('net_cash_from_operating_activities')
            capex = cf.get('purchase_of_property_plant_and_equipment')
            free_cash_flow = None
            if operating_cf is not None:
                capex_value = abs(capex) if capex else 0
                free_cash_flow = operating_cf - capex_value
            
            statement = FinancialStatementCreate(
                ticker=ticker,
                period_date=parsed_date,
                period_type=period_type,
                fiscal_year=fiscal_year,
                
                # Balance Sheet
                total_assets=self._to_decimal(bs.get('total_assets')),
                total_liabilities=self._to_decimal(bs.get('total_liabilities')),
                stockholders_equity=self._to_decimal(bs.get('total_equity_attributable_to_parent')),
                cash_and_equivalents=self._to_decimal(bs.get('cash_and_equivalents')),
                short_term_investments=self._to_decimal(bs.get('short_term_investments')),
                total_debt=self._to_decimal(total_debt),
                total_current_assets=self._to_decimal(bs.get('total_current_assets')),
                total_current_liabilities=self._to_decimal(bs.get('total_current_liabilities')),
                
                # Income Statement
                revenue=self._to_decimal(income.get('revenue')),
                gross_profit=self._to_decimal(income.get('gross_profit')),
                operating_income=self._to_decimal(income.get('operating_income')),
                net_income=self._to_decimal(income.get('net_income_loss_attributable_common_shareholders')),
                eps_basic=self._to_decimal(income.get('basic_earnings_per_share')),
                eps_diluted=self._to_decimal(income.get('diluted_earnings_per_share')),
                
                # Cash Flow
                operating_cash_flow=self._to_decimal(cf.get('net_cash_from_operating_activities')),
                investing_cash_flow=self._to_decimal(cf.get('net_cash_from_investing_activities')),
                financing_cash_flow=self._to_decimal(cf.get('net_cash_from_financing_activities')),
                free_cash_flow=self._to_decimal(free_cash_flow),
                
                # Shares (CRÍTICO para dilution tracking)
                shares_outstanding=None,  # No está en balance sheets
                weighted_avg_shares_basic=self._to_int(income.get('basic_shares_outstanding')),
                weighted_avg_shares_diluted=self._to_int(income.get('diluted_shares_outstanding')),
                
                source="polygon"
            )
            
            return statement
            
        except Exception as e:
            logger.error(
                "build_polygon_statement_failed",
                ticker=ticker,
                period=period_end,
                error=str(e)
            )
            return None
    
    def _map_fiscal_quarter(self, fiscal_quarter: Optional[int]) -> FinancialPeriod:
        """Mapear fiscal quarter de Polygon a FinancialPeriod"""
        if not fiscal_quarter:
            return FinancialPeriod.FY
        
        quarter_map = {
            1: FinancialPeriod.Q1,
            2: FinancialPeriod.Q2,
            3: FinancialPeriod.Q3,
            4: FinancialPeriod.Q4,
        }
        
        return quarter_map.get(fiscal_quarter, FinancialPeriod.FY)
    
    def _to_decimal(self, value) -> Optional[Decimal]:
        """Convert value to Decimal safely"""
        if value is None:
            return None
        
        try:
            return Decimal(str(value))
        except:
            return None
    
    def _to_int(self, value) -> Optional[int]:
        """Convert value to int safely"""
        if value is None:
            return None
        
        try:
            return int(value)
        except:
            return None
