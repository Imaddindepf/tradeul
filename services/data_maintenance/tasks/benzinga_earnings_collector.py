"""Benzinga Earnings Collector - Uses Polygon/Benzinga API for earnings data."""
import asyncio
import httpx
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
from shared.utils.logger import get_logger
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.config.settings import settings

logger = get_logger(__name__)

class BenzingaEarningsCollector:
    def __init__(self, redis: RedisClient, db: TimescaleClient):
        self.redis, self.db = redis, db
        self.api_key = settings.POLYGON_API_KEY
        self._client = None

    async def connect(self):
        if not self._client:
            self._client = httpx.AsyncClient(base_url="https://api.polygon.io", timeout=30.0, 
                                             headers={"Authorization": f"Bearer {self.api_key}"})

    async def disconnect(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _fetch(self, params: Dict) -> List[Dict]:
        results = []
        while True:
            r = await self._client.get("/benzinga/v1/earnings", params=params)
            r.raise_for_status()
            data = r.json()
            results.extend(data.get("results", []))
            if not data.get("next_url") or len(data.get("results", [])) < params.get("limit", 100):
                break
            if "cursor=" in data["next_url"]:
                params["cursor"] = data["next_url"].split("cursor=")[1].split("&")[0]
            await asyncio.sleep(0.1)
        return results

    def _time_slot(self, rec: Dict) -> str:
        t = rec.get("time", "")
        if not t: return "TBD"
        try:
            h = (int(t.split(":")[0]) - 5) % 24
            return "BMO" if h < 9 else ("AMC" if h >= 16 else "DURING")
        except: return "TBD"

    async def _upsert(self, rec: Dict):
        ticker, dt = rec.get("ticker", "").upper(), rec.get("date")
        if not ticker or not dt: return
        beat_eps = rec.get("actual_eps") > rec.get("estimated_eps") if rec.get("actual_eps") and rec.get("estimated_eps") else None
        beat_rev = rec.get("actual_revenue") > rec.get("estimated_revenue") if rec.get("actual_revenue") and rec.get("estimated_revenue") else None
        status = "reported" if rec.get("actual_eps") else "scheduled"
        fq = f"{rec.get('fiscal_period')} {rec.get('fiscal_year')}" if rec.get("fiscal_period") and rec.get("fiscal_year") else None
        
        q = """INSERT INTO earnings_calendar (symbol,company_name,report_date,time_slot,fiscal_quarter,eps_estimate,eps_actual,
               eps_surprise_pct,beat_eps,revenue_estimate,revenue_actual,revenue_surprise_pct,beat_revenue,status,source,
               importance,date_status,eps_method,revenue_method,previous_eps,previous_revenue,benzinga_id,notes,confidence)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24)
               ON CONFLICT (symbol,report_date) DO UPDATE SET company_name=COALESCE(EXCLUDED.company_name,earnings_calendar.company_name),
               time_slot=COALESCE(EXCLUDED.time_slot,earnings_calendar.time_slot),eps_estimate=COALESCE(EXCLUDED.eps_estimate,earnings_calendar.eps_estimate),
               eps_actual=COALESCE(EXCLUDED.eps_actual,earnings_calendar.eps_actual),eps_surprise_pct=COALESCE(EXCLUDED.eps_surprise_pct,earnings_calendar.eps_surprise_pct),
               beat_eps=COALESCE(EXCLUDED.beat_eps,earnings_calendar.beat_eps),revenue_estimate=COALESCE(EXCLUDED.revenue_estimate,earnings_calendar.revenue_estimate),
               revenue_actual=COALESCE(EXCLUDED.revenue_actual,earnings_calendar.revenue_actual),revenue_surprise_pct=COALESCE(EXCLUDED.revenue_surprise_pct,earnings_calendar.revenue_surprise_pct),
               beat_revenue=COALESCE(EXCLUDED.beat_revenue,earnings_calendar.beat_revenue),status=CASE WHEN EXCLUDED.eps_actual IS NOT NULL THEN 'reported' ELSE earnings_calendar.status END,
               source='benzinga',importance=COALESCE(EXCLUDED.importance,earnings_calendar.importance),date_status=COALESCE(EXCLUDED.date_status,earnings_calendar.date_status),
               eps_method=COALESCE(EXCLUDED.eps_method,earnings_calendar.eps_method),revenue_method=COALESCE(EXCLUDED.revenue_method,earnings_calendar.revenue_method),
               previous_eps=COALESCE(EXCLUDED.previous_eps,earnings_calendar.previous_eps),previous_revenue=COALESCE(EXCLUDED.previous_revenue,earnings_calendar.previous_revenue),
               benzinga_id=COALESCE(EXCLUDED.benzinga_id,earnings_calendar.benzinga_id),notes=COALESCE(EXCLUDED.notes,earnings_calendar.notes),updated_at=NOW()"""
        
        await self.db.execute(q, ticker, rec.get("company_name"), date.fromisoformat(dt), self._time_slot(rec), fq,
            rec.get("estimated_eps"), rec.get("actual_eps"), rec.get("eps_surprise_percent"), beat_eps,
            int(rec["estimated_revenue"]) if rec.get("estimated_revenue") else None,
            int(rec["actual_revenue"]) if rec.get("actual_revenue") else None,
            rec.get("revenue_surprise_percent"), beat_rev, status, "benzinga", rec.get("importance"),
            rec.get("date_status"), rec.get("eps_method"), rec.get("revenue_method"), rec.get("previous_eps"),
            int(rec["previous_revenue"]) if rec.get("previous_revenue") else None,
            rec.get("benzinga_id"), rec.get("notes"), 0.95)

    async def collect_date(self, d: date) -> Dict:
        logger.info("collecting_benzinga_earnings", date=d.isoformat())
        try:
            results = await self._fetch({"date": d.isoformat(), "limit": 1000, "sort": "importance.desc"})
            cnt = 0
            for r in results:
                try: await self._upsert(r); cnt += 1
                except Exception as e: logger.warning("upsert_failed", ticker=r.get("ticker"), error=str(e))
            await self.redis.set(f"earnings:calendar:{d.isoformat()}", results, ttl=300)
            logger.info("earnings_collected", date=d.isoformat(), total=len(results), inserted=cnt)
            return {"success": True, "date": d.isoformat(), "total": len(results), "inserted": cnt}
        except Exception as e:
            logger.error("collect_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def collect_range(self, start: date, end: date) -> Dict:
        logger.info("collecting_range", start=start.isoformat(), end=end.isoformat())
        try:
            results = await self._fetch({"date.gte": start.isoformat(), "date.lte": end.isoformat(), "limit": 1000, "sort": "date.asc,importance.desc"})
            cnt = 0
            for r in results:
                try: await self._upsert(r); cnt += 1
                except: pass
            await self.redis.set("earnings:upcoming", results, ttl=180)
            return {"success": True, "total": len(results), "inserted": cnt}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def execute(self, mode: str = "full") -> Dict:
        results = {"mode": mode, "success": True}
        try:
            await self.connect()
            today = date.today()
            if mode in ("today", "full"): results["today"] = await self.collect_date(today)
            if mode in ("upcoming", "full"): results["upcoming"] = await self.collect_range(today, today + timedelta(14))
            if mode in ("recent", "full"): results["recent"] = await self.collect_range(today - timedelta(7), today - timedelta(1))
            return results
        except Exception as e:
            results["success"], results["error"] = False, str(e)
            return results
        finally:
            await self.disconnect()

async def collect_earnings_benzinga(mode: str = "full") -> Dict:
    redis, db = RedisClient(), TimescaleClient()
    try:
        await redis.connect(); await db.connect()
        return await BenzingaEarningsCollector(redis, db).execute(mode)
    finally:
        await db.disconnect(); await redis.disconnect()

async def collect_today_earnings() -> Dict:
    return await collect_earnings_benzinga("today")

async def collect_upcoming_earnings() -> Dict:
    return await collect_earnings_benzinga("upcoming")
