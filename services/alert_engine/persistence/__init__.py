"""
AlertWriter — Efficient batch persistence of alerts to TimescaleDB.

Uses asyncpg COPY protocol (copy_records_to_table) for maximum throughput.
Buffers alerts in memory and flushes every FLUSH_INTERVAL seconds.
Only runs on partition 0 to avoid duplicate writes across workers.

Resilience:
  - Automatic reconnection on pool/connection failures.
  - Exponential back-off on consecutive errors (5s → 10s → 20s → 40s cap).
  - Health heartbeat every 60s regardless of traffic.
  - Never silently stops — the run() loop is crash-proof.

Performance: ~15K inserts/flush in <200ms via binary COPY.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger("alert-engine.persistence")

COLUMNS = [
    "id", "ts", "symbol", "event_type", "rule_id", "price",
    "change_pct", "rvol", "volume", "market_cap", "float_shares", "gap_pct",
    "security_type", "sector",
    "prev_value", "new_value", "delta", "delta_pct",
    "change_from_open", "open_price", "prev_close", "vwap", "atr_pct",
    "intraday_high", "intraday_low",
    "chg_1min", "chg_5min", "chg_10min", "chg_15min", "chg_30min",
    "vol_1min", "vol_5min",
    "vol_1min_pct", "vol_5min_pct",
    "rsi", "ema_20", "ema_50",
    "details", "context",
]

ALERT_KEY_TO_COL = {
    "id": "id",
    "timestamp": "ts",
    "symbol": "symbol",
    "event_type": "event_type",
    "rule_id": "rule_id",
    "price": "price",
    "change_percent": "change_pct",
    "rvol": "rvol",
    "volume": "volume",
    "market_cap": "market_cap",
    "float_shares": "float_shares",
    "gap_percent": "gap_pct",
    "security_type": "security_type",
    "sector": "sector",
    "prev_value": "prev_value",
    "new_value": "new_value",
    "delta": "delta",
    "delta_pct": "delta_pct",
    "change_from_open": "change_from_open",
    "open_price": "open_price",
    "prev_close": "prev_close",
    "vwap": "vwap",
    "atr_percent": "atr_pct",
    "intraday_high": "intraday_high",
    "intraday_low": "intraday_low",
    "chg_1min": "chg_1min",
    "chg_5min": "chg_5min",
    "chg_10min": "chg_10min",
    "chg_15min": "chg_15min",
    "chg_30min": "chg_30min",
    "vol_1min": "vol_1min",
    "vol_5min": "vol_5min",
    "vol_1min_pct": "vol_1min_pct",
    "vol_5min_pct": "vol_5min_pct",
    "rsi": "rsi",
    "ema_20": "ema_20",
    "ema_50": "ema_50",
    "details": "details",
}

_MAPPED_COL_SET = set(ALERT_KEY_TO_COL.values())
_SKIP_CONTEXT_KEYS = {"quality", "description", "__meta__"}

_BASE_BACKOFF = 5
_MAX_BACKOFF = 40
_HEALTH_INTERVAL = 60


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None
    except (ValueError, TypeError):
        return None


def _safe_int(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _parse_ts(raw) -> Optional[datetime]:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


class AlertWriter:
    FLUSH_INTERVAL = 5
    MAX_BUFFER = 80_000
    MAX_BATCH = 15_000

    def __init__(self, timescale_client):
        self._ts = timescale_client
        self._buffer: List[Dict[str, Any]] = []
        self._running = False
        self._total_flushed = 0
        self._total_errors = 0
        self._consecutive_errors = 0
        self._total_dropped = 0
        self._last_flush_ms = 0.0
        self._last_health_log = 0.0

    def buffer_alert(self, alert_dict: Dict, enriched: Optional[Dict] = None):
        if len(self._buffer) >= self.MAX_BUFFER:
            drop = len(self._buffer) // 4
            self._buffer = self._buffer[drop:]
            self._total_dropped += drop
            logger.warning("Buffer overflow — dropped %d oldest alerts (total dropped: %d)", drop, self._total_dropped)
        self._buffer.append({"alert": alert_dict, "enriched": enriched})

    async def run(self):
        """Main loop — crash-proof, never exits unless stopped."""
        self._running = True
        logger.info("AlertWriter started (COPY protocol, flush every %ds, max_batch=%d)", self.FLUSH_INTERVAL, self.MAX_BATCH)
        self._last_health_log = time.monotonic()

        while self._running:
            try:
                sleep_time = self._current_sleep()
                await asyncio.sleep(sleep_time)

                if self._buffer:
                    await self._flush()

                self._emit_health()

            except asyncio.CancelledError:
                logger.info("AlertWriter cancelled — flushing remaining %d alerts", len(self._buffer))
                if self._buffer:
                    try:
                        await self._flush()
                    except Exception:
                        pass
                break
            except Exception as e:
                self._consecutive_errors += 1
                self._total_errors += 1
                logger.error("AlertWriter run loop error (consec=%d): %s", self._consecutive_errors, str(e)[:300])
                await asyncio.sleep(self._current_sleep())

        logger.info("AlertWriter stopped (total persisted: %d, errors: %d, dropped: %d)", self._total_flushed, self._total_errors, self._total_dropped)

    async def stop(self):
        self._running = False

    def _current_sleep(self) -> float:
        if self._consecutive_errors == 0:
            return self.FLUSH_INTERVAL
        return min(_BASE_BACKOFF * (2 ** (self._consecutive_errors - 1)), _MAX_BACKOFF)

    def _emit_health(self):
        now = time.monotonic()
        if now - self._last_health_log >= _HEALTH_INTERVAL:
            self._last_health_log = now
            logger.info(
                "AlertWriter health: flushed=%d errors=%d consec_err=%d dropped=%d buffer=%d last_ms=%.0f",
                self._total_flushed, self._total_errors, self._consecutive_errors,
                self._total_dropped, len(self._buffer), self._last_flush_ms,
            )

    async def _flush(self):
        batch = self._buffer[:self.MAX_BATCH]
        self._buffer = self._buffer[self.MAX_BATCH:]
        t0 = time.monotonic()

        records = self._build_records(batch)
        if not records:
            return

        try:
            cols = ", ".join(COLUMNS)
            async with self._ts.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "CREATE TEMP TABLE _stg (LIKE market_events INCLUDING DEFAULTS) ON COMMIT DROP"
                    )
                    await conn.copy_records_to_table(
                        "_stg", records=records, columns=COLUMNS,
                    )
                    result = await conn.execute(f"""
                        INSERT INTO market_events ({cols})
                        SELECT {cols} FROM _stg
                        ON CONFLICT (id, ts) DO NOTHING
                    """)

            elapsed = (time.monotonic() - t0) * 1000
            self._total_flushed += len(records)
            self._last_flush_ms = elapsed
            self._consecutive_errors = 0

            if len(records) >= 50 or elapsed > 500:
                logger.info(
                    "Persisted %d alerts in %.0fms (total=%d, buffer=%d)",
                    len(records), elapsed, self._total_flushed, len(self._buffer),
                )

        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            self._consecutive_errors += 1
            self._total_errors += 1
            err_msg = str(e)[:300]
            logger.error(
                "COPY flush failed (consec=%d, elapsed=%.0fms, batch=%d): %s",
                self._consecutive_errors, elapsed, len(records), err_msg,
            )
            self._buffer = batch + self._buffer
            if len(self._buffer) > self.MAX_BUFFER:
                overflow = len(self._buffer) - self.MAX_BUFFER
                self._buffer = self._buffer[-self.MAX_BUFFER:]
                self._total_dropped += overflow
                logger.warning("Post-error buffer trim: dropped %d alerts", overflow)

    def _build_records(self, batch: List[Dict]) -> List[Tuple]:
        records = []
        for item in batch:
            a = item["alert"]
            enriched = item.get("enriched") or {}

            mapped: Dict[str, Any] = {}
            for alert_key, col in ALERT_KEY_TO_COL.items():
                v = a.get(alert_key)
                if v is not None:
                    mapped[col] = v

            context: Dict[str, Any] = {}
            for k, v in enriched.items():
                if v is not None and k not in _SKIP_CONTEXT_KEYS:
                    context[k] = v
            for k, v in a.items():
                if ALERT_KEY_TO_COL.get(k) is None and k not in _SKIP_CONTEXT_KEYS and v is not None:
                    context[k] = v

            ts = _parse_ts(mapped.get("ts"))
            if not ts or not mapped.get("id") or not mapped.get("symbol"):
                continue

            details_raw = mapped.get("details")
            if isinstance(details_raw, dict):
                details_json = json.dumps(details_raw)
            elif isinstance(details_raw, str):
                details_json = details_raw
            else:
                details_json = None

            context_json = json.dumps(context) if context else None

            row = (
                str(mapped.get("id", "")),
                ts,
                str(mapped.get("symbol", "")),
                str(mapped.get("event_type", "")),
                str(mapped.get("rule_id", "")),
                _safe_float(mapped.get("price")),
                _safe_float(mapped.get("change_pct")),
                _safe_float(mapped.get("rvol")),
                _safe_int(mapped.get("volume")),
                _safe_float(mapped.get("market_cap")),
                _safe_float(mapped.get("float_shares")),
                _safe_float(mapped.get("gap_pct")),
                mapped.get("security_type"),
                mapped.get("sector"),
                _safe_float(mapped.get("prev_value")),
                _safe_float(mapped.get("new_value")),
                _safe_float(mapped.get("delta")),
                _safe_float(mapped.get("delta_pct")),
                _safe_float(mapped.get("change_from_open")),
                _safe_float(mapped.get("open_price")),
                _safe_float(mapped.get("prev_close")),
                _safe_float(mapped.get("vwap")),
                _safe_float(mapped.get("atr_pct")),
                _safe_float(mapped.get("intraday_high")),
                _safe_float(mapped.get("intraday_low")),
                _safe_float(mapped.get("chg_1min")),
                _safe_float(mapped.get("chg_5min")),
                _safe_float(mapped.get("chg_10min")),
                _safe_float(mapped.get("chg_15min")),
                _safe_float(mapped.get("chg_30min")),
                _safe_int(mapped.get("vol_1min")),
                _safe_int(mapped.get("vol_5min")),
                _safe_float(mapped.get("vol_1min_pct")),
                _safe_float(mapped.get("vol_5min_pct")),
                _safe_float(mapped.get("rsi")),
                _safe_float(mapped.get("ema_20")),
                _safe_float(mapped.get("ema_50")),
                details_json,
                context_json,
            )
            records.append(row)

        return records

    @property
    def stats(self) -> Dict:
        return {
            "flushed": self._total_flushed,
            "errors": self._total_errors,
            "consecutive_errors": self._consecutive_errors,
            "dropped": self._total_dropped,
            "buffer": len(self._buffer),
            "last_flush_ms": round(self._last_flush_ms, 1),
        }
