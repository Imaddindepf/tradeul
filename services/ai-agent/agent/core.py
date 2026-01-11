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
from datetime import datetime, timedelta
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
    type: str  # 'reasoning', 'tool', 'result', 'code'
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
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)  # Full tool call info including code
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
    
    SYSTEM_PROMPT = """You are TradeUL's AI financial analyst. Respond in the same language as the user.

CAPABILITIES (via tools):
- get_market_snapshot: Real-time data for ~1000 active tickers (price, change, volume, sector, RVOL)
- get_historical_data: Minute-level OHLCV for any date (1760+ days available)
- get_top_movers: Pre-aggregated gainers/losers for any date/time range
- classify_synthetic_sectors: Create thematic ETFs (Nuclear, AI, EV, Biotech, Cannabis, Space, etc.)
- research_ticker: Deep research with news, X.com, web search - USE FOR "WHY" QUESTIONS
- execute_analysis: Custom Python/SQL code in sandbox for complex analysis
- get_ticker_info: Basic ticker lookup (price, market cap, sector)

TOOL SELECTION (choose the simplest that works):

1. REAL-TIME / TODAY:
   - "top gainers/losers today" → get_market_snapshot(filter_type='gainers'/'losers')
   - "current price of X" → get_ticker_info(symbol='X')
   - "sectores sintéticos/thematic ETFs" → classify_synthetic_sectors(date='today')

2. HISTORICAL (yesterday, specific dates):
   - "top movers yesterday/friday" → get_top_movers(date='...')
   - "after-hours movers" → get_top_movers(date='...', start_hour=16)
   - "pre-market leaders" → get_top_movers(date='...', start_hour=4, end_hour=9)

3. WHY/NEWS QUESTIONS:
   - "why is NVDA up?" → research_ticker(symbol='NVDA')
   - "por qué subió X?" → research_ticker(symbol='X')
   - "noticias de X" → research_ticker(symbol='X')
   - "what happened to X?" → research_ticker(symbol='X')

4. COMPLEX ANALYSIS (use execute_analysis with SQL):
   - Relative strength vs SPY/QQQ
   - Stocks that held during pullbacks
   - Correlation analysis
   - Custom multi-condition filters
   - Minute-by-minute comparisons
   
   IMPORTANT: Use historical_query(sql) inside execute_analysis - 10x faster than Python loops.

RESPONSE FORMAT:
- Data first, explanation after
- Tables for multiple items
- Numbers: +15.3%, $123.45, 1.2M
- Cite source: "(Source: research_ticker)"

NEVER:
- Make up numbers without tools
- Say "I can't explain" - USE research_ticker!
- Say "I can't analyze" - USE execute_analysis!

Current time: {current_time} ET
Market session: {market_session}
Last trading day: {last_trading_day}
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
        
        # Calculate last trading day (skip weekends)
        last_trading = now.date()
        if last_trading.weekday() == 6:  # Sunday
            last_trading = last_trading - timedelta(days=2)  # Friday
        elif last_trading.weekday() == 5:  # Saturday
            last_trading = last_trading - timedelta(days=1)  # Friday
        elif now.hour < 9 or (now.hour == 9 and now.minute < 30):
            # Before market open, last trading day is yesterday (or Friday if Monday)
            last_trading = last_trading - timedelta(days=1)
            if last_trading.weekday() == 6:  # Was Sunday
                last_trading = last_trading - timedelta(days=2)
            elif last_trading.weekday() == 5:  # Was Saturday
                last_trading = last_trading - timedelta(days=1)
        
        return self.SYSTEM_PROMPT.format(
            current_time=now.strftime("%A, %Y-%m-%d %H:%M"),  # e.g., "Sunday, 2026-01-11 22:24"
            market_session=session,
            last_trading_day=last_trading.strftime("%A, %Y-%m-%d")  # e.g., "Friday, 2026-01-09"
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
        tool_calls: List[Dict[str, Any]] = []  # Full tool call details
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
                type="reasoning",
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
            
            # Call Gemini with tools (advanced retry with backoff and reformulation)
            parts = None
            retry_configs = [
                {"temp": 0.7, "wait": 0, "reformulate": False},
                {"temp": 0.5, "wait": 1, "reformulate": False},  # Lower temp, wait 1s
                {"temp": 0.9, "wait": 2, "reformulate": True},   # Higher temp, reformulate query
                {"temp": 0.7, "wait": 3, "reformulate": True},   # Final attempt
            ]
            
            current_query = query
            for attempt, config in enumerate(retry_configs):
                if config["wait"] > 0:
                    import asyncio
                    await asyncio.sleep(config["wait"])
                
                # Reformulate query on later attempts
                if config["reformulate"] and attempt > 1:
                    current_query = f"Please analyze this request carefully and use execute_analysis if needed: {query}"
                    # Update reasoning step to show retry
                    reasoning_step.description = f"Retrying with reformulated query (attempt {attempt + 1})"
                    await emit_step(reasoning_step)
                
                # Update contents with current query
                retry_contents = contents[:-1] + [types.Content(
                    role="user",
                    parts=[types.Part(text=current_query)]
                )]
                
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=retry_contents,
                    config=types.GenerateContentConfig(
                        system_instruction=self._get_system_prompt(market_context),
                        tools=self._build_tools(),
                        temperature=config["temp"],
                        max_output_tokens=4096
                    )
                )
                
                if response.candidates and response.candidates[0].content:
                    parts = response.candidates[0].content.parts
                    if parts:
                        logger.info("response_success", attempt=attempt + 1)
                        break  # Got valid response
                
                logger.warning("empty_response_retry", attempt=attempt + 1, temp=config["temp"])
            
            # Process response - handle function calls
            if not parts:
                response_text = "No se pudo procesar la consulta. Intenta reformularla."
                logger.warning("empty_response_after_retries")
                reasoning_step.status = "complete"
                reasoning_step.description = f"Failed after {attempt + 1} attempts"
                await emit_step(reasoning_step)
            
            # Extract any reasoning text from Gemini's response
            reasoning_text_parts = []
            function_calls_found = []
            
            for part in (parts or []):
                # Capture text parts as reasoning
                if hasattr(part, 'text') and part.text:
                    reasoning_text_parts.append(part.text)
                
                # Check for function call
                if hasattr(part, 'function_call') and part.function_call:
                    function_calls_found.append(part.function_call)
            
            # Update reasoning step with actual reasoning from Gemini
            if reasoning_text_parts or function_calls_found:
                reasoning_details = []
                
                # Add Gemini's reasoning text if any
                if reasoning_text_parts:
                    reasoning_details.append("💭 " + " ".join(reasoning_text_parts)[:500])
                
                # Add tool selection reasoning
                if function_calls_found:
                    for fc in function_calls_found:
                        tool_name = fc.name
                        if tool_name == "execute_analysis":
                            reasoning_details.append(f"📊 Selecting execute_analysis for custom data analysis")
                            if fc.args and fc.args.get("description"):
                                reasoning_details.append(f"   → {fc.args['description']}")
                        elif tool_name == "get_market_snapshot":
                            reasoning_details.append(f"📈 Selecting get_market_snapshot for real-time data")
                        elif tool_name == "get_top_movers":
                            reasoning_details.append(f"🔝 Selecting get_top_movers for historical rankings")
                        elif tool_name == "research_ticker":
                            reasoning_details.append(f"🔍 Selecting research_ticker for deep analysis")
                        else:
                            reasoning_details.append(f"🛠️ Selecting {tool_name}")
                
                reasoning_step.status = "complete"
                reasoning_step.title = "Query Analyzed"
                reasoning_step.description = f"Selected {len(function_calls_found)} tool(s)"
                reasoning_step.details = "\n".join(reasoning_details) if reasoning_details else None
                await emit_step(reasoning_step)
            else:
                reasoning_step.status = "complete"
                reasoning_step.description = "Direct response (no tools needed)"
                await emit_step(reasoning_step)
            
            # Now process each function call
            for fc in function_calls_found:
                        tool_name = fc.name
                        tool_args = dict(fc.args) if fc.args else {}
                        
                        logger.info("tool_called", tool=tool_name, args=tool_args)
                        tools_used.append(tool_name)
                        tool_calls.append({"name": tool_name, "args": tool_args})
                        
                        # Emit tool step
                        tool_step = AgentStep(
                            id=f"tool_{tool_name}",
                            type="tool",
                            title=f"Using {tool_name}",
                            description="Executing...",
                            status="running"
                        )
                        await emit_step(tool_step)
                        
                        # Execute tool with SELF-HEALING LOOP (Cursor-style)
                        self._context["llm_client"] = self
                        tool_result = await execute_tool(tool_name, tool_args, self._context)
                        
                        # SELF-HEALING: If execute_analysis fails, retry with error context
                        MAX_SELF_HEAL_ATTEMPTS = 2
                        heal_attempt = 0
                        original_code = tool_args.get("code", "")
                        
                        while (not tool_result.get("success") 
                               and tool_name == "execute_analysis" 
                               and heal_attempt < MAX_SELF_HEAL_ATTEMPTS):
                            heal_attempt += 1
                            error_msg = tool_result.get("error", "Unknown error")
                            
                            logger.info("self_healing_attempt", attempt=heal_attempt, error=error_msg[:200])
                            
                            # Update step to show we're retrying
                            tool_step.description = f"Error detected, auto-correcting (attempt {heal_attempt})..."
                            await emit_step(tool_step)
                            
                            # Ask LLM to fix the code
                            fix_prompt = f"""The following Python code failed with an error. Fix it and return ONLY the corrected code.

ORIGINAL CODE:
```python
{original_code}
```

ERROR:
{error_msg}

IMPORTANT RULES:
1. Use historical_query(sql) for SQL queries, not default_api.historical_query
2. Use get_minute_bars(date, symbol) - NOT get_minute_bars(symbol, date)
3. Use save_output(data, 'name') to save results
4. Do NOT redefine existing functions
5. Return ONLY the corrected Python code, no explanations

CORRECTED CODE:"""

                            # Get fixed code from LLM
                            fix_response = self.client.models.generate_content(
                                model=self.model,
                                contents=[types.Content(role="user", parts=[types.Part(text=fix_prompt)])],
                                config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=2048)
                            )
                            
                            if fix_response.candidates and fix_response.candidates[0].content:
                                fixed_text = fix_response.candidates[0].content.parts[0].text
                                # Extract code from markdown blocks if present
                                if "```python" in fixed_text:
                                    fixed_code = fixed_text.split("```python")[1].split("```")[0].strip()
                                elif "```" in fixed_text:
                                    fixed_code = fixed_text.split("```")[1].split("```")[0].strip()
                                else:
                                    fixed_code = fixed_text.strip()
                                
                                if fixed_code and fixed_code != original_code:
                                    # Update tool_args and retry
                                    tool_args["code"] = fixed_code
                                    original_code = fixed_code
                                    tool_calls[-1]["args"]["code"] = fixed_code  # Update for display
                                    
                                    logger.info("self_healing_retry", attempt=heal_attempt)
                                    tool_result = await execute_tool(tool_name, tool_args, self._context)
                                else:
                                    logger.warning("self_healing_no_change", attempt=heal_attempt)
                                    break
                            else:
                                logger.warning("self_healing_empty_response", attempt=heal_attempt)
                                break
                        
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
                            elif tool_name == "execute_analysis":
                                # Count results from outputs
                                output_count = 0
                                outputs = tool_result.get("outputs", {})
                                if outputs:
                                    for filename, file_bytes in outputs.items():
                                        if filename.endswith('.parquet') and file_bytes:
                                            try:
                                                import pandas as _pd
                                                import io as _io
                                                df = _pd.read_parquet(_io.BytesIO(file_bytes))
                                                output_count += len(df)
                                            except:
                                                pass
                                attempts = tool_result.get("attempts", 1)
                                corrected = tool_result.get("corrected", False)
                                if corrected:
                                    tool_step.description = f"Analysis complete ({output_count} rows, auto-corrected)"
                                else:
                                    tool_step.description = f"Analysis complete ({output_count} rows)"
                            else:
                                tool_step.description = f"Got {tool_result.get('count', 'N/A')} results"
                            
                            # Collect data
                            if "data" in tool_result:
                                collected_data[tool_name] = tool_result["data"]
                            if "sectors" in tool_result:
                                collected_data["sector_performance"] = tool_result["sectors"]
                            if "tickers" in tool_result:
                                collected_data["sector_tickers"] = tool_result["tickers"]
                            # Capture execute_analysis results (stdout and output files)
                            if "stdout" in tool_result and tool_result["stdout"]:
                                collected_data[f"{tool_name}_output"] = tool_result["stdout"]
                            if "outputs" in tool_result and tool_result["outputs"]:
                                # Convert Parquet files to readable DataFrames
                                import pandas as _pd
                                import io as _io
                                for filename, file_bytes in tool_result["outputs"].items():
                                    if filename.endswith('.parquet') and file_bytes:
                                        try:
                                            df = _pd.read_parquet(_io.BytesIO(file_bytes))
                                            collected_data[filename.replace('.parquet', '')] = df
                                        except Exception as e:
                                            logger.warning("parquet_read_error", file=filename, error=str(e))
                                    elif filename.endswith('.json') and file_bytes:
                                        try:
                                            collected_data[filename.replace('.json', '')] = json.loads(file_bytes.decode('utf-8'))
                                        except:
                                            pass
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
                tool_calls=tool_calls,
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
            elif isinstance(value, str) and value.strip():
                # Handle string outputs (like stdout from execute_analysis)
                summaries.append(f"=== {key} ===\n{value[:3000]}")
        
        return "\n\n".join(summaries) if summaries else "No data collected"
    
    # Provide LLM client interface for synthetic sectors
    @property 
    def client(self):
        return self._client
    
    @client.setter
    def client(self, value):
        self._client = value
