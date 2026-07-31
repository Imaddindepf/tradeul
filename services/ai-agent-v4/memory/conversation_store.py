"""
ConversationStore — persistencia durable del historial de conversaciones
en Postgres (TimescaleDB), fuente de verdad del historial del AI Agent.

Contexto: hasta julio de 2026 el historial vivía solo en Redis (DB 5), con
lista capada a 200 mensajes y sin durabilidad garantizada. Además, antes de
introducir la autenticación Clerk todas las conversaciones se guardaban bajo
el user_id literal "default". Este store:

  - Persiste threads y mensajes en Postgres sin caps ni caducidad.
  - Ejecuta al arrancar un backfill idempotente desde Redis (una sola vez,
    con marker en `agent_conv_migrations`), incluyendo los threads legacy
    de "default" (marcados legacy=TRUE: preservados pero no atribuibles).

Misma infraestructura que RunStore/AlertStore: pool psycopg 3 async sobre
CHECKPOINT_DB_URL, no-fatal — si Postgres no está disponible, MemoryManager
degrada al camino Redis existente.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional


def _semantic_enabled() -> bool:
    """Flag de la memoria semántica (Fase 4a). Default ON — todo fallo de
    embeddings/pgvector cae solo a keywords, así que activarla es seguro."""
    return os.getenv("MEMORY_SEMANTIC", "1").strip().lower() not in ("0", "false", "off")

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_conversations (
    user_id    TEXT NOT NULL,
    thread_id  TEXT NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    last_query TEXT NOT NULL DEFAULT '',
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL,
    legacy     BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (user_id, thread_id)
);
CREATE INDEX IF NOT EXISTS idx_agent_conv_user_updated
    ON agent_conversations (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS agent_conv_messages (
    id        BIGSERIAL PRIMARY KEY,
    user_id   TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    ts        DOUBLE PRECISION NOT NULL,
    query     TEXT NOT NULL DEFAULT '',
    response  TEXT NOT NULL DEFAULT '',
    tickers   JSONB,
    intent    TEXT,
    agent_results_summary JSONB,
    structured_response   JSONB
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_conv_msg
    ON agent_conv_messages (user_id, thread_id, ts);

CREATE TABLE IF NOT EXISTS agent_conv_migrations (
    name       TEXT PRIMARY KEY,
    applied_at DOUBLE PRECISION NOT NULL
);
"""

_REDIS_BACKFILL_MARKER = "redis_backfill_v1"


class ConversationStore:
    """Store Postgres de threads + mensajes de conversación (psycopg 3 pool)."""

    def __init__(self, db_url: Optional[str] = None) -> None:
        self._db_url = db_url or os.getenv("CHECKPOINT_DB_URL", "").strip()
        self._pool = None
        self._ready = False

    @property
    def available(self) -> bool:
        return self._ready

    async def init(self) -> None:
        if not self._db_url:
            logger.warning("ConversationStore disabled: CHECKPOINT_DB_URL not set")
            return
        try:
            from psycopg_pool import AsyncConnectionPool

            self._pool = AsyncConnectionPool(
                self._db_url,
                min_size=1,
                max_size=3,
                open=False,
                check=AsyncConnectionPool.check_connection,
                kwargs={"autocommit": True},
            )
            await self._pool.open(wait=True, timeout=15)
            async with self._pool.connection() as conn:
                await conn.execute(_SCHEMA)
            self._ready = True
            logger.info("ConversationStore ready (agent_conversations / agent_conv_messages)")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ConversationStore unavailable (%s) — history falls back to Redis", exc,
            )
            self._pool = None
            self._ready = False

    async def close(self) -> None:
        if self._pool is not None:
            try:
                await self._pool.close()
            except Exception:  # noqa: BLE001
                pass
            self._pool = None
            self._ready = False

    # ── Escritura ────────────────────────────────────────────────

    async def store_turn(
        self,
        user_id: str,
        thread_id: str,
        query: str,
        response: str,
        *,
        ts: Optional[float] = None,
        agent_results_summary: Optional[dict[str, Any]] = None,
        structured_response: Optional[dict[str, Any]] = None,
        tickers: Optional[list[str]] = None,
        intent: Optional[str] = None,
        legacy: bool = False,
    ) -> bool:
        """Inserta un turno (query/response) y actualiza el índice del thread.

        Returns True si se persistió en Postgres.
        """
        if not self._ready:
            return False
        now = ts if ts is not None else time.time()
        try:
            async with self._pool.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO agent_conv_messages
                        (user_id, thread_id, ts, query, response,
                         tickers, intent, agent_results_summary, structured_response)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb)
                    ON CONFLICT (user_id, thread_id, ts) DO NOTHING
                    """,
                    (
                        user_id, thread_id, now, query, response,
                        _jsonb(tickers), intent,
                        _jsonb(agent_results_summary), _jsonb(structured_response),
                    ),
                )
                await conn.execute(
                    """
                    INSERT INTO agent_conversations
                        (user_id, thread_id, title, last_query, created_at, updated_at, legacy)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, thread_id) DO UPDATE SET
                        last_query = EXCLUDED.last_query,
                        updated_at = GREATEST(agent_conversations.updated_at, EXCLUDED.updated_at)
                    """,
                    (user_id, thread_id, query[:200], query[:200], now, now, legacy),
                )
            # Fase 4a: embedding en background — nunca bloquea ni rompe el turno.
            if _semantic_enabled():
                try:
                    asyncio.get_running_loop().create_task(
                        self._embed_turn(user_id, thread_id, now, query, response),
                    )
                except RuntimeError:
                    pass  # sin loop (scripts síncronos): lo cubrirá el backfill
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("ConversationStore.store_turn failed: %s", exc)
            return False

    async def _embed_turn(
        self, user_id: str, thread_id: str, ts: float, query: str, response: str,
    ) -> None:
        """Calcula y persiste el embedding de un turno recién guardado."""
        try:
            from memory.embeddings import embed_texts, to_pgvector
            vecs = await embed_texts([f"{query}\n{(response or '')[:1500]}"])
            if not vecs:
                return
            async with self._pool.connection() as conn:
                await conn.execute(
                    """
                    UPDATE agent_conv_messages SET embedding = %s::vector
                    WHERE user_id = %s AND thread_id = %s AND ts = %s
                    """,
                    (to_pgvector(vecs[0]), user_id, thread_id, ts),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("embed_turn failed (thread=%s): %s", thread_id, exc)

    # ── Lectura ──────────────────────────────────────────────────

    async def get_history(
        self, user_id: str, thread_id: str, limit: int = 20,
    ) -> Optional[list[dict[str, Any]]]:
        """Últimos `limit` turnos del thread, en orden cronológico.

        Returns None si Postgres no está disponible o falla (para que el
        caller pueda degradar a Redis); [] si el thread no tiene mensajes.
        """
        if not self._ready:
            return None
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    """
                    SELECT ts, query, response, tickers, intent,
                           agent_results_summary, structured_response
                    FROM (
                        SELECT * FROM agent_conv_messages
                        WHERE user_id = %s AND thread_id = %s
                        ORDER BY ts DESC LIMIT %s
                    ) sub
                    ORDER BY ts ASC
                    """,
                    (user_id, thread_id, limit),
                )
                rows = await cur.fetchall()
            return [_row_to_entry(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            logger.warning("ConversationStore.get_history failed: %s", exc)
            return None

    async def list_threads(
        self, user_id: str, limit: int = 10,
    ) -> Optional[list[dict[str, Any]]]:
        """Threads del usuario, más reciente primero. None si PG no disponible."""
        if not self._ready:
            return None
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    """
                    SELECT thread_id, last_query, updated_at
                    FROM agent_conversations
                    WHERE user_id = %s AND NOT legacy
                    ORDER BY updated_at DESC LIMIT %s
                    """,
                    (user_id, limit),
                )
                rows = await cur.fetchall()
            return [
                {"thread_id": r[0], "last_query": r[1], "updated_at": r[2]}
                for r in rows
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("ConversationStore.list_threads failed: %s", exc)
            return None

    async def search_messages(
        self, user_id: str, query: str, limit: int = 5,
    ) -> Optional[list[dict[str, Any]]]:
        """Búsqueda sobre los mensajes del usuario.

        Fase 4a: primero SEMÁNTICA (pgvector, coseno con umbral) — entiende
        significado, no tokens: es la clase de fallo del recall por keywords
        (caso "aranceles" 2026-07-22) la que esto elimina. Si los embeddings
        fallan o no hay hits sobre el umbral, cae a keywords (ILIKE por token,
        el comportamiento histórico).

        Devuelve hits con el mismo shape que search_memory() de MemoryManager
        (source=conversation). None si PG no disponible.
        """
        if not self._ready:
            return None

        if _semantic_enabled():
            try:
                hits = await self._search_semantic(user_id, query, limit)
                if hits:
                    return hits
            except Exception as exc:  # noqa: BLE001
                logger.warning("semantic search failed — keyword fallback: %s", exc)
        tokens = [t for t in query.lower().split() if len(t) >= 3][:8]
        if not tokens:
            return []
        # Un OR por token; el score es la fracción de tokens que aparecen.
        conds = " OR ".join(
            ["(query ILIKE %s OR response ILIKE %s)"] * len(tokens)
        )
        params: list[Any] = [user_id]
        for t in tokens:
            like = f"%{t}%"
            params.extend([like, like])
        params.append(limit * 4)  # sobre-muestrear para poder puntuar
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    f"""
                    SELECT thread_id, ts, query, response
                    FROM agent_conv_messages
                    WHERE user_id = %s AND ({conds})
                    ORDER BY ts DESC LIMIT %s
                    """,
                    params,
                )
                rows = await cur.fetchall()
            hits: list[dict[str, Any]] = []
            for thread_id, ts, q, resp in rows:
                text = f"{q} {resp}".lower()
                overlap = sum(1 for t in tokens if t in text)
                hits.append({
                    "source": "conversation",
                    "thread_id": thread_id,
                    "content": (q or "")[:300],
                    "response_snippet": (resp or "")[:300],
                    "score": round(overlap / len(tokens), 3),
                    "timestamp": ts,
                })
            hits.sort(key=lambda h: (-h["score"], -h["timestamp"]))
            return hits[:limit]
        except Exception as exc:  # noqa: BLE001
            logger.warning("ConversationStore.search_messages failed: %s", exc)
            return None

    # ── Borrado ──────────────────────────────────────────────────

    async def _search_semantic(
        self, user_id: str, query: str, limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Búsqueda por similitud coseno sobre pgvector.

        Solo devuelve hits con score >= MEMORY_SEMANTIC_MIN_SCORE (el top-N de
        coseno SIEMPRE devuelve algo aunque sea irrelevante — sin umbral, la
        memoria inyectaría ruido en el planner). Lista vacía → keyword fallback.
        """
        from memory.embeddings import embed_query, to_pgvector

        vec = await embed_query(query)
        if not vec:
            return []
        vec_lit = to_pgvector(vec)
        min_score = float(os.getenv("MEMORY_SEMANTIC_MIN_SCORE", "0.60"))
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT thread_id, ts, query, response,
                       1 - (embedding <=> %s::vector) AS score
                FROM agent_conv_messages
                WHERE user_id = %s AND embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vec_lit, user_id, vec_lit, limit * 2),
            )
            rows = await cur.fetchall()
        hits: list[dict[str, Any]] = []
        for thread_id, ts, q, resp, score in rows:
            if score is None or float(score) < min_score:
                continue
            hits.append({
                "source": "conversation",
                "thread_id": thread_id,
                "content": (q or "")[:300],
                "response_snippet": (resp or "")[:300],
                "score": round(float(score), 3),
                "timestamp": ts,
            })
            if len(hits) >= limit:
                break
        return hits

    async def delete_thread(self, user_id: str, thread_id: str) -> bool:
        if not self._ready:
            return False
        try:
            async with self._pool.connection() as conn:
                await conn.execute(
                    "DELETE FROM agent_conv_messages WHERE user_id = %s AND thread_id = %s",
                    (user_id, thread_id),
                )
                await conn.execute(
                    "DELETE FROM agent_conversations WHERE user_id = %s AND thread_id = %s",
                    (user_id, thread_id),
                )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("ConversationStore.delete_thread failed: %s", exc)
            return False

    # ── Backfill desde Redis (una sola vez) ──────────────────────

    async def backfill_from_redis(self, redis) -> None:
        """Migra el historial existente en Redis a Postgres.

        Idempotente a dos niveles: marker en agent_conv_migrations (no se
        re-ejecuta) y ON CONFLICT DO NOTHING por mensaje (re-ejecutable sin
        duplicar si se borra el marker). Los threads del user_id "default"
        (era pre-auth) se marcan legacy=TRUE: quedan preservados pero fuera
        de los listados (no son atribuibles a un usuario concreto).
        """
        if not self._ready:
            return
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT 1 FROM agent_conv_migrations WHERE name = %s",
                    (_REDIS_BACKFILL_MARKER,),
                )
                if await cur.fetchone() is not None:
                    return  # ya migrado

            import orjson

            threads_migrated = 0
            messages_migrated = 0

            cursor: int | bytes = 0
            conv_keys: list[str] = []
            while True:
                cursor, keys = await redis.scan(
                    cursor=cursor, match="memory:conversations:*", count=200,
                )
                conv_keys.extend(
                    k.decode() if isinstance(k, bytes) else k for k in keys
                )
                if cursor == 0:
                    break

            for key in conv_keys:
                # memory:conversations:{user_id}:{thread_id}
                parts = key.split(":", 3)
                if len(parts) != 4:
                    logger.warning("backfill: skipping unparseable key %s", key)
                    continue
                _, _, user_id, thread_id = parts
                legacy = user_id == "default"

                raw_entries = await redis.lrange(key, 0, -1)
                last_ts = 0.0
                for raw in raw_entries:
                    try:
                        entry = orjson.loads(raw)
                    except Exception:  # noqa: BLE001
                        continue
                    ts = float(entry.get("timestamp") or 0.0)
                    ok = await self.store_turn(
                        user_id,
                        thread_id,
                        entry.get("query") or "",
                        entry.get("response") or "",
                        ts=ts,
                        agent_results_summary=entry.get("agent_results_summary"),
                        structured_response=entry.get("structured_response"),
                        tickers=entry.get("tickers"),
                        intent=entry.get("intent"),
                        legacy=legacy,
                    )
                    if ok:
                        messages_migrated += 1
                        last_ts = max(last_ts, ts)
                if raw_entries:
                    threads_migrated += 1

            async with self._pool.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO agent_conv_migrations (name, applied_at)
                    VALUES (%s, %s) ON CONFLICT (name) DO NOTHING
                    """,
                    (_REDIS_BACKFILL_MARKER, time.time()),
                )
            logger.info(
                "ConversationStore: Redis backfill complete (%d threads, %d messages)",
                threads_migrated, messages_migrated,
            )
        except Exception as exc:  # noqa: BLE001
            # Sin marker: se reintentará en el próximo arranque.
            logger.warning("ConversationStore: Redis backfill failed: %s", exc)


# ── Helpers ──────────────────────────────────────────────────────


def _jsonb(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return None


def _row_to_entry(row: tuple) -> dict[str, Any]:
    ts, query, response, tickers, intent, summary, structured = row
    entry: dict[str, Any] = {
        "query": query,
        "response": response,
        "agent_results_summary": _parse_jsonb(summary) or {},
        "timestamp": ts,
    }
    tickers = _parse_jsonb(tickers)
    if tickers:
        entry["tickers"] = tickers
    if intent:
        entry["intent"] = intent
    structured = _parse_jsonb(structured)
    if structured:
        entry["structured_response"] = structured
    return entry


def _parse_jsonb(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:  # noqa: BLE001
            return None
    return value


_store: Optional[ConversationStore] = None


def get_conversation_store() -> ConversationStore:
    global _store
    if _store is None:
        _store = ConversationStore()
    return _store
