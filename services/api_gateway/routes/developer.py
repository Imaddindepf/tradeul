"""
Developer API — Trader Key Management
======================================
Permite a usuarios con rol 'trader' generar, listar y revocar
API keys para acceder al Openul stream vía WebSocket.

Las keys se almacenan en Redis como SHA-256 del valor real.
El valor en claro solo se retorna UNA VEZ al momento de creación.

Estructura en Redis:
    openul:apikey:<sha256>  →  Hash {
        key_id, trader_clerk_id, name, active,
        created_at, last_used_at, rate_limit
    }
    openul:trader:<clerk_id>:keys  →  Set de sha256 pertenecientes al trader

Endpoints:
    POST   /api/v1/developer/keys          — genera nueva key
    GET    /api/v1/developer/keys          — lista keys del trader autenticado
    DELETE /api/v1/developer/keys/{key_id} — revoca key (active=false)
    PATCH  /api/v1/developer/keys/{key_id} — reactiva key revocada
"""

import hashlib
import secrets
import json
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from shared.utils.logger import get_logger
from shared.utils.redis_client import RedisClient

from auth.dependencies import require_trader
from auth.models import AuthenticatedUser

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/developer", tags=["developer"])

# Redis client inyectado desde main.py al arrancar
_redis: Optional[RedisClient] = None

MAX_KEYS_PER_TRADER = 100   # sin límite práctico
DEFAULT_RATE_LIMIT = 0      # sin rate limiting en WS stream


def set_redis_client(client: RedisClient) -> None:
    global _redis
    _redis = client


def _get_redis() -> RedisClient:
    if not _redis:
        raise HTTPException(status_code=503, detail="Service not ready")
    return _redis


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _generate_key() -> str:
    """Genera una API key con prefijo reconocible."""
    return f"opn_{secrets.token_hex(24)}"


def _redis_key(sha: str) -> str:
    return f"openul:apikey:{sha}"


def _trader_index_key(clerk_id: str) -> str:
    return f"openul:trader:{clerk_id}:keys"


# ── Models ───────────────────────────────────────────────────────────────────

class CreateKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="Friendly name for this key")


class KeyInfo(BaseModel):
    key_id: str
    name: str
    active: bool
    created_at: str
    last_used_at: Optional[str]
    rate_limit: int


class CreateKeyResponse(BaseModel):
    key: str = Field(..., description="API key value — shown only once, store it safely")
    info: KeyInfo


class KeyListResponse(BaseModel):
    keys: List[KeyInfo]
    total: int


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _load_key_info(redis: RedisClient, sha: str) -> Optional[KeyInfo]:
    raw = await redis.client.hgetall(_redis_key(sha))
    if not raw:
        return None
    return KeyInfo(
        key_id=raw.get("key_id", ""),
        name=raw.get("name", ""),
        active=raw.get("active", "false") == "true",
        created_at=raw.get("created_at", ""),
        last_used_at=raw.get("last_used_at") or None,
        rate_limit=int(raw.get("rate_limit", DEFAULT_RATE_LIMIT)),
    )


async def _assert_owns_key(redis: RedisClient, clerk_id: str, key_id: str) -> str:
    """Retorna el sha256 si el trader es dueño de la key, lanza 404 si no."""
    members = await redis.client.smembers(_trader_index_key(clerk_id))
    for sha in members:
        raw = await redis.client.hgetall(_redis_key(sha))
        if raw.get("key_id") == key_id:
            return sha
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/keys", response_model=CreateKeyResponse, status_code=201)
async def create_key(
    body: CreateKeyRequest,
    user: AuthenticatedUser = Depends(require_trader),
):
    """
    Genera una nueva API key para el trader autenticado.
    El valor de la key se retorna UNA SOLA VEZ — guárdala en un lugar seguro.
    """
    redis = _get_redis()

    index_key = _trader_index_key(user.id)
    existing = await redis.client.smembers(index_key)

    raw_key = _generate_key()
    sha = _sha256(raw_key)
    key_id = f"trd_{secrets.token_hex(6)}"
    now = datetime.now(timezone.utc).isoformat()

    key_data = {
        "key_id": key_id,
        "trader_clerk_id": user.id,
        "trader_email": user.email or "",
        "name": body.name,
        "active": "true",
        "created_at": now,
        "last_used_at": "",
        "rate_limit": str(DEFAULT_RATE_LIMIT),
    }

    pipe = redis.client.pipeline()
    pipe.hset(_redis_key(sha), mapping=key_data)
    pipe.sadd(index_key, sha)
    await pipe.execute()

    logger.info(f"trader_key_created key_id={key_id} user={user.id} name={body.name!r}")

    return CreateKeyResponse(
        key=raw_key,
        info=KeyInfo(
            key_id=key_id,
            name=body.name,
            active=True,
            created_at=now,
            last_used_at=None,
            rate_limit=DEFAULT_RATE_LIMIT,
        ),
    )


@router.get("/keys", response_model=KeyListResponse)
async def list_keys(
    user: AuthenticatedUser = Depends(require_trader),
):
    """Lista todas las API keys del trader autenticado (sin mostrar el valor real)."""
    redis = _get_redis()
    shas = await redis.client.smembers(_trader_index_key(user.id))

    keys: List[KeyInfo] = []
    for sha in shas:
        info = await _load_key_info(redis, sha)
        if info:
            keys.append(info)

    keys.sort(key=lambda k: k.created_at, reverse=True)
    return KeyListResponse(keys=keys, total=len(keys))


@router.delete("/keys/{key_id}", status_code=200)
async def revoke_key(
    key_id: str,
    user: AuthenticatedUser = Depends(require_trader),
):
    """Revoca una API key (soft delete: active=false). La key deja de funcionar inmediatamente."""
    redis = _get_redis()
    sha = await _assert_owns_key(redis, user.id, key_id)
    await redis.client.hset(_redis_key(sha), "active", "false")
    logger.info(f"trader_key_revoked key_id={key_id} user={user.id}")
    return {"status": "revoked", "key_id": key_id}


@router.patch("/keys/{key_id}/reactivate", status_code=200)
async def reactivate_key(
    key_id: str,
    user: AuthenticatedUser = Depends(require_trader),
):
    """Reactiva una API key previamente revocada."""
    redis = _get_redis()
    sha = await _assert_owns_key(redis, user.id, key_id)
    existing = await redis.client.smembers(_trader_index_key(user.id))
    active_count = 0
    for s in existing:
        raw = await redis.client.hgetall(_redis_key(s))
        if raw.get("active") == "true":
            active_count += 1
    if active_count >= MAX_KEYS_PER_TRADER:
        raise HTTPException(status_code=400, detail="Key limit reached")
    await redis.client.hset(_redis_key(sha), "active", "true")
    logger.info(f"trader_key_reactivated key_id={key_id} user={user.id}")
    return {"status": "active", "key_id": key_id}
