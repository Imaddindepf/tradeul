"""
Pydantic models for Ticker Description feature
Combines metadata, financials, ratios, and analyst data
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, Field


# =============================================
# FMP RATIOS (TTM)
# =============================================

class FMPRatios(BaseModel):
    """
    Financial ratios from FMP
    Endpoint: /stable/ratios?symbol={symbol}&limit=1
    """
    symbol: str
    date: Optional[str] = None
    period: Optional[str] = None
    
    # Valuation Ratios
    priceToEarningsRatio: Optional[float] = Field(None, alias="priceToEarningsRatio", description="P/E Ratio")
    priceToBookRatio: Optional[float] = Field(None, description="P/B Ratio")
    priceToSalesRatio: Optional[float] = Field(None, description="P/S Ratio")
    priceToFreeCashFlowRatio: Optional[float] = Field(None, description="P/FCF Ratio")
    enterpriseValueMultiple: Optional[float] = Field(None, description="EV/EBITDA")
    
    # Profitability
    grossProfitMargin: Optional[float] = None
    operatingProfitMargin: Optional[float] = None
    netProfitMargin: Optional[float] = None
    
    # Dividend
    dividendYield: Optional[float] = None
    dividendYieldPercentage: Optional[float] = None
    dividendPayoutRatio: Optional[float] = None
    dividendPerShare: Optional[float] = None
    
    # Per Share
    revenuePerShare: Optional[float] = None
    netIncomePerShare: Optional[float] = None
    bookValuePerShare: Optional[float] = None
    cashPerShare: Optional[float] = None
    
    # Debt/Leverage
    debtToEquityRatio: Optional[float] = None
    debtToAssetsRatio: Optional[float] = None
    currentRatio: Optional[float] = None
    quickRatio: Optional[float] = None
    
    class Config:
        populate_by_name = True


# =============================================
# ANALYST DATA
# =============================================

class AnalystRating(BaseModel):
    """
    Analyst rating summary
    Endpoint: /api/v3/analyst-stock-recommendations/{symbol}
    """
    symbol: str
    date: Optional[str] = None
    analystRatingsbuy: Optional[int] = Field(None, alias="analystRatingsbuy")
    analystRatingsHold: Optional[int] = None
    analystRatingsSell: Optional[int] = None
    analystRatingsStrongSell: Optional[int] = None
    analystRatingsStrongBuy: Optional[int] = None
    
    class Config:
        populate_by_name = True


class PriceTarget(BaseModel):
    """
    Individual analyst price target
    Endpoint: /api/v4/price-target?symbol={symbol}
    """
    symbol: str
    publishedDate: Optional[str] = None
    analystName: Optional[str] = None
    analystCompany: Optional[str] = None
    priceTarget: Optional[float] = None
    adjPriceTarget: Optional[float] = None
    priceWhenPosted: Optional[float] = None
    newsTitle: Optional[str] = None
    newsURL: Optional[str] = None
    newsPublisher: Optional[str] = None


# =============================================
# COMPANY INFO (from metadata + profile)
# =============================================

class CompanyInfo(BaseModel):
    """
    Combined company information
    """
    symbol: str
    name: str
    exchange: Optional[str] = None
    exchangeFullName: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    
    # Special company types
    is_spac: Optional[bool] = Field(None, description="True if company is a SPAC (Special Purpose Acquisition Company)")
    sic_code: Optional[str] = Field(None, description="SIC Code (6770 = Blank Checks/SPAC)")
    
    # Description
    description: Optional[str] = None
    ceo: Optional[str] = None
    website: Optional[str] = None
    
    # Location
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    
    # Employees & Dates
    employees: Optional[int] = None
    ipoDate: Optional[str] = None
    
    # Images
    logoUrl: Optional[str] = None
    iconUrl: Optional[str] = None


# =============================================
# MARKET STATS
# =============================================

class MarketStats(BaseModel):
    """
    Market statistics - all numeric fields as float to handle API variations
    """
    price: Optional[float] = None
    change: Optional[float] = None
    changePercent: Optional[float] = None
    volume: Optional[float] = None  # Changed to float - API may return float
    avgVolume: Optional[float] = None  # Changed to float - API may return float
    
    # Market Cap & Float
    marketCap: Optional[float] = None
    sharesOutstanding: Optional[float] = None  # Changed to float
    floatShares: Optional[float] = None  # Changed to float
    
    # Ranges
    dayLow: Optional[float] = None
    dayHigh: Optional[float] = None
    yearLow: Optional[float] = None
    yearHigh: Optional[float] = None
    range52Week: Optional[str] = None
    
    # Beta & Risk
    beta: Optional[float] = None


# =============================================
# VALUATION METRICS (formatted for display)
# =============================================

class ValuationMetrics(BaseModel):
    """
    Valuation metrics for display
    """
    # Valuation Ratios
    peRatio: Optional[float] = Field(None, description="Trailing P/E")
    forwardPE: Optional[float] = Field(None, description="Forward P/E")
    pegRatio: Optional[float] = Field(None, description="PEG Ratio")
    pbRatio: Optional[float] = Field(None, description="Price/Book")
    psRatio: Optional[float] = Field(None, description="Price/Sales")
    evToEbitda: Optional[float] = Field(None, description="EV/EBITDA")
    evToRevenue: Optional[float] = Field(None, description="EV/Revenue")
    enterpriseValue: Optional[float] = Field(None, description="Enterprise Value")


class DividendInfo(BaseModel):
    """
    Dividend information
    """
    trailingYield: Optional[float] = None
    forwardYield: Optional[float] = None
    payoutRatio: Optional[float] = None
    dividendPerShare: Optional[float] = None
    exDividendDate: Optional[str] = None
    dividendDate: Optional[str] = None
    fiveYearAvgYield: Optional[float] = None


class RiskMetrics(BaseModel):
    """
    Risk and sentiment metrics
    """
    beta: Optional[float] = None
    shortInterest: Optional[int] = None
    shortRatio: Optional[float] = None
    shortPercentFloat: Optional[float] = None


# =============================================
# COMPLETE DESCRIPTION RESPONSE
# =============================================

class TickerDescription(BaseModel):
    """
    Complete ticker description combining all data sources
    """
    symbol: str
    updatedAt: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    
    # Company Info
    company: CompanyInfo
    
    # Market Stats
    stats: MarketStats
    
    # Valuation
    valuation: ValuationMetrics
    
    # Dividend
    dividend: DividendInfo
    
    # Risk
    risk: RiskMetrics
    
    # Analyst Data
    analystRating: Optional[AnalystRating] = None
    priceTargets: List[PriceTarget] = Field(default_factory=list)
    
    # Consensus
    consensusTarget: Optional[float] = None
    targetUpside: Optional[float] = None
    
    # Raw ratios (for additional data)
    ratios: Optional[FMPRatios] = None

