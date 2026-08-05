"""
Rosters de herramientas por agente — la spec del tool-calling nativo (Fase 3c).

Hoy cada agente llama sus tools hardcodeadas; 29 de las 63 tools del catálogo
(46%) están declaradas pero jamás se invocan (huérfanas). La Fase 3c da a
cada agente selección nativa de herramientas sobre SU roster: este archivo
define qué tools posee cada agente — las que ya usa (`used`) más las
huérfanas que le corresponden por dominio (`orphans`, la capacidad a
recuperar).

Fuente de verdad de la asignación: qué agente usa hoy cada servidor MCP
(grep MCP.<server>.* por archivo, 2026-07-22).

`TOOL_DESCS` da la descripción que ve el selector LLM (agents/_tool_selector).
Se va completando agente a agente según entran al rollout nativo; para tools
sin entrada aquí, el selector cae al snapshot del gateway
(evals/gateway_tools_snapshot.json) y en último término al nombre.

Formato de tool: "server.tool" (el full_name del gateway es server_tool).
"""
from __future__ import annotations

ROSTERS: dict[str, dict[str, list[str]]] = {
    "market_data": {
        "used": [
            "scanner.get_market_session",
            "scanner.get_scanner_snapshot",
            "scanner.get_enriched_batch",
            "scanner.apply_dynamic_filter",
            "analytics.get_technical_snapshot",
            "historical.get_day_bars",
            "historical.get_minute_bars",
            "patterns.find_similar_patterns",
            "market_pulse.analyze_market",
            "market_pulse.get_market_regime",
            "screener.search_by_theme",
            "screener.enrich_with_classification",
        ],
        "orphans": [
            "scanner.get_enriched_ticker",   # snapshot 1-ticker sin batch
            "scanner.search_scanner",        # búsqueda libre en el scanner
            "scanner.get_all_categories",    # listado de categorías live
            "analytics.get_rvol",            # RVOL puntual
            "analytics.get_rvol_batch",      # RVOL en lote
            "analytics.get_price_windows",   # ventanas de precio (5m/30m/1h…)
            "analytics.get_volume_windows",  # ventanas de volumen
            "historical.get_top_movers",     # top movers de una fecha pasada
            "historical.available_dates",    # qué fechas hay en la BD
        ],
    },
    "news_events": {
        "used": [
            "news.get_latest_news",
            "news.get_news_by_ticker",
            "events.get_events_by_ticker",
            "events.query_historical_events",
            "events.get_event_stats",
            "earnings.get_today_earnings",
            "earnings.get_upcoming_earnings",
            "earnings.get_earnings_by_ticker",
            "earnings.get_earnings_results",
            "sec.search_filings",
            "scanner.get_market_session",
        ],
        "orphans": [
            "news.get_catalyst_alerts",         # alertas de catalizadores activas
            "events.get_recent_events",         # eventos de mercado AHORA (sin ticker)
            "events.get_available_event_types", # catálogo de tipos de evento
            "earnings.get_earnings_by_date",    # earnings de una fecha concreta
        ],
    },
    "financial": {
        "used": [
            "financials.get_financial_statements",
            "sec.search_filings",
        ],
        "orphans": [
            "financials.get_income_statement",   # P&L aislado
            "financials.get_balance_sheet",      # balance aislado
            "financials.get_cash_flow",          # cash flow aislado
            "financials.get_segments",           # ingresos por segmento de negocio
            "financials.get_financial_ratios",   # ratios valoración/márgenes/salud
            "financials.get_key_stats",          # key stats + estimaciones forward
            "financials.get_adjusted_metrics",   # métricas ajustadas (non-GAAP)
            "sec.get_recent_filings",            # últimos filings (sin query)
            "sec.get_filing_detail",             # detalle/contenido de un filing
        ],
        # 2026-07-22: income/balance/cashflow estaban ROTAS EN ORIGEN (el
        # gateway apuntaba a financials:8020, que no implementa esas rutas).
        # El server MCP ahora sirve todo vía api_gateway /api/v1/financials/*
        # (mismo dataset que el frontend) e incluye ratios/key-stats/adjusted.
    },
    "dilution": {
        "used": [
            "dilution.get_instrument_context",
            "dilution.get_dilution_risk_ratings",
            "dilution.get_sec_dilution_profile",
            "dilution.get_dilution_analysis",
            "dilution.get_cash_runway",
            "dilution.get_cash_position",
            "dilution.get_warrants",
            "dilution.get_shares_history",
            "dilution.get_completed_offerings",
        ],
        "orphans": [
            "dilution.get_atm_offerings",        # ATMs activos/históricos
            "dilution.get_shelf_registrations",  # shelfs S-3 y capacidad restante
            "dilution.get_sec_filings",          # filings de dilución del ticker
            "dilution.get_enhanced_profile",     # perfil completo enriquecido
            "dilution.get_trending_dilution",    # tickers con dilución trending
        ],
    },
    "screener": {
        "used": [
            "screener.run_screen",
        ],
        "orphans": [
            "screener.get_available_filters",  # qué campos/filtros existen
            "screener.get_daily_indicators",   # indicadores diarios por ticker
            "screener.list_available_themes",  # catálogo de temáticas
        ],
    },
    "research": {
        # research trabaja con web/X search (fuera del gateway MCP); las
        # predictions (mercados de predicción) son su dominio natural:
        # probabilidad de eventos macro/catalizadores.
        "used": [],
        "orphans": [
            "predictions.get_prediction_events",
            "predictions.get_prediction_price_history",
        ],
    },
}

# Descripciones curadas para el selector (prompt determinista, sin depender
# del gateway en runtime). Completadas por agente al entrar al rollout.
TOOL_DESCS: dict[str, str] = {
    # ── financial (piloto Fase 3c) ──
    "financials.get_financial_statements": (
        "Full financial statements bundle (income + balance + cash flow) with "
        "margins, growth rates and FCF. Args: symbol, period (annual/quarter), limit. "
        "Best for complete fundamental analysis."
    ),
    "financials.get_income_statement": (
        "Income statement only: revenue, expenses, margins, growth. "
        "Prefer when the user asks ONLY about P&L/revenue/earnings."
    ),
    "financials.get_balance_sheet": (
        "Balance sheet only: assets, liabilities, equity, key ratios. "
        "Prefer when the user asks ONLY about balance/debt/cash position."
    ),
    "financials.get_cash_flow": (
        "Cash flow statement only: operating, investing, financing activities. "
        "Prefer when the user asks ONLY about cash flow / FCF."
    ),
    "financials.get_segments": (
        "Revenue breakdown by business segment (e.g. AWS vs retail for AMZN) "
        "plus company-specific KPIs. The ONLY tool that answers 'how does X "
        "split its revenue'."
    ),
    "financials.get_financial_ratios": (
        "Financial ratios by period: valuation, profitability margins, "
        "efficiency, financial health and growth rates. Prefer when the user "
        "asks about ratios, multiples, ROIC/ROE or financial health."
    ),
    "financials.get_key_stats": (
        "Key statistics per period including forward analyst estimates "
        "(revenue/EPS). The only financials tool with forward-looking data."
    ),
    "financials.get_adjusted_metrics": (
        "Adjusted (non-GAAP) metrics as reported by the company: adjusted "
        "EPS/EBITDA. Prefer when the user asks about adjusted figures."
    ),
    # ── dilution (rollout Fase 3c) ──
    "dilution.get_sec_dilution_profile": (
        "Full SEC dilution profile: every dilutive instrument (warrants, "
        "converts, ATM, shelf) with terms. The default overview tool."
    ),
    "dilution.get_instrument_context": (
        "Compact context: float, short interest, warrant/ATM/shelf capacity "
        "summary, baby-shelf flag. Good cheap companion for any dilution query."
    ),
    "dilution.get_dilution_risk_ratings": (
        "Risk scores 0-10: overall risk, offering ability, overhead supply, "
        "cash need. Prefer for 'how risky / rating' questions."
    ),
    "dilution.get_dilution_analysis": (
        "Quantified POTENTIAL dilution % if all instruments were exercised, "
        "broken down by type. Prefer for 'how much dilution could happen'."
    ),
    "dilution.get_cash_runway": (
        "Months of cash left, burn rate, projected depletion date. "
        "Prefer for runway/burn questions."
    ),
    "dilution.get_cash_position": (
        "Current cash position and recent capital raises."
    ),
    "dilution.get_warrants": (
        "Outstanding warrants with exercise prices and expirations. "
        "Prefer when the user asks specifically about warrants."
    ),
    "dilution.get_shares_history": (
        "Share count evolution over time — how much the company has already "
        "diluted holders."
    ),
    "dilution.get_completed_offerings": (
        "Past completed offerings: dates, amounts, banks."
    ),
    "dilution.get_atm_offerings": (
        "At-the-market (ATM) programs with total and REMAINING capacity. "
        "Prefer for 'does X have an active ATM / how much left'."
    ),
    "dilution.get_shelf_registrations": (
        "Shelf registrations (S-3/S-1) with remaining capacity and baby-shelf "
        "status. Prefer for shelf-specific questions."
    ),
    "dilution.get_sec_filings": (
        "Dilution-relevant SEC filings for one ticker, classified "
        "(offering/financial/ownership) with is_dilutive flags."
    ),
    "dilution.get_enhanced_profile": (
        "Everything at once: profile + dilution analysis + shares history + "
        "cash + risk flags. Heavy; prefer only for 'deep dive / todo sobre'."
    ),
    "dilution.get_trending_dilution": (
        "MARKET-WIDE: tickers ranked by recent dilutive filing activity. The "
        "ONLY tool that answers 'who is diluting now' — needs no ticker."
    ),
    "sec.search_filings": (
        "Search SEC filings with filters: ticker, form_type (8-K, 10-K, 10-Q, "
        "S-1...), date range. Returns filing metadata list."
    ),
    "sec.get_recent_filings": (
        "Latest SEC filings stream (optionally for one ticker), no query needed. "
        "Best for 'what has X filed lately'."
    ),
    "sec.get_filing_detail": (
        "Full detail/content of ONE filing by accession number. Use AFTER a "
        "search to open the most relevant filing and read what it announces."
    ),
    # ── news_events ──
    "earnings.get_earnings_results": (
        "Actual REPORTED earnings results for a day: who has ALREADY reported "
        "and how the numbers came in — EPS/revenue actual vs estimate, "
        "surprise % and price reaction, sorted server-side. Args: date, "
        "time_slot (amc/bmo), sort_by (surprise/mkt_cap/move), sort_order "
        "(desc/asc). sort_by='move' ranks reporters by their session price "
        "reaction — THE tool for 'top earnings movers after hours/premarket'; "
        "never answer that with a market-wide ranking. Prefer over the "
        "calendar tools when the user asks how results WERE, not who WILL "
        "report."
    ),
}


def roster_tools(agent: str) -> list[str]:
    """Roster completo (used + orphans) de un agente."""
    r = ROSTERS[agent]
    return list(r["used"]) + list(r["orphans"])


def all_roster_tools() -> set[str]:
    return {t for r in ROSTERS.values() for k in ("used", "orphans") for t in r[k]}
