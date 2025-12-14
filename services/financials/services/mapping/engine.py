"""
Mapping Engine - Sistema multi-etapa para mapear XBRL → Canonical.

Flujo:
1. CACHE (PostgreSQL) → Mapeos ya conocidos (~90% hit después de warmup)
2. REGEX PATTERNS → Patrones compilados para conceptos comunes (~8%)
3. FASB LABELS → 10,732 etiquetas US-GAAP oficiales (~1.5%)
4. LLM CLASSIFIER → Claude/GPT para conceptos desconocidos (~0.5%)

Usage:
    engine = MappingEngine()
    await engine.initialize()
    
    result = await engine.map_concept("CostOfGoodsAndServicesSold", "income")
    # result = MappingResult(canonical_key="cost_of_revenue", confidence=1.0, source="cache")
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

try:
    from .schema import CANONICAL_FIELDS, XBRL_TO_CANONICAL, get_canonical_key
    from .database import get_repository, XBRLMapping
except ImportError:
    from schema import CANONICAL_FIELDS, XBRL_TO_CANONICAL, get_canonical_key
    from database import get_repository, XBRLMapping

logger = logging.getLogger(__name__)


class MappingSource(str, Enum):
    """Source of a mapping."""
    CACHE = "cache"
    DIRECT = "direct"
    REGEX = "regex"
    FASB = "fasb"
    LLM = "llm"
    UNKNOWN = "unknown"


@dataclass
class MappingResult:
    """Result of a mapping operation."""
    canonical_key: str
    label: str
    confidence: float
    source: MappingSource
    section: Optional[str] = None
    importance: int = 50


# =============================================================================
# REGEX PATTERNS (Compilados para performance)
# =============================================================================

# Cada tupla: (compiled_regex, canonical_key, label, importance)
REGEX_PATTERNS: List[Tuple[re.Pattern, str, str, int]] = [
    # === REVENUE ===
    (re.compile(r'^revenue$|^revenues$|^net_sales|^sales_revenue|revenue.*contract.*customer|^total_revenue', re.I),
     'revenue', 'Revenue', 10000),
    (re.compile(r'^product.*revenue|products_revenue|product_sales', re.I),
     'product_revenue', 'Product Revenue', 9000),
    (re.compile(r'^service.*revenue|services_revenue', re.I),
     'service_revenue', 'Service Revenue', 9000),
    (re.compile(r'subscription.*revenue|saas.*revenue', re.I),
     'subscription_revenue', 'Subscription Revenue', 8500),
    (re.compile(r'membership.*fee|membership.*revenue', re.I),
     'membership_fees', 'Membership Fees', 8500),
    
    # === COST & GROSS PROFIT ===
    (re.compile(r'cost.*revenue|cost.*goods.*service|^cost_of_sales$|cost.*products.*services', re.I),
     'cost_of_revenue', 'Cost of Revenue', 9500),
    (re.compile(r'cost.*goods.*sold|^cogs$', re.I),
     'cost_of_goods_sold', 'Cost of Goods Sold', 9400),
    (re.compile(r'cost.*service|cost_of_services', re.I),
     'cost_of_services', 'Cost of Services', 9400),
    (re.compile(r'gross_profit|gross_margin_value', re.I),
     'gross_profit', 'Gross Profit', 9300),
    
    # === OPERATING EXPENSES ===
    # R&D: Match patterns ending with "Expense" to avoid tax assets like DeferredTaxAssetsInProcess...
    # Also match technology.*content and technology.*infrastructure for Amazon
    (re.compile(r'(?:research.*development|technology.*(?:content|infrastructure|development)).*expense$|^r_and_d$|^r&d$', re.I),
     'rd_expenses', 'R&D Expenses', 8900),
    (re.compile(r'selling.*general.*admin|sg.*a', re.I),
     'sga_expenses', 'SG&A Expenses', 8900),
    (re.compile(r'selling.*marketing|sales.*marketing|selling_expense|marketing_expense', re.I),
     'sales_marketing', 'Sales & Marketing', 8800),
    (re.compile(r'^general.*admin|^administrative_expense', re.I),
     'ga_expenses', 'G&A Expenses', 8700),
    (re.compile(r'fulfillment.*expense|fulfillment.*cost', re.I),
     'fulfillment_expense', 'Fulfillment Expense', 8600),
    (re.compile(r'pre.?opening.*cost|preopening_cost', re.I),
     'pre_opening_costs', 'Pre-Opening Costs', 8500),
    (re.compile(r'share.*based.*compensation|stock.*based.*compensation|stock_compensation', re.I),
     'stock_compensation', 'Stock-Based Compensation', 8400),
    (re.compile(r'depreciation.*amortization|depreciation_depletion', re.I),
     'depreciation_amortization', 'Depreciation & Amortization', 8300),
    (re.compile(r'restructuring.*charge|restructuring_cost', re.I),
     'restructuring_charges', 'Restructuring Charges', 7500),
    (re.compile(r'operating.*expense|costs.*expenses|total.*operating.*cost', re.I),
     'total_operating_expenses', 'Total Operating Expenses', 8000),
    
    # === OPERATING INCOME ===
    (re.compile(r'^operating_income|^income.*operations|operating_profit|profit_loss.*operating', re.I),
     'operating_income', 'Operating Income', 8000),
    
    # === NON-OPERATING ===
    (re.compile(r'^interest_expense|finance_cost$|finance_expense', re.I),
     'interest_expense', 'Interest Expense', 7500),
    (re.compile(r'^interest_income|finance_income$|interest_revenue', re.I),
     'interest_income', 'Interest Income', 7400),
    (re.compile(r'interest.*other.*income|other.*interest.*income', re.I),
     'interest_and_other_income', 'Interest & Other Income', 7350),
    (re.compile(r'investment_income|interest.*dividend.*income', re.I),
     'investment_income', 'Investment Income', 7300),
    (re.compile(r'equity.*method.*investment|income.*equity.*invest', re.I),
     'equity_method_income', 'Income from Equity Investments', 7200),
    (re.compile(r'foreign.*currency.*gain|foreign.*exchange|fx_gain_loss', re.I),
     'foreign_exchange_gain_loss', 'FX Gain (Loss)', 7100),
    (re.compile(r'gain.*loss.*sale.*securit|realized.*investment.*gain|marketable.*securit.*gain', re.I),
     'gain_loss_securities', 'Gain (Loss) on Securities', 7000),
    (re.compile(r'gain.*loss.*sale.*asset|gain.*disposal.*asset', re.I),
     'gain_loss_sale_assets', 'Gain (Loss) on Sale of Assets', 6900),
    (re.compile(r'impairment.*charge|goodwill.*impairment|asset.*impairment|write.*down', re.I),
     'impairment_charges', 'Impairment Charges', 6800),
    (re.compile(r'^other.*nonoperating|other.*income.*expense|^nonoperating', re.I),
     'other_nonoperating', 'Other Non-Operating', 6500),
    
    # === EARNINGS ===
    (re.compile(r'unusual.*item|extraordinary.*item|special.*charge', re.I),
     'unusual_items', 'Unusual Items', 6200),
    (re.compile(r'income.*before.*tax|profit.*before.*tax|ebt', re.I),
     'income_before_tax', 'Income Before Tax', 6500),
    (re.compile(r'income.*tax.*expense|provision.*income.*tax|^income_tax$', re.I),
     'income_tax', 'Income Tax Expense', 6000),
    (re.compile(r'income.*continuing.*operation', re.I),
     'income_continuing_ops', 'Income from Continuing Ops', 5800),
    (re.compile(r'income.*discontinued|discontinued.*operation', re.I),
     'income_discontinued_ops', 'Income from Discontinued Ops', 5500),
    (re.compile(r'minority.*interest|noncontrolling.*interest', re.I),
     'minority_interest', 'Minority Interest', 5400),
    (re.compile(r'^net_income$|^net_income_loss$|^profit_loss$|net_earnings', re.I),
     'net_income', 'Net Income', 5500),
    (re.compile(r'net_income.*common|net_income_available.*common', re.I),
     'net_income_to_common', 'Net Income to Common', 5450),
    
    # === PER SHARE ===
    (re.compile(r'earnings.*per.*share.*basic|^eps_basic$', re.I),
     'eps_basic', 'EPS Basic', 5000),
    (re.compile(r'earnings.*per.*share.*diluted|^eps_diluted$', re.I),
     'eps_diluted', 'EPS Diluted', 4900),
    (re.compile(r'shares.*outstanding.*basic|weighted.*average.*basic', re.I),
     'shares_basic', 'Shares Outstanding Basic', 4800),
    (re.compile(r'shares.*diluted|weighted.*average.*diluted', re.I),
     'shares_diluted', 'Shares Outstanding Diluted', 4700),
    (re.compile(r'dividend.*per.*share|dividends.*declared.*per', re.I),
     'dividend_per_share', 'Dividend per Share', 4600),
    
    # === BALANCE SHEET - ASSETS ===
    (re.compile(r'^cash$|cash.*equivalent|cash.*carrying', re.I),
     'cash', 'Cash & Equivalents', 9500),
    (re.compile(r'restricted.*cash', re.I),
     'restricted_cash', 'Restricted Cash', 9400),
    (re.compile(r'short.*term.*investment|marketable.*securities.*current', re.I),
     'st_investments', 'Short-term Investments', 9300),
    (re.compile(r'accounts.*receivable|receivables.*net.*current', re.I),
     'receivables', 'Accounts Receivable', 9200),
    (re.compile(r'^inventory$|inventory.*net$', re.I),
     'inventory', 'Inventory', 9100),
    (re.compile(r'prepaid.*expense|prepaid.*asset', re.I),
     'prepaid', 'Prepaid Expenses', 9000),
    (re.compile(r'assets.*current$|current.*assets.*total', re.I),
     'current_assets', 'Total Current Assets', 9500),
    (re.compile(r'property.*plant.*equipment.*net|ppe.*net', re.I),
     'ppe', 'PP&E Net', 8500),
    (re.compile(r'^goodwill$', re.I),
     'goodwill', 'Goodwill', 8400),
    (re.compile(r'intangible.*asset|intangibles.*net', re.I),
     'intangibles', 'Intangible Assets', 8300),
    (re.compile(r'long.*term.*investment', re.I),
     'lt_investments', 'Long-term Investments', 8200),
    (re.compile(r'^assets$|total.*assets', re.I),
     'total_assets', 'Total Assets', 10000),
    
    # === BALANCE SHEET - LIABILITIES ===
    (re.compile(r'accounts.*payable', re.I),
     'accounts_payable', 'Accounts Payable', 7500),
    (re.compile(r'accrued.*liabilit|accrued.*expense', re.I),
     'accrued_liabilities', 'Accrued Liabilities', 7400),
    (re.compile(r'deferred.*revenue.*current|contract.*liabilit.*current', re.I),
     'deferred_revenue', 'Deferred Revenue', 7300),
    (re.compile(r'short.*term.*debt|short.*term.*borrow|debt.*current', re.I),
     'st_debt', 'Short-term Debt', 7200),
    (re.compile(r'liabilities.*current$|current.*liabilities.*total', re.I),
     'current_liabilities', 'Total Current Liabilities', 7600),
    (re.compile(r'long.*term.*debt.*noncurrent|debt.*noncurrent', re.I),
     'lt_debt', 'Long-term Debt', 7000),
    (re.compile(r'^liabilities$|total.*liabilities', re.I),
     'total_liabilities', 'Total Liabilities', 7700),
    
    # === BALANCE SHEET - EQUITY ===
    (re.compile(r'common.*stock.*value', re.I),
     'common_stock', 'Common Stock', 6300),
    (re.compile(r'additional.*paid.*in.*capital|apic', re.I),
     'apic', 'Additional Paid-in Capital', 6200),
    (re.compile(r'retained.*earnings|accumulated.*deficit', re.I),
     'retained_earnings', 'Retained Earnings', 6500),
    (re.compile(r'treasury.*stock', re.I),
     'treasury_stock', 'Treasury Stock', 6100),
    (re.compile(r'stockholders.*equity$|total.*equity$|shareholders.*equity', re.I),
     'total_equity', 'Total Equity', 6600),
    
    # === CASH FLOW ===
    (re.compile(r'net.*cash.*operating|cash.*provided.*operating', re.I),
     'operating_cf', 'Cash from Operations', 10000),
    (re.compile(r'net.*cash.*investing|cash.*used.*investing', re.I),
     'investing_cf', 'Cash from Investing', 9000),
    (re.compile(r'net.*cash.*financing|cash.*used.*financing', re.I),
     'financing_cf', 'Cash from Financing', 8000),
    (re.compile(r'capital.*expenditure|payments.*property.*plant', re.I),
     'capex', 'Capital Expenditures', 8500),
    (re.compile(r'payments.*acquire.*business|acquisition.*payment', re.I),
     'acquisitions', 'Acquisitions', 8000),
    (re.compile(r'repurchase.*common.*stock|stock.*repurchased', re.I),
     'stock_repurchased', 'Stock Repurchased', 7400),
    (re.compile(r'dividend.*paid|payment.*dividend', re.I),
     'dividends_paid', 'Dividends Paid', 7500),
]


# =============================================================================
# FASB LABELS INDEX (Para búsqueda rápida)
# =============================================================================

def _build_fasb_index() -> Dict[str, str]:
    """
    Build index from FASB labels to canonical keys.
    Maps common FASB labels to our canonical fields.
    """
    # Este mapeo se expande con fasb_labels.py si existe
    index = {}
    try:
        try:
            from ..fasb_labels import FASB_LABELS
        except ImportError:
            from services.fasb_labels import FASB_LABELS
        # FASB_LABELS es {concept: label}, necesitamos invertirlo y mapear a canonical
        for concept, label in FASB_LABELS.items():
            # Intentar obtener mapeo directo
            canonical = get_canonical_key(concept)
            if canonical:
                index[concept.lower()] = canonical
    except ImportError:
        logger.debug("FASB_LABELS not found, skipping FASB index")
    return index

# Lazy load del índice FASB
_FASB_INDEX: Optional[Dict[str, str]] = None


def get_fasb_index() -> Dict[str, str]:
    """Get FASB index (lazy loaded)."""
    global _FASB_INDEX
    if _FASB_INDEX is None:
        _FASB_INDEX = _build_fasb_index()
    return _FASB_INDEX


# =============================================================================
# MAPPING ENGINE
# =============================================================================

class MappingEngine:
    """
    Multi-stage mapping engine for XBRL → Canonical conversion.
    
    Stages:
    1. Cache (DB lookup)
    2. Direct (XBRL_TO_CANONICAL dict)
    3. Regex patterns
    4. FASB labels
    5. LLM (optional, requires API key)
    """
    
    def __init__(self, use_cache: bool = True, use_llm: bool = False):
        """
        Initialize engine.
        
        Args:
            use_cache: Whether to use database cache
            use_llm: Whether to use LLM for unknown concepts
        """
        self.use_cache = use_cache
        self.use_llm = use_llm
        self._cache_initialized = False
        self._stats = {
            "cache_hits": 0,
            "direct_hits": 0,
            "regex_hits": 0,
            "fasb_hits": 0,
            "llm_hits": 0,
            "unknown": 0,
        }
    
    async def initialize(self) -> None:
        """Initialize cache connection."""
        if self.use_cache and not self._cache_initialized:
            repo = get_repository()
            try:
                await repo.connect()
                self._cache_initialized = True
                logger.info("MappingEngine: Cache initialized")
            except Exception as e:
                logger.warning(f"MappingEngine: Cache unavailable ({e}), using memory only")
                self.use_cache = False
    
    def normalize_concept(self, xbrl_concept: str) -> str:
        """
        Normalize XBRL concept name for matching.
        
        CostOfGoodsAndServicesSold → cost_of_goods_and_services_sold
        """
        # CamelCase to snake_case
        result = re.sub(r'([a-z])([A-Z])', r'\1_\2', xbrl_concept)
        return result.lower()
    
    async def map_concept(
        self,
        xbrl_concept: str,
        statement_type: str = "income",
        company_cik: Optional[str] = None
    ) -> MappingResult:
        """
        Map an XBRL concept to a canonical field.
        
        Args:
            xbrl_concept: XBRL concept name (e.g., "CostOfGoodsAndServicesSold")
            statement_type: Statement type ("income", "balance", "cashflow")
            company_cik: CIK of company (for tracking unknown concepts)
            
        Returns:
            MappingResult with canonical_key, confidence, and source
        """
        # Stage 1: Direct lookup (fastest)
        if xbrl_concept in XBRL_TO_CANONICAL:
            canonical_key = XBRL_TO_CANONICAL[xbrl_concept]
            field = CANONICAL_FIELDS.get(canonical_key)
            self._stats["direct_hits"] += 1
            return MappingResult(
                canonical_key=canonical_key,
                label=field.label if field else canonical_key,
                confidence=1.0,
                source=MappingSource.DIRECT,
                section=field.section if field else None,
                importance=field.importance if field else 100
            )
        
        # Stage 2: Cache lookup
        if self.use_cache and self._cache_initialized:
            try:
                repo = get_repository()
                mapping = await repo.get_mapping(xbrl_concept)
                if mapping:
                    field = CANONICAL_FIELDS.get(mapping.canonical_key)
                    self._stats["cache_hits"] += 1
                    # Increment usage count
                    await repo.increment_usage(xbrl_concept)
                    return MappingResult(
                        canonical_key=mapping.canonical_key,
                        label=field.label if field else mapping.canonical_key,
                        confidence=mapping.confidence,
                        source=MappingSource.CACHE,
                        section=field.section if field else None,
                        importance=field.importance if field else 100
                    )
            except Exception as e:
                logger.warning(f"Cache lookup failed: {e}")
        
        # Stage 3: Regex patterns
        normalized = self.normalize_concept(xbrl_concept)
        for pattern, canonical_key, label, importance in REGEX_PATTERNS:
            if pattern.search(normalized):
                # Save to cache for future
                await self._save_mapping(xbrl_concept, canonical_key, 0.9, "regex", statement_type, company_cik)
                self._stats["regex_hits"] += 1
                return MappingResult(
                    canonical_key=canonical_key,
                    label=label,
                    confidence=0.9,
                    source=MappingSource.REGEX,
                    section=CANONICAL_FIELDS[canonical_key].section if canonical_key in CANONICAL_FIELDS else None,
                    importance=importance
                )
        
        # Stage 4: FASB labels
        fasb_index = get_fasb_index()
        if normalized in fasb_index:
            canonical_key = fasb_index[normalized]
            field = CANONICAL_FIELDS.get(canonical_key)
            await self._save_mapping(xbrl_concept, canonical_key, 0.85, "fasb", statement_type, company_cik)
            self._stats["fasb_hits"] += 1
            return MappingResult(
                canonical_key=canonical_key,
                label=field.label if field else canonical_key,
                confidence=0.85,
                source=MappingSource.FASB,
                section=field.section if field else None,
                importance=field.importance if field else 100
            )
        
        # Stage 5: LLM (if enabled)
        if self.use_llm:
            result = await self._llm_classify(xbrl_concept, statement_type)
            if result:
                self._stats["llm_hits"] += 1
                return result
        
        # Unknown concept - track for review
        await self._track_unknown(xbrl_concept, company_cik)
        self._stats["unknown"] += 1
        
        # Generate fallback label
        words = normalized.split('_')[:4]
        auto_label = ' '.join(w.capitalize() for w in words if w not in {'and', 'the', 'of', 'to'})
        
        return MappingResult(
            canonical_key=normalized,
            label=auto_label or xbrl_concept,
            confidence=0.0,
            source=MappingSource.UNKNOWN,
            section="Other",
            importance=50
        )
    
    async def map_concepts_batch(
        self,
        concepts: List[str],
        statement_type: str = "income",
        company_cik: Optional[str] = None
    ) -> Dict[str, MappingResult]:
        """
        Map multiple concepts in batch (optimized for cache).
        
        Args:
            concepts: List of XBRL concept names
            statement_type: Statement type
            company_cik: Company CIK
            
        Returns:
            Dict mapping concept → MappingResult
        """
        results = {}
        remaining = []
        
        # First pass: direct lookups
        for concept in concepts:
            if concept in XBRL_TO_CANONICAL:
                canonical_key = XBRL_TO_CANONICAL[concept]
                field = CANONICAL_FIELDS.get(canonical_key)
                self._stats["direct_hits"] += 1
                results[concept] = MappingResult(
                    canonical_key=canonical_key,
                    label=field.label if field else canonical_key,
                    confidence=1.0,
                    source=MappingSource.DIRECT,
                    section=field.section if field else None,
                    importance=field.importance if field else 100
                )
            else:
                remaining.append(concept)
        
        # Batch cache lookup
        if self.use_cache and self._cache_initialized and remaining:
            try:
                repo = get_repository()
                cached = await repo.get_mappings_batch(remaining)
                for concept, mapping in cached.items():
                    field = CANONICAL_FIELDS.get(mapping.canonical_key)
                    self._stats["cache_hits"] += 1
                    results[concept] = MappingResult(
                        canonical_key=mapping.canonical_key,
                        label=field.label if field else mapping.canonical_key,
                        confidence=mapping.confidence,
                        source=MappingSource.CACHE,
                        section=field.section if field else None,
                        importance=field.importance if field else 100
                    )
                remaining = [c for c in remaining if c not in cached]
            except Exception as e:
                logger.warning(f"Batch cache lookup failed: {e}")
        
        # Process remaining individually
        for concept in remaining:
            results[concept] = await self.map_concept(concept, statement_type, company_cik)
        
        return results
    
    async def _save_mapping(
        self,
        xbrl_concept: str,
        canonical_key: str,
        confidence: float,
        source: str,
        statement_type: str,
        company_cik: Optional[str]
    ) -> None:
        """Save mapping to cache."""
        if self.use_cache and self._cache_initialized:
            try:
                repo = get_repository()
                await repo.add_mapping(
                    xbrl_concept=xbrl_concept,
                    canonical_key=canonical_key,
                    confidence=confidence,
                    source=source,
                    statement_type=statement_type,
                    example_company=company_cik
                )
            except Exception as e:
                logger.warning(f"Failed to save mapping: {e}")
    
    async def _track_unknown(self, xbrl_concept: str, company_cik: Optional[str]) -> None:
        """Track unknown concept for review."""
        if self.use_cache and self._cache_initialized:
            try:
                repo = get_repository()
                await repo.add_unknown_concept(
                    xbrl_concept=xbrl_concept,
                    example_company=company_cik
                )
            except Exception as e:
                logger.warning(f"Failed to track unknown concept: {e}")
    
    async def _llm_classify(
        self,
        xbrl_concept: str,
        statement_type: str
    ) -> Optional[MappingResult]:
        """
        Use LLM to classify unknown concept.
        
        Uses Grok (XAI) for intelligent classification.
        """
        try:
            try:
                from .llm_classifier import get_classifier
            except ImportError:
                from llm_classifier import get_classifier
            
            classifier = get_classifier()
            if not classifier.is_available:
                return None
            
            result = await classifier.classify_single(xbrl_concept, statement_type)
            if result and result.canonical_key:
                # Save to cache for future
                await self._save_mapping(
                    xbrl_concept, 
                    result.canonical_key, 
                    result.confidence, 
                    "llm", 
                    statement_type, 
                    None
                )
                
                field = CANONICAL_FIELDS.get(result.canonical_key)
                return MappingResult(
                    canonical_key=result.canonical_key,
                    label=field.label if field else result.canonical_key,
                    confidence=result.confidence,
                    source=MappingSource.LLM,
                    section=field.section if field else "Other",
                    importance=field.importance if field else 50
                )
        except Exception as e:
            logger.warning(f"LLM classification failed: {e}")
        
        return None
    
    def get_stats(self) -> Dict:
        """Get mapping statistics."""
        total = sum(self._stats.values())
        return {
            **self._stats,
            "total": total,
            "cache_hit_rate": self._stats["cache_hits"] / total if total > 0 else 0,
            "unknown_rate": self._stats["unknown"] / total if total > 0 else 0,
        }
    
    def reset_stats(self) -> None:
        """Reset statistics."""
        for key in self._stats:
            self._stats[key] = 0


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_engine: Optional[MappingEngine] = None


def get_engine(use_cache: bool = True, use_llm: bool = False) -> MappingEngine:
    """Get singleton engine instance."""
    global _engine
    if _engine is None:
        _engine = MappingEngine(use_cache=use_cache, use_llm=use_llm)
    return _engine

