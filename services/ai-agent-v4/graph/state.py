"""
Shared state schema for the LangGraph multi-agent orchestrator V5.

Key change from V4: removed `current_agent` and `iteration_count` since
the parallel Send() architecture no longer loops through supervisor.
The `active_agents` field is still used by the query planner to tell
the fan_out function which agents to dispatch.
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

    This state is checkpointed after each node execution,
    enabling time-travel debugging and crash recovery.
    """

    # ── Conversation ──
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Query ──
    query: str                           # Original user query
    language: str                        # Detected language (es/en)
    tickers: list[str]                   # Tickers extracted by planner LLM + validated against Redis
    ticker_info: dict[str, dict]         # Company metadata per ticker {TICKER: {company_name, sector, ...}}

    # ── Planning ──
    plan: str                            # Query planner's execution plan
    active_agents: list[str]             # Which specialist agents to activate (for Send fan-out)

    # ── Results ──
    agent_results: Annotated[dict[str, Any], merge_dicts]  # Results from each agent (merged in parallel)
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
    execution_metadata: Annotated[dict, merge_dicts]  # Timing, tokens used, agents activated

    # ── Thematic ──
    theme_tags: list[str]                # Canonical theme tags resolved by supervisor (e.g. ["robotics", "memory_chips"])

    # ── Chart Analysis ──
    chart_context: Optional[dict]        # Chart snapshot from frontend (ticker, bars, indicators, drawings)

    # ── Control ──
    mode: str                            # Execution mode: "auto" | "quick" | "deep"
    clarification: Optional[dict]        # Clarification options when confidence is low
    clarification_hint: str              # Rewritten query from user's clarification choice
    error: Optional[str]                 # Last error message
