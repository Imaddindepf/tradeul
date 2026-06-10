"""
User Rules Converter
Convierte filtros de usuario (de BD) a ScanRule para RETE
"""

from typing import List, Dict, Any, Optional

from .models import Condition, Operator, ScanRule, RuleOwnerType


# Mapeo de campos min/max a condiciones.
# AUTO-GENERADO desde shared/config/filter_catalog.json (fuente única de verdad).
# Para añadir/quitar filtros: editar el JSON y ejecutar scripts/gen_filter_assets.py
from .filter_mapping_generated import FILTER_FIELD_MAPPING, MARKET_CONTEXT_FIELDS  # noqa: F401


def filter_params_to_conditions(params: Dict[str, Any]) -> List[Condition]:
    """
    Convierte FilterParameters (dict) a lista de Condition.
    """
    conditions = []
    
    for min_param, max_param, field in FILTER_FIELD_MAPPING:
        min_val = params.get(min_param)
        max_val = params.get(max_param) if max_param else None
        
        if min_val is not None and max_val is not None:
            op = Operator.OUTSIDE if min_val > max_val else Operator.BETWEEN
            conditions.append(Condition(
                field=field,
                operator=op,
                value=[min_val, max_val],
            ))
        elif min_val is not None:
            conditions.append(Condition(
                field=field,
                operator=Operator.GTE,
                value=min_val
            ))
        elif max_val is not None:
            conditions.append(Condition(
                field=field,
                operator=Operator.LTE,
                value=max_val
            ))
    
    # Filtros de lista
    security_type = params.get("security_type")
    if security_type and isinstance(security_type, str) and security_type.strip():
        conditions.append(Condition(
            field="security_type",
            operator=Operator.EQ,
            value=security_type.strip()
        ))
    
    sectors = params.get("sectors")
    if sectors and isinstance(sectors, list):
        conditions.append(Condition(
            field="sector",
            operator=Operator.IN,
            value=sectors
        ))
    
    industries = params.get("industries")
    if industries and isinstance(industries, list):
        conditions.append(Condition(
            field="industry",
            operator=Operator.IN,
            value=industries
        ))
    
    exchanges = params.get("exchanges")
    if exchanges and isinstance(exchanges, list):
        conditions.append(Condition(
            field="exchange",
            operator=Operator.IN,
            value=exchanges
        ))
    
    return conditions


def user_filter_to_scan_rule(
    filter_data: Dict[str, Any],
    user_id: str
) -> Optional[ScanRule]:
    """
    Convierte un registro de user_scanner_filters a ScanRule.
    
    Args:
        filter_data: Dict con campos de la tabla user_scanner_filters
        user_id: ID del usuario propietario
        
    Returns:
        ScanRule o None si no hay condiciones
    """
    filter_id = filter_data.get("id")
    name = filter_data.get("name", f"Scan {filter_id}")
    enabled = filter_data.get("enabled", True)
    priority = filter_data.get("priority", 0)
    params = filter_data.get("parameters", {})
    
    # Si params es string (JSON), parsearlo
    if isinstance(params, str):
        import json
        params = json.loads(params)
    
    conditions = filter_params_to_conditions(params)
    
    if not conditions:
        return None
    
    return ScanRule(
        id=f"user:{user_id}:scan:{filter_id}",
        owner_type=RuleOwnerType.USER,
        owner_id=user_id,
        name=name,
        conditions=conditions,
        enabled=enabled,
        priority=priority,
        sort_field="change_percent",
        sort_descending=True,
    )


def convert_user_filters(
    filters: List[Dict[str, Any]],
    user_id: str
) -> List[ScanRule]:
    """
    Convierte lista de filtros de usuario a ScanRule.
    """
    rules = []
    for filter_data in filters:
        rule = user_filter_to_scan_rule(filter_data, user_id)
        if rule:
            rules.append(rule)
    return rules
