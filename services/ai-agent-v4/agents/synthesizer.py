"""
Synthesizer Agent - Produces the final user-facing response.

Takes all agent_results from state, feeds them to Gemini Flash,
and produces a polished markdown response.
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
            max_output_tokens=4096,
        )
    return _llm


SYNTHESIS_PROMPT = """\
You are the final-stage synthesizer of TradeUL, a professional trading analysis platform.

RULES:
1. Be concise – avoid filler; every sentence must add value.
2. Use **bold** for key numbers, percentages, prices, and important terms.
3. Use markdown tables when comparing tickers, metrics, or time-series data.
4. Use bullet points for lists of 3+ items.
5. Add section headers (##) only when the response covers multiple topics.
6. Match the user's language exactly (if the query is in Spanish, respond in Spanish).
7. Never reveal internal tool names, agent names, or system architecture.
8. If data is missing or unavailable, say so briefly – do not hallucinate numbers.
9. End with a one-line actionable insight or caveat when appropriate.
10. Keep total response under 800 words unless the data truly requires more.

You will receive:
- The original user query
- Results collected from specialist agents (JSON)

Synthesize these into a single, polished markdown response for the end user.
"""


async def synthesizer_node(state: dict) -> dict:
    """Synthesize all agent results into a final markdown response."""
    llm = _get_llm()
    start_time = time.time()

    query = state.get("query", "")
    agent_results = state.get("agent_results", {})
    language = state.get("language", "en")

    # Build the data payload for the LLM
    results_payload = {}
    for agent_name, result in agent_results.items():
        result_str = json.dumps(result, default=str)
        # Truncate very large payloads to stay within context window
        if len(result_str) > 8000:
            result_str = result_str[:8000] + "...(truncated)"
        results_payload[agent_name] = result_str

    messages = [
        SystemMessage(content=SYNTHESIS_PROMPT),
        HumanMessage(content=json.dumps({
            "query": query,
            "language": language,
            "agent_results": results_payload,
        }, ensure_ascii=False)),
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
            },
        },
    }
