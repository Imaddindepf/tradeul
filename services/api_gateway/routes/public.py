"""
Public API Routes (sin autenticación).

Endpoints expuestos al landing page y consumidores externos no autenticados.
Todos los endpoints aquí:
- No requieren token.
- Usan cache in-memory corto (3-5s) para proteger Redis y reducir carga.
- Devuelven payloads mínimos (sin datos sensibles).
"""
import logging
import time
from typing import List, Optional

import orjson
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

logger = logging.getLogger("api_gateway.public")

# Redis client inyectado desde main.py
redis_client = None


def set_redis_client(client):
    global redis_client
    redis_client = client


router = APIRouter(prefix="/api/public", tags=["public"])


# ============================================================================
# Models
# ============================================================================

class MoverTicker(BaseModel):
    symbol: str
    price: Optional[float] = None
    change_percent: Optional[float] = None
    volume: Optional[int] = None


class TopMoversResponse(BaseModel):
    tickers: List[MoverTicker]
    updated_at: float
    source: str  # "latest" | "last_close" | "cache"


# ============================================================================
# In-memory cache (TTL corto, compartido entre workers si hay muchas réplicas
# Redis haría de coordinador, pero para un ticker tape esto es más que suficiente)
# ============================================================================

_CACHE: dict = {"data": None, "ts": 0.0, "source": ""}
_CACHE_TTL_S = 4.0  # 4 segundos — el marquee del front refresca cada 5s


async def _fetch_snapshot_from_redis() -> tuple[list[dict], str]:
    """Lee el snapshot enriquecido de Redis. Prefiere 'latest', si no existe cae a 'last_close'."""
    if redis_client is None:
        return [], "no_redis"

    try:
        all_hash_data = await redis_client.client.hgetall("snapshot:enriched:latest")
        source = "latest"
        if not all_hash_data:
            all_hash_data = await redis_client.client.hgetall("snapshot:enriched:last_close")
            source = "last_close"

        if not all_hash_data:
            return [], "empty"

        # Quitar metadatos
        all_hash_data.pop(b"__meta__", None)
        all_hash_data.pop("__meta__", None)

        tickers: list[dict] = []
        for _, ticker_json in all_hash_data.items():
            try:
                tickers.append(orjson.loads(ticker_json))
            except Exception:
                continue

        return tickers, source
    except Exception as e:
        logger.error(f"public.snapshot_fetch_error error={e}")
        return [], "error"


def _extract_symbol(t: dict) -> Optional[str]:
    return t.get("ticker") or t.get("symbol") or None


def _extract_price(t: dict) -> Optional[float]:
    price = t.get("current_price")
    if price is None:
        lt = t.get("lastTrade") or {}
        if isinstance(lt, dict):
            price = lt.get("p")
    try:
        return float(price) if price is not None else None
    except (TypeError, ValueError):
        return None


def _extract_change_pct(t: dict) -> Optional[float]:
    chg = t.get("todaysChangePerc") or t.get("change_percent")
    try:
        return float(chg) if chg is not None else None
    except (TypeError, ValueError):
        return None


def _extract_volume(t: dict) -> Optional[int]:
    vol = t.get("current_volume") or t.get("volume")
    if vol is None:
        day = t.get("day") or {}
        if isinstance(day, dict):
            vol = day.get("v")
    try:
        return int(vol) if vol is not None else None
    except (TypeError, ValueError):
        return None


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/top-movers", response_model=TopMoversResponse)
async def get_top_movers(
    response: Response,
    limit: int = Query(20, ge=1, le=50, description="Total de tickers a devolver"),
    min_price: float = Query(1.0, ge=0.0, description="Precio mínimo (filtra pennies muy finos)"),
    min_volume: int = Query(100_000, ge=0, description="Volumen mínimo del día"),
    max_abs_change: float = Query(
        50.0,
        ge=0.0,
        description="Cambio % absoluto máximo. Evita artefactos de splits/fusiones (ej: +700%) en la cinta.",
    ),
    mix: str = Query(
        "balanced",
        description="'balanced' (mitad gainers, mitad losers) | 'gainers' | 'losers' | 'abs' (top por |%|)",
    ),
):
    """
    Top movers del mercado — endpoint público para el ticker tape del landing.

    - Sin autenticación.
    - Cache in-memory 4s.
    - Lee del snapshot enriquecido en Redis (prioriza intraday, cae a last_close fuera de mercado).
    - Filtra pennies muy finos y baja liquidez por defecto para evitar ruido en la cinta.
    """
    now = time.time()

    # Cache-Control header para que el browser/CDN también cachee un poquito
    response.headers["Cache-Control"] = "public, max-age=4, s-maxage=4"

    cache_key = f"{limit}:{min_price}:{min_volume}:{max_abs_change}:{mix}"

    # ── Cache hit ────────────────────────────────────────────────────────
    if _CACHE["data"] is not None and _CACHE.get("key") == cache_key and (now - _CACHE["ts"]) < _CACHE_TTL_S:
        return TopMoversResponse(
            tickers=_CACHE["data"],
            updated_at=_CACHE["ts"],
            source=f"cache:{_CACHE['source']}",
        )

    # ── Fetch fresh ──────────────────────────────────────────────────────
    raw_tickers, source = await _fetch_snapshot_from_redis()

    if not raw_tickers:
        # Fallback vacío — el front debe tener su propio fallback estático
        return TopMoversResponse(tickers=[], updated_at=now, source=source)

    # Normalizar + filtrar mínimos
    normalized: list[MoverTicker] = []
    for t in raw_tickers:
        sym = _extract_symbol(t)
        if not sym:
            continue
        price = _extract_price(t)
        chg = _extract_change_pct(t)
        vol = _extract_volume(t)

        if price is None or chg is None:
            continue
        if price < min_price:
            continue
        if vol is not None and vol < min_volume:
            continue
        if max_abs_change > 0 and abs(chg) > max_abs_change:
            continue

        normalized.append(MoverTicker(symbol=sym, price=price, change_percent=chg, volume=vol))

    if not normalized:
        return TopMoversResponse(tickers=[], updated_at=now, source=source)

    # Selección según mix
    if mix == "gainers":
        normalized.sort(key=lambda m: m.change_percent or 0.0, reverse=True)
        selected = normalized[:limit]
    elif mix == "losers":
        normalized.sort(key=lambda m: m.change_percent or 0.0)
        selected = normalized[:limit]
    elif mix == "abs":
        normalized.sort(key=lambda m: abs(m.change_percent or 0.0), reverse=True)
        selected = normalized[:limit]
    else:  # balanced
        half = max(1, limit // 2)
        by_chg = sorted(normalized, key=lambda m: m.change_percent or 0.0, reverse=True)
        gainers = by_chg[:half]
        losers = sorted(normalized, key=lambda m: m.change_percent or 0.0)[:limit - half]
        # Interleave para que la cinta visual alterne verde/rojo de forma natural
        selected: list[MoverTicker] = []
        g_iter = iter(gainers)
        l_iter = iter(losers)
        for _ in range(limit):
            try:
                selected.append(next(g_iter))
            except StopIteration:
                pass
            try:
                selected.append(next(l_iter))
            except StopIteration:
                pass
            if len(selected) >= limit:
                break
        selected = selected[:limit]

    # Guardar en cache
    _CACHE["data"] = selected
    _CACHE["ts"] = now
    _CACHE["source"] = source
    _CACHE["key"] = cache_key

    logger.info(
        f"public.top_movers_served count={len(selected)} mix={mix} "
        f"source={source} limit={limit}"
    )

    return TopMoversResponse(tickers=selected, updated_at=now, source=source)
