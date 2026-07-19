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
import asyncio
import re
import time
from typing import Any

from agents.mcp_catalog import MCP


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


# ── Pattern forecast / deep technicals detection ─────────────────
_PATTERN_KW = [
    "patrón", "patron", "pattern", "similar", "forecast", "pronóstico",
    "pronostico", "probabilidad", "probability", "prediccion", "predicción",
    "se parece", "parecido", "históricamente similar", "next 15", "próximos minutos",
]

_TECHNICALS_KW = [
    "rsi", "macd", "bollinger", "adx", "estocástico", "stochastic", "sma",
    "ema", "vwap", "atr", "técnico", "tecnico", "technical", "indicadores",
    "indicators", "sobrecompra", "sobreventa", "overbought", "oversold",
]


def _wants_pattern_forecast(q: str) -> bool:
    return any(kw in q.lower() for kw in _PATTERN_KW)


def _wants_deep_technicals(q: str) -> bool:
    return any(kw in q.lower() for kw in _TECHNICALS_KW)


async def _fetch_pattern_forecasts(tickers: list[str]) -> dict[str, Any]:
    """FAISS pattern-similarity forecast (next 15 min) for up to 2 tickers."""
    async def _one(t: str):
        try:
            raw = await MCP.patterns.find_similar_patterns({"symbol": t, "top_k": 50})
            if isinstance(raw, dict) and not raw.get("error"):
                forecast = raw.get("forecast", {})
                # Keep the statistical summary; drop bulky trajectories/neighbors
                return t, {
                    "prob_up": forecast.get("prob_up"),
                    "prob_down": forecast.get("prob_down"),
                    "mean_return_pct": forecast.get("mean_return"),
                    "median_return_pct": forecast.get("median_return"),
                    "best_case_pct": forecast.get("best_case"),
                    "worst_case_pct": forecast.get("worst_case"),
                    "confidence": forecast.get("confidence"),
                    "horizon_minutes": forecast.get("horizon_minutes"),
                    "n_similar_patterns": forecast.get("n_neighbors"),
                }
        except Exception:
            pass
        return t, None

    out = await asyncio.gather(*[_one(t) for t in tickers[:2]])
    return {t: f for t, f in out if f}


async def _fetch_technical_snapshots(tickers: list[str]) -> dict[str, Any]:
    """Full indicator set (RSI, MACD, BB, ADX, stoch, SMAs...) per ticker."""
    async def _one(t: str):
        try:
            raw = await MCP.analytics.get_technical_snapshot({"symbol": t})
            if isinstance(raw, dict) and not raw.get("error"):
                return t, raw
        except Exception:
            pass
        return t, None

    out = await asyncio.gather(*[_one(t) for t in tickers[:3]])
    return {t: s for t, s in out if s}


# ── Category mapping ─────────────────────────────────────────────
_CATEGORY_MAP: dict[str, list[str]] = {
    "winners": ["winners"], "gainers": ["winners"], "ganadoras": ["winners"],
    "mejores": ["winners"], "best": ["winners"],
    "top gainers": ["winners"], "top ganadoras": ["winners"],
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
    """Detect which scanner categories the user is asking about.

    Matches longest keywords first to prevent partial false-positives
    (e.g., "top gainers" should match as a unit, not just "gainers").
    """
    q_lower = query.lower()
    categories: list[str] = []
    # Sort by keyword length descending so longer/more specific matches win first
    sorted_keywords = sorted(_CATEGORY_MAP.keys(), key=len, reverse=True)
    for keyword in sorted_keywords:
        if keyword in q_lower:
            for c in _CATEGORY_MAP[keyword]:
                if c not in categories:
                    categories.append(c)
    return categories


_SESSION_MOVERS_MIN_VOLUME = 100_000
_SESSION_MOVERS_MIN_CHANGE = 0.5  # percent, either direction

# ── Numeric constraints extracted from the query ─────────────────
# "market cap above 300m", "price under $5", "volumen mayor a 1M"...
# These MUST be applied inside the universe screen: filtering the
# truncated top-N afterwards silently drops qualifying tickers.

_AMOUNT_SUFFIX = {
    "k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12,
    "thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12,
}
_GT_WORDS = r"(?:above|over|greater\s+than|more\s+than|at\s+least|mayor(?:es)?\s+(?:a|de|que)|m[aá]s\s+de|encima\s+de|superior(?:es)?\s+a|>=?)"
_LT_WORDS = r"(?:below|under|less\s+than|at\s+most|menor(?:es)?\s+(?:a|de|que)|menos\s+de|debajo\s+de|inferior(?:es)?\s+a|<=?)"
_AMOUNT_RE = r"\$?\s*([\d][\d.,]*)\s*(k|m|b|t|thousand|million|billion|trillion)?\b"

_CONSTRAINT_FIELDS = [
    (r"(?:market\s*cap|mcap|capitalizaci[oó]n(?:\s+de\s+mercado)?)", "market_cap"),
    (r"(?:price|precio)", "current_price"),
    (r"(?:volume|volumen)", "current_volume"),
    (r"(?:float)", "float_shares"),
]


def _extract_query_filters(query: str) -> list[dict[str, Any]]:
    """Parse numeric constraints from the query into dynamic-filter dicts."""
    ql = query.lower()
    filters: list[dict[str, Any]] = []
    for field_words, field in _CONSTRAINT_FIELDS:
        for op_words, op in ((_GT_WORDS, "gte"), (_LT_WORDS, "lte")):
            m = re.search(field_words + r"\s*(?:of\s+)?" + op_words + r"\s*" + _AMOUNT_RE, ql)
            if not m:
                continue
            try:
                value = float(m.group(1).rstrip(".,").replace(",", ""))
            except ValueError:
                continue
            if m.group(2):
                value *= _AMOUNT_SUFFIX[m.group(2)]
            filters.append({"field": field, "op": op, "value": value})
    return filters


async def _run_universe_screen(screen: dict) -> tuple[dict[str, Any], list[str]]:
    """Execute a planner-emitted screen spec against the full enriched universe.

    The planner translates arbitrary trader queries ("mcap > 500M sorted by
    RVOL at the close") into {filters, sort_by, sort_order, limit, snapshot};
    this just forwards it to apply_dynamic_filter and normalizes the output.
    """
    args: dict[str, Any] = {
        "filters": screen.get("filters") or [],
        "sort_by": screen.get("sort_by") or "volume",
        "sort_order": screen.get("sort_order") or "desc",
        "limit": min(int(screen.get("limit") or 25), 100),
    }
    if screen.get("snapshot") in ("live", "close"):
        args["snapshot"] = screen["snapshot"]

    try:
        raw = await MCP.scanner.apply_dynamic_filter(args)
    except Exception as exc:
        return {}, [f"universe_screen: {exc}"]

    if not isinstance(raw, dict) or raw.get("error"):
        err = raw.get("error") if isinstance(raw, dict) else "invalid response"
        return {}, [f"universe_screen: {err}"]

    return {
        "universe_screen": {
            "spec": args,
            "matched_total": raw.get("count", 0),
            "universe_size": raw.get("total_scanned", 0),
            "tickers": raw.get("tickers", []),
        },
    }, []


async def _fetch_session_movers(query: str, limit: int) -> tuple[dict[str, Any], list[str]]:
    """Rank after-hours / premarket movers by screening the FULL enriched
    universe (~11K tickers) with apply_dynamic_filter.

    The scanner's post_market category is not emitted by the RETE system
    rules (always empty), and categories only cover a top-N subset anyway —
    the dynamic filter is the authoritative path for session-based rankings.
    """
    ql = query.lower()
    if any(k in ql for k in ("after hours", "after-hours", "afterhours", "post market", "post-market", "postmarket")):
        field, prefix = "postmarket_change_percent", "afterhours"
    elif any(k in ql for k in ("premarket", "pre market", "pre-market")):
        field, prefix = "premarket_change_percent", "premarket"
    else:
        return {}, []

    # User constraints (market cap, price, volume, float) go INSIDE the
    # screen; a default liquidity floor applies only if the user didn't
    # constrain volume themselves.
    extra_filters = _extract_query_filters(query)
    if not any(f["field"] == "current_volume" for f in extra_filters):
        extra_filters.append({"field": "current_volume", "op": "gt", "value": _SESSION_MOVERS_MIN_VOLUME})

    async def _screen(op: str, value: float, order: str) -> list[dict]:
        raw = await MCP.scanner.apply_dynamic_filter({
            "filters": [{"field": field, "op": op, "value": value}, *extra_filters],
            "sort_by": field,
            "sort_order": order,
            "limit": limit,
        })
        return raw.get("tickers", []) if isinstance(raw, dict) else []

    out: dict[str, Any] = {}
    errors: list[str] = []
    try:
        gainers, losers = await asyncio.gather(
            _screen("gte", _SESSION_MOVERS_MIN_CHANGE, "desc"),
            _screen("lte", -_SESSION_MOVERS_MIN_CHANGE, "asc"),
        )
        if gainers:
            out[f"{prefix}_gainers"] = gainers
        if losers:
            out[f"{prefix}_losers"] = losers
    except Exception as exc:
        errors.append(f"session_movers: {exc}")
    return out, errors


def _extract_limit(query: str) -> int:
    """Extract a result-count limit from the query.
    Only matches patterns like 'top 20', 'show 50', 'dame 10', 'primeros 30'.
    Ignores numbers that are prices, RSI values, etc.
    """
    patterns = [
        r'\btop\s+(\d{1,3})\b',
        r'\bshow\s+(\d{1,3})\b',
        r'\bdame\s+(\d{1,3})\b',
        r'\bmuestra\s+(\d{1,3})\b',
        r'\bprimeros?\s+(\d{1,3})\b',
        r'\bfirst\s+(\d{1,3})\b',
        r'\blast\s+(\d{1,3})\b',
        r'\b(\d{1,3})\s+(?:stocks?|acciones|tickers?|results?|resultados)\b',
    ]
    ql = query.lower()
    for pattern in patterns:
        match = re.search(pattern, ql)
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
    "premarket_change_percent", "premarket_volume",
    "premarket_high", "premarket_low",
    "postmarket_change_percent", "postmarket_volume",
    "postmarket_change_dollars", "postmarket_high", "postmarket_low",
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

        # Normalize change_percent to a single key (avoid `or` — 0.0 is valid)
        chg = row.pop("change_percent", None)
        if chg is None:
            chg = row.pop("todaysChangePerc", None)
        if chg is None:
            chg = row.pop("change_pct", None)
        if chg is not None:
            row["change_pct"] = round(chg, 2) if isinstance(chg, float) else chg

        # Normalize volume to a single key (avoid `or` — 0 is valid)
        vol = row.pop("volume_today", None)
        if vol is None:
            vol = row.pop("current_volume", None)
        if vol is None:
            vol = row.get("volume")
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

    # ── CHART_ANALYSIS fast-path: use snapshot data directly ──
    chart_context = state.get("chart_context")
    if chart_context:
        snap = chart_context.get("snapshot", {})
        bars = snap.get("recentBars", [])
        is_hist = snap.get("isHistorical", False)
        visible_range = snap.get("visibleDateRange", {})

        period_high = max((b["high"] for b in bars), default=0) if bars else 0
        period_low = min((b["low"] for b in bars), default=0) if bars else 0
        open_first = bars[0]["open"] if bars else 0
        close_last = bars[-1]["close"] if bars else 0
        volumes = [b.get("volume", 0) for b in bars]
        vol_avg = round(sum(volumes) / max(len(volumes), 1)) if volumes else 0

        # Trend analysis: count higher-highs/higher-lows vs lower-highs/lower-lows
        hh_count, hl_count, lh_count, ll_count = 0, 0, 0, 0
        for i in range(1, len(bars)):
            if bars[i]["high"] > bars[i-1]["high"]: hh_count += 1
            else: lh_count += 1
            if bars[i]["low"] > bars[i-1]["low"]: hl_count += 1
            else: ll_count += 1
        total_swings = max(hh_count + lh_count, 1)
        trend_score = round((hh_count + hl_count - lh_count - ll_count) / total_swings, 2)

        # Volume analysis
        vol_max_idx = volumes.index(max(volumes)) if volumes else 0
        vol_min_idx = volumes.index(min(volumes)) if volumes else 0
        vol_last5 = volumes[-5:] if len(volumes) >= 5 else volumes
        vol_first5 = volumes[:5] if len(volumes) >= 5 else volumes
        vol_expanding = round(sum(vol_last5) / max(len(vol_last5), 1)) > vol_avg if vol_last5 else False

        # Volatility: average true range over last 14 bars
        atr_vals = []
        for i in range(1, min(15, len(bars))):
            tr = max(
                bars[i]["high"] - bars[i]["low"],
                abs(bars[i]["high"] - bars[i-1]["close"]),
                abs(bars[i]["low"] - bars[i-1]["close"]),
            )
            atr_vals.append(tr)
        computed_atr = round(sum(atr_vals) / max(len(atr_vals), 1), 4) if atr_vals else 0

        # Key candles: largest body, largest volume, dojis
        key_candles = []
        for b in bars:
            body = abs(b["close"] - b["open"])
            wick_total = (b["high"] - b["low"])
            if wick_total > 0 and body / wick_total < 0.1:
                key_candles.append({"time": b["time"], "pattern": "doji", "close": b["close"]})
        if len(key_candles) > 5:
            key_candles = key_candles[-5:]

        # Auto support/resistance from price clusters
        auto_levels = []
        if len(bars) >= 10:
            all_prices = sorted([b["high"] for b in bars] + [b["low"] for b in bars])
            step = (all_prices[-1] - all_prices[0]) / max(20, 1)
            if step > 0:
                buckets: dict[int, list[float]] = {}
                for p in all_prices:
                    k = int((p - all_prices[0]) / step)
                    buckets.setdefault(k, []).append(p)
                top_buckets = sorted(buckets.items(), key=lambda x: len(x[1]), reverse=True)[:4]
                for _, prices in top_buckets:
                    if len(prices) >= 3:
                        avg_p = round(sum(prices) / len(prices), 2)
                        label = "resistance" if avg_p > close_last else "support"
                        auto_levels.append({"price": avg_p, "type": label, "touches": len(prices)})

        results["chart_analysis"] = {
            "source": "user_chart_snapshot",
            "ticker": chart_context.get("ticker"),
            "interval": chart_context.get("interval"),
            "range": chart_context.get("range"),
            "is_historical": is_hist,
            "visible_date_range": visible_range,
            "visible_bars_count": len(bars),
            "price_action": {
                "period_high": period_high,
                "period_low": period_low,
                "open_first": open_first,
                "close_last": close_last,
                "period_change_pct": round(((close_last - open_first) / open_first) * 100, 2) if open_first else 0,
                "range_pct": round(((period_high - period_low) / period_low) * 100, 2) if period_low else 0,
            },
            "trend": {
                "score": trend_score,
                "direction": "bullish" if trend_score > 0.2 else ("bearish" if trend_score < -0.2 else "sideways"),
                "higher_highs": hh_count,
                "lower_lows": ll_count,
            },
            "volume": {
                "average": vol_avg,
                "max": max(volumes) if volumes else 0,
                "max_bar_time": bars[vol_max_idx]["time"] if bars else 0,
                "expanding": vol_expanding,
            },
            "volatility": {
                "atr14": computed_atr,
                "atr_pct": round((computed_atr / close_last) * 100, 2) if close_last else 0,
            },
            "indicators": snap.get("indicators", {}),
            "support_resistance_levels": snap.get("levels", []) + auto_levels,
            "key_candles": key_candles,
            "target_candle": chart_context.get("targetCandle"),
            "last_5_bars": bars[-5:] if len(bars) >= 5 else bars,
            "first_5_bars": bars[:5] if len(bars) >= 5 else bars,
        }

        # For historical charts, only get current price for reference (not as primary data)
        if is_hist and tickers:
            try:
                raw = await MCP.scanner.get_enriched_batch({"symbols": tickers})
                enriched = _clean_enriched(raw)
                ref = {
                    t: {"current_price": d.get("current_price"), "todaysChangePerc": d.get("todaysChangePerc")}
                    for t, d in enriched.items()
                }
                if ref:
                    results["current_reference"] = ref
                else:
                    results["current_reference"] = {"note": "Market data temporarily unavailable"}
            except Exception as exc:
                import logging as _log
                _log.getLogger(__name__).warning("current_reference fetch failed: %s", exc)
                results["current_reference"] = {"note": "Market data temporarily unavailable"}

            elapsed_ms = int((time.time() - start_time) * 1000)
            return {
                "agent_results": {
                    "market_data": {
                        "tickers_queried": tickers,
                        "categories": [],
                        "limit": 0,
                        **results,
                    },
                },
                "execution_metadata": {
                    **(state.get("execution_metadata", {})),
                    "market_data": {"elapsed_ms": elapsed_ms, "tickers": tickers, "mode": "chart_analysis_historical"},
                },
            }

        # For current-view charts, also fetch enriched to complement the snapshot
        if not is_hist and tickers:
            try:
                raw = await MCP.scanner.get_enriched_batch({"symbols": tickers})
                results["enriched"] = _clean_enriched(raw)
            except Exception as exc:
                errors.append(f"enriched_batch: {exc}")

            # FAISS pattern forecast on the live chart ticker (realtime-only signal)
            forecasts = await _fetch_pattern_forecasts(tickers)
            if forecasts:
                results["pattern_forecast"] = forecasts

        elapsed_ms = int((time.time() - start_time) * 1000)
        if errors:
            results["_errors"] = errors
        return {
            "agent_results": {
                "market_data": {
                    "tickers_queried": tickers,
                    "categories": [],
                    "limit": 0,
                    **results,
                },
            },
            "execution_metadata": {
                **(state.get("execution_metadata", {})),
                "market_data": {"elapsed_ms": elapsed_ms, "tickers": tickers, "mode": "chart_analysis_current"},
            },
        }

    # ── Standard flow (no chart context) ──

    # 0a. MARKET PULSE path — broad market queries (sectors, themes, industries)
    pulse_queries = state.get("pulse_queries")
    if pulse_queries:
        try:
            pulse_args = {"queries": pulse_queries}
            pulse_compare = state.get("pulse_compare", False)
            pulse_metrics = state.get("pulse_metrics")
            pulse_drilldown = state.get("pulse_drilldown")
            if pulse_compare:
                pulse_args["compare"] = True
            if pulse_metrics:
                pulse_args["metrics"] = pulse_metrics
            if pulse_drilldown:
                pulse_args["drilldown"] = pulse_drilldown

            pulse_data = await MCP.market_pulse.analyze_market(pulse_args)
            if pulse_data and not pulse_data.get("error"):
                results["market_pulse"] = pulse_data
        except Exception as exc:
            errors.append(f"market_pulse: {exc}")

        # If this is a pure market pulse query (no tickers), return early
        if not tickers and not _detect_categories(query):
            elapsed_ms = int((time.time() - start_time) * 1000)
            if errors:
                results["_errors"] = errors
            return {
                "agent_results": {
                    "market_data": {
                        "tickers_queried": [],
                        "categories": [],
                        "limit": limit,
                        **results,
                    },
                },
                "execution_metadata": {
                    **(state.get("execution_metadata", {})),
                    "market_data": {"elapsed_ms": elapsed_ms, "tickers": [], "mode": "market_pulse"},
                },
            }

    # 0b. THEMATIC resolution — resolve theme_tags into tickers before anything else
    theme_tags = state.get("theme_tags", [])
    if theme_tags:
        try:
            theme_data = await MCP.screener.search_by_theme({
                "themes": theme_tags,
                "limit": limit,
                "min_relevance": 0.5,
                "operating_only": True,
                "sort_by": "relevance",
            })
            if theme_data and not theme_data.get("error"):
                theme_results = theme_data.get("results", [])
                results["thematic_resolution"] = theme_data
                resolved_tickers = [r["symbol"] for r in theme_results]
                if resolved_tickers:
                    tickers = resolved_tickers
        except Exception as exc:
            errors.append(f"thematic_resolution: {exc}")

    # 1. Market session context — reuse from supervisor if available
    mc = state.get("market_context", {})
    if mc and mc.get("current_session"):
        results["market_session"] = mc
    else:
        try:
            session = await MCP.scanner.get_market_session({})
            results["market_session"] = session
        except Exception as exc:
            errors.append(f"market_session: {exc}")

    # 2. Enriched data for specific tickers — CLEANED
    if tickers:
        try:
            raw = await MCP.scanner.get_enriched_batch({"symbols": tickers})
            results["enriched"] = _clean_enriched(raw)
        except Exception as exc:
            errors.append(f"enriched_batch: {exc}")

    # 2b. FAISS pattern forecast — statistical outlook from similar history
    if tickers and _wants_pattern_forecast(query):
        forecasts = await _fetch_pattern_forecasts(tickers)
        if forecasts:
            results["pattern_forecast"] = forecasts

    # 2c. Deep technical snapshot — full indicator set beyond enriched fields
    if tickers and _wants_deep_technicals(query):
        snapshots = await _fetch_technical_snapshots(tickers)
        if snapshots:
            results["technical_snapshot"] = snapshots

    # 3. Historical data — daily or minute bars (parallelized)
    if tickers and _wants_historical_daily(query):
        from datetime import datetime, timedelta
        today = datetime.now()
        trading_dates = []
        for days_back in range(0, 10):
            dt = today - timedelta(days=days_back)
            if dt.weekday() < 5:
                trading_dates.append(dt.strftime("%Y-%m-%d"))
            if len(trading_dates) >= 5:
                break

        async def _fetch_day_bars(date_str: str):
            try:
                raw = await MCP.historical.get_day_bars({
                    "date": date_str, "symbols": tickers[:3],
                })
                if raw and not raw.get("error"):
                    return {"date": date_str, "data": raw}
            except Exception as exc:
                errors.append(f"historical_daily/{date_str}: {exc}")
            return None

        day_results = await asyncio.gather(*[_fetch_day_bars(d) for d in trading_dates])
        hist_daily = [r for r in day_results if r is not None]
        if hist_daily:
            results["historical_daily"] = hist_daily

    if tickers and _wants_historical_minute(query):
        try:
            raw = await MCP.historical.get_minute_bars({
                "date": "yesterday", "symbols": tickers[:2],
            })
            if raw and not raw.get("error"):
                results["historical_minute"] = raw
        except Exception as exc:
            errors.append(f"historical_minute: {exc}")

    # 4. Scanner snapshot — parallelized
    categories = explicit_categories
    if not categories and not tickers:
        categories = ["winners"]

    # 4a. Planner-emitted universe screen — the authoritative path for
    # rankings with constraints or custom sort. Runs on the full ~12K
    # universe; categories are skipped since the screen IS the ranking.
    screen = state.get("screen")
    if isinstance(screen, dict) and screen.get("filters") is not None:
        screen_results, screen_errors = await _run_universe_screen(screen)
        errors.extend(screen_errors)
        if screen_results:
            results.update(screen_results)
            categories = []

    # 4b. After-hours / premarket movers — keyword fallback when the planner
    # didn't emit a screen. Replaces the dead post_market category.
    if "universe_screen" not in results:
        session_movers, session_errors = await _fetch_session_movers(query, limit)
        if session_movers:
            results.update(session_movers)
            categories = [c for c in categories if c != "post_market"]
        errors.extend(session_errors)

    # Minimum-threshold constraints also apply to category snapshots
    # (get_scanner_snapshot only supports min_* filters).
    snapshot_args: dict[str, Any] = {}
    _MIN_ARG_BY_FIELD = {
        "current_price": "min_price",
        "current_volume": "min_volume",
        "market_cap": "min_market_cap",
    }
    for f in _extract_query_filters(query):
        arg = _MIN_ARG_BY_FIELD.get(f["field"])
        if arg and f["op"] == "gte":
            snapshot_args[arg] = f["value"]

    async def _fetch_snapshot(cat: str):
        try:
            raw = await MCP.scanner.get_scanner_snapshot(
                {"category": cat, "limit": limit, **snapshot_args},
            )
            return (cat, _clean_scanner(raw, limit=limit), None)
        except Exception as exc:
            return (cat, None, f"snapshot_{cat}: {exc}")

    snapshot_results = await asyncio.gather(*[_fetch_snapshot(c) for c in categories])
    for cat, data, err in snapshot_results:
        if err:
            errors.append(err)
        elif data is not None:
            results[f"snapshot_{cat}"] = data

    # 5. GICS enrichment — replace SIC codes with clean GICS classification
    all_symbols = set(tickers or [])
    for key, val in results.items():
        if key.startswith("snapshot_") and isinstance(val, list):
            for item in val:
                if isinstance(item, dict) and "symbol" in item:
                    all_symbols.add(item["symbol"])
    screen_rows = results.get("universe_screen", {}).get("tickers", [])
    for item in screen_rows:
        if isinstance(item, dict) and "symbol" in item:
            all_symbols.add(item["symbol"])
    if isinstance(results.get("enriched"), dict):
        all_symbols.update(results["enriched"].keys())

    if all_symbols:
        try:
            gics = await MCP.screener.enrich_with_classification(
                {"symbols": list(all_symbols)},
            )
            if isinstance(gics, dict) and gics:
                for key, val in results.items():
                    if key.startswith("snapshot_") and isinstance(val, list):
                        for item in val:
                            sym = item.get("symbol", "")
                            if sym in gics:
                                item["sector"] = gics[sym]["sector"]
                                item["industry"] = gics[sym]["industry"]
                                item["company_name"] = gics[sym].get("company_name", "")
                for item in screen_rows:
                    sym = item.get("symbol", "") if isinstance(item, dict) else ""
                    if sym in gics:
                        item["sector"] = gics[sym]["sector"]
                        item["industry"] = gics[sym]["industry"]
                        item["company_name"] = gics[sym].get("company_name", "")
                if isinstance(results.get("enriched"), dict):
                    for sym, data in results["enriched"].items():
                        if sym in gics:
                            data["sector"] = gics[sym]["sector"]
                            data["industry"] = gics[sym]["industry"]
                            data["company_name"] = gics[sym].get("company_name", "")
        except Exception as exc:
            errors.append(f"gics_enrichment: {exc}")

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
