"""
Lake Archiver Scheduler — Event Lake (Backtester v2, Fase 0)
============================================================
Loop horario que ejecuta ArchiveMarketEventsTask en modo catch-up.

¿Por qué horario y no una vez por noche? La retención de `market_events` es
de solo 3 días: si el job nocturno fallara dos noches seguidas (deploy, caída
de red, disco lleno), empezaríamos a perder historia irrecuperable. El task
es idempotente y barato cuando no hay nada nuevo (un stat de manifiesto por
día), así que pasar cada hora compra resiliencia gratis.

Corre una pasada inmediata al arrancar (recuperación tras deploys).
"""

import asyncio
import sys

sys.path.append('/app')

from shared.utils.logger import get_logger
from shared.utils.timescale_client import TimescaleClient
from tasks.archive_market_events import ArchiveMarketEventsTask
from tasks.archive_reference_snapshots import ArchiveReferenceSnapshotsTask

logger = get_logger(__name__)

INTERVAL_SECONDS = 3600


class LakeArchiverScheduler:
    """Pasada de archivado cada hora, con pasada inicial al arrancar."""

    def __init__(self, timescale_client: TimescaleClient):
        self.events_task = ArchiveMarketEventsTask(timescale_client)
        self.reference_task = ArchiveReferenceSnapshotsTask(timescale_client)

    async def run(self) -> None:
        logger.info("lake_archiver_scheduler started (interval=%ss)", INTERVAL_SECONDS)
        while True:
            try:
                results = await self.events_task.execute()
                archived = [r for r in results if r["status"] == "archived"]
                errors = [r for r in results if r["status"] == "error"]
                if archived or errors:
                    logger.info(
                        "lake_archiver pass: archived=%s errors=%s",
                        [f"{r['date']}({r['total_rows']})" for r in archived],
                        [r["date"] for r in errors],
                    )
            except Exception as exc:  # noqa: BLE001 — el loop nunca muere
                logger.error("lake_archiver events pass failed: %s", exc)
            try:
                # Snapshot point-in-time del universo: idempotente, 1×/día ET.
                await self.reference_task.execute()
            except Exception as exc:  # noqa: BLE001
                logger.error("lake_archiver reference pass failed: %s", exc)
            await asyncio.sleep(INTERVAL_SECONDS)
