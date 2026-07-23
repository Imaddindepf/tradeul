"""
Archive Market Events — Event Lake (Backtester v2, Fase 0)
==========================================================
TimescaleDB `market_events` tiene retención de 3 días (policy_retention,
drop_after='3 days'). Este task exporta cada día ET cerrado a Parquet
inmutable ANTES de que la retención lo borre:

    /data/lake/events/dt=YYYY-MM-DD/event_type=<tipo>/part-000.parquet
    /data/lake/events/dt=YYYY-MM-DD/_manifest.json

Garantías:
- Idempotente: un día con `_manifest.json` no se re-archiva (salvo --force).
- Atómico: todo el día se escribe en un directorio temporal oculto y se
  renombra al final; nunca hay particiones a medias visibles para lectores.
- Verificado: los row counts de cada Parquet se comparan con los del origen
  dentro de la misma pasada; si no cuadran, el día se aborta (sin manifiesto
  → se reintenta en la siguiente pasada).
- Memoria acotada: keyset pagination (ts, id) en lotes de 100K filas aunque
  el día tenga 12M+ eventos.

El particionado dt/event_type está pensado para DuckDB (partition pruning):
los backtests del Event-Outcome Engine filtran casi siempre por tipo y rango
de fechas. Ver docs/backtester-v2-architecture.md §2.1.
"""

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

sys.path.append('/app')

import pyarrow as pa
import pyarrow.parquet as pq

from shared.utils.logger import get_logger
from shared.utils.timescale_client import TimescaleClient

logger = get_logger(__name__)

ET = ZoneInfo("America/New_York")
SCHEMA_VERSION = 2
BATCH_ROWS = 100_000
TABLE = "market_events"

# Columnas EXCLUIDAS del archivo. `context` es un JSON de ~50 campos con el
# estado completo del ticker repetido en cada evento: medido en producción
# (2026-07-22) era el 95% del peso del día (20 de 23 GB) y es redundante —
# price/rvol/float/mcap/vwap/sector ya son columnas planas del evento, y los
# high/low históricos se reconstruyen desde las barras del lake. `details`
# (payload específico del evento, ~16 MB/día) SÍ se conserva.
EXCLUDED_COLUMNS = {"context"}

# Solo caracteres seguros en nombres de partición (los event_type vienen de
# un enum interno, pero el path del filesystem no confía en nadie).
_UNSAFE_PART = re.compile(r"[^A-Za-z0-9_\-]")

# Mapeo tipo Postgres → tipo Arrow. Columnas nuevas en la tabla caen a string
# (nunca rompen el archiver); el manifiesto registra el schema usado.
_PG_TO_ARROW: dict[str, pa.DataType] = {
    "text": pa.string(),
    "character varying": pa.string(),
    "timestamp with time zone": pa.timestamp("us", tz="UTC"),
    "double precision": pa.float64(),
    "bigint": pa.int64(),
    "integer": pa.int64(),
    "boolean": pa.bool_(),
    "jsonb": pa.string(),   # JSON serializado; DuckDB lo parsea on-read si hace falta
    "json": pa.string(),
}


def lake_events_dir() -> Path:
    """Raíz del lake de eventos (env LAKE_DIR para tests/overrides)."""
    return Path(os.getenv("LAKE_DIR", "/data/lake")) / "events"


def sanitize_partition(value: str) -> str:
    """Nombre de partición seguro para filesystem/Hive-style."""
    cleaned = _UNSAFE_PART.sub("_", value.strip())
    return cleaned or "_unknown"


def day_bounds_utc(d: date) -> tuple[datetime, datetime]:
    """[inicio, fin) del día calendario ET en UTC — sargable sobre el índice ts.

    La sesión completa (pre 4:00 → post 20:00 ET) cae dentro del día ET, así
    que el día calendario ET es exactamente "la sesión" a efectos de archivo.
    """
    start = datetime(d.year, d.month, d.day, tzinfo=ET)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


class ArchiveMarketEventsTask:
    """Archiva a Parquet todos los días ET cerrados aún presentes en la BD."""

    name = "archive_market_events"

    def __init__(self, timescale_client: TimescaleClient):
        self.db = timescale_client

    # ── Introspección de schema ───────────────────────────────────────────

    async def _table_schema(self) -> tuple[list[str], pa.Schema]:
        rows = await self.db.fetch(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = $1
            ORDER BY ordinal_position
            """,
            TABLE, timeout=300.0,
        )
        if not rows:
            raise RuntimeError(f"tabla {TABLE} no encontrada")
        rows = [r for r in rows if r["column_name"] not in EXCLUDED_COLUMNS]
        columns = [r["column_name"] for r in rows]
        fields = [
            pa.field(r["column_name"], _PG_TO_ARROW.get(r["data_type"], pa.string()))
            for r in rows
        ]
        return columns, pa.schema(fields)

    # ── Selección de días ─────────────────────────────────────────────────

    async def _closed_days_in_db(self) -> list[date]:
        row = await self.db.fetchrow(
            f"SELECT min(ts) AS lo, max(ts) AS hi FROM {TABLE}", timeout=300.0
        )
        if not row or row["lo"] is None:
            return []
        today_et = datetime.now(ET).date()
        first = row["lo"].astimezone(ET).date()
        last = min(row["hi"].astimezone(ET).date(), today_et - timedelta(days=1))
        days: list[date] = []
        d = first
        while d <= last:
            days.append(d)
            d += timedelta(days=1)
        return days

    # ── Archivo de un día ─────────────────────────────────────────────────

    async def _write_event_type(
        self,
        d: date,
        event_type: str,
        columns: list[str],
        schema: pa.Schema,
        out_path: Path,
    ) -> int:
        """Streaming del tipo completo a un Parquet con paginación keyset."""
        start, end = day_bounds_utc(d)
        col_list = ", ".join(f'"{c}"' for c in columns)
        base = (
            f"SELECT {col_list} FROM {TABLE} "
            f"WHERE ts >= $1 AND ts < $2 AND event_type = $3"
        )
        total = 0
        last_key: Optional[tuple[datetime, str]] = None
        writer = pq.ParquetWriter(out_path, schema, compression="zstd")
        try:
            while True:
                # timeout explícito: el command_timeout=60 del pool se queda
                # corto para ordenar los tipos con millones de filas/día.
                if last_key is None:
                    rows = await self.db.fetch(
                        base + f" ORDER BY ts, id LIMIT {BATCH_ROWS}",
                        start, end, event_type, timeout=300.0,
                    )
                else:
                    rows = await self.db.fetch(
                        base + f" AND (ts, id) > ($4, $5) ORDER BY ts, id LIMIT {BATCH_ROWS}",
                        start, end, event_type, last_key[0], last_key[1], timeout=300.0,
                    )
                if not rows:
                    break
                table = pa.Table.from_pylist([dict(r) for r in rows], schema=schema)
                writer.write_table(table)
                total += len(rows)
                last_key = (rows[-1]["ts"], rows[-1]["id"])
                if len(rows) < BATCH_ROWS:
                    break
        finally:
            writer.close()
        return total

    async def archive_day(self, d: date, force: bool = False) -> dict[str, Any]:
        events_dir = lake_events_dir()
        day_dir = events_dir / f"dt={d.isoformat()}"
        manifest_path = day_dir / "_manifest.json"

        if manifest_path.exists() and not force:
            return {"date": d.isoformat(), "status": "skipped"}

        start, end = day_bounds_utc(d)
        counts = {
            r["event_type"]: r["n"]
            for r in await self.db.fetch(
                f"SELECT event_type, count(*) AS n FROM {TABLE} "
                f"WHERE ts >= $1 AND ts < $2 GROUP BY event_type",
                start, end, timeout=300.0,
            )
        }
        if not counts:
            # Día ya purgado por retención o sin trading — nada que archivar.
            return {"date": d.isoformat(), "status": "empty"}

        columns, schema = await self._table_schema()

        tmp_dir = events_dir / f".tmp-dt={d.isoformat()}"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True)

        try:
            written: dict[str, int] = {}
            for event_type in sorted(counts):
                part_dir = tmp_dir / f"event_type={sanitize_partition(event_type)}"
                part_dir.mkdir(parents=True, exist_ok=True)
                n = await self._write_event_type(
                    d, event_type, columns, schema, part_dir / "part-000.parquet"
                )
                written[event_type] = n

            # Verificación fuente↔parquet. La retención borra chunks enteros de
            # 1 día: si cae a mitad de pasada sobre el día más viejo, esto lo
            # detecta y aborta (sin manifiesto → retry en la siguiente pasada).
            mismatches = {
                et: (counts[et], written.get(et, 0))
                for et in counts
                if counts[et] != written.get(et, 0)
            }
            if mismatches:
                raise RuntimeError(
                    f"conteo fuente≠parquet para {d}: "
                    + ", ".join(f"{et} {src}≠{dst}" for et, (src, dst) in mismatches.items())
                )

            manifest = {
                "schema_version": SCHEMA_VERSION,
                "date": d.isoformat(),
                "source": "timescaledb.market_events",
                "columns": columns,
                "event_type_counts": written,
                "total_rows": sum(written.values()),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            (tmp_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2))

            # Publicación atómica: el directorio final aparece completo o no aparece.
            if day_dir.exists():
                shutil.rmtree(day_dir)
            os.rename(tmp_dir, day_dir)
        except BaseException:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise

        logger.info(
            "market_events archived date=%s rows=%d types=%d dir=%s",
            d.isoformat(), sum(written.values()), len(written), day_dir,
        )
        return {
            "date": d.isoformat(),
            "status": "archived",
            "total_rows": sum(written.values()),
            "event_types": len(written),
        }

    # ── Entrada principal ─────────────────────────────────────────────────

    async def execute(
        self, target_date: Optional[date] = None, force: bool = False
    ) -> list[dict[str, Any]]:
        """Archiva `target_date`, o TODOS los días cerrados aún en BD (catch-up).

        Con retención de 3 días, el modo catch-up hace que una pasada horaria
        se recupere sola de cualquier fallo previo sin perder días.
        """
        days = [target_date] if target_date else await self._closed_days_in_db()
        results: list[dict[str, Any]] = []
        for d in days:
            try:
                results.append(await self.archive_day(d, force=force))
            except Exception as exc:  # noqa: BLE001 — un día malo no bloquea el resto
                # repr(): TimeoutError y similares tienen str() vacío.
                logger.error("archive_market_events failed date=%s: %r", d, exc)
                results.append({"date": d.isoformat(), "status": "error", "error": repr(exc)})
        return results


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Archiva market_events al Event Lake")
    parser.add_argument("--date", type=date.fromisoformat, default=None,
                        help="Día ET concreto (YYYY-MM-DD); por defecto, catch-up de todos los cerrados")
    parser.add_argument("--force", action="store_true", help="Re-archiva aunque exista manifiesto")
    args = parser.parse_args()

    db = TimescaleClient()
    await db.connect()
    try:
        task = ArchiveMarketEventsTask(db)
        results = await task.execute(target_date=args.date, force=args.force)
    finally:
        await db.disconnect()

    print(json.dumps(results, indent=2))
    return 0 if all(r["status"] != "error" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
