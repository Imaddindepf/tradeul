"""
Sync Tier 1 Job
Sincronizar tickers de Tier 1 (diariamente)
"""

import sys
sys.path.append('/app')

import asyncio
from typing import List

from shared.utils.timescale_client import TimescaleClient
from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from shared.config.settings import get_settings

from ..strategies.tier_manager import TierManager
from ..services.fmp_financials import FMPFinancialsService
from ..services.fmp_holders import FMPHoldersService
from ..services.fmp_filings import FMPFilingsService
from ..models.sync_models import SyncTier

logger = get_logger(__name__)
settings = get_settings()


class SyncTier1Job:
    """
    Job para sincronizar tickers de Tier 1 (top 500)
    Se ejecuta diariamente
    """
    
    def __init__(self):
        self.name = "sync_tier1"
        self.fmp_api_key = settings.FMP_API_KEY
    
    async def run(self):
        """Ejecutar sincronización de Tier 1"""
        logger.info("tier1_sync_started")
        
        try:
            # Get clients
            db = await TimescaleClient.get_instance()
            redis = await RedisClient.get_instance()
            
            # Get tier manager
            tier_manager = TierManager(db, redis)
            
            # Get Tier 1 tickers
            tier1_tickers = await tier_manager.get_tickers_by_tier(SyncTier.TIER_1)
            
            logger.info("tier1_tickers_fetched", count=len(tier1_tickers))
            
            if not tier1_tickers:
                logger.warning("no_tier1_tickers_found")
                return
            
            # Sync each ticker
            synced_count = 0
            failed_count = 0
            
            for ticker in tier1_tickers:
                try:
                    await self._sync_ticker(ticker)
                    synced_count += 1
                    
                    # Rate limiting: sleep 0.5s between requests
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error("ticker_sync_failed", ticker=ticker, error=str(e))
                    failed_count += 1
                    continue
            
            logger.info(
                "tier1_sync_completed",
                synced=synced_count,
                failed=failed_count,
                total=len(tier1_tickers)
            )
            
        except Exception as e:
            logger.error("tier1_sync_job_failed", error=str(e))
    
    async def _sync_ticker(self, ticker: str):
        """Sincronizar un ticker individual"""
        logger.debug("syncing_ticker", ticker=ticker)
        
        # Initialize services
        financials_service = FMPFinancialsService(self.fmp_api_key)
        holders_service = FMPHoldersService(self.fmp_api_key)
        filings_service = FMPFilingsService(self.fmp_api_key)
        
        # 1. Fetch financials
        financials = await financials_service.get_financial_statements(
            ticker,
            period="quarter",
            limit=20
        )
        
        if financials:
            # TODO: Save to DB
            logger.debug("financials_fetched", ticker=ticker, count=len(financials))
        
        # 2. Fetch holders
        holders = await holders_service.get_institutional_holders(ticker)
        
        if holders:
            # TODO: Save to DB
            logger.debug("holders_fetched", ticker=ticker, count=len(holders))
        
        # 3. Fetch filings
        filings = await filings_service.get_sec_filings(ticker, limit=50)
        
        if filings:
            # TODO: Save to DB
            logger.debug("filings_fetched", ticker=ticker, count=len(filings))
        
        # 4. Update sync config
        db = await TimescaleClient.get_instance()
        await db.execute("""
            UPDATE ticker_sync_config
            SET last_synced_at = NOW(),
                sync_count = sync_count + 1,
                updated_at = NOW()
            WHERE ticker = $1
        """, ticker)
        
        logger.debug("ticker_synced", ticker=ticker)


async def main():
    """Entry point for job"""
    job = SyncTier1Job()
    await job.run()


if __name__ == "__main__":
    asyncio.run(main())

