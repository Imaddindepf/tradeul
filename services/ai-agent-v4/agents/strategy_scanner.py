"""
Strategy Scanner Agent — "Did my setup happen in the market?"

Translates a natural-language intraday setup description into a declarative
event-sequence spec and runs it against the real-time alert-engine event
store (TimescaleDB, 240+ event types, ~12M events/day) via the MCP
strategy.scan_day_setups tool.

Answers queries like:
  "acciones con mcap > 1B que cruzaron el VWAP al alza tras una larga caída
   en el opening y cerraron por encima de la apertura"

Pipeline:
  1. Fetch the LIVE event-type catalog for the target date (cached 10 min)
  2. LLM (fast tier) → spec JSON {steps, day_conditions, filters, date}
  3. MCP strategy.scan_day_setups → matches with per-step evidence
  4. Clean + return results for the synthesizer
"""
from __future__ import annotations
import json
import logging
import time
from typing import Any

from langchain_core.callbacks import adispatch_custom_event
from langchain_core.messages import SystemMessage, HumanMessage

from agents.mcp_catalog import MCP
from agents._canvas import canvas_step
from agents._llm_retry import llm_invoke_with_retry

logger = logging.getLogger(__name__)

_NODE = "strategy_scanner"

_llm = None

# Live event catalog cache: {date_str: (fetched_at, catalog_text)}
_catalog_cache: dict[str, tuple[float, str]] = {}
_CATALOG_TTL = 600


async def _progress(message: str) -> None:
    try:
        await adispatch_custom_event("strategy_scan_progress", {"message": message})
    except Exception:
        pass


def _get_llm():
    global _llm
    if _llm is None:
        from agents._make_llm import make_llm
        _llm = make_llm(tier="fast", temperature=0.0, max_tokens=1536)
    return _llm


# Curated event types most useful for setups — shown first in the prompt.
# The live catalog appended below covers the rest.
_CORE_EVENTS = """\
vwap_cross_up / vwap_cross_down     - price crosses VWAP up/down
crossed_above_open / crossed_below_open - price crosses today's open
crossed_above_prev_close / crossed_below_prev_close
new_high / new_low                  - intraday high/low
intraday_high_5m / intraday_low_5m  - 5-min window high/low (also _10m/_15m/_30m)
running_up / running_down           - rapid directional move
running_up_sustained / running_down_sustained
orb_breakout_up / orb_breakout_down - opening range breakout
gap_up_reversal / gap_down_reversal - gap fading / recovering through open
pullback_25_from_high / pullback_75_from_high - retrace from intraday high
pullback_25_from_low / pullback_75_from_low   - bounce from intraday low
volume_surge / volume_spike_1min / rvol_spike
halt / resume                       - trading halts
consol_breakout_5m / consol_breakdown_5m (also _10m)
channel_breakout / channel_breakdown
double_top / double_bottom
doji_5m, hammer patterns via candle events
sma5_above_sma8_1m / sma5_below_sma8_1m (also _2m)
macd_above_signal_5m / macd_below_signal_5m
stoch_cross_bullish_5m / stoch_cross_bearish_5m
bb_upper_breakout / bb_lower_breakdown
trailing_stop_pct_up / trailing_stop_pct_down
linreg_up_5m / linreg_down_5m
sma_thrust_up_2m / sma_thrust_down_2m
cont_123_buy_2m / cont_123_sell_2m  - 1-2-3 continuation patterns
"""

SPEC_PROMPT = """\
You are the strategy-scan spec compiler for Tradeul.

Convert the user's intraday setup description into a JSON spec for the
event-sequence scanner. The scanner searches ALL stocks whose event stream
matches the setup on a given day (real-time for today, 60-day history).

OUTPUT: ONLY a JSON object (no markdown) with these keys:
{
  "steps": [            // ordered event sequence, 1-3 steps
    {
      "event_types": ["vwap_cross_up"],   // from EVENT TYPES below
      "after": "session_open" | "opening_low" | "prev_step",
      "within_minutes": null | int        // optional max delay after anchor
    }
  ],
  "day_conditions": [   // day-level price conditions (may be empty)
    {"metric": "...", "op": "gt|gte|lt|lte", "value": number}
  ],
  "date": "today" | "yesterday" | "YYYY-MM-DD",
  "session": "regular" | "premarket" | "afterhours" | "all",
  "opening_minutes": 60,        // what counts as "the opening"
  "min_market_cap": null | number,
  "max_market_cap": null | number,
  "min_price": null | number,
  "max_price": null | number,
  "sort_by": "close_vs_open_pct",
  "limit": 30
}

DAY METRICS (for day_conditions and sort_by):
  close_vs_open_pct   - close vs open % (positive = closed above open)
  opening_drop_pct    - low of the opening window vs open % (negative = declined)
  low_vs_open_pct     - session low vs open %
  high_vs_open_pct    - session high vs open %
  open_price, close_price, low_price, high_price, market_cap

ANCHORS:
  "session_open"  - event any time after the session starts
  "opening_low"   - event must happen AFTER the lowest price of the opening window
  "prev_step"     - event must happen after the previous step's event

RULES:
1. "caída en el opening" / "opening decline" → day_condition opening_drop_pct lte -2
   (use -3 for "larga caída"/"strong decline", -5 for "huge/brutal").
2. "cruzó el VWAP al alza tras la caída" → step vwap_cross_up with after="opening_low".
3. "cerró por encima de la apertura" / "closed above open" → close_vs_open_pct gt 0.
4. Market cap: "1B" = 1000000000, "500M" = 500000000.
5. Numbers in user query stay numbers (no strings).
6. If user says "hoy"/"today" or gives no date → "today". "ayer"/"yesterday" → "yesterday".
7. Session defaults to "regular" unless user mentions premarket/afterhours.
8. Pick the FEWEST steps that capture the setup — day_conditions are cheaper
   than steps. Only use multiple steps for genuine sequences (A then B).

EVENT TYPES (core setup vocabulary):
""" + _CORE_EVENTS + """
{live_catalog}

EXAMPLES:

User: "acciones con market cap minimo 1B que cruzaron el vwap al alza tras una larga caida en el opening y cerraron por encima del opening"
{"steps": [{"event_types": ["vwap_cross_up"], "after": "opening_low", "within_minutes": null}], "day_conditions": [{"metric": "opening_drop_pct", "op": "lte", "value": -3}, {"metric": "close_vs_open_pct", "op": "gt", "value": 0}], "date": "today", "session": "regular", "opening_minutes": 60, "min_market_cap": 1000000000, "max_market_cap": null, "min_price": null, "max_price": null, "sort_by": "close_vs_open_pct", "limit": 30}

User: "stocks that got halted and then broke out of the opening range yesterday"
{"steps": [{"event_types": ["halt"], "after": "session_open", "within_minutes": null}, {"event_types": ["orb_breakout_up"], "after": "prev_step", "within_minutes": null}], "day_conditions": [], "date": "yesterday", "session": "regular", "opening_minutes": 30, "min_market_cap": null, "max_market_cap": null, "min_price": null, "max_price": null, "sort_by": "close_vs_open_pct", "limit": 30}

User: "small caps bajo 10 dolares con volume surge en la primera media hora que acabaron cerrando en verde vs open el 2026-07-10"
{"steps": [{"event_types": ["volume_surge", "volume_spike_1min", "rvol_spike"], "after": "session_open", "within_minutes": 30}], "day_conditions": [{"metric": "close_vs_open_pct", "op": "gt", "value": 0}], "date": "2026-07-10", "session": "regular", "opening_minutes": 30, "min_market_cap": null, "max_market_cap": 2000000000, "min_price": null, "max_price": 10, "sort_by": "close_vs_open_pct", "limit": 30}
"""


async def _get_live_catalog(date: str) -> str:
    """Fetch (cached) the live event catalog to ground the LLM's vocabulary."""
    now = time.time()
    cached = _catalog_cache.get(date)
    if cached and now - cached[0] < _CATALOG_TTL:
        return cached[1]
    try:
        raw = await MCP.strategy.get_event_catalog({"date": date, "min_count": 500})
        types = raw.get("event_types", [])
        lines = [f"{t['event_type']} ({t['symbols']} symbols)" for t in types[:120]]
        text = "LIVE EVENT TYPES firing on " + raw.get("date", date) + ":\n" + ", ".join(lines)
    except Exception as exc:
        logger.warning("strategy_scanner: live catalog unavailable: %s", exc)
        text = ""
    _catalog_cache[date] = (now, text)
    return text


def _clean_matches(raw: dict) -> dict:
    """Trim scan output for the synthesizer: keep evidence, drop noise."""
    matches = []
    for m in raw.get("matches", []):
        row = {
            "symbol": m.get("symbol"),
            "open": m.get("o_price"),
            "close": m.get("c_price"),
            "close_vs_open_pct": m.get("close_vs_open_pct"),
            "opening_low": m.get("olow_price"),
            "opening_low_time": m.get("olow_ts"),
            "opening_drop_pct": m.get("opening_drop_pct"),
            "market_cap": m.get("mcap"),
            "sector": m.get("sector"),
        }
        # Per-step evidence (s0_ts, s0_event, s1_ts...)
        for i in range(5):
            ts = m.get(f"s{i}_ts")
            if ts is None:
                break
            row[f"step{i+1}_event"] = m.get(f"s{i}_event")
            row[f"step{i+1}_time"] = ts
            row[f"step{i+1}_price"] = m.get(f"s{i}_price")
        matches.append(row)
    return {
        "date": raw.get("date"),
        "session": raw.get("session"),
        "count": raw.get("count", len(matches)),
        "matches": matches,
        "note": raw.get("note"),
    }


async def strategy_scanner_node(state: dict) -> dict:
    """Compile NL setup → spec, run the event-sequence scan, return evidence."""
    start_time = time.time()
    query = state.get("agent_task") or state.get("query", "")

    results: dict[str, Any] = {}
    errors: list[str] = []

    await _progress("Compiling your setup into an event-sequence spec...")

    # ── Step 1: live catalog + LLM spec compilation ──
    await canvas_step(
        _NODE, "compile", "Compilar setup", "running",
        subtitle="lenguaje natural → spec de secuencia",
    )
    t_comp = time.time()
    live_catalog = await _get_live_catalog("today")
    messages = [
        SystemMessage(content=SPEC_PROMPT.replace("{live_catalog}", live_catalog)),
        HumanMessage(content=query),
    ]

    llm = _get_llm()
    response = await llm_invoke_with_retry(llm, messages)
    raw_spec = response.content.strip()
    if raw_spec.startswith("```"):
        raw_spec = raw_spec.split("```")[1]
        if raw_spec.lower().startswith("json"):
            raw_spec = raw_spec[4:]
        raw_spec = raw_spec.strip()

    try:
        spec = json.loads(raw_spec)
        if not isinstance(spec, dict) or not spec.get("steps"):
            raise ValueError("spec must be an object with non-empty steps")
    except (json.JSONDecodeError, ValueError) as exc:
        await canvas_step(
            _NODE, "compile", "Compilar setup", "error",
            subtitle="spec inválida",
            duration_ms=int((time.time() - t_comp) * 1000),
            blocks=[{"kind": "text", "text": str(exc)[:220]}],
        )
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "agent_results": {
                "strategy_scanner": {
                    "error": f"No pude compilar el setup a una spec: {exc}",
                    "raw_output": raw_spec[:500],
                },
            },
            "execution_metadata": {
                **(state.get("execution_metadata", {})),
                "strategy_scanner": {"elapsed_ms": elapsed_ms, "error": "spec_parse"},
            },
        }

    results["spec"] = spec

    n_steps = len(spec.get("steps", []))
    n_conds = len(spec.get("day_conditions") or [])
    await canvas_step(
        _NODE, "compile", "Compilar setup", "complete",
        subtitle=f"{n_steps} paso(s) de eventos + {n_conds} condición(es) de día",
        duration_ms=int((time.time() - t_comp) * 1000),
        blocks=[{
            "kind": "code",
            "language": "json",
            "content": json.dumps(spec, indent=2, ensure_ascii=False)[:800],
            "typewriter": True,
        }],
    )
    await _progress(
        f"Spec compilada: {n_steps} paso(s) de eventos + {n_conds} condición(es) de día. "
        f"Escaneando el universo completo ({spec.get('date', 'today')})..."
    )

    # ── Step 2: run the scan ──
    scan_args = {
        "steps": spec["steps"],
        "date": spec.get("date", "today"),
        "session": spec.get("session", "regular"),
        "day_conditions": spec.get("day_conditions") or [],
        "opening_minutes": spec.get("opening_minutes", 60),
        "sort_by": spec.get("sort_by", "close_vs_open_pct"),
        "limit": min(int(spec.get("limit") or 30), 100),
    }
    for k in ("min_market_cap", "max_market_cap", "min_price", "max_price"):
        if spec.get(k) is not None:
            scan_args[k] = spec[k]

    await canvas_step(
        _NODE, "scan", "Escanear el universo", "running",
        subtitle=f"eventos reales · {scan_args['date']} · todo el mercado",
    )
    t_scan = time.time()
    try:
        raw = await MCP.strategy.scan_day_setups(scan_args, timeout=150.0)
        if isinstance(raw, dict) and raw.get("error"):
            errors.append(f"scan: {raw['error']}")
            await canvas_step(
                _NODE, "scan", "Escanear el universo", "error",
                duration_ms=int((time.time() - t_scan) * 1000),
                blocks=[{"kind": "text", "text": str(raw["error"])[:220]}],
            )
        else:
            results["scan_results"] = _clean_matches(raw)
            matches = results["scan_results"]["matches"]
            rows = [
                [
                    str(m.get("symbol") or ""),
                    str(m.get("step1_event") or ""),
                    str(m.get("step1_time") or ""),
                    f"{m['close_vs_open_pct']:+.1f}%" if isinstance(m.get("close_vs_open_pct"), (int, float)) else "",
                ]
                for m in matches[:6]
            ]
            await canvas_step(
                _NODE, "scan", "Escanear el universo", "complete",
                subtitle=f"{results['scan_results']['count']} acciones cumplen el setup",
                duration_ms=int((time.time() - t_scan) * 1000),
                blocks=[{
                    "kind": "table",
                    "columns": ["Ticker", "Evento", "Hora", "Cierre/Open"],
                    "rows": rows,
                    "total": results["scan_results"]["count"],
                    "cascade": True,
                }] if rows else [{"kind": "text", "text": "El setup no se dio ese día."}],
            )
            await _progress(
                f"Scan completado: {results['scan_results']['count']} acciones "
                f"cumplen el setup ({raw.get('elapsed_ms', '?')}ms)."
            )
    except Exception as exc:
        errors.append(f"strategy/scan_day_setups: {exc}")
        await canvas_step(
            _NODE, "scan", "Escanear el universo", "error",
            duration_ms=int((time.time() - t_scan) * 1000),
            blocks=[{"kind": "text", "text": str(exc)[:220]}],
        )

    if errors:
        results["_errors"] = errors

    elapsed_ms = int((time.time() - start_time) * 1000)
    return {
        "agent_results": {
            "strategy_scanner": {
                "query_interpreted": query,
                **results,
            },
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "strategy_scanner": {
                "elapsed_ms": elapsed_ms,
                "match_count": results.get("scan_results", {}).get("count", 0),
                "error_count": len(errors),
            },
        },
    }
