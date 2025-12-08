"""
FMP Financials Service
Obtiene financial statements desde Financial Modeling Prep API (stable endpoints)

Endpoints usados:
- /stable/income-statement
- /stable/balance-sheet-statement  
- /stable/cash-flow-statement
"""

import httpx
from typing import Optional, List, Dict, Any
from datetime import datetime

from shared.utils.logger import get_logger
from shared.models.financials import (
    FinancialPeriod,
    IncomeStatement,
    BalanceSheet,
    CashFlow,
    FinancialData,
    FinancialRatios
)

logger = get_logger(__name__)


class FMPFinancialsService:
    """
    Servicio para obtener financial statements desde FMP API (stable)
    """
    
    BASE_URL = "https://financialmodelingprep.com/stable"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.timeout = 30.0
    
    async def _get(self, endpoint: str, params: Dict) -> Optional[List[Dict]]:
        """Hacer GET request a FMP API"""
        url = f"{self.BASE_URL}/{endpoint}"
        params['apikey'] = self.api_key
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # FMP retorna error como dict
                    if isinstance(data, dict) and "Error Message" in data:
                        logger.warning("fmp_error", endpoint=endpoint, error=data["Error Message"])
                        return None
                    
                    return data if isinstance(data, list) else None
                
                elif response.status_code == 429:
                    logger.warning("fmp_rate_limited", endpoint=endpoint)
                    return None
                
                else:
                    logger.error("fmp_error", endpoint=endpoint, status=response.status_code)
                    return None
                    
        except Exception as e:
            logger.error("fmp_exception", endpoint=endpoint, error=str(e))
            return None
    
    async def get_profile(self, symbol: str) -> Optional[Dict]:
        """Obtener company profile con industry y sector"""
        params = {"symbol": symbol.upper()}
        data = await self._get("profile", params)
        if data and len(data) > 0:
            return data[0]
            return None
    
    async def get_financials(
        self,
        symbol: str,
        period: str = "annual",  # "annual" o "quarter"
        limit: int = 20  # INCREASED: 20 períodos (5 años quarterly)
    ) -> Optional[FinancialData]:
        """
        Obtener datos financieros completos de un ticker
        
        Args:
            symbol: Ticker symbol (ej: AAPL)
            period: "annual" o "quarter"
            limit: Número de períodos (default 20)
        
        Returns:
            FinancialData con income, balance, cash flow, ratios, industry y sector
        """
        symbol = symbol.upper()
        
        # Obtener statements + profile en paralelo
        import asyncio
        
        income_task = self.get_income_statements(symbol, period, limit)
        balance_task = self.get_balance_sheets(symbol, period, limit)
        cashflow_task = self.get_cash_flows(symbol, period, limit)
        profile_task = self.get_profile(symbol)
        
        income_data, balance_data, cashflow_data, profile_data = await asyncio.gather(
            income_task, balance_task, cashflow_task, profile_task
        )
        
        # Parsear datos
        income_statements = self._parse_income_statements(income_data) if income_data else []
        balance_sheets = self._parse_balance_sheets(balance_data) if balance_data else []
        cash_flows = self._parse_cash_flows(cashflow_data) if cashflow_data else []
        
        if not income_statements and not balance_sheets and not cash_flows:
            logger.warning("no_financial_data", symbol=symbol)
            return None
        
        # Calcular ratios
        ratios = self._calculate_ratios(income_statements, balance_sheets, cash_flows)
        
        # Extraer industry y sector del profile
        industry = profile_data.get("industry") if profile_data else None
        sector = profile_data.get("sector") if profile_data else None
        
        return FinancialData(
            symbol=symbol,
            currency="USD",
            industry=industry,
            sector=sector,
            income_statements=income_statements,
            balance_sheets=balance_sheets,
            cash_flows=cash_flows,
            ratios=ratios,
            last_updated=datetime.utcnow().isoformat() + "Z",
            cached=False
        )
    
    async def get_income_statements(
        self,
        symbol: str,
        period: str = "annual",
        limit: int = 5
    ) -> Optional[List[Dict]]:
        """Obtener income statements"""
        params = {
            "symbol": symbol.upper(),
            "period": period,
            "limit": limit
        }
        return await self._get("income-statement", params)
    
    async def get_balance_sheets(
        self,
        symbol: str,
        period: str = "annual",
        limit: int = 5
    ) -> Optional[List[Dict]]:
        """Obtener balance sheets"""
        params = {
            "symbol": symbol.upper(),
            "period": period,
            "limit": limit
        }
        return await self._get("balance-sheet-statement", params)
    
    async def get_cash_flows(
        self,
        symbol: str,
        period: str = "annual",
        limit: int = 5
    ) -> Optional[List[Dict]]:
        """Obtener cash flow statements"""
        params = {
            "symbol": symbol.upper(),
            "period": period,
            "limit": limit
        }
        return await self._get("cash-flow-statement", params)
    
    def _parse_income_statements(self, data: List[Dict]) -> List[IncomeStatement]:
        """Parsear income statements de FMP"""
        statements = []
        
        for item in data:
            try:
                period = FinancialPeriod(
                    date=item.get("date", ""),
                    symbol=item.get("symbol", ""),
                    fiscal_year=str(item.get("fiscalYear", "")),
                    period=item.get("period", "FY"),
                    filing_date=item.get("filingDate"),
                    currency=item.get("reportedCurrency", "USD")
                )
                
                revenue = self._safe_float(item.get("revenue"))
                gross_profit = self._safe_float(item.get("grossProfit"))
                operating_income = self._safe_float(item.get("operatingIncome"))
                net_income = self._safe_float(item.get("netIncome"))
                
                # Net Interest Income (para bancos)
                interest_income = self._safe_float(item.get("interestIncome"))
                interest_expense = self._safe_float(item.get("interestExpense"))
                net_interest_income = self._safe_float(item.get("netInterestIncome"))
                
                # Si FMP no lo provee, calcularlo
                if net_interest_income is None and interest_income and interest_expense:
                    net_interest_income = interest_income - interest_expense
                
                statement = IncomeStatement(
                    period=period,
                    revenue=revenue,
                    cost_of_revenue=self._safe_float(item.get("costOfRevenue")),
                    gross_profit=gross_profit,
                    research_development=self._safe_float(item.get("researchAndDevelopmentExpenses")),
                    selling_general_admin=self._safe_float(item.get("sellingGeneralAndAdministrativeExpenses")),
                    operating_expenses=self._safe_float(item.get("operatingExpenses")),
                    operating_income=operating_income,
                    interest_expense=interest_expense,
                    interest_income=interest_income,
                    net_interest_income=net_interest_income,
                    other_income_expense=self._safe_float(item.get("totalOtherIncomeExpensesNet")),
                    income_before_tax=self._safe_float(item.get("incomeBeforeTax")),
                    income_tax=self._safe_float(item.get("incomeTaxExpense")),
                    net_income=net_income,
                    eps=self._safe_float(item.get("eps")),
                    eps_diluted=self._safe_float(item.get("epsDiluted")),
                    shares_outstanding=self._safe_float(item.get("weightedAverageShsOut")),
                    shares_diluted=self._safe_float(item.get("weightedAverageShsOutDil")),
                    ebitda=self._safe_float(item.get("ebitda")),
                    ebit=self._safe_float(item.get("ebit")),
                    depreciation=self._safe_float(item.get("depreciationAndAmortization"))
                )
                
                statements.append(statement)
                
            except Exception as e:
                logger.warning("parse_income_error", error=str(e))
                continue
        
        return statements
    
    def _parse_balance_sheets(self, data: List[Dict]) -> List[BalanceSheet]:
        """Parsear balance sheets de FMP"""
        statements = []
        
        for item in data:
            try:
                period = FinancialPeriod(
                    date=item.get("date", ""),
                    symbol=item.get("symbol", ""),
                    fiscal_year=str(item.get("fiscalYear", "")),
                    period=item.get("period", "FY"),
                    filing_date=item.get("filingDate"),
                    currency=item.get("reportedCurrency", "USD")
                )
                
                statement = BalanceSheet(
                    period=period,
                    # Assets
                    total_assets=self._safe_float(item.get("totalAssets")),
                    current_assets=self._safe_float(item.get("totalCurrentAssets")),
                    cash_and_equivalents=self._safe_float(item.get("cashAndCashEquivalents")),
                    short_term_investments=self._safe_float(item.get("shortTermInvestments")),
                    cash_and_short_term=self._safe_float(item.get("cashAndShortTermInvestments")),
                    receivables=self._safe_float(item.get("netReceivables")),
                    inventory=self._safe_float(item.get("inventory")),
                    other_current_assets=self._safe_float(item.get("otherCurrentAssets")),
                    property_plant_equipment=self._safe_float(item.get("propertyPlantEquipmentNet")),
                    goodwill=self._safe_float(item.get("goodwill")),
                    intangible_assets=self._safe_float(item.get("intangibleAssets")),
                    long_term_investments=self._safe_float(item.get("longTermInvestments")),
                    other_noncurrent_assets=self._safe_float(item.get("otherNonCurrentAssets")),
                    noncurrent_assets=self._safe_float(item.get("totalNonCurrentAssets")),
                    # Liabilities
                    total_liabilities=self._safe_float(item.get("totalLiabilities")),
                    current_liabilities=self._safe_float(item.get("totalCurrentLiabilities")),
                    accounts_payable=self._safe_float(item.get("accountPayables")),
                    short_term_debt=self._safe_float(item.get("shortTermDebt")),
                    deferred_revenue=self._safe_float(item.get("deferredRevenue")),
                    other_current_liabilities=self._safe_float(item.get("otherCurrentLiabilities")),
                    long_term_debt=self._safe_float(item.get("longTermDebt")),
                    other_noncurrent_liabilities=self._safe_float(item.get("otherNonCurrentLiabilities")),
                    noncurrent_liabilities=self._safe_float(item.get("totalNonCurrentLiabilities")),
                    # Equity
                    total_equity=self._safe_float(item.get("totalStockholdersEquity")),
                    common_stock=self._safe_float(item.get("commonStock")),
                    retained_earnings=self._safe_float(item.get("retainedEarnings")),
                    treasury_stock=self._safe_float(item.get("treasuryStock")),
                    accumulated_other_income=self._safe_float(item.get("accumulatedOtherComprehensiveIncomeLoss")),
                    # Metrics
                    total_debt=self._safe_float(item.get("totalDebt")),
                    net_debt=self._safe_float(item.get("netDebt")),
                    total_investments=self._safe_float(item.get("totalInvestments"))
                )
                
                statements.append(statement)
                
            except Exception as e:
                logger.warning("parse_balance_error", error=str(e))
                continue
        
        return statements
    
    def _parse_cash_flows(self, data: List[Dict]) -> List[CashFlow]:
        """Parsear cash flow statements de FMP"""
        statements = []
        
        for item in data:
            try:
                period = FinancialPeriod(
                    date=item.get("date", ""),
                    symbol=item.get("symbol", ""),
                    fiscal_year=str(item.get("fiscalYear", "")),
                    period=item.get("period", "FY"),
                    filing_date=item.get("filingDate"),
                    currency=item.get("reportedCurrency", "USD")
                )
                
                statement = CashFlow(
                    period=period,
                    # Operating
                    net_income=self._safe_float(item.get("netIncome")),
                    depreciation=self._safe_float(item.get("depreciationAndAmortization")),
                    stock_compensation=self._safe_float(item.get("stockBasedCompensation")),
                    change_working_capital=self._safe_float(item.get("changeInWorkingCapital")),
                    change_receivables=self._safe_float(item.get("accountsReceivables")),
                    change_inventory=self._safe_float(item.get("inventory")),
                    change_payables=self._safe_float(item.get("accountsPayables")),
                    other_operating=self._safe_float(item.get("otherNonCashItems")),
                    operating_cash_flow=self._safe_float(item.get("operatingCashFlow")),
                    # Investing
                    capex=self._safe_float(item.get("capitalExpenditure")),
                    acquisitions=self._safe_float(item.get("acquisitionsNet")),
                    purchases_investments=self._safe_float(item.get("purchasesOfInvestments")),
                    sales_investments=self._safe_float(item.get("salesMaturitiesOfInvestments")),
                    other_investing=self._safe_float(item.get("otherInvestingActivities")),
                    investing_cash_flow=self._safe_float(item.get("netCashProvidedByInvestingActivities")),
                    # Financing
                    debt_issued=self._safe_float(item.get("netDebtIssuance")),
                    debt_repaid=self._safe_float(item.get("longTermNetDebtIssuance")),
                    stock_issued=self._safe_float(item.get("commonStockIssuance")),
                    stock_repurchased=self._safe_float(item.get("commonStockRepurchased")),
                    dividends_paid=self._safe_float(item.get("commonDividendsPaid")),
                    other_financing=self._safe_float(item.get("otherFinancingActivities")),
                    financing_cash_flow=self._safe_float(item.get("netCashProvidedByFinancingActivities")),
                    # Summary
                    net_change_cash=self._safe_float(item.get("netChangeInCash")),
                    cash_beginning=self._safe_float(item.get("cashAtBeginningOfPeriod")),
                    cash_ending=self._safe_float(item.get("cashAtEndOfPeriod")),
                    free_cash_flow=self._safe_float(item.get("freeCashFlow"))
                )
                
                statements.append(statement)
                
            except Exception as e:
                logger.warning("parse_cashflow_error", error=str(e))
                continue
        
        return statements
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Convertir a float de forma segura"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _calculate_ratios(
        self,
        income_statements: List[IncomeStatement],
        balance_sheets: List[BalanceSheet],
        cash_flows: List[CashFlow]
    ) -> List[FinancialRatios]:
        """
        Calcular ratios financieros por período.
        Combina datos de income, balance y cash flow para cada fecha.
        """
        ratios = []
        
        # Crear mapas por fecha
        income_map = {i.period.date: i for i in income_statements}
        balance_map = {b.period.date: b for b in balance_sheets}
        cashflow_map = {c.period.date: c for c in cash_flows}
        
        # Obtener todas las fechas únicas
        all_dates = set(income_map.keys()) | set(balance_map.keys()) | set(cashflow_map.keys())
        
        for period_date in sorted(all_dates, reverse=True):
            income = income_map.get(period_date)
            balance = balance_map.get(period_date)
            cashflow = cashflow_map.get(period_date)
            
            ratio = FinancialRatios(period_date=period_date)
            
            # Liquidity Ratios (from balance sheet)
            if balance:
                if balance.current_liabilities and balance.current_liabilities != 0:
                    if balance.current_assets:
                        ratio.current_ratio = round(balance.current_assets / balance.current_liabilities, 2)
                    
                    # Quick ratio: (current_assets - inventory) / current_liabilities
                    if balance.current_assets:
                        inventory = balance.inventory or 0
                        ratio.quick_ratio = round((balance.current_assets - inventory) / balance.current_liabilities, 2)
                
                # Working Capital
                if balance.current_assets and balance.current_liabilities:
                    ratio.working_capital = balance.current_assets - balance.current_liabilities
                
                # Solvency Ratios
                if balance.total_equity and balance.total_equity != 0:
                    if balance.total_debt:
                        ratio.debt_to_equity = round(balance.total_debt / balance.total_equity, 2)
                
                if balance.total_assets and balance.total_assets != 0:
                    if balance.total_debt:
                        ratio.debt_to_assets = round(balance.total_debt / balance.total_assets, 2)
            
            # Profitability Ratios (from income statement)
            if income and income.revenue and income.revenue != 0:
                if income.gross_profit:
                    ratio.gross_margin = round((income.gross_profit / income.revenue) * 100, 2)
                
                if income.operating_income:
                    ratio.operating_margin = round((income.operating_income / income.revenue) * 100, 2)
                
                if income.net_income:
                    ratio.net_margin = round((income.net_income / income.revenue) * 100, 2)
            
            # ROE (Net Income / Total Equity)
            if income and balance:
                if income.net_income and balance.total_equity and balance.total_equity != 0:
                    ratio.roe = round((income.net_income / balance.total_equity) * 100, 2)
                
                if income.net_income and balance.total_assets and balance.total_assets != 0:
                    ratio.roa = round((income.net_income / balance.total_assets) * 100, 2)
                
                if income.revenue and balance.total_assets and balance.total_assets != 0:
                    ratio.asset_turnover = round(income.revenue / balance.total_assets, 2)
            
            # FCF Margin
            if cashflow and income:
                if cashflow.free_cash_flow and income.revenue and income.revenue != 0:
                    ratio.fcf_margin = round((cashflow.free_cash_flow / income.revenue) * 100, 2)
            
            ratios.append(ratio)
        
        return ratios

