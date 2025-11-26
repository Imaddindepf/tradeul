"""
Financial Models - Shared
Modelos Pydantic para datos financieros (Income, Balance, Cash Flow)
Usados por API Gateway y otros servicios
"""

from typing import Optional, List
from pydantic import BaseModel
from datetime import date


class FinancialPeriod(BaseModel):
    """Información del período financiero"""
    date: str
    symbol: str
    fiscal_year: str
    period: str  # Q1, Q2, Q3, Q4, FY
    filing_date: Optional[str] = None
    currency: str = "USD"


class IncomeStatement(BaseModel):
    """Income Statement / Estado de Resultados"""
    period: FinancialPeriod
    # Revenue
    revenue: Optional[float] = None
    cost_of_revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    # Operating Expenses
    research_development: Optional[float] = None
    selling_general_admin: Optional[float] = None
    operating_expenses: Optional[float] = None
    operating_income: Optional[float] = None
    # Interest (Banks)
    interest_expense: Optional[float] = None
    interest_income: Optional[float] = None
    net_interest_income: Optional[float] = None  # Banks: interest_income - interest_expense
    # Other
    other_income_expense: Optional[float] = None
    income_before_tax: Optional[float] = None
    income_tax: Optional[float] = None
    net_income: Optional[float] = None
    # Per Share
    eps: Optional[float] = None
    eps_diluted: Optional[float] = None
    shares_outstanding: Optional[float] = None
    shares_diluted: Optional[float] = None
    # Metrics
    ebitda: Optional[float] = None
    ebit: Optional[float] = None
    depreciation: Optional[float] = None


class BalanceSheet(BaseModel):
    """Balance Sheet / Balance General"""
    period: FinancialPeriod
    # Assets
    total_assets: Optional[float] = None
    current_assets: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    short_term_investments: Optional[float] = None
    cash_and_short_term: Optional[float] = None
    receivables: Optional[float] = None
    inventory: Optional[float] = None
    other_current_assets: Optional[float] = None
    # Non-current Assets
    property_plant_equipment: Optional[float] = None
    goodwill: Optional[float] = None
    intangible_assets: Optional[float] = None
    long_term_investments: Optional[float] = None
    other_noncurrent_assets: Optional[float] = None
    noncurrent_assets: Optional[float] = None
    # Liabilities
    total_liabilities: Optional[float] = None
    current_liabilities: Optional[float] = None
    accounts_payable: Optional[float] = None
    short_term_debt: Optional[float] = None
    deferred_revenue: Optional[float] = None
    other_current_liabilities: Optional[float] = None
    long_term_debt: Optional[float] = None
    other_noncurrent_liabilities: Optional[float] = None
    noncurrent_liabilities: Optional[float] = None
    # Equity
    total_equity: Optional[float] = None
    common_stock: Optional[float] = None
    retained_earnings: Optional[float] = None
    treasury_stock: Optional[float] = None
    accumulated_other_income: Optional[float] = None
    # Metrics
    total_debt: Optional[float] = None
    net_debt: Optional[float] = None
    total_investments: Optional[float] = None


class CashFlow(BaseModel):
    """Cash Flow Statement / Estado de Flujo de Efectivo"""
    period: FinancialPeriod
    # Operating
    net_income: Optional[float] = None
    depreciation: Optional[float] = None
    stock_compensation: Optional[float] = None
    change_working_capital: Optional[float] = None
    change_receivables: Optional[float] = None
    change_inventory: Optional[float] = None
    change_payables: Optional[float] = None
    other_operating: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    # Investing
    capex: Optional[float] = None
    acquisitions: Optional[float] = None
    purchases_investments: Optional[float] = None
    sales_investments: Optional[float] = None
    other_investing: Optional[float] = None
    investing_cash_flow: Optional[float] = None
    # Financing
    debt_issued: Optional[float] = None
    debt_repaid: Optional[float] = None
    stock_issued: Optional[float] = None
    stock_repurchased: Optional[float] = None
    dividends_paid: Optional[float] = None
    other_financing: Optional[float] = None
    financing_cash_flow: Optional[float] = None
    # Summary
    net_change_cash: Optional[float] = None
    cash_beginning: Optional[float] = None
    cash_ending: Optional[float] = None
    free_cash_flow: Optional[float] = None


class FinancialData(BaseModel):
    """Datos financieros completos de un ticker"""
    symbol: str
    currency: str = "USD"
    income_statements: List[IncomeStatement] = []
    balance_sheets: List[BalanceSheet] = []
    cash_flows: List[CashFlow] = []
    last_updated: str
    cached: bool = False
    cache_age_seconds: Optional[int] = None

