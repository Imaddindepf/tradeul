"""
Brief-thread follow-up router.

Los threads que nacen de un "Contexto de noticia" (ai-news-brief / Opus)
son conversacionales por diseño, pero un follow-up puede pedir datos live
de mercado ("qué stocks suben hoy con este catalizador") que ese motor no
puede responder: solo tiene web search + 3 tools de fundamentales por
ticker — ni scanner, ni snapshot enriched, ni screener.

Este módulo decide, por follow-up, si la pregunta necesita el grafo
completo del agente (65 tools MCP) o puede quedarse en el motor de briefs.

Clasificación: LLM fast (Gemini Flash, temp 0) con fallback a heurística
de keywords si el LLM falla. Fail-safe: ante la duda se queda en el brief
(comportamiento previo), nunca rompe el flujo.
"""
from __future__ import annotations

import logging
import re

from agents._when import SESSION_PHRASES

logger = logging.getLogger(__name__)

# Señales fuertes de datos live de mercado (fallback sin LLM).
# Las frases de sesión vienen del vocabulario compartido: aquí sólo estaban
# 'after\\s*hours', que no casa con "after hour" en singular.
_SESSION_ALT = "|".join(re.escape(p) for p in sorted(SESSION_PHRASES, key=len, reverse=True))

_LIVE_DATA_RE = re.compile(
    r"(?ix)\b("
    r"suben?|bajan?|caen?|cayendo|subiendo|"
    r"movers?|gappers?|screener?|scanner|snapshot|"
    r"top\s*\d+|ranking|rvol|volumen\s+(?:relativo|inusual)|"
    + _SESSION_ALT + r"|"
    r"precio\s+(?:ahora|actual)|cotiza(?:n|ndo)?\s+(?:ahora|hoy)|"
    r"se\s+(?:mueven?|est[aá]n?\s+moviendo)"
    r")\b"
)

_CLASSIFIER_PROMPT = """Eres un router binario para una plataforma de trading.

Un usuario está conversando sobre una noticia y hace una pregunta de seguimiento.
Decide si responderla BIEN exige datos de mercado EN TIEMPO REAL de la plataforma
(precios/movimientos de HOY, listas de acciones que suben o bajan ahora, rankings,
volumen, gappers, screeners) o si es una pregunta conversacional/analítica sobre
la noticia (implicaciones, fundamentales, quién se beneficia a futuro, contexto).

Pregunta: {query}

Responde EXACTAMENTE una palabra:
LIVE  -> exige datos de mercado en tiempo real de la plataforma
CHAT  -> conversacional/analítica, no necesita datos live"""


async def needs_live_market_data(query: str) -> bool:
    """True si el follow-up necesita el grafo completo (datos live).

    Dos etapas:
      1. Regex de señales fuertes → LIVE inmediato (sin coste ni latencia).
      2. Casos sin señal clara → LLM fast. Solo se acepta un veredicto
         explícito (LIVE/CHAT en la respuesta); respuesta vacía o ambigua
         (p.ej. thinking-tokens agotando max_tokens) o error → CHAT, el
         comportamiento previo (fail-safe: nunca rompe el flujo del brief).
    """
    q = (query or "").strip()
    if not q:
        return False

    if _LIVE_DATA_RE.search(q):
        logger.info("brief_router: heuristic verdict=LIVE query=%r", q[:80])
        return True

    try:
        from agents._make_llm import make_llm

        llm = make_llm(tier="fast", temperature=0.0, max_tokens=256)
        result = await llm.ainvoke(_CLASSIFIER_PROMPT.format(query=q[:500]))
        text = (getattr(result, "content", "") or "").strip().upper()
        if "LIVE" in text:
            verdict = True
        elif "CHAT" in text:
            verdict = False
        else:
            logger.warning(
                "brief_router: unparseable LLM output %r — defaulting to CHAT", text[:60],
            )
            verdict = False
        logger.info(
            "brief_router: llm verdict=%s query=%r", "LIVE" if verdict else "CHAT", q[:80],
        )
        return verdict
    except Exception as exc:  # noqa: BLE001
        logger.warning("brief_router: LLM failed (%s) — defaulting to CHAT", exc)
        return False
