"""
Volume Window Consumer - Feeds VolumeWindowTracker from WebSocket aggregates.

Reads 'volume_accumulated' (av) from stream:realtime:aggregates.
Uses aggregate timestamp (not datetime.now()) for accurate window calculations.

Formula: vol_5min = av[now] - av[5 min ago]

Only covers ~643 subscribed tickers.
"""

import asyncio
from datetime import datetime

from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from volume_window_tracker import VolumeWindowTracker

logger = get_logger(__name__)

STREAM_NAME = "stream:realtime:aggregates"
CONSUMER_GROUP = "analytics_volume_window_consumer"
CONSUMER_NAME = "analytics_volume_window_1"


class VolumeWindowConsumer:
    """Consumes aggregates to feed VolumeWindowTracker."""
    
    def __init__(
        self,
        redis_client: RedisClient,
        tracker: VolumeWindowTracker,
        is_holiday_check=None
    ):
        self.redis = redis_client
        self.tracker = tracker
        self._is_holiday_check = is_holiday_check or (lambda: False)
        self._update_count = 0
        self._last_stats_log = datetime.now()
    
    async def run(self) -> None:
        """Main consumer loop."""
        logger.info("volume_window_consumer_started", stream=STREAM_NAME)
        
        try:
            await self.redis.create_consumer_group(
                STREAM_NAME, CONSUMER_GROUP, mkstream=True
            )
        except Exception as e:
            logger.debug("volume_window_consumer_group_exists", error=str(e))
        
        while True:
            try:
                if self._is_holiday_check():
                    await asyncio.sleep(30)
                    continue
                
                messages = await self.redis.read_stream(
                    stream_name=STREAM_NAME,
                    consumer_group=CONSUMER_GROUP,
                    consumer_name=CONSUMER_NAME,
                    count=500,
                    block=1000
                )
                
                if messages:
                    message_ids_to_ack = []
                    batch_updates = 0
                    
                    for stream, stream_messages in messages:
                        for message_id, data in stream_messages:
                            symbol = data.get('symbol')
                            av_str = data.get('volume_accumulated') or data.get('av')
                            ts_end_str = data.get('timestamp_end')
                            
                            if symbol and av_str:
                                try:
                                    av = int(float(av_str))
                                    agg_ts = (
                                        int(int(ts_end_str) / 1000) if ts_end_str
                                        else int(datetime.now().timestamp())
                                    )
                                    if av > 0:
                                        self.tracker.update(symbol, av, agg_ts)
                                        batch_updates += 1
                                except (ValueError, TypeError):
                                    pass
                            
                            message_ids_to_ack.append(message_id)
                    
                    if message_ids_to_ack:
                        try:
                            await self.redis.xack(
                                STREAM_NAME, CONSUMER_GROUP, *message_ids_to_ack
                            )
                        except Exception as e:
                            logger.error("volume_window_xack_error", error=str(e))
                    
                    self._update_count += batch_updates
                    self._log_stats_periodically()
            
            except asyncio.CancelledError:
                logger.info("volume_window_consumer_cancelled")
                raise
            except Exception as e:
                if 'NOGROUP' in str(e):
                    try:
                        await self.redis.create_consumer_group(
                            STREAM_NAME, CONSUMER_GROUP, start_id="0", mkstream=True
                        )
                        continue
                    except Exception:
                        pass
                logger.error("volume_window_consumer_error", error=str(e))
                await asyncio.sleep(1)
    
    def _log_stats_periodically(self):
        """Log stats every 30 seconds."""
        now = datetime.now()
        if (now - self._last_stats_log).total_seconds() >= 30:
            stats = self.tracker.get_stats()
            logger.info(
                "volume_window_tracker_stats",
                updates_since_last=self._update_count,
                symbols_active=stats["symbols_active"],
                memory_mb=stats["memory_mb"]
            )
            self._update_count = 0
            self._last_stats_log = now
