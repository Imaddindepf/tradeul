"""
Extraction Services
===================
v4: ContextualDilutionExtractor - Extracción con contexto largo de Gemini

Pipeline:
1. Fetch filings de SEC-API.io (últimos 3 años)
2. Categorizar por File Number (registration chains)
3. Procesar chains con Gemini (S-1, F-3, 424B, etc.)
4. Procesar material events (6-K, 8-K) con contexto acumulado
5. Normalizar nombres y filtrar warrants de placement agents
"""

from .contextual_extractor import (
    ContextualDilutionExtractor,
    get_contextual_extractor,
    ExtractionContext
)

__all__ = [
    'ContextualDilutionExtractor',
    'get_contextual_extractor',
    'ExtractionContext'
]
