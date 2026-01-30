"""
RETE Engine for Scanner
"""

from .models import (
    Operator, RuleOwnerType, Condition, ScanRule,
    AlphaNode, BetaNode, TerminalNode, ReteNetwork,
)

from .compiler import (
    compile_network, add_rule_to_network, remove_rule_from_network,
)

from .evaluator import (
    evaluate_condition, evaluate_ticker,
    get_matching_rules, get_matching_rules_by_owner,
)

from .system_rules import get_system_rules, CATEGORY_TO_CHANNEL

from .user_rules import (
    filter_params_to_conditions, user_filter_to_scan_rule, convert_user_filters,
)

__all__ = [
    "Operator", "RuleOwnerType", "Condition", "ScanRule",
    "AlphaNode", "BetaNode", "TerminalNode", "ReteNetwork",
    "compile_network", "add_rule_to_network", "remove_rule_from_network",
    "evaluate_condition", "evaluate_ticker", "get_matching_rules",
    "get_matching_rules_by_owner", "get_system_rules", "CATEGORY_TO_CHANNEL",
    "filter_params_to_conditions", "user_filter_to_scan_rule", "convert_user_filters",
]

from .manager import ReteManager

__all__.append("ReteManager")
