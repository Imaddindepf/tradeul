"""
Filter Parser - Converts JSON filters to SQL WHERE clauses
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FilterCondition:
    """A single filter condition"""
    field: str
    operator: str
    value: Any


class FilterParser:
    """Parses filter conditions into SQL WHERE clauses"""
    
    OPERATOR_MAP = {
        "gt": ">",
        "gte": ">=",
        "lt": "<",
        "lte": "<=",
        "eq": "=",
        "neq": "!=",
    }
    
    def __init__(self, indicator_registry):
        self.registry = indicator_registry
    
    def parse(self, filters: List[Dict[str, Any]]) -> str:
        """
        Parse list of filter conditions into SQL WHERE clause
        
        Args:
            filters: List of {"field": "rsi_14", "operator": "lt", "value": 30}
        
        Returns:
            SQL WHERE clause string
        """
        if not filters:
            return "1=1"
        
        conditions = []
        for f in filters:
            condition = self._parse_single(f)
            if condition:
                conditions.append(condition)
        
        return " AND ".join(conditions) if conditions else "1=1"
    
    def _parse_single(self, filter_dict: Dict[str, Any]) -> Optional[str]:
        """Parse a single filter into SQL condition"""
        field = filter_dict.get("field")
        operator = filter_dict.get("operator", "").lower()
        value = filter_dict.get("value")
        
        if not field or not operator:
            logger.warning("invalid_filter", filter=filter_dict)
            return None
        
        # Get indicator definition
        indicator = self.registry.get_indicator(field)
        if not indicator:
            logger.warning("unknown_indicator", field=field)
            return None
        
        # Get SQL expression for this indicator
        sql_field = indicator.sql_expression
        
        # Handle different operators
        if operator == "between":
            if isinstance(value, (list, tuple)) and len(value) == 2:
                return f"({sql_field} BETWEEN {self._escape(value[0])} AND {self._escape(value[1])})"
            logger.warning("invalid_between_value", value=value)
            return None
        
        elif operator in ("cross_above", "cross_below"):
            # Cross requires comparing with previous value
            # This is handled specially in the query builder
            return self._build_cross_condition(sql_field, operator, value)
        
        elif operator in self.OPERATOR_MAP:
            sql_op = self.OPERATOR_MAP[operator]
            
            # Handle comparison with another indicator
            if isinstance(value, str) and self.registry.get_indicator(value):
                other_indicator = self.registry.get_indicator(value)
                return f"({sql_field} {sql_op} {other_indicator.sql_expression})"
            
            return f"({sql_field} {sql_op} {self._escape(value)})"
        
        logger.warning("unknown_operator", operator=operator)
        return None
    
    def _build_cross_condition(self, field: str, operator: str, value: Any) -> str:
        """Build cross above/below condition"""
        # Simplified: just check current position
        # Full implementation would need prev_<field>
        if operator == "cross_above":
            if isinstance(value, str):
                return f"({field} > {value})"
            return f"({field} > {self._escape(value)})"
        else:
            if isinstance(value, str):
                return f"({field} < {value})"
            return f"({field} < {self._escape(value)})"
    
    def _escape(self, value: Any) -> str:
        """Escape value for SQL"""
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            # Sanitize string
            clean = value.replace("'", "''")
            return f"'{clean}'"
        return str(value)

