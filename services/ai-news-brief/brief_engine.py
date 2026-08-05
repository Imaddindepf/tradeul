"""
Brief Engine — Claude Opus 4.8 (loop agéntico)

Genera un Brief de Contexto Fundamental de una noticia. El modelo decide, según
el TIPO de catalizador, qué herramientas usar:
  - Tools internas de Tradeul (fundamentales / analistas / caja-dilución), en
    paralelo, SIN revelar el proveedor de los datos.
  - Web search (server tool) para el catalizador concreto + frescura + citas.
  - Extended thinking adaptativo + prompt caching de la metodología.

Defensivo: si la API rechaza una feature, degrada (internal -> web -> thinking).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import httpx

from config import settings
from tools import anthropic_tool_defs, execute_tool, TOOL_REGISTRY

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

STATIC_INSTRUCTIONS = """\
You are Tradeul's fundamental-context analyst. Your job: when a market news
item arrives, explain INSTANTLY the CONTEXT it appears in and WHAT CHANGES in
the company's fundamentals, so a trader understands it in seconds and can
position with judgment.

THE NEWS IS OURS AND ARRIVES FIRST. The news I pass you comes from Tradeul's
real-time feed: it is the PRIMARY, truthful SOURCE, and we almost always have
it BEFORE it appears on the public web. Therefore:
- Treat it as a FACT that already happened. Do NOT "verify" it or doubt it; do
  not search the web to confirm whether it happened.
- If the web does not carry it yet, that is NORMAL (we run ahead): never say
  "it cannot be verified" and never treat it as a rumor because of that.
- Your goal is NOT to discover the news, but to give CONTEXT for what we are
  already seeing: what the company is, the catalyst's background, what it implies.

Do NOT analyze technical metrics (RVOL, VWAP, ATR, levels): the trader already
has them. Do NOT give entry/exit signals or position sizing.

TOOLS. You have Tradeul internal data and web search. The web is for CONTEXT
and background (not for finding/confirming the news, which we already have).
Before writing, decide what you need based on the TYPE of catalyst:
- QUALITATIVE catalyst (DOJ/SEC investigation, lawsuit, regulation/FDA, M&A,
  appointments, rumor, geopolitics): prioritize WEB SEARCH to understand the
  context, background and implications. You normally do NOT need the internal
  financial metrics.
- FINANCIAL catalyst (earnings, guidance, offering/raise, debt, buyback,
  dividend, material contract): request IN PARALLEL the relevant internal
  tools (fundamentals, analysts, cash/dilution) AND search the web for the
  specific catalyst.
Call several tools at once when they add value. If one returns an error or
empty, say so or look it up on the web; NEVER invent figures. NEVER mention
where the data comes from: it is simply "Tradeul internal data".

Respond in Markdown, concise and actionable. Do NOT include preambles,
greetings or meta-comments: start DIRECTLY with "## TL;DR".
Use EXACTLY these sections (headings verbatim):

## TL;DR
One or two sentences: which fundamental changes and how much it matters (High/Medium/Low).

## The company
What it does, sector, approximate size and how it was doing before this news.

## The news, decoded
What the headline really says in plain language. Separate substance from marketing.

## What changes in the fundamentals
The core. Classify the type of change (revenue / capital structure /
cash-survival / regulatory-legal / strategic / narrative-hype) and its
magnitude. Explicitly flag dilution risk if the pattern fits.

## Background
How we got here: does this continue a prior story? Relevant context.

## What to watch
Upcoming fundamental milestones that would confirm or negate the change.

## Sources
List of the web sources used (title + link)."""

FOLLOWUP_INSTRUCTIONS = """\
You are continuing a conversation about the fundamental context of a news item.
Answer the user's question directly and conversationally (do not repeat the
brief's section format unless asked). Use the same internal tools and web
search when needed, with the same criterion: qualitative via web, financial
via internal tools. Cite web sources. Never invent data and never reveal where
the data comes from."""


@lru_cache(maxsize=1)
def _load_methodology() -> str:
    for path in (settings.methodology_path, settings.methodology_fallback):
        try:
            if path and os.path.exists(path):
                with open(path, "r", encoding="utf-8") as fh:
                    text = fh.read().strip()
                if text:
                    logger.info("methodology_loaded path=%s chars=%d", path, len(text))
                    return text
        except Exception as exc:  # noqa: BLE001
            logger.warning("methodology_read_failed path=%s err=%s", path, exc)
    logger.warning("methodology_not_found, using minimal lens")
    return "Focus: explain what changes in the company's fundamentals."


def _build_user_prompt(news: Dict[str, Any]) -> str:
    tickers = news.get("tickers") or []
    ticker_str = ", ".join(f"${t}" for t in tickers) if tickers else "(no explicit ticker)"
    when = news.get("created_at") or news.get("received_at") or ""
    text = (news.get("text") or "").strip()
    return (
        f"NEWS (tickers: {ticker_str}; time: {when}):\n"
        f"\"\"\"\n{text}\n\"\"\"\n\n"
        f"Generate the Fundamental Context Brief following the indicated structure."
    )


def _build_system(followup: bool) -> List[Dict[str, Any]]:
    methodology = _load_methodology()
    head = FOLLOWUP_INSTRUCTIONS if followup else STATIC_INSTRUCTIONS
    return [
        {"type": "text", "text": head},
        {
            "type": "text",
            "text": "METODOLOGÍA / LENTE DEL TRADER:\n\n" + methodology,
            "cache_control": {"type": "ephemeral"},
        },
    ]


def _build_tools(use_web: bool, use_internal: bool) -> List[Dict[str, Any]]:
    tools: List[Dict[str, Any]] = []
    if use_internal and settings.internal_tools_enabled:
        tools.extend(anthropic_tool_defs())
    if use_web and settings.web_search_enabled:
        tools.append({
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": settings.web_search_max_uses,
        })
    return tools


def _build_body(messages: List[Dict[str, Any]], *, use_web: bool, use_thinking: bool,
                use_internal: bool, followup: bool) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "model": settings.anthropic_model,
        "max_tokens": settings.max_tokens,
        "system": _build_system(followup),
        "messages": messages,
    }
    if use_thinking and settings.thinking_enabled:
        body["thinking"] = {"type": "adaptive"}
        body["output_config"] = {"effort": settings.effort}
    tools = _build_tools(use_web, use_internal)
    if tools:
        body["tools"] = tools
    return body


def _collect_sources(content: List[Dict[str, Any]], seen: set, sources: List[Dict[str, str]]) -> None:
    for block in content:
        btype = block.get("type")
        if btype == "text":
            for cit in block.get("citations") or []:
                url = cit.get("url")
                if url and url not in seen:
                    seen.add(url)
                    sources.append({"url": url, "title": cit.get("title") or url})
        elif btype == "web_search_tool_result":
            for res in block.get("content") or []:
                if isinstance(res, dict) and res.get("type") == "web_search_result":
                    url = res.get("url")
                    if url and url not in seen:
                        seen.add(url)
                        sources.append({"url": url, "title": res.get("title") or url})


def _final_text(content: List[Dict[str, Any]]) -> str:
    return "\n".join(b.get("text", "") for b in content if b.get("type") == "text").strip()


def _custom_tool_calls(content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [b for b in content if b.get("type") == "tool_use" and b.get("name") in TOOL_REGISTRY]


class _ApiError(Exception):
    def __init__(self, status: int, text: str):
        self.status = status
        self.text = text
        super().__init__(f"{status}: {text[:300]}")


async def _post(client: httpx.AsyncClient, headers: Dict[str, str], body: Dict[str, Any]) -> Dict[str, Any]:
    resp = await client.post(ANTHROPIC_URL, headers=headers, json=body)
    if resp.status_code == 200:
        return resp.json()
    raise _ApiError(resp.status_code, resp.text)


async def _run_loop(client: httpx.AsyncClient, headers: Dict[str, str],
                    messages: List[Dict[str, Any]], opts: Dict[str, bool],
                    followup: bool) -> Dict[str, Any]:
    """Ejecuta el loop agéntico con flags de features fijos. Lanza _ApiError."""
    seen: set = set()
    sources: List[Dict[str, str]] = []
    tools_used: List[str] = []
    last_usage: Dict[str, Any] = {}
    final_md = ""

    for turn in range(settings.max_tool_iterations + 1):
        body = _build_body(messages, use_web=opts["use_web"], use_thinking=opts["use_thinking"],
                            use_internal=opts["use_internal"], followup=followup)
        data = await _post(client, headers, body)
        content = data.get("content", [])
        last_usage = data.get("usage", {}) or {}
        _collect_sources(content, seen, sources)
        stop = data.get("stop_reason")

        calls = _custom_tool_calls(content)
        if calls:
            # Echo del turno del asistente (incluye thinking + tool_use, verbatim).
            messages.append({"role": "assistant", "content": content})
            # Ejecutar todas las tools en PARALELO.
            results = await asyncio.gather(*[
                execute_tool(c["name"], c.get("input") or {}) for c in calls
            ])
            tool_result_blocks = []
            for c, res in zip(calls, results):
                tools_used.append(c["name"])
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": c["id"],
                    "content": json.dumps(res, ensure_ascii=False),
                })
            messages.append({"role": "user", "content": tool_result_blocks})
            continue

        if stop == "pause_turn":
            # Web search larga: reanudar el turno enviando el contenido de vuelta.
            messages.append({"role": "assistant", "content": content})
            continue

        # Turno final.
        final_md = _final_text(content)
        break

    return {
        "brief_markdown": final_md,
        "sources": sources,
        "model": settings.anthropic_model,
        "tools_used": tools_used,
        "usage": {
            "input_tokens": last_usage.get("input_tokens"),
            "output_tokens": last_usage.get("output_tokens"),
            "cache_read_input_tokens": last_usage.get("cache_read_input_tokens"),
            "cache_creation_input_tokens": last_usage.get("cache_creation_input_tokens"),
        },
    }


# Orden de degradación de features ante rechazos 400/404 de la API.
_DEGRADE_LADDER = [
    {"use_web": True, "use_internal": True, "use_thinking": True},
    {"use_web": True, "use_internal": True, "use_thinking": False},
    {"use_web": True, "use_internal": False, "use_thinking": True},
    {"use_web": True, "use_internal": False, "use_thinking": False},
    {"use_web": False, "use_internal": False, "use_thinking": False},
]


async def _generate(initial_messages_factory) -> Dict[str, Any]:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY no configurada")

    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": settings.anthropic_version,
        "content-type": "application/json",
    }
    followup = initial_messages_factory.__name__ == "_fu"

    last_error: Optional[str] = None
    async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
        for i, opts in enumerate(_DEGRADE_LADDER):
            messages = initial_messages_factory()  # fresh copy per attempt
            try:
                result = await _run_loop(client, headers, messages, opts, followup)
                result["degraded"] = i > 0
                result["features"] = opts
                logger.info("brief_ok attempt=%d opts=%s tools=%s usage=%s",
                            i, opts, result.get("tools_used"), result.get("usage"))
                return result
            except _ApiError as exc:
                last_error = str(exc)
                if exc.status in (400, 404):
                    logger.warning("anthropic_feature_rejected attempt=%d %s", i, exc)
                    continue
                logger.error("anthropic_fatal %s", exc)
                break
            except httpx.HTTPError as exc:
                last_error = f"network: {exc}"
                logger.warning("anthropic_network_error attempt=%d err=%s", i, exc)
                continue

    raise RuntimeError(f"Anthropic request failed: {last_error}")


async def generate_brief(news: Dict[str, Any]) -> Dict[str, Any]:
    """Primer turno: genera el brief de contexto de una noticia."""
    def _factory():
        return [{"role": "user", "content": _build_user_prompt(news)}]
    return await _generate(_factory)


async def continue_conversation(news: Dict[str, Any], history: List[Dict[str, Any]],
                                user_message: str) -> Dict[str, Any]:
    """
    Follow-up en el mismo hilo. `history` son turnos previos en formato
    [{role, content(str)}]. Mantiene el contexto de la noticia.
    """
    def _fu():
        msgs: List[Dict[str, Any]] = [{
            "role": "user",
            "content": "CONTEXTO (noticia original):\n" + _build_user_prompt(news),
        }]
        for h in history:
            role = h.get("role")
            text = h.get("content")
            if role in ("user", "assistant") and isinstance(text, str) and text.strip():
                msgs.append({"role": role, "content": text})
        msgs.append({"role": "user", "content": user_message})
        return msgs
    return await _generate(_fu)
