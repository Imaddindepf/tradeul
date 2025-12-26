"""
SEC Dilution Profile Models
Models para warrants, ATM offerings, shelf registrations y completed offerings
"""

from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal, InvalidOperation
from pydantic import BaseModel, Field, validator
from dateutil import parser as date_parser


def parse_flexible_date(value):
    """Parse dates in various formats: ISO, 'December 16, 2026', etc."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        # Handle invalid date placeholders from Grok
        if cleaned in ('0000-00-00', '0000-00-01', '1900-01-01', 'N/A', 'TBD', 'null', 'None', '-'):
            return None
        try:
            # Try ISO format first
            return datetime.strptime(cleaned, '%Y-%m-%d').date()
        except ValueError:
            pass
        try:
            # Try flexible parsing (handles "December 16, 2026", "Dec 16, 2026", etc.)
            return date_parser.parse(cleaned).date()
        except Exception:
            return None
    return None


def parse_flexible_decimal(value):
    """Parse decimals, handling 'N/A', 'TBD', '$1,000', etc."""
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip().upper()
        # Skip non-numeric values
        if cleaned in ('N/A', 'TBD', 'UNKNOWN', 'PENDING', '-', '', 'NULL', 'NONE', 'NOT DISCLOSED', 'UNDISCLOSED'):
            return None
        # Clean currency symbols and commas
        cleaned = value.replace('$', '').replace('€', '').replace(',', '').replace(' ', '').strip()
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


def parse_flexible_int(value):
    """Parse integers, handling 'N/A', '1,000,000', etc."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip().upper()
        if cleaned in ('N/A', 'TBD', 'UNKNOWN', 'PENDING', '-', '', 'NULL', 'NONE', 'NOT DISCLOSED'):
            return None
        cleaned = value.replace(',', '').replace(' ', '').strip()
        if not cleaned:
            return None
        try:
            return int(float(cleaned))
        except (ValueError, TypeError):
            return None
    return None


class WarrantModel(BaseModel):
    """Model for warrant data with full lifecycle tracking"""
    id: Optional[int] = None
    ticker: str = Field(..., max_length=10)
    issue_date: Optional[date] = None
    outstanding: Optional[int] = Field(None, description="Number of warrants outstanding (split-adjusted)")
    exercise_price: Optional[Decimal] = Field(None, description="Exercise/strike price (split-adjusted)")
    expiration_date: Optional[date] = None
    potential_new_shares: Optional[int] = Field(None, description="Potential shares if all warrants exercised (split-adjusted)")
    notes: Optional[str] = None
    status: Optional[str] = Field(None, description="Status: Active, Exercised, Replaced, Historical_Summary")
    is_summary_row: Optional[bool] = Field(None, description="True if this is an aggregated summary row from 10-Q/10-K")
    exclude_from_dilution: Optional[bool] = Field(None, description="True if should be excluded from dilution calculation")
    imputed_fields: Optional[list] = Field(None, description="List of fields that were imputed from other warrants")
    # Split adjustment fields
    split_adjusted: Optional[bool] = Field(None, description="True if values were adjusted for stock splits")
    split_factor: Optional[float] = Field(None, description="Cumulative split factor applied (e.g., 10 for 1:10 reverse split)")
    original_exercise_price: Optional[Decimal] = Field(None, description="Original exercise price before split adjustment")
    original_outstanding: Optional[int] = Field(None, description="Original outstanding before split adjustment")
    # Exercise tracking fields (from 10-Q/10-K)
    total_issued: Optional[int] = Field(None, description="Total warrants originally issued")
    exercised: Optional[int] = Field(None, description="Number of warrants exercised to date")
    expired: Optional[int] = Field(None, description="Number of warrants expired/cancelled to date")
    remaining: Optional[int] = Field(None, description="Remaining warrants (total - exercised - expired)")
    last_update_date: Optional[date] = Field(None, description="Date of last 10-Q/10-K update for exercise data")
    # NEW: Additional fields from DilutionTracker
    series_name: Optional[str] = Field(None, max_length=255, description="Warrant series name (e.g., 'August 2025 Warrants')")
    known_owners: Optional[str] = Field(None, description="Known warrant holders (e.g., '3i, Akita, CVI')")
    underwriter_agent: Optional[str] = Field(None, max_length=255, description="Underwriter/Placement agent")
    price_protection: Optional[str] = Field(None, description="Price protection type: Customary Anti-Dilution, Reset, Full Ratchet, Undisclosed")
    pp_clause: Optional[str] = Field(None, description="Full text of Price Protection clause")
    exercisable_date: Optional[date] = Field(None, description="Date when warrants become exercisable")
    # Registration and exercise features
    is_registered: Optional[bool] = Field(None, description="True if warrants are registered (EDGAR)")
    registration_type: Optional[str] = Field(None, description="EDGAR / Not Registered")
    is_prefunded: Optional[bool] = Field(None, description="True if pre-funded warrants")
    has_cashless_exercise: Optional[bool] = Field(None, description="True if cashless exercise is permitted")
    warrant_coverage_ratio: Optional[Decimal] = Field(None, description="Warrant coverage ratio from offering")
    anti_dilution_provision: Optional[bool] = Field(None, description="True if has anti-dilution provision")
    # Trazabilidad de filings
    source_filing: Optional[str] = Field(None, description="Source filing (e.g., '6-K:2023-12-26')")
    source_filings: Optional[list] = Field(None, description="All source filings if merged from multiple")
    merged_from_count: Optional[int] = Field(None, description="Number of records merged into this one")
    filing_url: Optional[str] = Field(None, description="URL of the source filing")
    # Original values before split adjustment
    original_total_issued: Optional[int] = Field(None, description="Original total_issued before split adjustment")
    
    # ===========================================================================
    # NEW: Warrant Lifecycle Fields (v5)
    # ===========================================================================
    
    # Warrant Type Classification
    warrant_type: Optional[str] = Field(
        None, 
        max_length=50,
        description="Type: Common, Pre-Funded, Penny, Placement Agent, Underwriter, SPAC Public, SPAC Private, Inducement"
    )
    underlying_type: Optional[str] = Field(
        None,
        max_length=50, 
        description="Underlying security: shares (default), convertible_notes, preferred_stock"
    )
    
    # Ownership Blocker (important for large holders)
    ownership_blocker_pct: Optional[Decimal] = Field(
        None, 
        description="Beneficial ownership blocker percentage (e.g., 4.99, 9.99, 19.99)"
    )
    blocker_clause: Optional[str] = Field(
        None,
        description="Full text of ownership blocker clause"
    )
    
    # Proceeds Tracking
    potential_proceeds: Optional[Decimal] = Field(
        None, 
        description="Total potential proceeds if all warrants exercised (outstanding × exercise_price)"
    )
    actual_proceeds_to_date: Optional[Decimal] = Field(
        None, 
        description="Actual proceeds received from warrant exercises to date"
    )
    
    # Warrant Agreement / Exhibit Reference
    warrant_agreement_exhibit: Optional[str] = Field(
        None, 
        max_length=50,
        description="Exhibit number where warrant agreement is filed (e.g., '4.1', '4.2', '10.1')"
    )
    warrant_agreement_url: Optional[str] = Field(
        None, 
        description="Direct URL to warrant agreement exhibit"
    )
    
    # Series Linking (for replacements/amendments)
    replaced_by_id: Optional[int] = Field(
        None, 
        description="ID of the warrant series that replaced this one"
    )
    replaces_id: Optional[int] = Field(
        None, 
        description="ID of the warrant series that this one replaced"
    )
    amendment_of_id: Optional[int] = Field(
        None, 
        description="ID of the original warrant if this is an amendment"
    )
    
    # Alternate Exercise Options
    has_alternate_cashless: Optional[bool] = Field(
        None, 
        description="Has alternate cashless exercise formula (used when no registration)"
    )
    forced_exercise_provision: Optional[bool] = Field(
        None, 
        description="Has forced exercise if stock trades above threshold"
    )
    forced_exercise_price: Optional[Decimal] = Field(
        None, 
        description="Stock price threshold that triggers forced exercise"
    )
    forced_exercise_days: Optional[int] = Field(
        None,
        description="Number of trading days above threshold before forced exercise"
    )
    
    # Price Adjustment History Reference
    price_adjustment_count: Optional[int] = Field(
        None, 
        description="Number of price adjustments since issuance"
    )
    original_issue_price: Optional[Decimal] = Field(
        None, 
        description="Original exercise price at issuance (before any adjustments)"
    )
    last_price_adjustment_date: Optional[date] = Field(
        None, 
        description="Date of most recent price adjustment"
    )
    
    # Lifecycle Events Summary
    exercise_events_count: Optional[int] = Field(
        None, 
        description="Total number of exercise events"
    )
    last_exercise_date: Optional[date] = Field(
        None, 
        description="Date of most recent exercise"
    )
    last_exercise_quantity: Optional[int] = Field(
        None, 
        description="Quantity exercised in most recent exercise"
    )
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    @validator('issue_date', 'expiration_date', 'exercisable_date', 'last_update_date', 
               'last_price_adjustment_date', 'last_exercise_date', pre=True)
    def parse_dates(cls, v):
        return parse_flexible_date(v)
    
    @validator('exercise_price', 'original_exercise_price', 'warrant_coverage_ratio',
               'ownership_blocker_pct', 'potential_proceeds', 'actual_proceeds_to_date',
               'forced_exercise_price', 'original_issue_price', pre=True)
    def parse_decimal(cls, v):
        return parse_flexible_decimal(v)
    
    @validator('outstanding', 'potential_new_shares', 'total_issued', 'exercised', 
               'expired', 'remaining', 'original_outstanding', 'replaced_by_id',
               'replaces_id', 'amendment_of_id', 'price_adjustment_count',
               'exercise_events_count', 'last_exercise_quantity', 'forced_exercise_days', pre=True)
    def parse_int(cls, v):
        return parse_flexible_int(v)
    
    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "SOUN",
                "series_name": "May 2023 Public Warrants",
                "warrant_type": "Common",
                "issue_date": "2023-05-15",
                "outstanding": 15000000,
                "exercise_price": 11.50,
                "expiration_date": "2028-05-15",
                "potential_new_shares": 15000000,
                "ownership_blocker_pct": 4.99,
                "has_cashless_exercise": True,
                "notes": "Public warrants, cashless exercise permitted"
            }
        }


class WarrantLifecycleEvent(BaseModel):
    """
    Model for warrant lifecycle events (exercises, price adjustments, expirations, etc.)
    
    Tracks the complete history of a warrant series from issuance to expiration.
    """
    id: Optional[int] = None
    ticker: str = Field(..., max_length=10)
    warrant_id: Optional[int] = Field(None, description="FK to sec_warrants.id")
    series_name: Optional[str] = Field(None, max_length=255, description="Warrant series name for matching")
    
    # Event Type
    event_type: str = Field(
        ...,
        max_length=50,
        description="Type: Exercise, Cashless_Exercise, Price_Adjustment, Expiration, Amendment, Redemption, Cancellation, Split_Adjustment"
    )
    event_date: date = Field(..., description="Date of the event")
    
    # For Exercise Events
    warrants_affected: Optional[int] = Field(None, description="Number of warrants exercised/expired/cancelled")
    shares_issued: Optional[int] = Field(None, description="Number of common shares issued (for exercises)")
    proceeds_received: Optional[Decimal] = Field(None, description="Cash proceeds from exercise")
    exercise_method: Optional[str] = Field(
        None, 
        max_length=50,
        description="Cash, Cashless, or Combination"
    )
    
    # For Price Adjustment Events
    old_price: Optional[Decimal] = Field(None, description="Exercise price before adjustment")
    new_price: Optional[Decimal] = Field(None, description="Exercise price after adjustment")
    adjustment_reason: Optional[str] = Field(
        None,
        max_length=100,
        description="Reason: Stock_Split, Reverse_Split, Reset_Provision, Anti_Dilution, Amendment"
    )
    adjustment_factor: Optional[Decimal] = Field(None, description="Adjustment multiplier if applicable")
    
    # For Amendment Events
    amendment_description: Optional[str] = Field(None, description="Description of what was amended")
    
    # Running Totals (after this event)
    outstanding_after: Optional[int] = Field(None, description="Warrants outstanding after event")
    exercised_cumulative: Optional[int] = Field(None, description="Cumulative warrants exercised")
    expired_cumulative: Optional[int] = Field(None, description="Cumulative warrants expired/cancelled")
    
    # Source
    source_filing: Optional[str] = Field(None, description="Source filing (e.g., '10-Q:2024-08-14')")
    filing_url: Optional[str] = Field(None, description="URL of the source filing")
    created_at: Optional[datetime] = Field(None, description="When this record was created")
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    @validator('event_date', pre=True)
    def parse_dates(cls, v):
        return parse_flexible_date(v)
    
    @validator('proceeds_received', 'old_price', 'new_price', 'adjustment_factor', pre=True)
    def parse_decimal(cls, v):
        return parse_flexible_decimal(v)
    
    @validator('warrants_affected', 'shares_issued', 'outstanding_after', 
               'exercised_cumulative', 'expired_cumulative', pre=True)
    def parse_int(cls, v):
        return parse_flexible_int(v)
    
    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "VMAR",
                "series_name": "August 2024 Common Warrants",
                "event_type": "Exercise",
                "event_date": "2024-10-15",
                "warrants_affected": 500000,
                "shares_issued": 500000,
                "proceeds_received": 250000,
                "exercise_method": "Cash",
                "outstanding_after": 1500000,
                "source_filing": "10-Q:2024-11-14"
            }
        }


class WarrantPriceAdjustment(BaseModel):
    """
    Model for warrant price adjustment history
    
    Tracks all price adjustments due to stock splits, reverse splits, 
    anti-dilution provisions, amendments, etc.
    """
    id: Optional[int] = None
    ticker: str = Field(..., max_length=10)
    warrant_id: Optional[int] = Field(None, description="FK to sec_warrants.id")
    series_name: Optional[str] = Field(None, max_length=255, description="Warrant series name for matching")
    
    # Adjustment Details
    adjustment_date: date = Field(..., description="Date adjustment became effective")
    adjustment_type: str = Field(
        ...,
        max_length=50,
        description="Type: Stock_Split, Reverse_Split, Reset_Provision, Full_Ratchet, Weighted_Average, Amendment, Anti_Dilution"
    )
    
    # Price Change
    price_before: Decimal = Field(..., description="Exercise price before adjustment")
    price_after: Decimal = Field(..., description="Exercise price after adjustment")
    price_change_pct: Optional[Decimal] = Field(None, description="Percentage change in price")
    
    # Quantity Change (if applicable, e.g., for splits)
    quantity_before: Optional[int] = Field(None, description="Warrants outstanding before adjustment")
    quantity_after: Optional[int] = Field(None, description="Warrants outstanding after adjustment")
    quantity_multiplier: Optional[Decimal] = Field(None, description="Quantity adjustment multiplier")
    
    # Trigger Information
    trigger_event: Optional[str] = Field(
        None,
        description="Event that triggered adjustment (e.g., 'Reverse split 1:10', 'Offering at $0.50')"
    )
    trigger_price: Optional[Decimal] = Field(
        None, 
        description="Stock price that triggered reset/anti-dilution"
    )
    trigger_filing: Optional[str] = Field(
        None, 
        description="Filing that triggered (e.g., '8-K:2024-05-15')"
    )
    
    # Source
    source_filing: Optional[str] = Field(None, description="Filing where adjustment is disclosed")
    filing_url: Optional[str] = Field(None, description="URL of the source filing")
    created_at: Optional[datetime] = Field(None, description="When this record was created")
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    @validator('adjustment_date', pre=True)
    def parse_dates(cls, v):
        return parse_flexible_date(v)
    
    @validator('price_before', 'price_after', 'price_change_pct', 
               'quantity_multiplier', 'trigger_price', pre=True)
    def parse_decimal(cls, v):
        return parse_flexible_decimal(v)
    
    @validator('quantity_before', 'quantity_after', pre=True)
    def parse_int(cls, v):
        return parse_flexible_int(v)
    
    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "VMAR",
                "series_name": "August 2024 Common Warrants",
                "adjustment_date": "2024-09-01",
                "adjustment_type": "Reverse_Split",
                "price_before": 0.50,
                "price_after": 5.00,
                "quantity_before": 20000000,
                "quantity_after": 2000000,
                "quantity_multiplier": 0.1,
                "trigger_event": "Reverse split 1:10",
                "source_filing": "8-K:2024-09-01"
            }
        }


class ATMOfferingModel(BaseModel):
    """Model for At-The-Market offering data"""
    id: Optional[int] = None
    ticker: str = Field(..., max_length=10)
    series_name: Optional[str] = Field(None, max_length=255, description="ATM name (e.g., 'January 2023 Cantor ATM')")
    total_capacity: Optional[Decimal] = Field(None, description="Total ATM capacity in dollars")
    remaining_capacity: Optional[Decimal] = Field(None, description="Remaining capacity in dollars (may be limited by baby shelf)")
    placement_agent: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = Field(None, max_length=50, description="Active, Terminated, Replaced, etc.")
    agreement_start_date: Optional[date] = None
    filing_date: Optional[date] = None
    filing_url: Optional[str] = None
    potential_shares_at_current_price: Optional[int] = None
    notes: Optional[str] = None
    # Registration
    is_registered: Optional[bool] = Field(None, description="True if ATM is registered (EDGAR)")
    registration_type: Optional[str] = Field(None, description="EDGAR / Not Registered")
    # Baby Shelf calculation fields
    atm_limited_by_baby_shelf: Optional[bool] = Field(None, description="True if ATM is limited by baby shelf restriction")
    remaining_capacity_without_restriction: Optional[Decimal] = Field(None, description="Remaining capacity without baby shelf limitation")
    last_update_date: Optional[date] = Field(None, description="Date of last update")
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    @validator('agreement_start_date', 'filing_date', pre=True)
    def parse_dates(cls, v):
        return parse_flexible_date(v)
    
    @validator('total_capacity', 'remaining_capacity', pre=True)
    def parse_decimal(cls, v):
        return parse_flexible_decimal(v)
    
    @validator('potential_shares_at_current_price', pre=True)
    def parse_int(cls, v):
        return parse_flexible_int(v)
    
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
    series_name: Optional[str] = Field(None, max_length=255, description="Shelf name (e.g., 'April 2022 Shelf')")
    total_capacity: Optional[Decimal] = Field(None, description="Total shelf capacity in dollars")
    remaining_capacity: Optional[Decimal] = Field(None, description="Remaining capacity in dollars")
    current_raisable_amount: Optional[Decimal] = Field(None, description="Current amount that can be raised (limited by baby shelf)")
    total_amount_raised: Optional[Decimal] = Field(None, description="Total amount raised from this shelf")
    total_amount_raised_last_12mo: Optional[Decimal] = Field(None, description="Total raised in last 12 months under IB6")
    is_baby_shelf: Optional[bool] = Field(default=False, description="Is this a baby shelf (<$75M float)?")
    baby_shelf_restriction: Optional[bool] = Field(None, description="Is baby shelf restriction currently active?")
    security_type: Optional[str] = Field(None, max_length=50, description="Type of security: 'common_stock', 'preferred_stock', 'mixed', or null if unknown")
    filing_date: Optional[date] = None
    effect_date: Optional[date] = None
    registration_statement: Optional[str] = Field(None, max_length=50, description="e.g., S-3, S-1, S-11")
    filing_url: Optional[str] = None
    expiration_date: Optional[date] = Field(None, description="Shelf expiration (typically 3 years)")
    last_banker: Optional[str] = Field(None, max_length=255, description="Last investment banker used")
    status: Optional[str] = Field(None, max_length=50, description="Active, Expired, Replaced, etc.")
    notes: Optional[str] = None
    # Registration
    is_registered: Optional[bool] = Field(None, description="True if shelf is registered (EDGAR)")
    registration_type: Optional[str] = Field(None, description="EDGAR / Not Registered")
    # Baby Shelf calculation fields (calculated at runtime)
    price_to_exceed_baby_shelf: Optional[Decimal] = Field(None, description="Price needed to exceed baby shelf restriction")
    ib6_float_value: Optional[Decimal] = Field(None, description="IB6 float value = Float × Highest60DayClose × (1/3)")
    highest_60_day_close: Optional[Decimal] = Field(None, description="Highest closing price in last 60 days")
    outstanding_shares_calc: Optional[int] = Field(None, description="Outstanding shares used for calculation")
    float_shares_calc: Optional[int] = Field(None, description="Float shares used for calculation")
    last_update_date: Optional[date] = Field(None, description="Date of last update")
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    @validator('filing_date', 'effect_date', 'expiration_date', pre=True)
    def parse_dates(cls, v):
        return parse_flexible_date(v)
    
    @validator('total_capacity', 'remaining_capacity', 'current_raisable_amount', 
               'total_amount_raised', 'total_amount_raised_last_12mo', pre=True)
    def parse_decimal(cls, v):
        return parse_flexible_decimal(v)
    
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
    
    @validator('offering_date', pre=True)
    def parse_dates(cls, v):
        return parse_flexible_date(v)
    
    @validator('price_per_share', 'amount_raised', pre=True)
    def parse_decimal(cls, v):
        return parse_flexible_decimal(v)
    
    @validator('shares_issued', pre=True)
    def parse_int(cls, v):
        return parse_flexible_int(v)
    
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
    series_name: Optional[str] = Field(None, max_length=255, description="Name of the offering (e.g., 'December 2025 F-1 Offering')")
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
    
    @validator('s1_filing_date', 'last_update_date', pre=True)
    def parse_dates(cls, v):
        return parse_flexible_date(v)
    
    @validator('anticipated_deal_size', 'final_deal_size', 'final_pricing', 
               'warrant_coverage', 'final_warrant_coverage', 'exercise_price', pre=True)
    def parse_decimal(cls, v):
        return parse_flexible_decimal(v)
    
    @validator('final_shares_offered', pre=True)
    def parse_int(cls, v):
        return parse_flexible_int(v)


class ConvertibleNoteModel(BaseModel):
    """Model for convertible notes/debt"""
    id: Optional[int] = None
    ticker: str = Field(..., max_length=10)
    series_name: Optional[str] = Field(None, max_length=255, description="Note name (e.g., 'November 2020 1.25% Convertible Notes Due 2025')")
    total_principal_amount: Optional[Decimal] = Field(None, description="Total principal amount")
    remaining_principal_amount: Optional[Decimal] = Field(None, description="Remaining principal amount")
    conversion_price: Optional[Decimal] = Field(None, description="Conversion price per share")
    original_conversion_price: Optional[Decimal] = Field(None, description="Original conversion price before adjustments")
    conversion_ratio: Optional[Decimal] = Field(None, description="Conversion ratio (shares per $1000)")
    total_shares_when_converted: Optional[int] = Field(None, description="Total shares if fully converted")
    remaining_shares_when_converted: Optional[int] = Field(None, description="Remaining shares to be issued")
    interest_rate: Optional[Decimal] = Field(None, description="Interest rate (e.g., 1.25 for 1.25%)")
    issue_date: Optional[date] = None
    convertible_date: Optional[date] = None
    maturity_date: Optional[date] = None
    underwriter_agent: Optional[str] = Field(None, max_length=255)
    filing_url: Optional[str] = None
    notes: Optional[str] = None
    # Registration and protection fields
    is_registered: Optional[bool] = Field(None, description="True if notes are registered (EDGAR)")
    registration_type: Optional[str] = Field(None, description="EDGAR / Not Registered")
    known_owners: Optional[str] = Field(None, description="Known note holders (e.g., 'Cavalry, WVP, Bigger Capital')")
    price_protection: Optional[str] = Field(None, description="Price protection type: Customary Anti-Dilution, Reset, Full Ratchet, Variable Rate (TOXIC)")
    pp_clause: Optional[str] = Field(None, description="Full text of Price Protection clause")
    # Toxic financing indicators
    variable_rate_adjustment: Optional[bool] = Field(None, description="True if has variable rate conversion (TOXIC)")
    floor_price: Optional[Decimal] = Field(None, description="Floor price for variable rate notes")
    is_toxic: Optional[bool] = Field(None, description="True if identified as toxic/death spiral financing")
    last_update_date: Optional[date] = Field(None, description="Date of last update")
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    @validator('issue_date', 'convertible_date', 'maturity_date', pre=True)
    def parse_dates(cls, v):
        return parse_flexible_date(v)
    
    @validator('total_principal_amount', 'remaining_principal_amount', 'conversion_price',
                'original_conversion_price', 'conversion_ratio', 'interest_rate', 'floor_price', pre=True)
    def parse_decimal(cls, v):
        return parse_flexible_decimal(v)
    
    @validator('total_shares_when_converted', 'remaining_shares_when_converted', pre=True)
    def parse_int(cls, v):
        return parse_flexible_int(v)


class ConvertiblePreferredModel(BaseModel):
    """Model for convertible preferred stock"""
    id: Optional[int] = None
    ticker: str = Field(..., max_length=10)
    series_name: Optional[str] = Field(None, max_length=255, description="Full name (e.g., 'October 2025 Series B Convertible Preferred')")
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
    # Registration
    is_registered: Optional[bool] = Field(None, description="True if registered (EDGAR)")
    registration_type: Optional[str] = Field(None, description="EDGAR / Not Registered / Pending Effect")
    # Additional fields from DilutionTracker
    known_owners: Optional[str] = Field(None, description="Known preferred holders (e.g., 'C/M Capital, WVP')")
    price_protection: Optional[str] = Field(None, description="Price protection type: Customary Anti-Dilution, Reset, Full Ratchet, Variable Rate")
    pp_clause: Optional[str] = Field(None, description="Full text of Price Protection clause")
    floor_price: Optional[Decimal] = Field(None, description="Floor price for variable rate conversion")
    variable_rate_adjustment: Optional[bool] = Field(None, description="True if has variable rate conversion (TOXIC)")
    is_toxic: Optional[bool] = Field(None, description="True if death spiral or highly dilutive")
    status: Optional[str] = Field(None, max_length=50, description="Registered, Pending Effect, etc.")
    last_update_date: Optional[date] = Field(None, description="Date of last update")
    # Trazabilidad de filings
    source_filing: Optional[str] = Field(None, description="Source filing (e.g., '6-K:2023-12-26')")
    source_filings: Optional[list] = Field(None, description="All source filings if merged from multiple")
    merged_from_count: Optional[int] = Field(None, description="Number of records merged into this one")
    # Split adjustment tracking
    split_adjusted: Optional[bool] = Field(None, description="True if values were split-adjusted")
    split_factor: Optional[float] = Field(None, description="Split factor applied")
    original_conversion_price: Optional[Decimal] = Field(None, description="Original conversion price before split")
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    @validator('issue_date', 'convertible_date', 'maturity_date', pre=True)
    def parse_dates(cls, v):
        return parse_flexible_date(v)
    
    @validator('total_dollar_amount_issued', 'remaining_dollar_amount', 'conversion_price', 'floor_price', 'original_conversion_price', pre=True)
    def parse_decimal(cls, v):
        return parse_flexible_decimal(v)
    
    @validator('total_shares_when_converted', 'remaining_shares_when_converted', pre=True)
    def parse_int(cls, v):
        return parse_flexible_int(v)


class EquityLineModel(BaseModel):
    """Model for Equity Line of Credit (ELOC)"""
    id: Optional[int] = None
    ticker: str = Field(..., max_length=10)
    series_name: Optional[str] = Field(None, max_length=255, description="ELOC name (e.g., 'September 2025 White Lion SPA')")
    total_capacity: Optional[Decimal] = Field(None, description="Total equity line capacity")
    remaining_capacity: Optional[Decimal] = Field(None, description="Remaining capacity")
    agreement_start_date: Optional[date] = None
    agreement_end_date: Optional[date] = None
    filing_url: Optional[str] = None
    notes: Optional[str] = None
    # Registration
    is_registered: Optional[bool] = Field(None, description="True if ELOC is registered (EDGAR)")
    registration_type: Optional[str] = Field(None, description="EDGAR / Not Registered")
    # Counterparty
    counterparty: Optional[str] = Field(None, max_length=255, description="Equity line counterparty (e.g., 'Lincoln Park', 'YA II', 'White Lion')")
    last_update_date: Optional[date] = Field(None, description="Date of last update")
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    @validator('agreement_start_date', 'agreement_end_date', pre=True)
    def parse_dates(cls, v):
        return parse_flexible_date(v)
    
    @validator('total_capacity', 'remaining_capacity', pre=True)
    def parse_decimal(cls, v):
        return parse_flexible_decimal(v)


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
    
    # NEW: Warrant Lifecycle (v5)
    warrant_lifecycle_events: List[WarrantLifecycleEvent] = Field(
        default_factory=list,
        description="Historical warrant events (exercises, adjustments, etc.)"
    )
    warrant_price_adjustments: List[WarrantPriceAdjustment] = Field(
        default_factory=list,
        description="Historical price adjustments for warrants"
    )
    
    # Context
    current_price: Optional[Decimal] = None
    shares_outstanding: Optional[int] = None
    float_shares: Optional[int] = None
    
    # Historical shares outstanding (from SEC EDGAR XBRL)
    historical_shares: List[dict] = Field(
        default_factory=list,
        description="Historical shares outstanding: [{date, shares, form, filed}]"
    )
    
    # Metadata
    metadata: DilutionProfileMetadata
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    def calculate_warrant_analysis(self) -> dict:
        """
        Analizar warrants in-the-money vs out-of-money
        """
        if not self.current_price:
            return {"error": "Missing current_price"}
        
        current_price_float = float(self.current_price)
        active_warrants = [w for w in self.warrants if w.status == 'Active' and not w.exclude_from_dilution]
        
        in_the_money = []
        out_of_money = []
        
        for w in active_warrants:
            exercise_price = float(w.exercise_price or 0)
            warrant_info = {
                "outstanding": w.outstanding or 0,
                "exercise_price": exercise_price,
                "expiration_date": str(w.expiration_date) if w.expiration_date else None,
                "notes": w.notes
            }
            if exercise_price > 0 and exercise_price <= current_price_float:
                in_the_money.append(warrant_info)
            else:
                out_of_money.append(warrant_info)
        
        total_itm = sum(w["outstanding"] for w in in_the_money)
        total_otm = sum(w["outstanding"] for w in out_of_money)
        
        return {
            "in_the_money_count": len(in_the_money),
            "in_the_money_warrants": total_itm,
            "in_the_money_details": in_the_money,
            "out_of_money_count": len(out_of_money),
            "out_of_money_warrants": total_otm,
            "out_of_money_details": out_of_money,
            "total_active_warrants": total_itm + total_otm,
            "current_price": current_price_float
        }
    
    def calculate_equity_line_shares(self) -> dict:
        """
        Calcular shares de equity lines considerando 20% NASDAQ rule
        """
        if not self.current_price or not self.shares_outstanding:
            return {"error": "Missing current_price or shares_outstanding"}
        
        current_price_float = float(self.current_price)
        nasdaq_20_pct_limit = int(self.shares_outstanding * 0.20)  # 20% of outstanding
        
        results = []
        total_estimated_shares = 0
        total_shares_with_nasdaq_limit = 0
        
        for el in self.equity_lines:
            remaining = float(el.remaining_capacity or 0)
            estimated_shares = int(remaining / current_price_float) if current_price_float > 0 else 0
            shares_with_limit = min(estimated_shares, nasdaq_20_pct_limit)
            
            results.append({
                "partner": el.partner,
                "remaining_capacity": remaining,
                "estimated_shares_no_limit": estimated_shares,
                "nasdaq_20_pct_limit": nasdaq_20_pct_limit,
                "estimated_shares_with_limit": shares_with_limit,
                "is_limited_by_nasdaq": estimated_shares > nasdaq_20_pct_limit
            })
            total_estimated_shares += estimated_shares
            total_shares_with_nasdaq_limit += shares_with_limit
        
        return {
            "equity_lines": results,
            "total_estimated_shares_no_limit": total_estimated_shares,
            "total_shares_with_nasdaq_limit": total_shares_with_nasdaq_limit,
            "nasdaq_20_pct_cap": nasdaq_20_pct_limit,
            "note": "20% NASDAQ rule limits ELOC usage without shareholder approval"
        }
    
    def calculate_warrant_lifecycle_summary(self) -> dict:
        """
        Calculate comprehensive warrant lifecycle analysis.
        
        Returns:
            Dict with lifecycle metrics:
            - Total proceeds potential
            - Actual proceeds received
            - Exercise velocity
            - Price adjustments impact
            - By warrant type breakdown
        """
        if not self.warrants:
            return {"error": "No warrants found", "has_data": False}
        
        current_price_float = float(self.current_price or 0)
        
        # Aggregate metrics
        total_outstanding = 0
        total_exercised = 0
        total_expired = 0
        total_potential_proceeds = Decimal('0')
        total_actual_proceeds = Decimal('0')
        
        # By type
        by_type = {}
        by_status = {"Active": 0, "Exercised": 0, "Replaced": 0, "Expired": 0, "Historical_Summary": 0}
        
        # In-the-money analysis
        itm_warrants = []
        otm_warrants = []
        
        for w in self.warrants:
            # Skip excluded warrants
            if w.exclude_from_dilution:
                continue
            
            # By type aggregation
            w_type = w.warrant_type or "Unknown"
            if w_type not in by_type:
                by_type[w_type] = {"count": 0, "outstanding": 0, "potential_proceeds": Decimal('0')}
            
            outstanding = w.outstanding or w.remaining or 0
            by_type[w_type]["count"] += 1
            by_type[w_type]["outstanding"] += outstanding
            
            # By status
            status = w.status or "Active"
            if status in by_status:
                by_status[status] += outstanding
            
            # Only count Active warrants for totals
            if status == "Active":
                total_outstanding += outstanding
                
                # Potential proceeds
                if w.exercise_price and outstanding:
                    proceeds = Decimal(str(outstanding)) * w.exercise_price
                    total_potential_proceeds += proceeds
                    by_type[w_type]["potential_proceeds"] += proceeds
                    
                    # ITM/OTM analysis
                    ex_price = float(w.exercise_price)
                    if current_price_float > 0 and ex_price <= current_price_float:
                        itm_warrants.append({
                            "series": w.series_name,
                            "type": w_type,
                            "outstanding": outstanding,
                            "exercise_price": ex_price,
                            "intrinsic_value": (current_price_float - ex_price) * outstanding
                        })
                    else:
                        otm_warrants.append({
                            "series": w.series_name,
                            "type": w_type,
                            "outstanding": outstanding,
                            "exercise_price": ex_price,
                            "distance_from_itm": (ex_price - current_price_float) if current_price_float > 0 else None
                        })
                
                # Actual proceeds
                if w.actual_proceeds_to_date:
                    total_actual_proceeds += w.actual_proceeds_to_date
            
            # Exercise tracking
            total_exercised += w.exercised or 0
            total_expired += w.expired or 0
        
        # Lifecycle events summary
        exercise_events = [e for e in self.warrant_lifecycle_events if e.event_type in ('Exercise', 'Cashless_Exercise')]
        price_adjustments = len(self.warrant_price_adjustments)
        
        # Calculate exercise velocity (exercises per quarter)
        if exercise_events:
            from datetime import timedelta
            dates = sorted([e.event_date for e in exercise_events if e.event_date])
            if len(dates) >= 2:
                span_days = (dates[-1] - dates[0]).days
                quarters = max(span_days / 90, 1)
                exercise_velocity = len(exercise_events) / quarters
            else:
                exercise_velocity = None
        else:
            exercise_velocity = None
        
        return {
            "has_data": True,
            "summary": {
                "total_active_outstanding": total_outstanding,
                "total_exercised_to_date": total_exercised,
                "total_expired_cancelled": total_expired,
                "total_original_issued": total_outstanding + total_exercised + total_expired,
                "exercise_rate_pct": round(
                    (total_exercised / (total_outstanding + total_exercised + total_expired) * 100) 
                    if (total_outstanding + total_exercised + total_expired) > 0 else 0, 2
                ),
            },
            "proceeds": {
                "potential_if_all_exercised": float(total_potential_proceeds),
                "actual_received_to_date": float(total_actual_proceeds),
                "realization_rate_pct": round(
                    float(total_actual_proceeds / total_potential_proceeds * 100) 
                    if total_potential_proceeds > 0 else 0, 2
                ),
            },
            "by_type": {k: {"count": v["count"], "outstanding": v["outstanding"], 
                          "potential_proceeds": float(v["potential_proceeds"])} 
                       for k, v in by_type.items()},
            "by_status": by_status,
            "in_the_money": {
                "count": len(itm_warrants),
                "total_outstanding": sum(w["outstanding"] for w in itm_warrants),
                "total_intrinsic_value": sum(w["intrinsic_value"] for w in itm_warrants),
                "details": itm_warrants[:5],  # Top 5
            },
            "out_of_money": {
                "count": len(otm_warrants),
                "total_outstanding": sum(w["outstanding"] for w in otm_warrants),
                "details": otm_warrants[:5],  # Top 5
            },
            "lifecycle_activity": {
                "exercise_events": len(exercise_events),
                "price_adjustments": price_adjustments,
                "exercise_velocity_per_quarter": round(exercise_velocity, 2) if exercise_velocity else None,
            },
            "current_price": current_price_float,
        }
    
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
        
        # Convertir current_price a float para operaciones matemáticas
        # (puede venir como Decimal de BD o float de Redis)
        current_price_float = float(self.current_price)
        
        # Shares potenciales de warrants
        # INCLUIR warrants con status="Active" o None (si no tienen status, asumir activos)
        # Excluir: Replaced, Exercised, Historical_Summary
        warrant_shares = sum(
            w.potential_new_shares or w.outstanding or w.total_issued or 0 
            for w in self.warrants
            if not w.exclude_from_dilution and (w.status in ['Active', None])  # Active o None
        )
        
        # Shares potenciales de ATM (remaining capacity / current price)
        # ATM siempre es para common stock
        # SOLO contar ATMs con status="Active" o None (excluir Terminated, Replaced)
        atm_shares = sum(
            int(float(a.remaining_capacity or 0) / current_price_float)
            for a in self.atm_offerings
            if a.status in ['Active', None]
        )
        
        # Shares potenciales de shelf - CRÍTICO: Solo common stock shelves
        # NO convertir preferred stock shelves a acciones comunes
        # S-11 normalmente es preferred stock, not common stock
        # SOLO contar shelfs con status="Active" (excluir Expired)
        shelf_shares = 0
        shelf_capacity_common = 0
        shelf_capacity_preferred = 0
        
        for s in self.shelf_registrations:
            # Solo contar shelfs activos (Active o None, excluir Expired)
            if s.status not in ['Active', None]:
                continue
                
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
                conservative_price = current_price_float * 0.8
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
            int(float(el.remaining_capacity or 0) / current_price_float)
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
        
        # % dilución (convertir a float para evitar errores Decimal/float)
        shares_out = float(self.shares_outstanding) if self.shares_outstanding else 0
        dilution_pct = (total_potential_shares / shares_out) * 100 if shares_out else 0
        
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

    # Company type detection
    is_spac: Optional[bool] = Field(None, description="True if company is a SPAC")
    sic_code: Optional[str] = Field(None, description="SIC Code (6770 = Blank Checks/SPAC)")
    
    # Risk Assessment (DilutionTracker-style ratings)
    risk_assessment: Optional[dict] = Field(None, description="Risk ratings: overall, offering_ability, overhead_supply, historical, cash_need")


