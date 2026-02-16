"""
Earnings Stream Manager

Manages real-time polling of Benzinga Earnings API and broadcasting
updates via Redis streams for frontend consumption.

Architecture:
- Polls Benzinga API at configurable intervals
- Deduplicates using Redis sets
- Caches in Redis sorted sets (by date)
- Persists to TimescaleDB for historical queries
- Publishes updates to Redis stream for real-time frontend updates
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Set
import structlog
import redis.asyncio as aioredis
from redis.asyncio import Redis
import asyncpg

from .benzinga_earnings_client import BenzingaEarningsClient
from models.earnings import BenzingaEarning

logger = structlog.get_logger(__name__)


class EarningsStreamManager:
    """
    Manages earnings data flow from Benzinga API to Redis and TimescaleDB.
    
    Features:
    - Frequent polling for real-time updates
    - Redis caching for fast frontend queries
    - Redis stream for real-time push to frontend
    - TimescaleDB persistence for historical data
    - Deduplication to avoid redundant processing
    """
    
    # Redis keys
    STREAM_KEY = "stream:benzinga:earnings"
    CACHE_TODAY_KEY = "cache:benzinga:earnings:today"
    CACHE_UPCOMING_KEY = "cache:benzinga:earnings:upcoming"
    CACHE_BY_DATE_PREFIX = "cache:benzinga:earnings:date:"
    CACHE_BY_TICKER_PREFIX = "cache:benzinga:earnings:ticker:"
    DEDUP_SET_KEY = "dedup:benzinga:earnings"
    LAST_POLL_KEY = "benzinga:earnings:last_poll"
    LAST_UPDATE_KEY = "benzinga:earnings:last_update"
    
    # Configuration
    CACHE_SIZE = 500
    CACHE_BY_DATE_SIZE = 200
    CACHE_BY_TICKER_SIZE = 50
    DEDUP_TTL = 86400 * 30  # 30 days
    STREAM_MAXLEN = 1000
    
    def __init__(
        self,
        api_key: str,
        redis_client: Redis,
        db_pool: Optional[asyncpg.Pool] = None,
        poll_interval: int = 30,
        full_sync_interval: int = 3600
    ):
        """
        Initialize the stream manager.
        
        Args:
            api_key: Polygon API key
            redis_client: Connected Redis client
            db_pool: Optional asyncpg pool for TimescaleDB
            poll_interval: Seconds between polls for updates
            full_sync_interval: Seconds between full syncs
        """
        self.redis = redis_client
        self.db_pool = db_pool
        self.poll_interval = poll_interval
        self.full_sync_interval = full_sync_interval
        
        # Earnings client
        self.client = BenzingaEarningsClient(api_key)
        
        # Control
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._full_sync_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.stats = {
            "earnings_processed": 0,
            "earnings_updated": 0,
            "duplicates_skipped": 0,
            "db_upserts": 0,
            "stream_publishes": 0,
            "errors": 0,
            "polls_completed": 0,
            "full_syncs_completed": 0,
            "started_at": None,
            "last_poll_time": None,
            "last_full_sync_time": None
        }
        
        logger.info(
            "earnings_stream_manager_initialized",
            poll_interval=poll_interval,
            full_sync_interval=full_sync_interval
        )
    
    async def start(self):
        """Start the stream manager."""
        logger.info("Starting Earnings Stream Manager...")
        
        self.stats["started_at"] = datetime.now().isoformat()
        self._running = True
        
        # Initial full sync
        await self._full_sync()
        
        # Start polling task
        self._poll_task = asyncio.create_task(self._poll_loop())
        
        # Start full sync task
        self._full_sync_task = asyncio.create_task(self._full_sync_loop())
        
        logger.info("Earnings Stream Manager started")
    
    async def stop(self):
        """Stop the stream manager."""
        logger.info("Stopping Earnings Stream Manager...")
        
        self._running = False
        
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        
        if self._full_sync_task:
            self._full_sync_task.cancel()
            try:
                await self._full_sync_task
            except asyncio.CancelledError:
                pass
        
        await self.client.close()
        
        logger.info("Earnings Stream Manager stopped")
    
    async def _poll_loop(self):
        """
        Main polling loop for incremental updates.
        
        Uses last_updated filter to get only changed records.
        """
        logger.info(f"Starting poll loop (interval: {self.poll_interval}s)")
        
        while self._running:
            try:
                # Get last update timestamp
                last_update = await self._get_last_update_time()
                
                if last_update:
                    # Fetch only updated records
                    earnings = await self.client.fetch_updated_since(
                        since=last_update,
                        limit=100
                    )
                else:
                    # First run - get today's earnings
                    earnings = await self.client.fetch_today_earnings()
                
                # Process earnings
                new_count = 0
                updated_count = 0
                
                for earning in earnings:
                    is_new, was_updated = await self._process_earning(earning)
                    if is_new:
                        new_count += 1
                    if was_updated:
                        updated_count += 1
                
                # Update last poll timestamp
                if earnings:
                    # Use the most recent last_updated from fetched earnings
                    latest = max(
                        (e.last_updated for e in earnings if e.last_updated),
                        default=None
                    )
                    if latest:
                        await self._set_last_update_time(latest)
                
                self.stats["polls_completed"] += 1
                self.stats["last_poll_time"] = datetime.now().isoformat()
                
                if new_count > 0 or updated_count > 0:
                    logger.info(
                        "Poll completed",
                        new=new_count,
                        updated=updated_count,
                        total_fetched=len(earnings)
                    )
                
            except Exception as e:
                logger.error("poll_loop_error", error=str(e))
                self.stats["errors"] += 1
            
            await asyncio.sleep(self.poll_interval)
    
    async def _full_sync_loop(self):
        """
        Periodic full sync to catch any missed updates.
        """
        # Wait before first full sync (already did one at start)
        await asyncio.sleep(self.full_sync_interval)
        
        while self._running:
            try:
                await self._full_sync()
            except Exception as e:
                logger.error("full_sync_loop_error", error=str(e))
                self.stats["errors"] += 1
            
            await asyncio.sleep(self.full_sync_interval)
    
    async def _full_sync(self):
        """
        Perform a full sync of earnings data.
        
        Fetches upcoming and recent earnings to ensure complete data.
        """
        logger.info("Starting full sync...")
        
        try:
            # Fetch upcoming earnings (next 14 days)
            upcoming = await self.client.fetch_upcoming_earnings(days=14)
            
            # Fetch recent earnings (past 7 days)
            recent = await self.client.fetch_recent_earnings(days=7)
            
            # Combine and dedupe
            all_earnings = {f"{e.ticker}-{e.date}": e for e in upcoming + recent}
            
            # Process all
            processed = 0
            for earning in all_earnings.values():
                await self._process_earning(earning, publish_stream=False)
                processed += 1
            
            # Rebuild today's cache
            await self._rebuild_today_cache()
            
            self.stats["full_syncs_completed"] += 1
            self.stats["last_full_sync_time"] = datetime.now().isoformat()
            
            logger.info(
                "Full sync completed",
                upcoming=len(upcoming),
                recent=len(recent),
                processed=processed
            )
            
        except Exception as e:
            logger.error("full_sync_error", error=str(e))
            self.stats["errors"] += 1
    
    async def _process_earning(
        self, 
        earning: BenzingaEarning,
        publish_stream: bool = True
    ) -> tuple[bool, bool]:
        """
        Process a single earnings record.
        
        Args:
            earning: Earnings record to process
            publish_stream: Whether to publish to stream
            
        Returns:
            Tuple of (is_new, was_updated)
        """
        try:
            key = f"{earning.ticker}-{earning.date}"
            
            # Check if exists and get previous version
            is_new = not await self._exists_in_dedup(key)
            was_updated = False
            
            if not is_new:
                # Check if data changed
                previous = await self._get_cached_earning(earning.ticker, earning.date)
                if previous:
                    was_updated = self._has_changes(previous, earning)
                    if not was_updated:
                        self.stats["duplicates_skipped"] += 1
                        return False, False
            
            # Mark as processed
            await self._add_to_dedup(key)
            
            # Cache in Redis
            await self._cache_earning(earning)
            
            # Persist to database
            if self.db_pool:
                await self._upsert_to_db(earning)
            
            # Publish to stream
            if publish_stream and (is_new or was_updated):
                await self._publish_to_stream(earning, is_new)
            
            self.stats["earnings_processed"] += 1
            if was_updated:
                self.stats["earnings_updated"] += 1
            
            return is_new, was_updated
            
        except Exception as e:
            logger.error("process_earning_error", error=str(e), ticker=earning.ticker)
            self.stats["errors"] += 1
            return False, False
    
    def _has_changes(self, previous: Dict, current: BenzingaEarning) -> bool:
        """Check if earnings data has meaningful changes."""
        # Key fields to check for changes
        check_fields = [
            ("actual_eps", current.actual_eps),
            ("actual_revenue", current.actual_revenue),
            ("eps_surprise_percent", current.eps_surprise_percent),
            ("revenue_surprise_percent", current.revenue_surprise_percent),
            ("date_status", current.date_status),
            ("time", current.time),
        ]
        
        for field, new_value in check_fields:
            old_value = previous.get(field)
            if old_value != new_value and new_value is not None:
                return True
        
        return False
    
    async def _exists_in_dedup(self, key: str) -> bool:
        """Check if key exists in dedup set."""
        return bool(await self.redis.sismember(self.DEDUP_SET_KEY, key))
    
    async def _add_to_dedup(self, key: str):
        """Add key to dedup set."""
        await self.redis.sadd(self.DEDUP_SET_KEY, key)
    
    async def _get_cached_earning(
        self, 
        ticker: str, 
        date: str
    ) -> Optional[Dict]:
        """Get cached earning by ticker and date."""
        try:
            key = f"{self.CACHE_BY_DATE_PREFIX}{date}"
            results = await self.redis.zrange(key, 0, -1)
            
            for result in results:
                data = json.loads(result)
                if data.get("ticker") == ticker:
                    return data
            
            return None
        except:
            return None
    
    async def _cache_earning(self, earning: BenzingaEarning):
        """Cache earning in Redis sorted sets."""
        try:
            data = earning.model_dump_json()
            score = datetime.now().timestamp()
            
            # Parse date for score
            try:
                dt = datetime.strptime(earning.date, "%Y-%m-%d")
                score = dt.timestamp()
            except:
                pass
            
            # Cache by date
            date_key = f"{self.CACHE_BY_DATE_PREFIX}{earning.date}"
            await self.redis.zadd(date_key, {data: score})
            await self.redis.zremrangebyrank(date_key, 0, -(self.CACHE_BY_DATE_SIZE + 1))
            await self.redis.expire(date_key, 86400 * 7)  # 7 days
            
            # Cache by ticker
            ticker_key = f"{self.CACHE_BY_TICKER_PREFIX}{earning.ticker}"
            await self.redis.zadd(ticker_key, {data: score})
            await self.redis.zremrangebyrank(ticker_key, 0, -(self.CACHE_BY_TICKER_SIZE + 1))
            await self.redis.expire(ticker_key, 86400 * 30)  # 30 days
            
            # Update today's cache if applicable
            today = datetime.now().strftime("%Y-%m-%d")
            if earning.date == today:
                await self.redis.zadd(self.CACHE_TODAY_KEY, {data: score})
                await self.redis.zremrangebyrank(
                    self.CACHE_TODAY_KEY, 0, -(self.CACHE_SIZE + 1)
                )
            
            # Update upcoming cache if future date
            # Use negative score so nearest dates have lowest rank and are
            # preserved when we trim the highest-rank (most distant) entries.
            if earning.date >= today:
                await self.redis.zadd(
                    self.CACHE_UPCOMING_KEY, {data: -score}
                )
                await self.redis.zremrangebyrank(
                    self.CACHE_UPCOMING_KEY, self.CACHE_SIZE, -1
                )
            
        except Exception as e:
            logger.error("cache_earning_error", error=str(e))
    
    async def _rebuild_today_cache(self):
        """Rebuild today's cache from by-date cache."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            date_key = f"{self.CACHE_BY_DATE_PREFIX}{today}"
            
            # Get all from today's date cache
            results = await self.redis.zrange(date_key, 0, -1, withscores=True)
            
            # Clear and rebuild today cache
            await self.redis.delete(self.CACHE_TODAY_KEY)
            
            if results:
                mapping = {data: score for data, score in results}
                await self.redis.zadd(self.CACHE_TODAY_KEY, mapping)
            
            logger.debug("today_cache_rebuilt", count=len(results))
            
        except Exception as e:
            logger.error("rebuild_today_cache_error", error=str(e))
    
    async def _upsert_to_db(self, earning: BenzingaEarning):
        """Upsert earning to TimescaleDB."""
        if not self.db_pool:
            return
        
        try:
            db_data = earning.to_db_dict()
            
            # Convert date string to date object for PostgreSQL
            from datetime import date as date_type
            report_date_str = db_data.get("report_date", "")
            if report_date_str and isinstance(report_date_str, str):
                try:
                    db_data["report_date"] = datetime.strptime(report_date_str, "%Y-%m-%d").date()
                except:
                    db_data["report_date"] = None
            
            query = """
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
            
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    query,
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
            
            self.stats["db_upserts"] += 1
            
        except Exception as e:
            logger.error("db_upsert_error", error=str(e), ticker=earning.ticker)
    
    async def _publish_to_stream(self, earning: BenzingaEarning, is_new: bool):
        """Publish earning update to Redis stream."""
        try:
            payload = {
                "type": "earning_update" if not is_new else "new_earning",
                "data": earning.model_dump_json(),
                "ticker": earning.ticker,
                "date": earning.date,
                "timestamp": datetime.now().isoformat()
            }
            
            await self.redis.xadd(
                self.STREAM_KEY,
                payload,
                maxlen=self.STREAM_MAXLEN
            )
            
            self.stats["stream_publishes"] += 1
            
            logger.debug(
                "earning_published",
                ticker=earning.ticker,
                date=earning.date,
                is_new=is_new
            )
            
        except Exception as e:
            logger.error("publish_to_stream_error", error=str(e))
    
    async def _get_last_update_time(self) -> Optional[str]:
        """Get last update timestamp."""
        result = await self.redis.get(self.LAST_UPDATE_KEY)
        return result if result else None
    
    async def _set_last_update_time(self, timestamp: str):
        """Set last update timestamp."""
        await self.redis.set(self.LAST_UPDATE_KEY, timestamp)
    
    # =========================================================================
    # Public API methods for HTTP endpoints
    # =========================================================================
    
    async def get_today_earnings(self) -> List[Dict[str, Any]]:
        """Get today's earnings from cache."""
        try:
            results = await self.redis.zrevrange(self.CACHE_TODAY_KEY, 0, -1)
            return [json.loads(r) for r in results]
        except Exception as e:
            logger.error("get_today_earnings_error", error=str(e))
            return []
    
    async def get_upcoming_earnings(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get upcoming earnings from cache."""
        try:
            results = await self.redis.zrange(
                self.CACHE_UPCOMING_KEY, 0, limit - 1
            )
            return [json.loads(r) for r in results]
        except Exception as e:
            logger.error("get_upcoming_earnings_error", error=str(e))
            return []
    
    async def get_earnings_by_date(
        self, 
        date: str, 
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """Get earnings for a specific date."""
        try:
            key = f"{self.CACHE_BY_DATE_PREFIX}{date}"
            results = await self.redis.zrevrange(key, 0, limit - 1)
            return [json.loads(r) for r in results]
        except Exception as e:
            logger.error("get_earnings_by_date_error", error=str(e), date=date)
            return []
    
    async def get_earnings_by_ticker(
        self, 
        ticker: str, 
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get earnings history for a ticker."""
        try:
            key = f"{self.CACHE_BY_TICKER_PREFIX}{ticker.upper()}"
            results = await self.redis.zrevrange(key, 0, limit - 1)
            return [json.loads(r) for r in results]
        except Exception as e:
            logger.error("get_earnings_by_ticker_error", error=str(e), ticker=ticker)
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get stream manager statistics."""
        return {
            "manager": self.stats,
            "client": self.client.get_stats()
        }
