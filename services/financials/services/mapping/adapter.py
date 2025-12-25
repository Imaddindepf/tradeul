"""
Adapter to integrate MappingEngine with existing extractors.py.

Provides sync wrappers for async mapping functions, allowing
gradual migration from the old pattern-based system to the new
multi-stage mapping engine.

Key Design Decisions:
1. Direct lookups (XBRL_TO_CANONICAL) and regex patterns are SYNC - no async overhead
2. DB cache and LLM are ASYNC but only used when available and when not in event loop
3. Falls back gracefully when async operations can't be performed

Usage in extractors.py:
    from services.mapping.adapter import XBRLMapper
    
    mapper = XBRLMapper()
    key, label, importance, dtype, confidence, source = mapper.detect_concept(field_name)

Quality Score System:
    - confidence: 0.0-1.0 score indicating mapping reliability
    - source: "direct" | "regex" | "fasb" | "fallback"
"""

import re
import logging
import asyncio
import threading
from typing import Dict, List, Tuple, Optional, NamedTuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


@dataclass
class MappingResult:
    """Result of a concept mapping with quality metadata."""
    canonical_key: str
    label: str
    importance: int
    data_type: str
    confidence: float  # 0.0-1.0
    source: str  # "direct", "regex", "fasb", "fallback"
    
    def to_tuple(self) -> Tuple[str, str, int, str]:
        """Legacy tuple format for backwards compatibility."""
        return (self.canonical_key, self.label, self.importance, self.data_type)
    
    def to_tuple_extended(self) -> Tuple[str, str, int, str, float, str]:
        """Extended tuple with quality metadata."""
        return (self.canonical_key, self.label, self.importance, self.data_type, 
                self.confidence, self.source)

# Thread pool for async operations in sync context
_executor: Optional[ThreadPoolExecutor] = None


def _get_executor() -> ThreadPoolExecutor:
    """Get or create thread pool executor."""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mapping_")
    return _executor


class XBRLMapper:
    """
    Adapter class for XBRL → Canonical mapping.
    
    Provides synchronous interface compatible with existing extractors.
    Uses a multi-stage approach:
    1. Memory cache (instant)
    2. Direct XBRL_TO_CANONICAL lookup (instant)
    3. Regex patterns (fast)
    4. DB cache (async, if available)
    5. FASB labels (fast)
    6. LLM (async, if enabled)
    
    Stages 1-3 and 5 are completely synchronous and don't require event loop.
    Stages 4 and 6 are attempted only when safe (no running event loop).
    """
    
    def __init__(self, use_engine: bool = True, use_llm: bool = False):
        """
        Initialize mapper.
        
        Args:
            use_engine: Whether to use the full MappingEngine capabilities
            use_llm: Whether to enable LLM for unknown concepts
        """
        self.use_llm = use_llm
        self._cache: Dict[str, Tuple[str, str, int, str]] = {}
        
        # Load schemas (sync, no DB needed)
        self._direct_mappings: Dict[str, str] = {}
        self._canonical_fields: Dict = {}
        self._regex_patterns: List = []
        self._fasb_index: Dict[str, str] = {}
        
        self._load_schemas()
        logger.info("XBRLMapper: Initialized with sync-first approach")
    
    def _load_schemas(self):
        """Load all schemas and patterns (sync operation)."""
        try:
            try:
                from .schema import XBRL_TO_CANONICAL, CANONICAL_FIELDS, get_all_xbrl_concepts
                from .engine import REGEX_PATTERNS, get_fasb_index
            except ImportError:
                from schema import XBRL_TO_CANONICAL, CANONICAL_FIELDS, get_all_xbrl_concepts
                from engine import REGEX_PATTERNS, get_fasb_index
            
            # Usar get_all_xbrl_concepts() que incluye XBRL_TO_CANONICAL + CONCEPT_GROUPS
            self._direct_mappings = get_all_xbrl_concepts()
            self._canonical_fields = CANONICAL_FIELDS
            self._regex_patterns = REGEX_PATTERNS
            self._fasb_index = get_fasb_index()
            
            # Load SEC Tier 2 auto-generated mappings
            tier2_count = 0
            try:
                try:
                    from .sec_tier2 import SEC_TIER2_MAPPINGS
                except ImportError:
                    from sec_tier2 import SEC_TIER2_MAPPINGS
                
                # Merge Tier 2 mappings (Tier 1 manual has priority)
                for xbrl_tag, canonical_key in SEC_TIER2_MAPPINGS.items():
                    if xbrl_tag not in self._direct_mappings:
                        self._direct_mappings[xbrl_tag] = canonical_key
                        tier2_count += 1
            except ImportError:
                logger.debug("SEC Tier 2 mappings not available")
            except Exception as e:
                logger.warning(f"Failed to load SEC Tier 2 mappings: {e}")
            
            logger.info(f"XBRLMapper: Loaded {len(self._direct_mappings)} XBRL mappings "
                        f"(+{tier2_count} Tier 2), {len(self._regex_patterns)} regex, "
                        f"{len(self._fasb_index)} FASB")
        except Exception as e:
            logger.error(f"Failed to load schemas: {e}")
    
    def _normalize_concept(self, name: str) -> str:
        """Convert CamelCase to snake_case."""
        s1 = re.sub(r'([a-z])([A-Z])', r'\1_\2', name)
        return s1.lower()
    
    def detect_concept(
        self,
        field_name: str,
        statement_type: str = "income",
        extended: bool = False
    ) -> Tuple[str, str, int, str]:
        """
        Detect financial concept from XBRL field name.
        
        Uses sync-first approach for maximum reliability:
        1. Memory cache
        2. Direct mappings (confidence=1.0)
        3. Regex patterns (confidence=0.95)
        4. FASB labels (confidence=0.9)
        5. Fallback generation (confidence=0.5)
        
        Args:
            field_name: XBRL field name (CamelCase or snake_case)
            statement_type: Statement type hint (income, balance, cashflow)
            extended: If True, returns extended tuple with confidence/source
            
        Returns:
            Tuple of (canonical_key, display_label, importance_score, data_type)
            If extended=True: adds (confidence, source)
        """
        # Stage 1: Memory cache (instant)
        cache_key = f"{field_name}:{statement_type}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if extended and isinstance(cached, MappingResult):
                return cached.to_tuple_extended()
            elif isinstance(cached, MappingResult):
                return cached.to_tuple()
            return cached
        
        result: Optional[MappingResult] = None
        
        # Stage 2: Direct XBRL_TO_CANONICAL lookup (instant, confidence=1.0)
        if field_name in self._direct_mappings:
            canonical_key = self._direct_mappings[field_name]
            result = self._build_result(canonical_key, confidence=1.0, source="direct")
            if result:
                self._cache[cache_key] = result
                return result.to_tuple_extended() if extended else result.to_tuple()
        
        # Stage 3: Regex patterns (fast, confidence=0.95)
        normalized = self._normalize_concept(field_name)
        result = self._match_regex(normalized, confidence=0.95, source="regex")
        if result:
            self._cache[cache_key] = result
            return result.to_tuple_extended() if extended else result.to_tuple()
        
        # Stage 4: FASB labels (fast, confidence=0.9)
        if normalized in self._fasb_index:
            canonical_key = self._fasb_index[normalized]
            result = self._build_result(canonical_key, confidence=0.9, source="fasb")
            if result:
                self._cache[cache_key] = result
                return result.to_tuple_extended() if extended else result.to_tuple()
        
        # Stage 5: Fallback - generate from name (confidence=0.5)
        result = self._generate_fallback(normalized, field_name)
        self._cache[cache_key] = result
        return result.to_tuple_extended() if extended else result.to_tuple()
    
    def _build_result(
        self, 
        canonical_key: str, 
        confidence: float = 1.0, 
        source: str = "direct"
    ) -> Optional[MappingResult]:
        """Build MappingResult from canonical key."""
        field = self._canonical_fields.get(canonical_key)
        if field:
            return MappingResult(
                canonical_key=canonical_key,
                label=field.label,
                importance=field.importance,
                data_type=field.data_type.value if hasattr(field.data_type, 'value') else str(field.data_type),
                confidence=confidence,
                source=source
            )
        return None
    
    def _match_regex(
        self, 
        normalized_name: str, 
        confidence: float = 0.95, 
        source: str = "regex"
    ) -> Optional[MappingResult]:
        """Match against regex patterns."""
        for pattern, canonical_key, label, importance in self._regex_patterns:
            if pattern.search(normalized_name):
                field = self._canonical_fields.get(canonical_key)
                data_type = "monetary"
                if field and hasattr(field.data_type, 'value'):
                    data_type = field.data_type.value
                return MappingResult(
                    canonical_key=canonical_key,
                    label=label,
                    importance=importance,
                    data_type=data_type,
                    confidence=confidence,
                    source=source
                )
        return None
    
    def _generate_fallback(
        self,
        normalized_name: str,
        original_name: str
    ) -> MappingResult:
        """Generate fallback result for unknown concepts."""
        words = normalized_name.split('_')[:4]
        auto_label = ' '.join(
            w.capitalize() for w in words 
            if w not in {'and', 'the', 'of', 'to'}
        )
        return MappingResult(
            canonical_key=normalized_name,
            label=auto_label or original_name,
            importance=50,  # Low importance for unknown
            data_type="monetary",
            confidence=0.5,  # Low confidence for fallback
            source="fallback"
        )
    
    def detect_concepts_batch(
        self,
        field_names: List[str],
        statement_type: str = "income"
    ) -> Dict[str, Tuple[str, str, int, str]]:
        """
        Detect concepts for multiple fields at once.
        
        Args:
            field_names: List of XBRL field names
            statement_type: Statement type hint
            
        Returns:
            Dict mapping field_name → (canonical_key, label, importance, data_type)
        """
        results = {}
        for name in field_names:
            results[name] = self.detect_concept(name, statement_type)
        return results
    
    def get_stats(self) -> Dict:
        """Get mapping statistics."""
        return {
            "cache_size": len(self._cache),
            "direct_mappings": len(self._direct_mappings),
            "regex_patterns": len(self._regex_patterns),
            "fasb_entries": len(self._fasb_index),
        }
    
    def clear_cache(self):
        """Clear the local cache."""
        self._cache.clear()


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_mapper: Optional[XBRLMapper] = None
_mapper_lock = threading.Lock()


def get_mapper(use_engine: bool = True, use_llm: bool = False) -> XBRLMapper:
    """Get singleton mapper instance (thread-safe)."""
    global _mapper
    if _mapper is None:
        with _mapper_lock:
            if _mapper is None:  # Double-check
                _mapper = XBRLMapper(use_engine=use_engine, use_llm=use_llm)
    return _mapper


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def detect_concept(field_name: str, statement_type: str = "income") -> Tuple[str, str, int, str]:
    """
    Convenience function for concept detection.
    
    Can be used as drop-in replacement in extractors.py:
        from services.mapping.adapter import detect_concept
        canonical_key, label, importance, data_type = detect_concept(field_name)
    """
    return get_mapper().detect_concept(field_name, statement_type)
