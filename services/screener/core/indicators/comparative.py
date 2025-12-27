"""
Comparative Indicators - Simplified for precomputed data
"""

from typing import List
from .base import IndicatorGroup, IndicatorDefinition, OperatorType, DataType


class ComparativeIndicators(IndicatorGroup):
    """Comparative and relative indicators"""
    
    category = "comparative"
    description = "Relative performance metrics"
    
    def get_indicators(self) -> List[IndicatorDefinition]:
        # No comparative indicators available in precomputed data yet
        # Can add beta, correlation etc. when we add SPY comparison
        return []
    
    def get_sql_cte(self) -> str:
        return ""
