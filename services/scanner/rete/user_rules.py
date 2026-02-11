"""
User Rules Converter
Convierte filtros de usuario (de BD) a ScanRule para RETE
"""

from typing import List, Dict, Any, Optional

from .models import Condition, Operator, ScanRule, RuleOwnerType


# Mapeo de campos min/max a condiciones
FILTER_FIELD_MAPPING = [
    # (min_param, max_param, ticker_field)
    #
    # === Price & Spread ===
    ("min_price", "max_price", "price"),
    ("min_vwap", "max_vwap", "vwap"),
    ("min_spread", "max_spread", "spread"),
    ("min_bid_size", "max_bid_size", "bid_size"),
    ("min_ask_size", "max_ask_size", "ask_size"),
    ("min_distance_from_nbbo", "max_distance_from_nbbo", "distance_from_nbbo"),
    #
    # === Change % ===
    ("min_change_percent", "max_change_percent", "change_percent"),
    ("min_change_from_open", "max_change_from_open", "change_from_open"),
    ("min_gap_percent", "max_gap_percent", "gap_percent"),
    ("min_premarket_change_percent", "max_premarket_change_percent", "premarket_change_percent"),
    ("min_postmarket_change_percent", "max_postmarket_change_percent", "postmarket_change_percent"),
    ("min_price_from_high", "max_price_from_high", "price_from_high"),
    #
    # === Volume ===
    ("min_rvol", "max_rvol", "rvol"),
    ("min_volume", None, "volume_today"),
    ("min_volume_today", None, "volume_today"),
    ("min_minute_volume", None, "minute_volume"),
    ("min_avg_volume_5d", "max_avg_volume_5d", "avg_volume_5d"),
    ("min_avg_volume_10d", "max_avg_volume_10d", "avg_volume_10d"),
    ("min_avg_volume_3m", "max_avg_volume_3m", "avg_volume_3m"),
    ("min_dollar_volume", "max_dollar_volume", "dollar_volume"),
    ("min_volume_today_pct", "max_volume_today_pct", "volume_today_pct"),
    ("min_vol_1min", "max_vol_1min", "vol_1min"),
    ("min_vol_5min", "max_vol_5min", "vol_5min"),
    #
    # === Time Windows ===
    ("min_chg_1min", "max_chg_1min", "chg_1min"),
    ("min_chg_5min", "max_chg_5min", "chg_5min"),
    ("min_chg_10min", "max_chg_10min", "chg_10min"),
    ("min_chg_15min", "max_chg_15min", "chg_15min"),
    ("min_chg_30min", "max_chg_30min", "chg_30min"),
    #
    # === Technical ===
    ("min_atr", "max_atr", "atr"),
    ("min_atr_percent", "max_atr_percent", "atr_percent"),
    ("min_rsi", "max_rsi", "rsi_14"),
    ("min_ema_20", "max_ema_20", "ema_20"),
    ("min_ema_50", "max_ema_50", "ema_50"),
    # Legacy compat: old filters saved as min_sma_20 still work
    ("min_sma_20", "max_sma_20", "ema_20"),
    ("min_sma_50", "max_sma_50", "ema_50"),
    ("min_price_vs_vwap", "max_price_vs_vwap", "price_vs_vwap"),
    #
    # === Fundamentals ===
    ("min_market_cap", "max_market_cap", "market_cap"),
    ("min_float", "max_float", "free_float"),
    ("min_float_shares", "max_float_shares", "free_float"),
    ("min_shares_outstanding", "max_shares_outstanding", "shares_outstanding"),
    ("min_short_interest", "max_short_interest", "short_interest"),
]


def filter_params_to_conditions(params: Dict[str, Any]) -> List[Condition]:
    """
    Convierte FilterParameters (dict) a lista de Condition.
    """
    conditions = []
    
    for min_param, max_param, field in FILTER_FIELD_MAPPING:
        min_val = params.get(min_param)
        max_val = params.get(max_param) if max_param else None
        
        # Si ambos estan definidos, usar BETWEEN
        if min_val is not None and max_val is not None:
            conditions.append(Condition(
                field=field,
                operator=Operator.BETWEEN,
                value=[min_val, max_val]
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
