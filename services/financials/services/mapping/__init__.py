"""
Mapping Engine - Sistema de mapeo XBRL → Schema Universal.

Este módulo proporciona:
- Schema Universal (taxonomía propia)
- Mapeo de conceptos XBRL a campos canónicos
- Cache de mapeos en PostgreSQL
- LLM classifier para conceptos desconocidos
"""

from .schema import (
    CanonicalField,
    DataType,
    StatementType,
    CANONICAL_FIELDS,
    XBRL_TO_CANONICAL,
    INCOME_STATEMENT_SCHEMA,
    BALANCE_SHEET_SCHEMA,
    CASH_FLOW_SCHEMA,
    get_canonical_key,
    get_all_canonical_fields,
    get_canonical_keys,
    SCHEMA_STATS,
)

from .database import (
    XBRLMapping,
    MappingRepository,
    get_repository,
)

from .engine import (
    MappingEngine,
    MappingResult,
    MappingSource,
    get_engine,
)

from .llm_classifier import (
    LLMClassifier,
    LLMClassification,
    get_classifier,
)

__all__ = [
    # Schema
    "CanonicalField",
    "DataType",
    "StatementType",
    "CANONICAL_FIELDS",
    "XBRL_TO_CANONICAL",
    "INCOME_STATEMENT_SCHEMA",
    "BALANCE_SHEET_SCHEMA",
    "CASH_FLOW_SCHEMA",
    "get_canonical_key",
    "get_all_canonical_fields",
    "get_canonical_keys",
    "SCHEMA_STATS",
    # Database
    "XBRLMapping",
    "MappingRepository",
    "get_repository",
    # Engine
    "MappingEngine",
    "MappingResult",
    "MappingSource",
    "get_engine",
    # LLM
    "LLMClassifier",
    "LLMClassification",
    "get_classifier",
]

