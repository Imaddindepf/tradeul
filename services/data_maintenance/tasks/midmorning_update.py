"""
Mid-Morning Update Generator V2
===============================

Genera el reporte de media mañana (12:30 ET) combinando:
1. Datos del Scanner TradeUL (tickers en movimiento)
2. Gemini + Google Search (noticias formales)
3. Grok + X.com Search (sentiment y breaking news)
4. Clustering de sectores sintéticos (priorizando big caps)
5. Consolidación final inteligente

Este es un reporte REACTIVO que analiza lo que está pasando
en la primera mitad de la sesión de trading.

V2 Changes:
- Market Snapshot mejorado con más índices
- Sectores sintéticos priorizan big caps para narrativa
- Separación clara de noticias vs rumores
- Prompts mejorados para evitar alucinaciones
- Formato compatible con colores del frontend
"""

import os
import json
import asyncio
import aiohttp
import httpx
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
from dataclasses import dataclass

from google import genai
from google.genai.types import Tool, GoogleSearch

from shared.utils.logger import get_logger
from shared.utils.redis_client import RedisClient
from shared.config.settings import settings

logger = get_logger(__name__)

NY_TZ = ZoneInfo("America/New_York")

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ScannerTicker:
    """Ticker del scanner con datos relevantes"""
    symbol: str
    price: float
    change_percent: float
    volume: int
    rvol: Optional[float] = None
    market_cap: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    name: Optional[str] = None


@dataclass
class TickerNews:
    """Noticias enriquecidas de un ticker"""
    symbol: str
    confirmed_news: str  # Noticias confirmadas de Google
    rumors_sentiment: str  # Rumores/sentiment de X.com
    catalyst: Optional[str] = None


@dataclass
class SyntheticSector:
    """Sector sintético identificado por IA"""
    name: str
    tickers: List[str]
    avg_change: float
    narrative: str
    leader: str  # Ticker líder del sector
    big_cap_leader: Optional[str] = None  # Big cap más relevante


# ============================================================================
# MARKET DATA PROVIDER (Layer 0)
# ============================================================================

class MarketDataProvider:
    """Provee datos de mercado en tiempo real desde FMP"""
    
    def __init__(self):
        self.fmp_key = os.getenv('FMP_API_KEY')
        
    async def get_complete_market_snapshot(self) -> Dict:
        """
        Obtiene snapshot completo del mercado incluyendo:
        - Índices principales (S&P, Nasdaq, Dow, Russell)
        - Volatilidad (VIX)
        - Treasuries (2Y, 10Y, 30Y)
        - Sectores ETFs principales
        - Commodities
        - Crypto
        """
        if not self.fmp_key:
            logger.warning("FMP_API_KEY not found")
            return {}
        
        symbols_config = {
            # Índices principales
            'indices': {
                'S&P 500': '^GSPC',
                'Nasdaq': '^IXIC', 
                'Dow Jones': '^DJI',
                'Russell 2000': '^RUT',
                'S&P 400 Mid Cap': '^MID',
            },
            # Volatilidad
            'volatility': {
                'VIX': '^VIX',
            },
            # Sector ETFs
            'sector_etfs': {
                'Technology (XLK)': 'XLK',
                'Financials (XLF)': 'XLF',
                'Healthcare (XLV)': 'XLV',
                'Energy (XLE)': 'XLE',
                'Consumer Disc (XLY)': 'XLY',
                'Industrials (XLI)': 'XLI',
                'Materials (XLB)': 'XLB',
                'Utilities (XLU)': 'XLU',
                'Real Estate (XLRE)': 'XLRE',
                'Comm Services (XLC)': 'XLC',
                'Consumer Staples (XLP)': 'XLP',
            },
            # Commodities
            'commodities': {
                'Gold': 'GC=F',
                'Silver': 'SI=F',
                'Crude Oil WTI': 'CL=F',
                'Natural Gas': 'NG=F',
            },
            # Crypto
            'crypto': {
                'Bitcoin': 'BTCUSD',
                'Ethereum': 'ETHUSD',
            },
        }
        
        results = {
            'indices': {},
            'volatility': {},
            'sector_etfs': {},
            'commodities': {},
            'crypto': {},
            'treasuries': {},
        }
        
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                # Fetch índices y ETFs
                for category, symbols in symbols_config.items():
                    for name, symbol in symbols.items():
                        try:
                            url = f'https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={self.fmp_key}'
                            resp = await client.get(url)
                            data = resp.json()
                            
                            if data and len(data) > 0:
                                d = data[0]
                                results[category][name] = {
                                    'price': d.get('price'),
                                    'change': d.get('change'),
                                    'change_pct': d.get('changesPercentage'),
                                    'prev_close': d.get('previousClose'),
                                }
                        except Exception as e:
                            logger.warning(f"fmp_quote_error", symbol=symbol, error=str(e))
                
                # Fetch Treasury yields
                try:
                    url = f'https://financialmodelingprep.com/api/v4/treasury?from={date.today().isoformat()}&to={date.today().isoformat()}&apikey={self.fmp_key}'
                    resp = await client.get(url)
                    data = resp.json()
                    if data and len(data) > 0:
                        results['treasuries'] = {
                            '2Y Treasury': data[0].get('year2'),
                            '10Y Treasury': data[0].get('year10'),
                            '30Y Treasury': data[0].get('year30'),
                        }
                except Exception as e:
                    logger.warning("treasury_fetch_error", error=str(e))
            
            logger.info("market_snapshot_fetched", 
                       indices=len(results['indices']),
                       etfs=len(results['sector_etfs']))
            return results
            
        except Exception as e:
            logger.error("market_snapshot_error", error=str(e))
            return results


# ============================================================================
# SCANNER DATA EXTRACTION (Layer 1)
# ============================================================================

class ScannerDataExtractor:
    """Extrae datos del Scanner TradeUL desde Redis"""
    
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client
    
    async def get_all_movers(self, limit_per_category: int = 30) -> Dict[str, List[ScannerTicker]]:
        """
        Extrae todos los movers de las categorías principales.
        """
        categories = ['winners', 'losers', 'gappers_up', 'gappers_down', 
                      'momentum_up', 'high_volume', 'anomalies']
        
        result = {}
        
        for category in categories:
            try:
                data = await self.redis.get(f'scanner:category:{category}')
                if data:
                    tickers_raw = json.loads(data) if isinstance(data, str) else data
                    tickers = []
                    for t in tickers_raw[:limit_per_category]:
                        tickers.append(ScannerTicker(
                            symbol=t.get('symbol', ''),
                            price=t.get('price', 0),
                            change_percent=t.get('change_percent', 0),
                            volume=t.get('volume_today', 0),
                            rvol=t.get('rvol', 0),
                            market_cap=t.get('market_cap'),
                            sector=t.get('sector'),
                            industry=t.get('industry'),
                            name=t.get('name')
                        ))
                    result[category] = tickers
                    logger.info(f"scanner_category_loaded", category=category, count=len(tickers))
            except Exception as e:
                logger.error(f"scanner_category_error", category=category, error=str(e))
                result[category] = []
        
        return result
    
    def get_unique_tickers(self, categories_data: Dict[str, List[ScannerTicker]], 
                           max_tickers: int = 60) -> List[ScannerTicker]:
        """
        Obtiene lista única de tickers ordenados por relevancia.
        """
        seen = set()
        unique = []
        
        priority_order = ['winners', 'losers', 'gappers_up', 'gappers_down', 
                          'momentum_up', 'high_volume', 'anomalies']
        
        for category in priority_order:
            for ticker in categories_data.get(category, []):
                if ticker.symbol not in seen and ticker.symbol:
                    seen.add(ticker.symbol)
                    unique.append(ticker)
                    if len(unique) >= max_tickers:
                        return unique
        
        return unique
    
    def get_big_caps_movers(self, categories_data: Dict[str, List[ScannerTicker]], 
                            min_market_cap: float = 10_000_000_000,
                            max_results: int = 15) -> List[ScannerTicker]:
        """
        Extrae los big caps (>$10B market cap) que están moviéndose.
        """
        seen = set()
        big_caps = []
        
        for category, tickers in categories_data.items():
            for ticker in tickers:
                if ticker.symbol in seen:
                    continue
                
                if ticker.market_cap and ticker.market_cap >= min_market_cap:
                    if abs(ticker.change_percent) >= 0.3:
                        seen.add(ticker.symbol)
                        big_caps.append(ticker)
        
        big_caps.sort(key=lambda x: abs(x.change_percent), reverse=True)
        
        logger.info("big_caps_extracted", count=len(big_caps[:max_results]))
        return big_caps[:max_results]
    
    def get_mega_caps(self, categories_data: Dict[str, List[ScannerTicker]],
                      min_market_cap: float = 100_000_000_000) -> List[ScannerTicker]:
        """
        Extrae mega caps (>$100B) para narrativa del día.
        """
        seen = set()
        mega_caps = []
        
        for category, tickers in categories_data.items():
            for ticker in tickers:
                if ticker.symbol in seen:
                    continue
                
                if ticker.market_cap and ticker.market_cap >= min_market_cap:
                    seen.add(ticker.symbol)
                    mega_caps.append(ticker)
        
        mega_caps.sort(key=lambda x: x.market_cap or 0, reverse=True)
        return mega_caps[:20]


# ============================================================================
# GEMINI + GOOGLE SEARCH (Layer 2A)
# ============================================================================

class GeminiNewsEnricher:
    """Enriquece tickers con noticias CONFIRMADAS de Google Search"""
    
    def __init__(self):
        api_key = settings.GOOGL_API_KEY_V2 or os.getenv('GOOGL_API_KEY')
        if not api_key:
            raise ValueError("GOOGL_API_KEY es requerido")
        
        self.client = genai.Client(api_key=api_key)
        self.google_search_tool = Tool(google_search=GoogleSearch())
        self.model = "gemini-2.5-flash"
    
    async def get_news_for_tickers(self, tickers: List[ScannerTicker]) -> Dict[str, str]:
        """
        Obtiene noticias CONFIRMADAS de Google para una lista de tickers.
        Solo información verificable de fuentes oficiales.
        """
        if not tickers:
            return {}
        
        ticker_info = []
        for t in tickers[:35]:
            direction = "UP" if t.change_percent > 0 else "DOWN"
            mcap = f"${t.market_cap/1e9:.1f}B" if t.market_cap and t.market_cap >= 1e9 else ""
            ticker_info.append(f"{t.symbol} ({t.change_percent:+.1f}% {direction}) {mcap}")
        
        today = datetime.now(NY_TZ).strftime("%B %d, %Y")
        
        prompt = f'''You are a financial news researcher for a professional trading desk. 
Search Google News for CONFIRMED news about these stocks TODAY ({today}).

STOCKS MOVING:
{chr(10).join(ticker_info)}

CRITICAL RULES:
1. ONLY report CONFIRMED news from TODAY ({today}) from official sources
2. If NO confirmed news exists for a ticker, write exactly: "No confirmed news today"
3. DO NOT invent or speculate - only factual, verified information
4. Include specific numbers: dollar amounts, percentages, share counts, price targets
5. Include names: CEO names, analyst firms, acquirer/target companies
6. Write in THIRD PERSON, active voice

FOR EACH TICKER provide 2-3 sentences covering ONLY confirmed facts:
- Official announcements (earnings, guidance, M&A)
- Analyst actions (upgrades, downgrades, price target changes)
- FDA decisions, contract wins, partnerships
- Executive changes, share buybacks, dividends

OUTPUT FORMAT (one ticker per line):
SYMBOL: [Detailed factual news from official sources]

Example:
NVDA: Goldman Sachs upgraded to Buy with price target raised from $700 to $850, citing 40% AI chip demand growth. Q4 earnings beat estimates with EPS $5.16 vs $4.60 expected.
LMT: Won $2.3B Pentagon contract for F-35 maintenance, the largest single award this quarter.

Search and report ONLY confirmed news:'''

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={'tools': [self.google_search_tool]}
            )
            
            result = {}
            if response.text:
                lines = response.text.strip().split('\n')
                for line in lines:
                    if ':' in line:
                        parts = line.split(':', 1)
                        symbol = parts[0].strip().upper()
                        news = parts[1].strip() if len(parts) > 1 else ""
                        symbol = ''.join(c for c in symbol if c.isalpha() or c == '.')
                        if symbol and news and len(symbol) <= 6:
                            result[symbol] = news
            
            logger.info("gemini_news_fetched", ticker_count=len(result))
            return result
            
        except Exception as e:
            logger.error("gemini_news_error", error=str(e))
            return {}


# ============================================================================
# GROK + X.COM SEARCH (Layer 2B) - RUMORS & SENTIMENT ONLY
# ============================================================================

class GrokSentimentEnricher:
    """Enriquece tickers con RUMORS y SENTIMENT de X.com via Grok"""
    
    def __init__(self):
        self.api_key = os.getenv('GROK_API_KEY_2') or settings.GROK_API_KEY
        if not self.api_key:
            raise ValueError("GROK_API_KEY es requerido")
        
        self.base_url = "https://api.x.ai/v1/chat/completions"
    
    async def get_xcom_sentiment(self, tickers: List[ScannerTicker]) -> Dict[str, str]:
        """
        Obtiene SENTIMENT y RUMORS de X.com. 
        Claramente marcados como tal, no como hechos.
        """
        if not tickers:
            return {}
        
        ticker_info = []
        for t in tickers[:25]:
            direction = "UP" if t.change_percent > 0 else "DOWN"
            ticker_info.append(f"${t.symbol} ({t.change_percent:+.1f}% {direction})")
        
        today = datetime.now(NY_TZ).strftime("%B %d, %Y")
        
        prompt = f'''Search X.com for trader SENTIMENT and MARKET CHATTER about these stocks TODAY ({today}).

STOCKS:
{chr(10).join(ticker_info)}

CRITICAL RULES - READ CAREFULLY:
1. ONLY report what you ACTUALLY FIND on X.com from TODAY
2. If you find NOTHING for a ticker, write: "No X activity found"
3. DO NOT INVENT information - if there's no chatter, say so
4. Clearly distinguish between:
   - CONFIRMED posts you found (summarize sentiment)
   - RUMORS being discussed (label as "Rumor:")
5. Report the GENERAL SENTIMENT: bullish/bearish/mixed
6. Include options flow ONLY if you find actual posts mentioning it

FOR EACH TICKER, report ONLY what you find:
- Trader sentiment (bullish/bearish/mixed)
- Key price levels being discussed
- Options activity IF mentioned in posts
- Rumors IF being discussed (clearly labeled)

OUTPUT FORMAT:
$SYMBOL: [Sentiment: bullish/bearish/mixed]. [What traders are actually saying]. [Rumor: X if any]. [Key levels: $X support, $X resistance if discussed].

Example of GOOD response:
$NVDA: Sentiment: bullish. Traders celebrating AI demand growth. Call buying heavy at $900 strike mentioned. Key levels: $850 support.
$AAPL: No X activity found.
$XYZ: Sentiment: mixed. Rumor: Possible acquisition being discussed but unconfirmed. Key levels: $45 resistance.

DO NOT make up data. Report what exists:'''

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "grok-3-fast",
                        "messages": [{"role": "user", "content": prompt}],
                        "search_enabled": True,
                        "temperature": 0.2  # Lower temperature for less hallucination
                    },
                    timeout=aiohttp.ClientTimeout(total=90)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                        
                        result = {}
                        if content:
                            lines = content.strip().split('\n')
                            for line in lines:
                                if ':' in line and '$' in line:
                                    start = line.find('$') + 1
                                    end = line.find(':')
                                    if start > 0 and end > start:
                                        symbol = line[start:end].strip().upper()
                                        sentiment = line[end+1:].strip()
                                        if symbol and sentiment:
                                            # Filter out "No activity" responses
                                            if "no x activity" not in sentiment.lower() and "no activity" not in sentiment.lower():
                                                result[symbol] = sentiment
                        
                        logger.info("grok_sentiment_fetched", ticker_count=len(result))
                        return result
                    else:
                        error_text = await response.text()
                        logger.error("grok_api_error", status=response.status, error=error_text[:200])
                        return {}
                        
        except Exception as e:
            logger.error("grok_sentiment_error", error=str(e))
            return {}


# ============================================================================
# SYNTHETIC SECTOR CLUSTERING (Layer 2C)
# ============================================================================

class SectorClusterAnalyzer:
    """Agrupa tickers en sectores sintéticos, priorizando big caps para narrativa"""
    
    def __init__(self):
        api_key = settings.GOOGL_API_KEY_V2 or os.getenv('GOOGL_API_KEY')
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-2.5-flash"
    
    async def cluster_into_sectors(self, tickers: List[ScannerTicker], 
                                    news_data: Dict[str, str],
                                    mega_caps: List[ScannerTicker] = None) -> List[SyntheticSector]:
        """
        Agrupa tickers en sectores sintéticos basados en narrativas del mercado.
        Prioriza big caps para la narrativa del día.
        """
        if not tickers:
            return []
        
        # Preparar datos para el análisis
        ticker_data = []
        for t in tickers:
            news = news_data.get(t.symbol, "No news")[:150]
            mcap_str = ""
            if t.market_cap:
                if t.market_cap >= 1e12:
                    mcap_str = f"[MEGA CAP ${t.market_cap/1e12:.1f}T]"
                elif t.market_cap >= 100e9:
                    mcap_str = f"[MEGA CAP ${t.market_cap/1e9:.0f}B]"
                elif t.market_cap >= 10e9:
                    mcap_str = f"[LARGE CAP ${t.market_cap/1e9:.0f}B]"
                elif t.market_cap >= 2e9:
                    mcap_str = f"[MID CAP ${t.market_cap/1e9:.1f}B]"
                else:
                    mcap_str = f"[SMALL CAP ${t.market_cap/1e6:.0f}M]"
            
            ticker_data.append(
                f"{t.symbol}: {t.change_percent:+.1f}% {mcap_str} | "
                f"Sector: {t.sector or 'Unknown'} | "
                f"News: {news}"
            )
        
        # Incluir mega caps explícitamente si los tenemos
        mega_cap_list = ""
        if mega_caps:
            mega_cap_list = f"\n\nMEGA CAPS MOVING TODAY (use these for narrative):\n"
            mega_cap_list += "\n".join([f"{t.symbol} ({t.change_percent:+.1f}%) - ${t.market_cap/1e9:.0f}B" 
                                        for t in mega_caps[:10]])
        
        prompt = f'''You are a market analyst creating SYNTHETIC SECTORS based on today's market narratives.

IMPORTANT: Prioritize BIG CAP and MEGA CAP stocks for sector leadership and narrative.

STOCKS MOVING TODAY:
{chr(10).join(ticker_data[:50])}
{mega_cap_list}

TASK:
1. Create 6-8 SYNTHETIC SECTORS based on TODAY's market THEMES and NARRATIVES
2. Each sector should have a BIG CAP leader when possible (for credibility)
3. Sectors should capture the DAY'S STORY - what's driving the market
4. Examples of good sector names:
   - "AI INFRASTRUCTURE RALLY" (not just "Technology")
   - "BIOTECH M&A WAVE" (not just "Healthcare")
   - "DEFENSE SPENDING BENEFICIARIES"
   - "CRYPTO-ADJACENT MOMENTUM"
   - "EARNINGS BEAT MOMENTUM"
   - "FDA APPROVAL PLAYS"
   - "RATE CUT BENEFICIARIES"

OUTPUT FORMAT (JSON):
{{
  "sectors": [
    {{
      "name": "AI INFRASTRUCTURE RALLY",
      "tickers": ["NVDA", "SMCI", "AMD", "MRVL"],
      "avg_change": 5.2,
      "leader": "NVDA",
      "big_cap_leader": "NVDA",
      "narrative": "Mega-cap tech leading AI infrastructure rally on strong demand signals and positive analyst sentiment"
    }}
  ]
}}

RULES:
- Sector names should be NARRATIVE-DRIVEN (tell the story of the day)
- Always try to include a big cap as leader for credibility
- Each ticker only in ONE sector
- Sort by avg_change (best first, worst last)
- Include 2 negative/laggard sectors at the end

Respond with ONLY the JSON:'''

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt
            )
            
            if response.text:
                text = response.text.strip()
                if text.startswith('```json'):
                    text = text[7:]
                if text.startswith('```'):
                    text = text[3:]
                if text.endswith('```'):
                    text = text[:-3]
                
                data = json.loads(text)
                sectors = []
                
                for s in data.get('sectors', []):
                    sectors.append(SyntheticSector(
                        name=s.get('name', 'Unknown'),
                        tickers=s.get('tickers', []),
                        avg_change=float(s.get('avg_change', 0)),
                        narrative=s.get('narrative', ''),
                        leader=s.get('leader', ''),
                        big_cap_leader=s.get('big_cap_leader')
                    ))
                
                sectors.sort(key=lambda x: x.avg_change, reverse=True)
                
                logger.info("sectors_clustered", sector_count=len(sectors))
                return sectors
            
            return []
            
        except Exception as e:
            logger.error("sector_clustering_error", error=str(e))
            return []


# ============================================================================
# MORNING NEWS COMPLETER (Layer 2D)
# ============================================================================

class MorningNewsCompleter:
    """
    Lee el Morning News Call y completa los eventos económicos y earnings
    con los resultados reales que ya salieron.
    """
    
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client
        api_key = settings.GOOGL_API_KEY_V2 or os.getenv('GOOGL_API_KEY')
        self.client = genai.Client(api_key=api_key)
        self.google_search_tool = Tool(google_search=GoogleSearch())
    
    async def get_morning_news(self, report_date: date) -> Optional[str]:
        """Obtener el Morning News Call del día desde Redis"""
        try:
            key = f"morning_news:{report_date.isoformat()}:en"
            data = await self.redis.get(key)
            if data:
                parsed = json.loads(data) if isinstance(data, str) else data
                return parsed.get("report", "")
            return None
        except Exception as e:
            logger.error("get_morning_news_error", error=str(e))
            return None
    
    def extract_economic_events(self, morning_report: str) -> List[str]:
        """Extraer eventos económicos del Morning News"""
        import re
        events = []
        
        match = re.search(r'ECONOMIC EVENTS.*?\n\n(.*?)(?=\n\n[A-Z]|\n={10,}|$)', 
                         morning_report, re.DOTALL | re.IGNORECASE)
        if match:
            section = match.group(1)
            for line in section.split('\n'):
                line = line.strip()
                if re.match(r'^\d{1,2}:\d{2}', line):
                    events.append(line)
        
        return events[:15]
    
    def extract_earnings_bmo(self, morning_report: str) -> List[str]:
        """Extraer empresas que reportan BMO (Before Market Open)"""
        import re
        earnings = []
        
        match = re.search(r'COMPANIES REPORTING RESULTS.*?\n\n(.*?)(?=\n\n[A-Z]|\n={10,}|$)', 
                         morning_report, re.DOTALL | re.IGNORECASE)
        if match:
            section = match.group(1)
            for line in section.split('\n'):
                line = line.strip()
                if 'BMO' in line.upper() and '(' in line:
                    earnings.append(line)
        
        return earnings[:12]
    
    async def get_economic_results(self, events: List[str], report_date: date) -> str:
        """Buscar resultados reales de eventos económicos via Google Search"""
        if not events:
            return ""
        
        today = report_date.strftime("%B %d, %Y")
        events_text = "\n".join(events[:10])
        
        prompt = f'''Search for the ACTUAL RESULTS of these economic data releases from TODAY ({today}).

SCHEDULED EVENTS:
{events_text}

CRITICAL RULES:
1. Output ONLY the data in the exact format below - NO introduction
2. One event per line
3. Skip events not yet released
4. Include market reaction if significant

OUTPUT FORMAT:
Event Name: Actual X.XX% vs Expected X.XX% (Beat/Miss/Met) - Brief market reaction

Example:
U.S. CPI (Dec): Actual 2.9% YoY vs Expected 2.9% (Met) - Core CPI cooled to 3.2%, markets rallied
Initial Jobless Claims: Actual 201K vs Expected 215K (Beat) - Labor market remains tight
PPI (Dec): Actual 3.3% YoY vs Expected 3.5% (Beat) - Easing inflation pressures

START OUTPUT NOW:'''

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={'tools': [self.google_search_tool]}
            )
            result = response.text.strip() if response.text else ""
            result = self._clean_ai_intro(result)
            logger.info("economic_results_fetched", chars=len(result))
            return result
        except Exception as e:
            logger.error("economic_results_error", error=str(e))
            return ""
    
    async def get_earnings_results(self, earnings: List[str], report_date: date) -> str:
        """Buscar resultados reales de earnings BMO via Google Search"""
        if not earnings:
            return ""
        
        today = report_date.strftime("%B %d, %Y")
        earnings_text = "\n".join(earnings[:10])
        
        prompt = f'''Search for ACTUAL EARNINGS RESULTS of these BMO companies today ({today}).

COMPANIES:
{earnings_text}

CRITICAL RULES:
1. Output ONLY the data in the exact format below - NO introduction
2. One company per line
3. Skip companies that haven't reported yet
4. Include stock reaction

OUTPUT FORMAT:
Company Name (TICKER): EPS $X.XX vs Est $X.XX (Beat/Miss) | Rev $X.XXB vs Est $X.XXB (Beat/Miss) | Stock +/-X.X%

Example:
JPMorgan Chase (JPM): EPS $4.81 vs Est $4.03 (Beat) | Rev $42.8B vs Est $41.7B (Beat) | Stock +2.4%
Delta Air Lines (DAL): EPS $1.28 vs Est $1.40 (Miss) | Rev $13.7B vs Est $13.5B (Beat) | Stock -5.2%
Bank of NY Mellon (BK): EPS $1.54 vs Est $1.52 (Beat) | Rev $4.55B vs Est $4.50B (Beat) | Stock +0.8%

START OUTPUT NOW:'''

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={'tools': [self.google_search_tool]}
            )
            result = response.text.strip() if response.text else ""
            result = self._clean_ai_intro(result)
            logger.info("earnings_results_fetched", chars=len(result))
            return result
        except Exception as e:
            logger.error("earnings_results_error", error=str(e))
            return ""
    
    def _clean_ai_intro(self, text: str) -> str:
        """Eliminar introducciones típicas de IA"""
        import re
        
        intro_patterns = [
            r'^(Here are|Aquí están|Based on|Basado en|The following|Los siguientes|Below are|A continuación)[^:]*:?\s*',
            r'^(Note:|Nota:)[^\n]*\n*',
            r'^\s*\*+\s*',
        ]
        
        result = text
        for pattern in intro_patterns:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE | re.MULTILINE)
        
        result = re.sub(r'\n{3,}', '\n\n', result)
        result = re.sub(r'\n +', '\n', result)
        
        return result.strip()
    
    async def complete_morning_data(self, report_date: date) -> Dict[str, str]:
        """
        Proceso completo: leer morning news, extraer eventos/earnings, buscar resultados.
        """
        logger.info("completing_morning_data", date=str(report_date))
        
        morning_report = await self.get_morning_news(report_date)
        if not morning_report:
            logger.warning("no_morning_news_found", date=str(report_date))
            return {"economic_results": "", "earnings_results": ""}
        
        events = self.extract_economic_events(morning_report)
        earnings = self.extract_earnings_bmo(morning_report)
        
        logger.info("extracted_from_morning_news", 
                   events_count=len(events), 
                   earnings_count=len(earnings))
        
        economic_task = self.get_economic_results(events, report_date)
        earnings_task = self.get_earnings_results(earnings, report_date)
        
        economic_results, earnings_results = await asyncio.gather(
            economic_task, earnings_task, return_exceptions=True
        )
        
        if isinstance(economic_results, Exception):
            logger.error("economic_results_failed", error=str(economic_results))
            economic_results = ""
        if isinstance(earnings_results, Exception):
            logger.error("earnings_results_failed", error=str(earnings_results))
            earnings_results = ""
        
        return {
            "economic_results": economic_results,
            "earnings_results": earnings_results
        }


# ============================================================================
# FINAL CONSOLIDATION (Layer 3)
# ============================================================================

class ReportConsolidator:
    """Genera el reporte final consolidado con formato para colores"""
    
    def __init__(self):
        api_key = settings.GOOGL_API_KEY_V2 or os.getenv('GOOGL_API_KEY')
        self.client = genai.Client(api_key=api_key)
        self.google_search_tool = Tool(google_search=GoogleSearch())
        self.model = "gemini-2.5-flash"
    
    def _format_date(self, d: date) -> str:
        """Formatear fecha para el reporte"""
        days_en = {0: 'MONDAY', 1: 'TUESDAY', 2: 'WEDNESDAY', 3: 'THURSDAY', 
                   4: 'FRIDAY', 5: 'SATURDAY', 6: 'SUNDAY'}
        months_en = {1: 'JANUARY', 2: 'FEBRUARY', 3: 'MARCH', 4: 'APRIL', 
                     5: 'MAY', 6: 'JUNE', 7: 'JULY', 8: 'AUGUST', 
                     9: 'SEPTEMBER', 10: 'OCTOBER', 11: 'NOVEMBER', 12: 'DECEMBER'}
        return f"{days_en[d.weekday()]}, {months_en[d.month]} {d.day}, {d.year}"
    
    def _format_change(self, change: float) -> str:
        """Formatea cambio con signo"""
        if change > 0:
            return f'+{change:.2f}%'
        else:
            return f'{change:.2f}%'
    
    def _format_market_cap(self, market_cap: float) -> str:
        """Formatea market cap en formato legible"""
        if market_cap >= 1_000_000_000_000:
            return f"${market_cap / 1_000_000_000_000:.2f}T"
        elif market_cap >= 1_000_000_000:
            return f"${market_cap / 1_000_000_000:.1f}B"
        elif market_cap >= 1_000_000:
            return f"${market_cap / 1_000_000:.0f}M"
        else:
            return f"${market_cap:,.0f}"
    
    def _clean_markdown(self, text: str) -> str:
        """Limpia markdown del texto"""
        import re
        text = text.replace('**', '')
        text = re.sub(r'\*([^*\s][^*]*[^*\s])\*', r'\1', text)
        text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
        text = text.replace('\\$', '$').replace('\\&', '&')
        text = re.sub(r'[^\S\n]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
    
    def _format_market_snapshot(self, market_data: Dict) -> str:
        """Formatear market snapshot completo"""
        lines = []
        
        def fmt_pct(val):
            if val is None:
                return "N/A"
            sign = "+" if val >= 0 else ""
            return f"{sign}{val:.2f}%"
        
        # Índices principales
        indices = market_data.get('indices', {})
        if indices:
            for name, data in indices.items():
                if data.get('price'):
                    lines.append(f"{name}: {data['price']:,.2f} ({fmt_pct(data.get('change_pct'))})")
        
        # VIX
        vix = market_data.get('volatility', {}).get('VIX', {})
        if vix.get('price'):
            lines.append(f"VIX: {vix['price']:.2f}")
        
        # Treasuries
        treasuries = market_data.get('treasuries', {})
        if treasuries:
            treasury_parts = []
            for name, val in treasuries.items():
                if val:
                    treasury_parts.append(f"{name}: {val:.2f}%")
            if treasury_parts:
                lines.append(" | ".join(treasury_parts))
        
        return '\n'.join(lines)
    
    def _format_sector_etfs(self, market_data: Dict) -> str:
        """Formatear sector ETFs"""
        lines = []
        
        etfs = market_data.get('sector_etfs', {})
        if etfs:
            # Ordenar por cambio
            sorted_etfs = sorted(etfs.items(), key=lambda x: x[1].get('change_pct', 0) or 0, reverse=True)
            
            for name, data in sorted_etfs:
                if data.get('change_pct') is not None:
                    change = data['change_pct']
                    sign = "+" if change >= 0 else ""
                    lines.append(f"{name}: {sign}{change:.2f}%")
        
        return '\n'.join(lines)
    
    async def generate_report(
        self,
        report_date: date,
        tickers: List[ScannerTicker],
        google_news: Dict[str, str],
        xcom_sentiment: Dict[str, str],
        sectors: List[SyntheticSector],
        morning_data: Dict[str, str],
        market_data: Dict,
        big_caps: List[ScannerTicker] = None,
        mega_caps: List[ScannerTicker] = None,
        lang: str = "en"
    ) -> str:
        """
        Genera el reporte Mid-Morning consolidado.
        Formato optimizado para colores del frontend.
        """
        date_formatted = self._format_date(report_date)
        time_et = datetime.now(NY_TZ).strftime("%H:%M ET")
        
        # Separar gainers y losers
        gainers = sorted([t for t in tickers if t.change_percent > 0], 
                        key=lambda x: x.change_percent, reverse=True)[:12]
        losers = sorted([t for t in tickers if t.change_percent < 0], 
                       key=lambda x: x.change_percent)[:10]
        
        # Construir reporte
        report_lines = []
        
        # ========== HEADER ==========
        report_lines.append("=" * 80)
        report_lines.append("")
        report_lines.append("                              TRADEUL.COM")
        report_lines.append("                          MID-MORNING UPDATE")
        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")
        report_lines.append("USA EDITION")
        report_lines.append(f"{date_formatted} - {time_et}")
        report_lines.append("")
        report_lines.append("")
        
        # ========== MARKET SNAPSHOT ==========
        report_lines.append("MARKET SNAPSHOT")
        report_lines.append("")
        market_snapshot = self._format_market_snapshot(market_data)
        report_lines.append(market_snapshot)
        report_lines.append("")
        report_lines.append("")
        
        # ========== ECONOMIC DATA RESULTS ==========
        economic_results = morning_data.get("economic_results", "")
        if economic_results and len(economic_results) > 20:
            report_lines.append("ECONOMIC DATA RESULTS")
            report_lines.append("")
            report_lines.append(self._clean_markdown(economic_results))
            report_lines.append("")
            report_lines.append("")
        
        # ========== EARNINGS RESULTS (BMO) ==========
        earnings_results = morning_data.get("earnings_results", "")
        if earnings_results and len(earnings_results) > 20:
            report_lines.append("EARNINGS RESULTS (BMO)")
            report_lines.append("")
            report_lines.append(self._clean_markdown(earnings_results))
            report_lines.append("")
            report_lines.append("")
        
        # ========== BIG CAPS MOVERS ==========
        if big_caps:
            report_lines.append("BIG CAPS MOVERS")
            report_lines.append("")
            
            for t in big_caps[:10]:
                change_str = self._format_change(t.change_percent)
                mcap_str = self._format_market_cap(t.market_cap) if t.market_cap else ""
                news = self._clean_markdown(google_news.get(t.symbol, ""))
                
                report_lines.append(f"{t.symbol} {change_str} | {mcap_str}")
                if news and "no confirmed news" not in news.lower() and "no news" not in news.lower():
                    report_lines.append(f"   {news}")
                report_lines.append("")
            
            report_lines.append("")
        
        # ========== TOP SYNTHETIC SECTORS ==========
        report_lines.append("TOP SYNTHETIC SECTORS")
        report_lines.append("")
        
        # Top 2 positivos con detalle
        top_positive = [s for s in sectors if s.avg_change > 0][:2]
        for i, sector in enumerate(top_positive, 1):
            change_str = self._format_change(sector.avg_change)
            report_lines.append(f"{i}. {sector.name} ({change_str})")
            report_lines.append(f"   Symbols: {', '.join(sector.tickers[:6])}")
            report_lines.append(f"   Leader: {sector.leader}")
            report_lines.append(f"   Narrative: {sector.narrative}")
            report_lines.append("")
        
        # Otros sectores en una línea
        other_sectors = sectors[2:6] if len(sectors) > 2 else []
        if other_sectors:
            other_str = ", ".join([f"{s.name} {self._format_change(s.avg_change)}" for s in other_sectors])
            report_lines.append(f"Other sectors: {other_str}")
            report_lines.append("")
        
        report_lines.append("")
        
        # ========== TOP GAINERS ==========
        report_lines.append("TOP GAINERS")
        report_lines.append("")
        
        for t in gainers[:8]:
            change_str = self._format_change(t.change_percent)
            news = self._clean_markdown(google_news.get(t.symbol, ""))
            xcom = xcom_sentiment.get(t.symbol, "")
            
            report_lines.append(f"{t.symbol} {change_str}")
            
            # Noticias confirmadas primero
            if news and "no confirmed news" not in news.lower() and "no news" not in news.lower():
                report_lines.append(f"   {news}")
            
            # Sentiment/Rumors separado y etiquetado
            if xcom and len(xcom) > 10:
                # Limpiar y acortar
                xcom_clean = self._clean_markdown(xcom)
                if len(xcom_clean) > 200:
                    xcom_clean = xcom_clean[:200] + "..."
                report_lines.append(f"   [Sentiment] {xcom_clean}")
            
            report_lines.append("")
        
        report_lines.append("")
        
        # ========== TOP LOSERS ==========
        report_lines.append("TOP LOSERS")
        report_lines.append("")
        
        for t in losers[:8]:
            change_str = self._format_change(t.change_percent)
            news = self._clean_markdown(google_news.get(t.symbol, ""))
            xcom = xcom_sentiment.get(t.symbol, "")
            
            report_lines.append(f"{t.symbol} {change_str}")
            
            if news and "no confirmed news" not in news.lower() and "no news" not in news.lower():
                report_lines.append(f"   {news}")
            
            if xcom and len(xcom) > 10:
                xcom_clean = self._clean_markdown(xcom)
                if len(xcom_clean) > 200:
                    xcom_clean = xcom_clean[:200] + "..."
                report_lines.append(f"   [Sentiment] {xcom_clean}")
            
            report_lines.append("")
        
        report_lines.append("")
        
        # ========== UNUSUAL VOLUME ==========
        high_vol = sorted([t for t in tickers if t.rvol and t.rvol > 3.0], 
                         key=lambda x: x.rvol or 0, reverse=True)[:6]
        if high_vol:
            report_lines.append("UNUSUAL VOLUME")
            report_lines.append("")
            for t in high_vol:
                vol_str = f"{t.volume/1e6:.1f}M" if t.volume > 1e6 else f"{t.volume/1e3:.0f}K"
                rvol_str = f"{t.rvol:.1f}x avg" if t.rvol else ""
                change_str = self._format_change(t.change_percent)
                report_lines.append(f"{t.symbol} {change_str} | Volume: {vol_str} ({rvol_str})")
            report_lines.append("")
            report_lines.append("")
        
        # ========== SECTOR ETF PERFORMANCE ==========
        etf_section = self._format_sector_etfs(market_data)
        if etf_section:
            report_lines.append("SECTOR ETF PERFORMANCE")
            report_lines.append("")
            report_lines.append(etf_section)
            report_lines.append("")
            report_lines.append("")
        
        # ========== MARKET NARRATIVE ==========
        narrative_prompt = f'''Based on this market data, write a 4-5 sentence professional market narrative.

Market Context:
- Top Gainers: {', '.join([f"{t.symbol} {t.change_percent:+.1f}%" for t in gainers[:5]])}
- Top Losers: {', '.join([f"{t.symbol} {t.change_percent:+.1f}%" for t in losers[:5]])}
- Top Sectors: {', '.join([f"{s.name} {s.avg_change:+.1f}%" for s in sectors[:3]])}
- Big Caps Moving: {', '.join([f"{t.symbol} {t.change_percent:+.1f}%" for t in (big_caps or [])[:5]])}

Write a concise, professional analysis that:
1. Identifies the MAIN THEME driving the market today
2. Explains what's causing the biggest moves
3. Notes any risk-on or risk-off sentiment
4. Highlights what traders should watch

Write in plain text, no markdown. Be specific with the narrative.'''

        try:
            narrative_response = self.client.models.generate_content(
                model=self.model,
                contents=narrative_prompt
            )
            narrative = narrative_response.text.strip() if narrative_response.text else ""
            
            if narrative:
                report_lines.append("MARKET NARRATIVE")
                report_lines.append("")
                report_lines.append(self._clean_markdown(narrative))
                report_lines.append("")
                report_lines.append("")
        except Exception as e:
            logger.error("narrative_generation_error", error=str(e))
        
        # Footer
        report_lines.append("=" * 80)
        
        return '\n'.join(report_lines)


# ============================================================================
# MAIN GENERATOR
# ============================================================================

class MidMorningUpdateGenerator:
    """
    Generador principal del Mid-Morning Update V2.
    """
    
    def __init__(self):
        self.redis = None
        self.scanner_extractor = None
        self.morning_completer = None
        self.market_provider = MarketDataProvider()
        self.gemini_enricher = GeminiNewsEnricher()
        self.grok_enricher = GrokSentimentEnricher()
        self.sector_analyzer = SectorClusterAnalyzer()
        self.consolidator = ReportConsolidator()
    
    async def _ensure_redis(self):
        """Asegurar conexión a Redis"""
        if self.redis is None:
            self.redis = RedisClient()
            await self.redis.connect()
            self.scanner_extractor = ScannerDataExtractor(self.redis)
            self.morning_completer = MorningNewsCompleter(self.redis)
    
    async def generate(self, report_date: Optional[date] = None, lang: str = "en") -> Dict:
        """
        Genera el Mid-Morning Update completo.
        """
        if report_date is None:
            report_date = datetime.now(NY_TZ).date()
        
        logger.info("generating_midmorning_update_v2", date=str(report_date), lang=lang)
        start_time = datetime.now()
        
        try:
            await self._ensure_redis()
            
            # ============================================
            # LAYER 1: Scanner Data Extraction (do this first to fail fast)
            # ============================================
            logger.info("layer1_scanner_extraction_start")
            categories_data = await self.scanner_extractor.get_all_movers()
            unique_tickers = self.scanner_extractor.get_unique_tickers(categories_data, max_tickers=60)
            big_caps = self.scanner_extractor.get_big_caps_movers(categories_data)
            mega_caps = self.scanner_extractor.get_mega_caps(categories_data)
            logger.info("layer1_complete", 
                       ticker_count=len(unique_tickers), 
                       big_caps_count=len(big_caps),
                       mega_caps_count=len(mega_caps))
            
            if not unique_tickers:
                return {
                    "success": False,
                    "date": report_date.isoformat(),
                    "error": "No scanner data available",
                    "generated_at": datetime.now(NY_TZ).isoformat()
                }
            
            # ============================================
            # LAYER 0: Market Data (after scanner to fail fast if no data)
            # ============================================
            logger.info("layer0_market_data_start")
            market_data = await self.market_provider.get_complete_market_snapshot()
            logger.info("layer0_complete", indices=len(market_data.get('indices', {})))
            
            # ============================================
            # LAYER 2A: Complete Morning News Data
            # ============================================
            logger.info("layer2a_morning_completion_start")
            morning_data = await self.morning_completer.complete_morning_data(report_date)
            logger.info("layer2a_complete", 
                       economic_chars=len(morning_data.get("economic_results", "")),
                       earnings_chars=len(morning_data.get("earnings_results", "")))
            
            # ============================================
            # LAYER 2B: Parallel News & Sentiment Enrichment
            # ============================================
            logger.info("layer2b_enrichment_start")
            
            gemini_task = self.gemini_enricher.get_news_for_tickers(unique_tickers)
            grok_task = self.grok_enricher.get_xcom_sentiment(unique_tickers)
            
            google_news, xcom_sentiment = await asyncio.gather(
                gemini_task, grok_task, return_exceptions=True
            )
            
            if isinstance(google_news, Exception):
                logger.error("gemini_enrichment_failed", error=str(google_news))
                google_news = {}
            if isinstance(xcom_sentiment, Exception):
                logger.error("grok_enrichment_failed", error=str(xcom_sentiment))
                xcom_sentiment = {}
            
            logger.info("layer2b_complete", 
                       google_news_count=len(google_news),
                       xcom_sentiment_count=len(xcom_sentiment))
            
            # ============================================
            # LAYER 2C: Sector Clustering
            # ============================================
            logger.info("layer2c_sector_clustering_start")
            sectors = await self.sector_analyzer.cluster_into_sectors(
                unique_tickers, google_news, mega_caps
            )
            logger.info("layer2c_complete", sector_count=len(sectors))
            
            # ============================================
            # LAYER 3: Final Consolidation
            # ============================================
            logger.info("layer3_consolidation_start")
            report_text = await self.consolidator.generate_report(
                report_date=report_date,
                tickers=unique_tickers,
                google_news=google_news,
                xcom_sentiment=xcom_sentiment,
                sectors=sectors,
                morning_data=morning_data,
                market_data=market_data,
                big_caps=big_caps,
                mega_caps=mega_caps,
                lang=lang
            )
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            logger.info("midmorning_update_generated",
                       date=str(report_date),
                       length=len(report_text),
                       duration_seconds=round(elapsed, 2))
            
            return {
                "success": True,
                "date": report_date.isoformat(),
                "date_formatted": self.consolidator._format_date(report_date),
                "report": report_text,
                "generated_at": datetime.now(NY_TZ).isoformat(),
                "generation_time_seconds": round(elapsed, 2),
                "lang": lang,
                "type": "midmorning",
                "stats": {
                    "tickers_analyzed": len(unique_tickers) if unique_tickers else 0,
                    "big_caps": len(big_caps) if big_caps else 0,
                    "mega_caps": len(mega_caps) if mega_caps else 0,
                    "google_news": len(google_news) if isinstance(google_news, dict) else 0,
                    "xcom_sentiment": len(xcom_sentiment) if isinstance(xcom_sentiment, dict) else 0,
                    "sectors": len(sectors) if sectors else 0
                }
            }
            
        except Exception as e:
            logger.error("midmorning_update_error", error=str(e))
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "date": report_date.isoformat(),
                "error": str(e),
                "generated_at": datetime.now(NY_TZ).isoformat(),
                "lang": lang,
                "type": "midmorning"
            }
    
    async def generate_bilingual(self, report_date: Optional[date] = None) -> Dict:
        """
        Genera el reporte en inglés y lo traduce a español.
        """
        result_en = await self.generate(report_date, lang="en")
        
        if not result_en.get("success"):
            return result_en
        
        try:
            api_key = settings.GOOGL_API_KEY_V2 or os.getenv('GOOGL_API_KEY')
            client = genai.Client(api_key=api_key)
            
            translate_prompt = f'''Translate this financial report from English to Spanish.

CRITICAL TRANSLATION RULES:
1. Keep the EXACT same format and structure
2. USE THESE EXACT TRANSLATIONS (copy-paste exactly):
   - "MID-MORNING UPDATE" → "ACTUALIZACIÓN DE MEDIA MAÑANA"
   - "USA EDITION" → "EDICIÓN USA" (NOT "EDICIÓN ESTADOS UNIDOS" or "EDICIÓN DE EE.UU.")
   - "MARKET SNAPSHOT" → "PANORAMA DEL MERCADO"
   - "ECONOMIC DATA RESULTS" → "RESULTADOS DE DATOS ECONÓMICOS"
   - "EARNINGS RESULTS (BMO)" → "RESULTADOS DE GANANCIAS (BMO)"
   - "BIG CAPS MOVERS" → "GRANDES CAPITALIZACIONES EN MOVIMIENTO"
   - "TOP SYNTHETIC SECTORS" → "PRINCIPALES SECTORES SINTÉTICOS"
   - "TOP GAINERS" → "PRINCIPALES GANADORES"
   - "TOP LOSERS" → "PRINCIPALES PERDEDORES"
   - "UNUSUAL VOLUME" → "VOLUMEN INUSUAL"
   - "SECTOR ETF PERFORMANCE" → "RENDIMIENTO DE ETFs SECTORIALES"
   - "MARKET NARRATIVE" → "NARRATIVA DEL MERCADO"
   - "[Sentiment]" → "[Sentimiento]"
3. Keep ALL ticker symbols exactly as they are (AAPL, NVDA, etc.)
4. Keep all numbers, percentages, and dollar amounts exactly as they are
5. Translate: "Beat" → "Superado", "Miss" → "No cumplido", "Met" → "Cumplido"
6. Output ONLY the translated report starting with ==== (no introduction)
7. PRESERVE all leading spaces for centered text

Report to translate:
{result_en["report"]}'''

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=translate_prompt
            )
            
            report_es = response.text.strip() if response.text else result_en["report"]
            
            if '====' in report_es:
                import re
                match = re.search(r'={10,}', report_es)
                if match:
                    report_es = report_es[match.start():]
            
            result_es = {
                **result_en,
                "report": report_es,
                "lang": "es",
                "date_formatted": self._format_date_spanish(datetime.now(NY_TZ).date())
            }
            
            return {
                "success": True,
                "reports": {
                    "en": result_en,
                    "es": result_es
                },
                "generated_at": datetime.now(NY_TZ).isoformat()
            }
            
        except Exception as e:
            logger.error("translation_error", error=str(e))
            return {
                "success": True,
                "reports": {
                    "en": result_en,
                    "es": result_en
                },
                "generated_at": datetime.now(NY_TZ).isoformat()
            }
    
    def _format_date_spanish(self, d: date) -> str:
        """Formatear fecha en español"""
        days = {0: 'LUNES', 1: 'MARTES', 2: 'MIERCOLES', 3: 'JUEVES',
                4: 'VIERNES', 5: 'SABADO', 6: 'DOMINGO'}
        months = {1: 'ENERO', 2: 'FEBRERO', 3: 'MARZO', 4: 'ABRIL',
                  5: 'MAYO', 6: 'JUNIO', 7: 'JULIO', 8: 'AGOSTO',
                  9: 'SEPTIEMBRE', 10: 'OCTUBRE', 11: 'NOVIEMBRE', 12: 'DICIEMBRE'}
        return f"{days[d.weekday()]}, {d.day} DE {months[d.month]} DE {d.year}"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def generate_midmorning_update(report_date: Optional[date] = None, lang: str = "en") -> Dict:
    """Helper function para generar el Mid-Morning Update"""
    generator = MidMorningUpdateGenerator()
    return await generator.generate(report_date, lang)


async def generate_bilingual_midmorning_update(report_date: Optional[date] = None) -> Dict:
    """Helper function para generar el Mid-Morning Update bilingüe"""
    generator = MidMorningUpdateGenerator()
    return await generator.generate_bilingual(report_date)


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    async def test():
        print("=" * 60)
        print("TESTING MID-MORNING UPDATE GENERATOR V2")
        print("=" * 60)
        
        generator = MidMorningUpdateGenerator()
        result = await generator.generate()
        
        if result.get("success"):
            print("\n✓ Report generated successfully!")
            print(f"  - Tickers analyzed: {result['stats']['tickers_analyzed']}")
            print(f"  - Big caps: {result['stats']['big_caps_found']}")
            print(f"  - Mega caps: {result['stats']['mega_caps_found']}")
            print(f"  - Google news: {result['stats']['google_news_found']}")
            print(f"  - X.com sentiment: {result['stats']['xcom_sentiment_found']}")
            print(f"  - Sectors: {result['stats']['sectors_identified']}")
            print(f"  - Generation time: {result['generation_time_seconds']}s")
            print("\n" + "=" * 60)
            print("REPORT PREVIEW:")
            print("=" * 60)
            print(result['report'][:4000])
        else:
            print(f"\n✗ Error: {result.get('error')}")
    
    asyncio.run(test())
