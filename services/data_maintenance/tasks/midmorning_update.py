"""
Mid-Morning Update Generator
============================

Genera el reporte de media mañana (12:30 ET) combinando:
1. Datos del Scanner TradeUL (tickers en movimiento)
2. Gemini + Google Search (noticias formales)
3. Grok + X.com Search (sentiment y breaking news)
4. Clustering de sectores sintéticos
5. Consolidación final inteligente

Este es un reporte REACTIVO que analiza lo que está pasando
en la primera mitad de la sesión de trading.
"""

import os
import json
import asyncio
import aiohttp
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
    google_news: str  # De Gemini + Google Search
    xcom_sentiment: str  # De Grok + X.com
    catalyst: Optional[str] = None


@dataclass
class SyntheticSector:
    """Sector sintético identificado por IA"""
    name: str
    tickers: List[str]
    avg_change: float
    narrative: str
    leader: str  # Ticker líder del sector


# ============================================================================
# SCANNER DATA EXTRACTION (Layer 1)
# ============================================================================

class ScannerDataExtractor:
    """Extrae datos del Scanner TradeUL desde Redis"""
    
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client
    
    async def get_all_movers(self, limit_per_category: int = 25) -> Dict[str, List[ScannerTicker]]:
        """
        Extrae todos los movers de las categorías principales.
        
        Returns:
            Dict con categorías y sus tickers
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
                           max_tickers: int = 50) -> List[ScannerTicker]:
        """
        Obtiene lista única de tickers ordenados por relevancia.
        Prioriza: winners > losers > momentum > high_volume
        """
        seen = set()
        unique = []
        
        # Orden de prioridad
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
                            min_market_cap: float = 10_000_000_000,  # $10B
                            max_results: int = 12) -> List[ScannerTicker]:
        """
        Extrae los big caps (>$10B market cap) que están moviéndose en el scanner.
        
        Returns:
            Lista de big caps ordenados por movimiento absoluto
        """
        seen = set()
        big_caps = []
        
        # Buscar en todas las categorías
        for category, tickers in categories_data.items():
            for ticker in tickers:
                if ticker.symbol in seen:
                    continue
                
                # Filtrar por market cap
                if ticker.market_cap and ticker.market_cap >= min_market_cap:
                    # Solo incluir si tiene movimiento significativo (>0.5%)
                    if abs(ticker.change_percent) >= 0.5:
                        seen.add(ticker.symbol)
                        big_caps.append(ticker)
        
        # Ordenar por movimiento absoluto (los que más se mueven primero)
        big_caps.sort(key=lambda x: abs(x.change_percent), reverse=True)
        
        logger.info("big_caps_extracted", count=len(big_caps[:max_results]))
        return big_caps[:max_results]


# ============================================================================
# GEMINI + GOOGLE SEARCH (Layer 2A)
# ============================================================================

class GeminiNewsEnricher:
    """Enriquece tickers con noticias de Google Search via Gemini"""
    
    def __init__(self):
        api_key = settings.GOOGL_API_KEY_V2 or os.getenv('GOOGL_API_KEY')
        if not api_key:
            raise ValueError("GOOGL_API_KEY es requerido")
        
        self.client = genai.Client(api_key=api_key)
        self.google_search_tool = Tool(google_search=GoogleSearch())
        self.model = "gemini-3-pro-preview"
    
    async def get_news_for_tickers(self, tickers: List[ScannerTicker]) -> Dict[str, str]:
        """
        Obtiene noticias de Google para una lista de tickers.
        
        Returns:
            Dict con symbol -> news_summary
        """
        if not tickers:
            return {}
        
        # Crear lista de símbolos con cambios
        ticker_info = []
        for t in tickers[:30]:  # Limitar a 30 para el prompt
            direction = "UP" if t.change_percent > 0 else "DOWN"
            ticker_info.append(f"{t.symbol} ({t.change_percent:+.1f}% {direction})")
        
        today = datetime.now(NY_TZ).strftime("%B %d, %Y")
        
        prompt = f'''You are a senior financial news analyst. Search Google News for what is happening TODAY ({today}) with these stocks.

STOCKS MOVING RIGHT NOW:
{chr(10).join(ticker_info)}

CRITICAL RULES:
1. ONLY report news from TODAY ({today}) - do NOT include old news
2. If there is no news from TODAY, write "No news today"
3. Be DETAILED - include specific numbers, names, percentages, dollar amounts
4. DO NOT mention the source (no "according to...", "reported by...", etc.)
5. Write in ACTIVE voice with specific facts

FOR EACH TICKER provide 2-3 sentences covering:
- The specific catalyst/event causing the move
- Key numbers: dollar amounts, percentages, share counts, price targets
- Names of analysts, executives, or firms involved
- Market impact or investor reaction

OUTPUT FORMAT:
SYMBOL: [Detailed 2-3 sentence explanation with specific facts and numbers]

Example:
NVDA: Upgraded to Buy by Goldman Sachs with price target raised from $700 to $850, citing 40% growth in AI chip demand. CEO Jensen Huang announced new Blackwell GPU architecture will ship in Q2.
LMT: Won $2.3B contract from Pentagon for F-35 maintenance, the largest single award this quarter. Defense spending boost under new administration driving sector-wide rally.

NOW search for TODAY's news on each ticker:'''

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
                        # Limpiar símbolos
                        symbol = ''.join(c for c in symbol if c.isalpha())
                        if symbol and news:
                            result[symbol] = news
            
            logger.info("gemini_news_fetched", ticker_count=len(result))
            return result
            
        except Exception as e:
            logger.error("gemini_news_error", error=str(e))
            return {}


# ============================================================================
# GROK + X.COM SEARCH (Layer 2B)
# ============================================================================

class GrokSentimentEnricher:
    """Enriquece tickers con sentiment de X.com via Grok"""
    
    def __init__(self):
        self.api_key = os.getenv('GROK_API_KEY_2') or settings.GROK_API_KEY
        if not self.api_key:
            raise ValueError("GROK_API_KEY es requerido")
        
        self.base_url = "https://api.x.ai/v1/chat/completions"
    
    async def get_xcom_sentiment(self, tickers: List[ScannerTicker]) -> Dict[str, str]:
        """
        Obtiene sentiment de X.com para una lista de tickers via Grok.
        
        Returns:
            Dict con symbol -> xcom_sentiment
        """
        if not tickers:
            return {}
        
        # Crear lista de símbolos con cambios
        ticker_info = []
        for t in tickers[:25]:  # Limitar a 25
            direction = "UP" if t.change_percent > 0 else "DOWN"
            ticker_info.append(f"${t.symbol} ({t.change_percent:+.1f}% {direction})")
        
        today = datetime.now(NY_TZ).strftime("%B %d, %Y")
        
        prompt = f'''Search X.com for breaking financial news and trader sentiment about these stocks moving TODAY ({today}).

STOCKS:
{chr(10).join(ticker_info)}

CRITICAL RULES:
1. ONLY posts from TODAY ({today}) - ignore anything older
2. DO NOT mention "according to X user" or cite specific accounts
3. Report the NEWS and SENTIMENT, not who posted it
4. Be specific with numbers, percentages, and facts
5. Include institutional flow info if mentioned (dark pool, unusual options)

FOR EACH TICKER report:
- Breaking news or rumors driving the move
- Trader sentiment summary (bullish/bearish/mixed)
- Options activity or unusual flow if mentioned
- Key price levels traders are watching

OUTPUT FORMAT:
$SYMBOL: [2-3 sentences of detailed analysis without mentioning sources]

Example:
$NVDA: Strong bullish sentiment following analyst upgrade. Heavy call buying at $800 strike for March expiry. Traders noting AI revenue could exceed $50B next year.
$TSLA: Mixed sentiment after delivery miss. Bears targeting $180 support, bulls defending on margin improvement. Unusual put activity in weekly options.

NOW search X.com for TODAY's discussion:'''

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "grok-4-1-fast-reasoning",
                        "messages": [{"role": "user", "content": prompt}],
                        "search_enabled": True,  # Habilitar búsqueda en X.com
                        "temperature": 0.3
                    },
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                        
                        result = {}
                        if content:
                            lines = content.strip().split('\n')
                            for line in lines:
                                if ':' in line and '$' in line:
                                    # Extraer símbolo (entre $ y :)
                                    start = line.find('$') + 1
                                    end = line.find(':')
                                    if start > 0 and end > start:
                                        symbol = line[start:end].strip().upper()
                                        sentiment = line[end+1:].strip()
                                        if symbol and sentiment:
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
    """Agrupa tickers en sectores sintéticos usando IA"""
    
    def __init__(self):
        api_key = settings.GOOGL_API_KEY_V2 or os.getenv('GOOGL_API_KEY')
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-3-pro-preview"
    
    async def cluster_into_sectors(self, tickers: List[ScannerTicker], 
                                    news_data: Dict[str, str]) -> List[SyntheticSector]:
        """
        Agrupa tickers en sectores sintéticos basados en narrativas del mercado.
        
        Returns:
            Lista de SyntheticSector ordenados por performance
        """
        if not tickers:
            return []
        
        # Preparar datos para el análisis
        ticker_data = []
        for t in tickers:
            news = news_data.get(t.symbol, "No news")
            ticker_data.append(
                f"{t.symbol}: {t.change_percent:+.1f}% | "
                f"Sector: {t.sector or 'Unknown'} | "
                f"Industry: {t.industry or 'Unknown'} | "
                f"News: {news[:100]}"
            )
        
        prompt = f'''You are a market analyst creating SYNTHETIC SECTORS based on today's market narratives.

STOCKS MOVING TODAY:
{chr(10).join(ticker_data)}

TASK:
1. Group these stocks into 5-8 SYNTHETIC SECTORS based on THEMES, not traditional sectors
2. Synthetic sectors should capture market NARRATIVES (e.g., "AI INFRASTRUCTURE", "QUANTUM COMPUTING", "EV BATTERIES", "BIOTECH FDA PLAYS", "MEME STOCKS", etc.)
3. Calculate average performance for each sector
4. Identify the sector leader (biggest mover)

OUTPUT FORMAT (JSON):
{{
  "sectors": [
    {{
      "name": "AI INFRASTRUCTURE",
      "tickers": ["NVDA", "SMCI", "AMD"],
      "avg_change": 5.2,
      "leader": "SMCI",
      "narrative": "AI chip and server demand driving sector higher"
    }},
    ...
  ]
}}

IMPORTANT:
- Be creative with sector names - capture the NARRATIVE
- Each ticker should only appear in ONE sector
- Sort sectors by avg_change (best performing first)
- Narrative should be 1 sentence explaining the theme

Respond with ONLY the JSON:'''

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt
            )
            
            if response.text:
                # Limpiar respuesta JSON
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
                        leader=s.get('leader', '')
                    ))
                
                # Ordenar por avg_change descendente
                sectors.sort(key=lambda x: x.avg_change, reverse=True)
                
                logger.info("sectors_clustered", sector_count=len(sectors))
                return sectors
            
            return []
            
        except Exception as e:
            logger.error("sector_clustering_error", error=str(e))
            return []


# ============================================================================
# MORNING NEWS COMPLETER (Layer 2D) - Completar datos del Morning Call
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
        
        # Buscar sección ECONOMIC EVENTS
        match = re.search(r'ECONOMIC EVENTS.*?\n\n(.*?)(?=\n\n[A-Z]|\n={10,}|$)', 
                         morning_report, re.DOTALL | re.IGNORECASE)
        if match:
            section = match.group(1)
            # Extraer líneas que empiezan con hora
            for line in section.split('\n'):
                line = line.strip()
                if re.match(r'^\d{1,2}:\d{2}', line):
                    events.append(line)
        
        return events[:15]  # Limitar a 15 eventos
    
    def extract_earnings_bmo(self, morning_report: str) -> List[str]:
        """Extraer empresas que reportan BMO (Before Market Open)"""
        import re
        earnings = []
        
        # Buscar sección COMPANIES REPORTING RESULTS
        match = re.search(r'COMPANIES REPORTING RESULTS.*?\n\n(.*?)(?=\n\n[A-Z]|\n={10,}|$)', 
                         morning_report, re.DOTALL | re.IGNORECASE)
        if match:
            section = match.group(1)
            for line in section.split('\n'):
                line = line.strip()
                # Solo BMO (Before Market Open)
                if 'BMO' in line.upper() and '(' in line:
                    earnings.append(line)
        
        return earnings[:10]  # Limitar a 10 empresas
    
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
1. DO NOT write any introduction or explanation
2. DO NOT write "Here are the results" or similar
3. Output ONLY the data in the exact format below
4. One event per line
5. Skip events not yet released

OUTPUT FORMAT (one line per event):
EVENT NAME: Actual X.XX vs Expected X.XX (Beat/Miss/Met) - Brief reaction

Example output:
Initial Jobless Claims: Actual 198K vs Expected 205K (Beat) - Labor market strong
Trade Balance: Actual -$67.4B vs Expected -$65.0B (Miss) - Wider deficit
Productivity Q3: Actual +4.9% vs Expected +2.5% (Beat) - Strong growth

START OUTPUT NOW (no introduction):'''

        try:
            response = self.client.models.generate_content(
                model="gemini-3-pro-preview",
                contents=prompt,
                config={'tools': [self.google_search_tool]}
            )
            result = response.text.strip() if response.text else ""
            # Limpiar introducciones de IA
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
        earnings_text = "\n".join(earnings[:8])
        
        prompt = f'''Search for ACTUAL EARNINGS RESULTS of these BMO companies today ({today}).

COMPANIES:
{earnings_text}

CRITICAL RULES:
1. DO NOT write any introduction or explanation
2. Output ONLY the data in the exact format below
3. One company per line
4. Skip companies that haven't reported yet

OUTPUT FORMAT (one line per company):
TICKER: EPS $X.XX vs Est $X.XX (Beat/Miss) | Rev $X.XXB vs Est $X.XXB | Stock +/-X.X%

Example output:
RPM: EPS $1.52 vs Est $1.42 (Beat) | Rev $1.85B vs Est $1.82B | Stock +3.2%
STZ: EPS $3.25 vs Est $3.10 (Beat) | Rev $2.5B vs Est $2.4B | Stock +1.8%
AYI: EPS $4.69 vs Est $4.45 (Beat) | Rev $1.14B vs Est $1.15B (Miss) | Stock -13%

START OUTPUT NOW (no introduction):'''

        try:
            response = self.client.models.generate_content(
                model="gemini-3-pro-preview",
                contents=prompt,
                config={'tools': [self.google_search_tool]}
            )
            result = response.text.strip() if response.text else ""
            # Limpiar introducciones de IA
            result = self._clean_ai_intro(result)
            logger.info("earnings_results_fetched", chars=len(result))
            return result
        except Exception as e:
            logger.error("earnings_results_error", error=str(e))
            return ""
    
    def _clean_ai_intro(self, text: str) -> str:
        """Eliminar introducciones típicas de IA y formatear con saltos de línea"""
        import re
        
        # Patrones de introducción a eliminar
        intro_patterns = [
            r'^(Here are|Aquí están|Based on|Basado en|The following|Los siguientes|Below are|A continuación)[^:]*:?\s*',
            r'^(Note:|Nota:)[^\n]*\n*',
            r'^\s*\*+\s*',  # Asteriscos al inicio
        ]
        
        result = text
        for pattern in intro_patterns:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE | re.MULTILINE)
        
        # Agregar saltos de línea ANTES de cada nuevo evento económico
        # Detectar inicio de evento: Nombre que empieza con mayúscula seguido de ":"
        # Pero primero agregar newline después de ciertos patrones de cierre
        
        # Patrón 1: Después de (Beat/Miss/Met/N/A) - descripción - antes del siguiente evento
        result = re.sub(
            r'(\(Beat\)|\(Miss\)|\(Met\)|\(N/A\)|\(Superado\)|\(No Alcanzado\)|\(Cumplido\))\s*-?\s*([^A-Z\n]*?)(?=\s*[A-Z][a-zA-Z\s\.]+:)',
            r'\1 - \2\n',
            result
        )
        
        # Patrón 2: Para earnings - después de Stock/Acciones +/-X.X% antes del siguiente ticker
        result = re.sub(
            r'(Stock|Acciones)\s*([+-]?\d+[.,]?\d*%)\s*(?=[A-Z]{2,5}:)',
            r'\1 \2\n',
            result
        )
        
        # Patrón 3: Forzar newline antes de tickers conocidos en earnings (TICKER:)
        result = re.sub(
            r'\s+((?:TLRY|AEHR|RPM|AYI|CMC|SMPL|STZ|NVDA|AAPL|MSFT|META|AMZN|GOOGL|TSLA)[A-Z]*:)',
            r'\n\1',
            result
        )
        
        # Limpiar líneas vacías múltiples
        result = re.sub(r'\n{3,}', '\n\n', result)
        # Limpiar espacios al inicio de líneas
        result = re.sub(r'\n +', '\n', result)
        
        return result.strip()
    
    async def complete_morning_data(self, report_date: date) -> Dict[str, str]:
        """
        Proceso completo: leer morning news, extraer eventos/earnings, buscar resultados.
        
        Returns:
            Dict con 'economic_results' y 'earnings_results'
        """
        logger.info("completing_morning_data", date=str(report_date))
        
        # 1. Leer Morning News
        morning_report = await self.get_morning_news(report_date)
        if not morning_report:
            logger.warning("no_morning_news_found", date=str(report_date))
            return {"economic_results": "", "earnings_results": ""}
        
        # 2. Extraer eventos y earnings
        events = self.extract_economic_events(morning_report)
        earnings = self.extract_earnings_bmo(morning_report)
        
        logger.info("extracted_from_morning_news", 
                   events_count=len(events), 
                   earnings_count=len(earnings))
        
        # 3. Buscar resultados en paralelo
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
    """Genera el reporte final consolidado"""
    
    def __init__(self):
        api_key = settings.GOOGL_API_KEY_V2 or os.getenv('GOOGL_API_KEY')
        self.client = genai.Client(api_key=api_key)
        self.google_search_tool = Tool(google_search=GoogleSearch())
        self.model = "gemini-3-pro-preview"
    
    def _format_date(self, d: date) -> str:
        """Formatear fecha para el reporte"""
        days_en = {0: 'MONDAY', 1: 'TUESDAY', 2: 'WEDNESDAY', 3: 'THURSDAY', 
                   4: 'FRIDAY', 5: 'SATURDAY', 6: 'SUNDAY'}
        months_en = {1: 'JANUARY', 2: 'FEBRUARY', 3: 'MARCH', 4: 'APRIL', 
                     5: 'MAY', 6: 'JUNE', 7: 'JULY', 8: 'AUGUST', 
                     9: 'SEPTEMBER', 10: 'OCTOBER', 11: 'NOVEMBER', 12: 'DECEMBER'}
        return f"{days_en[d.weekday()]}, {months_en[d.month]} {d.day}, {d.year}"
    
    def _format_change(self, change: float) -> str:
        """Formatea cambio con color HTML"""
        if change > 0:
            return f'<span style="color: #22c55e; font-weight: bold;">+{change:.2f}%</span>'
        elif change < 0:
            return f'<span style="color: #ef4444; font-weight: bold;">{change:.2f}%</span>'
        else:
            return f'{change:.2f}%'
    
    def _format_change_plain(self, change: float) -> str:
        """Formatea cambio sin HTML (para texto plano)"""
        if change > 0:
            return f'+{change:.2f}%'
        else:
            return f'{change:.2f}%'
    
    def _format_market_cap(self, market_cap: float) -> str:
        """Formatea market cap en formato legible (B/T)"""
        if market_cap >= 1_000_000_000_000:  # Trillion
            return f"${market_cap / 1_000_000_000_000:.1f}T"
        elif market_cap >= 1_000_000_000:  # Billion
            return f"${market_cap / 1_000_000_000:.1f}B"
        elif market_cap >= 1_000_000:  # Million
            return f"${market_cap / 1_000_000:.0f}M"
        else:
            return f"${market_cap:,.0f}"
    
    def _clean_markdown(self, text: str) -> str:
        """Limpia markdown del texto preservando saltos de línea"""
        import re
        # Eliminar todos los ** (bold markers)
        text = text.replace('**', '')
        # Eliminar italic (*texto* -> texto) pero no asteriscos sueltos
        text = re.sub(r'\*([^*\s][^*]*[^*\s])\*', r'\1', text)
        # Eliminar headers markdown (# ## ###)
        text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
        # Limpiar backslashes
        text = text.replace('\\$', '$').replace('\\&', '&')
        # Limpiar espacios múltiples (pero NO newlines)
        text = re.sub(r'[^\S\n]+', ' ', text)
        # Limpiar múltiples newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
    
    async def generate_market_snapshot(self) -> str:
        """Genera el snapshot del mercado usando FMP API"""
        import httpx
        
        fmp_key = os.getenv('FMP_API_KEY')
        if not fmp_key:
            logger.warning("FMP_API_KEY not found for market snapshot")
            return "Market data unavailable"
        
        # Símbolos de FMP
        symbols = {
            'S&P 500': '^GSPC',
            'Nasdaq': '^IXIC',
            'Dow': '^DJI',
            'Russell 2000': '^RUT',
            'VIX': '^VIX',
        }
        
        lines = []
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for name, symbol in symbols.items():
                    try:
                        url = f'https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={fmp_key}'
                        resp = await client.get(url)
                        data = resp.json()
                        
                        if data and len(data) > 0:
                            d = data[0]
                            price = d.get('price', 0)
                            change_pct = d.get('changesPercentage', 0)
                            
                            if name == 'VIX':
                                lines.append(f"VIX: {price:.2f}")
                            else:
                                sign = '+' if change_pct >= 0 else ''
                                lines.append(f"{name}: {price:,.2f} ({sign}{change_pct:.2f}%)")
                    except Exception as e:
                        logger.warning(f"fmp_snapshot_error", symbol=symbol, error=str(e))
                
                # Treasury yield
                try:
                    url = f'https://financialmodelingprep.com/api/v4/treasury?from=2026-01-01&to=2026-01-08&apikey={fmp_key}'
                    resp = await client.get(url)
                    data = resp.json()
                    if data and len(data) > 0:
                        yield_10y = data[0].get('year10', 0)
                        lines.append(f"10Y Treasury: {yield_10y:.2f}%")
                except:
                    pass
            
            if lines:
                return '\n'.join(lines)
            return "Market data unavailable"
            
        except Exception as e:
            logger.error("market_snapshot_error", error=str(e))
            return "Market data unavailable"
    
    async def generate_report(
        self,
        report_date: date,
        tickers: List[ScannerTicker],
        google_news: Dict[str, str],
        xcom_sentiment: Dict[str, str],
        sectors: List[SyntheticSector],
        morning_data: Dict[str, str],
        big_caps: List[ScannerTicker] = None,
        lang: str = "en"
    ) -> str:
        """
        Genera el reporte Mid-Morning consolidado.
        
        Args:
            report_date: Fecha del reporte
            tickers: Lista de tickers del scanner
            google_news: Noticias de Google por ticker
            xcom_sentiment: Sentiment de X.com por ticker
            sectors: Sectores sintéticos identificados
            morning_data: Resultados de eventos económicos y earnings del morning
            lang: Idioma del reporte (en/es)
        
        Returns:
            Reporte formateado en texto plano
        """
        date_formatted = self._format_date(report_date)
        time_et = datetime.now(NY_TZ).strftime("%H:%M ET")
        
        # Obtener snapshot del mercado
        market_snapshot = await self.generate_market_snapshot()
        
        # Separar gainers y losers
        gainers = sorted([t for t in tickers if t.change_percent > 0], 
                        key=lambda x: x.change_percent, reverse=True)[:10]
        losers = sorted([t for t in tickers if t.change_percent < 0], 
                       key=lambda x: x.change_percent)[:10]
        
        # Top 2 sectores sintéticos
        top_sectors = sectors[:2] if len(sectors) >= 2 else sectors
        
        # Construir reporte
        report_lines = []
        
        # Header
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
        
        # Market Snapshot
        report_lines.append("MARKET SNAPSHOT")
        report_lines.append("")
        report_lines.append(self._clean_markdown(market_snapshot))
        report_lines.append("")
        report_lines.append("")
        
        # ==== ECONOMIC EVENTS RESULTS (del Morning News) ====
        economic_results = morning_data.get("economic_results", "")
        if economic_results and len(economic_results) > 20:
            report_lines.append("ECONOMIC DATA RESULTS")
            report_lines.append("")
            report_lines.append(self._clean_markdown(economic_results))
            report_lines.append("")
            report_lines.append("")
        
        # ==== EARNINGS RESULTS (BMO del Morning News) ====
        earnings_results = morning_data.get("earnings_results", "")
        if earnings_results and len(earnings_results) > 20:
            report_lines.append("EARNINGS RESULTS (BMO)")
            report_lines.append("")
            report_lines.append(self._clean_markdown(earnings_results))
            report_lines.append("")
            report_lines.append("")
        
        # ==== BIG CAPS MOVERS (>$10B Market Cap) ====
        if big_caps:
            report_lines.append("BIG CAPS MOVERS")
            report_lines.append("")
            
            # Separar gainers y losers de big caps
            big_gainers = [t for t in big_caps if t.change_percent > 0]
            big_losers = [t for t in big_caps if t.change_percent < 0]
            
            for t in big_gainers[:6]:
                change_str = self._format_change_plain(t.change_percent)
                name_str = f" ({t.name})" if t.name and len(t.name) < 30 else ""
                mcap_str = self._format_market_cap(t.market_cap) if t.market_cap else ""
                news = self._clean_markdown(google_news.get(t.symbol, ""))
                
                report_lines.append(f"{t.symbol}{name_str} {change_str} | {mcap_str}")
                if news and news.lower() not in ["no specific catalyst found", "no news today", ""]:
                    report_lines.append(f"   {news}")
                report_lines.append("")
            
            for t in big_losers[:6]:
                change_str = self._format_change_plain(t.change_percent)
                name_str = f" ({t.name})" if t.name and len(t.name) < 30 else ""
                mcap_str = self._format_market_cap(t.market_cap) if t.market_cap else ""
                news = self._clean_markdown(google_news.get(t.symbol, ""))
                
                report_lines.append(f"{t.symbol}{name_str} {change_str} | {mcap_str}")
                if news and news.lower() not in ["no specific catalyst found", "no news today", ""]:
                    report_lines.append(f"   {news}")
                report_lines.append("")
            
            report_lines.append("")
        
        # Top Synthetic Sectors
        report_lines.append("TOP SYNTHETIC SECTORS")
        report_lines.append("")
        
        for i, sector in enumerate(top_sectors, 1):
            change_str = self._format_change_plain(sector.avg_change)
            report_lines.append(f"{i}. {sector.name} ({change_str})")
            report_lines.append(f"   Tickers: {', '.join(sector.tickers[:6])}")
            report_lines.append(f"   Leader: {sector.leader}")
            report_lines.append(f"   Narrative: {sector.narrative}")
            report_lines.append("")
        
        # Other sectors
        if len(sectors) > 2:
            other_sectors = []
            for s in sectors[2:6]:
                other_sectors.append(f"{s.name} {self._format_change_plain(s.avg_change)}")
            report_lines.append(f"Other sectors: {', '.join(other_sectors)}")
            report_lines.append("")
        
        report_lines.append("")
        
        # Top Gainers
        report_lines.append("TOP GAINERS")
        report_lines.append("")
        
        for t in gainers[:8]:
            change_str = self._format_change_plain(t.change_percent)
            news = self._clean_markdown(google_news.get(t.symbol, ""))
            xcom = self._clean_markdown(xcom_sentiment.get(t.symbol, ""))
            
            # Combinar noticias sin mencionar fuente
            combined_news = ""
            if news and news.lower() not in ["no specific catalyst found", "no news today", ""]:
                combined_news = news
            if xcom and "no" not in xcom.lower()[:20]:
                if combined_news:
                    combined_news += " " + xcom
                else:
                    combined_news = xcom
            
            report_lines.append(f"{t.symbol} {change_str}")
            if combined_news:
                report_lines.append(f"   {combined_news}")
            report_lines.append("")
        
        report_lines.append("")
        
        # Top Losers
        report_lines.append("TOP LOSERS")
        report_lines.append("")
        
        for t in losers[:8]:
            change_str = self._format_change_plain(t.change_percent)
            news = self._clean_markdown(google_news.get(t.symbol, ""))
            xcom = self._clean_markdown(xcom_sentiment.get(t.symbol, ""))
            
            # Combinar noticias sin mencionar fuente
            combined_news = ""
            if news and news.lower() not in ["no specific catalyst found", "no news today", ""]:
                combined_news = news
            if xcom and "no" not in xcom.lower()[:20]:
                if combined_news:
                    combined_news += " " + xcom
                else:
                    combined_news = xcom
            
            report_lines.append(f"{t.symbol} {change_str}")
            if combined_news:
                report_lines.append(f"   {combined_news}")
            report_lines.append("")
        
        report_lines.append("")
        
        # High Volume / Anomalies
        high_vol = [t for t in tickers if t.rvol and t.rvol > 3.0][:5]
        if high_vol:
            report_lines.append("UNUSUAL VOLUME")
            report_lines.append("")
            for t in high_vol:
                vol_str = f"{t.volume/1e6:.1f}M" if t.volume > 1e6 else f"{t.volume/1e3:.0f}K"
                rvol_str = f"{t.rvol:.1f}x avg" if t.rvol else ""
                change_str = self._format_change_plain(t.change_percent)
                report_lines.append(f"{t.symbol} {change_str} | Volume: {vol_str} ({rvol_str})")
            report_lines.append("")
            report_lines.append("")
        
        # Market Narrative (Gemini genera análisis)
        narrative_prompt = f'''Based on this market data, write a 3-4 sentence professional market narrative:

Top Gainers: {', '.join([f"{t.symbol} {t.change_percent:+.1f}%" for t in gainers[:5]])}
Top Losers: {', '.join([f"{t.symbol} {t.change_percent:+.1f}%" for t in losers[:5]])}
Top Sectors: {', '.join([f"{s.name} {s.avg_change:+.1f}%" for s in top_sectors])}

Write a concise, professional analysis of what's driving the market this morning. Focus on the main themes and narratives.'''

        try:
            narrative_response = self.client.models.generate_content(
                model=self.model,
                contents=narrative_prompt
            )
            narrative = narrative_response.text.strip() if narrative_response.text else ""
            
            if narrative:
                report_lines.append("MARKET NARRATIVE")
                report_lines.append("")
                report_lines.append(narrative)
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
    Generador principal del Mid-Morning Update.
    
    Orquesta todas las capas del pipeline:
    1. Scanner data extraction
    2. Morning News completion (economic events + earnings results)
    3. News enrichment (Gemini + Google)
    4. Sentiment enrichment (Grok + X.com)
    5. Sector clustering
    6. Final consolidation
    """
    
    def __init__(self):
        self.redis = None
        self.scanner_extractor = None
        self.morning_completer = None
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
        
        Args:
            report_date: Fecha del reporte (default: hoy)
            lang: Idioma del reporte (en/es)
        
        Returns:
            Dict con el reporte y metadata
        """
        if report_date is None:
            report_date = datetime.now(NY_TZ).date()
        
        logger.info("generating_midmorning_update", date=str(report_date), lang=lang)
        start_time = datetime.now()
        
        try:
            await self._ensure_redis()
            
            # ============================================
            # LAYER 1: Scanner Data Extraction
            # ============================================
            logger.info("layer1_scanner_extraction_start")
            categories_data = await self.scanner_extractor.get_all_movers()
            unique_tickers = self.scanner_extractor.get_unique_tickers(categories_data, max_tickers=50)
            
            # Extraer big caps (>$10B market cap) que se están moviendo
            big_caps = self.scanner_extractor.get_big_caps_movers(categories_data)
            logger.info("layer1_complete", ticker_count=len(unique_tickers), big_caps_count=len(big_caps))
            
            if not unique_tickers:
                return {
                    "success": False,
                    "date": report_date.isoformat(),
                    "error": "No scanner data available",
                    "generated_at": datetime.now(NY_TZ).isoformat()
                }
            
            # ============================================
            # LAYER 2A: Complete Morning News Data
            # ============================================
            logger.info("layer2a_morning_completion_start")
            morning_data = await self.morning_completer.complete_morning_data(report_date)
            logger.info("layer2a_complete", 
                       economic_chars=len(morning_data.get("economic_results", "")),
                       earnings_chars=len(morning_data.get("earnings_results", "")))
            
            # ============================================
            # LAYER 2B: Parallel News Enrichment
            # ============================================
            logger.info("layer2b_enrichment_start")
            
            # Ejecutar en paralelo: Gemini news, Grok sentiment
            gemini_task = self.gemini_enricher.get_news_for_tickers(unique_tickers)
            grok_task = self.grok_enricher.get_xcom_sentiment(unique_tickers)
            
            google_news, xcom_sentiment = await asyncio.gather(
                gemini_task, grok_task, return_exceptions=True
            )
            
            # Manejar excepciones
            if isinstance(google_news, Exception):
                logger.error("gemini_enrichment_failed", error=str(google_news))
                google_news = {}
            if isinstance(xcom_sentiment, Exception):
                logger.error("grok_enrichment_failed", error=str(xcom_sentiment))
                xcom_sentiment = {}
            
            logger.info("layer2_enrichment_complete", 
                       google_news_count=len(google_news),
                       xcom_sentiment_count=len(xcom_sentiment))
            
            # ============================================
            # LAYER 2C: Sector Clustering
            # ============================================
            logger.info("layer2c_sector_clustering_start")
            sectors = await self.sector_analyzer.cluster_into_sectors(unique_tickers, google_news)
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
                big_caps=big_caps,
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
                    "tickers_analyzed": len(unique_tickers),
                    "google_news_found": len(google_news),
                    "xcom_sentiment_found": len(xcom_sentiment),
                    "sectors_identified": len(sectors)
                }
            }
            
        except Exception as e:
            logger.error("midmorning_update_error", error=str(e))
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
        
        Returns:
            Dict con ambas versiones
        """
        # Generar en inglés primero
        result_en = await self.generate(report_date, lang="en")
        
        if not result_en.get("success"):
            return result_en
        
        # Traducir a español
        try:
            api_key = settings.GOOGL_API_KEY_V2 or os.getenv('GOOGL_API_KEY')
            client = genai.Client(api_key=api_key)
            
            translate_prompt = f'''Translate this financial report from English to Spanish.
Keep the EXACT same format and structure. Translate all content including section headers.
Do NOT add any introduction. Output ONLY the translated report.

Report:
{result_en["report"]}'''

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=translate_prompt
            )
            
            report_es = response.text.strip() if response.text else result_en["report"]
            
            # Limpiar si empieza con introducción
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
        print("TESTING MID-MORNING UPDATE GENERATOR")
        print("=" * 60)
        
        generator = MidMorningUpdateGenerator()
        result = await generator.generate()
        
        if result.get("success"):
            print("\n✓ Report generated successfully!")
            print(f"  - Tickers analyzed: {result['stats']['tickers_analyzed']}")
            print(f"  - Google news: {result['stats']['google_news_found']}")
            print(f"  - X.com sentiment: {result['stats']['xcom_sentiment_found']}")
            print(f"  - Sectors: {result['stats']['sectors_identified']}")
            print(f"  - Generation time: {result['generation_time_seconds']}s")
            print("\n" + "=" * 60)
            print("REPORT PREVIEW:")
            print("=" * 60)
            print(result['report'][:3000])
        else:
            print(f"\n✗ Error: {result.get('error')}")
    
    asyncio.run(test())

