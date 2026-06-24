"""
Tools internas para el Brief de Contexto.

Exponen datos de NUESTROS endpoints internos al LLM, SIN revelar de qué
proveedor vienen (eso es interno). El LLM solo ve "datos internos de Tradeul".

Cada tool es best-effort: si el endpoint falla, devuelve {"error": ...} para
que el modelo sepa que ese dato no está disponible (y no invente).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

# Campos que NUNCA deben llegar al modelo (revelan proveedor / ruido interno).
_STRIP_KEYS = {"source", "symbiotic", "updatedAt", "last_updated", "created_at",
               "updated_at", "data_source"}


def _strip(obj: Any) -> Any:
    """Elimina recursivamente claves que revelan proveedor o son ruido."""
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in _STRIP_KEYS}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


async def _get(client: httpx.AsyncClient, url: str) -> Optional[Any]:
    try:
        r = await client.get(url, timeout=settings.tool_timeout_s)
        if r.status_code == 200:
            return r.json()
        logger.warning("tool_http_non200 url=%s status=%d", url, r.status_code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tool_http_error url=%s err=%s", url, exc)
    return None


def _flatten_key_metrics(km: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Convierte {groups:[{title, rows:[{label,value}]}]} -> {title: {label: value}}."""
    out: Dict[str, Dict[str, Any]] = {}
    for g in (km.get("groups") or []):
        title = g.get("title") or "Otros"
        rows = {}
        for row in (g.get("rows") or []):
            label = row.get("label")
            if label is not None and row.get("value") is not None:
                rows[label] = row.get("value")
        if rows:
            out[title] = rows
    return out


# ─────────────────────────────────────────────────────────────────────────
# TOOL 1: Fundamentales / situación financiera
# ─────────────────────────────────────────────────────────────────────────
async def get_company_fundamentals(ticker: str) -> Dict[str, Any]:
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return {"error": "ticker vacío"}
    base = settings.gateway_url
    async with httpx.AsyncClient() as client:
        desc, km = await asyncio.gather(
            _get(client, f"{base}/api/v1/ticker/{ticker}/description"),
            _get(client, f"{base}/api/report/{ticker}/key-metrics"),
        )

    if not desc and not km:
        return {"error": f"sin datos fundamentales para {ticker}"}

    result: Dict[str, Any] = {"ticker": ticker}

    if desc:
        company = desc.get("company") or {}
        comp_desc = (company.get("description") or "")[:600]
        result["identity"] = {
            "name": company.get("name"),
            "exchange": company.get("exchange"),
            "sector": company.get("sector"),
            "industry": company.get("industry"),
            "is_spac": company.get("is_spac"),
            "description": comp_desc,
        }
        if desc.get("stats"):
            result["stats"] = _strip(desc["stats"])
        if desc.get("valuation"):
            result["valuation"] = _strip(desc["valuation"])
        if desc.get("ratios"):
            result["ratios"] = _strip(desc["ratios"])

    if km:
        result["financials"] = _flatten_key_metrics(km)

    return result


# ─────────────────────────────────────────────────────────────────────────
# TOOL 2: Consenso de analistas / precios objetivo
# ─────────────────────────────────────────────────────────────────────────
async def get_analyst_ratings(ticker: str) -> Dict[str, Any]:
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return {"error": "ticker vacío"}
    base = settings.gateway_url
    async with httpx.AsyncClient() as client:
        desc = await _get(client, f"{base}/api/v1/ticker/{ticker}/description")

    if not desc:
        return {"error": f"sin datos de analistas para {ticker}"}

    rating = desc.get("analystRating")
    targets = desc.get("priceTargets") or []
    # Quedarnos con los más recientes y limpios.
    targets = _strip(targets)[: settings.max_price_targets]

    if not rating and not targets and desc.get("consensusTarget") is None:
        return {"error": f"sin cobertura de analistas para {ticker}"}

    return {
        "ticker": ticker,
        "rating": _strip(rating) if rating else None,
        "consensus_target": desc.get("consensusTarget"),
        "target_upside_pct": desc.get("targetUpside"),
        "recent_price_targets": targets,
    }


# ─────────────────────────────────────────────────────────────────────────
# TOOL 3: Caja, runway y estructura de dilución
# ─────────────────────────────────────────────────────────────────────────
async def get_cash_and_dilution(ticker: str) -> Dict[str, Any]:
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return {"error": "ticker vacío"}
    base = settings.dilution_url
    async with httpx.AsyncClient() as client:
        ctx, runway = await asyncio.gather(
            _get(client, f"{base}/api/instrument-context/{ticker}"),
            _get(client, f"{base}/api/sec-dilution/{ticker}/cash-runway-enhanced"),
        )

    if not ctx and not runway:
        return {"error": f"sin datos de caja/dilución para {ticker}"}

    result: Dict[str, Any] = {"ticker": ticker}

    if ctx:
        ti = _strip(ctx.get("ticker_info") or {})
        result["snapshot"] = ti
        # Resumen compacto de instrumentos de dilución (ATM/shelf/ofertas).
        instruments = []
        for ins in (ctx.get("instruments") or [])[: settings.max_instruments]:
            det = ins.get("details") or {}
            instruments.append({
                "type": ins.get("offering_type"),
                "name": ins.get("security_name"),
                "status": ins.get("reg_status"),
                "total_capacity": det.get("total_atm_capacity"),
                "remaining_capacity": det.get("remaining_atm_capacity"),
                "limited_by_baby_shelf": det.get("atm_limited_by_baby_shelf"),
            })
        if instruments:
            result["dilution_instruments"] = instruments
        if ctx.get("completed_offerings") is not None:
            co = ctx.get("completed_offerings")
            result["completed_offerings_count"] = len(co) if isinstance(co, list) else co

    if runway:
        result["cash_runway"] = {
            "estimated_current_cash": runway.get("estimated_current_cash"),
            "runway_days": runway.get("runway_days"),
            "runway_months": runway.get("runway_months"),
            "runway_risk_level": runway.get("runway_risk_level"),
            "daily_burn_rate": runway.get("daily_burn_rate"),
        }

    return result


# ─────────────────────────────────────────────────────────────────────────
# Registro: nombre -> (callable, descripción para el LLM, schema)
# Las descripciones NO mencionan proveedores. Son "datos internos de Tradeul".
# ─────────────────────────────────────────────────────────────────────────
def _ticker_schema(desc: str) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {"ticker": {"type": "string", "description": "Símbolo, ej. TSLA"}},
        "required": ["ticker"],
    }


TOOL_REGISTRY = {
    "get_company_fundamentals": {
        "fn": get_company_fundamentals,
        "description": (
            "Datos fundamentales internos de Tradeul para un ticker: identidad "
            "(nombre, sector, industria, descripción del negocio), estructura de "
            "capital (market cap, EV, acciones, deuda), valoración (P/E, márgenes) "
            "y situación financiera. Úsalo SOLO cuando el fundamento financiero sea "
            "relevante para entender la noticia (resultados, guidance, valoración). "
            "Para eventos puramente cualitativos (investigación, demanda, regulación) "
            "no suele hacer falta."
        ),
        "schema": _ticker_schema("fundamentales"),
    },
    "get_analyst_ratings": {
        "fn": get_analyst_ratings,
        "description": (
            "Consenso de analistas y precios objetivo internos de Tradeul para un "
            "ticker (rating, target medio, upside, targets recientes por firma). "
            "Úsalo cuando la reacción de Wall Street o la valoración importen."
        ),
        "schema": _ticker_schema("analistas"),
    },
    "get_cash_and_dilution": {
        "fn": get_cash_and_dilution,
        "description": (
            "Situación de caja, runway, burn rate y estructura de dilución interna "
            "de Tradeul (ATM, shelf, ofertas completadas, acciones, cash por acción). "
            "CLAVE para small caps y para cualquier catalizador de financiación, "
            "oferta de acciones o riesgo de supervivencia."
        ),
        "schema": _ticker_schema("caja y dilución"),
    },
}


async def execute_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    spec = TOOL_REGISTRY.get(name)
    if not spec:
        return {"error": f"tool desconocida: {name}"}
    ticker = args.get("ticker", "")
    try:
        return await spec["fn"](ticker)
    except Exception as exc:  # noqa: BLE001
        logger.exception("tool_exec_failed name=%s", name)
        return {"error": f"fallo ejecutando {name}: {exc}"}


def anthropic_tool_defs() -> List[Dict[str, Any]]:
    """Definiciones de las custom tools para la Messages API."""
    return [
        {
            "name": name,
            "description": spec["description"],
            "input_schema": spec["schema"],
        }
        for name, spec in TOOL_REGISTRY.items()
    ]
