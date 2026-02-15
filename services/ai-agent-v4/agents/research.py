"""
Deep Research Agent - Uses Grok (XAI) for X.com + web search.
Falls back to Gemini 2.5 Pro if Grok/XAI is unavailable.

Priority:
  1. xai-sdk  → grok-3-mini (search=True) for real-time X.com + web results
  2. Gemini   → gemini-2.5-pro as general-purpose fallback
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

# ── Ticker extraction (shared pattern) ───────────────────────────
_TICKER_RE = re.compile(r'(?<!\w)\$?([A-Z]{1,5})(?:\s|$|[,;.!?\)])')

_STOPWORDS = {
    "I", "A", "AM", "PM", "US", "CEO", "FDA", "SEC", "IPO", "ETF",
    "GDP", "CPI", "ATH", "DD", "EPS", "PE", "API", "AI", "IT", "IS",
    "ARE", "THE", "AND", "FOR", "TOP", "ALL", "BUY", "GET", "HAS",
    "NEW", "NOW", "HOW", "WHY", "UP", "DE", "LA", "EL", "EN", "ES",
    "LOS", "LAS", "QUE", "POR", "MAS", "CON", "UNA", "DEL", "DIA",
    "HOY", "LOW", "HIGH",
}


def _extract_tickers(query: str) -> list[str]:
    """Extract probable stock tickers from a user query."""
    explicit = re.findall(r'\$([A-Z]{1,5})\b', query.upper())
    implicit = _TICKER_RE.findall(query.upper())
    combined = list(dict.fromkeys(explicit + implicit))
    return [t for t in combined if t not in _STOPWORDS]


# ── Grok (XAI) research ─────────────────────────────────────────

async def _research_with_grok(query: str, tickers: list[str]) -> dict[str, Any]:
    """Call Grok-3-mini via xai-sdk with live search enabled."""
    from xai_sdk import Client

    client = Client()
    ticker_context = ", ".join(f"${t}" for t in tickers)

    prompt = (
        f"You are a financial research analyst. Search X.com and the web "
        f"for the latest information about {ticker_context}.\n\n"
        f"User query: {query}\n\n"
        f"Provide:\n"
        f"1. Latest social sentiment from X.com posts\n"
        f"2. Recent news and developments\n"
        f"3. Key analyst opinions or price targets mentioned\n"
        f"4. Any upcoming catalysts or events\n\n"
        f"Include source URLs where available."
    )

    response_text = ""
    citations: list[str] = []

    conversation = client.chat.create_conversation()
    token_stream = conversation.add_response(
        conversation.new_message(prompt, role="user"),
        model="grok-3-mini",
        search=True,
    )

    async for token in token_stream:
        if hasattr(token, "token"):
            response_text += token.token
        if hasattr(token, "citations"):
            citations.extend(token.citations)

    return {
        "source": "grok-3-mini",
        "content": response_text,
        "citations": list(dict.fromkeys(citations)),  # dedupe
        "tickers": tickers,
    }


# ── Gemini fallback ──────────────────────────────────────────────

async def _research_with_gemini(query: str, tickers: list[str]) -> dict[str, Any]:
    """Fallback: use Gemini 2.5 Pro for research synthesis."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-pro",
        temperature=0.3,
        max_output_tokens=4096,
    )

    ticker_context = ", ".join(f"${t}" for t in tickers) if tickers else "general market"

    prompt = (
        f"You are a financial research analyst. Provide a comprehensive research "
        f"briefing about {ticker_context} based on your training data.\n\n"
        f"User query: {query}\n\n"
        f"Cover:\n"
        f"1. Company overview and recent developments\n"
        f"2. Key financial metrics and trends\n"
        f"3. Market sentiment and analyst consensus\n"
        f"4. Potential risks and catalysts\n\n"
        f"Note: This is based on training data, not real-time search."
    )

    response = await llm.ainvoke([{"role": "user", "content": prompt}])

    return {
        "source": "gemini-2.5-pro",
        "content": response.content,
        "citations": [],
        "tickers": tickers,
        "note": "Fallback to Gemini — results are not real-time.",
    }


# ── Node entry point ─────────────────────────────────────────────

async def research_node(state: dict) -> dict:
    """Run deep research using Grok (preferred) or Gemini (fallback)."""
    start_time = time.time()

    query = state.get("query", "")
    tickers = _extract_tickers(query)
    xai_available = bool(os.getenv("XAI_API_KEY"))

    source_used = "none"
    research_result: dict[str, Any] = {}

    try:
        if xai_available and tickers:
            logger.info("Research: using Grok (XAI) for tickers %s", tickers)
            research_result = await _research_with_grok(query, tickers)
            source_used = "grok"
        else:
            if not xai_available:
                logger.info("Research: XAI_API_KEY not set, falling back to Gemini")
            elif not tickers:
                logger.info("Research: no tickers detected, using Gemini for general research")
            research_result = await _research_with_gemini(query, tickers)
            source_used = "gemini"
    except Exception as exc:
        logger.error("Research (%s) failed: %s", source_used or "grok", exc)
        # If Grok fails, try Gemini as secondary fallback
        if source_used != "gemini":
            try:
                logger.info("Research: Grok failed, retrying with Gemini fallback")
                research_result = await _research_with_gemini(query, tickers)
                source_used = "gemini-fallback"
            except Exception as fallback_exc:
                logger.error("Research Gemini fallback also failed: %s", fallback_exc)
                research_result = {
                    "source": "error",
                    "content": "",
                    "citations": [],
                    "error": f"Both Grok and Gemini failed: {exc}; {fallback_exc}",
                }
                source_used = "error"
        else:
            research_result = {
                "source": "error",
                "content": "",
                "citations": [],
                "error": str(exc),
            }
            source_used = "error"

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "agent_results": {
            "research": research_result,
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "research": {
                "elapsed_ms": elapsed_ms,
                "source": source_used,
                "tickers": tickers,
                "xai_available": xai_available,
            },
        },
    }
