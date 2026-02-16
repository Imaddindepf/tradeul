"""
Market Data Agent - Real-time scanner snapshots and enriched ticker data.

MCP tools:
  - scanner.get_enriched_batch   → enriched data for specific tickers
  - scanner.get_scanner_snapshot → top movers / gappers / volume leaders
  - scanner.get_market_session   → current market session info

Data cleaning:
  - Enriched: 145 fields → ~25 essential fields per ticker
  - Scanner: 100 items × 145 fields → capped + cleaned to key columns
"""
from __future__ import annotations
import re
import time
from typing import Any

from agents._mcp_tools import call_mcp_tool


# ── Historical data detection ────────────────────────────────────
_HISTORICAL_DAILY_KW = [
    "datos diarios", "daily data", "day bars", "barras diarias",
    "historical", "historial", "precio de la semana", "última semana",
    "last week", "chart", "gráfico",
]

_HISTORICAL_MINUTE_KW = [
    "minuto", "minute", "intraday", "barras por minuto",
    "minute bars", "intradía", "1min", "5min",
]


def _wants_historical_daily(q: str) -> bool:
    return any(kw in q.lower() for kw in _HISTORICAL_DAILY_KW)


def _wants_historical_minute(q: str) -> bool:
    return any(kw in q.lower() for kw in _HISTORICAL_MINUTE_KW)


# ── Category mapping ─────────────────────────────────────────────
_CATEGORY_MAP: dict[str, list[str]] = {
    "winners": ["winners"], "gainers": ["winners"], "ganadoras": ["winners"],
    "mejores": ["winners"], "top": ["winners"], "best": ["winners"],
    "subiendo": ["winners"],
    "losers": ["losers"], "perdedoras": ["losers"], "peores": ["losers"],
    "worst": ["losers"], "bajando": ["losers"], "caidas": ["losers"],
    "gapper": ["gappers_up", "gappers_down"], "gap up": ["gappers_up"],
    "gap down": ["gappers_down"], "gappers": ["gappers_up"],
    "premarket": ["gappers_up", "gappers_down"],
    "momentum": ["momentum_up"], "runners": ["momentum_up"],
    "running": ["momentum_up"], "movers": ["momentum_up", "momentum_down"],
    "volume": ["high_volume"], "volumen": ["high_volume"], "vol": ["high_volume"],
    "halt": ["halts"], "halted": ["halts"], "halts": ["halts"],
    "reversals": ["reversals"], "anomalies": ["anomalies"],
    "new highs": ["new_highs"], "new lows": ["new_lows"],
    "post market": ["post_market"], "after hours": ["post_market"],
}


def _detect_categories(query: str) -> list[str]:
    """Detect which scanner categories the user is asking about."""
    q_lower = query.lower()
    categories: list[str] = []
    for keyword, cats in _CATEGORY_MAP.items():
        if keyword in q_lower:
            for c in cats:
                if c not in categories:
                    categories.append(c)
    return categories


def _extract_limit(query: str) -> int:
    match = re.search(r'\b(\d{1,3})\b', query)
    if match:
        n = int(match.group(1))
        if 1 <= n <= 200:
            return n
    return 25


# ── Data cleaning ───────────────────────────────────────────────────

# Essential fields for enriched ticker data (25 of 145)
_ENRICHED_FIELDS = {
    "ticker", "current_price", "todaysChangePerc", "current_volume",
    "prev_day_volume", "market_cap", "float_shares", "sector",
    "rsi_14", "daily_rsi", "vwap", "dist_from_vwap",
    "macd_line", "macd_signal", "macd_hist",
    "bb_upper", "bb_lower", "bb_mid",
    "sma_20", "sma_50", "sma_200",
    "daily_sma_20", "daily_sma_50", "daily_sma_200",
    "adx_14", "daily_adx_14",
    "stoch_k", "stoch_d",
    "atr_percent", "daily_atr_percent",
    "high_52w", "low_52w", "from_52w_high", "from_52w_low",
    "gap_percent", "daily_gap_percent",
    "change_1d", "change_5d", "change_20d",
    "rvol", "dollar_volume",
    "intraday_high", "intraday_low",
    "shares_outstanding",
}


def _clean_enriched(raw: dict) -> dict:
    """Strip enriched data to essential fields only.
    Input: raw MCP response (may have 'tickers' key or be flat).
    Output: {ticker: {essential_fields}} 
    """
    tickers_data = raw
    if isinstance(raw, dict) and "tickers" in raw:
        tickers_data = raw["tickers"]

    if not isinstance(tickers_data, dict):
        return raw

    cleaned = {}
    for symbol, data in tickers_data.items():
        if not isinstance(data, dict):
            continue
        row = {}
        for k in _ENRICHED_FIELDS:
            if k in data and data[k] is not None:
                row[k] = data[k]
        # Add formatted price from day data if present
        day = data.get("day", {})
        if isinstance(day, dict):
            row["day_open"] = day.get("o")
            row["day_high"] = day.get("h")
            row["day_low"] = day.get("l")
            row["day_close"] = day.get("c")
            row["day_volume"] = day.get("v")
            row["day_vwap"] = day.get("vw")
        cleaned[symbol] = row

    return cleaned


# Essential fields for scanner snapshot items
_SCANNER_FIELDS = {
    "symbol", "price", "bid", "ask",
    "change_percent", "todaysChangePerc", "change_pct",
    "current_volume", "volume", "volume_today",
    "rvol",
    "market_cap", "float_shares", "sector", "industry",
    "gap_percent", "prev_close", "open",
    "intraday_high", "intraday_low",
    "session",
}


def _clean_scanner(raw: Any, limit: int = 50) -> list[dict]:
    """Clean scanner snapshot: cap items and strip to essential fields.
    Input: raw MCP response (list or dict with data key).
    Output: list of clean dicts with ~10 fields each.
    Normalizes field names for consistent downstream consumption.
    """
    items = raw
    if isinstance(raw, dict):
        items = raw.get("data", raw.get("stocks", raw.get("tickers", [])))
    if not isinstance(items, list):
        return []

    cleaned = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        row = {}
        for k in _SCANNER_FIELDS:
            if k in item and item[k] is not None:
                row[k] = item[k]

        # Normalize change_percent to a single key
        chg = (row.pop("change_percent", None)
               or row.pop("todaysChangePerc", None)
               or row.pop("change_pct", None))
        if chg is not None:
            row["change_pct"] = round(chg, 2) if isinstance(chg, float) else chg

        # Normalize volume to a single key
        vol = (row.pop("volume_today", None)
               or row.pop("current_volume", None)
               or row.get("volume"))
        if vol is not None:
            row["volume"] = vol

        # Clean sector: map SIC descriptions to standard names
        sector = row.get("sector", "")
        if sector and len(sector) > 25:
            row["sector"] = _normalize_sector(sector)

        if row:
            cleaned.append(row)

    return cleaned


_SIC_SECTOR_MAP = {
    "semiconductor": "Technology", "software": "Technology", "computer": "Technology",
    "electronic": "Technology", "data processing": "Technology", "telecom": "Communication Services",
    "pharma": "Healthcare", "biotech": "Healthcare", "medical": "Healthcare", "surgical": "Healthcare",
    "hospital": "Healthcare", "diagnostic": "Healthcare", "drug": "Healthcare",
    "crude": "Energy", "petroleum": "Energy", "natural gas": "Energy", "oil": "Energy",
    "mining": "Basic Materials", "metal": "Basic Materials", "chemical": "Basic Materials",
    "steel": "Basic Materials",
    "bank": "Financial Services", "insurance": "Financial Services", "invest": "Financial Services",
    "real estate": "Real Estate", "reit": "Real Estate",
    "motor": "Consumer Cyclical", "auto": "Consumer Cyclical", "retail": "Consumer Cyclical",
    "apparel": "Consumer Cyclical", "restaurant": "Consumer Cyclical", "hotel": "Consumer Cyclical",
    "food": "Consumer Defensive", "beverage": "Consumer Defensive", "tobacco": "Consumer Defensive",
    "grocery": "Consumer Defensive",
    "air transport": "Industrials", "railroad": "Industrials", "aerospace": "Industrials",
    "construction": "Industrials", "electric": "Utilities", "water": "Utilities", "gas distrib": "Utilities",
    "phonograph": "Communication Services", "broadcast": "Communication Services",
    "motion picture": "Communication Services",
}


def _normalize_sector(sic_desc: str) -> str:
    """Map SIC industry descriptions to standard sector names."""
    desc_lower = sic_desc.lower()
    for keyword, sector in _SIC_SECTOR_MAP.items():
        if keyword in desc_lower:
            return sector
    return sic_desc[:30]


# ── Main node ───────────────────────────────────────────────────────

async def market_data_node(state: dict) -> dict:
    """Fetch market data via MCP scanner tools."""
    start_time = time.time()

    query = state.get("query", "")
    tickers = state.get("tickers", [])
    explicit_categories = _detect_categories(query)
    limit = _extract_limit(query)

    results: dict[str, Any] = {}
    errors: list[str] = []

    # 1. Market session context
    try:
        session = await call_mcp_tool("scanner", "get_market_session", {})
        results["market_session"] = session
    except Exception as exc:
        errors.append(f"market_session: {exc}")

    # 2. Enriched data for specific tickers — CLEANED
    if tickers:
        try:
            raw = await call_mcp_tool("scanner", "get_enriched_batch", {"symbols": tickers})
            results["enriched"] = _clean_enriched(raw)
        except Exception as exc:
            errors.append(f"enriched_batch: {exc}")

    # 3. Historical data — daily or minute bars if requested
    if tickers and _wants_historical_daily(query):
        # Fetch last 5 trading days for each ticker
        from datetime import datetime, timedelta
        today = datetime.now()
        for days_back in range(0, 10):
            dt = today - timedelta(days=days_back)
            if dt.weekday() >= 5:
                continue
            date_str = dt.strftime("%Y-%m-%d")
            try:
                raw = await call_mcp_tool("historical", "get_day_bars", {
                    "date": date_str, "symbols": tickers[:3],
                })
                if raw and not raw.get("error"):
                    results.setdefault("historical_daily", []).append({
                        "date": date_str, "data": raw
                    })
            except Exception as exc:
                errors.append(f"historical_daily/{date_str}: {exc}")
                break

    if tickers and _wants_historical_minute(query):
        try:
            raw = await call_mcp_tool("historical", "get_minute_bars", {
                "date": "yesterday", "symbols": tickers[:2],
            })
            if raw and not raw.get("error"):
                results["historical_minute"] = raw
        except Exception as exc:
            errors.append(f"historical_minute: {exc}")

    # 4. Scanner snapshot — only if explicitly requested or no tickers
    categories = explicit_categories
    if not categories and not tickers:
        categories = ["winners"]

    for category in categories:
        try:
            raw = await call_mcp_tool(
                "scanner", "get_scanner_snapshot",
                {"category": category, "limit": limit},
            )
            results[f"snapshot_{category}"] = _clean_scanner(raw, limit=limit)
        except Exception as exc:
            errors.append(f"snapshot_{category}: {exc}")

    if errors:
        results["_errors"] = errors

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "agent_results": {
            "market_data": {
                "tickers_queried": tickers,
                "categories": categories,
                "limit": limit,
                **results,
            },
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "market_data": {
                "elapsed_ms": elapsed_ms,
                "tickers": tickers,
                "categories": categories,
                "limit": limit,
                "error_count": len(errors),
            },
        },
    }
