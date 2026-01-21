"""
Polymarket API Response Models
Raw data models matching the Gamma and CLOB API responses
"""

from typing import Optional, List, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
import json


class PolymarketTag(BaseModel):
    """Tag/category from Polymarket"""
    id: str
    label: str
    slug: str
    force_show: Optional[bool] = Field(default=None, alias="forceShow")
    force_hide: Optional[bool] = Field(default=None, alias="forceHide")
    
    class Config:
        populate_by_name = True


class PolymarketMarket(BaseModel):
    """Individual market within an event"""
    id: str
    question: Optional[str] = None
    slug: Optional[str] = None
    outcomes: Optional[Union[List[str], str]] = None
    outcome_prices: Optional[Union[List[str], str]] = Field(default=None, alias="outcomePrices")
    volume: Optional[str] = None
    liquidity: Optional[str] = None
    active: Optional[bool] = None
    closed: Optional[bool] = None
    end_date: Optional[datetime] = Field(default=None, alias="endDate")
    clob_token_ids: Optional[Union[List[str], str]] = Field(default=None, alias="clobTokenIds")
    
    # Price change fields (if available from API)
    one_day_price_change: Optional[float] = Field(default=None, alias="oneDayPriceChange")
    one_week_price_change: Optional[float] = Field(default=None, alias="oneWeekPriceChange")
    one_month_price_change: Optional[float] = Field(default=None, alias="oneMonthPriceChange")
    
    class Config:
        populate_by_name = True
    
    @field_validator('outcomes', 'outcome_prices', 'clob_token_ids', mode='before')
    @classmethod
    def parse_json_string(cls, v: Any) -> Any:
        """Parse JSON string to list if needed"""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v
    
    def parse_outcomes(self) -> List[str]:
        """Get outcomes as list"""
        if not self.outcomes:
            return []
        if isinstance(self.outcomes, list):
            return self.outcomes
        return []
    
    def parse_outcome_prices(self) -> List[float]:
        """Get outcome prices as list of floats"""
        if not self.outcome_prices:
            return []
        if isinstance(self.outcome_prices, list):
            try:
                return [float(p) for p in self.outcome_prices]
            except (ValueError, TypeError):
                return []
        return []
    
    def parse_clob_token_ids(self) -> List[str]:
        """Get CLOB token IDs as list"""
        if not self.clob_token_ids:
            return []
        if isinstance(self.clob_token_ids, list):
            return self.clob_token_ids
        return []
    
    def get_yes_probability(self) -> Optional[float]:
        """Get probability of YES outcome (first outcome)"""
        prices = self.parse_outcome_prices()
        if prices and len(prices) >= 1:
            return prices[0]
        return None
    
    def get_yes_token_id(self) -> Optional[str]:
        """Get CLOB token ID for YES outcome"""
        ids = self.parse_clob_token_ids()
        if ids and len(ids) >= 1:
            return ids[0]
        return None


class PolymarketEvent(BaseModel):
    """Event from Polymarket Gamma API"""
    id: str
    title: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    
    # Volume metrics
    volume: Optional[float] = None
    volume_24hr: Optional[float] = Field(default=None, alias="volume24hr")
    volume_1wk: Optional[float] = Field(default=None, alias="volume1wk")
    volume_1mo: Optional[float] = Field(default=None, alias="volume1mo")
    
    liquidity: Optional[float] = None
    open_interest: Optional[float] = Field(default=None, alias="openInterest")
    
    # Status
    active: Optional[bool] = None
    closed: Optional[bool] = None
    archived: Optional[bool] = None
    featured: Optional[bool] = None
    
    # Dates
    start_date: Optional[datetime] = Field(default=None, alias="startDate")
    end_date: Optional[datetime] = Field(default=None, alias="endDate")
    created_at: Optional[datetime] = Field(default=None, alias="createdAt")
    updated_at: Optional[datetime] = Field(default=None, alias="updatedAt")
    
    # Related data
    tags: Optional[List[PolymarketTag]] = None
    markets: Optional[List[PolymarketMarket]] = None
    
    class Config:
        populate_by_name = True
    
    def get_tag_labels(self) -> List[str]:
        """Get list of tag labels"""
        if not self.tags:
            return []
        return [tag.label for tag in self.tags if tag.label]
    
    def get_tag_slugs(self) -> List[str]:
        """Get list of tag slugs"""
        if not self.tags:
            return []
        return [tag.slug for tag in self.tags if tag.slug]


class PricePoint(BaseModel):
    """Single price point in history"""
    timestamp: int = Field(alias="t")
    price: float = Field(alias="p")
    
    class Config:
        populate_by_name = True
    
    def get_datetime(self) -> datetime:
        """Convert timestamp to datetime"""
        return datetime.fromtimestamp(self.timestamp)


class PriceHistory(BaseModel):
    """Price history response from CLOB API"""
    history: List[PricePoint] = Field(default_factory=list)
    
    def get_price_at_days_ago(self, days: int) -> Optional[float]:
        """Get price approximately N days ago"""
        if not self.history:
            return None
        
        target_ts = datetime.now().timestamp() - (days * 86400)
        
        # Find closest price point
        closest = None
        min_diff = float('inf')
        
        for point in self.history:
            diff = abs(point.timestamp - target_ts)
            if diff < min_diff:
                min_diff = diff
                closest = point
        
        return closest.price if closest else None
    
    def get_current_price(self) -> Optional[float]:
        """Get most recent price"""
        if not self.history:
            return None
        return max(self.history, key=lambda p: p.timestamp).price
    
    def get_min_price(self) -> Optional[float]:
        """Get minimum price in history"""
        if not self.history:
            return None
        return min(p.price for p in self.history)
    
    def get_max_price(self) -> Optional[float]:
        """Get maximum price in history"""
        if not self.history:
            return None
        return max(p.price for p in self.history)
