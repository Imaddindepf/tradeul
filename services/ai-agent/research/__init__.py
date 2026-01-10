"""
Research Module
===============
Provides deep research capabilities using Grok and other LLMs.
Combines X.com, web search, and Benzinga for comprehensive coverage.
"""

from .grok_research import (
    research_ticker,
    research_ticker_combined,
    search_financial_news,
    fetch_benzinga_news,
    format_research_for_display,
    FINANCIAL_X_HANDLES,
    WEB_PRIORITY_SOURCES
)

__all__ = [
    'research_ticker',
    'research_ticker_combined',
    'search_financial_news',
    'fetch_benzinga_news',
    'format_research_for_display',
    'FINANCIAL_X_HANDLES',
    'WEB_PRIORITY_SOURCES'
]

