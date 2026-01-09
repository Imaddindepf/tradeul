"""
Request Handler - Orchestrator
==============================
Handles the complete flow from user query to analysis result:

1. Analyze user query
2. Fetch required data from services (Scanner, Polygon)
3. Generate analysis code via LLM
4. Execute code in isolated sandbox
5. Return formatted results

This replaces the old DSL-based approach with a more flexible sandbox execution.
"""

import asyncio
import json
import re
import io
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

import pandas as pd
import pytz
import structlog

from sandbox import SandboxManager, SandboxConfig
from sandbox.manager import ExecutionResult, ExecutionStatus
from data.service_clients import get_service_clients, ServiceClients
from llm.sandbox_prompts import build_code_generation_prompt

logger = structlog.get_logger(__name__)

ET = pytz.timezone('America/New_York')


class DataSource(Enum):
    """Available data sources."""
    SCANNER = "scanner"
    POLYGON_BARS = "polygon_bars"
    TICKER_INFO = "ticker_info"


class FlowType(Enum):
    """Types of analysis flows."""
    ANALYSIS = "analysis"      # Data analysis with code execution
    RESEARCH = "research"      # Deep research with Grok (news, sentiment)
    CLARIFICATION = "clarification"  # Need more info from user
    INFO = "info"              # Simple ticker info lookup


@dataclass
class AgentStep:
    """A step in the agent's execution flow."""
    id: str
    type: str  # 'reasoning', 'tool', 'code', 'result'
    title: str
    description: str = ""
    status: str = "pending"  # 'pending', 'running', 'complete', 'error'
    details: str = ""
    expandable: bool = False


@dataclass
class AnalysisRequest:
    """Request for analysis."""
    query: str
    session_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    market_context: Dict[str, Any] = field(default_factory=dict)
    conversation_history: List[Dict[str, str]] = field(default_factory=list)  # [{"role": "user/assistant", "content": "..."}]


@dataclass  
class AnalysisResult:
    """Result of analysis execution."""
    success: bool
    query: str
    explanation: str  # LLM's explanation
    code: str
    stdout: str
    data: Dict[str, Any]
    charts: Dict[str, bytes]
    error: Optional[str]
    execution_time: float
    data_sources: List[str]
    flow_type: str = "analysis"  # 'analysis', 'research', 'clarification', 'info'
    steps: List[AgentStep] = field(default_factory=list)  # Steps taken during execution
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        import math
        
        def clean_value(v):
            """Clean value for JSON serialization."""
            if isinstance(v, float):
                if math.isnan(v) or math.isinf(v):
                    return None
            return v
        
        def clean_row(row):
            """Clean a dict row for JSON."""
            return {k: clean_value(v) for k, v in row.items()}
        
        # Convert DataFrames to dict format
        serialized_data = {}
        for key, value in self.data.items():
            if isinstance(value, pd.DataFrame):
                # Convert to records and clean values
                records = value.to_dict('records')
                clean_records = [clean_row(r) for r in records]
                
                serialized_data[key] = {
                    "type": "dataframe",
                    "columns": value.columns.tolist(),
                    "rows": clean_records,
                    "row_count": len(value)
                }
            elif isinstance(value, dict):
                serialized_data[key] = value
            else:
                serialized_data[key] = str(value)
        
        return {
            "success": self.success,
            "query": self.query,
            "explanation": self.explanation,
            "code": self.code,
            "stdout": self.stdout,
            "data": serialized_data,
            "charts": list(self.charts.keys()),  # Just names, actual bytes sent separately
            "error": self.error,
            "execution_time": self.execution_time,
            "data_sources": self.data_sources
        }


class RequestHandler:
    """
    Main orchestrator for analysis requests.
    
    Flow:
    1. Analyze query to determine data needs
    2. Fetch data from Scanner/Polygon
    3. Generate analysis code via LLM
    4. Execute in sandbox
    5. Format and return results
    """
    
    def __init__(self, llm_client=None):
        """
        Initialize request handler.
        
        Args:
            llm_client: GeminiClient instance for code generation
        """
        self.sandbox = SandboxManager()
        self.service_clients: Optional[ServiceClients] = None
        self.llm_client = llm_client
        self._initialized = False
    
    async def initialize(self):
        """Initialize async resources."""
        if self._initialized:
            return
            
        self.service_clients = get_service_clients()
        
        # Ensure sandbox image exists
        if not await self.sandbox.ensure_image_exists():
            logger.warning(
                "sandbox_image_missing",
                message="Run: docker build -f Dockerfile.sandbox -t tradeul-sandbox:latest services/ai-agent/"
            )
        
        self._initialized = True
        logger.info("request_handler_initialized")
    
    async def _classify_query(
        self, 
        query: str, 
        conversation_history: List[Dict] = None,
        on_thinking: callable = None
    ) -> tuple[FlowType, List[str], str]:
        """
        Use LLM with thinking mode to classify the type of query and extract relevant entities.
        
        Returns:
            Tuple of (FlowType, list of mentioned tickers, thinking_summary)
        """
        # Build context from conversation
        context_summary = ""
        if conversation_history:
            recent = conversation_history[-3:]  # Last 3 messages
            context_summary = "\n".join([f"{m['role']}: {m['content'][:100]}" for m in recent])
        
        prompt = f"""Classify this financial query and extract tickers.

CONVERSATION CONTEXT:
{context_summary if context_summary else "No previous context"}

CURRENT QUERY: "{query}"

Think through your analysis step by step, then provide the JSON classification.

Respond with your JSON at the end:
{{
    "flow_type": "research" | "analysis" | "clarification" | "info",
    "tickers": ["AAPL", "TSLA"],
    "reason": "brief explanation"
}}

FLOW TYPE DEFINITIONS:
- "research": User wants NEWS, WHY something is moving, sentiment, investigation, reasons behind price moves, social buzz. Keywords: why, news, moving, reason, what happened, catalyst
- "analysis": User wants DATA analysis, calculations, charts, comparisons, top/bottom rankings, historical price data
- "clarification": Query is too vague or ambiguous to proceed
- "info": User wants specific numeric info about a ticker (current price, market cap)

CRITICAL RULES:
- If query contains "why" + ticker → ALWAYS research
- If query contains "news" + ticker → ALWAYS research  
- If query asks about "moving", "up", "down" + ticker → ALWAYS research
- If query contains "what happened" + ticker → ALWAYS research

EXAMPLES:
- "Research RDDT news" → research
- "What's happening with AAPL?" → research  
- "Why is SERV moving?" → research
- "Why is TSLA up after hours?" → research
- "Tell me news about NVDA" → research
- "What happened to GME?" → research
- "Top gainers today" → analysis
- "Compare AAPL vs MSFT volume" → analysis
- "Show me historical data for SPY" → analysis
- "TSLA" (just ticker, no context) → clarification
- "What's the price of NVDA?" → info

JSON:"""

        try:
            from google.genai import types
            import json
            
            # Use thinking mode for better classification with visible reasoning
            response = self.llm_client.client.models.generate_content(
                model=self.llm_client.model_thinking,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=1024,
                    thinking_config=types.ThinkingConfig(include_thoughts=True)
                )
            )
            
            # Extract thoughts and response
            thoughts = []
            response_text = ""
            
            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'thought') and part.thought:
                        thought_text = part.text if hasattr(part, 'text') else ""
                        if thought_text:
                            thoughts.append(thought_text)
                            # Emit thinking step if callback provided
                            if on_thinking:
                                await on_thinking(thought_text)
                    elif hasattr(part, 'text'):
                        response_text += part.text
            
            # Parse JSON from response
            json_match = None
            try:
                # Find JSON in response
                if '{' in response_text:
                    start = response_text.find('{')
                    end = response_text.rfind('}') + 1
                    json_str = response_text[start:end]
                    json_match = json.loads(json_str)
            except json.JSONDecodeError:
                pass
            
            if not json_match:
                # Fallback
                return FlowType.ANALYSIS, self._extract_tickers(query), ""
            
            flow_type_str = json_match.get("flow_type", "analysis")
            tickers = json_match.get("tickers", [])
            
            # Map string to enum
            flow_map = {
                "research": FlowType.RESEARCH,
                "analysis": FlowType.ANALYSIS,
                "clarification": FlowType.CLARIFICATION,
                "info": FlowType.INFO
            }
            flow_type = flow_map.get(flow_type_str, FlowType.ANALYSIS)
            
            # Create thinking summary from thoughts
            thinking_summary = ""
            if thoughts:
                # Extract key points from thinking (first 500 chars)
                full_thinking = " ".join(thoughts)
                thinking_summary = full_thinking[:500] + "..." if len(full_thinking) > 500 else full_thinking
            
            logger.info("query_classified_with_thinking", 
                       query=query[:50], 
                       flow_type=flow_type.value,
                       tickers=tickers,
                       reason=json_match.get("reason", ""),
                       thinking_length=len(thinking_summary))
            
            return flow_type, tickers, thinking_summary
            
        except Exception as e:
            logger.warning("query_classification_error", error=str(e))
            # Fallback to analysis
            return FlowType.ANALYSIS, self._extract_tickers(query), ""
    
    async def process(self, request: AnalysisRequest, on_step: callable = None) -> AnalysisResult:
        """
        Process an analysis request end-to-end.
        
        Args:
            request: The analysis request
        
        Returns:
            AnalysisResult with data, charts, and execution info
        """
        if not self._initialized:
            await self.initialize()
        
        start_time = datetime.now()
        
        logger.info(
            "processing_request",
            query=request.query[:100],
            session_id=request.session_id
        )
        
        # Helper to emit steps
        steps_taken: List[AgentStep] = []
        
        async def emit_step(step: AgentStep):
            """Emit a step and store it."""
            steps_taken.append(step)
            if on_step:
                try:
                    await on_step(step)
                except Exception as e:
                    logger.warning("step_callback_error", error=str(e))
        
        try:
            # Callback to stream thinking in real-time
            thinking_chunks = []
            async def on_thinking_chunk(chunk: str):
                thinking_chunks.append(chunk)
                # Emit thinking as it comes
                await emit_step(AgentStep(
                    id="thinking",
                    type="reasoning",
                    title="Reasoning",
                    description=chunk[:200] + "..." if len(chunk) > 200 else chunk,
                    status="running",
                    expandable=True,
                    details=chunk
                ))
            
            # Step 0: Classify query using LLM with thinking mode
            flow_type, mentioned_tickers, thinking_summary = await self._classify_query(
                request.query, 
                request.conversation_history,
                on_thinking=on_thinking_chunk
            )
            
            # Mark thinking as complete with summary
            if thinking_summary:
                await emit_step(AgentStep(
                    id="thinking",
                    type="reasoning",
                    title="Reasoning Complete",
                    description=f"Analyzed query intent and context",
                    status="complete",
                    expandable=True,
                    details=thinking_summary
                ))
            
            # Emit classification result
            await emit_step(AgentStep(
                id="classify",
                type="reasoning",
                title="Query Classification",
                description=f"{flow_type.value.upper()} | {', '.join(mentioned_tickers) if mentioned_tickers else 'no tickers'}",
                status="complete"
            ))
            
            # Step 1: ORCHESTRATOR - Reformulate query with context
            await emit_step(AgentStep(
                id="reformulate",
                type="reasoning",
                title="Processing Intent",
                description="Understanding context and data requirements",
                status="running"
            ))
            
            reformulated_query, orchestrator_intent = await self._orchestrator_reformulate(
                query=request.query,
                conversation_history=request.conversation_history,
                market_context=request.market_context
            )
            
            # Extract key info for display
            intent_summary = orchestrator_intent[:60] + "..." if orchestrator_intent and len(orchestrator_intent) > 60 else orchestrator_intent
            await emit_step(AgentStep(
                id="reformulate",
                type="reasoning",
                title="Intent Understood",
                description=f"{intent_summary}" if intent_summary else f"Query: {reformulated_query[:50]}...",
                status="complete"
            ))
            
            logger.info(
                "query_reformulated",
                original=request.query[:50],
                reformulated=reformulated_query[:100],
                intent=orchestrator_intent[:50] if orchestrator_intent else None,
                flow_type=flow_type.value
            )
            
            # Handle RESEARCH flow type with Grok
            if flow_type == FlowType.RESEARCH and mentioned_tickers:
                await emit_step(AgentStep(
                    id="research_start",
                    type="tool",
                    title="Deep Research Mode",
                    description=f"Researching {mentioned_tickers[0]}",
                    status="running"
                ))
                
                try:
                    from research.grok_research import research_ticker, format_research_for_display
                    
                    ticker = mentioned_tickers[0]  # Primary ticker
                    logger.info("grok_research_triggered", ticker=ticker, query=request.query[:50])
                    
                    await emit_step(AgentStep(
                        id="x_search",
                        type="tool",
                        title="X.com Search",
                        description="Searching financial Twitter for news & sentiment",
                        status="running"
                    ))
                    
                    await emit_step(AgentStep(
                        id="web_search",
                        type="tool",
                        title="Web Search",
                        description="Searching news and financial data sources",
                        status="running"
                    ))
                    
                    research_result = await research_ticker(
                        ticker=ticker,
                        query=request.query,
                        include_technicals=True,
                        include_fundamentals=True,
                        max_retries=3  # Auto-retry on connection errors
                    )
                    
                    if research_result.get("success"):
                        # Update ALL steps to complete only on success
                        await emit_step(AgentStep(
                            id="research_start",
                            type="tool",
                            title="Deep Research Mode",
                            description=f"Research for {ticker} complete",
                            status="complete"
                        ))
                        await emit_step(AgentStep(
                            id="x_search",
                            type="tool",
                            title="X.com Search",
                            description="Found social sentiment data",
                            status="complete"
                        ))
                        await emit_step(AgentStep(
                            id="web_search",
                            type="tool",
                            title="Web Search",
                            description="Found news and financial data",
                            status="complete"
                        ))
                        
                        formatted = format_research_for_display(research_result)
                        
                        await emit_step(AgentStep(
                            id="research_complete",
                            type="result",
                            title="Research Complete",
                            description=f"Analysis for {ticker} ready",
                            status="complete"
                        ))
                        
                        return AnalysisResult(
                            success=True,
                            query=request.query,
                            explanation=formatted,
                            code="",
                            stdout="",
                            data={"research": research_result},
                            charts={},
                            error=None,
                            execution_time=(datetime.now() - start_time).total_seconds(),
                            data_sources=["grok_research", "x_search", "web_search"],
                            flow_type="research",
                            steps=steps_taken
                        )
                    else:
                        # Mark steps as error and fall through to analysis
                        error_msg = research_result.get("error", "Unknown error")[:50]
                        await emit_step(AgentStep(
                            id="research_start",
                            type="tool",
                            title="Deep Research Mode",
                            description=f"Failed: {error_msg}",
                            status="error"
                        ))
                        await emit_step(AgentStep(
                            id="x_search",
                            type="tool",
                            title="X.com Search",
                            description="Research failed",
                            status="error"
                        ))
                        await emit_step(AgentStep(
                            id="web_search",
                            type="tool",
                            title="Web Search",
                            description="Research failed",
                            status="error"
                        ))
                        await emit_step(AgentStep(
                            id="fallback",
                            type="reasoning",
                            title="Fallback to Analysis",
                            description="Using scanner data instead",
                            status="running"
                        ))
                        logger.warning("grok_research_failed_fallback", error=error_msg)
                        # Fall through to normal processing
                except ImportError as e:
                    logger.warning("grok_research_import_error", error=str(e))
                except Exception as e:
                    logger.error("grok_research_exception", error=str(e))
            
            # Check if orchestrator needs clarification
            if orchestrator_intent and orchestrator_intent.startswith("CLARIFICATION_NEEDED:"):
                clarification_question = orchestrator_intent.replace("CLARIFICATION_NEEDED:", "").strip()
                await emit_step(AgentStep(
                    id="clarification",
                    type="reasoning",
                    title="Need More Information",
                    description=clarification_question,
                    status="complete"
                ))
                return AnalysisResult(
                    success=True,
                    query=request.query,
                    explanation=clarification_question,
                    code="",
                    stdout="",
                    data={},
                    charts={},
                    error=None,
                    execution_time=(datetime.now() - start_time).total_seconds(),
                    data_sources=[],
                    flow_type="clarification",
                    steps=steps_taken
                )
            
            # Extract target_date from orchestrator intent if present
            forced_date = None
            clean_intent = orchestrator_intent
            if orchestrator_intent and orchestrator_intent.startswith("TARGET_DATE:"):
                parts = orchestrator_intent.split("|", 1)
                date_part = parts[0].replace("TARGET_DATE:", "")
                try:
                    forced_date = datetime.strptime(date_part, "%Y-%m-%d").replace(tzinfo=ET)
                    logger.info("orchestrator_forced_date", date=date_part)
                except:
                    pass
                clean_intent = parts[1] if len(parts) > 1 else None
            
            # Step: Data loading with detailed progress
            await emit_step(AgentStep(
                id="data_loading",
                type="tool",
                title="Loading Data Sources",
                description="Connecting to scanner, historical data, and APIs",
                status="running"
            ))
            
            # Fetch data based on REFORMULATED query (with optional forced date)
            data, data_sources = await self._fetch_relevant_data(reformulated_query, forced_date=forced_date)
            
            # Build data manifest for LLM context
            data_manifest = self._build_data_manifest(data)
            
            # Calculate data stats for display
            total_rows = 0
            for key, df in data.items():
                if hasattr(df, '__len__'):
                    total_rows += len(df)
            
            source_desc = f"{len(data_sources)} sources, {total_rows:,} rows"
            await emit_step(AgentStep(
                id="data_loading",
                type="tool",
                title="Data Ready",
                description=source_desc,
                status="complete"
            ))
            
            logger.info(
                "data_fetched",
                sources=data_sources,
                manifest_keys=list(data_manifest.keys())
            )
            
            # Step: Generate analysis code
            await emit_step(AgentStep(
                id="code_gen",
                type="reasoning",
                title="Writing Analysis",
                description="LLM generating Python code for your query",
                status="running"
            ))
            
            explanation, code = await self._generate_code(
                reformulated_query,  # Use reformulated, not original
                data_manifest,
                request.market_context,
                request.conversation_history,
                clean_intent  # Pass the clean intent (without TARGET_DATE prefix)
            )
            
            # Count lines for better description
            code_lines = len(code.strip().split('\n')) if code else 0
            await emit_step(AgentStep(
                id="code_gen",
                type="reasoning",
                title="Code Generated",
                description=f"{code_lines} lines of analysis code",
                status="complete"
            ))
            
            logger.info("code_generated", code_length=len(code))
            
            # Step: Execute in sandbox
            await emit_step(AgentStep(
                id="execution",
                type="code",
                title="Running Analysis",
                description="Executing in sandbox",
                status="running",
                details=code,
                expandable=True
            ))
            
            # Execute in sandbox with self-healing retry loop
            max_retries = 3
            execution_result = None
            last_error = None
            
            for attempt in range(max_retries):
                execution_result = await self.sandbox.execute(
                    code=code,
                    data=data,
                    timeout=30
                )
                
                # If successful, break
                if execution_result.success:
                    if attempt > 0:
                        logger.info("code_fixed_after_retry", attempt=attempt + 1)
                    break
                
                # Build error message from execution result
                last_error = execution_result.error_message or execution_result.stderr or f"Exit code: {execution_result.exit_code}"
                
                if attempt < max_retries - 1:
                    logger.info(
                        "code_execution_failed_retrying",
                        attempt=attempt + 1,
                        error=last_error[:200] if last_error else "Unknown"
                    )
                    
                    # Ask LLM to fix the code
                    code = await self._fix_code_with_error(
                        original_query=request.query,
                        original_code=code,
                        error_message=last_error,
                        data_manifest=data_manifest
                    )
                    
                    logger.info("code_regenerated", attempt=attempt + 2, code_length=len(code))
            
            # Step 4b: Check for empty results (silent failures)
            # If execution succeeded but produced no output, ask LLM to investigate
            if execution_result.success:
                has_output = bool(execution_result.output_files) or bool(execution_result.stdout.strip())
                has_empty_df = False
                
                # Check if all outputs are empty (small parquet files = empty df)
                if execution_result.output_files:
                    for filename, content in execution_result.output_files.items():
                        if filename.endswith('.parquet') and len(content) < 500:  # Empty parquet is ~400 bytes
                            has_empty_df = True
                            break
                
                # If no meaningful output and this is a "top" or ranking query, retry with investigation
                if (not has_output or has_empty_df) and any(kw in request.query.lower() for kw in ['top', 'best', 'highest', 'mayor', 'mejor']):
                    logger.info("empty_result_detected", has_output=has_output, has_empty_df=has_empty_df)
                    
                    # Only do this once
                    if 'empty_result_retry' not in request.context:
                        request.context['empty_result_retry'] = True
                        
                        # Build a diagnostic prompt
                        diagnostic_error = (
                            "CODE EXECUTED WITHOUT ERRORS BUT PRODUCED NO RESULTS.\n"
                            f"The filter conditions may be wrong. Check:\n"
                            "1. Column values (e.g., session='MARKET_OPEN' not 'REGULAR')\n"
                            "2. Numeric thresholds may be too strict\n"
                            "3. Data might be empty for the requested criteria\n\n"
                            f"stdout was: {execution_result.stdout[:200] if execution_result.stdout else 'empty'}"
                        )
                        
                        code = await self._fix_code_with_error(
                            original_query=request.query,
                            original_code=code,
                            error_message=diagnostic_error,
                            data_manifest=data_manifest
                        )
                        
                        # Re-execute with corrected code
                        execution_result = await self.sandbox.execute(
                            code=code,
                            data=data,
                            timeout=30
                        )
                        logger.info("code_re_executed_after_empty_result", success=execution_result.success)
            
            # Update execution step
            exec_status = "complete" if execution_result.success else "error"
            exec_desc = "Analysis complete" if execution_result.success else f"Error: {execution_result.error_message[:50] if execution_result.error_message else 'Unknown'}"
            await emit_step(AgentStep(
                id="execution",
                type="code",
                title="Analysis Code",
                description=exec_desc,
                status=exec_status,
                details=code,
                expandable=True
            ))
            
            # Format result
            result = self._format_result(
                request=request,
                explanation=explanation,
                code=code,
                execution=execution_result,
                data_sources=data_sources
            )
            
            result.execution_time = (datetime.now() - start_time).total_seconds()
            result.flow_type = "analysis"
            result.steps = steps_taken
            
            # Final result step
            await emit_step(AgentStep(
                id="result",
                type="result",
                title="Results Ready",
                description=f"Completed in {result.execution_time:.1f}s",
                status="complete" if result.success else "error"
            ))
            
            logger.info(
                "request_processed",
                success=result.success,
                execution_time=result.execution_time,
                flow_type=result.flow_type,
                steps_count=len(result.steps)
            )
            
            return result
            
        except Exception as e:
            import traceback
            logger.error("request_processing_error", error=str(e), tb=traceback.format_exc())
            
            # Emit error step
            await emit_step(AgentStep(
                id="error",
                type="result",
                title="Error",
                description=str(e)[:100],
                status="error"
            ))
            
            return AnalysisResult(
                success=False,
                query=request.query,
                explanation="",
                code="",
                stdout="",
                data={},
                charts={},
                error=str(e),
                execution_time=(datetime.now() - start_time).total_seconds(),
                data_sources=[],
                flow_type="analysis",
                steps=steps_taken
            )
    
    async def _orchestrator_reformulate(
        self,
        query: str,
        conversation_history: List[Dict[str, str]] = None,
        market_context: dict = None
    ) -> tuple[str, str]:
        """
        ORCHESTRATOR LLM: Reformulates user query into clear, actionable intent.
        
        This LLM:
        1. Understands conversation context (e.g., "total" refers to previous question)
        2. Knows what data sources are available
        3. Produces a clear, unambiguous query for the executor
        
        Args:
            query: Raw user query (could be short like "total" or "yes")
            conversation_history: Previous messages for context
            market_context: Current market session info
            
        Returns:
            Tuple of (reformulated_query, intent_for_executor)
        """
        if not self.llm_client:
            return query, None
        
        # If query is already long and clear, skip reformulation
        if len(query.split()) > 10 and not conversation_history:
            return query, None
        
        try:
            from google.genai import types
            
            now = datetime.now(ET)
            
            # Build context about available data with smart routing rules
            data_context = f"""
## DATA SOURCE ROUTING (CRITICAL - Follow these rules)

| Query Type | Data Source | Reason |
|------------|-------------|--------|
| After-hours/post-market NOW | scanner_data.postmarket_change_percent, postmarket_volume | Pre-aggregated per symbol |
| Pre-market NOW | scanner_data.premarket_change_percent | Pre-aggregated per symbol |
| Historical after-hours (yesterday, date) | historical_bars (hours 16-20) | Minute bars need aggregation |
| Current market snapshot | scanner_data | Already aggregated per symbol |
| Historical time range | historical_bars | Needs aggregation by symbol |

**AGGREGATION RULE**: When user asks for "top stocks", results MUST be ONE ROW PER SYMBOL (not multiple bars of same symbol).

## Available Data Sources
- scanner_data: Real-time snapshot with pre-calculated metrics (postmarket_change_percent, postmarket_volume, change_percent, volume_today)
- historical_bars: Raw minute OHLCV bars (requires groupby('symbol').agg(...) for rankings)
- today_bars: Today's minute bars
- categories_data: Scanner categories
"""
            
            # Build conversation context
            history_context = ""
            if conversation_history and len(conversation_history) > 0:
                history_context = "\n## CONVERSATION HISTORY (CRITICAL - Use this for context)\n"
                for msg in conversation_history[-6:]:
                    role = "User" if msg.get("role") == "user" else "Assistant"
                    history_context += f"{role}: {msg.get('content', '')[:200]}\n"
            
            prompt = f"""You are the ORCHESTRATOR for a financial analysis system.

## YOUR TASK
Transform the user's query into a clear, actionable instruction for the code executor.
If the query references previous conversation (like "yes", "total", "filter by X"), resolve it using the history.

**CRITICAL RULES:**
1. ALWAYS include EXPLICIT DATE in reformulated_query: "today {now.strftime('%Y-%m-%d')}" or "yesterday {(now - timedelta(days=1)).strftime('%Y-%m-%d')}"
2. If user adds a filter to previous query, KEEP the same date/time context from the previous query
3. If previous query was about TODAY, the filter MUST also be about TODAY
4. Never change temporal context unless user explicitly requests it

{history_context}

## CURRENT CONTEXT
Date/Time: {now.strftime('%Y-%m-%d %H:%M')} ET ({now.strftime('%A')})
Today: {now.strftime('%Y-%m-%d')}
Yesterday: {(now - timedelta(days=1)).strftime('%Y-%m-%d')}
Market Session: {market_context.get('session', 'UNKNOWN') if market_context else 'UNKNOWN'}

{data_context}

## USER QUERY
"{query}"

## OUTPUT FORMAT (JSON)
{{
  "reformulated_query": "Clear query with EXPLICIT DATE. Example: 'Top 10 stocks with highest percentage change between 16:00-17:00 ET on 2026-01-07'",
  "intent": "Technical instruction for executor. Example: 'Filter historical_bars for date 2026-01-07 hour 16-17, calculate change%...'",
  "target_date": "{now.strftime('%Y-%m-%d')}" or "YYYY-MM-DD",
  "needs_clarification": false,
  "clarification_question": null
}}

If the query is truly ambiguous even with history, set needs_clarification=true.

Respond ONLY with the JSON object."""

            response = self.llm_client.client.models.generate_content(
                model=self.llm_client.model,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(
                    temperature=0.3,  # Low temperature for consistency
                    max_output_tokens=1024,
                )
            )
            
            response_text = response.text if response.text else ""
            
            # Parse JSON response
            import json
            # Clean markdown if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            result = json.loads(response_text.strip())
            
            reformulated = result.get("reformulated_query", query)
            intent = result.get("intent", None)
            target_date = result.get("target_date", None)
            needs_clarification = result.get("needs_clarification", False)
            clarification = result.get("clarification_question", None)
            
            # If needs clarification, return the question as explanation
            if needs_clarification and clarification:
                logger.info("orchestrator_needs_clarification", question=clarification)
                return query, f"CLARIFICATION_NEEDED: {clarification}"
            
            # Include target_date in intent if provided
            if target_date and intent:
                intent = f"TARGET_DATE:{target_date}|{intent}"
            elif target_date:
                intent = f"TARGET_DATE:{target_date}"
            
            logger.info(
                "orchestrator_reformulated",
                original=query[:50],
                reformulated=reformulated[:100],
                intent=intent[:50] if intent else None,
                target_date=target_date
            )
            
            return reformulated, intent
            
        except Exception as e:
            logger.warning("orchestrator_reformulation_error", error=str(e))
            return query, None
    
    async def _fetch_relevant_data(
        self,
        query: str,
        forced_date: datetime = None
    ) -> tuple[Dict[str, pd.DataFrame], List[str]]:
        """
        Fetch data relevant to the query.
        
        Args:
            query: The query to analyze
            forced_date: If provided by orchestrator, use this date instead of inferring
        
        Uses heuristics to determine what data is needed.
        In the future, could use LLM function calling for smarter detection.
        """
        data = {}
        sources = []
        query_lower = query.lower()
        
        # Almost always need scanner data
        try:
            scanner_df = await self._fetch_scanner_data()
            if not scanner_df.empty:
                data['scanner_data'] = scanner_df
                sources.append('scanner')
                logger.info("scanner_data_fetched", rows=len(scanner_df))
        except Exception as e:
            logger.error("scanner_fetch_error", error=str(e))
        
        # Check if user is asking about categories/tables
        needs_categories = any(term in query_lower for term in [
            'categor', 'table', 'tabla', 'list', 'lista', 'group', 'grupo',
            'winners', 'losers', 'gappers', 'momentum', 'anomal', 'high_volume',
            'new_high', 'new_low', 'reversal', 'more than', 'más de', 'multiple',
            'múltiple', 'overlap', 'intersection', 'común', 'common'
        ])
        
        if needs_categories:
            try:
                categories_df = await self._fetch_all_categories()
                if not categories_df.empty:
                    data['categories_data'] = categories_df
                    sources.append('categories')
                    logger.info("categories_data_fetched", rows=len(categories_df))
            except Exception as e:
                logger.error("categories_fetch_error", error=str(e))
        
        # Check for specific date/time in query using LLM normalization
        # BUT if orchestrator provided forced_date, skip normalization for date
        target_dates = []  # Support multiple dates
        target_hour = None
        hour_range = None
        
        if forced_date:
            target_dates.append(forced_date)
            logger.info("using_orchestrator_forced_date", date=forced_date.strftime('%Y-%m-%d'))
        
        logger.info("starting_temporal_normalization", query=query[:80])
        temporal = await self._normalize_temporal_expression(query)
        logger.info("temporal_result", temporal=temporal)
        
        if temporal and (temporal.get('has_temporal') or temporal.get('needs_historical')):
            now = datetime.now(ET)
            
            # ONLY process date from temporal if orchestrator didn't provide forced_date
            if not forced_date:
                # Handle date range (e.g., "últimos 3 días")
                if temporal.get('date_range_days'):
                    days = temporal['date_range_days']
                    for i in range(1, days + 1):
                        target_dates.append(now - timedelta(days=i))
                    logger.info("date_range_detected", days=days, dates=[d.strftime('%Y-%m-%d') for d in target_dates])
                
                # Handle single date offset
                elif temporal.get('date_offset') is not None:
                    offset = temporal['date_offset']
                    target_dates.append(now + timedelta(days=offset))
                
                # Handle specific day
                elif temporal.get('specific_day'):
                    try:
                        target_dates.append(now.replace(day=temporal['specific_day']))
                    except ValueError:
                        pass
                
                # Default: if needs_historical but no specific dates, load last 3 days
                elif temporal.get('needs_historical'):
                    for i in range(1, 4):  # Last 3 days
                        target_dates.append(now - timedelta(days=i))
                    logger.info("default_historical_range", dates=[d.strftime('%Y-%m-%d') for d in target_dates])
            
            # ALWAYS extract hour or hour range (even with forced_date)
            if temporal.get('use_current_hour'):
                target_hour = now.hour
            elif temporal.get('hour') is not None:
                target_hour = temporal['hour']
            elif temporal.get('hour_range'):
                hour_range = temporal['hour_range']
        
        # Fallback to regex for ISO dates
        if not target_dates:
            match = re.search(r'(\d{4})-(\d{2})-(\d{2})', query)
            if match:
                target_dates.append(datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=ET))
        
        if not target_hour and not hour_range:
            target_hour = self._extract_hour_from_query(query)
        
        # KEY FIX: If hour_range or target_hour specified but no date, assume TODAY
        if (hour_range or target_hour is not None) and not target_dates:
            now = datetime.now(ET)
            target_dates.append(now)
            logger.info("assuming_today_for_hour_query", hour_range=hour_range, target_hour=target_hour)
        
        # Load minute_aggs if dates requested (single or multiple)
        if target_dates:
            try:
                all_dfs = []
                for target_date in target_dates:
                    # Determine hours to load
                    hours_to_load = []
                    if hour_range:
                        hours_to_load = list(range(hour_range.get('start', 4), hour_range.get('end', 10) + 1))
                    elif target_hour is not None:
                        hours_to_load = [target_hour]
                    else:
                        hours_to_load = [None]  # Load all hours
                    
                    for hour in hours_to_load:
                        minute_df = await self._load_minute_aggs(target_date, hour)
                        if not minute_df.empty:
                            minute_df['date_label'] = target_date.strftime('%Y-%m-%d')
                            all_dfs.append(minute_df)
                
                if all_dfs:
                    combined_df = pd.concat(all_dfs, ignore_index=True)
                    data['historical_bars'] = combined_df
                    sources.append('minute_aggs')
                    logger.info("historical_bars_loaded", 
                        dates=[d.strftime('%Y-%m-%d') for d in target_dates],
                        hours=hours_to_load if hour_range or target_hour else 'all',
                        rows=len(combined_df)
                    )
            except Exception as e:
                logger.error("minute_aggs_error", error=str(e))
        
        # Check if historical data is needed
        needs_historical = any(term in query_lower for term in [
            'ayer', 'yesterday', 'historical', 'historia', 'semana', 'week',
            'chart', 'gráfico', 'grafico', 'barras', 'bars', 'precio', 'price',
            'tendencia', 'trend', 'sma', 'rsi', 'macd', 'technical', 'técnico',
            'premarket', 'pre market', 'pre-market', 'postmarket', 'post market',
            'hora', 'hour', 'minuto', 'minute', '4am', '5am', '9:30'
        ])
        
        # Check if query is about TODAY's intraday data
        needs_today_bars = any(term in query_lower for term in [
            'hoy', 'today', 'ahora', 'now', 'esta hora', 'this hour',
            'últim', 'ultim', 'last', 'minuto', 'minute', 'intraday'
        ]) and not any(term in query_lower for term in ['ayer', 'yesterday', 'semana', 'week'])
        
        # Check for specific tickers mentioned
        tickers = self._extract_tickers(query)
        
        # If asking about today's intraday data for specific tickers, request on-demand
        if needs_today_bars and tickers:
            await self._request_today_bars(tickers[:20])
            # Load today's minute bars
            today = datetime.now(ET)
            today_bars = await self._load_minute_aggs(today)
            if not today_bars.empty:
                # Filter to mentioned tickers if any
                ticker_bars = today_bars[today_bars['symbol'].isin(tickers)]
                if not ticker_bars.empty:
                    data['today_bars'] = ticker_bars
                    sources.append('today_bars')
                    logger.info("today_bars_loaded", tickers=tickers[:10], rows=len(ticker_bars))
                else:
                    # Return all today bars as fallback
                    data['today_bars'] = today_bars
                    sources.append('today_bars')
        
        if needs_historical and tickers:
            # Fetch bars for mentioned tickers
            bars_list = []
            for ticker in tickers[:10]:  # Limit to 10
                try:
                    bars = await self._fetch_ticker_bars(ticker)
                    if not bars.empty:
                        bars['symbol'] = ticker
                        bars_list.append(bars)
                except Exception as e:
                    logger.warning("bars_fetch_error", ticker=ticker, error=str(e))
            
            if bars_list:
                data['historical_bars'] = pd.concat(bars_list, ignore_index=True)
                sources.append('polygon_bars')
                logger.info("historical_bars_from_polygon", tickers=tickers[:10])
        
        elif needs_historical and 'scanner_data' in data:
            # Fetch bars for top movers from scanner
            if 'change_percent' in data['scanner_data'].columns:
                top_symbols = data['scanner_data'].nlargest(15, 'change_percent')['symbol'].tolist()
            else:
                top_symbols = data['scanner_data']['symbol'].head(15).tolist()
            
            bars_list = []
            for ticker in top_symbols[:10]:
                try:
                    bars = await self._fetch_ticker_bars(ticker)
                    if not bars.empty:
                        bars['symbol'] = ticker
                        bars_list.append(bars)
                except Exception as e:
                    logger.warning("bars_fetch_error", ticker=ticker, error=str(e))
            
            if bars_list:
                data['bars_data'] = pd.concat(bars_list, ignore_index=True)
                sources.append('polygon_bars')
        
        return data, sources
    
    async def _fetch_scanner_data(self) -> pd.DataFrame:
        """Fetch current scanner data."""
        try:
            client = await self.service_clients._get_client()
            url = f"{self.service_clients.scanner_url}/api/scanner/filtered"
            
            response = await client.get(url)
            
            if response.status_code == 200:
                tickers = response.json()
                df = pd.DataFrame(tickers)
                
                # Remove complex columns that can't be serialized
                for col in list(df.columns):
                    if df[col].apply(lambda x: isinstance(x, (list, dict))).any():
                        df = df.drop(columns=[col])
                
                return df
            
            return pd.DataFrame()
            
        except Exception as e:
            logger.error("scanner_fetch_error", error=str(e))
            return pd.DataFrame()
    
    async def _fetch_all_categories(self) -> pd.DataFrame:
        """
        Fetch all category data and combine into a single DataFrame.
        
        Returns DataFrame with columns: symbol, category, price, change_percent, volume, etc.
        Each row represents a ticker in a specific category.
        A ticker can appear multiple times (once per category it belongs to).
        """
        categories = [
            'winners', 'losers', 'gappers_up', 'gappers_down',
            'momentum_up', 'momentum_down', 'new_highs', 'new_lows',
            'high_volume', 'anomalies', 'reversals'
        ]
        
        all_data = []
        
        try:
            client = await self.service_clients._get_client()
            
            for category in categories:
                try:
                    url = f"{self.service_clients.scanner_url}/api/categories/{category}"
                    response = await client.get(url, timeout=5.0)
                    
                    if response.status_code == 200:
                        data = response.json()
                        tickers = data.get('tickers', [])
                        
                        for ticker in tickers:
                            ticker['category'] = category
                            all_data.append(ticker)
                            
                except Exception as e:
                    logger.warning("category_fetch_error", category=category, error=str(e))
                    continue
            
            if all_data:
                df = pd.DataFrame(all_data)
                
                # Remove complex columns
                for col in list(df.columns):
                    if df[col].apply(lambda x: isinstance(x, (list, dict))).any():
                        df = df.drop(columns=[col])
                
                logger.info("categories_combined", 
                    total_rows=len(df), 
                    unique_symbols=df['symbol'].nunique(),
                    categories=df['category'].nunique()
                )
                return df
            
            return pd.DataFrame()
            
        except Exception as e:
            logger.error("categories_fetch_error", error=str(e))
            return pd.DataFrame()
    
    async def _fetch_ticker_bars(
        self,
        symbol: str,
        days: int = 2,
        interval: str = '5min'
    ) -> pd.DataFrame:
        """Fetch historical bars for a ticker."""
        try:
            now = datetime.now(ET)
            yesterday = now - timedelta(days=days)
            
            bars = await self.service_clients.get_bars_range(
                symbol=symbol,
                from_datetime=yesterday.replace(hour=9, minute=30),
                to_datetime=now.replace(hour=16, minute=0),
                interval=interval
            )
            
            return bars if bars is not None else pd.DataFrame()
            
        except Exception as e:
            logger.warning("ticker_bars_error", symbol=symbol, error=str(e))
            return pd.DataFrame()
    
    async def _normalize_temporal_expression(self, query: str) -> Optional[dict]:
        """
        Use LLM to normalize any temporal expression in the query.
        
        Returns dict with:
        - date_offset: int (days from today, negative = past, positive = future)
        - hour: int or None
        - is_relative: bool (e.g., "same hour" = True)
        - needs_historical: bool (if query needs past data)
        """
        now = datetime.now(ET)
        
        prompt = f"""Analiza esta consulta y extrae la información temporal para cargar datos.
Fecha/hora actual: {now.strftime('%Y-%m-%d %H:%M')} (ET, {now.strftime('%A')})

Consulta: "{query}"

IMPORTANTE: 
- Si la consulta COMPARA "hoy vs ayer" o menciona PASADO, necesitamos datos HISTORICOS
- Si menciona RANGO ("últimos X días", "last week"), usar date_range_days
- En comparaciones, prioriza la fecha PASADA

Responde SOLO con JSON válido:
{{
  "has_temporal": true/false,
  "needs_historical": true si menciona ayer/pasado/últimos/antes/vs/comparar/semana/días,
  "date_offset": días desde hoy para UN día específico (-1=ayer, -2=anteayer) o null,
  "date_range_days": número de días para rangos ("últimos 3 días" = 3) o null,
  "specific_day": día del mes (1-31) o null,
  "hour": hora específica (0-23) o null,
  "hour_range": {{"start": 4, "end": 5}} para rangos como "primera hora premarket" o null,
  "use_current_hour": true si "misma hora"/"same hour",
  "is_future": true si mañana/próximo
}}

Ejemplos:
- "últimos 3 días", "last 3 days" → {{"has_temporal": true, "needs_historical": true, "date_range_days": 3, ...}}
- "últimos tres días primera hora premarket" → {{"has_temporal": true, "needs_historical": true, "date_range_days": 3, "hour_range": {{"start": 4, "end": 5}}, ...}}
- "hoy vs ayer" → {{"has_temporal": true, "needs_historical": true, "date_offset": -1, ...}}
- "ayer a las 16:00" → {{"has_temporal": true, "needs_historical": true, "date_offset": -1, "hour": 16, ...}}
- "top gainers ahora" → {{"has_temporal": false, "needs_historical": false, ...}}
"""
        
        try:
            response = await self.llm_client.generate_json(prompt)
            logger.info("temporal_normalization_result", query=query[:50], response=response)
            if response and (response.get('has_temporal') or response.get('needs_historical')):
                return response
        except Exception as e:
            logger.warning("temporal_normalization_failed", error=str(e))
        
        return None
    
    async def _extract_date_from_query(self, query: str) -> Optional[datetime]:
        """
        Extract a specific date from query using LLM normalization.
        Falls back to regex for simple patterns.
        """
        now = datetime.now(ET)
        
        # Try LLM normalization first
        temporal = await self._normalize_temporal_expression(query)
        
        if temporal and temporal.get('has_temporal'):
            # Handle date_offset (relative dates)
            if temporal.get('date_offset') is not None:
                offset = temporal['date_offset']
                return now + timedelta(days=offset)
            
            # Handle specific_day (e.g., "día 5")
            if temporal.get('specific_day'):
                day = temporal['specific_day']
                try:
                    return now.replace(day=day)
                except ValueError:
                    pass
        
        # Fallback: ISO format "2026-01-05" (always works)
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', query)
        if match:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=ET)
        
        return None
    
    async def _extract_hour_from_query_smart(self, query: str) -> Optional[int]:
        """
        Extract hour using LLM normalization result.
        """
        temporal = await self._normalize_temporal_expression(query)
        
        if temporal:
            # "same hour" / "misma hora"
            if temporal.get('use_current_hour'):
                return datetime.now(ET).hour
            
            # Explicit hour
            if temporal.get('hour') is not None:
                return temporal['hour']
        
        # Fallback to regex
        return self._extract_hour_from_query(query)
    
    def _extract_hour_from_query(self, query: str) -> Optional[int]:
        """Extract hour from query using regex. Fallback for simple patterns."""
        query_lower = query.lower()
        
        # "HH:MM" format
        match = re.search(r'(\d{1,2}):(\d{2})', query)
        if match:
            return int(match.group(1))
        
        # "Xpm" or "Xam"
        match = re.search(r'(\d{1,2})\s*(am|pm)', query_lower)
        if match:
            hour = int(match.group(1))
            if match.group(2) == 'pm' and hour < 12:
                hour += 12
            elif match.group(2) == 'am' and hour == 12:
                hour = 0
            return hour
        
        # "a las X"
        match = re.search(r'a\s*las?\s*(\d{1,2})', query_lower)
        if match:
            return int(match.group(1))
        
        return None
    
    async def _load_minute_aggs(self, target_date: datetime, hour: Optional[int] = None) -> pd.DataFrame:
        """
        Load minute aggregates from Polygon flat files or today.parquet.
        
        Args:
            target_date: Date to load
            hour: Optional hour to filter (0-23) in ET timezone
        
        Returns:
            DataFrame with columns: symbol, datetime, open, high, low, close, volume
            datetime is timezone-aware in ET
        """
        date_str = target_date.strftime('%Y-%m-%d')
        today_str = datetime.now(ET).strftime('%Y-%m-%d')
        is_today = date_str == today_str
        
        # Determine file path
        if is_today:
            file_path = '/data/polygon/minute_aggs/today.parquet'
        else:
            file_path = f'/data/polygon/minute_aggs/{date_str}.csv.gz'
        
        try:
            if not Path(file_path).exists():
                if is_today:
                    logger.info("today_parquet_not_found_yet", date=date_str)
                else:
                    logger.warning("minute_aggs_not_found", date=date_str)
                return pd.DataFrame()
            
            # Read file based on type
            if file_path.endswith('.parquet'):
                df = pd.read_parquet(file_path)
                # today.parquet uses milliseconds since epoch
                df['datetime_utc'] = pd.to_datetime(df['window_start'], unit='ms', utc=True)
            else:
                df = pd.read_csv(file_path, compression='gzip')
                # Polygon CSV uses nanoseconds since epoch in UTC
                df['datetime_utc'] = pd.to_datetime(df['window_start'], unit='ns', utc=True)
            
            # Convert to Eastern Time for proper hour filtering
            df['datetime'] = df['datetime_utc'].dt.tz_convert(ET)
            df['hour_et'] = df['datetime'].dt.hour
            df['day_et'] = df['datetime'].dt.day
            
            # Filter by ET date (in case file contains multiple days due to UTC)
            target_day = target_date.day
            df = df[df['day_et'] == target_day]
            
            # Filter by hour if specified (in ET)
            if hour is not None:
                df = df[df['hour_et'] == hour]
                logger.info("minute_aggs_hour_filter", date=date_str, hour=hour, rows_after=len(df))
            
            # Rename and select columns
            if 'ticker' in df.columns:
                df = df.rename(columns={'ticker': 'symbol'})
            df = df[['symbol', 'datetime', 'open', 'high', 'low', 'close', 'volume']]
            
            logger.info("minute_aggs_loaded", date=date_str, hour=hour, rows=len(df), source='today' if is_today else 'flat')
            return df
            
        except Exception as e:
            logger.error("minute_aggs_load_error", date=date_str, error=str(e))
            return pd.DataFrame()
    
    async def _request_today_bars(self, tickers: List[str]) -> bool:
        """Request on-demand download of tickers from today-bars-worker."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "http://today-bars-worker:8035/download",
                    json={"tickers": tickers}
                )
                if resp.status_code == 200:
                    result = resp.json()
                    logger.info("today_bars_requested", tickers=tickers, result=result)
                    return result.get("success", False)
        except Exception as e:
            logger.warning("today_bars_request_failed", error=str(e))
        return False
    
    def _extract_tickers(self, query: str) -> List[str]:
        """Extract potential ticker symbols from query."""
        # Pattern for 1-5 uppercase letters
        pattern = r'\b([A-Z]{1,5})\b'
        potential = re.findall(pattern, query.upper())
        
        # Filter out common words (English + Spanish + technical terms)
        common_words = {
            # English - common words
            'I', 'A', 'THE', 'AND', 'OR', 'FOR', 'TOP', 'VS', 'FROM', 'TO', 'AT',
            'IN', 'ON', 'BY', 'WITH', 'WHAT', 'HOW', 'WHY', 'WHEN', 'WHERE',
            'LAST', 'FIRST', 'NEXT', 'DAYS', 'DAY', 'HOUR', 'HOURS', 'WEEK',
            'SAME', 'UNTIL', 'ONLY', 'ALSO', 'SHOW', 'GET', 'FIND', 'ALL',
            'THAT', 'THIS', 'WHICH', 'WHO', 'THEM', 'THEIR', 'THOSE', 'THESE',
            'HAD', 'HAS', 'HAVE', 'BEEN', 'WAS', 'WERE', 'ARE', 'IS', 'OF',
            'AFTER', 'BEFORE', 'DURING', 'TODAY', 'YESTERDAY', 'TOMORROW',
            'ABOVE', 'BELOW', 'OVER', 'UNDER', 'MORE', 'LESS', 'THAN',
            'PRICE', 'VOLUME', 'CHANGE', 'PERCENT', 'ROSE', 'FELL', 'UP', 'DOWN',
            'STOCKS', 'STOCK', 'SHARES', 'SHARE', 'TRADING', 'TRADE',
            'FILTER', 'RESULTS', 'QUERY', 'PREVIOUS', 'CURRENT',
            # Spanish
            'DE', 'LA', 'EL', 'EN', 'LOS', 'LAS', 'UN', 'UNA', 'QUE', 'CON',
            'POR', 'MAS', 'COMO', 'TODO', 'SU', 'SI', 'NO', 'HAY', 'SER',
            'HOY', 'AYER', 'DIA', 'DIAS', 'HORA', 'HORAS', 'SEMANA',
            'PERO', 'SOLO', 'HASTA', 'ESE', 'ESTE', 'DESDE', 'ENTRE',
            'TRES', 'DOS', 'UNO', 'CINCO', 'DIEZ', 'PRIMERA', 'ULTIMO',
            'ULTIMOS', 'PRECIOS', 'PRECIO', 'QUIERO', 'DAME', 'MUESTRA',
            'PRE', 'POST', 'MARKET', 'PREMARKET', 'POSTMARKET',
            # Technical indicators
            'RSI', 'SMA', 'EMA', 'MACD', 'ATR', 'VWAP', 'VOL', 'RVOL', 'ET', 'PM', 'AM'
        }
        
        return [t for t in potential if t not in common_words]
    
    def _build_data_manifest(self, data: Dict[str, pd.DataFrame]) -> Dict[str, dict]:
        """Build manifest describing available data."""
        manifest = {}
        
        for name, df in data.items():
            if isinstance(df, pd.DataFrame) and not df.empty:
                manifest[name] = {
                    'rows': len(df),
                    'columns': df.columns.tolist()
                }
                
                # Add date range for historical_bars
                if name == 'historical_bars' and 'datetime' in df.columns:
                    try:
                        dates = pd.to_datetime(df['datetime']).dt.date.unique()
                        manifest[name]['date_range'] = sorted([str(d) for d in dates])
                    except Exception:
                        pass
        
        return manifest
    
    async def _generate_code(
        self,
        query: str,
        data_manifest: dict,
        market_context: dict = None,
        conversation_history: List[Dict[str, str]] = None,
        orchestrator_intent: str = None
    ) -> tuple[str, str]:
        """
        Generate analysis code using LLM.
        
        Args:
            query: User's query (already reformulated by orchestrator)
            data_manifest: Available data description
            market_context: Current market session info
            conversation_history: Previous messages for context
            orchestrator_intent: Clear intent from orchestrator
        
        Returns:
            Tuple of (explanation, code)
        """
        if not self.llm_client:
            # Fallback: generate basic template
            return self._generate_fallback_code(query, data_manifest)
        
        try:
            # Build the prompt with orchestrator intent
            prompt = build_code_generation_prompt(
                user_query=query,
                data_manifest=data_manifest,
                market_context=market_context
            )
            
            # If orchestrator provided intent, prepend it
            if orchestrator_intent:
                prompt = f"## ORCHESTRATOR INTENT (Follow this exactly)\n{orchestrator_intent}\n\n{prompt}"
            
            logger.info("llm_prompt_context", 
                manifest_keys=list(data_manifest.keys()),
                historical_dates=data_manifest.get('historical_bars', {}).get('date_range', [])
            )
            
            # Call LLM with conversation history for context
            from google.genai import types
            
            # Build contents with history if available
            contents = []
            
            # Add conversation history (last 6 messages for context)
            if conversation_history:
                for msg in conversation_history[-6:]:
                    role = "user" if msg.get("role") == "user" else "model"
                    contents.append(types.Content(
                        role=role,
                        parts=[types.Part(text=msg.get("content", ""))]
                    ))
            
            # Add current query with full prompt context
            contents.append(types.Content(
                role="user",
                parts=[types.Part(text=prompt)]
            ))
            
            response = self.llm_client.client.models.generate_content(
                model=self.llm_client.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=4096,
                )
            )
            
            response_text = response.text if response.text else ""
            
            # Extract code and explanation
            explanation, code = self._parse_llm_response(response_text)
            
            return explanation, code
            
        except Exception as e:
            logger.error("llm_code_generation_error", error=str(e))
            return self._generate_fallback_code(query, data_manifest)
    
    def _parse_llm_response(self, response_text: str) -> tuple[str, str]:
        """Parse LLM response to extract explanation and code."""
        # Extract code block
        code_pattern = r'```(?:python)?\s*(.*?)```'
        code_matches = re.findall(code_pattern, response_text, re.DOTALL)
        
        code = code_matches[0].strip() if code_matches else ""
        
        # Explanation is everything before the first code block
        explanation = response_text.split('```')[0].strip() if '```' in response_text else response_text
        
        return explanation, code
    
    async def _fix_code_with_error(
        self,
        original_query: str,
        original_code: str,
        error_message: str,
        data_manifest: dict
    ) -> str:
        """
        Ask LLM to fix code that failed execution.
        
        Args:
            original_query: The user's original query
            original_code: The code that failed
            error_message: The error message from execution
            data_manifest: Available data description
        
        Returns:
            Fixed code string
        """
        prompt = f"""El siguiente codigo Python falló con un error. Corrígelo.

## Query original del usuario:
{original_query}

## Datos YA CARGADOS como variables globales:
{json.dumps(data_manifest, indent=2)}

## Codigo que falló:
```python
{original_code}
```

## Error:
{error_message}

## REGLAS ABSOLUTAS:
1. Los datos YA existen como variables: `scanner_data`, `historical_bars` - USALOS DIRECTAMENTE
2. NUNCA definas funciones - escribe codigo ejecutable directo
3. NUNCA redefinas save_output() o save_chart() - YA EXISTEN
4. NUNCA simules datos con np.random
5. NUNCA uses imports - ya estan disponibles (pd, np, plt)

## CORRECCION:
1. Analiza el error y corrígelo
2. Errores comunes:
   - TypeError con Categorical: usa .astype(str) antes de concatenar
   - KeyError: verifica que la columna existe
   - Graficos con demasiados datos: agrupa y limita a TOP 10-20
3. SIEMPRE usa save_output() y save_chart() para guardar resultados

Responde SOLO con el código Python corregido en un bloque ```python ... ```
El codigo debe ser EJECUTABLE DIRECTAMENTE, sin funciones def.
"""
        
        try:
            from google.genai import types
            
            response = self.llm_client.client.models.generate_content(
                model=self.llm_client.model,
                contents=[types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)]
                )],
                config=types.GenerateContentConfig(
                    temperature=0.3,  # Lower temperature for more deterministic fix
                    max_output_tokens=4096,
                )
            )
            
            response_text = response.text if response.text else ""
            
            # Extract just the code
            _, fixed_code = self._parse_llm_response(response_text)
            
            if fixed_code:
                logger.info("code_fixed_by_llm", original_error=error_message[:100])
                return fixed_code
            
        except Exception as e:
            logger.error("code_fix_failed", error=str(e))
        
        # Return original code if fix failed
        return original_code
    
    def _generate_fallback_code(
        self,
        query: str,
        data_manifest: dict
    ) -> tuple[str, str]:
        """Generate fallback code when LLM is unavailable."""
        explanation = "Analizando los datos disponibles..."
        
        code = f'''# Query: {query}
print("=" * 60)
print("📊 ANÁLISIS DE MERCADO")
print("=" * 60)

# Scanner data analysis
if 'scanner_data' in dir() and not scanner_data.empty:
    print(f"\\n📡 Scanner: {{len(scanner_data)}} símbolos")
    
    if 'change_percent' in scanner_data.columns:
        # Top gainers
        gainers = scanner_data[scanner_data['change_percent'] > 0]
        losers = scanner_data[scanner_data['change_percent'] < 0]
        
        print(f"🟢 Gainers: {{len(gainers)}}")
        print(f"🔴 Losers: {{len(losers)}}")
        
        top10 = scanner_data.nlargest(10, 'change_percent')
        print("\\n🏆 TOP 10 GAINERS:")
        cols = ['symbol', 'price', 'change_percent']
        cols = [c for c in cols if c in top10.columns]
        print(top10[cols].to_string(index=False))
        
        save_output(top10, 'top_gainers')

# Bars analysis if available
if 'bars_data' in dir() and not bars_data.empty:
    print(f"\\n📈 Barras históricas: {{len(bars_data)}} registros")
    print(f"   Símbolos: {{bars_data['symbol'].nunique()}}")

print("\\n" + "=" * 60)
print("✅ Análisis completado")
'''
        
        return explanation, code
    
    def _format_result(
        self,
        request: AnalysisRequest,
        explanation: str,
        code: str,
        execution: ExecutionResult,
        data_sources: List[str]
    ) -> AnalysisResult:
        """Format execution result into AnalysisResult."""
        charts = {}
        data = {}
        
        for filename, content in execution.output_files.items():
            if filename.endswith('.png') or filename.endswith('.jpg'):
                charts[filename] = content
            elif filename.endswith('.parquet'):
                try:
                    df = pd.read_parquet(io.BytesIO(content))
                    data[filename.replace('.parquet', '')] = df
                except Exception as e:
                    logger.warning("parquet_parse_error", file=filename, error=str(e))
            elif filename.endswith('.json'):
                try:
                    data[filename.replace('.json', '')] = json.loads(content)
                except Exception as e:
                    logger.warning("json_parse_error", file=filename, error=str(e))
        
        return AnalysisResult(
            success=execution.success,
            query=request.query,
            explanation=explanation,
            code=code,
            stdout=execution.stdout,
            data=data,
            charts=charts,
            error=execution.error_message,
            execution_time=execution.execution_time,
            data_sources=data_sources
        )
    
    def health_check(self) -> Dict[str, Any]:
        """Check orchestrator health."""
        sandbox_health = self.sandbox.health_check()
        
        return {
            "sandbox": sandbox_health,
            "service_clients_initialized": self.service_clients is not None,
            "llm_client_initialized": self.llm_client is not None,
            "initialized": self._initialized,
            "healthy": sandbox_health.get("healthy", False)
        }
    
    async def close(self):
        """Cleanup resources."""
        if self.service_clients:
            await self.service_clients.close()
