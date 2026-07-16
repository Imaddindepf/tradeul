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

from agents.mcp_catalog import MCP
from agents._ticker_utils import get_ticker_info, validate_tickers
from agents._llm_retry import llm_invoke_with_retry

logger = logging.getLogger(__name__)

_llm = None

# ── Agent registry (intent-focused descriptions) ─────────────────

AVAILABLE_AGENTS = {
    "market_data": (
        "Real-time price data, enriched snapshots (145+ indicators), "
        "scanner rankings (winners, losers, gappers, momentum, volume, halts), "
        "historical daily/minute bars, deep technical snapshots (RSI, MACD, BB, ADX...), "
        "and FAISS pattern-similarity forecasts (probability up/down for the next minutes "
        "based on historically similar price action). "
        "Capabilities: current quotes, technicals, top movers, price history, OHLCV data, "
        "pattern forecasts ('¿se parece a algún patrón?', 'probabilidad de que siga subiendo')."
    ),
    "news_events": (
        "Benzinga financial news, real-time market events (85+ types: breakouts, VWAP crosses, "
        "halts, volume spikes, momentum shifts), historical events (TimescaleDB, 60-day retention), "
        "earnings calendar with EPS/revenue estimates. "
        "Capabilities: ticker news, market headlines, event history by date, earnings calendar."
    ),
    "financial": (
        "Fundamental data: income statements, balance sheets, cash flow, SEC filings. "
        "Capabilities: quarterly/annual financials, SEC 10-K/10-Q/8-K, EPS history, ratios. "
        "Does NOT handle dilution analysis — use the dilution agent for that."
    ),
    "dilution": (
        "Stock dilution analysis from the Tradeul dilution tracker service — uses OUR OWN DATABASE, "
        "no internet search needed. Two complementary data sources: "
        "(1) SEC-extracted data: warrants (exercise price, expiration, price protection/ratchet clauses, "
        "lifecycle events), ATM offerings (capacity, remaining, placement agent), "
        "shelf registrations (S-3, baby-shelf restrictions, current raisable amount), "
        "completed offerings history, convertible notes/preferred, equity lines, S-1 offerings. "
        "(2) Analyst-curated instrument context: precise ATM/shelf/warrant details with "
        "baby-shelf calculations, overhead supply analysis. "
        "Risk scoring (1-10): overall_risk, offering_ability, overhead_supply, "
        "historical_dilution, cash_need. "
        "Cash runway: months remaining, burn rate, available financing. "
        "Potential dilution %: total ceiling if all instruments exercised. "
        "Use for: ANY question about warrants, ATM, shelf, dilution risk, cash runway, "
        "shares outstanding history, offering history, convertible instruments, "
        "equity lines, PIPE deals, registration statements. "
        "CRITICAL for micro-cap and small-cap analysis."
    ),
    "research": (
        "Real-time web and X.com search via Grok, or Gemini Pro fallback. "
        "Searches social media posts, analyst commentary, breaking rumors, and web articles IN REAL TIME. "
        "This is the ONLY agent that can explain WHY a stock is moving — "
        "it finds catalysts, rumors, and breaking info not yet in structured feeds. "
        "Capabilities: why a stock moves, social sentiment, analyst opinions, real-time catalysts."
    ),
    "code_exec": (
        "Python/DuckDB code generation for custom statistical analysis and data exploration. "
        "Use for: frequency studies ('how often does X happen?', 'con qué frecuencia...'), "
        "conditional probability ('what % of the time does X happen when Y?'), "
        "statistical correlations, custom calculations, data transformations, comparisons, "
        "pattern counts, historical distribution analysis, and any quantitative question that "
        "requires custom code but is NOT asking for trading strategy P&L simulation. "
        "Examples: 'how often does a gap >3% continue up the next day?', "
        "'what % of TSLA gap-up days close green?', 'average return after a VWAP reclaim'. "
        "CRITICAL: do NOT use for trading strategy P&L backtesting — use backtest for that."
    ),
    "backtest": (
        "Professional backtesting engine for TRADING STRATEGIES only. "
        "Use ONLY when user wants to simulate a trading strategy with explicit entry rules, "
        "exit rules (stop loss, profit target, time stop), and measure P&L performance. "
        "Returns: Sharpe ratio, Win Rate, Max Drawdown, equity curve, trade log, walk-forward, Monte Carlo. "
        "Examples: 'backtest buying gap-ups >5% on TSLA with 10% stop', "
        "'test RSI<30 entry with 2R target on SPY', 'strategy: buy VWAP reclaim, sell EOD'. "
        "CRITICAL: Do NOT use for statistical/frequency questions ('how often...', '% of time', "
        "'con qué frecuencia') — those belong to code_exec. "
        "The strategy MUST have entry conditions + exit rules to qualify for backtest."
    ),
    "screener": (
        "DuckDB-powered stock screener on daily data with 60+ indicators. "
        "Translates natural language criteria into database filters. "
        "Capabilities: find stocks matching specific numeric criteria (RSI, volume, market cap, sector)."
    ),
    "strategy_scanner": (
        "Event-sequence strategy scanner over the real-time alert-engine store "
        "(240+ intraday event types, 12M events/day, 60-day history — works for TODAY in real time). "
        "Finds ALL stocks whose intraday event stream matched a described SETUP: "
        "sequences like 'crossed VWAP up after the opening low', 'halted then broke the opening range', "
        "'volume surge in the first 30 min', combined with day-level price conditions "
        "(closed above open, declined X% in the opening, market cap / price bounds). "
        "Returns matched tickers WITH EVIDENCE: exact timestamps and prices of each event step. "
        "Use for: '¿qué acciones hicieron X y luego Y hoy?', 'stocks that did <setup> today/yesterday/on DATE', "
        "'¿se dio mi estrategia en el mercado?'. "
        "CRITICAL: this is for FINDING PAST OCCURRENCES of a setup across the universe, "
        "NOT for P&L simulation (backtest) and NOT for current-state filtering (screener/screen)."
    ),
    "alert_compiler": (
        "LLM alert compiler — creates PERSISTENT, FORWARD-LOOKING market alerts from natural "
        "language. The user wants to BE NOTIFIED IN THE FUTURE when a condition happens: "
        "'avísame cuando...', 'alert me when...', 'quiero una alerta de...', 'notify me if...', "
        "'crea una alerta...'. Compiles the sentence into a validated alert spec, replays it "
        "against recent market history (dry-run with evidence: 'this would have fired N times "
        "this week'), and saves it as a DRAFT the user can confirm/arm. "
        "Supports: event conditions (VWAP crosses, ORB breakouts, halts, volume/RVOL spikes, "
        "MA/MACD/stoch crosses, 240+ event types), universe filters (price, RVOL, market cap, "
        "specific tickers, session), intraday sequences (A then B), and membership "
        "(enter/exit scanner rankings like top gappers). "
        "CRITICAL: use when the user wants FUTURE notifications (standing alert). "
        "If they ask what happened in the PAST, use strategy_scanner instead. "
        "If they want to LIST/PAUSE/ARM existing alerts, use alert_manager instead."
    ),
    "alert_manager": (
        "Manage EXISTING LLM alerts: list them, pause, arm, or archive. Keywords: "
        "'mis alertas', 'lista mis alertas', 'pausa la alerta de MSFT', 'arma la de VWAP', "
        "'borra/archiva la alerta…', 'my alerts', 'pause alert', 'activate alert'. "
        "Does NOT create new alerts — that is alert_compiler."
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

<conversation_awareness>
The user message may include a [Conversation so far] block with prior turns of this
thread (each turn: the user's query, the tickers it resolved to, and its intent).

Follow-up resolution rules:
1. If the current query is elliptical or uses pronouns/possessives ("y su caja?",
   "what about its warrants?", "dame más detalles", "compáralo con AMD"), resolve
   the missing subject from the MOST RECENT turn that has tickers.
2. Inherit those tickers into the "tickers" field and route as if the user had
   named them explicitly. Set confidence >= 0.9 — do NOT ask for clarification
   when the conversation context disambiguates the subject.
3. If the user explicitly names a NEW ticker or topic, the new subject wins;
   ignore prior context.
4. Mention the resolved subject in "plan" (e.g. "Follow-up sobre NVDA: ...").
5. A [Relevant past analysis] block may include snippets from other conversations —
   use it only as background, never as the subject of the current query.
</conversation_awareness>

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
RANKING — Top/bottom lists: gainers, losers, gappers, halts, volume leaders → market_data. When the query has numeric constraints (market cap, price, volume, float...) OR a custom sort metric (RVOL, gap %, 5-min change...), you MUST also emit a "screen" spec (see universe_screen section) so the ranking runs on the FULL 12K-ticker universe instead of a pre-cut category.
MARKET_PULSE — Broad market analysis: "what sectors are leading?", "que temas dominan en big caps?", "compare sectors", "market regime", "risk-on or risk-off?", "que industria tiene mejor breadth?", "temas oversold con momentum", "rotacion sectorial". Any question about SECTOR/INDUSTRY/THEME PERFORMANCE as aggregated groups (not individual stocks). → market_data. You MUST populate "pulse_queries" with a structured analytical spec (see pulse_query_format below).
CAUSAL — WHY something is happening: "why is X up/down/moving?", "por qué sube/baja X?", "what's driving X?", "what caused X to spike?" → research + news_events + market_data
NEWS — Recent news, headlines, "what happened with X" → news_events
EVENTS — Market events by date: breakouts, halts, VWAP crosses on a given day → news_events
EARNINGS_CALENDAR — Upcoming earnings dates, "who reports this week" → news_events
EARNINGS_HISTORY — Past EPS, revenue, quarterly results for a ticker → financial
FUNDAMENTALS — Financial statements, balance sheets, ratios → financial
SEC_FILINGS — SEC documents: 10-K, 10-Q, 8-K, S-1 → financial
SCREENING — Filter stocks by specific numeric criteria (without ranking) → screener
ALERT_CREATE — The user wants a STANDING ALERT: to be notified in the FUTURE when a market condition occurs → alert_compiler. Keywords: "avísame cuando", "alerta cuando", "crea una alerta", "quiero que me avises", "alert me when", "notify me when/if", "create an alert", "watch for", "cuando entre en top gappers". The condition may reference events, filters, sequences or scanner membership. Distinct from STRATEGY_SCAN (looks BACKWARD) and from ALERT_MANAGE.
ALERT_MANAGE — List / pause / arm / archive EXISTING alerts → alert_manager. Keywords: "mis alertas", "lista mis alertas", "pausa la alerta", "arma la alerta de…", "borra la alerta", "my alerts", "pause/activate/delete alert". Does NOT create.
STRATEGY_SCAN — Find stocks whose INTRADAY PRICE ACTION matched a described setup/sequence on a specific day → strategy_scanner. The user describes a temporal pattern of events ("crossed VWAP up AFTER an opening decline", "halted then broke out", "volume spike in the first 30 min and closed green vs open") and wants the LIST of stocks where it HAPPENED (today, yesterday, or a past date). Keywords: "cruzaron", "hicieron", "tras", "después de", "that did", "which stocks crossed/reclaimed/broke... and then...". Distinct from SCREENING (current-state filters, no temporal sequence), RANKING (top lists), BACKTEST (P&L simulation with entry/exit rules) and CODE (statistical frequencies).
THEMATIC — Find stocks by investment theme, sector vertical, or industry category. The user is explicitly looking for a LIST of companies in a specific theme. Examples: "robotics stocks", "empresas de memoria", "quantum computing companies", "acciones de energía nuclear", "cybersecurity zero trust", "EV charging", "GLP-1 weight loss drugs", "chip foundry stocks", "defense tech", "lithium miners" → market_data. IMPORTANT: Broad market questions like "what theme is driving the market today?", "que tema mueve el mercado?", "what sectors are hot?" are NOT THEMATIC — they are RANKING queries because the user wants to see current market movers, not a static list of themed companies.
DEEP_RESEARCH — Comprehensive analysis, business model, competitive positioning, sentiment, analyst opinions → research + financial (when tickers are present). Use for: "how does X make money?", "compare X vs Y", "what's X's competitive moat?", "diferencias entre X e Y", "modelo de negocio de X"
COMPLETE_ANALYSIS — Full picture: "análisis completo", "deep dive", "full breakdown" → market_data + news_events + financial (add research if sentiment/opinions requested)
CODE — Custom statistical analysis, frequency studies, conditional probabilities, data transformations → code_exec. Use when user asks "how often", "what % of the time", "con qué frecuencia", "average return after X", "correlation between X and Y" — any question needing custom Python/DuckDB analysis on historical data WITHOUT trading strategy P&L simulation.
BACKTEST — Trading strategy P&L simulation with entry/exit rules → backtest. ONLY when user describes a STRATEGY with entry conditions AND exit rules (stop, target, time). Examples: "backtest buying RSI<30 with 5% stop", "/backtest gap-up strategy". If query is a frequency/statistical question WITHOUT explicit P&L strategy intent, route to CODE instead. If user is only asking ABOUT backtest capabilities (no strategy given), classify as GREETING.
CHART_ANALYSIS — User is asking about a specific chart they are viewing (technical analysis, patterns, support/resistance, trend) → market_data (add research if "why" is asked, add news_events for context)
DILUTION_ANALYSIS — ANY question about stock dilution, warrants, ATM offerings, shelf registrations, convertible notes/preferred, equity lines, S-1 filings, cash runway, burn rate, shares outstanding history, offering history, PIPE deals, registration statements, dilution risk scores, price protection/ratchet clauses, baby-shelf restrictions, overhead supply → dilution. Add market_data for current price context. Add news_events if asking about recent filings or catalysts.

A single query can combine MULTIPLE intents — select agents for ALL detected intents.
Example: "Why is TSLA up? Show me the financials too" = CAUSAL + FUNDAMENTALS → research + news_events + market_data + financial
Example: "What's NVAX's dilution risk and cash runway?" = DILUTION_ANALYSIS → dilution + market_data
</intent_types>

<routing_principles>
1. CAUSAL queries (why, por qué, what's causing, what's driving, what triggered) ALWAYS include the research agent. It is the ONLY agent that searches X.com and the web in real time for catalysts and breaking information. Without it, causal questions cannot be answered.

2. When a query mentions a specific ticker, include market_data alongside other agents to provide current price context.

3. RANKING queries use market_data with the appropriate scanner category. The screener agent is only for custom numeric filtering without a ranking.

4. For COMPLETE_ANALYSIS, select at least market_data + news_events + financial. Add research when the user mentions sentiment, opinions, research, or "con sentimiento".

5. DILUTION queries use the dilution agent exclusively — it queries our own database with no internet needed. Keywords: warrants, ATM, shelf, s-3, cash runway, burn rate, dilution risk, shares outstanding, PIPE, registered direct, offering history, convertible note, equity line, price protection, ratchet, baby-shelf, overhead supply. Do NOT route dilution queries to financial or research agents. Always add market_data alongside dilution for current price context.

7. THEMATIC queries ask for stocks by theme, sector, or industry vertical. Route to market_data ONLY — it resolves themes via the classification database (124 pre-computed themes, no LLM needed at query time). You MUST populate the "theme_tags" field with canonical tags from the thematic catalog below. Map the user's natural language to one or more canonical tags. Examples: "robótica" → ["robotics"], "chips de memoria" → ["memory_chips"], "IA generativa" → ["generative_ai"], "cybersecurity zero trust" → ["cybersecurity", "identity_zero_trust"].

8. Write the plan field in the same language the user used in their query.

9. CHART_ANALYSIS queries come with a chart_context containing the user's visible chart data (OHLCV bars, indicators, drawings). Always include market_data for enrichment. Add research if the user asks "why" something happened.

10. AGENT TASK DECOMPOSITION: When selecting 2+ agents, you MUST generate "agent_tasks" — a dict mapping each agent name to a specific sub-question or instruction tailored to that agent's data sources. Each task must be a clear, self-contained sentence that tells the agent EXACTLY what to search for. Use the verified company names from ticker extraction. For single-agent queries, set agent_tasks to null. This is critical — without tailored tasks, agents fall back to generic behavior and may miss the user's actual question.

11. MARKET_PULSE queries analyze aggregated sector/industry/theme performance. You MUST generate "pulse_queries" — an array of structured query objects. Each query: {{"group": "sectors"|"industries"|"themes", "sort_by": metric, "limit": int, "cap_size": "mega"|"large"|"mid"|"small"|null, "min_market_cap": int|null, "sector": str|null, "include_movers": bool, "metric_filters": [{{"metric":str,"op":"gt|gte|lt|lte","value":float}}], "label": str}}. Set "pulse_compare": true when comparing segments. Set "pulse_drilldown": {{"from_query":0,"rank":1,"sort_by":"change_percent","limit":10}} to drill into a result. Sortable metrics: weighted_change, avg_change, breadth, avg_rvol, avg_rsi, avg_daily_rsi, avg_atr_pct, avg_change_5d, avg_change_10d, avg_change_20d, avg_from_52w_high, avg_from_52w_low, avg_pos_in_range, avg_bb_position, avg_dist_vwap, avg_dist_sma20, avg_dist_sma50, total_dollar_volume, count. Cap sizes: mega(>200B), large(>10B), mid(>2B), small(>300M), micro(>50M).
</routing_principles>

<universe_screen>
The platform maintains a real-time enriched snapshot of ~12,000 tickers x 395 fields.
When a RANKING or SCREENING query includes numeric constraints or a custom sort metric,
emit a "screen" object so market_data runs it on the FULL universe:

"screen": {{
  "filters": [{{"field": str, "op": "gt|gte|lt|lte|eq|neq|contains", "value": number|string}}],
  "sort_by": str,          // field to rank by
  "sort_order": "desc"|"asc",
  "limit": int,            // default 25
  "snapshot": "live"|"close"  // "close" = universe frozen at last regular-session close
}}

Field vocabulary (use EXACTLY these names):
- Identity/size: price, volume, market_cap, float_shares, shares_outstanding, dollar_volume, sector, industry, security_type
- Day performance: change_pct (% today), gap_percent, change_from_open, todays_range_pct, pos_in_range
- Relative volume: rvol (day RVOL), vol_1min, vol_5min, vol_10min, vol_30min, vol_60min, minute_volume, trades_today, trades_z_score
- Momentum windows (%): chg_1min, chg_2min, chg_5min, chg_10min, chg_15min, chg_30min, chg_60min, chg_120min
- Sessions: premarket_change_percent, premarket_volume, premarket_rvol, postmarket_change_percent
- Intraday technicals: rsi_14, macd_line, macd_hist, adx_14, stoch_k, stoch_d, vwap, dist_from_vwap, atr_percent, bb_position_5m, ema_9, ema_20, sma_20, sma_200
- Daily technicals: daily_rsi, daily_adx_14, daily_atr_percent, daily_gap_percent, daily_bb_position, dist_daily_sma_20, dist_daily_sma_50, dist_daily_sma_200
- Multi-day performance: change_1d, change_3d, change_5d, change_10d, change_20d, change_ytd, change_1y, consecutive_days_up
- Range position: from_52w_high, from_52w_low, pos_in_52w_range, pos_in_5d_range, pos_in_20d_range, price_from_intraday_high, price_from_intraday_low
- Liquidity averages: avg_volume_5d, avg_volume_10d, avg_volume_20d, avg_volume_3m, float_turnover
- Dilution risk (1-10): dilution_overall_risk_score, dilution_cash_need_score, dilution_overhead_supply_score

Rules:
1. Use "close" snapshot when the user says "at the close", "before the close", "al cierre", "antes del cierre" AND the current session is POST_MARKET or CLOSED. Otherwise "live".
2. Session-change rankings (after-hours/premarket movers) sort by postmarket_change_percent / premarket_change_percent.
3. Add a liquidity floor {{"field":"volume","op":"gt","value":100000}} unless the user constrained volume themselves.
4. Numeric suffixes: 500m = 500000000, 1.5b = 1500000000, 300k = 300000.
5. Percent fields are plain numbers: "gap over 5%" → {{"field":"gap_percent","op":"gte","value":5}}.
6. Set "screen" to null when the query is a plain category ranking with no constraints and no custom sort.
</universe_screen>

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
  "screen": null,
  "pulse_queries": null,
  "pulse_compare": false,
  "pulse_metrics": null,
  "pulse_drilldown": null,
  "agent_tasks": null,
  "plan": "Brief execution plan in the user's language",
  "confidence": 0.95,
  "reasoning": "One sentence explaining why you chose these agents",
  "clarification": null
}}

IMPORTANT: "agent_tasks" maps each selected agent to a tailored sub-question. Generate it when 2+ agents are selected. Example:
"agent_tasks": {{"research": "Why is TSLA moving? Find the specific catalyst.", "market_data": "Current price and technicals for TSLA"}}
For single-agent queries, set to null.

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
{{"intent": "CAUSAL", "tickers": ["LFS"], "agents": ["research", "news_events", "market_data"], "theme_tags": [], "agent_tasks": {{"research": "Why is LFS stock moving right now? Find the specific catalyst: earnings, analyst action, news, partnership, or breaking event.", "news_events": "Latest Benzinga news and real-time market events for LFS", "market_data": "Current price, volume, RVOL, and technicals for LFS"}}, "plan": "Investigar por qué se mueve LFS: buscar catalizador en web/X.com, noticias, datos de precio", "confidence": 0.95, "reasoning": "Causal query — research searches real-time sources for catalysts", "clarification": null}}

User: "top 20 gappers"
{{"intent": "RANKING", "tickers": [], "agents": ["market_data"], "theme_tags": [], "screen": null, "plan": "Fetch top 20 gappers from scanner", "confidence": 1.0, "reasoning": "Ranking query for gappers_up scanner category — no constraints, category is enough", "clarification": null}}

User: "dame las acciones por encima de 500m de market cap ordenadas por volumen relativo antes del cierre de la sesión regular"
{{"intent": "RANKING", "tickers": [], "agents": ["market_data"], "theme_tags": [], "screen": {{"filters": [{{"field": "market_cap", "op": "gte", "value": 500000000}}, {{"field": "volume", "op": "gt", "value": 100000}}], "sort_by": "rvol", "sort_order": "desc", "limit": 25, "snapshot": "close"}}, "plan": "Screen del universo completo al cierre: market cap > $500M ordenado por RVOL", "confidence": 1.0, "reasoning": "Ranking with market cap constraint and custom sort (RVOL) referenced at the regular-session close — full-universe screen on the close snapshot", "clarification": null}}

User: "top after hours stocks with market cap above 300m"
{{"intent": "RANKING", "tickers": [], "agents": ["market_data"], "theme_tags": [], "screen": {{"filters": [{{"field": "market_cap", "op": "gte", "value": 300000000}}, {{"field": "volume", "op": "gt", "value": 100000}}], "sort_by": "postmarket_change_percent", "sort_order": "desc", "limit": 25, "snapshot": "live"}}, "plan": "Screen full universe: after-hours movers with market cap > $300M ranked by AH change", "confidence": 1.0, "reasoning": "After-hours ranking with market cap constraint — universe screen sorted by postmarket change", "clarification": null}}

User: "small caps entre 1 y 10 dolares con gap de mas de 5%, RVOL sobre 3 y float bajo 20 millones"
{{"intent": "RANKING", "tickers": [], "agents": ["market_data"], "theme_tags": [], "screen": {{"filters": [{{"field": "price", "op": "gte", "value": 1}}, {{"field": "price", "op": "lte", "value": 10}}, {{"field": "gap_percent", "op": "gte", "value": 5}}, {{"field": "rvol", "op": "gte", "value": 3}}, {{"field": "float_shares", "op": "lte", "value": 20000000}}], "sort_by": "gap_percent", "sort_order": "desc", "limit": 25, "snapshot": "live"}}, "plan": "Screen: small caps $1-$10, gap >5%, RVOL >3, float <20M ordenado por gap", "confidence": 1.0, "reasoning": "Multi-constraint day-trader screen — full-universe filter with 5 conditions", "clarification": null}}

User: "acciones sobre VWAP con RSI diario menor a 40 haciendo maximos, ordenadas por volumen en dolares"
{{"intent": "RANKING", "tickers": [], "agents": ["market_data"], "theme_tags": [], "screen": {{"filters": [{{"field": "dist_from_vwap", "op": "gt", "value": 0}}, {{"field": "daily_rsi", "op": "lt", "value": 40}}, {{"field": "price_from_intraday_high", "op": "gte", "value": -1}}, {{"field": "volume", "op": "gt", "value": 100000}}], "sort_by": "dollar_volume", "sort_order": "desc", "limit": 25, "snapshot": "live"}}, "plan": "Screen: sobre VWAP, RSI diario <40, cerca del máximo intradía, ordenado por dollar volume", "confidence": 0.95, "reasoning": "Technical multi-condition screen with custom sort — full-universe filter", "clarification": null}}

User: "stocks con RSI menor a 30 y volumen mayor a 1M"
{{"intent": "SCREENING", "tickers": [], "agents": ["screener"], "theme_tags": [], "plan": "Screener: filtrar acciones con RSI < 30 y volumen > 1M", "confidence": 1.0, "reasoning": "Numeric criteria screening without ranking implied", "clarification": null}}

User: "dame las acciones con minimo market cap 1b que cruzaran el vwap al alza tras una larga caida en el opening y que cerraran por encima del opening"
{{"intent": "STRATEGY_SCAN", "tickers": [], "agents": ["strategy_scanner"], "theme_tags": [], "plan": "Escanear el universo: mcap > $1B, caída fuerte en el opening, cruce de VWAP al alza tras el mínimo, cierre sobre la apertura", "confidence": 1.0, "reasoning": "Temporal setup sequence (decline → VWAP reclaim → close above open) — strategy_scanner matches it against the intraday event stream", "clarification": null}}

User: "which stocks got halted and then broke the opening range high yesterday?"
{{"intent": "STRATEGY_SCAN", "tickers": [], "agents": ["strategy_scanner"], "theme_tags": [], "plan": "Scan yesterday's event stream: halt followed by ORB breakout up", "confidence": 1.0, "reasoning": "Event sequence query (halt then breakout) on a past day — strategy_scanner", "clarification": null}}

User: "avísame cuando cualquier acción con rvol por encima de 1.5 cruce el vwap al alza"
{{"intent": "ALERT_CREATE", "tickers": [], "agents": ["alert_compiler"], "theme_tags": [], "plan": "Crear alerta permanente: cruce de VWAP al alza con RVOL > 1.5, compilar spec + dry-run", "confidence": 1.0, "reasoning": "User wants a standing future notification — alert_compiler builds and previews the alert", "clarification": null}}

User: "alert me when TSLA gets halted"
{{"intent": "ALERT_CREATE", "tickers": ["TSLA"], "agents": ["alert_compiler"], "theme_tags": [], "plan": "Create standing alert: TSLA halt detection with instant notification", "confidence": 1.0, "reasoning": "Forward-looking notification request for a specific ticker event — alert_compiler", "clarification": null}}

User: "quiero una alerta para acciones de más de 1B que caigan en el opening y luego reclamen el vwap"
{{"intent": "ALERT_CREATE", "tickers": [], "agents": ["alert_compiler"], "theme_tags": [], "plan": "Crear alerta de secuencia: caída en opening + reclaim de VWAP en acciones >1B, con dry-run de evidencia", "confidence": 1.0, "reasoning": "Standing sequence alert with universe filter — alert_compiler compiles and previews it", "clarification": null}}

User: "avísame cuando una acción entre en el top 10 de gappers"
{{"intent": "ALERT_CREATE", "tickers": [], "agents": ["alert_compiler"], "theme_tags": [], "plan": "Crear alerta membership: enter top 10 gappers_up", "confidence": 1.0, "reasoning": "Scanner ranking enter watch — alert_compiler membership tier", "clarification": null}}

User: "mis alertas"
{{"intent": "ALERT_MANAGE", "tickers": [], "agents": ["alert_manager"], "theme_tags": [], "plan": "Listar alertas IA existentes del usuario", "confidence": 1.0, "reasoning": "Manage existing alerts — alert_manager", "clarification": null}}

User: "pausa la alerta de MSFT"
{{"intent": "ALERT_MANAGE", "tickers": ["MSFT"], "agents": ["alert_manager"], "theme_tags": [], "plan": "Pausar la alerta existente de MSFT", "confidence": 1.0, "reasoning": "Pause existing alert by ticker — alert_manager", "clarification": null}}

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

User: "Quiero hacer backtest contigo! podrias decirme que necesitas?"
{{"intent": "GREETING", "tickers": [], "agents": [], "theme_tags": [], "plan": "El usuario pregunta sobre cómo usar el backtester — responder con instrucciones", "confidence": 1.0, "reasoning": "Informational question about backtest capabilities, no actual strategy to execute", "clarification": null}}

User: "how does backtest work? what do I need?"
{{"intent": "GREETING", "tickers": [], "agents": [], "theme_tags": [], "plan": "User asking about backtest usage — respond with instructions", "confidence": 1.0, "reasoning": "Informational question about backtest, no trading strategy provided", "clarification": null}}

User: "/backtest Buy stocks gapping up 5% with volume > 1M, sell at 10% profit or 5% stop on AAPL, 2024-2025"
{{"intent": "BACKTEST", "tickers": ["AAPL"], "agents": ["backtest"], "theme_tags": [], "plan": "Backtest gap-up momentum strategy with volume filter, profit target and stop loss on AAPL", "confidence": 1.0, "reasoning": "Explicit backtest command with strategy description and ticker", "clarification": null}}

User: "backtest RSI mean reversion on SPY from 2020 to 2024"
{{"intent": "BACKTEST", "tickers": ["SPY"], "agents": ["backtest"], "theme_tags": [], "plan": "Backtest RSI mean reversion strategy on SPY", "confidence": 1.0, "reasoning": "Backtest request with specific ticker and strategy", "clarification": null}}

User: "con qué frecuencia un gap > 3% continúa al alza al día siguiente en TSLA cuando su volumen relativo es por encima de 2?"
{{"intent": "CODE", "tickers": ["TSLA"], "agents": ["code_exec"], "theme_tags": [], "plan": "Statistical frequency study: gap >3% continuation rate when RVOL>2 on TSLA using historical daily bars", "confidence": 1.0, "reasoning": "Frequency/probability question — not a strategy P&L simulation. Needs custom code to count occurrences and calculate conditional probability.", "clarification": null}}

User: "how often does AAPL close green after gapping up more than 2%?"
{{"intent": "CODE", "tickers": ["AAPL"], "agents": ["code_exec"], "theme_tags": [], "plan": "Calculate % of AAPL gap-up days (>2%) that close positive using historical data", "confidence": 1.0, "reasoning": "Statistical frequency question — code_exec will analyze historical bars and compute the conditional win rate.", "clarification": null}}

User: "average return of SPY the day after a red Friday"
{{"intent": "CODE", "tickers": ["SPY"], "agents": ["code_exec"], "theme_tags": [], "plan": "Compute average Monday return for SPY following a red Friday using historical daily bars", "confidence": 1.0, "reasoning": "Historical pattern analysis without entry/exit strategy — code_exec statistical study.", "clarification": null}}

User: "noticias de AAPL"
{{"intent": "NEWS", "tickers": ["AAPL"], "agents": ["news_events", "market_data"], "theme_tags": [], "plan": "Obtener noticias recientes de AAPL con contexto de precio", "confidence": 1.0, "reasoning": "News query for specific ticker with price context", "clarification": null}}

User: "análisis completo de PLTR con sentimiento"
{{"intent": "COMPLETE_ANALYSIS", "tickers": ["PLTR"], "agents": ["market_data", "news_events", "financial", "research"], "theme_tags": [], "agent_tasks": {{"market_data": "Price, volume, technicals, and enriched snapshot for PLTR", "news_events": "Latest news and real-time events for Palantir (PLTR)", "financial": "Recent financial statements for Palantir — income, balance sheet, cash flow", "research": "Analyst sentiment, opinions, price targets, and social media buzz for Palantir (PLTR)"}}, "plan": "Análisis completo de PLTR: precio, noticias, fundamentales y sentimiento", "confidence": 0.95, "reasoning": "Complete analysis with sentiment — all four agents with tailored tasks", "clarification": null}}

User: "que diferencia hay entre el modelo de negocio de UPST y FOUR?"
{{"intent": "DEEP_RESEARCH", "tickers": ["UPST", "FOUR"], "agents": ["research", "financial"], "theme_tags": [], "agent_tasks": {{"research": "Compare the business models of Upstart Holdings (UPST) and Shift4 Payments (FOUR). How does each generate revenue? Key differences in strategy, technology, target market, and competitive moat.", "financial": "Financial statements for UPST and FOUR to compare revenue composition, margins, growth rates, and unit economics."}}, "plan": "Comparar modelos de negocio: research para análisis conceptual, financial para datos cuantitativos", "confidence": 0.95, "reasoning": "Deep research comparing two companies — needs web research + financial data", "clarification": null}}

User: "how does Palantir make money?"
{{"intent": "DEEP_RESEARCH", "tickers": ["PLTR"], "agents": ["research", "financial"], "theme_tags": [], "agent_tasks": {{"research": "How does Palantir Technologies (PLTR) make money? Describe its business model, revenue streams (Gotham vs Foundry vs AIP), customer segments (government vs commercial), and go-to-market strategy.", "financial": "Financial statements for PLTR to show revenue breakdown, margins, growth trajectory, and profitability trends."}}, "plan": "Explicar modelo de negocio de PLTR: research para análisis cualitativo, financial para datos", "confidence": 0.95, "reasoning": "Business model deep dive — research for qualitative analysis, financial for quantitative", "clarification": null}}

User: "ninguna"
{{"intent": "GREETING", "tickers": [], "agents": [], "theme_tags": [], "plan": "Dismissal — responder brevemente", "confidence": 1.0, "reasoning": "User dismissal, not a financial query", "clarification": null}}

User: "Full technical analysis of TSLA chart" [chart_context attached]
{{"intent": "CHART_ANALYSIS", "tickers": ["TSLA"], "agents": ["market_data", "news_events"], "theme_tags": [], "plan": "Analyze TSLA chart: read visible bars/indicators from chart context, enrich with current data and recent news", "confidence": 1.0, "reasoning": "Chart analysis with chart_context — market_data for enrichment, news for context", "clarification": null}}

User: "Why did NVDA move like this on 2025-12-15?" [chart_context attached]
{{"intent": "CHART_ANALYSIS", "tickers": ["NVDA"], "agents": ["market_data", "news_events", "research"], "theme_tags": [], "plan": "Analyze NVDA chart candle movement: search for catalysts on that date via research, check news, get price context", "confidence": 0.95, "reasoning": "Chart analysis with causal why — needs research agent for catalyst discovery", "clarification": null}}

User: "qué warrants tiene NVAX y cuál es su precio de ejercicio?"
{{"intent": "DILUTION_ANALYSIS", "tickers": ["NVAX"], "agents": ["dilution", "market_data"], "theme_tags": [], "agent_tasks": {{"dilution": "Get all outstanding warrants for NVAX (Novavax): exercise prices, expiration dates, shares underlying, price protection clauses, and warrant lifecycle events.", "market_data": "Current price and float data for NVAX to contextualize warrant exercise prices"}}, "plan": "Obtener warrants de NVAX: precios de ejercicio, vencimientos y claúsulas de protección de precio", "confidence": 1.0, "reasoning": "Dilution query focused on warrants — use dilution agent with market_data for price context", "clarification": null}}

User: "how much cash runway does SNDX have? when will they need to raise?"
{{"intent": "DILUTION_ANALYSIS", "tickers": ["SNDX"], "agents": ["dilution", "market_data"], "theme_tags": [], "agent_tasks": {{"dilution": "Get cash position, burn rate, and cash runway analysis for SNDX (Syndax Pharmaceuticals). Include available ATM/shelf financing capacity.", "market_data": "Current price and market cap for SNDX"}}, "plan": "Analyze SNDX cash runway: months remaining, burn rate, and available financing options", "confidence": 1.0, "reasoning": "Cash runway is a dilution domain query — dilution agent has the cash_position and runway data", "clarification": null}}

User: "dame el análisis completo de dilución de MARA"
{{"intent": "DILUTION_ANALYSIS", "tickers": ["MARA"], "agents": ["dilution", "market_data"], "theme_tags": [], "agent_tasks": {{"dilution": "Full dilution analysis for MARA (Marathon Digital Holdings): SEC profile with all instruments (warrants, ATM, shelf, convertibles, equity lines), risk scores (overall, offering ability, overhead supply, historical, cash need), cash runway, potential total dilution percentage, and completed offerings history.", "market_data": "Current price, volume, market cap, and float for MARA"}}, "plan": "Análisis completo de dilución de MARA: perfil SEC, riesgo, runway de caja, % dilución potencial", "confidence": 1.0, "reasoning": "Full dilution analysis request — dilution agent covers all aspects, market_data for context", "clarification": null}}

User: "what is ILUS's dilution risk score?"
{{"intent": "DILUTION_ANALYSIS", "tickers": ["ILUS"], "agents": ["dilution", "market_data"], "theme_tags": [], "agent_tasks": {{"dilution": "Get dilution risk ratings for ILUS: overall risk score, offering ability risk, overhead supply risk, historical dilution risk, and cash need risk (all on 1-10 scale).", "market_data": "Current price and market cap for ILUS"}}, "plan": "Get ILUS dilution risk scores across all 5 risk dimensions", "confidence": 1.0, "reasoning": "Risk score query maps directly to dilution agent risk_ratings endpoint", "clarification": null}}

User: "cuánto puede diluirse MMAT si usa todo su shelf y ATM?"
{{"intent": "DILUTION_ANALYSIS", "tickers": ["MMAT"], "agents": ["dilution", "market_data"], "theme_tags": [], "agent_tasks": {{"dilution": "Calculate total potential dilution percentage for MMAT (Meta Materials): breakdown by instrument type (warrants, ATM, shelf, convertibles) showing worst-case dilution ceiling if all instruments are exercised at current price.", "market_data": "Current price and shares outstanding for MMAT to contextualize dilution percentages"}}, "plan": "Calcular dilución potencial total de MMAT: desglose por instrumento y porcentaje máximo de dilución", "confidence": 1.0, "reasoning": "Potential dilution ceiling query — dilution agent's dilution_analysis endpoint provides exact breakdown", "clarification": null}}

User: "show me the offering history for SAVA and how many times they've diluted shareholders"
{{"intent": "DILUTION_ANALYSIS", "tickers": ["SAVA"], "agents": ["dilution", "market_data"], "theme_tags": [], "agent_tasks": {{"dilution": "Get completed offerings history for SAVA (Cassava Sciences): all past capital raises with dates, types, amounts raised, shares issued, prices, and banks. Include shares outstanding history to quantify historical dilution percentage.", "market_data": "Current price and shares outstanding for SAVA"}}, "plan": "Pull SAVA offering history and shares outstanding trajectory to quantify historical dilution", "confidence": 1.0, "reasoning": "Offering history is dilution domain — completed_offerings and shares_history from dilution agent", "clarification": null}}

User: "análisis completo de NVAX con noticias y dilución"
{{"intent": "COMPLETE_ANALYSIS", "tickers": ["NVAX"], "agents": ["market_data", "news_events", "dilution", "financial"], "theme_tags": [], "agent_tasks": {{"market_data": "Current price, volume, RVOL, technicals, and enriched snapshot for NVAX (Novavax)", "news_events": "Latest Benzinga news and market events for NVAX", "dilution": "Full dilution profile for NVAX: warrants, ATM, shelf, cash runway, risk scores", "financial": "Recent financial statements for NVAX: income, balance sheet, cash flow"}}, "plan": "Análisis completo de NVAX: precio, noticias, perfil de dilución y fundamentales", "confidence": 0.95, "reasoning": "Complete analysis with explicit dilution request — four agents covering all data domains", "clarification": null}}
</examples>"""


# ── LLM singleton ─────────────────────────────────────────────────

def _get_llm():
    global _llm
    if _llm is None:
        from agents._make_llm import make_llm
        _llm = make_llm(tier="fast", temperature=0.0, max_tokens=1024)
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
        session_data = await MCP.scanner.get_market_session({})
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


# ── Conversation context formatting ──────────────────────────────

def _format_conversation_context(memory_context: list[dict]) -> str:
    """Format memory_context entries into compact blocks for the planner prompt.

    Returns "" when there is nothing useful, so the planner prompt stays
    identical to the no-history case (cache-friendly).
    """
    if not memory_context:
        return ""

    thread_lines: list[str] = []
    recall_lines: list[str] = []

    for entry in memory_context:
        source = entry.get("source", "")
        if source == "thread":
            q = (entry.get("query") or "").strip()
            if not q:
                continue
            tickers = entry.get("tickers") or []
            intent = entry.get("intent") or ""
            meta = []
            if tickers:
                meta.append(f"tickers={','.join(tickers)}")
            if intent:
                meta.append(f"intent={intent}")
            suffix = f" [{'; '.join(meta)}]" if meta else ""
            thread_lines.append(f"- {q[:200]}{suffix}")
        else:
            content = (entry.get("content") or "").strip()
            if content:
                recall_lines.append(f"- {content[:200]}")

    parts: list[str] = []
    if thread_lines:
        # Oldest first so "most recent" is last (matches LLM recency bias)
        parts.append("[Conversation so far]\n" + "\n".join(thread_lines[-6:]))
    if recall_lines:
        parts.append("[Relevant past analysis]\n" + "\n".join(recall_lines[:3]))
    return "\n\n".join(parts)


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
    has_full_chart = chart_context and len(chart_context.get("snapshot", {}).get("recentBars", [])) > 0
    if has_full_chart:
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

        # Chart ticker is user-verified (from their own chart) — keep it even if
        # not in the real-time scanner universe (e.g. low-float or recently delisted)
        llm_tickers = [ticker] if ticker else []
        ticker_info: dict = {}
        if llm_tickers:
            validated = await validate_tickers(llm_tickers)
            if not validated:
                logger.info("Query planner: chart ticker %s not in scanner universe, keeping anyway", ticker)
            ticker_info = await get_ticker_info(validated or llm_tickers)

        return {
            **state,
            "intent": "CHART_ANALYSIS",
            "tickers": llm_tickers,
            "ticker_info": ticker_info,
            "active_agents": agents,
            "plan": plan,
            "clarification": None,
            "market_context": state.get("market_context", {}),
        }

    # ── BACKTEST fast-path: only for /backtest command prefix (not bare "backtest" word) ──
    if query.strip().lower().startswith("/backtest"):
        logger.info("Query planner: BACKTEST (fast-path) — routing directly to backtest agent")

        llm_tickers = []
        ticker_info: dict = {}

        return {
            **state,
            "intent": "BACKTEST",
            "tickers": llm_tickers,
            "ticker_info": ticker_info,
            "active_agents": ["backtest"],
            "plan": "Execute professional backtest from natural language strategy",
            "clarification": None,
            "market_context": state.get("market_context", {}),
        }

    # ── Standard LLM-based routing ──
    user_content = f"[Language: {language}] {query}"

    conversation_block = _format_conversation_context(state.get("memory_context") or [])
    if conversation_block:
        user_content = f"{conversation_block}\n\n[Current query]\n{user_content}"

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
            "intent": decision.get("intent", "UNKNOWN"),
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

    # ── Execution mode shaping ──
    # quick: cheapest useful answer — cap fan-out at 2 agents, drop research
    #        (web search is the slowest agent by far).
    # deep:  maximum coverage — always add research when tickers are present.
    mode = state.get("mode", "auto")
    if mode == "quick" and len(requested_agents) > 1:
        _quick_priority = [
            "market_data", "news_events", "dilution", "screener",
            "strategy_scanner", "financial", "backtest", "code_exec", "research",
        ]
        requested_agents = sorted(
            [a for a in requested_agents if a != "research"],
            key=_quick_priority.index,
        )[:2] or requested_agents[:1]
    elif mode == "deep":
        if "research" not in requested_agents and decision.get("tickers"):
            requested_agents.append("research")
        if "financial" not in requested_agents and decision.get("intent") in (
            "COMPLETE_ANALYSIS", "DEEP_RESEARCH", "CAUSAL",
        ):
            requested_agents.append("financial")

    theme_tags = decision.get("theme_tags", [])
    if theme_tags:
        theme_tags = [t.strip() for t in theme_tags if isinstance(t, str) and t.strip()]

    # Universe screen spec (full-universe structured ranking)
    screen = decision.get("screen")
    if screen is not None and not (isinstance(screen, dict) and isinstance(screen.get("filters"), list)):
        screen = None

    # Market Pulse structured queries
    pulse_queries = decision.get("pulse_queries")
    pulse_compare = decision.get("pulse_compare", False)
    pulse_metrics = decision.get("pulse_metrics")
    pulse_drilldown = decision.get("pulse_drilldown")

    # Agent task decomposition
    agent_tasks = decision.get("agent_tasks")
    if agent_tasks and not isinstance(agent_tasks, dict):
        agent_tasks = None

    logger.info(
        "Query planner: intent=%s confidence=%.2f mode=%s tickers=%s agents=%s themes=%s screen=%s pulse=%s tasks=%s ctx_turns=%d plan=%s",
        decision.get("intent", "?"), confidence, mode, llm_tickers,
        requested_agents, theme_tags,
        bool(screen), bool(pulse_queries), bool(agent_tasks),
        len([e for e in (state.get("memory_context") or []) if e.get("source") == "thread"]),
        decision.get("plan", "")[:120],
    )

    result_state = {
        **state,
        "intent": decision.get("intent", "UNKNOWN"),
        "tickers": llm_tickers,
        "ticker_info": ticker_info,
        "active_agents": requested_agents,
        "theme_tags": theme_tags,
        "agent_tasks": agent_tasks,
        "screen": screen,
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

    agent_tasks = state.get("agent_tasks") or {}
    sends = []
    for agent in agents:
        if agent in agent_tasks:
            sends.append(Send(agent, {**state, "agent_task": agent_tasks[agent]}))
        else:
            sends.append(Send(agent, state))
    return sends
