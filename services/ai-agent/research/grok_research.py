"""
Grok Research Module
====================
Uses Grok 4.1 Fast with X.com and Web search to research tickers.
Combines multiple sources: X.com (breaking news), Benzinga, and web search.
"""

import os
import asyncio
import httpx
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional
import structlog

logger = structlog.get_logger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# X.COM HANDLES - BREAKING NEWS ACCOUNTS (Verified by Grok)
# Focus: SPEED & NEWS - Not analysts or investors
# Source: Grok research on fastest financial news accounts
# ══════════════════════════════════════════════════════════════════════════════

FINANCIAL_X_HANDLES = [
    # ═══════════════════════════════════════════════════════════════════════════
    # 🚨 ULTRA-FAST BREAKING NEWS (These break news in SECONDS)
    # ═══════════════════════════════════════════════════════════════════════════
    "DeItaOne",           # #1 FASTEST - Headlines before anyone
    "FirstSquawk",        # Breaking market news - ESSENTIAL
    "LiveSquawk",         # Live breaking headlines
    "Newsquawk",          # Real-time market news
    "financialjuice",     # Fast financial headlines
    "StockMKTNewz",       # Stock market news aggregator
    "thestalwart",        # Joe Weisenthal - Bloomberg fast news
    "MarioNawfal",        # Breaking news aggregator
    "WatcherGuru",        # Crypto + stocks breaking
    "TreeNewsFeed",       # Breaking news feed
    "Barchart",           # Real-time market data & news
    "RanSquawk",          # Market news squawk
    "SquawkCNBC",         # CNBC Squawk Box
    "disclosetv",         # Breaking news
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 🎯 SMALL CAP & PENNY STOCK NEWS (SEC filings, PRs, catalysts)
    # ═══════════════════════════════════════════════════════════════════════════
    "InvestorsLive",      # Small cap news & alerts
    "Lycanbull",          # Small cap specialist
    "smallcapvoice",      # Small cap news
    "OTCInsider",         # OTC market news
    "MicroCapDaily",      # Microcap daily news
    "smallcapscan",       # Small cap scanner news
    "otcfinder",          # OTC stock finder
    "ValueTheMarkets",    # Small cap value news
    "SmallCapAlts",       # Small cap alternatives
    "otcquick",           # OTC quick news
    "Banana3Stocks",      # Small cap alerts
    "PennyStockGuru",     # Penny stock news
    "pennystockla",       # Penny stock LA
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 🌍 FED / MACRO / ECONOMIC DATA (Fed decisions, CPI, jobs)
    # ═══════════════════════════════════════════════════════════════════════════
    "ForexLive",          # Forex & macro news - FAST
    "MacroMicroMe",       # Macro economic data
    "truflation",         # Real-time inflation data
    "ADMacroInsights",    # Macro insights
    "StLouisFed",         # St. Louis Fed (FRED data)
    "economics",          # Economics news
    "zerohedge",          # Alternative macro news - FAST
    "NickTimiraos",       # WSJ Fed reporter - ESSENTIAL
    "FedGuy12",           # Fed analysis
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 📈 OPTIONS FLOW & UNUSUAL ACTIVITY (Whale alerts)
    # ═══════════════════════════════════════════════════════════════════════════
    "unusual_whales",     # #1 Options flow tracker
    "theoptionsflow",     # Options flow alerts
    "WhaleStream",        # Whale activity
    "OptionsFlowLLC",     # Options flow LLC
    "BullflowIO",         # Bullflow options
    "CheddarFlow",        # Cheddar flow alerts
    "BlackBoxStocks",     # Dark pool & options
    "OptionsFlowBoss",    # Options flow boss
    "dreamoptions",       # Options alerts
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 📊 EARNINGS & SEC FILINGS (8-K, 10-Q, earnings releases)
    # ═══════════════════════════════════════════════════════════════════════════
    "EarningsWhispers",   # Earnings calendar & surprises
    "StockTitan",         # PR wire & SEC filings - USER REQUESTED
    "marketalertsz",      # Market alerts
    "Tijori1",            # SEC filings tracker
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 📰 MAJOR OUTLETS (Credible, fast news)
    # ═══════════════════════════════════════════════════════════════════════════
    "Bloomberg",          # Bloomberg main
    "BloombergTV",        # Bloomberg TV
    "business",           # Bloomberg Business
    "WSJmarkets",         # WSJ Markets (faster than main)
    "WSJ",                # Wall Street Journal
    "Reuters",            # Reuters main
    "ReutersBiz",         # Reuters Business
    "FT",                 # Financial Times
    "CNBC",               # CNBC main
    "CNBCFastMoney",      # CNBC Fast Money
    "MarketWatch",        # MarketWatch
    "YahooFinance",       # Yahoo Finance
    "Benzinga",           # Benzinga - FAST news
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 🏛️ OFFICIAL SOURCES (Primary data)
    # ═══════════════════════════════════════════════════════════════════════════
    "SECGov",             # SEC official
    "federalreserve",     # Federal Reserve
    "NewYorkFed",         # NY Fed
    "USTreasury",         # US Treasury
    "WhiteHouse",         # White House
]

# Additional sources to search via web (Bloomberg, CNBC, FT, Yahoo, Reddit)
WEB_PRIORITY_SOURCES = [
    "bloomberg.com",
    "cnbc.com",
    "ft.com",           # Financial Times
    "yahoo.com/finance",
    "reddit.com/r/wallstreetbets",
    "reddit.com/r/stocks",
    "seekingalpha.com",
    "benzinga.com"
]


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
    
    Args:
        ticker: Stock ticker symbol (e.g., 'RDDT', 'AAPL')
        query: Optional specific query about the ticker
        include_technicals: Whether to include technical analysis request
        include_fundamentals: Whether to include fundamental data request
        max_retries: Maximum number of retry attempts on failure
    
    Returns:
        Dict with research results, citations, and analysis
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
    
    for attempt in range(max_retries):
        try:
            # Wait before retry (exponential backoff)
            if attempt > 0:
                wait_time = 2 ** attempt  # 2, 4, 8 seconds
                logger.info("grok_research_retry", ticker=ticker, attempt=attempt + 1, wait_seconds=wait_time)
                await asyncio.sleep(wait_time)
            
            from xai_sdk import Client
            from xai_sdk.chat import user
            from xai_sdk.tools import x_search, web_search
            
            client = Client()
            today = datetime.now().strftime("%B %d, %Y")
            
            # Build the research prompt - PRIORITIZE X.COM FOR BREAKING NEWS
            prompt_parts = [
                f"You are a senior financial analyst specializing in real-time market research. Today is {today}.",
                f"\n\n## TASK: Research ${ticker} comprehensively",
                f"\nUser question: {query}" if query else "",
                
                "\n\n## SEARCH PRIORITY (follow this order):",
                "\n1. **X.COM FIRST** - Search X/Twitter for the LATEST breaking news, analyst opinions, and sentiment",
                "\n2. **Financial News** - Bloomberg, WSJ, Reuters, FT, CNBC for verified news",
                "\n3. **Reddit** - Check r/wallstreetbets and r/stocks for retail sentiment",
                "\n4. **Yahoo Finance** - For quick metrics and earnings data",
                
                "\n\n## REQUIRED RESEARCH:",
                "\n1. **Breaking News** - What happened TODAY or in the last 24-48 hours? (prioritize X.com sources)",
                "\n2. **Social Sentiment** - What are traders saying on X? Bullish/bearish? Any notable accounts?",
                "\n3. **Catalyst Analysis** - WHY is it moving? Earnings? News? Sector rotation?",
                "\n4. **Key Metrics** - Price, market cap, P/E, recent earnings beat/miss",
            ]
            
            if include_technicals:
                prompt_parts.append("\n5. **Technical View** - Key levels, trend, volume analysis")
            
            if include_fundamentals:
                prompt_parts.append("\n6. **Fundamental View** - Growth, risks, competitive position")
            
            prompt_parts.extend([
                "\n\n## OUTPUT FORMAT:",
                "\n**TLDR**: 2-3 sentences answering the user's question directly",
                "\n\n**Breaking News**: Most recent developments with DATES and SOURCES",
                "\n\n**X.com Sentiment**: What financial Twitter is saying (quote specific accounts if notable)",
                "\n\n**Key Numbers**: Market cap, P/E, earnings, price action in a clean list",
                "\n\n**Analysis**: Your professional assessment",
                "\n\n⚠️ IMPORTANT: Cite your sources with inline citations. Prioritize X.com and Bloomberg/Reuters over Yahoo."
            ])
            
            prompt = "".join(prompt_parts)
            
            # Configure Grok with search tools and inline citations
            chat = client.chat.create(
                model="grok-4-1-fast",
                tools=[
                    x_search(
                        allowed_x_handles=FINANCIAL_X_HANDLES,
                        from_date=datetime.now().replace(day=1)
                    ),
                    web_search()
                ],
                include=["inline_citations", "verbose_streaming"]  # Get [1], [2] inline + streaming tool calls
            )
            
            chat.append(user(prompt))
            
            logger.info("grok_ticker_research_starting", ticker=ticker, query=query[:50] if query else None)
            
            content = ""
            tool_calls = []
            
            for response, chunk in chat.stream():
                if chunk.content:
                    content += chunk.content
                
                # Log tool calls as they happen (verbose streaming)
                for tc in chunk.tool_calls:
                    tool_calls.append({
                        "tool": tc.function.name,
                        "args": tc.function.arguments[:100] if tc.function.arguments else ""
                    })
                    logger.debug("grok_tool_call", tool=tc.function.name)
            
            # Get all citations (URLs)
            all_citations = list(response.citations) if response.citations else []
            
            # Get inline citations with structured data
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
            
            # Use all_citations if inline_citations is empty
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
                "content": content,  # Contains inline [[1]](url) format
                "citations": citations,  # All source URLs
                "inline_citations": inline_citations,  # Structured citation data
                "tool_calls": tool_calls,
                "timestamp": datetime.now().isoformat()
            }
            
        except ImportError:
            # Don't retry import errors
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
    
    # All retries exhausted
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
    """
    Search for general financial news on a topic using Grok.
    """
    api_key = os.getenv('GROK_API_KEY_2') or os.getenv('GROK_API_KEY')
    if not api_key:
        return {"success": False, "error": "Grok API key not configured"}
    
    os.environ['XAI_API_KEY'] = api_key
    
    try:
        from xai_sdk import Client
        from xai_sdk.chat import user
        from xai_sdk.tools import x_search, web_search
        
        client = Client()
        today = datetime.now()
        
        prompt = f"""You are a financial news researcher. Today is {today.strftime("%B %d, %Y")}.

Search for the latest news and developments about: {topic}

Provide:
1. **Headlines**: Top 5 most important recent news items with dates
2. **Market Impact**: How this affects markets/stocks
3. **Social Buzz**: What financial Twitter is saying
4. **Key Takeaways**: 3 bullet points summary

Be specific and cite sources."""

        from_date = today.replace(day=max(1, today.day - days_back))
        
        chat = client.chat.create(
            model="grok-4-1-fast",
            tools=[
                x_search(
                    allowed_x_handles=FINANCIAL_X_HANDLES,
                    from_date=from_date
                ),
                web_search()
            ],
            include=["inline_citations"]  # Get inline citations
        )
        
        chat.append(user(prompt))
        
        content = ""
        for response, chunk in chat.stream():
            if chunk.content:
                content += chunk.content
        
        citations = list(response.citations) if response.citations else []
        
        return {
            "success": True,
            "topic": topic,
            "content": content,  # Contains inline [[1]](url) format
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
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"http://benzinga-news:8015/api/v1/news/ticker/{ticker}",
                params={"limit": limit}
            )
            
            if response.status_code == 200:
                data = response.json()
                articles = data.get("results", [])
                
                # Format for easy consumption
                formatted = []
                for art in articles:
                    formatted.append({
                        "title": art.get("title", ""),
                        "summary": art.get("summary", art.get("description", ""))[:300],
                        "url": art.get("article_url") or art.get("url", ""),
                        "published": art.get("published_utc") or art.get("published_at", ""),
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
    # Run Grok research and Benzinga fetch in parallel
    grok_task = research_ticker(
        ticker=ticker,
        query=query,
        include_technicals=include_technicals,
        include_fundamentals=include_fundamentals
    )
    benzinga_task = fetch_benzinga_news(ticker, limit=10)
    
    grok_result, benzinga_news = await asyncio.gather(grok_task, benzinga_task)
    
    # Add Benzinga news to the result
    if benzinga_news:
        grok_result["benzinga_news"] = benzinga_news
        
        # Add Benzinga URLs to citations
        existing_citations = grok_result.get("citations", [])
        for news in benzinga_news:
            if news.get("url") and news["url"] not in existing_citations:
                existing_citations.append(news["url"])
        grok_result["citations"] = existing_citations
    
    return grok_result


def format_research_for_display(research: Dict) -> str:
    """
    Format research results for display in the chat.
    """
    if not research.get("success"):
        return f"Research failed: {research.get('error', 'Unknown error')}"
    
    output = []
    output.append(research.get("content", ""))
    
    # Add Benzinga news section if available
    benzinga = research.get("benzinga_news", [])
    if benzinga:
        output.append("\n\n---\n**📰 Additional News (Benzinga):**")
        for news in benzinga[:5]:
            title = news.get("title", "")
            if title:
                output.append(f"\n• {title}")
    
    # Add citations if available
    citations = research.get("citations", [])
    if citations:
        output.append("\n\n---\n**Sources:**")
        for i, cite in enumerate(citations[:15], 1):
            output.append(f"\n[{i}] {cite}")
    
    return "".join(output)
