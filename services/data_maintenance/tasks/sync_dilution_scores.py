"""
Sync Dilution Scores → Redis
============================
Vuelca todos los risk ratings del dilution tracker al hash Redis
`dilution:scores:latest` para que el enrichment pipeline los inyecte
en cada ticker enriquecido.

- Lee la tabla `dilution_scores` de la BD local (tradeul).
  Esta tabla es populada por `write_dilution_scores_to_redis` en dilution-tracker
  cada vez que se calculan ratings para un ticker.
- Para cada ticker con ratings calculados, escribe en Redis.
- No usa TTL: el hash persiste hasta que este task lo sobreescriba.

Ejecutado:
  1. Al arrancar el servicio data_maintenance (startup populate).
  2. Como tarea diaria dentro del ciclo de mantenimiento.
  3. Disparable manualmente vía endpoint /api/maintenance/trigger.
"""

import orjson
from datetime import datetime
from typing import Any, Dict

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)

DILUTION_SCORES_KEY = "dilution:scores:latest"

# Mapping Low/Medium/High → 1/2/3
_LABEL_TO_INT = {"Low": 1, "Medium": 2, "High": 3}


def _label_to_int(label: str | None) -> int | None:
    return _LABEL_TO_INT.get(label) if label else None


class SyncDilutionScoresTask:
    """
    Lee la tabla `dilution_scores` de la BD local (tradeul) y popula Redis.

    La tabla `dilution_scores` es mantenida por el servicio dilution-tracker:
    cada vez que calcula risk ratings para un ticker, los persiste ahí además de Redis.
    Así data_maintenance puede sincronizarlos sin acceso al remoto dilutiontracker DB.
    """

    RATINGS_QUERY = """
        SELECT
            ticker,
            overall_risk,
            offering_ability,
            overhead_supply,
            historical_dilution,
            cash_need
        FROM dilution_scores
        ORDER BY ticker
    """

    def __init__(self, redis: RedisClient, db: TimescaleClient):
        self.redis = redis
        self.db = db

    async def execute(self, _target_date=None) -> Dict[str, Any]:
        """Run the sync. Returns result dict compatible with MaintenanceOrchestrator."""
        start = datetime.now()
        logger.info("sync_dilution_scores_starting")

        try:
            rows = await self.db.fetch(self.RATINGS_QUERY)
        except Exception as exc:
            logger.error("sync_dilution_scores_db_failed", error=str(exc))
            return {"success": False, "error": str(exc)}

        if not rows:
            logger.warning("sync_dilution_scores_no_rows",
                           note="Table dilution_scores is empty; scores populate as users browse tickers.")
            return {"success": True, "tickers_synced": 0, "note": "no rated tickers in dilution_scores table yet"}

        written = await self._write_to_redis(rows)

        elapsed = (datetime.now() - start).total_seconds()
        logger.info(
            "sync_dilution_scores_done",
            tickers_synced=written,
            elapsed_s=round(elapsed, 2),
        )
        return {"success": True, "tickers_synced": written, "elapsed_s": elapsed}

    async def _write_to_redis(self, rows) -> int:
        """Batch-write all rows to Redis hash using a pipeline."""
        pipe = self.redis.client.pipeline()

        count = 0
        for row in rows:
            ticker = row["ticker"]
            if not ticker:
                continue

            overall    = row.get("overall_risk")
            offering   = row.get("offering_ability")
            overhead   = row.get("overhead_supply")
            historical = row.get("historical_dilution")
            cash_need  = row.get("cash_need")

            payload = {
                "overall_risk":               overall,
                "overall_risk_score":         _label_to_int(overall),
                "offering_ability":           offering,
                "offering_ability_score":     _label_to_int(offering),
                "overhead_supply":            overhead,
                "overhead_supply_score":      _label_to_int(overhead),
                "historical_dilution":        historical,
                "historical_dilution_score":  _label_to_int(historical),
                "cash_need":                  cash_need,
                "cash_need_score":            _label_to_int(cash_need),
                "updated_at":                 datetime.now().isoformat(),
            }

            pipe.hset(DILUTION_SCORES_KEY, ticker, orjson.dumps(payload))
            count += 1

            # Execute in batches of 500
            if count % 500 == 0:
                await pipe.execute()
                pipe = self.redis.client.pipeline()

        if count % 500 != 0 and count > 0:
            await pipe.execute()

        return count
