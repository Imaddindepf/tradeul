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


@dataclass
class AnalysisRequest:
    """Request for analysis."""
    query: str
    session_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    market_context: Dict[str, Any] = field(default_factory=dict)


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
    
    async def process(self, request: AnalysisRequest) -> AnalysisResult:
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
        
        try:
            # Step 1: Fetch data based on query analysis
            data, data_sources = await self._fetch_relevant_data(request.query)
            
            # Step 2: Build data manifest for LLM context
            data_manifest = self._build_data_manifest(data)
            
            logger.info(
                "data_fetched",
                sources=data_sources,
                manifest_keys=list(data_manifest.keys())
            )
            
            # Step 3: Generate analysis code via LLM
            explanation, code = await self._generate_code(
                request.query,
                data_manifest,
                request.market_context
            )
            
            logger.info("code_generated", code_length=len(code))
            
            # Step 4: Execute in sandbox
            execution_result = await self.sandbox.execute(
                code=code,
                data=data,
                timeout=30
            )
            
            # Step 5: Format result
            result = self._format_result(
                request=request,
                explanation=explanation,
                code=code,
                execution=execution_result,
                data_sources=data_sources
            )
            
            result.execution_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(
                "request_processed",
                success=result.success,
                execution_time=result.execution_time
            )
            
            return result
            
        except Exception as e:
            import traceback
            logger.error("request_processing_error", error=str(e), tb=traceback.format_exc())
            
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
                data_sources=[]
            )
    
    async def _fetch_relevant_data(
        self,
        query: str
    ) -> tuple[Dict[str, pd.DataFrame], List[str]]:
        """
        Fetch data relevant to the query.
        
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
        
        # Check for specific date/time in query using LLM normalization
        logger.info("starting_temporal_normalization", query=query[:80])
        temporal = await self._normalize_temporal_expression(query)
        logger.info("temporal_result", temporal=temporal)
        target_dates = []  # Support multiple dates
        target_hour = None
        hour_range = None
        
        if temporal and (temporal.get('has_temporal') or temporal.get('needs_historical')):
            now = datetime.now(ET)
            
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
            
            # Extract hour or hour range
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
                data['bars_data'] = pd.concat(bars_list, ignore_index=True)
                sources.append('polygon_bars')
                logger.info("bars_data_fetched", tickers=tickers[:10])
        
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
                # Convert window_start to datetime
                df['datetime_utc'] = pd.to_datetime(df['window_start'] / 1e6, unit='ms', utc=True)
            else:
                df = pd.read_csv(file_path, compression='gzip')
                # Convert timestamp: Polygon uses nanoseconds since epoch in UTC
                df['datetime_utc'] = pd.to_datetime(df['window_start'] / 1e9, unit='s', utc=True)
            
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
            # English
            'I', 'A', 'THE', 'AND', 'OR', 'FOR', 'TOP', 'VS', 'FROM', 'TO', 'AT',
            'IN', 'ON', 'BY', 'WITH', 'WHAT', 'HOW', 'WHY', 'WHEN', 'WHERE',
            'LAST', 'FIRST', 'NEXT', 'DAYS', 'DAY', 'HOUR', 'HOURS', 'WEEK',
            'SAME', 'UNTIL', 'ONLY', 'ALSO', 'SHOW', 'GET', 'FIND',
            # Spanish
            'DE', 'LA', 'EL', 'EN', 'LOS', 'LAS', 'UN', 'UNA', 'QUE', 'CON',
            'POR', 'MAS', 'COMO', 'TODO', 'SU', 'SI', 'NO', 'HAY', 'SER',
            'HOY', 'AYER', 'DIA', 'DIAS', 'HORA', 'HORAS', 'SEMANA',
            'PERO', 'SOLO', 'HASTA', 'ESE', 'ESTE', 'DESDE', 'ENTRE',
            'TRES', 'DOS', 'UNO', 'CINCO', 'DIEZ', 'PRIMERA', 'ULTIMO',
            'ULTIMOS', 'PRECIOS', 'PRECIO', 'QUIERO', 'DAME', 'MUESTRA',
            'PRE', 'POST', 'MARKET', 'PREMARKET', 'POSTMARKET',
            # Technical indicators
            'RSI', 'SMA', 'EMA', 'MACD', 'ATR', 'VWAP', 'VOL', 'RVOL'
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
        market_context: dict = None
    ) -> tuple[str, str]:
        """
        Generate analysis code using LLM.
        
        Returns:
            Tuple of (explanation, code)
        """
        if not self.llm_client:
            # Fallback: generate basic template
            return self._generate_fallback_code(query, data_manifest)
        
        try:
            # Build the prompt
            prompt = build_code_generation_prompt(
                user_query=query,
                data_manifest=data_manifest,
                market_context=market_context
            )
            
            logger.info("llm_prompt_context", 
                manifest_keys=list(data_manifest.keys()),
                historical_dates=data_manifest.get('historical_bars', {}).get('date_range', [])
            )
            
            # Call LLM
            from google.genai import types
            
            response = self.llm_client.client.models.generate_content(
                model=self.llm_client.model,
                contents=[types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)]
                )],
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
