"""
LLM Verification Service
========================
Capa de verificación usando Gemini 3 Pro y Grok 4 con búsqueda en internet
para validar datos de dilución extraídos de SEC filings.
"""

from .llm_verifier import LLMDilutionVerifier, VerificationResult, get_llm_verifier

__all__ = ["LLMDilutionVerifier", "VerificationResult", "get_llm_verifier"]
