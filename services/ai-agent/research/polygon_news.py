"""
Polygon News Integration
========================
Fetches news from both Polygon News API and Benzinga API,
merges results intelligently.

Speed: ~5 seconds for 50 tickers (vs 17+ minutes with Grok)
Cost: $0 (included in Polygon subscription)
Sentiment: Included from Polygon API
"""

import asyncio
import httpx
import re
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger(__name__)

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "vjzI76TMiepqrMZKphpfs3SA54JFkhEx")
POLYGON_BASE_URL = "https://api.polygon.io"


@dataclass
class NewsArticle:
    """Unified news article from any source."""
    ticker: str
    title: str
    summary: str
    published: datetime
    source: str  # "polygon" | "benzinga" | "both"
    url: str
    
    # From Polygon (may be None if only Benzinga)
    sentiment: Optional[str] = None  # "positive" | "negative" | "neutral"
    sentiment_reasoning: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    
    # From Benzinga (may be None if only Polygon)
    body: Optional[str] = None
    teaser: Optional[str] = None
    channels: List[str] = field(default_factory=list)
    
    @property
    def age_hours(self) -> float:
        """Hours since publication."""
        now = datetime.utcnow()
        if self.published.tzinfo:
            self.published = self.published.replace(tzinfo=None)
        delta = now - self.published
        return delta.total_seconds() / 3600
    
    @property
    def best_summary(self) -> str:
        """Get best available summary (clean, no markdown)."""
        # Prefer: teaser > summary > body truncated
        if self.teaser:
            return self._clean_text(self.teaser)
        if self.summary:
            return self._clean_text(self.summary)
        if self.body:
            clean = self._strip_html(self.body)
            return clean[:500] + "..." if len(clean) > 500 else clean
        return ""
    
    def _strip_html(self, text: str) -> str:
        """Remove HTML tags from text."""
        clean = re.sub(r'<[^>]+>', ' ', text)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()
    
    def _clean_text(self, text: str) -> str:
        """Clean text: remove markdown, extra whitespace."""
        # Remove markdown bold/italic
        clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        clean = re.sub(r'\*([^*]+)\*', r'\1', clean)
        # Remove markdown links [[n]](url)
        clean = re.sub(r'\[\[?\d+\]?\]\([^)]+\)', '', clean)
        # Remove extra whitespace
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()


async def fetch_polygon_news(
    ticker: str,
    hours_back: int = 24,
    limit: int = 10
) -> List[NewsArticle]:
    """
    Fetch from Polygon /v2/reference/news (includes sentiment).
    
    Args:
        ticker: Stock symbol
        hours_back: How many hours back to search
        limit: Max articles to return
        
    Returns:
        List of NewsArticle objects
    """
    articles = []
    now = datetime.utcnow()
    from_date = (now - timedelta(hours=hours_back)).strftime("%Y-%m-%d")
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{POLYGON_BASE_URL}/v2/reference/news",
                params={
                    "ticker": ticker,
                    "published_utc.gte": from_date,
                    "order": "desc",
                    "limit": limit,
                    "sort": "published_utc",
                    "apiKey": POLYGON_API_KEY,
                }
            )
            
            if response.status_code != 200:
                logger.warning("polygon_news_error", ticker=ticker, status=response.status_code)
                return []
            
            data = response.json()
            results = data.get("results", [])
            
            for item in results:
                # Find sentiment for this specific ticker
                sentiment = None
                sentiment_reasoning = None
                
                for insight in item.get("insights", []):
                    if insight.get("ticker", "").upper() == ticker.upper():
                        sentiment = insight.get("sentiment")
                        sentiment_reasoning = insight.get("sentiment_reasoning")
                        break
                
                # Parse published date
                pub_str = item.get("published_utc", "")
                try:
                    published = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                    published = published.replace(tzinfo=None)
                except:
                    published = now
                
                articles.append(NewsArticle(
                    ticker=ticker,
                    title=item.get("title", ""),
                    summary=item.get("description", ""),
                    published=published,
                    source="polygon",
                    url=item.get("article_url", ""),
                    sentiment=sentiment,
                    sentiment_reasoning=sentiment_reasoning,
                    keywords=item.get("keywords", []),
                ))
            
            logger.debug("polygon_news_fetched", ticker=ticker, count=len(articles))
            
    except Exception as e:
        logger.error("polygon_news_exception", ticker=ticker, error=str(e))
    
    return articles


async def fetch_benzinga_news(
    ticker: str,
    hours_back: int = 24,
    limit: int = 10
) -> List[NewsArticle]:
    """
    Fetch from Polygon /benzinga/v2/news (real-time, full body).
    
    Args:
        ticker: Stock symbol
        hours_back: How many hours back to search
        limit: Max articles to return
        
    Returns:
        List of NewsArticle objects
    """
    articles = []
    now = datetime.utcnow()
    from_date = (now - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{POLYGON_BASE_URL}/benzinga/v2/news",
                params={
                    "tickers": ticker,
                    "published.gte": from_date,
                    "sort": "published.desc",
                    "limit": limit,
                    "apiKey": POLYGON_API_KEY,
                }
            )
            
            if response.status_code != 200:
                logger.warning("benzinga_news_error", ticker=ticker, status=response.status_code)
                return []
            
            data = response.json()
            results = data.get("results", [])
            
            for item in results:
                # Parse published date
                pub_str = item.get("published", "")
                try:
                    published = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                    published = published.replace(tzinfo=None)
                except:
                    published = now
                
                # Clean title (remove HTML entities)
                title = item.get("title", "")
                title = title.replace("&#39;", "'").replace("&amp;", "&").replace("&quot;", '"')
                
                articles.append(NewsArticle(
                    ticker=ticker,
                    title=title,
                    summary="",
                    published=published,
                    source="benzinga",
                    url=item.get("url", ""),
                    teaser=item.get("teaser", ""),
                    body=item.get("body", ""),
                    channels=item.get("channels", []),
                ))
            
            logger.debug("benzinga_news_fetched", ticker=ticker, count=len(articles))
            
    except Exception as e:
        logger.error("benzinga_news_exception", ticker=ticker, error=str(e))
    
    return articles


def merge_news_articles(
    polygon_articles: List[NewsArticle],
    benzinga_articles: List[NewsArticle],
    similarity_threshold: float = 0.6
) -> List[NewsArticle]:
    """
    Merge articles from both sources, combining metadata.
    
    Strategy:
    - If same article in both: combine (sentiment from Polygon + body from Benzinga)
    - If only in one: use as-is
    - Dedupe by title similarity
    """
    from difflib import SequenceMatcher
    
    def similar(a: str, b: str) -> float:
        """Calculate string similarity 0-1."""
        a_clean = re.sub(r'[^\w\s]', '', a.lower())
        b_clean = re.sub(r'[^\w\s]', '', b.lower())
        return SequenceMatcher(None, a_clean, b_clean).ratio()
    
    merged = []
    used_benzinga_indices = set()
    
    # For each Polygon article, try to find matching Benzinga article
    for p_article in polygon_articles:
        best_match = None
        best_match_idx = None
        best_score = 0
        
        for idx, b_article in enumerate(benzinga_articles):
            if idx in used_benzinga_indices:
                continue
                
            score = similar(p_article.title, b_article.title)
            if score > best_score and score >= similarity_threshold:
                best_score = score
                best_match = b_article
                best_match_idx = idx
        
        if best_match:
            # Combine: sentiment from Polygon + body/teaser from Benzinga
            used_benzinga_indices.add(best_match_idx)
            merged.append(NewsArticle(
                ticker=p_article.ticker,
                title=p_article.title,
                summary=p_article.summary,
                published=max(p_article.published, best_match.published),
                source="both",
                url=p_article.url or best_match.url,
                sentiment=p_article.sentiment,
                sentiment_reasoning=p_article.sentiment_reasoning,
                keywords=p_article.keywords,
                body=best_match.body,
                teaser=best_match.teaser,
                channels=best_match.channels,
            ))
        else:
            # Only in Polygon
            merged.append(p_article)
    
    # Add remaining Benzinga articles (not matched)
    for idx, b_article in enumerate(benzinga_articles):
        if idx not in used_benzinga_indices:
            merged.append(b_article)
    
    # Sort by published date (most recent first)
    merged.sort(key=lambda x: x.published, reverse=True)
    
    return merged


async def get_news_for_ticker(
    ticker: str,
    hours_back: int = 24,
    limit_per_source: int = 5,
    max_results: int = 3
) -> List[NewsArticle]:
    """
    Get merged news for a single ticker from all sources.
    
    Args:
        ticker: Stock symbol
        hours_back: Hours to look back
        limit_per_source: Max articles per source
        max_results: Max final results to return
        
    Returns:
        List of merged NewsArticle objects
    """
    # Fetch from both sources in parallel
    polygon_task = fetch_polygon_news(ticker, hours_back, limit_per_source)
    benzinga_task = fetch_benzinga_news(ticker, hours_back, limit_per_source)
    
    polygon_articles, benzinga_articles = await asyncio.gather(
        polygon_task, benzinga_task
    )
    
    # Merge and dedupe
    merged = merge_news_articles(polygon_articles, benzinga_articles)
    
    # Return top N
    return merged[:max_results]


async def get_news_for_tickers(
    tickers: List[str],
    hours_back: int = 24,
    max_concurrent: int = 20
) -> Dict[str, List[NewsArticle]]:
    """
    Get news for multiple tickers with concurrency control.
    
    Args:
        tickers: List of stock symbols
        hours_back: Hours to look back
        max_concurrent: Max parallel requests
        
    Returns:
        Dict mapping ticker -> list of articles
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch_with_semaphore(ticker: str):
        async with semaphore:
            articles = await get_news_for_ticker(ticker, hours_back)
            return ticker, articles
    
    tasks = [fetch_with_semaphore(t) for t in tickers]
    results = await asyncio.gather(*tasks)
    
    return dict(results)
