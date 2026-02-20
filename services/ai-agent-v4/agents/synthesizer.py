"""
Synthesizer Agent — Premium response generation.

Takes all agent_results from state, constructs a clean context payload,
and uses Gemini Flash to produce a polished, data-rich markdown response
with structured sections, tables, metrics cards, and actionable insights.

Prompt engineering:
  - Query-type-aware formatting (CAUSAL, RANKING, ANALYSIS, etc.)
  - Structured output templates for each data type
  - Company metadata integration (ticker_info) for verified names
  - Few-shot section examples inline
  - XML-structured prompt sections
"""
from __future__ import annotations
import json
import logging
import re
import time
from typing import Any
from langchain_core.messages import SystemMessage, HumanMessage
from agents._llm_retry import llm_invoke_with_retry

logger = logging.getLogger(__name__)

# ── Lazy LLM singleton ──────────────────────────────────────────
_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.3,
            max_output_tokens=8192,
        )
    return _llm


SYNTHESIS_PROMPT = """\
<role>
You are the premium response synthesizer for Tradeul, a professional stock trading intelligence platform. Your audience: experienced day traders and institutional analysts who demand precision, structure, and actionable insights. Every response must look like it came from a Bloomberg terminal analyst, not a chatbot.
</role>

<language>
{language_instruction}
</language>

<rules>
1. ONLY use data from agent_results. NEVER hallucinate prices, volumes, percentages, or company info.
2. Use the company names from ticker_info — these are VERIFIED from our database.
3. NEVER mention internal agent names, tool names, or system architecture.
4. NEVER dump raw JSON. Transform everything into formatted markdown.
5. If data is missing or an agent returned an error, say so honestly in one sentence.
6. CONVERSATIONAL QUERIES: If the query is a greeting or off-topic, respond conversationally without market data.
</rules>

<market_session_awareness>
Check "market_session" in the data. Use the "current_session" field to determine the exact session:
- current_session=CLOSED + weekend/holiday: "El mercado está cerrado (fin de semana/festivo). Datos de la última sesión de [day], [date]."
- current_session=CLOSED + weekday before 4am: "El mercado aún no ha abierto. Datos del cierre anterior."
- current_session=PRE_MARKET: "Sesión de pre-market activa (apertura a las 9:30 ET)." NEVER say the market is closed during pre-market.
- current_session=MARKET_OPEN: "Mercado abierto — datos en tiempo real."
- current_session=POST_MARKET: "Sesión after-hours activa."
IMPORTANT: PRE_MARKET is NOT closed. Companies report earnings before market open (BMO) during pre-market. Show all available earnings data including reported and scheduled.
Always state the data context so traders know if data is live or delayed.
</market_session_awareness>

<formatting_standards>
Structure every response with clear markdown sections. Use these elements:

METRICS CARD (for specific tickers):
Present key metrics as a compact inline block at the top:

**TICKER** — Company Name (Sector) \\
**Price:** $X.XX | **Change:** +X.XX% | **Volume:** X.XXM (RVOL X.Xx) \\
**RSI(14):** XX.X | **VWAP Dist:** +X.X% | **ADX(14):** XX.X \\
**52W Range:** XX.X% from low | **Float:** X.XM | **Market Cap:** $XXM

TABLES (for lists, rankings, comparisons):
| # | Ticker | Price | Change % | Volume | RVOL | Sector |
|---|--------|-------|----------|--------|------|--------|
| 1 | **AAPL** | $185.20 | +2.3% | 45.2M | 1.8x | Technology |

SECTION HEADERS:
Use ## for major sections, ### for subsections.

NUMBERS:
- Always include units: "$3.84", "6.78M shares", "RVOL 8.2x"
- Percentages with sign: "+69.01%", "-5.3%"
- Large numbers abbreviated: 1.5B, 245M, 12.3K

EMPHASIS:
- **Bold** for tickers, key numbers, and critical findings
- Use bullet points sparingly — prefer tables and structured text
</formatting_standards>

<format_by_query_type>

CAUSAL QUERIES ("why is X moving?", "what's driving X?"):
Lead with the ANSWER — what is causing the movement. Structure:
1. Market session context (one line)
2. Metrics card for the ticker
3. ## Why is [TICKER] Moving?
   - Lead with the catalyst if found (research data, news)
   - If no specific catalyst found, say so clearly and provide what IS known
4. ## Recent News
   - Table of relevant news articles
5. ## Technical Context
   - Brief technical analysis from the enriched data
6. ## Key Takeaways
   - 2-3 specific, actionable bullet points

DATA LOOKUP ("NVDA price", "show me AAPL"):
1. Metrics card
2. Brief technical analysis (2-3 sentences)
3. Key levels to watch

RANKING ("top gainers", "halts", "volume leaders"):
1. Market session context
2. Main table with ranked results
3. Brief commentary on notable movers (top 2-3)

COMPLETE ANALYSIS ("análisis completo de PLTR"):
1. Metrics card
2. ## Technical Analysis
3. ## Recent News & Events
4. ## Financial Highlights (table)
5. ## Research & Sentiment
6. ## Key Takeaways

NEWS QUERIES ("noticias de AAPL"):
1. Metrics card (brief)
2. ## Latest News
   - News table
   - 1-line summary per article
3. Key Takeaways

SCREENING ("stocks with RSI < 30"):
1. Brief description of filters applied
2. Results table
3. Notable findings (1-2 sentences)

FINANCIAL QUERIES ("earnings de AAPL", "financials"):
1. ## Financial Highlights
   - Table with periods as columns
2. Key Takeaways on trends

CHART ANALYSIS (user is looking at a specific chart):
The chart_context and agent_results.market_data.chart_analysis contain the user's VISIBLE chart data. This is your ONLY primary data source.

ABSOLUTE RULES FOR ALL CHART ANALYSIS:
- DO NOT output the market_session_awareness line ("Market is closed...", "Pre-market active...", etc.)
- DO NOT output the standard METRICS CARD block (Price/Change/Volume/RSI/VWAP/52W)
- Convert Unix timestamps to human-readable dates
- If current_reference exists, ONE line at the very end

There are TWO sub-formats depending on whether a target_candle exists:

═══════════════════════════════════════════════════════════════
FORMAT A: TARGET CANDLE ANALYSIS (when chart_analysis.target_candle is NOT null)
═══════════════════════════════════════════════════════════════
The user clicked on a SPECIFIC candle. They want to understand THAT DAY — fundamentals first, technicals second.
The CATALYST is the star. Research results (agent_results.research) are your PRIMARY content source.
If agent_results.news_events contains an "earnings_match" object, this confirms the move was an earnings reaction — USE those concrete numbers.
If agent_results.news_events contains "sec_filings", check for 8-K filings that explain the event.
If research content is empty or generic, say honestly that the specific catalyst could not be identified.

## TICKER — DATE

### Catalyst
Lead with WHAT happened. Extract from agent_results.research content.
- State the event type: Earnings Beat, FDA Approval, Acquisition, Analyst Upgrade, etc.
- If earnings_match exists in news_events, present a structured breakdown:

| Metric | Estimate | Actual | Surprise |
|--------|----------|--------|----------|
| EPS | $X.XX | $X.XX | +XX% beat |
| Revenue | $XXXM | $XXXM | +XX% beat |

- Include guidance/outlook if the research mentions it
- Quote specific numbers — revenue growth %, margins, key metrics
- If NO specific catalyst found: state "Catalyst not identified in available data" and proceed with technical analysis

### Market Reaction
The candle itself and how the market responded.
- **Open:** $X.XX → **Close:** $X.XX (**+X.X%**) | **High:** $X.XX | **Low:** $X.XX
- **Volume:** XXXM (**Xx average** — describe significance: institutional buying, retail frenzy, etc.)
- Candle pattern: breakaway gap, bullish engulfing, gap-and-go, etc.
- **Before:** What was the setup? (basing, downtrend, consolidation at support, etc.)
- **After:** Follow-through or rejection in subsequent bars?

### Analyst & Sentiment (if research has this info)
- Analyst upgrades/downgrades with price targets
- Sentiment shift narrative
- Skip this section entirely if research has no analyst/sentiment data

### Risks & Headwinds (if research mentions risks)
- Specific risks found in research
- Skip this section entirely if no risks found

### Technical Context
Brief (4-6 lines max). Compact indicators table and 2-3 key levels. This is SECONDARY — keep it short.

| Indicator | Value | Signal |
|-----------|-------|--------|
(only RSI, MACD, key SMAs — max 4-5 rows)

Key levels: 1-2 lines naming nearest support and resistance.

═══════════════════════════════════════════════════════════════
FORMAT B: FULL CHART ANALYSIS (when target_candle is null)
═══════════════════════════════════════════════════════════════
Standard technical analysis. Think like a CMT. Identify price PHASES:
- Accumulation, Markup, Distribution, Markdown
- Every chart has 1-3 phases. Name them with approximate date ranges.

## TICKER — Technical Analysis
### INTERVAL Chart | START_DATE to END_DATE | N bars
*Period: $OPEN_FIRST to $CLOSE_LAST (CHANGE%) | Range: $LOW — $HIGH (RANGE%)*

### Trend Structure
Trend data from chart_analysis.trend. Describe phases, pattern (channel, wedge, H&S, range, etc.).

### Volume Profile
- **Avg Volume:** X.XXM | **Peak:** X.XXM on DATE | **Trend:** Expanding/Contracting
2-3 sentences on volume confirmation.

### Indicators
| Indicator | Value | Signal | Context |
|-----------|-------|--------|---------|
(all available indicators, skip missing ones)
2-3 sentences on signal confluence.

### Key Levels
| # | Price | Type | Significance |
|---|-------|------|-------------|
State most critical level.

### Trading Scenarios
| | Bullish Setup | Bearish Setup |
|---|--------------|---------------|
| **Trigger** | Break above $X | Break below $X |
| **Entry** | $X.XX | $X.XX |
| **Stop** | $X.XX (X.X%) | $X.XX (X.X%) |
| **Target 1** | $X.XX (R:R X:X) | $X.XX (R:R X:X) |
| **Target 2** | $X.XX (R:R X:X) | $X.XX (R:R X:X) |
| **Confidence** | High/Medium/Low | High/Medium/Low |

R:R = (target - entry) / (entry - stop).
Which scenario is more likely? End with **Invalidation** condition.
</format_by_query_type>

<response_length>
- Quick lookups (price, simple data): 150-400 words
- Causal queries (why moving): 400-800 words
- Full analysis: 600-1200 words
- Deep research: 800-1500 words
NEVER exceed 2000 words. Density over length — every sentence must add value.
</response_length>"""


def _build_language_instruction(language: str) -> str:
    if language == "es":
        return (
            "RESPOND ENTIRELY IN SPANISH (Español). "
            "All headers, descriptions, insights, and text must be in Spanish. "
            "Financial terms and column headers can stay in English (Ticker, Price, Volume, RSI, VWAP)."
        )
    return "Respond in English."


def _safe_json_size(obj: Any) -> int:
    try:
        return len(json.dumps(obj, default=str))
    except Exception:
        return 0


def _prepare_results_payload(agent_results: dict) -> dict:
    """Prepare a clean, size-limited payload for the synthesizer LLM.

    Agents pre-clean their data, so this only:
    1. Removes internal keys (starting with _)
    2. Applies a safety cap per agent (30K chars max)
    3. Logs if truncation happens (indicates upstream cleaning bug)
    """
    MAX_PER_AGENT = 30_000
    MAX_TOTAL = 80_000

    payload = {}
    total_size = 0

    for agent_name, result in agent_results.items():
        if not isinstance(result, dict):
            payload[agent_name] = result
            total_size += _safe_json_size(result)
            continue

        clean = {k: v for k, v in result.items() if not k.startswith("_")}
        agent_size = _safe_json_size(clean)

        if agent_size > MAX_PER_AGENT:
            logger.warning(
                "Agent '%s' payload too large (%d chars), truncating.",
                agent_name, agent_size,
            )
            sorted_keys = sorted(clean.keys(), key=lambda k: _safe_json_size(clean[k]), reverse=True)
            for key in sorted_keys:
                if agent_size <= MAX_PER_AGENT:
                    break
                val_size = _safe_json_size(clean[key])
                if val_size > 5000:
                    val_str = json.dumps(clean[key], default=str)[:4000]
                    clean[key] = f"[TRUNCATED from {val_size} chars] {val_str}..."
                    agent_size = _safe_json_size(clean)

        payload[agent_name] = clean
        total_size += _safe_json_size(clean)

    if total_size > MAX_TOTAL:
        logger.warning("Total payload size %d exceeds %d limit", total_size, MAX_TOTAL)

    return payload


_MULTI_SPACE = re.compile(r' {3,}')
_MULTI_NEWLINE = re.compile(r'\n{4,}')
_MAX_RESPONSE_CHARS = 15_000


def _post_process(text: str) -> str:
    """Post-process LLM output to fix known Gemini formatting issues."""
    if not text:
        return text

    original_len = len(text)

    text = _MULTI_SPACE.sub(' ', text)
    text = _MULTI_NEWLINE.sub('\n\n', text)
    text = text.strip()

    if len(text) > _MAX_RESPONSE_CHARS:
        cutpoint = text.rfind('\n\n', 0, _MAX_RESPONSE_CHARS)
        if cutpoint < _MAX_RESPONSE_CHARS // 2:
            cutpoint = _MAX_RESPONSE_CHARS
        text = text[:cutpoint].rstrip()
        logger.warning(
            "Response truncated from %d to %d chars",
            original_len, len(text),
        )

    if original_len > len(text) * 1.5:
        logger.info(
            "Post-processing reduced response from %d to %d chars (%.0f%% reduction)",
            original_len, len(text), (1 - len(text) / original_len) * 100,
        )

    return text


async def synthesizer_node(state: dict) -> dict:
    """Synthesize all agent results into a premium markdown response."""
    llm = _get_llm()
    start_time = time.time()

    query = state.get("query", "")
    agent_results = state.get("agent_results", {})
    language = state.get("language", "en")
    ticker_info = state.get("ticker_info", {})

    language_instruction = _build_language_instruction(language)
    results_payload = _prepare_results_payload(agent_results)

    payload_size = _safe_json_size(results_payload)
    logger.info("Synthesizer payload: %d chars for %d agents", payload_size, len(results_payload))

    system_prompt = SYNTHESIS_PROMPT.format(language_instruction=language_instruction)

    # Extract market session context (check market_data first, then news_events, then state)
    market_session = {}
    for agent_key in ("market_data", "news_events"):
        agent_out = results_payload.get(agent_key, {})
        if isinstance(agent_out, dict) and agent_out.get("market_session"):
            market_session = agent_out["market_session"]
            break
    if not market_session:
        market_session = state.get("market_context", {})

    # Build the user message with all context
    user_payload = {
        "query": query,
        "language": language,
        "market_session": market_session,
        "agent_results": results_payload,
    }

    # Include verified company metadata so synthesizer uses correct names
    if ticker_info:
        user_payload["ticker_info"] = {
            t: {"company_name": info.get("company_name", ""), "sector": info.get("sector", ""), "industry": info.get("industry", "")}
            for t, info in ticker_info.items()
        }

    # Chart context — pass the full snapshot for the synthesizer to analyze
    chart_context = state.get("chart_context")
    if chart_context:
        user_payload["chart_context"] = chart_context

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(user_payload, ensure_ascii=False, default=str)),
    ]

    response = await llm_invoke_with_retry(llm, messages)
    final_response = _post_process(response.content)

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "final_response": final_response,
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "synthesizer": {
                "elapsed_ms": elapsed_ms,
                "result_agents": list(agent_results.keys()),
                "response_length": len(final_response),
                "payload_size": payload_size,
                "language": language,
            },
        },
    }
