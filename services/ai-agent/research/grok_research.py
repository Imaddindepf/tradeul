"""
Grok Research Module
====================
Uses Grok 4.1 Fast with X.com and Web search to research tickers.
Combines multiple sources: X.com (breaking news), Benzinga, and web search.
"""

import os
import re
import asyncio
import httpx
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional
import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# RESPONSE SANITIZATION - Remove internal system information from output
# =============================================================================

# Patterns that should NEVER appear in user-facing responses
INTERNAL_PATTERNS_TO_REMOVE = [
    # X.com account names that reveal our search strategy
    r'@?DeItaOne',
    r'@?FirstSquawk',
    r'@?LiveSquawk',
    r'@?Newsquawk',
    r'@?unusual_whales',
    r'@?CheddarFlow',
    r'@?theoptionsflow',
    r'@?StockTitan',
    r'@?InvestorsLive',
    r'@?smallcapvoice',
    r'@?zerohedge',
    r'@?NickTimiraos',
    r'@?ForexLive',
    r'@?financialjuice',
    r'@?WatcherGuru',
    r'@?EarningsWhispers',
    # Phrases that reveal internal workings
    r'trusted accounts?',
    r'prioritize these accounts?',
    r'search(?:es|ed)?\s+returned\s+unrelated',
    r'no\s+(?:significant\s+)?(?:notable\s+)?mentions?\s+(?:of\s+)?\$?\w+\s+(?:stock\s+)?from\s+traders',
    r'(?:older|old)\s+threads?',
    r'e\.?g\.?,?\s*@\w+',
    r'Welsh\s+football',
    r'Ghana.{0,20}GCB',
    r'non-US\s+stocks?',
    r'unrelated\s+posts?',
    r'acronym\s+celebrations?',
]

# Compiled patterns for efficiency
_SANITIZE_PATTERNS = None


def _get_sanitize_patterns():
    """Lazy compile sanitization patterns."""
    global _SANITIZE_PATTERNS
    if _SANITIZE_PATTERNS is None:
        _SANITIZE_PATTERNS = [
            re.compile(pattern, re.IGNORECASE) for pattern in INTERNAL_PATTERNS_TO_REMOVE
        ]
    return _SANITIZE_PATTERNS


def sanitize_research_response(content: str) -> str:
    """
    Remove internal system information from research response.
    This prevents exposing our search strategy, account lists, and debug info.
    """
    if not content:
        return content
    
    sanitized = content
    
    # Remove patterns that expose internal workings
    for pattern in _get_sanitize_patterns():
        sanitized = pattern.sub('', sanitized)
    
    # Clean up sentences that became empty or nonsensical after removal
    # e.g., "No mentions from  ,  , " -> clean
    sanitized = re.sub(r'\(\s*e\.?g\.?,?\s*,?\s*\)', '', sanitized)
    sanitized = re.sub(r'\(\s*,?\s*\)', '', sanitized)
    sanitized = re.sub(r',\s*,', ',', sanitized)
    sanitized = re.sub(r',\s*\)', ')', sanitized)
    sanitized = re.sub(r'\(\s*,', '(', sanitized)
    
    # Clean up multiple spaces and empty lines
    sanitized = re.sub(r' {2,}', ' ', sanitized)
    sanitized = re.sub(r'\n{3,}', '\n\n', sanitized)
    
    # Remove sentences that are now empty or just "from" or similar
    sanitized = re.sub(r'from\s*[,\.\s]*(?:\.|$)', '', sanitized, flags=re.IGNORECASE)
    
    # Fix broken markdown (** without closing)
    # Count ** and ensure they're paired
    sanitized = fix_markdown_formatting(sanitized)
    
    return sanitized.strip()


def fix_markdown_formatting(content: str) -> str:
    """Fix common markdown formatting issues."""
    if not content:
        return content
    
    fixed = content
    
    # ==========================================================================
    # 1. REMOVE INLINE CITATION URLS - Keep only [1], [2], etc.
    # The frontend already has buttons that open the URLs
    # ==========================================================================
    
    # Remove [ 1](url) or [ [1]](url) -> [1]
    fixed = re.sub(r'\[\s*\[?(\d+)\]?\]\([^)]+\)', r'[\1]', fixed)
    
    # ==========================================================================
    # 2. FIX HEADERS - Ensure **Header** format is correct
    # Process line by line for reliability
    # ==========================================================================
    
    lines = fixed.split('\n')
    result_lines = []
    for line in lines:
        stripped = line.rstrip()
        # Check if line starts with ** and doesn't end with **
        if stripped.startswith('**') and not stripped.endswith('**') and len(stripped) > 2:
            header_text = stripped[2:]
            # Only fix if it looks like a header (letters and spaces only)
            if header_text and re.match(r'^[A-Za-z][A-Za-z ]*$', header_text):
                line = f'**{header_text}**'
        result_lines.append(line)
    fixed = '\n'.join(result_lines)
    
    # ==========================================================================
    # 3. CLEAN UP FORMATTING
    # ==========================================================================
    
    # Fix :**: -> :**
    fixed = re.sub(r':\*\*:', ':**', fixed)
    
    # Fix **** -> **
    fixed = re.sub(r'\*{4,}', '**', fixed)
    
    # Fix citation numbers stuck to prices: $13.021 -> $13.02 [1]
    fixed = re.sub(r'(\$\d+\.\d{2})(\d)(\s|$)', r'\1 [\2]\3', fixed)
    
    # Ensure spacing before citations: text[1] -> text [1]
    fixed = re.sub(r'([a-zA-Z])(\[\d+\])', r'\1 \2', fixed)
    
    # Clean up multiple spaces
    fixed = re.sub(r' {2,}', ' ', fixed)
    
    # Clean up space before punctuation
    fixed = re.sub(r' ([.,;:])', r'\1', fixed)
    
    return fixed


def detect_language(text: str) -> str:
    """
    Simple language detection based on common words.
    Returns 'es' for Spanish, 'en' for English.
    """
    if not text:
        return 'en'
    
    text_lower = text.lower()
    
    # Spanish indicators
    spanish_words = [
        'por qué', 'porque', 'cómo', 'qué', 'cuál', 'dónde', 'cuándo',
        'está', 'están', 'tiene', 'tienen', 'hace', 'hacen',
        'bolsa', 'acciones', 'acción', 'mercado', 'caen', 'sube', 'baja',
        'precio', 'análisis', 'noticias', 'hoy', 'ayer', 'mañana'
    ]
    
    spanish_count = sum(1 for word in spanish_words if word in text_lower)
    
    return 'es' if spanish_count >= 2 else 'en'


def get_response_language_instruction(query: str) -> str:
    """Get instruction for response language based on query language."""
    lang = detect_language(query)
    
    if lang == 'es':
        return "\n\n⚠️ IMPORTANTE: Responde COMPLETAMENTE en ESPAÑOL. Toda la respuesta debe estar en español."
    return ""


# =============================================================================
# RESEARCH FUNCTIONS
# =============================================================================

async def research_ticker(
    ticker: str,
    query: str = None,
    include_technicals: bool = True,
    include_fundamentals: bool = True,
    max_retries: int = 3
) -> Dict:
    """
    Research a specific ticker using Grok with X.com and web search.
    Includes automatic retry on connection errors.
    """
    api_key = os.getenv('GROK_API_KEY_2') or os.getenv('GROK_API_KEY')
    if not api_key:
        logger.warning("GROK_API_KEY not found")
        return {
            "success": False,
            "error": "Grok API key not configured",
            "content": "",
            "citations": []
        }
    
    os.environ['XAI_API_KEY'] = api_key
    last_error = None
    
    # Detect query language for response
    lang_instruction = get_response_language_instruction(query or "")
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                wait_time = 2 ** attempt
                logger.info("grok_research_retry", ticker=ticker, attempt=attempt + 1, wait_seconds=wait_time)
                await asyncio.sleep(wait_time)
            
            from xai_sdk import Client
            from xai_sdk.chat import user
            from xai_sdk.tools import x_search, web_search
            
            client = Client()
            today = datetime.now().strftime("%B %d, %Y")
            
            # Build clean prompt - NO internal account names or search strategies
            prompt_parts = [
                f"You are a senior financial analyst. Today is {today}.",
                f"\n\n## TASK: Research ${ticker}",
                f"\nUser question: {query}" if query else "",
                
                "\n\n## RESEARCH REQUIREMENTS:",
                "\n1. Search X.com (Twitter) for breaking news and trader sentiment",
                "\n2. Search financial news sites (Bloomberg, Reuters, WSJ, CNBC) for verified news",
                "\n3. Find key metrics: price, market cap, P/E, volume, recent earnings",
                "\n4. Identify the CATALYST - why is it moving?",
                
                "\n\n## OUTPUT FORMAT:",
                "\n",
                "\n**Summary**",
                "\n[2-3 sentences directly answering the user's question]",
                "\n",
                "\n**Breaking News**",
                "\n[Most recent developments in the last 24-48 hours. If no significant news, state 'No major news in the last 48 hours.' - do NOT mention search details or which accounts you checked]",
                "\n",
                "\n**Social Sentiment**",
                "\n[Overall trader sentiment: bullish/bearish/neutral with brief explanation. If low activity, say 'Limited social activity' - do NOT list accounts checked]",
                "\n",
                "\n**Key Metrics**",
                "\n- Current Price: $X.XX (change%)",
                "\n- Market Cap: $X.XXB",
                "\n- P/E Ratio: X.XX",
                "\n- Volume: X.XXM (vs avg X.XXM)",
                "\n- 52-Week Range: $X.XX - $X.XX",
                "\n",
                "\n**Analysis**",
                "\n[Your professional assessment of the situation]",
            ]
            
            if include_technicals:
                prompt_parts.append("\n\n**Technical View**\n[Key support/resistance levels, trend analysis]")
            
            if include_fundamentals:
                prompt_parts.append("\n\n**Fundamental View**\n[Growth outlook, risks, competitive position]")
            
            prompt_parts.extend([
                "\n\n## CRITICAL RULES:",
                "\n- Cite sources with inline numbers like [1], [2]",
                "\n- Use proper markdown: **bold** for headers",
                "\n- Do NOT mention which accounts or sources you searched",
                "\n- Do NOT say 'searches returned unrelated results'",
                "\n- If you find nothing, just say 'No significant news found'",
                "\n- Be professional and concise",
                lang_instruction
            ])
            
            prompt = "".join(prompt_parts)
            
            chat = client.chat.create(
                model="grok-4-1-fast",
                tools=[
                    x_search(from_date=datetime.now().replace(day=1)),
                    web_search()
                ],
                include=["inline_citations", "verbose_streaming"]
            )
            
            chat.append(user(prompt))
            
            logger.info("grok_ticker_research_starting", ticker=ticker, query=query[:50] if query else None)
            
            content = ""
            tool_calls = []
            
            for response, chunk in chat.stream():
                if chunk.content:
                    content += chunk.content
                
                for tc in chunk.tool_calls:
                    tool_calls.append({
                        "tool": tc.function.name,
                        "args": tc.function.arguments[:100] if tc.function.arguments else ""
                    })
                    logger.debug("grok_tool_call", tool=tc.function.name)
            
            # CRITICAL: Sanitize response before returning
            content = sanitize_research_response(content)
            
            all_citations = list(response.citations) if response.citations else []
            
            inline_citations = []
            if hasattr(response, 'inline_citations') and response.inline_citations:
                for cite in response.inline_citations:
                    cite_data = {"id": cite.id}
                    if hasattr(cite, 'web_citation') and cite.HasField("web_citation"):
                        cite_data["url"] = cite.web_citation.url
                        cite_data["type"] = "web"
                    elif hasattr(cite, 'x_citation') and cite.HasField("x_citation"):
                        cite_data["url"] = f"https://x.com/i/status/{cite.x_citation.post_id}" if hasattr(cite.x_citation, 'post_id') else ""
                        cite_data["type"] = "x"
                    inline_citations.append(cite_data)
            
            citations = all_citations if all_citations else [c.get("url", "") for c in inline_citations]
            
            logger.info("grok_ticker_research_completed",
                       ticker=ticker,
                       chars=len(content),
                       citations=len(citations),
                       inline_citations=len(inline_citations),
                       tools_used=len(tool_calls),
                       attempt=attempt + 1)
            
            return {
                "success": True,
                "ticker": ticker,
                "content": content,
                "citations": citations,
                "inline_citations": inline_citations,
                "tool_calls": tool_calls,
                "timestamp": datetime.now().isoformat()
            }
            
        except ImportError:
            logger.error("xai_sdk_not_installed")
            return {
                "success": False,
                "error": "xai-sdk not installed. Run: pip install xai-sdk",
                "content": "",
                "citations": []
            }
        except Exception as e:
            last_error = str(e)
            logger.warning("grok_ticker_research_attempt_failed",
                          ticker=ticker,
                          attempt=attempt + 1,
                          max_retries=max_retries,
                          error=last_error[:200])
            continue
    
    logger.error("grok_ticker_research_failed_all_retries",
                ticker=ticker,
                attempts=max_retries,
                last_error=last_error[:200] if last_error else "Unknown")
    
    return {
        "success": False,
        "error": f"Failed after {max_retries} attempts: {last_error}",
        "content": "",
        "citations": []
    }


async def search_financial_news(
    topic: str,
    days_back: int = 7
) -> Dict:
    """Search for general financial news on a topic using Grok."""
    api_key = os.getenv('GROK_API_KEY_2') or os.getenv('GROK_API_KEY')
    if not api_key:
        return {"success": False, "error": "Grok API key not configured"}
    
    os.environ['XAI_API_KEY'] = api_key
    
    # Detect language
    lang_instruction = get_response_language_instruction(topic)
    
    try:
        from xai_sdk import Client
        from xai_sdk.chat import user
        from xai_sdk.tools import x_search, web_search
        
        client = Client()
        today = datetime.now()
        
        prompt = f"""You are a financial news researcher. Today is {today.strftime("%B %d, %Y")}.

Search for the latest news about: {topic}

Provide a clean, professional response:

**Headlines**
[Top 5 most important recent news items with dates]

**Market Impact**
[How this affects markets/stocks]

**Sentiment**
[Overall market sentiment - bullish/bearish/neutral]

**Key Takeaways**
- [Point 1]
- [Point 2]
- [Point 3]

Rules:
- Cite sources with [1], [2], etc.
- Do NOT mention which accounts or sources you searched
- Be professional and factual
{lang_instruction}"""

        from_date = today.replace(day=max(1, today.day - days_back))
        
        chat = client.chat.create(
            model="grok-4-1-fast",
            tools=[
                x_search(from_date=from_date),
                web_search()
            ],
            include=["inline_citations"]
        )
        
        chat.append(user(prompt))
        
        content = ""
        for response, chunk in chat.stream():
            if chunk.content:
                content += chunk.content
        
        # Sanitize response
        content = sanitize_research_response(content)
        
        citations = list(response.citations) if response.citations else []
        
        return {
            "success": True,
            "topic": topic,
            "content": content,
            "citations": citations,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error("grok_news_search_error", topic=topic, error=str(e))
        return {"success": False, "error": str(e)}


async def fetch_benzinga_news(ticker: str, limit: int = 10) -> List[Dict]:
    """
    Fetch recent news from our Benzinga service.
    Returns list of news articles with title, summary, url, published_at.
    """
    def clean_html(html: str) -> str:
        """Remove HTML tags and clean up text."""
        if not html:
            return ""
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    async def extract_ticker_info(full_text: str, target_ticker: str) -> str:
        """Use Gemini Flash to extract only info about the target ticker."""
        try:
            from google import genai
            from google.genai import types
            
            api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GEMINI_TRADEUL_AGENT')
            if not api_key:
                logger.warning("no_gemini_api_key_for_extraction")
                return full_text[:500]
            
            client = genai.Client(api_key=api_key)
            
            prompt = f"""Extract ONLY the information about ${target_ticker} from this news article.
If the article mentions multiple tickers, return ONLY the part about ${target_ticker}.
Be concise but include all relevant details (price movement, %, reason if mentioned).

Article:
{full_text[:2000]}

Response format: Just the extracted info about ${target_ticker}, nothing else. If no specific info found, say "No specific details for ${target_ticker}"."""

            response = await client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=300)
            )
            
            return (response.text or "").strip() or full_text[:300]
        except Exception as e:
            logger.warning("llm_extraction_failed", error=str(e))
            return full_text[:300]
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"http://benzinga-news:8015/api/v1/news/ticker/{ticker}",
                params={"limit": limit}
            )
            
            if response.status_code == 200:
                data = response.json()
                articles = data.get("results", [])
                
                formatted = []
                for art in articles:
                    body = art.get("body", "")
                    full_text = clean_html(body)
                    
                    tickers_in_article = art.get("tickers", [])
                    is_multi_ticker = len(tickers_in_article) > 3
                    
                    if is_multi_ticker and full_text:
                        summary = await extract_ticker_info(full_text, ticker)
                    else:
                        teaser = art.get("teaser") or ""
                        summary = teaser.strip() if isinstance(teaser, str) else ""
                        if not summary or summary == " ":
                            summary = full_text[:500]
                    
                    formatted.append({
                        "title": art.get("title", ""),
                        "summary": summary,
                        "url": art.get("article_url") or art.get("url", ""),
                        "published": art.get("published_utc") or art.get("published", ""),
                        "source": "Benzinga"
                    })
                
                logger.info("benzinga_news_fetched", ticker=ticker, count=len(formatted))
                return formatted
            else:
                logger.warning("benzinga_news_failed", ticker=ticker, status=response.status_code)
                return []
                
    except Exception as e:
        logger.warning("benzinga_news_error", ticker=ticker, error=str(e))
        return []


async def research_ticker_combined(
    ticker: str,
    query: str = None,
    include_technicals: bool = True,
    include_fundamentals: bool = True
) -> Dict:
    """
    Combined research using both Grok (X.com + web) and Benzinga news.
    Runs both in parallel for faster results.
    """
    grok_task = research_ticker(
        ticker=ticker,
        query=query,
        include_technicals=include_technicals,
        include_fundamentals=include_fundamentals
    )
    benzinga_task = fetch_benzinga_news(ticker, limit=10)
    
    grok_result, benzinga_news = await asyncio.gather(grok_task, benzinga_task)
    
    if benzinga_news:
        grok_result["benzinga_news"] = benzinga_news
        
        benzinga_section = "\n\n---\n**Recent News:**\n"
        for news in benzinga_news[:5]:
            title = news.get("title", "")
            summary = news.get("summary", "")[:150]
            published = news.get("published", "")
            if title:
                benzinga_section += f"\n• **{title}**"
                if summary:
                    benzinga_section += f"\n  {summary}..."
                if published:
                    benzinga_section += f" ({published[:10]})"
        
        content = grok_result.get("content", "")
        if "Social Sentiment" in content or "Sentiment" in content:
            parts = content.split("Key Metrics", 1)
            if len(parts) == 2:
                content = parts[0] + benzinga_section + "\n\n**Key Metrics**" + parts[1]
            else:
                content = content + benzinga_section
        else:
            content = content + benzinga_section
        
        grok_result["content"] = content
        
        existing_citations = grok_result.get("citations", [])
        for news in benzinga_news:
            if news.get("url") and news["url"] not in existing_citations:
                existing_citations.append(news["url"])
        grok_result["citations"] = existing_citations
    
    return grok_result


def format_research_for_display(research: Dict) -> str:
    """Format research results for display in the chat."""
    if not research.get("success"):
        return f"Research failed: {research.get('error', 'Unknown error')}"
    
    output = []
    content = research.get("content", "")
    
    # Final sanitization pass
    content = sanitize_research_response(content)
    output.append(content)
    
    benzinga = research.get("benzinga_news", [])
    if benzinga:
        output.append("\n\n---\n**Additional News:**")
        for news in benzinga[:5]:
            title = news.get("title", "")
            if title:
                output.append(f"\n• {title}")
    
    citations = research.get("citations", [])
    if citations:
        output.append("\n\n---\n**Sources:**")
        for i, cite in enumerate(citations[:15], 1):
            output.append(f"\n[{i}] {cite}")
    
    return "".join(output)
