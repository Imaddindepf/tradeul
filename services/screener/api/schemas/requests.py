"""Request schemas"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Union, Literal, Optional


class FilterCondition(BaseModel):
    """A single filter condition"""
    
    field: str = Field(..., description="Indicator field name", examples=["rsi_14", "price", "volume"])
    operator: Literal["gt", "gte", "lt", "lte", "eq", "neq", "between", "cross_above", "cross_below"] = Field(
        ..., 
        description="Comparison operator"
    )
    value: Union[float, int, bool, str, List[float]] = Field(
        ..., 
        description="Value to compare against. Use array [min, max] for 'between' operator"
    )
    
    @field_validator("field")
    @classmethod
    def validate_field(cls, v):
        return v.lower().strip()
    
    @field_validator("operator")
    @classmethod  
    def validate_operator(cls, v):
        return v.lower().strip()


class ScreenerRequest(BaseModel):
    """Screener request payload"""
    
    filters: List[FilterCondition] = Field(
        default=[],
        description="List of filter conditions (AND logic)"
    )
    symbols: Optional[List[str]] = Field(
        default=None,
        description="Filter to specific symbols (e.g., ['AAPL', 'MSFT', 'IREN'])"
    )
    sort_by: str = Field(
        default="relative_volume",
        description="Field to sort results by"
    )
    sort_order: Literal["asc", "desc"] = Field(
        default="desc",
        description="Sort direction"
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum number of results"
    )
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "filters": [
                        {"field": "price", "operator": "between", "value": [10, 100]},
                        {"field": "rsi_14", "operator": "lt", "value": 35},
                        {"field": "volume", "operator": "gt", "value": 1000000},
                        {"field": "above_sma_50", "operator": "eq", "value": True}
                    ],
                    "sort_by": "relative_volume",
                    "sort_order": "desc",
                    "limit": 50
                }
            ]
        }
    }


class PresetSaveRequest(BaseModel):
    """Request to save a screener preset"""
    
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    filters: List[FilterCondition]
    sort_by: str = "relative_volume"
    sort_order: Literal["asc", "desc"] = "desc"
    is_public: bool = False

