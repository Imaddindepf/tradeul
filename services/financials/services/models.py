"""
Financial Models - Modelos Pydantic compartidos para servicios financieros.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


class StatementType(str, Enum):
    """Tipo de estado financiero."""
    INCOME = "income"
    BALANCE = "balance"
    CASHFLOW = "cashflow"


class DataType(str, Enum):
    """Tipo de dato del campo (TDH compliant)."""
    MONETARY = "monetary"
    PERCENT = "percent"
    SHARES = "shares"
    PER_SHARE = "perShare"
    RATIO = "ratio"


class FinancialField(BaseModel):
    """
    Campo financiero individual.
    
    Representa un campo como Revenue, Net Income, etc.
    con sus valores para múltiples períodos.
    """
    key: str = Field(..., description="Identificador único")
    label: str = Field(..., description="Etiqueta para display")
    values: List[Optional[float]] = Field(default_factory=list)
    
    # Metadata de estructura
    section: str = Field(default="Other")
    display_order: int = Field(default=9999)
    indent_level: int = Field(default=0)
    is_subtotal: bool = Field(default=False)
    is_industry_specific: bool = Field(default=False)
    
    # Metadata de datos
    data_type: DataType = Field(default=DataType.MONETARY)
    importance: int = Field(default=100)
    source_fields: List[str] = Field(default_factory=list)
    calculated: bool = Field(default=False)
    corrected: bool = Field(default=False)
    split_adjusted: bool = Field(default=False)
    
    class Config:
        use_enum_values = True


class FinancialStatement(BaseModel):
    """Estado financiero completo."""
    symbol: str
    statement_type: StatementType
    periods: List[str]
    period_end_dates: List[str]
    fields: List[FinancialField]
    currency: str = "USD"


class FinancialData(BaseModel):
    """Datos financieros completos de una empresa."""
    symbol: str
    currency: str = "USD"
    source: str = "sec-api-xbrl"
    
    # Metadata
    industry: Optional[str] = None
    sector: Optional[str] = None
    fiscal_year_end_month: Optional[int] = None
    
    # Períodos
    periods: List[str] = Field(default_factory=list)
    period_end_dates: List[str] = Field(default_factory=list)
    
    # Statements
    income_statement: List[Dict[str, Any]] = Field(default_factory=list)
    balance_sheet: List[Dict[str, Any]] = Field(default_factory=list)
    cash_flow: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Splits
    split_adjusted: bool = False
    splits: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Timestamps
    processing_time_seconds: Optional[float] = None
    last_updated: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    cached: bool = False


class SplitInfo(BaseModel):
    """Información de un stock split."""
    execution_date: str
    split_from: int
    split_to: int
    
    @property
    def ratio(self) -> str:
        return f"{self.split_to}:{self.split_from}"
    
    @property
    def factor(self) -> float:
        return self.split_to / self.split_from if self.split_from > 0 else 1.0

