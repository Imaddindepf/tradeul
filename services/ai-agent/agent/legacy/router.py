"""
Intent Router
=============
Classifies user queries BEFORE sending to specialists.

This solves the "temporal confusion" problem where LLMs confuse
"now" with "1 hour ago" because all tools are available at once.

Architecture:
  User Query → Router → Specialist Agent → Response
                 ↓
         {category, time_context, complexity, specialist}
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import json
import re
import structlog

logger = structlog.get_logger(__name__)


class QueryCategory(Enum):
    """Types of queries the system can handle."""
    REAL_TIME = "real_time"           # Current market data, live prices
    HISTORICAL = "historical"          # Past data, specific dates/times
    COMPUTATION = "computation"        # Complex calculations, synthetic ETFs
    RESEARCH = "research"              # News, analysis, "why" questions
    SIMPLE_LOOKUP = "simple_lookup"    # Basic ticker info


class Specialist(Enum):
    """Specialist agents available."""
    SCANNER = "scanner"           # Real-time market data
    HISTORIAN = "historian"       # Historical queries via SQL/DuckDB
    QUANT = "quant"              # Calculations, synthetic ETFs, code execution
    RESEARCHER = "researcher"     # News, social media, SEC filings
    GENERAL = "general"          # Simple lookups, general questions


@dataclass
class RoutingDecision:
    """Result of routing analysis."""
    category: QueryCategory
    specialist: Specialist
    time_context: str              # "now", "today", "yesterday", "2024-01-15", etc.
    complexity: str                # "simple", "multi_step", "computation"
    needs_chart: bool              # User wants visualization
    filters: Dict[str, Any]        # Extracted filters (min_market_cap, etc.)
    confidence: float              # 0-1 routing confidence
    reasoning: str                 # Why this routing was chosen
    data_hint: str = "auto"        # "day_aggs" for daily/weekly, "minute_aggs" for intraday, "auto" for LLM to decide


class IntentRouter:
    """
    Routes queries to the appropriate specialist agent.
    
    Uses a lightweight LLM call to classify before heavy processing.
    This prevents the "all tools available" confusion.
    """
    
    ROUTING_PROMPT = """You are a query classifier for a financial analysis system.
Analyze the user's query and classify it.

CATEGORIES:
- real_time: Current prices, today's movers, live data ("top gainers now", "current price")
- historical: Past data with specific time ("yesterday", "last week", "hace 1 hora", specific dates)
- computation: Complex calculations, synthetic ETFs, indices ("create ETF", "calculate", "weighted average")
- research: News, analysis, "why" questions ("why is X up?", "news about X")
- simple_lookup: Basic info ("what is AAPL?", "ticker info")

TIME CONTEXT (extract the temporal reference):
- "now" / "ahora" / "current" → "now"
- "today" / "hoy" → "today"  
- "yesterday" / "ayer" → "yesterday"
- "hace 1 hora" / "1 hour ago" → "1_hour_ago"
- Specific date → "YYYY-MM-DD"
- No time specified for real-time queries → "now"
- No time specified for historical → "today"

COMPLEXITY:
- simple: Single data fetch ("top gainers")
- multi_step: Multiple data sources ("compare X and Y")
- computation: Needs calculation ("synthetic ETF", "weighted index", "promedio ponderado")

CHART DETECTION (needs_chart = true if):
- "gráfico", "grafico", "chart", "plot", "visualizar", "visualize", "graph"

FILTER EXTRACTION:
- "market cap > 100M" → min_market_cap: 100000000
- "al menos 5 acciones" → min_tickers_per_sector: 5
- "volume > 1M" → min_volume: 1000000
- "price > $5" → min_price: 5

Respond ONLY with JSON:
{
    "category": "real_time|historical|computation|research|simple_lookup",
    "time_context": "now|today|yesterday|YYYY-MM-DD|1_hour_ago|etc",
    "complexity": "simple|multi_step|computation",
    "needs_chart": true|false,
    "filters": {"min_market_cap": null, "min_volume": null, "min_price": null, "max_price": null, "min_tickers_per_sector": null},
    "reasoning": "Brief explanation of why this classification"
}

USER QUERY: {query}
CURRENT TIME: {current_time}
"""

    # Pattern-based pre-classification for common queries (faster than LLM)
    FAST_PATTERNS = {
        # Multi-step/temporal patterns (check first - higher priority)
        r"(per|each|every|cada)\s*(hour|hora|range|rango)": (QueryCategory.COMPUTATION, Specialist.QUANT),
        r"(by|por)\s*(hour|hora|time\s*range)": (QueryCategory.COMPUTATION, Specialist.QUANT),
        r"(from|de)\s*\d{1,2}:\d{2}\s*(to|a|until|hasta)": (QueryCategory.COMPUTATION, Specialist.QUANT),
        r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}": (QueryCategory.COMPUTATION, Specialist.QUANT),  # 09:30-10:30
        r"(range|rango)\s*(of|de)?\s*(hour|hora|time)": (QueryCategory.COMPUTATION, Specialist.QUANT),
        r"(franja|slot)\s*(horari|hour)": (QueryCategory.COMPUTATION, Specialist.QUANT),  # franja horaria
        
        # Weekly/Monthly patterns - USE DAY_AGGS (fast)
        r"(of|de)\s*(the|la|esta)?\s*(week|semana)": (QueryCategory.COMPUTATION, Specialist.QUANT),
        r"(of|de)\s*(the|el|este)?\s*(month|mes)": (QueryCategory.COMPUTATION, Specialist.QUANT),
        r"(last|últim[oa]s?)\s*(\d+)?\s*(days?|días?|weeks?|semanas?|months?|meses?)": (QueryCategory.COMPUTATION, Specialist.QUANT),
        r"(this|esta)\s*(week|semana|month|mes)": (QueryCategory.COMPUTATION, Specialist.QUANT),
        r"(per|por)\s*(day|día)": (QueryCategory.COMPUTATION, Specialist.QUANT),  # per day = day_aggs
        r"(weekly|semanal|mensual|monthly)": (QueryCategory.COMPUTATION, Specialist.QUANT),
        
        # Gapper analysis with statistics → QUANT (needs execute_analysis)
        r"gappers?\s*.*(semana|week|porcentaje|percent|vwap|cuántos|how\s*many|total)": (QueryCategory.COMPUTATION, Specialist.QUANT),
        r"(semana|week|cuántos|total|porcentaje).*gappers?": (QueryCategory.COMPUTATION, Specialist.QUANT),
        
        # Real-time patterns (simple queries)
        r"^(top|mejores)\s*(gainers?|winners?|ganadores)\s*(today|hoy)?$": (QueryCategory.REAL_TIME, Specialist.SCANNER),
        r"^(top|peores)\s*(losers?|perdedores)\s*(today|hoy)?$": (QueryCategory.REAL_TIME, Specialist.SCANNER),
        r"precio\s*(actual|ahora)|current\s*price": (QueryCategory.REAL_TIME, Specialist.SCANNER),
        r"^gappers?\s*(today|hoy)?$": (QueryCategory.REAL_TIME, Specialist.SCANNER),  # Simple gappers query only
        r"halts?|squeeze": (QueryCategory.REAL_TIME, Specialist.SCANNER),
        
        # Historical patterns
        r"(ayer|yesterday|hace\s*\d+|ago|\d{4}-\d{2}-\d{2})": (QueryCategory.HISTORICAL, Specialist.HISTORIAN),
        r"(semana|week|mes|month)\s*(pasad|last)": (QueryCategory.HISTORICAL, Specialist.HISTORIAN),
        
        # Computation patterns
        r"(etf|etfs)\s*sint[eé]tic": (QueryCategory.COMPUTATION, Specialist.QUANT),
        r"sector(es)?\s*sint[eé]tic": (QueryCategory.COMPUTATION, Specialist.QUANT),
        r"(calcul|comput|weighted|ponder)": (QueryCategory.COMPUTATION, Specialist.QUANT),
        r"(índice|index)\s*(sint[eé]tic|custom)": (QueryCategory.COMPUTATION, Specialist.QUANT),
        
        # Research patterns - "why" questions about price movements
        r"(por\s*qu[eé]|porque|why)\s*.*(sube|baja|up|down|cay[oóe]|caer|dropped|fell|crashed|subió|bajó)": (QueryCategory.RESEARCH, Specialist.RESEARCHER),
        r"(why|por\s*qu[eé]|porque)\s+.{0,20}\s*\$?[A-Z]{1,5}\b": (QueryCategory.RESEARCH, Specialist.RESEARCHER),  # "why WRBY", "porque AAPL"
        r"(noticias?|news|análisis|analysis)": (QueryCategory.RESEARCH, Specialist.RESEARCHER),
        r"(sec\s*filing|8-k|10-k|insider)": (QueryCategory.RESEARCH, Specialist.RESEARCHER),
        r"(earnings?\s*(today|hoy|calendar|calendario|reporta|reports?))": (QueryCategory.REAL_TIME, Specialist.SCANNER),
        r"(ganancias|resultados)\s*(hoy|trimestral|de\s*hoy)": (QueryCategory.REAL_TIME, Specialist.SCANNER),
        r"(who|qui[eé]n)\s*(report|reporta)\s*(earnings|ganancias)": (QueryCategory.REAL_TIME, Specialist.SCANNER),
    }
    
    # Patterns that indicate using day_aggs (daily data) vs minute_aggs
    DAY_AGGS_PATTERNS = [
        r"(of|de)\s*(the|la|esta)?\s*(week|semana)",
        r"(of|de)\s*(the|el|este)?\s*(month|mes)",
        r"(last|últim[oa]s?)\s*(\d+)?\s*(days?|días?|weeks?|semanas?|months?|meses?)",
        r"(this|esta)\s*(week|semana|month|mes)",
        r"(per|por)\s*(day|día)",
        r"(weekly|semanal|mensual|monthly)",
        r"(\d+)\s*(days?|días?|weeks?|semanas?)",
    ]
    
    # Patterns that require minute_aggs (intraday data)
    MINUTE_AGGS_PATTERNS = [
        r"(per|each|every|cada)\s*(hour|hora)",
        r"(franja|slot)\s*(horari|hour)",
        r"(premarket|pre-market|afterhours|after-hours|postmarket)",
        r"\d{1,2}:\d{2}",  # Time like 09:30
        r"(intrad[ií]a|intraday)",
        r"(hora|hour)\s*(por|by|range)",
    ]
    
    # Chart detection pattern
    CHART_PATTERN = re.compile(r"(gr[aá]fico|chart|plot|visuali[zs]|graph)", re.IGNORECASE)
    
    # Filter extraction patterns
    FILTER_PATTERNS = {
        "min_market_cap": [
            (r"market\s*cap\s*[>≥]\s*(\d+)\s*([MBmb])?", lambda m: _parse_number(m.group(1), m.group(2))),
            (r"capitaliza[cz]i[oó]n\s*[>≥]\s*(\d+)\s*([MBmb])?", lambda m: _parse_number(m.group(1), m.group(2))),
        ],
        "min_volume": [
            (r"vol(ume|umen)?\s*[>≥]\s*(\d+)\s*([MKmk])?", lambda m: _parse_number(m.group(2), m.group(3))),
        ],
        "min_price": [
            (r"(precio|price)\s*[>≥]\s*\$?(\d+\.?\d*)", lambda m: float(m.group(2))),
        ],
        "max_price": [
            (r"(precio|price)\s*[<≤]\s*\$?(\d+\.?\d*)", lambda m: float(m.group(2))),
        ],
        "min_tickers_per_sector": [
            (r"(al\s*menos|at\s*least|m[ií]nimo)\s*(\d+)\s*(acciones?|stocks?|tickers?)", lambda m: int(m.group(2))),
            (r"(\d+)\s*(acciones?|stocks?|tickers?)\s*(m[ií]nimo|minimum)", lambda m: int(m.group(1))),
        ],
    }

    def __init__(self, llm_client=None):
        """
        Initialize router.
        
        Args:
            llm_client: Optional LLM client for complex classification.
                       If None, uses pattern-based routing only.
        """
        self.llm_client = llm_client
    
    def route(self, query: str, current_time: datetime = None) -> RoutingDecision:
        """
        Route a query to the appropriate specialist.
        
        Uses fast pattern matching first, falls back to LLM for ambiguous queries.
        
        Args:
            query: User's query
            current_time: Current datetime (for temporal context)
        
        Returns:
            RoutingDecision with classification details
        """
        if current_time is None:
            current_time = datetime.now()
        
        query_lower = query.lower()
        
        # Extract filters first (these are definitive)
        filters = self._extract_filters(query)
        needs_chart = bool(self.CHART_PATTERN.search(query))
        
        # Detect data source hint (day_aggs vs minute_aggs)
        data_hint = self._detect_data_hint(query_lower)
        
        # Try fast pattern matching
        for pattern, (category, specialist) in self.FAST_PATTERNS.items():
            if re.search(pattern, query_lower):
                time_context = self._extract_time_context(query_lower, category)
                complexity = self._determine_complexity(query_lower, category)
                
                # Override specialist for computation-heavy queries
                if category == QueryCategory.COMPUTATION or complexity == "computation":
                    specialist = Specialist.QUANT
                
                logger.info("router_fast_match", 
                           pattern=pattern, 
                           category=category.value,
                           specialist=specialist.value,
                           data_hint=data_hint)
                
                return RoutingDecision(
                    category=category,
                    specialist=specialist,
                    time_context=time_context,
                    complexity=complexity,
                    needs_chart=needs_chart,
                    filters=filters,
                    confidence=0.9,
                    reasoning=f"Pattern match: {pattern}",
                    data_hint=data_hint
                )
        
        # Default routing for unmatched queries
        # If has filters or chart, likely computation
        if filters or needs_chart:
            category = QueryCategory.COMPUTATION
            specialist = Specialist.QUANT
        else:
            category = QueryCategory.REAL_TIME
            specialist = Specialist.SCANNER
        
        time_context = self._extract_time_context(query_lower, category)
        complexity = self._determine_complexity(query_lower, category)
        
        logger.info("router_default", 
                   category=category.value,
                   specialist=specialist.value,
                   has_filters=bool(filters),
                   needs_chart=needs_chart,
                   data_hint=data_hint)
        
        return RoutingDecision(
            category=category,
            specialist=specialist,
            time_context=time_context,
            complexity=complexity,
            needs_chart=needs_chart,
            filters=filters,
            confidence=0.7,
            reasoning="Default routing (no pattern match)",
            data_hint=data_hint
        )
    
    def _detect_data_hint(self, query: str) -> str:
        """
        Detect whether to use day_aggs or minute_aggs based on query.
        
        Uses semantic routing (embeddings) first for natural language understanding,
        falls back to regex patterns for explicit keywords.
        
        Semantic router benefits:
        - "últimos 7 días" = "semana pasada" = "last week" → day_aggs
        - "por franja horaria" = "per hour" = "premarket" → minute_aggs
        - More robust to typos and natural language variation
        
        Returns:
            'day_aggs': For daily/weekly/monthly analysis (10-15x faster with Parquet)
            'minute_aggs': For intraday/hourly analysis
            'auto': Let LLM decide
        """
        # Try semantic routing first (more intelligent, handles variations)
        try:
            from .semantic_router import get_semantic_router
            semantic = get_semantic_router()
            hint, confidence = semantic.get_data_hint_with_confidence(query)
            
            if hint != 'auto' and confidence >= 0.5:
                logger.info(
                    "semantic_router_decision",
                    query=query[:50],
                    data_hint=hint,
                    confidence=round(confidence, 3)
                )
                return hint
        except Exception as e:
            logger.debug("Semantic router not available, using regex", error=str(e))
        
        # Fallback to regex patterns
        # Check for minute_aggs patterns first (more specific)
        for pattern in self.MINUTE_AGGS_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                logger.info("regex_router_decision", pattern=pattern, data_hint="minute_aggs")
                return "minute_aggs"
        
        # Check for day_aggs patterns
        for pattern in self.DAY_AGGS_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                logger.info("regex_router_decision", pattern=pattern, data_hint="day_aggs")
                return "day_aggs"
        
        # Default: auto (let LLM decide based on context)
        return "auto"
    
    async def route_with_llm(self, query: str, current_time: datetime = None) -> RoutingDecision:
        """
        Route using LLM for complex/ambiguous queries.
        
        This is slower but more accurate for edge cases.
        """
        if current_time is None:
            current_time = datetime.now()
        
        # First try fast routing
        fast_result = self.route(query, current_time)
        if fast_result.confidence >= 0.9:
            return fast_result
        
        # For lower confidence, use LLM if available
        if not self.llm_client:
            return fast_result
        
        try:
            prompt = self.ROUTING_PROMPT.format(
                query=query,
                current_time=current_time.strftime("%Y-%m-%d %H:%M")
            )
            
            response = await self.llm_client.generate_content_async(
                contents=prompt,
                config={"temperature": 0}
            )
            
            # Parse JSON response
            text = response.text.strip()
            # Extract JSON from markdown if present
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            data = json.loads(text)
            
            category = QueryCategory(data.get("category", "real_time"))
            specialist = self._category_to_specialist(category, data.get("complexity", "simple"))
            
            return RoutingDecision(
                category=category,
                specialist=specialist,
                time_context=data.get("time_context", "now"),
                complexity=data.get("complexity", "simple"),
                needs_chart=data.get("needs_chart", False),
                filters=data.get("filters", {}),
                confidence=0.95,
                reasoning=data.get("reasoning", "LLM classification")
            )
        except Exception as e:
            logger.warning("router_llm_failed", error=str(e))
            return fast_result
    
    def _extract_time_context(self, query: str, category: QueryCategory) -> str:
        """Extract temporal context from query."""
        # Specific patterns
        if re.search(r"ayer|yesterday", query):
            return "yesterday"
        if re.search(r"hace\s*(\d+)\s*hora", query):
            match = re.search(r"hace\s*(\d+)\s*hora", query)
            return f"{match.group(1)}_hours_ago"
        if re.search(r"(\d+)\s*hour.*ago", query):
            match = re.search(r"(\d+)\s*hour.*ago", query)
            return f"{match.group(1)}_hours_ago"
        if re.search(r"\d{4}-\d{2}-\d{2}", query):
            match = re.search(r"(\d{4}-\d{2}-\d{2})", query)
            return match.group(1)
        if re.search(r"(semana|week)\s*(pasad|last)", query):
            return "last_week"
        
        # Default based on category
        if category == QueryCategory.HISTORICAL:
            return "today"  # Historical queries default to today's completed data
        return "now"
    
    def _determine_complexity(self, query: str, category: QueryCategory) -> str:
        """Determine query complexity."""
        if category == QueryCategory.COMPUTATION:
            return "computation"
        
        # Multi-step / computation indicators
        computation_patterns = [
            r"(per|each|every|cada)\s*(hour|hora|range)",  # Per hour analysis
            r"(from|de)\s*\d{1,2}:\d{2}\s*(to|a)",         # Time range
            r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}",          # 09:30-10:30
            r"(until|hasta)\s*\d{1,2}:\d{2}",              # Until 16:00
            r"(loop|iterate|for\s+each)",                  # Explicit iteration
        ]
        for pattern in computation_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return "computation"
        
        # Multi-step indicators
        multi_step_patterns = [
            r"(compar|versus|vs\.?)",
            r"(y\s+luego|then|después)",
            r"(analiz.*y.*calcul)",
            r"(and\s+then|and\s+so\s+on)",
        ]
        for pattern in multi_step_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return "multi_step"
        
        return "simple"
    
    def _extract_filters(self, query: str) -> Dict[str, Any]:
        """Extract filter parameters from query."""
        filters = {}
        
        for filter_name, patterns in self.FILTER_PATTERNS.items():
            for pattern, extractor in patterns:
                match = re.search(pattern, query, re.IGNORECASE)
                if match:
                    try:
                        filters[filter_name] = extractor(match)
                        logger.debug("filter_extracted", filter=filter_name, value=filters[filter_name])
                    except Exception as e:
                        logger.warning("filter_extraction_failed", filter=filter_name, error=str(e))
        
        return filters
    
    def _category_to_specialist(self, category: QueryCategory, complexity: str) -> Specialist:
        """Map category to specialist agent."""
        if complexity == "computation":
            return Specialist.QUANT
        
        mapping = {
            QueryCategory.REAL_TIME: Specialist.SCANNER,
            QueryCategory.HISTORICAL: Specialist.HISTORIAN,
            QueryCategory.COMPUTATION: Specialist.QUANT,
            QueryCategory.RESEARCH: Specialist.RESEARCHER,
            QueryCategory.SIMPLE_LOOKUP: Specialist.GENERAL,
        }
        return mapping.get(category, Specialist.GENERAL)


def _parse_number(value: str, suffix: str = None) -> float:
    """Parse a number with optional M/B/K suffix."""
    num = float(value)
    if suffix:
        suffix = suffix.upper()
        if suffix == "B":
            num *= 1_000_000_000
        elif suffix == "M":
            num *= 1_000_000
        elif suffix == "K":
            num *= 1_000
    return num


# Specialist tool configurations
SPECIALIST_TOOLS = {
    Specialist.SCANNER: [
        "get_market_snapshot",
        "get_ticker_info",
        "get_earnings_calendar",
        "execute_analysis",  # Added: for complex queries that slip through routing
    ],
    Specialist.HISTORIAN: [
        "get_historical_data",
        "get_top_movers",
        "get_top_movers_hourly",  # For "top per hour" queries
        "execute_analysis",  # For SQL queries
    ],
    Specialist.QUANT: [
        "classify_synthetic_sectors",
        "execute_analysis",
        "get_market_snapshot",  # May need current data for calculations
        "get_top_movers_hourly",  # For hourly analysis
    ],
    Specialist.RESEARCHER: [
        "quick_news",       # Fast Benzinga lookup (<1s) - USE FIRST
        "research_ticker",  # Deep research (60-90s) - USE ONLY if user asks for more
        "get_ticker_info",
    ],
    Specialist.GENERAL: [
        "get_ticker_info",
        "get_market_snapshot",
    ],
}


def get_tools_for_specialist(specialist: Specialist) -> List[str]:
    """Get the list of tools available for a specialist."""
    return SPECIALIST_TOOLS.get(specialist, [])
