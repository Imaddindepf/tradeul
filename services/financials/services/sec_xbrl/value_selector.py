"""
Professional Value Selection System for XBRL Data.

Implements intelligent selection of financial values when multiple
sources/concepts exist for the same metric.

Key Principles:
1. Section Priority: Income Statement > Balance Sheet > Disclosures > Notes
2. Segment Priority: Consolidated (no segment) > Segmented values
3. Concept Hierarchy: Primary concepts > Alternative concepts > Custom extensions
4. Period Matching: Exact fiscal year match required, NO fallbacks

This eliminates the naive "prefer larger value" heuristic that causes
incorrect data extraction (e.g., ASTS revenue bug).
"""

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import IntEnum
import logging

logger = logging.getLogger(__name__)


class SectionPriority(IntEnum):
    """Priority levels for XBRL sections. Lower = Higher priority."""
    INCOME_STATEMENT = 1
    BALANCE_SHEET = 2
    CASH_FLOW = 3
    COMPREHENSIVE_INCOME = 4
    EQUITY_STATEMENT = 5
    DISCLOSURE_REVENUE = 10
    DISCLOSURE_DETAIL = 15
    NOTES = 20
    OTHER = 99


@dataclass
class ValueCandidate:
    """A candidate value with full metadata for selection."""
    value: float
    field_name: str              # Original XBRL concept name
    section_name: str            # Section where found
    section_priority: int        # Priority score (lower = better)
    has_segment: bool            # True if value has segment dimension
    segment_info: Optional[str]  # Segment details if any
    period_start: str            # Period start date
    period_end: str              # Period end date
    concept_priority: int        # Concept-specific priority (lower = better)
    
    @property
    def total_priority(self) -> int:
        """Combined priority score. Lower = better."""
        segment_penalty = 100 if self.has_segment else 0
        return self.section_priority + self.concept_priority + segment_penalty


class ValueSelector:
    """
    Professional value selection system.
    
    Selects the most appropriate value when multiple XBRL concepts
    map to the same canonical field.
    """
    
    # Section name patterns → Priority
    SECTION_PATTERNS = {
        # Primary statements (highest priority)
        'StatementsOfIncome': SectionPriority.INCOME_STATEMENT,
        'ConsolidatedStatementsOfIncome': SectionPriority.INCOME_STATEMENT,
        'ConsolidatedStatementsOfOperations': SectionPriority.INCOME_STATEMENT,
        'IncomeStatement': SectionPriority.INCOME_STATEMENT,
        'StatementsOfOperations': SectionPriority.INCOME_STATEMENT,
        'StatementOfIncome': SectionPriority.INCOME_STATEMENT,
        
        'BalanceSheet': SectionPriority.BALANCE_SHEET,
        'StatementsOfFinancialPosition': SectionPriority.BALANCE_SHEET,
        'ConsolidatedBalanceSheets': SectionPriority.BALANCE_SHEET,
        
        'CashFlowStatement': SectionPriority.CASH_FLOW,
        'StatementsOfCashFlows': SectionPriority.CASH_FLOW,
        'ConsolidatedStatementsOfCashFlows': SectionPriority.CASH_FLOW,
        
        # Disclosures (lower priority)
        'RevenueFromContractWithCustomer': SectionPriority.DISCLOSURE_REVENUE,
        'DisaggregationOfRevenue': SectionPriority.DISCLOSURE_REVENUE,
        'DisclosureRevenue': SectionPriority.DISCLOSURE_REVENUE,
        
        # Notes and details (lowest priority)
        'Details': SectionPriority.DISCLOSURE_DETAIL,
        'Narrative': SectionPriority.NOTES,
        'Policies': SectionPriority.NOTES,
    }
    
    # Primary concepts for key metrics (higher priority)
    # These are the "official" US-GAAP concepts for each metric
    CONCEPT_PRIORITY = {
        # Revenue - Primary
        'RevenueFromContractWithCustomerIncludingAssessedTax': 1,
        'Revenues': 2,
        'RevenueFromContractWithCustomerExcludingAssessedTax': 5,  # Lower priority
        'SalesRevenueNet': 3,
        'SalesRevenueGoodsNet': 4,
        'SalesRevenueServicesNet': 4,
        
        # Cost of Revenue
        'CostOfGoodsAndServicesSold': 1,
        'CostOfRevenue': 2,
        'CostOfGoodsSold': 3,
        
        # Operating Income
        'OperatingIncomeLoss': 1,
        'IncomeLossFromOperations': 2,
        
        # Net Income
        'NetIncomeLoss': 1,
        'ProfitLoss': 2,
        'NetIncomeLossAvailableToCommonStockholdersBasic': 3,
        
        # EPS
        'EarningsPerShareBasic': 1,
        'EarningsPerShareBasicAndDiluted': 2,
        
        # Default for unknown concepts
        '_default': 50
    }
    
    @classmethod
    def get_section_priority(cls, section_name: str) -> int:
        """Get priority for a section name."""
        # Check exact matches first
        for pattern, priority in cls.SECTION_PATTERNS.items():
            if pattern in section_name:
                return priority
        
        # Check for common keywords
        section_lower = section_name.lower()
        if 'income' in section_lower or 'operations' in section_lower:
            return SectionPriority.INCOME_STATEMENT
        if 'balance' in section_lower or 'position' in section_lower:
            return SectionPriority.BALANCE_SHEET
        if 'cashflow' in section_lower or 'cash_flow' in section_lower:
            return SectionPriority.CASH_FLOW
        if 'disclosure' in section_lower:
            return SectionPriority.DISCLOSURE_DETAIL
        if 'detail' in section_lower:
            return SectionPriority.DISCLOSURE_DETAIL
        if 'narrative' in section_lower or 'note' in section_lower:
            return SectionPriority.NOTES
        
        return SectionPriority.OTHER
    
    @classmethod
    def get_concept_priority(cls, concept_name: str) -> int:
        """Get priority for a concept name."""
        return cls.CONCEPT_PRIORITY.get(concept_name, cls.CONCEPT_PRIORITY['_default'])
    
    @classmethod
    def extract_value_candidates(
        cls,
        xbrl_data: Dict[str, Any],
        field_name: str,
        fiscal_year: str
    ) -> List[ValueCandidate]:
        """
        Extract all candidate values for a field across all sections.
        
        Args:
            xbrl_data: Full XBRL data dictionary
            field_name: XBRL concept name to search for
            fiscal_year: Target fiscal year (e.g., "2024")
            
        Returns:
            List of ValueCandidate objects sorted by priority (best first)
        """
        candidates = []
        fiscal_year_str = str(fiscal_year)[:4]
        
        for section_name, section_data in xbrl_data.items():
            if not isinstance(section_data, dict):
                continue
            
            values = section_data.get(field_name, [])
            if not isinstance(values, list):
                continue
            
            section_priority = cls.get_section_priority(section_name)
            concept_priority = cls.get_concept_priority(field_name)
            
            for item in values:
                if not isinstance(item, dict) or item.get('value') is None:
                    continue
                
                period = item.get('period', {})
                end_date = period.get('endDate', '') or period.get('instant', '')
                start_date = period.get('startDate', '')
                
                # Only accept exact year matches
                if not end_date or end_date[:4] != fiscal_year_str:
                    continue
                
                try:
                    value = float(item['value'])
                except (ValueError, TypeError):
                    continue
                
                # Check for segment
                segment = item.get('segment', {})
                has_segment = bool(segment)
                segment_info = None
                if has_segment:
                    if isinstance(segment, dict):
                        segment_info = f"{segment.get('dimension', '')}:{segment.get('value', '')}"
                    else:
                        segment_info = str(segment)
                
                candidate = ValueCandidate(
                    value=value,
                    field_name=field_name,
                    section_name=section_name,
                    section_priority=section_priority,
                    has_segment=has_segment,
                    segment_info=segment_info,
                    period_start=start_date,
                    period_end=end_date,
                    concept_priority=concept_priority
                )
                candidates.append(candidate)
        
        # Sort by total priority (lower = better)
        candidates.sort(key=lambda c: c.total_priority)
        
        return candidates
    
    @classmethod
    def select_best_value(
        cls,
        candidates: List[ValueCandidate],
        prefer_consolidated: bool = True
    ) -> Optional[ValueCandidate]:
        """
        Select the best value from candidates.
        
        Args:
            candidates: List of ValueCandidate objects
            prefer_consolidated: If True, prefer values without segments
            
        Returns:
            Best ValueCandidate or None
        """
        if not candidates:
            return None
        
        if prefer_consolidated:
            # First try to find consolidated (no segment) value
            consolidated = [c for c in candidates if not c.has_segment]
            if consolidated:
                return consolidated[0]  # Already sorted by priority
        
        # Return best overall candidate
        return candidates[0]
    
    @classmethod
    def select_revenue_value(
        cls,
        xbrl_data: Dict[str, Any],
        fiscal_year: str
    ) -> Optional[Tuple[float, str, str]]:
        """
        Specialized revenue selection with proper priority.
        
        Revenue has complex rules because companies report it differently:
        - Some use IncludingAssessedTax (includes VAT/sales tax)
        - Some use ExcludingAssessedTax (net of VAT)
        - Some use Revenues or SalesRevenueNet
        
        Returns:
            Tuple of (value, concept_name, section_name) or None
        """
        # Revenue concepts in priority order
        REVENUE_CONCEPTS = [
            'RevenueFromContractWithCustomerIncludingAssessedTax',
            'Revenues',
            'SalesRevenueNet',
            'RevenueFromContractWithCustomerExcludingAssessedTax',
            'SalesRevenueGoodsNet',
            'SalesRevenueServicesNet',
        ]
        
        best_candidate = None
        
        for concept in REVENUE_CONCEPTS:
            candidates = cls.extract_value_candidates(xbrl_data, concept, fiscal_year)
            
            # Filter to only income statement and non-segmented
            primary_candidates = [
                c for c in candidates 
                if c.section_priority <= SectionPriority.DISCLOSURE_REVENUE
                and not c.has_segment
            ]
            
            if primary_candidates:
                candidate = primary_candidates[0]
                if best_candidate is None or candidate.total_priority < best_candidate.total_priority:
                    best_candidate = candidate
        
        if best_candidate:
            return (best_candidate.value, best_candidate.field_name, best_candidate.section_name)
        
        return None


# =============================================================================
# INTEGRATION FUNCTIONS
# =============================================================================

def extract_field_with_priority(
    xbrl_data: Dict[str, Any],
    field_names: List[str],
    fiscal_year: str,
    prefer_consolidated: bool = True
) -> Optional[Tuple[float, str]]:
    """
    Extract a field value using professional priority selection.
    
    Args:
        xbrl_data: Full XBRL data
        field_names: List of XBRL concepts to search (in priority order)
        fiscal_year: Target fiscal year
        prefer_consolidated: Prefer values without segments
        
    Returns:
        Tuple of (value, source_concept) or None
    """
    for concept in field_names:
        candidates = ValueSelector.extract_value_candidates(xbrl_data, concept, fiscal_year)
        best = ValueSelector.select_best_value(candidates, prefer_consolidated)
        
        if best:
            return (best.value, best.field_name)
    
    return None


def debug_value_selection(
    xbrl_data: Dict[str, Any],
    field_name: str,
    fiscal_year: str
) -> None:
    """Debug helper to see all candidates for a field."""
    candidates = ValueSelector.extract_value_candidates(xbrl_data, field_name, fiscal_year)
    
    print(f"\n=== Candidates for {field_name} ({fiscal_year}) ===")
    print(f"Total candidates: {len(candidates)}\n")
    
    for i, c in enumerate(candidates[:10]):
        segment_str = f" [SEGMENT: {c.segment_info}]" if c.has_segment else ""
        print(f"{i+1}. Value: {c.value:,.0f}")
        print(f"   Section: {c.section_name} (priority: {c.section_priority})")
        print(f"   Concept priority: {c.concept_priority}")
        print(f"   Total priority: {c.total_priority}{segment_str}")
        print()

