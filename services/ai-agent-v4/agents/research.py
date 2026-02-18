"""
Deep Research Agent - Uses Grok (XAI) for X.com + web search.
Falls back to Gemini 2.5 Pro if Grok/XAI is unavailable.

Priority:
  1. xai-sdk  → grok-3-mini (search=True) for real-time X.com + web results
  2. Gemini   → gemini-2.5-pro as general-purpose fallback

Company metadata:
  The supervisor stores verified company names in state["ticker_info"].
  This agent uses those names in every prompt to prevent the LLM from
  hallucinating the wrong company (e.g. confusing $LFS with LendingTree
  when it's actually LEIFRAS Co., Ltd.).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from agents._llm_retry import llm_invoke_with_retry

logger = logging.getLogger(__name__)


# ── Ticker context builder ───────────────────────────────────────

def _build_ticker_context(tickers: list[str], ticker_info: dict) -> str:
    """Build a detailed ticker context string using company metadata.

    Instead of just "$LFS", produces:
      "$LFS (LEIFRAS Co., Ltd. — Education & Training Services)"
    This prevents the LLM from hallucinating the wrong company.
    """
    parts = []
    for t in tickers:
        info = ticker_info.get(t, {})
        name = info.get("company_name", "")
        industry = info.get("industry", "")
        if name and industry:
            parts.append(f"${t} ({name} — {industry})")
        elif name:
            parts.append(f"${t} ({name})")
        else:
            parts.append(f"${t}")
    return ", ".join(parts)


# ── Grok (XAI) research ─────────────────────────────────────────

async def _research_with_grok(query: str, tickers: list[str], ticker_info: dict) -> dict[str, Any]:
    """Call Grok-3-mini via xai-sdk with live search enabled."""
    from xai_sdk import Client

    client = Client()
    ticker_context = _build_ticker_context(tickers, ticker_info)

    prompt = (
        f"You are a financial research analyst. Search X.com and the web "
        f"for the LATEST information about {ticker_context}.\n\n"
        f"CRITICAL: The ticker(s) and company name(s) above are VERIFIED from our database. "
        f"Use the exact company name provided. Do NOT confuse with other companies "
        f"that may share similar ticker symbols.\n\n"
        f"User query: {query}\n\n"
        f"Focus on:\n"
        f"1. WHY is this stock moving right now? What is the specific catalyst?\n"
        f"2. Latest social sentiment from X.com posts (last 24-48 hours)\n"
        f"3. Recent news and developments about this specific company\n"
        f"4. Key analyst opinions or price targets mentioned\n"
        f"5. Any upcoming catalysts or events\n\n"
        f"Prioritize the most RECENT information (today and this week). "
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

_gemini_llm = None

def _get_gemini_llm():
    """Lazily create and reuse a single Gemini instance for research."""
    global _gemini_llm
    if _gemini_llm is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _gemini_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            temperature=0.3,
            max_output_tokens=4096,
        )
    return _gemini_llm


async def _research_with_gemini(query: str, tickers: list[str], ticker_info: dict) -> dict[str, Any]:
    """Fallback: use Gemini 2.5 Pro for research synthesis."""
    llm = _get_gemini_llm()

    ticker_context = _build_ticker_context(tickers, ticker_info) if tickers else "general market"

    # Build company description context from metadata
    company_desc = ""
    for t in tickers:
        info = ticker_info.get(t, {})
        desc = info.get("description", "")
        if desc:
            company_desc += f"\n{t}: {desc}"

    prompt = (
        f"You are a financial research analyst. Provide a comprehensive research "
        f"briefing about {ticker_context} based on your training data.\n\n"
        f"CRITICAL: The ticker(s) and company name(s) above are VERIFIED from our database. "
        f"Use the exact company name provided. Do NOT confuse with other companies.\n\n"
    )

    if company_desc:
        prompt += f"Company descriptions from our database:{company_desc}\n\n"

    prompt += (
        f"User query: {query}\n\n"
        f"Cover:\n"
        f"1. Company overview based on the verified name and description above\n"
        f"2. Key financial metrics and trends\n"
        f"3. Market sentiment and analyst consensus\n"
        f"4. Potential risks and catalysts\n\n"
        f"Note: This is based on training data, not real-time search."
    )

    response = await llm_invoke_with_retry(llm, [{"role": "user", "content": prompt}])

    return {
        "source": "gemini-2.5-pro",
        "content": response.content,
        "citations": [],
        "tickers": tickers,
        "note": "Fallback to Gemini — results are not real-time.",
    }


# ── Node entry point ─────────────────────────────────────────────

async def research_node(state: dict) -> dict:
    """Run deep research using Grok (preferred) or Gemini (fallback).

    Uses ticker_info from state to provide verified company names,
    preventing the LLM from researching the wrong company.
    """
    start_time = time.time()

    query = state.get("query", "")
    tickers = state.get("tickers", [])
    ticker_info = state.get("ticker_info", {})
    xai_available = bool(os.getenv("XAI_API_KEY"))

    # Enrich query with target candle context for date-specific research
    chart_context = state.get("chart_context")
    research_query = query
    if chart_context and chart_context.get("targetCandle"):
        from datetime import datetime as dt
        tc = chart_context["targetCandle"]
        tc_date = dt.utcfromtimestamp(tc.get("date", 0)).strftime("%B %d, %Y")
        ticker = chart_context.get("ticker", tickers[0] if tickers else "")
        change_pct = ""
        if tc.get("open") and tc.get("close"):
            pct = round(((tc["close"] - tc["open"]) / tc["open"]) * 100, 2)
            direction = "up" if pct > 0 else "down"
            change_pct = f" (moved {direction} {abs(pct)}% that day, volume {tc.get('volume', 'N/A'):,.0f})"
        research_query = (
            f"What happened to {ticker} stock on {tc_date}{change_pct}? "
            f"Find the SPECIFIC catalyst that caused this price movement. "
            f"Could be: earnings report, FDA decision, acquisition/merger, analyst upgrade/downgrade, "
            f"contract win, SEC filing, guidance revision, product launch, legal action, short squeeze, etc. "
            f"Provide: 1) The specific event/catalyst with concrete numbers (revenue, EPS, margins vs estimates if earnings) "
            f"2) Forward guidance if applicable 3) Analyst reactions and price target changes "
            f"4) Market narrative — why did this matter? 5) Any risks or headwinds mentioned"
        )
        logger.info("Research: enriched query for target candle on %s", tc_date)

    source_used = "none"
    research_result: dict[str, Any] = {}

    try:
        if xai_available and tickers:
            logger.info("Research: using Grok (XAI) for tickers %s", tickers)
            research_result = await _research_with_grok(research_query, tickers, ticker_info)
            source_used = "grok"
        else:
            if not xai_available:
                logger.info("Research: XAI_API_KEY not set, falling back to Gemini")
            elif not tickers:
                logger.info("Research: no tickers detected, using Gemini for general research")
            research_result = await _research_with_gemini(research_query, tickers, ticker_info)
            source_used = "gemini"
    except Exception as exc:
        logger.error("Research (%s) failed: %s", source_used or "grok", exc)
        # If Grok fails, try Gemini as secondary fallback
        if source_used != "gemini":
            try:
                logger.info("Research: Grok failed, retrying with Gemini fallback")
                research_result = await _research_with_gemini(research_query, tickers, ticker_info)
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
