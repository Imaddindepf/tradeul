"""
Alert Compiler Agent — "describe your alert, see when it would have fired".

Pipeline (LLM compiles ONCE, deterministic runtime evaluates forever):
  1. Ground the LLM on the LIVE event catalog (same trick as strategy_scanner)
  2. LLM (fast tier) → AlertSpec IR draft (JSON, strict schema)
  3. Pydantic validation + event-type check against the live catalog
     (hallucinated event names are rejected, one repair round-trip)
  4. Dry-run: replay the spec over the last N trading days with evidence
  5. Persist as DRAFT in Postgres — the user confirms/arms via REST
     (or by follow-up chat turn)

The node NEVER arms anything by itself: creation is a two-phase commit
(draft + evidence → explicit user confirmation) so no alert goes live on a
misunderstood sentence.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.callbacks import adispatch_custom_event
from langchain_core.messages import HumanMessage, SystemMessage

from agents._canvas import canvas_step
from agents._llm_retry import llm_invoke_with_retry
from agents.mcp_catalog import MCP
from alerts.dryrun import run_dry_run
from alerts.similarity import find_similar
from alerts.spec import AlertSpec, validate_event_types
from alerts.store import get_store

logger = logging.getLogger(__name__)

_llm = None

# Live event catalog cache: {date: (fetched_at, types_set, prompt_text)}
# The vocabulary of a finished session never changes, so a long TTL is safe;
# it is also warmed at startup (see main.py) so no user pays the ~45s cold
# aggregation over ~12M event rows.
_catalog_cache: dict[str, tuple[float, set[str], str]] = {}
_CATALOG_TTL = 6 * 3600


def _get_llm():
    global _llm
    if _llm is None:
        from agents._make_llm import make_llm
        _llm = make_llm(tier="fast", temperature=0.0, max_tokens=2048)
    return _llm


async def _progress(message: str) -> None:
    try:
        await adispatch_custom_event("alert_compiler_progress", {"message": message})
    except Exception:
        pass


# ── Nodos dinámicos del canvas (el agente "monta" su workflow en vivo) ──

_NODE = "alert_compiler"


def _spec_code_block(spec: AlertSpec) -> dict[str, Any]:
    """La spec compilada como código: se escribe con typewriter en el canvas."""
    payload = {
        "tier": str(spec.tier),
        "universe": {
            k: v for k, v in spec.universe.model_dump().items()
            if v not in (None, [], "regular")
        },
        "steps": [
            {"event_types": s.event_types, "after": str(s.after)}
            for s in spec.steps
        ],
        "price_levels": [p.model_dump() for p in spec.price_levels],
        "lifecycle": {"cooldown_seconds": spec.lifecycle.cooldown_seconds},
    }
    if not payload["price_levels"]:
        payload.pop("price_levels")
    if spec.schedule is not None:
        payload["schedule"] = spec.schedule.model_dump()
    return {
        "kind": "code",
        "language": "json",
        "content": json.dumps(payload, indent=2, ensure_ascii=False)[:800],
        "typewriter": True,
    }


def _fmt_pct(row: dict[str, Any]) -> str:
    for k in ("postmarket_change_percent", "premarket_change_percent", "change_percent"):
        v = row.get(k)
        if isinstance(v, (int, float)):
            return f"{v:+.2f}%"
    return ""


def _fmt_mcap(v: Any) -> str:
    if not isinstance(v, (int, float)) or v <= 0:
        return ""
    if v >= 1e12:
        return f"{v / 1e12:.1f}T"
    if v >= 1e9:
        return f"{v / 1e9:.1f}B"
    return f"{v / 1e6:.0f}M"


async def _canvas_day_step(day: dict[str, Any]) -> None:
    """Un día del dry-run terminó: nodo nuevo con sus disparos reales."""
    date = day.get("date", "?")
    count = day.get("count", 0)
    rows = [
        [
            str(m.get("symbol") or ""),
            str(m.get("step1_event") or ""),
            str(m.get("step1_time") or ""),
            f"${m['step1_price']:.2f}" if isinstance(m.get("step1_price"), (int, float)) else "",
        ]
        for m in (day.get("matches") or [])[:5]
    ]
    blocks: list[dict[str, Any]] = (
        [{
            "kind": "table",
            "columns": ["Ticker", "Evento", "Hora", "Precio"],
            "rows": rows,
            "total": count,
            "cascade": True,
        }]
        if rows
        else [{"kind": "text", "text": day.get("error") or "Sin disparos ese día."}]
    )
    await canvas_step(
        _NODE, f"dry-{date}", f"Replay {date}", "complete",
        subtitle=f"{count} disparo(s) reales",
        blocks=blocks,
    )


# Curated core vocabulary (most useful for alert setups) — the live catalog
# appended below covers the rest and keeps counts honest.
_CORE_EVENTS = """\
vwap_cross_up / vwap_cross_down       - price crosses VWAP up/down
crossed_above_open / crossed_below_open
crossed_above_prev_close / crossed_below_prev_close
new_high / new_low                    - intraday extremes
running_up / running_down / running_up_sustained / running_down_sustained
orb_breakout_up / orb_breakout_down   - opening range breakout
gap_up_reversal / gap_down_reversal
pullback_25_from_high / pullback_75_from_high (also _from_low)
volume_surge / volume_spike_1min / rvol_spike
halt / resume
consol_breakout_5m / consol_breakdown_5m (also _10m)
channel_breakout / channel_breakdown
double_top / double_bottom
sma5_above_sma8_1m / sma5_below_sma8_1m (also _2m)
macd_above_signal_5m / macd_below_signal_5m
stoch_cross_bullish_5m / stoch_cross_bearish_5m
bb_upper_breakout / bb_lower_breakdown
linreg_up_5m / linreg_down_5m
sma_thrust_up_2m / sma_thrust_down_2m
"""

COMPILER_PROMPT = """\
You are the alert-spec compiler for Tradeul. The user describes, in natural
language, a market alert they want to be notified
about. You compile it into a strict AlertSpec JSON. A deterministic engine
— not you — will evaluate it in real time, so precision matters more than
creativity.

OUTPUT: ONLY a JSON object (no markdown fences) with these keys:
{
  "name": "short human name for the alert (<=60 chars)",
  "paraphrase": "1-2 sentences restating EXACTLY what \
will be watched and when it fires. The user will confirm this text.",
  "tier": "event_match" | "sequence" | "membership" | "scheduled",
  "universe": {
    "symbols_include": [],          // uppercase tickers, [] = all stocks
    "symbols_exclude": [],
    "min_price": null | number,
    "max_price": null | number,
    "min_rvol": null | number,      // "RVOL above 1.5" -> 1.5
    "min_volume": null | number,
    "min_market_cap": null | number, // "1B" = 1000000000
    "max_market_cap": null | number,
    "sector": null | "string",
    "session": "regular" | "premarket" | "afterhours" | "all"
  },
  "steps": [                        // 1 step = event_match, 2-3 = sequence; [] for membership
    {
      "event_types": ["vwap_cross_up"],   // ONLY from EVENT TYPES below
      "after": "session_open" | "opening_low" | "prev_step",
      "within_minutes": null | int
    }
  ],
  "day_conditions": [               // OPTIONAL day-level context conditions
    {"metric": "opening_drop_pct", "op": "lte", "value": -2}
  ],
  "membership": null | {            // ONLY when tier = "membership"
    "category": "gappers_up",       // scanner category
    "on": "enter" | "exit",
    "rank_lte": null | int          // e.g. 10 = top 10 only
  },
  "schedule": null | {              // ONLY when tier = "scheduled"
    "every_seconds": 60,            // 30-86400; "cada minuto" = 60
    "task": "scanner_snapshot",
    "category": "post_market",      // gappers_up, gappers_down, momentum_up,
                                    // momentum_down, high_volume, winners,
                                    // losers, reversals, anomalies, new_highs,
                                    // new_lows, post_market, halts
    "limit": 10,                    // top N rows per capture (1-25)
    "sessions": []                  // only run during: PRE_MARKET, MARKET_OPEN,
                                    // POST_MARKET, CLOSED; [] = always
  },
  "price_levels": [                 // ABSOLUTE price levels (needs symbols_include)
    {"direction": "above", "value": 502},   // fires when price crosses UP through 502
    {"direction": "below", "value": 500}    // fires when price crosses DOWN through 500
  ],                                // multiple levels are OR'ed; [] when unused
  "lifecycle": {
    "cooldown_seconds": 900,        // min seconds between fires per symbol
    "max_fires_per_day": 20
  },
  "message_template": "{symbol}: <short fire message>",
  "dry_run_days": 5                 // 1-10, how many past days to preview
}

DAY METRICS: open_price, close_price, low_price, high_price,
close_vs_open_pct, opening_drop_pct, low_vs_open_pct, high_vs_open_pct,
market_cap, n_events.

RULES:
1. tier "event_match" = ONE step, fires live the moment the event happens.
   tier "sequence" = 2-3 ordered steps (A then B) with within_minutes windows.
   Prefer event_match when one event type captures the intent.
   tier "membership" = symbol ENTERS/EXITS a scanner ranking (gappers_up,
   winners, momentum_up, high_volume, new_highs, losers…). Use when the user
   says "cuando entre en top gappers", "entra en winners", "sale de losers".
   For membership: steps=[], membership={category,on,rank_lte}, dry_run_days=0.
   tier "scheduled" = PERIODIC SNAPSHOT workflow: the user wants a recurring
   "picture"/"foto"/"captura"/"resumen" of a ranking on an interval ("cada
   minuto", "every 5 minutes", "cada hora"). NOT event-driven — time-driven.
   For scheduled: steps=[], schedule={every_seconds, task, category, limit,
   sessions}, dry_run_days=0. Map "after hours"/"post market" to category
   post_market AND sessions ["POST_MARKET"]; "premarket" -> gappers_up +
   ["PRE_MARKET"]; "top stocks"/"top gainers" during regular -> winners or
   momentum_up. Universe filters (min_market_cap...) still apply.
2. day_conditions describe how the DAY looked (close vs open, opening drop).
   They only make sense for reviewing PAST days — a live alert cannot know
   the close in advance. Use them ONLY when the user describes day-level
   context; leave [] for pure live alerts. Sequences WITHOUT day_conditions
   ARE live-armable on the CEP runtime.
3. Momentum/strategy vocabulary mapping:
   - "cruce del VWAP al alza" / "crosses above VWAP" -> vwap_cross_up
   - "9 EMA cruza VWAP" (Fashionably Late style) -> closest available:
     vwap_cross_up + note in paraphrase that the engine uses price/VWAP cross;
     dedicated EMA9/VWAP-slope events land in a later phase. Be HONEST in the
     paraphrase about the approximation.
   - "RVOL por encima de N" -> universe.min_rvol = N
   - "ruptura del rango de apertura" / "ORB" -> orb_breakout_up/_down
   - "halt" / "parada" -> halt; "reanuda" -> resume
   - "volumen inusual" / "volume spike" -> volume_surge, volume_spike_1min, rvol_spike
   - "top gappers" / "gap up" ranking -> membership gappers_up enter
   - "top losers" -> membership losers enter
4. Numbers: "1B" = 1000000000, "500M" = 500000000, "$5" -> min/max_price 5.
5. cooldown: scalping alerts 300-900s; slower setups 1800-3600s. Default 900.
6. paraphrase MUST be faithful — it is the
   contract the user confirms. Mention universe filters, the event(s), the
   order, and the cooldown.
7. Direction matters: "cruce a la baja"/"short" versions use the _down /
   bearish event variants. Invert every condition, not just the first.
8. If the user mentions specific tickers, put them in symbols_include.
9. For live sequences prefer two real event steps (e.g. pullback then
   vwap_cross_up) with within_minutes, NOT day_conditions.
10. ABSOLUTE PRICE LEVELS ("reclame 502", "pierda 500", "supere los 300",
   "cruce por encima de 502", "break above 300", "toque 150"): use
   tier="event_match" with steps=[] and price_levels=[...]. "reclamar" /
   "superar" / "romper al alza" -> direction "above"; "perder" / "caer por
   debajo" / "breakdown" -> direction "below". Several levels in one
   sentence ("reclame 502 O pierda 500") go in the SAME price_levels array
   (any cross fires). This REQUIRES specific tickers in symbols_include.
   Do NOT confuse absolute levels with min_price/max_price universe filters
   (those pre-filter the universe, they never fire an alert).

EVENT TYPES (core vocabulary):
""" + _CORE_EVENTS + """
{live_catalog}

EXAMPLES:

User: "avísame cuando cualquier acción con rvol mayor a 1.5 cruce el vwap al alza"
{"name": "Cruce VWAP alcista con RVOL > 1.5", "paraphrase": "Vigilaré todas las acciones en sesión regular con RVOL por encima de 1.5 y te avisaré en el momento en que el precio cruce el VWAP al alza (máximo un aviso cada 15 minutos por símbolo).", "tier": "event_match", "universe": {"symbols_include": [], "symbols_exclude": [], "min_price": null, "max_price": null, "min_rvol": 1.5, "min_volume": null, "min_market_cap": null, "max_market_cap": null, "sector": null, "session": "regular"}, "steps": [{"event_types": ["vwap_cross_up"], "after": "session_open", "within_minutes": null}], "day_conditions": [], "lifecycle": {"cooldown_seconds": 900, "max_fires_per_day": 20}, "message_template": "{symbol}: cruce de VWAP al alza con RVOL {rvol}", "dry_run_days": 3}

User: "alert me when TSLA gets halted"
{"name": "TSLA halt", "paraphrase": "I will watch TSLA during all sessions and notify you the moment a trading halt is detected (at most one alert every 5 minutes).", "tier": "event_match", "universe": {"symbols_include": ["TSLA"], "symbols_exclude": [], "min_price": null, "max_price": null, "min_rvol": null, "min_volume": null, "min_market_cap": null, "max_market_cap": null, "sector": null, "session": "all"}, "steps": [{"event_types": ["halt"], "after": "session_open", "within_minutes": null}], "day_conditions": [], "lifecycle": {"cooldown_seconds": 300, "max_fires_per_day": 20}, "message_template": "{symbol} HALTED at {price}", "dry_run_days": 5}

User: "acciones de más de 1B que caigan fuerte en el opening y luego crucen el vwap al alza tras el mínimo"
{"name": "Reclaim de VWAP tras caída en el opening (>1B)", "paraphrase": "Vigilaré acciones con capitalización superior a 1B: cuando caigan al menos un 2% en la primera hora y después crucen el VWAP al alza tras marcar el mínimo del opening, te avisaré. Nota: la condición de caída se evalúa sobre el día en curso, por lo que esta alerta funciona mejor como secuencia intradía.", "tier": "sequence", "universe": {"symbols_include": [], "symbols_exclude": [], "min_price": null, "max_price": null, "min_rvol": null, "min_volume": null, "min_market_cap": 1000000000, "max_market_cap": null, "sector": null, "session": "regular"}, "steps": [{"event_types": ["vwap_cross_up"], "after": "opening_low", "within_minutes": null}], "day_conditions": [{"metric": "opening_drop_pct", "op": "lte", "value": -2}], "membership": null, "lifecycle": {"cooldown_seconds": 1800, "max_fires_per_day": 10}, "message_template": "{symbol}: reclaim de VWAP tras caída en el opening", "dry_run_days": 5}

User: "avísame cuando AMD reclame 502 o pierda 500"
{"name": "AMD reclama 502 / pierde 500", "paraphrase": "Vigilaré AMD durante la sesión regular y te avisaré cuando el precio cruce al alza los $502 (reclaim) o cruce a la baja los $500 (pérdida del nivel), con un máximo de un aviso cada 5 minutos.", "tier": "event_match", "universe": {"symbols_include": ["AMD"], "symbols_exclude": [], "min_price": null, "max_price": null, "min_rvol": null, "min_volume": null, "min_market_cap": null, "max_market_cap": null, "sector": null, "session": "regular"}, "steps": [], "day_conditions": [], "membership": null, "price_levels": [{"direction": "above", "value": 502}, {"direction": "below", "value": 500}], "lifecycle": {"cooldown_seconds": 300, "max_fires_per_day": 20}, "message_template": "{symbol}: cruce del nivel {level} ({direction}) a {price}", "dry_run_days": 5}

User: "give me every 1 minute a picture of top stocks after hours with market cap above 1b"
{"name": "Top after-hours >1B cada minuto", "paraphrase": "Cada minuto durante el after-hours capturaré el top 10 de acciones con mayor movimiento post-market y capitalización superior a 1B, y te lo enviaré como snapshot en vivo.", "tier": "scheduled", "universe": {"symbols_include": [], "symbols_exclude": [], "min_price": null, "max_price": null, "min_rvol": null, "min_volume": null, "min_market_cap": 1000000000, "max_market_cap": null, "sector": null, "session": "afterhours"}, "steps": [], "day_conditions": [], "membership": null, "schedule": {"every_seconds": 60, "task": "scanner_snapshot", "category": "post_market", "limit": 10, "sessions": ["POST_MARKET"]}, "price_levels": [], "lifecycle": {"cooldown_seconds": 60, "max_fires_per_day": 500}, "message_template": "{trigger_name}: top after-hours actualizado", "dry_run_days": 0}

User: "avísame cuando una acción entre en el top 10 de gappers"
{"name": "Entra en top 10 gappers", "paraphrase": "Te avisaré en el momento en que cualquier acción entre en el top 10 del scanner de gappers al alza durante la sesión regular (máximo un aviso cada 15 minutos por símbolo).", "tier": "membership", "universe": {"symbols_include": [], "symbols_exclude": [], "min_price": null, "max_price": null, "min_rvol": null, "min_volume": null, "min_market_cap": null, "max_market_cap": null, "sector": null, "session": "regular"}, "steps": [], "day_conditions": [], "membership": {"category": "gappers_up", "on": "enter", "rank_lte": 10}, "lifecycle": {"cooldown_seconds": 900, "max_fires_per_day": 30}, "message_template": "{symbol}: entra en top gappers (#{rank})", "dry_run_days": 0}
"""

_REPAIR_PROMPT = """\
Your previous AlertSpec JSON had validation errors:

{errors}

Return the FULL corrected JSON object (same schema, no markdown fences).
Use ONLY event types from the catalog you were given.
"""


async def _get_live_catalog(date: str = "yesterday") -> tuple[set[str], str]:
    """Fetch (cached) the live event-type catalog: (known_types, prompt_text).

    Defaults to YESTERDAY: a complete session covers the full vocabulary
    (a today catalog compiled at 09:35 would miss most afternoon patterns)
    and the gateway can cache it for the whole day.
    """
    now = time.time()
    cached = _catalog_cache.get(date)
    if cached and now - cached[0] < _CATALOG_TTL:
        return cached[1], cached[2]
    known: set[str] = set()
    text = ""
    try:
        # Cold catalog aggregates ~12M event rows; the gateway caches it after
        # the first call, but that first call needs more than the 30s default.
        raw = await MCP.strategy.get_event_catalog(
            {"date": date, "min_count": 100}, timeout=170.0,
        )
        if isinstance(raw, dict) and raw.get("error"):
            raise RuntimeError(raw["error"])
        types = raw.get("event_types", [])
        known = {t["event_type"] for t in types}
        lines = [f"{t['event_type']} ({t['symbols']} symbols)" for t in types[:150]]
        text = "LIVE EVENT TYPES firing on " + raw.get("date", date) + ":\n" + ", ".join(lines)
    except Exception as exc:
        logger.warning("alert_compiler: live catalog unavailable: %s", exc)
    _catalog_cache[date] = (now, known, text)
    return known, text


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.lower().startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _build_spec(payload: dict[str, Any], query: str, user_id: str) -> AlertSpec:
    """Map the LLM draft onto the AlertSpec IR (raises on invalid)."""
    actions = [{
        "channel": "in_app",
        "message_template": payload.get("message_template"),
    }]
    return AlertSpec(
        user_id=user_id,
        name=payload.get("name") or "Alerta sin nombre",
        source_query=query,
        paraphrase=payload.get("paraphrase") or "",
        tier=payload.get("tier") or "event_match",
        universe=payload.get("universe") or {},
        steps=payload.get("steps") or [],
        day_conditions=payload.get("day_conditions") or [],
        membership=payload.get("membership"),
        schedule=payload.get("schedule"),
        price_levels=payload.get("price_levels") or [],
        lifecycle=payload.get("lifecycle") or {},
        actions=actions,
    )


async def _compile_with_repair(
    query: str, user_id: str, known_types: set[str], catalog_text: str,
) -> tuple[AlertSpec | None, dict[str, Any] | None, str]:
    """LLM → AlertSpec with one validation-repair round trip.

    Returns (spec, raw_payload, error). spec is None on failure.
    """
    llm = _get_llm()
    system = SystemMessage(content=COMPILER_PROMPT.replace("{live_catalog}", catalog_text))
    messages: list[Any] = [system, HumanMessage(content=query)]

    last_error = ""
    for attempt in range(2):
        response = await llm_invoke_with_retry(llm, messages)
        raw = _strip_fences(response.content)
        try:
            payload = json.loads(raw)
            spec = _build_spec(payload, query, user_id)
            unknown = validate_event_types(spec, known_types)
            if unknown:
                raise ValueError(
                    f"unknown event types (not firing on the live engine): {unknown}"
                )
            dry_days = payload.get("dry_run_days") or 5
            return spec, {"dry_run_days": dry_days}, ""
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = str(exc)
            logger.info("alert_compiler validation failed (attempt %d): %s", attempt + 1, exc)
            if attempt == 0:
                messages = [
                    system,
                    HumanMessage(content=query),
                    response,
                    HumanMessage(content=_REPAIR_PROMPT.format(errors=last_error)),
                ]
    return None, None, last_error


# ── Graph node ───────────────────────────────────────────────────

async def alert_compiler_node(state: dict) -> dict:
    """Compile NL alert sentence → validated AlertSpec draft + dry-run evidence."""
    start = time.time()
    query = state.get("agent_task") or state.get("query", "")
    user_id = state.get("user_id") or "default"

    results: dict[str, Any] = {}
    errors: list[str] = []

    await _progress("Compiling your alert into an executable spec...")

    # ── 1-3: catalog grounding + compile + validate (with 1 repair) ──
    await canvas_step(
        _NODE, "catalog", "Catálogo de eventos", "running",
        subtitle="vocabulario en vivo del alert engine",
    )
    t_cat = time.time()
    known_types, catalog_text = await _get_live_catalog()
    await canvas_step(
        _NODE, "catalog", "Catálogo de eventos", "complete",
        subtitle="vocabulario en vivo del alert engine",
        duration_ms=int((time.time() - t_cat) * 1000),
        blocks=[{
            "kind": "metrics",
            "items": [
                {"label": "tipos de evento", "value": len(known_types) or "240+"},
                {"label": "fuente", "value": "engine en vivo"},
            ],
        }],
    )

    await canvas_step(
        _NODE, "compile", "Compilar spec ejecutable", "running",
        subtitle="lenguaje natural → AlertSpec JSON",
    )
    t_comp = time.time()
    try:
        spec, meta, err = await _compile_with_repair(query, user_id, known_types, catalog_text)
    except Exception as exc:
        spec, meta, err = None, None, f"compiler crashed: {exc}"

    if spec is None:
        await canvas_step(
            _NODE, "compile", "Compilar spec ejecutable", "error",
            subtitle="la validación rechazó la spec",
            duration_ms=int((time.time() - t_comp) * 1000),
            blocks=[{"kind": "text", "text": (err or "")[:220]}],
        )
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "agent_results": {
                "alert_compiler": {
                    "error": f"No pude compilar la alerta: {err}",
                    "query_interpreted": query,
                },
            },
            "execution_metadata": {
                **(state.get("execution_metadata", {})),
                "alert_compiler": {"elapsed_ms": elapsed_ms, "error": "compile_failed"},
            },
        }

    await canvas_step(
        _NODE, "compile", "Compilar spec ejecutable", "complete",
        subtitle=f"tier {spec.tier} · validada contra el catálogo",
        duration_ms=int((time.time() - t_comp) * 1000),
        blocks=[_spec_code_block(spec)],
    )

    results["spec"] = spec.model_dump(mode="json")
    results["paraphrase"] = spec.paraphrase
    results["armable_now"] = spec.is_live_armable()

    # ── 3b: duplicate / near-duplicate check against user's existing specs ──
    store = get_store()
    existing = await store.list_specs(user_id, include_archived=False)
    similar = find_similar(spec, existing)
    results["similar"] = similar
    if similar["recommendation"] == "reuse":
        # Exact duplicate already exists — do NOT create another draft.
        # Surface the existing one so the UI can reuse/arm it.
        match = similar["exact"][0]
        await _progress(
            f"Ya tienes una alerta equivalente («{match['name']}», "
            f"estado: {match['status']}). No creo un borrador duplicado."
        )
        results["duplicate"] = True
        results["existing_spec_id"] = match["spec_id"]
        results["spec_id"] = match["spec_id"]
        results["persisted"] = False
        # Still attach a dry-run preview of the NEW draft so the user sees
        # evidence, but reuse the existing id for arming.
        dry_days = int((meta or {}).get("dry_run_days", 5))
        if dry_days > 0 and (spec.steps or spec.price_levels):
            try:
                results["dry_run"] = await run_dry_run(
                    spec, days=dry_days,
                    on_progress=_progress, on_day=_canvas_day_step,
                )
            except Exception as exc:
                errors.append(f"dry_run: {exc}")
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "agent_results": {
                "alert_compiler": {
                    "query_interpreted": query,
                    **results,
                },
            },
            "execution_metadata": {
                **(state.get("execution_metadata", {})),
                "alert_compiler": {
                    "elapsed_ms": elapsed_ms,
                    "tier": str(spec.tier),
                    "duplicate": True,
                    "error_count": len(errors),
                },
            },
        }

    if similar["recommendation"] == "review":
        await _progress(
            f"Encontré {len(similar['near'])} alerta(s) parecida(s). "
            "Creo el borrador nuevo; revisa si prefieres reutilizar una existente."
        )

    # ── 4: dry-run with evidence (skip for membership — no historical events) ──
    dry_days = int((meta or {}).get("dry_run_days", 5))
    if dry_days > 0 and (spec.steps or spec.price_levels):
        await _progress(
            f"Spec validated ({spec.tier}). Checking when it would have fired "
            f"over the last {dry_days} market days..."
        )
        try:
            dry = await run_dry_run(
                spec, days=dry_days,
                on_progress=_progress, on_day=_canvas_day_step,
            )
            spec.dry_run = {
                "total_fires": dry["total_fires"],
                "days_scanned": dry["days_scanned"],
                "unique_symbols": dry["unique_symbols"][:30],
                "ran_at": time.time(),
            }
            results["dry_run"] = dry
            await _progress(
                f"Dry-run completado: {dry['total_fires']} disparos en "
                f"{len(dry['days_scanned'])} días ({len(dry['unique_symbols'])} símbolos)."
            )
        except Exception as exc:
            errors.append(f"dry_run: {exc}")
    elif spec.is_scheduled_armable():
        # Scheduled workflows: no dry-run — run ONE capture right now so the
        # user (and the canvas) see exactly what each interval will deliver.
        await canvas_step(
            _NODE, "preview", "Primera captura", "running",
            subtitle=f"cada {spec.schedule.every_seconds}s · {spec.schedule.category}",
        )
        t_prev = time.time()
        try:
            from alerts.scheduler import run_snapshot_task
            preview = await run_snapshot_task(spec)
            results["preview"] = preview
            rows = preview.get("rows") or []
            table_rows = [
                [
                    str(r.get("symbol") or ""),
                    f"${r['price']:.2f}" if isinstance(r.get("price"), (int, float)) else "",
                    _fmt_pct(r),
                    _fmt_mcap(r.get("market_cap")),
                ]
                for r in rows[:8]
            ]
            await canvas_step(
                _NODE, "preview", "Primera captura", "complete",
                subtitle=(
                    f"{len(rows)} valores · se repetirá cada {spec.schedule.every_seconds}s"
                    if rows else (preview.get("note") or "sin datos ahora mismo")
                ),
                duration_ms=int((time.time() - t_prev) * 1000),
                blocks=[{
                    "kind": "table",
                    "columns": ["Ticker", "Precio", "Cambio", "MCap"],
                    "rows": table_rows,
                    "total": len(rows),
                    "cascade": True,
                }] if table_rows else [{
                    "kind": "text",
                    "text": preview.get("note") or "La captura llegará al armar el workflow.",
                }],
            )
        except Exception as exc:
            errors.append(f"preview: {exc}")
            await canvas_step(
                _NODE, "preview", "Primera captura", "error",
                blocks=[{"kind": "text", "text": str(exc)[:220]}],
            )
        results["dry_run"] = {
            "total_fires": 0, "days_scanned": [], "unique_symbols": [],
            "per_day": [], "errors": [], "note": "scheduled workflows preview live, not historically",
        }
    elif not spec.steps and not spec.price_levels:
        results["dry_run"] = {
            "total_fires": 0, "days_scanned": [], "unique_symbols": [],
            "per_day": [], "errors": [], "note": "membership alerts have no historical dry-run",
        }

    # ── 5: persist as DRAFT (user confirms via REST /api/alerts/{id}/arm) ──
    persisted = await store.save_spec(spec)
    results["persisted"] = persisted
    results["spec_id"] = spec.id
    results["duplicate"] = False
    if not persisted:
        errors.append("persistence unavailable — spec draft was not saved")

    dry_summary = spec.dry_run or {}
    await canvas_step(
        _NODE, "persist", "Borrador guardado", "complete" if persisted else "error",
        subtitle="confírmalo para armarlo en vivo",
        blocks=[{
            "kind": "metrics",
            "items": [
                {"label": "disparos", "value": dry_summary.get("total_fires", 0)},
                {"label": "símbolos", "value": len(dry_summary.get("unique_symbols") or [])},
                {"label": "estado", "value": "draft"},
            ],
        }],
    )

    if errors:
        results["_errors"] = errors

    elapsed_ms = int((time.time() - start) * 1000)
    logger.info(
        "alert_compiler: compiled '%s' tier=%s fires=%s persisted=%s in %dms",
        spec.name, spec.tier,
        (spec.dry_run or {}).get("total_fires", "?"), persisted, elapsed_ms,
    )
    return {
        "agent_results": {
            "alert_compiler": {
                "query_interpreted": query,
                **results,
            },
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "alert_compiler": {
                "elapsed_ms": elapsed_ms,
                "tier": str(spec.tier),
                "total_fires": (spec.dry_run or {}).get("total_fires"),
                "error_count": len(errors),
            },
        },
    }
