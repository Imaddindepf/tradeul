"""
Validate pydantic v2 instrument models against live dilutiontracker data.

Usage:
  python scripts/validate_instrument_models_v2.py --limit 200
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.append(str(SERVICE_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
if "/app" not in sys.path:
    sys.path.append("/app")

from repositories.instrument_context_repository import InstrumentContextRepository
from shared.utils.logger import get_logger
from shared.utils.timescale_client import TimescaleClient

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    ticker: str
    ok: bool
    instruments: int
    error: str | None = None


async def _validate_one(
    ticker: str,
    repo: InstrumentContextRepository,
    include_completed_offerings: bool,
) -> ValidationResult:
    try:
        context = await repo.get_ticker_context(
            ticker=ticker,
            include_completed_offerings=include_completed_offerings,
        )
        if context is None:
            return ValidationResult(ticker=ticker, ok=False, instruments=0, error="ticker_not_found")
        return ValidationResult(
            ticker=ticker,
            ok=True,
            instruments=len(context.instruments),
        )
    except Exception as exc:
        return ValidationResult(ticker=ticker, ok=False, instruments=0, error=str(exc))


async def run_validation(limit: int, concurrency: int, include_completed_offerings: bool) -> int:
    db = TimescaleClient()
    await db.connect(min_size=2, max_size=max(4, concurrency + 1))

    try:
        tickers = await db.fetch(
            """
            SELECT ticker
            FROM tickers
            ORDER BY ticker
            LIMIT $1
            """,
            limit,
        )
        ticker_list = [item["ticker"] for item in tickers]
        repo = InstrumentContextRepository(db)
        sem = asyncio.Semaphore(concurrency)

        async def worker(symbol: str) -> ValidationResult:
            async with sem:
                return await _validate_one(
                    ticker=symbol,
                    repo=repo,
                    include_completed_offerings=include_completed_offerings,
                )

        results = await asyncio.gather(*(worker(symbol) for symbol in ticker_list))
        ok_count = sum(1 for item in results if item.ok)
        failed = [item for item in results if not item.ok]
        total_instruments = sum(item.instruments for item in results if item.ok)

        logger.info(
            "instrument_models_v2_validation_finished",
            tickers_total=len(results),
            ok=ok_count,
            failed=len(failed),
            total_instruments=total_instruments,
        )

        print(f"Tickers evaluados: {len(results)}")
        print(f"Validaciones OK:  {ok_count}")
        print(f"Fallos:          {len(failed)}")
        print(f"Instrumentos OK: {total_instruments}")

        if failed:
            print("\nPrimeros fallos:")
            for item in failed[:25]:
                print(f"- {item.ticker}: {item.error}")
            return 1
        return 0
    finally:
        await db.disconnect()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate instrument context models v2")
    parser.add_argument("--limit", type=int, default=200, help="Number of tickers to validate")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Concurrent ticker validations",
    )
    parser.add_argument(
        "--include-completed-offerings",
        action="store_true",
        help="Also validate completed_offerings mapping for each ticker",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    exit_code = asyncio.run(
        run_validation(
            limit=arguments.limit,
            concurrency=arguments.concurrency,
            include_completed_offerings=arguments.include_completed_offerings,
        )
    )
    raise SystemExit(exit_code)
