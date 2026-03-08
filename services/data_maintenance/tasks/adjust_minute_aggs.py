"""
Adjust Minute Aggs Task
========================

Genera el Parquet ajustado por splits para los minute_aggs del día anterior
y lo escribe en /data/backtester/minute_aggs_adjusted/.

También re-ajusta archivos existentes si hay splits recientes (últimos 30 días)
que afecten a datos históricos ya generados.

FLUJO:
1. Leer adjustment_factors.parquet (generado por build_adjusted_data.py)
2. Buscar archivos raw en /data/polygon/minute_aggs/ que no existan en adjusted/
3. Para cada archivo nuevo, aplicar split adjustment con DuckDB y escribir Parquet
4. Detectar splits recientes y re-ajustar archivos históricos afectados

DEPENDENCIAS:
- Se ejecuta DESPUÉS de reconcile_parquet_splits (que ya actualizó day_aggs)
- Requiere /data/backtester/splits/adjustment_factors.parquet
- Requiere volumen backtester_data montado en /data/backtester

CAMPOS AJUSTADOS:
- open, high, low, close: × price_factor
- volume: × volume_factor (redondeado a int)
- transactions, window_start, ticker: sin cambio
"""

import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

sys.path.append('/app')

import duckdb
import httpx

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger
from shared.config.settings import settings

logger = get_logger(__name__)

RAW_DIR = Path("/data/polygon/minute_aggs")
ADJ_DIR = Path("/data/backtester/minute_aggs_adjusted")
FACTORS_FILE = Path("/data/backtester/splits/adjustment_factors.parquet")

PARQUET_COMPRESSION = "zstd"
SPLIT_LOOKBACK_DAYS = 30

FLATS_CSV_COLUMNS = {
    "ticker": "VARCHAR",
    "volume": "DOUBLE",
    "open": "DOUBLE",
    "close": "DOUBLE",
    "high": "DOUBLE",
    "low": "DOUBLE",
    "window_start": "BIGINT",
    "transactions": "DOUBLE",
}
COL_SPEC_STR = ", ".join(f"'{k}': '{v}'" for k, v in FLATS_CSV_COLUMNS.items())
CSV_COLS_CLAUSE = f"columns={{{COL_SPEC_STR}}}"


class AdjustMinuteAggsTask:
    """
    Tarea nightly para mantener minute_aggs_adjusted/ al día.

    Dos responsabilidades:
    1. Generar archivos ajustados para días nuevos (raw existe, adjusted no)
    2. Re-ajustar archivos históricos si hay splits recientes
    """

    name = "adjust_minute_aggs"

    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client

    async def execute(self, target_date: date) -> Dict:
        logger.info("adjust_minute_aggs_starting", target_date=str(target_date))

        if not RAW_DIR.exists():
            return {"success": False, "error": f"Raw dir not found: {RAW_DIR}"}
        if not FACTORS_FILE.exists():
            return {"success": False, "error": f"Factors file not found: {FACTORS_FILE}"}

        ADJ_DIR.mkdir(parents=True, exist_ok=True)
        t0 = time.time()

        new_processed, new_errors = self._process_new_days()

        split_reprocessed = await self._reprocess_for_recent_splits(target_date)

        elapsed = round(time.time() - t0, 2)

        logger.info(
            "adjust_minute_aggs_completed",
            new_days=new_processed,
            new_errors=new_errors,
            split_reprocessed=split_reprocessed,
            elapsed_s=elapsed,
        )

        return {
            "success": new_errors == 0,
            "new_days_adjusted": new_processed,
            "new_errors": new_errors,
            "split_reprocessed": split_reprocessed,
            "elapsed_seconds": elapsed,
        }

    MAX_NEW_DAYS = 10

    def _process_new_days(self) -> tuple[int, int]:
        """Genera archivos ajustados para días raw que aún no existen en adjusted/."""
        existing = {f.stem for f in ADJ_DIR.glob("*.parquet")}

        work: list[tuple[date, Path]] = []
        for f in RAW_DIR.iterdir():
            stem = f.stem.replace(".csv", "")
            try:
                d = date.fromisoformat(stem)
            except ValueError:
                continue
            if f.suffix in (".parquet", ".gz") and d.isoformat() not in existing:
                work.append((d, f))

        if not work:
            logger.info("adjust_minute_aggs_no_new_days")
            return 0, 0

        work.sort(key=lambda x: x[0])

        if len(work) > self.MAX_NEW_DAYS:
            logger.warning(
                "adjust_minute_aggs_too_many_missing",
                total_missing=len(work),
                processing_last=self.MAX_NEW_DAYS,
            )
            work = work[-self.MAX_NEW_DAYS:]

        logger.info("adjust_minute_aggs_new_days", count=len(work))

        con = duckdb.connect(":memory:")
        con.execute("SET threads = 4")
        con.execute("SET memory_limit = '1GB'")

        row_count = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{FACTORS_FILE}')"
        ).fetchone()[0]
        has_factors = row_count > 0
        if has_factors:
            con.execute(f"""
                CREATE TABLE adj_factors AS
                SELECT * FROM read_parquet('{FACTORS_FILE}')
            """)
        processed = 0
        errors = 0

        for day, raw_path in work:
            out = ADJ_DIR / f"{day.isoformat()}.parquet"
            try:
                if raw_path.suffix == ".gz":
                    self._adjust_csv(con, raw_path, out, has_factors)
                else:
                    self._adjust_parquet(con, raw_path, out, has_factors)
                processed += 1
            except Exception as e:
                errors += 1
                logger.error("adjust_minute_aggs_day_error", day=str(day), error=str(e))

        con.close()
        return processed, errors

    def _adjust_csv(self, con: duckdb.DuckDBPyConnection, raw: Path, out: Path, has_factors: bool) -> None:
        con.execute(f"""
            CREATE OR REPLACE TABLE _raw AS
            SELECT
                ticker,
                CAST(open AS DOUBLE) AS open,
                CAST(high AS DOUBLE) AS high,
                CAST(low AS DOUBLE) AS low,
                CAST(close AS DOUBLE) AS close,
                CAST(volume AS BIGINT) AS volume,
                CAST(window_start AS BIGINT) AS window_start,
                CAST(transactions AS INTEGER) AS transactions,
                CAST(make_timestamp(CAST(window_start / 1000 AS BIGINT)) AS DATE) AS _date
            FROM read_csv(
                '{raw}', header=true, delim=',', {CSV_COLS_CLAUSE}
            )
        """)
        self._write_adjusted(con, out, has_factors)

    def _adjust_parquet(self, con: duckdb.DuckDBPyConnection, raw: Path, out: Path, has_factors: bool) -> None:
        con.execute(f"""
            CREATE OR REPLACE TABLE _raw AS
            SELECT *,
                CAST(make_timestamp(CAST(window_start / 1000 AS BIGINT)) AS DATE) AS _date
            FROM read_parquet('{raw}')
        """)
        self._write_adjusted(con, out, has_factors)

    def _write_adjusted(self, con: duckdb.DuckDBPyConnection, out: Path, has_factors: bool) -> None:
        if has_factors:
            con.execute(f"""
                COPY (
                    SELECT
                        b.ticker,
                        b.open  * COALESCE(a.price_factor, 1.0) AS open,
                        b.high  * COALESCE(a.price_factor, 1.0) AS high,
                        b.low   * COALESCE(a.price_factor, 1.0) AS low,
                        b.close * COALESCE(a.price_factor, 1.0) AS close,
                        CAST(b.volume * COALESCE(a.volume_factor, 1.0) AS BIGINT) AS volume,
                        b.window_start, b.transactions
                    FROM _raw b
                    ASOF LEFT JOIN adj_factors a
                        ON b.ticker = a.ticker AND b._date < a.effective_before_date
                    ORDER BY b.ticker, b.window_start
                ) TO '{out}' (FORMAT PARQUET, COMPRESSION '{PARQUET_COMPRESSION}')
            """)
        else:
            con.execute(f"""
                COPY (
                    SELECT ticker, open, high, low, close, volume, window_start, transactions
                    FROM _raw ORDER BY ticker, window_start
                ) TO '{out}' (FORMAT PARQUET, COMPRESSION '{PARQUET_COMPRESSION}')
            """)
        con.execute("DROP TABLE IF EXISTS _raw")

    async def _reprocess_for_recent_splits(self, target_date: date) -> int:
        """
        Si hay splits recientes, re-genera los archivos adjusted afectados.

        Busca splits de los últimos 30 días. Para cada uno, elimina los archivos
        adjusted anteriores a la fecha de ejecución del split para que se
        re-generen con los factores actualizados.
        """
        splits = await self._fetch_recent_splits(target_date)
        if not splits:
            return 0

        significant = [
            s for s in splits
            if abs(s["split_from"] / s["split_to"] - 1.0) > 0.10
        ]
        if not significant:
            return 0

        cache_key = f"adjust_minute:last_splits_hash:{target_date.isoformat()}"
        splits_sig = "|".join(
            f"{s['ticker']}:{s['execution_date']}" for s in sorted(significant, key=lambda x: x["ticker"])
        )
        cached = await self.redis.get(cache_key)
        if cached == splits_sig:
            logger.info("adjust_minute_aggs_splits_already_processed")
            return 0

        deleted = 0
        for s in significant:
            exec_date = s["execution_date"]
            for f in ADJ_DIR.glob("*.parquet"):
                try:
                    fdate = date.fromisoformat(f.stem)
                except ValueError:
                    continue
                if fdate < date.fromisoformat(exec_date):
                    f.unlink()
                    deleted += 1

        if deleted > 0:
            logger.info("adjust_minute_aggs_reprocessing_splits", files_deleted=deleted)
            new_processed, _ = self._process_new_days()
            deleted = new_processed

        await self.redis.set(cache_key, splits_sig, ttl=86400 * 7)
        return deleted

    async def _fetch_recent_splits(self, target_date: date) -> List[Dict]:
        from_date = target_date - timedelta(days=SPLIT_LOOKBACK_DAYS)
        url: Optional[str] = (
            f"https://api.polygon.io/v3/reference/splits"
            f"?execution_date.gte={from_date}"
            f"&execution_date.lte={target_date}"
            f"&limit=1000"
            f"&apiKey={settings.POLYGON_API_KEY}"
        )

        all_splits: list[dict] = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            while url:
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    all_splits.extend(data.get("results", []))
                    next_url = data.get("next_url")
                    url = f"{next_url}&apiKey={settings.POLYGON_API_KEY}" if next_url else None
                except Exception as e:
                    logger.error("adjust_minute_splits_api_error", error=str(e))
                    break

        return [
            {
                "ticker": s.get("ticker"),
                "execution_date": s.get("execution_date"),
                "split_from": float(s["split_from"]),
                "split_to": float(s["split_to"]),
            }
            for s in all_splits
            if s.get("split_from") is not None and s.get("split_to") is not None
        ]
