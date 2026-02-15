"""
LangGraph Multi-Agent Orchestrator
START -> supervisor -> [specialists] -> supervisor -> synthesizer -> END
"""
from __future__ import annotations
import os
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from graph.state import AgentState
from agents.supervisor import supervisor_node, route_after_supervisor
from agents.synthesizer import synthesizer_node
from agents.market_data import market_data_node
from agents.news_events import news_events_node
from agents.financial import financial_node
from agents.research import research_node
from agents.code_exec import code_exec_node
from agents.screener import screener_node


def build_graph() -> StateGraph:
    # MemorySaver provides in-process checkpointing (thread-safe, no external deps).
    # For production persistence, switch to RedisSaver with Redis Stack (RediSearch module).
    checkpointer = MemorySaver()
    graph = StateGraph(AgentState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("market_data", market_data_node)
    graph.add_node("news_events", news_events_node)
    graph.add_node("financial", financial_node)
    graph.add_node("research", research_node)
    graph.add_node("code_exec", code_exec_node)
    graph.add_node("screener", screener_node)
    graph.add_node("synthesizer", synthesizer_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "market_data": "market_data",
            "news_events": "news_events",
            "financial": "financial",
            "research": "research",
            "code_exec": "code_exec",
            "screener": "screener",
            "synthesizer": "synthesizer",
            "end": END,
        },
    )
    for name in ["market_data", "news_events", "financial", "research", "code_exec", "screener"]:
        graph.add_edge(name, "supervisor")
    graph.add_edge("synthesizer", END)

    return graph.compile(checkpointer=checkpointer)


_graph = None

def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
