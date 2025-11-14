"""
Sync Configuration Models
"""

from datetime import datetime
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field, validator


class SyncTier(int, Enum):
    """Sync tier levels"""
    TIER_1 = 1  # Top 500 - Daily sync
    TIER_2 = 2  # Mid 2000 - Weekly sync
    TIER_3 = 3  # Long tail - On-demand only


class SyncFrequency(str, Enum):
    """Sync frequency options"""
    DAILY = "daily"
    WEEKLY = "weekly"
    ON_DEMAND = "on-demand"


class TickerSyncConfigCreate(BaseModel):
    """Model for creating ticker sync config"""
    ticker: str = Field(..., max_length=10)
    tier: SyncTier = Field(default=SyncTier.TIER_3)
    sync_frequency: SyncFrequency = Field(default=SyncFrequency.ON_DEMAND)
    
    # Tracking
    search_count_7d: int = Field(default=0, ge=0)
    search_count_30d: int = Field(default=0, ge=0)
    
    # Priority
    priority_score: float = Field(default=0.0, ge=0)
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    @validator('sync_frequency', always=True)
    def sync_frequency_matches_tier(cls, v, values):
        """Ensure sync frequency matches tier"""
        tier = values.get('tier')
        if tier == SyncTier.TIER_1:
            return SyncFrequency.DAILY
        elif tier == SyncTier.TIER_2:
            return SyncFrequency.WEEKLY
        else:
            return SyncFrequency.ON_DEMAND
    
    class Config:
        schema_extra = {
            "example": {
                "ticker": "AAPL",
                "tier": 1,
                "sync_frequency": "daily",
                "search_count_7d": 45,
                "search_count_30d": 187,
                "priority_score": 95.5
            }
        }


class TickerSyncConfig(TickerSyncConfigCreate):
    """Complete ticker sync configuration"""
    
    # Sync tracking
    last_synced_at: Optional[datetime] = None
    sync_count: int = Field(default=0, ge=0)
    failed_sync_count: int = Field(default=0, ge=0)
    last_error: Optional[str] = None
    
    # Search tracking
    last_searched_at: Optional[datetime] = None
    
    # Auto-promotion/demotion
    promoted_at: Optional[datetime] = None
    demoted_at: Optional[datetime] = None
    
    # Metadata
    created_at: datetime
    updated_at: datetime
    
    @property
    def needs_sync(self) -> bool:
        """Check if ticker needs sync based on frequency"""
        if self.sync_frequency == SyncFrequency.ON_DEMAND:
            return False
        
        if self.last_synced_at is None:
            return True
        
        now = datetime.now()
        hours_since_sync = (now - self.last_synced_at).total_seconds() / 3600
        
        if self.sync_frequency == SyncFrequency.DAILY:
            return hours_since_sync >= 24
        elif self.sync_frequency == SyncFrequency.WEEKLY:
            return hours_since_sync >= 168  # 7 days
        
        return False
    
    @property
    def is_popular(self) -> bool:
        """Check if ticker is popular (many searches)"""
        return self.search_count_30d >= 20
    
    @property
    def should_promote(self) -> bool:
        """Check if ticker should be promoted to higher tier"""
        if self.tier == SyncTier.TIER_1:
            return False  # Already top tier
        
        if self.tier == SyncTier.TIER_3 and self.search_count_30d >= 5:
            return True
        
        if self.tier == SyncTier.TIER_2 and self.search_count_30d >= 20:
            return True
        
        return False
    
    @property
    def should_demote(self) -> bool:
        """Check if ticker should be demoted to lower tier"""
        if self.tier == SyncTier.TIER_3:
            return False  # Already lowest tier
        
        # No searches in 30 days and last sync > 60 days ago
        if self.search_count_30d == 0:
            if self.last_synced_at is None:
                return True
            
            days_since_sync = (datetime.now() - self.last_synced_at).days
            return days_since_sync > 60
        
        return False
    
    @property
    def sync_health(self) -> str:
        """Get sync health status"""
        if self.failed_sync_count == 0:
            return "healthy"
        
        if self.sync_count == 0:
            return "failed"
        
        failure_rate = self.failed_sync_count / (self.sync_count + self.failed_sync_count)
        
        if failure_rate > 0.5:
            return "unhealthy"
        elif failure_rate > 0.2:
            return "degraded"
        else:
            return "healthy"
    
    class Config:
        orm_mode = True


class TickerSyncConfigResponse(BaseModel):
    """Response model for ticker sync config"""
    ticker: str
    tier: int
    sync_frequency: str
    
    # Status
    needs_sync: bool
    last_synced_at: Optional[datetime] = None
    sync_health: str
    
    # Popularity
    search_count_30d: int
    is_popular: bool
    priority_score: float
    
    # Recommendations
    should_promote: bool
    should_demote: bool
    
    @classmethod
    def from_model(cls, config: TickerSyncConfig) -> "TickerSyncConfigResponse":
        """Convert TickerSyncConfig to response format"""
        return cls(
            ticker=config.ticker,
            tier=config.tier,
            sync_frequency=config.sync_frequency,
            needs_sync=config.needs_sync,
            last_synced_at=config.last_synced_at,
            sync_health=config.sync_health,
            search_count_30d=config.search_count_30d,
            is_popular=config.is_popular,
            priority_score=config.priority_score,
            should_promote=config.should_promote,
            should_demote=config.should_demote
        )
    
    class Config:
        schema_extra = {
            "example": {
                "ticker": "AAPL",
                "tier": 1,
                "sync_frequency": "daily",
                "needs_sync": False,
                "last_synced_at": "2024-11-14T08:00:00Z",
                "sync_health": "healthy",
                "search_count_30d": 187,
                "is_popular": True,
                "priority_score": 95.5,
                "should_promote": False,
                "should_demote": False
            }
        }


class TierStats(BaseModel):
    """Statistics for a specific tier"""
    tier: int
    total_tickers: int
    sync_frequency: str
    tickers_needing_sync: int
    popular_tickers: int
    
    class Config:
        schema_extra = {
            "example": {
                "tier": 1,
                "total_tickers": 500,
                "sync_frequency": "daily",
                "tickers_needing_sync": 45,
                "popular_tickers": 500
            }
        }


class SyncOverview(BaseModel):
    """Overview of sync system"""
    total_tickers: int
    tier_stats: dict
    pending_syncs: int
    failed_syncs_24h: int
    last_tier_rebalance: Optional[datetime] = None
    
    class Config:
        schema_extra = {
            "example": {
                "total_tickers": 11000,
                "tier_stats": {
                    "tier_1": {"total": 500, "pending": 45},
                    "tier_2": {"total": 2000, "pending": 123},
                    "tier_3": {"total": 8500, "pending": 0}
                },
                "pending_syncs": 168,
                "failed_syncs_24h": 3,
                "last_tier_rebalance": "2024-11-07T00:00:00Z"
            }
        }

