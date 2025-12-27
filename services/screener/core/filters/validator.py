"""
Filter Validator - Validates filter conditions against indicator definitions
"""

from typing import List, Dict, Any, Tuple
import structlog

logger = structlog.get_logger(__name__)


class FilterValidator:
    """Validates filter conditions"""
    
    def __init__(self, indicator_registry):
        self.registry = indicator_registry
    
    def validate(self, filters: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """
        Validate list of filters
        
        Returns:
            (is_valid, list of error messages)
        """
        errors = []
        
        for i, f in enumerate(filters):
            filter_errors = self._validate_single(f, i)
            errors.extend(filter_errors)
        
        return len(errors) == 0, errors
    
    def _validate_single(self, filter_dict: Dict[str, Any], index: int) -> List[str]:
        """Validate a single filter"""
        errors = []
        prefix = f"Filter {index + 1}"
        
        # Required fields
        field = filter_dict.get("field")
        operator = filter_dict.get("operator")
        value = filter_dict.get("value")
        
        if not field:
            errors.append(f"{prefix}: 'field' is required")
            return errors
        
        if not operator:
            errors.append(f"{prefix}: 'operator' is required")
            return errors
        
        # Check indicator exists
        indicator = self.registry.get_indicator(field)
        if not indicator:
            available = ", ".join(list(self.registry.get_all_indicators().keys())[:10])
            errors.append(f"{prefix}: Unknown field '{field}'. Available: {available}...")
            return errors
        
        # Check operator is valid for this indicator
        valid_ops = [op.value for op in indicator.operators]
        if operator not in valid_ops:
            errors.append(f"{prefix}: Operator '{operator}' not valid for '{field}'. Valid: {valid_ops}")
            return errors
        
        # Validate value
        if value is None and operator != "eq":
            errors.append(f"{prefix}: 'value' is required for operator '{operator}'")
            return errors
        
        # Type validation
        if operator == "between":
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                errors.append(f"{prefix}: 'between' requires [min, max] array")
                return errors
            
            try:
                min_val, max_val = float(value[0]), float(value[1])
                if min_val > max_val:
                    errors.append(f"{prefix}: min value must be <= max value")
            except (ValueError, TypeError):
                errors.append(f"{prefix}: 'between' values must be numbers")
        
        elif operator in ("gt", "gte", "lt", "lte"):
            # Value should be numeric or another indicator
            if isinstance(value, str):
                # Check if it's another indicator
                if not self.registry.get_indicator(value):
                    try:
                        float(value)
                    except ValueError:
                        errors.append(f"{prefix}: Invalid value '{value}'")
            elif not isinstance(value, (int, float)):
                errors.append(f"{prefix}: Value must be numeric, got {type(value).__name__}")
        
        # Range validation
        if indicator.min_value is not None and isinstance(value, (int, float)):
            if value < indicator.min_value:
                errors.append(f"{prefix}: Value {value} below minimum {indicator.min_value}")
        
        if indicator.max_value is not None and isinstance(value, (int, float)):
            if value > indicator.max_value:
                errors.append(f"{prefix}: Value {value} above maximum {indicator.max_value}")
        
        return errors

