"""
Polygon News Service

Ingesta de /v2/reference/news de Polygon hacia el pipeline unificado de
noticias, con la capa exclusiva de sentimiento por ticker (insights).
"""

import logging
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
import structlog
import redis.asyncio as aioredis

from config import settings
from tasks.stream_manager import PolygonNewsStreamManager

logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    force=True,
)

# httpx loguea a INFO la URL completa de cada request (incluida la API key)
logging.getLogger("httpx").setLevel(logging.WARNING)

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

redis_client: Optional[aioredis.Redis] = None
stream_manager: Optional[PolygonNewsStreamManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, stream_manager

    logger.info("🚀 Starting Polygon News Service...")

    redis_url = f"redis://{settings.redis_host}:{settings.redis_port}"
    if settings.redis_password:
        redis_url = f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}"

    redis_client = await aioredis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_keepalive=True,
        health_check_interval=30,
        retry_on_timeout=True,
    )
    await redis_client.ping()
    logger.info("✅ Connected to Redis")

    stream_manager = PolygonNewsStreamManager(
        redis_client=redis_client,
        api_key=settings.polygon_api_key,
        base_url=settings.polygon_base_url,
        settings=settings,
    )
    await stream_manager.start()

    yield

    logger.info("Shutting down Polygon News Service...")
    if stream_manager:
        await stream_manager.stop()
    if redis_client:
        await redis_client.aclose()


app = FastAPI(title="Polygon News Service", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "polygon-news"}


@app.get("/status")
async def status():
    return {
        "service": "polygon-news",
        "stats": stream_manager.stats if stream_manager else {},
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.service_port, log_level="info")
