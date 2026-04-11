"""
Sync Dilution Scores → Redis
============================
Pipeline:
  1. Llama a dilution-tracker /batch-score/run-sync para recalcular TODOS los
     tickers desde la DB (sin Polygon ni Perplexity) — tarda ~1 segundo.
  2. Lee la tabla `dilution_scores` de la BD local (tradeul) ya actualizada.
  3. Vuelca los ratings al hash Redis `dilution:scores:latest` para que el
     enrichment pipeline los inyecte en cada ticker enriquecido.

Ejecutado:
  1. Como tarea diaria dentro del ciclo de mantenimiento (data_maintenance).
  2. Al arrancar el servicio data_maintenance (startup populate).
  3. Disparable manualmente vía endpoint /api/maintenance/trigger.
"""

import asyncio
import orjson
from datetime import datetime
from typing import Any, Dict

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)

DILUTION_SCORES_KEY   = "dilution:scores:latest"
# Canales/claves Redis para comunicación con dilution-tracker
BATCH_TRIGGER_CHANNEL = "dilution:batch:trigger"
BATCH_RESULT_KEY      = "dilution:batch:last_result"
BATCH_TIMEOUT_S       = 120   # máx 2 minutos esperando el resultado

# Mapping Low/Medium/High → 1/2/3
_LABEL_TO_INT = {"Low": 1, "Medium": 2, "High": 3}


def _label_to_int(label: str | None) -> int | None:
    return _LABEL_TO_INT.get(label) if label else None


class SyncDilutionScoresTask:
    """
    Recalcula todos los risk ratings via dilution-tracker (batch scorer) y
    luego vuelca los resultados desde la tabla local `dilution_scores` a Redis.
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

        # ── Paso 1: Disparar el batch scorer en dilution-tracker y esperar ──────
        await self._trigger_batch_scorer()

        # ── Paso 2: Leer tabla local ya actualizada ───────────────────────────────
        try:
            rows = await self.db.fetch(self.RATINGS_QUERY)
        except Exception as exc:
            logger.error("sync_dilution_scores_db_failed", error=str(exc))
            return {"success": False, "error": str(exc)}

        if not rows:
            logger.warning("sync_dilution_scores_no_rows",
                           note="Table dilution_scores is empty.")
            return {"success": True, "tickers_synced": 0, "note": "no rated tickers"}

        # ── Paso 3: Volcar a Redis ────────────────────────────────────────────────
        written = await self._write_to_redis(rows)

        elapsed = (datetime.now() - start).total_seconds()
        logger.info(
            "sync_dilution_scores_done",
            tickers_synced=written,
            elapsed_s=round(elapsed, 2),
        )
        return {"success": True, "tickers_synced": written, "elapsed_s": elapsed}

    async def _trigger_batch_scorer(self) -> None:
        """
        Dispara el batch scorer en dilution-tracker vía Redis pub/sub y
        espera el resultado (máx BATCH_TIMEOUT_S segundos).
        Fallo no es fatal — los datos del ciclo anterior siguen válidos.
        """
        try:
            # Borrar resultado anterior para no confundirlo con el nuevo
            await self.redis.client.delete(BATCH_RESULT_KEY)

            # Publicar el trigger
            await self.redis.client.publish(BATCH_TRIGGER_CHANNEL, "run")
            logger.info("sync_dilution_scores_trigger_sent", channel=BATCH_TRIGGER_CHANNEL)

            # Esperar el resultado (polling cada 0.5s con timeout)
            deadline = asyncio.get_event_loop().time() + BATCH_TIMEOUT_S
            while asyncio.get_event_loop().time() < deadline:
                raw = await self.redis.client.get(BATCH_RESULT_KEY)
                if raw:
                    result = orjson.loads(raw)
                    if result.get("ok"):
                        logger.info(
                            "sync_dilution_scores_batch_done",
                            scored=result.get("scored"),
                            elapsed_ms=result.get("elapsed_ms"),
                        )
                    else:
                        logger.warning("sync_dilution_scores_batch_error", result=result)
                    return
                await asyncio.sleep(0.5)

            logger.warning(
                "sync_dilution_scores_batch_timeout",
                timeout_s=BATCH_TIMEOUT_S,
                note="Continuing with existing dilution_scores data",
            )
        except Exception as exc:
            logger.warning(
                "sync_dilution_scores_batch_failed",
                error=str(exc),
                note="Continuing with existing dilution_scores data",
            )

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
