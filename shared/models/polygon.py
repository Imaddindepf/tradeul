"""
Pydantic models for Polygon.io API responses
Documentation: https://polygon.io/docs/stocks/getting-started
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator


# =============================================
# SNAPSHOT MODELS
# =============================================

class DayData(BaseModel):
    """
    Daily bar data
    The most recent daily bar for this ticker
    """
    c: Optional[float] = Field(None, description="Close price")
    h: Optional[float] = Field(None, description="High price")
    l: Optional[float] = Field(None, description="Low price")
    o: Optional[float] = Field(None, description="Open price")
    v: Optional[float] = Field(None, description="Volume (can be float from Polygon)")
    vw: Optional[float] = Field(None, description="Volume weighted average price")
    otc: Optional[bool] = Field(None, description="Whether this aggregate is for an OTC ticker")
    
    @validator('v', pre=True)
    def convert_volume_to_int(cls, v):
        """Convert volume to int if needed"""
        if v is not None:
            return int(v)
        return v


class LastTrade(BaseModel):
    """
    Last trade information
    Most recent trade for the ticker
    """
    p: Optional[float] = Field(None, description="Trade price")
    s: Optional[int] = Field(None, description="Trade size (volume)")
    c: Optional[List[int]] = Field(None, description="Trade conditions")
    i: Optional[str] = Field(None, description="Trade ID")
    t: Optional[int] = Field(None, description="Timestamp (nanoseconds)")
    x: Optional[int] = Field(None, description="Exchange ID")


class LastQuote(BaseModel):
    """
    Last quote information
    Most recent bid/ask for the ticker
    """
    p: Optional[float] = Field(None, description="Bid price")
    s: Optional[int] = Field(None, description="Bid size (in lots)")
    P: Optional[float] = Field(None, description="Ask price")
    S: Optional[int] = Field(None, description="Ask size (in lots)")
    t: Optional[int] = Field(None, description="Timestamp (nanoseconds)")


class MinuteData(BaseModel):
    """
    Minute aggregate data
    Most recent minute bar for the ticker
    """
    av: Optional[int] = Field(None, description="Accumulated volume")
    c: Optional[float] = Field(None, description="Close price")
    h: Optional[float] = Field(None, description="High price")
    l: Optional[float] = Field(None, description="Low price")
    o: Optional[float] = Field(None, description="Open price")
    v: Optional[int] = Field(None, description="Volume")
    vw: Optional[float] = Field(None, description="Volume weighted average")
    n: Optional[int] = Field(None, description="Number of transactions")
    t: Optional[int] = Field(None, description="Unix millisecond timestamp")
    otc: Optional[bool] = Field(None, description="Whether this is OTC ticker")


class PrevDayData(BaseModel):
    """
    Previous day data
    Complete bar data from the previous trading day
    """
    o: Optional[float] = Field(None, description="Open price")
    h: Optional[float] = Field(None, description="High price")
    l: Optional[float] = Field(None, description="Low price")
    c: Optional[float] = Field(None, description="Close price")
    v: Optional[float] = Field(None, description="Volume (can be float from Polygon)")
    vw: Optional[float] = Field(None, description="Volume weighted average")
    
    @validator('v', pre=True)
    def convert_volume_to_int(cls, v):
        """Convert volume to int if needed"""
        if v is not None:
            return int(v)
        return v


class PolygonSnapshot(BaseModel):
    """
    Full market snapshot for a single ticker
    Endpoint: GET /v2/snapshot/locale/us/markets/stocks/tickers
    
    Provides comprehensive real-time data including current prices,
    volume, trades, quotes, and comparative metrics.
    """
    # Identity
    ticker: str = Field(..., description="Exchange symbol")
    updated: Optional[int] = Field(None, description="Last update timestamp (nanoseconds)")
    
    # Market data components
    day: Optional[DayData] = Field(None, description="Most recent daily bar")
    fmv: Optional[float] = Field(None, description="Fair market value (Business plan only)")
    lastTrade: Optional[LastTrade] = Field(None, description="Most recent trade")
    lastQuote: Optional[LastQuote] = Field(None, description="Most recent quote")
    min: Optional[MinuteData] = Field(None, description="Current minute bar")
    prevDay: Optional[PrevDayData] = Field(None, description="Previous day's bar")
    
    # Change metrics
    todaysChange: Optional[float] = Field(None, description="Value of change from previous day")
    todaysChangePerc: Optional[float] = Field(None, description="Percentage change since previous day")
    
    @validator('updated', pre=True)
    def convert_updated(cls, v):
        """Keep timestamp as nanoseconds for precision"""
        return v
    
    @property
    def current_price(self) -> Optional[float]:
        """
        Get current price from best available source
        Priority: lastTrade > day.c > prevDay.c
        Filters out invalid prices (0 or negative)
        """
        if self.lastTrade and self.lastTrade.p and self.lastTrade.p > 0:
            return self.lastTrade.p
        if self.day and self.day.c and self.day.c > 0:
            return self.day.c
        if self.prevDay and self.prevDay.c and self.prevDay.c > 0:
            return self.prevDay.c
        return None
    
    @property
    def current_volume(self) -> Optional[int]:
        """
        Get current accumulated volume
        
        Priority: min.av > day.v
        - min.av: Volumen acumulado (perfecto para pre/post market)
        - day.v: Volumen del día completo (solo válido después del cierre) o cuando la sesión está abierta
        """
        if self.min and self.min.av:
            return self.min.av
        if self.day and self.day.v:
            return self.day.v
        return None
    
    @property
    def bid_ask_spread(self) -> Optional[float]:
        """Calculate bid-ask spread"""
        if self.lastQuote and self.lastQuote.p and self.lastQuote.P:
            return self.lastQuote.P - self.lastQuote.p
        return None
    
    @property
    def mid_price(self) -> Optional[float]:
        """Calculate mid price from bid/ask"""
        if self.lastQuote and self.lastQuote.p and self.lastQuote.P:
            return (self.lastQuote.p + self.lastQuote.P) / 2
        return None
    
    @property
    def is_otc(self) -> bool:
        """Check if this is an OTC security"""
        return (self.day and self.day.otc) or (self.min and self.min.otc) or False


class PolygonSnapshotResponse(BaseModel):
    """
    Response wrapper for snapshot API
    Endpoint: GET /v2/snapshot/locale/us/markets/stocks/tickers
    
    Contains snapshots for 10,000+ actively traded tickers
    """
    status: str = Field(..., description="Response status")
    count: Optional[int] = Field(None, description="Number of tickers returned")
    tickers: List[PolygonSnapshot] = Field(default_factory=list, description="Array of ticker snapshots")


# =============================================
# WEBSOCKET MODELS
# =============================================

class PolygonTrade(BaseModel):
    """
    Trade (Ticker) message from WebSocket
    Event type: T
    
    Subscription: Use ticker symbol or * for all
    Example: T.AAPL or T.*
    """
    ev: str = Field("T", description="Event type (always 'T')")
    sym: str = Field(..., description="Ticker symbol")
    x: int = Field(..., description="Exchange ID")
    i: str = Field(..., description="Trade ID")
    z: int = Field(..., description="Tape (1=NYSE, 2=AMEX, 3=Nasdaq)")
    p: float = Field(..., description="Trade price")
    s: int = Field(..., description="Trade size")
    c: Optional[List[int]] = Field(None, description="Trade conditions")
    t: int = Field(..., description="SIP timestamp (Unix MS)")
    q: int = Field(..., description="Sequence number")
    trfi: Optional[int] = Field(None, description="Trade Reporting Facility ID")
    trft: Optional[int] = Field(None, description="TRF timestamp (Unix MS)")
    
    @property
    def symbol(self) -> str:
        """Get ticker symbol"""
        return self.sym
    
    @property
    def price(self) -> float:
        """Get trade price"""
        return self.p
    
    @property
    def size(self) -> int:
        """Get trade size"""
        return self.s
    
    @property
    def timestamp_ms(self) -> int:
        """Get SIP timestamp in milliseconds"""
        return self.t
    
    @property
    def tape_name(self) -> str:
        """Get human-readable tape name"""
        tape_map = {1: "NYSE", 2: "AMEX", 3: "NASDAQ"}
        return tape_map.get(self.z, f"Unknown ({self.z})")


class PolygonQuote(BaseModel):
    """
    Quote (NBBO) message from WebSocket
    Event type: Q
    
    Provides National Best Bid and Offer quote data
    Subscription: Use ticker symbol or * for all
    Example: Q.AAPL or Q.*
    
    Note: bx/ax (exchange IDs) may not always be present depending on quote type
    """
    ev: str = Field("Q", description="Event type (always 'Q')")
    sym: str = Field(..., description="Ticker symbol")
    bx: Optional[int] = Field(None, description="Bid exchange ID")
    bp: float = Field(..., description="Bid price")
    bs: int = Field(..., description="Bid size (round lots)")
    ax: Optional[int] = Field(None, description="Ask exchange ID")
    ap: float = Field(..., description="Ask price")
    as_: int = Field(..., alias="as", description="Ask size (round lots)")
    c: Optional[int] = Field(None, description="Condition")
    i: Optional[List[int]] = Field(None, description="Indicators")
    t: int = Field(..., description="SIP timestamp (Unix MS)")
    q: int = Field(..., description="Sequence number")
    z: int = Field(..., description="Tape (1=NYSE, 2=AMEX, 3=Nasdaq)")
    
    @property
    def symbol(self) -> str:
        """Get ticker symbol"""
        return self.sym
    
    @property
    def bid(self) -> float:
        """Get bid price"""
        return self.bp
    
    @property
    def ask(self) -> float:
        """Get ask price"""
        return self.ap
    
    @property
    def bid_size_shares(self) -> int:
        """Get bid size in shares (round lots * 100)"""
        return self.bs * 100
    
    @property
    def ask_size_shares(self) -> int:
        """Get ask size in shares (round lots * 100)"""
        return self.as_ * 100
    
    @property
    def spread(self) -> float:
        """Calculate bid-ask spread"""
        return self.ap - self.bp
    
    @property
    def mid_price(self) -> float:
        """Calculate mid price"""
        return (self.ap + self.bp) / 2
    
    @property
    def spread_percent(self) -> float:
        """Calculate spread as percentage of mid price"""
        mid = self.mid_price
        if mid > 0:
            return (self.spread / mid) * 100
        return 0.0
    
    @property
    def tape_name(self) -> str:
        """Get human-readable tape name"""
        tape_map = {1: "NYSE", 2: "AMEX", 3: "NASDAQ"}
        return tape_map.get(self.z, f"Unknown ({self.z})")


class PolygonAgg(BaseModel):
    """
    Aggregate (Per Second) message from WebSocket
    Event type: A
    
    Provides second-by-second OHLCV aggregates in Eastern Time (ET)
    Covers pre-market, regular hours, and after-hours sessions
    
    Subscription: Use ticker symbol or * for all
    Example: A.AAPL or A.*
    
    Note: Bars are only emitted when qualifying trades occur
    """
    ev: str = Field("A", description="Event type (always 'A' for second bars)")
    sym: str = Field(..., description="Ticker symbol")
    
    # Volume data
    v: int = Field(..., description="Tick volume (this bar)")
    av: int = Field(..., description="Today's accumulated volume")
    
    # Price data for this bar
    o: float = Field(..., description="Opening tick price for this window")
    c: float = Field(..., description="Closing tick price for this window")
    h: float = Field(..., description="Highest tick price for this window")
    l: float = Field(..., description="Lowest tick price for this window")
    
    # Volume-weighted averages
    vw: float = Field(..., description="Tick's volume weighted average price")
    a: float = Field(..., description="Today's volume weighted average price (VWAP)")
    
    # Today's official data (only available during/after market open)
    op: Optional[float] = Field(None, description="Today's official opening price (None in pre-market)")
    
    # Additional metrics
    z: int = Field(..., description="Average trade size for this window")
    
    # Timestamps
    s: int = Field(..., description="Start timestamp (Unix MS)")
    e: int = Field(..., description="End timestamp (Unix MS)")
    
    # OTC indicator
    otc: Optional[bool] = Field(None, description="Whether this is an OTC ticker")
    
    @property
    def symbol(self) -> str:
        """Get ticker symbol"""
        return self.sym
    
    @property
    def open(self) -> float:
        """Get bar open price"""
        return self.o
    
    @property
    def close(self) -> float:
        """Get bar close price"""
        return self.c
    
    @property
    def high(self) -> float:
        """Get bar high price"""
        return self.h
    
    @property
    def low(self) -> float:
        """Get bar low price"""
        return self.l
    
    @property
    def volume(self) -> int:
        """Get bar volume"""
        return self.v
    
    @property
    def vwap(self) -> float:
        """Get today's VWAP"""
        return self.a
    
    @property
    def bar_range(self) -> float:
        """Calculate bar range (high - low)"""
        return self.h - self.l
    
    @property
    def bar_change(self) -> float:
        """Calculate bar change (close - open)"""
        return self.c - self.o
    
    @property
    def bar_change_percent(self) -> float:
        """Calculate bar change as percentage"""
        if self.o > 0:
            return ((self.c - self.o) / self.o) * 100
        return 0.0
    
    @property
    def is_otc(self) -> bool:
        """Check if this is an OTC ticker"""
        return self.otc or False


# =============================================
# MARKET STATUS
# =============================================

class PolygonExchanges(BaseModel):
    """Exchange statuses"""
    nasdaq: Optional[str] = Field(None, description="Nasdaq status")
    nyse: Optional[str] = Field(None, description="NYSE status")
    otc: Optional[str] = Field(None, description="OTC status")


class PolygonCurrencies(BaseModel):
    """Currency market statuses"""
    crypto: Optional[str] = Field(None, description="Crypto market status")
    fx: Optional[str] = Field(None, description="Forex market status")


class PolygonIndicesGroups(BaseModel):
    """Indices groups statuses"""
    s_and_p: Optional[str] = Field(None, alias="s_and_p", description="S&P indices status")
    nasdaq: Optional[str] = Field(None, description="Nasdaq indices status")
    dow_jones: Optional[str] = Field(None, description="Dow Jones indices status")
    msci: Optional[str] = Field(None, description="MSCI indices status")
    ftse_russell: Optional[str] = Field(None, description="FTSE Russell indices status")
    mstar: Optional[str] = Field(None, description="Morningstar indices status")
    mstarc: Optional[str] = Field(None, description="Morningstar Customer indices status")
    societe_generale: Optional[str] = Field(None, description="Societe Generale indices status")
    cccy: Optional[str] = Field(None, description="Cboe Crypto indices status")
    cgi: Optional[str] = Field(None, description="Cboe Global Indices status")


class PolygonMarketStatus(BaseModel):
    """
    Market status response (real-time)
    Endpoint: GET /v1/marketstatus/now
    
    Status values:
    - "open": Market is open for trading
    - "extended-hours": Pre-market or after-hours
    - "closed": Market is closed
    """
    market: str = Field(..., description="Overall market status")
    serverTime: str = Field(..., description="Server time (RFC3339 format)")
    earlyHours: bool = Field(..., description="Is market in pre-market hours")
    afterHours: bool = Field(..., description="Is market in post-market hours")
    exchanges: PolygonExchanges = Field(..., description="Exchange statuses")
    currencies: Optional[PolygonCurrencies] = Field(None, description="Currency market statuses")
    indicesGroups: Optional[PolygonIndicesGroups] = Field(None, description="Indices groups statuses")
    
    @property
    def is_market_open(self) -> bool:
        """Check if regular market hours are active"""
        return self.market == "open" and not self.earlyHours and not self.afterHours
    
    @property
    def is_pre_market(self) -> bool:
        """Check if in pre-market hours"""
        return self.earlyHours and self.market == "extended-hours"
    
    @property
    def is_post_market(self) -> bool:
        """Check if in post-market hours"""
        return self.afterHours and self.market == "extended-hours"
    
    @property
    def is_closed(self) -> bool:
        """Check if market is closed"""
        return self.market == "closed"
    
    def get_market_session_enum(self):
        """
        Convert Polygon status to our MarketSession enum
        
        Returns:
            MarketSession enum value
        """
        from shared.enums.market_session import MarketSession
        
        if self.is_pre_market:
            return MarketSession.PRE_MARKET
        elif self.is_market_open:
            return MarketSession.MARKET_OPEN
        elif self.is_post_market:
            return MarketSession.POST_MARKET
        else:
            return MarketSession.CLOSED


class PolygonMarketHoliday(BaseModel):
    """
    Market holiday information
    Endpoint: GET /v1/marketstatus/upcoming
    """
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    exchange: str = Field(..., description="Exchange (NASDAQ, NYSE)")
    name: str = Field(..., description="Holiday name")
    status: str = Field(..., description="Status (closed, early-close)")
    open: Optional[str] = Field(None, description="Market open time (ISO 8601) if early-close")
    close: Optional[str] = Field(None, description="Market close time (ISO 8601) if early-close")
    
    @property
    def is_closed(self) -> bool:
        """Check if market is fully closed"""
        return self.status == "closed"
    
    @property
    def is_early_close(self) -> bool:
        """Check if market closes early"""
        return self.status == "early-close"


class PolygonMarketHolidaysResponse(BaseModel):
    """
    Response wrapper for market holidays
    Note: Polygon returns holidays as an object with numeric keys
    """
    holidays: List[PolygonMarketHoliday] = Field(default_factory=list)
    
    @classmethod
    def from_dict_response(cls, data) -> "PolygonMarketHolidaysResponse":
        """
        Parse Polygon's market holidays response
        
        Polygon can return:
        - List format: [{...}, {...}, ...]
        - Dict format with numeric keys: {"0": {...}, "1": {...}, ...}
        """
        holidays = []
        
        # Handle list format (Polygon's actual response format)
        if isinstance(data, list):
            for item in data:
                try:
                    holiday = PolygonMarketHoliday(**item)
                    holidays.append(holiday)
                except Exception:
                    continue
        
        # Handle dict format with numeric keys (legacy/alternate format)
        elif isinstance(data, dict):
            for key in sorted(data.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
                try:
                    holiday_data = data[key]
                    holiday = PolygonMarketHoliday(**holiday_data)
                    holidays.append(holiday)
                except Exception:
                    continue
        
        return cls(holidays=holidays)


# =============================================
# TICKER DETAILS
# =============================================

class PolygonAddress(BaseModel):
    """Company headquarters address"""
    address1: Optional[str] = Field(None, description="First line of address")
    address2: Optional[str] = Field(None, description="Second line of address")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State")
    postal_code: Optional[str] = Field(None, description="Postal code")


class PolygonBranding(BaseModel):
    """Company branding assets"""
    logo_url: Optional[str] = Field(None, description="URL to company logo (requires API key)")
    icon_url: Optional[str] = Field(None, description="URL to company icon (requires API key)")


class PolygonTickerDetails(BaseModel):
    """
    Comprehensive ticker details
    Endpoint: GET /v3/reference/tickers/{ticker}
    
    Provides deep company information including fundamentals, identifiers,
    market data, and branding assets.
    """
    # Core identifiers
    ticker: str = Field(..., description="Exchange symbol")
    name: str = Field(..., description="Company name")
    market: str = Field(..., description="Market type (stocks, crypto, fx, otc, indices)")
    locale: str = Field(..., description="Locale (us, global)")
    primary_exchange: Optional[str] = Field(None, description="ISO code of primary exchange")
    type: Optional[str] = Field(None, description="Asset type")
    active: bool = Field(True, description="Is actively traded")
    
    # Currency
    currency_name: Optional[str] = Field(None, description="Trading currency name")
    
    # Regulatory identifiers
    cik: Optional[str] = Field(None, description="CIK number")
    composite_figi: Optional[str] = Field(None, description="Composite OpenFIGI")
    share_class_figi: Optional[str] = Field(None, description="Share class OpenFIGI")
    
    # Company info
    description: Optional[str] = Field(None, description="Company description")
    homepage_url: Optional[str] = Field(None, description="Company website")
    phone_number: Optional[str] = Field(None, description="Company phone")
    address: Optional[PolygonAddress] = Field(None, description="Headquarters address")
    branding: Optional[PolygonBranding] = Field(None, description="Branding assets")
    
    # Market data
    market_cap: Optional[float] = Field(None, description="Market capitalization")
    share_class_shares_outstanding: Optional[float] = Field(
        None, 
        description="Outstanding shares for this class"
    )
    weighted_shares_outstanding: Optional[float] = Field(
        None,
        description="Weighted outstanding shares (all classes converted)"
    )
    round_lot: Optional[float] = Field(None, description="Round lot size")
    
    # Industry classification
    sic_code: Optional[str] = Field(None, description="SIC code")
    sic_description: Optional[str] = Field(None, description="SIC description")
    
    # Ticker components
    ticker_root: Optional[str] = Field(None, description="Root ticker (e.g., BRK from BRK.A)")
    ticker_suffix: Optional[str] = Field(None, description="Ticker suffix (e.g., A from BRK.A)")
    
    # Dates
    list_date: Optional[str] = Field(None, description="First listing date (YYYY-MM-DD)")
    delisted_utc: Optional[str] = Field(None, description="Delisting date if applicable")
    
    # Employees
    total_employees: Optional[int] = Field(None, description="Approximate employee count")
    
    @property
    def is_delisted(self) -> bool:
        """Check if ticker is delisted"""
        return self.delisted_utc is not None or not self.active
    
    @property
    def has_branding(self) -> bool:
        """Check if branding assets are available"""
        return self.branding is not None and (
            self.branding.logo_url is not None or 
            self.branding.icon_url is not None
        )
    
    def get_logo_url_with_key(self, api_key: str) -> Optional[str]:
        """Get logo URL with API key appended"""
        if self.branding and self.branding.logo_url:
            separator = "&" if "?" in self.branding.logo_url else "?"
            return f"{self.branding.logo_url}{separator}apiKey={api_key}"
        return None
    
    def get_icon_url_with_key(self, api_key: str) -> Optional[str]:
        """Get icon URL with API key appended"""
        if self.branding and self.branding.icon_url:
            separator = "&" if "?" in self.branding.icon_url else "?"
            return f"{self.branding.icon_url}{separator}apiKey={api_key}"
        return None


class PolygonTickerDetailsResponse(BaseModel):
    """Response wrapper for ticker details API"""
    status: str = Field(..., description="Response status")
    request_id: Optional[str] = Field(None, description="Request ID")
    results: PolygonTickerDetails = Field(..., description="Ticker details")
    count: Optional[int] = Field(None, description="Result count")

