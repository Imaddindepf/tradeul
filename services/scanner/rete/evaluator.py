"""
RETE Evaluator
Evalua condiciones y tickers contra el grafo RETE
"""

from typing import Any, Dict, Set, Optional

from .models import (
    Condition, Operator, ReteNetwork, RuleOwnerType
)


def evaluate_condition(ticker_value: Any, condition: Condition) -> bool:
    """
    Evalua una condicion contra un valor de ticker.
    
    Args:
        ticker_value: Valor del campo del ticker
        condition: Condicion a evaluar
        
    Returns:
        True si el valor cumple la condicion
    """
    op = condition.operator
    cond_value = condition.value
    
    # Operadores que manejan None especialmente
    if op == Operator.IS_NONE:
        return ticker_value is None
    
    if op == Operator.NOT_NONE:
        return ticker_value is not None
    
    # Si el valor del ticker es None, no puede cumplir otras condiciones
    if ticker_value is None:
        return False
    
    # Operadores de comparacion
    if op == Operator.GT:
        return ticker_value > cond_value
    
    if op == Operator.GTE:
        return ticker_value >= cond_value
    
    if op == Operator.LT:
        return ticker_value < cond_value
    
    if op == Operator.LTE:
        return ticker_value <= cond_value
    
    if op == Operator.EQ:
        return ticker_value == cond_value
    
    if op == Operator.NEQ:
        return ticker_value != cond_value
    
    if op == Operator.BETWEEN:
        min_val, max_val = cond_value
        return min_val <= ticker_value <= max_val
    
    if op == Operator.IN:
        return ticker_value in cond_value
    
    if op == Operator.NOT_IN:
        return ticker_value not in cond_value
    
    return False


def evaluate_ticker(ticker: Any, network: ReteNetwork) -> Dict[str, bool]:
    """
    Evalua un ticker contra todo el grafo RETE.
    
    Proceso:
    1. Evaluar todos los nodos alpha (condiciones individuales)
    2. Propagar resultados a nodos beta (AND de condiciones)
    3. Determinar que reglas (terminales) matchean
    
    Args:
        ticker: Objeto ScannerTicker
        network: Grafo RETE compilado
        
    Returns:
        Dict {rule_id: bool} indicando que reglas matchean
    """
    # Paso 1: Evaluar todos los alpha nodes
    alpha_results: Dict[str, bool] = {}
    
    for alpha_id, alpha_node in network.alpha_nodes.items():
        field_name = alpha_node.condition.field
        ticker_value = getattr(ticker, field_name, None)
        result = evaluate_condition(ticker_value, alpha_node.condition)
        alpha_results[alpha_id] = result
    
    # Paso 2: Evaluar beta nodes (AND de alphas)
    beta_results: Dict[str, bool] = {}
    
    for beta_id, beta_node in network.beta_nodes.items():
        # Beta es True solo si TODOS sus parent alphas son True
        all_true = all(
            alpha_results.get(alpha_id, False) 
            for alpha_id in beta_node.parent_alphas
        )
        beta_results[beta_id] = all_true
    
    # Paso 3: Mapear a rule_ids
    matches: Dict[str, bool] = {}
    
    for terminal_id, terminal_node in network.terminal_nodes.items():
        rule_id = terminal_node.rule.id
        matches[rule_id] = beta_results.get(terminal_node.parent_beta, False)
    
    return matches


def get_matching_rules(ticker: Any, network: ReteNetwork) -> Set[str]:
    """
    Obtiene los IDs de las reglas que matchean un ticker.
    
    Convenience wrapper sobre evaluate_ticker.
    """
    matches = evaluate_ticker(ticker, network)
    return {rule_id for rule_id, matched in matches.items() if matched}


def get_matching_rules_by_owner(
    ticker: Any, 
    network: ReteNetwork
) -> Dict[str, Set[str]]:
    """
    Obtiene reglas que matchean agrupadas por tipo de owner.
    
    Returns:
        {
            "system": {"category:gappers_up", "category:winners"},
            "user:abc123": {"user:abc123:scan:1"},
            "user:xyz789": {"user:xyz789:scan:3"},
        }
    """
    matches = evaluate_ticker(ticker, network)
    result: Dict[str, Set[str]] = {"system": set()}
    
    for rule_id, matched in matches.items():
        if not matched:
            continue
        
        terminal = network.terminal_nodes.get(f"terminal:{rule_id}")
        if not terminal:
            continue
        
        rule = terminal.rule
        
        if rule.owner_type == RuleOwnerType.SYSTEM:
            result["system"].add(rule_id)
        else:
            user_key = f"user:{rule.owner_id}"
            if user_key not in result:
                result[user_key] = set()
            result[user_key].add(rule_id)
    
    return result
