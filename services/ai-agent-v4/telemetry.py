"""
LLM telemetry — tokens, coste y latencia por llamada, atribuidos a run/user/node.

El servicio usa 3 proveedores LLM y hasta ahora no registraba ni un token ni un
céntimo: imposible responder "¿cuánto cuesta un usuario?" o "¿qué nodo es el
cuello de botella?". Este módulo cierra ese hueco sin tocar los call-sites:

  - Un `contextvar` lleva {run_id, user_id, node}; el orquestador lo fija al
    entrar en cada nodo del grafo.
  - Un callback async de LangChain (adjuntado en `make_llm`) captura el uso de
    tokens de CADA invocación y lo encola.
  - Un writer en segundo plano vuelca lotes a Postgres (`agent_llm_calls`), así
    la escritura nunca añade latencia al camino del usuario.
  - El mismo writer persiste cada llamada a tool MCP (`agent_tool_calls`,
    éxito/fallo/latencia, desde `agents/_mcp_tools.py`) — antes un fallo de
    tool solo vivía en el array `_errors` en memoria y en logs docker que
    rotan en minutos: imposible responder "¿desde cuándo falla la tool X?".

No-fatal en todos los frentes: si Postgres no está, si falta el uso de tokens,
o si el buffer se llena, se degrada silenciosamente sin romper la respuesta.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Contexto de atribución (run/user/node) ───────────────────────

_call_ctx: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "llm_call_ctx", default={}
)


def set_call_context(*, run_id: str = "", user_id: str = "", node: str = "") -> Any:
    """Fija el contexto de atribución para las llamadas LLM del nodo actual.
    Devuelve un token para restaurar con `reset_call_context`."""
    return _call_ctx.set({"run_id": run_id, "user_id": user_id, "node": node})


def reset_call_context(token: Any) -> None:
    try:
        _call_ctx.reset(token)
    except Exception:  # noqa: BLE001
        pass


# ── Precios (USD por 1M tokens) — editables vía env o aquí ────────
# Valores aproximados 2026; el objetivo es una señal de coste consistente,
# no facturación exacta. Ajustables sin redeploy con LLM_PRICING_JSON.

_DEFAULT_PRICING = {
    "gemini-2.5-flash": {"in": 0.30, "out": 2.50},
    "gemini-2.5-pro": {"in": 1.25, "out": 10.00},
    "grok-3-mini": {"in": 0.30, "out": 0.50},
    "grok-3": {"in": 3.00, "out": 15.00},
}


def _load_pricing() -> dict:
    raw = os.getenv("LLM_PRICING_JSON", "").strip()
    if raw:
        try:
            import json
            return {**_DEFAULT_PRICING, **json.loads(raw)}
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM_PRICING_JSON ignored (%s)", exc)
    return dict(_DEFAULT_PRICING)


_PRICING = _load_pricing()


def _provider_of(model: str) -> str:
    m = (model or "").lower()
    if m.startswith("gemini"):
        return "google"
    if m.startswith("grok"):
        return "xai"
    return "unknown"


def _cost_usd(model: str, in_tok: int, out_tok: int) -> float:
    p = _PRICING.get(model)
    if not p:
        return 0.0
    return round((in_tok / 1e6) * p["in"] + (out_tok / 1e6) * p["out"], 6)


# ── Buffer + writer en segundo plano ─────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_llm_calls (
    id            BIGSERIAL PRIMARY KEY,
    ts            DOUBLE PRECISION NOT NULL,
    run_id        TEXT NOT NULL DEFAULT '',
    user_id       TEXT NOT NULL DEFAULT '',
    node          TEXT NOT NULL DEFAULT '',
    provider      TEXT NOT NULL DEFAULT '',
    model         TEXT NOT NULL DEFAULT '',
    input_tokens  INT  NOT NULL DEFAULT 0,
    output_tokens INT  NOT NULL DEFAULT 0,
    total_tokens  INT  NOT NULL DEFAULT 0,
    cost_usd      DOUBLE PRECISION NOT NULL DEFAULT 0,
    latency_ms    INT  NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_run  ON agent_llm_calls (run_id);
CREATE INDEX IF NOT EXISTS idx_llm_calls_user ON agent_llm_calls (user_id, ts DESC);
CREATE TABLE IF NOT EXISTS agent_tool_calls (
    id         BIGSERIAL PRIMARY KEY,
    ts         DOUBLE PRECISION NOT NULL,
    run_id     TEXT NOT NULL DEFAULT '',
    user_id    TEXT NOT NULL DEFAULT '',
    node       TEXT NOT NULL DEFAULT '',
    server     TEXT NOT NULL DEFAULT '',
    tool       TEXT NOT NULL DEFAULT '',
    ok         BOOLEAN NOT NULL DEFAULT TRUE,
    error      TEXT NOT NULL DEFAULT '',
    latency_ms INT  NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tool_calls_tool ON agent_tool_calls (server, tool, ts DESC);
CREATE INDEX IF NOT EXISTS idx_tool_calls_ts   ON agent_tool_calls (ts);
"""

_RETENTION_DAYS = int(os.getenv("LLM_TELEMETRY_RETENTION_DAYS", "30"))
# Las filas de tools son minúsculas y su valor es histórico ("¿desde cuándo
# falla X?"), así que viven más que las de LLM por defecto.
_TOOL_RETENTION_DAYS = int(os.getenv("TOOL_TELEMETRY_RETENTION_DAYS", "90"))
_FLUSH_INTERVAL_S = float(os.getenv("LLM_TELEMETRY_FLUSH_S", "5"))
_MAX_BUFFER = 5000


class _Telemetry:
    def __init__(self) -> None:
        self._db_url = os.getenv("CHECKPOINT_DB_URL", "").strip()
        self._pool = None
        self._buffer: list[tuple] = []
        self._tool_buffer: list[tuple] = []
        self._task: Optional[asyncio.Task] = None
        self._ready = False
        self._last_prune = 0.0

    @property
    def enabled(self) -> bool:
        return self._ready

    async def init(self) -> None:
        if not self._db_url:
            logger.info("LLM telemetry disabled: CHECKPOINT_DB_URL not set")
            return
        try:
            from psycopg_pool import AsyncConnectionPool
            self._pool = AsyncConnectionPool(
                self._db_url, min_size=1, max_size=2, open=False,
                kwargs={"autocommit": True},
            )
            await self._pool.open(wait=True, timeout=15)
            async with self._pool.connection() as conn:
                await conn.execute(_SCHEMA)
            self._ready = True
            self._task = asyncio.create_task(self._flush_loop())
            logger.info("LLM telemetry ready (agent_llm_calls, agent_tool_calls)")
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM telemetry unavailable (%s)", exc)
            self._ready = False

    def record(
        self, *, model: str, input_tokens: int, output_tokens: int, latency_ms: int,
    ) -> None:
        """Sincrónico, no bloqueante: encola una fila. Descarta si el buffer
        está lleno (nunca bloquea el camino del LLM)."""
        if not self._ready or len(self._buffer) >= _MAX_BUFFER:
            return
        ctx = _call_ctx.get() or {}
        model = model or ""
        total = int(input_tokens) + int(output_tokens)
        self._buffer.append((
            time.time(), ctx.get("run_id", ""), ctx.get("user_id", ""),
            ctx.get("node", ""), _provider_of(model), model,
            int(input_tokens), int(output_tokens), total,
            _cost_usd(model, int(input_tokens), int(output_tokens)), int(latency_ms),
        ))

    def record_tool(
        self, *, server: str, tool: str, ok: bool, error: str = "", latency_ms: int = 0,
    ) -> None:
        """Sincrónico, no bloqueante: encola una llamada a tool MCP (éxito o
        fallo). Mismo contrato que `record`: descarta si el buffer está lleno."""
        if not self._ready or len(self._tool_buffer) >= _MAX_BUFFER:
            return
        ctx = _call_ctx.get() or {}
        self._tool_buffer.append((
            time.time(), ctx.get("run_id", ""), ctx.get("user_id", ""),
            ctx.get("node", ""), server or "", tool or "",
            bool(ok), (error or "")[:500], int(latency_ms),
        ))

    async def _flush_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(_FLUSH_INTERVAL_S)
                await self._flush()
                await self._maybe_prune()
            except asyncio.CancelledError:
                await self._flush()
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("telemetry flush error: %s", exc)

    async def _flush(self) -> None:
        if not self._pool:
            return
        if self._buffer:
            batch, self._buffer = self._buffer, []
            try:
                async with self._pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.executemany(
                            """
                            INSERT INTO agent_llm_calls
                              (ts, run_id, user_id, node, provider, model,
                               input_tokens, output_tokens, total_tokens, cost_usd, latency_ms)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """,
                            batch,
                        )
            except Exception as exc:  # noqa: BLE001
                logger.warning("telemetry batch insert failed (%d rows dropped): %s", len(batch), exc)
        if self._tool_buffer:
            batch, self._tool_buffer = self._tool_buffer, []
            try:
                async with self._pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.executemany(
                            """
                            INSERT INTO agent_tool_calls
                              (ts, run_id, user_id, node, server, tool, ok, error, latency_ms)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """,
                            batch,
                        )
            except Exception as exc:  # noqa: BLE001
                logger.warning("tool telemetry batch insert failed (%d rows dropped): %s", len(batch), exc)

    async def _maybe_prune(self) -> None:
        now = time.time()
        if now - self._last_prune < 3600:
            return
        self._last_prune = now
        try:
            cutoff = now - _RETENTION_DAYS * 86400
            tool_cutoff = now - _TOOL_RETENTION_DAYS * 86400
            async with self._pool.connection() as conn:
                await conn.execute("DELETE FROM agent_llm_calls WHERE ts < %s", (cutoff,))
                await conn.execute("DELETE FROM agent_tool_calls WHERE ts < %s", (tool_cutoff,))
        except Exception as exc:  # noqa: BLE001
            logger.warning("telemetry prune failed: %s", exc)

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if self._pool is not None:
            try:
                await self._pool.close()
            except Exception:  # noqa: BLE001
                pass

    # ── Lectura / agregación ─────────────────────────────────────

    async def run_summary(self, run_id: str) -> dict:
        if not self._ready:
            return {}
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    """
                    SELECT node, model, count(*), sum(input_tokens), sum(output_tokens),
                           sum(cost_usd), sum(latency_ms)
                    FROM agent_llm_calls WHERE run_id = %s
                    GROUP BY node, model ORDER BY sum(cost_usd) DESC
                    """,
                    (run_id,),
                )
                rows = await cur.fetchall()
            calls = [
                {"node": r[0], "model": r[1], "calls": r[2],
                 "input_tokens": int(r[3] or 0), "output_tokens": int(r[4] or 0),
                 "cost_usd": round(float(r[5] or 0), 6), "latency_ms": int(r[6] or 0)}
                for r in rows
            ]
            return {
                "run_id": run_id,
                "total_cost_usd": round(sum(c["cost_usd"] for c in calls), 6),
                "total_tokens": sum(c["input_tokens"] + c["output_tokens"] for c in calls),
                "by_node_model": calls,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("telemetry run_summary failed: %s", exc)
            return {}

    async def user_summary(self, user_id: str, days: int = 7) -> dict:
        if not self._ready:
            return {}
        try:
            cutoff = time.time() - days * 86400
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    """
                    SELECT model, count(*), sum(total_tokens), sum(cost_usd)
                    FROM agent_llm_calls WHERE user_id = %s AND ts >= %s
                    GROUP BY model ORDER BY sum(cost_usd) DESC
                    """,
                    (user_id, cutoff),
                )
                rows = await cur.fetchall()
            by_model = [
                {"model": r[0], "calls": r[1], "tokens": int(r[2] or 0),
                 "cost_usd": round(float(r[3] or 0), 6)} for r in rows
            ]
            return {
                "user_id": user_id, "window_days": days,
                "total_cost_usd": round(sum(m["cost_usd"] for m in by_model), 6),
                "by_model": by_model,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("telemetry user_summary failed: %s", exc)
            return {}

    async def tool_summary(self, days: int = 7) -> dict:
        """Contadores de éxito/fallo por tool MCP en la ventana. `last_ok`,
        `first_error` y `last_error_at` responden "¿desde cuándo falla X?"."""
        if not self._ready:
            return {}
        try:
            cutoff = time.time() - days * 86400
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    """
                    SELECT server, tool, count(*),
                           count(*) FILTER (WHERE NOT ok),
                           max(ts) FILTER (WHERE ok),
                           min(ts) FILTER (WHERE NOT ok),
                           max(ts) FILTER (WHERE NOT ok),
                           avg(latency_ms)
                    FROM agent_tool_calls WHERE ts >= %s
                    GROUP BY server, tool
                    ORDER BY count(*) FILTER (WHERE NOT ok) DESC, count(*) DESC
                    """,
                    (cutoff,),
                )
                rows = await cur.fetchall()
                cur = await conn.execute(
                    """
                    SELECT DISTINCT ON (server, tool) server, tool, error
                    FROM agent_tool_calls
                    WHERE ts >= %s AND NOT ok
                    ORDER BY server, tool, ts DESC
                    """,
                    (cutoff,),
                )
                last_errors = {(r[0], r[1]): r[2] for r in await cur.fetchall()}

            def _iso(ts) -> Optional[str]:
                if not ts:
                    return None
                return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")

            tools = []
            for r in rows:
                calls, errors = int(r[2] or 0), int(r[3] or 0)
                entry = {
                    "server": r[0], "tool": r[1], "calls": calls, "errors": errors,
                    "error_rate": round(errors / calls, 3) if calls else 0.0,
                    "avg_latency_ms": int(r[7] or 0),
                    "last_ok": _iso(r[4]),
                    "first_error": _iso(r[5]),
                    "last_error_at": _iso(r[6]),
                }
                if errors:
                    entry["last_error"] = last_errors.get((r[0], r[1]), "")
                tools.append(entry)
            return {"window_days": days, "tools": tools}
        except Exception as exc:  # noqa: BLE001
            logger.warning("telemetry tool_summary failed: %s", exc)
            return {}


_telemetry: Optional[_Telemetry] = None


def get_telemetry() -> _Telemetry:
    global _telemetry
    if _telemetry is None:
        _telemetry = _Telemetry()
    return _telemetry


# ── Callback LangChain (adjuntado en make_llm) ───────────────────


def make_callback_handler():
    """Devuelve un AsyncCallbackHandler que registra el uso de cada llamada LLM.
    Import diferido de langchain para no acoplar el módulo si no está."""
    try:
        from langchain_core.callbacks import AsyncCallbackHandler
    except Exception:  # noqa: BLE001
        return None

    class _UsageHandler(AsyncCallbackHandler):
        def __init__(self) -> None:
            self._starts: dict = {}

        async def on_llm_start(self, serialized, prompts, *, run_id=None, **kw):
            if run_id is not None:
                self._starts[run_id] = time.time()

        async def on_chat_model_start(self, serialized, messages, *, run_id=None, **kw):
            if run_id is not None:
                self._starts[run_id] = time.time()

        async def on_llm_end(self, response, *, run_id=None, **kw):
            started = self._starts.pop(run_id, None)
            latency_ms = int((time.time() - started) * 1000) if started else 0
            model, in_tok, out_tok = _extract_usage(response)
            if in_tok or out_tok:
                get_telemetry().record(
                    model=model, input_tokens=in_tok,
                    output_tokens=out_tok, latency_ms=latency_ms,
                )

        async def on_llm_error(self, error, *, run_id=None, **kw):
            self._starts.pop(run_id, None)

    return _UsageHandler()


def _extract_usage(response) -> tuple:
    """Extrae (model, input_tokens, output_tokens) de un LLMResult, robusto
    entre proveedores (Gemini / Grok vía LangChain)."""
    model = ""
    in_tok = out_tok = 0
    try:
        gens = getattr(response, "generations", None) or []
        for row in gens:
            for gen in row:
                msg = getattr(gen, "message", None)
                if msg is None:
                    continue
                um = getattr(msg, "usage_metadata", None) or {}
                if um:
                    in_tok = int(um.get("input_tokens") or 0)
                    out_tok = int(um.get("output_tokens") or 0)
                meta = getattr(msg, "response_metadata", None) or {}
                model = meta.get("model_name") or meta.get("model") or model
                if in_tok or out_tok:
                    break
            if in_tok or out_tok:
                break
        if not model:
            llm_out = getattr(response, "llm_output", None) or {}
            model = llm_out.get("model_name") or llm_out.get("model") or ""
    except Exception:  # noqa: BLE001
        pass
    return model, in_tok, out_tok
