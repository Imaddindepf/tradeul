"""
Pydantic models for Scanner functionality
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator

from ..enums.market_session import MarketSession


# =============================================
# SCANNER TICKER (COMBINED DATA)
# =============================================

class ScannerTicker(BaseModel):
    """
    Combined data structure for a scanned ticker
    Merges real-time data from Polygon with historical/reference data
    """
    # Identity
    symbol: str = Field(..., description="Ticker symbol")
    timestamp: datetime = Field(default_factory=datetime.now, description="Scan timestamp")
    
    # Real-time market data
    price: float = Field(..., description="Current price")
    bid: Optional[float] = Field(None, description="Bid price")
    ask: Optional[float] = Field(None, description="Ask price")
    volume: int = Field(..., description="Current volume")
    volume_today: int = Field(..., description="Total volume today")
    
    # OHLC
    open: Optional[float] = Field(None, description="Open price")
    high: Optional[float] = Field(None, description="High price")
    low: Optional[float] = Field(None, description="Low price")
    
    # Previous day reference
    prev_close: Optional[float] = Field(None, description="Previous close")
    prev_volume: Optional[int] = Field(None, description="Previous day volume")
    
    # Changes
    change: Optional[float] = Field(None, description="Price change from prev close")
    change_percent: Optional[float] = Field(None, description="Percentage change")
    
    # Historical/Reference data
    avg_volume_30d: Optional[int] = Field(None, description="30-day average volume")
    avg_volume_10d: Optional[int] = Field(None, description="10-day average volume")
    float_shares: Optional[int] = Field(None, description="Float shares")
    shares_outstanding: Optional[int] = Field(None, description="Shares outstanding")
    market_cap: Optional[int] = Field(None, description="Market capitalization")
    
    # Fundamental data
    sector: Optional[str] = Field(None, description="Sector")
    industry: Optional[str] = Field(None, description="Industry")
    exchange: Optional[str] = Field(None, description="Exchange")
    
    # Calculated indicators
    rvol: Optional[float] = Field(None, description="Relative volume")
    rvol_slot: Optional[float] = Field(None, description="RVOL for current slot")
    atr: Optional[float] = Field(None, description="Average True Range (14 periods)")
    atr_percent: Optional[float] = Field(None, description="ATR as % of price")
    price_from_high: Optional[float] = Field(None, description="% from day high")
    price_from_low: Optional[float] = Field(None, description="% from day low")
    price_vs_vwap: Optional[float] = Field(None, description="Price vs VWAP")
    
    # Session context
    session: MarketSession = Field(..., description="Current market session")
    
    # Scoring
    score: float = Field(0.0, description="Composite score")
    rank: Optional[int] = Field(None, description="Rank in results")
    
    # Metadata
    filters_matched: List[str] = Field(default_factory=list, description="Matched filter names")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    @validator('change', always=True)
    def calculate_change(cls, v, values):
        """Auto-calculate change if not provided"""
        if v is None and 'price' in values and 'prev_close' in values:
            if values['prev_close']:
                return values['price'] - values['prev_close']
        return v
    
    @validator('change_percent', always=True)
    def calculate_change_percent(cls, v, values):
        """Auto-calculate change percent if not provided"""
        if v is None and 'price' in values and 'prev_close' in values:
            if values['prev_close'] and values['prev_close'] != 0:
                return ((values['price'] - values['prev_close']) / values['prev_close']) * 100
        return v
    
    @validator('rvol', always=True)
    def calculate_rvol(cls, v, values):
        """
        Auto-calculate RVOL simple si no está provisto
        
        NOTA: Este es un cálculo SIMPLIFICADO para screening inicial rápido.
        El cálculo preciso por slots se hace en el Analytics Service.
        
        Pipeline de dos fases:
        1. Scanner usa RVOL simple para reducir 11k → 1000 tickers
        2. Analytics calcula RVOL preciso por slots para los 1000 filtrados
        
        Este enfoque es:
        - ✅ Escalable: No calculamos slots para 11k tickers
        - ✅ Rápido: Screening inicial veloz
        - ✅ Preciso: RVOL detallado donde importa
        """
        if v is None and 'volume_today' in values and 'avg_volume_30d' in values:
            if values['avg_volume_30d'] and values['avg_volume_30d'] > 0:
                # RVOL simple = volumen total hoy / promedio 30 días
                # (se refinará por el Analytics Service usando slots)
                return values['volume_today'] / values['avg_volume_30d']
        return v
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return self.model_dump()
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


# =============================================
# SCANNER RESULT (OUTPUT)
# =============================================

class ScannerResult(BaseModel):
    """
    Scanner result set
    Contains filtered tickers and metadata
    """
    timestamp: datetime = Field(default_factory=datetime.now)
    session: MarketSession
    total_universe_size: int = Field(..., description="Total tickers scanned")
    filtered_count: int = Field(..., description="Number of tickers passing filters")
    tickers: List[ScannerTicker] = Field(..., description="Filtered tickers")
    filters_applied: List[str] = Field(..., description="Names of applied filters")
    scan_duration_ms: Optional[float] = Field(None, description="Scan duration in ms")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


# =============================================
# FILTER CONFIGURATION
# =============================================

class FilterParameters(BaseModel):
    """Base parameters for filters"""
    # RVOL filters
    min_rvol: Optional[float] = Field(None, ge=0, description="Minimum RVOL")
    max_rvol: Optional[float] = Field(None, ge=0, description="Maximum RVOL")
    
    # Price filters
    min_price: Optional[float] = Field(None, ge=0, description="Minimum price")
    max_price: Optional[float] = Field(None, ge=0, description="Maximum price")
    
    # Volume filters
    min_volume: Optional[int] = Field(None, ge=0, description="Minimum volume")
    min_volume_today: Optional[int] = Field(None, ge=0, description="Minimum volume today")
    
    # Change filters
    min_change_percent: Optional[float] = Field(None, description="Minimum % change")
    max_change_percent: Optional[float] = Field(None, description="Maximum % change")
    
    # Market cap filters
    min_market_cap: Optional[int] = Field(None, ge=0, description="Minimum market cap")
    max_market_cap: Optional[int] = Field(None, ge=0, description="Maximum market cap")
    
    # Float filters
    min_float: Optional[int] = Field(None, ge=0, description="Minimum float shares")
    max_float: Optional[int] = Field(None, ge=0, description="Maximum float shares")
    
    # Sector/Industry filters
    sectors: Optional[List[str]] = Field(None, description="Allowed sectors")
    industries: Optional[List[str]] = Field(None, description="Allowed industries")
    exchanges: Optional[List[str]] = Field(None, description="Allowed exchanges")
    
    # Advanced filters
    min_price_from_high: Optional[float] = Field(None, description="Min % from day high")
    max_price_from_high: Optional[float] = Field(None, description="Max % from day high")
    
    # Custom expression (for advanced users)
    custom_expression: Optional[str] = Field(None, description="Python expression for custom filter")
    
    class Config:
        extra = "allow"  # Allow additional fields for custom filters


class FilterConfig(BaseModel):
    """
    Configuration for a scanner filter
    Stored in database and configurable via admin panel
    """
    id: Optional[int] = Field(None, description="Database ID")
    name: str = Field(..., description="Filter name", max_length=100)
    description: Optional[str] = Field(None, description="Filter description")
    enabled: bool = Field(True, description="Is filter enabled")
    filter_type: str = Field(..., description="Filter type (rvol, price, volume, custom)")
    parameters: FilterParameters = Field(..., description="Filter parameters")
    priority: int = Field(0, description="Filter priority (higher = applied first)")
    
    # Sessions where filter applies
    apply_to_sessions: Optional[List[MarketSession]] = Field(
        None, 
        description="Sessions where filter applies (None = all sessions)"
    )
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def applies_to_session(self, session: MarketSession) -> bool:
        """Check if filter applies to given session"""
        if self.apply_to_sessions is None:
            return True
        return session in self.apply_to_sessions
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


# =============================================
# RVOL SLOT DATA
# =============================================

class RVOLSlotData(BaseModel):
    """
    RVOL data for a specific time slot
    Used for more accurate RVOL calculations
    """
    symbol: str
    date: str  # YYYY-MM-DD
    slot_number: int = Field(..., ge=0, le=77, description="Slot number (0-77 for 5-min slots)")
    slot_time: str  # HH:MM format
    volume_accumulated: int = Field(..., description="Volume accumulated up to this slot")
    trades_count: Optional[int] = Field(None, description="Number of trades")
    avg_price: Optional[float] = Field(None, description="Average price in slot")
    
    @validator('slot_number')
    def validate_slot(cls, v):
        """Validate slot number (78 slots of 5 min = 390 minutes)"""
        if not 0 <= v <= 77:
            raise ValueError("Slot number must be between 0 and 77")
        return v


# =============================================
# TICKER METADATA
# =============================================

class TickerMetadata(BaseModel):
    """
    Reference metadata for a ticker
    Cached in Redis with TTL
    """
    symbol: str
    company_name: Optional[str] = None
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[int] = None
    float_shares: Optional[int] = None
    shares_outstanding: Optional[int] = None
    avg_volume_30d: Optional[int] = None
    avg_volume_10d: Optional[int] = None
    avg_price_30d: Optional[float] = None
    beta: Optional[float] = None
    is_etf: bool = False
    is_actively_trading: bool = True
    updated_at: datetime = Field(default_factory=datetime.now)
    
    @validator('market_cap', 'float_shares', 'shares_outstanding', 'avg_volume_30d', 'avg_volume_10d', pre=True)
    def convert_to_int(cls, v):
        """Convert float to int for numeric fields"""
        if v is not None and isinstance(v, float):
            return int(v)
        return v
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

