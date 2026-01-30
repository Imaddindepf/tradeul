"""
RETE Engine Models
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional, Dict, Set
from enum import Enum


class Operator(str, Enum):
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    EQ = "eq"
    NEQ = "neq"
    BETWEEN = "between"
    IN = "in"
    NOT_IN = "not_in"
    IS_NONE = "is_none"
    NOT_NONE = "not_none"


class RuleOwnerType(str, Enum):
    SYSTEM = "system"
    USER = "user"


@dataclass
class Condition:
    field: str
    operator: Operator
    value: Any
    
    def get_key(self) -> str:
        if isinstance(self.value, (list, tuple)):
            if self.operator in (Operator.IN, Operator.NOT_IN):
                val_str = str(sorted(self.value))
            else:
                val_str = str(list(self.value))
        elif isinstance(self.value, set):
            val_str = str(sorted(self.value))
        else:
            val_str = str(self.value)
        return f"{self.field}:{self.operator.value}:{val_str}"


@dataclass
class ScanRule:
    id: str
    owner_type: RuleOwnerType
    name: str
    conditions: List[Condition]
    owner_id: Optional[str] = None
    enabled: bool = True
    priority: int = 0
    sort_field: Optional[str] = None
    sort_descending: bool = True


@dataclass
class AlphaNode:
    id: str
    condition: Condition
    children: Set[str] = field(default_factory=set)


@dataclass
class BetaNode:
    id: str
    rule_id: str
    parent_alphas: List[str]
    children: Set[str] = field(default_factory=set)


@dataclass
class TerminalNode:
    id: str
    rule: ScanRule
    parent_beta: str


@dataclass
class ReteNetwork:
    alpha_nodes: Dict[str, AlphaNode] = field(default_factory=dict)
    beta_nodes: Dict[str, BetaNode] = field(default_factory=dict)
    terminal_nodes: Dict[str, TerminalNode] = field(default_factory=dict)
    condition_to_alpha: Dict[str, str] = field(default_factory=dict)
    rule_to_terminal: Dict[str, str] = field(default_factory=dict)
    total_rules: int = 0
    system_rules: int = 0
    user_rules: int = 0
    
    def get_stats(self) -> Dict[str, int]:
        return {
            "total_rules": self.total_rules,
            "system_rules": self.system_rules,
            "user_rules": self.user_rules,
            "alpha_nodes": len(self.alpha_nodes),
            "beta_nodes": len(self.beta_nodes),
            "terminal_nodes": len(self.terminal_nodes),
        }
