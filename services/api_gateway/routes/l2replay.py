"""
L2 Replay API — montaje Level 2 por venue reproducido desde histórico Databento.

Superficie que consume la ventana flotante "L2 Replay" del workspace:

    GET /api/v1/l2replay/health              estado + venues
    GET /api/v1/l2replay/start?...           lanza un job de descarga (28 fetches)
    GET /api/v1/l2replay/progress?job=...    avance del job
    GET /api/v1/l2replay/result?job=...      payload completo (frames conflacionados)
    GET /api/v1/l2replay/cost?...            coste estimado en USD antes de descargar

La lógica vive en l2replay_core (extraída del demo verificado): saneado DBN por
tipo (centinelas INT64/UINT32/UINT64 max), orden por ts_recv, semántica de
acciones (T/F/N no tocan libro, R limpia por publicador), F_LAST con red de
seguridad, convención de ticker CMS/Nasdaq por venue, caché en disco (cada
petición repetida a Databento SE COBRA) y reintentos solo en 429/500/503/504.

Requiere DATABENTO_API_KEY en el entorno del gateway. Sin ella, /health lo dice
y el resto devuelve 503 — la ventana lo muestra como aviso, no como crash.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import get_current_user
from shared.utils.logger import get_logger

import l2replay_core as core

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/l2replay", tags=["l2replay"])

SCHEMAS = ("mbp-1", "bbo-1s")
MAX_MINUTES = 120


def _parse_start(date_str: str, time_str: str) -> datetime:
    """'2026-08-03' + '09:45:00' en hora ET -> datetime UTC.

    Fin de semana se rechaza aquí además de en la UI: la API es superficie
    pública y una llamada directa no debe gastar 30 peticiones a Databento
    para descubrir que el mercado estaba cerrado.
    """
    if len(time_str) == 5:
        time_str += ":00"
    try:
        naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise HTTPException(status_code=422, detail="Fecha u hora inválidas")
    if naive.weekday() >= 5:
        dia = "sábado" if naive.weekday() == 5 else "domingo"
        raise HTTPException(status_code=422, detail=f"El {dia} el mercado está cerrado")
    return naive.replace(tzinfo=core.ET).astimezone(timezone.utc)


def _require_key():
    if not core.KEY:
        raise HTTPException(
            status_code=503,
            detail="DATABENTO_API_KEY no configurada en el gateway")


@router.get("/health")
async def health(user=Depends(get_current_user)):
    return {"ok": bool(core.KEY), "venues": core.LABELS,
            "conflateMs": core.CONFLATE_MS, "warmupSec": core.WARMUP_SEC}


@router.get("/start")
async def start(
    symbol: str = Query(..., min_length=1, max_length=12),
    date: str = Query(...),
    time: str = Query(...),
    minutes: int = Query(5, ge=1, le=MAX_MINUTES),
    seconds: int = Query(0, ge=0, le=7200),
    schema: str = Query("mbp-1"),
    tape: bool = Query(True),
    user=Depends(get_current_user),
):
    _require_key()
    if schema not in SCHEMAS:
        schema = "mbp-1"
    start_utc = _parse_start(date, time)
    sym = symbol.upper().strip()
    jid = core.start_job(sym, start_utc, minutes, schema, tape, seconds=seconds or None)
    logger.info("l2replay_start", symbol=sym, date=date, time=time,
                minutes=minutes, schema=schema, job=jid)
    return {"ok": True, "job": jid}


@router.get("/progress")
async def progress(job: str = Query(...), user=Depends(get_current_user)):
    with core.JOBS_LOCK:
        j = core.JOBS.get(job)
        if not j:
            return {"ok": False, "error": "job desconocido"}
        return {"ok": True, "done": j["done"], "total": j["total"],
                "venue": j["venue"], "ready": j["ready"], "error": j["error"]}


@router.get("/result")
async def result(job: str = Query(...), user=Depends(get_current_user)):
    with core.JOBS_LOCK:
        j = core.JOBS.get(job)
        if not j:
            return {"ok": False, "error": "job desconocido"}
        if not j["ready"]:
            # No se destruye el job por pedirlo pronto: el cliente sondea
            # /progress, pero una carrera no debe costar la descarga entera.
            return {"ok": False, "error": "not_ready"}
        core.JOBS.pop(job, None)
    if j["error"]:
        return {"ok": False, "error": j["error"]}
    return j["payload"]


@router.get("/cost")
async def cost(
    symbol: str = Query(..., min_length=1, max_length=12),
    date: str = Query(...),
    time: str = Query(...),
    minutes: int = Query(5, ge=1, le=MAX_MINUTES),
    schema: str = Query("mbp-1"),
    tape: bool = Query(True),
    user=Depends(get_current_user),
):
    _require_key()
    if schema not in SCHEMAS:
        schema = "mbp-1"
    start_utc = _parse_start(date, time)
    usd = core.estimate_cost(symbol.upper().strip(), start_utc, minutes, schema, tape)
    return {"ok": True, "usd": usd}
