"""
Morning News Call Generator V2
==============================

Genera el reporte matutino de noticias financieras usando:
- Grok 4.1 Fast con búsqueda nativa de X.com y Web (xai-sdk)
- Gemini 2.5 Flash con Google Search para datos adicionales

Se ejecuta diariamente a las 7:30 AM ET (antes de pre-market).
"""

import asyncio
import os
import re
from datetime import datetime, date
from zoneinfo import ZoneInfo
from typing import Dict, Optional, List, Tuple

from google import genai
from google.genai.types import Tool, GoogleSearch

from xai_sdk import Client as XAIClient
from xai_sdk.chat import user
from xai_sdk.tools import web_search, x_search

import httpx

from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Símbolos de FMP para datos de mercado "Before the Bell"
MARKET_SYMBOLS = {
    'sp500': '^GSPC',
    'dow': '^DJI',
    'nasdaq': '^IXIC',
    'vix': '^VIX',
    'dax': '^GDAXI',
    'ftse': '^FTSE',
    'cac': '^FCHI',
    'nikkei': '^N225',
    'hangseng': '^HSI',
    'gold': 'GCUSD',
    'oil': 'CLUSD',
    'bitcoin': 'BTCUSD',
    'dxy': 'DX-Y.NYB'
}

NY_TZ = ZoneInfo("America/New_York")

# Cuentas financieras de X.com para búsqueda
FINANCIAL_X_HANDLES = [
    "Reuters",
    "Bloomberg",
    "CNBC",
    "WSJ",
    "DeItaone",
    "FirstSquawk",
    "LiveSquawk",
    "Newsquawk",
    "unusual_whales",
    "zabormarket"
]

# Días y meses para formateo
DAYS_EN = {0: 'MONDAY', 1: 'TUESDAY', 2: 'WEDNESDAY', 3: 'THURSDAY', 
           4: 'FRIDAY', 5: 'SATURDAY', 6: 'SUNDAY'}
MONTHS_EN = {1: 'JANUARY', 2: 'FEBRUARY', 3: 'MARCH', 4: 'APRIL', 
             5: 'MAY', 6: 'JUNE', 7: 'JULY', 8: 'AUGUST', 
             9: 'SEPTEMBER', 10: 'OCTOBER', 11: 'NOVEMBER', 12: 'DECEMBER'}

DAYS_ES = {0: 'LUNES', 1: 'MARTES', 2: 'MIERCOLES', 3: 'JUEVES',
           4: 'VIERNES', 5: 'SABADO', 6: 'DOMINGO'}
MESES_ES = {1: 'ENERO', 2: 'FEBRERO', 3: 'MARZO', 4: 'ABRIL',
            5: 'MAYO', 6: 'JUNIO', 7: 'JULIO', 8: 'AGOSTO',
            9: 'SEPTIEMBRE', 10: 'OCTUBRE', 11: 'NOVIEMBRE', 12: 'DICIEMBRE'}


def format_date_en(d: date) -> str:
    """Formatear fecha en inglés"""
    return f"{DAYS_EN[d.weekday()]}, {MONTHS_EN[d.month]} {d.day}, {d.year}"


def format_date_es(d: date) -> str:
    """Formatear fecha en español"""
    return f"{DAYS_ES[d.weekday()]}, {d.day} DE {MESES_ES[d.month]} DE {d.year}"


async def get_market_data_from_fmp() -> dict:
    """
    Obtener datos de mercado en tiempo real desde FMP para "Before the Bell".
    
    Returns:
        Dict con datos de índices, commodities, crypto
    """
    fmp_key = os.getenv('FMP_API_KEY')
    if not fmp_key:
        logger.warning("FMP_API_KEY not found")
        return {}
    
    results = {}
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for name, symbol in MARKET_SYMBOLS.items():
                try:
                    url = f'https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={fmp_key}'
                    resp = await client.get(url)
                    data = resp.json()
                    
                    if data and len(data) > 0:
                        d = data[0]
                        results[name] = {
                            'price': d.get('price'),
                            'change_pct': d.get('changesPercentage'),
                            'change': d.get('change'),
                            'name': d.get('name', symbol)
                        }
                except Exception as e:
                    logger.warning(f"fmp_quote_error", symbol=symbol, error=str(e))
        
        logger.info("market_data_fetched", count=len(results))
        return results
        
    except Exception as e:
        logger.error("market_data_error", error=str(e))
        return {}


def format_market_data_section(market_data: dict) -> str:
    """
    Formatear los datos de mercado para la sección "Before the Bell".
    """
    if not market_data:
        return ""
    
    def fmt_pct(val):
        if val is None:
            return "N/A"
        sign = "+" if val >= 0 else ""
        return f"{sign}{val:.2f}%"
    
    def fmt_price(val, decimals=2):
        if val is None:
            return "N/A"
        if val >= 1000:
            return f"${val:,.{decimals}f}"
        return f"${val:.{decimals}f}"
    
    lines = []
    
    # US Futures/Indices
    sp = market_data.get('sp500', {})
    dow = market_data.get('dow', {})
    nas = market_data.get('nasdaq', {})
    lines.append(f"US Indices: S&P 500 {fmt_pct(sp.get('change_pct'))}, Dow {fmt_pct(dow.get('change_pct'))}, Nasdaq {fmt_pct(nas.get('change_pct'))}")
    
    # VIX
    vix = market_data.get('vix', {})
    if vix.get('price'):
        lines.append(f"VIX: {vix.get('price'):.2f} ({fmt_pct(vix.get('change_pct'))})")
    
    # Europe
    dax = market_data.get('dax', {})
    ftse = market_data.get('ftse', {})
    cac = market_data.get('cac', {})
    lines.append(f"Europe: DAX {fmt_pct(dax.get('change_pct'))}, FTSE 100 {fmt_pct(ftse.get('change_pct'))}, CAC 40 {fmt_pct(cac.get('change_pct'))}")
    
    # Asia
    nik = market_data.get('nikkei', {})
    hsi = market_data.get('hangseng', {})
    lines.append(f"Asia: Nikkei {fmt_pct(nik.get('change_pct'))}, Hang Seng {fmt_pct(hsi.get('change_pct'))}")
    
    # Dollar Index
    dxy = market_data.get('dxy', {})
    if dxy.get('price'):
        lines.append(f"Dollar Index (DXY): {dxy.get('price'):.2f} ({fmt_pct(dxy.get('change_pct'))})")
    
    # Commodities
    gold = market_data.get('gold', {})
    oil = market_data.get('oil', {})
    if gold.get('price') or oil.get('price'):
        gold_str = f"Gold: {fmt_price(gold.get('price'))}/oz ({fmt_pct(gold.get('change_pct'))})" if gold.get('price') else "Gold: N/A"
        oil_str = f"WTI Crude: {fmt_price(oil.get('price'))}/bbl ({fmt_pct(oil.get('change_pct'))})" if oil.get('price') else "WTI: N/A"
        lines.append(f"{gold_str}")
        lines.append(f"{oil_str}")
    
    # Crypto
    btc = market_data.get('bitcoin', {})
    if btc.get('price'):
        lines.append(f"Bitcoin: {fmt_price(btc.get('price'), 0)} ({fmt_pct(btc.get('change_pct'))})")
    
    return "\n".join(lines)


def clean_markdown(text: str) -> str:
    """Limpiar markdown residual del texto"""
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'^[\*\-]\s+', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    text = text.replace('\\$', '$')
    text = text.replace('\\&', '&')
    return text.strip()


async def get_grok_financial_news(report_date: date) -> Tuple[str, List[str]]:
    """
    Obtener noticias financieras usando Grok 4.1 Fast con búsqueda nativa.
    
    Returns:
        Tuple[str, List[str]]: (contenido, lista de citations)
    """
    api_key = os.getenv('GROK_API_KEY_2') or os.getenv('GROK_API_KEY')
    if not api_key:
        logger.warning("GROK_API_KEY not found, skipping Grok search")
        return "", []
    
    os.environ['XAI_API_KEY'] = api_key
    
    fecha = report_date.strftime("%B %d, %Y")
    
    prompt = f"""You are a financial news researcher for Wall Street. Today is {fecha}.

Search X.com and the web to find ALL important financial news for US stock markets TODAY.

SEARCH FOR:
1. Pre-market stock movers with ticker symbols and percentage changes
2. M&A announcements (acquirer, target, deal value in dollars)
3. Earnings reports and surprises (company, EPS actual vs expected)
4. Analyst upgrades/downgrades (bank name, ticker, price targets)
5. FDA approvals and drug news
6. CEO announcements and executive changes
7. Economic data releases (jobless claims, trade balance, etc.)
8. Defense sector news
9. Tech sector news
10. Breaking market-moving news

REQUIREMENTS:
- ONLY NYSE/NASDAQ listed US stocks
- Include specific numbers: dollar amounts, percentages, share counts
- Include executive names when mentioned
- Include analyst firm names for recommendations
- Be comprehensive - find everything relevant for today

Report all findings in organized plain text."""

    try:
        client = XAIClient(api_key=api_key)
        
        chat = client.chat.create(
            model="grok-4-1-fast",
            tools=[
                x_search(
                    allowed_x_handles=FINANCIAL_X_HANDLES,
                    from_date=datetime(report_date.year, report_date.month, report_date.day)
                ),
                web_search()
            ],
            include=["inline_citations"]
        )
        
        chat.append(user(prompt))
        
        logger.info("grok_search_starting", date=str(report_date))
        
        content = ""
        for response, chunk in chat.stream():
            if chunk.content:
                content += chunk.content
            
            # Log tool calls
            for tool_call in chunk.tool_calls:
                logger.debug("grok_tool_call", 
                           tool=tool_call.function.name,
                           args=tool_call.function.arguments[:100])
        
        citations = list(response.citations) if response.citations else []
        
        logger.info("grok_search_completed", 
                   chars=len(content), 
                   citations=len(citations))
        
        return content, citations
        
    except Exception as e:
        logger.error("grok_search_error", error=str(e))
        return "", []


async def get_gemini_financial_news(report_date: date) -> str:
    """
    Obtener noticias adicionales via Gemini + Google Search.
    """
    api_key = os.getenv('GOOGL_API_KEY') or os.getenv('GOOGL_API_KEY_V2')
    if not api_key:
        logger.warning("GOOGL_API_KEY not found, skipping Gemini search")
        return ""
    
    client = genai.Client(api_key=api_key)
    search_tool = Tool(google_search=GoogleSearch())
    
    fecha = report_date.strftime("%B %d, %Y")
    
    prompt = f"""Use Google Search to find comprehensive Wall Street financial news for TODAY ({fecha}).

Search for and report:
1. "stock market news today {fecha}" - major headlines
2. "earnings report today" - companies reporting
3. "analyst upgrade downgrade today" - rating changes
4. "premarket movers today" - stocks moving
5. "economic data {fecha}" - scheduled releases
6. "M&A deal announced" - mergers and acquisitions
7. "ex dividend today" - stocks going ex-dividend

ONLY NYSE/NASDAQ US stocks. Include all specific numbers, names, percentages."""

    try:
        logger.info("gemini_search_starting", date=str(report_date))
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={'tools': [search_tool]}
        )
        
        content = response.text if response.text else ""
        
        logger.info("gemini_search_completed", chars=len(content))
        
        return content
        
    except Exception as e:
        logger.error("gemini_search_error", error=str(e))
        return ""


async def synthesize_report(
    grok_data: str, 
    gemini_data: str, 
    citations: List[str],
    report_date: date,
    market_data: dict,
    lang: str = 'en'
) -> str:
    """
    Sintetizar el reporte final combinando todas las fuentes.
    """
    api_key = os.getenv('GOOGL_API_KEY') or os.getenv('GOOGL_API_KEY_V2')
    if not api_key:
        raise ValueError("GOOGL_API_KEY required for synthesis")
    
    client = genai.Client(api_key=api_key)
    
    fecha = format_date_en(report_date) if lang == 'en' else format_date_es(report_date)
    citations_text = "\n".join(citations[:30]) if citations else "No citations"
    
    # Formatear datos de mercado reales de FMP
    market_section = format_market_data_section(market_data) if market_data else "Market data not available"
    
    lang_instruction = "Write ALL content in ENGLISH." if lang == 'en' else "Write ALL content in SPANISH (Español)."
    
    prompt = f"""You are a senior financial news editor at Reuters/LSEG.

Create a comprehensive, professional Morning News Call from this research:

=== GROK X.COM + WEB RESEARCH ===
{grok_data}

=== GEMINI GOOGLE RESEARCH ===
{gemini_data}

=== SOURCE CITATIONS ===
{citations_text}

=== REAL-TIME MARKET DATA (USE THIS EXACTLY FOR "BEFORE THE BELL") ===
{market_section}

DATE: {fecha}

CRITICAL RULES:
1. ONLY NYSE/NASDAQ US companies - NO stocks from India, UK, Europe, Asia (except as market context)
2. Use ONLY factual information from the research - DO NOT invent any data
3. Include specific: dollar amounts ($X.XX), percentages (X.X%), share counts
4. Include executive names (CEO, CFO names)
5. Include analyst firm names (Goldman Sachs, JPMorgan, etc.)
6. Plain text ONLY - absolutely NO markdown symbols (**, *, #, -)
7. Each STOCKS TO WATCH entry should be a detailed paragraph
8. {lang_instruction}
9. For "BEFORE THE BELL" section, USE THE EXACT MARKET DATA provided above - do not invent different numbers

START DIRECTLY with ==== (no introduction)

FORMAT:

================================================================================

                              TRADEUL.COM
                           MORNING NEWS CALL

================================================================================

USA EDITION

{fecha}


TOP NEWS

(Write 6-8 detailed news paragraphs. Each should be 4-5 sentences with specific facts, figures, executive names, and market impact. Cover: major market moves, Fed/policy, big deals, sector themes)


BEFORE THE BELL

(COPY THE EXACT MARKET DATA from above - do not modify the numbers)


STOCKS TO WATCH

(Write 15-20 detailed stock entries. Each entry should be:
Company Name (TICKER): A 3-4 sentence paragraph explaining the news in detail, including executive names if mentioned, specific dollar amounts, percentage changes, and market reaction.)


SMALL CAPS MOVERS

(List 6-10 small cap stocks:
Company Name (TICKER): +/-XX.X% - Brief catalyst explanation)


ANALYSIS

(Write 2-3 paragraphs of professional market analysis. Discuss key themes, risks, sector rotations, and what traders should watch today.)


ANALYSTS' RECOMMENDATIONS

(List 8-12 analyst actions in this format:
Company Name (TICKER): Bank/Firm Name - Upgrade/Downgrade/Initiate - PT: $XX -> $XX - Reason)


ECONOMIC EVENTS (All timings in U.S. Eastern Time)

(List ALL scheduled economic releases:
HH:MM AM/PM: Event Name; Expected: X.XX; Prior: X.XX)


COMPANIES REPORTING RESULTS

(List ALL companies reporting earnings today:
Company Name (TICKER): EPS Est: $X.XX; Rev Est: $X.XXB; Time: BMO/AMC)


EX-DIVIDENDS

(List stocks going ex-dividend today:
Company Name (TICKER): $X.XX per share)


================================================================================"""

    try:
        logger.info("synthesis_starting", lang=lang)
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        
        report = response.text.strip() if response.text else ""
        report = clean_markdown(report)
        
        logger.info("synthesis_completed", lang=lang, chars=len(report))
        
        return report
        
    except Exception as e:
        logger.error("synthesis_error", error=str(e), lang=lang)
        return ""


class MorningNewsCallGenerator:
    """
    Generador del Morning News Call diario.
    
    Usa Grok 4.1 Fast + Gemini 2.5 Flash para obtener noticias en tiempo real
    y generar un reporte profesional estilo LSEG/Reuters.
    """
    
    async def generate(self, report_date: Optional[date] = None, lang: str = 'en') -> Dict:
        """
        Generar el Morning News Call.
        
        Args:
            report_date: Fecha del reporte (default: hoy)
            lang: Idioma del reporte ('es' o 'en')
        
        Returns:
            Dict con el reporte y metadata
        """
        if report_date is None:
            report_date = datetime.now(NY_TZ).date()
        
        logger.info("generating_morning_news_call", date=str(report_date), lang=lang)
        
        start_time = datetime.now()
        
        try:
            # Fase 1: Recopilar datos en paralelo
            grok_task = get_grok_financial_news(report_date)
            gemini_task = get_gemini_financial_news(report_date)
            market_task = get_market_data_from_fmp()
            
            (grok_data, citations), gemini_data, market_data = await asyncio.gather(
                grok_task, gemini_task, market_task
            )
            
            total_research = len(grok_data) + len(gemini_data)
            logger.info("research_collected", 
                       grok_chars=len(grok_data),
                       gemini_chars=len(gemini_data),
                       citations=len(citations),
                       market_symbols=len(market_data))
            
            # Fase 2: Sintetizar reporte
            report = await synthesize_report(
                grok_data, gemini_data, citations, report_date, market_data, lang
            )
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            fecha_fmt = format_date_en(report_date) if lang == 'en' else format_date_es(report_date)
            
            logger.info(
                "morning_news_call_generated",
                date=str(report_date),
                lang=lang,
                length=len(report),
                duration_seconds=round(elapsed, 2)
            )
            
            return {
                "success": True,
                "date": report_date.isoformat(),
                "date_formatted": fecha_fmt,
                "report": report,
                "generated_at": datetime.now(NY_TZ).isoformat(),
                "generation_time_seconds": round(elapsed, 2),
                "lang": lang,
                "sources": {
                    "grok_chars": len(grok_data),
                    "gemini_chars": len(gemini_data),
                    "citations": len(citations)
                }
            }
            
        except Exception as e:
            logger.error("morning_news_call_error", error=str(e), lang=lang)
            return {
                "success": False,
                "date": report_date.isoformat(),
                "error": str(e),
                "generated_at": datetime.now(NY_TZ).isoformat(),
                "lang": lang
            }
    
    async def translate_to_spanish(self, report_en: str, report_date: date) -> str:
        """
        Traducir el reporte de inglés a español.
        """
        api_key = os.getenv('GOOGL_API_KEY') or os.getenv('GOOGL_API_KEY_V2')
        if not api_key:
            return report_en
        
        client = genai.Client(api_key=api_key)
        
        fecha_es = format_date_es(report_date)
        
        translate_prompt = f'''Translate this financial report from English to Spanish.

RULES:
1. Keep the EXACT same format and structure
2. Keep section headers in ENGLISH (TOP NEWS, BEFORE THE BELL, STOCKS TO WATCH, etc.)
3. Translate only the content paragraphs to Spanish
4. Keep ALL ticker symbols (like LMT, NVDA, AAPL) exactly as they are
5. Keep all numbers, percentages, and dollar amounts exactly as they are
6. Keep executive names exactly as they are
7. Replace the date line with: {fecha_es}
8. Keep "USA EDITION" as is
9. Do NOT add any introduction - output ONLY the translated report starting with ====

Report to translate:

{report_en}'''

        try:
            logger.info("translating_to_spanish", date=str(report_date))
            
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=translate_prompt
            )
            
            report_es = response.text.strip() if response.text else report_en
            
            # Asegurar que empiece con ====
            header_match = re.search(r'={10,}', report_es)
            if header_match:
                report_es = report_es[header_match.start():]
            
            logger.info("translation_completed", chars=len(report_es))
            
            return report_es
            
        except Exception as e:
            logger.error("translation_error", error=str(e))
            return report_en
    
    async def generate_both_languages(self, report_date: Optional[date] = None) -> Dict:
        """
        Generar el reporte en inglés y traducirlo a español.
        
        Returns:
            Dict con ambas versiones del reporte
        """
        if report_date is None:
            report_date = datetime.now(NY_TZ).date()
        
        logger.info("generating_bilingual_morning_news", date=str(report_date))
        
        start_time = datetime.now()
        
        try:
            # Fase 1: Recopilar datos en paralelo
            grok_task = get_grok_financial_news(report_date)
            gemini_task = get_gemini_financial_news(report_date)
            market_task = get_market_data_from_fmp()
            
            (grok_data, citations), gemini_data, market_data = await asyncio.gather(
                grok_task, gemini_task, market_task
            )
            
            logger.info("data_collection_complete", 
                       grok_chars=len(grok_data),
                       gemini_chars=len(gemini_data),
                       market_symbols=len(market_data))
            
            # Fase 2: Generar reporte en inglés
            report_en = await synthesize_report(
                grok_data, gemini_data, citations, report_date, market_data, 'en'
            )
            
            # Fase 3: Traducir a español
            report_es = await self.translate_to_spanish(report_en, report_date)
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            generated_at = datetime.now(NY_TZ).isoformat()
        
            result_en = {
                "success": True,
                "date": report_date.isoformat(),
                    "date_formatted": format_date_en(report_date),
                "report": report_en,
                    "generated_at": generated_at,
                    "generation_time_seconds": round(elapsed, 2),
                    "lang": "en",
                    "sources": {
                        "grok_chars": len(grok_data),
                        "gemini_chars": len(gemini_data),
                        "citations": len(citations)
                    }
                }
                
            result_es = {
                    "success": True,
                    "date": report_date.isoformat(),
                    "date_formatted": format_date_es(report_date),
                    "report": report_es,
                    "generated_at": generated_at,
                    "generation_time_seconds": round(elapsed, 2),
                    "lang": "es",
                    "sources": {
                        "grok_chars": len(grok_data),
                        "gemini_chars": len(gemini_data),
                        "citations": len(citations)
                    }
                }
                
            logger.info(
                    "bilingual_morning_news_generated",
                    date=str(report_date),
                    en_length=len(report_en),
                    es_length=len(report_es),
                    duration_seconds=round(elapsed, 2)
                )
            
            return {
                    "en": result_en,
                    "es": result_es
                }
            
        except Exception as e:
            logger.error("bilingual_morning_news_error", error=str(e))
            return {
                "en": {"success": False, "error": str(e)},
                "es": {"success": False, "error": str(e)}
        }


async def generate_morning_news_call(report_date: Optional[date] = None) -> Dict:
    """
    Función helper para generar el Morning News Call en ambos idiomas.
    
    Args:
        report_date: Fecha del reporte (default: hoy)
    
    Returns:
        Dict con ambas versiones del reporte (es y en)
    """
    generator = MorningNewsCallGenerator()
    return await generator.generate_both_languages(report_date)


async def generate_bilingual_morning_news_call(report_date: Optional[date] = None) -> Dict:
    """
    Alias para generate_morning_news_call (compatibilidad).
    """
    return await generate_morning_news_call(report_date)
