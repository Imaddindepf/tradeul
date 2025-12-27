"""
Trend Indicators - Using precomputed screener_data columns
"""

from typing import List
from .base import IndicatorGroup, IndicatorDefinition, OperatorType, DataType


class TrendIndicators(IndicatorGroup):
    """Trend following indicators"""
    
    category = "trend"
    description = "Trend direction and strength indicators"
    
    def get_indicators(self) -> List[IndicatorDefinition]:
        standard_ops = [OperatorType.GT, OperatorType.GTE, OperatorType.LT, OperatorType.LTE, OperatorType.BETWEEN]
        
        return [
            IndicatorDefinition(
                name="sma_20",
                display_name="SMA 20",
                description="20-day Simple Moving Average",
                category=self.category,
                data_type=DataType.FLOAT,
                sql_expression="sma_20",
                operators=standard_ops,
                format_string="${:.2f}",
            ),
            IndicatorDefinition(
                name="sma_50",
                display_name="SMA 50",
                description="50-day Simple Moving Average",
                category=self.category,
                data_type=DataType.FLOAT,
                sql_expression="sma_50",
                operators=standard_ops,
                format_string="${:.2f}",
            ),
            IndicatorDefinition(
                name="sma_200",
                display_name="SMA 200",
                description="200-day Simple Moving Average",
                category=self.category,
                data_type=DataType.FLOAT,
                sql_expression="sma_200",
                operators=standard_ops,
                format_string="${:.2f}",
            ),
            IndicatorDefinition(
                name="above_sma_20",
                display_name="Above SMA 20",
                description="Price is above SMA 20",
                category=self.category,
                data_type=DataType.BOOLEAN,
                sql_expression="CASE WHEN price > sma_20 THEN 1 ELSE 0 END",
                operators=[OperatorType.EQ],
            ),
            IndicatorDefinition(
                name="above_sma_50",
                display_name="Above SMA 50",
                description="Price is above SMA 50",
                category=self.category,
                data_type=DataType.BOOLEAN,
                sql_expression="CASE WHEN price > sma_50 THEN 1 ELSE 0 END",
                operators=[OperatorType.EQ],
            ),
            IndicatorDefinition(
                name="above_sma_200",
                display_name="Above SMA 200",
                description="Price is above SMA 200",
                category=self.category,
                data_type=DataType.BOOLEAN,
                sql_expression="CASE WHEN price > sma_200 THEN 1 ELSE 0 END",
                operators=[OperatorType.EQ],
            ),
            IndicatorDefinition(
                name="dist_sma_20",
                display_name="Dist SMA 20 %",
                description="Distance from SMA 20 in percentage",
                category=self.category,
                data_type=DataType.PERCENT,
                sql_expression="dist_sma_20",
                operators=standard_ops,
                format_string="{:+.2f}%",
            ),
            IndicatorDefinition(
                name="dist_sma_50",
                display_name="Dist SMA 50 %",
                description="Distance from SMA 50 in percentage",
                category=self.category,
                data_type=DataType.PERCENT,
                sql_expression="dist_sma_50",
                operators=standard_ops,
                format_string="{:+.2f}%",
            ),
            IndicatorDefinition(
                name="sma_50_above_200",
                display_name="SMA50 > SMA200",
                description="SMA 50 is above SMA 200 (bullish)",
                category=self.category,
                data_type=DataType.BOOLEAN,
                sql_expression="CASE WHEN sma_50 > sma_200 THEN 1 ELSE 0 END",
                operators=[OperatorType.EQ],
            ),
        ]
    
    def get_sql_cte(self) -> str:
        return ""
