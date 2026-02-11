"""
Stream Consumers - Read from Redis Streams to feed in-memory trackers.

Each consumer reads from its Redis stream with its own consumer group,
extracting only the fields it needs.

Consumers:
- vwap_consumer: Maintains VWAP cache from WebSocket aggregates (A.*)
- volume_window_consumer: Feeds VolumeWindowTracker with accumulated volume (A.*)
- price_window_consumer: Feeds PriceWindowTracker with close prices (A.*)
- minute_bar_consumer: Feeds BarEngine with 1-minute bars (AM.*, entire market)
"""

from .vwap_consumer import VwapConsumer
from .volume_window_consumer import VolumeWindowConsumer
from .price_window_consumer import PriceWindowConsumer
from .minute_bar_consumer import MinuteBarConsumer

__all__ = ["VwapConsumer", "VolumeWindowConsumer", "PriceWindowConsumer", "MinuteBarConsumer"]
