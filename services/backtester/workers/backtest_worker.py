"""
Backtest job worker: consumes queue, runs backtest, saves result.

Run: python -m workers.backtest_worker
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.chdir(Path(__file__).resolve().parents[1])

import structlog
from config import settings
from core.data_layer import DataLayer
from core.engine import BacktestEngine
from application.run_backtest_sync import execute_backtest_job
from infrastructure.job_repository import RedisJobRepository
from infrastructure.queue import RedisJobQueue

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger(__name__)


def main() -> None:
    redis_url = getattr(settings, "redis_url", "redis://redis:6379")
    queue_name = getattr(settings, "jobs_queue_name", "backtester:jobs")
    ttl = getattr(settings, "job_result_ttl_seconds", 7 * 24 * 3600)

    queue = RedisJobQueue(redis_url, queue_name)
    repo = RedisJobRepository(redis_url, ttl)

    rest_cache = settings.splits_cache_dir.parent / "rest_cache"
    data_layer = DataLayer(
        polygon_data_dir=settings.polygon_data_dir,
        polygon_api_key=settings.polygon_api_key,
        rest_cache_dir=rest_cache,
        minute_aggs_dir=settings.minute_aggs_dir,
    )
    engine = BacktestEngine(data_layer)
    logger.info("backtest_worker_started", queue=queue_name)

    while True:
        try:
            item = queue.dequeue(timeout_seconds=5)
        except Exception as e:
            logger.warning("dequeue_error", error=str(e))
            continue
        if item is None:
            continue
        job_id, data = item
        job_type = data.get("type", "template")
        payload = data.get("payload", data)
        meta = repo.get_job(job_id)
        user_id = (meta or {}).get("user_id")
        if user_id and hasattr(repo, "add_to_running"):
            repo.add_to_running(user_id, job_id)
        logger.info("job_started", job_id=job_id, type=job_type)
        repo.update_job(job_id, {"status": "running", "message": "Running backtest..."})

        def progress_cb(msg: str, pct: float) -> None:
            repo.update_job(job_id, {"message": msg, "progress_pct": round(pct * 100)})

        try:
            response = asyncio.run(
                execute_backtest_job(
                    job_type, payload, data_layer, engine, progress_callback=progress_cb
                )
            )
            if response.status == "success" and response.result is not None:
                repo.set_result(job_id, response)
                repo.update_job(job_id, {"status": "completed", "progress_pct": 100, "message": "Done"})
                if user_id and hasattr(repo, "remove_from_running"):
                    repo.remove_from_running(user_id, job_id)
                logger.info("job_completed", job_id=job_id, trades=response.result.core_metrics.total_trades)
            else:
                err = response.error or "Unknown error"
                repo.set_error(job_id, err)
                logger.warning("job_failed", job_id=job_id, error=err)
        except Exception as e:
            repo.set_error(job_id, str(e))
            logger.exception("job_crashed", job_id=job_id)
    data_layer.close()


if __name__ == "__main__":
    main()
