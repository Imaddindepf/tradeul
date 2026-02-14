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
from detectors.macd_events import MACDEventsDetector
from detectors.stochastic_events import StochasticEventsDetector
from detectors.orb_events import ORBEventsDetector
from detectors.consolidation_events import ConsolidationEventsDetector
from detectors.confirmed_cross_events import ConfirmedCrossEventsDetector
from detectors.session_events import SessionEventsDetector

# All detector plugin classes - the engine instantiates each one
ALL_DETECTOR_CLASSES = [
    # Phase 1 — Live (tick-based)
    PriceEventsDetector,
    VWAPEventsDetector,
    VolumeEventsDetector,
    MomentumEventsDetector,
    PullbackEventsDetector,         # Includes open/close variants
    GapEventsDetector,
    # Phase 1B — Snapshot + BarEngine indicators
    MACrossEventsDetector,          # SMA + EMA + Daily SMA200 crosses
    BollingerEventsDetector,
    DailyLevelEventsDetector,
    MACDEventsDetector,
    StochasticEventsDetector,
    ORBEventsDetector,
    ConsolidationEventsDetector,
    # Phase 2 — Confirmed crosses + Session-aware
    ConfirmedCrossEventsDetector,   # CAOC/CBOC/CACC/CBCC (30s confirmation)
    SessionEventsDetector,          # HPRE/LPRE/HPOST/LPOST
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
    "MACDEventsDetector",
    "StochasticEventsDetector",
    "ORBEventsDetector",
    "ConsolidationEventsDetector",
    "ConfirmedCrossEventsDetector",
    "SessionEventsDetector",
    "ALL_DETECTOR_CLASSES",
]
