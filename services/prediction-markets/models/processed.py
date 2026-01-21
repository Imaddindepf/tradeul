"""
Processed Models for API Response
These models represent the final data sent to the frontend
"""

from typing import Optional, List, Dict
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class MarketSource(str, Enum):
    """Source of prediction market data"""
    POLYMARKET = "PolyM"
    KALSHI = "Kalshi"


class ProcessedMarket(BaseModel):
    """
    Processed market with calculated price changes
    Represents a single prediction within an event
    """
    id: str
    question: str
    
    # Current state
    probability: float = Field(description="Current YES probability (0-1)")
    probability_pct: float = Field(description="Current YES probability (0-100)")
    
    # Price changes (percentage points)
    change_1d: Optional[float] = Field(default=None, description="1-day change in probability")
    change_5d: Optional[float] = Field(default=None, description="5-day change in probability")
    change_1m: Optional[float] = Field(default=None, description="1-month change in probability")
    
    # 30-day range
    low_30d: Optional[float] = Field(default=None, description="30-day low probability")
    high_30d: Optional[float] = Field(default=None, description="30-day high probability")
    
    # Volume
    volume: Optional[float] = Field(default=None, description="Total volume USD")
    volume_24h: Optional[float] = Field(default=None, description="24h volume USD")
    
    # Dates
    end_date: Optional[datetime] = Field(default=None, description="Resolution date")
    end_date_label: Optional[str] = Field(default=None, description="Human readable date label")
    
    # Metadata
    source: MarketSource = MarketSource.POLYMARKET
    clob_token_id: Optional[str] = Field(default=None, description="Token ID for price history")
    
    # Timestamps
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


class ProcessedEvent(BaseModel):
    """
    Processed event containing multiple markets (date variants)
    """
    id: str
    title: str
    slug: Optional[str] = None
    
    # Categorization
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    
    # Aggregated metrics
    total_volume: Optional[float] = Field(default=None, description="Total volume across all markets")
    volume_24h: Optional[float] = Field(default=None, description="24h volume")
    
    # Markets (sorted by end_date)
    markets: List[ProcessedMarket] = Field(default_factory=list)
    
    # Relevance score (for sorting)
    relevance_score: float = Field(default=0.0)
    
    # Timestamps
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def get_primary_market(self) -> Optional[ProcessedMarket]:
        """Get the primary/featured market (highest volume or nearest date)"""
        if not self.markets:
            return None
        return self.markets[0]


class CategoryGroup(BaseModel):
    """
    Group of events within a category/subcategory
    """
    category: str
    subcategory: Optional[str] = None
    display_name: str
    events: List[ProcessedEvent] = Field(default_factory=list)
    total_events: int = 0
    total_volume: float = 0.0


class PredictionMarketsResponse(BaseModel):
    """
    Full API response with categorized events
    """
    categories: List[CategoryGroup] = Field(default_factory=list)
    
    # Metadata
    total_events: int = 0
    total_markets: int = 0
    
    # Cache info
    cached_at: datetime = Field(default_factory=datetime.utcnow)
    cache_ttl_seconds: int = 300
    
    # Filters applied
    filters: Dict[str, str] = Field(default_factory=dict)


class EventsListResponse(BaseModel):
    """Simple list response for events endpoint"""
    events: List[ProcessedEvent] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
    cached_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Extended Models for New Features
# =============================================================================

class SearchResult(BaseModel):
    """Single search result item"""
    id: str
    title: str
    slug: Optional[str] = None
    type: str = Field(description="event, market, or profile")
    volume: Optional[float] = None
    probability: Optional[float] = None
    image: Optional[str] = None


class SearchResponse(BaseModel):
    """Search results response"""
    query: str
    events: List[SearchResult] = Field(default_factory=list)
    markets: List[SearchResult] = Field(default_factory=list)
    total_results: int = 0


class SeriesItem(BaseModel):
    """A series grouping related events"""
    id: str
    title: str
    slug: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    event_count: int = 0
    total_volume: float = 0.0


class SeriesResponse(BaseModel):
    """Series list response"""
    series: List[SeriesItem] = Field(default_factory=list)
    total: int = 0


class Comment(BaseModel):
    """Single comment on an event/market"""
    id: str
    content: str
    author_address: Optional[str] = None
    author_name: Optional[str] = None
    created_at: Optional[datetime] = None
    likes: int = 0


class CommentsResponse(BaseModel):
    """Comments response"""
    comments: List[Comment] = Field(default_factory=list)
    total: int = 0
    asset_id: Optional[str] = None


class TopHolder(BaseModel):
    """Top holder of a market position"""
    address: str
    display_name: Optional[str] = None
    position_value: float = 0.0
    shares: float = 0.0
    side: str = "YES"


class TopHoldersResponse(BaseModel):
    """Top holders response"""
    market_id: str
    holders: List[TopHolder] = Field(default_factory=list)


class LiveVolume(BaseModel):
    """Live volume data"""
    event_id: str
    volume_24h: float = 0.0
    volume_1h: float = 0.0
    trades_24h: int = 0


class SparklineData(BaseModel):
    """Price history for sparkline rendering"""
    prices: List[float] = Field(default_factory=list, description="Normalized prices 0-100")
    timestamps: List[int] = Field(default_factory=list, description="Unix timestamps")
    min_price: float = 0.0
    max_price: float = 100.0
    change_pct: float = 0.0


class EventDetail(BaseModel):
    """Extended event detail with all data"""
    event: ProcessedEvent
    comments: List[Comment] = Field(default_factory=list)
    sparklines: Dict[str, SparklineData] = Field(default_factory=dict, description="Market ID to sparkline")
    related_events: List[ProcessedEvent] = Field(default_factory=list)
