"""
Watchlist Models for Quote Monitor
Supports multi-watchlist with tabs, real-time quotes, and user persistence
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class WatchlistColumn(str, Enum):
    """Available columns for watchlist display"""
    TICKER = "ticker"
    LAST = "last"
    BID = "bid"
    ASK = "ask"
    CHANGE = "change"
    CHANGE_PERCENT = "change_percent"
    VOLUME = "volume"
    AVG_VOLUME = "avg_volume"
    MARKET_CAP = "market_cap"
    PE_RATIO = "pe_ratio"
    DAY_HIGH = "day_high"
    DAY_LOW = "day_low"
    WEEK_CHANGE = "week_change"
    MONTH_CHANGE = "month_change"
    YTD_CHANGE = "ytd_change"
    LATENCY = "latency"
    SPARKLINE = "sparkline"
    NOTES = "notes"


class WatchlistTicker(BaseModel):
    """A ticker entry in a watchlist"""
    symbol: str
    exchange: str = "US"
    section_id: Optional[str] = None  # NULL = sin sección (unsorted)
    added_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None
    alert_price_above: Optional[float] = None
    alert_price_below: Optional[float] = None
    alert_change_percent: Optional[float] = None
    position_size: Optional[float] = None  # For synthetic ETF
    weight: Optional[float] = None  # Weight in synthetic ETF (0-100)
    tags: List[str] = Field(default_factory=list)
    position: int = 0  # Orden dentro de la sección
    
    class Config:
        from_attributes = True


class WatchlistTickerCreate(BaseModel):
    """Create a new ticker in watchlist"""
    symbol: str
    exchange: str = "US"
    section_id: Optional[str] = None  # NULL = añadir al final sin sección
    notes: Optional[str] = None
    weight: Optional[float] = None
    tags: List[str] = Field(default_factory=list)


class WatchlistTickerUpdate(BaseModel):
    """Update a ticker in watchlist"""
    section_id: Optional[str] = None  # Mover a otra sección
    notes: Optional[str] = None
    alert_price_above: Optional[float] = None
    alert_price_below: Optional[float] = None
    alert_change_percent: Optional[float] = None
    position_size: Optional[float] = None
    weight: Optional[float] = None
    tags: Optional[List[str]] = None
    position: Optional[int] = None  # Reordenar dentro de la sección


# ============================================================================
# Section Models
# ============================================================================

class WatchlistSection(BaseModel):
    """A section/category within a watchlist for organizing tickers"""
    id: str
    watchlist_id: str
    name: str
    color: Optional[str] = None  # Badge color
    icon: Optional[str] = None  # Lucide icon name
    is_collapsed: bool = False  # UI state
    position: int = 0  # Order within watchlist
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    tickers: List[WatchlistTicker] = Field(default_factory=list)
    
    class Config:
        from_attributes = True


class WatchlistSectionCreate(BaseModel):
    """Create a new section in watchlist"""
    name: str
    color: Optional[str] = None
    icon: Optional[str] = None


class WatchlistSectionUpdate(BaseModel):
    """Update a section"""
    name: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_collapsed: Optional[bool] = None
    position: Optional[int] = None


class WatchlistSectionReorder(BaseModel):
    """Reorder sections within a watchlist"""
    section_ids: List[str]  # Ordered list of section IDs


class TickerMoveToSection(BaseModel):
    """Move ticker(s) to a section"""
    symbols: List[str]
    target_section_id: Optional[str] = None  # NULL = unsorted/no section


class Watchlist(BaseModel):
    """A watchlist/tab in the Quote Monitor"""
    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    color: Optional[str] = None  # Tab color
    icon: Optional[str] = None  # Tab icon
    is_synthetic_etf: bool = False  # If true, show aggregate performance
    columns: List[WatchlistColumn] = Field(
        default_factory=lambda: [
            WatchlistColumn.TICKER,
            WatchlistColumn.LAST,
            WatchlistColumn.BID,
            WatchlistColumn.ASK,
            WatchlistColumn.CHANGE_PERCENT,
            WatchlistColumn.VOLUME,
            WatchlistColumn.LATENCY,
        ]
    )
    sections: List["WatchlistSection"] = Field(default_factory=list)  # Secciones ordenadas
    tickers: List[WatchlistTicker] = Field(default_factory=list)  # Tickers sin sección (unsorted)
    sort_by: Optional[str] = None
    sort_order: str = "asc"
    position: int = 0  # Tab order
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        from_attributes = True


class WatchlistCreate(BaseModel):
    """Create a new watchlist"""
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_synthetic_etf: bool = False
    columns: Optional[List[WatchlistColumn]] = None


class WatchlistUpdate(BaseModel):
    """Update a watchlist"""
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_synthetic_etf: Optional[bool] = None
    columns: Optional[List[WatchlistColumn]] = None
    sort_by: Optional[str] = None
    sort_order: Optional[str] = None
    position: Optional[int] = None


class WatchlistReorder(BaseModel):
    """Reorder watchlist tabs"""
    watchlist_ids: List[str]  # Ordered list of watchlist IDs


class WatchlistWithQuotes(BaseModel):
    """Watchlist with real-time quote data"""
    watchlist: Watchlist
    quotes: Dict[str, Dict[str, Any]]  # symbol -> quote data
    aggregate: Optional[Dict[str, Any]] = None  # Synthetic ETF aggregate stats


class QuoteMonitorState(BaseModel):
    """Full state of the Quote Monitor for a user"""
    user_id: str
    watchlists: List[Watchlist]
    active_watchlist_id: Optional[str] = None
    settings: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Database Row Models (for asyncpg)
# ============================================================================

class WatchlistRow(BaseModel):
    """Database row for watchlist table"""
    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_synthetic_etf: bool = False
    columns: List[str] = Field(default_factory=list)
    sort_by: Optional[str] = None
    sort_order: str = "asc"
    position: int = 0
    created_at: datetime
    updated_at: datetime


class WatchlistTickerRow(BaseModel):
    """Database row for watchlist_ticker table"""
    id: str
    watchlist_id: str
    symbol: str
    exchange: str = "US"
    section_id: Optional[str] = None
    notes: Optional[str] = None
    alert_price_above: Optional[float] = None
    alert_price_below: Optional[float] = None
    alert_change_percent: Optional[float] = None
    position_size: Optional[float] = None
    weight: Optional[float] = None
    tags: List[str] = Field(default_factory=list)
    position: int = 0
    added_at: datetime


class WatchlistSectionRow(BaseModel):
    """Database row for watchlist_section table"""
    id: str
    watchlist_id: str
    name: str
    color: Optional[str] = None
    icon: Optional[str] = None
    is_collapsed: bool = False
    position: int = 0
    created_at: datetime
    updated_at: datetime


# Resolve forward references
Watchlist.model_rebuild()
WatchlistSection.model_rebuild()

