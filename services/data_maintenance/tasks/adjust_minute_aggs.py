"""
Adjust Minute Aggs Task
========================

Genera el Parquet ajustado por splits para los minute_aggs del día anterior
y lo escribe en /data/backtester/minute_aggs_adjusted/.

También re-ajusta archivos existentes si hay splits recientes (últimos 30 días)
que afecten a datos históricos ya generados.

FLUJO:
1. Refresh adjustment_factors.parquet desde Polygon API (auto-rebuild)
2. Buscar archivos raw en /data/polygon/minute_aggs/ que no existan en adjusted/
3. Para cada archivo nuevo, aplicar split adjustment con DuckDB y escribir Parquet
4. Detectar splits recientes y re-ajustar archivos históricos afectados

DEPENDENCIAS:
- Se ejecuta DESPUÉS de reconcile_parquet_splits (que ya actualizó day_aggs)
- Genera /data/backtester/splits/adjustment_factors.parquet automáticamente
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
import pyarrow as pa
import pyarrow.parquet as pq

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger
from shared.config.settings import settings

logger = get_logger(__name__)

RAW_DIR = Path("/data/polygon/minute_aggs")
ADJ_DIR = Path("/data/backtester/minute_aggs_adjusted")
SPLITS_DIR = Path("/data/backtester/splits")
FACTORS_FILE = SPLITS_DIR / "adjustment_factors.parquet"
ALL_SPLITS_FILE = SPLITS_DIR / "all_splits.parquet"

PARQUET_COMPRESSION = "zstd"
SPLIT_LOOKBACK_DAYS = 30
FACTORS_REBUILD_INTERVAL_HOURS = 20

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

        ADJ_DIR.mkdir(parents=True, exist_ok=True)
        SPLITS_DIR.mkdir(parents=True, exist_ok=True)
        t0 = time.time()

        factors_rebuilt = await self._ensure_factors_fresh()

        new_processed, new_errors = self._process_new_days()

        split_reprocessed = await self._reprocess_for_recent_splits(target_date)

        elapsed = round(time.time() - t0, 2)

        logger.info(
            "adjust_minute_aggs_completed",
            new_days=new_processed,
            new_errors=new_errors,
            split_reprocessed=split_reprocessed,
            factors_rebuilt=factors_rebuilt,
            elapsed_s=elapsed,
        )

        return {
            "success": new_errors == 0,
            "new_days_adjusted": new_processed,
            "new_errors": new_errors,
            "split_reprocessed": split_reprocessed,
            "factors_rebuilt": factors_rebuilt,
            "elapsed_seconds": elapsed,
        }

    MAX_NEW_DAYS = 30

    async def _ensure_factors_fresh(self) -> bool:
        """
        Rebuild adjustment_factors.parquet if stale (>FACTORS_REBUILD_INTERVAL_HOURS old).

        Fetches ALL splits from Polygon since 2019-01-01, computes cumulative
        adjustment factors, and writes both all_splits.parquet and
        adjustment_factors.parquet. This replaces the manual build_adjusted_data.py
        dependency.
        """
        if FACTORS_FILE.exists():
            age_hours = (time.time() - FACTORS_FILE.stat().st_mtime) / 3600
            if age_hours < FACTORS_REBUILD_INTERVAL_HOURS:
                logger.info(
                    "adjust_minute_factors_fresh",
                    age_hours=round(age_hours, 1),
                )
                return False

        logger.info("adjust_minute_factors_rebuilding")
        t0 = time.time()

        raw_splits = await self._fetch_all_splits()
        if not raw_splits:
            logger.warning("adjust_minute_factors_no_splits_from_api")
            return False

        splits = [
            s for s in raw_splits
            if s["split_from"] != s["split_to"]
        ]
        splits.sort(key=lambda s: (s["ticker"], s["execution_date"]))

        from collections import defaultdict
        by_ticker: dict[str, list] = defaultdict(list)
        for s in splits:
            by_ticker[s["ticker"]].append(s)

        factors_rows: list[dict] = []
        for ticker in sorted(by_ticker):
            ticker_splits = sorted(by_ticker[ticker], key=lambda s: s["execution_date"], reverse=True)
            cumulative = 1.0
            for s in ticker_splits:
                pf = s["split_from"] / s["split_to"]
                cumulative *= pf
                factors_rows.append({
                    "ticker": ticker,
                    "effective_before_date": date.fromisoformat(s["execution_date"]),
                    "price_factor": cumulative,
                    "volume_factor": 1.0 / cumulative,
                })

        factors_rows.sort(key=lambda r: (r["ticker"], r["effective_before_date"]))

        splits_table = pa.table({
            "ticker": [s["ticker"] for s in splits],
            "execution_date": [date.fromisoformat(s["execution_date"]) for s in splits],
            "split_from": [s["split_from"] for s in splits],
            "split_to": [s["split_to"] for s in splits],
        })
        factors_table = pa.table({
            "ticker": [r["ticker"] for r in factors_rows],
            "effective_before_date": [r["effective_before_date"] for r in factors_rows],
            "price_factor": [r["price_factor"] for r in factors_rows],
            "volume_factor": [r["volume_factor"] for r in factors_rows],
        })

        pq.write_table(splits_table, ALL_SPLITS_FILE)
        pq.write_table(factors_table, FACTORS_FILE)

        elapsed = round(time.time() - t0, 1)
        logger.info(
            "adjust_minute_factors_rebuilt",
            splits=len(splits),
            factors=len(factors_rows),
            elapsed_s=elapsed,
        )
        return True

    async def _fetch_all_splits(self) -> List[Dict]:
        """Fetch all splits from Polygon since 2019-01-01 with pagination."""
        all_splits: List[Dict] = []
        url: Optional[str] = (
            f"https://api.polygon.io/v3/reference/splits"
            f"?execution_date.gte=2019-01-01"
            f"&limit=1000"
            f"&order=asc"
            f"&sort=execution_date"
            f"&apiKey={settings.POLYGON_API_KEY}"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            page = 0
            while url:
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        logger.warning("factors_splits_api_error", status=resp.status_code, page=page)
                        break
                    data = resp.json()
                    results = data.get("results", [])
                    all_splits.extend(results)
                    page += 1

                    next_url = data.get("next_url")
                    url = f"{next_url}&apiKey={settings.POLYGON_API_KEY}" if next_url else None
                except Exception as e:
                    logger.error("factors_splits_api_exception", error=str(e), page=page)
                    break

        logger.info("factors_splits_fetched", total=len(all_splits), pages=page)

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

        has_factors = False
        if FACTORS_FILE.exists():
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
