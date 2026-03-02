"""
Ticker Chain - Historical Symbol Mapping
=========================================

Mapea tickers actuales a sus símbolos anteriores para obtener
gráficos históricos completos desde Polygon.

Ejemplo: META → ["FB", "META"]
- Polygon solo devuelve datos bajo el ticker activo en esa fecha
- FB tiene datos hasta Jun 2022, META desde Jun 2022+
- Este módulo encadena ambos automáticamente

Datos vienen de Redis hash ticker:chain (poblado por data_maintenance).
92% de tickers NO tienen cadena → overhead = 1 HGET (~0.05ms).
"""

import time
from datetime import datetime as dt
from typing import Optional, List, Tuple

from shared.utils.logger import get_logger

logger = get_logger(__name__)

# In-process cache to avoid repeated Redis calls
# {symbol: (chain_or_None, timestamp)}
_chain_cache: dict[str, tuple] = {}
_CACHE_TTL = 3600  # 1 hour


async def get_ticker_chain(symbol: str, redis_client) -> Optional[List[str]]:
    """
    Get the ticker chain for a symbol.
    
    Returns:
        List of tickers ordered old→new (e.g. ["FB", "META"]), or None if no chain.
    """
    now = time.time()
    
    # Check in-process cache first
    if symbol in _chain_cache:
        cached_val, cached_at = _chain_cache[symbol]
        if now - cached_at < _CACHE_TTL:
            return cached_val
    
    # Fetch from Redis hash
    chain = await redis_client.hget("ticker:chain", symbol)
    
    # Cache result (including None for tickers without chains)
    _chain_cache[symbol] = (chain, now)
    
    return chain


async def fetch_chained_polygon_data(
    symbol: str,
    multiplier: int,
    timespan: str,
    to_date: str,
    bars_limit: int,
    before_timestamp: Optional[int],
    chain: List[str],
    fetch_fn
) -> Tuple[List[dict], Optional[int]]:
    """
    Fetch chart data across a ticker chain.
    
    Iterates from newest ticker to oldest, filling bars until limit is reached.
    All bars are normalized to the current (requested) symbol.
    
    Args:
        symbol: Current ticker symbol (e.g. "META")
        multiplier: Polygon multiplier
        timespan: Polygon timespan
        to_date: End date string
        bars_limit: Number of bars to fetch
        before_timestamp: Unix timestamp for lazy loading (or None)
        chain: Ordered list old→new (e.g. ["FB", "META"])
        fetch_fn: Reference to fetch_polygon_chunk function
    
    Returns:
        (bars, oldest_timestamp) - same signature as fetch_polygon_chunk
    """
    # Find current symbol's position in chain
    try:
        current_idx = chain.index(symbol)
    except ValueError:
        current_idx = len(chain) - 1
    
    all_bars = []
    remaining = bars_limit
    current_before = before_timestamp
    current_to_date = to_date
    
    # Iterate from current ticker backwards through chain
    for i in range(current_idx, -1, -1):
        ticker = chain[i]
        
        bars, oldest_time = await fetch_fn(
            ticker, multiplier, timespan, current_to_date, remaining,
            before_timestamp=current_before
        )
        
        if bars:
            # Normalize symbol to the requested ticker
            if ticker != symbol:
                for bar in bars:
                    bar["symbol"] = symbol
            
            all_bars = bars + all_bars  # prepend older bars
            remaining -= len(bars)
            
            # Set boundary for the next (older) ticker
            current_before = all_bars[0]["time"]
            current_to_date = dt.fromtimestamp(all_bars[0]["time"]).strftime("%Y-%m-%d")
            
            logger.info(
                "chain_segment_fetched",
                requested=symbol,
                fetched_from=ticker,
                bars=len(bars),
                remaining=remaining
            )
        else:
            # No bars from this ticker at this date range.
            # If this is NOT the oldest ticker in the chain, keep going
            # (the current ticker may just not have data for this period).
            logger.info(
                "chain_segment_empty",
                requested=symbol,
                fetched_from=ticker,
                to_date=current_to_date,
                before=current_before
            )
        
        if remaining <= 0:
            break
    
    oldest_time = all_bars[0]["time"] if all_bars else None
    
    logger.info(
        "chained_fetch_complete",
        symbol=symbol,
        chain=chain,
        total_bars=len(all_bars),
        oldest_time=oldest_time
    )
    
    return all_bars, oldest_time
