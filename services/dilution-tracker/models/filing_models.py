"""
SEC Filing Models
"""

from datetime import date, datetime
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field, validator, HttpUrl


class FilingCategory(str, Enum):
    """Filing category for classification"""
    FINANCIAL = "financial"  # 10-K, 10-Q
    OFFERING = "offering"    # S-3, 424B5, S-1
    OWNERSHIP = "ownership"  # SC 13D/A, SC 13G
    PROXY = "proxy"          # DEF 14A
    DISCLOSURE = "disclosure"  # 8-K
    OTHER = "other"


class FilingType(str, Enum):
    """Common SEC filing types"""
    # Annual/Quarterly Reports
    FORM_10K = "10-K"
    FORM_10Q = "10-Q"
    
    # Current Reports
    FORM_8K = "8-K"
    
    # Registration Statements
    FORM_S1 = "S-1"
    FORM_S3 = "S-3"
    FORM_S4 = "S-4"
    FORM_S8 = "S-8"
    
    # Prospectus
    FORM_424B2 = "424B2"
    FORM_424B3 = "424B3"
    FORM_424B5 = "424B5"
    
    # Proxy Statements
    FORM_DEF14A = "DEF 14A"
    FORM_DEFA14A = "DEFA14A"
    
    # Ownership Reports
    FORM_SC13D = "SC 13D"
    FORM_SC13DA = "SC 13D/A"
    FORM_SC13G = "SC 13G"
    FORM_SC13GA = "SC 13G/A"
    
    # Other
    FORM_NT10K = "NT 10-K"
    FORM_NT10Q = "NT 10-Q"


class SECFilingCreate(BaseModel):
    """Model for creating SEC filing record"""
    ticker: str = Field(..., max_length=10)
    filing_type: str = Field(..., max_length=20)
    filing_date: date
    report_date: Optional[date] = None
    
    accession_number: str = Field(..., max_length=50, description="Unique SEC accession number")
    
    title: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    
    # Classification
    category: Optional[FilingCategory] = None
    is_offering_related: bool = False
    is_dilutive: bool = False
    
    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper() if v else v
    
    @validator('category', pre=True, always=True)
    def auto_classify_category(cls, v, values):
        """Auto-classify category based on filing type if not provided"""
        if v is not None:
            return v
        
        filing_type = values.get('filing_type', '').upper()
        
        # Financial reports
        if filing_type in ['10-K', '10-Q', 'NT 10-K', 'NT 10-Q']:
            return FilingCategory.FINANCIAL
        
        # Offerings/Registration
        if filing_type in ['S-1', 'S-3', 'S-4', 'S-8', '424B2', '424B3', '424B5']:
            return FilingCategory.OFFERING
        
        # Ownership
        if filing_type.startswith('SC 13'):
            return FilingCategory.OWNERSHIP
        
        # Proxy
        if 'DEF 14A' in filing_type or 'DEFA14A' in filing_type:
            return FilingCategory.PROXY
        
        # Current reports
        if filing_type == '8-K':
            return FilingCategory.DISCLOSURE
        
        return FilingCategory.OTHER
    
    @validator('is_offering_related', pre=True, always=True)
    def auto_flag_offering(cls, v, values):
        """Auto-flag offering-related filings"""
        filing_type = values.get('filing_type', '').upper()
        
        # Override if explicitly set
        if v is True:
            return True
        
        # Auto-flag based on filing type
        offering_types = ['S-1', 'S-3', 'S-4', 'S-8', '424B2', '424B3', '424B5']
        return filing_type in offering_types
    
    @validator('is_dilutive', pre=True, always=True)
    def auto_flag_dilutive(cls, v, values):
        """Auto-flag potentially dilutive filings"""
        filing_type = values.get('filing_type', '').upper()
        
        # Override if explicitly set
        if v is True:
            return True
        
        # Auto-flag based on filing type
        # S-3 and prospectus supplements usually mean dilution
        dilutive_types = ['S-3', '424B5', '424B3']
        return filing_type in dilutive_types
    
    class Config:
        schema_extra = {
            "example": {
                "ticker": "AAPL",
                "filing_type": "10-Q",
                "filing_date": "2024-11-01",
                "report_date": "2024-09-30",
                "accession_number": "0000320193-24-000123",
                "title": "Quarterly Report",
                "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193",
                "category": "financial",
                "is_offering_related": False,
                "is_dilutive": False
            }
        }


class SECFiling(SECFilingCreate):
    """Complete SEC filing with ID and metadata"""
    id: int
    fetched_at: datetime
    
    class Config:
        orm_mode = True


class SECFilingResponse(BaseModel):
    """Response model for SEC filing"""
    id: int
    filing_type: str
    filing_date: date
    report_date: Optional[date] = None
    
    title: Optional[str] = None
    category: FilingCategory
    
    # Flags
    is_offering_related: bool
    is_dilutive: bool
    
    # URL
    url: Optional[str] = None
    
    # Display helpers
    @property
    def filing_display_name(self) -> str:
        """Human-readable filing name"""
        type_names = {
            "10-K": "Annual Report",
            "10-Q": "Quarterly Report",
            "8-K": "Current Report",
            "S-3": "Shelf Registration",
            "424B5": "Prospectus Supplement",
            "SC 13D": "Ownership Report (Active)",
            "SC 13G": "Ownership Report (Passive)",
            "DEF 14A": "Proxy Statement",
        }
        return type_names.get(self.filing_type, self.filing_type)
    
    @classmethod
    def from_model(cls, filing: SECFiling) -> "SECFilingResponse":
        """Convert SECFiling to response format"""
        return cls(
            id=filing.id,
            filing_type=filing.filing_type,
            filing_date=filing.filing_date,
            report_date=filing.report_date,
            title=filing.title,
            category=filing.category,
            is_offering_related=filing.is_offering_related,
            is_dilutive=filing.is_dilutive,
            url=filing.url
        )
    
    class Config:
        schema_extra = {
            "example": {
                "id": 12345,
                "filing_type": "10-Q",
                "filing_date": "2024-11-01",
                "report_date": "2024-09-30",
                "title": "Quarterly Report",
                "category": "financial",
                "is_offering_related": False,
                "is_dilutive": False,
                "url": "https://www.sec.gov/..."
            }
        }


class FilingsResponse(BaseModel):
    """Response model for list of filings"""
    ticker: str
    total_filings: int
    category_filter: Optional[FilingCategory] = None
    filings: List[SECFilingResponse]
    
    class Config:
        schema_extra = {
            "example": {
                "ticker": "AAPL",
                "total_filings": 25,
                "category_filter": None,
                "filings": [
                    {
                        "id": 1,
                        "filing_type": "10-Q",
                        "filing_date": "2024-11-01",
                        "title": "Quarterly Report",
                        "category": "financial",
                        "is_offering_related": False,
                        "is_dilutive": False
                    }
                ]
            }
        }

