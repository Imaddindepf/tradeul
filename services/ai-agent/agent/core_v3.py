"""
Market Agent V3 - Direct Function Calling (2026)
=================================================

ELIMINADO:
- Intent Router (MiniLM local) - 52s cold start
- Regex patterns - frágil, falla con "tdy" vs "today"

NUEVO:
- Gemini Flash para routing (barato, rápido, entiende variaciones)
- Function Calling nativo - el LLM decide qué tool usar
- Sin cold start, sin regex

Costo estimado: ~$0.001 por query de routing
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Tuple
from datetime import datetime
import pytz
import structlog

from google import genai
from google.genai import types

from .schema import get_analysis_system_prompt, get_self_correction_prompt, get_current_date
from .tools import execute_tool
from .tool_definitions import MARKET_TOOLS

logger = structlog.get_logger(__name__)
ET = pytz.timezone('America/New_York')


@dataclass
class AgentResult:
    """Result from agent processing."""
    success: bool
    response: str
    data: Dict[str, Any] = field(default_factory=dict)
    charts: Dict[str, bytes] = field(default_factory=dict)
    tools_used: List[str] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    execution_time: float = 0.0
    error: Optional[str] = None
    self_corrections: int = 0


class MarketAgentV3:
    """
    Market Agent with Direct Function Calling.
    
    NO intent router. NO regex. NO local embeddings.
    Gemini Flash decides which tool to use based on descriptions.
    """
    
    MAX_SELF_CORRECTIONS = 3
    BASE_TEMPERATURE = 0.1
    RETRY_TEMPERATURE = 0.05
    
    # Models
    ROUTING_MODEL = "gemini-2.0-flash"  # Cheap, fast for routing
    ANALYSIS_MODEL = "gemini-2.5-pro"    # Smart for code generation
    
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self._context: Dict[str, Any] = {}
        
        logger.info(
            "MarketAgentV3 initialized",
            routing_model=self.ROUTING_MODEL,
            analysis_model=self.ANALYSIS_MODEL,
            architecture="direct_function_calling"
        )
    
    async def process(
        self,
        query: str,
        user_id: str = "anonymous",
        on_step: Optional[Callable] = None,
        market_context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict]] = None,
    ) -> AgentResult:
        """
        Process a user query.
        
        Flow:
        1. Gemini Flash decides which tool to use (Function Calling)
        2. Execute the tool
        3. If execute_analysis, use Gemini Pro for code generation
        4. Self-correct on errors
        """
        start_time = datetime.now()
        
        try:
            result = await self._process_with_function_calling(
                query=query,
                market_context=market_context or {},
            )
            
            result.execution_time = (datetime.now() - start_time).total_seconds()
            return result
            
        except Exception as e:
            logger.error("agent_error", error=str(e), query=query[:50])
            return AgentResult(
                success=False,
                response=f"Error: {str(e)}",
                error=str(e)
            )
    
    async def _process_with_function_calling(
        self,
        query: str,
        market_context: Dict[str, Any],
    ) -> AgentResult:
        """
        Direct function calling - no router needed.
        
        The LLM sees all tools and picks the best one.
        """
        tools_used = []
        tool_calls = []
        data = {}
        charts = {}
        self_corrections = 0
        
        # System prompt that helps the LLM choose correctly
        system_prompt = self._build_routing_prompt(market_context)
        
        # All tools available
        tool_definitions = self._build_all_tools()
        
        # Step 1: Let Gemini Flash decide which tool to use
        logger.info("routing_with_flash", query=query[:50])
        
        response = await self.client.aio.models.generate_content(
            model=self.ROUTING_MODEL,
            contents=[{"role": "user", "parts": [{"text": query}]}],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=tool_definitions,
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode="any")
                ),
                temperature=0.1,
                max_output_tokens=2048
            )
        )
        
        if not response.candidates or not response.candidates[0].content:
            return AgentResult(
                success=False,
                response="No response from model",
                error="Empty response"
            )
        
        parts = response.candidates[0].content.parts
        if not parts:
            return AgentResult(
                success=False,
                response="No response parts",
                error="Empty parts"
            )
        
        response_text = ""
        
        for part in parts:
            if hasattr(part, 'text') and part.text:
                response_text += part.text
            
            if hasattr(part, 'function_call') and part.function_call:
                fc = part.function_call
                tool_name = fc.name
                tool_args = dict(fc.args) if fc.args else {}
                
                tools_used.append(tool_name)
                tool_calls.append({"name": tool_name, "args": tool_args})
                
                logger.info("tool_selected", tool=tool_name, by="flash")
                
                # Special handling for execute_analysis
                if tool_name == "execute_analysis":
                    result = await self._handle_execute_analysis(
                        query=query,
                        initial_args=tool_args,
                    )
                    data.update(result.get("data", {}))
                    charts.update(result.get("charts", {}))
                    self_corrections = result.get("self_corrections", 0)
                    
                    if result.get("error"):
                        return AgentResult(
                            success=False,
                            response=f"Analysis failed: {result['error']}",
                            data=data,
                            tools_used=tools_used,
                            tool_calls=tool_calls,
                            error=result["error"],
                            self_corrections=self_corrections
                        )
                else:
                    # Execute other tools directly
                    try:
                        tool_result = await execute_tool(tool_name, tool_args, self._context)
                        
                        # Convert DataFrame to JSON-serializable format
                        tool_result = self._make_json_serializable(tool_result)
                        data[tool_name] = tool_result
                    except Exception as e:
                        logger.error("tool_error", tool=tool_name, error=str(e))
                        return AgentResult(
                            success=False,
                            response=f"Tool error: {str(e)}",
                            error=str(e),
                            tools_used=tools_used,
                            tool_calls=tool_calls
                        )
        
        # Generate final response - let LLM interpret the data
        final_response = await self._generate_interpreted_response(query, data, tools_used)
        
        return AgentResult(
            success=True,
            response=final_response,
            data=data,
            charts=charts,
            tools_used=tools_used,
            tool_calls=tool_calls,
            self_corrections=self_corrections
        )
    
    async def _handle_execute_analysis(
        self,
        query: str,
        initial_args: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle execute_analysis with Gemini Pro and self-correction.
        """
        data = {}
        charts = {}
        self_corrections = 0
        last_error = None
        last_code = None
        
        # Build system prompt with data schema
        system_prompt = get_analysis_system_prompt("daily")
        system_prompt += "\n\nCRITICAL: You MUST call execute_analysis(code) with Python code that uses historical_query(sql) and save_output(result, 'name')."
        
        # Tool definition for execute_analysis
        tool_def = types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name="execute_analysis",
                description="Execute Python/SQL code to analyze market data.",
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code with DuckDB SQL"
                        }
                    },
                    "required": ["code"]
                }
            )
        ])
        
        for attempt in range(self.MAX_SELF_CORRECTIONS + 1):
            messages = [{"role": "user", "parts": [{"text": query}]}]
            
            # Add correction context on retry
            if attempt > 0 and last_error and last_code:
                correction = get_self_correction_prompt(query, last_code, last_error)
                messages.append({"role": "user", "parts": [{"text": correction}]})
                self_corrections += 1
                logger.info("self_correction", attempt=attempt)
            
            temperature = self.RETRY_TEMPERATURE if attempt > 0 else self.BASE_TEMPERATURE
            
            # Use Pro for code generation
            response = await self.client.aio.models.generate_content(
                model=self.ANALYSIS_MODEL,
                contents=messages,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=[tool_def],
                    tool_config=types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(mode="any")
                    ),
                    temperature=temperature,
                    max_output_tokens=4096
                )
            )
            
            if not response.candidates or not response.candidates[0].content:
                continue
            
            parts = response.candidates[0].content.parts
            if not parts:
                continue
            
            for part in parts:
                if hasattr(part, 'function_call') and part.function_call:
                    fc = part.function_call
                    if fc.name == "execute_analysis":
                        code = dict(fc.args).get("code", "")
                        
                        try:
                            self._context["llm_client"] = self
                            result = await execute_tool("execute_analysis", {"code": code}, self._context)
                            
                            if not result.get("success", True):
                                last_error = result.get("error", "Unknown error")
                                last_code = code
                                continue
                            
                            # Extract data from outputs
                            if result.get("outputs"):
                                import pandas as pd
                                import numpy as np
                                import io
                                
                                for filename, file_bytes in result["outputs"].items():
                                    if filename.endswith('.parquet') and file_bytes:
                                        try:
                                            df = pd.read_parquet(io.BytesIO(file_bytes))
                                            key = filename.replace('.parquet', '')
                                            records = self._convert_df_to_json(df)
                                            data[key] = records
                                            logger.info("output_processed", file=filename, rows=len(df))
                                        except Exception as e:
                                            logger.warning("parquet_error", error=str(e))
                                    elif filename.endswith('.png') and file_bytes:
                                        charts[filename.replace('.png', '')] = file_bytes
                            
                            # Check for empty results
                            if self._is_empty_result(data) and attempt < self.MAX_SELF_CORRECTIONS:
                                last_error = "Query returned 0 results. Check your SQL logic and date ranges."
                                last_code = code
                                data = {}
                                continue
                            
                            return {
                                "data": data,
                                "charts": charts,
                                "self_corrections": self_corrections
                            }
                            
                        except Exception as e:
                            last_error = str(e)
                            last_code = code
                            continue
        
        return {
            "data": data,
            "charts": charts,
            "error": last_error,
            "self_corrections": self_corrections
        }
    
    def _convert_df_to_json(self, df) -> List[Dict]:
        """Convert DataFrame to JSON-serializable records."""
        import pandas as pd
        import numpy as np
        
        records = df.to_dict('records')
        for record in records:
            for k, v in record.items():
                if isinstance(v, (np.integer, np.int64)):
                    record[k] = int(v)
                elif isinstance(v, (np.floating, np.float64)):
                    record[k] = float(v)
                elif isinstance(v, np.bool_):
                    record[k] = bool(v)
                elif pd.isna(v):
                    record[k] = None
                elif hasattr(v, 'isoformat'):
                    record[k] = v.isoformat()
        return records
    
    def _make_json_serializable(self, obj: Any) -> Any:
        """Recursively convert all numpy/pandas types to JSON-serializable Python types."""
        import pandas as pd
        import numpy as np
        
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                # Skip chart bytes
                if k == "chart" and isinstance(v, bytes):
                    result[k] = v
                elif k == "data" and hasattr(v, 'to_dict'):
                    # DataFrame
                    result[k] = self._convert_df_to_json(v)
                else:
                    result[k] = self._make_json_serializable(v)
            return result
        elif isinstance(obj, list):
            return [self._make_json_serializable(item) for item in obj]
        elif isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif pd.isna(obj) if hasattr(pd, 'isna') else False:
            return None
        elif hasattr(obj, 'isoformat'):
            return obj.isoformat()
        elif hasattr(obj, 'to_dict'):
            # DataFrame or Series
            return self._convert_df_to_json(obj)
        else:
            return obj
    
    def _is_empty_result(self, data: Dict) -> bool:
        """Check if all results are empty."""
        if not data:
            return True
        return all(
            (isinstance(v, list) and len(v) == 0) or
            (isinstance(v, dict) and not v)
            for v in data.values()
        )
    
    def _build_routing_prompt(self, market_context: Dict) -> str:
        """Build system prompt for routing decisions."""
        current_date = get_current_date()
        session = market_context.get("session", "UNKNOWN")
        
        return f"""You are TradeUL's AI routing agent. Your job is to pick the RIGHT tool for the user's question.

CURRENT CONTEXT:
- Date: {current_date}
- Market session: {session}

CRITICAL ROUTING RULES:

1. **REALTIME DATA** (use get_market_snapshot):
   - "top gainers today", "top stocks now", "what's moving", "precio actual"
   - "top stocks tdy", "gainers ahora", "live prices"
   - ANY query about CURRENT/TODAY prices without historical calculations
   - Keywords: today, now, ahora, hoy, live, current, tdy, 2day

2. **HISTORICAL ANALYSIS** (use execute_analysis):
   - "gappers this week", "top gainers of the week/month"
   - ANY query about PAST dates, weeks, months
   - Calculations like gaps, VWAP comparisons, multi-day analysis
   - Keywords: week, month, yesterday, last, semana, mes, ayer

3. **RESEARCH** (use research_ticker):
   - "why is X up/down", "news about X", "what happened to X"
   - Sentiment, news, SEC filings

4. **TICKER INFO** (use get_ticker_info):
   - "what is AAPL", "info about MSFT", basic lookups

When in doubt about "today":
- If asking for TOP/RANKINGS → get_market_snapshot (Redis has live data)
- If asking for CALCULATIONS (gaps, vwap) → execute_analysis

Respond in the same language as the user."""
    
    def _build_all_tools(self) -> List[types.Tool]:
        """Build all tool definitions for Gemini."""
        declarations = []
        
        for tool in MARKET_TOOLS:
            # Enhanced descriptions for better routing
            description = tool["description"]
            
            if tool["name"] == "get_market_snapshot":
                description = """Get REAL-TIME market data from Redis snapshot.
Use for: current prices, today's gainers/losers, live rankings, "top stocks today/now/tdy"
Returns: ~11,000 tickers with price, change%, volume, vwap
THIS IS THE CORRECT TOOL FOR "TODAY" QUESTIONS ABOUT RANKINGS/PRICES."""
            
            elif tool["name"] == "execute_analysis":
                description = """Execute Python/DuckDB code for HISTORICAL analysis.
Use for: past weeks/months, gaps, multi-day analysis, calculations
NOT for today's rankings (use get_market_snapshot instead).
Data: day_aggs (parquet files by date), minute_aggs"""
            
            declarations.append(types.FunctionDeclaration(
                name=tool["name"],
                description=description[:1000],
                parameters=tool.get("parameters", {})
            ))
        
        return [types.Tool(function_declarations=declarations)]
    
    async def _generate_interpreted_response(
        self,
        query: str,
        data: Dict[str, Any],
        tools_used: List[str]
    ) -> str:
        """Generate a natural language response by having LLM interpret the data."""
        if not data:
            return "No data found."
        
        # Extract the actual data to show
        data_to_interpret = {}
        for tool_name, result in data.items():
            if isinstance(result, dict):
                # For get_market_snapshot, extract the ticker data
                if "data" in result and isinstance(result["data"], list):
                    # Take top 10 for response
                    data_to_interpret[tool_name] = result["data"][:10]
                elif "tickers" in result:
                    data_to_interpret[tool_name] = result["tickers"][:10]
                else:
                    data_to_interpret[tool_name] = result
            elif isinstance(result, list):
                data_to_interpret[tool_name] = result[:10]
            else:
                data_to_interpret[tool_name] = result
        
        # Format data as JSON for the prompt
        import json
        try:
            data_json = json.dumps(data_to_interpret, indent=2, default=str)
        except:
            data_json = str(data_to_interpret)
        
        # Use Flash to interpret and respond
        interpret_prompt = f"""The user asked: "{query}"

Here is the data retrieved:
```json
{data_json}
```

Generate a helpful, concise response that:
1. Directly answers the user's question
2. Shows the TOP results in a clean format (table or list)
3. Highlights key insights (biggest gainers, notable moves, etc.)
4. Respond in the same language as the user's query

For market data, show: Symbol, Price, Change%, Volume
Keep it concise but informative."""

        try:
            response = await self.client.aio.models.generate_content(
                model=self.ROUTING_MODEL,  # Flash is enough for formatting
                contents=[{"role": "user", "parts": [{"text": interpret_prompt}]}],
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=1024
                )
            )
            
            if response.candidates and response.candidates[0].content:
                parts = response.candidates[0].content.parts
                if parts and hasattr(parts[0], 'text'):
                    return parts[0].text
        except Exception as e:
            logger.warning("interpret_response_failed", error=str(e))
        
        # Fallback: basic summary
        return self._generate_basic_summary(data)


    def _generate_basic_summary(self, data: Dict[str, Any]) -> str:
        """Fallback: generate basic summary without LLM."""
        summaries = []
        for key, value in data.items():
            if isinstance(value, dict) and "data" in value:
                records = value["data"]
                if isinstance(records, list) and len(records) > 0:
                    summaries.append(f"**{key}**: {len(records)} resultados")
                    # Show top 5
                    for i, rec in enumerate(records[:5]):
                        if isinstance(rec, dict):
                            symbol = rec.get("symbol", rec.get("ticker", "?"))
                            change = rec.get("change_percent", rec.get("todaysChangePerc", 0))
                            price = rec.get("price", rec.get("current_price", 0))
                            summaries.append(f"  {i+1}. {symbol}: {change:+.2f}% (${price:.2f})")
            elif isinstance(value, list) and len(value) > 0:
                summaries.append(f"**{key}**: {len(value)} resultados")
        
        if summaries:
            return "Análisis completado:\n\n" + "\n".join(summaries)
        return "Analysis complete."


# Factory function for backward compatibility
def create_market_agent(api_key: str) -> MarketAgentV3:
    """Create a MarketAgentV3 instance."""
    return MarketAgentV3(api_key=api_key)


# Alias for compatibility
MarketAgent = MarketAgentV3
