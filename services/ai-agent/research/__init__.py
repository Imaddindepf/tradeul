"""
Research Module
===============
Provides deep research capabilities using Grok and other LLMs.
"""

from .grok_research import (
    research_ticker,
    search_financial_news,
    format_research_for_display
)

__all__ = [
    'research_ticker',
    'search_financial_news', 
    'format_research_for_display'
]

