"""
Agent Module V3 - Direct Function Calling (2026)
================================================
- NO intent router (no MiniLM, no cold start)
- NO regex patterns (no fragility)
- Gemini Flash for routing (cheap, fast, understands variations)
- Gemini Pro for code generation
- Self-correction loop
"""

# V3: Direct Function Calling
from .core_v3 import MarketAgentV3 as MarketAgent, AgentResult

from .tool_definitions import MARKET_TOOLS
from .tools import execute_tool

# AgentStep for websocket handler compatibility
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class AgentStep:
    step_type: str
    content: str
    data: Optional[Dict[str, Any]] = None
    tool_name: Optional[str] = None

__all__ = [
    "MarketAgent",
    "AgentResult", 
    "AgentStep",
    "MARKET_TOOLS",
    "execute_tool",
]
