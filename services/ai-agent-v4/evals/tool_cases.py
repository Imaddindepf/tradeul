"""
Casos curados de SELECCIÓN DE HERRAMIENTA por agente (gate de la Fase 3c).

Cada caso: un agente, una query (la sub-tarea que le llegaría del planner) y
aserciones sobre qué tools de SU roster debería elegir:

  - `tools_all`:  todas estas deben elegirse (⊆ selección).
  - `tools_any`:  al menos una de estas.
  - `tools_none`: ninguna de estas (guardas negativas).
  - `orphan_unlock`: marca informativa — el caso existe para demostrar que
    una tool hoy huérfana se elegiría si el agente pudiera verla.

Filosofía (igual que evals/cases.py): no sobre-especificar. El selector puede
añadir tools de más (over-fetch barato); lo que NO debe pasar es que falte la
tool imprescindible o que elija una absurda. Estos casos son el listón que el
tool-calling nativo de la Fase 3c tiene que superar ANTES del refactor.
"""

TOOL_CASES = [
    # ── market_data ──────────────────────────────────────────────
    {
        "id": "md_price_now",
        "agent": "market_data",
        "query": "¿A cuánto cotiza NVDA ahora mismo y cómo está su RSI?",
        "tools_any": ["scanner.get_enriched_ticker", "scanner.get_enriched_batch",
                      "analytics.get_technical_snapshot"],
        "tools_none": ["historical.get_top_movers", "patterns.find_similar_patterns"],
    },
    {
        "id": "md_rvol_orphan",
        "agent": "market_data",
        "query": "¿Qué RVOL llevan AAPL, TSLA y AMD en este momento?",
        "tools_any": ["analytics.get_rvol_batch", "analytics.get_rvol",
                      "scanner.get_enriched_batch"],
        "orphan_unlock": "analytics.get_rvol_batch",
    },
    {
        "id": "md_past_movers_orphan",
        "agent": "market_data",
        "query": "¿Cuáles fueron los mayores movers del 15 de julio?",
        "tools_all": ["historical.get_top_movers"],
        "tools_none": ["scanner.get_scanner_snapshot"],
        "orphan_unlock": "historical.get_top_movers",
    },
    {
        "id": "md_ranking_today",
        "agent": "market_data",
        "query": "Top 10 gappers de hoy en premarket",
        "tools_any": ["scanner.get_scanner_snapshot", "scanner.apply_dynamic_filter"],
        "tools_none": ["historical.get_top_movers"],
    },
    {
        "id": "md_volume_window_orphan",
        "agent": "market_data",
        "query": "¿Cuánto volumen ha hecho SMCI en los últimos 30 minutos vs su media?",
        "tools_any": ["analytics.get_volume_windows", "analytics.get_rvol"],
        "orphan_unlock": "analytics.get_volume_windows",
    },

    # ── news_events ──────────────────────────────────────────────
    {
        "id": "ne_ticker_news",
        "agent": "news_events",
        "query": "Últimas noticias de MARA",
        "tools_all": ["news.get_news_by_ticker"],
        "tools_none": ["earnings.get_today_earnings"],
    },
    {
        "id": "ne_market_events_now_orphan",
        "agent": "news_events",
        "query": "¿Qué eventos de mercado están saltando ahora mismo? (halts, breakouts, spikes)",
        "tools_any": ["events.get_recent_events"],
        "orphan_unlock": "events.get_recent_events",
    },
    {
        "id": "ne_catalyst_orphan",
        "agent": "news_events",
        "query": "¿Hay alertas de catalizadores activas en este momento?",
        "tools_any": ["news.get_catalyst_alerts", "events.get_recent_events"],
        "orphan_unlock": "news.get_catalyst_alerts",
    },
    {
        # 2026-07-27: get_earnings_by_date proxea al servicio benzinga
        # PARADO (entitlement revocado); la ruta viva para fechas pasadas es
        # get_earnings_results(date=...). Se retira el orphan_unlock: elegir
        # el tool vivo es lo correcto, no un fallo del selector.
        "id": "ne_earnings_date_orphan",
        "agent": "news_events",
        "query": "¿Quién presentó resultados el 18 de julio?",
        "tools_any": ["earnings.get_earnings_results"],
        "tools_none": ["earnings.get_today_earnings"],
    },
    {
        "id": "ne_earnings_results_amc",
        "agent": "news_events",
        "query": "¿Quién presentó resultados hoy after hours y cómo fueron? De mejor a peor",
        "tools_all": ["earnings.get_earnings_results"],
        "tools_none": ["earnings.get_upcoming_earnings"],
    },

    # ── financial ────────────────────────────────────────────────
    {
        "id": "fi_segments_orphan",
        "agent": "financial",
        "query": "¿Cómo se reparten los ingresos de AMZN por segmento de negocio?",
        "tools_any": ["financials.get_segments"],
        "orphan_unlock": "financials.get_segments",
    },
    {
        # 2026-07-22: get_cash_flow ya funciona (servida vía api_gateway);
        # tanto la tool aislada como el bundle son respuestas válidas.
        "id": "fi_cashflow",
        "agent": "financial",
        "query": "Enséñame el cash flow operativo de INTC de los últimos trimestres",
        "tools_any": ["financials.get_cash_flow", "financials.get_financial_statements"],
        "orphan_unlock": "financials.get_cash_flow",
    },
    {
        "id": "fi_income_orphan",
        "agent": "financial",
        "query": "¿Cuánto facturó MSFT el último año fiscal y cuál fue su beneficio neto?",
        "tools_any": ["financials.get_income_statement", "financials.get_financial_statements"],
        "orphan_unlock": "financials.get_income_statement",
    },
    {
        "id": "fi_balance_orphan",
        "agent": "financial",
        "query": "¿Cuánta deuda y cuánta caja tiene TSLA en su balance?",
        "tools_any": ["financials.get_balance_sheet", "financials.get_financial_statements"],
        "orphan_unlock": "financials.get_balance_sheet",
    },
    {
        "id": "fi_ratios_orphan",
        "agent": "financial",
        "query": "¿Qué ROIC y ROE tiene NVDA y cómo está de liquidez?",
        "tools_any": ["financials.get_financial_ratios"],
        "orphan_unlock": "financials.get_financial_ratios",
    },
    {
        "id": "fi_keystats_orphan",
        "agent": "financial",
        "query": "¿Qué EPS estiman los analistas para AAPL el año que viene?",
        "tools_any": ["financials.get_key_stats"],
        "orphan_unlock": "financials.get_key_stats",
    },
    {
        "id": "fi_adjusted_orphan",
        "agent": "financial",
        "query": "Dame el EBITDA ajustado (non-GAAP) que reporta PLTR",
        "tools_any": ["financials.get_adjusted_metrics"],
        "orphan_unlock": "financials.get_adjusted_metrics",
    },
    {
        "id": "fi_filing_detail_orphan",
        "agent": "financial",
        "query": "Ábreme el último 8-K de NVAX y dime qué anuncia",
        "tools_any": ["sec.get_filing_detail", "sec.get_recent_filings", "sec.search_filings"],
        "orphan_unlock": "sec.get_filing_detail",
    },
    {
        "id": "fi_statements_bundle",
        "agent": "financial",
        "query": "Análisis financiero completo de AAPL: income, balance y ratios",
        "tools_any": ["financials.get_financial_statements"],
    },

    # ── dilution ─────────────────────────────────────────────────
    {
        "id": "di_atm_orphan",
        "agent": "dilution",
        "query": "¿Tiene MULN un ATM activo y cuánto le queda por colocar?",
        "tools_any": ["dilution.get_atm_offerings", "dilution.get_instrument_context"],
        "orphan_unlock": "dilution.get_atm_offerings",
    },
    {
        "id": "di_shelf_orphan",
        "agent": "dilution",
        "query": "¿Qué shelfs S-3 tiene registrados GNS y cuánta capacidad le queda?",
        "tools_any": ["dilution.get_shelf_registrations", "dilution.get_sec_dilution_profile"],
        "orphan_unlock": "dilution.get_shelf_registrations",
    },
    {
        "id": "di_trending_orphan",
        "agent": "dilution",
        "query": "¿Qué tickers están ahora mismo con más actividad de dilución?",
        "tools_any": ["dilution.get_trending_dilution"],
        "tools_none": ["dilution.get_cash_runway"],
        "orphan_unlock": "dilution.get_trending_dilution",
    },
    {
        "id": "di_runway_core",
        "agent": "dilution",
        "query": "¿Cuánta caja le queda a NVAX y para cuántos meses?",
        "tools_any": ["dilution.get_cash_runway", "dilution.get_cash_position"],
        "tools_none": ["dilution.get_trending_dilution"],
    },
    {
        "id": "di_filings_orphan",
        "agent": "dilution",
        "query": "Lístame los últimos filings de dilución de NVAX y dime cuáles son dilutivos",
        "tools_any": ["dilution.get_sec_filings"],
        "orphan_unlock": "dilution.get_sec_filings",
    },
    {
        "id": "di_enhanced_orphan",
        "agent": "dilution",
        "query": "Deep dive completo de la dilución de GNS: perfil, instrumentos, historial, caja y riesgo, todo",
        "tools_any": ["dilution.get_enhanced_profile", "dilution.get_sec_dilution_profile"],
        "orphan_unlock": "dilution.get_enhanced_profile",
    },

    # ── screener ─────────────────────────────────────────────────
    {
        "id": "sc_run_screen_core",
        "agent": "screener",
        "query": "Acciones bajo 10$ con RVOL > 2 y market cap < 500M",
        "tools_all": ["screener.run_screen"],
    },
    {
        "id": "sc_filters_orphan",
        "agent": "screener",
        "query": "¿Por qué campos puedo filtrar? ¿Se puede filtrar por gap % y por float?",
        "tools_any": ["screener.get_available_filters"],
        "tools_none": ["screener.run_screen"],
        "orphan_unlock": "screener.get_available_filters",
    },
    {
        "id": "sc_themes_orphan",
        "agent": "screener",
        "query": "¿Qué temáticas de inversión tenéis catalogadas?",
        "tools_any": ["screener.list_available_themes"],
        "orphan_unlock": "screener.list_available_themes",
    },

    # ── research ─────────────────────────────────────────────────
    {
        "id": "re_prediction_orphan",
        "agent": "research",
        "query": "¿Qué probabilidad dan los mercados de predicción a una bajada de tipos de la Fed en septiembre?",
        "tools_any": ["predictions.get_prediction_events"],
        "orphan_unlock": "predictions.get_prediction_events",
    },
    {
        "id": "re_prediction_history_orphan",
        "agent": "research",
        "query": "¿Cómo ha evolucionado esa probabilidad de bajada de tipos en el último mes?",
        "tools_any": ["predictions.get_prediction_price_history"],
        "orphan_unlock": "predictions.get_prediction_price_history",
    },
]
