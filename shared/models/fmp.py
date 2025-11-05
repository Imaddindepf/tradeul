"""
Pydantic models for Financial Modeling Prep (FMP) API
Documentation: https://site.financialmodelingprep.com/developer/docs
"""

from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field, validator


# =============================================
# COMPANY PROFILE
# =============================================

class FMPProfile(BaseModel):
    """
    Company profile from FMP
    Endpoint: /api/v3/profile/{symbol}
    """
    symbol: str = Field(..., description="Ticker symbol")
    price: Optional[float] = Field(None, description="Current price")
    beta: Optional[float] = Field(None, description="Beta")
    volAvg: Optional[int] = Field(None, description="Average volume")
    mktCap: Optional[int] = Field(None, description="Market capitalization")
    lastDiv: Optional[float] = Field(None, description="Last dividend")
    range: Optional[str] = Field(None, description="52-week range")
    changes: Optional[float] = Field(None, description="Price changes")
    companyName: Optional[str] = Field(None, description="Company name")
    currency: Optional[str] = Field(None, description="Currency")
    cik: Optional[str] = Field(None, description="CIK number")
    isin: Optional[str] = Field(None, description="ISIN")
    cusip: Optional[str] = Field(None, description="CUSIP")
    exchange: Optional[str] = Field(None, description="Exchange")
    exchangeShortName: Optional[str] = Field(None, description="Exchange short name")
    industry: Optional[str] = Field(None, description="Industry")
    website: Optional[str] = Field(None, description="Company website")
    description: Optional[str] = Field(None, description="Company description")
    ceo: Optional[str] = Field(None, description="CEO name")
    sector: Optional[str] = Field(None, description="Sector")
    country: Optional[str] = Field(None, description="Country")
    fullTimeEmployees: Optional[str] = Field(None, description="Number of employees")
    phone: Optional[str] = Field(None, description="Phone number")
    address: Optional[str] = Field(None, description="Address")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State")
    zip: Optional[str] = Field(None, description="ZIP code")
    dcfDiff: Optional[float] = Field(None, description="DCF difference")
    dcf: Optional[float] = Field(None, description="DCF value")
    image: Optional[str] = Field(None, description="Logo URL")
    ipoDate: Optional[str] = Field(None, description="IPO date")
    defaultImage: Optional[bool] = Field(None, description="Is default image")
    isEtf: Optional[bool] = Field(None, description="Is ETF")
    isActivelyTrading: Optional[bool] = Field(None, description="Is actively trading")
    isAdr: Optional[bool] = Field(None, description="Is ADR")
    isFund: Optional[bool] = Field(None, description="Is fund")


# =============================================
# QUOTE
# =============================================

class FMPQuote(BaseModel):
    """
    Real-time quote from FMP
    Endpoint: /api/v3/quote/{symbol}
    """
    symbol: str
    name: Optional[str] = None
    price: Optional[float] = None
    changesPercentage: Optional[float] = None
    change: Optional[float] = None
    dayLow: Optional[float] = None
    dayHigh: Optional[float] = None
    yearHigh: Optional[float] = None
    yearLow: Optional[float] = None
    marketCap: Optional[int] = None
    priceAvg50: Optional[float] = None
    priceAvg200: Optional[float] = None
    exchange: Optional[str] = None
    volume: Optional[int] = None
    avgVolume: Optional[int] = None
    open: Optional[float] = None
    previousClose: Optional[float] = None
    eps: Optional[float] = None
    pe: Optional[float] = None
    earningsAnnouncement: Optional[str] = None
    sharesOutstanding: Optional[int] = None
    timestamp: Optional[int] = None


# =============================================
# HISTORICAL PRICE
# =============================================

class FMPHistoricalPrice(BaseModel):
    """
    Historical price data
    Endpoint: /api/v3/historical-price-full/{symbol}
    """
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    open: float
    high: float
    low: float
    close: float
    adjClose: Optional[float] = None
    volume: int
    unadjustedVolume: Optional[int] = None
    change: Optional[float] = None
    changePercent: Optional[float] = None
    vwap: Optional[float] = None
    label: Optional[str] = None
    changeOverTime: Optional[float] = None
    
    @validator('date', pre=True)
    def parse_date(cls, v):
        if isinstance(v, date):
            return v.strftime('%Y-%m-%d')
        return v


# =============================================
# KEY METRICS
# =============================================

class FMPKeyMetrics(BaseModel):
    """
    Key metrics (TTM)
    Endpoint: /api/v3/key-metrics-ttm/{symbol}
    """
    symbol: str
    revenuePerShareTTM: Optional[float] = None
    netIncomePerShareTTM: Optional[float] = None
    operatingCashFlowPerShareTTM: Optional[float] = None
    freeCashFlowPerShareTTM: Optional[float] = None
    cashPerShareTTM: Optional[float] = None
    bookValuePerShareTTM: Optional[float] = None
    tangibleBookValuePerShareTTM: Optional[float] = None
    shareholdersEquityPerShareTTM: Optional[float] = None
    interestDebtPerShareTTM: Optional[float] = None
    marketCapTTM: Optional[float] = None
    enterpriseValueTTM: Optional[float] = None
    peRatioTTM: Optional[float] = None
    priceToSalesRatioTTM: Optional[float] = None
    pocfratioTTM: Optional[float] = None
    pfcfRatioTTM: Optional[float] = None
    pbRatioTTM: Optional[float] = None
    ptbRatioTTM: Optional[float] = None
    evToSalesTTM: Optional[float] = None
    enterpriseValueOverEBITDATTM: Optional[float] = None
    evToOperatingCashFlowTTM: Optional[float] = None
    evToFreeCashFlowTTM: Optional[float] = None
    earningsYieldTTM: Optional[float] = None
    freeCashFlowYieldTTM: Optional[float] = None
    debtToEquityTTM: Optional[float] = None
    debtToAssetsTTM: Optional[float] = None
    netDebtToEBITDATTM: Optional[float] = None
    currentRatioTTM: Optional[float] = None
    interestCoverageTTM: Optional[float] = None
    incomeQualityTTM: Optional[float] = None
    dividendYieldTTM: Optional[float] = None
    payoutRatioTTM: Optional[float] = None
    salesGeneralAndAdministrativeToRevenueTTM: Optional[float] = None
    researchAndDdevelopementToRevenueTTM: Optional[float] = None
    intangiblesToTotalAssetsTTM: Optional[float] = None
    capexToOperatingCashFlowTTM: Optional[float] = None
    capexToRevenueTTM: Optional[float] = None
    capexToDepreciationTTM: Optional[float] = None
    stockBasedCompensationToRevenueTTM: Optional[float] = None
    grahamNumberTTM: Optional[float] = None
    roicTTM: Optional[float] = None
    returnOnTangibleAssetsTTM: Optional[float] = None
    grahamNetNetTTM: Optional[float] = None
    workingCapitalTTM: Optional[float] = None
    tangibleAssetValueTTM: Optional[float] = None
    netCurrentAssetValueTTM: Optional[float] = None
    investedCapitalTTM: Optional[float] = None
    averageReceivablesTTM: Optional[float] = None
    averagePayablesTTM: Optional[float] = None
    averageInventoryTTM: Optional[float] = None
    daysSalesOutstandingTTM: Optional[float] = None
    daysPayablesOutstandingTTM: Optional[float] = None
    daysOfInventoryOnHandTTM: Optional[float] = None
    receivablesTurnoverTTM: Optional[float] = None
    payablesTurnoverTTM: Optional[float] = None
    inventoryTurnoverTTM: Optional[float] = None
    roeTTM: Optional[float] = None
    capexPerShareTTM: Optional[float] = None


# =============================================
# FLOAT SHARES (BULK)
# =============================================

class FMPFloat(BaseModel):
    """
    Float shares data (bulk endpoint)
    Endpoint: /stable/shares-float-all
    """
    symbol: str
    date: Optional[str] = Field(None, description="Date of data")
    freeFloat: Optional[float] = Field(None, description="Free float")
    floatShares: Optional[float] = Field(None, description="Float shares")
    outstandingShares: Optional[float] = Field(None, description="Outstanding shares")
    source: Optional[str] = Field(None, description="Data source")


class FMPFloatBulkResponse(BaseModel):
    """
    Bulk float response with pagination
    """
    data: List[FMPFloat] = Field(default_factory=list)
    page: Optional[int] = None
    total_pages: Optional[int] = None


# =============================================
# MARKET CAP (BATCH)
# =============================================

class FMPMarketCap(BaseModel):
    """
    Market cap data (batch endpoint)
    Endpoint: /stable/market-capitalization-batch
    """
    symbol: str
    marketCap: int = Field(..., description="Market capitalization")
    date: Optional[str] = Field(None, description="Date of data")


class FMPMarketCapBatch(BaseModel):
    """
    Batch market cap response
    Endpoint: /stable/market-capitalization-batch
    """
    market_capitalizations: List[FMPMarketCap] = Field(default_factory=list)


# =============================================
# STOCK SCREENER
# =============================================

class FMPScreenerResult(BaseModel):
    """
    Stock screener result
    Endpoint: /api/v3/stock-screener
    """
    symbol: str
    companyName: Optional[str] = None
    marketCap: Optional[int] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    beta: Optional[float] = None
    price: Optional[float] = None
    lastAnnualDividend: Optional[float] = None
    volume: Optional[int] = None
    exchange: Optional[str] = None
    exchangeShortName: Optional[str] = None
    country: Optional[str] = None
    isEtf: Optional[bool] = None
    isActivelyTrading: Optional[bool] = None

