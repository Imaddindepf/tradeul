"""
Context Enricher — Auto-inject sector/industry/theme context for mentioned tickers.

Runs after all agents complete and before the Synthesizer.
Adds market_pulse_context to agent_results so the Synthesizer can reference
the broader market picture without the user explicitly asking.

Lightweight: only fires when tickers are present, skips for GREETING/RANKING-only.

También cotiza los símbolos DESCUBIERTOS por los agentes. El planner sólo
extrae tickers que el usuario nombra, así que una pregunta como "los earnings
de ayer y cómo se han movido" llega con tickers=[]: los símbolos aparecen
después, dentro del resultado de earnings, cuando el agente de mercado ya ha
terminado. Este nodo corre tras el fan-out, que es el único punto donde ya se
conocen y todavía se puede pedir su precio.
"""
import asyncio
import logging
import time
from typing import Any

from agents.mcp_catalog import MCP

logger = logging.getLogger(__name__)


async def context_enricher_node(state: dict) -> dict:
    """Enrich agent results with sector/industry/theme context for mentioned tickers."""
    start = time.time()

    tickers = state.get("tickers", [])
    agent_results = state.get("agent_results", {})
    plan = state.get("plan", "")

    # Skip for greetings or when there's no substance to enrich
    if not agent_results or plan == "clarification_needed":
        return state

    # Collect market regime (always useful)
    regime_task = _fetch_regime()

    # If we have tickers, get their sector/theme positioning
    positioning_task = _fetch_ticker_positioning(tickers) if tickers else _noop()

    # Símbolos que ningún agente pudo cotizar porque no se conocían al planificar
    discovered = _discovered_symbols(agent_results, exclude=tickers)
    quotes_task = _fetch_quotes(discovered) if discovered else _noop()

    regime, positioning, quotes = await asyncio.gather(
        regime_task, positioning_task, quotes_task, return_exceptions=True
    )

    context: dict[str, Any] = {}

    if isinstance(regime, dict) and "error" not in regime:
        context["market_regime"] = regime

    if isinstance(positioning, dict) and positioning:
        context["ticker_positioning"] = positioning

    if isinstance(quotes, dict) and quotes:
        context["discovered_quotes"] = quotes

    if not context:
        return state

    elapsed = int((time.time() - start) * 1000)
    logger.info("Context enricher: added %s keys in %dms", list(context.keys()), elapsed)

    return {
        "agent_results": {"_market_pulse_context": context},
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "context_enricher": {"elapsed_ms": elapsed, "keys": list(context.keys())},
        },
    }


async def _noop():
    return {}


# Tope de cotizaciones por turno: cubre de sobra una jornada de resultados
# sin convertir el enriquecido en una segunda pasada cara.
_QUOTE_CAP = 60

# Lo justo para responder "cuánto se ha movido": precio, referencias de
# sesión y los cambios ya calculados aguas arriba.
_QUOTE_FIELDS = (
    "current_price", "todaysChangePerc", "change_from_open",
    "day_open", "day_close", "premarket_change_percent",
    "postmarket_change_percent", "postmarket_volume",
    "premarket_volume", "current_volume", "rvol", "market_cap",
)


def _discovered_symbols(agent_results: dict, exclude: list[str]) -> list[str]:
    """Símbolos que aparecen en los resultados y que nadie ha cotizado.

    Recorre las filas devueltas por los agentes en busca de 'symbol'. No
    inventa nada: si un agente no devolvió símbolos, no hay nada que pedir.
    """
    seen: list[str] = []
    known = {t.upper() for t in (exclude or [])}

    def walk(node: Any, depth: int = 0) -> None:
        if depth > 6 or len(seen) >= _QUOTE_CAP:
            return
        if isinstance(node, dict):
            sym = node.get("symbol") or node.get("ticker")
            if isinstance(sym, str) and sym.isascii() and 1 <= len(sym) <= 6:
                up = sym.upper()
                if up not in known and up not in seen:
                    seen.append(up)
            for v in node.values():
                walk(v, depth + 1)
        elif isinstance(node, list):
            for v in node:
                walk(v, depth + 1)

    for key, value in (agent_results or {}).items():
        if key.startswith("_"):
            continue
        walk(value)
    return seen[:_QUOTE_CAP]


async def _fetch_quotes(symbols: list[str]) -> dict:
    """Cotización actual de una lista de símbolos, recortada a lo esencial."""
    try:
        raw = await MCP.scanner.get_enriched_batch({"symbols": symbols})
    except Exception as e:
        logger.warning("Discovered quotes failed: %s", e)
        return {}

    data = raw.get("tickers") if isinstance(raw, dict) and "tickers" in raw else raw
    if not isinstance(data, dict):
        return {}

    out: dict[str, dict] = {}
    for sym, row in data.items():
        if not isinstance(row, dict):
            continue
        keep = {k: row[k] for k in _QUOTE_FIELDS if row.get(k) is not None}
        day = row.get("day")
        if isinstance(day, dict):
            if day.get("o") is not None:
                keep.setdefault("day_open", day["o"])
            if day.get("c") is not None:
                keep.setdefault("day_close", day["c"])
        if keep:
            out[sym] = keep
    return out


async def _fetch_regime() -> dict:
    """Fetch market regime from market_pulse MCP tool."""
    try:
        return await MCP.market_pulse.get_market_regime({})
    except Exception as e:
        logger.warning("Regime fetch failed: %s", e)
        return {"error": str(e)}


async def _fetch_ticker_positioning(tickers: list[str]) -> dict:
    """For each ticker, determine its sector/industry/theme positioning.

    Returns a dict per ticker with:
      - sector + sector performance summary
      - top themes the ticker belongs to + their performance
    """
    if not tickers or len(tickers) > 5:
        return {}

    try:
        classification = await MCP.screener.enrich_with_classification({"symbols": tickers})
    except Exception:
        return {}

    if not isinstance(classification, dict) or not classification:
        return {}

    unique_sectors = set()
    for sym, info in classification.items():
        if isinstance(info, dict) and info.get("sector"):
            unique_sectors.add(info["sector"])

    if not unique_sectors:
        return {}

    # Fetch sector performance for the relevant sectors
    try:
        sector_perf = await MCP.market_pulse.analyze_market({
            "queries": [{"group": "sectors", "limit": 15}],
            "metrics": ["weighted_change", "breadth", "avg_rvol", "avg_change_5d"],
        })
    except Exception:
        sector_perf = {}

    sector_data = {}
    for result in (sector_perf.get("results") or []):
        for entry in result.get("data", []):
            if entry.get("name") in unique_sectors:
                sector_data[entry["name"]] = entry

    positioning = {}
    for sym in tickers:
        cls = classification.get(sym, {})
        if not isinstance(cls, dict):
            continue
        sector = cls.get("sector", "")
        sp = sector_data.get(sector, {})
        positioning[sym] = {
            "sector": sector,
            "industry": cls.get("industry", ""),
            "sector_performance": {
                "weighted_change": sp.get("weighted_change"),
                "breadth": sp.get("breadth"),
                "avg_rvol": sp.get("avg_rvol"),
            } if sp else None,
        }

    return positioning
