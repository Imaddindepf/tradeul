"""
Indicators API routes
"""

from fastapi import APIRouter, Depends
import structlog

from ..schemas import IndicatorsResponse
from core.engine import ScreenerEngine
from .screener import get_engine

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/indicators", tags=["indicators"])


@router.get("", response_model=dict)
async def get_indicators(engine: ScreenerEngine = Depends(get_engine)):
    """
    Get all available indicators
    
    Returns a dictionary of indicators grouped by category.
    Each indicator includes:
    - name: Field name to use in filters
    - display_name: Human-readable name
    - description: What the indicator measures
    - data_type: float, integer, boolean, percent
    - operators: Valid comparison operators
    """
    indicators = engine.get_indicators()
    
    total = sum(len(v) for v in indicators.values())
    
    return {
        "categories": indicators,
        "total_count": total
    }


@router.get("/categories")
async def get_categories(engine: ScreenerEngine = Depends(get_engine)):
    """Get list of indicator categories"""
    indicators = engine.get_indicators()
    
    return {
        "categories": [
            {
                "id": cat,
                "name": cat.replace("_", " ").title(),
                "count": len(items)
            }
            for cat, items in indicators.items()
        ]
    }


@router.get("/{indicator_name}")
async def get_indicator_info(
    indicator_name: str,
    engine: ScreenerEngine = Depends(get_engine)
):
    """Get detailed information about a specific indicator"""
    indicator = engine.registry.get_indicator(indicator_name)
    
    if not indicator:
        return {"error": f"Indicator '{indicator_name}' not found"}
    
    return {
        "name": indicator.name,
        "display_name": indicator.display_name,
        "description": indicator.description,
        "category": indicator.category,
        "data_type": indicator.data_type.value,
        "operators": [op.value for op in indicator.operators],
        "min_value": indicator.min_value,
        "max_value": indicator.max_value,
        "format": indicator.format_string,
    }

