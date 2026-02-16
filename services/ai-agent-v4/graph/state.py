"""
Shared state schema for the LangGraph multi-agent orchestrator.
All agents read/write to this shared state.
"""
from __future__ import annotations
from typing import TypedDict, Annotated, Any, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


def merge_dicts(left: dict, right: dict) -> dict:
    """Merge two dicts, right overwrites left."""
    merged = left.copy()
    merged.update(right)
    return merged


class AgentState(TypedDict):
    """Shared state flowing through the LangGraph execution graph.

    This state is checkpointed in Redis after each node execution,
    enabling time-travel debugging and crash recovery.
    """

    # ── Conversation ──
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Query ──
    query: str                           # Original user query
    language: str                        # Detected language (es/en)
    tickers: list[str]                   # Tickers extracted by supervisor LLM + validated against Redis

    # ── Planning ──
    plan: str                            # Supervisor's execution plan
    active_agents: list[str]             # Which specialist agents to activate
    current_agent: str                   # Currently executing agent

    # ── Results ──
    agent_results: Annotated[dict[str, Any], merge_dicts]  # Results from each agent
    charts: list[dict]                   # Generated charts (base64 or cache keys)
    tables: list[dict]                   # Generated tables (for display)

    # ── Context ──
    market_context: dict                 # Current market session, time, etc.
    memory_context: list[dict]           # Retrieved memories from RAG

    # ── Workflow ──
    workflow_id: Optional[str]           # If executing a saved workflow
    trigger_context: Optional[dict]      # If activated by a reactive trigger
    node_config: Optional[dict]          # Per-node configuration overrides

    # ── Output ──
    final_response: str                  # Synthesized response for the user
    execution_metadata: dict             # Timing, tokens used, agents activated

    # ── Control ──
    iteration_count: int                 # Safety counter for loops
    error: Optional[str]                 # Last error message
