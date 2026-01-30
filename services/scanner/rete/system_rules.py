"""
System Rules
Define las categorias del sistema como ScanRule para RETE
"""

from typing import List

from .models import Condition, Operator, ScanRule, RuleOwnerType


def get_system_rules() -> List[ScanRule]:
    """
    Retorna las categorias del sistema convertidas a ScanRule.
    
    Cada categoria tiene:
    - Condiciones de filtrado (AND)
    - Campo y direccion de ordenamiento
    """
    return [
        # GAPPERS_UP: Gap >= 2%, price >= 1, volume > 0
        ScanRule(
            id="category:gappers_up",
            owner_type=RuleOwnerType.SYSTEM,
            name="Gappers Up",
            conditions=[
                Condition("gap_percent", Operator.GTE, 2.0),
                Condition("price", Operator.GTE, 1.0),
                Condition("volume_today", Operator.GT, 0),
            ],
            sort_field="gap_percent",
            sort_descending=True,
        ),
        
        # GAPPERS_DOWN: Gap <= -2%, price >= 1, volume > 0
        ScanRule(
            id="category:gappers_down",
            owner_type=RuleOwnerType.SYSTEM,
            name="Gappers Down",
            conditions=[
                Condition("gap_percent", Operator.LTE, -2.0),
                Condition("price", Operator.GTE, 1.0),
                Condition("volume_today", Operator.GT, 0),
            ],
            sort_field="gap_percent",
            sort_descending=False,
        ),
        
        # MOMENTUM_UP: chg_5min >= 1.5%, near HOD, above VWAP, high RVOL
        ScanRule(
            id="category:momentum_up",
            owner_type=RuleOwnerType.SYSTEM,
            name="Momentum Up",
            conditions=[
                Condition("chg_5min", Operator.GTE, 1.5),
                Condition("price_from_intraday_high", Operator.GTE, -2.0),
                Condition("price_vs_vwap", Operator.GT, 0),
                Condition("rvol", Operator.GTE, 5.0),
            ],
            sort_field="chg_5min",
            sort_descending=True,
        ),
        
        # MOMENTUM_DOWN: change <= -3%
        ScanRule(
            id="category:momentum_down",
            owner_type=RuleOwnerType.SYSTEM,
            name="Momentum Down",
            conditions=[
                Condition("change_percent", Operator.LTE, -3.0),
                Condition("price", Operator.GTE, 1.0),
            ],
            sort_field="change_percent",
            sort_descending=False,
        ),
        
        # WINNERS: change >= 5%
        ScanRule(
            id="category:winners",
            owner_type=RuleOwnerType.SYSTEM,
            name="Winners",
            conditions=[
                Condition("change_percent", Operator.GTE, 5.0),
                Condition("price", Operator.GTE, 1.0),
            ],
            sort_field="change_percent",
            sort_descending=True,
        ),
        
        # LOSERS: change <= -5%
        ScanRule(
            id="category:losers",
            owner_type=RuleOwnerType.SYSTEM,
            name="Losers",
            conditions=[
                Condition("change_percent", Operator.LTE, -5.0),
                Condition("price", Operator.GTE, 1.0),
            ],
            sort_field="change_percent",
            sort_descending=False,
        ),
        
        # HIGH_VOLUME: RVOL >= 2.0
        ScanRule(
            id="category:high_volume",
            owner_type=RuleOwnerType.SYSTEM,
            name="High Volume",
            conditions=[
                Condition("rvol", Operator.GTE, 2.0),
                Condition("price", Operator.GTE, 1.0),
            ],
            sort_field="volume_today",
            sort_descending=True,
        ),
        
        # ANOMALIES: trades_z_score >= 3.0
        ScanRule(
            id="category:anomalies",
            owner_type=RuleOwnerType.SYSTEM,
            name="Anomalies",
            conditions=[
                Condition("trades_z_score", Operator.GTE, 3.0),
            ],
            sort_field="trades_z_score",
            sort_descending=True,
        ),
        
        # NEW_HIGHS: precio dentro de 0.1% del maximo intraday
        ScanRule(
            id="category:new_highs",
            owner_type=RuleOwnerType.SYSTEM,
            name="New Highs",
            conditions=[
                Condition("price_from_intraday_high", Operator.GTE, -0.1),
                Condition("price", Operator.GTE, 1.0),
                Condition("volume_today", Operator.GT, 0),
            ],
            sort_field="price_from_intraday_high",
            sort_descending=True,
        ),
        
        # NEW_LOWS: precio dentro de 0.1% del minimo intraday
        ScanRule(
            id="category:new_lows",
            owner_type=RuleOwnerType.SYSTEM,
            name="New Lows",
            conditions=[
                Condition("price_from_intraday_low", Operator.LTE, 0.1),
                Condition("price", Operator.GTE, 1.0),
                Condition("volume_today", Operator.GT, 0),
            ],
            sort_field="price_from_intraday_low",
            sort_descending=False,
        ),
    ]


# Mapeo de category_id a nombre de canal WebSocket
CATEGORY_TO_CHANNEL = {
    "category:gappers_up": "gappers_up",
    "category:gappers_down": "gappers_down",
    "category:momentum_up": "momentum_up",
    "category:momentum_down": "momentum_down",
    "category:winners": "winners",
    "category:losers": "losers",
    "category:high_volume": "high_volume",
    "category:anomalies": "anomalies",
    "category:new_highs": "new_highs",
    "category:new_lows": "new_lows",
    "category:reversals": "reversals",
    "category:post_market": "post_market",
}
