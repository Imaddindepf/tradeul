"""
Reactive consumer for SEC filing stream -> dilution v2 pipeline.
"""

from __future__ import annotations

import asyncio
import csv
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import redis.asyncio as aioredis

SERVICE_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.append(str(SERVICE_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
if "/app" not in sys.path:
    sys.path.append("/app")

from shared.config.settings import settings
from shared.utils.logger import get_logger
from shared.utils.timescale_client import TimescaleClient

logger = get_logger(__name__)


@dataclass
class FilingPriorityRule:
    form_type: str
    immediate_impact: str


class ReactiveFilingConsumerV2:
    SEC_STREAM_KEY = "stream:sec:filings"
    DILUTION_STREAM_KEY = "stream:dilution:v2:filings"
    GROUP_NAME = "dilution-v2"
    CONSUMER_NAME = "dilution-v2-consumer"

    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None
        self._redis = None
        self._db: TimescaleClient | None = None
        self._rules = self._load_priority_rules()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._redis = await self._build_redis_client()
        self._db = TimescaleClient()
        await self._db.connect(min_size=1, max_size=5)
        await self._ensure_group()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("reactive_filing_consumer_started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._redis:
            await self._redis.close()
        if self._db:
            await self._db.disconnect()
        logger.info("reactive_filing_consumer_stopped")

    async def _run_loop(self) -> None:
        assert self._redis is not None
        while self._running:
            try:
                records = await self._redis.xreadgroup(
                    groupname=self.GROUP_NAME,
                    consumername=self.CONSUMER_NAME,
                    streams={self.SEC_STREAM_KEY: ">"},
                    count=50,
                    block=5000,
                )
                if not records:
                    continue
                for stream_name, entries in records:
                    for message_id, fields in entries:
                        try:
                            await self._handle_message(fields)
                            await self._redis.xack(stream_name, self.GROUP_NAME, message_id)
                        except Exception as exc:
                            logger.error("reactive_filing_message_failed", error=str(exc), message_id=message_id)
                            await self._redis.xack(stream_name, self.GROUP_NAME, message_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("reactive_filing_loop_error", error=str(exc))
                await asyncio.sleep(2)

    async def _handle_message(self, fields: dict[str, Any]) -> None:
        raw = fields.get("data")
        if not raw:
            return
        filing = json.loads(raw)
        ticker = (filing.get("ticker") or "").upper().strip()
        accession = filing.get("accessionNo")
        if not ticker or not accession:
            return

        assert self._db is not None
        ticker_exists = await self._db.fetchval(
            "SELECT 1 FROM tickers WHERE ticker = $1",
            ticker,
        )
        if not ticker_exists:
            return

        form_type = (filing.get("formType") or "").strip()
        priority = self._priority_for(form_type)
        filing_date = self._parse_filing_date(filing.get("filedAt"))
        filing_url = filing.get("linkToFilingDetails") or filing.get("linkToHtml")
        context_url = f"/api/instrument-context/{ticker}"

        payload = {
            "ticker": ticker,
            "accession_number": accession,
            "form_type": form_type,
            "filed_at": filing.get("filedAt"),
            "filing_url": filing_url,
            "file_number": filing.get("fileNumber"),
            "priority": priority,
            "context_url": context_url,
            "source": "sec_stream_reactive",
        }

        assert self._redis is not None
        await self._redis.xadd(
            self.DILUTION_STREAM_KEY,
            {"data": json.dumps(payload)},
            maxlen=5000,
            approximate=True,
        )

        await self._insert_log_event(
            ticker=ticker,
            form_type=form_type,
            accession_number=accession,
            filing_date=filing_date,
            filing_url=filing_url,
            payload=payload,
        )

    async def _insert_log_event(
        self,
        ticker: str,
        form_type: str,
        accession_number: str,
        filing_date: date,
        filing_url: str | None,
        payload: dict[str, Any],
    ) -> None:
        assert self._db is not None
        await self._db.execute(
            """
            INSERT INTO filing_events (
                id, ticker, form_type, purpose, filing_date, edgar_url,
                accession_number, file_number, agent_action, instrument_id,
                confidence, agent_model, raw_extraction, processed_at
            )
            VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, NULL, 'LOG'::agent_action_enum, NULL,
                1.0, 'reactive-consumer-v2', $8::jsonb, NOW()
            )
            ON CONFLICT (accession_number) DO NOTHING
            """,
            uuid4(),
            ticker,
            form_type,
            "reactive filing queued",
            filing_date,
            filing_url,
            accession_number,
            json.dumps(payload),
        )

    async def _ensure_group(self) -> None:
        assert self._redis is not None
        try:
            await self._redis.xgroup_create(
                name=self.SEC_STREAM_KEY,
                groupname=self.GROUP_NAME,
                id="$",
                mkstream=True,
            )
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def _build_redis_client(self):
        if settings.redis_password:
            redis_url = f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
        else:
            redis_url = f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
        return await aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)

    def _priority_for(self, form_type: str) -> str:
        normalized = form_type.upper()
        rule = self._rules.get(normalized)
        if not rule:
            return "normal"
        impact = (rule.immediate_impact or "").lower()
        if "high" in impact:
            return "high"
        if "medium" in impact:
            return "medium"
        return "normal"

    def _load_priority_rules(self) -> dict[str, FilingPriorityRule]:
        csv_path = PROJECT_ROOT / "SEC_Cheat_Sheet_Cheat_Sheet.csv"
        if not csv_path.exists():
            return {}
        rules: dict[str, FilingPriorityRule] = {}
        with csv_path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                filing = (row.get("Filing") or "").strip()
                impact = (row.get("Immediate Price Impact") or "").strip()
                if not filing:
                    continue
                for token in filing.split("/"):
                    clean = token.strip().upper()
                    if clean:
                        rules[clean] = FilingPriorityRule(form_type=clean, immediate_impact=impact)
        return rules

    @staticmethod
    def _parse_filing_date(value: Any) -> date:
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
            except ValueError:
                pass
        return datetime.utcnow().date()
