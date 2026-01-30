"""
RETE Compiler
Compila reglas en un grafo RETE optimizado
"""

from typing import List

from .models import (
    ScanRule, RuleOwnerType, AlphaNode, BetaNode, 
    TerminalNode, ReteNetwork
)


def compile_network(rules: List[ScanRule]) -> ReteNetwork:
    """
    Compila una lista de reglas en un grafo RETE.
    
    El grafo comparte nodos alpha entre reglas que usan
    condiciones identicas, reduciendo evaluaciones redundantes.
    
    Ejemplo:
        Si 1000 reglas tienen "price > 1.0", solo existe
        UN nodo alpha para esa condicion.
    
    Args:
        rules: Lista de ScanRule a compilar
        
    Returns:
        ReteNetwork listo para evaluacion
    """
    network = ReteNetwork()
    
    system_count = 0
    user_count = 0
    
    for rule in rules:
        if not rule.enabled:
            continue
        
        # Contador por tipo
        if rule.owner_type == RuleOwnerType.SYSTEM:
            system_count += 1
        else:
            user_count += 1
        
        alpha_ids = []
        
        # Crear o reutilizar alpha nodes para cada condicion
        for condition in rule.conditions:
            condition_key = condition.get_key()
            
            # Buscar alpha existente con misma condicion
            if condition_key in network.condition_to_alpha:
                alpha_id = network.condition_to_alpha[condition_key]
            else:
                # Crear nuevo alpha node
                alpha_id = f"alpha:{condition_key}"
                network.alpha_nodes[alpha_id] = AlphaNode(
                    id=alpha_id,
                    condition=condition,
                    children=set()
                )
                network.condition_to_alpha[condition_key] = alpha_id
            
            alpha_ids.append(alpha_id)
        
        # Crear beta node para esta regla
        beta_id = f"beta:{rule.id}"
        network.beta_nodes[beta_id] = BetaNode(
            id=beta_id,
            rule_id=rule.id,
            parent_alphas=alpha_ids,
            children=set()
        )
        
        # Conectar alphas al beta
        for alpha_id in alpha_ids:
            network.alpha_nodes[alpha_id].children.add(beta_id)
        
        # Crear terminal node
        terminal_id = f"terminal:{rule.id}"
        network.terminal_nodes[terminal_id] = TerminalNode(
            id=terminal_id,
            rule=rule,
            parent_beta=beta_id
        )
        network.beta_nodes[beta_id].children.add(terminal_id)
        
        # Indice rule -> terminal
        network.rule_to_terminal[rule.id] = terminal_id
    
    # Estadisticas
    network.total_rules = system_count + user_count
    network.system_rules = system_count
    network.user_rules = user_count
    
    return network


def add_rule_to_network(rule: ScanRule, network: ReteNetwork) -> None:
    """
    Agrega una regla a un network existente.
    
    Util para hot-reload de reglas de usuario.
    """
    if not rule.enabled:
        return
    
    # Ya existe?
    if rule.id in network.rule_to_terminal:
        # Remover primero
        remove_rule_from_network(rule.id, network)
    
    alpha_ids = []
    
    for condition in rule.conditions:
        condition_key = condition.get_key()
        
        if condition_key in network.condition_to_alpha:
            alpha_id = network.condition_to_alpha[condition_key]
        else:
            alpha_id = f"alpha:{condition_key}"
            network.alpha_nodes[alpha_id] = AlphaNode(
                id=alpha_id,
                condition=condition,
                children=set()
            )
            network.condition_to_alpha[condition_key] = alpha_id
        
        alpha_ids.append(alpha_id)
    
    beta_id = f"beta:{rule.id}"
    network.beta_nodes[beta_id] = BetaNode(
        id=beta_id,
        rule_id=rule.id,
        parent_alphas=alpha_ids,
        children=set()
    )
    
    for alpha_id in alpha_ids:
        network.alpha_nodes[alpha_id].children.add(beta_id)
    
    terminal_id = f"terminal:{rule.id}"
    network.terminal_nodes[terminal_id] = TerminalNode(
        id=terminal_id,
        rule=rule,
        parent_beta=beta_id
    )
    network.beta_nodes[beta_id].children.add(terminal_id)
    network.rule_to_terminal[rule.id] = terminal_id
    
    # Actualizar contadores
    if rule.owner_type == RuleOwnerType.SYSTEM:
        network.system_rules += 1
    else:
        network.user_rules += 1
    network.total_rules += 1


def remove_rule_from_network(rule_id: str, network: ReteNetwork) -> bool:
    """
    Remueve una regla del network.
    
    Returns:
        True si se removio, False si no existia
    """
    terminal_id = network.rule_to_terminal.get(rule_id)
    if not terminal_id:
        return False
    
    terminal = network.terminal_nodes.get(terminal_id)
    if not terminal:
        return False
    
    # Obtener beta
    beta_id = terminal.parent_beta
    beta = network.beta_nodes.get(beta_id)
    
    if beta:
        # Desconectar de alphas
        for alpha_id in beta.parent_alphas:
            alpha = network.alpha_nodes.get(alpha_id)
            if alpha:
                alpha.children.discard(beta_id)
                # Si alpha quedo sin hijos, podriamos limpiarlo
                # (pero lo dejamos para evitar recompilacion)
        
        del network.beta_nodes[beta_id]
    
    del network.terminal_nodes[terminal_id]
    del network.rule_to_terminal[rule_id]
    
    # Actualizar contadores
    if terminal.rule.owner_type == RuleOwnerType.SYSTEM:
        network.system_rules -= 1
    else:
        network.user_rules -= 1
    network.total_rules -= 1
    
    return True
