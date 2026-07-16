"""
AlertStore — durable persistence for AlertSpecs and their fire history.

Uses the same TimescaleDB/Postgres the service already reaches through
CHECKPOINT_DB_URL (psycopg 3, async pool). Redis remains the hot runtime
cache for the TriggerEngine; Postgres is the source of truth so specs
survive restarts and become first-class, queryable assets (phase 5:
public library, post-fire performance metrics).
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

from alerts.spec import AlertSpec, AlertStatus

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alert_specs (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    name          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'draft',
    tier          TEXT NOT NULL,
    version       INT  NOT NULL DEFAULT 1,
    spec          JSONB NOT NULL,
    source_query  TEXT NOT NULL DEFAULT '',
    paraphrase    TEXT NOT NULL DEFAULT '',
    trigger_id    TEXT,
    dry_run       JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_alert_specs_user   ON alert_specs (user_id, status);

CREATE TABLE IF NOT EXISTS alert_fires (
    id          BIGSERIAL PRIMARY KEY,
    spec_id     TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    event_type  TEXT,
    price       DOUBLE PRECISION,
    evidence    JSONB,
    fired_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_alert_fires_spec   ON alert_fires (spec_id, fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_fires_user   ON alert_fires (user_id, fired_at DESC);
"""


class AlertStore:
    """Async Postgres store for alert specs (psycopg 3 pool)."""

    def __init__(self, db_url: Optional[str] = None) -> None:
        self._db_url = db_url or os.getenv("CHECKPOINT_DB_URL", "").strip()
        self._pool = None
        self._ready = False

    @property
    def available(self) -> bool:
        return self._ready

    async def init(self) -> None:
        """Open the pool and run idempotent schema migration. Non-fatal."""
        if not self._db_url:
            logger.warning("AlertStore disabled: CHECKPOINT_DB_URL not set")
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
            logger.info("AlertStore ready (alert_specs / alert_fires)")
        except Exception as exc:
            logger.warning("AlertStore unavailable (%s) — specs will not persist", exc)
            self._pool = None
            self._ready = False

    async def close(self) -> None:
        if self._pool is not None:
            try:
                await self._pool.close()
            except Exception:
                pass
            self._pool = None
            self._ready = False

    # ── Specs ────────────────────────────────────────────────────

    async def save_spec(self, spec: AlertSpec) -> bool:
        if not self._ready:
            return False
        spec.updated_at = time.time()
        payload = json.dumps(spec.model_dump(mode="json"))
        try:
            async with self._pool.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO alert_specs
                        (id, user_id, name, status, tier, version, spec,
                         source_query, paraphrase, trigger_id, dry_run, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, now())
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        status = EXCLUDED.status,
                        tier = EXCLUDED.tier,
                        spec = EXCLUDED.spec,
                        paraphrase = EXCLUDED.paraphrase,
                        trigger_id = EXCLUDED.trigger_id,
                        dry_run = EXCLUDED.dry_run,
                        updated_at = now()
                    """,
                    (
                        spec.id, spec.user_id, spec.name,
                        spec.status if isinstance(spec.status, str) else spec.status.value,
                        spec.tier if isinstance(spec.tier, str) else spec.tier.value,
                        spec.version, payload,
                        spec.source_query, spec.paraphrase, spec.trigger_id,
                        json.dumps(spec.dry_run) if spec.dry_run is not None else None,
                    ),
                )
            return True
        except Exception as exc:
            logger.error("save_spec failed for %s: %s", spec.id, exc)
            return False

    async def get_spec(self, spec_id: str, user_id: str) -> Optional[AlertSpec]:
        if not self._ready:
            return None
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT spec FROM alert_specs WHERE id = %s AND user_id = %s",
                    (spec_id, user_id),
                )
                row = await cur.fetchone()
            if row is None:
                return None
            data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            return AlertSpec(**data)
        except Exception as exc:
            logger.error("get_spec failed for %s: %s", spec_id, exc)
            return None

    async def list_specs(
        self, user_id: str, include_archived: bool = False, limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not self._ready:
            return []
        cond = "" if include_archived else "AND status <> 'archived'"
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    f"""
                    SELECT spec FROM alert_specs
                    WHERE user_id = %s {cond}
                    ORDER BY updated_at DESC LIMIT %s
                    """,
                    (user_id, limit),
                )
                rows = await cur.fetchall()
            out = []
            for (raw,) in rows:
                out.append(raw if isinstance(raw, dict) else json.loads(raw))
            return out
        except Exception as exc:
            logger.error("list_specs failed for %s: %s", user_id, exc)
            return []

    async def set_status(
        self, spec_id: str, user_id: str, status: AlertStatus | str,
        trigger_id: Optional[str] = None,
    ) -> Optional[AlertSpec]:
        """Update status (and trigger linkage) atomically; returns fresh spec."""
        spec = await self.get_spec(spec_id, user_id)
        if spec is None:
            return None
        spec.status = status if isinstance(status, AlertStatus) else AlertStatus(status)
        if trigger_id is not None:
            spec.trigger_id = trigger_id
        elif spec.status in (AlertStatus.PAUSED, AlertStatus.ARCHIVED):
            spec.trigger_id = None
        ok = await self.save_spec(spec)
        return spec if ok else None

    # ── Fires (history with evidence) ────────────────────────────

    async def record_fire(
        self, spec_id: str, user_id: str, symbol: str,
        event_type: Optional[str] = None, price: Optional[float] = None,
        evidence: Optional[dict] = None,
    ) -> None:
        if not self._ready:
            return
        try:
            async with self._pool.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO alert_fires (spec_id, user_id, symbol, event_type, price, evidence)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (spec_id, user_id, symbol, event_type, price,
                     json.dumps(evidence) if evidence else None),
                )
        except Exception as exc:
            logger.error("record_fire failed for %s: %s", spec_id, exc)

    async def list_fires(self, spec_id: str, user_id: str, limit: int = 50) -> list[dict]:
        if not self._ready:
            return []
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    """
                    SELECT symbol, event_type, price, evidence,
                           extract(epoch FROM fired_at) AS fired_at
                    FROM alert_fires
                    WHERE spec_id = %s AND user_id = %s
                    ORDER BY fired_at DESC LIMIT %s
                    """,
                    (spec_id, user_id, limit),
                )
                rows = await cur.fetchall()
            return [
                {
                    "symbol": r[0], "event_type": r[1], "price": r[2],
                    "evidence": r[3], "fired_at": float(r[4]),
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error("list_fires failed for %s: %s", spec_id, exc)
            return []


# ── Singleton ────────────────────────────────────────────────────

_store: Optional[AlertStore] = None


def get_store() -> AlertStore:
    global _store
    if _store is None:
        _store = AlertStore()
    return _store
