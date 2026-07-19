"""
RunStore — persistencia de runs del agente y sus artifacts SIN truncar.

Cada query del chat crea un `run`. Cada nodo del grafo que produce datos
guarda sus `artifacts` completos (tablas enteras, código completo, charts,
resúmenes) en Postgres. El WebSocket solo transporta previews + una
referencia (run_id, node); el inspector del frontend pide el detalle por
REST: GET /api/runs/{run_id}/nodes/{node}/artifacts.

Misma infraestructura que AlertStore (psycopg 3 async pool sobre
CHECKPOINT_DB_URL). No-fatal: si Postgres no está, el agente sigue
funcionando con los previews de siempre.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_runs (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'default',
    thread_id   TEXT NOT NULL DEFAULT '',
    query       TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'running',
    started_at  DOUBLE PRECISION NOT NULL,
    finished_at DOUBLE PRECISION,
    meta        JSONB
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_user ON agent_runs (user_id, started_at DESC);

CREATE TABLE IF NOT EXISTS run_artifacts (
    id         BIGSERIAL PRIMARY KEY,
    run_id     TEXT NOT NULL,
    node       TEXT NOT NULL,
    idx        INT  NOT NULL DEFAULT 0,
    kind       TEXT NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    payload    JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_run_artifacts_run ON run_artifacts (run_id, node, idx);
"""

# Retención: los runs son material de inspección, no un data lake.
_RETENTION_DAYS = 7
_MAX_RUNS_PER_USER = 400


class RunStore:
    """Async Postgres store para runs + artifacts (psycopg 3 pool)."""

    def __init__(self, db_url: Optional[str] = None) -> None:
        self._db_url = db_url or os.getenv("CHECKPOINT_DB_URL", "").strip()
        self._pool = None
        self._ready = False

    @property
    def available(self) -> bool:
        return self._ready

    async def init(self) -> None:
        if not self._db_url:
            logger.warning("RunStore disabled: CHECKPOINT_DB_URL not set")
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
            logger.info("RunStore ready (agent_runs / run_artifacts)")
        except Exception as exc:  # noqa: BLE001
            logger.warning("RunStore unavailable (%s) — artifacts will not persist", exc)
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

    # ── Runs ─────────────────────────────────────────────────────

    async def create_run(
        self, run_id: str, *, user_id: str = "default",
        thread_id: str = "", query: str = "",
    ) -> None:
        if not self._ready:
            return
        try:
            async with self._pool.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO agent_runs (id, user_id, thread_id, query, status, started_at)
                    VALUES (%s, %s, %s, %s, 'running', %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (run_id, user_id, thread_id, query[:2000], time.time()),
                )
            await self._prune(user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RunStore.create_run failed: %s", exc)

    async def finish_run(self, run_id: str, status: str = "complete") -> None:
        if not self._ready:
            return
        try:
            async with self._pool.connection() as conn:
                await conn.execute(
                    "UPDATE agent_runs SET status = %s, finished_at = %s WHERE id = %s",
                    (status, time.time(), run_id),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("RunStore.finish_run failed: %s", exc)

    async def get_run(self, run_id: str, *, user_id: str = "default") -> dict | None:
        """Metadatos del run + índice de nodos con artifacts (kind/título)."""
        if not self._ready:
            return None
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    """
                    SELECT id, thread_id, query, status, started_at, finished_at
                    FROM agent_runs WHERE id = %s AND user_id = %s
                    """,
                    (run_id, user_id),
                )
                row = await cur.fetchone()
                if row is None:
                    return None
                cur = await conn.execute(
                    """
                    SELECT node, idx, kind, title FROM run_artifacts
                    WHERE run_id = %s ORDER BY node, idx
                    """,
                    (run_id,),
                )
                arts = await cur.fetchall()
            nodes: dict[str, list[dict]] = {}
            for node, idx, kind, title in arts:
                nodes.setdefault(node, []).append({"idx": idx, "kind": kind, "title": title})
            return {
                "run_id": row[0],
                "thread_id": row[1],
                "query": row[2],
                "status": row[3],
                "started_at": row[4],
                "finished_at": row[5],
                "nodes": nodes,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("RunStore.get_run failed: %s", exc)
            return None

    # ── Artifacts ────────────────────────────────────────────────

    async def save_artifacts(
        self, run_id: str, node: str, artifacts: list[dict[str, Any]],
    ) -> None:
        """Reemplaza (idempotente) los artifacts de un nodo dentro de un run."""
        if not self._ready or not artifacts:
            return
        try:
            async with self._pool.connection() as conn:
                await conn.execute(
                    "DELETE FROM run_artifacts WHERE run_id = %s AND node = %s",
                    (run_id, node),
                )
                for idx, art in enumerate(artifacts):
                    await conn.execute(
                        """
                        INSERT INTO run_artifacts (run_id, node, idx, kind, title, payload)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        (
                            run_id, node, idx,
                            str(art.get("kind", "json")),
                            str(art.get("title", ""))[:200],
                            json.dumps(art, ensure_ascii=False, default=str),
                        ),
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("RunStore.save_artifacts failed (%s/%s): %s", run_id, node, exc)

    async def get_artifacts(
        self, run_id: str, node: str, *, user_id: str = "default",
    ) -> list[dict[str, Any]]:
        if not self._ready:
            return []
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    """
                    SELECT a.payload
                    FROM run_artifacts a
                    JOIN agent_runs r ON r.id = a.run_id
                    WHERE a.run_id = %s AND a.node = %s AND r.user_id = %s
                    ORDER BY a.idx
                    """,
                    (run_id, node, user_id),
                )
                rows = await cur.fetchall()
            out: list[dict[str, Any]] = []
            for (payload,) in rows:
                if isinstance(payload, dict):
                    out.append(payload)
                elif isinstance(payload, str):
                    try:
                        out.append(json.loads(payload))
                    except Exception:  # noqa: BLE001
                        pass
            return out
        except Exception as exc:  # noqa: BLE001
            logger.warning("RunStore.get_artifacts failed (%s/%s): %s", run_id, node, exc)
            return []

    # ── Retención ────────────────────────────────────────────────

    async def _prune(self, user_id: str) -> None:
        """Borra runs viejos (por edad y por exceso) y sus artifacts huérfanos."""
        try:
            cutoff = time.time() - _RETENTION_DAYS * 86400
            async with self._pool.connection() as conn:
                await conn.execute(
                    """
                    DELETE FROM agent_runs
                    WHERE user_id = %s AND (
                        started_at < %s
                        OR id IN (
                            SELECT id FROM agent_runs WHERE user_id = %s
                            ORDER BY started_at DESC OFFSET %s
                        )
                    )
                    """,
                    (user_id, cutoff, user_id, _MAX_RUNS_PER_USER),
                )
                await conn.execute(
                    "DELETE FROM run_artifacts WHERE run_id NOT IN (SELECT id FROM agent_runs)",
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("RunStore prune skipped: %s", exc)


_STORE: RunStore | None = None


def get_run_store() -> RunStore:
    global _STORE
    if _STORE is None:
        _STORE = RunStore()
    return _STORE
