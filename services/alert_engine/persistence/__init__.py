import asyncio, json, logging
from datetime import datetime
from typing import Dict, List, Any

logger = logging.getLogger("alert-engine.persistence")

class AlertWriter:
    PERSIST_INTERVAL = 5
    MAX_BUFFER = 50000
    MAX_BATCH = 10000

    def __init__(self, timescale_client):
        self.ts = timescale_client
        self._buffer: List[Dict[str, Any]] = []
        self._running = False

    def buffer_alert(self, alert_dict, enriched=None):
        if len(self._buffer) >= self.MAX_BUFFER:
            self._buffer = self._buffer[-self.MAX_BUFFER // 2:]
        self._buffer.append({"alert": alert_dict, "enriched": enriched})

    async def run(self):
        self._running = True
        while self._running:
            await asyncio.sleep(self.PERSIST_INTERVAL)
            if self._buffer:
                await self._flush()

    async def stop(self):
        self._running = False

    async def _flush(self):
        batch = self._buffer[:self.MAX_BATCH]
        self._buffer = self._buffer[self.MAX_BATCH:]
        try:
            records = []
            for item in batch:
                a = item["alert"]
                e = item.get("enriched")
                records.append((
                    a.get("id"), datetime.fromisoformat(a["timestamp"]),
                    a["symbol"], a["event_type"], a.get("rule_id", ""),
                    float(a.get("price", 0)), float(a.get("quality", 0)),
                    a.get("description", ""),
                    float(a.get("change_percent", 0) or 0),
                    float(a.get("rvol", 0) or 0),
                    int(a.get("volume", 0) or 0),
                    float(a.get("market_cap", 0) or 0),
                    json.dumps(a.get("details", {})) if a.get("details") else None,
                    json.dumps(e) if e else None,
                ))
            await self.ts.executemany(
                """INSERT INTO market_events (id,ts,symbol,event_type,rule_id,price,
                   quality,description,change_percent,rvol,volume,market_cap,details,context)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                   ON CONFLICT (id) DO NOTHING""", records)
        except Exception as e:
            logger.error(f"Flush error: {e}")
            self._buffer = batch + self._buffer

    async def ensure_table(self):
        try:
            await self.ts.execute("""
                CREATE TABLE IF NOT EXISTS market_events (
                    id TEXT PRIMARY KEY, ts TIMESTAMPTZ NOT NULL,
                    symbol TEXT NOT NULL, event_type TEXT NOT NULL,
                    rule_id TEXT, price DOUBLE PRECISION,
                    quality DOUBLE PRECISION DEFAULT 0,
                    description TEXT DEFAULT '',
                    change_percent DOUBLE PRECISION, rvol DOUBLE PRECISION,
                    volume BIGINT, market_cap DOUBLE PRECISION,
                    details JSONB, context JSONB)""")
            return True
        except Exception as e:
            logger.error(f"Table error: {e}")
            return False
