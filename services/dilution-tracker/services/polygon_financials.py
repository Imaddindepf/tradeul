"""
Polygon Financials Service
Obtiene financial statements desde Polygon API v1 (endpoints específicos)

NOTA: Usa http_clients.polygon con connection pooling.
"""

import sys
sys.path.append('/app')

from typing import Optional, List, Dict
from datetime import datetime
from decimal import Decimal

from shared.utils.logger import get_logger
from models.financial_models import FinancialStatementCreate, FinancialPeriod
from http_clients import http_clients

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
        """Fetch desde un endpoint específico de Polygon usando cliente compartido"""
        try:
            # Usar cliente Polygon con connection pooling
            # El endpoint de financials es diferente al base_url del cliente
            data = await http_clients.polygon.get_financials(ticker, limit=limit)
            
            if data:
                results = data.get('results', [])
                return results if results else None
            
            logger.warning(
                "polygon_endpoint_error",
                endpoint=endpoint,
                ticker=ticker
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
                
                # Balance Sheet - Assets (COMPLETO)
                total_assets=self._to_decimal(bs.get('total_assets')),
                total_current_assets=self._to_decimal(bs.get('total_current_assets')),
                cash_and_equivalents=self._to_decimal(bs.get('cash_and_equivalents')),
                short_term_investments=self._to_decimal(bs.get('short_term_investments')),
                receivables=self._to_decimal(bs.get('receivables')),
                inventories=self._to_decimal(bs.get('inventories')),
                other_current_assets=self._to_decimal(bs.get('other_current_assets')),
                property_plant_equipment_net=self._to_decimal(bs.get('property_plant_equipment_net')),
                goodwill=self._to_decimal(bs.get('goodwill')),
                intangible_assets_net=self._to_decimal(bs.get('intangible_assets_net')),
                other_noncurrent_assets=self._to_decimal(bs.get('other_assets')),
                
                # Balance Sheet - Liabilities (COMPLETO)
                total_liabilities=self._to_decimal(bs.get('total_liabilities')),
                total_current_liabilities=self._to_decimal(bs.get('total_current_liabilities')),
                accounts_payable=self._to_decimal(bs.get('accounts_payable')),
                debt_current=self._to_decimal(bs.get('debt_current')),
                accrued_liabilities=self._to_decimal(bs.get('accrued_and_other_current_liabilities')),
                deferred_revenue_current=self._to_decimal(bs.get('deferred_revenue_current')),
                long_term_debt=self._to_decimal(bs.get('long_term_debt_and_capital_lease_obligations')),
                other_noncurrent_liabilities=self._to_decimal(bs.get('other_noncurrent_liabilities')),
                total_debt=self._to_decimal(total_debt),
                
                # Balance Sheet - Equity (COMPLETO)
                stockholders_equity=self._to_decimal(bs.get('total_equity_attributable_to_parent')),
                common_stock=self._to_decimal(bs.get('common_stock')),
                additional_paid_in_capital=self._to_decimal(bs.get('additional_paid_in_capital')),
                treasury_stock=self._to_decimal(bs.get('treasury_stock')),
                retained_earnings=self._to_decimal(bs.get('retained_earnings_deficit')),
                accumulated_other_comprehensive_income=self._to_decimal(bs.get('accumulated_other_comprehensive_income')),
                
                # Income Statement (COMPLETO)
                revenue=self._to_decimal(income.get('revenue')),
                cost_of_revenue=self._to_decimal(income.get('cost_of_revenue')),
                gross_profit=self._to_decimal(income.get('gross_profit')),
                research_development=self._to_decimal(income.get('research_development')),
                selling_general_administrative=self._to_decimal(income.get('selling_general_administrative')),
                other_operating_expenses=self._to_decimal(income.get('other_operating_expenses')),
                total_operating_expenses=self._to_decimal(income.get('total_operating_expenses')),
                operating_income=self._to_decimal(income.get('operating_income')),
                interest_expense=self._to_decimal(income.get('interest_expense')),
                interest_income=self._to_decimal(income.get('interest_income')),
                other_income_expense=self._to_decimal(income.get('other_income_expense')),
                income_before_taxes=self._to_decimal(income.get('income_before_income_taxes')),
                income_taxes=self._to_decimal(income.get('income_taxes')),
                net_income=self._to_decimal(income.get('net_income_loss_attributable_common_shareholders')),
                eps_basic=self._to_decimal(income.get('basic_earnings_per_share')),
                eps_diluted=self._to_decimal(income.get('diluted_earnings_per_share')),
                ebitda=self._to_decimal(income.get('ebitda')),
                
                # Cash Flow Statement (COMPLETO)
                operating_cash_flow=self._to_decimal(cf.get('net_cash_from_operating_activities')),
                depreciation_amortization=self._to_decimal(cf.get('depreciation_depletion_and_amortization')),
                stock_based_compensation=None,  # No disponible directo en Polygon v1
                change_in_working_capital=self._to_decimal(cf.get('change_in_other_operating_assets_and_liabilities_net')),
                other_operating_activities=self._to_decimal(cf.get('other_operating_activities')),
                investing_cash_flow=self._to_decimal(cf.get('net_cash_from_investing_activities')),
                capital_expenditures=self._to_decimal(cf.get('purchase_of_property_plant_and_equipment')),
                acquisitions=None,  # No disponible directo
                other_investing_activities=self._to_decimal(cf.get('other_investing_activities')),
                financing_cash_flow=self._to_decimal(cf.get('net_cash_from_financing_activities')),
                debt_issuance_repayment=self._to_decimal(cf.get('long_term_debt_issuances_repayments')),
                dividends_paid=self._to_decimal(cf.get('dividends')),
                stock_repurchased=None,  # No disponible directo
                other_financing_activities=self._to_decimal(cf.get('other_financing_activities')),
                change_in_cash=self._to_decimal(cf.get('change_in_cash_and_equivalents')),
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
