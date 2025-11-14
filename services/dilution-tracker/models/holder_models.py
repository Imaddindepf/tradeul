"""
Institutional Holder Models
"""

from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, Field, validator


class InstitutionalHolderCreate(BaseModel):
    """Model for creating institutional holder record"""
    ticker: str = Field(..., max_length=10)
    holder_name: str = Field(..., max_length=300)
    report_date: date
    
    # Position data
    shares_held: Optional[int] = None
    position_value: Optional[Decimal] = None
    ownership_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    
    # Change vs previous report
    position_change: Optional[int] = None
    position_change_percent: Optional[Decimal] = None
    
    # Filing info
    filing_date: Optional[date] = None
    form_type: str = Field(default="13F", max_length=10)
    
    # Metadata
    cik: Optional[str] = Field(None, max_length=20)
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    class Config:
        schema_extra = {
            "example": {
                "ticker": "AAPL",
                "holder_name": "Vanguard Group Inc",
                "report_date": "2024-09-30",
                "shares_held": 1_268_900_000,
                "position_value": 227_200_000_000,
                "ownership_percent": 8.35,
                "position_change": 5_600_000,
                "position_change_percent": 0.44,
                "filing_date": "2024-11-14",
                "form_type": "13F-HR"
            }
        }


class InstitutionalHolder(InstitutionalHolderCreate):
    """Complete institutional holder with metadata"""
    fetched_at: datetime
    
    @property
    def is_increase(self) -> bool:
        """Check if position increased"""
        return self.position_change is not None and self.position_change > 0
    
    @property
    def is_decrease(self) -> bool:
        """Check if position decreased"""
        return self.position_change is not None and self.position_change < 0
    
    @property
    def is_new_position(self) -> bool:
        """Check if this is a new position"""
        return self.position_change == self.shares_held
    
    class Config:
        orm_mode = True


class InstitutionalHolderResponse(BaseModel):
    """Response model for institutional holder"""
    holder_name: str
    shares_held: Optional[int] = None
    ownership_percent: Optional[float] = None
    position_value: Optional[float] = None
    
    # Change indicators
    position_change: Optional[int] = None
    position_change_percent: Optional[float] = None
    change_direction: Optional[str] = Field(None, description="increase|decrease|new|unchanged")
    
    # Filing info
    report_date: date
    filing_date: Optional[date] = None
    form_type: str
    
    @classmethod
    def from_model(cls, holder: InstitutionalHolder) -> "InstitutionalHolderResponse":
        """Convert InstitutionalHolder to response format"""
        # Determine change direction
        change_direction = None
        if holder.position_change is not None:
            if holder.is_new_position:
                change_direction = "new"
            elif holder.is_increase:
                change_direction = "increase"
            elif holder.is_decrease:
                change_direction = "decrease"
            else:
                change_direction = "unchanged"
        
        return cls(
            holder_name=holder.holder_name,
            shares_held=holder.shares_held,
            ownership_percent=float(holder.ownership_percent) if holder.ownership_percent else None,
            position_value=float(holder.position_value) if holder.position_value else None,
            position_change=holder.position_change,
            position_change_percent=float(holder.position_change_percent) if holder.position_change_percent else None,
            change_direction=change_direction,
            report_date=holder.report_date,
            filing_date=holder.filing_date,
            form_type=holder.form_type
        )
    
    class Config:
        schema_extra = {
            "example": {
                "holder_name": "Vanguard Group Inc",
                "shares_held": 1268900000,
                "ownership_percent": 8.35,
                "position_value": 227200000000,
                "position_change": 5600000,
                "position_change_percent": 0.44,
                "change_direction": "increase",
                "report_date": "2024-09-30",
                "filing_date": "2024-11-14",
                "form_type": "13F-HR"
            }
        }


class HoldersResponse(BaseModel):
    """Response model for list of holders"""
    ticker: str
    total_holders: int
    total_institutional_ownership: Optional[float] = Field(
        None,
        description="Total institutional ownership percentage"
    )
    last_report_date: Optional[date] = None
    holders: List[InstitutionalHolderResponse]
    
    class Config:
        schema_extra = {
            "example": {
                "ticker": "AAPL",
                "total_holders": 35,
                "total_institutional_ownership": 63.5,
                "last_report_date": "2024-09-30",
                "holders": [
                    {
                        "holder_name": "Vanguard Group Inc",
                        "shares_held": 1268900000,
                        "ownership_percent": 8.35,
                        "position_change": 5600000,
                        "change_direction": "increase",
                        "report_date": "2024-09-30",
                        "form_type": "13F-HR"
                    }
                ]
            }
        }

