"""
Pydantic models for Market Session and Trading Day management
"""

from datetime import datetime
from datetime import date as date_type
from datetime import time as time_type
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict

from ..enums.market_session import MarketSession


# =============================================
# MARKET HOLIDAY
# =============================================

class MarketHoliday(BaseModel):
    """Market holiday information"""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    date: date_type = Field(..., description="Holiday date")
    name: str = Field(..., description="Holiday name")
    exchange: str = Field(default="NASDAQ", description="Exchange")
    is_early_close: bool = Field(default=False, description="Is early close day")
    early_close_time: Optional[time_type] = Field(None, description="Early close time if applicable")


# =============================================
# TRADING DAY
# =============================================

class TradingDay(BaseModel):
    """
    Information about a trading day
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    date: date_type = Field(..., description="Trading date")
    is_trading_day: bool = Field(..., description="Is this a trading day")
    is_holiday: bool = Field(default=False, description="Is market holiday")
    is_early_close: bool = Field(default=False, description="Is early close")
    
    # Market hours
    pre_market_start: time_type = Field(default=time_type(4, 0), description="Pre-market start (ET)")
    market_open: time_type = Field(default=time_type(9, 30), description="Market open (ET)")
    market_close: time_type = Field(default=time_type(16, 0), description="Market close (ET)")
    post_market_end: time_type = Field(default=time_type(20, 0), description="Post-market end (ET)")
    
    # Metadata
    holiday_name: Optional[str] = Field(None, description="Holiday name if applicable")
    
    def get_current_session(self, current_time: time_type) -> MarketSession:
        """Determine current market session based on time"""
        if not self.is_trading_day:
            return MarketSession.CLOSED
        
        if current_time < self.pre_market_start:
            return MarketSession.CLOSED
        elif current_time < self.market_open:
            return MarketSession.PRE_MARKET
        elif current_time < self.market_close:
            return MarketSession.MARKET_OPEN
        elif current_time < self.post_market_end:
            return MarketSession.POST_MARKET
        else:
            return MarketSession.CLOSED
    
    def get_next_session_time(self, current_time: time_type) -> Optional[tuple[MarketSession, time_type]]:
        """Get next session and its start time"""
        if current_time < self.pre_market_start:
            return (MarketSession.PRE_MARKET, self.pre_market_start)
        elif current_time < self.market_open:
            return (MarketSession.MARKET_OPEN, self.market_open)
        elif current_time < self.market_close:
            return (MarketSession.POST_MARKET, self.market_close)
        elif current_time < self.post_market_end:
            return (MarketSession.CLOSED, self.post_market_end)
        return None


# =============================================
# SESSION CHANGE EVENT
# =============================================

class SessionChangeEvent(BaseModel):
    """
    Event emitted when market session changes
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    from_session: MarketSession = Field(..., description="Previous session")
    to_session: MarketSession = Field(..., description="New session")
    timestamp: datetime = Field(default_factory=datetime.now, description="Change timestamp")
    trading_date: date_type = Field(..., description="Trading date")
    is_new_day: bool = Field(default=False, description="Is this a new trading day")
    
    # Actions to take
    should_clear_buffers: bool = Field(default=False, description="Should clear data buffers")
    should_reload_universe: bool = Field(default=False, description="Should reload ticker universe")
    should_reset_rvol: bool = Field(default=False, description="Should reset RVOL calculations")


# =============================================
# MARKET STATUS
# =============================================

class MarketStatus(BaseModel):
    """
    Current market status snapshot
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    timestamp: datetime = Field(default_factory=datetime.now)
    current_session: MarketSession
    trading_date: date_type
    is_trading_day: bool
    is_holiday: bool = False
    holiday_name: Optional[str] = None
    
    # Session times
    pre_market_start: time_type
    market_open: time_type
    market_close: time_type
    post_market_end: time_type
    
    # Time until next session
    next_session: Optional[MarketSession] = None
    next_session_time: Optional[time_type] = None
    seconds_until_next_session: Optional[int] = None
    
    # Market info
    exchange: str = Field(default="NASDAQ")
    timezone: str = Field(default="America/New_York")


# =============================================
# SESSION STATISTICS
# =============================================

class SessionStatistics(BaseModel):
    """
    Statistics for a market session
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    session: MarketSession
    trading_date: date_type
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # Volume stats
    total_volume: int = 0
    avg_volume: Optional[float] = None
    max_volume: Optional[int] = None
    
    # Ticker stats
    total_tickers_scanned: int = 0
    total_tickers_filtered: int = 0
    unique_symbols: int = 0
    
    # Performance stats
    avg_rvol: Optional[float] = None
    max_rvol: Optional[float] = None
    avg_change_percent: Optional[float] = None
    
    # Top movers
    top_gainers: List[str] = Field(default_factory=list, max_length=10)
    top_losers: List[str] = Field(default_factory=list, max_length=10)
    highest_rvol: List[str] = Field(default_factory=list, max_length=10)


# =============================================
# SLOT INFORMATION
# =============================================

class TimeSlot(BaseModel):
    """
    Information about a time slot for RVOL calculations
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    slot_number: int = Field(..., ge=0, le=191, description="Slot number (0-191 for extended hours)")
    slot_time: time_type = Field(..., description="Slot start time")
    minutes_from_open: int = Field(..., ge=0, description="Minutes elapsed since market open")
    percent_of_day: float = Field(..., ge=0, le=1, description="Percentage of trading day complete")
    
    @classmethod
    def from_time(cls, current_time: time_type, market_open: time_type = time_type(9, 30)) -> "TimeSlot":
        """Calculate slot from current time"""
        # Calculate minutes from market open
        current_minutes = current_time.hour * 60 + current_time.minute
        open_minutes = market_open.hour * 60 + market_open.minute
        minutes_from_open = max(0, current_minutes - open_minutes)
        
        # Calculate slot (5-minute slots)
        slot_number = min(191, minutes_from_open // 5)
        
        # Calculate slot start time
        slot_start_minutes = open_minutes + (slot_number * 5)
        slot_hour = slot_start_minutes // 60
        slot_minute = slot_start_minutes % 60
        slot_time = time_type(slot_hour, slot_minute)
        
        # Calculate percent of day (960 minutes total for extended hours)
        percent_of_day = minutes_from_open / 960.0
        
        return cls(
            slot_number=slot_number,
            slot_time=slot_time,
            minutes_from_open=minutes_from_open,
            percent_of_day=min(1.0, percent_of_day)
        )

