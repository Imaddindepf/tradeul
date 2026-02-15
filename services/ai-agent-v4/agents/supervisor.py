"""Supervisor Agent - Routes queries to specialist agents using Gemini Flash."""
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_llm = None

AVAILABLE_AGENTS = {
    "market_data": "Real-time and historical price data, quotes, OHLCV, technicals, indicators",
    "news_events": "Financial news, earnings calendars, economic events, sentiment analysis",
    "financial": "Fundamental data: income statements, balance sheets, ratios, valuations",
    "research": "Analyst ratings, price targets, institutional holdings, SEC filings",
    "code_exec": "Execute Python code for custom calculations, backtests, data transformations",
    "screener": "Screen and filter stocks by criteria: market cap, sector, price, volume, metrics",
}

SYSTEM_PROMPT = """You are a supervisor agent that routes user queries to specialist agents.

Available agents and their capabilities:
{agents_desc}

ROUTING RULES:
1. Analyze the user query and determine which agents are needed.
2. Order agents by dependency - e.g. market_data before code_exec if code needs price data.
3. Use the MINIMUM number of agents needed. Do not route to agents unnecessarily.
4. If the query is ambiguous, prefer market_data and financial as defaults for stock queries.
5. For screening/filtering requests, always include screener.
6. For news or event-driven queries, always include news_events.
7. For code execution, calculations, or backtesting, include code_exec.
8. For analyst opinions or SEC filings, include research.

ALREADY COMPLETED:
{completed_info}

Respond ONLY with valid JSON (no markdown, no explanation):
{{
    "plan": "Brief description of the execution plan",
    "agents": ["agent1", "agent2"],
    "reasoning": "Why these agents were chosen"
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
            lines.append(f"- {agent}: FAILED ({result['error']})")
        else:
            lines.append(f"- {agent}: completed successfully")
    return "\n".join(lines)


def _build_agents_desc() -> str:
    """Format agent descriptions for the system prompt."""
    return "\n".join(f"- {name}: {desc}" for name, desc in AVAILABLE_AGENTS.items())


async def supervisor_node(state: dict) -> dict:
    """Analyze the query and decide which agents to invoke next.

    Reads state keys:
        - query (str): the user question
        - agent_results (dict): results from agents that already ran
        - iteration (int): current iteration count

    Returns updated state with:
        - active_agents (list[str]): agents to run this round
        - current_agent (str): first agent to execute
        - plan (str): execution plan description
        - iteration (int): incremented iteration
    """
    query = state.get("query", "")
    agent_results = state.get("agent_results", {})
    iteration = state.get("iteration", 0)

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

    prompt = SYSTEM_PROMPT.format(
        agents_desc=agents_desc,
        completed_info=completed_info,
    )

    llm = _get_llm()
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": query},
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
    """Conditional edge: return the name of the next agent node to execute.

    If current_agent is '__end__' or active_agents is empty, route to the
    synthesizer (or end). Otherwise return the current_agent name so
    LangGraph follows the correct branch.
    """
    current = state.get("current_agent", "__end__")
    active = state.get("active_agents", [])

    if current == "__end__" or not active:
        return "synthesizer"

    if current in AVAILABLE_AGENTS:
        return current

    logger.warning("Unknown agent '%s', routing to synthesizer.", current)
    return "synthesizer"
