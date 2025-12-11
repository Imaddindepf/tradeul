"""
Edgar Service - Extracción de datos financieros via edgartools.

Este paquete proporciona un servicio profesional para:
- Extraer datos de Income Statement, Balance Sheet, Cash Flow
- Complementar/corregir datos de SEC-API
- Cache de dos niveles (memoria + Redis)
- Modelos Pydantic para tipado estricto

Estructura:
    edgar/
    ├── __init__.py          # Este archivo
    ├── models.py            # Modelos Pydantic
    ├── service.py           # Servicio principal
    ├── cache.py             # Gestión de cache
    ├── corrections.py       # Correcciones de datos
    └── extractors/
        ├── __init__.py
        └── income.py        # Extractor de Income Statement

Uso básico:
    from services.edgar import EdgarService, get_edgar_service
    
    # Obtener servicio
    service = get_edgar_service()
    
    # Obtener datos enriquecidos
    enrichment = await service.get_enrichment("UNH")
    
    # Corregir datos de SEC-API
    corrections = await service.correct_sec_api_data(
        symbol="UNH",
        sec_api_fields=income_fields,
        periods=periods
    )
    
    # Obtener info de empresa
    company = await service.get_company_info("UNH")
    print(f"SIC: {company.sic}, Is Insurance: {company.is_insurance}")

Modelos:
    - FinancialField: Campo financiero con valores
    - EnrichmentResult: Resultado de extracción
    - CorrectionResult: Resultado de corrección
    - CompanyInfo: Info de empresa
"""

from .service import EdgarService, get_edgar_service
from .models import (
    FinancialField,
    EnrichmentResult,
    CorrectionResult,
    CompanyInfo,
    StatementType,
    DataType,
)
from .cache import EdgarCache, get_edgar_cache
from .corrections import DataCorrector

__all__ = [
    # Service
    "EdgarService",
    "get_edgar_service",
    
    # Models
    "FinancialField",
    "EnrichmentResult", 
    "CorrectionResult",
    "CompanyInfo",
    "StatementType",
    "DataType",
    
    # Cache
    "EdgarCache",
    "get_edgar_cache",
    
    # Corrections
    "DataCorrector",
]

__version__ = "1.0.0"

