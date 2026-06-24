"""
Cliente para el servicio ai-news-brief (Brief de Contexto Fundamental, Opus 4.8).

ai-news-brief corre en network_mode host; este servicio (ai_agent_v4) está en
la red bridge, así que lo alcanza vía host-gateway (NEWS_BRIEF_URL).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

NEWS_BRIEF_URL = os.getenv("NEWS_BRIEF_URL", "http://host.docker.internal:8072")
_TIMEOUT = httpx.Timeout(240.0, connect=5.0)

_client: Optional[httpx.AsyncClient] = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=_TIMEOUT, base_url=NEWS_BRIEF_URL)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


async def generate_brief(news: dict[str, Any]) -> dict[str, Any]:
    """Primer turno: brief de contexto de la noticia."""
    client = await _get_client()
    resp = await client.post("/api/v1/brief", json=news)
    resp.raise_for_status()
    return resp.json()


async def followup(news: dict[str, Any], history: list[dict[str, str]], message: str) -> dict[str, Any]:
    """Follow-up en el mismo hilo, manteniendo el contexto de la noticia."""
    client = await _get_client()
    resp = await client.post(
        "/api/v1/followup",
        json={"news": news, "history": history, "message": message},
    )
    resp.raise_for_status()
    return resp.json()
