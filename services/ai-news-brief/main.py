"""
AI News Brief Service

POST /api/v1/brief  -> Brief Fundamental de una noticia (Claude Opus 4.8).
"""
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import settings
from brief_engine import generate_brief, continue_conversation, _load_methodology

logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO, force=True)
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)
logger = structlog.get_logger(__name__)

app = FastAPI(title="AI News Brief", version="1.0.0")


class BriefRequest(BaseModel):
    text: str = Field(..., description="Texto de la noticia")
    tickers: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    received_at: Optional[str] = None
    id: Optional[str] = None


class HistoryTurn(BaseModel):
    role: str
    content: str


class FollowupRequest(BaseModel):
    news: BriefRequest = Field(..., description="Noticia original del hilo")
    history: List[HistoryTurn] = Field(default_factory=list, description="Turnos previos")
    message: str = Field(..., description="Pregunta de seguimiento del usuario")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "ai-news-brief"}


@app.get("/status")
async def status():
    methodology = _load_methodology()
    return {
        "status": "ok" if settings.anthropic_api_key else "degraded",
        "model": settings.anthropic_model,
        "anthropic_key": bool(settings.anthropic_api_key),
        "web_search": settings.web_search_enabled,
        "internal_tools": settings.internal_tools_enabled,
        "effort": settings.effort,
        "methodology_chars": len(methodology),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/v1/brief")
async def brief(req: BriefRequest) -> Dict[str, Any]:
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    started = time.time()
    try:
        result = await generate_brief(req.model_dump())
    except RuntimeError as exc:
        logger.error("brief_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))

    result["elapsed_ms"] = int((time.time() - started) * 1000)
    logger.info(
        "brief_served",
        tickers=req.tickers,
        elapsed_ms=result["elapsed_ms"],
        sources=len(result.get("sources", [])),
        degraded=result.get("degraded"),
    )
    return result


@app.post("/api/v1/followup")
async def followup(req: FollowupRequest) -> Dict[str, Any]:
    msg = (req.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="message is required")

    started = time.time()
    try:
        result = await continue_conversation(
            news=req.news.model_dump(),
            history=[h.model_dump() for h in req.history],
            user_message=msg,
        )
    except RuntimeError as exc:
        logger.error("followup_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))

    result["elapsed_ms"] = int((time.time() - started) * 1000)
    logger.info(
        "followup_served",
        elapsed_ms=result["elapsed_ms"],
        history_len=len(req.history),
        tools_used=result.get("tools_used"),
    )
    return result


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
