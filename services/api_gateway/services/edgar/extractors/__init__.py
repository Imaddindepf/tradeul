"""
Edgar Extractors - Extractores especializados por tipo de estado financiero.
"""

from .income import IncomeStatementExtractor
from .segments import SegmentsExtractor

__all__ = [
    "IncomeStatementExtractor",
    "SegmentsExtractor",
]

