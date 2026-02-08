"""
Event Rules - Define what triggers an event.

Rules specify:
1. A TRIGGER condition (price crosses above, value exceeds threshold, etc.)
2. Optional FILTER conditions (only for certain stocks, with certain metrics)
3. A COOLDOWN to prevent spam
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class EventTrigger(str, Enum):
    """Types of triggers that can fire an event."""
    
    # Price crosses a reference value
    PRICE_CROSSES_ABOVE = "price_crosses_above"
    PRICE_CROSSES_BELOW = "price_crosses_below"
    
    # Value exceeds/drops below threshold
    VALUE_CROSSES_ABOVE = "value_crosses_above"
    VALUE_CROSSES_BELOW = "value_crosses_below"
    
    # External event (halt, news, etc.)
    EXTERNAL_EVENT = "external_event"


class RuleOwnerType(str, Enum):
    """Who owns the rule."""
    SYSTEM = "system"  # Pre-built rules
    USER = "user"      # User-created rules


class Operator(str, Enum):
    """Comparison operators for conditions."""
    EQ = "eq"      # ==
    NE = "ne"      # !=
    GT = "gt"      # >
    GTE = "gte"    # >=
    LT = "lt"      # <
    LTE = "lte"    # <=
    IN = "in"      # in list
    NOT_IN = "not_in"  # not in list


@dataclass
class Condition:
    """
    A filter condition for an event rule.
    
    Example: Condition("rvol", Operator.GTE, 1.5) means "RVOL >= 1.5"
    """
    field: str
    operator: Operator
    value: Any
    
    def evaluate(self, data: Dict[str, Any]) -> bool:
        """Evaluate this condition against data."""
        field_value = data.get(self.field)
        if field_value is None:
            return False
        
        if self.operator == Operator.EQ:
            return field_value == self.value
        elif self.operator == Operator.NE:
            return field_value != self.value
        elif self.operator == Operator.GT:
            return field_value > self.value
        elif self.operator == Operator.GTE:
            return field_value >= self.value
        elif self.operator == Operator.LT:
            return field_value < self.value
        elif self.operator == Operator.LTE:
            return field_value <= self.value
        elif self.operator == Operator.IN:
            return field_value in self.value
        elif self.operator == Operator.NOT_IN:
            return field_value not in self.value
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "operator": self.operator.value,
            "value": self.value,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Condition":
        return cls(
            field=data["field"],
            operator=Operator(data["operator"]),
            value=data["value"],
        )


@dataclass
class EventRule:
    """
    A rule that defines when an event should be triggered.
    
    Attributes:
        id: Unique rule ID (e.g., "event:system:new_high")
        owner_type: SYSTEM or USER
        name: Human-readable name
        trigger: What causes the event to fire
        trigger_field: Field to check (e.g., "price")
        reference_field: Field to compare against (e.g., "intraday_high")
        threshold: Fixed threshold for value-based triggers
        conditions: Additional filter conditions
        cooldown_seconds: Minimum time between events for same symbol
        enabled: Whether the rule is active
    """
    
    id: str
    owner_type: RuleOwnerType
    name: str
    trigger: EventTrigger
    
    # Trigger configuration
    trigger_field: str = "price"
    reference_field: Optional[str] = None  # For CROSSES triggers
    threshold: Optional[float] = None       # For VALUE triggers
    
    # External event config
    external_source: Optional[str] = None   # Stream name for EXTERNAL triggers
    external_filter: Optional[Dict[str, Any]] = None
    
    # Filters (AND logic)
    conditions: List[Condition] = field(default_factory=list)
    
    # Timing
    cooldown_seconds: int = 60
    
    # State
    enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "owner_type": self.owner_type.value,
            "name": self.name,
            "trigger": self.trigger.value,
            "trigger_field": self.trigger_field,
            "reference_field": self.reference_field,
            "threshold": self.threshold,
            "external_source": self.external_source,
            "external_filter": self.external_filter,
            "conditions": [c.to_dict() for c in self.conditions],
            "cooldown_seconds": self.cooldown_seconds,
            "enabled": self.enabled,
        }


@dataclass
class UserEventRule(EventRule):
    """
    A user-created event rule with additional user-specific fields.
    
    Extends EventRule with:
    - user_id: Owner of the rule
    - notify_push: Send push notification
    - notify_sound: Play sound in UI
    - symbols: Optional list of specific symbols to watch
    """
    
    user_id: str = ""
    notify_push: bool = False
    notify_sound: bool = True
    symbols: Optional[List[str]] = None  # None = all symbols
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "user_id": self.user_id,
            "notify_push": self.notify_push,
            "notify_sound": self.notify_sound,
            "symbols": self.symbols,
        })
        return base
