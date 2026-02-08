"""
Pytest configuration and fixtures for Event Detector tests.
"""

import pytest
from datetime import datetime
from typing import List

from models import (
    EventRecord,
    EventType,
    TickerState,
    TickerStateCache,
)
from detectors import (
    PriceEventsDetector,
    VWAPEventsDetector,
    VolumeEventsDetector,
    MomentumEventsDetector,
    PullbackEventsDetector,
    GapEventsDetector,
    ALL_DETECTOR_CLASSES,
)


@pytest.fixture
def sample_ticker_state() -> TickerState:
    """Create a sample ticker state for testing."""
    return TickerState(
        symbol="TSLA",
        price=250.50,
        volume=1_500_000,
        timestamp=datetime.utcnow(),
        vwap=248.00,
        intraday_high=252.00,
        intraday_low=245.00,
        prev_close=240.00,
        open_price=242.00,
        rvol=2.5,
        change_percent=4.37,
        market_cap=800_000_000_000,
    )


@pytest.fixture
def low_volume_state() -> TickerState:
    """Create a low volume ticker state."""
    return TickerState(
        symbol="LOWVOL",
        price=10.00,
        volume=5000,  # Below 10k threshold
        timestamp=datetime.utcnow(),
        vwap=9.50,
        intraday_high=10.50,
        intraday_low=9.00,
        rvol=1.0,
    )


@pytest.fixture
def state_cache() -> TickerStateCache:
    """Create a fresh state cache."""
    return TickerStateCache(max_age_seconds=3600)


@pytest.fixture
def price_detector() -> PriceEventsDetector:
    return PriceEventsDetector()


@pytest.fixture
def vwap_detector() -> VWAPEventsDetector:
    return VWAPEventsDetector()


@pytest.fixture
def volume_detector() -> VolumeEventsDetector:
    return VolumeEventsDetector()


@pytest.fixture
def momentum_detector() -> MomentumEventsDetector:
    return MomentumEventsDetector()


@pytest.fixture
def pullback_detector() -> PullbackEventsDetector:
    return PullbackEventsDetector()


@pytest.fixture
def gap_detector() -> GapEventsDetector:
    return GapEventsDetector()
