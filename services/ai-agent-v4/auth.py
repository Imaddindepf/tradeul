"""
Verificación de JWT de Clerk para el AI Agent V4.

El agente es caro (consume créditos de LLM: Gemini/Grok/Perplexity vía MCP), así
que tanto el WebSocket de chat como los endpoints REST exigen un token válido de
Clerk. La identidad se valida criptográficamente contra el JWKS de Clerk (cacheado
localmente), sin llamar a Clerk en cada request.

Config (desde .env, ya montado en el contenedor):
  - CLERK_JWKS_URL   (preferido)  ej: https://<dominio>/.well-known/jwks.json
  - CLERK_ISSUER     (preferido)  ej: https://<dominio>
  - CLERK_PUBLISHABLE_KEY  (fallback para derivar dominio si faltan los de arriba)
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

import jwt
from fastapi import HTTPException, Request
from jwt import PyJWKClient

logger = logging.getLogger(__name__)


class AgentAuthError(Exception):
    """El token no es válido / no se pudo verificar."""


def user_id_from_claims(claims: dict[str, Any]) -> str:
    """El user_id canónico de la plataforma es el `sub` del JWT de Clerk."""
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise AgentAuthError("token has no sub claim")
    return sub


def request_user_id(request: Request) -> str:
    """Dependencia FastAPI: usuario autenticado inyectado por ClerkAuthMiddleware.

    El middleware verifica el JWT en toda ruta HTTP (salvo /api/health) y deja
    el sub en request.state.user_id. Si falta, la request no pasó por el
    middleware o el token no traía sub → 401.
    """
    uid = getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return uid


def _derive_domain_from_pk() -> Optional[str]:
    pk = os.getenv("CLERK_PUBLISHABLE_KEY", "")
    parts = pk.split("_")
    if len(parts) < 3:
        return None
    encoded = parts[2]
    padding = 4 - len(encoded) % 4
    if padding != 4:
        encoded += "=" * padding
    try:
        return base64.b64decode(encoded).decode("utf-8").rstrip("$")
    except Exception:
        return None


def _jwks_url() -> str:
    url = os.getenv("CLERK_JWKS_URL", "").strip()
    if url:
        return url
    domain = _derive_domain_from_pk()
    if not domain:
        raise AgentAuthError("CLERK_JWKS_URL / CLERK_PUBLISHABLE_KEY not configured")
    return f"https://{domain}/.well-known/jwks.json"


def _issuer() -> Optional[str]:
    iss = os.getenv("CLERK_ISSUER", "").strip()
    if iss:
        return iss
    domain = _derive_domain_from_pk()
    return f"https://{domain}" if domain else None


# Cliente JWKS con caché (las claves públicas de Clerk rotan rara vez).
_jwk_client: Optional[PyJWKClient] = None


def _get_jwk_client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(_jwks_url(), cache_keys=True, lifespan=3600)
    return _jwk_client


def verify_clerk_token(token: str) -> dict[str, Any]:
    """Verifica un JWT de Clerk. Devuelve los claims o lanza AgentAuthError."""
    if not token:
        raise AgentAuthError("missing token")
    try:
        signing_key = _get_jwk_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=_issuer(),
            options={
                "verify_aud": False,  # Clerk no siempre incluye audience
                "verify_exp": True,
                "verify_iss": bool(_issuer()),
                "require": ["exp", "iat", "sub"],
            },
        )
    except AgentAuthError:
        raise
    except Exception as exc:  # noqa: BLE001 — jwt lanza varios tipos
        raise AgentAuthError(str(exc)) from exc


def extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    """Extrae el token de un header 'Authorization: Bearer <jwt>'."""
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization[7:].strip()
    return None


def extract_ws_token(raw_query_string: str) -> Optional[str]:
    """Extrae ?token=<jwt> del query string de una conexión WebSocket."""
    if not raw_query_string:
        return None
    qs = parse_qs(raw_query_string)
    values = qs.get("token")
    if values:
        return values[0]
    return None
