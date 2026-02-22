"""
Deep Research Agent — Gemini with Google Search Grounding (primary)
                     + Grok/XAI for X.com search (optional secondary).

Priority:
  1. Gemini 2.5 Flash + Google Search Grounding → real-time web search with citations
  2. xai-sdk → grok-3-mini (search=True) for X.com social sentiment (if XAI_API_KEY set)
  3. Merge both results when available

Company metadata:
  The supervisor stores verified company names in state["ticker_info"].
  This agent uses those names in every prompt to prevent the LLM from
  hallucinating the wrong company.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


# ── Ticker context builder ───────────────────────────────────────

def _build_ticker_context(tickers: list[str], ticker_info: dict) -> str:
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


_ANTI_HALLUCINATION = (
    "ABSOLUTE RULE: Only report information you actually found in search results. "
    "If you cannot find the specific catalyst or event, say clearly: "
    "'No specific catalyst identified in available sources.' "
    "NEVER fabricate hypothetical scenarios, fictional analyst ratings, "
    "invented price targets, or made-up regulatory events. Accuracy over completeness."
)


# ── Gemini + Google Search Grounding (PRIMARY) ───────────────────

_genai_client = None


def _get_genai_client():
    global _genai_client
    if _genai_client is None:
        from google import genai
        _genai_client = genai.Client()
    return _genai_client


async def _research_with_gemini_grounding(
    query: str, tickers: list[str], ticker_info: dict,
    *, is_historical: bool = False,
) -> dict[str, Any]:
    """Use Gemini 2.5 Flash with Google Search grounding for real-time web search.

    The `query` parameter is the resolved research task — either the planner's
    agent_task (tailored sub-question) or the user's original query as fallback.
    """
    from google.genai import types

    client = _get_genai_client()
    ticker_context = _build_ticker_context(tickers, ticker_info) if tickers else "general market"

    if is_historical:
        supplementary = (
            "Search for the SPECIFIC event or catalyst on the date mentioned. "
            "Look for: earnings reports, partnerships, acquisitions, FDA decisions, "
            "analyst upgrades/downgrades, SEC filings, product launches, contract wins, "
            "or any significant news that could explain a stock price movement.\n\n"
            "Provide concrete numbers (revenue, EPS, margins vs estimates) when available. "
            "Include analyst reactions and price target changes if found."
        )
    else:
        supplementary = (
            "Provide concrete data, numbers, and sources. "
            "Prioritize the most relevant and recent information. "
            "Be specific with dates and figures when available."
        )

    prompt = (
        f"You are a financial research analyst. Search the web for information "
        f"about {ticker_context}.\n\n"
        f"CRITICAL: The ticker(s) and company name(s) above are VERIFIED from our database. "
        f"Use the exact company name provided. Do NOT confuse with other companies "
        f"that may share similar ticker symbols.\n\n"
        f"{_ANTI_HALLUCINATION}\n\n"
        f"RESEARCH TASK:\n{query}\n\n"
        f"{supplementary}"
    )

    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(
        tools=[grounding_tool],
        temperature=0.2,
        max_output_tokens=4096,
    )

    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=config,
    )

    citations: list[dict] = []
    search_queries: list[str] = []

    candidate = response.candidates[0] if response.candidates else None
    if candidate and hasattr(candidate, "grounding_metadata") and candidate.grounding_metadata:
        gm = candidate.grounding_metadata
        search_queries = list(gm.web_search_queries or [])

        chunks = gm.grounding_chunks or []
        for chunk in chunks:
            if hasattr(chunk, "web") and chunk.web:
                citations.append({
                    "url": chunk.web.uri or "",
                    "title": chunk.web.title or "",
                })

    return {
        "source": "gemini-grounding",
        "content": response.text or "",
        "citations": citations,
        "search_queries": search_queries,
        "tickers": tickers,
    }


# ── Grok (XAI) for X.com social search (SECONDARY) ──────────────

async def _research_with_grok(
    query: str, tickers: list[str], ticker_info: dict, *, is_historical: bool = False,
) -> dict[str, Any]:
    """Call Grok-3-mini via xai-sdk with live X.com + web search."""
    from xai_sdk import Client

    client = Client()
    ticker_context = _build_ticker_context(tickers, ticker_info)

    prompt = (
        f"You are a financial analyst focused on social media sentiment. "
        f"Search X.com (Twitter) for the latest posts about {ticker_context}.\n\n"
        f"CRITICAL: The ticker(s) and company name(s) above are VERIFIED from our database. "
        f"Use the exact company name provided.\n\n"
        f"{_ANTI_HALLUCINATION}\n\n"
        f"User query: {query}\n\n"
        f"Focus ONLY on:\n"
        f"1. Social sentiment from X.com posts (last 24-48 hours)\n"
        f"2. Retail trader chatter and notable accounts discussing this stock\n"
        f"3. Any breaking rumors or unconfirmed reports\n\n"
        f"Keep it concise. Include @handles of notable posters when relevant."
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
        "citations": list(dict.fromkeys(citations)),
        "tickers": tickers,
    }


# ── Node entry point ─────────────────────────────────────────────

async def research_node(state: dict) -> dict:
    """Run deep research: Gemini+Grounding (primary) + Grok/X.com (conditional).

    Uses agent_task from state (injected by fan_out) as primary research focus.
    Falls back to raw query when no task is provided.
    Grok only runs for CAUSAL/sentiment queries (not for business model, fundamentals, etc.)
    """
    import asyncio

    start_time = time.time()

    query = state.get("query", "")
    agent_task = state.get("agent_task", "")
    intent = state.get("intent", "")
    tickers = list(state.get("tickers", []))
    ticker_info = state.get("ticker_info", {})
    xai_available = bool(os.getenv("XAI_API_KEY"))

    chart_context = state.get("chart_context")

    # Ensure chart ticker is in tickers even if scanner rejected it
    if chart_context and chart_context.get("ticker"):
        chart_ticker = chart_context["ticker"].upper()
        if chart_ticker and chart_ticker not in tickers:
            tickers.append(chart_ticker)

    # Priority: chart enrichment > planner's agent_task > raw user query
    research_query = agent_task or query
    is_historical_research = False
    if chart_context and chart_context.get("targetCandle"):
        is_historical_research = True
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
            f"partnership announcement, contract win, SEC filing, guidance revision, product launch, "
            f"legal action, short squeeze, etc. "
            f"Provide: 1) The specific event/catalyst with concrete numbers (revenue, EPS, margins vs estimates if earnings) "
            f"2) Forward guidance if applicable 3) Analyst reactions and price target changes "
            f"4) Market narrative — why did this matter? 5) Any risks or headwinds mentioned"
        )
        logger.info("Research: enriched query for target candle on %s", tc_date)

    sources_used: list[str] = []
    research_result: dict[str, Any] = {}

    # ── PRIMARY: Gemini with Google Search Grounding ──
    gemini_result: dict[str, Any] | None = None
    grok_result: dict[str, Any] | None = None

    tasks = []

    async def _run_gemini():
        return await _research_with_gemini_grounding(
            research_query, tickers, ticker_info, is_historical=is_historical_research,
        )

    async def _run_grok():
        return await _research_with_grok(
            research_query, tickers, ticker_info, is_historical=is_historical_research,
        )

    tasks.append(_run_gemini())
    _SOCIAL_INTENTS = {"CAUSAL", "COMPLETE_ANALYSIS", "CHART_ANALYSIS"}
    use_grok = xai_available and tickers and intent in _SOCIAL_INTENTS
    if use_grok:
        tasks.append(_run_grok())

    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)

        gemini_result = results[0] if not isinstance(results[0], Exception) else None
        if isinstance(results[0], Exception):
            logger.error("Research: Gemini grounding failed: %s", results[0])

        if len(results) > 1:
            grok_result = results[1] if not isinstance(results[1], Exception) else None
            if isinstance(results[1], Exception):
                logger.warning("Research: Grok failed (non-critical): %s", results[1])

    except Exception as exc:
        logger.error("Research: parallel execution failed: %s", exc)

    # ── Merge results ──
    if gemini_result and grok_result:
        sources_used = ["gemini-grounding", "grok-3-mini"]
        research_result = {
            "source": "gemini-grounding+grok",
            "content": gemini_result.get("content", ""),
            "social_sentiment": grok_result.get("content", ""),
            "citations": gemini_result.get("citations", []),
            "social_citations": grok_result.get("citations", []),
            "search_queries": gemini_result.get("search_queries", []),
            "tickers": tickers,
        }
    elif gemini_result:
        sources_used = ["gemini-grounding"]
        research_result = gemini_result
    elif grok_result:
        sources_used = ["grok-3-mini"]
        research_result = grok_result
    else:
        sources_used = ["error"]
        research_result = {
            "source": "error",
            "content": "",
            "citations": [],
            "error": "Both Gemini grounding and Grok failed.",
        }

    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "Research: completed in %dms, sources=%s, citations=%d, task=%s, grok=%s",
        elapsed_ms, sources_used, len(research_result.get("citations", [])),
        bool(agent_task), use_grok,
    )

    return {
        "agent_results": {
            "research": research_result,
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "research": {
                "elapsed_ms": elapsed_ms,
                "sources": sources_used,
                "tickers": tickers,
                "xai_available": xai_available,
                "had_agent_task": bool(agent_task),
            },
        },
    }
