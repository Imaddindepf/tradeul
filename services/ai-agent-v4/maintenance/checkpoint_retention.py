"""
Checkpoint retention — poda de checkpoints de LangGraph inactivos.

Los checkpoints (`checkpoints` / `checkpoint_blobs` / `checkpoint_writes`) se
escriben en cada super-step de cada turno y NADA los borraba: crecían de forma
lineal e ilimitada (la tabla más grande del servicio). Este job elimina, de
forma periódica y segura, los hilos claramente inactivos.

Seguridad del criterio: solo se borran hilos que (a) tienen una conversación
asociada en `agent_conversations` y (b) cuyo `updated_at` es más viejo que el
umbral. Un hilo en vuelo (segundos de antigüedad, o sin fila de conversación
aún) NUNCA coincide, así que jamás se borra estado activo. Borrar todas las
filas de un `thread_id` en las tres tablas lo elimina limpiamente (son
per-thread), preservando las invariantes del checkpointer.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

logger = logging.getLogger(__name__)

_RETENTION_DAYS = int(os.getenv("CHECKPOINT_RETENTION_DAYS", "45"))
_INTERVAL_S = int(os.getenv("CHECKPOINT_RETENTION_INTERVAL_S", str(24 * 3600)))
_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


async def _prune_once(db_url: str) -> int:
    from psycopg_pool import AsyncConnectionPool

    cutoff = time.time() - _RETENTION_DAYS * 86400
    removed_threads = 0
    async with AsyncConnectionPool(
        db_url, min_size=1, max_size=1, open=False,
        kwargs={"autocommit": True},
    ) as pool:
        await pool.open(wait=True, timeout=15)
        async with pool.connection() as conn:
            # Hilos con conversación asociada claramente inactiva.
            cur = await conn.execute(
                """
                SELECT DISTINCT cp.thread_id
                FROM checkpoints cp
                JOIN agent_conversations ac
                  ON ac.user_id || ':' || ac.thread_id = cp.thread_id
                WHERE ac.updated_at < %s
                """,
                (cutoff,),
            )
            stale = [r[0] for r in await cur.fetchall()]
            if not stale:
                return 0
            for table in _TABLES:
                await conn.execute(
                    f"DELETE FROM {table} WHERE thread_id = ANY(%s)",
                    (stale,),
                )
            removed_threads = len(stale)
    logger.info(
        "checkpoint_retention: pruned %d inactive thread(s) (> %d days)",
        removed_threads, _RETENTION_DAYS,
    )
    return removed_threads


async def run_retention_loop() -> None:
    """Background loop: prune once at startup, then every _INTERVAL_S."""
    db_url = os.getenv("CHECKPOINT_DB_URL", "").strip()
    if not db_url:
        logger.info("checkpoint_retention disabled: CHECKPOINT_DB_URL not set")
        return
    while True:
        try:
            await _prune_once(db_url)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("checkpoint_retention pass failed: %s", exc)
        await asyncio.sleep(_INTERVAL_S)
