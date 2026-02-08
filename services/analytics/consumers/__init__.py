"""
Stream Consumers - Read from stream:realtime:aggregates to feed in-memory trackers.

Each consumer reads from the same Redis stream but with its own consumer group,
extracting only the fields it needs.

Consumers:
- vwap_consumer: Maintains VWAP cache from WebSocket aggregates
- volume_window_consumer: Feeds VolumeWindowTracker with accumulated volume
- price_window_consumer: Feeds PriceWindowTracker with close prices
"""

from .vwap_consumer import VwapConsumer
from .volume_window_consumer import VolumeWindowConsumer
from .price_window_consumer import PriceWindowConsumer

__all__ = ["VwapConsumer", "VolumeWindowConsumer", "PriceWindowConsumer"]
