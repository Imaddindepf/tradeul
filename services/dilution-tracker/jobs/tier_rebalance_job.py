"""
Tier Rebalance Job
Rebalancea tickers entre tiers basado en popularidad
Se ejecuta semanalmente
"""

import sys
sys.path.append('/app')

import asyncio

from shared.utils.timescale_client import TimescaleClient
from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger

from ..strategies.tier_manager import TierManager

logger = get_logger(__name__)


class TierRebalanceJob:
    """
    Job para rebalancear tiers semanalmente
    """
    
    def __init__(self):
        self.name = "tier_rebalance"
    
    async def run(self):
        """Ejecutar rebalanceo de tiers"""
        logger.info("tier_rebalance_started")
        
        try:
            # Get clients
            db = await TimescaleClient.get_instance()
            redis = await RedisClient.get_instance()
            
            # Get tier manager
            tier_manager = TierManager(db, redis)
            
            # Reclassify all tickers
            counts = await tier_manager.classify_all_tickers()
            
            logger.info(
                "tier_rebalance_completed",
                tier1=counts['tier_1'],
                tier2=counts['tier_2'],
                tier3=counts['tier_3'],
                total=counts['total']
            )
            
        except Exception as e:
            logger.error("tier_rebalance_failed", error=str(e))


async def main():
    """Entry point for job"""
    job = TierRebalanceJob()
    await job.run()


if __name__ == "__main__":
    asyncio.run(main())

