"""
VWAP Consumer - Maintains VWAP cache from WebSocket per-second aggregates.

Reads field 'a' (Today's VWAP) from stream:realtime:aggregates.
If VWAP is 0 or missing, keeps the last known value (prevents VWAP "disappearing").

Only covers ~643 subscribed tickers (scanner-selected).
Fallback: enrichment pipeline uses day.vw from REST snapshot for unsubscribed tickers.
"""

import asyncio
from datetime import datetime
from typing import Dict

from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)

STREAM_NAME = "stream:realtime:aggregates"
CONSUMER_GROUP = "analytics_vwap_consumer"
CONSUMER_NAME = "analytics_vwap_1"


class VwapConsumer:
    """
    Consumes per-second aggregates to maintain an in-memory VWAP cache.
    The cache is shared with the enrichment pipeline via reference.
    """
    
    def __init__(self, redis_client: RedisClient, vwap_cache: Dict[str, float]):
        self.redis = redis_client
        self.vwap_cache = vwap_cache  # Shared dict reference
    
    async def run(self) -> None:
        """Main consumer loop."""
        logger.info("vwap_consumer_started", stream=STREAM_NAME)
        
        # Create consumer group
        try:
            await self.redis.create_consumer_group(
                STREAM_NAME, CONSUMER_GROUP, mkstream=True
            )
            logger.info("vwap_consumer_group_created", group=CONSUMER_GROUP)
        except Exception as e:
            logger.debug("vwap_consumer_group_exists", error=str(e))
        
        while True:
            try:
                messages = await self.redis.read_stream(
                    stream_name=STREAM_NAME,
                    consumer_group=CONSUMER_GROUP,
                    consumer_name=CONSUMER_NAME,
                    count=500,
                    block=1000
                )
                
                if messages:
                    message_ids_to_ack = []
                    vwap_updates = 0
                    
                    for stream, stream_messages in messages:
                        for message_id, data in stream_messages:
                            symbol = data.get('symbol')
                            vwap_str = data.get('vwap')
                            
                            if symbol and vwap_str:
                                try:
                                    vwap = float(vwap_str)
                                    if vwap > 0:
                                        self.vwap_cache[symbol] = vwap
                                        vwap_updates += 1
                                except (ValueError, TypeError):
                                    pass
                            
                            message_ids_to_ack.append(message_id)
                    
                    if message_ids_to_ack:
                        try:
                            await self.redis.xack(
                                STREAM_NAME, CONSUMER_GROUP, *message_ids_to_ack
                            )
                        except Exception as e:
                            logger.error("vwap_xack_error", error=str(e))
                    
                    if vwap_updates > 0:
                        logger.debug(
                            "vwap_cache_updated",
                            updates=vwap_updates,
                            cache_size=len(self.vwap_cache)
                        )
            
            except asyncio.CancelledError:
                logger.info("vwap_consumer_cancelled")
                raise
            except Exception as e:
                if 'NOGROUP' in str(e):
                    logger.warn("vwap_consumer_group_missing_recreating")
                    try:
                        await self.redis.create_consumer_group(
                            STREAM_NAME, CONSUMER_GROUP, start_id="0", mkstream=True
                        )
                        continue
                    except Exception:
                        pass
                logger.error("vwap_consumer_error", error=str(e))
                await asyncio.sleep(1)
