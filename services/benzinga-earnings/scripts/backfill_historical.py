#!/usr/bin/env python3
"""
Historical Earnings Backfill Script

Fetches all historical earnings from Benzinga (via Polygon.io) and upserts
into TimescaleDB. Safe to run multiple times (upsert on symbol+report_date).

Usage:
    python3 scripts/backfill_historical.py                    # Default: 2015 to now
    python3 scripts/backfill_historical.py --from-year 2020   # From 2020
    python3 scripts/backfill_historical.py --dry-run           # Preview only
"""

import asyncio
import argparse
import sys
import os
from datetime import datetime, date, timedelta

# Add parent dir to path so we can import project modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg
from tasks.benzinga_earnings_client import BenzingaEarningsClient
from models.earnings import BenzingaEarning, EarningsFilterParams
from config import settings


UPSERT_QUERY = """
    INSERT INTO earnings_calendar (
        symbol, company_name, report_date, time_slot, fiscal_quarter,
        fiscal_year, eps_estimate, eps_actual, eps_surprise_pct, beat_eps,
        revenue_estimate, revenue_actual, revenue_surprise_pct, beat_revenue,
        status, importance, date_status, eps_method, revenue_method,
        previous_eps, previous_revenue, benzinga_id, notes, source
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
        $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24
    )
    ON CONFLICT (symbol, report_date) DO UPDATE SET
        company_name = COALESCE(EXCLUDED.company_name, earnings_calendar.company_name),
        time_slot = COALESCE(EXCLUDED.time_slot, earnings_calendar.time_slot),
        fiscal_quarter = COALESCE(EXCLUDED.fiscal_quarter, earnings_calendar.fiscal_quarter),
        eps_estimate = COALESCE(EXCLUDED.eps_estimate, earnings_calendar.eps_estimate),
        eps_actual = COALESCE(EXCLUDED.eps_actual, earnings_calendar.eps_actual),
        eps_surprise_pct = COALESCE(EXCLUDED.eps_surprise_pct, earnings_calendar.eps_surprise_pct),
        beat_eps = COALESCE(EXCLUDED.beat_eps, earnings_calendar.beat_eps),
        revenue_estimate = COALESCE(EXCLUDED.revenue_estimate, earnings_calendar.revenue_estimate),
        revenue_actual = COALESCE(EXCLUDED.revenue_actual, earnings_calendar.revenue_actual),
        revenue_surprise_pct = COALESCE(EXCLUDED.revenue_surprise_pct, earnings_calendar.revenue_surprise_pct),
        beat_revenue = COALESCE(EXCLUDED.beat_revenue, earnings_calendar.beat_revenue),
        status = CASE
            WHEN EXCLUDED.eps_actual IS NOT NULL THEN 'reported'
            ELSE earnings_calendar.status
        END,
        importance = COALESCE(EXCLUDED.importance, earnings_calendar.importance),
        date_status = COALESCE(EXCLUDED.date_status, earnings_calendar.date_status),
        eps_method = COALESCE(EXCLUDED.eps_method, earnings_calendar.eps_method),
        revenue_method = COALESCE(EXCLUDED.revenue_method, earnings_calendar.revenue_method),
        previous_eps = COALESCE(EXCLUDED.previous_eps, earnings_calendar.previous_eps),
        previous_revenue = COALESCE(EXCLUDED.previous_revenue, earnings_calendar.previous_revenue),
        benzinga_id = COALESCE(EXCLUDED.benzinga_id, earnings_calendar.benzinga_id),
        notes = COALESCE(EXCLUDED.notes, earnings_calendar.notes),
        source = 'benzinga',
        updated_at = NOW()
"""


def generate_quarters(from_year: int, to_year: int):
    """Generate (start_date, end_date) tuples for each quarter."""
    quarters = []
    for year in range(from_year, to_year + 1):
        for q_start_month in [1, 4, 7, 10]:
            start = date(year, q_start_month, 1)
            if q_start_month == 10:
                end = date(year, 12, 31)
            else:
                end = date(year, q_start_month + 3, 1) - timedelta(days=1)

            # Don't go beyond today
            today = date.today()
            if start > today:
                break
            if end > today:
                end = today

            quarters.append((start.isoformat(), end.isoformat()))
    return quarters


async def upsert_earning(conn, earning: BenzingaEarning):
    """Upsert a single earning to TimescaleDB."""
    db_data = earning.to_db_dict()

    report_date_str = db_data.get("report_date", "")
    if report_date_str and isinstance(report_date_str, str):
        try:
            db_data["report_date"] = datetime.strptime(report_date_str, "%Y-%m-%d").date()
        except Exception:
            return False

    try:
        await conn.execute(
            UPSERT_QUERY,
            db_data["symbol"],
            db_data["company_name"],
            db_data["report_date"],
            db_data["time_slot"],
            db_data["fiscal_quarter"],
            db_data["fiscal_year"],
            db_data["eps_estimate"],
            db_data["eps_actual"],
            db_data["eps_surprise_pct"],
            db_data["beat_eps"],
            db_data["revenue_estimate"],
            db_data["revenue_actual"],
            db_data["revenue_surprise_pct"],
            db_data["beat_revenue"],
            db_data["status"],
            db_data["importance"],
            db_data["date_status"],
            db_data["eps_method"],
            db_data["revenue_method"],
            db_data["previous_eps"],
            db_data["previous_revenue"],
            db_data["benzinga_id"],
            db_data["notes"],
            db_data["source"]
        )
        return True
    except Exception as e:
        print(f"  [ERROR] Upsert failed for {earning.ticker} {earning.date}: {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="Backfill historical earnings from Benzinga")
    parser.add_argument("--from-year", type=int, default=2015, help="Start year (default: 2015)")
    parser.add_argument("--to-year", type=int, default=datetime.now().year, help="End year (default: current)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't write to DB")
    args = parser.parse_args()

    print("=" * 70)
    print("  BENZINGA EARNINGS HISTORICAL BACKFILL")
    print(f"  Range: {args.from_year} -> {args.to_year}")
    print(f"  Dry run: {args.dry_run}")
    print("=" * 70)

    # Generate quarter windows
    quarters = generate_quarters(args.from_year, args.to_year)
    print(f"\n  {len(quarters)} quarters to process\n")

    # Initialize Benzinga client
    client = BenzingaEarningsClient(api_key=settings.polygon_api_key)

    # Connect to TimescaleDB
    db_pool = None
    if not args.dry_run:
        try:
            db_pool = await asyncpg.create_pool(
                host=settings.timescale_host,
                port=settings.timescale_port,
                user=settings.timescale_user,
                password=settings.timescale_password,
                database=settings.timescale_database,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            async with db_pool.acquire() as conn:
                count_before = await conn.fetchval("SELECT COUNT(*) FROM earnings_calendar")
            print(f"  DB connected. Current rows: {count_before:,}\n")
        except Exception as e:
            print(f"  [FATAL] Cannot connect to TimescaleDB: {e}")
            await client.close()
            return

    # Process each quarter
    total_fetched = 0
    total_upserted = 0
    total_errors = 0

    for i, (start_date, end_date) in enumerate(quarters, 1):
        print(f"  [{i:>3}/{len(quarters)}] {start_date} -> {end_date} ", end="", flush=True)

        try:
            params = EarningsFilterParams(
                date_gte=start_date,
                date_lte=end_date,
                limit=50000,
                sort="date.asc"
            )
            earnings = await client.fetch_earnings_paginated(
                params=params,
                max_results=50000
            )

            total_fetched += len(earnings)
            print(f"fetched {len(earnings):>6,} ", end="", flush=True)

            if args.dry_run:
                print("[DRY RUN]")
                continue

            # Batch upsert
            upserted = 0
            errors = 0
            async with db_pool.acquire() as conn:
                for earning in earnings:
                    ok = await upsert_earning(conn, earning)
                    if ok:
                        upserted += 1
                    else:
                        errors += 1

            total_upserted += upserted
            total_errors += errors
            print(f"upserted {upserted:>6,}" + (f" errors {errors}" if errors else ""))

        except Exception as e:
            print(f"[ERROR] {e}")
            total_errors += 1

    # Summary
    print("\n" + "=" * 70)
    print("  BACKFILL COMPLETE")
    print(f"  Total fetched:  {total_fetched:>10,}")
    print(f"  Total upserted: {total_upserted:>10,}")
    print(f"  Total errors:   {total_errors:>10,}")

    if db_pool and not args.dry_run:
        async with db_pool.acquire() as conn:
            count_after = await conn.fetchval("SELECT COUNT(*) FROM earnings_calendar")
            unique_symbols = await conn.fetchval("SELECT COUNT(DISTINCT symbol) FROM earnings_calendar")
        print(f"  DB rows after:  {count_after:>10,} (was {count_before:,})")
        print(f"  Unique symbols: {unique_symbols:>10,}")
        await db_pool.close()

    print("=" * 70)

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
