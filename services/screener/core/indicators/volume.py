"""
Volume Indicators - Using precomputed screener_data columns
"""

from typing import List
from .base import IndicatorGroup, IndicatorDefinition, OperatorType, DataType


class VolumeIndicators(IndicatorGroup):
    """Volume and liquidity indicators"""
    
    category = "volume"
    description = "Volume and liquidity metrics"
    
    def get_indicators(self) -> List[IndicatorDefinition]:
        standard_ops = [OperatorType.GT, OperatorType.GTE, OperatorType.LT, OperatorType.LTE, OperatorType.BETWEEN]
        
        return [
            IndicatorDefinition(
                name="volume",
                display_name="Volume",
                description="Current day volume",
                category=self.category,
                data_type=DataType.INTEGER,
                sql_expression="volume",
                operators=standard_ops,
                min_value=0,
                format_string="{:,.0f}",
            ),
            IndicatorDefinition(
                name="avg_volume_20",
                display_name="Avg Vol 20D",
                description="20-day average volume",
                category=self.category,
                data_type=DataType.INTEGER,
                sql_expression="avg_volume_20",
                operators=standard_ops,
                min_value=0,
                format_string="{:,.0f}",
            ),
            IndicatorDefinition(
                name="relative_volume",
                display_name="Rel Volume",
                description="Volume relative to 20-day average (RVOL)",
                category=self.category,
                data_type=DataType.FLOAT,
                sql_expression="relative_volume",
                operators=standard_ops,
                min_value=0,
                format_string="{:.2f}x",
            ),
            IndicatorDefinition(
                name="dollar_volume",
                display_name="$ Volume",
                description="Dollar volume (price x volume)",
                category=self.category,
                data_type=DataType.INTEGER,
                sql_expression="price * volume",
                operators=standard_ops,
                min_value=0,
                format_string="${:,.0f}",
            ),
            IndicatorDefinition(
                name="volume_spike",
                display_name="Volume Spike",
                description="Volume is 2x+ above 20D average",
                category=self.category,
                data_type=DataType.BOOLEAN,
                sql_expression="CASE WHEN relative_volume > 2 THEN 1 ELSE 0 END",
                operators=[OperatorType.EQ],
            ),
        ]
    
    def get_sql_cte(self) -> str:
        return ""
