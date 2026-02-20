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

from agents._mcp_tools import call_mcp_tool


# -- Intent detection --

_EARNINGS_KEYWORDS = [
    "earnings", "earning", "eps", "revenue",
    "quarterly", "quarter", "q1", "q2", "q3", "q4",
    "beat", "miss", "guidance", "forecast",
    "resultados", "ganancias", "trimestral", "reportan", "reporta",
    "reportes", "reporte",
]

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

def _extract_days(q: str) -> int:
    match = re.search(r'(\d+)\s*(?:days?|dias?)', q.lower())
    if match:
        return min(max(int(match.group(1)), 1), 30)
    return 7

_DATE_NUMERIC_RE = re.compile(
    r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})'
)
_ISO_DATE_RE = re.compile(r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})')


def _extract_date_reference(q: str, language: str = "en") -> tuple[str | None, str | None]:
    """Extract date_from and date_to from natural language references."""
    ql = q.lower()
    today = datetime.now()

    iso_m = _ISO_DATE_RE.search(ql)
    if iso_m:
        y, m, d = int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3))
        try:
            target = datetime(y, m, d)
            return target.strftime("%Y-%m-%d"), (target + timedelta(days=1)).strftime("%Y-%m-%d")
        except ValueError:
            pass

    num_m = _DATE_NUMERIC_RE.search(ql)
    if num_m:
        a, b, y = int(num_m.group(1)), int(num_m.group(2)), int(num_m.group(3))
        if language == "es":
            d, m = a, b
        else:
            m, d = a, b
        try:
            target = datetime(y, m, d)
            return target.strftime("%Y-%m-%d"), (target + timedelta(days=1)).strftime("%Y-%m-%d")
        except ValueError:
            d, m = m, d
            try:
                target = datetime(y, m, d)
                return target.strftime("%Y-%m-%d"), (target + timedelta(days=1)).strftime("%Y-%m-%d")
            except ValueError:
                pass

    day_map = {
        "monday": 0, "lunes": 0,
        "tuesday": 1, "martes": 1,
        "wednesday": 2, "miércoles": 2, "miercoles": 2,
        "thursday": 3, "jueves": 3,
        "friday": 4, "viernes": 4,
    }

    for name, weekday in day_map.items():
        if name in ql:
            days_back = (today.weekday() - weekday) % 7
            # days_back == 0 means "today is that day" → use today, not last week
            if days_back == 0:
                target = today
            else:
                target = today - timedelta(days=days_back)
            return target.strftime("%Y-%m-%d"), (target + timedelta(days=1)).strftime("%Y-%m-%d")

    if "yesterday" in ql or "ayer" in ql:
        yest = today - timedelta(days=1)
        # Skip weekends: if yesterday is Sunday → use Friday
        if yest.weekday() == 6:  # Sunday
            yest = today - timedelta(days=2)
        elif yest.weekday() == 5:  # Saturday
            yest = today - timedelta(days=1)
        return yest.strftime("%Y-%m-%d"), (yest + timedelta(days=1)).strftime("%Y-%m-%d")

    if "last week" in ql or "semana pasada" in ql:
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=5)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    return today.strftime("%Y-%m-%d"), (today + timedelta(days=1)).strftime("%Y-%m-%d")


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


def _clean_earnings(raw: Any) -> Any:
    """Clean earnings -- already small, just pass through."""
    return raw


_TODAY_KEEP = {
    "ticker", "company_name", "time", "time_slot", "fiscal_year", "fiscal_period",
    "estimated_eps", "actual_eps", "eps_surprise_percent",
    "estimated_revenue", "actual_revenue", "revenue_surprise_percent",
    "importance",
}


def _clean_today_earnings(raw: Any) -> dict:
    """Structure today's earnings into reported vs. scheduled, top entries only."""
    if not isinstance(raw, dict):
        return raw

    results = raw.get("results", [])
    stats = raw.get("stats", {})

    reported = []
    scheduled_bmo = []
    scheduled_amc = []

    for item in results:
        if not isinstance(item, dict):
            continue
        row = {k: v for k, v in item.items() if k in _TODAY_KEEP and v is not None}
        if not row.get("ticker"):
            continue
        if item.get("actual_eps") is not None:
            reported.append(row)
        elif item.get("time_slot") == "AMC":
            scheduled_amc.append(row)
        else:
            scheduled_bmo.append(row)

    importance_key = lambda x: -(x.get("importance") or 0)
    scheduled_bmo.sort(key=importance_key)
    scheduled_amc.sort(key=importance_key)

    return {
        "date": raw.get("date"),
        "total": stats.get("total", len(results)),
        "bmo_count": stats.get("bmo", len(scheduled_bmo)),
        "amc_count": stats.get("amc", len(scheduled_amc)),
        "reported_count": stats.get("reported", len(reported)),
        "reported": reported,
        "top_scheduled_bmo": scheduled_bmo[:25],
        "top_scheduled_amc": scheduled_amc[:25],
    }


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

    query = state.get("query", "")
    tickers = state.get("tickers", [])
    language = state.get("language", "en")
    chart_context = state.get("chart_context")
    wants_earn = _wants_earnings(query)
    wants_nws = _wants_news(query)
    wants_hist_events = _wants_historical_events(query)

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
            session = await call_mcp_tool("scanner", "get_market_session", {})
            results["market_session"] = session
        except Exception as exc:
            errors.append(f"market_session: {exc}")

    # -- Per-ticker data (parallelized) --
    if tickers:
        async def _fetch_ticker_news(t: str):
            try:
                raw = await call_mcp_tool("news", "get_news_by_ticker", {"symbol": t, "count": 10})
                return ("ticker_news", t, _clean_news(raw), None)
            except Exception as exc:
                return ("ticker_news", t, None, f"news/{t}: {exc}")

        async def _fetch_ticker_events(t: str):
            try:
                raw = await call_mcp_tool("events", "get_events_by_ticker", {"symbol": t, "count": 20})
                return ("ticker_events", t, _clean_events(raw), None)
            except Exception as exc:
                return ("ticker_events", t, None, f"events/{t}: {exc}")

        async def _fetch_ticker_earnings(t: str):
            try:
                raw = await call_mcp_tool("earnings", "get_earnings_by_ticker", {"ticker": t})
                return ("ticker_earnings", t, _clean_earnings(raw), None)
            except Exception as exc:
                return ("ticker_earnings", t, None, f"earnings/{t}: {exc}")

        async def _fetch_ticker_hist(t: str, df: str, dt: str, evt: str | None):
            try:
                params = {"symbol": t, "date_from": df, "date_to": dt, "limit": 50}
                if evt:
                    params["event_type"] = evt
                raw = await call_mcp_tool("events", "query_historical_events", params)
                return ("historical_events", t, _clean_events(raw), None)
            except Exception as exc:
                return ("historical_events", t, None, f"hist_events/{t}: {exc}")

        async def _fetch_sec_filings(t: str, df: str, dt: str):
            """Search SEC filings ±2 days around target candle (8-K = material events)."""
            try:
                raw = await call_mcp_tool("sec_filings", "search_filings", {
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
                date_from, date_to = _extract_date_reference(query, language)
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
                    raw = await call_mcp_tool(
                        "earnings",
                        "get_upcoming_earnings",
                        {"days": days, "min_importance": 3, "limit": 100},
                    )
                    results["upcoming_earnings"] = _clean_upcoming_earnings(raw)
                except Exception as exc:
                    errors.append(f"upcoming_earnings: {exc}")

            if timeframe == "today":
                try:
                    raw = await call_mcp_tool("earnings", "get_today_earnings", {})
                    results["today_earnings"] = _clean_today_earnings(raw)
                except Exception as exc:
                    errors.append(f"today_earnings: {exc}")

        if wants_hist_events:
            date_from, date_to = _extract_date_reference(query, language)
            event_type = _detect_event_type(query)
            try:
                params = {
                    "date_from": date_from,
                    "date_to": date_to,
                    "limit": 100,
                }
                if event_type:
                    params["event_type"] = event_type
                raw = await call_mcp_tool("events", "query_historical_events", params)
                results["historical_events"] = _clean_events(raw)
            except Exception as exc:
                errors.append(f"hist_events: {exc}")

            # Also fetch event stats for context
            try:
                stats_params = {"date": date_from}
                raw_stats = await call_mcp_tool("events", "get_event_stats", stats_params)
                results["event_stats"] = raw_stats
            except Exception as exc:
                errors.append(f"event_stats: {exc}")

        if wants_nws or (not wants_earn and not wants_hist_events):
            try:
                raw = await call_mcp_tool("news", "get_latest_news", {"count": 15})
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
