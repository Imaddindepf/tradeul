"""
Embeddings para la memoria semántica (Fase 4a).

Genera vectores con gemini-embedding-001 recortados a 768 dims (HNSW de
pgvector indexa hasta 2000) y normalizados en cliente (con
output_dimensionality < 3072 Gemini NO normaliza — sin esto el coseno
mentiría). Fail-safe: cualquier error devuelve None y el caller cae a la
búsqueda por keywords, nunca rompe el flujo.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os

logger = logging.getLogger(__name__)

EMBED_MODEL = os.getenv("MEMORY_EMBED_MODEL", "gemini-embedding-001")
EMBED_DIMS = int(os.getenv("MEMORY_EMBED_DIMS", "768"))

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client()
    return _client


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in values)) or 1.0
    return [x / norm for x in values]


async def embed_texts(
    texts: list[str],
    *,
    task_type: str = "RETRIEVAL_DOCUMENT",
    timeout: float = 20.0,
) -> list[list[float]] | None:
    """Embeddings normalizados de una lista de textos. None si falla."""
    if not texts:
        return []
    try:
        from google.genai import types
        client = _get_client()
        resp = await asyncio.wait_for(
            client.aio.models.embed_content(
                model=EMBED_MODEL,
                contents=[(t or " ")[:2000] for t in texts],
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=EMBED_DIMS,
                ),
            ),
            timeout=timeout,
        )
        return [_normalize(list(e.values)) for e in resp.embeddings]
    except Exception as exc:  # noqa: BLE001
        logger.warning("embed_texts failed (%d texts): %s", len(texts), exc)
        return None


async def embed_query(text: str) -> list[float] | None:
    """Embedding de una query de búsqueda (task_type asimétrico)."""
    out = await embed_texts([text], task_type="RETRIEVAL_QUERY", timeout=10.0)
    return out[0] if out else None


def to_pgvector(values: list[float]) -> str:
    """Literal pgvector: '[0.1,0.2,...]' (se castea con ::vector en SQL)."""
    return "[" + ",".join(f"{x:.6f}" for x in values) + "]"
