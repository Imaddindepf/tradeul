"""
Supervisor Agent - LLM-first query understanding.

The LLM (Gemini Flash) handles EVERYTHING in a single call:
  - Ticker extraction (understands company names, context, ANY language)
  - Agent routing (which specialists to invoke)
  - Execution planning

Tickers are then validated against the real Redis universe
to catch LLM hallucinations. No regex, no stopwords.
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
        "Real-time and historical price data, enriched snapshots with 100+ indicators, "
        "scanner categories (winners, losers, gappers, momentum, volume leaders, halts, etc.), "
        "historical daily bars, minute bars. "
        "Use for: top movers, gainers, losers, gappers, volume spikes, specific ticker quotes, "
        "historical daily/minute OHLCV data, price history."
    ),
    "news_events": (
        "Financial news from Benzinga, market events (breakouts, VWAP crosses, halts), "
        "earnings calendar with EPS/revenue estimates. "
        "Use for: news queries, what happened with X, earnings dates, events."
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
        "DuckDB-powered stock screener with 60+ indicators. Natural language to filters. "
        "Use for: screening stocks by criteria (RSI, volume, market cap, sector, etc.), "
        "finding stocks matching specific technical/fundamental criteria."
    ),
}

SCANNER_CATEGORIES = [
    "gappers_up", "gappers_down", "momentum_up", "momentum_down",
    "high_volume", "winners", "losers", "reversals", "anomalies",
    "new_highs", "new_lows", "post_market", "halts",
]

SYSTEM_PROMPT = """\
You are the supervisor of TradeUL, a professional stock trading analysis platform.

Your job: fully understand the user query, extract tickers, and route to the right agents.

AVAILABLE AGENTS:
{agents_desc}

MARKET CONTEXT:
{market_context}

SCANNER CATEGORIES: {scanner_categories}

TICKER EXTRACTION RULES:
1. Extract ALL stock ticker symbols mentioned or implied in the query.
2. Map company names to tickers: "tesla" → "TSLA", "apple" → "AAPL", "nvidia" → "NVDA", "amazon" → "AMZN", etc.
3. Recognize tickers in any format: $TSLA, TSLA, tsla, Tesla, etc.
4. DO NOT extract common words as tickers. "ha hecho" is Spanish for "has done", NOT the ticker HA.
5. "SEC" means Securities and Exchange Commission, NOT a ticker. Same for: CEO, CFO, IPO, ETF, GDP, CPI, FDA, EPS, RSI, AI (unless explicitly "$AI").
6. If no specific stocks are mentioned, return an empty tickers array.

ROUTING RULES:
1. Use the MINIMUM agents needed. Don't over-route.
2. For "top gainers", "winners", "best performers", "mejores acciones" → market_data
3. For "top losers", "worst", "peores" → market_data
4. For "gappers", "gap up/down", "premarket" → market_data
5. For specific ticker price/data → market_data
6. For screening with criteria (RSI < 30, volume > X) → screener
7. For news, events, "what happened", "noticias" → news_events
8. For earnings dates/calendar → news_events
9. For historical earnings (EPS, revenue, quarterly results, beats/misses) → financial
10. For SEC filings, 10-K, 10-Q, 8-K → financial
11. For fundamentals, income statements, balance sheets → financial
12. For deep research, sentiment, analyst opinions → research
13. For backtests, custom calculations → code_exec
14. When market is CLOSED, data is still available via last_close snapshots.
15. Match the user's language in your plan description.

ALREADY COMPLETED AGENTS:
{completed_info}

If all needed agents already ran, return empty agents list.

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


def _build_completed_info(agent_results: dict[str, Any]) -> str:
    if not agent_results:
        return "No agents have run yet."
    lines = []
    for agent, result in agent_results.items():
        if isinstance(result, dict) and "error" in result:
            lines.append(f"- {agent}: FAILED ({result['error'][:100]})")
        elif isinstance(result, dict):
            keys = [k for k in result.keys() if not k.startswith("_")]
            lines.append(f"- {agent}: completed (data keys: {keys})")
        else:
            lines.append(f"- {agent}: completed")
    return "\n".join(lines)


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


async def supervisor_node(state: dict) -> dict:
    """Analyze the query: extract tickers + decide agents in ONE LLM call."""
    query = state.get("query", "")
    agent_results = state.get("agent_results", {})
    iteration = state.get("iteration", 0)
    language = state.get("language", "en")

    max_iterations = 5
    if iteration >= max_iterations:
        logger.warning("Supervisor hit max iterations (%d), stopping.", max_iterations)
        return {
            **state,
            "active_agents": [],
            "current_agent": "__end__",
            "iteration": iteration,
        }

    completed_info = _build_completed_info(agent_results)
    agents_desc = _build_agents_desc()
    market_context = await _get_market_context_str(state)

    prompt = SYSTEM_PROMPT.format(
        agents_desc=agents_desc,
        market_context=market_context,
        scanner_categories=", ".join(SCANNER_CATEGORIES),
        completed_info=completed_info,
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
        logger.error("Supervisor LLM parse error: %s — raw: %s", e, raw if 'raw' in dir() else "N/A")
        decision = {
            "tickers": [],
            "plan": "Fallback: routing to market_data due to parse error",
            "agents": ["market_data"],
            "reasoning": f"LLM output could not be parsed: {e}",
        }

    # ── Ticker validation against Redis universe ──
    # The LLM extracted tickers from context. Now validate they're real.
    llm_tickers = decision.get("tickers", [])
    if llm_tickers:
        validated_tickers = await validate_tickers(llm_tickers)
        rejected = set(llm_tickers) - set(validated_tickers)
        if rejected:
            logger.info("Supervisor: LLM suggested tickers %s but rejected by universe: %s",
                        llm_tickers, rejected)
        llm_tickers = validated_tickers

    # On first iteration, set tickers. On subsequent, keep existing if LLM returns empty.
    existing_tickers = state.get("tickers", [])
    final_tickers = llm_tickers if llm_tickers else existing_tickers

    # ── Agent routing ──
    requested = decision.get("agents", [])
    pending = [a for a in requested if a in AVAILABLE_AGENTS and a not in agent_results]

    if not pending:
        return {
            **state,
            "tickers": final_tickers,
            "active_agents": [],
            "current_agent": "__end__",
            "plan": decision.get("plan", ""),
            "iteration": iteration + 1,
        }

    return {
        **state,
        "tickers": final_tickers,
        "active_agents": pending,
        "current_agent": pending[0],
        "plan": decision.get("plan", ""),
        "iteration": iteration + 1,
    }


def route_after_supervisor(state: dict) -> str:
    current = state.get("current_agent", "__end__")
    active = state.get("active_agents", [])

    if current == "__end__" or not active:
        return "synthesizer"

    if current in AVAILABLE_AGENTS:
        return current

    logger.warning("Unknown agent '%s', routing to synthesizer.", current)
    return "synthesizer"
