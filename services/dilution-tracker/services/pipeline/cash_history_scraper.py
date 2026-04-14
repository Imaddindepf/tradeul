"""
Cash History Scraper
====================
Background service that populates the `cash_history` table in the remote
dilutiontracker DB with quarterly Balance Sheet + Cash Flow data from Perplexity.

Methodology (DilutionTracker.com):
  cash = cashAndShortTermInvestments  (primary)
       | cashAndCashEquivalents        (fallback if primary is NULL)

Strategy:
  - At startup applies the DB migration (CREATE TABLE IF NOT EXISTS).
  - Fetches all tickers from the remote dilutiontracker DB.
  - Prioritises tickers never scraped or scraped > STALE_DAYS ago.
  - Upserts quarterly rows into cash_history.
  - Refreshes the Redis cache key `perplexity:cash_summary:{ticker}` (7-day TTL)
    so PerplexityCashService picks up the corrected data immediately.
  - Runs 1 ticker every DELAY_S seconds (default 4s).
    → 3 385 tickers × 4s ≈ 3.7 h for a full pass.
  - After a full pass waits IDLE_S seconds before starting again.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg

from shared.utils.logger import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
DELAY_S          = float(os.getenv("CASH_SCRAPER_DELAY_S",  "4"))     # secs between tickers
STALE_DAYS       = int(os.getenv("CASH_SCRAPER_STALE_DAYS", "7"))     # re-scrape after N days
IDLE_S           = int(os.getenv("CASH_SCRAPER_IDLE_S",     "3600"))  # wait after full pass
REDIS_TTL        = int(os.getenv("CASH_SCRAPER_REDIS_TTL",  str(7 * 24 * 3600)))  # 7 days

# Remote dilutiontracker DB
REMOTE_DB_HOST = os.getenv("DB_HOST",     "127.0.0.1")
REMOTE_DB_PORT = int(os.getenv("DB_PORT", "55433"))
REMOTE_DB_NAME = os.getenv("DB_NAME",     "dilutiontracker")
REMOTE_DB_USER = os.getenv("DB_USER",     "dilution_admin")
REMOTE_DB_PASS = os.getenv("DB_PASSWORD", "")

# Perplexity Finance API
_PX_BASE    = "https://www.perplexity.ai/rest/finance/financials"
_PX_HEADERS = {
    "Accept":           "application/json, text/plain, */*",
    "Accept-Language":  "en-US,en;q=0.9",
    "Origin":           "https://www.perplexity.ai",
    "Sec-Fetch-Dest":   "empty",
    "Sec-Fetch-Mode":   "cors",
    "Sec-Fetch-Site":   "same-origin",
}

_MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS cash_history (
    ticker                          TEXT        NOT NULL,
    period_date                     DATE        NOT NULL,
    period_label                    TEXT,
    calendar_year                   TEXT,
    cash_and_short_term_investments BIGINT,
    cash_and_cash_equivalents       BIGINT,
    operating_cf                    BIGINT,
    scraped_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, period_date)
);
CREATE INDEX IF NOT EXISTS idx_cash_history_ticker     ON cash_history (ticker);
CREATE INDEX IF NOT EXISTS idx_cash_history_scraped_at ON cash_history (scraped_at);
"""

_UPSERT_SQL = """
INSERT INTO cash_history
    (ticker, period_date, period_label, calendar_year,
     cash_and_short_term_investments, cash_and_cash_equivalents,
     operating_cf, scraped_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
ON CONFLICT (ticker, period_date) DO UPDATE SET
    period_label                    = EXCLUDED.period_label,
    calendar_year                   = EXCLUDED.calendar_year,
    cash_and_short_term_investments = EXCLUDED.cash_and_short_term_investments,
    cash_and_cash_equivalents       = EXCLUDED.cash_and_cash_equivalents,
    operating_cf                    = EXCLUDED.operating_cf,
    scraped_at                      = NOW()
"""


# ── Perplexity fetch (sync, using curl_cffi for Chrome impersonation) ─────────

def _fetch_px(ticker: str, category: str) -> Optional[dict]:
    """Fetch from Perplexity with Chrome impersonation and retries."""
    from curl_cffi import requests as cffi_requests

    headers = {
        **_PX_HEADERS,
        "Referer": f"https://www.perplexity.ai/finance/{ticker}/financials",
    }
    url = f"{_PX_BASE}/{ticker}?period=quarter&category={category}"

    for target in ("chrome", "chrome124", "chrome120", "chrome110"):
        try:
            session = cffi_requests.Session(impersonate=target)
            resp = session.get(url, timeout=15, headers=headers)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            continue
    return None


def _extract_section(data: dict, section_type: str) -> list[dict]:
    for section in data.get("quarter", []):
        if section.get("type") == section_type:
            return section.get("data", [])
    return []


def _build_quarters(ticker: str) -> list[dict]:
    """
    Fetch BALANCE_SHEET + CASH_FLOW from Perplexity and return merged quarters.

    Each quarter dict:
        date          str   "2025-09-30"
        period        str   "Q3"
        year          str   "2025"
        cash_st       int|None   cashAndShortTermInvestments
        cash_eq       int|None   cashAndCashEquivalents
        operating_cf  int|None   netCashProvidedByOperatingActivities
    """
    bs_data = _fetch_px(ticker, "BALANCE_SHEET")
    cf_data = _fetch_px(ticker, "CASH_FLOW")

    bs_rows = _extract_section(bs_data, "BALANCE_SHEET") if bs_data else []
    cf_rows = _extract_section(cf_data, "CASH_FLOW") if cf_data else []

    cf_by_date = {r["date"]: r for r in cf_rows if "date" in r}

    quarters = []
    for row in bs_rows:
        d = row.get("date")
        if not d:
            continue

        cash_st = row.get("cashAndShortTermInvestments")
        cash_eq = row.get("cashAndCashEquivalents")

        # Skip rows with no cash data at all
        if cash_st is None and cash_eq is None:
            continue

        cf_row = cf_by_date.get(d, {})
        ocf_raw = cf_row.get("netCashProvidedByOperatingActivities")

        quarters.append({
            "date":        d,
            "period":      row.get("period"),
            "year":        row.get("calendarYear"),
            "cash_st":     int(cash_st) if cash_st is not None else None,
            "cash_eq":     int(cash_eq) if cash_eq is not None else None,
            "operating_cf": int(ocf_raw) if ocf_raw is not None else None,
        })

    quarters.sort(key=lambda q: q["date"], reverse=True)
    return quarters


# ── Redis cache helpers ────────────────────────────────────────────────────────

def _build_redis_payload(ticker: str, quarters: list[dict]) -> dict:
    """
    Build the payload written to Redis so PerplexityCashService
    picks it up automatically.  Uses cashAndShortTermInvestments as `cash`
    (DT methodology), falls back to cashAndCashEquivalents.
    """
    redis_quarters = []
    for q in quarters:
        cash = q["cash_st"] if q["cash_st"] is not None else q["cash_eq"]
        if cash is None:
            continue
        redis_quarters.append({
            "date":                 q["date"],
            "period":               q["period"],
            "year":                 q["year"],
            "cash":                 cash,
            "cash_and_equivalents": q["cash_eq"],
            "operating_cf":         q["operating_cf"],
        })
    return {
        "ticker":  ticker,
        "quarters": redis_quarters,
        "source":  "cash_history_db",
    }


# ── Main service class ─────────────────────────────────────────────────────────

class CashHistoryScraper:
    """
    Background service.  Call start() once; it runs until stop() is called.
    """

    def __init__(self, redis: RedisClient):
        self.redis = redis
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # Stats
        self._pass_number      = 0
        self._scraped_this_pass = 0
        self._errors_this_pass  = 0
        self._total_scraped     = 0
        self._queue_size        = 0
        self._current_ticker: Optional[str] = None
        self._started_at: Optional[datetime] = None
        self._last_scraped_at: Optional[datetime] = None

    # ── Public ────────────────────────────────────────────────────────────────

    def start(self):
        if self._task and not self._task.done():
            logger.info("cash_scraper_already_running")
            return
        self._running = True
        self._started_at = datetime.now(timezone.utc)
        self._task = asyncio.create_task(self._run(), name="cash_history_scraper")
        logger.info("cash_history_scraper_started", delay_s=DELAY_S, stale_days=STALE_DAYS)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("cash_history_scraper_stopped", total_scraped=self._total_scraped)

    def status(self) -> dict:
        eta_s = self._queue_size * DELAY_S
        return {
            "running":            self._running,
            "current_ticker":     self._current_ticker,
            "pass_number":        self._pass_number,
            "scraped_this_pass":  self._scraped_this_pass,
            "errors_this_pass":   self._errors_this_pass,
            "total_scraped":      self._total_scraped,
            "queue_remaining":    self._queue_size,
            "eta_hours":          round(eta_s / 3600, 1),
            "started_at":         self._started_at.isoformat() if self._started_at else None,
            "last_scraped_at":    self._last_scraped_at.isoformat() if self._last_scraped_at else None,
            "delay_s":            DELAY_S,
            "stale_days":         STALE_DAYS,
        }

    # ── Internal loop ─────────────────────────────────────────────────────────

    async def _run(self):
        # Apply migration first
        await self._apply_migration()

        while self._running:
            try:
                tickers = await self._fetch_pending_tickers()
                self._queue_size        = len(tickers)
                self._pass_number      += 1
                self._scraped_this_pass = 0
                self._errors_this_pass  = 0

                if not tickers:
                    logger.info("cash_scraper_no_pending", idle_s=IDLE_S)
                    await asyncio.sleep(IDLE_S)
                    continue

                logger.info(
                    "cash_scraper_pass_starting",
                    pass_num=self._pass_number,
                    tickers=len(tickers),
                    eta_hours=round(len(tickers) * DELAY_S / 3600, 1),
                )

                for ticker in tickers:
                    if not self._running:
                        break
                    self._current_ticker = ticker
                    await self._scrape_one(ticker)
                    self._queue_size = max(0, self._queue_size - 1)
                    await asyncio.sleep(DELAY_S)

                self._current_ticker = None
                logger.info(
                    "cash_scraper_pass_done",
                    pass_num=self._pass_number,
                    scraped=self._scraped_this_pass,
                    errors=self._errors_this_pass,
                )

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("cash_scraper_loop_error", error=str(exc))
                await asyncio.sleep(60)

    async def _apply_migration(self):
        """Create cash_history table if it does not exist."""
        try:
            conn = await asyncpg.connect(
                host=REMOTE_DB_HOST, port=REMOTE_DB_PORT,
                user=REMOTE_DB_USER, password=REMOTE_DB_PASS,
                database=REMOTE_DB_NAME,
            )
            await conn.execute(_MIGRATION_SQL)
            await conn.close()
            logger.info("cash_history_migration_applied")
        except Exception as exc:
            logger.error("cash_history_migration_failed", error=str(exc))

    async def _fetch_pending_tickers(self) -> list[str]:
        """
        Returns tickers ordered by priority:
          1. Never scraped (no row in cash_history)
          2. Scraped > STALE_DAYS ago
        Both groups sorted alphabetically.
        """
        try:
            conn = await asyncpg.connect(
                host=REMOTE_DB_HOST, port=REMOTE_DB_PORT,
                user=REMOTE_DB_USER, password=REMOTE_DB_PASS,
                database=REMOTE_DB_NAME,
            )
            stale_cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)
            rows = await conn.fetch(
                """
                SELECT t.ticker,
                       MAX(ch.scraped_at) AS last_scraped
                FROM tickers t
                LEFT JOIN cash_history ch ON ch.ticker = t.ticker
                GROUP BY t.ticker
                HAVING MAX(ch.scraped_at) IS NULL
                    OR MAX(ch.scraped_at) < $1
                ORDER BY
                    CASE WHEN MAX(ch.scraped_at) IS NULL THEN 0 ELSE 1 END,
                    t.ticker
                """,
                stale_cutoff,
            )
            await conn.close()
            return [r["ticker"] for r in rows if r["ticker"]]
        except Exception as exc:
            logger.error("cash_scraper_fetch_pending_failed", error=str(exc))
            return []

    async def _scrape_one(self, ticker: str):
        """Fetch Perplexity data for one ticker, upsert to DB, refresh Redis."""
        try:
            # Run sync curl_cffi call in thread pool to avoid blocking event loop
            quarters = await asyncio.get_event_loop().run_in_executor(
                None, _build_quarters, ticker
            )

            if not quarters:
                logger.debug("cash_scraper_no_data", ticker=ticker)
                self._errors_this_pass += 1
                return

            # Upsert to remote DB
            await self._upsert_quarters(ticker, quarters)

            # Update Redis cache (7-day TTL) so PerplexityCashService reads fresh data
            payload = _build_redis_payload(ticker, quarters)
            cache_key = f"perplexity:cash_summary:{ticker}"
            await self.redis.set(cache_key, payload, ttl=REDIS_TTL, serialize=True)

            self._scraped_this_pass += 1
            self._total_scraped     += 1
            self._last_scraped_at    = datetime.now(timezone.utc)

            logger.debug(
                "cash_scraper_ticker_done",
                ticker=ticker,
                quarters=len(quarters),
                latest=quarters[0]["date"] if quarters else None,
            )

        except Exception as exc:
            logger.warning("cash_scraper_ticker_error", ticker=ticker, error=str(exc))
            self._errors_this_pass += 1

    async def _upsert_quarters(self, ticker: str, quarters: list[dict]):
        conn = await asyncpg.connect(
            host=REMOTE_DB_HOST, port=REMOTE_DB_PORT,
            user=REMOTE_DB_USER, password=REMOTE_DB_PASS,
            database=REMOTE_DB_NAME,
        )
        try:
            from datetime import date as _date
            async with conn.transaction():
                for q in quarters:
                    try:
                        period_date = _date.fromisoformat(q["date"])
                    except Exception:
                        continue
                    await conn.execute(
                        _UPSERT_SQL,
                        ticker,
                        period_date,
                        q["period"],
                        q["year"],
                        q["cash_st"],
                        q["cash_eq"],
                        q["operating_cf"],
                    )
        finally:
            await conn.close()


# ── Singleton ─────────────────────────────────────────────────────────────────

_scraper_instance: Optional[CashHistoryScraper] = None


def get_cash_history_scraper(redis: RedisClient) -> CashHistoryScraper:
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = CashHistoryScraper(redis)
    return _scraper_instance
