"""
Synthesizer Agent - Premium response generation.

Takes all agent_results from state, constructs a clean context payload,
and uses Gemini Flash to produce a polished, data-rich markdown response
with tables, metrics, and actionable insights.

Architecture:
  Agent results arrive pre-cleaned by each agent (no raw data dumps).
  The synthesizer's job is ONLY formatting, analysis and insight generation.
"""
from __future__ import annotations
import json
import logging
import re
import time
from typing import Any
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

# ── Lazy LLM singleton ──────────────────────────────────────────
_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.3,
            max_output_tokens=8192,
        )
    return _llm


SYNTHESIS_PROMPT = """\
You are the final-stage synthesizer of TradeUL, a professional stock trading analysis platform.
Your audience: ultra-professional traders and analysts. They need precision, not fluff.

YOUR ROLE: Transform structured data from specialist agents into a polished, insightful response.

RESPONSE LANGUAGE: {language_instruction}

CRITICAL RULES:
1. ONLY use data provided in agent_results. NEVER hallucinate data.
2. NEVER mention internal tool/agent names or system architecture.
3. NEVER dump raw JSON. Present everything in formatted markdown tables.
4. NEVER include null values, internal IDs, accession numbers, or technical metadata.
5. If data is missing or an agent returned an error, say so honestly and briefly.

FORMATTING STANDARDS:
- Use markdown tables (| Col1 | Col2 |) for ALL structured data
- Use **bold** for tickers, key numbers, and important terms
- Use ## headers to separate sections (only for multi-topic responses)
- Include specific numbers — say "**161M shares** (RVOL **8.2x**)" not "significant volume"
- After data, add concise "Key Takeaways" with 2-4 bullet points max
- Keep responses focused and professional. No filler text.

FORMAT BY DATA TYPE:

SEC FILINGS:
| Form | Date Filed | Description |
Show formType, filed_date, and description only.
If accession_no available, link to: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=TICKER&type=FORM_TYPE
Do NOT show internal IDs, null fields, or raw document content.

FINANCIAL STATEMENTS:
Use the pre-formatted metrics provided (already human-readable numbers like 130.5B).
Present as a markdown table with periods as columns:
| Metric | 2025 | 2024 | 2023 | ...
Do NOT reformat or recalculate numbers.

STOCK RANKINGS (top gainers/losers/etc):
| # | Ticker | Price | Change % | Volume | Sector |
Clean sector names: map SIC descriptions to standard sectors (Tech, Healthcare, etc).

TICKER ANALYSIS (specific stock query):
Present key metrics inline or as a compact card:
- Price, Change, Volume, RVOL
- RSI, VWAP distance, ADX
- 52-week range position
Then add brief technical/fundamental analysis.

NEWS:
| Date | Title | Source |
Plus 1-line summary per article. No article body text.

EARNINGS:
| Date | Ticker | Company | EPS Est | EPS Actual | Revenue Est | Revenue Actual |
Include surprise % if available.

SCREENER RESULTS:
| # | Ticker | Price | [filter-relevant columns] |
Summarize the filter criteria used.

RESPONSE LENGTH:
- Quick data queries (prices, simple lookups): 200-500 words
- Analysis queries (financials, multi-ticker): 500-1000 words
- Deep research: 1000-2000 words max
- NEVER exceed 2000 words. Be concise and professional.
"""


def _build_language_instruction(language: str) -> str:
    if language == "es":
        return (
            "RESPOND ENTIRELY IN SPANISH (Español). "
            "All headers, descriptions, insights, and text must be in Spanish. "
            "Financial column headers can stay in English (Ticker, Price, Volume)."
        )
    return "Respond in English."


def _safe_json_size(obj: Any) -> int:
    """Get JSON serialized size of an object."""
    try:
        return len(json.dumps(obj, default=str))
    except Exception:
        return 0


def _prepare_results_payload(agent_results: dict) -> dict:
    """Prepare a clean, size-limited payload for the synthesizer LLM.
    
    Since agents now pre-clean their data, this function only needs to:
    1. Remove internal keys (starting with _)
    2. Apply a safety cap per agent (30K chars max) — should rarely trigger
    3. Log if truncation happens (indicates a cleaning bug upstream)
    """
    MAX_PER_AGENT = 30_000
    MAX_TOTAL = 80_000

    payload = {}
    total_size = 0

    for agent_name, result in agent_results.items():
        if not isinstance(result, dict):
            payload[agent_name] = result
            total_size += _safe_json_size(result)
            continue

        clean = {k: v for k, v in result.items() if not k.startswith("_")}
        agent_size = _safe_json_size(clean)

        if agent_size > MAX_PER_AGENT:
            logger.warning(
                "Agent '%s' payload too large (%d chars), truncating. "
                "This indicates insufficient upstream cleaning.",
                agent_name, agent_size,
            )
            # Truncate the largest values first
            sorted_keys = sorted(clean.keys(), key=lambda k: _safe_json_size(clean[k]), reverse=True)
            for key in sorted_keys:
                if agent_size <= MAX_PER_AGENT:
                    break
                val_size = _safe_json_size(clean[key])
                if val_size > 5000:
                    val_str = json.dumps(clean[key], default=str)[:4000]
                    clean[key] = f"[TRUNCATED from {val_size} chars] {val_str}..."
                    agent_size = _safe_json_size(clean)

        payload[agent_name] = clean
        total_size += _safe_json_size(clean)

    if total_size > MAX_TOTAL:
        logger.warning("Total payload size %d exceeds %d limit", total_size, MAX_TOTAL)

    return payload


_MULTI_SPACE = re.compile(r' {3,}')
_MULTI_NEWLINE = re.compile(r'\n{4,}')
_MAX_RESPONSE_CHARS = 15_000


def _post_process(text: str) -> str:
    """Post-process LLM output to fix known Gemini issues.
    
    1. Collapse excessive whitespace (Gemini sometimes fills table cells with spaces)
    2. Collapse excessive newlines
    3. Hard limit on response length (safety net)
    """
    if not text:
        return text

    original_len = len(text)

    # Collapse runs of 3+ spaces to a single space
    text = _MULTI_SPACE.sub(' ', text)
    # Collapse 4+ newlines to 2
    text = _MULTI_NEWLINE.sub('\n\n', text)
    # Strip trailing whitespace
    text = text.strip()

    if len(text) > _MAX_RESPONSE_CHARS:
        # Find a natural break point (end of paragraph or table)
        cutpoint = text.rfind('\n\n', 0, _MAX_RESPONSE_CHARS)
        if cutpoint < _MAX_RESPONSE_CHARS // 2:
            cutpoint = _MAX_RESPONSE_CHARS
        text = text[:cutpoint].rstrip()
        logger.warning(
            "Response truncated from %d to %d chars (original raw: %d)",
            original_len, len(text), original_len,
        )

    if original_len > len(text) * 1.5:
        logger.info(
            "Post-processing reduced response from %d to %d chars (%.0f%% reduction)",
            original_len, len(text), (1 - len(text) / original_len) * 100,
        )

    return text


async def synthesizer_node(state: dict) -> dict:
    """Synthesize all agent results into a final markdown response."""
    llm = _get_llm()
    start_time = time.time()

    query = state.get("query", "")
    agent_results = state.get("agent_results", {})
    language = state.get("language", "en")

    language_instruction = _build_language_instruction(language)
    results_payload = _prepare_results_payload(agent_results)

    payload_size = _safe_json_size(results_payload)
    logger.info("Synthesizer payload: %d chars for %d agents", payload_size, len(results_payload))

    system_prompt = SYNTHESIS_PROMPT.format(language_instruction=language_instruction)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps({
            "query": query,
            "language": language,
            "agent_results": results_payload,
        }, ensure_ascii=False, default=str)),
    ]

    response = await llm.ainvoke(messages)
    final_response = _post_process(response.content)

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "final_response": final_response,
        "current_agent": "done",
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "synthesizer": {
                "elapsed_ms": elapsed_ms,
                "result_agents": list(agent_results.keys()),
                "response_length": len(final_response),
                "payload_size": payload_size,
                "language": language,
            },
        },
    }
