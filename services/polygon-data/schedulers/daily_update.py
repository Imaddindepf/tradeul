"""
Daily Update Scheduler
Automatically downloads new data each day
"""

from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import structlog

from config import settings
from downloaders import MinuteAggsDownloader, DayAggsDownloader

logger = structlog.get_logger(__name__)


class DailyUpdateScheduler:
    """
    Schedules daily data updates after market close
    """
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.minute_downloader = MinuteAggsDownloader()
        self.day_downloader = DayAggsDownloader()
        
        self._running = False
    
    def start(self):
        """Start the scheduler"""
        if self._running:
            return
        
        # Schedule daily update (6 AM UTC = 1 AM EST after market close)
        self.scheduler.add_job(
            self._daily_update,
            CronTrigger(
                hour=settings.daily_update_hour,
                minute=settings.daily_update_minute
            ),
            id="daily_update",
            name="Daily Polygon Data Update",
            replace_existing=True
        )
        
        self.scheduler.start()
        self._running = True
        
        logger.info(
            "Scheduler started",
            update_time=f"{settings.daily_update_hour:02d}:{settings.daily_update_minute:02d} UTC"
        )
    
    def stop(self):
        """Stop the scheduler"""
        if self._running:
            self.scheduler.shutdown()
            self._running = False
            logger.info("Scheduler stopped")
    
    async def _daily_update(self):
        """Run daily update job"""
        logger.info("Starting daily update")
        
        # Download yesterday's data (today's data not available yet)
        yesterday = datetime.now() - timedelta(days=1)
        
        # Skip weekends
        if yesterday.weekday() >= 5:
            logger.info("Skipping weekend", date=yesterday.strftime("%Y-%m-%d"))
            return
        
        try:
            # Download minute aggs
            minute_result = self.minute_downloader.download_date(yesterday)
            if minute_result:
                logger.info("Minute aggs downloaded", date=yesterday.strftime("%Y-%m-%d"))
            
            # Download day aggs
            day_result = self.day_downloader.download_date(yesterday)
            if day_result:
                logger.info("Day aggs downloaded", date=yesterday.strftime("%Y-%m-%d"))
            
        except Exception as e:
            logger.error("Daily update failed", error=str(e))
    
    def run_now(self):
        """Trigger immediate update"""
        import asyncio
        asyncio.create_task(self._daily_update())
    
    def get_next_run(self) -> str:
        """Get next scheduled run time"""
        job = self.scheduler.get_job("daily_update")
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        return None

