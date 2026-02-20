"""
Query Planner (Supervisor V3) — Intent-first parallel query routing.

Prompt engineering standards applied (2025-2026):
  - Gemini native JSON output (response_mime_type: application/json)
  - Intent classification BEFORE agent routing (MasRouter pattern)
  - Few-shot examples (8 diverse intent types)
  - XML-structured prompt sections (OpenAI/Anthropic best practice)
  - Positive instruction framing (avoid negations)
  - PTCF framework: Persona · Task · Context · Format (Google)
  - max_output_tokens raised to 1024 (avoid truncation)

Architecture:
  Single LLM call → classify intent → extract tickers → select agents
  Graph fans out to all selected agents in parallel via Send().
"""
import json
import logging
import re
from typing import Any

from agents._mcp_tools import call_mcp_tool
from agents._ticker_utils import get_ticker_info, validate_tickers
from agents._llm_retry import llm_invoke_with_retry

logger = logging.getLogger(__name__)

_llm = None

# ── Agent registry (intent-focused descriptions) ─────────────────

AVAILABLE_AGENTS = {
    "market_data": (
        "Real-time price data, enriched snapshots (145+ indicators), "
        "scanner rankings (winners, losers, gappers, momentum, volume, halts), "
        "historical daily/minute bars. "
        "Capabilities: current quotes, technicals, top movers, price history, OHLCV data."
    ),
    "news_events": (
        "Benzinga financial news, real-time market events (85+ types: breakouts, VWAP crosses, "
        "halts, volume spikes, momentum shifts), historical events (TimescaleDB, 60-day retention), "
        "earnings calendar with EPS/revenue estimates. "
        "Capabilities: ticker news, market headlines, event history by date, earnings calendar."
    ),
    "financial": (
        "Fundamental data: income statements, balance sheets, cash flow, SEC filings. "
        "Capabilities: quarterly/annual financials, SEC 10-K/10-Q/8-K, EPS history, ratios."
    ),
    "research": (
        "Real-time web and X.com search via Grok, or Gemini Pro fallback. "
        "Searches social media posts, analyst commentary, breaking rumors, and web articles IN REAL TIME. "
        "This is the ONLY agent that can explain WHY a stock is moving — "
        "it finds catalysts, rumors, and breaking info not yet in structured feeds. "
        "Capabilities: why a stock moves, social sentiment, analyst opinions, real-time catalysts."
    ),
    "code_exec": (
        "Python/DuckDB code generation for custom analysis. "
        "Capabilities: backtesting, custom calculations, data transformations, comparisons."
    ),
    "screener": (
        "DuckDB-powered stock screener on daily data with 60+ indicators. "
        "Translates natural language criteria into database filters. "
        "Capabilities: find stocks matching specific numeric criteria (RSI, volume, market cap, sector)."
    ),
}

SCANNER_CATEGORIES = [
    "gappers_up", "gappers_down", "momentum_up", "momentum_down",
    "high_volume", "winners", "losers", "reversals", "anomalies",
    "new_highs", "new_lows", "post_market", "halts",
]

# ── Prompt builder ────────────────────────────────────────────────


def _build_system_prompt(agents_desc: str, market_context: str, scanner_cats: str) -> str:
    """Build the structured system prompt with XML sections and few-shot examples.

    Uses f-string with doubled braces for literal JSON in examples.
    """
    return f"""<role>
You are the senior query router for Tradeul, a professional stock trading intelligence platform serving day traders and institutional analysts. You have deep expertise in financial markets, trading terminology in both English and Spanish, and precise information routing. Your routing decisions directly determine the quality of answers for thousands of active traders.
</role>

<task>
For each user query, follow these steps in order:
1. Classify the user's INTENT — what type of answer do they need?
2. Extract any ticker symbols mentioned or implied in the query.
3. Select ALL specialist agents required to FULLY answer the question.
All selected agents execute IN PARALLEL — select every needed agent at once.
</task>

<agents>
{agents_desc}
</agents>

<context>
Market session: {market_context}
Scanner categories: {scanner_cats}
</context>

<date_format_awareness>
The user message starts with [Language: XX]. Use this to parse ambiguous dates:
- Language: es (Spanish) → dates are DD/MM/YYYY. "07/01/2026" = January 7, 2026.
- Language: en (English) → dates are MM/DD/YYYY. "07/01/2026" = July 1, 2026.
When you output dates (in "plan" or elsewhere), ALWAYS use ISO format YYYY-MM-DD to avoid ambiguity.
</date_format_awareness>

<intent_types>
Classify the query into one or more of these intent types, then route to the corresponding agents:

GREETING — Non-financial message (hello, thanks, who are you, ok, ninguna) → no agents
DATA_LOOKUP — Current price, volume, technicals for specific tickers → market_data
RANKING — Top/bottom lists: gainers, losers, gappers, halts, volume leaders → market_data
MARKET_PULSE — Broad market analysis: "what sectors are leading?", "que temas dominan en big caps?", "compare sectors", "market regime", "risk-on or risk-off?", "que industria tiene mejor breadth?", "temas oversold con momentum", "rotacion sectorial". Any question about SECTOR/INDUSTRY/THEME PERFORMANCE as aggregated groups (not individual stocks). → market_data. You MUST populate "pulse_queries" with a structured analytical spec (see pulse_query_format below).
CAUSAL — WHY something is happening: "why is X up/down/moving?", "por qué sube/baja X?", "what's driving X?", "what caused X to spike?" → research + news_events + market_data
NEWS — Recent news, headlines, "what happened with X" → news_events
EVENTS — Market events by date: breakouts, halts, VWAP crosses on a given day → news_events
EARNINGS_CALENDAR — Upcoming earnings dates, "who reports this week" → news_events
EARNINGS_HISTORY — Past EPS, revenue, quarterly results for a ticker → financial
FUNDAMENTALS — Financial statements, balance sheets, ratios → financial
SEC_FILINGS — SEC documents: 10-K, 10-Q, 8-K, S-1 → financial
SCREENING — Filter stocks by specific numeric criteria (without ranking) → screener
THEMATIC — Find stocks by investment theme, sector vertical, or industry category. The user is explicitly looking for a LIST of companies in a specific theme. Examples: "robotics stocks", "empresas de memoria", "quantum computing companies", "acciones de energía nuclear", "cybersecurity zero trust", "EV charging", "GLP-1 weight loss drugs", "chip foundry stocks", "defense tech", "lithium miners" → market_data. IMPORTANT: Broad market questions like "what theme is driving the market today?", "que tema mueve el mercado?", "what sectors are hot?" are NOT THEMATIC — they are RANKING queries because the user wants to see current market movers, not a static list of themed companies.
DEEP_RESEARCH — Comprehensive analysis, sentiment, analyst opinions → research
COMPLETE_ANALYSIS — Full picture: "análisis completo", "deep dive", "full breakdown" → market_data + news_events + financial (add research if sentiment/opinions requested)
CODE — Custom calculations, backtesting → code_exec
CHART_ANALYSIS — User is asking about a specific chart they are viewing (technical analysis, patterns, support/resistance, trend) → market_data (add research if "why" is asked, add news_events for context)

A single query can combine MULTIPLE intents — select agents for ALL detected intents.
Example: "Why is TSLA up? Show me the financials too" = CAUSAL + FUNDAMENTALS → research + news_events + market_data + financial
</intent_types>

<routing_principles>
1. CAUSAL queries (why, por qué, what's causing, what's driving, what triggered) ALWAYS include the research agent. It is the ONLY agent that searches X.com and the web in real time for catalysts and breaking information. Without it, causal questions cannot be answered.

2. When a query mentions a specific ticker, include market_data alongside other agents to provide current price context.

3. RANKING queries use market_data with the appropriate scanner category. The screener agent is only for custom numeric filtering without a ranking.

4. For COMPLETE_ANALYSIS, select at least market_data + news_events + financial. Add research when the user mentions sentiment, opinions, research, or "con sentimiento".

5. THEMATIC queries ask for stocks by theme, sector, or industry vertical. Route to market_data ONLY — it resolves themes via the classification database (124 pre-computed themes, no LLM needed at query time). You MUST populate the "theme_tags" field with canonical tags from the thematic catalog below. Map the user's natural language to one or more canonical tags. Examples: "robótica" → ["robotics"], "chips de memoria" → ["memory_chips"], "IA generativa" → ["generative_ai"], "cybersecurity zero trust" → ["cybersecurity", "identity_zero_trust"].

6. Write the plan field in the same language the user used in their query.

7. CHART_ANALYSIS queries come with a chart_context containing the user's visible chart data (OHLCV bars, indicators, drawings). Always include market_data for enrichment. Add research if the user asks "why" something happened.

8. MARKET_PULSE queries analyze aggregated sector/industry/theme performance. You MUST generate "pulse_queries" — an array of structured query objects. Each query: {{"group": "sectors"|"industries"|"themes", "sort_by": metric, "limit": int, "cap_size": "mega"|"large"|"mid"|"small"|null, "min_market_cap": int|null, "sector": str|null, "include_movers": bool, "metric_filters": [{{"metric":str,"op":"gt|gte|lt|lte","value":float}}], "label": str}}. Set "pulse_compare": true when comparing segments. Set "pulse_drilldown": {{"from_query":0,"rank":1,"sort_by":"change_percent","limit":10}} to drill into a result. Sortable metrics: weighted_change, avg_change, breadth, avg_rvol, avg_rsi, avg_daily_rsi, avg_atr_pct, avg_change_5d, avg_change_10d, avg_change_20d, avg_from_52w_high, avg_from_52w_low, avg_pos_in_range, avg_bb_position, avg_dist_vwap, avg_dist_sma20, avg_dist_sma50, total_dollar_volume, count. Cap sizes: mega(>200B), large(>10B), mid(>2B), small(>300M), micro(>50M).
</routing_principles>

<thematic_catalog>
When intent is THEMATIC, you MUST set "theme_tags" to one or more of these canonical tags:

SEMICONDUCTORS: semiconductors, semiconductor_equipment, memory_chips, gpu_accelerators, cpu_processors, analog_mixed_signal, networking_chips, rf_wireless_chips, chip_foundry, power_semiconductors, eda_chip_design
AI & SOFTWARE: artificial_intelligence, generative_ai, machine_learning, data_infrastructure, cloud_computing, edge_computing, saas, enterprise_software, crm_marketing_tech, developer_tools, big_data_analytics, cybersecurity, identity_zero_trust, endpoint_network_security, ar_vr
CONNECTIVITY: 5g_iot, satellite_internet, fiber_optics
ROBOTICS: robotics, surgical_robotics, industrial_automation, autonomous_vehicles, lidar, drones, 3d_printing
FRONTIER: quantum_computing, blockchain_crypto, crypto_exchange, space_technology
FINTECH: fintech, digital_payments, buy_now_pay_later, neobanking, insurtech, lending_platforms, wealthtech, payroll_hr_tech, online_gambling
BIOTECH & PHARMA: biotech, genomics, gene_editing_crispr, mrna_therapeutics, cell_gene_therapy, immunotherapy, oncology, glp1_weight_loss, diabetes, neuroscience, cardiovascular, rare_disease, vaccines, psychedelics, cannabis
MEDTECH: digital_health, telehealth, medical_devices, diagnostics, medical_imaging, dental, animal_health, cro_cdmo, aging_population
OIL & GAS: oil_exploration, oil_refining, oil_services, midstream_pipelines, natural_gas
CLEAN ENERGY: clean_energy, solar, wind, nuclear_energy, uranium, hydrogen_fuel_cells, battery_storage, lithium, carbon_capture, smart_grid
TRANSPORTATION: electric_vehicles, ev_charging, ride_sharing, shipping, rails_freight, airlines
MINING: gold_mining, silver_mining, copper, rare_earths, steel, aluminum, agriculture_agtech
CONSUMER DIGITAL: e_commerce, social_media, streaming, esports_gaming, food_delivery, education_tech
CONSUMER LIFESTYLE: travel_tech, gig_economy, luxury_brands, restaurant_tech, pet_economy, athleisure_wellness
DEFENSE: defense_contractors, defense_tech, commercial_aerospace, hypersonics_missiles, border_surveillance
INFRASTRUCTURE: construction_engineering, water_treatment, waste_management
REAL ESTATE: data_center_reits, cell_tower_reits, healthcare_reits
</thematic_catalog>

<ticker_extraction>
Extract valid US stock ticker symbols (1-5 uppercase letters):
- Map company names: "tesla" → TSLA, "apple" → AAPL, "nvidia" → NVDA, "palantir" → PLTR
- Accept any format: $TSLA, TSLA, tsla, Tesla
- Abbreviations that are organizations/concepts, not tickers: SEC, CEO, CFO, IPO, ETF, GDP, CPI, FDA, EPS, RSI, AI, ER, ATR, MACD, VWAP, BB
- Spanish words that are not tickers: HA (ha hecho), SI (si puede), DE, LA, EL, ES, UN, MAS, POR, QUE
- Return an empty array when no specific stock is referenced
</ticker_extraction>

<confidence_scoring>
Rate your confidence from 0.0 to 1.0:
- 0.9–1.0: Clear intent, obvious routing
- 0.7–0.89: Clear intent, minor ambiguity
- 0.5–0.69: Ambiguous query — provide 2-3 clarification options
- Below 0.5: Very unclear — provide clarification options

When confidence < 0.65, include a "clarification" object with a message and 2-3 options. Each option has a "label" and a "rewrite" (unambiguous rewritten query).
</confidence_scoring>

<output_format>
Respond with ONLY a JSON object containing these exact fields:
{{
  "intent": "PRIMARY_INTENT_TYPE",
  "tickers": ["TICKER1", "TICKER2"],
  "agents": ["agent1", "agent2"],
  "theme_tags": [],
  "pulse_queries": null,
  "pulse_compare": false,
  "pulse_metrics": null,
  "pulse_drilldown": null,
  "plan": "Brief execution plan in the user's language",
  "confidence": 0.95,
  "reasoning": "One sentence explaining why you chose these agents",
  "clarification": null
}}

IMPORTANT: "theme_tags" is an array of canonical theme tag strings from the thematic catalog. 
It MUST be populated when intent is THEMATIC. Leave as empty array [] for all other intents.

IMPORTANT: "pulse_queries" MUST be populated when intent is MARKET_PULSE. It is an array of query objects for the composable market analysis tool. Leave as null for all other intents.
</output_format>

<examples>
User: "hola buenos días"
{{"intent": "GREETING", "tickers": [], "agents": [], "theme_tags": [], "plan": "Saludo — responder conversacionalmente", "confidence": 1.0, "reasoning": "Non-financial greeting in Spanish", "clarification": null}}

User: "NVDA price"
{{"intent": "DATA_LOOKUP", "tickers": ["NVDA"], "agents": ["market_data"], "theme_tags": [], "plan": "Fetch current NVDA price and technicals", "confidence": 1.0, "reasoning": "Simple price lookup for a specific ticker", "clarification": null}}

User: "why is LFS moving?"
{{"intent": "CAUSAL", "tickers": ["LFS"], "agents": ["research", "news_events", "market_data"], "theme_tags": [], "plan": "Investigate why LFS is moving: search X.com/web for catalysts, check news, get price data", "confidence": 0.95, "reasoning": "Causal query — research agent searches real-time sources for the reason behind the move", "clarification": null}}

User: "top 20 gappers"
{{"intent": "RANKING", "tickers": [], "agents": ["market_data"], "theme_tags": [], "plan": "Fetch top 20 gappers from scanner", "confidence": 1.0, "reasoning": "Ranking query for gappers_up scanner category", "clarification": null}}

User: "stocks con RSI menor a 30 y volumen mayor a 1M"
{{"intent": "SCREENING", "tickers": [], "agents": ["screener"], "theme_tags": [], "plan": "Screener: filtrar acciones con RSI < 30 y volumen > 1M", "confidence": 1.0, "reasoning": "Numeric criteria screening without ranking implied", "clarification": null}}

User: "top 10 robotics stocks"
{{"intent": "THEMATIC", "tickers": [], "agents": ["market_data"], "theme_tags": ["robotics"], "plan": "Find top 10 robotics companies by theme classification and enrich with live market data", "confidence": 1.0, "reasoning": "Thematic query — resolve via classification database then enrich with market data", "clarification": null}}

User: "empresas de chips de memoria"
{{"intent": "THEMATIC", "tickers": [], "agents": ["market_data"], "theme_tags": ["memory_chips"], "plan": "Buscar empresas de semiconductores de memoria via clasificación temática", "confidence": 1.0, "reasoning": "Thematic query for memory semiconductor companies", "clarification": null}}

User: "cybersecurity companies focused on zero trust"
{{"intent": "THEMATIC", "tickers": [], "agents": ["market_data"], "theme_tags": ["cybersecurity", "identity_zero_trust"], "plan": "Find cybersecurity companies with zero-trust focus via thematic classification", "confidence": 1.0, "reasoning": "Multi-theme thematic query — combining cybersecurity + identity_zero_trust", "clarification": null}}

User: "acciones de energía nuclear y uranio"
{{"intent": "THEMATIC", "tickers": [], "agents": ["market_data"], "theme_tags": ["nuclear_energy", "uranium"], "plan": "Buscar acciones de energía nuclear y mineras de uranio", "confidence": 1.0, "reasoning": "Thematic query for nuclear energy and uranium mining stocks", "clarification": null}}

User: "que tema está moviendo el mercado hoy?"
{{"intent": "MARKET_PULSE", "tickers": [], "agents": ["market_data"], "theme_tags": [], "pulse_queries": [{{"group": "themes", "sort_by": "weighted_change", "limit": 10, "include_movers": true, "label": "top_themes"}}, {{"group": "sectors", "sort_by": "weighted_change", "limit": 11, "label": "sectors"}}], "pulse_compare": false, "pulse_metrics": ["weighted_change", "breadth", "avg_rvol", "count"], "pulse_drilldown": null, "plan": "Analizar qué temas y sectores lideran el mercado hoy", "confidence": 1.0, "reasoning": "Market pulse query — aggregated theme/sector performance analysis", "clarification": null}}

User: "what sectors are hot right now?"
{{"intent": "MARKET_PULSE", "tickers": [], "agents": ["market_data"], "theme_tags": [], "pulse_queries": [{{"group": "sectors", "sort_by": "weighted_change", "limit": 11, "include_movers": true, "label": "sectors"}}], "pulse_compare": false, "pulse_metrics": ["weighted_change", "breadth", "avg_rvol", "avg_change_5d"], "pulse_drilldown": null, "plan": "Show sector performance ranked by weighted change", "confidence": 1.0, "reasoning": "Market pulse query — sector performance analysis", "clarification": null}}

User: "que temas dominan en big caps vs small caps?"
{{"intent": "MARKET_PULSE", "tickers": [], "agents": ["market_data"], "theme_tags": [], "pulse_queries": [{{"group": "themes", "cap_size": "large", "sort_by": "weighted_change", "limit": 10, "label": "big_caps"}}, {{"group": "themes", "cap_size": "small", "sort_by": "weighted_change", "limit": 10, "label": "small_caps"}}], "pulse_compare": true, "pulse_metrics": ["weighted_change", "breadth", "avg_rvol", "count"], "pulse_drilldown": null, "plan": "Comparar temas dominantes en big caps vs small caps", "confidence": 1.0, "reasoning": "Market pulse comparison — big cap vs small cap theme dominance", "clarification": null}}

User: "temas con RSI oversold y momentum positivo en 5 dias"
{{"intent": "MARKET_PULSE", "tickers": [], "agents": ["market_data"], "theme_tags": [], "pulse_queries": [{{"group": "themes", "sort_by": "avg_change_5d", "limit": 15, "metric_filters": [{{"metric": "avg_daily_rsi", "op": "lt", "value": 40}}, {{"metric": "avg_change_5d", "op": "gt", "value": 0}}], "label": "oversold_momentum"}}], "pulse_compare": false, "pulse_metrics": ["weighted_change", "avg_daily_rsi", "avg_change_5d", "breadth", "avg_rvol"], "pulse_drilldown": null, "plan": "Buscar temas oversold con momentum positivo semanal", "confidence": 1.0, "reasoning": "Market pulse with conditional screening on theme-level metrics", "clarification": null}}

User: "top tema en large caps y dame los 5 mejores stocks de ese tema"
{{"intent": "MARKET_PULSE", "tickers": [], "agents": ["market_data"], "theme_tags": [], "pulse_queries": [{{"group": "themes", "cap_size": "large", "sort_by": "weighted_change", "limit": 5, "label": "top_themes"}}], "pulse_compare": false, "pulse_metrics": null, "pulse_drilldown": {{"from_query": 0, "rank": 1, "sort_by": "change_percent", "limit": 5}}, "plan": "Tema más fuerte en large caps con drilldown a sus mejores stocks", "confidence": 1.0, "reasoning": "Market pulse with automatic drilldown into top result", "clarification": null}}

User: "noticias de AAPL"
{{"intent": "NEWS", "tickers": ["AAPL"], "agents": ["news_events", "market_data"], "theme_tags": [], "plan": "Obtener noticias recientes de AAPL con contexto de precio", "confidence": 1.0, "reasoning": "News query for specific ticker with price context", "clarification": null}}

User: "análisis completo de PLTR con sentimiento"
{{"intent": "COMPLETE_ANALYSIS", "tickers": ["PLTR"], "agents": ["market_data", "news_events", "financial", "research"], "theme_tags": [], "plan": "Análisis completo de PLTR: precio, noticias, fundamentales y sentimiento via X.com", "confidence": 0.95, "reasoning": "Complete analysis with sentiment requested — needs all four agents", "clarification": null}}

User: "ninguna"
{{"intent": "GREETING", "tickers": [], "agents": [], "theme_tags": [], "plan": "Dismissal — responder brevemente", "confidence": 1.0, "reasoning": "User dismissal, not a financial query", "clarification": null}}

User: "Full technical analysis of TSLA chart" [chart_context attached]
{{"intent": "CHART_ANALYSIS", "tickers": ["TSLA"], "agents": ["market_data", "news_events"], "theme_tags": [], "plan": "Analyze TSLA chart: read visible bars/indicators from chart context, enrich with current data and recent news", "confidence": 1.0, "reasoning": "Chart analysis with chart_context — market_data for enrichment, news for context", "clarification": null}}

User: "Why did NVDA move like this on 2025-12-15?" [chart_context attached]
{{"intent": "CHART_ANALYSIS", "tickers": ["NVDA"], "agents": ["market_data", "news_events", "research"], "theme_tags": [], "plan": "Analyze NVDA chart candle movement: search for catalysts on that date via research, check news, get price context", "confidence": 0.95, "reasoning": "Chart analysis with causal why — needs research agent for catalyst discovery", "clarification": null}}
</examples>"""


# ── LLM singleton ─────────────────────────────────────────────────

def _get_llm():
    global _llm
    if _llm is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.0,
            max_output_tokens=1024,
            response_mime_type="application/json",
        )
    return _llm


def _build_agents_desc() -> str:
    return "\n".join(f"- {name}: {desc}" for name, desc in AVAILABLE_AGENTS.items())


# ── Market context helper ─────────────────────────────────────────

async def _get_market_context_str(state: dict) -> str:
    mc = state.get("market_context", {})
    if mc and mc.get("current_session"):
        session = mc.get("current_session", "UNKNOWN")
        is_trading = mc.get("is_trading_day", True)
        return (
            f"Session: {session}, Trading day: {is_trading}. "
            f"When market is CLOSED, last-session data is available via last_close snapshots."
        )

    try:
        session_data = await call_mcp_tool("scanner", "get_market_session", {})
        if isinstance(session_data, dict) and "error" not in session_data:
            session = session_data.get("current_session", "UNKNOWN")
            is_trading = session_data.get("is_trading_day", True)
            trading_date = session_data.get("trading_date", "unknown")
            return (
                f"Session: {session}, Date: {trading_date}, Trading day: {is_trading}. "
                f"When CLOSED, last-session data is available."
            )
    except Exception as e:
        logger.warning("Failed to get market session: %s", e)

    return "Session: UNKNOWN. Assume last-session data is available."


_NUMERIC_DATE_RE = re.compile(r'\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b')


def _normalize_dates_to_iso(text: str, language: str) -> str:
    """Convert numeric dates in text to unambiguous ISO YYYY-MM-DD format.

    Spanish (es): DD/MM/YYYY → YYYY-MM-DD
    English (en): MM/DD/YYYY → YYYY-MM-DD
    Already ISO (YYYY-MM-DD): left unchanged.
    """
    def _replace(m: re.Match) -> str:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            return m.group(0)
        if language == "es":
            d, mo = a, b
        else:
            mo, d = a, b
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            d, mo = mo, d
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            return m.group(0)
        return f"{y:04d}-{mo:02d}-{d:02d}"

    return _NUMERIC_DATE_RE.sub(_replace, text)


# ── Main planner node ─────────────────────────────────────────────

async def query_planner_node(state: dict) -> dict:
    """Classify intent, extract tickers, and select ALL agents for parallel execution.

    Steps:
      1. Build structured system prompt with XML sections + few-shot examples
      2. Invoke Gemini with native JSON output (response_mime_type)
      3. Validate tickers against Redis universe
      4. Return routing decision or clarification request
    """
    query = state.get("query", "")
    language = state.get("language", "en")

    agents_desc = _build_agents_desc()
    market_context = await _get_market_context_str(state)
    scanner_cats = ", ".join(SCANNER_CATEGORIES)

    system_prompt = _build_system_prompt(agents_desc, market_context, scanner_cats)

    # ── CHART_ANALYSIS fast-path: deterministic routing when chart_context is present ──
    chart_context = state.get("chart_context")
    if chart_context:
        cc = chart_context
        snap = cc.get("snapshot", {})
        ticker = cc.get("ticker", "")
        is_hist = snap.get("isHistorical", False)
        has_why = any(kw in query.lower() for kw in ["why", "por qué", "por que", "what caused", "what's driving"])

        has_target_candle = bool(cc.get("targetCandle"))
        agents = ["market_data", "news_events"]
        if has_why or has_target_candle:
            agents.append("research")

        visible_range = snap.get("visibleDateRange", {})
        from_date = visible_range.get("from", 0)
        to_date = visible_range.get("to", 0)
        from_str = __import__("datetime").datetime.utcfromtimestamp(from_date).strftime("%Y-%m-%d") if from_date else "?"
        to_str = __import__("datetime").datetime.utcfromtimestamp(to_date).strftime("%Y-%m-%d") if to_date else "?"

        plan = (
            f"Chart analysis: {ticker} {cc.get('interval', '?')} "
            f"visible range {from_str} to {to_str} "
            f"({'HISTORICAL view' if is_hist else 'current view'}) — "
            f"analyze {len(snap.get('recentBars', []))} visible bars, "
            f"indicators, user-drawn levels"
        )

        logger.info(
            "Query planner: CHART_ANALYSIS (deterministic) ticker=%s interval=%s historical=%s range=%s→%s agents=%s",
            ticker, cc.get("interval"), is_hist, from_str, to_str, agents,
        )

        llm_tickers = [ticker] if ticker else []
        ticker_info: dict = {}
        if llm_tickers:
            validated = await validate_tickers(llm_tickers)
            llm_tickers = validated
            if llm_tickers:
                ticker_info = await get_ticker_info(llm_tickers)

        return {
            **state,
            "tickers": llm_tickers,
            "ticker_info": ticker_info,
            "active_agents": agents,
            "plan": plan,
            "clarification": None,
            "market_context": state.get("market_context", {}),
        }

    # ── Standard LLM-based routing ──
    user_content = f"[Language: {language}] {query}"

    llm = _get_llm()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    try:
        response = await llm_invoke_with_retry(llm, messages)
        raw = response.content.strip()

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        decision = json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Query planner parse error: %s — raw: %s", e, raw if "raw" in dir() else "N/A")
        decision = {
            "intent": "FALLBACK",
            "tickers": [],
            "plan": "Fallback: routing to market_data due to parse error",
            "agents": ["market_data"],
            "confidence": 0.5,
            "reasoning": f"LLM output could not be parsed: {e}",
        }

    # ── Clarification handling ──
    confidence = decision.get("confidence", 1.0)
    clarification = decision.get("clarification")
    clarification_hint = state.get("clarification_hint", "")

    # Re-execution after user chose a clarification option → skip confidence check
    if clarification_hint:
        confidence = 1.0
        clarification = None

    if confidence < 0.65 and clarification and isinstance(clarification, dict):
        logger.info(
            "Query planner: LOW CONFIDENCE (%.2f) [intent=%s], requesting clarification",
            confidence, decision.get("intent", "?"),
        )
        return {
            **state,
            "tickers": [],
            "active_agents": [],
            "plan": "clarification_needed",
            "clarification": clarification,
            "market_context": state.get("market_context", {}),
        }

    # ── Ticker validation + metadata ──
    llm_tickers = decision.get("tickers", [])
    ticker_info: dict = {}
    if llm_tickers:
        validated_tickers = await validate_tickers(llm_tickers)
        rejected = set(llm_tickers) - set(validated_tickers)
        if rejected:
            logger.info("Planner: rejected tickers %s (not in universe)", rejected)
        llm_tickers = validated_tickers

        # Fetch company metadata so downstream agents know the exact company
        if llm_tickers:
            ticker_info = await get_ticker_info(llm_tickers)
            if ticker_info:
                names = {t: info.get("company_name", "?") for t, info in ticker_info.items()}
                logger.info("Planner: ticker metadata loaded: %s", names)

    requested_agents = [a for a in decision.get("agents", []) if a in AVAILABLE_AGENTS]
    theme_tags = decision.get("theme_tags", [])
    if theme_tags:
        theme_tags = [t.strip() for t in theme_tags if isinstance(t, str) and t.strip()]

    # Market Pulse structured queries
    pulse_queries = decision.get("pulse_queries")
    pulse_compare = decision.get("pulse_compare", False)
    pulse_metrics = decision.get("pulse_metrics")
    pulse_drilldown = decision.get("pulse_drilldown")

    logger.info(
        "Query planner: intent=%s confidence=%.2f tickers=%s agents=%s themes=%s pulse=%s plan=%s",
        decision.get("intent", "?"), confidence, llm_tickers,
        requested_agents, theme_tags,
        bool(pulse_queries), decision.get("plan", "")[:120],
    )

    result_state = {
        **state,
        "tickers": llm_tickers,
        "ticker_info": ticker_info,
        "active_agents": requested_agents,
        "theme_tags": theme_tags,
        "plan": decision.get("plan", ""),
        "clarification": None,
        "market_context": state.get("market_context", {}),
    }

    if pulse_queries and isinstance(pulse_queries, list):
        result_state["pulse_queries"] = pulse_queries
        result_state["pulse_compare"] = pulse_compare
        if pulse_metrics:
            result_state["pulse_metrics"] = pulse_metrics
        if pulse_drilldown:
            result_state["pulse_drilldown"] = pulse_drilldown

    return result_state


# ── Fan-out edge function ─────────────────────────────────────────

def fan_out_to_agents(state: dict):
    """Conditional edge: fan-out to all active agents in parallel via Send().

    Returns a list of Send() objects for parallel execution,
    routes directly to synthesizer if no agents needed,
    or routes to END if clarification is requested.
    """
    from langgraph.types import Send

    if state.get("clarification") and state.get("plan") == "clarification_needed":
        return "__end__"

    agents = state.get("active_agents", [])

    if not agents:
        return "synthesizer"

    sends = [Send(agent, state) for agent in agents]
    return sends
