"""
Market Agent Core
=================
Main agent using Gemini Function Calling for intelligent tool selection.

Architecture:
1. User sends query
2. Gemini analyzes and decides which tool(s) to call
3. Agent executes tools and collects results
4. Gemini generates final response with results

Benefits:
- Single LLM call for decision (vs 3-5 before)
- Native tool selection (no manual classification)
- Cleaner, more maintainable code
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
import pytz
import structlog

from google import genai
from google.genai import types

from .tools import MARKET_TOOLS, execute_tool

logger = structlog.get_logger(__name__)
ET = pytz.timezone('America/New_York')


@dataclass
class AgentStep:
    """A step in agent execution (for UI feedback)."""
    id: str
    type: str  # 'thinking', 'tool', 'result'
    title: str
    description: str = ""
    status: str = "pending"  # 'pending', 'running', 'complete', 'error'
    details: Optional[str] = None


@dataclass
class AgentResult:
    """Result from agent processing."""
    success: bool
    response: str
    data: Dict[str, Any] = field(default_factory=dict)
    charts: Dict[str, bytes] = field(default_factory=dict)
    tools_used: List[str] = field(default_factory=list)
    steps: List[AgentStep] = field(default_factory=list)
    execution_time: float = 0.0
    error: Optional[str] = None


class MarketAgent:
    """
    Intelligent market analysis agent using Gemini Function Calling.
    
    The agent:
    1. Receives user query
    2. Uses Gemini to decide which tools to call
    3. Executes tools in parallel when possible
    4. Returns formatted response with data/charts
    
    Usage:
        agent = MarketAgent(api_key="...")
        result = await agent.process("top gainers de hoy")
    """
    
    SYSTEM_PROMPT = """You are TradeUL's AI financial analyst. You help users analyze market data.

CAPABILITIES (via tools):
- get_market_snapshot: Real-time data for ~1000 active tickers
- get_historical_data: Minute-level OHLCV for any date (1760+ days available)
- get_top_movers: Pre-aggregated gainers/losers for any date/time
- classify_synthetic_sectors: Create thematic ETFs (Nuclear, AI, EV, etc.)
- research_ticker: Deep research with news, X.com, web search
- execute_analysis: Custom Python code in sandbox
- get_ticker_info: Basic ticker lookup

RULES:
1. ALWAYS use tools to get data - never make up numbers
2. For "WHY/POR QUÉ" questions about price moves → use research_ticker
   - "why is NVDA up?" → research_ticker(symbol='NVDA')
   - "por qué subió el sector solar?" → research_ticker for top solar stocks
   - "what happened to X?" → research_ticker
   - "noticias de X" → research_ticker
3. For "top gainers/losers" → use get_market_snapshot or get_top_movers
4. For "sectores sintéticos/thematic ETFs" → use classify_synthetic_sectors
5. For historical analysis → use get_historical_data or get_top_movers
6. For complex analysis → use execute_analysis with Python code

IMPORTANT: NEVER say "I can't explain why stocks moved". You CAN research with research_ticker!

RESPONSE FORMAT:
- Be concise and data-driven
- Always cite the source (scanner, historical, research)
- Format numbers nicely (%, $, commas)
- If multiple tools needed, call them all

Current time: {current_time} ET
Market session: {market_session}
"""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash"
    ):
        """
        Initialize agent.
        
        Args:
            api_key: Google AI API key
            model: Gemini model to use
        """
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self._sandbox = None
        self._context: Dict[str, Any] = {}
    
    def _build_tools(self) -> List[types.Tool]:
        """Convert tool definitions to Gemini format."""
        function_declarations = []
        
        for tool in MARKET_TOOLS:
            fd = types.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters=tool.get("parameters")
            )
            function_declarations.append(fd)
        
        return [types.Tool(function_declarations=function_declarations)]
    
    def _get_system_prompt(self, market_context: Dict = None) -> str:
        """Build system prompt with current context."""
        now = datetime.now(ET)
        session = "UNKNOWN"
        
        if market_context:
            session = market_context.get("session", "UNKNOWN")
        else:
            hour = now.hour
            if 4 <= hour < 9.5:
                session = "PRE-MARKET"
            elif 9.5 <= hour < 16:
                session = "REGULAR"
            elif 16 <= hour < 20:
                session = "POST-MARKET"
            else:
                session = "CLOSED"
        
        return self.SYSTEM_PROMPT.format(
            current_time=now.strftime("%Y-%m-%d %H:%M"),
            market_session=session
        )
    
    async def process(
        self,
        query: str,
        market_context: Dict = None,
        conversation_history: List[Dict] = None,
        on_step: Callable = None
    ) -> AgentResult:
        """
        Process user query using function calling.
        
        Args:
            query: User's question
            market_context: Current market session info
            conversation_history: Previous messages for context
            on_step: Callback for step updates
        
        Returns:
            AgentResult with response, data, and charts
        """
        import time
        start_time = time.time()
        
        steps: List[AgentStep] = []
        tools_used: List[str] = []
        collected_data: Dict[str, Any] = {}
        collected_charts: Dict[str, bytes] = {}
        tool_errors: List[str] = []
        
        # Helper to emit steps
        async def emit_step(step: AgentStep):
            steps.append(step)
            if on_step:
                await on_step(step)
        
        try:
            # Step 1: Reasoning
            reasoning_step = AgentStep(
                id="reasoning",
                type="thinking",
                title="Analyzing query",
                description="Understanding what you need...",
                status="running"
            )
            await emit_step(reasoning_step)
            
            # Build conversation
            contents = []
            
            # Add history if available
            if conversation_history:
                for msg in conversation_history[-5:]:
                    role = "user" if msg["role"] == "user" else "model"
                    contents.append(types.Content(
                        role=role,
                        parts=[types.Part(text=msg["content"])]
                    ))
            
            # Add current query
            contents.append(types.Content(
                role="user",
                parts=[types.Part(text=query)]
            ))
            
            # Call Gemini with tools
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=self._get_system_prompt(market_context),
                    tools=self._build_tools(),
                    temperature=0.7,
                    max_output_tokens=4096
                )
            )
            
            # Update reasoning step
            reasoning_step.status = "complete"
            reasoning_step.description = "Query analyzed"
            await emit_step(reasoning_step)
            
            # Process response - handle function calls
            if response.candidates and response.candidates[0].content:
                parts = response.candidates[0].content.parts
                
                for part in parts:
                    # Check for function call
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        tool_name = fc.name
                        tool_args = dict(fc.args) if fc.args else {}
                        
                        logger.info("tool_called", tool=tool_name, args=tool_args)
                        tools_used.append(tool_name)
                        
                        # Emit tool step
                        tool_step = AgentStep(
                            id=f"tool_{tool_name}",
                            type="tool",
                            title=f"Using {tool_name}",
                            description="Executing...",
                            status="running"
                        )
                        await emit_step(tool_step)
                        
                        # Execute tool
                        self._context["llm_client"] = self
                        tool_result = await execute_tool(tool_name, tool_args, self._context)
                        
                        # Update step
                        if tool_result.get("success"):
                            tool_step.status = "complete"
                            
                            # Build description based on tool type
                            if tool_name == "research_ticker":
                                research_data = tool_result.get("data", {})
                                citations_count = len(research_data.get("citations", []))
                                tool_step.description = f"Research complete ({citations_count} sources)"
                            elif tool_name == "classify_synthetic_sectors":
                                sector_count = tool_result.get("sector_count", 0)
                                tool_step.description = f"Created {sector_count} synthetic ETFs"
                            else:
                                tool_step.description = f"Got {tool_result.get('count', 'N/A')} results"
                            
                            # Collect data
                            if "data" in tool_result:
                                collected_data[tool_name] = tool_result["data"]
                            if "sectors" in tool_result:
                                collected_data["sector_performance"] = tool_result["sectors"]
                            if "tickers" in tool_result:
                                collected_data["sector_tickers"] = tool_result["tickers"]
                        else:
                            tool_step.status = "error"
                            error_msg = tool_result.get("error", "Failed")
                            tool_step.description = error_msg
                            tool_errors.append(f"{tool_name}: {error_msg}")
                        
                        await emit_step(tool_step)
            
            # Generate final response with tool results
            if tools_used and collected_data:
                # Special case: research_ticker - use Grok's response directly (already formatted with citations)
                if "research_ticker" in tools_used and "research_ticker" in collected_data:
                    research_data = collected_data["research_ticker"]
                    if research_data.get("content"):
                        response_text = research_data["content"]
                        # Add citations at the end if available
                        citations = research_data.get("citations", [])
                        if citations:
                            response_text += "\n\n---\n**Sources:**\n"
                            for i, cite in enumerate(citations[:15], 1):
                                response_text += f"\n[{i}] {cite}"
                    else:
                        response_text = "Research completed but no content available."
                else:
                    # For other tools, summarize with LLM
                    results_summary = self._summarize_results(collected_data)
                    
                    # Get final response from LLM
                    final_prompt = f"""Based on the tool results, provide a helpful response to the user.

USER QUERY: {query}

TOOL RESULTS:
{results_summary}

Provide a detailed, informative response. Include key numbers, insights, and cite sources when available."""

                    final_response = self.client.models.generate_content(
                        model=self.model,
                        contents=[types.Content(
                            role="user",
                            parts=[types.Part(text=final_prompt)]
                        )],
                        config=types.GenerateContentConfig(
                            temperature=0.7,
                            max_output_tokens=4096
                        )
                    )
                    
                    response_text = final_response.text if final_response.text else "Analysis complete."
            else:
                # Direct response (no tools needed)
                response_text = response.text if response.text else "I couldn't process that request."
            
            execution_time = time.time() - start_time
            
            # Determine success based on tool errors
            has_errors = len(tool_errors) > 0
            error_message = "; ".join(tool_errors) if has_errors else None
            
            return AgentResult(
                success=not has_errors or len(collected_data) > 0,  # Success if we got some data
                response=response_text,
                data=collected_data,
                charts=collected_charts,
                tools_used=tools_used,
                steps=steps,
                execution_time=execution_time,
                error=error_message
            )
            
        except Exception as e:
            logger.error("agent_error", error=str(e))
            return AgentResult(
                success=False,
                response=f"Error processing request: {str(e)}",
                error=str(e),
                steps=steps,
                execution_time=time.time() - start_time
            )
    
    def _summarize_results(self, data: Dict[str, Any]) -> str:
        """Summarize tool results for LLM context."""
        import pandas as pd
        
        summaries = []
        
        for key, value in data.items():
            if isinstance(value, pd.DataFrame):
                if len(value) > 0:
                    # Show first few rows as summary
                    sample = value.head(10).to_string()
                    summaries.append(f"=== {key} ({len(value)} rows) ===\n{sample}")
            elif isinstance(value, dict):
                # Special handling for research_ticker - include full content
                if key == "research_ticker" and "content" in value:
                    content = value.get("content", "")
                    citations = value.get("citations", [])
                    summaries.append(f"=== RESEARCH RESULTS ===\n{content}")
                    if citations:
                        # Include first 10 citations
                        citations_text = "\n".join([f"[{i+1}] {url}" for i, url in enumerate(citations[:10])])
                        summaries.append(f"=== SOURCES ===\n{citations_text}")
                else:
                    # For other dicts, allow more content (2000 chars)
                    summaries.append(f"=== {key} ===\n{json.dumps(value, indent=2, default=str)[:2000]}")
            elif isinstance(value, list):
                summaries.append(f"=== {key} ({len(value)} items) ===")
        
        return "\n\n".join(summaries) if summaries else "No data collected"
    
    # Provide LLM client interface for synthetic sectors
    @property 
    def client(self):
        return self._client
    
    @client.setter
    def client(self, value):
        self._client = value
