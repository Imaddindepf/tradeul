"""
Time & Sales (tape) endpoints.

- GET /api/v1/tape/reference: catálogos de condition codes y exchanges de
  Polygon, cacheados en memoria 24h. El frontend los usa para decodificar
  los IDs numéricos que llegan en cada print (condiciones y market center).
- GET /api/v1/tape/{symbol}/backfill: últimos N prints vía REST /v3/trades,
  normalizados al mismo shape compacto que el WebSocket (tape_trades), para
  llenar la ventana al abrirla antes de que fluya el tiempo real.
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import structlog
from fastapi import APIRouter, HTTPException, Query

from http_clients import http_clients

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/tape", tags=["tape"])

# Cache en memoria del reference data (condiciones + exchanges).
# Los catálogos cambian rara vez; Polygon recomienda no hardcodearlos.
_REFERENCE_TTL_SECONDS = 24 * 3600
_reference_cache: Dict[str, Any] = {"data": None, "fetched_at": 0.0}

# ns → ms (REST /v3/trades da nanosegundos; el WS y el frontend usan ms)
_NS_PER_MS = 1_000_000


@router.get("/reference")
async def get_tape_reference():
    """Catálogos de conditions y exchanges para decodificar el tape."""
    now = time.time()
    if (
        _reference_cache["data"] is not None
        and now - _reference_cache["fetched_at"] < _REFERENCE_TTL_SECONDS
    ):
        return _reference_cache["data"]

    if not http_clients.polygon:
        raise HTTPException(status_code=503, detail="Polygon client not initialized")

    try:
        conditions_resp = await http_clients.polygon.get_trade_conditions()
        exchanges_resp = await http_clients.polygon.get_exchanges()
    except Exception as e:
        logger.error("tape_reference_fetch_error", error=str(e))
        # Servir cache caducada antes que fallar: los catálogos casi no cambian
        if _reference_cache["data"] is not None:
            return _reference_cache["data"]
        raise HTTPException(status_code=502, detail="Error fetching Polygon reference data")

    conditions = []
    for c in conditions_resp.get("results", []):
        conditions.append({
            "id": c.get("id"),
            "name": c.get("name"),
            "type": c.get("type"),
            "sip_mapping": c.get("sip_mapping", {}),
            "update_rules": c.get("update_rules", {}),
            "legacy": c.get("legacy", False),
        })

    exchanges = []
    for e in exchanges_resp.get("results", []):
        exchanges.append({
            "id": e.get("id"),
            "type": e.get("type"),
            "name": e.get("name"),
            "participant_id": e.get("participant_id"),
            "mic": e.get("mic"),
            "acronym": e.get("acronym"),
        })

    data = {"conditions": conditions, "exchanges": exchanges, "fetched_at": int(now)}
    _reference_cache["data"] = data
    _reference_cache["fetched_at"] = now

    logger.info(
        "tape_reference_refreshed",
        conditions=len(conditions),
        exchanges=len(exchanges),
    )
    return data


@router.get("/{symbol}/backfill")
async def get_tape_backfill(
    symbol: str,
    limit: int = Query(default=300, ge=1, le=1000),
    before: Optional[int] = Query(default=None, ge=0, description="Cursor: solo prints con SIP ts < before (Unix ms)"),
):
    """Prints del ticker del día en curso (hora NY), más reciente primero.

    Devuelve el mismo shape compacto que los mensajes tape_trades del
    WebSocket: p, s, t (ms), x, c, q, i, z, pt (ms), trfi, trft (ms).
    Paginación hacia atrás con `before` (ms, exclusivo); `has_more` indica
    si quedan prints más antiguos en el día.
    """
    if not http_clients.polygon:
        raise HTTPException(status_code=503, detail="Polygon client not initialized")

    symbol = symbol.upper().strip()
    if not symbol.isalnum() and not all(ch.isalnum() or ch in ".-" for ch in symbol):
        raise HTTPException(status_code=400, detail="Invalid symbol")

    # Página inicial: sin filtro de fecha — devuelve el final de la ÚLTIMA
    # sesión disponible (clave en fines de semana/festivos/madrugada, donde
    # "hoy en NY" no tiene prints y dejaría el tape vacío).
    # Paginación: acotar al día ET del cursor para no cruzar a la sesión
    # anterior al hacer scroll infinito.
    timestamp_gte = None
    if before:
        cursor_date = datetime.fromtimestamp(
            before / 1000, ZoneInfo("America/New_York")
        ).date().isoformat()
        timestamp_gte = cursor_date

    try:
        resp = await http_clients.polygon.get_trades(
            symbol,
            limit=limit,
            timestamp_gte=timestamp_gte,
            timestamp_lt=str(before * _NS_PER_MS) if before else None,
        )
    except Exception as e:
        logger.error("tape_backfill_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=502, detail="Error fetching trades from Polygon")

    prints: List[Dict[str, Any]] = []
    for t in resp.get("results", []):
        item: Dict[str, Any] = {
            "p": t.get("price"),
            "s": t.get("size"),
            "t": (t.get("sip_timestamp") or 0) // _NS_PER_MS,
        }
        if t.get("exchange") is not None:
            item["x"] = t["exchange"]
        if t.get("conditions"):
            item["c"] = t["conditions"]
        if t.get("sequence_number") is not None:
            item["q"] = t["sequence_number"]
        if t.get("id"):
            item["i"] = t["id"]
        if t.get("tape") is not None:
            item["z"] = t["tape"]
        if t.get("participant_timestamp"):
            item["pt"] = t["participant_timestamp"] // _NS_PER_MS
        if t.get("trf_id") is not None:
            item["trfi"] = t["trf_id"]
        if t.get("trf_timestamp"):
            item["trft"] = t["trf_timestamp"] // _NS_PER_MS
        if t.get("correction"):
            item["corr"] = t["correction"]
        prints.append(item)

    return {
        "symbol": symbol,
        "prints": prints,
        "count": len(prints),
        "has_more": len(prints) >= limit,
    }
