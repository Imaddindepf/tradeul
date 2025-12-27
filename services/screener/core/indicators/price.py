"""
Price and Returns Indicators - Using precomputed screener_data columns
"""

from typing import List
from .base import IndicatorGroup, IndicatorDefinition, OperatorType, DataType


class PriceIndicators(IndicatorGroup):
    """Price, returns, and gap indicators"""
    
    category = "price"
    description = "Price levels and percentage changes"
    
    def get_indicators(self) -> List[IndicatorDefinition]:
        standard_ops = [OperatorType.GT, OperatorType.GTE, OperatorType.LT, OperatorType.LTE, OperatorType.BETWEEN]
        
        return [
            IndicatorDefinition(
                name="price",
                display_name="Price",
                description="Current closing price",
                category=self.category,
                data_type=DataType.FLOAT,
                sql_expression="price",
                operators=standard_ops,
                min_value=0,
                format_string="${:.2f}",
            ),
            IndicatorDefinition(
                name="change_1d",
                display_name="Change 1D %",
                description="1-day price change percentage",
                category=self.category,
                data_type=DataType.PERCENT,
                sql_expression="change_1d",
                operators=standard_ops,
                format_string="{:+.2f}%",
            ),
            IndicatorDefinition(
                name="change_5d",
                display_name="Change 5D %",
                description="5-day price change percentage",
                category=self.category,
                data_type=DataType.PERCENT,
                sql_expression="change_5d",
                operators=standard_ops,
                format_string="{:+.2f}%",
            ),
            IndicatorDefinition(
                name="change_20d",
                display_name="Change 1M %",
                description="20-day (1 month) price change percentage",
                category=self.category,
                data_type=DataType.PERCENT,
                sql_expression="change_20d",
                operators=standard_ops,
                format_string="{:+.2f}%",
            ),
            IndicatorDefinition(
                name="gap_percent",
                display_name="Gap %",
                description="Gap from previous close to today's open",
                category=self.category,
                data_type=DataType.PERCENT,
                sql_expression="gap_percent",
                operators=standard_ops,
                format_string="{:+.2f}%",
            ),
            IndicatorDefinition(
                name="high_52w",
                display_name="52W High",
                description="52-week high price",
                category=self.category,
                data_type=DataType.FLOAT,
                sql_expression="high_52w",
                operators=standard_ops,
                format_string="${:.2f}",
            ),
            IndicatorDefinition(
                name="low_52w",
                display_name="52W Low",
                description="52-week low price",
                category=self.category,
                data_type=DataType.FLOAT,
                sql_expression="low_52w",
                operators=standard_ops,
                format_string="${:.2f}",
            ),
            IndicatorDefinition(
                name="from_52w_high",
                display_name="From 52W High %",
                description="Distance from 52-week high",
                category=self.category,
                data_type=DataType.PERCENT,
                sql_expression="from_52w_high",
                operators=standard_ops,
                max_value=0,
                format_string="{:.2f}%",
            ),
            IndicatorDefinition(
                name="from_52w_low",
                display_name="From 52W Low %",
                description="Distance from 52-week low",
                category=self.category,
                data_type=DataType.PERCENT,
                sql_expression="from_52w_low",
                operators=standard_ops,
                min_value=0,
                format_string="{:+.2f}%",
            ),
        ]
    
    def get_sql_cte(self) -> str:
        return ""
