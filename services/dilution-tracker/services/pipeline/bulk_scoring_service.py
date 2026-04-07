"""
Bulk Scoring Service
====================
Background worker that gradually calculates dilution risk scores for ALL tickers
in the dilutiontracker DB and persists them to dilution_scores (local DB) + Redis.

Strategy:
  - Fetches tickers without scores (or stale > 7 days) from the remote DB.
  - Processes them one by one with a configurable delay to avoid Perplexity rate limits.
  - On service restart, continues where it left off (prioritises unscored tickers).
  - Runs 1 ticker every DELAY_BETWEEN_TICKERS seconds (default 6s).
    → 3385 tickers × 6s ≈ 5.6 hours for a full pass.
  - After a full pass it waits IDLE_AFTER_FULL_PASS seconds before starting again.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
import httpx

from shared.utils.logger import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
DELAY_BETWEEN_TICKERS   = float(os.getenv("BULK_SCORE_DELAY_S", "6"))     # secs between calls
CONCURRENCY             = int(os.getenv("BULK_SCORE_CONCURRENCY", "1"))    # parallel workers
STALE_DAYS              = int(os.getenv("BULK_SCORE_STALE_DAYS", "7"))     # re-score after N days
IDLE_AFTER_FULL_PASS    = int(os.getenv("BULK_SCORE_IDLE_S", "3600"))      # 1h idle after a full pass
RISK_RATINGS_URL        = "http://127.0.0.1:{port}/api/sec-dilution/{ticker}/risk-ratings"
SERVICE_PORT            = int(os.getenv("SERVICE_PORT", "8009"))

# Remote dilutiontracker DB (same as sec_dilution_router)
REMOTE_DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
REMOTE_DB_PORT = int(os.getenv("DB_PORT", "55433"))
REMOTE_DB_NAME = os.getenv("DB_NAME", "dilutiontracker")
REMOTE_DB_USER = os.getenv("DB_USER", "dilution_admin")
REMOTE_DB_PASS = os.getenv("DB_PASSWORD", "")

# Local tradeul DB (for dilution_scores table)
LOCAL_DB_HOST = os.getenv("POSTGRES_HOST", "172.18.0.2")
LOCAL_DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
LOCAL_DB_NAME = os.getenv("POSTGRES_DB", "tradeul")
LOCAL_DB_USER = os.getenv("POSTGRES_USER", "tradeul_user")
LOCAL_DB_PASS = os.getenv("POSTGRES_PASSWORD", "")


class BulkScoringService:
    """
    Background service that scores all tickers gradually.
    Start with start(), stop with stop().
    """

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._current_ticker: Optional[str] = None
        self._scored_this_pass = 0
        self._errors_this_pass = 0
        self._total_scored = 0
        self._pass_number = 0
        self._started_at: Optional[datetime] = None
        self._last_scored_at: Optional[datetime] = None
        self._queue_size = 0
        self._priority_queue_size = 0   # tier A (user tables)
        self._priority_done = 0
        self._tier_a = 0
        self._tier_b = 0
        self._tier_c = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        if self._task and not self._task.done():
            logger.info("bulk_scoring_already_running")
            return
        self._running = True
        self._started_at = datetime.now(timezone.utc)
        self._task = asyncio.create_task(self._run(), name="bulk_scoring_service")
        logger.info("bulk_scoring_service_started", delay_s=DELAY_BETWEEN_TICKERS)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("bulk_scoring_service_stopped", total_scored=self._total_scored)

    def status(self) -> dict:
        eta_s = self._queue_size * DELAY_BETWEEN_TICKERS
        tier_a_remaining = max(0, self._tier_a - self._priority_done)
        return {
            "running": self._running,
            "current_ticker": self._current_ticker,
            "pass_number": self._pass_number,
            "scored_this_pass": self._scored_this_pass,
            "errors_this_pass": self._errors_this_pass,
            "total_scored_lifetime": self._total_scored,
            "queue_remaining": self._queue_size,
            "tier_a_user_tables": self._tier_a,
            "tier_a_remaining": tier_a_remaining,
            "tier_a_eta_minutes": round(tier_a_remaining * DELAY_BETWEEN_TICKERS / 60, 1),
            "tier_b_system_cats": self._tier_b,
            "tier_c_rest_db": self._tier_c,
            "eta_total_hours": round(eta_s / 3600, 1),
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "last_scored_at": self._last_scored_at.isoformat() if self._last_scored_at else None,
            "delay_between_tickers_s": DELAY_BETWEEN_TICKERS,
            "stale_threshold_days": STALE_DAYS,
        }

    # ── Internal loop ─────────────────────────────────────────────────────────

    async def _run(self):
        while self._running:
            try:
                tickers = await self._fetch_pending_tickers()
                self._queue_size = len(tickers)
                self._pass_number += 1
                self._scored_this_pass = 0
                self._errors_this_pass = 0
                self._priority_done = 0

                if not tickers:
                    logger.info("bulk_scoring_no_pending_tickers",
                                idle_s=IDLE_AFTER_FULL_PASS)
                    await asyncio.sleep(IDLE_AFTER_FULL_PASS)
                    continue

                logger.info("bulk_scoring_pass_starting",
                            pass_num=self._pass_number,
                            tickers=len(tickers),
                            priority=self._priority_queue_size,
                            eta_hours=round(len(tickers) * DELAY_BETWEEN_TICKERS / 3600, 1))

                for i, ticker in enumerate(tickers):
                    if not self._running:
                        break
                    self._current_ticker = ticker
                    await self._score_one(ticker)
                    self._queue_size = max(0, self._queue_size - 1)
                    if i < self._priority_queue_size:
                        self._priority_done += 1
                    await asyncio.sleep(DELAY_BETWEEN_TICKERS)

                self._current_ticker = None
                logger.info("bulk_scoring_pass_done",
                            pass_num=self._pass_number,
                            scored=self._scored_this_pass,
                            errors=self._errors_this_pass)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("bulk_scoring_loop_error", error=str(exc))
                await asyncio.sleep(60)

    async def _fetch_pending_tickers(self) -> list[str]:
        """
        Fetches tickers from remote DB that need scoring, ordered by priority:
          1. Scanner-active tickers (currently in scanner:category:* Redis keys) that lack a fresh score
          2. Remaining dilution DB tickers without a fresh score
        Fresh = score updated within STALE_DAYS.
        """
        # ── Step 1: all tickers in the remote dilution DB ────────────────────
        try:
            remote_conn = await asyncpg.connect(
                host=REMOTE_DB_HOST, port=REMOTE_DB_PORT,
                user=REMOTE_DB_USER, password=REMOTE_DB_PASS,
                database=REMOTE_DB_NAME,
            )
            remote_rows = await remote_conn.fetch("SELECT ticker FROM tickers ORDER BY ticker")
            await remote_conn.close()
            all_dilution_tickers = {r["ticker"] for r in remote_rows if r["ticker"]}
        except Exception as exc:
            logger.error("bulk_scoring_fetch_remote_failed", error=str(exc))
            return []

        # ── Step 2: tickers with a fresh score (local DB) ───────────────────
        try:
            local_conn = await asyncpg.connect(
                host=LOCAL_DB_HOST, port=LOCAL_DB_PORT,
                user=LOCAL_DB_USER, password=LOCAL_DB_PASS,
                database=LOCAL_DB_NAME,
            )
            stale_cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)
            scored_rows = await local_conn.fetch(
                "SELECT ticker FROM dilution_scores WHERE updated_at >= $1",
                stale_cutoff,
            )
            await local_conn.close()
            fresh_scored = {r["ticker"] for r in scored_rows}
        except Exception as exc:
            logger.warning("bulk_scoring_fetch_local_failed", error=str(exc))
            fresh_scored = set()

        # ── Step 3: scanner tickers split by priority tier ───────────────────
        # Tier A (highest): user-defined tables  → keys containing 'uscan_'
        # Tier B:           system categories    → all other scanner:* keys
        user_tickers:   set[str] = set()
        system_tickers: set[str] = set()
        try:
            import redis as sync_redis
            import json as _json
            r = sync_redis.Redis(
                host=os.getenv("REDIS_HOST", "127.0.0.1"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                password=os.getenv("REDIS_PASSWORD", ""),
                decode_responses=True,
            )
            all_scanner_keys = r.keys("scanner:*")
            for key in all_scanner_keys:
                is_user_table = "uscan_" in key
                try:
                    raw = r.get(key)
                    if not raw:
                        continue
                    items = _json.loads(raw)
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        sym = item.get("symbol")
                        if not sym:
                            continue
                        if is_user_table:
                            user_tickers.add(sym)
                        else:
                            system_tickers.add(sym)
                except Exception:
                    pass
            r.close()
            logger.debug("bulk_scoring_scanner_tickers_collected",
                         total_keys=len(all_scanner_keys),
                         user_tickers=len(user_tickers),
                         system_tickers=len(system_tickers))
        except Exception as exc:
            logger.warning("bulk_scoring_fetch_scanner_tickers_failed", error=str(exc))
        scanner_tickers = user_tickers | system_tickers

        # ── Step 4: Build 3-tier priority queue ──────────────────────────────
        # Tier A: user tables ∩ dilution DB  (highest — user's own scanners)
        tier_a = sorted((all_dilution_tickers & user_tickers) - fresh_scored)
        # Tier B: system categories ∩ dilution DB  (excluding already in tier_a)
        tier_b = sorted((all_dilution_tickers & system_tickers - user_tickers) - fresh_scored)
        # Tier C: rest of dilution DB not in any scanner
        tier_c = sorted((all_dilution_tickers - scanner_tickers) - fresh_scored)

        pending = tier_a + tier_b + tier_c
        self._priority_queue_size = len(tier_a)
        self._tier_a = len(tier_a)
        self._tier_b = len(tier_b)
        self._tier_c = len(tier_c)

        logger.info(
            "bulk_scoring_queue_built",
            dilution_db=len(all_dilution_tickers),
            fresh_scored=len(fresh_scored),
            tier_a_user_tables=len(tier_a),
            tier_b_system_cats=len(tier_b),
            tier_c_rest=len(tier_c),
            total_pending=len(pending),
        )
        return pending

    async def _score_one(self, ticker: str):
        """Calls the risk-ratings endpoint internally to score a single ticker."""
        url = RISK_RATINGS_URL.format(port=SERVICE_PORT, ticker=ticker)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    overall = data.get("overall_risk", "Unknown")
                    if overall and overall != "Unknown":
                        self._scored_this_pass += 1
                        self._total_scored += 1
                        self._last_scored_at = datetime.now(timezone.utc)
                        logger.debug("bulk_scoring_ticker_done",
                                     ticker=ticker, overall=overall)
                    else:
                        # No data available for this ticker (not in dilution DB)
                        logger.debug("bulk_scoring_ticker_no_data", ticker=ticker)
                elif resp.status_code == 404:
                    logger.debug("bulk_scoring_ticker_not_found", ticker=ticker)
                else:
                    self._errors_this_pass += 1
                    logger.warning("bulk_scoring_ticker_error",
                                   ticker=ticker, status=resp.status_code)
        except httpx.TimeoutException:
            self._errors_this_pass += 1
            logger.warning("bulk_scoring_ticker_timeout", ticker=ticker)
        except Exception as exc:
            self._errors_this_pass += 1
            logger.warning("bulk_scoring_ticker_failed", ticker=ticker, error=str(exc))


# Singleton
_bulk_scoring_service: Optional[BulkScoringService] = None


def get_bulk_scoring_service() -> BulkScoringService:
    global _bulk_scoring_service
    if _bulk_scoring_service is None:
        _bulk_scoring_service = BulkScoringService()
    return _bulk_scoring_service
