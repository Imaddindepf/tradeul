"""
LangGraph Multi-Agent Orchestrator V5 — Parallel Execution + Context Enrichment

Architecture:
  START -> query_planner -> [Send() fan-out to agents in parallel]
        -> context_enricher -> synthesizer -> END

The query_planner decides ALL agents needed in one LLM call.
Send() dispatches them all simultaneously.
State merges via the agent_results reducer (merge_dicts).
Context enricher auto-injects sector/industry/theme context.
Synthesizer produces the final response from merged results.
"""
from __future__ import annotations
import asyncio
import logging
import os

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from graph.state import AgentState
from agents.supervisor import query_planner_node, fan_out_to_agents
from agents.synthesizer import synthesizer_node
from agents.market_data import market_data_node
from agents.news_events import news_events_node
from agents.financial import financial_node
from agents.research import research_node
from agents.code_exec import code_exec_node
from agents.screener import screener_node
from agents.backtest import backtest_node
from agents.dilution import dilution_node
from agents.strategy_scanner import strategy_scanner_node
from agents.alert_compiler import alert_compiler_node
from agents.alert_manager import alert_manager_node
from agents.news_brief import news_brief_node
from agents.context_enricher import context_enricher_node

ALL_AGENTS = ["market_data", "news_events", "financial", "research", "code_exec", "screener", "backtest", "dilution", "strategy_scanner", "alert_compiler", "alert_manager", "news_brief"]

logger = logging.getLogger(__name__)

# Per-node wall-clock budget. Generous — the goal is to bound a hung MCP call
# or provider stall, not to clip legitimately slow work (research/backtest can
# be 60-90s). Overridable via env for tuning without a code change.
_NODE_TIMEOUT_S = float(os.getenv("AGENT_NODE_TIMEOUT_S", "150"))
_ENRICHER_TIMEOUT_S = float(os.getenv("AGENT_ENRICHER_TIMEOUT_S", "30"))
# El motor de briefs (Opus vía ai-news-brief) tarda 30-180s legítimamente;
# su cliente httpx ya corta a 240s, así que el guard va justo por encima.
_BRIEF_TIMEOUT_S = float(os.getenv("AGENT_BRIEF_NODE_TIMEOUT_S", "250"))


def _set_ctx(name: str, state):
    """Fija el contexto de telemetría (run/user/node) para las llamadas LLM
    de este nodo. Devuelve un token a restaurar, o None si no hay telemetría."""
    try:
        from telemetry import set_call_context
        return set_call_context(
            run_id=state.get("run_id", "") if isinstance(state, dict) else "",
            user_id=state.get("user_id", "") if isinstance(state, dict) else "",
            node=name,
        )
    except Exception:  # noqa: BLE001
        return None


def _reset_ctx(token) -> None:
    if token is None:
        return
    try:
        from telemetry import reset_call_context
        reset_call_context(token)
    except Exception:  # noqa: BLE001
        pass


def _instrument(name: str, fn):
    """Wrap a node so its LLM calls are attributed to run/user/node in
    telemetry. No timeout / no error capture — for planner & synthesizer,
    which have their own fallbacks."""
    async def wrapped(state):
        token = _set_ctx(name, state)
        try:
            return await fn(state)
        finally:
            _reset_ctx(token)

    wrapped.__name__ = getattr(fn, "__name__", name)
    return wrapped


def _guard(name: str, fn, timeout: float):
    """Wrap an agent node so a timeout or crash becomes a captured, visible
    error in `agent_results` instead of hanging the fan-out barrier forever,
    and its LLM calls are attributed to run/user/node in telemetry.

    The synthesizer reads these status markers, so a failed specialist yields
    "los datos de X no estaban disponibles" rather than a silent omission or
    an indefinitely stalled run.
    """
    async def wrapped(state):
        token = _set_ctx(name, state)
        try:
            return await asyncio.wait_for(fn(state), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error("node %s exceeded %.0fs budget — captured as tool_error", name, timeout)
            status = {"status": "tool_error", "error": f"{name} timed out after {timeout:.0f}s"}
        except Exception as exc:  # noqa: BLE001
            logger.exception("node %s crashed — captured as tool_error", name)
            status = {"status": "tool_error", "error": f"{name} failed: {type(exc).__name__}: {exc}"}
        finally:
            _reset_ctx(token)
        return {
            "agent_results": {name: status},
            "execution_metadata": {name: {"status": status["status"]}},
        }

    wrapped.__name__ = getattr(fn, "__name__", name)
    return wrapped


def build_graph(checkpointer=None) -> StateGraph:
    if checkpointer is None:
        checkpointer = MemorySaver()
    graph = StateGraph(AgentState)

    _AGENT_NODES = {
        "market_data": market_data_node,
        "news_events": news_events_node,
        "financial": financial_node,
        "research": research_node,
        "code_exec": code_exec_node,
        "screener": screener_node,
        "backtest": backtest_node,
        "dilution": dilution_node,
        "strategy_scanner": strategy_scanner_node,
        "alert_compiler": alert_compiler_node,
        "alert_manager": alert_manager_node,
        "news_brief": news_brief_node,
    }
    _NODE_TIMEOUTS = {"news_brief": _BRIEF_TIMEOUT_S}

    graph.add_node("query_planner", _instrument("query_planner", query_planner_node))
    for _name, _fn in _AGENT_NODES.items():
        graph.add_node(_name, _guard(_name, _fn, _NODE_TIMEOUTS.get(_name, _NODE_TIMEOUT_S)))
    graph.add_node("context_enricher", _guard("context_enricher", context_enricher_node, _ENRICHER_TIMEOUT_S))
    graph.add_node("synthesizer", _instrument("synthesizer", synthesizer_node))

    graph.add_edge(START, "query_planner")

    graph.add_conditional_edges(
        "query_planner",
        fan_out_to_agents,
        ALL_AGENTS + ["synthesizer", END],
    )

    for agent_name in ALL_AGENTS:
        graph.add_edge(agent_name, "context_enricher")

    graph.add_edge("context_enricher", "synthesizer")
    graph.add_edge("synthesizer", END)

    return graph.compile(checkpointer=checkpointer)


_graph = None
_checkpointer_pool = None


async def init_graph():
    """Build the graph with a durable Postgres checkpointer when available.

    Uses a psycopg connection pool with health checks so that a database
    restart doesn't leave the checkpointer holding a dead connection
    (a single from_conn_string() connection never reconnects, which used
    to crash every request with "the connection is closed").

    Falls back to in-memory checkpoints (single process, lost on restart)
    if CHECKPOINT_DB_URL is unset or the database is unreachable.
    Called once from the FastAPI lifespan.
    """
    global _graph, _checkpointer_pool
    if _graph is not None:
        return _graph

    checkpointer = None
    db_url = os.getenv("CHECKPOINT_DB_URL", "").strip()
    if db_url:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from psycopg_pool import AsyncConnectionPool

            _checkpointer_pool = AsyncConnectionPool(
                db_url,
                min_size=1,
                max_size=4,
                open=False,
                check=AsyncConnectionPool.check_connection,
                # autocommit + prepare_threshold=0 are required by AsyncPostgresSaver
                kwargs={"autocommit": True, "prepare_threshold": 0},
            )
            await _checkpointer_pool.open(wait=True, timeout=15)
            checkpointer = AsyncPostgresSaver(_checkpointer_pool)
            await checkpointer.setup()
            logger.info("Using Postgres checkpointer with connection pool (durable, auto-reconnect)")
        except Exception as exc:
            logger.warning("Postgres checkpointer unavailable (%s); falling back to MemorySaver", exc)
            if _checkpointer_pool is not None:
                try:
                    await _checkpointer_pool.close()
                except Exception:
                    pass
                _checkpointer_pool = None
            checkpointer = None

    if checkpointer is None:
        logger.warning("Using in-memory checkpointer: state is lost on restart")

    _graph = build_graph(checkpointer)
    return _graph


async def close_graph():
    """Release the checkpointer connection pool on shutdown."""
    global _checkpointer_pool
    if _checkpointer_pool is not None:
        try:
            await _checkpointer_pool.close()
        except Exception:
            pass
        _checkpointer_pool = None


def get_graph():
    global _graph
    if _graph is None:
        # Sync fallback for callers outside the app lifespan (e.g. scripts).
        _graph = build_graph()
    return _graph
