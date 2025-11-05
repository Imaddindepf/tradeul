"""
Market Session Enumerations
"""

from enum import Enum


class MarketSession(str, Enum):
    """
    Market session states
    Times in Eastern Time (ET)
    """
    PRE_MARKET = "PRE_MARKET"      # 4:00 AM - 9:30 AM ET
    MARKET_OPEN = "MARKET_OPEN"    # 9:30 AM - 4:00 PM ET
    POST_MARKET = "POST_MARKET"    # 4:00 PM - 8:00 PM ET
    CLOSED = "CLOSED"              # 8:00 PM - 4:00 AM ET (next day)
    
    def __str__(self) -> str:
        return self.value
    
    def is_trading_hours(self) -> bool:
        """Check if session is during regular trading hours"""
        return self == MarketSession.MARKET_OPEN
    
    def is_extended_hours(self) -> bool:
        """Check if session is during extended hours (pre/post market)"""
        return self in (MarketSession.PRE_MARKET, MarketSession.POST_MARKET)
    
    def is_market_active(self) -> bool:
        """Check if market is active (any session except closed)"""
        return self != MarketSession.CLOSED
    
    @classmethod
    def from_time_et(cls, hour: int, minute: int = 0) -> "MarketSession":
        """
        Determine session from ET time
        
        Args:
            hour: Hour in 24-hour format (0-23)
            minute: Minute (0-59)
        
        Returns:
            MarketSession enum
        """
        time_minutes = hour * 60 + minute
        
        # 4:00 AM = 240 minutes
        pre_market_start = 4 * 60  # 240
        # 9:30 AM = 570 minutes
        market_open = 9 * 60 + 30  # 570
        # 4:00 PM = 960 minutes
        market_close = 16 * 60  # 960
        # 8:00 PM = 1200 minutes
        post_market_end = 20 * 60  # 1200
        
        if pre_market_start <= time_minutes < market_open:
            return cls.PRE_MARKET
        elif market_open <= time_minutes < market_close:
            return cls.MARKET_OPEN
        elif market_close <= time_minutes < post_market_end:
            return cls.POST_MARKET
        else:
            return cls.CLOSED
    
    def get_display_name(self) -> str:
        """Get human-readable session name"""
        names = {
            MarketSession.PRE_MARKET: "Pre-Market",
            MarketSession.MARKET_OPEN: "Market Open",
            MarketSession.POST_MARKET: "Post-Market",
            MarketSession.CLOSED: "Market Closed",
        }
        return names.get(self, self.value)
    
    def get_time_range(self) -> tuple[str, str]:
        """Get time range for this session"""
        ranges = {
            MarketSession.PRE_MARKET: ("04:00", "09:30"),
            MarketSession.MARKET_OPEN: ("09:30", "16:00"),
            MarketSession.POST_MARKET: ("16:00", "20:00"),
            MarketSession.CLOSED: ("20:00", "04:00"),
        }
        return ranges.get(self, ("--:--", "--:--"))

