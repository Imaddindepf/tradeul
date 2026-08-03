"""
Archive Enriched Close — Event Lake (Backtester v2, Fase 0)
===========================================================
Snapshot diario del hash `snapshot:enriched:last_close` completo a Parquet:

    /data/lake/reference/enriched_close/dt=YYYY-MM-DD/enriched_close.parquet

Por qué existe: el matching de estrategias en vivo (websocket_server,
`eventPassesSubscription`) evalúa los filtros primero contra el payload del
evento y de fallback contra la enrichedCache. El lake de eventos archiva las
38 columnas del payload, pero NO el `context` de ~400 campos (95% del peso de
`market_events`). Este snapshot cubre ese hueco por la vía barata: los campos
de variación lenta (SMAs diarias, avg_volume_*, 52w, float, market_cap,
dilution scores, sector…) quedan congelados una vez al día, y con eso el
matching histórico de CUALQUIER filtro del catálogo se reconstruye con
granularidad diaria — el resto de campos rápidos viaja en el propio evento o
se deriva del minuto del día.

Se guarda el snapshot ENTERO (~400 campos × ~12.6K tickers ≈ 15-25 MB/día en
zstd) en vez de una proyección de "campos lentos": el coste extra es trivial
y elimina para siempre el riesgo de "olvidé una columna".

Idempotente por manifiesto y por día de SESIÓN (no de ejecución): la fecha se
deriva del `__meta__.timestamp` del hash (UTC → ET), retrocediendo a viernes
si cae en fin de semana. `last_close` tiene TTL 7d, así que las pasadas
horarias del scheduler tienen días de margen para capturarlo.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
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

SOURCE_KEY = "snapshot:enriched:last_close"


def lake_enriched_dir() -> Path:
    return Path(os.getenv("LAKE_DIR", "/data/lake")) / "reference" / "enriched_close"


def _session_date(meta_ts: str | None) -> Any:
    """Fecha de sesión ET a partir del timestamp (UTC) del __meta__.

    Si el hash no trae meta legible, cae al día ET actual. Fin de semana
    retrocede al viernes (el last_close de un sábado ES el del viernes).
    """
    dt_utc = None
    if meta_ts:
        try:
            dt_utc = datetime.fromisoformat(meta_ts)
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    if dt_utc is None:
        dt_utc = datetime.now(timezone.utc)

    d = dt_utc.astimezone(ET).date()
    while d.weekday() >= 5:  # 5=sábado, 6=domingo
        d -= timedelta(days=1)
    return d


def _infer_columns(records: list[dict]) -> tuple[list[str], dict[str, str]]:
    """Unión de claves con tipo estable: float si TODOS los no-nulos son
    numéricos, bool si todos son bool, string en cualquier otro caso."""
    kinds: dict[str, str] = {}
    for rec in records:
        for k, v in rec.items():
            if v is None:
                kinds.setdefault(k, "empty")
                continue
            if isinstance(v, bool):
                kind = "bool"
            elif isinstance(v, (int, float)):
                kind = "float"
            elif isinstance(v, str):
                try:
                    float(v)
                    kind = "float"
                except ValueError:
                    kind = "string"
            else:
                kind = "string"  # dicts/listas → JSON string
            prev = kinds.get(k)
            if prev in (None, "empty") or prev == kind:
                kinds[k] = kind
            else:
                kinds[k] = "string"
    for k, v in kinds.items():
        if v == "empty":
            kinds[k] = "string"
    return sorted(kinds.keys()), kinds


def _coerce(value: Any, kind: str) -> Any:
    if value is None:
        return None
    if kind == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if kind == "bool":
        return bool(value)
    if isinstance(value, str):
        return value
    return json.dumps(value)


_PA_TYPES = {"float": pa.float64(), "bool": pa.bool_(), "string": pa.string()}


class ArchiveEnrichedCloseTask:
    """Snapshot diario del enriched del cierre al lake (idempotente por sesión ET)."""

    name = "archive_enriched_close"

    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client

    async def execute(self, force: bool = False) -> dict[str, Any]:
        # RedisClient.hgetall deserializa cada field por defecto (orjson):
        # los valores llegan ya como dict, no como string JSON.
        raw = await self.redis.hgetall(SOURCE_KEY)
        if not raw:
            return {"status": "empty", "source": SOURCE_KEY}

        meta_raw = raw.pop("__meta__", None)
        meta: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}
        if isinstance(meta_raw, str):
            try:
                meta = json.loads(meta_raw)
            except (TypeError, ValueError):
                meta = {}

        session_date = _session_date(meta.get("timestamp"))
        day_dir = lake_enriched_dir() / f"dt={session_date.isoformat()}"
        out_path = day_dir / "enriched_close.parquet"
        manifest_path = day_dir / "_manifest.json"

        if manifest_path.exists() and not force:
            return {"date": session_date.isoformat(), "status": "skipped"}

        records: list[dict] = []
        bad = 0
        for symbol, payload in raw.items():
            entry = payload
            if isinstance(entry, str):
                try:
                    entry = json.loads(entry)
                except (TypeError, ValueError):
                    bad += 1
                    continue
            if not isinstance(entry, dict):
                bad += 1
                continue
            entry["symbol"] = symbol
            records.append(entry)

        if not records:
            return {"date": session_date.isoformat(), "status": "empty"}

        columns, kinds = _infer_columns(records)
        # symbol primero, resto alfabético — esquema legible y estable.
        columns.remove("symbol")
        columns = ["symbol"] + columns
        kinds["symbol"] = "string"

        arrays = []
        fields = []
        for col in columns:
            kind = kinds[col]
            arrays.append(pa.array(
                [_coerce(r.get(col), kind) for r in records],
                type=_PA_TYPES[kind],
            ))
            fields.append(pa.field(col, _PA_TYPES[kind]))
        table = pa.Table.from_arrays(arrays, schema=pa.schema(fields))

        day_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = out_path.with_suffix(".parquet.tmp")
        pq.write_table(table, tmp_path, compression="zstd")
        tmp_path.rename(out_path)

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "date": session_date.isoformat(),
            "source": SOURCE_KEY,
            "rows": len(records),
            "columns": len(columns),
            "bad_entries": bad,
            "meta_timestamp": meta.get("timestamp"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2))

        logger.info(
            "archive_enriched_close_done",
            date=session_date.isoformat(),
            rows=len(records),
            columns=len(columns),
            bad_entries=bad,
        )
        return {"date": session_date.isoformat(), "status": "archived", **manifest}
