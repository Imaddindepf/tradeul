"""
Financial Statement Models
"""

from datetime import date, datetime
from typing import Optional
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field, validator


class FinancialPeriod(str, Enum):
    """Financial reporting period"""
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"
    FY = "FY"  # Full Year


class FinancialStatementCreate(BaseModel):
    """Model for creating a new financial statement"""
    ticker: str = Field(..., max_length=10)
    period_date: date
    period_type: FinancialPeriod
    fiscal_year: Optional[int] = None
    
    # Balance Sheet - Assets
    total_assets: Optional[Decimal] = None
    total_current_assets: Optional[Decimal] = None
    cash_and_equivalents: Optional[Decimal] = None
    short_term_investments: Optional[Decimal] = None
    receivables: Optional[Decimal] = None
    inventories: Optional[Decimal] = None
    other_current_assets: Optional[Decimal] = None
    property_plant_equipment_net: Optional[Decimal] = None
    goodwill: Optional[Decimal] = None
    intangible_assets_net: Optional[Decimal] = None
    other_noncurrent_assets: Optional[Decimal] = None
    
    # Balance Sheet - Liabilities
    total_liabilities: Optional[Decimal] = None
    total_current_liabilities: Optional[Decimal] = None
    accounts_payable: Optional[Decimal] = None
    debt_current: Optional[Decimal] = None
    accrued_liabilities: Optional[Decimal] = None
    deferred_revenue_current: Optional[Decimal] = None
    long_term_debt: Optional[Decimal] = None
    other_noncurrent_liabilities: Optional[Decimal] = None
    total_debt: Optional[Decimal] = None  # Calculado: current + long-term
    
    # Balance Sheet - Equity
    stockholders_equity: Optional[Decimal] = None
    common_stock: Optional[Decimal] = None
    additional_paid_in_capital: Optional[Decimal] = None
    treasury_stock: Optional[Decimal] = None
    retained_earnings: Optional[Decimal] = None
    accumulated_other_comprehensive_income: Optional[Decimal] = None
    
    # Income Statement
    revenue: Optional[Decimal] = None
    cost_of_revenue: Optional[Decimal] = None
    gross_profit: Optional[Decimal] = None
    research_development: Optional[Decimal] = None
    selling_general_administrative: Optional[Decimal] = None
    other_operating_expenses: Optional[Decimal] = None
    total_operating_expenses: Optional[Decimal] = None
    operating_income: Optional[Decimal] = None
    interest_expense: Optional[Decimal] = None
    interest_income: Optional[Decimal] = None
    other_income_expense: Optional[Decimal] = None
    income_before_taxes: Optional[Decimal] = None
    income_taxes: Optional[Decimal] = None
    net_income: Optional[Decimal] = None
    eps_basic: Optional[Decimal] = None
    eps_diluted: Optional[Decimal] = None
    ebitda: Optional[Decimal] = None
    
    # Cash Flow Statement
    operating_cash_flow: Optional[Decimal] = None
    depreciation_amortization: Optional[Decimal] = None
    stock_based_compensation: Optional[Decimal] = None
    change_in_working_capital: Optional[Decimal] = None
    other_operating_activities: Optional[Decimal] = None
    investing_cash_flow: Optional[Decimal] = None
    capital_expenditures: Optional[Decimal] = None
    acquisitions: Optional[Decimal] = None
    other_investing_activities: Optional[Decimal] = None
    financing_cash_flow: Optional[Decimal] = None
    debt_issuance_repayment: Optional[Decimal] = None
    dividends_paid: Optional[Decimal] = None
    stock_repurchased: Optional[Decimal] = None
    other_financing_activities: Optional[Decimal] = None
    change_in_cash: Optional[Decimal] = None
    free_cash_flow: Optional[Decimal] = None  # Calculado: OCF - CapEx
    
    # Shares
    shares_outstanding: Optional[int] = None
    weighted_avg_shares_basic: Optional[int] = None
    weighted_avg_shares_diluted: Optional[int] = None
    
    # Metadata
    source: str = Field(default="fmp", max_length=10)
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    class Config:
        schema_extra = {
            "example": {
                "ticker": "AAPL",
                "period_date": "2024-09-30",
                "period_type": "Q4",
                "fiscal_year": 2024,
                "cash_and_equivalents": 29_943_000_000,
                "total_debt": 106_626_000_000,
                "revenue": 94_930_000_000,
                "net_income": 22_956_000_000,
                "operating_cash_flow": 27_551_000_000,
                "free_cash_flow": 26_274_000_000,
                "shares_outstanding": 15_204_000_000
            }
        }


class FinancialStatement(FinancialStatementCreate):
    """Complete financial statement with metadata"""
    fetched_at: datetime
    
    # Computed properties
    @property
    def total_cash(self) -> Optional[Decimal]:
        """Total liquid cash (cash + short-term investments)"""
        if self.cash_and_equivalents is None:
            return None
        return self.cash_and_equivalents + (self.short_term_investments or Decimal(0))
    
    @property
    def current_ratio(self) -> Optional[Decimal]:
        """Current assets / Current liabilities"""
        if not self.total_current_assets or not self.total_current_liabilities:
            return None
        if self.total_current_liabilities == 0:
            return None
        return self.total_current_assets / self.total_current_liabilities
    
    @property
    def debt_to_equity(self) -> Optional[Decimal]:
        """Total debt / Stockholders equity"""
        if not self.total_debt or not self.stockholders_equity:
            return None
        if self.stockholders_equity == 0:
            return None
        return self.total_debt / self.stockholders_equity
    
    @property
    def working_capital(self) -> Optional[Decimal]:
        """Current assets - Current liabilities"""
        if self.total_current_assets is None or self.total_current_liabilities is None:
            return None
        return self.total_current_assets - self.total_current_liabilities
    
    class Config:
        orm_mode = True


class FinancialStatementResponse(BaseModel):
    """Response model for financial statement"""
    ticker: str
    period_date: date
    period_type: FinancialPeriod
    fiscal_year: Optional[int]
    
    # Balance Sheet (formatted)
    cash: Optional[float] = Field(None, description="Cash and equivalents")
    investments: Optional[float] = Field(None, description="Short-term investments")
    total_cash: Optional[float] = Field(None, description="Cash + Investments")
    debt: Optional[float] = Field(None, description="Total debt")
    equity: Optional[float] = Field(None, description="Stockholders equity")
    
    # Income Statement (formatted)
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    eps_diluted: Optional[float] = None
    
    # Cash Flow (formatted)
    operating_cash_flow: Optional[float] = None
    free_cash_flow: Optional[float] = None
    
    # Shares
    shares_outstanding: Optional[int] = None
    
    # Ratios
    current_ratio: Optional[float] = None
    debt_to_equity_ratio: Optional[float] = None
    working_capital: Optional[float] = None
    
    # Metadata
    fetched_at: datetime
    
    @classmethod
    def from_model(cls, statement: FinancialStatement) -> "FinancialStatementResponse":
        """Convert FinancialStatement to response format"""
        return cls(
            ticker=statement.ticker,
            period_date=statement.period_date,
            period_type=statement.period_type,
            fiscal_year=statement.fiscal_year,
            cash=float(statement.cash_and_equivalents) if statement.cash_and_equivalents else None,
            investments=float(statement.short_term_investments) if statement.short_term_investments else None,
            total_cash=float(statement.total_cash) if statement.total_cash else None,
            debt=float(statement.total_debt) if statement.total_debt else None,
            equity=float(statement.stockholders_equity) if statement.stockholders_equity else None,
            revenue=float(statement.revenue) if statement.revenue else None,
            net_income=float(statement.net_income) if statement.net_income else None,
            eps_diluted=float(statement.eps_diluted) if statement.eps_diluted else None,
            operating_cash_flow=float(statement.operating_cash_flow) if statement.operating_cash_flow else None,
            free_cash_flow=float(statement.free_cash_flow) if statement.free_cash_flow else None,
            shares_outstanding=statement.shares_outstanding,
            current_ratio=float(statement.current_ratio) if statement.current_ratio else None,
            debt_to_equity_ratio=float(statement.debt_to_equity) if statement.debt_to_equity else None,
            working_capital=float(statement.working_capital) if statement.working_capital else None,
            fetched_at=statement.fetched_at
        )
    
    class Config:
        schema_extra = {
            "example": {
                "ticker": "AAPL",
                "period_date": "2024-09-30",
                "period_type": "Q4",
                "fiscal_year": 2024,
                "cash": 29943000000,
                "total_cash": 35000000000,
                "debt": 106626000000,
                "equity": 62146000000,
                "revenue": 94930000000,
                "net_income": 22956000000,
                "operating_cash_flow": 27551000000,
                "free_cash_flow": 26274000000,
                "shares_outstanding": 15204000000,
                "current_ratio": 0.87,
                "debt_to_equity_ratio": 1.72,
                "working_capital": -7082000000,
                "fetched_at": "2024-11-14T10:30:00Z"
            }
        }

