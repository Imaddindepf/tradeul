"""
Category Classifier Service
Classifies events into categories based on tags and keywords
Supports dynamic configuration loading from database
"""

from typing import Optional, Tuple, Set, Dict, List, TYPE_CHECKING
import re
import structlog

from models.polymarket import PolymarketEvent
from models.categories import (
    DEFAULT_CATEGORIES,
    DEFAULT_BLACKLIST_TAGS,
    DEFAULT_WHITELIST_TAGS,
    CategoryConfig,
    SubcategoryConfig,
)

if TYPE_CHECKING:
    from .config_manager import LoadedConfig

logger = structlog.get_logger(__name__)


class CategoryClassifier:
    """
    Classifies events into categories and subcategories
    Uses a combination of:
    1. Tag-based classification (whitelist/blacklist)
    2. Keyword pattern matching in titles
    3. Volume-based relevance scoring
    
    Supports dynamic configuration updates from database.
    """
    
    def __init__(
        self,
        categories: Optional[Dict[str, CategoryConfig]] = None,
        blacklist_tags: Optional[Set[str]] = None,
        whitelist_tags: Optional[Set[str]] = None,
        tag_category_mapping: Optional[Dict[str, Tuple[str, Optional[str]]]] = None,
        tag_relevance_boost: Optional[Dict[str, float]] = None,
    ):
        self.categories = categories or DEFAULT_CATEGORIES
        self.blacklist_tags = blacklist_tags or DEFAULT_BLACKLIST_TAGS
        self.whitelist_tags = whitelist_tags or DEFAULT_WHITELIST_TAGS
        self.tag_category_mapping = tag_category_mapping or {}
        self.tag_relevance_boost = tag_relevance_boost or {}
        
        # Precompile keyword patterns for efficiency
        self._keyword_patterns: Dict[str, Dict[str, re.Pattern]] = {}
        self._compile_patterns()
    
    @classmethod
    def from_loaded_config(cls, config: "LoadedConfig") -> "CategoryClassifier":
        """Create classifier from LoadedConfig (from database or defaults)"""
        return cls(
            categories=config.categories,
            blacklist_tags=config.blacklist_tags,
            whitelist_tags=config.whitelist_tags,
            tag_category_mapping=config.tag_category_mapping,
            tag_relevance_boost=config.tag_relevance_boost,
        )
    
    def update_from_config(self, config: "LoadedConfig") -> None:
        """Update classifier with new configuration"""
        self.categories = config.categories
        self.blacklist_tags = config.blacklist_tags
        self.whitelist_tags = config.whitelist_tags
        self.tag_category_mapping = config.tag_category_mapping
        self.tag_relevance_boost = config.tag_relevance_boost
        self._keyword_patterns.clear()
        self._compile_patterns()
        logger.info("classifier_config_updated", categories=len(self.categories))
    
    def _compile_patterns(self) -> None:
        """Precompile regex patterns for all keywords"""
        for cat_id, category in self.categories.items():
            self._keyword_patterns[cat_id] = {}
            for subcat_id, subcat in category.subcategories.items():
                if subcat.keywords:
                    # Create pattern that matches any keyword
                    pattern_str = "|".join(
                        re.escape(kw) for kw in subcat.keywords
                    )
                    self._keyword_patterns[cat_id][subcat_id] = re.compile(
                        pattern_str,
                        re.IGNORECASE
                    )
    
    def is_relevant(self, event: PolymarketEvent) -> bool:
        """
        Determine if an event is relevant for our platform
        
        Returns True if:
        - Has any whitelist tag, OR
        - Has no blacklist tags AND (has relevant keywords OR high volume)
        
        Returns False if:
        - Has any blacklist tag (unless also has whitelist tag)
        """
        tag_slugs = set(event.get_tag_slugs())
        tag_labels = set(t.lower() for t in event.get_tag_labels())
        all_tags = tag_slugs | tag_labels
        
        # Check for whitelist tags (always include)
        has_whitelist = bool(all_tags & self.whitelist_tags)
        
        # Check for blacklist tags
        has_blacklist = bool(all_tags & self.blacklist_tags)
        
        # Whitelist overrides blacklist
        if has_whitelist:
            return True
        
        # Pure blacklist = exclude
        if has_blacklist:
            return False
        
        # No explicit tags - check keywords and volume
        title = (event.title or "").lower()
        
        # Check for relevant keywords
        for cat_id, subcats in self._keyword_patterns.items():
            for subcat_id, pattern in subcats.items():
                if pattern.search(title):
                    return True
        
        # High volume events might be relevant even without tags
        if event.volume and event.volume > 500000:
            return True
        
        # Default: exclude unknown events
        return False
    
    def classify(
        self,
        event: PolymarketEvent
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Classify an event into category and subcategory
        
        Returns:
            Tuple of (category_name, subcategory_name) or (None, None)
        """
        title = (event.title or "").lower()
        tag_slugs = set(event.get_tag_slugs())
        tag_labels = set(t.lower() for t in event.get_tag_labels())
        
        # Try keyword-based classification first (more accurate)
        for cat_id, category in sorted(
            self.categories.items(),
            key=lambda x: x[1].priority
        ):
            for subcat_id, subcat in sorted(
                category.subcategories.items(),
                key=lambda x: x[1].priority
            ):
                pattern = self._keyword_patterns.get(cat_id, {}).get(subcat_id)
                if pattern and pattern.search(title):
                    return category.name, subcat.name
        
        # Fallback: tag-based classification using dynamic mapping from DB
        all_tags = tag_slugs | tag_labels
        
        # First try dynamic tag_category_mapping from database
        for tag in all_tags:
            if tag in self.tag_category_mapping:
                cat_id, subcat_id = self.tag_category_mapping[tag]
                category = self.categories.get(cat_id)
                if category:
                    subcat_name = None
                    if subcat_id and subcat_id in category.subcategories:
                        subcat_name = category.subcategories[subcat_id].name
                    return category.name, subcat_name
        
        # Static fallback for basic tag matching
        category_tag_map = {
            "geopolitics": {"geopolitics", "world", "world-affairs", "international-affairs"},
            "macro": {"economy", "fed", "interest-rates", "inflation", "recession"},
            "corporate": {"finance", "business", "ipo", "merger", "stocks"},
            "crypto": {"crypto", "bitcoin", "ethereum", "defi"},
            "tech": {"tech", "ai", "technology"},
        }
        
        for cat_id, cat_tags in category_tag_map.items():
            if all_tags & cat_tags:
                category = self.categories.get(cat_id)
                if category:
                    return category.name, None
        
        return None, None
    
    def calculate_relevance_score(self, event: PolymarketEvent) -> float:
        """
        Calculate a relevance score for sorting events
        
        Score is based on:
        - Volume (higher = more relevant)
        - Tag matches (whitelist = bonus)
        - Keyword matches (more specific = higher score)
        """
        score = 0.0
        
        # Volume contribution (log scale, normalized)
        if event.volume and event.volume > 0:
            import math
            score += min(math.log10(event.volume) / 10, 1.0) * 0.4
        
        # 24h volume bonus (active markets)
        if event.volume_24hr and event.volume_24hr > 10000:
            score += 0.2
        
        # Tag contributions
        tag_slugs = set(event.get_tag_slugs())
        tag_labels = set(t.lower() for t in event.get_tag_labels())
        all_tags = tag_slugs | tag_labels
        
        whitelist_matches = len(all_tags & self.whitelist_tags)
        score += min(whitelist_matches * 0.1, 0.3)
        
        # Apply tag-specific relevance boosts from database
        for tag in all_tags:
            if tag in self.tag_relevance_boost:
                score += self.tag_relevance_boost[tag]
        
        # Keyword match bonus
        title = (event.title or "").lower()
        keyword_matches = 0
        for cat_patterns in self._keyword_patterns.values():
            for pattern in cat_patterns.values():
                if pattern.search(title):
                    keyword_matches += 1
        
        score += min(keyword_matches * 0.05, 0.1)
        
        return min(score, 1.0)
    
    def filter_and_classify_events(
        self,
        events: List[PolymarketEvent]
    ) -> List[Tuple[PolymarketEvent, str, Optional[str], float]]:
        """
        Filter relevant events and classify them
        
        Returns:
            List of tuples: (event, category, subcategory, relevance_score)
        """
        results = []
        
        for event in events:
            if not self.is_relevant(event):
                continue
            
            category, subcategory = self.classify(event)
            if category is None:
                category = "Other"
            
            score = self.calculate_relevance_score(event)
            results.append((event, category, subcategory, score))
        
        # Sort by relevance score (descending)
        results.sort(key=lambda x: x[3], reverse=True)
        
        logger.info(
            "events_classified",
            total_input=len(events),
            relevant=len(results)
        )
        
        return results
