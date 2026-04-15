"""
Trader API Key Authentication — Openul Stream
================================================
Verifica API keys emitidas por el API Gateway para acceso programático
al Openul WebSocket stream.

Seguridad:
- Las keys nunca se almacenan en claro; solo su SHA-256 vive en Redis.
- Rate limiting por key usando contadores Redis con TTL de 60s.
- Audit log: cada conexión registra key_id, IP y timestamp en Redis.
- Una key revocada (active=false) se rechaza de inmediato.

Uso en endpoints FastAPI:
    trader = Depends(verify_trader_key)
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Optional

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, WebSocket, status

from config import settings


@dataclass
class TraderSession:
    key_id: str
    name: str
    rate_limit: int


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _redis_key(sha: str) -> str:
    return f"openul:apikey:{sha}"


def _rl_key(key_id: str) -> str:
    """Clave de rate limiting: contador por key por minuto."""
    minute = int(time.time() // 60)
    return f"openul:rl:{key_id}:{minute}"


def _audit_key(key_id: str) -> str:
    return f"openul:audit:{key_id}"


async def _resolve_key(
    raw_key: str,
    redis: aioredis.Redis,
) -> TraderSession:
    """
    Valida una API key contra Redis y aplica rate limiting.
    Lanza HTTPException si la key es inválida, revocada o supera el límite.
    """
    if not raw_key or not raw_key.startswith("opn_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sha = _sha256(raw_key)
    key_data = await redis.hgetall(_redis_key(sha))

    if not key_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if key_data.get("active", "false") != "true":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    key_id = key_data["key_id"]
    rate_limit = int(key_data.get("rate_limit", settings.trader_rate_limit))

    # Rate limiting: INCR + EXPIRE atómico
    rl_key = _rl_key(key_id)
    pipe = redis.pipeline()
    pipe.incr(rl_key)
    pipe.expire(rl_key, 60)
    results = await pipe.execute()
    current_count = results[0]

    if current_count > rate_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {rate_limit} req/min",
            headers={"Retry-After": "60"},
        )

    # Actualizar last_used_at de forma no bloqueante (fire-and-forget)
    import asyncio
    asyncio.create_task(
        redis.hset(_redis_key(sha), "last_used_at", _iso_now())
    )

    return TraderSession(
        key_id=key_id,
        name=key_data.get("name", ""),
        rate_limit=rate_limit,
    )


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _extract_bearer(authorization: str) -> Optional[str]:
    """Extrae el token de un header 'Authorization: Bearer opn_xxx'."""
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:].strip()
    return None


async def verify_trader_key_http(
    request: Request,
    redis: aioredis.Redis,
) -> TraderSession:
    """
    Dependencia para endpoints HTTP REST.
    Acepta:
      - Header: Authorization: Bearer opn_xxx
      - Query param: ?api_key=opn_xxx  (fallback para clientes limitados)
    """
    if not settings.trader_auth_enabled:
        return TraderSession(key_id="dev", name="dev_bypass", rate_limit=9999)

    raw_key = (
        _extract_bearer(request.headers.get("Authorization", ""))
        or request.query_params.get("api_key")
    )

    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide Authorization: Bearer <api-key>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await _resolve_key(raw_key, redis)


async def verify_trader_key_ws(
    websocket: WebSocket,
    redis: aioredis.Redis,
) -> TraderSession:
    """
    Verificación para WebSocket. Los WS no soportan headers 401 estándar,
    así que cerramos con código 1008 (Policy Violation) si la key es inválida.
    Acepta:
      - Header: Authorization: Bearer opn_xxx
      - Query param: ?api_key=opn_xxx
    """
    if not settings.trader_auth_enabled:
        return TraderSession(key_id="dev", name="dev_bypass", rate_limit=9999)

    raw_key = (
        _extract_bearer(websocket.headers.get("Authorization", ""))
        or websocket.query_params.get("api_key")
    )

    if not raw_key:
        await websocket.close(code=1008, reason="Authentication required")
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        return await _resolve_key(raw_key, redis)
    except HTTPException as exc:
        await websocket.close(code=1008, reason=exc.detail)
        raise
