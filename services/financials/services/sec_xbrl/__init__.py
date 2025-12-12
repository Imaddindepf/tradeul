"""
SEC XBRL Service - Extracción de datos financieros via SEC-API.

Módulos:
- service.py: Servicio principal
- extractors.py: Extracción de datos XBRL
- calculators.py: Métricas calculadas
- structures.py: Estructuras jerárquicas
- splits.py: Ajustes por stock splits
"""

from .service import SECXBRLService
from .extractors import XBRLExtractor
from .calculators import FinancialCalculator
from .structures import get_structure, CUSTOM_LABELS
from .splits import SplitAdjuster

__all__ = [
    "SECXBRLService",
    "XBRLExtractor",
    "FinancialCalculator",
    "get_structure",
    "CUSTOM_LABELS",
    "SplitAdjuster",
]
