"""
Grok Research Module
====================
Uses Grok 4.1 Fast with X.com and Web search to research tickers.
"""

import os
import asyncio
from datetime import datetime, date
from typing import Dict, List, Tuple, Optional
import structlog

logger = structlog.get_logger(__name__)

# Financial X handles to search (max 10 allowed by Grok API)
FINANCIAL_X_HANDLES = [
    "DeItaone", "Newsquawk", "unusual_whales", "FirstSquawk",
    "WSJ", "Reuters", "Bloomberg", "CNBC", "MarketWatch", "zerohedge"
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
            
            # Build the research prompt
            prompt_parts = [
                f"You are a senior financial analyst. Today is {today}.",
                f"\nResearch the stock ticker {ticker} thoroughly.",
                f"\nUser's specific question: {query}" if query else "",
                "\n\n## Required Research:",
                "\n1. **Latest News** - What are the most recent news and developments?",
                "\n2. **Social Sentiment** - What is the sentiment on X/Twitter?",
                "\n3. **Key Metrics** - Market cap, P/E, revenue, recent earnings if available",
            ]
            
            if include_technicals:
                prompt_parts.append("\n4. **Technical View** - Recent price action, support/resistance levels, trend")
            
            if include_fundamentals:
                prompt_parts.append("\n5. **Fundamental Analysis** - Growth prospects, competitive position, risks")
            
            prompt_parts.extend([
                "\n\n## Output Format:",
                "\nProvide a structured analysis with:",
                "\n- **TLDR**: 2-3 sentence summary",
                "\n- **News**: Recent developments with dates",
                "\n- **Financial Metrics**: Key numbers in a list",
                "\n- **Social Sentiment**: Twitter/X sentiment summary",
                "\n- **Analyst View**: Your assessment",
                "\n\nBe specific with numbers, dates, and cite your sources."
            ])
            
            prompt = "".join(prompt_parts)
            
            # Configure Grok with search tools
            chat = client.chat.create(
                model="grok-4-1-fast",
                tools=[
                    x_search(
                        allowed_x_handles=FINANCIAL_X_HANDLES,
                        from_date=datetime.now().replace(day=1)
                    ),
                    web_search()
                ]
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
            
            citations = list(response.citations) if response.citations else []
            
            logger.info("grok_ticker_research_completed",
                       ticker=ticker,
                       chars=len(content),
                       citations=len(citations),
                       tools_used=len(tool_calls),
                       attempt=attempt + 1)
            
            return {
                "success": True,
                "ticker": ticker,
                "content": content,
                "citations": citations,
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
            ]
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
            "content": content,
            "citations": citations,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error("grok_news_search_error", topic=topic, error=str(e))
        return {"success": False, "error": str(e)}


def format_research_for_display(research: Dict) -> str:
    """
    Format research results for display in the chat.
    """
    if not research.get("success"):
        return f"Research failed: {research.get('error', 'Unknown error')}"
    
    output = []
    output.append(research.get("content", ""))
    
    # Add citations if available
    citations = research.get("citations", [])
    if citations:
        output.append("\n\n---\n**Sources:**")
        for i, cite in enumerate(citations[:10], 1):
            output.append(f"\n[{i}] {cite}")
    
    return "".join(output)
