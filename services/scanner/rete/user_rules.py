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
    ("min_volume_today_pct", "max_volume_today_pct", "volume_today_pct"),
    #
    # === Volume Windows ===
    ("min_vol_1min", "max_vol_1min", "vol_1min"),
    ("min_vol_5min", "max_vol_5min", "vol_5min"),
    ("min_vol_10min", "max_vol_10min", "vol_10min"),
    ("min_vol_15min", "max_vol_15min", "vol_15min"),
    ("min_vol_30min", "max_vol_30min", "vol_30min"),
    #
    # === Time Window Changes ===
    ("min_chg_1min", "max_chg_1min", "chg_1min"),
    ("min_chg_5min", "max_chg_5min", "chg_5min"),
    ("min_chg_10min", "max_chg_10min", "chg_10min"),
    ("min_chg_15min", "max_chg_15min", "chg_15min"),
    ("min_chg_30min", "max_chg_30min", "chg_30min"),
    ("min_chg_60min", "max_chg_60min", "chg_60min"),
    #
    # === Quote ===
    ("min_bid", "max_bid", "bid"),
    ("min_ask", "max_ask", "ask"),
    ("min_bid_ask_ratio", "max_bid_ask_ratio", "bid_ask_ratio"),
    #
    # === Technical (Intraday) ===
    ("min_atr", "max_atr", "atr"),
    ("min_atr_percent", "max_atr_percent", "atr_percent"),
    ("min_rsi", "max_rsi", "rsi_14"),
    ("min_ema_20", "max_ema_20", "ema_20"),
    ("min_ema_50", "max_ema_50", "ema_50"),
    ("min_price_vs_vwap", "max_price_vs_vwap", "price_vs_vwap"),
    # Intraday SMA (actual SMA from BarEngine, not EMA)
    ("min_sma_5", "max_sma_5", "sma_5"),
    ("min_sma_8", "max_sma_8", "sma_8"),
    ("min_sma_20", "max_sma_20", "sma_20"),
    ("min_sma_50", "max_sma_50", "sma_50"),
    ("min_sma_200", "max_sma_200", "sma_200"),
    # MACD / Stochastic / Bollinger
    ("min_macd_line", "max_macd_line", "macd_line"),
    ("min_macd_hist", "max_macd_hist", "macd_hist"),
    ("min_stoch_k", "max_stoch_k", "stoch_k"),
    ("min_stoch_d", "max_stoch_d", "stoch_d"),
    ("min_adx_14", "max_adx_14", "adx_14"),
    ("min_bb_upper", "max_bb_upper", "bb_upper"),
    ("min_bb_lower", "max_bb_lower", "bb_lower"),
    #
    # === Daily Indicators ===
    ("min_daily_sma_20", "max_daily_sma_20", "daily_sma_20"),
    ("min_daily_sma_50", "max_daily_sma_50", "daily_sma_50"),
    ("min_daily_sma_200", "max_daily_sma_200", "daily_sma_200"),
    ("min_daily_rsi", "max_daily_rsi", "daily_rsi"),
    ("min_daily_adx_14", "max_daily_adx_14", "daily_adx_14"),
    ("min_daily_atr_percent", "max_daily_atr_percent", "daily_atr_percent"),
    ("min_daily_bb_position", "max_daily_bb_position", "daily_bb_position"),
    #
    # === 52-Week ===
    ("min_high_52w", "max_high_52w", "high_52w"),
    ("min_low_52w", "max_low_52w", "low_52w"),
    ("min_from_52w_high", "max_from_52w_high", "from_52w_high"),
    ("min_from_52w_low", "max_from_52w_low", "from_52w_low"),
    #
    # === Derived / Computed ===
    ("min_dollar_volume", "max_dollar_volume", "dollar_volume"),
    ("min_todays_range", "max_todays_range", "todays_range"),
    ("min_todays_range_pct", "max_todays_range_pct", "todays_range_pct"),
    ("min_float_turnover", "max_float_turnover", "float_turnover"),
    ("min_dist_from_vwap", "max_dist_from_vwap", "dist_from_vwap"),
    ("min_dist_sma_5", "max_dist_sma_5", "dist_sma_5"),
    ("min_dist_sma_8", "max_dist_sma_8", "dist_sma_8"),
    ("min_dist_sma_20", "max_dist_sma_20", "dist_sma_20"),
    ("min_dist_sma_50", "max_dist_sma_50", "dist_sma_50"),
    ("min_dist_sma_200", "max_dist_sma_200", "dist_sma_200"),
    ("min_dist_daily_sma_20", "max_dist_daily_sma_20", "dist_daily_sma_20"),
    ("min_dist_daily_sma_50", "max_dist_daily_sma_50", "dist_daily_sma_50"),
    ("min_pos_in_range", "max_pos_in_range", "pos_in_range"),
    ("min_below_high", "max_below_high", "below_high"),
    ("min_above_low", "max_above_low", "above_low"),
    ("min_pos_of_open", "max_pos_of_open", "pos_of_open"),
    ("min_prev_day_volume", "max_prev_day_volume", "prev_day_volume"),
    #
    # === Multi-Day Changes ===
    ("min_change_1d", "max_change_1d", "change_1d"),
    ("min_change_3d", "max_change_3d", "change_3d"),
    ("min_change_5d", "max_change_5d", "change_5d"),
    ("min_change_10d", "max_change_10d", "change_10d"),
    ("min_change_20d", "max_change_20d", "change_20d"),
    #
    # === Average Volumes ===
    ("min_avg_volume_5d", "max_avg_volume_5d", "avg_volume_5d"),
    ("min_avg_volume_10d", "max_avg_volume_10d", "avg_volume_10d"),
    ("min_avg_volume_20d", "max_avg_volume_20d", "avg_volume_20d"),
    ("min_avg_volume_3m", "max_avg_volume_3m", "avg_volume_3m"),
    #
    # === Trades ===
    ("min_trades_today", "max_trades_today", "trades_today"),
    ("min_trades_z_score", "max_trades_z_score", "trades_z_score"),
    #
    # === Fundamentals ===
    ("min_market_cap", "max_market_cap", "market_cap"),
    ("min_float", "max_float", "free_float"),
    ("min_float_shares", "max_float_shares", "free_float"),
    ("min_shares_outstanding", "max_shares_outstanding", "shares_outstanding"),
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
