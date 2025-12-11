"""
Edgar Service Models - Modelos Pydantic para datos financieros.

Estos modelos definen la estructura de datos extraídos via edgartools.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import date


class StatementType(str, Enum):
    """Tipo de estado financiero."""
    INCOME = "income"
    BALANCE = "balance"
    CASHFLOW = "cashflow"


class DataType(str, Enum):
    """Tipo de dato del campo."""
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
    key: str = Field(..., description="Identificador único del campo")
    label: str = Field(..., description="Etiqueta para mostrar")
    values: List[Optional[float]] = Field(default_factory=list, description="Valores por período")
    
    # Metadata
    data_type: DataType = Field(default=DataType.MONETARY)
    section: str = Field(default="Other", description="Sección del estado financiero")
    order: int = Field(default=9999, description="Orden de visualización")
    indent: int = Field(default=0, description="Nivel de indentación")
    is_subtotal: bool = Field(default=False, description="Es un subtotal")
    
    # Trazabilidad
    source: str = Field(default="edgartools", description="Fuente del dato")
    xbrl_concept: Optional[str] = Field(default=None, description="Concepto XBRL original")
    calculated: bool = Field(default=False, description="Es calculado vs extraído")
    corrected: bool = Field(default=False, description="Fue corregido")
    
    class Config:
        use_enum_values = True


class EnrichmentResult(BaseModel):
    """
    Resultado de enriquecimiento para un símbolo.
    
    Contiene los campos adicionales extraídos de edgartools
    que complementan los datos de SEC-API.
    """
    symbol: str
    periods: List[str] = Field(default_factory=list, description="Años fiscales")
    fields: Dict[str, FinancialField] = Field(default_factory=dict)
    
    # Metadata
    filings_processed: int = Field(default=0)
    extraction_time_ms: Optional[float] = None
    errors: List[str] = Field(default_factory=list)
    
    def get_values(self, key: str) -> List[Optional[float]]:
        """Obtener valores de un campo alineados con períodos."""
        field = self.fields.get(key)
        return field.values if field else []
    
    def has_field(self, key: str) -> bool:
        """Verificar si tiene un campo."""
        return key in self.fields


class CorrectionResult(BaseModel):
    """
    Resultado de corrección de datos.
    
    Cuando SEC-API extrae datos incorrectos, este modelo
    documenta qué se corrigió y por qué.
    """
    field_key: str
    original_values: List[Optional[float]]
    corrected_values: List[Optional[float]]
    reason: str
    periods_affected: List[str]


class FilingInfo(BaseModel):
    """Información de un filing SEC."""
    accession_number: str
    filing_date: date
    period_of_report: date
    form_type: str = "10-K"
    
    @property
    def fiscal_year(self) -> str:
        return str(self.period_of_report.year)


class CompanyInfo(BaseModel):
    """Información básica de una empresa."""
    symbol: str
    name: Optional[str] = None
    cik: Optional[Any] = None  # Puede ser int o str
    sic: Optional[int] = None
    industry: Optional[str] = None
    sector: Optional[str] = None
    
    @property
    def is_insurance(self) -> bool:
        """Es una empresa de seguros (SIC 6300-6411)."""
        if self.sic:
            return 6300 <= self.sic <= 6411
        return False
    
    @property
    def is_bank(self) -> bool:
        """Es un banco (SIC 6000-6282)."""
        if self.sic:
            return 6000 <= self.sic <= 6282
        return False


# =============================================================================
# Mapeos de campos XBRL a nuestros modelos
# =============================================================================

class FieldMapping(BaseModel):
    """Mapeo de un label XBRL a nuestro campo."""
    xbrl_label: str
    key: str
    label: str
    order: int
    section: str
    data_type: DataType = DataType.MONETARY
    indent: int = 0
    is_subtotal: bool = False


# Mapeos por defecto para Income Statement
INCOME_FIELD_MAPPINGS: List[FieldMapping] = [
    # Revenue
    FieldMapping(
        xbrl_label="Revenue",
        key="revenue_total",
        label="Total Revenue",
        order=100,
        section="Revenue",
        is_subtotal=True
    ),
    FieldMapping(
        xbrl_label="Premiums",
        key="premiums",
        label="Premiums",
        order=110,
        section="Revenue",
        indent=1
    ),
    FieldMapping(
        xbrl_label="Investment and other income",
        key="investment_income",
        label="Investment & Other Income",
        order=120,
        section="Revenue",
        indent=1
    ),
    FieldMapping(
        xbrl_label="Products",
        key="products_revenue",
        label="Products Revenue",
        order=130,
        section="Revenue",
        indent=1
    ),
    FieldMapping(
        xbrl_label="Services",
        key="services_revenue",
        label="Services Revenue",
        order=140,
        section="Revenue",
        indent=1
    ),
    
    # Costs
    FieldMapping(
        xbrl_label="Medical costs",
        key="medical_costs",
        label="Medical Costs",
        order=200,
        section="Operating Costs",
        indent=1
    ),
    FieldMapping(
        xbrl_label="Cost of Goods and Services Sold",
        key="cogs",
        label="Cost of Goods Sold",
        order=210,
        section="Operating Costs",
        indent=1
    ),
    FieldMapping(
        xbrl_label="Selling, General and Administrative Expense",
        key="sga",
        label="SG&A Expenses",
        order=220,
        section="Operating Costs",
        indent=1
    ),
    FieldMapping(
        xbrl_label="Depreciation and Amortization",
        key="da",
        label="D&A",
        order=230,
        section="Operating Costs",
        indent=1
    ),
    FieldMapping(
        xbrl_label="Costs and Expenses",
        key="total_costs",
        label="Total Operating Costs",
        order=290,
        section="Operating Costs",
        is_subtotal=True
    ),
    
    # Operating Income
    FieldMapping(
        xbrl_label="Operating Income",
        key="operating_income",
        label="Operating Income",
        order=300,
        section="Operating Income",
        is_subtotal=True
    ),
    
    # Non-Operating
    FieldMapping(
        xbrl_label="Interest Expense",
        key="interest_expense",
        label="Interest Expense",
        order=400,
        section="Non-Operating",
        indent=1
    ),
    
    # Earnings
    FieldMapping(
        xbrl_label="Income Before Tax from Continuing Operations",
        key="pretax_income",
        label="Pretax Income",
        order=500,
        section="Earnings",
        is_subtotal=True
    ),
    FieldMapping(
        xbrl_label="Income Tax Expense",
        key="income_tax",
        label="Income Tax",
        order=510,
        section="Earnings",
        indent=1
    ),
    FieldMapping(
        xbrl_label="Net Income",
        key="net_income",
        label="Net Income",
        order=600,
        section="Earnings",
        is_subtotal=True
    ),
]

# Crear diccionario de lookup
INCOME_LABEL_TO_MAPPING: Dict[str, FieldMapping] = {
    m.xbrl_label: m for m in INCOME_FIELD_MAPPINGS
}

