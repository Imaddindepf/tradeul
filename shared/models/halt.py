"""
Halt Event Models

Models for tracking trading halts and resumes.
Based on NYSE/NASDAQ halt codes and LULD data from Polygon.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class HaltEvent(BaseModel):
    """
    Represents a trading halt event.
    
    A halt event tracks the full lifecycle of a trading halt:
    1. Initial halt (status = HALTED)
    2. Resume (status = RESUMED)
    
    The event persists in history even after resume for audit trail.
    """
    symbol: str = Field(..., description="Ticker symbol")
    halt_time: int = Field(..., description="Halt start timestamp (Unix MS)")
    halt_reason: str = Field(..., description="Halt reason code (T1, LUDP, etc.)")
    halt_reason_desc: str = Field("", description="Human readable halt reason")
    status: str = Field(..., description="Current status: HALTED or RESUMED")
    resume_time: Optional[int] = Field(None, description="Resume timestamp (Unix MS)")
    duration_seconds: Optional[int] = Field(None, description="Halt duration in seconds")
    upper_band: Optional[float] = Field(None, description="LULD upper price band")
    lower_band: Optional[float] = Field(None, description="LULD lower price band")
    indicators: Optional[List[int]] = Field(None, description="LULD indicator codes")
    
    @property
    def halt_time_formatted(self) -> str:
        """Format halt time as HH:MM:SS"""
        if self.halt_time:
            dt = datetime.utcfromtimestamp(self.halt_time / 1000)
            return dt.strftime('%H:%M:%S')
        return ""
    
    @property
    def resume_time_formatted(self) -> Optional[str]:
        """Format resume time as HH:MM:SS"""
        if self.resume_time:
            dt = datetime.utcfromtimestamp(self.resume_time / 1000)
            return dt.strftime('%H:%M:%S')
        return None
    
    @property
    def duration_formatted(self) -> Optional[str]:
        """Format duration as MM:SS or HH:MM:SS"""
        if self.duration_seconds is None:
            return None
        
        hours = self.duration_seconds // 3600
        minutes = (self.duration_seconds % 3600) // 60
        seconds = self.duration_seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    @property
    def is_active(self) -> bool:
        """Check if halt is currently active"""
        return self.status == "HALTED"
    
    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "halt_time": 1707051323000,
                "halt_reason": "LUDP",
                "halt_reason_desc": "Volatility Trading Pause",
                "status": "HALTED",
                "resume_time": None,
                "duration_seconds": None,
                "upper_band": 185.50,
                "lower_band": 175.30,
                "indicators": [17]
            }
        }


class HaltHistory(BaseModel):
    """
    Container for halt history response.
    """
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    halts: List[HaltEvent] = Field(default_factory=list, description="List of halt events")
    stats: dict = Field(default_factory=dict, description="Statistics about halts")
    timestamp: str = Field(..., description="Response timestamp")


class ActiveHalts(BaseModel):
    """
    Container for active halts response.
    """
    halts: List[HaltEvent] = Field(default_factory=list, description="Currently active halts")
    count: int = Field(0, description="Number of active halts")
    timestamp: str = Field(..., description="Response timestamp")


# Halt reason codes (NYSE/NASDAQ standard)
HALT_REASON_CODES = {
    "T1": "News Pending",
    "T2": "News Released",
    "T3": "News and Resumption Times",
    "T5": "Single Stock Trading Pause",
    "T6": "Extraordinary Market Activity",
    "T7": "Single Stock Trading Pause/Quotation-Only",
    "T8": "ETF Halt",
    "T12": "Additional Information Requested",
    "H4": "Non-compliance",
    "H9": "Not Current",
    "H10": "SEC Trading Suspension",
    "H11": "Regulatory Concern",
    "LUDP": "Volatility Trading Pause",
    "LUDS": "Volatility Trading Pause - Straddle",
    "MWC1": "Market Wide Circuit Breaker - Level 1",
    "MWC2": "Market Wide Circuit Breaker - Level 2",
    "MWC3": "Market Wide Circuit Breaker - Level 3",
    "IPO1": "IPO Issue Not Yet Trading",
    "M1": "Corporate Action",
    "M2": "Quotation Not Available",
    "O1": "Operations Halt",
}


def get_halt_reason_description(code: str) -> str:
    """Get human readable description for halt reason code."""
    return HALT_REASON_CODES.get(code, f"Unknown ({code})")
