"""Response schemas"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import date


class ScreenerResult(BaseModel):
    """A single screener result"""
    
    symbol: str
    date: date
    price: float
    volume: int
    change_1d: Optional[float] = None
    change_5d: Optional[float] = None
    change_20d: Optional[float] = None
    gap_percent: Optional[float] = None
    relative_volume: Optional[float] = None
    rsi_14: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    atr_percent: Optional[float] = None
    bb_position: Optional[float] = None
    # Add more fields as needed


class ScreenerResponse(BaseModel):
    """Screener response"""
    
    status: str = Field(..., description="'ok' or 'error'")
    results: List[Dict[str, Any]] = Field(default=[], description="List of matching stocks")
    count: int = Field(default=0, description="Number of results returned")
    total_matched: Optional[int] = Field(None, description="Total matching (before limit)")
    query_time_ms: float = Field(default=0, description="Query execution time in milliseconds")
    filters_applied: Optional[int] = Field(None, description="Number of filters applied")
    dynamic_indicators: Optional[int] = Field(None, description="Number of dynamic indicator calculations")
    errors: Optional[List[str]] = Field(None, description="Error messages if status is 'error'")


class IndicatorInfo(BaseModel):
    """Information about a single indicator"""
    
    name: str
    display_name: str
    description: str
    data_type: str
    operators: List[str]
    min_value: Optional[float] = None
    max_value: Optional[float] = None


class IndicatorsResponse(BaseModel):
    """Response listing all available indicators"""
    
    categories: Dict[str, List[IndicatorInfo]]
    total_count: int


class EngineStats(BaseModel):
    """Engine statistics"""
    
    symbols_count: int
    date_range: Dict[str, Optional[str]]
    indicators_count: int


class HealthResponse(BaseModel):
    """Health check response"""
    
    status: str
    service: str
    version: str
    stats: Optional[EngineStats] = None

