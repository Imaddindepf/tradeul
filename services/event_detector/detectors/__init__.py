"""
Event Detector Plugins Registry.

All detector plugins are imported here and exposed via ALL_DETECTORS.
The engine loads all detectors from this list at startup.
"""

from detectors.base import BaseEventDetector, CooldownTracker
from detectors.price_events import PriceEventsDetector
from detectors.vwap_events import VWAPEventsDetector
from detectors.volume_events import VolumeEventsDetector
from detectors.momentum_events import MomentumEventsDetector
from detectors.pullback_events import PullbackEventsDetector
from detectors.gap_events import GapEventsDetector
from detectors.ma_cross_events import MACrossEventsDetector
from detectors.bollinger_events import BollingerEventsDetector
from detectors.daily_level_events import DailyLevelEventsDetector

# All detector plugin classes - the engine instantiates each one
ALL_DETECTOR_CLASSES = [
    # Phase 1 — Live (tick-based)
    PriceEventsDetector,
    VWAPEventsDetector,
    VolumeEventsDetector,
    MomentumEventsDetector,
    PullbackEventsDetector,
    GapEventsDetector,
    # Phase 2 — Daily indicators + confirmed crosses
    MACrossEventsDetector,
    BollingerEventsDetector,
    DailyLevelEventsDetector,
]

__all__ = [
    "BaseEventDetector",
    "CooldownTracker",
    "PriceEventsDetector",
    "VWAPEventsDetector",
    "VolumeEventsDetector",
    "MomentumEventsDetector",
    "PullbackEventsDetector",
    "GapEventsDetector",
    "MACrossEventsDetector",
    "BollingerEventsDetector",
    "DailyLevelEventsDetector",
    "ALL_DETECTOR_CLASSES",
]
