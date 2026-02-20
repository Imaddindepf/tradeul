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
from agents.context_enricher import context_enricher_node

ALL_AGENTS = ["market_data", "news_events", "financial", "research", "code_exec", "screener"]


def build_graph() -> StateGraph:
    checkpointer = MemorySaver()
    graph = StateGraph(AgentState)

    graph.add_node("query_planner", query_planner_node)
    graph.add_node("market_data", market_data_node)
    graph.add_node("news_events", news_events_node)
    graph.add_node("financial", financial_node)
    graph.add_node("research", research_node)
    graph.add_node("code_exec", code_exec_node)
    graph.add_node("screener", screener_node)
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


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
