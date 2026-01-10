"""
Agent Module - Function Calling Architecture
=============================================
Core agent implementation using Gemini's native function calling.
Single LLM call decides and executes tools.
"""

from .core import MarketAgent, AgentStep, AgentResult
from .tools import MARKET_TOOLS, execute_tool

__all__ = ["MarketAgent", "AgentStep", "AgentResult", "MARKET_TOOLS", "execute_tool"]
