"""
Financial Models - Shared
Modelos Pydantic para datos financieros (Income, Balance, Cash Flow)
Usados por API Gateway y otros servicios

Incluye campos específicos de industria:
- Seguros: premiums_earned, policy_benefits, investment_income
- Bancos: net_interest_income, provision_loan_losses, deposits
- Healthcare: medical_costs, medical_cost_ratio
"""

from typing import Optional, List, Any
from pydantic import BaseModel
from datetime import date


class FinancialPeriod(BaseModel):
    """Información del período financiero"""
    date: str
    symbol: Optional[str] = None
    fiscal_year: str
    period: str  # Q1, Q2, Q3, Q4, FY
    filing_date: Optional[str] = None
    currency: str = "USD"


class IncomeStatement(BaseModel):
    """Income Statement / Estado de Resultados"""
    period: FinancialPeriod
    
    # =========================================================================
    # CAMPOS UNIVERSALES
    # =========================================================================
    # Revenue
    revenue: Optional[float] = None
    cost_of_revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    # Operating Expenses
    research_development: Optional[float] = None
    selling_general_admin: Optional[float] = None
    operating_expenses: Optional[float] = None
    operating_income: Optional[float] = None
    # Interest
    interest_expense: Optional[float] = None
    interest_income: Optional[float] = None
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
    
    # =========================================================================
    # CAMPOS ESPECÍFICOS DE INDUSTRIA
    # =========================================================================
    
    # SEGUROS (Insurance)
    premiums_earned: Optional[float] = None  # Primas ganadas
    policy_benefits: Optional[float] = None  # Beneficios pagados a asegurados
    investment_income: Optional[float] = None  # Ingresos de inversiones
    
    # BANCOS (Banks/Financial Services)
    net_interest_income: Optional[float] = None  # interest_income - interest_expense
    provision_loan_losses: Optional[float] = None  # Provisión para pérdidas
    non_interest_income: Optional[float] = None  # Comisiones, trading, etc.
    non_interest_expense: Optional[float] = None  # Salarios, operaciones, etc.
    
    # HEALTHCARE (UNH, CVS, CI)
    medical_costs: Optional[float] = None  # Costos médicos (claims)
    medical_cost_ratio: Optional[float] = None  # MCR = medical_costs / premiums
    
    # OTROS
    minority_interest: Optional[float] = None  # Participación no controladora
    
    class Config:
        extra = 'allow'  # Permitir campos adicionales de XBRL


class BalanceSheet(BaseModel):
    """Balance Sheet / Balance General"""
    period: FinancialPeriod
    
    # =========================================================================
    # CAMPOS UNIVERSALES
    # =========================================================================
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
    
    # =========================================================================
    # CAMPOS ESPECÍFICOS DE INDUSTRIA
    # =========================================================================
    
    # BANCOS (Banks)
    loans_net: Optional[float] = None  # Préstamos netos
    deposits: Optional[float] = None  # Depósitos de clientes
    allowance_loan_losses: Optional[float] = None  # Reserva para pérdidas
    
    # SEGUROS (Insurance)
    policy_liabilities: Optional[float] = None  # Pasivos de pólizas
    unearned_premiums: Optional[float] = None  # Primas no devengadas
    
    # REITS
    real_estate_assets: Optional[float] = None
    
    class Config:
        extra = 'allow'


class CashFlow(BaseModel):
    """Cash Flow Statement / Estado de Flujo de Efectivo"""
    period: FinancialPeriod
    
    # =========================================================================
    # CAMPOS UNIVERSALES
    # =========================================================================
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
    
    class Config:
        extra = 'allow'


class FinancialRatios(BaseModel):
    """Ratios financieros calculados"""
    period_date: str
    # Liquidity
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    # Solvency
    debt_to_equity: Optional[float] = None
    debt_to_assets: Optional[float] = None
    # Profitability
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    roe: Optional[float] = None  # Return on Equity
    roa: Optional[float] = None  # Return on Assets
    # Efficiency
    asset_turnover: Optional[float] = None
    # Cash
    working_capital: Optional[float] = None
    fcf_margin: Optional[float] = None  # Free Cash Flow Margin
    
    # Industry-specific
    net_interest_margin: Optional[float] = None  # Banks
    medical_cost_ratio: Optional[float] = None  # Healthcare
    combined_ratio: Optional[float] = None  # Insurance


class FinancialData(BaseModel):
    """Datos financieros completos de un ticker"""
    symbol: str
    currency: str = "USD"
    industry: Optional[str] = None  # From FMP profile (e.g., "Consumer Electronics")
    sector: Optional[str] = None    # From FMP profile (e.g., "Technology")
    source: Optional[str] = None    # "sec-api-xbrl" or "fmp"
    income_statements: List[Any] = []  # List[IncomeStatement] pero más flexible
    balance_sheets: List[Any] = []
    cash_flows: List[Any] = []
    ratios: List[FinancialRatios] = []
    last_updated: str
    cached: bool = False
    cache_age_seconds: Optional[int] = None
