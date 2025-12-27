"""
Screener API routes
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Any
import math
import structlog

from ..schemas import ScreenerRequest, ScreenerResponse
from core.engine import ScreenerEngine

logger = structlog.get_logger(__name__)


def clean_float_values(data: Any) -> Any:
    """Replace NaN and Infinity with None for JSON serialization"""
    if isinstance(data, dict):
        return {k: clean_float_values(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_float_values(v) for v in data]
    elif isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            return None
        return data
    return data

router = APIRouter(prefix="/screen", tags=["screener"])

# Engine instance (initialized in main.py lifespan)
_engine: ScreenerEngine = None


def get_engine() -> ScreenerEngine:
    """Dependency to get screener engine"""
    if _engine is None:
        raise HTTPException(status_code=503, detail="Screener engine not initialized")
    return _engine


def set_engine(engine: ScreenerEngine):
    """Set the engine instance (called from main.py)"""
    global _engine
    _engine = engine


@router.post("", response_model=ScreenerResponse)
async def run_screener(
    request: ScreenerRequest,
    engine: ScreenerEngine = Depends(get_engine)
):
    """
    Run stock screener with filters
    
    Execute a screener query with custom filters. All filters are combined with AND logic.
    
    Example filters:
    - Price between $10-$100: `{"field": "price", "operator": "between", "value": [10, 100]}`
    - RSI oversold: `{"field": "rsi_14", "operator": "lt", "value": 30}`
    - High volume: `{"field": "relative_volume", "operator": "gt", "value": 2}`
    - Above SMA 50: `{"field": "above_sma_50", "operator": "eq", "value": true}`
    """
    logger.info(
        "screener_request",
        filters_count=len(request.filters),
        sort_by=request.sort_by,
        limit=request.limit
    )
    
    # Convert filters to dict format
    filters = [f.model_dump() for f in request.filters]
    
    result = engine.screen(
        filters=filters,
        sort_by=request.sort_by,
        sort_order=request.sort_order,
        limit=request.limit,
        symbols=request.symbols
    )
    
    # Clean NaN/Infinity values for JSON serialization
    result = clean_float_values(result)
    
    logger.info(
        "screener_response",
        status=result["status"],
        count=result["count"],
        query_time_ms=result["query_time_ms"]
    )
    
    return ScreenerResponse(**result)


@router.get("/presets")
async def get_presets():
    """Get popular screener presets"""
    # Built-in presets
    return {
        "presets": [
            {
                "id": "oversold_bounce",
                "name": "Oversold Bounce",
                "description": "RSI oversold stocks with high volume",
                "filters": [
                    {"field": "rsi_14", "operator": "lt", "value": 30},
                    {"field": "relative_volume", "operator": "gt", "value": 1.5},
                    {"field": "price", "operator": "gt", "value": 5},
                ],
                "sort_by": "rsi_14",
                "sort_order": "asc"
            },
            {
                "id": "momentum_breakout",
                "name": "Momentum Breakout",
                "description": "Strong momentum above moving averages",
                "filters": [
                    {"field": "above_sma_20", "operator": "eq", "value": True},
                    {"field": "above_sma_50", "operator": "eq", "value": True},
                    {"field": "change_1d", "operator": "gt", "value": 3},
                    {"field": "relative_volume", "operator": "gt", "value": 2},
                ],
                "sort_by": "change_1d",
                "sort_order": "desc"
            },
            {
                "id": "high_volume_gappers",
                "name": "High Volume Gappers",
                "description": "Stocks gapping up with volume",
                "filters": [
                    {"field": "gap_percent", "operator": "gt", "value": 3},
                    {"field": "relative_volume", "operator": "gt", "value": 2},
                    {"field": "price", "operator": "between", "value": [5, 200]},
                ],
                "sort_by": "gap_percent",
                "sort_order": "desc"
            },
            {
                "id": "52w_high_breakout",
                "name": "52-Week High Breakout",
                "description": "Stocks near or at 52-week highs",
                "filters": [
                    {"field": "from_52w_high", "operator": "gt", "value": -5},
                    {"field": "volume", "operator": "gt", "value": 500000},
                    {"field": "change_1d", "operator": "gt", "value": 0},
                ],
                "sort_by": "from_52w_high",
                "sort_order": "desc"
            },
            {
                "id": "bollinger_squeeze",
                "name": "Bollinger Squeeze",
                "description": "Low volatility squeeze setup",
                "filters": [
                    {"field": "bb_squeeze", "operator": "eq", "value": True},
                    {"field": "volume", "operator": "gt", "value": 500000},
                ],
                "sort_by": "atr_percent",
                "sort_order": "asc"
            },
            {
                "id": "bullish_trend",
                "name": "Bullish Trend",
                "description": "Price above all major moving averages",
                "filters": [
                    {"field": "above_sma_20", "operator": "eq", "value": True},
                    {"field": "above_sma_50", "operator": "eq", "value": True},
                    {"field": "above_sma_200", "operator": "eq", "value": True},
                    {"field": "volume", "operator": "gt", "value": 500000},
                ],
                "sort_by": "change_1d",
                "sort_order": "desc"
            },
        ]
    }


@router.post("/refresh")
async def refresh_data(
    engine: ScreenerEngine = Depends(get_engine)
):
    """
    Hot refresh - reload data and recalculate all indicators.
    Call this after polygon-data downloads new files.
    Zero downtime - queries continue working during refresh.
    """
    logger.info("refresh_endpoint_called")
    result = engine.refresh()
    return result

