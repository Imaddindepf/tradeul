"""
Archive Scanner Categories — Event Lake (Backtester v2, Fase 0)
===============================================================
Snapshot horario (en horario de mercado ET) de las categorías core del
scanner a Parquet:

    /data/lake/reference/scanner_categories/dt=YYYY-MM-DD/snap-HH.parquet

Hoy las categorías (gappers_up, momentum_up, anomalies…) viven solo en Redis
y se recalculan en vivo: "qué tickers eran gappers_up el día X a las 10:00"
es irreconstruible. Este snapshot lo hace posible — universos de backtest
del tipo "los gappers de aquella mañana".

Se archivan solo las categorías CORE (catálogo público de la plataforma);
los user-scans (uscan_*) son por-usuario y quedan fuera del lake.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.append('/app')

import pyarrow as pa
import pyarrow.parquet as pq

from shared.utils.logger import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)

ET = ZoneInfo("America/New_York")
SCHEMA_VERSION = 1

# Sesión extendida: pre-market 4:00 → post-market 20:00 ET.
MARKET_OPEN_HOUR = 4
MARKET_CLOSE_HOUR = 20

CORE_CATEGORIES = [
    "gappers_up", "gappers_down", "momentum_up", "momentum_down",
    "anomalies", "new_highs", "new_lows", "winners", "losers",
    "high_volume", "reversals", "post_market",
]

# Campos compactos por fila: identidad + rank + métricas clave del momento.
# El resto del payload enriquecido es reconstruible desde eventos/barras.
_ROW_FIELDS = [
    "symbol", "price", "volume", "minute_volume", "open", "high", "low",
    "bid", "ask", "spread_percent",
]

_SCHEMA = pa.schema(
    [pa.field("category", pa.string()), pa.field("rank", pa.int32())]
    + [
        pa.field(f, pa.string() if f == "symbol" else pa.float64())
        for f in _ROW_FIELDS
    ]
    + [pa.field("captured_at", pa.timestamp("us", tz="UTC"))]
)


def lake_categories_dir() -> Path:
    return Path(os.getenv("LAKE_DIR", "/data/lake")) / "reference" / "scanner_categories"


class ArchiveScannerCategoriesTask:
    """Snapshot de categorías core del scanner (idempotente por hora ET)."""

    name = "archive_scanner_categories"

    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client

    def _in_market_hours(self, now_et: datetime) -> bool:
        return (
            now_et.weekday() < 5
            and MARKET_OPEN_HOUR <= now_et.hour < MARKET_CLOSE_HOUR
        )

    async def execute(self, force: bool = False) -> dict[str, Any]:
        now_et = datetime.now(ET)
        if not force and not self._in_market_hours(now_et):
            return {"status": "outside_market_hours"}

        day_dir = lake_categories_dir() / f"dt={now_et.date().isoformat()}"
        out_path = day_dir / f"snap-{now_et.hour:02d}.parquet"
        if out_path.exists() and not force:
            return {"status": "skipped", "snapshot": out_path.name}

        captured_at = datetime.now(timezone.utc)
        records: list[dict[str, Any]] = []
        missing: list[str] = []
        for category in CORE_CATEGORIES:
            # RedisClient.get() ya deserializa JSON por defecto; se acepta
            # también el caso de string cruda por robustez.
            raw = await self.redis.get(f"scanner:category:{category}")
            if not raw:
                missing.append(category)
                continue
            if isinstance(raw, (list, dict)):
                rows = raw
            else:
                try:
                    rows = json.loads(raw)
                except (TypeError, ValueError):
                    logger.warning("scanner category %s: payload inválido, se omite", category)
                    continue
            for rank, row in enumerate(rows if isinstance(rows, list) else []):
                rec: dict[str, Any] = {
                    "category": category,
                    "rank": rank,
                    "captured_at": captured_at,
                }
                for f in _ROW_FIELDS:
                    v = row.get(f)
                    if f == "symbol":
                        rec[f] = v if isinstance(v, str) else None
                    else:
                        rec[f] = float(v) if isinstance(v, (int, float)) else None
                records.append(rec)

        if not records:
            return {"status": "empty", "missing": missing}

        day_dir.mkdir(parents=True, exist_ok=True)
        tmp = day_dir / f".{out_path.name}.tmp"
        pq.write_table(pa.Table.from_pylist(records, schema=_SCHEMA), tmp, compression="zstd")
        os.rename(tmp, out_path)

        logger.info(
            "scanner categories archived %s rows=%d categories=%d missing=%s",
            out_path.name, len(records),
            len(CORE_CATEGORIES) - len(missing), missing or "none",
        )
        return {
            "status": "archived",
            "snapshot": str(out_path.name),
            "rows": len(records),
            "missing": missing,
        }


async def _main() -> int:
    db = RedisClient()
    await db.connect()
    try:
        result = await ArchiveScannerCategoriesTask(db).execute(force=True)
    finally:
        await db.disconnect()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
