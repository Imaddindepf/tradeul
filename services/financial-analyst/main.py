"""
Financial Analyst Service - Experimental

Usa Gemini 2.0 con Google Search para generar reportes financieros en tiempo real.
Este es un servicio experimental - NO subir a git sin aprobación.
"""

import os
import json
import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from google.genai.types import Tool, GoogleSearch
import redis.asyncio as aioredis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
GOOGLE_API_KEY = os.getenv("GOOGL_API_KEY", "")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

# Initialize Gemini client
client = genai.Client(api_key=GOOGLE_API_KEY)

# ============== Redis Cache ==============
# TTL: 20 hours - covers full trading day + after hours
# Cleanup: managed by data_maintenance at 3:00 AM EST
CACHE_TTL_SECONDS = 20 * 60 * 60  # 20 hours
CACHE_PREFIX = "fan:report:"

redis_client: Optional[aioredis.Redis] = None


async def init_redis():
    """Initialize Redis connection"""
    global redis_client
    try:
        redis_client = aioredis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD if REDIS_PASSWORD else None,
            decode_responses=True
        )
        await redis_client.ping()
        logger.info(f"Redis connected: {REDIS_HOST}:{REDIS_PORT}")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        redis_client = None


async def close_redis():
    """Close Redis connection"""
    global redis_client
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")


async def get_cached_report(ticker: str, lang: str) -> Optional[Dict[str, Any]]:
    """Get report from Redis cache"""
    if not redis_client:
        return None
    
    cache_key = f"{CACHE_PREFIX}{ticker.upper()}:{lang}"
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            data = json.loads(cached)
            logger.info(f"[{ticker}] Cache HIT (Redis)")
            return data
    except Exception as e:
        logger.warning(f"[{ticker}] Cache GET error: {e}")
    return None


async def set_cached_report(ticker: str, lang: str, data: Dict[str, Any]):
    """Store report in Redis cache with TTL"""
    if not redis_client:
        return
    
    cache_key = f"{CACHE_PREFIX}{ticker.upper()}:{lang}"
    try:
        await redis_client.setex(
            cache_key,
            CACHE_TTL_SECONDS,
            json.dumps(data)
        )
        logger.info(f"[{ticker}] Cache SET (Redis, TTL: {CACHE_TTL_SECONDS}s)")
    except Exception as e:
        logger.warning(f"[{ticker}] Cache SET error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown"""
    await init_redis()
    yield
    await close_redis()


app = FastAPI(
    title="Financial Analyst",
    description="Real-time financial analysis using Gemini with Google Search",
    version="0.2.0-experimental",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== Models ==============

class AnalystRating(BaseModel):
    firm: str
    rating: str
    price_target: Optional[float] = None
    date: Optional[str] = None

class RiskFactor(BaseModel):
    category: str
    description: str
    severity: str  # Low/Medium/High/Critical

class Competitor(BaseModel):
    ticker: str
    name: str
    market_cap: Optional[str] = None
    competitive_advantage: Optional[str] = None

class TechnicalSummary(BaseModel):
    trend: str  # Bullish/Bearish/Neutral
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None
    rsi_status: Optional[str] = None  # Oversold/Neutral/Overbought
    ma_50_status: Optional[str] = None  # Above/Below
    ma_200_status: Optional[str] = None  # Above/Below
    pattern: Optional[str] = None  # Head & Shoulders, Cup & Handle, etc.

class ShortInterest(BaseModel):
    short_percent_of_float: Optional[float] = None
    days_to_cover: Optional[float] = None
    short_ratio_change: Optional[str] = None  # Increasing/Decreasing/Stable
    squeeze_potential: Optional[str] = None  # Low/Medium/High

class UpcomingCatalyst(BaseModel):
    event: str
    date: Optional[str] = None
    importance: str  # Low/Medium/High

class InsiderActivity(BaseModel):
    type: str  # Buy/Sell
    insider_name: Optional[str] = None
    title: Optional[str] = None
    shares: Optional[int] = None
    value: Optional[str] = None
    date: Optional[str] = None

class FinancialHealth(BaseModel):
    revenue_growth_yoy: Optional[float] = None
    earnings_growth_yoy: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    cash_position: Optional[str] = None  # Strong/Adequate/Weak
    profit_margin: Optional[float] = None
    roe: Optional[float] = None  # Return on Equity

class NewsSentiment(BaseModel):
    overall: str  # Bullish/Neutral/Bearish
    score: Optional[float] = None  # -100 to 100
    trending_topics: List[str] = []
    recent_headlines: List[str] = []

class FinancialReport(BaseModel):
    ticker: str
    company_name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    exchange: Optional[str] = None
    ceo: Optional[str] = None
    website: Optional[str] = None
    employees: Optional[int] = None
    business_summary: str
    special_status: Optional[str] = None
    
    # Analyst Consensus
    consensus_rating: Optional[str] = None
    analyst_ratings: List[AnalystRating] = []
    average_price_target: Optional[float] = None
    price_target_high: Optional[float] = None
    price_target_low: Optional[float] = None
    num_analysts: Optional[int] = None
    
    # Valuation Metrics
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    pb_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    ev_ebitda: Optional[float] = None
    peg_ratio: Optional[float] = None
    
    # Dividend
    dividend_yield: Optional[float] = None
    dividend_frequency: Optional[str] = None
    ex_dividend_date: Optional[str] = None
    
    # NEW: Technical Analysis
    technical: Optional[TechnicalSummary] = None
    
    # NEW: Short Interest
    short_interest: Optional[ShortInterest] = None
    
    # NEW: Competitive Landscape
    competitors: List[Competitor] = []
    competitive_moat: Optional[str] = None  # Wide/Narrow/None
    market_position: Optional[str] = None  # Leader/Challenger/Follower/Niche
    
    # NEW: Financial Health
    financial_health: Optional[FinancialHealth] = None
    financial_grade: Optional[str] = None  # A/B/C/D/F
    
    # NEW: Upcoming Catalysts
    upcoming_catalysts: List[UpcomingCatalyst] = []
    earnings_date: Optional[str] = None
    
    # NEW: Insider Activity
    insider_activity: List[InsiderActivity] = []
    insider_sentiment: Optional[str] = None  # Bullish/Neutral/Bearish
    
    # NEW: News Sentiment
    news_sentiment: Optional[NewsSentiment] = None
    
    # Risk Assessment
    risk_sentiment: Optional[str] = None
    risk_factors: List[RiskFactor] = []
    risk_score: Optional[int] = None  # 1-10 scale
    critical_event: Optional[str] = None
    
    # Meta
    generated_at: str
    sources: List[str] = []


class ReportRequest(BaseModel):
    ticker: str
    language: str = "en"


class DBMetadata(BaseModel):
    """Metadata enriquecida desde múltiples fuentes internas"""
    # Campos básicos de ticker_metadata
    symbol: Optional[str] = None
    company_name: Optional[str] = None
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None
    shares_outstanding: Optional[float] = None
    free_float: Optional[float] = None
    free_float_percent: Optional[float] = None
    description: Optional[str] = None
    homepage_url: Optional[str] = None
    total_employees: Optional[int] = None
    cik: Optional[str] = None
    list_date: Optional[str] = None
    is_etf: Optional[bool] = None
    type: Optional[str] = None
    
    # Indicadores técnicos DIARIOS desde Screener
    technical_daily: Optional[Dict[str, Any]] = None
    
    # Resumen de actividad insider + CEO/CFO
    insider_summary: Optional[Dict[str, Any]] = None
    
    # Precio actual desde Polygon snapshot
    price_snapshot: Optional[Dict[str, Any]] = None
    
    # Fundamentales desde SEC XBRL (P/E, P/B, P/S, EV/EBITDA)
    fundamentals_xbrl: Optional[Dict[str, Any]] = None
    
    class Config:
        extra = "allow"  # Permitir campos adicionales


class ReportRequestWithMetadata(BaseModel):
    """Request con metadata de BD para optimizar el prompt"""
    db_metadata: Optional[DBMetadata] = None


# ============== Gemini Integration ==============

def _format_market_cap(mc: float) -> str:
    """Formatear market cap para el prompt"""
    if mc >= 1e12:
        return f"${mc/1e12:.2f}T"
    elif mc >= 1e9:
        return f"${mc/1e9:.2f}B"
    elif mc >= 1e6:
        return f"${mc/1e6:.2f}M"
    return f"${mc:,.0f}"


def _build_known_data_section(db_metadata: Optional[Dict[str, Any]]) -> tuple[str, dict]:
    """
    Construir sección de datos conocidos si tenemos metadata de BD.
    Retorna (sección_texto, valores_prefijados)
    
    Incluye:
    - Metadata básica: company_name, sector, industry, exchange, etc.
    - technical_daily: RSI-14, MA50, MA200, 52W High/Low (diarios)
    - insider_summary: resumen actividad + CEO/CFO
    - price_snapshot: precio actual y cambio
    """
    if not db_metadata or not any(db_metadata.values()):
        return "", {}
    
    known_fields = []
    prefilled = {}
    
    # === METADATA BÁSICA ===
    if db_metadata.get("company_name"):
        known_fields.append(f"- Company Name: {db_metadata['company_name']}")
        prefilled["company_name"] = db_metadata["company_name"]
    
    if db_metadata.get("sector"):
        known_fields.append(f"- Sector: {db_metadata['sector']}")
        prefilled["sector"] = db_metadata["sector"]
    
    if db_metadata.get("industry"):
        known_fields.append(f"- Industry: {db_metadata['industry']}")
        prefilled["industry"] = db_metadata["industry"]
    
    if db_metadata.get("exchange"):
        known_fields.append(f"- Exchange: {db_metadata['exchange']}")
        prefilled["exchange"] = db_metadata["exchange"]
    
    if db_metadata.get("homepage_url"):
        known_fields.append(f"- Website: {db_metadata['homepage_url']}")
        prefilled["website"] = db_metadata["homepage_url"]
    
    if db_metadata.get("total_employees"):
        emp = db_metadata['total_employees']
        emp_str = f"{emp:,}" if isinstance(emp, (int, float)) else str(emp)
        known_fields.append(f"- Employees: {emp_str}")
        prefilled["employees"] = db_metadata["total_employees"]
    
    if db_metadata.get("description"):
        desc = db_metadata["description"]
        if len(desc) > 400:
            desc = desc[:400] + "..."
        known_fields.append(f"- Business Description: {desc}")
        prefilled["business_summary"] = db_metadata["description"]
    
    if db_metadata.get("market_cap"):
        known_fields.append(f"- Market Cap: {_format_market_cap(db_metadata['market_cap'])}")
    
    if db_metadata.get("shares_outstanding"):
        known_fields.append(f"- Shares Outstanding: {db_metadata['shares_outstanding']:,.0f}")
    
    if db_metadata.get("is_etf"):
        known_fields.append("- Type: ETF")
    
    # === PRICE SNAPSHOT (Polygon) ===
    price_snap = db_metadata.get("price_snapshot", {})
    if price_snap:
        if price_snap.get("current_price"):
            known_fields.append(f"- Current Price: ${price_snap['current_price']:.2f}")
            prefilled["current_price"] = price_snap["current_price"]
        if price_snap.get("change_percent") is not None:
            sign = "+" if price_snap['change_percent'] >= 0 else ""
            known_fields.append(f"- Today's Change: {sign}{price_snap['change_percent']:.2f}%")
        if price_snap.get("day_volume"):
            vol = price_snap['day_volume']
            if vol >= 1e6:
                known_fields.append(f"- Today's Volume: {vol/1e6:.1f}M")
            else:
                known_fields.append(f"- Today's Volume: {vol:,.0f}")
    
    # === TECHNICAL INDICATORS (DAILY - from screener) ===
    tech = db_metadata.get("technical_daily", {})
    if tech:
        tech_lines = []
        
        # Usar last_close del screener como precio si no tenemos del snapshot
        if tech.get("last_close") and not prefilled.get("current_price"):
            prefilled["current_price"] = tech["last_close"]
        
        # RSI
        if tech.get("rsi_14") is not None:
            rsi = tech["rsi_14"]
            # Usar rsi_status del screener si está disponible, si no calcular
            rsi_status = tech.get("rsi_status") or ("Oversold" if rsi < 30 else "Overbought" if rsi > 70 else "Neutral")
            tech_lines.append(f"RSI-14: {rsi:.1f} ({rsi_status})")
            prefilled["rsi_14"] = rsi
            prefilled["rsi_status"] = rsi_status
        
        # MAs con status calculado
        price = prefilled.get("current_price") or tech.get("last_close")
        if tech.get("ma_50"):
            ma50 = tech["ma_50"]
            ma50_status = "Above" if price and price > ma50 else "Below" if price else "Unknown"
            tech_lines.append(f"MA-50: ${ma50:.2f} ({ma50_status})")
            prefilled["ma_50"] = ma50
            prefilled["ma_50_status"] = ma50_status
        if tech.get("ma_200"):
            ma200 = tech["ma_200"]
            ma200_status = "Above" if price and price > ma200 else "Below" if price else "Unknown"
            tech_lines.append(f"MA-200: ${ma200:.2f} ({ma200_status})")
            prefilled["ma_200"] = ma200
            prefilled["ma_200_status"] = ma200_status
        
        # 52W Range
        if tech.get("high_52w"):
            prefilled["high_52w"] = tech["high_52w"]
            if tech.get("from_52w_high_pct") is not None:
                tech_lines.append(f"52W High: ${tech['high_52w']:.2f} ({tech['from_52w_high_pct']:+.1f}%)")
            else:
                tech_lines.append(f"52W High: ${tech['high_52w']:.2f}")
        if tech.get("low_52w"):
            prefilled["low_52w"] = tech["low_52w"]
            if tech.get("from_52w_low_pct") is not None:
                tech_lines.append(f"52W Low: ${tech['low_52w']:.2f} (+{tech['from_52w_low_pct']:.1f}%)")
            else:
                tech_lines.append(f"52W Low: ${tech['low_52w']:.2f}")
        
        # Extra del screener
        if tech.get("gap_percent") and abs(tech["gap_percent"]) >= 0.5:
            tech_lines.append(f"Gap: {tech['gap_percent']:+.2f}%")
        if tech.get("relative_volume") and tech["relative_volume"] >= 1.5:
            tech_lines.append(f"RVOL: {tech['relative_volume']:.1f}x")
        
        if tech_lines:
            known_fields.append(f"- Technical (DAILY): {' | '.join(tech_lines)}")
    
    # === INSIDER ACTIVITY ===
    insider = db_metadata.get("insider_summary", {})
    if insider:
        insider_lines = []
        if insider.get("recent_transactions"):
            insider_lines.append(f"{insider['recent_transactions']} recent transactions")
        if insider.get("buys_count"):
            insider_lines.append(f"{insider['buys_count']} buys")
        if insider.get("sells_count"):
            insider_lines.append(f"{insider['sells_count']} sells")
        if insider.get("net_insider_sentiment"):
            insider_lines.append(f"Sentiment: {insider['net_insider_sentiment']}")
            prefilled["insider_sentiment"] = insider["net_insider_sentiment"]
        
        if insider_lines:
            known_fields.append(f"- Insider Activity: {', '.join(insider_lines)}")
        
        # CEO/CFO names
        if insider.get("ceo"):
            known_fields.append(f"- CEO: {insider['ceo']}")
            prefilled["ceo"] = insider["ceo"]
        if insider.get("cfo"):
            known_fields.append(f"- CFO: {insider['cfo']}")
            prefilled["cfo"] = insider["cfo"]
    
    # === FUNDAMENTALS FROM SEC XBRL (P/E, P/B, P/S, EV/EBITDA) ===
    fundamentals = db_metadata.get("fundamentals_xbrl", {})
    if fundamentals:
        fund_lines = []
        
        # Valuation ratios
        if fundamentals.get("pe_ratio") is not None:
            fund_lines.append(f"P/E: {fundamentals['pe_ratio']:.1f}")
            prefilled["pe_ratio"] = fundamentals["pe_ratio"]
        if fundamentals.get("pb_ratio") is not None:
            fund_lines.append(f"P/B: {fundamentals['pb_ratio']:.2f}")
            prefilled["pb_ratio"] = fundamentals["pb_ratio"]
        if fundamentals.get("ps_ratio") is not None:
            fund_lines.append(f"P/S: {fundamentals['ps_ratio']:.2f}")
            prefilled["ps_ratio"] = fundamentals["ps_ratio"]
        if fundamentals.get("ev_ebitda") is not None:
            fund_lines.append(f"EV/EBITDA: {fundamentals['ev_ebitda']:.1f}")
            prefilled["ev_ebitda"] = fundamentals["ev_ebitda"]
        if fundamentals.get("debt_equity") is not None:
            fund_lines.append(f"D/E: {fundamentals['debt_equity']:.2f}")
            prefilled["debt_equity"] = fundamentals["debt_equity"]
        if fundamentals.get("profit_margin") is not None:
            fund_lines.append(f"Margin: {fundamentals['profit_margin']:.1f}%")
            prefilled["profit_margin"] = fundamentals["profit_margin"]
        
        if fund_lines:
            known_fields.append(f"- Valuation (SEC XBRL): {' | '.join(fund_lines)}")
        
        # Revenue & EPS
        if fundamentals.get("eps_diluted") is not None:
            prefilled["eps"] = fundamentals["eps_diluted"]
            known_fields.append(f"- EPS (Diluted): ${fundamentals['eps_diluted']:.2f}")
        if fundamentals.get("revenue"):
            rev = fundamentals["revenue"]
            if rev >= 1e9:
                known_fields.append(f"- Annual Revenue: ${rev/1e9:.2f}B")
            elif rev >= 1e6:
                known_fields.append(f"- Annual Revenue: ${rev/1e6:.1f}M")
            prefilled["revenue"] = rev
        if fundamentals.get("net_income"):
            ni = fundamentals["net_income"]
            if ni >= 1e9:
                known_fields.append(f"- Net Income: ${ni/1e9:.2f}B")
            elif ni >= 1e6:
                known_fields.append(f"- Net Income: ${abs(ni)/1e6:.1f}M" + (" (loss)" if ni < 0 else ""))
            prefilled["net_income"] = ni
        
        # Filing info
        if fundamentals.get("filing_type"):
            prefilled["fundamental_source"] = f"{fundamentals['filing_type']} ({fundamentals.get('filing_date', 'recent')})"
    
    if not known_fields:
        return "", {}
    
    # Determinar qué falta para búsqueda
    has_valuation = bool(fundamentals.get("pe_ratio") or fundamentals.get("pb_ratio"))
    search_items = ["Analyst ratings and price targets"]
    if not has_valuation:
        search_items.append("P/E, P/B, P/S ratios (if not provided above)")
    search_items.extend([
        "Short interest",
        "Upcoming catalysts (earnings, FDA dates)",
        "News headlines and sentiment",
        "Risk factors"
    ])
    
    section = f"""
VERIFIED DATA FROM OUR DATABASE (use exactly as provided, do NOT search for these):
{chr(10).join(known_fields)}

IMPORTANT: 
- Technical indicators above are DAILY (end-of-day close prices). DO NOT search for RSI, MA-50, MA-200, or 52W High/Low.
- Valuation ratios (P/E, P/B, P/S, EV/EBITDA) are calculated from official SEC XBRL filings. USE THESE VALUES EXACTLY.
- DO NOT override any provided values with different numbers from Google Search.

Focus your Google Search ONLY on data we DON'T have:
{chr(10).join(f"- {item}" for item in search_items)}
"""
    return section, prefilled


def create_analysis_prompt(ticker: str, language: str = "en", db_metadata: Optional[Dict[str, Any]] = None) -> str:
    """
    Crear prompt para Gemini.
    Si tenemos db_metadata, usamos esos datos y le pedimos a Gemini que se centre en lo dinámico.
    """
    lang_instruction = "Responde en Español." if language == "es" else "Respond in English."
    
    # Construir sección de datos conocidos
    known_data_section, prefilled = _build_known_data_section(db_metadata)
    
    # Valores para el JSON template - básicos
    company_name = prefilled.get('company_name', 'Full Company Name')
    sector = prefilled.get('sector', 'Technology')
    industry = prefilled.get('industry', 'Software - Application')
    exchange = prefilled.get('exchange', 'NASDAQ')
    website = prefilled.get('website', 'https://company.com')
    employees = prefilled.get('employees', 'null')
    
    # Valores técnicos prefijados (DIARIOS - desde screener)
    rsi_status = prefilled.get('rsi_status', 'Neutral')
    ma_50_status = prefilled.get('ma_50_status', 'Unknown')
    ma_200_status = prefilled.get('ma_200_status', 'Unknown')
    
    # CEO/CFO desde insider data
    ceo = prefilled.get('ceo', 'Search for current CEO')
    insider_sentiment = prefilled.get('insider_sentiment', 'Neutral')
    
    return f"""You are a senior financial analyst at a top investment bank. Generate a COMPREHENSIVE real-time analysis for ticker symbol "{ticker}".

{lang_instruction}
{known_data_section}
CRITICAL INSTRUCTIONS:
1. Use Google Search to find the MOST RECENT real-time data available TODAY.
2. Search for: "{ticker} stock analyst ratings", "{ticker} price target", "{ticker} short interest", "{ticker} earnings date"

FOCUS YOUR SEARCH ON DYNAMIC DATA (do NOT search for data already provided above):
A) ANALYST COVERAGE: Latest ratings, price targets, upgrades/downgrades from major firms
B) VALUATION: P/E, Forward P/E, P/B, P/S, EV/EBITDA, PEG ratio  
C) TECHNICAL: ONLY search for support/resistance levels and chart patterns (RSI, MAs, 52W already provided)
D) SHORT INTEREST: % of float short, days to cover, squeeze potential
E) COMPETITORS: Top 3-5 competitors in the same industry
F) FINANCIAL HEALTH: Revenue growth, earnings growth, debt/equity, margins
G) UPCOMING CATALYSTS: Earnings dates, FDA dates (PDUFA, NDA, BLA), conferences, ex-dividend
H) NEWS SENTIMENT: Recent headlines and overall market sentiment - INCLUDE THE ACTUAL HEADLINES
I) RISK FACTORS: Key risks facing the company - ALWAYS include at least 2-3 risks

CRITICAL EVENTS - MUST DETECT (set critical_event field if any of these occurred recently):
- FDA rejection / Complete Response Letter (CRL)
- FDA approval
- Clinical trial failure or success
- SEC investigation / lawsuit
- Bankruptcy filing
- CEO resignation / major management change
- Earnings miss > 20%
- Major contract win/loss
- Merger/acquisition announcement
- Delisting notice

SPECIAL STATUS FLAGS (if applicable):
- SPAC: Pre-merger blank check company
- De-SPAC: Recently completed SPAC merger
- Chinese ADR/VIE: VIE structure risk
- Meme Stock: High retail interest/volatility
- FDA Setback: Recent CRL or rejection
- Bankruptcy Risk: Chapter 11 concerns
- Delisting Warning: Exchange compliance issues
- Pending M&A: Active merger/acquisition

Return ONLY valid JSON (no markdown, no extra text) in this exact structure:
{{
    "ticker": "{ticker}",
    "company_name": "{company_name}",
    "sector": "{sector}",
    "industry": "{industry}",
    "exchange": "{exchange}",
    "ceo": "{ceo}",
    "website": "{website}",
    "employees": {employees},
    "business_summary": "Use the description from database if provided above, otherwise 2-3 sentences",
    "special_status": null,
    
    "consensus_rating": "Buy",
    "analyst_ratings": [
        {{"firm": "Goldman Sachs", "rating": "Buy", "price_target": 200.00, "date": "2025-01-02"}}
    ],
    "average_price_target": 195.00,
    "price_target_high": 250.00,
    "price_target_low": 150.00,
    "num_analysts": 35,
    
    "pe_ratio": 28.5,
    "forward_pe": 24.2,
    "pb_ratio": 8.5,
    "ps_ratio": 7.2,
    "ev_ebitda": 18.5,
    "peg_ratio": 1.2,
    
    "dividend_yield": 0.5,
    "dividend_frequency": "Quarterly",
    "ex_dividend_date": "2025-02-15",
    
    "technical": {{
        "trend": "Search for current trend (Bullish/Bearish/Neutral)",
        "support_level": "Search for support level",
        "resistance_level": "Search for resistance level",
        "rsi_status": "{rsi_status}",
        "ma_50_status": "{ma_50_status}",
        "ma_200_status": "{ma_200_status}",
        "pattern": "Search for chart pattern if any"
    }},
    
    "short_interest": {{
        "short_percent_of_float": 3.5,
        "days_to_cover": 2.1,
        "short_ratio_change": "Decreasing",
        "squeeze_potential": "Low"
    }},
    
    "competitors": [
        {{"ticker": "COMP", "name": "Competitor Inc", "market_cap": "$50B", "competitive_advantage": "Price leader"}}
    ],
    "competitive_moat": "Wide",
    "market_position": "Leader",
    
    "financial_health": {{
        "revenue_growth_yoy": 15.5,
        "earnings_growth_yoy": 22.3,
        "debt_to_equity": 0.45,
        "current_ratio": 2.1,
        "cash_position": "Strong",
        "profit_margin": 25.5,
        "roe": 35.2
    }},
    "financial_grade": "A",
    
    "upcoming_catalysts": [
        {{"event": "Q4 2024 Earnings", "date": "2025-01-28", "importance": "High"}},
        {{"event": "Product Launch", "date": "2025-02-15", "importance": "Medium"}}
    ],
    "earnings_date": "2025-01-28",
    
    "insider_activity": [
        {{"type": "Buy", "insider_name": "John CEO", "title": "CEO", "shares": 10000, "value": "$2.5M", "date": "2024-12-15"}}
    ],
    "insider_sentiment": "{insider_sentiment}",
    
    "news_sentiment": {{
        "overall": "Bullish",
        "score": 65,
        "trending_topics": ["AI expansion", "Strong earnings"],
        "recent_headlines": ["Company beats Q3 estimates - actual headline from news", "New partnership announced - actual headline from news"]
    }},
    
    NOTE ON SCORE: Score must be -100 to +100. NEGATIVE score for Bearish/Negative sentiment, POSITIVE for Bullish/Positive.
    
    "risk_sentiment": "Bullish",
    "risk_factors": [
        {{"category": "Competition", "description": "Increasing competition from new entrants", "severity": "Medium"}},
        {{"category": "Regulation", "description": "Pending antitrust review", "severity": "High"}}
    ],
    "risk_score": 4,
    "critical_event": null
}}

If data is not available, use null. Do NOT make up data. Search Google thoroughly.
"""


MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


def create_minimal_report(ticker: str, error_msg: str) -> Dict[str, Any]:
    """Create a minimal report when API fails completely"""
    return {
        "ticker": ticker,
        "company_name": f"{ticker} (Data unavailable)",
        "sector": None,
        "industry": None,
        "business_summary": f"Unable to generate report: {error_msg}. Please try again.",
        "special_status": "API Error",
        "consensus_rating": None,
        "analyst_ratings": [],
        "average_price_target": None,
        "price_target_high": None,
        "price_target_low": None,
        "pe_ratio": None,
        "forward_pe": None,
        "pb_ratio": None,
        "ev_ebitda": None,
        "dividend_yield": None,
        "dividend_frequency": None,
        "risk_sentiment": None,
        "risk_factors": [],
        "critical_event": error_msg,
        "generated_at": datetime.utcnow().isoformat(),
        "sources": []
    }


async def call_gemini_with_retry(prompt: str, ticker: str) -> Dict[str, Any]:
    """Call Gemini API with automatic retries"""
    google_search_tool = Tool(google_search=GoogleSearch())
    last_error = None
    text = ""
    
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"[{ticker}] Attempt {attempt + 1}/{MAX_RETRIES}")
            
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config={
                    "tools": [google_search_tool],
                }
            )
            
            # Check for empty response
            if not response or not hasattr(response, 'text') or not response.text:
                logger.warning(f"[{ticker}] Empty response on attempt {attempt + 1}")
                last_error = "Empty response from API"
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                continue
            
            text = response.text
            logger.info(f"[{ticker}] Got response, length: {len(text)}")
            
            # Clean markdown if exists
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                parts = text.split("```")
                if len(parts) >= 2:
                    text = parts[1]
            
            # Try to parse JSON
            text = text.strip()
            if not text:
                logger.warning(f"[{ticker}] Empty text after cleanup on attempt {attempt + 1}")
                last_error = "Empty text after cleanup"
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                continue
            
            report_data = json.loads(text)
            
            # Validate required fields
            if not report_data.get("ticker") or not report_data.get("company_name"):
                logger.warning(f"[{ticker}] Missing required fields on attempt {attempt + 1}")
                last_error = "Missing required fields in response"
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                continue
            
            report_data["generated_at"] = datetime.utcnow().isoformat()
            report_data["sources"] = []  # Disabled - not needed
            
            logger.info(f"[{ticker}] Success on attempt {attempt + 1}")
            return report_data
            
        except json.JSONDecodeError as e:
            logger.warning(f"[{ticker}] JSON parse error on attempt {attempt + 1}: {e}")
            last_error = f"JSON parse error: {str(e)[:100]}"
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
                
        except Exception as e:
            logger.warning(f"[{ticker}] Error on attempt {attempt + 1}: {type(e).__name__}: {e}")
            last_error = f"{type(e).__name__}: {str(e)[:100]}"
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
    
    # All retries failed
    logger.error(f"[{ticker}] All {MAX_RETRIES} attempts failed. Last error: {last_error}")
    raise HTTPException(
        status_code=503, 
        detail=f"Service temporarily unavailable after {MAX_RETRIES} attempts. Last error: {last_error}"
    )


async def generate_report(ticker: str, language: str = "en", db_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Generar reporte usando Gemini con Google Search (con caché).
    
    Si se proporciona db_metadata, se usa para optimizar el prompt:
    - Gemini no busca datos que ya tenemos
    - Se centra en datos dinámicos (ratings, technical, news, etc.)
    """
    
    # Check cache first
    cached = await get_cached_report(ticker, language)
    if cached:
        # Si tenemos datos de BD más frescos, actualizar campos básicos del cache
        if db_metadata:
            for key in ["company_name", "sector", "industry", "exchange"]:
                if db_metadata.get(key):
                    cached[key] = db_metadata[key]
            if db_metadata.get("homepage_url"):
                cached["website"] = db_metadata["homepage_url"]
            if db_metadata.get("total_employees"):
                cached["employees"] = db_metadata["total_employees"]
            if db_metadata.get("description") and not cached.get("business_summary"):
                cached["business_summary"] = db_metadata["description"]
        return cached
    
    # Generate new report - pasar db_metadata para optimizar prompt
    has_metadata = bool(db_metadata and any(db_metadata.values()))
    logger.info(f"[{ticker}] Generating report, db_metadata: {has_metadata}")
    
    prompt = create_analysis_prompt(ticker, language, db_metadata)
    report = await call_gemini_with_retry(prompt, ticker)
    
    # Si tenemos db_metadata, asegurar que los campos usen nuestros datos verificados
    if db_metadata:
        # Campos básicos
        if db_metadata.get("company_name"):
            report["company_name"] = db_metadata["company_name"]
        if db_metadata.get("sector"):
            report["sector"] = db_metadata["sector"]
        if db_metadata.get("industry"):
            report["industry"] = db_metadata["industry"]
        if db_metadata.get("exchange"):
            report["exchange"] = db_metadata["exchange"]
        if db_metadata.get("homepage_url"):
            report["website"] = db_metadata["homepage_url"]
        if db_metadata.get("total_employees"):
            report["employees"] = db_metadata["total_employees"]
        if db_metadata.get("description") and (not report.get("business_summary") or len(report.get("business_summary", "")) < 50):
            report["business_summary"] = db_metadata["description"]
        
        # Campos técnicos del screener (MÁS PRECISOS que lo que Gemini puede buscar)
        tech = db_metadata.get("technical_daily", {})
        if tech and "technical" in report:
            price = tech.get("last_close")
            ma_50 = tech.get("ma_50")
            ma_200 = tech.get("ma_200")
            
            # RSI status
            if tech.get("rsi_14") is not None:
                rsi = tech["rsi_14"]
                report["technical"]["rsi_status"] = "Oversold" if rsi < 30 else "Overbought" if rsi > 70 else "Neutral"
            
            # MA status (calculado con precio real)
            if price and ma_50:
                report["technical"]["ma_50_status"] = "Below" if price < ma_50 else "Above"
            if price and ma_200:
                report["technical"]["ma_200_status"] = "Below" if price < ma_200 else "Above"
        
        # Insider sentiment
        insider = db_metadata.get("insider_summary", {})
        if insider.get("net_insider_sentiment"):
            report["insider_sentiment"] = insider["net_insider_sentiment"]
        if insider.get("ceo") and not report.get("ceo"):
            report["ceo"] = insider["ceo"]
        
        # Fundamentales de SEC XBRL (MÁS PRECISOS que Google Search)
        # Los ratios van en NIVEL SUPERIOR del report (donde Gemini los espera)
        fundamentals = db_metadata.get("fundamentals_xbrl", {})
        if fundamentals:
            # Valuation ratios - NIVEL SUPERIOR (sobrescribir datos de Gemini)
            if fundamentals.get("pe_ratio") is not None:
                report["pe_ratio"] = fundamentals["pe_ratio"]
            if fundamentals.get("pb_ratio") is not None:
                report["pb_ratio"] = fundamentals["pb_ratio"]
            if fundamentals.get("ps_ratio") is not None:
                report["ps_ratio"] = fundamentals["ps_ratio"]
            if fundamentals.get("ev_ebitda") is not None:
                report["ev_ebitda"] = fundamentals["ev_ebitda"]
            
            # Financial health - actualizar con datos SEC
            if "financial_health" not in report:
                report["financial_health"] = {}
            if fundamentals.get("debt_equity") is not None:
                report["financial_health"]["debt_to_equity"] = fundamentals["debt_equity"]
            if fundamentals.get("profit_margin") is not None:
                report["financial_health"]["profit_margin"] = fundamentals["profit_margin"]
            
            # Añadir fuente de datos XBRL
            report["valuation_source"] = f"SEC {fundamentals.get('filing_type', 'XBRL')}"
    
    # Cache successful report
    await set_cached_report(ticker, language, report)
    
    return report


# ============== Endpoints ==============

@app.get("/")
async def root():
    return {
        "service": "Financial Analyst",
        "status": "experimental",
        "version": "0.2.0"
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "api_configured": bool(GOOGLE_API_KEY)}


@app.post("/api/report", response_model=FinancialReport)
async def get_report(request: ReportRequest):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="Google API key not configured")
    
    ticker = request.ticker.upper().strip()
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    
    report_data = await generate_report(ticker, request.language)
    return FinancialReport(**report_data)


@app.get("/api/report/{ticker}")
async def get_report_simple(ticker: str, lang: str = "en"):
    """GET endpoint - sin metadata de BD (legacy/fallback)"""
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="Google API key not configured")
    
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    
    report_data = await generate_report(ticker, lang)
    return report_data


@app.post("/api/report/{ticker}")
async def get_report_with_metadata(ticker: str, lang: str = "en", body: Optional[ReportRequestWithMetadata] = None):
    """
    POST endpoint - recibe metadata de BD para optimizar el prompt.
    
    Cuando api_gateway nos envía datos de ticker_metadata:
    - Gemini no tiene que buscar datos básicos (company_name, sector, etc.)
    - Se centra en datos dinámicos (ratings, technical, news, etc.)
    - Resultado: más rápido, más barato, más preciso
    """
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="Google API key not configured")
    
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    
    # Extraer db_metadata del body si existe
    db_metadata = None
    if body and body.db_metadata:
        db_metadata = body.db_metadata.model_dump(exclude_none=True)
        logger.info(f"[{ticker}] Received db_metadata with {len(db_metadata)} fields")
    
    report_data = await generate_report(ticker, lang, db_metadata)
    return report_data


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8099)
