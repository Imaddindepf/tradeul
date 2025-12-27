"""
Base classes for technical indicators

All indicators generate SQL expressions that DuckDB can execute.
This approach is much faster than calculating in Python.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Literal
from dataclasses import dataclass, field
from enum import Enum


class OperatorType(str, Enum):
    """Supported filter operators"""
    GT = "gt"           # Greater than
    GTE = "gte"         # Greater than or equal
    LT = "lt"           # Less than
    LTE = "lte"         # Less than or equal
    EQ = "eq"           # Equal
    BETWEEN = "between" # Between two values
    CROSS_ABOVE = "cross_above"  # Crossed above (for MAs)
    CROSS_BELOW = "cross_below"  # Crossed below


class DataType(str, Enum):
    """Data types for indicator values"""
    FLOAT = "float"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    PERCENT = "percent"


@dataclass
class IndicatorDefinition:
    """Definition of a single indicator"""
    name: str                           # e.g., "rsi_14"
    display_name: str                   # e.g., "RSI (14)"
    description: str                    # e.g., "Relative Strength Index"
    category: str                       # e.g., "momentum"
    data_type: DataType                 # e.g., DataType.FLOAT
    sql_expression: str                 # SQL to calculate
    operators: List[OperatorType]       # Allowed operators
    default_value: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    format_string: str = "{:.2f}"       # For display
    requires_benchmark: bool = False    # Needs SPY data


@dataclass
class IndicatorGroup(ABC):
    """Base class for a group of related indicators"""
    
    category: str = ""
    description: str = ""
    
    @abstractmethod
    def get_indicators(self) -> List[IndicatorDefinition]:
        """Return list of indicator definitions"""
        pass
    
    @abstractmethod
    def get_sql_cte(self) -> str:
        """Return SQL CTE for calculating these indicators"""
        pass


class IndicatorRegistry:
    """Registry of all available indicators"""
    
    def __init__(self):
        self._indicators: Dict[str, IndicatorDefinition] = {}
        self._groups: List[IndicatorGroup] = []
        self._sql_ctes: List[str] = []
    
    def register_group(self, group: IndicatorGroup):
        """Register a group of indicators"""
        self._groups.append(group)
        for indicator in group.get_indicators():
            self._indicators[indicator.name] = indicator
        self._sql_ctes.append(group.get_sql_cte())
    
    def get_indicator(self, name: str) -> Optional[IndicatorDefinition]:
        """Get indicator by name"""
        return self._indicators.get(name)
    
    def get_all_indicators(self) -> Dict[str, IndicatorDefinition]:
        """Get all registered indicators"""
        return self._indicators.copy()
    
    def get_indicators_by_category(self, category: str) -> List[IndicatorDefinition]:
        """Get indicators in a category"""
        return [i for i in self._indicators.values() if i.category == category]
    
    def get_categories(self) -> List[str]:
        """Get all categories"""
        return list(set(i.category for i in self._indicators.values()))
    
    def get_combined_sql_cte(self) -> str:
        """Get combined SQL CTE for all indicators"""
        return "\n".join(self._sql_ctes)
    
    def validate_filter(self, field: str, operator: str, value: Any) -> bool:
        """Validate a filter against indicator definition"""
        indicator = self._indicators.get(field)
        if not indicator:
            return False
        
        try:
            op = OperatorType(operator)
        except ValueError:
            return False
        
        return op in indicator.operators
    
    def to_dict(self) -> Dict:
        """Export registry as dict for API"""
        result = {}
        for category in self.get_categories():
            indicators = self.get_indicators_by_category(category)
            result[category] = [
                {
                    "name": i.name,
                    "display_name": i.display_name,
                    "description": i.description,
                    "data_type": i.data_type.value,
                    "operators": [op.value for op in i.operators],
                    "min_value": i.min_value,
                    "max_value": i.max_value,
                }
                for i in indicators
            ]
        return result

