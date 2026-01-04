"""
Fundamental Indicators - Market Cap, Float, Sector
"""

from typing import List
from .base import IndicatorGroup, IndicatorDefinition, OperatorType, DataType


class FundamentalIndicators(IndicatorGroup):
    """Market Cap, Float, and other fundamental data"""
    
    category = "fundamentals"
    description = "Fundamental company data"
    
    def get_indicators(self) -> List[IndicatorDefinition]:
        standard_ops = [OperatorType.GT, OperatorType.GTE, OperatorType.LT, OperatorType.LTE, OperatorType.BETWEEN]
        
        return [
            IndicatorDefinition(
                name="market_cap",
                display_name="Market Cap",
                description="Market capitalization in USD",
                category=self.category,
                data_type=DataType.INTEGER,
                sql_expression="market_cap",
                operators=standard_ops,
                min_value=0,
                format_string="{:,.0f}",
            ),
            IndicatorDefinition(
                name="free_float",
                display_name="Float",
                description="Number of floating shares",
                category=self.category,
                data_type=DataType.INTEGER,
                sql_expression="free_float",
                operators=standard_ops,
                min_value=0,
                format_string="{:,.0f}",
            ),
        ]
    
    def get_sql_cte(self) -> str:
        return ""

