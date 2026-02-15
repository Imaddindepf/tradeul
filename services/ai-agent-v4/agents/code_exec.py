"""
Code Execution Agent - Generates Python/DuckDB code via Gemini 2.5 Pro.

The generated code is designed to run inside a Docker sandbox that provides
helper functions for querying market data, saving charts, etc. Sandbox
integration will be wired up in Phase 6 (reuses ai-agent v3 sandbox infra).
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

_llm = None

# ── Code generation prompt ───────────────────────────────────────

CODE_GEN_PROMPT = """\
You are a financial code generation assistant.  Generate ONLY executable
Python 3.12 code that runs inside a sandboxed Docker container.

The sandbox pre-imports these helpers — use them directly (do NOT import):

  historical_query(ticker, start, end, interval="1d")
    → pandas DataFrame with columns: date, open, high, low, close, volume

  live_quote(ticker)
    → dict with keys: price, change, change_pct, volume, market_cap

  run_sql(query)
    → DuckDB SQL against any DataFrame registered with `register_df(name, df)`

  register_df(name, df)
    → Register a pandas DataFrame so DuckDB can query it by name

  save_output(data, label="result")
    → Persist a dict / DataFrame as the node output (returned to the agent)

  save_chart(fig, label="chart")
    → Save a matplotlib / plotly figure as base64 PNG for display

Pre-installed packages: pandas, numpy, matplotlib, plotly, scipy,
scikit-learn, ta (technical analysis), duckdb.

RULES:
1. Wrap your code in a single ```python ... ``` block.
2. Always call save_output() with the final result.
3. Use save_chart() for any visual output.
4. Handle errors gracefully with try/except.
5. Do NOT use subprocess, os.system, socket, or network calls.
6. Keep execution under 30 seconds.

User request:
{query}

Additional context (if any):
{context}
"""


def _get_llm():
    """Lazily create the Gemini 2.5 Pro LLM for code generation."""
    global _llm
    if _llm is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            temperature=0.1,
            max_output_tokens=4096,
        )
    return _llm


def _extract_code(text: str) -> str:
    """Extract Python code from markdown fenced blocks."""
    # Try ```python ... ``` first
    pattern = r'```python\s*\n(.*?)```'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Try generic ``` ... ```
    pattern = r'```\s*\n(.*?)```'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # No fences — return the full text (best effort)
    return text.strip()


async def code_exec_node(state: dict) -> dict:
    """Generate Python/DuckDB code from the user query.

    Phase 5: Code generation only (LLM produces the script).
    Phase 6: Will integrate with Docker sandbox for actual execution.
    """
    start_time = time.time()

    query = state.get("query", "")
    agent_results = state.get("agent_results", {})

    # Build context from other agents' results (if available)
    context_parts: list[str] = []
    if "market_data" in agent_results:
        md = agent_results["market_data"]
        tickers = md.get("tickers_detected", [])
        if tickers:
            context_parts.append(f"Available tickers from market data: {', '.join(tickers)}")
    if "financial" in agent_results:
        fin = agent_results["financial"]
        analyzed = fin.get("tickers_analyzed", [])
        if analyzed:
            context_parts.append(f"Financial data available for: {', '.join(analyzed)}")

    context = "\n".join(context_parts) if context_parts else "No additional context."

    result: dict[str, Any] = {}

    try:
        llm = _get_llm()
        prompt = CODE_GEN_PROMPT.format(query=query, context=context)
        response = await llm.ainvoke([{"role": "user", "content": prompt}])

        raw_response = response.content
        generated_code = _extract_code(raw_response)

        result = {
            "status": "code_generated",
            "code": generated_code,
            "language": "python",
            "sandbox_execution": "pending",
            "note": (
                "Code generated successfully. Sandbox execution will be "
                "integrated in Phase 6 using the existing Docker sandbox "
                "infrastructure from ai-agent v3."
            ),
        }
        logger.info("Code exec: generated %d chars of Python code", len(generated_code))

    except Exception as exc:
        logger.error("Code exec generation failed: %s", exc)
        result = {
            "status": "error",
            "error": str(exc),
            "code": "",
        }

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "agent_results": {
            "code_exec": result,
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "code_exec": {
                "elapsed_ms": elapsed_ms,
                "status": result.get("status", "unknown"),
                "code_length": len(result.get("code", "")),
            },
        },
    }
