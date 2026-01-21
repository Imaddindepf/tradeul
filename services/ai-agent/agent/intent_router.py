"""
Intent Router - Pure Semantic Classification (2025 Architecture)
================================================================

NO REGEX. Only embeddings.

This router classifies user queries into intents using semantic similarity,
not keyword matching. The LLM knows financial concepts - we just need to
route to the right tools.

Intents:
- HISTORICAL_ANALYSIS: Past data analysis (gappers, top movers, statistics, trends)
- REALTIME_SCAN: Current market state (live prices, current gainers, alerts)  
- RESEARCH: News, "why" questions, SEC filings
- TICKER_INFO: Basic ticker lookup
- SYNTHETIC_ETF: Create thematic portfolios

Each intent maps to specific tools, not to hardcoded SQL.
"""

import re
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
import structlog

logger = structlog.get_logger(__name__)

# Lazy load model
_model = None


def _get_model():
    """Lazy load sentence transformer model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Loaded intent router model", model="all-MiniLM-L6-v2")
        except ImportError:
            logger.error("sentence-transformers not installed")
            return None
    return _model


class Intent(Enum):
    """User intent categories."""
    HISTORICAL_ANALYSIS = "historical_analysis"  # Analyze past data
    REALTIME_SCAN = "realtime_scan"              # Current market state
    RESEARCH = "research"                         # News, why questions
    TICKER_INFO = "ticker_info"                   # Basic lookups
    SYNTHETIC_ETF = "synthetic_etf"               # Thematic portfolios


@dataclass
class IntentClassification:
    """Result of intent classification."""
    intent: Intent
    confidence: float
    data_granularity: str  # "daily" or "intraday" - for choosing data source
    requires_code: bool    # True if needs execute_analysis
    
    
# Intent exemplars - queries that clearly belong to each intent
# The model learns from these without hardcoding rules
INTENT_EXEMPLARS = {
    Intent.HISTORICAL_ANALYSIS: [
        # English - Analysis queries
        "how many gappers were there this week",
        "what percentage closed below vwap",
        "top stocks of the week",
        "best performers last month",
        "analyze gap patterns",
        "stocks with highest volume this week",
        "momentum analysis for the past 5 days",
        "which stocks had 3 consecutive up days",
        "average gap percentage this month",
        "compare weekly performance",
        "breakout analysis",
        "reversal patterns this week",
        "high volume stocks analysis",
        "relative strength vs SPY",
        "stocks that beat the market",
        # Added for better coverage
        "stocks with high volume",
        "high volume movers this week",
        "moving average analysis",
        "200 day moving average",
        "price vs moving average",
        "breakouts this month",
        "monthly breakouts",
        "resistance breakouts",
        # IMPORTANT: Weekly/Historical gainers (NOT realtime)
        "top gainers of the week",
        "top gainers this week",
        "top gainers last week",
        "top gainers of the month",
        "weekly top gainers",
        "best gainers this week",
        "gainers of the past week",
        "top losers of the week",
        "weekly losers",
        "gainers above market cap",
        "top gainers above 1m market cap",
        "stocks above 1 million market cap",
        "large cap gainers this week",
        # Date-specific queries  
        "top gappers del 16 de enero",
        "gappers on january 16",
        "best movers on friday",
        "performance on a specific date",
        "what happened on monday",
        "top stocks yesterday",
        "gappers de ayer",
        "mejores del lunes",
        "support analysis",
        "technical analysis",
        # Date ranges (CRITICAL - override "today" keyword when dates present)
        "desde el 24 de diciembre hasta el 31 de diciembre",
        "from december 24 to december 31",
        "between january 1 and january 15",
        "entre el 1 y el 15 de enero",
        "acciones baratas que gapearon en diciembre",
        "cheap stocks that gapped in december",
        "stocks under $10 from last week",
        "acciones menores de $10 de la semana pasada",
        "gap analysis from specific dates",
        "volatility analysis for date range",
        "ATR analysis for december",
        "análisis de ATR de diciembre",
        
        # Spanish - Analysis queries  
        "cuántos gappers hubo esta semana",
        "qué porcentaje cerró debajo del vwap",
        "mejores acciones de la semana",
        "análisis de gaps",
        "acciones con mayor volumen",
        "análisis de momentum",
        "patrones de reversión",
        "estadísticas de la semana",
        "rendimiento mensual",
        "comparar rendimiento semanal",
        # Added for better coverage
        "stocks con volumen alto",
        "acciones de alto volumen",
        "promedio móvil",
        "media móvil de 200",
        "breakouts del mes",
        "rupturas de resistencia",
        "análisis técnico",
        # IMPORTANT: Weekly gainers in Spanish
        "top gainers de la semana",
        "mejores ganadores de la semana",
        "top gainers semana pasada",
        "gainers semanales",
        "acciones con mayor ganancia semanal",
        "top perdedores de la semana",
    ],
    
    Intent.REALTIME_SCAN: [
        # English - Real-time queries
        "top gainers right now",
        "what's moving today",
        "current price of AAPL",
        "show me today's losers",
        "alert me when there's a gapper",
        "live market scan",
        "premarket movers",
        "what's hot right now",
        "biggest movers today",
        "current market snapshot",
        "real-time gainers",
        "notify me if TSLA gaps up",
        "watch for breakouts",
        
        # Spanish - Real-time queries
        "top gainers ahora",
        "qué está subiendo hoy",
        "precio actual de AAPL",
        "avísame si hay un gapper",
        "escaneo del mercado",
        "qué está caliente ahora",
        "movimientos de hoy",
        "alerta de breakout",
    ],
    
    Intent.RESEARCH: [
        # English - Research queries
        "why is AAPL up today",
        "news about Tesla",
        "what happened to NVDA",
        "SEC filings for AMZN",
        "why did the stock crash",
        "earnings report analysis",
        "insider trading activity",
        "what's the sentiment on TSLA",
        "analyst ratings",
        "recent news",
        
        # Spanish - Research queries
        "por qué sube AAPL",
        "noticias de Tesla",
        "qué pasó con NVDA",
        "por qué cayó la acción",
        "análisis de earnings",
        "actividad de insiders",
        "sentimiento del mercado",
    ],
    
    Intent.TICKER_INFO: [
        # Basic lookups
        "what is AAPL",
        "ticker info for MSFT",
        "market cap of Google",
        "what sector is NVDA in",
        "company information",
        "qué es AAPL",
        "información de MSFT",
        "capitalización de mercado",
        "en qué sector está",
    ],
    
    Intent.SYNTHETIC_ETF: [
        # Thematic portfolios
        "create a nuclear energy ETF",
        "build an AI portfolio",
        "synthetic cannabis ETF",
        "space stocks basket",
        "EV sector ETF",
        "biotech portfolio",
        "crear ETF de energía nuclear",
        "portafolio de IA",
        "ETF sintético de cannabis",
        "canasta de acciones espaciales",
    ],
}


# Which tools each intent can use
INTENT_TOOLS = {
    Intent.HISTORICAL_ANALYSIS: [
        "execute_analysis",     # For SQL/code - THE ONLY TOOL for complex queries
        # get_top_movers removed - it confuses the model when calculating gaps/vwap
    ],
    Intent.REALTIME_SCAN: [
        "get_market_snapshot",  # Current prices
        "get_ticker_info",      # Quick lookups
        "get_earnings_calendar",
    ],
    Intent.RESEARCH: [
        "research_ticker",      # News, X.com, web
        "quick_news",           # Fast news lookup
    ],
    Intent.TICKER_INFO: [
        "get_ticker_info",
        "get_market_snapshot",
    ],
    Intent.SYNTHETIC_ETF: [
        "classify_synthetic_sectors",
        "get_market_snapshot",
    ],
}


# Data granularity hints - does this need daily or intraday data?
GRANULARITY_EXEMPLARS = {
    "daily": [
        "this week", "this month", "last 7 days", "weekly", "monthly",
        "semana", "mes", "últimos días", "semanal", "mensual",
        "gap analysis", "consecutive days", "trend",
    ],
    "intraday": [
        "by hour", "per hour", "hourly", "premarket", "after hours",
        "morning session", "opening bell", "first hour",
        "por hora", "franja horaria", "intradía", "apertura",
    ],
}


class IntentRouter:
    """
    Pure semantic intent classification.
    
    NO REGEX. Uses embeddings to understand query meaning.
    Exception: Date detection uses patterns to force HISTORICAL_ANALYSIS.
    """
    
    CONFIDENCE_THRESHOLD = 0.35  # Lower threshold - let LLM decide edge cases
    
    # NOW patterns that FORCE realtime (snapshot from Redis)
    # These indicate the user wants CURRENT market data, not historical analysis
    NOW_PATTERNS = [
        # Spanish - present/now keywords
        r'\bahora\b',                    # "ahora"
        r'\ben\s+este\s+momento\b',      # "en este momento"
        r'\bahora\s+mismo\b',            # "ahora mismo"
        r'\bactual(?:es|mente)?\b',      # "actual", "actualmente"
        r'\ben\s+vivo\b',                # "en vivo"
        r'\ben\s+tiempo\s+real\b',       # "en tiempo real"
        r'\bsnapshot\b',                 # "snapshot"
        # English - present/now keywords
        r'\bright\s+now\b',              # "right now"
        r'\bcurrently\b',                # "currently"
        r'\bcurrent\b',                  # "current"
        r'\blive\b',                     # "live"
        r'\breal[\s-]?time\b',           # "real-time", "realtime"
        r'\bat\s+the\s+moment\b',        # "at the moment"
        # "hoy/today" WITHOUT calculation words (gappers needs historical)
        # This is handled separately in _is_simple_today_query
    ]
    
    # Words that indicate calculation needed (even with "hoy")
    CALCULATION_WORDS = [
        'gap', 'gapper', 'vwap', 'atr', 'rsi', 'sma', 'ema', 
        'promedio', 'average', 'moving', 'móvil',
        'cerró', 'closed', 'abrió', 'opened',
        'porcentaje', 'percentage', 'estadística', 'statistic',
    ]
    
    # Date patterns that FORCE historical analysis (overrides semantic classification)
    # These indicate the user wants to analyze specific past dates, not "today"
    DATE_PATTERNS = [
        # Date ranges with months: "desde enero hasta marzo", "from january to march"
        r'desde\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+hasta',
        r'from\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+to',
        # Date ranges with numbers: "desde el 24 hasta", "from december 24 to"
        r'desde\s+(?:el\s+)?\d{1,2}\s+(?:de\s+)?\w+\s+hasta',
        r'from\s+\w+\s+\d{1,2}(?:st|nd|rd|th)?\s+to',
        r'between\s+\w+\s+\d{1,2}',
        r'entre\s+(?:el\s+)?\d{1,2}\s+(?:y|de)',
        # Specific months: "en diciembre", "in december", "de enero"
        r'(?:en|de|in|of|during)\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+(?:de\s+)?20\d{2})?',
        # Specific dates: "el 24 de diciembre", "on december 24"
        r'(?:el|on)\s+\d{1,2}\s+(?:de\s+)?\w+',
        # Week references: "semana pasada", "last week", "esta semana"  
        r'(?:la\s+)?semana\s+(?:pasada|anterior)',
        r'last\s+week',
        r'(?:this|past)\s+(?:week|month)',
        # Year with month: "diciembre 2025", "december 2025"
        r'(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|january|february|march|april|may|june|july|august|september|october|november|december)\s+(?:de\s+)?20\d{2}',
    ]
    
    def __init__(self):
        self._model = None
        self._intent_embeddings: Dict[Intent, np.ndarray] = {}
        self._granularity_embeddings: Dict[str, np.ndarray] = {}
        self._initialized = False
        self._date_patterns_compiled = None
        self._now_patterns_compiled = None
    
    def _compile_now_patterns(self):
        """Compile NOW patterns once for performance."""
        import re
        if self._now_patterns_compiled is None:
            self._now_patterns_compiled = [
                re.compile(p, re.IGNORECASE) for p in self.NOW_PATTERNS
            ]
        return self._now_patterns_compiled
    
    def _is_realtime_query(self, query: str) -> bool:
        """
        Check if query is asking for CURRENT/LIVE data.
        Returns True if should use get_market_snapshot (Redis).
        """
        query_lower = query.lower()
        
        # Check NOW_PATTERNS first
        patterns = self._compile_now_patterns()
        for pattern in patterns:
            if pattern.search(query):
                return True
        
        # Check "hoy/today" WITHOUT calculation words
        has_today = bool(re.search(r'\b(hoy|today)\b', query_lower))
        if has_today:
            # If "hoy/today" but NO calculation words → realtime
            has_calc = any(word in query_lower for word in self.CALCULATION_WORDS)
            if not has_calc:
                return True
        
        return False
    
    def _compile_date_patterns(self):
        """Compile date patterns once for performance."""
        import re
        if self._date_patterns_compiled is None:
            self._date_patterns_compiled = [
                re.compile(p, re.IGNORECASE) for p in self.DATE_PATTERNS
            ]
        return self._date_patterns_compiled
    
    def _has_specific_dates(self, query: str) -> bool:
        """
        Check if query contains specific date references.
        When dates are present, ALWAYS use HISTORICAL_ANALYSIS.
        """
        patterns = self._compile_date_patterns()
        for pattern in patterns:
            if pattern.search(query):
                return True
        return False
    
    def _ensure_initialized(self) -> bool:
        """Lazy initialization."""
        if self._initialized:
            return self._model is not None
        
        self._model = _get_model()
        if self._model is None:
            self._initialized = True
            return False
        
        # Pre-compute intent embeddings
        for intent, exemplars in INTENT_EXEMPLARS.items():
            embeddings = self._model.encode(exemplars, normalize_embeddings=True)
            self._intent_embeddings[intent] = embeddings
        
        # Pre-compute granularity embeddings
        for granularity, keywords in GRANULARITY_EXEMPLARS.items():
            embeddings = self._model.encode(keywords, normalize_embeddings=True)
            self._granularity_embeddings[granularity] = embeddings
        
        self._initialized = True
        logger.info("Intent router initialized", 
                   intents=len(self._intent_embeddings),
                   model="all-MiniLM-L6-v2")
        return True
    
    def classify(self, query: str) -> IntentClassification:
        """
        Classify a query into an intent using semantic similarity.
        
        Returns intent, confidence, and metadata.
        
        Priority:
        1. REALTIME keywords (ahora, now, hoy without calculations) → REALTIME_SCAN
        2. DATE patterns (specific dates, weeks, months) → HISTORICAL_ANALYSIS
        3. Semantic similarity → Best matching intent
        """
        if not self._ensure_initialized():
            # Fallback if model not available
            return IntentClassification(
                intent=Intent.HISTORICAL_ANALYSIS,
                confidence=0.0,
                data_granularity="daily",
                requires_code=True
            )
        
        # STEP 1: Check for REALTIME keywords - FORCES realtime_scan (snapshot)
        if self._is_realtime_query(query):
            logger.info(
                "intent_forced_realtime",
                query=query[:50],
                intent="realtime_scan",
                reason="now_keywords_detected"
            )
            return IntentClassification(
                intent=Intent.REALTIME_SCAN,
                confidence=0.95,  # High confidence when NOW detected
                data_granularity="intraday",
                requires_code=False
            )
        
        # STEP 2: Check for specific dates - FORCES historical analysis
        has_dates = self._has_specific_dates(query)
        if has_dates:
            logger.info(
                "intent_forced_by_dates",
                query=query[:50],
                intent="historical_analysis",
                reason="specific_dates_detected"
            )
            return IntentClassification(
                intent=Intent.HISTORICAL_ANALYSIS,
                confidence=0.95,  # High confidence when dates detected
                data_granularity="daily",
                requires_code=True
            )
        
        # STEP 3: Semantic classification (only if no explicit keywords)
        query_embedding = self._model.encode(query, normalize_embeddings=True)
        
        # Find best matching intent
        best_intent = Intent.HISTORICAL_ANALYSIS
        best_score = 0.0
        
        for intent, exemplar_embeddings in self._intent_embeddings.items():
            similarities = np.dot(exemplar_embeddings, query_embedding)
            max_similarity = float(np.max(similarities))
            
            if max_similarity > best_score:
                best_score = max_similarity
                best_intent = intent
        
        # Determine data granularity
        granularity = self._detect_granularity(query_embedding)
        
        # Determine if code execution is needed
        requires_code = best_intent == Intent.HISTORICAL_ANALYSIS and best_score > 0.3
        
        logger.info(
            "intent_classified",
            query=query[:50],
            intent=best_intent.value,
            confidence=round(best_score, 3),
            granularity=granularity,
            requires_code=requires_code
        )
        
        return IntentClassification(
            intent=best_intent,
            confidence=best_score,
            data_granularity=granularity,
            requires_code=requires_code
        )
    
    def _detect_granularity(self, query_embedding: np.ndarray) -> str:
        """Detect if query needs daily or intraday data."""
        daily_score = 0.0
        intraday_score = 0.0
        
        if "daily" in self._granularity_embeddings:
            similarities = np.dot(self._granularity_embeddings["daily"], query_embedding)
            daily_score = float(np.max(similarities))
        
        if "intraday" in self._granularity_embeddings:
            similarities = np.dot(self._granularity_embeddings["intraday"], query_embedding)
            intraday_score = float(np.max(similarities))
        
        return "intraday" if intraday_score > daily_score else "daily"
    
    def get_tools_for_intent(self, intent: Intent) -> List[str]:
        """Get available tools for an intent."""
        return INTENT_TOOLS.get(intent, ["execute_analysis"])
    
    def explain(self, query: str) -> Dict:
        """Explain classification for debugging."""
        if not self._ensure_initialized():
            return {"error": "Model not available"}
        
        query_embedding = self._model.encode(query, normalize_embeddings=True)
        
        explanation = {"query": query, "intents": {}}
        
        for intent, exemplar_embeddings in self._intent_embeddings.items():
            similarities = np.dot(exemplar_embeddings, query_embedding)
            top_idx = np.argmax(similarities)
            
            explanation["intents"][intent.value] = {
                "score": round(float(np.max(similarities)), 3),
                "best_match": INTENT_EXEMPLARS[intent][top_idx],
            }
        
        # Sort by score
        sorted_intents = sorted(
            explanation["intents"].items(),
            key=lambda x: x[1]["score"],
            reverse=True
        )
        explanation["ranking"] = [i[0] for i in sorted_intents]
        explanation["winner"] = sorted_intents[0][0] if sorted_intents else None
        
        return explanation


# Singleton instance
_router: Optional[IntentRouter] = None


def get_intent_router() -> IntentRouter:
    """Get or create the global intent router."""
    global _router
    if _router is None:
        _router = IntentRouter()
    return _router


def classify_intent(query: str) -> IntentClassification:
    """Quick intent classification."""
    return get_intent_router().classify(query)
