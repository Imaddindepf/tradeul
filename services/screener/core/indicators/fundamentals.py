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
        
        # Sanity ceilings: catch UI unit-scaling bugs (K/M/B select mismatch)
        # before they become silent count=0 responses.
        # Largest market cap on record is ~$4T; we leave a generous margin.
        MARKET_CAP_MAX = 100_000_000_000_000  # $100T
        FLOAT_MAX = 1_000_000_000_000          # 1T shares

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
                max_value=MARKET_CAP_MAX,
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
                max_value=FLOAT_MAX,
                format_string="{:,.0f}",
            ),
            IndicatorDefinition(
                name="sector",
                display_name="Sector",
                description="GICS sector classification",
                category=self.category,
                data_type=DataType.STRING,
                sql_expression="sector",
                operators=[OperatorType.EQ, OperatorType.NEQ],
            ),
        ]
    
    def get_sql_cte(self) -> str:
        return ""

