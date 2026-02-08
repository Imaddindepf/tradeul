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
        # GAPPERS_UP: Gap >= 2%, volume > 0 (sin filtro de precio - usuario configura)
        ScanRule(
            id="category:gappers_up",
            owner_type=RuleOwnerType.SYSTEM,
            name="Gappers Up",
            conditions=[
                Condition("gap_percent", Operator.GTE, 2.0),
                Condition("volume_today", Operator.GT, 0),
            ],
            sort_field="gap_percent",
            sort_descending=True,
        ),
        
        # GAPPERS_DOWN: Gap <= -2%, volume > 0 (sin filtro de precio - usuario configura)
        ScanRule(
            id="category:gappers_down",
            owner_type=RuleOwnerType.SYSTEM,
            name="Gappers Down",
            conditions=[
                Condition("gap_percent", Operator.LTE, -2.0),
                Condition("volume_today", Operator.GT, 0),
            ],
            sort_field="gap_percent",
            sort_descending=False,
        ),
        
        # MOMENTUM_UP (HOD MOMENTUM - BALANCED FOR ALL CAPS)
        # Stocks "running up" haciendo máximos con volumen
        # Basado en Trade Ideas / Warrior Trading - adaptado para ALL CAPS
        # Criterios balanceados que incluyen large caps como CMG, MCD
        ScanRule(
            id="category:momentum_up",
            owner_type=RuleOwnerType.SYSTEM,
            name="Momentum Up",
            conditions=[
                Condition("price_from_intraday_high", Operator.GTE, -1.0),  # Máx 1% del HOD
                Condition("change_percent", Operator.GTE, 1.0),             # Mínimo 1% del día (large cap friendly)
                Condition("price_vs_vwap", Operator.GT, 0),                 # Sobre VWAP
                Condition("rvol", Operator.GTE, 1.5),                       # RVOL >= 150% (watchable)
                Condition("volume_today", Operator.GTE, 100000),            # Mínimo 100K volumen (liquidez)
            ],
            sort_field="change_percent",
            sort_descending=True,
        ),
        
        # MOMENTUM_DOWN (LOD MOMENTUM - BALANCED FOR ALL CAPS)
        # Stocks "falling" haciendo mínimos con volumen
        # Espejo de MOMENTUM_UP pero para caídas - adaptado para ALL CAPS
        ScanRule(
            id="category:momentum_down",
            owner_type=RuleOwnerType.SYSTEM,
            name="Momentum Down",
            conditions=[
                Condition("price_from_intraday_low", Operator.LTE, 1.0),  # Máx 1% del LOD
                Condition("change_percent", Operator.LTE, -1.0),          # Mínimo -1% del día (large cap friendly)
                Condition("price_vs_vwap", Operator.LT, 0),               # Bajo VWAP
                Condition("rvol", Operator.GTE, 1.5),                     # RVOL >= 150% (watchable)
                Condition("volume_today", Operator.GTE, 100000),          # Mínimo 100K volumen (liquidez)
            ],
            sort_field="change_percent",
            sort_descending=False,
        ),
        
        # WINNERS: change >= 5% con liquidez mínima (RVOL >= 1.5)
        ScanRule(
            id="category:winners",
            owner_type=RuleOwnerType.SYSTEM,
            name="Winners",
            conditions=[
                Condition("change_percent", Operator.GTE, 5.0),
                Condition("rvol", Operator.GTE, 1.5),  # Liquidez mínima
            ],
            sort_field="change_percent",
            sort_descending=True,
        ),
        
        # LOSERS: change <= -5% con liquidez mínima (RVOL >= 1.5)
        ScanRule(
            id="category:losers",
            owner_type=RuleOwnerType.SYSTEM,
            name="Losers",
            conditions=[
                Condition("change_percent", Operator.LTE, -5.0),
                Condition("rvol", Operator.GTE, 1.5),  # Liquidez mínima
            ],
            sort_field="change_percent",
            sort_descending=False,
        ),
        
        # HIGH_VOLUME: RVOL >= 2.0 (sin filtro de precio)
        ScanRule(
            id="category:high_volume",
            owner_type=RuleOwnerType.SYSTEM,
            name="High Volume",
            conditions=[
                Condition("rvol", Operator.GTE, 2.0),
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
        
        # NEW_HIGHS: precio dentro de 0.1% del máximo intraday (sin filtro de precio)
        ScanRule(
            id="category:new_highs",
            owner_type=RuleOwnerType.SYSTEM,
            name="New Highs",
            conditions=[
                Condition("price_from_intraday_high", Operator.GTE, -0.1),
                Condition("volume_today", Operator.GT, 0),
            ],
            sort_field="price_from_intraday_high",
            sort_descending=True,
        ),
        
        # NEW_LOWS: precio dentro de 0.1% del mínimo intraday (sin filtro de precio)
        ScanRule(
            id="category:new_lows",
            owner_type=RuleOwnerType.SYSTEM,
            name="New Lows",
            conditions=[
                Condition("price_from_intraday_low", Operator.LTE, 0.1),
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
