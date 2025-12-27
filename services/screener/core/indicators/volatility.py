"""
Volatility Indicators - Using precomputed screener_data columns
"""

from typing import List
from .base import IndicatorGroup, IndicatorDefinition, OperatorType, DataType


class VolatilityIndicators(IndicatorGroup):
    """Volatility and range indicators"""
    
    category = "volatility"
    description = "Volatility and price range indicators"
    
    def get_indicators(self) -> List[IndicatorDefinition]:
        standard_ops = [OperatorType.GT, OperatorType.GTE, OperatorType.LT, OperatorType.LTE, OperatorType.BETWEEN]
        
        return [
            IndicatorDefinition(
                name="atr_14",
                display_name="ATR (14)",
                description="14-day Average True Range",
                category=self.category,
                data_type=DataType.FLOAT,
                sql_expression="atr_14",
                operators=standard_ops,
                min_value=0,
                format_string="${:.2f}",
            ),
            IndicatorDefinition(
                name="atr_percent",
                display_name="ATR %",
                description="ATR as percentage of price",
                category=self.category,
                data_type=DataType.PERCENT,
                sql_expression="atr_percent",
                operators=standard_ops,
                min_value=0,
                format_string="{:.2f}%",
            ),
            IndicatorDefinition(
                name="bb_upper",
                display_name="BB Upper",
                description="Bollinger Band Upper (20,2)",
                category=self.category,
                data_type=DataType.FLOAT,
                sql_expression="bb_upper",
                operators=standard_ops,
                format_string="${:.2f}",
            ),
            IndicatorDefinition(
                name="bb_middle",
                display_name="BB Middle",
                description="Bollinger Band Middle (SMA 20)",
                category=self.category,
                data_type=DataType.FLOAT,
                sql_expression="bb_middle",
                operators=standard_ops,
                format_string="${:.2f}",
            ),
            IndicatorDefinition(
                name="bb_lower",
                display_name="BB Lower",
                description="Bollinger Band Lower (20,2)",
                category=self.category,
                data_type=DataType.FLOAT,
                sql_expression="bb_lower",
                operators=standard_ops,
                format_string="${:.2f}",
            ),
            IndicatorDefinition(
                name="bb_width",
                display_name="BB Width %",
                description="Bollinger Band Width as percentage",
                category=self.category,
                data_type=DataType.PERCENT,
                sql_expression="bb_width",
                operators=standard_ops,
                min_value=0,
                format_string="{:.2f}%",
            ),
            IndicatorDefinition(
                name="bb_position",
                display_name="BB Position %",
                description="Price position within BB (0=lower, 100=upper)",
                category=self.category,
                data_type=DataType.PERCENT,
                sql_expression="bb_position",
                operators=standard_ops,
                min_value=0,
                max_value=100,
                format_string="{:.1f}%",
            ),
            IndicatorDefinition(
                name="bb_squeeze",
                display_name="BB Squeeze",
                description="Bollinger Band squeeze (width < 10%)",
                category=self.category,
                data_type=DataType.BOOLEAN,
                sql_expression="CASE WHEN bb_width < 10 THEN 1 ELSE 0 END",
                operators=[OperatorType.EQ],
            ),
            IndicatorDefinition(
                name="above_bb_upper",
                display_name="Above BB Upper",
                description="Price above upper Bollinger Band",
                category=self.category,
                data_type=DataType.BOOLEAN,
                sql_expression="CASE WHEN price > bb_upper THEN 1 ELSE 0 END",
                operators=[OperatorType.EQ],
            ),
            IndicatorDefinition(
                name="below_bb_lower",
                display_name="Below BB Lower",
                description="Price below lower Bollinger Band",
                category=self.category,
                data_type=DataType.BOOLEAN,
                sql_expression="CASE WHEN price < bb_lower THEN 1 ELSE 0 END",
                operators=[OperatorType.EQ],
            ),
        ]
    
    def get_sql_cte(self) -> str:
        return ""
