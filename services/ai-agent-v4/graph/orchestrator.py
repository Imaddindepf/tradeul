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
from agents.context_enricher import context_enricher_node

ALL_AGENTS = ["market_data", "news_events", "financial", "research", "code_exec", "screener", "backtest", "dilution", "strategy_scanner"]

logger = logging.getLogger(__name__)


def build_graph(checkpointer=None) -> StateGraph:
    if checkpointer is None:
        checkpointer = MemorySaver()
    graph = StateGraph(AgentState)

    graph.add_node("query_planner", query_planner_node)
    graph.add_node("market_data", market_data_node)
    graph.add_node("news_events", news_events_node)
    graph.add_node("financial", financial_node)
    graph.add_node("research", research_node)
    graph.add_node("code_exec", code_exec_node)
    graph.add_node("screener", screener_node)
    graph.add_node("backtest", backtest_node)
    graph.add_node("dilution", dilution_node)
    graph.add_node("strategy_scanner", strategy_scanner_node)
    graph.add_node("context_enricher", context_enricher_node)
    graph.add_node("synthesizer", synthesizer_node)

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
