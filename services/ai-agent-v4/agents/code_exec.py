"""
Code Execution Agent - Generates Python/DuckDB code via Gemini 2.5 Pro.

The generated code is designed to run inside a Docker sandbox that provides
helper functions for querying market data, saving charts, etc. Sandbox
integration will be wired up in Phase 6 (reuses ai-agent v3 sandbox infra).
"""
from __future__ import annotations

import logging
import ast
import os
import re
import time
from typing import Any

from agents._llm_retry import llm_invoke_with_retry

logger = logging.getLogger(__name__)


async def _prefetch_quotes(tickers: list[str]) -> dict[str, dict]:
    """Snapshot enriquecido de los tickers de la query, para que live_quote()
    dentro del sandbox (sin red) devuelva datos reales."""
    if not tickers:
        return {}
    try:
        from agents.mcp_catalog import MCP
        raw = await MCP.scanner.get_enriched_batch({"symbols": tickers[:20]})
        if not isinstance(raw, dict):
            return {}
        inner = raw.get("tickers", raw)  # el batch envuelve en {"tickers": {...}}
        if not isinstance(inner, dict):
            return {}
        quotes: dict[str, dict] = {}
        for sym, d in inner.items():
            if not isinstance(d, dict):
                continue
            day = d.get("day") or {}
            quotes[sym.upper()] = {
                "price": d.get("current_price") or (d.get("lastTrade") or {}).get("p"),
                "change": d.get("todaysChange"),
                "change_pct": d.get("todaysChangePerc"),
                "volume": d.get("current_volume") or day.get("v"),
                "market_cap": d.get("market_cap"),
            }
        return quotes
    except Exception as exc:  # noqa: BLE001
        logger.warning("code_exec: prefetch quotes failed: %s", exc)
        return {}


async def _run_in_sandbox(sandbox_url: str, code: str, quotes: dict) -> dict | None:
    """Ejecuta el código en el servicio sandbox aislado. None si no alcanzable."""
    import httpx

    token = os.getenv("CODE_SANDBOX_TOKEN", "").strip()
    headers = {"X-Sandbox-Token": token} if token else {}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            resp = await client.post(
                f"{sandbox_url.rstrip('/')}/run",
                json={"code": code, "quotes": quotes, "timeout_s": 35},
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("code_exec: sandbox call failed: %s", exc)
        return None

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
    → Save a matplotlib figure as base64 PNG for display

Pre-installed packages: pandas, numpy, matplotlib, scipy,
scikit-learn, ta (technical analysis), duckdb.

RULES:
1. Wrap your code in a single ```python ... ``` block.
2. Always call save_output() with the final result.
3. Use save_chart() for any visual output. Charts MUST be matplotlib
   figures — NEVER use plotly (its PNG export is unavailable in the
   sandbox and the chart will be silently dropped).
4. Handle errors gracefully with try/except.
5. Do NOT use subprocess, os.system, socket, or network calls.
6. Keep execution under 30 seconds.

DATE & DATA AVAILABILITY:
- TODAY IS {today}. When the user says a month/quarter WITHOUT a year (e.g.
  "julio", "in July"), assume the CURRENT year ({year}). Never default to a
  past year like 2023.
- Historical OHLCV via historical_query() covers roughly the last ~2 years up
  to today; recent dates in {year} and {last_year} ARE available. Do NOT treat
  the current year as "the future".
- Always pass explicit ISO dates (YYYY-MM-DD) to historical_query().

User request:
{query}

Additional context (if any):
{context}
"""


# Máximo de intentos: el primero más dos reparaciones. Sin tope, un modelo
# que no da con la tecla convierte un turno en un agujero de coste.
_MAX_ATTEMPTS = 3

# Claves que identifican una fila de mercado escrita a mano. Exigir a la vez
# un identificador de valor Y una cifra financiera evita marcar constantes
# legítimas (umbrales, pesos).
_ID_KEYS = {"ticker", "symbol"}
_FIN_KEYS = {
    "eps", "eps_actual", "eps_estimate", "revenue", "revenue_actual",
    "revenue_estimate", "price", "close", "open", "high", "low",
    "market_cap", "volume", "change_pct",
}

_REPAIR_PROMPT = """\
El código que generaste no se ejecutó. Este es el problema:

{error}

Corrígelo y devuelve el programa completo en un solo bloque ```python ... ```.
No expliques nada fuera del bloque. Recuerda que los datos se obtienen con los
helpers (historical_query, live_quote, run_sql); nunca se escriben a mano.

Código anterior:
```python
{code}
```
"""


def _hardcoded_market_data(tree: ast.AST) -> str | None:
    """Detecta filas de mercado escritas a mano en el propio código.

    El sandbox no tiene acceso a datos de earnings, así que un modelo que los
    necesita tiende a inventárselos y presentarlos como reales. Es preferible
    no ejecutar nada a devolver cifras fabricadas con aspecto de verdaderas.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {k.value.lower() for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        if not (keys & _ID_KEYS) or not (keys & _FIN_KEYS):
            continue
        numeric = any(
            isinstance(v, ast.Constant) and isinstance(v.value, (int, float))
            for v in node.values
        )
        if numeric:
            campos = sorted(keys & (_ID_KEYS | _FIN_KEYS))
            return (
                "El código lleva datos de mercado escritos a mano "
                f"(campos {campos}). Nunca inventes ni simules cifras: "
                "obtén los datos con historical_query() o live_quote(), y si "
                "un dato no está disponible dilo en la salida en vez de "
                "rellenarlo."
            )
    return None


def _validate_code(code: str) -> str | None:
    """Motivo por el que este código NO debe ejecutarse, o None.

    Barata y determinista, y corre antes de gastar una ejecución: el fallo
    típico —una respuesta truncada que deja la marca ```python dentro del
    programa— se caza aquí sin consumir sandbox ni tokens.
    """
    if not code.strip():
        return "No se generó código."
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        linea = (code.splitlines() or [""])[max(0, (exc.lineno or 1) - 1)]
        return f"SyntaxError en la línea {exc.lineno}: {exc.msg}\n  {linea.strip()[:120]}"
    return _hardcoded_market_data(tree)


def _get_llm():
    """Lazily create the LLM for code generation — uses best available provider."""
    global _llm
    if _llm is None:
        from agents._make_llm import make_llm
        _llm = make_llm(tier="pro", temperature=0.1, max_tokens=4096)
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
    tickers = state.get("tickers", [])
    active_agents = state.get("active_agents", [])

    # Build context from planner state (agent_results is empty in parallel arch)
    context_parts: list[str] = []
    if tickers:
        context_parts.append(f"Available tickers: {', '.join(tickers)}")
    if active_agents:
        context_parts.append(f"Other agents running in parallel: {', '.join(active_agents)}")
    plan = state.get("plan", "")
    if plan:
        context_parts.append(f"Execution plan: {plan}")

    context = "\n".join(context_parts) if context_parts else "No additional context."

    result: dict[str, Any] = {}

    try:
        llm = _get_llm()
        from datetime import datetime, timezone
        _now = datetime.now(timezone.utc)
        prompt = CODE_GEN_PROMPT.format(
            query=query, context=context,
            today=_now.strftime("%B %d, %Y"),
            year=_now.year, last_year=_now.year - 1,
        )
        sandbox_url = os.getenv("CODE_SANDBOX_URL", "").strip()
        quotes = await _prefetch_quotes(tickers) if sandbox_url else {}

        # Un fallo de ejecución es una señal, no un final: vuelve al modelo
        # como contexto del siguiente intento. Acotado a _MAX_ATTEMPTS.
        generated_code = ""
        exec_result = None
        attempts: list[str] = []
        next_prompt = prompt

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            response = await llm_invoke_with_retry(
                llm, [{"role": "user", "content": next_prompt}])
            generated_code = _extract_code(response.content)

            problema = _validate_code(generated_code)
            if problema is None and sandbox_url:
                exec_result = await _run_in_sandbox(sandbox_url, generated_code, quotes)
                if exec_result is None or exec_result.get("ok"):
                    break
                problema = (exec_result.get("error") or "")[:1500]
            elif problema is None:
                break

            attempts.append(f"intento {attempt}: {problema.splitlines()[0][:160]}")
            logger.warning("Code exec: intento %d rechazado — %s",
                           attempt, problema.splitlines()[0][:200])
            if attempt == _MAX_ATTEMPTS:
                break
            next_prompt = _REPAIR_PROMPT.format(error=problema, code=generated_code)

        result = {
            "status": "code_generated",
            "code": generated_code,
            "language": "python",
        }
        if attempts:
            # Los intentos fallidos viajan con la respuesta: si acabó bien tras
            # repararse, se ve; si no, se ve por qué.
            result["repair_attempts"] = attempts
        logger.info("Code exec: generated %d chars of Python code in %d attempt(s)",
                    len(generated_code), len(attempts) + 1)

        if generated_code and sandbox_url:
            if exec_result is not None:
                result["sandbox_execution"] = "ok" if exec_result.get("ok") else "error"
                result["outputs"] = exec_result.get("outputs", [])
                result["charts"] = exec_result.get("charts", [])
                result["exec_error"] = exec_result.get("error")
                result["exec_stdout"] = (exec_result.get("stdout") or "")[-4000:]
                result["exec_elapsed_ms"] = exec_result.get("elapsed_ms")
                logger.info(
                    "Code exec: sandbox %s in %sms (%d outputs, %d charts)",
                    result["sandbox_execution"], exec_result.get("elapsed_ms"),
                    len(result["outputs"]), len(result["charts"]),
                )
            else:
                result["sandbox_execution"] = "unavailable"
        else:
            result["sandbox_execution"] = "disabled"

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
