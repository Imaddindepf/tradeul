"""
Alerts WebSocket — live fire feed for LLM-compiled alerts.

Relays the user's Redis alert stream (``stream:alerts:{user_id}``, fed by the
TriggerEngine) to the browser over an authenticated WebSocket.

Protocol (server -> client):
    {"type": "connected", "user_id": "..."}
    {"type": "alert_fire", "backlog": true|false, "fire": {
        "id": "<stream entry id>", "spec_id": "...", "trigger_id": "...",
        "trigger_name": "...", "symbol": "TSLA", "event_type": "vwap_cross_up",
        "price": 389.97, "rvol": 1.8, "volume": 1234567,
        "message": "...", "timestamp": 1784214137.5
    }}
    {"type": "keepalive"}

On connect the last ``BACKLOG_COUNT`` fires are replayed with backlog=true so
the feed isn't empty, then the loop blocks on new entries only.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Optional

import redis.asyncio as aioredis
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

BACKLOG_COUNT = 25
BLOCK_MS = 5000          # xread block time; doubles as keepalive cadence
KEEPALIVE_EVERY_S = 20.0


def _redis_url() -> str:
    # Same DB as the TriggerEngine, where stream:alerts:{user_id} lives.
    return os.getenv("REDIS_URL", "redis://redis:6379/5")


def _to_float(v: str) -> Optional[float]:
    try:
        return float(v) if v not in ("", None) else None
    except (ValueError, TypeError):
        return None


def _to_int(v: str) -> Optional[int]:
    try:
        return int(float(v)) if v not in ("", None) else None
    except (ValueError, TypeError):
        return None


def _parse_fire(entry_id: str | bytes, fields: dict) -> dict[str, Any]:
    """Normalise a raw stream entry into the typed fire payload."""
    d: dict[str, str] = {}
    for k, v in fields.items():
        d[k.decode() if isinstance(k, bytes) else k] = (
            v.decode() if isinstance(v, bytes) else v
        )
    return {
        "id": entry_id.decode() if isinstance(entry_id, bytes) else entry_id,
        "spec_id": d.get("spec_id") or None,
        "trigger_id": d.get("trigger_id") or None,
        "trigger_name": d.get("trigger_name") or "",
        "symbol": d.get("symbol") or "",
        "event_type": d.get("event_type") or "",
        "price": _to_float(d.get("price", "")),
        "rvol": _to_float(d.get("rvol", "")),
        "volume": _to_int(d.get("volume", "")),
        "message": d.get("message") or "",
        "timestamp": _to_float(d.get("timestamp", "")) or time.time(),
    }


def _ws_alive(websocket: WebSocket) -> bool:
    return (
        websocket.application_state == WebSocketState.CONNECTED
        and websocket.client_state == WebSocketState.CONNECTED
    )


async def _safe_send(websocket: WebSocket, payload: dict) -> bool:
    if not _ws_alive(websocket):
        return False
    try:
        await websocket.send_json(payload)
        return True
    except (WebSocketDisconnect, RuntimeError):
        return False


async def _drain_client(websocket: WebSocket) -> None:
    """Consume inbound frames (pings) so disconnects surface immediately."""
    try:
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, RuntimeError):
        return
    except asyncio.CancelledError:
        return


async def handle_alerts_websocket(websocket: WebSocket, user_id: str) -> None:
    """Stream the user's alert fires until the client disconnects."""
    await websocket.accept()
    stream_key = f"stream:alerts:{user_id}"
    logger.info("Alerts WS connected (user=%s, stream=%s)", user_id, stream_key)

    r = aioredis.from_url(_redis_url(), decode_responses=False)
    drain_task = asyncio.create_task(_drain_client(websocket))

    try:
        await _safe_send(websocket, {"type": "connected", "user_id": user_id})

        # ── Backlog: last N fires, oldest first ──
        last_id = "0-0"
        try:
            backlog = await r.xrevrange(stream_key, count=BACKLOG_COUNT)
            for entry_id, fields in reversed(backlog):
                fire = _parse_fire(entry_id, fields)
                last_id = fire["id"]
                if not await _safe_send(
                    websocket, {"type": "alert_fire", "backlog": True, "fire": fire},
                ):
                    return
        except Exception:
            logger.exception("Alerts WS backlog read failed (user=%s)", user_id)

        # last_id stays "0-0" on an empty stream: there is nothing old to
        # replay, and (unlike "$") concrete ids never skip entries that land
        # between two consecutive xread calls.

        # ── Live loop ──
        last_keepalive = time.monotonic()
        while _ws_alive(websocket) and not drain_task.done():
            try:
                results = await r.xread({stream_key: last_id}, count=50, block=BLOCK_MS)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Alerts WS xread failed (user=%s), retrying", user_id)
                await asyncio.sleep(2)
                continue

            if results:
                for _stream, entries in results:
                    for entry_id, fields in entries:
                        fire = _parse_fire(entry_id, fields)
                        last_id = fire["id"]
                        if not await _safe_send(
                            websocket,
                            {"type": "alert_fire", "backlog": False, "fire": fire},
                        ):
                            return

            if time.monotonic() - last_keepalive >= KEEPALIVE_EVERY_S:
                last_keepalive = time.monotonic()
                if not await _safe_send(websocket, {"type": "keepalive"}):
                    return

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Alerts WS error (user=%s)", user_id)
    finally:
        drain_task.cancel()
        try:
            await drain_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        try:
            await r.aclose()
        except Exception:
            pass
        logger.info("Alerts WS closed (user=%s)", user_id)
