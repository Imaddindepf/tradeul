"""
Archive Reference Snapshots — Event Lake (Backtester v2, Fase 0)
================================================================
Snapshot diario point-in-time del universo de tickers a Parquet:

    /data/lake/reference/metadata/dt=YYYY-MM-DD/metadata.parquet

A diferencia del `screener_metadata.parquet` (snapshot único sobrescrito a
diario, solo tickers activos, sin fecha), este archivo:

- Se ACUMULA por fecha (nunca se sobrescribe un día pasado) → el motor de
  backtest hace ASOF join `dt <= fecha_del_trade` y obtiene el float/mcap
  que el ticker tenía ENTONCES, no el de hoy.
- Incluye TODOS los tickers (activos e inactivos, con `is_actively_trading`
  y `delisted_utc`) → el universo histórico contiene a los muertos; sin
  survivorship bias estructural.

El snapshot se etiqueta con la fecha ET en que se toma. Un día sin snapshot
(caída del servicio) se cubre por el ASOF join con el día anterior.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.append('/app')

import pyarrow as pa
import pyarrow.parquet as pq

from shared.utils.logger import get_logger
from shared.utils.timescale_client import TimescaleClient

logger = get_logger(__name__)

ET = ZoneInfo("America/New_York")
SCHEMA_VERSION = 1

# Columnas relevantes para backtesting (se omiten descripciones, URLs y
# datos de contacto: peso muerto para el motor).
_COLUMNS = [
    "symbol", "company_name", "exchange", "sector", "industry", "type",
    "current_price", "market_cap", "shares_outstanding",
    "free_float", "free_float_percent",
    "avg_volume_30d", "avg_volume_10d", "avg_price_30d", "beta",
    "is_etf", "is_active", "is_actively_trading",
    "list_date", "delisted_utc",
]

_SCHEMA = pa.schema([
    pa.field("symbol", pa.string()),
    pa.field("company_name", pa.string()),
    pa.field("exchange", pa.string()),
    pa.field("sector", pa.string()),
    pa.field("industry", pa.string()),
    pa.field("type", pa.string()),
    pa.field("current_price", pa.float64()),
    pa.field("market_cap", pa.float64()),
    pa.field("shares_outstanding", pa.float64()),
    pa.field("free_float", pa.float64()),
    pa.field("free_float_percent", pa.float64()),
    pa.field("avg_volume_30d", pa.float64()),
    pa.field("avg_volume_10d", pa.float64()),
    pa.field("avg_price_30d", pa.float64()),
    pa.field("beta", pa.float64()),
    pa.field("is_etf", pa.bool_()),
    pa.field("is_active", pa.bool_()),
    pa.field("is_actively_trading", pa.bool_()),
    pa.field("list_date", pa.string()),
    pa.field("delisted_utc", pa.string()),
])


def lake_metadata_dir() -> Path:
    return Path(os.getenv("LAKE_DIR", "/data/lake")) / "reference" / "metadata"


class ArchiveReferenceSnapshotsTask:
    """Snapshot diario de tickers_unified al lake (idempotente por día ET)."""

    name = "archive_reference_snapshots"

    def __init__(self, timescale_client: TimescaleClient):
        self.db = timescale_client

    async def execute(self, force: bool = False) -> dict[str, Any]:
        snapshot_date = datetime.now(ET).date()
        day_dir = lake_metadata_dir() / f"dt={snapshot_date.isoformat()}"
        out_path = day_dir / "metadata.parquet"
        manifest_path = day_dir / "_manifest.json"

        if manifest_path.exists() and not force:
            return {"date": snapshot_date.isoformat(), "status": "skipped"}

        col_list = ", ".join(_COLUMNS)
        rows = await self.db.fetch(f"SELECT {col_list} FROM tickers_unified")
        if not rows:
            return {"date": snapshot_date.isoformat(), "status": "empty"}

        # Fechas → ISO string (parquet estable ante cambios de tipo en origen).
        records = []
        for r in rows:
            rec = dict(r)
            for k in ("list_date", "delisted_utc"):
                if rec.get(k) is not None and not isinstance(rec[k], str):
                    rec[k] = rec[k].isoformat()
            for k in ("current_price", "market_cap", "shares_outstanding",
                      "free_float", "free_float_percent", "avg_volume_30d",
                      "avg_volume_10d", "avg_price_30d", "beta"):
                if rec.get(k) is not None:
                    rec[k] = float(rec[k])
            records.append(rec)

        day_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = day_dir / ".metadata.parquet.tmp"
        table = pa.Table.from_pylist(records, schema=_SCHEMA)
        pq.write_table(table, tmp_path, compression="zstd")
        os.rename(tmp_path, out_path)

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "date": snapshot_date.isoformat(),
            "source": "timescaledb.tickers_unified",
            "columns": _COLUMNS,
            "total_rows": len(records),
            "actively_trading": sum(1 for r in records if r.get("is_actively_trading")),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2))

        logger.info(
            "reference metadata archived date=%s rows=%d (active=%d)",
            snapshot_date.isoformat(), len(records), manifest["actively_trading"],
        )
        return {
            "date": snapshot_date.isoformat(),
            "status": "archived",
            "total_rows": len(records),
        }


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot point-in-time de tickers al Event Lake")
    parser.add_argument("--force", action="store_true", help="Re-escribe el snapshot de hoy")
    args = parser.parse_args()

    db = TimescaleClient()
    await db.connect()
    try:
        result = await ArchiveReferenceSnapshotsTask(db).execute(force=args.force)
    finally:
        await db.disconnect()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] != "error" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
