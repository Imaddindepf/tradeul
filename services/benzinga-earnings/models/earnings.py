"""
Benzinga Earnings Models

Data models for earnings announcements from Polygon/Benzinga API.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class BenzingaEarning(BaseModel):
    """
    Earnings announcement from Benzinga API.
    
    Maps to Polygon's /benzinga/v1/earnings endpoint response.
    """
    
    # Identifiers
    benzinga_id: str = Field(..., description="Unique Benzinga identifier")
    ticker: str = Field(..., description="Stock ticker symbol")
    company_name: Optional[str] = Field(None, description="Company name")
    
    # Date/Time
    date: str = Field(..., description="Earnings date (YYYY-MM-DD)")
    time: Optional[str] = Field(None, description="Time of announcement (HH:MM:SS UTC)")
    date_status: Optional[str] = Field(None, description="confirmed or projected")
    
    # Fiscal period
    fiscal_year: Optional[int] = Field(None, description="Fiscal year")
    fiscal_period: Optional[str] = Field(None, description="Q1, Q2, Q3, Q4, H1, FY")
    
    # EPS data
    estimated_eps: Optional[float] = Field(None, description="Analyst EPS estimate")
    actual_eps: Optional[float] = Field(None, description="Actual reported EPS")
    eps_surprise: Optional[float] = Field(None, description="EPS surprise (actual - estimate)")
    eps_surprise_percent: Optional[float] = Field(None, description="EPS surprise percentage")
    eps_method: Optional[str] = Field(None, description="gaap, adj, or ffo")
    previous_eps: Optional[float] = Field(None, description="Previous period EPS")
    
    # Revenue data
    estimated_revenue: Optional[float] = Field(None, description="Analyst revenue estimate")
    actual_revenue: Optional[float] = Field(None, description="Actual reported revenue")
    revenue_surprise: Optional[float] = Field(None, description="Revenue surprise")
    revenue_surprise_percent: Optional[float] = Field(None, description="Revenue surprise percentage")
    revenue_method: Optional[str] = Field(None, description="gaap, adj, or rental")
    previous_revenue: Optional[float] = Field(None, description="Previous period revenue")
    
    # Additional info
    currency: Optional[str] = Field(None, description="Currency code (USD, EUR, etc)")
    importance: Optional[int] = Field(None, description="Importance score 0-5")
    notes: Optional[str] = Field(None, description="Additional notes")
    
    # Metadata
    last_updated: Optional[str] = Field(None, description="Last update timestamp")
    
    @classmethod
    def from_polygon_response(cls, data: Dict[str, Any]) -> "BenzingaEarning":
        """
        Create BenzingaEarning from Polygon API response.
        
        Args:
            data: Raw response from Polygon /benzinga/v1/earnings
            
        Returns:
            BenzingaEarning instance
        """
        return cls(
            benzinga_id=data.get("benzinga_id", str(hash(f"{data.get('ticker')}-{data.get('date')}"))),
            ticker=data.get("ticker", ""),
            company_name=data.get("company_name"),
            date=data.get("date", ""),
            time=data.get("time"),
            date_status=data.get("date_status"),
            fiscal_year=data.get("fiscal_year"),
            fiscal_period=data.get("fiscal_period"),
            estimated_eps=data.get("estimated_eps"),
            actual_eps=data.get("actual_eps"),
            eps_surprise=data.get("eps_surprise"),
            eps_surprise_percent=data.get("eps_surprise_percent"),
            eps_method=data.get("eps_method"),
            previous_eps=data.get("previous_eps"),
            estimated_revenue=data.get("estimated_revenue"),
            actual_revenue=data.get("actual_revenue"),
            revenue_surprise=data.get("revenue_surprise"),
            revenue_surprise_percent=data.get("revenue_surprise_percent"),
            revenue_method=data.get("revenue_method"),
            previous_revenue=data.get("previous_revenue"),
            currency=data.get("currency"),
            importance=data.get("importance"),
            notes=data.get("notes"),
            last_updated=data.get("last_updated")
        )
    
    def to_db_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "benzinga_id": self.benzinga_id,
            "symbol": self.ticker,
            "company_name": self.company_name,
            "report_date": self.date,
            "time_slot": self._derive_time_slot(),
            "fiscal_quarter": self.fiscal_period,
            "fiscal_year": self.fiscal_year,
            "eps_estimate": self.estimated_eps,
            "eps_actual": self.actual_eps,
            "eps_surprise_pct": self.eps_surprise_percent,
            "beat_eps": self._beat_eps(),
            "revenue_estimate": self.estimated_revenue,
            "revenue_actual": self.actual_revenue,
            "revenue_surprise_pct": self.revenue_surprise_percent,
            "beat_revenue": self._beat_revenue(),
            "status": "reported" if self.actual_eps is not None else "scheduled",
            "importance": self.importance,
            "date_status": self.date_status,
            "eps_method": self.eps_method,
            "revenue_method": self.revenue_method,
            "previous_eps": self.previous_eps,
            "previous_revenue": self.previous_revenue,
            "notes": self.notes,
            "source": "benzinga"
        }
    
    def _derive_time_slot(self) -> str:
        """Derive time slot (BMO/AMC/TBD) from time field.
        
        Benzinga times are in Eastern Time (ET):
        - BMO (Before Market Open): before 9:30 AM ET
        - AMC (After Market Close): after 4:00 PM ET (16:00)
        - DURING: between 9:30 AM and 4:00 PM ET
        """
        if not self.time:
            return "TBD"
        try:
            parts = self.time.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            
            # Times are in ET local time
            if hour < 9 or (hour == 9 and minute < 30):
                return "BMO"
            elif hour >= 16:
                return "AMC"
            else:
                return "DURING"
        except:
            return "TBD"
    
    def _beat_eps(self) -> Optional[bool]:
        """Determine if EPS beat estimates."""
        if self.actual_eps is None or self.estimated_eps is None:
            return None
        return self.actual_eps >= self.estimated_eps
    
    def _beat_revenue(self) -> Optional[bool]:
        """Determine if revenue beat estimates."""
        if self.actual_revenue is None or self.estimated_revenue is None:
            return None
        return self.actual_revenue >= self.estimated_revenue


class EarningsFilterParams(BaseModel):
    """Parameters for filtering earnings queries."""
    
    ticker: Optional[str] = Field(None, description="Filter by ticker")
    date: Optional[str] = Field(None, description="Filter by date (YYYY-MM-DD)")
    date_gte: Optional[str] = Field(None, description="Date greater than or equal")
    date_lte: Optional[str] = Field(None, description="Date less than or equal")
    importance_gte: Optional[int] = Field(None, description="Minimum importance (0-5)")
    date_status: Optional[str] = Field(None, description="confirmed or projected")
    fiscal_period: Optional[str] = Field(None, description="Q1, Q2, Q3, Q4")
    limit: int = Field(default=100, description="Max results")
    sort: str = Field(default="date.desc", description="Sort order")
