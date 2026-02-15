"""
Supervisor Agent - Intelligent query router with market context awareness.

Uses Gemini Flash to analyze the user query alongside real market state
and routes to the minimum set of specialist agents needed.
"""
import json
import logging
from typing import Any

from agents._mcp_tools import call_mcp_tool

logger = logging.getLogger(__name__)

_llm = None

AVAILABLE_AGENTS = {
    "market_data": (
        "Real-time and historical price data, enriched snapshots with 100+ indicators, "
        "scanner categories (winners, losers, gappers, momentum, volume leaders, halts, etc.). "
        "Use for: top movers, gainers, losers, gappers, volume spikes, specific ticker quotes."
    ),
    "news_events": (
        "Financial news from Benzinga, market events (breakouts, VWAP crosses, halts), "
        "earnings calendar with EPS/revenue estimates. "
        "Use for: news queries, what happened with X, earnings, events."
    ),
    "financial": (
        "Fundamental data: income statements, balance sheets, ratios, SEC filings, "
        "dilution analysis, cash runway. "
        "Use for: financial analysis, dilution, SEC filings, fundamentals."
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

# Scanner categories available in the platform
SCANNER_CATEGORIES = [
    "gappers_up", "gappers_down", "momentum_up", "momentum_down",
    "high_volume", "winners", "losers", "reversals", "anomalies",
    "new_highs", "new_lows", "post_market", "halts",
]

SYSTEM_PROMPT = """\
You are the supervisor agent of TradeUL, a professional stock trading analysis platform.

Your job: analyze the user query + market context and decide which specialist agents to invoke.

AVAILABLE AGENTS:
{agents_desc}

MARKET CONTEXT:
{market_context}

SCANNER CATEGORIES AVAILABLE (for market_data agent):
{scanner_categories}

ROUTING RULES:
1. Analyze the query and determine the MINIMUM agents needed. Don't over-route.
2. For "top gainers", "winners", "best performers", "mejores acciones" → market_data (uses winners category)
3. For "top losers", "worst", "peores" → market_data (uses losers category)
4. For "gappers", "gap up/down", "premarket" → market_data (uses gappers categories)
5. For specific ticker analysis ($AAPL, NVDA, etc.) → market_data for data, optionally financial/news
6. For screening with criteria (RSI < 30, volume > X, etc.) → screener
7. For news, events, "what happened" → news_events
8. For deep research, sentiment, analyst opinions → research
9. For backtests, custom calculations → code_exec
10. When market is CLOSED, market_data still has last-session data (last_close). Use it.
11. Match the user's language in your plan description.

ALREADY COMPLETED AGENTS:
{completed_info}

IMPORTANT: If all needed agents already ran, return empty agents list to proceed to synthesis.

Respond ONLY with valid JSON (no markdown, no explanation):
{{
    "plan": "Brief execution plan (in the user's language)",
    "agents": ["agent1", "agent2"],
    "reasoning": "Why these agents (English ok)"
}}
"""


def _get_llm():
    """Lazily create the Gemini Flash LLM for routing decisions."""
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
    """Summarize which agents have already returned results."""
    if not agent_results:
        return "No agents have run yet."
    lines = []
    for agent, result in agent_results.items():
        if isinstance(result, dict) and "error" in result:
            lines.append(f"- {agent}: FAILED ({result['error'][:100]})")
        elif isinstance(result, dict):
            # Show what data keys are available
            keys = [k for k in result.keys() if not k.startswith("_")]
            lines.append(f"- {agent}: completed (data keys: {keys})")
        else:
            lines.append(f"- {agent}: completed")
    return "\n".join(lines)


def _build_agents_desc() -> str:
    """Format agent descriptions for the system prompt."""
    return "\n".join(f"- {name}: {desc}" for name, desc in AVAILABLE_AGENTS.items())


async def _get_market_context_str(state: dict) -> str:
    """Build a human-readable market context string."""
    # Try to get cached market session from state
    mc = state.get("market_context", {})
    if mc and mc.get("current_session"):
        session = mc.get("current_session", "UNKNOWN")
        is_trading = mc.get("is_trading_day", True)
        return (
            f"Session: {session}, Trading day: {is_trading}. "
            f"Note: When market is CLOSED, last-session data is still available via last_close snapshots."
        )

    # Fetch from MCP if not in state
    try:
        session_data = await call_mcp_tool("scanner", "get_market_session", {})
        if isinstance(session_data, dict) and "error" not in session_data:
            session = session_data.get("current_session", "UNKNOWN")
            is_trading = session_data.get("is_trading_day", True)
            trading_date = session_data.get("trading_date", "unknown")
            return (
                f"Session: {session}, Date: {trading_date}, Trading day: {is_trading}. "
                f"Note: When CLOSED, last-session data is available. Scanner categories contain last session's data."
            )
    except Exception as e:
        logger.warning("Failed to get market session: %s", e)

    return "Session: UNKNOWN. Assume last-session data is available."


async def supervisor_node(state: dict) -> dict:
    """Analyze the query and decide which agents to invoke next."""
    query = state.get("query", "")
    agent_results = state.get("agent_results", {})
    iteration = state.get("iteration", 0)
    language = state.get("language", "en")

    # Guard against infinite loops
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

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        decision = json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Supervisor LLM parse error: %s — raw: %s", e, raw if 'raw' in dir() else "N/A")
        # Fallback: route to market_data
        decision = {
            "plan": "Fallback: routing to market_data due to parse error",
            "agents": ["market_data"],
            "reasoning": f"LLM output could not be parsed: {e}",
        }

    # Filter out agents that already ran successfully
    requested = decision.get("agents", [])
    pending = [a for a in requested if a in AVAILABLE_AGENTS and a not in agent_results]

    if not pending:
        # All requested agents already ran — we are done
        return {
            **state,
            "active_agents": [],
            "current_agent": "__end__",
            "plan": decision.get("plan", ""),
            "iteration": iteration + 1,
        }

    return {
        **state,
        "active_agents": pending,
        "current_agent": pending[0],
        "plan": decision.get("plan", ""),
        "iteration": iteration + 1,
    }


def route_after_supervisor(state: dict) -> str:
    """Conditional edge: return the name of the next agent node to execute."""
    current = state.get("current_agent", "__end__")
    active = state.get("active_agents", [])

    if current == "__end__" or not active:
        return "synthesizer"

    if current in AVAILABLE_AGENTS:
        return current

    logger.warning("Unknown agent '%s', routing to synthesizer.", current)
    return "synthesizer"
