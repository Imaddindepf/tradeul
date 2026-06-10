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

import re
import time
from datetime import datetime as dt
from typing import Optional, List, Tuple

from shared.utils.logger import get_logger

logger = get_logger(__name__)


def _instrument_suffix(ticker: str) -> str:
    """
    Return the instrument-type suffix of a ticker, or '' for common stock.

    Polygon uses the trailing letter(s) to distinguish related instruments
    issued by the same company:
      W  → warrants   (SOUNW, SBFMW …)
      R  → rights     (AACGR …)
      U  → units      (OACCU …)
      p  → preferred  (TFINp, LOBpA …)

    A chain between two tickers is only valid when both have the SAME suffix
    (i.e. both are common stock, or both are warrants, etc.). Mixing types —
    e.g. SBFM (common) ↔ SBFMW (warrant) — produces false chains that redirect
    the common-stock chart to warrant price data.

    This guardrail mirrors the same logic in
    services/data_maintenance/tasks/build_ticker_chain.py so the API gateway
    never serves a chained chart that crosses instrument types, even if the
    underlying Redis hash was populated by an older (buggy) builder version.
    """
    if not ticker:
        return ''
    if re.search(r'p[A-Z]?$', ticker):
        return 'p'
    m = re.search(r'[WRU]$', ticker)
    return m.group(0) if m else ''


def _filter_chain_by_suffix(symbol: str, chain: Optional[List[str]]) -> Optional[List[str]]:
    """
    Drop chain members whose instrument suffix differs from `symbol`.

    Returns None if the filtered chain has fewer than 2 entries (in that case
    there is effectively no chain and the caller should fall back to a single-
    symbol fetch).
    """
    if not chain:
        return chain
    target = _instrument_suffix(symbol)
    filtered = [t for t in chain if _instrument_suffix(t) == target]
    if len(filtered) < 2:
        if filtered != chain:
            logger.warning(
                "ticker_chain_mixed_suffix_filtered_out",
                symbol=symbol,
                original_chain=chain,
                target_suffix=target,
            )
        return None
    if filtered != chain:
        logger.warning(
            "ticker_chain_mixed_suffix_filtered",
            symbol=symbol,
            original_chain=chain,
            filtered_chain=filtered,
            target_suffix=target,
        )
    return filtered

# In-process cache to avoid repeated Redis calls
# {symbol: (chain_or_None, timestamp)}
_chain_cache: dict[str, tuple] = {}
_CACHE_TTL = 3600  # 1 hour
_reverse_chain_cache: dict[str, tuple] = {}  # {symbol: (chain, timestamp)}

# Vendor feeds can miss or lag corporate-action chains.
# Manual overrides guarantee continuity for critical symbols.
MANUAL_CHAIN_OVERRIDES: dict[str, List[str]] = {
    # Cantor Equity Partners -> Twenty One Capital
    "CEP": ["CEP", "XXI"],
    "XXI": ["CEP", "XXI"],
    # Facebook -> Meta Platforms. The ticker "META" was ALSO used by the
    # Roundhill Ball Metaverse ETF (now "METV") before 2022, so Polygon's
    # ticker_change graph links META -> METV. Without this override a stale
    # Redis hash can resolve the META chart to the ETF (~$19) instead of
    # Meta Platforms (>$500). Pin META/FB to the correct common-stock chain.
    "META": ["FB", "META"],
    "FB": ["FB", "META"],
}


def _normalize_chain(raw_chain: object) -> Optional[List[str]]:
    """Normalize Redis value into an uppercase list chain."""
    if not isinstance(raw_chain, list) or not raw_chain:
        return None
    normalized = [str(s).upper() for s in raw_chain if s]
    return normalized if normalized else None


async def _get_chain_from_reverse_index(symbol: str, redis_client, now: float) -> Optional[List[str]]:
    """
    Resolve symbol -> chain by scanning all chains once per TTL.
    This covers legacy tickers that are not hash keys (e.g. XXII -> CEP).
    """
    cached = _reverse_chain_cache.get(symbol)
    if cached and now - cached[1] < _CACHE_TTL:
        return cached[0]

    all_chains = await redis_client.hgetall("ticker:chain")
    if not all_chains:
        _reverse_chain_cache[symbol] = (None, now)
        return None

    best_chain: Optional[List[str]] = None
    for _, raw_chain in all_chains.items():
        chain = _normalize_chain(raw_chain)
        if not chain:
            continue
        if symbol in chain:
            # Prefer the longest chain when multiple matches exist.
            if best_chain is None or len(chain) > len(best_chain):
                best_chain = chain

    # Guardrail: never cross instrument types via the reverse index.
    best_chain = _filter_chain_by_suffix(symbol, best_chain)

    _reverse_chain_cache[symbol] = (best_chain, now)
    if best_chain:
        logger.info("ticker_chain_resolved_via_reverse_index", symbol=symbol, chain=best_chain)
    return best_chain


async def get_ticker_chain(symbol: str, redis_client) -> Optional[List[str]]:
    """
    Get the ticker chain for a symbol.
    
    Returns:
        List of tickers ordered old→new (e.g. ["FB", "META"]), or None if no chain.
    """
    symbol = symbol.upper()
    now = time.time()

    # Hard override first (deterministic, no Redis dependency).
    if symbol in MANUAL_CHAIN_OVERRIDES:
        return MANUAL_CHAIN_OVERRIDES[symbol]
    
    # Check in-process cache first
    if symbol in _chain_cache:
        cached_val, cached_at = _chain_cache[symbol]
        if now - cached_at < _CACHE_TTL:
            return cached_val
    
    # Fetch from direct Redis hash lookup first
    chain = await redis_client.hget("ticker:chain", symbol)
    chain = _normalize_chain(chain)

    # Guardrail: drop chains that mix instrument types (e.g. common+warrant).
    # The Redis hash is built by a background job that has historically
    # generated cross-instrument chains from Polygon's noisy ticker_change
    # events. This filter keeps the API correct even if Redis is stale.
    chain = _filter_chain_by_suffix(symbol, chain)

    # Fallback: reverse index for legacy/inactive symbols
    if chain is None:
        chain = await _get_chain_from_reverse_index(symbol, redis_client, now)

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
    fetch_fn,
    fetch_legacy_daily_fn=None,
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

        # Fallback for legacy aliases missing in Polygon (daily chains only).
        if (
            not bars
            and fetch_legacy_daily_fn is not None
            and timespan == "day"
        ):
            legacy_bars, _ = await fetch_legacy_daily_fn(
                ticker,
                current_to_date,
                remaining
            )
            if current_before:
                legacy_bars = [b for b in legacy_bars if b.get("time", 0) < current_before]
            bars = legacy_bars[-remaining:] if len(legacy_bars) > remaining else legacy_bars
        
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
