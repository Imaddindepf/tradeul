"""
News & Events Agent - Benzinga news, market events, and earnings calendar.

MCP tools used:
  - news.get_news_by_ticker(symbol, count)            - ticker-specific Benzinga news
  - news.get_latest_news(count)                        - general / broad market news
  - events.get_events_by_ticker(symbol, count)         - real-time events (Redis stream)
  - events.query_historical_events(...)                - historical events (TimescaleDB)
  - events.get_event_stats(date, symbol)               - event stats by type
  - earnings.get_earnings_by_ticker(ticker)            - earnings history for a ticker
  - earnings.get_today_earnings()                      - today's earnings calendar
  - earnings.get_upcoming_earnings(days)               - earnings next N days
  - earnings.get_earnings_results(date, time_slot)     - actual reported results (sorted)

Data cleaning:
  - News: strip body (full article text), keep only metadata + teaser
  - Upcoming earnings: filter importance>=3, keep key fields only
  - Events: keep all (already small)
  - Earnings history: keep all (already small)
"""
from __future__ import annotations
import asyncio
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

from agents.mcp_catalog import MCP


# -- Intent detection --

# Un solo vocabulario de earnings para todo el agente: vive en _constraints
# (lo usa también la guarda determinista del supervisor). Forkearlo aquí de
# nuevo es exactamente como planner y agentes acabaron en desacuerdo.
from agents._constraints import EARNINGS_KEYWORDS as _EARNINGS_KEYWORDS

_NEWS_KEYWORDS = [
    "news", "noticias", "noticia", "headlines", "article",
    "happened", "paso", "pasado", "recientes",
]

_UPCOMING_KEYWORDS = [
    "upcoming", "next", "this week", "esta semana",
    "proxima", "siguiente", "tomorrow", "week",
    "semana", "proximos", "pronto",
]

_TODAY_KEYWORDS = [
    "today", "hoy", "today's",
]

_HISTORICAL_EVENT_KEYWORDS = [
    "breakout", "halt", "halts", "halted",
    "vwap cross", "vwap crosses", "volume spike", "volume spikes",
    "momentum", "new high", "new low", "gap up", "gap down",
    "squeeze", "running up", "running down",
    "events", "event", "eventos", "evento",
    "event stats", "event summary",
    "what happened", "qué pasó", "que paso", "qué ocurrió",
    "friday", "monday", "tuesday", "wednesday", "thursday",
    "viernes", "lunes", "martes", "miércoles", "jueves",
    "yesterday", "ayer", "last week", "semana pasada",
    "crossing", "crossed", "cruce", "cruces",
]

_EVENT_TYPE_MAP = {
    "breakout": "orb_breakout_up",
    "halt": "halt",
    "halts": "halt",
    "halted": "halt",
    "vwap cross": "vwap_cross_up",
    "vwap crosses": "vwap_cross_up",
    "volume spike": "volume_surge",
    "volume spikes": "volume_surge",
    "volume surge": "volume_surge",
    "momentum": "running_up",
    "running up": "running_up",
    "running down": "running_down",
    "new high": "new_high",
    "new low": "new_low",
    "gap up": "gap_up_reversal",
    "gap down": "gap_down_reversal",
    "squeeze": "squeeze_fire",
    "crossing sma": "sma_cross_up",
    "crossed sma": "sma_cross_up",
    "crossing": "sma_cross_up",
    "crossed": "sma_cross_up",
}


def _wants_earnings(q: str) -> bool:
    return any(kw in q.lower() for kw in _EARNINGS_KEYWORDS)

def _wants_news(q: str) -> bool:
    return any(kw in q.lower() for kw in _NEWS_KEYWORDS)

def _wants_historical_events(q: str) -> bool:
    return any(kw in q.lower() for kw in _HISTORICAL_EVENT_KEYWORDS)

def _detect_event_type(q: str) -> str | None:
    ql = q.lower()
    for kw, etype in _EVENT_TYPE_MAP.items():
        if kw in ql:
            return etype
    return None

def _earnings_timeframe(q: str) -> str:
    ql = q.lower()
    if any(kw in ql for kw in _UPCOMING_KEYWORDS):
        return "upcoming"
    if any(kw in ql for kw in _TODAY_KEYWORDS):
        return "today"
    return "general"

# El vocabulario temporal (franjas, días, ventanas) vive en agents/_when para
# que todos los consumidores reconozcan las mismas frases. Ver ese módulo.
from agents._when import (  # noqa: F401
    _AMC_KEYWORDS,
    _BMO_KEYWORDS,
    _MAX_WINDOWS,
    _detect_time_slot,
    _day_mentions,
    _extract_date_reference,
    _extract_days,
    _extract_earnings_windows,
    _slot_mentions,
)


# -- Data cleaning --

_NEWS_KEEP_FIELDS = {"title", "author", "published", "url", "teaser", "tickers"}


def _clean_news(raw: Any) -> list[dict]:
    """Strip news articles to metadata-only."""
    items = raw
    if isinstance(raw, dict):
        items = raw.get("news", raw.get("articles", raw.get("data", [])))
    if not isinstance(items, list):
        return []

    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = {}
        for k in _NEWS_KEEP_FIELDS:
            if k in item and item[k] is not None:
                row[k] = item[k]
        if row:
            cleaned.append(row)
    return cleaned


def _clean_events(raw: Any) -> list[dict]:
    """Clean events -- already small, just ensure it's a list."""
    if isinstance(raw, dict):
        items = raw.get("events", raw.get("data", []))
        return items if isinstance(items, list) else []
    if isinstance(raw, list):
        return raw
    return []


# Campos de una fila de calendario que el modelo necesita para responder.
# Todo lo demás (grounding, guidance_commentary, event_id, imágenes) es peso
# muerto que empuja el payload contra el límite del sintetizador.
_CALENDAR_KEEP = {
    "symbol", "report_date", "company_name", "report_time", "time_slot", "fiscal_period",
    "eps_estimate", "eps_actual", "eps_surprise_pct",
    "revenue_estimate", "revenue_actual", "revenue_surprise_pct",
    "market_cap", "status", "importance",
}

# El resumen alimenta las conclusiones, así que se conserva — recortado, no
# eliminado. Un día entero de resúmenes completos son ~30 KB.
_SUMMARY_CHARS = 300


def _calendar_row(item: dict, report_date: str | None = None,
                  keep_summary: bool = True) -> dict:
    row = {k: v for k, v in item.items() if k in _CALENDAR_KEEP and v is not None}
    # Igual que en los resultados: la fila lleva su día. Al pedir varios días
    # y aplanarlos, una fila sin fecha acaba contada en el día que no es.
    if report_date and not row.get("report_date"):
        row["report_date"] = report_date
    # El resumen se conserva también en las programadas: su previa dice el
    # estimado y el historial de sorpresas, que es justo lo que se pregunta
    # antes de que reporten. Se quitó un rato para encajar en un tope de
    # payload que resultó ser arbitrario.
    summary = item.get("summary") if keep_summary else None
    if isinstance(summary, str) and summary.strip():
        text = " ".join(summary.split())
        row["summary"] = text[:_SUMMARY_CHARS] + ("…" if len(text) > _SUMMARY_CHARS else "")
    return row


def _clean_calendar(raw: Any, cap: int = 25) -> Any:
    """Compacta un día de calendario: reportadas vs pendientes, filas al grano.

    `cap` limita cada lista. Al pedir varios días el presupuesto se reparte,
    porque tres días crudos superan por sí solos el tope del sintetizador.
    """
    if not isinstance(raw, dict):
        return raw
    reports = raw.get("reports")
    if not isinstance(reports, list):
        return raw

    reported: list[dict] = []
    scheduled: list[dict] = []
    for item in reports:
        if not isinstance(item, dict) or not item.get("symbol"):
            continue
        ya_reporto = (item.get("eps_actual") is not None
                      or item.get("revenue_actual") is not None)
        row = _calendar_row(item, raw.get("date"))
        (reported if ya_reporto else scheduled).append(row)

    by_size = lambda r: -(r.get("market_cap") or 0)
    reported.sort(key=by_size)
    scheduled.sort(key=by_size)

    out = {
        "date": raw.get("date"),
        "total": len(reports),
        "reported_count": len(reported),
        "scheduled_count": len(scheduled),
        "reported": reported[:cap],
        "scheduled": scheduled[:cap],
    }
    # La vista de día no trae consenso, y eso viaja con los datos: si se
    # pierde aquí, el modelo deduce el beat/miss del texto y se equivoca de
    # signo. Lo declara el tool; el limpiador no puede tragárselo.
    if raw.get("estimates_available") is False:
        out["estimates_available"] = False
        out["note"] = raw.get("note")

    # Recortar es legítimo; hacerlo sin decirlo, no.
    if len(reported) > cap or len(scheduled) > cap:
        out["truncated"] = (
            f"showing the {cap} largest by market cap of "
            f"{len(reported)} reported / {len(scheduled)} scheduled"
        )
    return out


def _clean_earnings(raw: Any) -> Any:
    """Historial per-ticker: ya viene compacto."""
    return raw


_RESULTS_KEEP = {
    "symbol", "company", "time_slot", "eps_estimate", "eps_actual",
    "eps_surprise_pct", "revenue_estimate", "revenue_actual",
    "revenue_surprise_pct", "post_move_pct", "live_reaction_pct", "market_cap", "source",
}


def _clean_earnings_results(raw: Any) -> Any:
    """Compact reported results: keep key row fields only, drop nulls."""
    if not isinstance(raw, dict):
        return raw

    rows = []
    for item in raw.get("results", []):
        if not isinstance(item, dict):
            continue
        row = {k: v for k, v in item.items() if k in _RESULTS_KEEP and v is not None}
        if row.get("symbol"):
            rows.append(row)

    out = {
        "date": raw.get("date"),
        "time_slot": raw.get("time_slot"),
        "sort_by": raw.get("sort_by"),
        "count": len(rows),
        "results": rows,
    }
    # Señales de cobertura: sin esto el LLM no distingue "reportaron pocas"
    # de "quedan N por reportar" ni datos completos de datos degradados.
    if raw.get("scheduled_pending") is not None:
        out["scheduled_pending"] = raw["scheduled_pending"]
    if raw.get("partial"):
        out["partial"] = raw["partial"]
    return out


_UPCOMING_KEEP = {
    "ticker", "company_name", "date", "time", "fiscal_year", "fiscal_period",
    "estimated_eps", "actual_eps", "eps_surprise_percent",
    "estimated_revenue", "actual_revenue", "revenue_surprise_percent",
    "importance", "date_status",
}


def _clean_upcoming_earnings(raw: Any) -> dict:
    """Clean upcoming earnings: keep summary + trimmed results (key fields only)."""
    if not isinstance(raw, dict):
        return raw

    results = raw.get("results", [])
    cleaned = []
    for item in results:
        if not isinstance(item, dict):
            continue
        row = {k: v for k, v in item.items() if k in _UPCOMING_KEEP and v is not None}
        if row:
            cleaned.append(row)

    return {
        "count": raw.get("count", len(cleaned)),
        "start_date": raw.get("start_date"),
        "end_date": raw.get("end_date"),
        "by_date": raw.get("by_date", {}),
        "results": cleaned,
    }


# -- Main node --

# ── Native tool-calling path (Fase 3c) ──────────────────────────────

async def _news_events_node_native(state: dict, start_time: float) -> dict | None:
    """Ruta nativa: el selector LLM elige del roster de 15 tools; los args
    salen del estado (tickers, fechas, tipo de evento) de forma determinista.
    Recupera las 4 huérfanas: get_recent_events (eventos AHORA sin ticker),
    get_catalyst_alerts, get_available_event_types y get_earnings_by_date.
    Devuelve None si no aplica (candle forense) o si el selector falla — el
    caller cae a la ruta heurística (fail-safe)."""
    from agents._tool_selector import select_tools

    # El flujo forense de un candle (chart) tiene su propia orquestación
    # determinista (fechas ±2 días, cross-ref de earnings) — se queda como está.
    cc = state.get("chart_context")
    if cc and cc.get("targetCandle"):
        return None

    query = state.get("query", "")
    task = state.get("agent_task") or query
    tickers = list(state.get("tickers", []))[:5]

    from agents._tool_args import start_run, take_warnings
    start_run()

    selected = await select_tools("news_events", task)
    if not selected:
        return None

    date_from, date_to = _extract_date_reference(task)
    if not date_from and task != query:
        date_from, date_to = _extract_date_reference(query)
    event_type = _detect_event_type(task) or _detect_event_type(query)

    # Las ventanas se resuelven una sola vez y las comparten TODAS las ramas
    # que toman fecha. Calcularlas dentro de una rama fue el fallo original:
    # la consulta se contestaba entera o a medias según qué tool eligiera el
    # selector.
    windows = _extract_earnings_windows(task) or _extract_earnings_windows(query)
    window_dates: list[str] = []
    for d, _ in windows:
        if d and d not in window_dates:
            window_dates.append(d)

    results: dict[str, Any] = {}
    errors: list[str] = []

    async def _exec(tool: str) -> None:
        try:
            if tool == "scanner.get_market_session":
                results["market_session"] = await MCP.scanner.get_market_session({})
            elif tool == "news.get_latest_news":
                raw = await MCP.news.get_latest_news({"count": 15})
                results["latest_news"] = _clean_news(raw)
            elif tool == "news.get_news_by_ticker":
                for t in tickers:
                    raw = await MCP.news.get_news_by_ticker({"symbol": t, "count": 10})
                    results.setdefault("ticker_news", {})[t] = _clean_news(raw)
            elif tool == "news.get_catalyst_alerts":
                raw = await MCP.news.get_catalyst_alerts({"count": 20})
                results["catalyst_alerts"] = raw
            elif tool == "events.get_recent_events":
                params: dict[str, Any] = {"count": 50}
                if event_type:
                    params["event_type"] = event_type
                if len(tickers) == 1:
                    params["symbol"] = tickers[0]
                raw = await MCP.events.get_recent_events(params)
                results["recent_events"] = _clean_events(raw)
            elif tool == "events.get_events_by_ticker":
                for t in tickers:
                    raw = await MCP.events.get_events_by_ticker({"symbol": t, "count": 20})
                    results.setdefault("ticker_events", {})[t] = _clean_events(raw)
            elif tool == "events.query_historical_events":
                if tickers:
                    for t in tickers[:3]:
                        params = {"symbol": t, "date_from": date_from,
                                  "date_to": date_to, "limit": 50}
                        if event_type:
                            params["event_type"] = event_type
                        raw = await MCP.events.query_historical_events(params)
                        results.setdefault("historical_events", {})[t] = _clean_events(raw)
                else:
                    params = {"date_from": date_from, "date_to": date_to, "limit": 100}
                    if event_type:
                        params["event_type"] = event_type
                    raw = await MCP.events.query_historical_events(params)
                    results["historical_events"] = _clean_events(raw)
            elif tool == "events.get_event_stats":
                raw = await MCP.events.get_event_stats(
                    {"date": date_from} if date_from else {})
                results["event_stats"] = raw
            elif tool == "events.get_available_event_types":
                results["event_types"] = await MCP.events.get_available_event_types({})
            elif tool == "earnings.get_today_earnings":
                raw = await MCP.earnings.get_today_earnings({})
                results["today_earnings"] = _clean_calendar(raw)
            elif tool == "earnings.get_upcoming_earnings":
                raw = await MCP.earnings.get_upcoming_earnings(
                    {"days": _extract_days(task or query), "min_importance": 3, "limit": 100})
                results["upcoming_earnings"] = _clean_upcoming_earnings(raw)
            elif tool == "earnings.get_earnings_by_ticker":
                for t in tickers:
                    raw = await MCP.earnings.get_earnings_by_ticker({"ticker": t})
                    results.setdefault("ticker_earnings", {})[t] = _clean_earnings(raw)
            elif tool == "earnings.get_earnings_by_date":
                dates = window_dates or ([date_from] if date_from else [])
                if not dates:
                    errors.append("earnings_by_date: no date detected in query")
                else:
                    # Un día de calendario en crudo ronda los 30 KB, así que el
                    # cupo de filas se reparte entre los días pedidos.
                    cap = max(8, 25 // len(dates))

                    async def _one_date(day: str) -> dict:
                        raw = await MCP.earnings.get_earnings_by_date({"date": day})
                        return _clean_calendar(raw, cap=cap)

                    got = await asyncio.gather(
                        *(_one_date(d) for d in dates), return_exceptions=True)
                    days = []
                    for day, res in zip(dates, got):
                        if isinstance(res, Exception):
                            errors.append(f"earnings_by_date[{day}]: {res}")
                        else:
                            days.append({"date": day, "earnings": res})
                    if len(days) == 1 and len(dates) == 1:
                        results["earnings_by_date"] = days[0]
                    elif days:
                        results["earnings_by_date_days"] = days
                        results["earnings_dates_requested"] = dates
            elif tool == "earnings.get_earnings_results":
                # Una consulta puede abarcar varias ventanas ("pre market de
                # hoy y after hours de ayer"): se pide cada una y se devuelven
                # todas. Con una sola ventana la forma no cambia.
                today_str = datetime.now().strftime("%Y-%m-%d")
                # Nombre local: asignar `windows` aquí lo convertiría en
                # variable local de _exec y la lectura de arriba reventaría
                # con UnboundLocalError.
                wins = windows
                if not wins:
                    slot = _detect_time_slot(task) or _detect_time_slot(query)
                    date = date_from if date_from and date_from != today_str else None
                    wins = [(date, slot)]

                # El presupuesto de filas se REPARTE entre ventanas: tres
                # ventanas a 40 filas cada una triplican el payload, y el
                # sintetizador acaba recortando y partiendo la tabla a media
                # fila. El total se mantiene como el de una consulta simple.
                per_window = max(8, 40 // max(1, len(wins)))

                # Eje de orden: lo fija la restricción determinista si existe
                # ("por movimiento" → 'move'); si no, sorpresa como siempre.
                e_sort = (state.get("constraints") or {}).get("earnings_sort") or "surprise"

                async def _one_window(date: str | None, slot: str | None) -> dict:
                    # Sin fecha explícita el tool resuelve el día en ET: el
                    # reloj del contenedor puede ir por delante de NY.
                    params: dict = {"sort_by": e_sort, "limit": per_window}
                    if date and date != today_str:
                        params["date"] = date
                    if slot:
                        params["time_slot"] = slot
                    return _clean_earnings_results(
                        await MCP.earnings.get_earnings_results(params))

                fetched = await asyncio.gather(
                    *(_one_window(d, sl) for d, sl in wins),
                    return_exceptions=True,
                )
                ok = [f for f in fetched if not isinstance(f, Exception)]
                for (d, sl), f in zip(wins, fetched):
                    if isinstance(f, Exception):
                        errors.append(f"earnings_results[{d or 'today'}/{sl or 'all'}]: {f}")
                if len(ok) == 1 and len(wins) == 1:
                    results["earnings_results"] = ok[0]
                elif ok:
                    # Se declara lo que se pidió, no sólo lo que volvió: si una
                    # ventana falla, la respuesta lo dice en vez de parecer
                    # completa.
                    results["earnings_results_windows"] = ok
                    results["earnings_windows_requested"] = [
                        {"date": d or "today", "time_slot": sl or "all"}
                        for d, sl in wins
                    ]
            elif tool == "sec.search_filings":
                for t in tickers[:3]:
                    params = {"ticker": t, "page_size": 10}
                    if date_from:
                        params["date_from"] = date_from
                    if date_to:
                        params["date_to"] = date_to
                    raw = await MCP.sec.search_filings(params)
                    filings = raw.get("results", raw.get("filings", []))
                    results.setdefault("sec_filings", {})[t] = filings if isinstance(filings, list) else []
            else:
                errors.append(f"unknown tool {tool}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{tool}: {exc}")

    await asyncio.gather(*[_exec(t) for t in selected])

    if not results:
        # Sin resultados se cede a la heurística, pero un fallo de ejecución
        # NO es lo mismo que "este tool no aplica": si hubo errores hay que
        # gritarlos. Un UnboundLocalError aquí se tragó una tarde entera de
        # respuestas degradadas sin dejar rastro.
        if errors:
            logger.error(
                "news_events native: %d tool(s) failed and produced nothing — %s",
                len(errors), "; ".join(errors[:5]),
            )
        return None  # nada ejecutable — que responda la heurística

    if errors:
        results["_errors"] = errors

    elapsed_ms = int((time.time() - start_time) * 1000)
    # Lo que no se pudo pedir viaja con la respuesta: el sintetizador puede
    # decir "no pude consultar X" en lugar de dar por completa una consulta
    # recortada.
    dropped = take_warnings()
    payload = {
        "tickers_detected": tickers,
        "native_tools": selected,
        **results,
    }
    if errors:
        payload["errors"] = errors
    if dropped:
        payload["unrequested"] = dropped

    return {
        "agent_results": {"news_events": payload},
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "news_events": {
                "elapsed_ms": elapsed_ms,
                "tickers": tickers,
                "native": True,
                "tools": selected,
                "error_count": len(errors),
                "dropped_args": len(dropped),
            },
        },
    }


async def news_events_node(state: dict) -> dict:
    """Fetch news, events, and earnings via MCP tools.

    Strategy:
      - Tickers present: fetch per-ticker news + events + earnings (if wanted)
      - Historical event queries: use query_historical_events (TimescaleDB)
      - No tickers, earnings wanted: use appropriate earnings calendar tool
      - No tickers, news wanted: fetch latest market news
      - Only fetch what the user actually asked for (don't mix irrelevant data)
    """
    start_time = time.time()

    # ── Fase 3c: ruta nativa tras el flag; cualquier fallo cae a la heurística ──
    from agents._tool_selector import native_tools_enabled
    if native_tools_enabled("news_events"):
        try:
            native = await _news_events_node_native(state, start_time)
            if native is not None:
                return native
            logger.info("news_events native: sin selección — ruta heurística")
        except Exception:  # noqa: BLE001
            logger.exception("news_events native path failed — falling back to heuristic")

    query = state.get("query", "")
    tickers = list(state.get("tickers", []))
    intent = state.get("intent", "")
    chart_context = state.get("chart_context")

    # Ensure chart ticker is in the tickers list even if scanner rejected it
    if chart_context and chart_context.get("ticker"):
        chart_ticker = chart_context["ticker"].upper()
        if chart_ticker and chart_ticker not in tickers:
            tickers.append(chart_ticker)

    wants_earn = _wants_earnings(query)
    wants_nws = _wants_news(query)
    wants_hist_events = _wants_historical_events(query)

    # CAUSAL/CHART_ANALYSIS queries: always check earnings as most common catalyst
    if intent in ("CAUSAL", "CHART_ANALYSIS", "COMPLETE_ANALYSIS") and tickers:
        wants_earn = True

    # When a specific candle is targeted, force searches around that date
    target_candle_date: str | None = None
    if chart_context and chart_context.get("targetCandle"):
        tc = chart_context["targetCandle"]
        tc_ts = tc.get("date", 0)
        if tc_ts:
            target_candle_date = datetime.utcfromtimestamp(tc_ts).strftime("%Y-%m-%d")
            wants_hist_events = True
            wants_nws = True
            wants_earn = True

    results: dict[str, Any] = {}
    errors: list[str] = []

    # Fetch market session when earnings are relevant (synthesizer needs it)
    if wants_earn:
        try:
            session = await MCP.scanner.get_market_session({})
            results["market_session"] = session
        except Exception as exc:
            errors.append(f"market_session: {exc}")

    # -- Per-ticker data (parallelized) --
    if tickers:
        async def _fetch_ticker_news(t: str):
            try:
                raw = await MCP.news.get_news_by_ticker({"symbol": t, "count": 10})
                return ("ticker_news", t, _clean_news(raw), None)
            except Exception as exc:
                return ("ticker_news", t, None, f"news/{t}: {exc}")

        async def _fetch_ticker_events(t: str):
            try:
                raw = await MCP.events.get_events_by_ticker({"symbol": t, "count": 20})
                return ("ticker_events", t, _clean_events(raw), None)
            except Exception as exc:
                return ("ticker_events", t, None, f"events/{t}: {exc}")

        async def _fetch_ticker_earnings(t: str):
            try:
                raw = await MCP.earnings.get_earnings_by_ticker({"ticker": t})
                return ("ticker_earnings", t, _clean_earnings(raw), None)
            except Exception as exc:
                return ("ticker_earnings", t, None, f"earnings/{t}: {exc}")

        async def _fetch_ticker_hist(t: str, df: str, dt: str, evt: str | None):
            try:
                params = {"symbol": t, "date_from": df, "date_to": dt, "limit": 50}
                if evt:
                    params["event_type"] = evt
                raw = await MCP.events.query_historical_events(params)
                return ("historical_events", t, _clean_events(raw), None)
            except Exception as exc:
                return ("historical_events", t, None, f"hist_events/{t}: {exc}")

        async def _fetch_sec_filings(t: str, df: str, dt: str):
            """Search SEC filings ±2 days around target candle (8-K = material events)."""
            try:
                # Gateway mounts the SEC server with prefix "sec" (the old
                # "sec_filings" prefix 404'd silently on every call).
                raw = await MCP.sec.search_filings({
                    "ticker": t, "date_from": df, "date_to": dt, "page_size": 10,
                })
                filings = raw.get("results", raw.get("filings", []))
                if isinstance(filings, list):
                    return ("sec_filings", t, filings, None)
                return ("sec_filings", t, [], None)
            except Exception as exc:
                return ("sec_filings", t, None, f"sec_filings/{t}: {exc}")

        tasks = []
        for ticker in tickers[:5]:
            tasks.append(_fetch_ticker_news(ticker))
            tasks.append(_fetch_ticker_events(ticker))
        if wants_earn:
            for ticker in tickers[:5]:
                tasks.append(_fetch_ticker_earnings(ticker))
        if wants_hist_events:
            if target_candle_date:
                date_from = target_candle_date
                next_day = (datetime.strptime(target_candle_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
                date_to = next_day
            else:
                date_from, date_to = _extract_date_reference(query)
            event_type = _detect_event_type(query)
            for ticker in tickers[:3]:
                tasks.append(_fetch_ticker_hist(ticker, date_from, date_to, event_type))

        # SEC filings search ±2 days around target candle
        if target_candle_date:
            tc_dt = datetime.strptime(target_candle_date, "%Y-%m-%d")
            sec_from = (tc_dt - timedelta(days=2)).strftime("%Y-%m-%d")
            sec_to = (tc_dt + timedelta(days=2)).strftime("%Y-%m-%d")
            for ticker in tickers[:3]:
                tasks.append(_fetch_sec_filings(ticker, sec_from, sec_to))

        fetch_results = await asyncio.gather(*tasks)
        for category, tkr, data, err in fetch_results:
            if err:
                errors.append(err)
            elif data is not None:
                results.setdefault(category, {})[tkr] = data

        # Earnings cross-reference: match target candle date ±1 day
        if target_candle_date and "ticker_earnings" in results:
            tc_dt = datetime.strptime(target_candle_date, "%Y-%m-%d")
            for tkr, earn_data in results["ticker_earnings"].items():
                earn_list = earn_data if isinstance(earn_data, list) else (
                    earn_data.get("earnings", earn_data.get("results", []))
                    if isinstance(earn_data, dict) else []
                )
                if not isinstance(earn_list, list):
                    continue
                for earn in earn_list:
                    if not isinstance(earn, dict):
                        continue
                    ed = earn.get("date", "")
                    if not ed:
                        continue
                    try:
                        earn_dt = datetime.strptime(ed[:10], "%Y-%m-%d")
                    except (ValueError, TypeError):
                        continue
                    if abs((tc_dt - earn_dt).days) <= 1:
                        results["earnings_match"] = {
                            "ticker": tkr,
                            "earnings_date": ed,
                            "target_candle_date": target_candle_date,
                            "fiscal_period": earn.get("fiscal_period", ""),
                            "fiscal_year": earn.get("fiscal_year", ""),
                            "estimated_eps": earn.get("estimated_eps"),
                            "actual_eps": earn.get("actual_eps"),
                            "eps_surprise_percent": earn.get("eps_surprise_percent"),
                            "estimated_revenue": earn.get("estimated_revenue"),
                            "actual_revenue": earn.get("actual_revenue"),
                            "revenue_surprise_percent": earn.get("revenue_surprise_percent"),
                            "time": earn.get("time", ""),
                        }
                        logger.info("Earnings match for %s on %s (target candle %s)", tkr, ed, target_candle_date)
                        break

    # -- No tickers: calendar / general / historical event queries --
    else:
        if wants_earn:
            timeframe = _earnings_timeframe(query)

            if timeframe in ("upcoming", "general"):
                days = _extract_days(query)
                try:
                    raw = await MCP.earnings.get_upcoming_earnings(
                        {"days": days, "min_importance": 3, "limit": 100},
                    )
                    results["upcoming_earnings"] = _clean_upcoming_earnings(raw)
                except Exception as exc:
                    errors.append(f"upcoming_earnings: {exc}")

            if timeframe == "today":
                # Misma regla que en la ruta nativa: si la pregunta nombra
                # varios días se piden todos. Dejar esto sólo en la otra ruta
                # hacía que la respuesta dependiera de por dónde entrara.
                dates = [d for d, _ in _extract_earnings_windows(query) if d]
                if dates:
                    cap = max(8, 25 // len(dates))

                    async def _one_day(day: str) -> dict:
                        raw = await MCP.earnings.get_earnings_by_date({"date": day})
                        return {"date": day, "earnings": _clean_calendar(raw, cap=cap)}

                    got = await asyncio.gather(
                        *(_one_day(d) for d in dates), return_exceptions=True)
                    days = []
                    for day, res in zip(dates, got):
                        if isinstance(res, Exception):
                            errors.append(f"earnings_by_date[{day}]: {res}")
                        else:
                            days.append(res)
                    if days:
                        results["earnings_by_date_days"] = days
                        results["earnings_dates_requested"] = dates
                else:
                    try:
                        raw = await MCP.earnings.get_today_earnings({})
                        results["today_earnings"] = _clean_calendar(raw)
                    except Exception as exc:
                        errors.append(f"today_earnings: {exc}")

        if wants_hist_events:
            date_from, date_to = _extract_date_reference(query)
            event_type = _detect_event_type(query)
            try:
                params = {
                    "date_from": date_from,
                    "date_to": date_to,
                    "limit": 100,
                }
                if event_type:
                    params["event_type"] = event_type
                raw = await MCP.events.query_historical_events(params)
                results["historical_events"] = _clean_events(raw)
            except Exception as exc:
                errors.append(f"hist_events: {exc}")

            # Also fetch event stats for context
            try:
                stats_params = {"date": date_from}
                raw_stats = await MCP.events.get_event_stats(stats_params)
                results["event_stats"] = raw_stats
            except Exception as exc:
                errors.append(f"event_stats: {exc}")

        if wants_nws or (not wants_earn and not wants_hist_events):
            try:
                raw = await MCP.news.get_latest_news({"count": 15})
                results["latest_news"] = _clean_news(raw)
            except Exception as exc:
                errors.append(f"latest_news: {exc}")

    if errors:
        results["_errors"] = errors

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "agent_results": {
            "news_events": {
                "tickers_detected": tickers,
                "earnings_checked": wants_earn,
                "historical_events_checked": wants_hist_events,
                **results,
            },
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "news_events": {
                "elapsed_ms": elapsed_ms,
                "tickers": tickers,
                "earnings_checked": wants_earn,
                "historical_events_checked": wants_hist_events,
                "error_count": len(errors),
            },
        },
    }
