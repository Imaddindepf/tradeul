"""
TV Designs Router
Diseños con nombre del chart TradingView (comando TVC): guardar/cargar/renombrar/
favoritos, estilo tradingview.com. La lista devuelve solo metadatos; el payload
(layout + estado completo de cada celda) se pide por id.
"""

import json
import re
import uuid
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import AuthenticatedUser, get_current_user

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/tv-designs", tags=["tv-designs"])
# Dibujos globales por símbolo (comparte tabla-manager e inyección de DB).
drawings_router = APIRouter(prefix="/api/v1/tv-drawings", tags=["tv-drawings"])

_timescale_client = None

# Límite defensivo del payload de un diseño (estado de hasta 16 celdas).
MAX_PAYLOAD_BYTES = 2_000_000


def set_timescale_client(client):
    """Inyectar el cliente de TimescaleDB"""
    global _timescale_client
    _timescale_client = client


def get_timescale():
    """Dependency para obtener el cliente de TimescaleDB"""
    if _timescale_client is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return _timescale_client


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tv_designs (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    favorite BOOLEAN NOT NULL DEFAULT FALSE,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tv_designs_user_updated_idx
    ON tv_designs (user_id, updated_at DESC);
-- Último estado TVC por usuario: puntero al diseño activo O el estado de
-- trabajo sin nombre. Al reabrir la ventana TVC se restaura desde aquí
-- (persistencia real por usuario, válida entre dispositivos).
CREATE TABLE IF NOT EXISTS tv_designs_last (
    user_id TEXT PRIMARY KEY,
    design_id UUID,
    payload JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Ajustes de usuario del chart TVC (independientes de los diseños, como
-- exige la doc oficial: "User settings are stored independently of chart
-- layouts"). P. ej. el modo de sincronización de dibujos.
CREATE TABLE IF NOT EXISTS tv_chart_settings (
    user_id TEXT PRIMARY KEY,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Dibujos GLOBALES por (usuario, símbolo) — modo "los nuevos dibujos se
-- sincronizan a nivel global" de TV (sharingMode=GloballyShared): el estado
-- de dibujos de un símbolo aparece en cualquier layout/diseño que lo cargue.
CREATE TABLE IF NOT EXISTS tv_drawings (
    user_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    state JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, symbol)
);
"""


async def ensure_table(db) -> None:
    await db.execute(CREATE_TABLE_SQL)


# ============================================================================
# Pydantic Models
# ============================================================================

class DesignMeta(BaseModel):
    id: str
    name: str
    favorite: bool = False
    # Resumen para la lista "Usados con frecuencia" (símbolo/intervalo celda 1)
    symbol: Optional[str] = None
    interval: Optional[str] = None
    updatedAt: float


class DesignCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    payload: Dict[str, Any]


class DesignUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    favorite: Optional[bool] = None
    payload: Optional[Dict[str, Any]] = None


class LastStateRequest(BaseModel):
    """O bien puntero a un diseño activo, o bien el estado sin nombre."""
    designId: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class ChartSettingsRequest(BaseModel):
    settings: Dict[str, Any]


class LastStateResponse(BaseModel):
    designId: Optional[str] = None
    designName: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


def _summary_from_payload(payload: Dict[str, Any]) -> Dict[str, Optional[str]]:
    cell1 = (payload.get("cells") or {}).get("cell-1") or {}
    return {"symbol": cell1.get("symbol"), "interval": cell1.get("interval")}


def _row_to_meta(row) -> DesignMeta:
    payload = row.get("payload")
    if isinstance(payload, str):
        payload = json.loads(payload)
    summary = _summary_from_payload(payload or {})
    return DesignMeta(
        id=str(row["id"]),
        name=row["name"],
        favorite=row["favorite"],
        symbol=summary["symbol"],
        interval=summary["interval"],
        updatedAt=row["updated_at"].timestamp(),
    )


def _check_payload_size(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload)
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Design payload too large")
    return raw


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=List[DesignMeta])
async def list_designs(
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale),
):
    await ensure_table(db)
    rows = await db.fetch(
        """
        SELECT id, name, favorite, payload, updated_at
        FROM tv_designs
        WHERE user_id = $1
        ORDER BY favorite DESC, updated_at DESC
        LIMIT 100
        """,
        user.id,
    )
    return [_row_to_meta(dict(r)) for r in rows]


@router.post("", response_model=DesignMeta)
async def create_design(
    body: DesignCreateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale),
):
    await ensure_table(db)
    raw = _check_payload_size(body.payload)
    design_id = str(uuid.uuid4())
    row = await db.fetchrow(
        """
        INSERT INTO tv_designs (id, user_id, name, payload)
        VALUES ($1, $2, $3, $4::jsonb)
        RETURNING id, name, favorite, payload, updated_at
        """,
        design_id,
        user.id,
        body.name.strip(),
        raw,
    )
    logger.info("tv_design_created", user_id=user.id, design_id=design_id)
    return _row_to_meta(dict(row))


# NOTA: /last debe declararse ANTES de /{design_id} (FastAPI resuelve por orden
# de registro y "last" matchearía como design_id).

@router.get("/last", response_model=LastStateResponse)
async def get_last_state(
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale),
):
    """Último estado TVC del usuario: diseño activo o estado sin nombre."""
    await ensure_table(db)
    row = await db.fetchrow(
        """
        SELECT l.design_id, l.payload, d.name AS design_name
        FROM tv_designs_last l
        LEFT JOIN tv_designs d ON d.id = l.design_id AND d.user_id = l.user_id
        WHERE l.user_id = $1
        """,
        user.id,
    )
    if not row:
        return LastStateResponse()
    # Puntero válido solo si el diseño sigue existiendo; si fue borrado,
    # degradar al payload sin nombre (si lo hay).
    if row["design_id"] and row["design_name"]:
        return LastStateResponse(designId=str(row["design_id"]), designName=row["design_name"])
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return LastStateResponse(payload=payload)


@router.put("/last")
async def set_last_state(
    body: LastStateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale),
):
    """Actualizar el último estado TVC (designId excluye payload y viceversa)."""
    await ensure_table(db)
    design_id = body.designId
    raw = None
    if design_id is None and body.payload is not None:
        raw = _check_payload_size(body.payload)
    await db.execute(
        """
        INSERT INTO tv_designs_last (user_id, design_id, payload, updated_at)
        VALUES ($1, $2::uuid, $3::jsonb, now())
        ON CONFLICT (user_id) DO UPDATE
        SET design_id = EXCLUDED.design_id,
            payload = EXCLUDED.payload,
            updated_at = now()
        """,
        user.id,
        design_id,
        raw,
    )
    return {"ok": True}


@router.get("/settings")
async def get_chart_settings(
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale),
):
    """Ajustes de usuario del chart TVC (p. ej. drawingsSync)."""
    await ensure_table(db)
    row = await db.fetchrow(
        "SELECT settings FROM tv_chart_settings WHERE user_id = $1",
        user.id,
    )
    settings = row["settings"] if row else {}
    if isinstance(settings, str):
        settings = json.loads(settings)
    return {"settings": settings or {}}


@router.put("/settings")
async def put_chart_settings(
    body: ChartSettingsRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale),
):
    """Merge de ajustes: solo pisa las claves enviadas."""
    await ensure_table(db)
    raw = _check_payload_size(body.settings)
    await db.execute(
        """
        INSERT INTO tv_chart_settings (user_id, settings, updated_at)
        VALUES ($1, $2::jsonb, now())
        ON CONFLICT (user_id) DO UPDATE
        SET settings = tv_chart_settings.settings || EXCLUDED.settings,
            updated_at = now()
        """,
        user.id,
        raw,
    )
    return {"ok": True}


@router.get("/{design_id}")
async def get_design(
    design_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale),
):
    await ensure_table(db)
    row = await db.fetchrow(
        "SELECT payload FROM tv_designs WHERE id = $1 AND user_id = $2",
        design_id,
        user.id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Design not found")
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return {"id": design_id, "payload": payload}


@router.patch("/{design_id}", response_model=DesignMeta)
async def update_design(
    design_id: str,
    body: DesignUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale),
):
    await ensure_table(db)
    sets, values = [], []
    if body.name is not None:
        values.append(body.name.strip())
        sets.append(f"name = ${len(values)}")
    if body.favorite is not None:
        values.append(body.favorite)
        sets.append(f"favorite = ${len(values)}")
    if body.payload is not None:
        values.append(_check_payload_size(body.payload))
        sets.append(f"payload = ${len(values)}::jsonb")
    if not sets:
        raise HTTPException(status_code=400, detail="Nothing to update")
    values.extend([design_id, user.id])
    row = await db.fetchrow(
        f"""
        UPDATE tv_designs
        SET {', '.join(sets)}, updated_at = now()
        WHERE id = ${len(values) - 1} AND user_id = ${len(values)}
        RETURNING id, name, favorite, payload, updated_at
        """,
        *values,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Design not found")
    return _row_to_meta(dict(row))


@router.delete("/{design_id}")
async def delete_design(
    design_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale),
):
    await ensure_table(db)
    result = await db.execute(
        "DELETE FROM tv_designs WHERE id = $1 AND user_id = $2",
        design_id,
        user.id,
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Design not found")
    return {"ok": True}


# ============================================================================
# Dibujos globales por símbolo (modo "sincronizar a nivel global")
# ============================================================================

_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-/]{1,20}$")


class DrawingsStateRequest(BaseModel):
    state: Dict[str, Any]


def _clean_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if not _SYMBOL_RE.match(s):
        raise HTTPException(status_code=400, detail="Invalid symbol")
    return s


@drawings_router.get("/{symbol}")
async def get_symbol_drawings(
    symbol: str,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale),
):
    await ensure_table(db)
    s = _clean_symbol(symbol)
    row = await db.fetchrow(
        "SELECT state FROM tv_drawings WHERE user_id = $1 AND symbol = $2",
        user.id,
        s,
    )
    if not row:
        return {"symbol": s, "state": None}
    state = row["state"]
    if isinstance(state, str):
        state = json.loads(state)
    return {"symbol": s, "state": state}


@drawings_router.put("/{symbol}")
async def put_symbol_drawings(
    symbol: str,
    body: DrawingsStateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale),
):
    """MERGE por dibujo (semántica TV: solo los dibujos NUEVOS creados con el
    modo activo entran, cada uno con su id): las claves de state.sources se
    fusionan con lo guardado; valor null = tombstone (borra ese dibujo).
    Nunca se reemplaza el estado completo."""
    await ensure_table(db)
    s = _clean_symbol(symbol)
    _check_payload_size(body.state)
    incoming = body.state.get("sources") or {}

    row = await db.fetchrow(
        "SELECT state FROM tv_drawings WHERE user_id = $1 AND symbol = $2",
        user.id,
        s,
    )
    existing = {}
    if row:
        stored = row["state"]
        if isinstance(stored, str):
            stored = json.loads(stored)
        existing = (stored or {}).get("sources") or {}

    for key, value in incoming.items():
        if value is None:
            existing.pop(key, None)
        else:
            existing[key] = value

    if not existing:
        await db.execute(
            "DELETE FROM tv_drawings WHERE user_id = $1 AND symbol = $2",
            user.id,
            s,
        )
        return {"ok": True, "sources": 0}

    merged = json.dumps({"sources": existing})
    if len(merged) > MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Drawings state too large")
    await db.execute(
        """
        INSERT INTO tv_drawings (user_id, symbol, state, updated_at)
        VALUES ($1, $2, $3::jsonb, now())
        ON CONFLICT (user_id, symbol) DO UPDATE
        SET state = EXCLUDED.state, updated_at = now()
        """,
        user.id,
        s,
        merged,
    )
    return {"ok": True, "sources": len(existing)}
