#!/usr/bin/env python3
"""
Build Adjusted Market Data Pipeline
====================================

Processes raw Polygon FLATS data into a professional backtesting dataset.

Phase 1: Fetch ALL stock splits from Polygon REST API -> splits/
Phase 2: Split-adjust ALL minute_aggs -> minute_aggs_adjusted/
Phase 3: Compute RVOL by 5-min slot -> rvol_slots/

Usage (inside backtester container):
    python scripts/build_adjusted_data.py --phase all
    python scripts/build_adjusted_data.py --phase splits
    python scripts/build_adjusted_data.py --phase adjust
    python scripts/build_adjusted_data.py --phase rvol

Resumable: skips days whose output files already exist.
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import httpx
import pandas as pd

# ── Configuration ────────────────────────────────────────────────────────

POLYGON_API_KEY = os.getenv("BACKTESTER_POLYGON_API_KEY", "")
RAW_DATA_DIR = Path(os.getenv("BACKTESTER_POLYGON_DATA_DIR", "/data/polygon"))
OUT_DATA_DIR = Path(os.getenv("BACKTESTER_DATA_DIR", "/data/backtester"))

MINUTE_RAW_DIR = RAW_DATA_DIR / "minute_aggs"
MINUTE_ADJ_DIR = OUT_DATA_DIR / "minute_aggs_adjusted"
SPLITS_DIR = OUT_DATA_DIR / "splits"
SLOT_ACC_DIR = OUT_DATA_DIR / "slot_accumulations"
RVOL_DIR = OUT_DATA_DIR / "rvol_slots"

SPLITS_FILE = SPLITS_DIR / "all_splits.parquet"
FACTORS_FILE = SPLITS_DIR / "adjustment_factors.parquet"

RVOL_LOOKBACK_DAYS = 5
SLOT_SIZE_MINUTES = 5
ET_DAY_START_MINUTES = 240
ET_DAY_END_MINUTES = 1200
TOTAL_SLOTS = 192

PARQUET_COMPRESSION = "zstd"
POLYGON_SPLITS_URL = "https://api.polygon.io/v3/reference/splits"
BATCH_SIZE = 3

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


def log(msg: str, **kwargs: Any) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
    print(f"[{ts}] {msg} {extra}".rstrip(), flush=True)


# =========================================================================
# PHASE 1: FETCH ALL SPLITS
# =========================================================================

async def fetch_all_splits() -> pd.DataFrame:
    """Fetch every US equity split since 2019-01-01 from Polygon (paginated)."""
    log("PHASE 1: Fetching ALL splits from Polygon API...")
    SPLITS_DIR.mkdir(parents=True, exist_ok=True)

    all_results: list[dict] = []
    params: dict[str, Any] = {
        "limit": 1000,
        "order": "asc",
        "sort": "execution_date",
        "apiKey": POLYGON_API_KEY,
        "execution_date.gte": "2019-01-01",
    }

    page = 0
    async with httpx.AsyncClient(timeout=60.0) as client:
        url: str | None = POLYGON_SPLITS_URL
        is_first = True
        while url:
            if is_first:
                resp = await client.get(url, params=params)
                is_first = False
            else:
                sep = "&" if "?" in url else "?"
                resp = await client.get(f"{url}{sep}apiKey={POLYGON_API_KEY}")
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("results", [])
            all_results.extend(batch)
            page += 1
            log(f"  Page {page}: +{len(batch)} splits (total: {len(all_results)})")
            url = data.get("next_url")
            await asyncio.sleep(0.12)

    log(f"  Total raw splits fetched: {len(all_results)}")

    records = []
    skipped = 0
    for s in all_results:
        try:
            sf = float(s["split_from"])
            st = float(s["split_to"])
            if sf == st:
                skipped += 1
                continue
            records.append({
                "ticker": s["ticker"],
                "execution_date": pd.Timestamp(s["execution_date"]).date(),
                "split_from": sf,
                "split_to": st,
            })
        except (KeyError, ValueError, TypeError):
            skipped += 1

    splits_df = pd.DataFrame(records)
    splits_df = splits_df.sort_values(["ticker", "execution_date"]).reset_index(drop=True)

    log(f"  Parsed splits: {len(splits_df)} (skipped {skipped} no-op/invalid)")
    log(f"  Unique tickers with splits: {splits_df['ticker'].nunique()}")

    for _, row in splits_df[splits_df["ticker"].isin(["AAPL", "TSLA", "NVDA", "AMZN", "GOOGL"])].iterrows():
        log(f"    {row['ticker']}: {row['split_from']}:{row['split_to']} on {row['execution_date']}")

    splits_df.to_parquet(SPLITS_FILE, index=False, compression=PARQUET_COMPRESSION)
    log(f"  Saved: {SPLITS_FILE}")

    factors_df = _compute_adjustment_factors(splits_df)
    factors_df.to_parquet(FACTORS_FILE, index=False, compression=PARQUET_COMPRESSION)
    log(f"  Factors computed: {len(factors_df)} entries for {factors_df['ticker'].nunique()} tickers")
    log(f"  Saved: {FACTORS_FILE}")

    _verify_factors(factors_df)
    return factors_df


def _compute_adjustment_factors(splits_df: pd.DataFrame) -> pd.DataFrame:
    if splits_df.empty:
        return pd.DataFrame(
            columns=["ticker", "effective_before_date", "price_factor", "volume_factor"]
        )
    results = []
    for ticker, group in splits_df.groupby("ticker"):
        rows = group.sort_values("execution_date", ascending=False)
        cum = 1.0
        for _, row in rows.iterrows():
            cum *= row["split_from"] / row["split_to"]
            results.append({
                "ticker": ticker,
                "effective_before_date": row["execution_date"],
                "price_factor": cum,
                "volume_factor": 1.0 / cum,
            })
    df = pd.DataFrame(results)
    df = df.sort_values(["ticker", "effective_before_date"]).reset_index(drop=True)
    return df


def _verify_factors(factors_df: pd.DataFrame) -> None:
    checks = {
        "NVDA": ("2024-06-10", 0.1, "10:1"),
        "TSLA": ("2022-08-25", 1 / 3, "3:1"),
        "GOOGL": ("2022-07-18", 0.05, "20:1"),
        "AMZN": ("2022-06-06", 0.05, "20:1"),
    }
    for ticker, (exec_date, expected_pf, desc) in checks.items():
        m = factors_df[
            (factors_df["ticker"] == ticker)
            & (factors_df["effective_before_date"] == date.fromisoformat(exec_date))
        ]
        if m.empty:
            log(f"  VERIFY: {ticker} {desc} - NOT FOUND")
            continue
        actual = m.iloc[0]["price_factor"]
        ok = "OK" if abs(actual - expected_pf) < 0.01 else "MISMATCH"
        log(f"  VERIFY: {ticker} {desc} pf={actual:.4f} (exp {expected_pf:.4f}) [{ok}]")


# =========================================================================
# PHASE 2: SPLIT-ADJUST ALL MINUTE_AGGS  (batch mode)
# =========================================================================

def _get_raw_day_files() -> list[tuple[date, Path]]:
    files = []
    if not MINUTE_RAW_DIR.exists():
        return files
    for f in MINUTE_RAW_DIR.iterdir():
        stem = f.stem.replace(".csv", "")
        try:
            d = date.fromisoformat(stem)
        except ValueError:
            continue
        if f.suffix in (".parquet", ".gz"):
            files.append((d, f))
    files.sort(key=lambda x: x[0])
    return files


def run_phase2(factors_df: pd.DataFrame) -> None:
    """Process all raw minute_aggs with split adjustment (batch reads)."""
    log(f"PHASE 2: Split-adjusting ALL minute_aggs (batch={BATCH_SIZE})...")
    MINUTE_ADJ_DIR.mkdir(parents=True, exist_ok=True)

    raw_files = _get_raw_day_files()
    total = len(raw_files)
    log(f"  Found {total} raw day files")

    if total == 0:
        log("  ERROR: No raw files found!")
        return

    work: list[tuple[date, Path]] = []
    skipped = 0
    for day, raw_path in raw_files:
        if (MINUTE_ADJ_DIR / f"{day.isoformat()}.parquet").exists():
            skipped += 1
        else:
            work.append((day, raw_path))

    to_process = len(work)
    log(f"  To process: {to_process} (skipping {skipped} already done)")
    if to_process == 0:
        _verify_adjustment()
        return

    con = duckdb.connect(":memory:")
    con.execute("SET threads = 8")
    con.execute("SET memory_limit = '3GB'")

    has_factors = not factors_df.empty
    if has_factors:
        fdf = factors_df.copy()
        fdf["effective_before_date"] = pd.to_datetime(fdf["effective_before_date"]).dt.date
        con.register("adj_factors", fdf)
        log(f"  Factors registered: {len(fdf)} rows")

    processed = 0
    errors = 0
    error_days: list[str] = []
    t0 = time.time()

    # Split work into CSV batches and individual parquet files
    csv_batch: list[tuple[date, Path]] = []
    pq_items: list[tuple[date, Path]] = []
    for day, path in work:
        if path.suffix == ".gz":
            csv_batch.append((day, path))
        else:
            pq_items.append((day, path))

    # Process CSV.GZ in batches
    for batch_start in range(0, len(csv_batch), BATCH_SIZE):
        batch = csv_batch[batch_start:batch_start + BATCH_SIZE]
        file_list = ", ".join(f"'{p}'" for _, p in batch)

        try:
            con.execute(f"""
                CREATE OR REPLACE TABLE batch_raw AS
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
                    [{file_list}],
                    header=true, delim=',', {CSV_COLS_CLAUSE}
                )
            """)

            if has_factors:
                con.execute("""
                    CREATE OR REPLACE TABLE batch_adj AS
                    SELECT
                        b.ticker,
                        b.open  * COALESCE(a.price_factor, 1.0) AS open,
                        b.high  * COALESCE(a.price_factor, 1.0) AS high,
                        b.low   * COALESCE(a.price_factor, 1.0) AS low,
                        b.close * COALESCE(a.price_factor, 1.0) AS close,
                        CAST(b.volume * COALESCE(a.volume_factor, 1.0) AS BIGINT) AS volume,
                        b.window_start, b.transactions, b._date
                    FROM batch_raw b
                    ASOF LEFT JOIN adj_factors a
                        ON b.ticker = a.ticker
                        AND b._date < a.effective_before_date
                """)
            else:
                con.execute("CREATE OR REPLACE TABLE batch_adj AS SELECT * FROM batch_raw")

            dates = [r[0] for r in con.execute(
                "SELECT DISTINCT _date FROM batch_adj ORDER BY _date"
            ).fetchall()]

            batch_ok = 0
            for d in dates:
                d_str = d.isoformat() if hasattr(d, "isoformat") else str(d)
                out = MINUTE_ADJ_DIR / f"{d_str}.parquet"
                if out.exists():
                    continue
                try:
                    con.execute(f"""
                        COPY (
                            SELECT ticker, open, high, low, close, volume, window_start, transactions
                            FROM batch_adj WHERE _date = '{d_str}'
                            ORDER BY ticker, window_start
                        ) TO '{out}' (FORMAT PARQUET, COMPRESSION '{PARQUET_COMPRESSION}')
                    """)
                    batch_ok += 1
                except Exception as e:
                    errors += 1
                    error_days.append(f"{d_str}: {e}")

            processed += batch_ok
            con.execute("DROP TABLE IF EXISTS batch_raw")
            con.execute("DROP TABLE IF EXISTS batch_adj")

        except Exception as e:
            errors += len(batch)
            error_days.append(f"batch {batch_start}: {e}")
            log(f"  BATCH ERROR at {batch_start}: {e}")

        done = processed + errors
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        remaining = to_process - done
        eta = remaining / rate / 60 if rate > 0 else 0
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(csv_batch) + BATCH_SIZE - 1) // BATCH_SIZE
        log(
            f"  Batch {batch_num}/{total_batches}: done={processed} err={errors}"
            f" | {rate:.1f} files/s, ETA ~{eta:.0f} min"
        )

        if batch_num % 5 == 0:
            gc.collect()

    # Process parquet files individually (fast, ~23 files)
    for day, pq_path in pq_items:
        out = MINUTE_ADJ_DIR / f"{day.isoformat()}.parquet"
        if out.exists():
            continue
        try:
            if has_factors:
                con.execute(f"""
                    COPY (
                        WITH raw AS (
                            SELECT *,
                                CAST(make_timestamp(CAST(window_start / 1000 AS BIGINT)) AS DATE) AS _date
                            FROM read_parquet('{pq_path}')
                        )
                        SELECT
                            b.ticker,
                            b.open  * COALESCE(a.price_factor, 1.0) AS open,
                            b.high  * COALESCE(a.price_factor, 1.0) AS high,
                            b.low   * COALESCE(a.price_factor, 1.0) AS low,
                            b.close * COALESCE(a.price_factor, 1.0) AS close,
                            CAST(b.volume * COALESCE(a.volume_factor, 1.0) AS BIGINT) AS volume,
                            b.window_start, b.transactions
                        FROM raw b
                        ASOF LEFT JOIN adj_factors a
                            ON b.ticker = a.ticker AND b._date < a.effective_before_date
                        ORDER BY b.ticker, b.window_start
                    ) TO '{out}' (FORMAT PARQUET, COMPRESSION '{PARQUET_COMPRESSION}')
                """)
            else:
                con.execute(f"""
                    COPY (SELECT * FROM read_parquet('{pq_path}') ORDER BY ticker, window_start)
                    TO '{out}' (FORMAT PARQUET, COMPRESSION '{PARQUET_COMPRESSION}')
                """)
            processed += 1
        except Exception as e:
            errors += 1
            error_days.append(f"{day} (pq): {e}")

    con.close()

    elapsed = time.time() - t0
    log(
        f"  Phase 2 COMPLETE: {processed} processed, {skipped} skipped, {errors} errors"
        f" | {elapsed / 60:.1f} min"
    )
    if error_days:
        log(f"  Failed days ({len(error_days)}):")
        for ed in error_days[:20]:
            log(f"    {ed}")

    _verify_adjustment()


def _verify_adjustment() -> None:
    checks = [
        ("NVDA", "2024-06-07", "2024-06-10", 0.1),
        ("TSLA", "2022-08-24", "2022-08-25", 1 / 3),
    ]
    for ticker, pre_date, split_date, expected_pf in checks:
        pre_path = MINUTE_ADJ_DIR / f"{pre_date}.parquet"
        post_path = MINUTE_ADJ_DIR / f"{split_date}.parquet"
        if not pre_path.exists() or not post_path.exists():
            continue
        try:
            con = duckdb.connect(":memory:")
            pre_close = con.execute(f"""
                SELECT AVG(close) FROM read_parquet('{pre_path}') WHERE ticker = '{ticker}'
            """).fetchone()[0]
            post_close = con.execute(f"""
                SELECT AVG(close) FROM read_parquet('{post_path}') WHERE ticker = '{ticker}'
            """).fetchone()[0]
            con.close()
            if pre_close and post_close:
                ratio = pre_close / post_close
                ok = "OK" if 0.5 < ratio < 2.0 else "SUSPICIOUS"
                log(f"  VERIFY ADJ: {ticker} pre={pre_close:.2f} post={post_close:.2f} ratio={ratio:.3f} [{ok}]")
        except Exception as e:
            log(f"  VERIFY ADJ: {ticker} error: {e}")


# =========================================================================
# PHASE 3: COMPUTE RVOL BY SLOT
# =========================================================================

def _get_adjusted_day_files() -> list[tuple[date, Path]]:
    files = []
    if not MINUTE_ADJ_DIR.exists():
        return files
    for f in MINUTE_ADJ_DIR.iterdir():
        if f.suffix != ".parquet":
            continue
        try:
            d = date.fromisoformat(f.stem)
        except ValueError:
            continue
        files.append((d, f))
    files.sort(key=lambda x: x[0])
    return files


def _compute_slot_accumulations(day: date, adj_path: Path, output_path: Path) -> int:
    con = duckdb.connect(":memory:")
    con.execute("SET threads = 4")
    con.execute("SET memory_limit = '1GB'")
    day_iso = day.isoformat()

    con.execute(f"""
        CREATE TABLE slot_data AS
        WITH bars_et AS (
            SELECT
                ticker, volume,
                EXTRACT(HOUR FROM timezone('America/New_York',
                    make_timestamp(CAST(window_start / 1000 AS BIGINT))
                ))::INT * 60 +
                EXTRACT(MINUTE FROM timezone('America/New_York',
                    make_timestamp(CAST(window_start / 1000 AS BIGINT))
                ))::INT AS minutes_et
            FROM read_parquet('{adj_path}')
        ),
        bars_slotted AS (
            SELECT ticker,
                (minutes_et - {ET_DAY_START_MINUTES}) / {SLOT_SIZE_MINUTES} AS slot,
                volume
            FROM bars_et
            WHERE minutes_et >= {ET_DAY_START_MINUTES} AND minutes_et < {ET_DAY_END_MINUTES}
        ),
        slot_volumes AS (
            SELECT ticker, CAST(slot AS SMALLINT) AS slot, SUM(volume) AS slot_volume
            FROM bars_slotted
            WHERE slot >= 0 AND slot < {TOTAL_SLOTS}
            GROUP BY ticker, slot
        )
        SELECT
            ticker,
            CAST('{day_iso}' AS DATE) AS trade_date,
            slot, slot_volume,
            SUM(slot_volume) OVER (
                PARTITION BY ticker ORDER BY slot
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS accumulated_volume
        FROM slot_volumes
        ORDER BY ticker, slot
    """)

    row_count = con.execute("SELECT COUNT(*) FROM slot_data").fetchone()[0]
    if row_count > 0:
        con.execute(f"""
            COPY slot_data TO '{output_path}'
            (FORMAT PARQUET, COMPRESSION '{PARQUET_COMPRESSION}')
        """)
    con.close()
    return row_count


def _compute_rvol_for_day(
    target_day: date,
    target_acc_path: Path,
    lookback_paths: list[Path],
    output_path: Path,
) -> int:
    con = duckdb.connect(":memory:")
    con.execute("SET threads = 4")
    con.execute("SET memory_limit = '1GB'")

    lb_files = ", ".join(f"'{p}'" for p in lookback_paths)

    con.execute(f"""
        CREATE TABLE avg_acc AS
        SELECT ticker, slot,
            AVG(accumulated_volume) AS avg_accumulated_5d,
            COUNT(DISTINCT trade_date) AS days_in_avg
        FROM read_parquet([{lb_files}])
        GROUP BY ticker, slot
    """)

    con.execute(f"""
        CREATE TABLE rvol_result AS
        SELECT
            t.ticker, t.trade_date, t.slot, t.slot_volume, t.accumulated_volume,
            a.avg_accumulated_5d,
            CAST(a.days_in_avg AS SMALLINT) AS days_in_avg,
            CASE WHEN a.avg_accumulated_5d > 0
                THEN ROUND(CAST(t.accumulated_volume AS DOUBLE) / a.avg_accumulated_5d, 4)
                ELSE NULL
            END AS rvol_slot
        FROM read_parquet('{target_acc_path}') t
        LEFT JOIN avg_acc a ON t.ticker = a.ticker AND t.slot = a.slot
        ORDER BY t.ticker, t.slot
    """)

    row_count = con.execute("SELECT COUNT(*) FROM rvol_result").fetchone()[0]
    if row_count > 0:
        con.execute(f"""
            COPY rvol_result TO '{output_path}'
            (FORMAT PARQUET, COMPRESSION '{PARQUET_COMPRESSION}')
        """)
    con.close()
    return row_count


def run_phase3() -> None:
    log("PHASE 3: Computing RVOL by slot...")
    SLOT_ACC_DIR.mkdir(parents=True, exist_ok=True)
    RVOL_DIR.mkdir(parents=True, exist_ok=True)

    adj_files = _get_adjusted_day_files()
    total = len(adj_files)
    log(f"  Found {total} adjusted day files")
    if total == 0:
        log("  ERROR: No adjusted files. Run --phase adjust first.")
        return

    # Phase 3a: Slot accumulations
    log("  --- Phase 3a: Computing slot accumulations ---")
    t0 = time.time()
    proc_3a = skip_3a = err_3a = 0

    for i, (day, adj_path) in enumerate(adj_files):
        acc_path = SLOT_ACC_DIR / f"{day.isoformat()}.parquet"
        if acc_path.exists():
            skip_3a += 1
            continue
        try:
            rows = _compute_slot_accumulations(day, adj_path, acc_path)
            proc_3a += 1
            if proc_3a % 50 == 0 or proc_3a == 1:
                elapsed = time.time() - t0
                rate = proc_3a / elapsed if elapsed > 0 else 0
                rem = total - skip_3a - proc_3a - err_3a
                eta = rem / rate / 60 if rate > 0 else 0
                log(f"  3a [{skip_3a + proc_3a + err_3a}/{total}] {day}: {rows:,} rows"
                    f" | {rate:.1f}/s, ETA ~{eta:.0f} min")
            if proc_3a % 100 == 0:
                gc.collect()
        except Exception as e:
            err_3a += 1
            log(f"  3a ERROR {day}: {e}")

    log(f"  Phase 3a DONE: {proc_3a} proc, {skip_3a} skip, {err_3a} err | {(time.time()-t0)/60:.1f} min")

    # Phase 3b: RVOL with lookback
    log("  --- Phase 3b: Computing RVOL ---")
    t0 = time.time()
    acc_files: dict[date, Path] = {}
    for f in SLOT_ACC_DIR.iterdir():
        if f.suffix != ".parquet":
            continue
        try:
            acc_files[date.fromisoformat(f.stem)] = f
        except ValueError:
            continue

    sorted_dates = sorted(acc_files.keys())
    total_d = len(sorted_dates)
    log(f"  Accumulation files: {total_d}")

    proc_3b = skip_3b = err_3b = 0
    for i, day in enumerate(sorted_dates):
        rvol_path = RVOL_DIR / f"{day.isoformat()}.parquet"
        if rvol_path.exists():
            skip_3b += 1
            continue
        lb = sorted_dates[max(0, i - RVOL_LOOKBACK_DAYS):i]
        if len(lb) < 2:
            continue
        try:
            rows = _compute_rvol_for_day(day, acc_files[day], [acc_files[d] for d in lb], rvol_path)
            proc_3b += 1
            if proc_3b % 50 == 0 or proc_3b == 1:
                elapsed = time.time() - t0
                rate = proc_3b / elapsed if elapsed > 0 else 0
                eta = (total_d - i) / rate / 60 if rate > 0 else 0
                log(f"  3b [{i+1}/{total_d}] {day}: {rows:,} rows | {rate:.1f}/s, ETA ~{eta:.0f} min")
            if proc_3b % 100 == 0:
                gc.collect()
        except Exception as e:
            err_3b += 1
            log(f"  3b ERROR {day}: {e}")

    log(f"  Phase 3b DONE: {proc_3b} proc, {skip_3b} skip, {err_3b} err | {(time.time()-t0)/60:.1f} min")
    _verify_rvol()


def _verify_rvol() -> None:
    rvol_files = sorted(RVOL_DIR.glob("*.parquet"))
    if not rvol_files:
        log("  VERIFY RVOL: No files")
        return
    sample = rvol_files[-1]
    try:
        con = duckdb.connect(":memory:")
        stats = con.execute(f"""
            SELECT COUNT(*) AS rows, COUNT(DISTINCT ticker) AS tickers,
                COUNT(DISTINCT slot) AS slots,
                ROUND(AVG(rvol_slot), 3) AS avg_rvol,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY rvol_slot), 3) AS median_rvol,
                ROUND(MAX(rvol_slot), 1) AS max_rvol,
                COUNT(*) FILTER (WHERE rvol_slot IS NULL) AS null_rvol
            FROM read_parquet('{sample}')
        """).fetchdf()
        con.close()
        log(f"  VERIFY RVOL ({sample.stem}):")
        for col in stats.columns:
            log(f"    {col}: {stats[col].iloc[0]}")
    except Exception as e:
        log(f"  VERIFY RVOL error: {e}")


# =========================================================================
# MAIN
# =========================================================================

async def main() -> None:
    parser = argparse.ArgumentParser(description="Build adjusted market data pipeline")
    parser.add_argument("--phase", choices=["all", "splits", "adjust", "rvol"], default="all")
    args = parser.parse_args()

    if not POLYGON_API_KEY:
        print("ERROR: BACKTESTER_POLYGON_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    log("=" * 70)
    log("BUILD ADJUSTED MARKET DATA PIPELINE")
    log("=" * 70)
    log(f"  Raw (ro):   {RAW_DATA_DIR}")
    log(f"  Output(rw): {OUT_DATA_DIR}")
    log(f"  Phase:      {args.phase}")
    log("=" * 70)

    t_start = time.time()

    if args.phase in ("all", "splits"):
        factors_df = await fetch_all_splits()
    else:
        if FACTORS_FILE.exists():
            factors_df = pd.read_parquet(FACTORS_FILE)
            log(f"Loaded factors: {len(factors_df)} entries, {factors_df['ticker'].nunique()} tickers")
        else:
            log("ERROR: No factors file. Run --phase splits first.")
            sys.exit(1)

    if args.phase in ("all", "adjust"):
        run_phase2(factors_df)

    if args.phase in ("all", "rvol"):
        run_phase3()

    elapsed = time.time() - t_start
    log("=" * 70)
    log(f"PIPELINE COMPLETE in {elapsed / 60:.1f} minutes")
    log("=" * 70)

    for name, path in [("splits", SPLITS_DIR), ("minute_aggs_adjusted", MINUTE_ADJ_DIR),
                        ("slot_accumulations", SLOT_ACC_DIR), ("rvol_slots", RVOL_DIR)]:
        if path.exists():
            sz = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / (1024**3)
            n = sum(1 for f in path.rglob("*") if f.is_file())
            log(f"  {name}: {n} files, {sz:.2f} GB")


if __name__ == "__main__":
    asyncio.run(main())
