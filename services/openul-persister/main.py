"""
OpenUL Persister Service

Consume el Redis Stream `openul:news` mediante un consumer group (entrega
garantizada + reanudacion tras reinicio) y persiste cada item en una BD
Postgres separada via inserts por lotes.

Diseno:
  - NO toca la ruta caliente: openul-stream sigue publicando a Redis tal cual.
  - Consumer group => si el servicio se cae, retoma desde el ultimo XACK.
  - Batch inserts + ON CONFLICT DO NOTHING => idempotente y eficiente.
  - Pending-claim al arrancar => reprocesa lo entregado-pero-no-confirmado.
"""

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import asyncpg
import redis.asyncio as aioredis
import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Query

from config import settings

logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO, force=True)

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.get_logger(__name__)

MIGRATION_PATH = os.path.join(os.path.dirname(__file__), "migrations", "001_create_openul_news.sql")

_INSERT_SQL = """
INSERT INTO openul_news (
    id, stream_id, type, text, tickers, source,
    created_at, received_at, media, urls,
    ref_id, direction, change_pct, price, ref_price, delay_seconds
) VALUES (
    $1, $2, $3, $4, $5, $6,
    $7, $8, $9::jsonb, $10,
    $11, $12, $13, $14, $15, $16
)
ON CONFLICT (id) DO NOTHING
"""


class Persister:
    def __init__(self) -> None:
        self.redis: Optional[aioredis.Redis] = None
        self.pool: Optional[asyncpg.Pool] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._stats = {
            "rows_inserted": 0,
            "batches": 0,
            "messages_read": 0,
            "errors": 0,
            "last_insert_at": None,
        }

    # ── Lifecycle ────────────────────────────────────────────────────────
    async def start(self) -> None:
        redis_url = (
            f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}"
            if settings.redis_password
            else f"redis://{settings.redis_host}:{settings.redis_port}"
        )
        self.redis = await aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        await self.redis.ping()
        logger.info("redis_connected", host=settings.redis_host)

        self.pool = await asyncpg.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            database=settings.db_name,
            min_size=settings.db_min_pool,
            max_size=settings.db_max_pool,
        )
        logger.info("postgres_connected", host=settings.db_host, db=settings.db_name)

        await self._apply_migration()
        await self._ensure_group()

        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info("persister_started", stream=settings.redis_stream_key)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.pool:
            await self.pool.close()
        if self.redis:
            await self.redis.close()
        logger.info("persister_stopped")

    # ── Setup ────────────────────────────────────────────────────────────
    async def _apply_migration(self) -> None:
        try:
            with open(MIGRATION_PATH, "r", encoding="utf-8") as fh:
                sql = fh.read()
            async with self.pool.acquire() as conn:
                await conn.execute(sql)
            logger.info("migration_applied")
        except Exception as exc:  # noqa: BLE001
            logger.error("migration_failed", error=str(exc))
            raise

    async def _ensure_group(self) -> None:
        """Crea el consumer group leyendo desde el inicio del stream (id=0)."""
        try:
            await self.redis.xgroup_create(
                name=settings.redis_stream_key,
                groupname=settings.consumer_group,
                id="0",
                mkstream=True,
            )
            logger.info("consumer_group_created", group=settings.consumer_group)
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                logger.info("consumer_group_exists", group=settings.consumer_group)
            else:
                raise

    # ── Consume loop ──────────────────────────────────────────────────────
    async def _consume_loop(self) -> None:
        # 1) Reclamar lo entregado-pero-no-confirmado (id="0") tras un reinicio.
        await self._drain("0")
        # 2) A partir de aqui, solo mensajes nuevos (">").
        while self._running:
            try:
                await self._drain(">")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._stats["errors"] += 1
                logger.error("consume_loop_error", error=str(exc))
                await asyncio.sleep(2)

    async def _drain(self, start_id: str) -> None:
        """
        Lee del stream y persiste por lotes. Con start_id="0" procesa el
        backlog pendiente de este consumidor una sola vez; con ">" entra en
        el bucle continuo de mensajes nuevos.
        """
        while self._running:
            resp = await self.redis.xreadgroup(
                groupname=settings.consumer_group,
                consumername=settings.consumer_name,
                streams={settings.redis_stream_key: start_id},
                count=settings.batch_size,
                block=settings.block_ms,
            )
            if not resp:
                if start_id == "0":
                    return  # backlog drenado
                continue

            # resp = [(stream_key, [(entry_id, {field: value}), ...])]
            entries = resp[0][1]
            if not entries:
                if start_id == "0":
                    return
                continue

            self._stats["messages_read"] += len(entries)

            rows: List[Tuple] = []
            ack_ids: List[str] = []
            for entry_id, fields in entries:
                row = self._build_row(entry_id, fields)
                if row is not None:
                    rows.append(row)
                ack_ids.append(entry_id)  # ack siempre: lo malformado no se reintenta

            if rows:
                await self._insert_batch(rows)

            if ack_ids:
                await self.redis.xack(settings.redis_stream_key, settings.consumer_group, *ack_ids)

            # En modo backlog (id="0"), si devolvio menos del batch, ya no queda.
            if start_id == "0" and len(entries) < settings.batch_size:
                return

    # ── Parsing / insert ──────────────────────────────────────────────────
    def _build_row(self, entry_id: str, fields: Dict[str, str]) -> Optional[Tuple]:
        try:
            item: Dict[str, Any] = json.loads(fields.get("data", "{}"))
        except json.JSONDecodeError:
            return None

        item_id = item.get("id")
        text = item.get("text")
        if not item_id or not text:
            return None

        received_at = self._parse_dt(item.get("received_at")) or self._from_ts(item.get("received_ts"))
        if received_at is None:
            received_at = datetime.now(timezone.utc)

        media = item.get("media")
        media_json = json.dumps(media) if media else None

        return (
            item_id,
            item.get("stream_id") or entry_id,
            item.get("type", "news"),
            text,
            list(item.get("tickers") or []),
            item.get("source"),
            self._parse_dt(item.get("created_at")),
            received_at,
            media_json,
            list(item.get("urls")) if item.get("urls") else None,
            item.get("ref_id"),
            item.get("direction"),
            self._as_float(item.get("change_pct")),
            self._as_float(item.get("price")),
            self._as_float(item.get("ref_price")),
            self._as_int(item.get("delay_seconds")),
        )

    async def _insert_batch(self, rows: List[Tuple]) -> None:
        async with self.pool.acquire() as conn:
            await conn.executemany(_INSERT_SQL, rows)
        self._stats["rows_inserted"] += len(rows)
        self._stats["batches"] += 1
        self._stats["last_insert_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("batch_inserted", rows=len(rows))

    @staticmethod
    def _parse_dt(val: Any) -> Optional[datetime]:
        if not val or not isinstance(val, str):
            return None
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _from_ts(val: Any) -> Optional[datetime]:
        try:
            return datetime.fromtimestamp(float(val), tz=timezone.utc)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_float(val: Any) -> Optional[float]:
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_int(val: Any) -> Optional[int]:
        try:
            return int(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "running": self._running}


persister = Persister()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_openul_persister")
    await persister.start()
    yield
    logger.info("shutting_down")
    await persister.stop()


app = FastAPI(
    title="OpenUL Persister",
    description="Persiste el stream openul:news en una BD Postgres separada",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "openul-persister"}


@app.get("/status")
async def status():
    db_ok = False
    try:
        if persister.pool:
            async with persister.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            db_ok = True
    except Exception:  # noqa: BLE001
        pass
    return {
        "status": "ok" if db_ok and persister._running else "degraded",
        "db": "connected" if db_ok else "disconnected",
        "consumer": persister.stats(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Historial paginado (lee de Postgres, no de Redis) ───────────────────

_HISTORY_COLS = (
    "id, stream_id, type, text, tickers, source, created_at, received_at, "
    "media, urls, ref_id, direction, change_pct, price, ref_price, delay_seconds"
)


def _row_to_item(r: asyncpg.Record) -> Dict[str, Any]:
    """Mapea una fila de openul_news al shape que espera el frontend."""
    media = r["media"]
    if isinstance(media, str):
        try:
            media = json.loads(media)
        except json.JSONDecodeError:
            media = None

    received_at = r["received_at"]
    created_at = r["created_at"]
    row_type = r["type"] or "news"

    item: Dict[str, Any] = {
        "id": r["id"],
        "text": r["text"],
        "tickers": list(r["tickers"] or []),
        "created_at": created_at.isoformat() if created_at else None,
        "received_at": received_at.isoformat() if received_at else None,
        "received_ts": received_at.timestamp() if received_at else None,
        "stream_id": r["stream_id"],
    }
    if media:
        item["media"] = media
    if r["urls"]:
        item["urls"] = list(r["urls"])

    if row_type == "reaction":
        item["type"] = "reaction"
        item["direction"] = r["direction"]
        item["change_pct"] = r["change_pct"]
        item["price"] = r["price"]
        item["ref_price"] = r["ref_price"]
        item["delay_seconds"] = r["delay_seconds"]
        item["ref_id"] = r["ref_id"]

    return item


@app.get("/api/v1/history")
async def history(
    before_ts: Optional[float] = Query(
        None, description="Devuelve items con received_at anterior a este epoch (cursor)"
    ),
    limit: int = Query(50, ge=1, le=200, description="Numero de items"),
):
    """
    Historial paginado por cursor sobre Postgres. Ordenado por received_at
    descendente (mas reciente primero). Para paginar hacia atras, pasa el
    received_ts del item mas antiguo que ya tienes como `before_ts`.
    """
    if not persister.pool:
        raise HTTPException(status_code=503, detail="Service not ready")

    async with persister.pool.acquire() as conn:
        if before_ts:
            rows = await conn.fetch(
                f"SELECT {_HISTORY_COLS} FROM openul_news "
                f"WHERE received_at < to_timestamp($1) "
                f"ORDER BY received_at DESC LIMIT $2",
                before_ts,
                limit,
            )
        else:
            rows = await conn.fetch(
                f"SELECT {_HISTORY_COLS} FROM openul_news "
                f"ORDER BY received_at DESC LIMIT $1",
                limit,
            )

    return {"status": "OK", "count": len(rows), "results": [_row_to_item(r) for r in rows]}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
