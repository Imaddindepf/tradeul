"""
Synthesizer Agent - Premium response generation.

Takes all agent_results from state, constructs a rich context payload,
and uses Gemini Flash to produce a polished, data-rich markdown response
with tables, metrics, and actionable insights.
"""
from __future__ import annotations
import json
import time
from langchain_core.messages import SystemMessage, HumanMessage

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

YOUR ROLE: Transform raw data from specialist agents into a polished, data-rich response.

RESPONSE LANGUAGE: {language_instruction}

FORMATTING RULES:
1. Use markdown tables when presenting ranked data, comparisons, or lists of stocks.
   Format: | Column1 | Column2 | ... |
2. Use **bold** for key numbers, prices, percentages, ticker symbols, and important terms.
3. Use ## headers to separate major sections (only when response covers multiple topics).
4. Use bullet points for qualitative observations and insights.
5. Include specific numbers — never say "significant volume" when you can say "**161M shares** (RVOL **8.2x**)".
6. For stock rankings, ALWAYS use a markdown table with columns like:
   | # | Ticker | Price | Change % | Volume | RVOL | Sector |
7. After data presentation, add a brief "Key Takeaways" or "Insights" section.
8. If market is closed, mention the data is from the last trading session.
9. Keep response comprehensive but focused. Use ALL the data provided.
10. Never mention internal tool names, agent names, or system architecture.
11. Never hallucinate data — only use what's provided in the agent results.
12. If an agent returned an error, work with whatever data IS available.
13. Clean up sector names: if a sector looks like a SIC code description (e.g. "PHONOGRAPH RECORDS & PRERECORDED AUDIO TAPES"), 
    map it to a standard sector (Technology, Healthcare, Consumer, Energy, Finance, Industrial, etc.) or use "Other".

DATA PRESENTATION PRIORITIES:
- For "top gainers/losers" queries: Table with rank, ticker, price, change%, volume, sector
- For ticker analysis: Key metrics card (price, change, volume, RSI, VWAP) + analysis
- For screening results: Table with matching stocks + filter criteria summary
- For news queries: Headlines with dates, sources, and brief summaries

You will receive the original query and JSON results from specialist agents.
Synthesize into a polished markdown response.
"""


def _build_language_instruction(language: str) -> str:
    """Build explicit language instruction."""
    if language == "es":
        return (
            "RESPOND ENTIRELY IN SPANISH (Español). "
            "All headers, descriptions, insights, and text must be in Spanish. "
            "Table column headers can remain in English for financial terms (Ticker, Price, Volume, etc.) "
            "but descriptions and insights MUST be in Spanish."
        )
    return "Respond in English."


def _prepare_results_payload(agent_results: dict) -> dict:
    """Prepare a clean, size-limited payload of agent results for the LLM."""
    payload = {}
    for agent_name, result in agent_results.items():
        if isinstance(result, dict):
            # For scanner snapshots, extract the ticker list directly
            clean_result = {}
            for key, value in result.items():
                if key.startswith("_"):
                    continue  # skip internal keys
                value_str = json.dumps(value, default=str)
                # Truncate very large values but keep enough for tables
                if len(value_str) > 12000:
                    value_str = value_str[:12000] + "...(truncated)"
                    try:
                        clean_result[key] = json.loads(value_str.rsplit("}", 1)[0] + "}]}")
                    except Exception:
                        clean_result[key] = value_str
                else:
                    clean_result[key] = value
            payload[agent_name] = clean_result
        else:
            result_str = json.dumps(result, default=str)
            if len(result_str) > 12000:
                result_str = result_str[:12000] + "...(truncated)"
            payload[agent_name] = result_str
    return payload


async def synthesizer_node(state: dict) -> dict:
    """Synthesize all agent results into a final markdown response."""
    llm = _get_llm()
    start_time = time.time()

    query = state.get("query", "")
    agent_results = state.get("agent_results", {})
    language = state.get("language", "en")

    language_instruction = _build_language_instruction(language)
    results_payload = _prepare_results_payload(agent_results)

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
    final_response = response.content

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
                "language": language,
            },
        },
    }
