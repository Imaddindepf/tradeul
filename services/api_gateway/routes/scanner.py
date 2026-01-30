"""
Scanner API Routes
Endpoints para filtrado de tickers del scanner.
"""
import json
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger("api_gateway.scanner")

# Redis client will be injected from main.py
redis_client = None

def set_redis_client(client):
    global redis_client
    redis_client = client

router = APIRouter(prefix="/api/scanner", tags=["scanner"])


class TickerResponse(BaseModel):
    symbol: str
    price: Optional[float] = None
    change_percent: Optional[float] = None
    gap_percent: Optional[float] = None
    volume: Optional[int] = None
    rvol: Optional[float] = None
    market_cap: Optional[float] = None


class FilteredResponse(BaseModel):
    tickers: List[TickerResponse]
    total: int
    filtered: int


@router.get("/filtered", response_model=FilteredResponse)
async def get_filtered_tickers(
    # Price filters
    price_min: Optional[float] = Query(None, description="Minimum price"),
    price_max: Optional[float] = Query(None, description="Maximum price"),
    # Change percent filters
    change_percent_min: Optional[float] = Query(None, description="Minimum change %"),
    change_percent_max: Optional[float] = Query(None, description="Maximum change %"),
    # Gap percent filters
    gap_percent_min: Optional[float] = Query(None, description="Minimum gap %"),
    gap_percent_max: Optional[float] = Query(None, description="Maximum gap %"),
    # Volume filters
    volume_min: Optional[int] = Query(None, description="Minimum volume"),
    volume_max: Optional[int] = Query(None, description="Maximum volume"),
    # RVOL filters
    rvol_min: Optional[float] = Query(None, description="Minimum relative volume"),
    rvol_max: Optional[float] = Query(None, description="Maximum relative volume"),
    # Market cap filters
    market_cap_min: Optional[float] = Query(None, description="Minimum market cap"),
    market_cap_max: Optional[float] = Query(None, description="Maximum market cap"),
    # Pagination
    limit: int = Query(100, ge=1, le=500, description="Max results"),
):
    """
    Filtra tickers del scanner basado en los parámetros dados.
    Lee del snapshot enriquecido en Redis.
    """
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis not available")
    
    try:
        # Leer snapshot de Redis
        data = await redis_client.get("snapshot:enriched:latest")
        if not data:
            logger.warning("No snapshot data found in Redis")
            return FilteredResponse(tickers=[], total=0, filtered=0)
        
        # Parsear JSON si es string, o usar directamente si ya es dict
        if isinstance(data, (str, bytes)):
            snapshot = json.loads(data)
        else:
            snapshot = data
        # El formato es {timestamp, count, tickers: [...]}
        all_tickers = snapshot.get("tickers", [])
        if isinstance(all_tickers, dict):
            all_tickers = list(all_tickers.values())
        total = len(all_tickers)
        
        # Aplicar filtros
        filtered = []
        for ticker in all_tickers:
            # Price filter (current_price o lastTrade.p)
            price = ticker.get("current_price")
            if price is None:
                last_trade = ticker.get("lastTrade", {})
                price = last_trade.get("p") if isinstance(last_trade, dict) else None
            
            if price_min is not None and (price is None or price < price_min):
                continue
            if price_max is not None and (price is None or price > price_max):
                continue
            
            # Change percent filter (todaysChangePerc)
            change = ticker.get("todaysChangePerc") or ticker.get("change_percent")
            if change_percent_min is not None and (change is None or change < change_percent_min):
                continue
            if change_percent_max is not None and (change is None or change > change_percent_max):
                continue
            
            # Gap percent filter
            gap = ticker.get("gap_percent") or ticker.get("gap_pct")
            if gap_percent_min is not None and (gap is None or gap < gap_percent_min):
                continue
            if gap_percent_max is not None and (gap is None or gap > gap_percent_max):
                continue
            
            # Volume filter (current_volume)
            vol = ticker.get("current_volume") or ticker.get("volume")
            if volume_min is not None and (vol is None or vol < volume_min):
                continue
            if volume_max is not None and (vol is None or vol > volume_max):
                continue
            
            # RVOL filter
            rvol = ticker.get("rvol") or ticker.get("relative_volume")
            if rvol_min is not None and (rvol is None or rvol < rvol_min):
                continue
            if rvol_max is not None and (rvol is None or rvol > rvol_max):
                continue
            
            # Market cap filter (fmv.marketCap)
            mcap = ticker.get("market_cap")
            if mcap is None:
                fmv = ticker.get("fmv", {})
                mcap = fmv.get("marketCap") if isinstance(fmv, dict) else None
            if market_cap_min is not None and (mcap is None or mcap < market_cap_min):
                continue
            if market_cap_max is not None and (mcap is None or mcap > market_cap_max):
                continue
            
            # Ticker passed all filters
            symbol = ticker.get("ticker") or ticker.get("symbol", "")
            filtered.append(TickerResponse(
                symbol=symbol,
                price=price,
                change_percent=change,
                gap_percent=gap,
                volume=vol,
                rvol=rvol,
                market_cap=mcap,
            ))
            
            if len(filtered) >= limit:
                break
        
        logger.info(f"scanner_filtered total={total} filtered={len(filtered)}")
        
        return FilteredResponse(
            tickers=filtered,
            total=total,
            filtered=len(filtered),
        )
        
    except Exception as e:
        logger.error(f"Error filtering tickers: {e}")
        return FilteredResponse(tickers=[], total=0, filtered=0)
