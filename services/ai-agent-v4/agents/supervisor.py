"""
Query Planner (Supervisor V2) - Parallel-first query understanding.

Single LLM call determines ALL agents needed + tickers, then the graph
uses Send() to fan-out to all agents in parallel.

No more sequential loop: supervisor -> agent -> supervisor -> agent.
Now: planner -> [all agents in parallel] -> synthesizer.
"""
import json
import logging
from typing import Any

from agents._mcp_tools import call_mcp_tool
from agents._ticker_utils import validate_tickers

logger = logging.getLogger(__name__)

_llm = None

AVAILABLE_AGENTS = {
    "market_data": (
        "Real-time and historical price data, enriched snapshots with 145+ indicators, "
        "scanner categories (winners, losers, gappers, momentum, volume leaders, halts, etc.), "
        "historical daily bars, minute bars, dynamic filtering on full ticker universe. "
        "Use for: top movers, gainers, losers, gappers, volume spikes, specific ticker quotes, "
        "historical daily/minute OHLCV data, price history, stocks matching technical criteria."
    ),
    "news_events": (
        "Financial news from Benzinga, real-time market events (85+ types: breakouts, VWAP crosses, "
        "halts, volume spikes, momentum shifts, MA crosses, BB events), historical events from "
        "TimescaleDB (60-day retention), earnings calendar with EPS/revenue estimates. "
        "Use for: news queries, what happened with X, earnings dates, market events, "
        "which stocks had breakouts/halts/volume spikes on a given day."
    ),
    "financial": (
        "Fundamental data: income statements, balance sheets, ratios, SEC filings (10-K, 10-Q, 8-K, S-1). "
        "Use for: financial analysis, SEC filings, fundamentals, revenue, EPS history, quarterly results."
    ),
    "research": (
        "Deep research using Grok (X.com search) or Gemini Pro. "
        "Analyst ratings, social sentiment, comprehensive analysis. "
        "Use for: deep research, sentiment, analyst opinions, comprehensive analysis."
    ),
    "code_exec": (
        "Python code generation for custom calculations, backtests, data transformations. "
        "Use for: backtesting, custom calculations, data analysis, comparisons."
    ),
    "screener": (
        "DuckDB-powered stock screener with 60+ indicators on daily data. Natural language to filters. "
        "Use for: screening stocks by criteria (RSI, volume, market cap, sector, etc.), "
        "finding stocks matching specific technical/fundamental criteria from historical daily data."
    ),
}

SCANNER_CATEGORIES = [
    "gappers_up", "gappers_down", "momentum_up", "momentum_down",
    "high_volume", "winners", "losers", "reversals", "anomalies",
    "new_highs", "new_lows", "post_market", "halts",
]

SYSTEM_PROMPT = """\
You are the query planner of TradeUL, a professional stock trading analysis platform.

Your job: fully understand the user query, extract tickers, and decide ALL agents needed.
ALL selected agents will run IN PARALLEL — choose them all at once.

AVAILABLE AGENTS:
{agents_desc}

MARKET CONTEXT:
{market_context}

SCANNER CATEGORIES: {scanner_categories}

TICKER EXTRACTION RULES:
1. Extract ALL stock ticker symbols mentioned or implied in the query.
2. Map company names to tickers: "tesla" → "TSLA", "apple" → "AAPL", "nvidia" → "NVDA", etc.
3. Recognize tickers in any format: $TSLA, TSLA, tsla, Tesla, etc.
4. DO NOT extract common words as tickers. "ha hecho" is Spanish for "has done", NOT ticker HA.
5. "SEC" = Securities and Exchange Commission, NOT a ticker. Same for: CEO, CFO, IPO, ETF, GDP, CPI, FDA, EPS, RSI, AI.
6. If no specific stocks are mentioned, return empty tickers array.

ROUTING RULES:
1. Select ALL agents needed for a complete answer. They run in parallel.
2. For "top gainers/losers", "winners", "gappers" → market_data
3. For specific ticker price/data → market_data
4. For screening with criteria (RSI < 30, volume > X, etc.) → screener
5. For news, "what happened", "noticias" → news_events
6. For earnings dates/calendar, "who reports earnings" → news_events
7. For historical earnings (EPS, revenue, quarterly results) → financial
8. For SEC filings, 10-K, 10-Q, 8-K → financial
9. For fundamentals, income/balance sheets → financial
10. For deep research, sentiment, analyst opinions → research
11. For backtests, custom calculations → code_exec
12. For "complete analysis of X" → market_data + news_events + financial (all 3)
13. For "X with sentiment" → add research alongside other agents
14. Match the user's language in your plan description.

Respond ONLY with valid JSON:
{{
    "tickers": ["TSLA", "AAPL"],
    "plan": "Brief execution plan (in user's language)",
    "agents": ["agent1", "agent2"],
    "reasoning": "Why these agents and tickers"
}}
"""


def _get_llm():
    global _llm
    if _llm is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.0,
            max_output_tokens=512,
        )
    return _llm


def _build_agents_desc() -> str:
    return "\n".join(f"- {name}: {desc}" for name, desc in AVAILABLE_AGENTS.items())


async def _get_market_context_str(state: dict) -> str:
    mc = state.get("market_context", {})
    if mc and mc.get("current_session"):
        session = mc.get("current_session", "UNKNOWN")
        is_trading = mc.get("is_trading_day", True)
        return (
            f"Session: {session}, Trading day: {is_trading}. "
            f"Note: When market is CLOSED, last-session data is still available via last_close snapshots."
        )

    try:
        session_data = await call_mcp_tool("scanner", "get_market_session", {})
        if isinstance(session_data, dict) and "error" not in session_data:
            session = session_data.get("current_session", "UNKNOWN")
            is_trading = session_data.get("is_trading_day", True)
            trading_date = session_data.get("trading_date", "unknown")
            return (
                f"Session: {session}, Date: {trading_date}, Trading day: {is_trading}. "
                f"Note: When CLOSED, last-session data is available."
            )
    except Exception as e:
        logger.warning("Failed to get market session: %s", e)

    return "Session: UNKNOWN. Assume last-session data is available."


async def query_planner_node(state: dict) -> dict:
    """Analyze the query and decide ALL agents to invoke in parallel.

    This replaces the old sequential supervisor. It runs ONCE,
    decides everything, and the graph fans out to all agents at once.
    """
    query = state.get("query", "")
    language = state.get("language", "en")

    agents_desc = _build_agents_desc()
    market_context = await _get_market_context_str(state)

    prompt = SYSTEM_PROMPT.format(
        agents_desc=agents_desc,
        market_context=market_context,
        scanner_categories=", ".join(SCANNER_CATEGORIES),
    )

    llm = _get_llm()
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"[Language: {language}] {query}"},
    ]

    try:
        response = await llm.ainvoke(messages)
        raw = response.content.strip()

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        decision = json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Query planner LLM parse error: %s — raw: %s", e, raw if 'raw' in dir() else "N/A")
        decision = {
            "tickers": [],
            "plan": "Fallback: routing to market_data due to parse error",
            "agents": ["market_data"],
            "reasoning": f"LLM output could not be parsed: {e}",
        }

    llm_tickers = decision.get("tickers", [])
    if llm_tickers:
        validated_tickers = await validate_tickers(llm_tickers)
        rejected = set(llm_tickers) - set(validated_tickers)
        if rejected:
            logger.info("Planner: rejected tickers %s (not in universe)", rejected)
        llm_tickers = validated_tickers

    requested_agents = [a for a in decision.get("agents", []) if a in AVAILABLE_AGENTS]
    if not requested_agents:
        requested_agents = ["market_data"]

    logger.info(
        "Query planner: tickers=%s, agents=%s (parallel), plan=%s",
        llm_tickers, requested_agents, decision.get("plan", "")[:100],
    )

    return {
        **state,
        "tickers": llm_tickers,
        "active_agents": requested_agents,
        "plan": decision.get("plan", ""),
        "market_context": state.get("market_context", {}),
    }


def fan_out_to_agents(state: dict):
    """Conditional edge function: fan-out to all active agents in parallel via Send().

    Returns a list of Send() objects for parallel execution,
    or routes directly to synthesizer if no agents needed.
    """
    from langgraph.types import Send

    agents = state.get("active_agents", [])

    if not agents:
        return "synthesizer"

    return [Send(agent, state) for agent in agents]


# Keep backward compatibility — the old name still works if referenced
supervisor_node = query_planner_node


def route_after_supervisor(state: dict) -> str:
    """Legacy routing function — kept for backward compatibility.
    Not used in v5 parallel graph, but kept so old code doesn't break."""
    return "synthesizer"
