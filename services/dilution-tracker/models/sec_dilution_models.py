"""
SEC Dilution Profile Models
Models para warrants, ATM offerings, shelf registrations y completed offerings
"""

from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, Field, validator


class WarrantModel(BaseModel):
    """Model for warrant data"""
    id: Optional[int] = None
    ticker: str = Field(..., max_length=10)
    issue_date: Optional[date] = None
    outstanding: Optional[int] = Field(None, description="Number of warrants outstanding")
    exercise_price: Optional[Decimal] = Field(None, description="Exercise/strike price")
    expiration_date: Optional[date] = None
    potential_new_shares: Optional[int] = Field(None, description="Potential shares if all warrants exercised")
    notes: Optional[str] = None
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "SOUN",
                "issue_date": "2023-05-15",
                "outstanding": 15000000,
                "exercise_price": 11.50,
                "expiration_date": "2028-05-15",
                "potential_new_shares": 15000000,
                "notes": "Public warrants, cashless exercise permitted"
            }
        }


class ATMOfferingModel(BaseModel):
    """Model for At-The-Market offering data"""
    id: Optional[int] = None
    ticker: str = Field(..., max_length=10)
    total_capacity: Optional[Decimal] = Field(None, description="Total ATM capacity in dollars")
    remaining_capacity: Optional[Decimal] = Field(None, description="Remaining capacity in dollars")
    placement_agent: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = Field(None, max_length=50, description="Active, Terminated, Replaced, etc.")
    agreement_start_date: Optional[date] = None
    filing_date: Optional[date] = None
    filing_url: Optional[str] = None
    potential_shares_at_current_price: Optional[int] = None
    notes: Optional[str] = None
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "SOUN",
                "total_capacity": 100000000.00,
                "remaining_capacity": 75000000.00,
                "placement_agent": "B. Riley Securities",
                "filing_date": "2024-06-20",
                "potential_shares_at_current_price": 25000000
            }
        }


class ShelfRegistrationModel(BaseModel):
    """Model for shelf registration data"""
    id: Optional[int] = None
    ticker: str = Field(..., max_length=10)
    total_capacity: Optional[Decimal] = Field(None, description="Total shelf capacity in dollars")
    remaining_capacity: Optional[Decimal] = Field(None, description="Remaining capacity in dollars")
    current_raisable_amount: Optional[Decimal] = Field(None, description="Current amount that can be raised")
    total_amount_raised: Optional[Decimal] = Field(None, description="Total amount raised from this shelf")
    total_amount_raised_last_12mo: Optional[Decimal] = Field(None, description="Total raised in last 12 months under IB6")
    is_baby_shelf: Optional[bool] = Field(default=False, description="Is this a baby shelf (<$75M)?")
    baby_shelf_restriction: Optional[bool] = Field(None, description="Is baby shelf restriction active?")
    security_type: Optional[str] = Field(None, max_length=50, description="Type of security: 'common_stock', 'preferred_stock', 'mixed', or null if unknown")
    filing_date: Optional[date] = None
    effect_date: Optional[date] = None
    registration_statement: Optional[str] = Field(None, max_length=50, description="e.g., S-3, S-1, S-11")
    filing_url: Optional[str] = None
    expiration_date: Optional[date] = Field(None, description="Shelf expiration (typically 3 years)")
    last_banker: Optional[str] = Field(None, max_length=255, description="Last investment banker used")
    notes: Optional[str] = None
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    @validator('is_baby_shelf', pre=True)
    def validate_baby_shelf(cls, v):
        if v is None:
            return False
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "SOUN",
                "total_capacity": 200000000.00,
                "remaining_capacity": 150000000.00,
                "is_baby_shelf": False,
                "filing_date": "2023-08-10",
                "registration_statement": "S-3",
                "expiration_date": "2026-08-10"
            }
        }


class CompletedOfferingModel(BaseModel):
    """Model for completed offering data"""
    id: Optional[int] = None
    ticker: str = Field(..., max_length=10)
    offering_type: Optional[str] = Field(None, max_length=50, description="Direct Offering, PIPE, Registered Direct, etc.")
    shares_issued: Optional[int] = Field(None, description="Number of shares issued")
    price_per_share: Optional[Decimal] = Field(None, description="Offering price per share")
    amount_raised: Optional[Decimal] = Field(None, description="Total amount raised")
    offering_date: Optional[date] = None
    filing_url: Optional[str] = None
    notes: Optional[str] = None
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "SOUN",
                "offering_type": "Registered Direct Offering",
                "shares_issued": 5000000,
                "price_per_share": 3.50,
                "amount_raised": 17500000.00,
                "offering_date": "2024-09-15",
                "notes": "Includes warrant coverage"
            }
        }


class S1OfferingModel(BaseModel):
    """Model for S-1 offerings with detailed information"""
    id: Optional[int] = None
    ticker: str = Field(..., max_length=10)
    anticipated_deal_size: Optional[Decimal] = Field(None, description="Anticipated deal size")
    final_deal_size: Optional[Decimal] = Field(None, description="Final deal size raised")
    final_pricing: Optional[Decimal] = Field(None, description="Final offering price per share")
    final_shares_offered: Optional[int] = Field(None, description="Final shares offered")
    warrant_coverage: Optional[Decimal] = Field(None, description="Warrant coverage percentage")
    final_warrant_coverage: Optional[Decimal] = Field(None, description="Final warrant coverage percentage")
    exercise_price: Optional[Decimal] = Field(None, description="Warrant exercise price")
    underwriter_agent: Optional[str] = Field(None, max_length=255, description="Underwriter/Placement Agent")
    s1_filing_date: Optional[date] = None
    status: Optional[str] = Field(None, max_length=50, description="Priced, Registered, etc.")
    filing_url: Optional[str] = None
    last_update_date: Optional[date] = None
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v


class ConvertibleNoteModel(BaseModel):
    """Model for convertible notes/debt"""
    id: Optional[int] = None
    ticker: str = Field(..., max_length=10)
    total_principal_amount: Optional[Decimal] = Field(None, description="Total principal amount")
    remaining_principal_amount: Optional[Decimal] = Field(None, description="Remaining principal amount")
    conversion_price: Optional[Decimal] = Field(None, description="Conversion price per share")
    total_shares_when_converted: Optional[int] = Field(None, description="Total shares if fully converted")
    remaining_shares_when_converted: Optional[int] = Field(None, description="Remaining shares to be issued")
    issue_date: Optional[date] = None
    convertible_date: Optional[date] = None
    maturity_date: Optional[date] = None
    underwriter_agent: Optional[str] = Field(None, max_length=255)
    filing_url: Optional[str] = None
    notes: Optional[str] = None
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v


class ConvertiblePreferredModel(BaseModel):
    """Model for convertible preferred stock"""
    id: Optional[int] = None
    ticker: str = Field(..., max_length=10)
    series: Optional[str] = Field(None, max_length=50, description="Series A, B, C, etc.")
    total_dollar_amount_issued: Optional[Decimal] = Field(None, description="Total dollar amount issued")
    remaining_dollar_amount: Optional[Decimal] = Field(None, description="Remaining dollar amount")
    conversion_price: Optional[Decimal] = Field(None, description="Conversion price per share")
    total_shares_when_converted: Optional[int] = Field(None, description="Total shares if fully converted")
    remaining_shares_when_converted: Optional[int] = Field(None, description="Remaining shares to be issued")
    issue_date: Optional[date] = None
    convertible_date: Optional[date] = None
    maturity_date: Optional[date] = None
    underwriter_agent: Optional[str] = Field(None, max_length=255)
    filing_url: Optional[str] = None
    notes: Optional[str] = None
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v


class EquityLineModel(BaseModel):
    """Model for Equity Line of Credit (ELOC)"""
    id: Optional[int] = None
    ticker: str = Field(..., max_length=10)
    total_capacity: Optional[Decimal] = Field(None, description="Total equity line capacity")
    remaining_capacity: Optional[Decimal] = Field(None, description="Remaining capacity")
    agreement_start_date: Optional[date] = None
    agreement_end_date: Optional[date] = None
    filing_url: Optional[str] = None
    notes: Optional[str] = None
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v


class DilutionProfileMetadata(BaseModel):
    """Metadata about the dilution profile scrape"""
    ticker: str
    cik: Optional[str] = None
    company_name: Optional[str] = None
    last_scraped_at: datetime
    source_filings: List[dict] = Field(default_factory=list, description="List of SEC filings used")
    scrape_success: bool = True
    scrape_error: Optional[str] = None


class SECDilutionProfile(BaseModel):
    """Complete SEC dilution profile for a ticker"""
    ticker: str
    company_name: Optional[str] = None
    cik: Optional[str] = None
    
    # Core dilution data
    warrants: List[WarrantModel] = Field(default_factory=list)
    atm_offerings: List[ATMOfferingModel] = Field(default_factory=list)
    shelf_registrations: List[ShelfRegistrationModel] = Field(default_factory=list)
    completed_offerings: List[CompletedOfferingModel] = Field(default_factory=list)
    s1_offerings: List[S1OfferingModel] = Field(default_factory=list)
    convertible_notes: List[ConvertibleNoteModel] = Field(default_factory=list)
    convertible_preferred: List[ConvertiblePreferredModel] = Field(default_factory=list)
    equity_lines: List[EquityLineModel] = Field(default_factory=list)
    
    # Context
    current_price: Optional[Decimal] = None
    shares_outstanding: Optional[int] = None
    float_shares: Optional[int] = None
    
    # Metadata
    metadata: DilutionProfileMetadata
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    def calculate_potential_dilution(self) -> dict:
        """
        Calcular dilución potencial total
        
        Returns:
            Dict con análisis de dilución potencial
        """
        if not self.shares_outstanding or not self.current_price:
            return {
                "error": "Missing shares_outstanding or current_price",
                "total_potential_dilution_pct": None
            }
        
        # Shares potenciales de warrants
        warrant_shares = sum(
            w.potential_new_shares or 0 
            for w in self.warrants
        )
        
        # Shares potenciales de ATM (remaining capacity / current price)
        # ATM siempre es para common stock
        atm_shares = sum(
            int((a.remaining_capacity or 0) / self.current_price)
            for a in self.atm_offerings
        )
        
        # Shares potenciales de shelf - CRÍTICO: Solo common stock shelves
        # NO convertir preferred stock shelves a acciones comunes
        # S-11 normalmente es preferred stock, no common stock
        shelf_shares = 0
        shelf_capacity_common = 0
        shelf_capacity_preferred = 0
        
        for s in self.shelf_registrations:
            remaining = float(s.remaining_capacity or 0)
            
            # Si es S-11, asumir preferred stock (no diluye common stock directamente)
            if s.registration_statement and 'S-11' in s.registration_statement:
                shelf_capacity_preferred += remaining
                continue
            
            # Si tiene security_type explícito
            if s.security_type:
                if s.security_type == 'preferred_stock':
                    shelf_capacity_preferred += remaining
                    continue
                elif s.security_type == 'common_stock':
                    shelf_capacity_common += remaining
                # Si es 'mixed', solo contar una parte conservadora
                elif s.security_type == 'mixed':
                    shelf_capacity_common += remaining * 0.5  # Conservador: 50%
                    shelf_capacity_preferred += remaining * 0.5
                    continue
            
            # Si no tiene security_type, pero es S-3/S-1, asumir common stock
            # PERO ser conservador: no asumir 100% uso al precio actual
            if s.registration_statement and s.registration_statement in ['S-3', 'S-1']:
                # Conservador: asumir que se usa a un precio 20% más bajo que actual
                # (las empresas suelen vender a descuento)
                conservative_price = self.current_price * 0.8
                shelf_shares += int(remaining / conservative_price)
                shelf_capacity_common += remaining
            # Si es desconocido, no contar (más seguro)
        
        # Shares potenciales de convertible notes (remaining shares when converted)
        convertible_note_shares = sum(
            cn.remaining_shares_when_converted or cn.total_shares_when_converted or 0
            for cn in self.convertible_notes
        )
        
        # Shares potenciales de convertible preferred (remaining shares when converted)
        convertible_preferred_shares = sum(
            cp.remaining_shares_when_converted or cp.total_shares_when_converted or 0
            for cp in self.convertible_preferred
        )
        
        # Shares potenciales de equity lines (remaining capacity / current price)
        equity_line_shares = sum(
            int((el.remaining_capacity or 0) / self.current_price)
            for el in self.equity_lines
        )
        
        total_potential_shares = (
            warrant_shares + 
            atm_shares + 
            shelf_shares + 
            convertible_note_shares + 
            convertible_preferred_shares + 
            equity_line_shares
        )
        
        # % dilución
        dilution_pct = (total_potential_shares / self.shares_outstanding) * 100 if self.shares_outstanding else 0
        
        return {
            "total_potential_new_shares": total_potential_shares,
            "warrant_shares": warrant_shares,
            "atm_potential_shares": atm_shares,
            "shelf_potential_shares": shelf_shares,
            "convertible_note_shares": convertible_note_shares,
            "convertible_preferred_shares": convertible_preferred_shares,
            "equity_line_shares": equity_line_shares,
            "shelf_capacity_common_stock": shelf_capacity_common,
            "shelf_capacity_preferred_stock": shelf_capacity_preferred,
            "current_shares_outstanding": self.shares_outstanding,
            "total_potential_dilution_pct": round(float(dilution_pct), 2),
            "assumptions": [
                "All warrants exercised",
                "All ATM capacity used at current price",
                "Common stock shelves used at 80% of current price (conservative)",
                "Preferred stock shelves (S-11) NOT converted to common stock dilution",
                "All convertible notes converted to common stock",
                "All convertible preferred converted to common stock",
                "All equity lines used at current price"
            ]
        }


class DilutionProfileResponse(BaseModel):
    """API response for dilution profile"""
    profile: SECDilutionProfile
    dilution_analysis: dict
    cached: bool = False
    cache_age_seconds: Optional[int] = None


