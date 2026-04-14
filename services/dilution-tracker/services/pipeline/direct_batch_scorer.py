"""
Direct Batch Scorer
===================
Scores ALL tickers in one pass using only local DB data — no external API calls.

Pipeline:
  1. One mega-query fetches all scoring inputs from the remote dilutiontracker DB
     (instruments, shares history, cash from dt_cash_position/meta, prices)
  2. Python calculates all 5 ratings per ticker using DilutionTrackerRiskScorer
  3. Bulk upsert into local dilution_scores table + Redis hash

Speed: ~3 385 tickers in < 2 minutes vs ~10 hours with the per-ticker HTTP approach.

Runs every RUN_INTERVAL_H hours (default 6).
"""

import asyncio
import os
import time
from datetime import date, datetime, timezone
from typing import Optional

import asyncpg
import orjson

from calculators.dilution_tracker_risk_scorer import (
    DilutionTrackerRiskScorer,
    write_dilution_scores_to_redis,
)
from shared.utils.logger import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
# Canal Redis donde data_maintenance publica el trigger
BATCH_TRIGGER_CHANNEL = "dilution:batch:trigger"
# Clave Redis donde se escribe el resultado para que data_maintenance lo lea
BATCH_RESULT_KEY      = "dilution:batch:last_result"

RUN_INTERVAL_H = float(os.getenv("BATCH_SCORER_INTERVAL_H", "6"))

# Remote dilutiontracker DB
REMOTE_DB_HOST = os.getenv("DB_HOST",     "127.0.0.1")
REMOTE_DB_PORT = int(os.getenv("DB_PORT", "55433"))
REMOTE_DB_NAME = os.getenv("DB_NAME",     "dilutiontracker")
REMOTE_DB_USER = os.getenv("DB_USER",     "dilution_admin")
REMOTE_DB_PASS = os.getenv("DB_PASSWORD", "")

# Local tradeul DB (dilution_scores)
LOCAL_DB_HOST = os.getenv("POSTGRES_HOST", "timescaledb")
LOCAL_DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
LOCAL_DB_NAME = os.getenv("POSTGRES_DB",   "tradeul")
LOCAL_DB_USER = os.getenv("POSTGRES_USER", "tradeul_user")
LOCAL_DB_PASS = os.getenv("POSTGRES_PASSWORD", "")

# ── Mega-query ────────────────────────────────────────────────────────────────
# Fetches all scoring inputs for every ticker in a single round-trip.
# Uses only local DB tables — no Perplexity, no Polygon, no SEC-API.
_BATCH_QUERY = """
WITH
-- ── Warrants: sum remaining_warrants per ticker (only where > 0) ─────────────
warrants AS (
    SELECT i.ticker,
           SUM(COALESCE(wd.remaining_warrants, 0)) AS warrant_shares
    FROM instruments i
    JOIN warrant_details wd ON wd.instrument_id = i.id
    WHERE wd.remaining_warrants > 0
    GROUP BY i.ticker
),

-- ── Shelves: sum raisable capacity; flag active shelf ────────────────────────
shelves AS (
    SELECT i.ticker,
           SUM(COALESCE(sd.current_raisable_amount, sd.total_shelf_capacity, 0)) AS shelf_capacity
    FROM instruments i
    JOIN shelf_details sd ON sd.instrument_id = i.id
    WHERE COALESCE(sd.current_raisable_amount, sd.total_shelf_capacity, 0) > 0
      AND (sd.expiration_date IS NULL OR sd.expiration_date >= CURRENT_DATE)
    GROUP BY i.ticker
),

-- ── ATMs: sum remaining capacity in USD (converted to shares later in Python) ─
atms AS (
    SELECT i.ticker,
           SUM(COALESCE(ad.remaining_atm_capacity, 0)) AS atm_usd
    FROM instruments i
    JOIN atm_details ad ON ad.instrument_id = i.id
    WHERE COALESCE(ad.remaining_atm_capacity, 0) > 0
    GROUP BY i.ticker
),

-- ── Convertible notes: sum remaining shares when converted ──────────────────
convs AS (
    SELECT i.ticker,
           SUM(COALESCE(cd.remaining_shares_converted,
                        cd.total_shares_converted, 0)) AS conv_shares
    FROM instruments i
    JOIN conv_note_details cd ON cd.instrument_id = i.id
    WHERE COALESCE(cd.remaining_shares_converted,
                   cd.total_shares_converted, 0) > 0
    GROUP BY i.ticker
),

-- ── Equity lines: use current_shares_equiv if available ─────────────────────
elocs AS (
    SELECT i.ticker,
           SUM(COALESCE(eld.current_shares_equiv, 0)) AS el_shares
    FROM instruments i
    JOIN equity_line_details eld ON eld.instrument_id = i.id
    WHERE COALESCE(eld.current_shares_equiv, 0) > 0
       OR COALESCE(eld.remaining_el_capacity, 0) > 0
    GROUP BY i.ticker
),

-- ── Pending S-1 ──────────────────────────────────────────────────────────────
s1_pending AS (
    SELECT DISTINCT i.ticker
    FROM instruments i
    JOIN s1_offering_details s1d ON s1d.instrument_id = i.id
    WHERE s1d.status::text NOT IN ('Priced', 'Withdrawn')
),

-- ── Current shares (latest from shares_outstanding table, in millions→actual) ─
shares_current AS (
    SELECT DISTINCT ON (ticker)
        ticker,
        ROUND(shares_outstanding * 1000000) AS current_shares
    FROM shares_outstanding
    ORDER BY ticker, report_date DESC
),

-- ── Shares outstanding 3 years ago (closest to -3yr within ±6mo window) ─────
-- Values are stored in millions → multiply by 1 000 000
shares_3yr AS (
    SELECT DISTINCT ON (ticker)
        ticker,
        ROUND(shares_outstanding * 1000000) AS shares_3yr_ago
    FROM shares_outstanding
    WHERE report_date BETWEEN CURRENT_DATE - INTERVAL '42 months'
                          AND CURRENT_DATE - INTERVAL '30 months'
    ORDER BY ticker, report_date DESC
),

-- ── Recent offerings (last 90 days) ─────────────────────────────────────────
recent_off AS (
    SELECT DISTINCT ticker
    FROM completed_offerings
    WHERE offering_date > CURRENT_DATE - INTERVAL '90 days'
)

SELECT
    t.ticker,
    t.last_price,
    -- Prefer shares_outstanding table (more up-to-date, stored in millions)
    COALESCE(sc.current_shares, t.shares_outstanding) AS so_tickers,
    -- instruments
    COALESCE(w.warrant_shares,  0)               AS warrant_shares,
    COALESCE(sh.shelf_capacity, 0)               AS shelf_capacity,
    (sh.ticker IS NOT NULL)                      AS has_active_shelf,
    COALESCE(a.atm_usd,         0)               AS atm_usd,
    COALESCE(c.conv_shares,     0)               AS conv_shares,
    COALESCE(el.el_shares,      0)               AS el_shares,
    (s1.ticker IS NOT NULL)                      AS has_pending_s1,
    (ro.ticker IS NOT NULL)                      AS has_recent_offering,
    -- shares history
    s3.shares_3yr_ago,
    -- cash (analyst tables)
    cm.quarterly_op_cashflow_millions            AS ocf_m,
    cm.recent_offerings_millions                 AS raises_m,
    cm.last_cash_date,
    cp.cash_millions                             AS cash_m
FROM tickers t
LEFT JOIN warrants       w  ON w.ticker  = t.ticker
LEFT JOIN shelves        sh ON sh.ticker = t.ticker
LEFT JOIN atms           a  ON a.ticker  = t.ticker
LEFT JOIN convs          c  ON c.ticker  = t.ticker
LEFT JOIN elocs          el ON el.ticker = t.ticker
LEFT JOIN s1_pending     s1 ON s1.ticker = t.ticker
LEFT JOIN shares_current sc ON sc.ticker = t.ticker
LEFT JOIN shares_3yr     s3 ON s3.ticker = t.ticker
LEFT JOIN recent_off     ro ON ro.ticker = t.ticker
LEFT JOIN dt_cash_meta     cm ON cm.ticker = t.ticker
LEFT JOIN dt_cash_position cp ON cp.ticker = t.ticker
                              AND cp.period_date = cm.last_cash_date
WHERE LENGTH(t.ticker) <= 20
  AND t.ticker NOT ILIKE '%delisted%'
  AND t.ticker NOT ILIKE '%_deleted%'
ORDER BY t.ticker
"""

_UPSERT_SCORES = """
INSERT INTO dilution_scores
    (ticker, overall_risk, overall_risk_score,
     offering_ability, offering_ability_score,
     overhead_supply,  overhead_supply_score,
     historical_dilution, historical_dilution_score,
     cash_need, cash_need_score, updated_at)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11, NOW())
ON CONFLICT (ticker) DO UPDATE SET
    overall_risk              = EXCLUDED.overall_risk,
    overall_risk_score        = EXCLUDED.overall_risk_score,
    offering_ability          = EXCLUDED.offering_ability,
    offering_ability_score    = EXCLUDED.offering_ability_score,
    overhead_supply           = EXCLUDED.overhead_supply,
    overhead_supply_score     = EXCLUDED.overhead_supply_score,
    historical_dilution       = EXCLUDED.historical_dilution,
    historical_dilution_score = EXCLUDED.historical_dilution_score,
    cash_need                 = EXCLUDED.cash_need,
    cash_need_score           = EXCLUDED.cash_need_score,
    updated_at                = NOW()
"""


def _label_to_int(label: str | None) -> Optional[int]:
    return {"Low": 1, "Medium": 2, "High": 3}.get(label or "") if label else None


def _risk_level_label(level) -> str:
    return level.value if hasattr(level, "value") else str(level)


# ── Score one row ──────────────────────────────────────────────────────────────

def _score_row(row: dict, scorer: DilutionTrackerRiskScorer) -> Optional[dict]:
    """
    Computes all 5 ratings from a single DB row.
    Returns ratings dict or None if data is insufficient.
    """
    ticker     = row["ticker"]
    price      = float(row["last_price"] or 0)
    so_current = int(row["so_tickers"] or 0)

    # ── Sharing outstanding (use tickers table; fallback 0) ───────────────────
    shares_3yr  = int(row["shares_3yr_ago"] or 0)

    # ── Cash ─────────────────────────────────────────────────────────────────
    M = 1_000_000
    ocf_q       = float(row["ocf_m"]    or 0) * M   # quarterly OCF in $
    raises      = float(row["raises_m"] or 0) * M
    hist_cash   = float(row["cash_m"]   or 0) * M
    last_date   = row["last_cash_date"]

    runway_months = None
    has_pos_cf    = False
    est_cash      = None

    if last_date and hist_cash:
        try:
            days = max((date.today() - last_date).days, 1)
        except Exception:
            days = 0
        prorated = (ocf_q / 90 * days) if ocf_q else 0
        est_cash  = hist_cash + prorated + raises
        if ocf_q >= 0:
            has_pos_cf = True
        elif ocf_q < 0:
            runway_months = round((est_cash / -ocf_q) * 3, 2) if est_cash > 0 else 0.0

    # ── Instruments ───────────────────────────────────────────────────────────
    warrant_shares   = int(row["warrant_shares"]  or 0)
    shelf_capacity   = float(row["shelf_capacity"] or 0)
    has_active_shelf = bool(row["has_active_shelf"])
    atm_usd          = float(row["atm_usd"]        or 0)
    conv_shares      = int(row["conv_shares"]      or 0)
    el_shares        = int(row["el_shares"]        or 0)
    has_pending_s1   = bool(row["has_pending_s1"])
    has_recent_off   = bool(row["has_recent_offering"])

    # ATM USD → shares (needs current price)
    atm_shares = int(atm_usd / price) if price > 0 and atm_usd > 0 else 0

    ratings = scorer.calculate_all_ratings(
        # Offering Ability
        shelf_capacity_remaining  = shelf_capacity,
        has_active_shelf          = has_active_shelf,
        has_pending_s1            = has_pending_s1,
        # Overhead Supply
        warrants_shares           = warrant_shares,
        atm_shares                = atm_shares,
        convertible_shares        = conv_shares,
        equity_line_shares        = el_shares,
        shares_outstanding        = so_current,
        # Historical
        shares_outstanding_3yr_ago        = shares_3yr,
        shares_outstanding_current_sec    = so_current,
        # Cash Need
        runway_months             = runway_months,
        has_positive_operating_cf = has_pos_cf,
        estimated_current_cash    = est_cash,
        annual_burn_rate          = ocf_q * 4 if ocf_q else None,
        # Context
        has_recent_offering       = has_recent_off,
        current_price             = price,
    )

    d = ratings.to_dict()
    return {
        "ticker":                   ticker,
        "overall_risk":             _risk_level_label(ratings.overall_risk),
        "overall_risk_score":       _label_to_int(_risk_level_label(ratings.overall_risk)),
        "offering_ability":         _risk_level_label(ratings.offering_ability),
        "offering_ability_score":   _label_to_int(_risk_level_label(ratings.offering_ability)),
        "overhead_supply":          _risk_level_label(ratings.overhead_supply),
        "overhead_supply_score":    _label_to_int(_risk_level_label(ratings.overhead_supply)),
        "historical_dilution":      _risk_level_label(ratings.historical),
        "historical_dilution_score": _label_to_int(_risk_level_label(ratings.historical)),
        "cash_need":                _risk_level_label(ratings.cash_need),
        "cash_need_score":          _label_to_int(_risk_level_label(ratings.cash_need)),
    }


# ── Main service class ─────────────────────────────────────────────────────────

class DirectBatchScorer:
    """
    Background service that scores ALL tickers from the DB in one fast pass.
    Start with start(), stop with stop().
    """

    def __init__(self, redis: RedisClient):
        self.redis   = redis
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._scorer  = DilutionTrackerRiskScorer()

        # Stats
        self._pass_number   = 0
        self._last_run_at: Optional[datetime] = None
        self._last_run_ms   = 0
        self._last_scored   = 0
        self._last_errors   = 0

    # ── Public ────────────────────────────────────────────────────────────────

    def start(self):
        """Inicia el listener Redis que espera trigger del servicio de mantenimiento."""
        if self._task and not self._task.done():
            logger.info("direct_batch_scorer_already_running")
            return
        self._running = True
        self._task = asyncio.create_task(
            self._redis_listener(), name="direct_batch_scorer_listener"
        )
        logger.info("direct_batch_scorer_listening", channel=BATCH_TRIGGER_CHANNEL)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("direct_batch_scorer_stopped")

    def status(self) -> dict:
        return {
            "running":        self._running,
            "pass_number":    self._pass_number,
            "last_run_at":    self._last_run_at.isoformat() if self._last_run_at else None,
            "last_run_ms":    self._last_run_ms,
            "last_scored":    self._last_scored,
            "last_errors":    self._last_errors,
            "interval_hours": RUN_INTERVAL_H,
        }

    # ── Redis pub/sub listener ────────────────────────────────────────────────

    async def _redis_listener(self):
        """
        Suscribe al canal `dilution:batch:trigger`.
        Cuando data_maintenance publica un mensaje, ejecuta _run_once() y
        escribe el resultado en `dilution:batch:last_result` (clave Redis TTL 5min).
        """
        while self._running:
            try:
                import redis.asyncio as aioredis
                redis_url = (
                    f"redis://:{os.getenv('REDIS_PASSWORD', 'tradeul_redis_secure_2024')}"
                    f"@{os.getenv('REDIS_HOST', '127.0.0.1')}"
                    f":{os.getenv('REDIS_PORT', '6379')}/0"
                )
                r = aioredis.from_url(redis_url)
                pubsub = r.pubsub()
                await pubsub.subscribe(BATCH_TRIGGER_CHANNEL)
                logger.info("direct_batch_scorer_subscribed", channel=BATCH_TRIGGER_CHANNEL)

                async for message in pubsub.listen():
                    if not self._running:
                        break
                    if message["type"] != "message":
                        continue

                    logger.info("direct_batch_scorer_trigger_received")
                    try:
                        await self._run_once()
                        result = {
                            "ok": True,
                            "scored": self._last_scored,
                            "errors": self._last_errors,
                            "elapsed_ms": self._last_run_ms,
                            "pass_num": self._pass_number,
                        }
                    except Exception as exc:
                        logger.error("direct_batch_scorer_run_failed", error=str(exc))
                        result = {"ok": False, "error": str(exc)}

                    # Escribir resultado para que data_maintenance lo lea
                    await r.set(BATCH_RESULT_KEY, orjson.dumps(result), ex=300)

                await pubsub.unsubscribe(BATCH_TRIGGER_CHANNEL)
                await r.aclose()

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("direct_batch_scorer_listener_error", error=str(exc))
                await asyncio.sleep(10)  # Reconectar tras error

    async def _run_once(self):
        t0 = time.monotonic()
        self._pass_number += 1
        logger.info("direct_batch_scorer_pass_start", pass_num=self._pass_number)

        # ── 1. Fetch all rows in one query ────────────────────────────────────
        try:
            remote_conn = await asyncpg.connect(
                host=REMOTE_DB_HOST, port=REMOTE_DB_PORT,
                user=REMOTE_DB_USER, password=REMOTE_DB_PASS,
                database=REMOTE_DB_NAME,
            )
            rows = await remote_conn.fetch(_BATCH_QUERY)
            await remote_conn.close()
        except Exception as exc:
            logger.error("direct_batch_scorer_fetch_failed", error=str(exc))
            return

        logger.info("direct_batch_scorer_rows_fetched", count=len(rows))

        # ── 2. Score all tickers in Python ────────────────────────────────────
        scored_list = []
        errors = 0
        for row in rows:
            try:
                result = _score_row(dict(row), self._scorer)
                if result:
                    scored_list.append(result)
            except Exception as exc:
                logger.debug("direct_batch_scorer_row_error",
                             ticker=row.get("ticker"), error=str(exc))
                errors += 1

        logger.info("direct_batch_scorer_scoring_done",
                    scored=len(scored_list), errors=errors)

        # ── 3. Bulk upsert into local dilution_scores ─────────────────────────
        await self._bulk_upsert(scored_list)

        # ── 4. Write Redis hash (dilution:scores:latest) ──────────────────────
        await self._write_redis(scored_list)

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        self._last_run_at  = datetime.now(timezone.utc)
        self._last_run_ms  = elapsed_ms
        self._last_scored  = len(scored_list)
        self._last_errors  = errors

        logger.info("direct_batch_scorer_pass_done",
                    pass_num=self._pass_number,
                    scored=len(scored_list),
                    errors=errors,
                    elapsed_ms=elapsed_ms,
                    next_run_h=RUN_INTERVAL_H)

    async def _bulk_upsert(self, scored_list: list[dict]):
        """Upsert all scores into local dilution_scores in one transaction."""
        if not scored_list:
            return
        try:
            local_conn = await asyncpg.connect(
                host=LOCAL_DB_HOST, port=LOCAL_DB_PORT,
                user=LOCAL_DB_USER, password=LOCAL_DB_PASS,
                database=LOCAL_DB_NAME,
            )
            try:
                async with local_conn.transaction():
                    await local_conn.executemany(
                        _UPSERT_SCORES,
                        [
                            (
                                s["ticker"],
                                s["overall_risk"],        s["overall_risk_score"],
                                s["offering_ability"],    s["offering_ability_score"],
                                s["overhead_supply"],     s["overhead_supply_score"],
                                s["historical_dilution"], s["historical_dilution_score"],
                                s["cash_need"],           s["cash_need_score"],
                            )
                            for s in scored_list
                        ],
                    )
            finally:
                await local_conn.close()
            logger.info("direct_batch_scorer_upsert_done", count=len(scored_list))
        except Exception as exc:
            logger.error("direct_batch_scorer_upsert_failed", error=str(exc))

    async def _write_redis(self, scored_list: list[dict]):
        """Write all scores to Redis hash dilution:scores:latest."""
        if not scored_list:
            return
        try:
            await self.redis.connect()
            now_iso = datetime.now().isoformat()
            pipe = {}
            for s in scored_list:
                payload = {
                    "overall_risk":             s["overall_risk"],
                    "overall_risk_score":       s["overall_risk_score"],
                    "offering_ability":         s["offering_ability"],
                    "offering_ability_score":   s["offering_ability_score"],
                    "overhead_supply":          s["overhead_supply"],
                    "overhead_supply_score":    s["overhead_supply_score"],
                    "historical_dilution":      s["historical_dilution"],
                    "historical_dilution_score": s["historical_dilution_score"],
                    "cash_need":                s["cash_need"],
                    "cash_need_score":          s["cash_need_score"],
                    "updated_at":               now_iso,
                }
                pipe[s["ticker"]] = orjson.dumps(payload)

            await self.redis.client.hset("dilution:scores:latest", mapping=pipe)
            logger.info("direct_batch_scorer_redis_done", count=len(pipe))
            try:
                await self.redis.disconnect()
            except Exception:
                pass
        except Exception as exc:
            logger.error("direct_batch_scorer_redis_failed", error=str(exc))


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[DirectBatchScorer] = None


def get_direct_batch_scorer(redis: RedisClient) -> DirectBatchScorer:
    global _instance
    if _instance is None:
        _instance = DirectBatchScorer(redis)
    return _instance
