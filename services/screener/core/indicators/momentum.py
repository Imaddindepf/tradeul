"""
Momentum Indicators - Using precomputed screener_data columns
"""

from typing import List
from .base import IndicatorGroup, IndicatorDefinition, OperatorType, DataType


class MomentumIndicators(IndicatorGroup):
    """Momentum and oscillator indicators"""
    
    category = "momentum"
    description = "Momentum oscillators and signals"
    
    def get_indicators(self) -> List[IndicatorDefinition]:
        standard_ops = [OperatorType.GT, OperatorType.GTE, OperatorType.LT, OperatorType.LTE, OperatorType.BETWEEN]
        
        return [
            IndicatorDefinition(
                name="rsi_14",
                display_name="RSI (14)",
                description="14-period Relative Strength Index",
                category=self.category,
                data_type=DataType.FLOAT,
                sql_expression="rsi_14",
                operators=standard_ops,
                min_value=0,
                max_value=100,
                format_string="{:.1f}",
            ),
            IndicatorDefinition(
                name="rsi_oversold",
                display_name="RSI Oversold",
                description="RSI below 30 (oversold)",
                category=self.category,
                data_type=DataType.BOOLEAN,
                sql_expression="CASE WHEN rsi_14 < 30 THEN 1 ELSE 0 END",
                operators=[OperatorType.EQ],
            ),
            IndicatorDefinition(
                name="rsi_overbought",
                display_name="RSI Overbought",
                description="RSI above 70 (overbought)",
                category=self.category,
                data_type=DataType.BOOLEAN,
                sql_expression="CASE WHEN rsi_14 > 70 THEN 1 ELSE 0 END",
                operators=[OperatorType.EQ],
            ),
        ]
    
    def get_sql_cte(self) -> str:
        return ""
