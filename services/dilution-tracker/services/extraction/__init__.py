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

HTML Cleaning (v4.1):
- clean_html_for_llm: Limpieza agresiva para reducir tokens ~51%
- Remueve CSS inline (style=), comentarios, iXBRL tags, etc.
"""

from .contextual_extractor import (
    ContextualDilutionExtractor,
    get_contextual_extractor,
    ExtractionContext
)

from .section_extractor import (
    clean_html_for_llm,
    clean_html_preserve_structure,
    extract_sections_for_dilution,
    html_table_to_text
)

__all__ = [
    'ContextualDilutionExtractor',
    'get_contextual_extractor',
    'ExtractionContext',
    # HTML cleaning utilities
    'clean_html_for_llm',
    'clean_html_preserve_structure',
    'extract_sections_for_dilution',
    'html_table_to_text'
]
