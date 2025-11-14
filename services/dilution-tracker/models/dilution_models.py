"""
Dilution Metrics Models
"""

from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, Field, validator


class DilutionMetricsCreate(BaseModel):
    """Model for creating dilution metrics"""
    ticker: str = Field(..., max_length=10)
    calculated_at: date
    
    # Cash Runway Analysis
    current_cash: Optional[Decimal] = None
    quarterly_burn_rate: Optional[Decimal] = None
    estimated_runway_months: Optional[Decimal] = Field(None, ge=0)
    
    # Dilution Analysis
    shares_outstanding_current: Optional[int] = None
    shares_outstanding_1y_ago: Optional[int] = None
    shares_outstanding_2y_ago: Optional[int] = None
    dilution_pct_1y: Optional[Decimal] = None
    dilution_pct_2y: Optional[Decimal] = None
    
    # Financial Health
    debt_to_equity: Optional[Decimal] = None
    current_ratio: Optional[Decimal] = None
    working_capital: Optional[Decimal] = None
    
    # Risk Scores (0-100)
    overall_risk_score: Optional[int] = Field(None, ge=0, le=100)
    cash_need_score: Optional[int] = Field(None, ge=0, le=100)
    dilution_risk_score: Optional[int] = Field(None, ge=0, le=100)
    
    # Metadata
    data_quality_score: Optional[Decimal] = Field(None, ge=0, le=1)
    last_financial_date: Optional[date] = None
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    class Config:
        schema_extra = {
            "example": {
                "ticker": "AAPL",
                "calculated_at": "2024-11-14",
                "current_cash": 35000000000,
                "quarterly_burn_rate": -2000000000,
                "estimated_runway_months": 43.8,
                "shares_outstanding_current": 15204000000,
                "shares_outstanding_1y_ago": 15550000000,
                "dilution_pct_1y": -2.23,
                "overall_risk_score": 15,
                "cash_need_score": 10,
                "dilution_risk_score": 5,
                "data_quality_score": 0.95
            }
        }


class DilutionMetrics(DilutionMetricsCreate):
    """Complete dilution metrics"""
    
    @property
    def is_burning_cash(self) -> bool:
        """Check if company is burning cash"""
        return self.quarterly_burn_rate is not None and self.quarterly_burn_rate < 0
    
    @property
    def runway_risk_level(self) -> str:
        """Get runway risk level"""
        if self.estimated_runway_months is None:
            return "unknown"
        
        if self.estimated_runway_months < 6:
            return "critical"
        elif self.estimated_runway_months < 12:
            return "high"
        elif self.estimated_runway_months < 24:
            return "medium"
        else:
            return "low"
    
    @property
    def is_high_dilution_risk(self) -> bool:
        """Check if company has high dilution risk"""
        return self.overall_risk_score is not None and self.overall_risk_score >= 70
    
    class Config:
        orm_mode = True


class DilutionMetricsResponse(BaseModel):
    """Response model for dilution metrics"""
    ticker: str
    calculated_at: date
    
    # Cash Analysis
    cash_analysis: Optional[dict] = Field(None, description="Cash runway analysis")
    
    # Dilution Analysis
    dilution_analysis: Optional[dict] = Field(None, description="Historical dilution analysis")
    
    # Risk Scores
    risk_scores: Optional[dict] = Field(None, description="Risk score breakdown")
    
    # Summary
    summary: Optional[dict] = Field(None, description="Quick summary")
    
    @classmethod
    def from_model(cls, metrics: DilutionMetrics) -> "DilutionMetricsResponse":
        """Convert DilutionMetrics to response format"""
        
        # Cash analysis
        cash_analysis = None
        if metrics.current_cash is not None:
            cash_analysis = {
                "current_cash": float(metrics.current_cash),
                "quarterly_burn_rate": float(metrics.quarterly_burn_rate) if metrics.quarterly_burn_rate else None,
                "estimated_runway_months": float(metrics.estimated_runway_months) if metrics.estimated_runway_months else None,
                "is_burning_cash": metrics.is_burning_cash,
                "runway_risk_level": metrics.runway_risk_level
            }
        
        # Dilution analysis
        dilution_analysis = None
        if metrics.shares_outstanding_current is not None:
            dilution_analysis = {
                "shares_outstanding_current": metrics.shares_outstanding_current,
                "shares_outstanding_1y_ago": metrics.shares_outstanding_1y_ago,
                "dilution_pct_1y": float(metrics.dilution_pct_1y) if metrics.dilution_pct_1y else None,
                "dilution_pct_2y": float(metrics.dilution_pct_2y) if metrics.dilution_pct_2y else None,
            }
        
        # Risk scores
        risk_scores = {
            "overall_risk": metrics.overall_risk_score,
            "cash_need": metrics.cash_need_score,
            "dilution_risk": metrics.dilution_risk_score,
            "is_high_risk": metrics.is_high_dilution_risk
        }
        
        # Summary
        summary = {
            "risk_level": "high" if metrics.is_high_dilution_risk else "medium" if metrics.overall_risk_score and metrics.overall_risk_score >= 40 else "low",
            "runway_risk": metrics.runway_risk_level,
            "data_quality": float(metrics.data_quality_score) if metrics.data_quality_score else None
        }
        
        return cls(
            ticker=metrics.ticker,
            calculated_at=metrics.calculated_at,
            cash_analysis=cash_analysis,
            dilution_analysis=dilution_analysis,
            risk_scores=risk_scores,
            summary=summary
        )
    
    class Config:
        schema_extra = {
            "example": {
                "ticker": "AAPL",
                "calculated_at": "2024-11-14",
                "cash_analysis": {
                    "current_cash": 35000000000,
                    "quarterly_burn_rate": -2000000000,
                    "estimated_runway_months": 43.8,
                    "is_burning_cash": True,
                    "runway_risk_level": "low"
                },
                "dilution_analysis": {
                    "shares_outstanding_current": 15204000000,
                    "shares_outstanding_1y_ago": 15550000000,
                    "dilution_pct_1y": -2.23,
                    "dilution_pct_2y": -5.12
                },
                "risk_scores": {
                    "overall_risk": 15,
                    "cash_need": 10,
                    "dilution_risk": 5,
                    "is_high_risk": False
                },
                "summary": {
                    "risk_level": "low",
                    "runway_risk": "low",
                    "data_quality": 0.95
                }
            }
        }


class CashRunwayAnalysis(BaseModel):
    """Detailed cash runway analysis with projection"""
    ticker: str
    current_cash: float
    quarterly_burn_rate: float
    estimated_runway_months: float
    runway_risk_level: str
    
    # Projection
    projection: List[dict] = Field(..., description="Monthly cash projection")
    
    # Context
    last_financial_date: date
    calculated_at: datetime
    
    class Config:
        schema_extra = {
            "example": {
                "ticker": "AAPL",
                "current_cash": 35000000000,
                "quarterly_burn_rate": -2000000000,
                "estimated_runway_months": 43.8,
                "runway_risk_level": "low",
                "projection": [
                    {"month": 1, "date": "2024-12-31", "estimated_cash": 33000000000},
                    {"month": 2, "date": "2025-01-31", "estimated_cash": 31000000000},
                    {"month": 3, "date": "2025-02-28", "estimated_cash": 29000000000}
                ],
                "last_financial_date": "2024-09-30",
                "calculated_at": "2024-11-14T10:30:00Z"
            }
        }

