"""
Synthesizer Agent — Structured output generation via Gemini 2.5 Flash.

Uses Google GenAI SDK with response_schema (constrained decoding) to
guarantee valid, parseable JSON output. Tables arrive as typed arrays
(impossible to break via truncation), text content is short markdown
scoped to individual sections.

Fallback: if structured generation fails, falls back to free-form
markdown with the legacy Gemini 2.0 Flash path.
"""
from __future__ import annotations
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# ── Structured schema ────────────────────────────────────────────
from agents.synthesizer_schema import SynthesizerResponse

# ── Lazy GenAI client singleton ──────────────────────────────────
_genai_client = None


def _get_genai_client():
    global _genai_client
    if _genai_client is None:
        import os
        google_key = os.getenv("GOOGLE_API_KEY", "").strip()
        if not google_key:
            raise RuntimeError("GOOGLE_API_KEY not set — structured Gemini path unavailable")
        from google import genai
        _genai_client = genai.Client()
    return _genai_client


# ── Fallback LLM (legacy markdown path) ─────────────────────────
_fallback_llm = None


def _get_fallback_llm():
    global _fallback_llm
    if _fallback_llm is None:
        from agents._make_llm import make_llm
        _fallback_llm = make_llm(tier="fast", temperature=0.3, max_tokens=8192)
    return _fallback_llm


# ── System prompt (structured output version) ───────────────────

STRUCTURED_PROMPT = """\
You are the premium response synthesizer for Tradeul, a professional stock trading intelligence platform.
Your audience: experienced day traders and institutional analysts who demand precision and actionable insights.

You MUST return a JSON object matching the provided schema. Every field you populate must come from the agent_results data — NEVER hallucinate prices, volumes, percentages, or company info.

<language>
{language_instruction}
All text fields (session_context, section titles, section content, bullets, key_takeaways) must be in the specified language.
Financial terms can stay in English: Ticker, Price, Volume, RSI, VWAP, RVOL, ADX, EPS, Revenue.
</language>

<market_session_rules>
Check "market_session" in the data. Use the "current_session" field:
- CLOSED + weekend/holiday → "El mercado está cerrado (fin de semana/festivo). Datos de la última sesión."
- CLOSED + weekday before 4am → "El mercado aún no ha abierto. Datos del cierre anterior."
- PRE_MARKET → "Sesión de pre-market activa (apertura a las 9:30 ET)." NEVER say the market is closed during pre-market.
- MARKET_OPEN → "Mercado abierto — datos en tiempo real."
- POST_MARKET → "Sesión after-hours activa."
Put this in the session_context field.
For CHART_ANALYSIS queries, leave session_context empty.
</market_session_rules>

<metrics_card_rules>
For queries about specific tickers, populate the metrics field with data from agent_results.market_data.enriched.
Use the company names from ticker_info — these are VERIFIED.
Format numbers with units: "$3.84", "6.78M", "RVOL 8.2x", "+69.01%", "-5.3%".
Large numbers abbreviated: 1.5B, 245M, 12.3K.
For CHART_ANALYSIS or RANKING queries, set metrics to null.
</metrics_card_rules>

<sections_rules>
Create sections based on query type:

CAUSAL ("why is X moving?"):
1. Section: catalyst/reason for the movement (from research data)
2. Section: recent news (with a table of articles: columns=[Date, Title, Summary])
3. Section: technical context (brief, with indicators table if data available)

RANKING ("top gainers", "halts"):
1. Section: main ranking table (columns=[#, Ticker, Price, Change%, Volume, RVOL, Sector])
2. Section: notable movers commentary (top 2-3)

DATA LOOKUP ("NVDA price"):
1. Section: technical analysis (2-3 sentences)
2. Section: key levels to watch

COMPLETE ANALYSIS:
1. Section: technical analysis
2. Section: recent news & events (with table)
3. Section: financial highlights (with table)
4. Section: research & sentiment

NEWS ("noticias de AAPL"):
1. Section: latest news (with table: columns=[Date, Title, Summary])

CHART_ANALYSIS:
Follow chart analysis format — focus on price action, trend, volume, indicators, key levels.
If target_candle exists, lead with the catalyst.

CONVERSATIONAL (greetings, off-topic):
1. Single section with a friendly conversational response, no market data.
If the user asks about backtest capabilities ("qué necesitas para backtest?", "how does backtest work?"), explain:
- Required: ticker(s) (max 3), entry strategy, exit rules
- Optional: date range, timeframe (1d/5min/1min)
- Example: "backtest RSI < 30 mean reversion en SPY, stop loss 5%, de 2023 a 2024"
- Limits: max 3 tickers, intraday max 60 days

Each section has:
- title: section header
- content: short markdown text (a few paragraphs max, NOT a full document)
- table: optional DataTable with headers[] and rows[] for structured data
- bullets: optional list of key points

CRITICAL: Tables MUST use the DataTable schema (headers + rows with cells array). NEVER put markdown tables in the content field.
Keep each section's content concise — 2-5 short paragraphs max.
</sections_rules>

<key_takeaways_rules>
Always provide 2-4 specific, actionable takeaways in the key_takeaways list.
Each takeaway should be one sentence with concrete data points.
For conversational queries, leave key_takeaways empty.
</key_takeaways_rules>

<citations_rules>
If agent_results.research contains citations, include them in the citations list.
Each citation needs a title and url.
</citations_rules>"""


def _build_language_instruction(language: str) -> str:
    if language == "es":
        return (
            "RESPOND ENTIRELY IN SPANISH (Español). "
            "All headers, descriptions, insights, and text must be in Spanish. "
            "Financial terms and column headers can stay in English."
        )
    return "Respond in English."


def _safe_json_size(obj: Any) -> int:
    try:
        return len(json.dumps(obj, default=str))
    except Exception:
        return 0


def _prepare_results_payload(agent_results: dict) -> dict:
    """Prepare a clean, size-limited payload for the synthesizer LLM."""
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
                "Agent '%s' payload too large (%d chars), truncating.",
                agent_name, agent_size,
            )
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


def _structured_to_markdown(resp: SynthesizerResponse) -> str:
    """Convert structured response to markdown for the legacy `final_response` field.

    This ensures backward compatibility — the Message.content field still
    contains readable markdown for the chat bubble, while the structured
    data is sent separately for the premium renderer.
    """
    parts: list[str] = []

    if resp.session_context:
        parts.append(resp.session_context)
        parts.append("")

    if resp.metrics:
        m = resp.metrics
        lines = [f"**{m.ticker}** — {m.company_name} ({m.sector}) \\\\"]
        kv_pairs = []
        if m.price:
            kv_pairs.append(f"**Price:** {m.price}")
        if m.change:
            kv_pairs.append(f"**Change:** {m.change}")
        if m.volume:
            kv_pairs.append(f"**Volume:** {m.volume}")
        if m.rvol:
            kv_pairs.append(f"(RVOL {m.rvol})")
        if kv_pairs:
            lines.append(" | ".join(kv_pairs) + " \\\\")
        kv2 = []
        if m.rsi:
            kv2.append(f"**RSI(14):** {m.rsi}")
        if m.vwap_dist:
            kv2.append(f"**VWAP Dist:** {m.vwap_dist}")
        if m.adx:
            kv2.append(f"**ADX(14):** {m.adx}")
        if kv2:
            lines.append(" | ".join(kv2) + " \\\\")
        kv3 = []
        if m.week52_range:
            kv3.append(f"**52W Range:** {m.week52_range}")
        if m.float_shares:
            kv3.append(f"**Float:** {m.float_shares}")
        if m.market_cap:
            kv3.append(f"**Market Cap:** {m.market_cap}")
        if kv3:
            lines.append(" | ".join(kv3))
        parts.append("\n".join(lines))
        parts.append("")

    for section in resp.sections:
        if section.title:
            parts.append(f"## {section.title}")
        if section.content:
            parts.append(section.content)
        if section.table and section.table.headers:
            t = section.table
            parts.append("| " + " | ".join(t.headers) + " |")
            parts.append("| " + " | ".join("---" for _ in t.headers) + " |")
            for row in t.rows:
                parts.append("| " + " | ".join(row.cells) + " |")
        if section.bullets:
            for b in section.bullets:
                parts.append(f"- {b}")
        parts.append("")

    if resp.key_takeaways:
        parts.append("## Key Takeaways")
        for t in resp.key_takeaways:
            parts.append(f"- {t}")
        parts.append("")

    return "\n".join(parts).strip()


async def _synthesize_structured(
    query: str,
    language: str,
    results_payload: dict,
    market_session: dict,
    ticker_info: dict,
    chart_context: dict | None,
) -> SynthesizerResponse:
    """Primary path: Gemini 2.5 Flash with constrained decoding."""
    from google.genai import types

    client = _get_genai_client()
    language_instruction = _build_language_instruction(language)

    user_payload = {
        "query": query,
        "language": language,
        "market_session": market_session,
        "agent_results": results_payload,
    }
    if ticker_info:
        user_payload["ticker_info"] = {
            t: {
                "company_name": info.get("company_name", ""),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
            }
            for t, info in ticker_info.items()
        }
    if chart_context:
        user_payload["chart_context"] = chart_context

    system_prompt = STRUCTURED_PROMPT.format(language_instruction=language_instruction)
    user_content = json.dumps(user_payload, ensure_ascii=False, default=str)

    config = types.GenerateContentConfig(
        response_schema=SynthesizerResponse,
        response_mime_type="application/json",
        system_instruction=system_prompt,
        temperature=0.3,
        max_output_tokens=8192,
    )

    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_content,
        config=config,
    )

    parsed = response.parsed
    if parsed is not None:
        return parsed

    raw_text = response.text or ""
    if raw_text:
        return SynthesizerResponse.model_validate_json(raw_text)

    raise ValueError("Gemini returned empty response")


async def _synthesize_fallback(
    query: str,
    language: str,
    results_payload: dict,
    market_session: dict,
    ticker_info: dict,
    chart_context: dict | None,
) -> str:
    """Fallback path: legacy Gemini 2.0 Flash free-form markdown."""
    from langchain_core.messages import SystemMessage, HumanMessage
    from agents._llm_retry import llm_invoke_with_retry
    import re

    llm = _get_fallback_llm()
    language_instruction = _build_language_instruction(language)

    # Use the legacy prompt inline (simplified)
    system_prompt = (
        "You are a premium stock trading analyst for Tradeul. "
        "Respond with structured markdown. Use ## headers, tables, bullet points. "
        f"{language_instruction} "
        "ONLY use data from agent_results. NEVER hallucinate. Keep response under 2000 words."
    )

    user_payload = {
        "query": query,
        "language": language,
        "market_session": market_session,
        "agent_results": results_payload,
    }
    if ticker_info:
        user_payload["ticker_info"] = {
            t: {"company_name": info.get("company_name", ""), "sector": info.get("sector", "")}
            for t, info in ticker_info.items()
        }
    if chart_context:
        user_payload["chart_context"] = chart_context

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(user_payload, ensure_ascii=False, default=str)),
    ]

    response = await llm_invoke_with_retry(llm, messages)
    text = response.content or ""
    text = re.sub(r' {3,}', ' ', text)
    text = re.sub(r'\n{4,}', '\n\n', text)
    return text.strip()[:15_000]


# ── Main node ────────────────────────────────────────────────────

async def synthesizer_node(state: dict) -> dict:
    """Synthesize all agent results into a structured JSON response."""
    start_time = time.time()

    query = state.get("query", "")
    agent_results = state.get("agent_results", {})
    language = state.get("language", "en")
    ticker_info = state.get("ticker_info", {})

    # ── Backtest fast-path (unchanged) ──
    bt_result = agent_results.get("backtest", {})
    if isinstance(bt_result, dict) and bt_result.get("status") == "success":
        bt_data = bt_result.get("backtest_result", {})
        cm = bt_data.get("core_metrics", {})
        strategy = bt_data.get("strategy_config") or bt_result.get("strategy_config", {})
        name = strategy.get("name", "Strategy")
        trades = cm.get("total_trades", 0)
        ret = cm.get("total_return_pct", 0)
        sharpe = cm.get("sharpe_ratio", 0)
        dd = cm.get("max_drawdown_pct", 0)
        wr = cm.get("win_rate", 0)
        elapsed_ms = int((time.time() - start_time) * 1000)

        if language == "es":
            summary = (
                f"Backtest completado: **{name}** - "
                f"{trades} operaciones, retorno {ret:+.1f}%, "
                f"Sharpe {sharpe:.2f}, Max DD {dd:.1f}%, Win Rate {wr*100:.0f}%. "
                f"Los resultados detallados se muestran en el panel interactivo."
            )
        else:
            summary = (
                f"Backtest complete: **{name}** - "
                f"{trades} trades, return {ret:+.1f}%, "
                f"Sharpe {sharpe:.2f}, Max DD {dd:.1f}%, Win Rate {wr*100:.0f}%. "
                f"Detailed results are shown in the interactive panel."
            )

        return {
            "final_response": summary,
            "execution_metadata": {
                **(state.get("execution_metadata", {})),
                "synthesizer": {
                    "elapsed_ms": elapsed_ms,
                    "result_agents": list(agent_results.keys()),
                    "response_length": len(summary),
                    "language": language,
                    "backtest_fast_path": True,
                },
            },
        }

    bt_status = bt_result.get("status") if isinstance(bt_result, dict) else None
    if bt_status in ("info", "needs_tickers", "too_many_tickers"):
        msg = bt_result.get("message", "")
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "final_response": msg,
            "execution_metadata": {
                **(state.get("execution_metadata", {})),
                "synthesizer": {"elapsed_ms": elapsed_ms, "language": language, "backtest_validation": bt_status},
            },
        }

    if isinstance(bt_result, dict) and bt_status == "error":
        error_msg = bt_result.get("error", "Error desconocido")
        elapsed_ms = int((time.time() - start_time) * 1000)
        if language == "es":
            helpful_suffix = (
                "\n\n**Consejos:**\n"
                "- Asegúrate de especificar tickers concretos (máx 3): ej. SPY, AAPL\n"
                "- Para intradía, usa un rango de máximo 60 días\n"
                "- Ejemplo: \"backtest RSI < 30 en SPY de 2023 a 2024\""
            )
        else:
            helpful_suffix = (
                "\n\n**Tips:**\n"
                "- Make sure to specify concrete tickers (max 3): e.g. SPY, AAPL\n"
                "- For intraday, use a max 60-day range\n"
                "- Example: \"backtest RSI < 30 on SPY from 2023 to 2024\""
            )
        return {
            "final_response": f"Error en backtest: {error_msg}{helpful_suffix}",
            "execution_metadata": {
                **(state.get("execution_metadata", {})),
                "synthesizer": {"elapsed_ms": elapsed_ms, "language": language},
            },
        }

    # ── Prepare payload ──
    results_payload = _prepare_results_payload(agent_results)
    payload_size = _safe_json_size(results_payload)
    logger.info("Synthesizer payload: %d chars for %d agents", payload_size, len(results_payload))

    market_session = {}
    for agent_key in ("market_data", "news_events"):
        agent_out = results_payload.get(agent_key, {})
        if isinstance(agent_out, dict) and agent_out.get("market_session"):
            market_session = agent_out["market_session"]
            break
    if not market_session:
        market_session = state.get("market_context", {})

    chart_context = state.get("chart_context")

    # ── Primary: structured output with Gemini 2.5 Flash ──
    structured_response: SynthesizerResponse | None = None
    used_fallback = False

    try:
        structured_response = await _synthesize_structured(
            query, language, results_payload, market_session, ticker_info, chart_context,
        )
        logger.info(
            "Synthesizer: structured output OK — %d sections, metrics=%s",
            len(structured_response.sections),
            structured_response.metrics is not None,
        )
    except Exception as exc:
        logger.warning("Synthesizer: structured output failed, falling back to markdown: %s", exc)
        used_fallback = True

    # ── Build final_response ──
    if structured_response:
        final_response = _structured_to_markdown(structured_response)
        structured_data = structured_response.model_dump(mode="json")
    else:
        final_response = await _synthesize_fallback(
            query, language, results_payload, market_session, ticker_info, chart_context,
        )
        structured_data = None

    elapsed_ms = int((time.time() - start_time) * 1000)

    result: dict[str, Any] = {
        "final_response": final_response,
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "synthesizer": {
                "elapsed_ms": elapsed_ms,
                "result_agents": list(agent_results.keys()),
                "response_length": len(final_response),
                "payload_size": payload_size,
                "language": language,
                "structured": structured_response is not None,
                "fallback": used_fallback,
            },
        },
    }

    if structured_data:
        result["structured_response"] = structured_data

    return result
