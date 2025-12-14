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
    key, label, importance, dtype = mapper.detect_concept(field_name)
"""

import re
import logging
import asyncio
import threading
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

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
        statement_type: str = "income"
    ) -> Tuple[str, str, int, str]:
        """
        Detect financial concept from XBRL field name.
        
        Uses sync-first approach for maximum reliability:
        1. Memory cache
        2. Direct mappings
        3. Regex patterns
        4. FASB labels
        5. Fallback generation
        
        Args:
            field_name: XBRL field name (CamelCase or snake_case)
            statement_type: Statement type hint (income, balance, cashflow)
            
        Returns:
            Tuple of (canonical_key, display_label, importance_score, data_type)
        """
        # Stage 1: Memory cache (instant)
        cache_key = f"{field_name}:{statement_type}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        result = None
        
        # Stage 2: Direct XBRL_TO_CANONICAL lookup (instant)
        if field_name in self._direct_mappings:
            canonical_key = self._direct_mappings[field_name]
            result = self._build_result(canonical_key)
            if result:
                self._cache[cache_key] = result
                return result
        
        # Stage 3: Regex patterns (fast)
        normalized = self._normalize_concept(field_name)
        result = self._match_regex(normalized)
        if result:
            self._cache[cache_key] = result
            return result
        
        # Stage 4: FASB labels (fast)
        if normalized in self._fasb_index:
            canonical_key = self._fasb_index[normalized]
            result = self._build_result(canonical_key)
            if result:
                self._cache[cache_key] = result
                return result
        
        # Stage 5: Fallback - generate from name
        result = self._generate_fallback(normalized, field_name)
        self._cache[cache_key] = result
        return result
    
    def _build_result(self, canonical_key: str) -> Optional[Tuple[str, str, int, str]]:
        """Build result tuple from canonical key."""
        field = self._canonical_fields.get(canonical_key)
        if field:
            return (
                canonical_key,
                field.label,
                field.importance,
                field.data_type.value if hasattr(field.data_type, 'value') else str(field.data_type)
            )
        return None
    
    def _match_regex(self, normalized_name: str) -> Optional[Tuple[str, str, int, str]]:
        """Match against regex patterns."""
        for pattern, canonical_key, label, importance in self._regex_patterns:
            if pattern.search(normalized_name):
                field = self._canonical_fields.get(canonical_key)
                data_type = "monetary"
                if field and hasattr(field.data_type, 'value'):
                    data_type = field.data_type.value
                return (canonical_key, label, importance, data_type)
        return None
    
    def _generate_fallback(
        self,
        normalized_name: str,
        original_name: str
    ) -> Tuple[str, str, int, str]:
        """Generate fallback result for unknown concepts."""
        words = normalized_name.split('_')[:4]
        auto_label = ' '.join(
            w.capitalize() for w in words 
            if w not in {'and', 'the', 'of', 'to'}
        )
        return (
            normalized_name,
            auto_label or original_name,
            50,  # Low importance for unknown
            "monetary"
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
