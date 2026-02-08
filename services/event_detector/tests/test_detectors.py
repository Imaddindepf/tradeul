"""
Tests for all event detector plugins.

Tests each detector independently with controlled TickerState inputs.
"""

import pytest
from datetime import datetime
from models import EventType, TickerState
from detectors.price_events import PriceEventsDetector
from detectors.vwap_events import VWAPEventsDetector
from detectors.volume_events import VolumeEventsDetector
from detectors.momentum_events import MomentumEventsDetector
from detectors.pullback_events import PullbackEventsDetector
from detectors.gap_events import GapEventsDetector


def make_state(
    symbol="TEST",
    price=100.0,
    volume=500_000,
    **kwargs
) -> TickerState:
    """Helper to create TickerState with defaults."""
    return TickerState(
        symbol=symbol,
        timestamp=datetime.utcnow(),
        price=price,
        volume=volume,
        **kwargs,
    )


# ============================================================================
# PRICE EVENTS
# ============================================================================

class TestPriceEvents:
    def setup_method(self):
        self.detector = PriceEventsDetector()
    
    def test_new_high_detected(self):
        prev = make_state(price=100.0, intraday_high=100.0, intraday_low=95.0)
        self.detector.detect(prev, None)  # init tracking
        
        curr = make_state(price=101.0, intraday_high=101.0, intraday_low=95.0)
        events = self.detector.detect(curr, prev)
        
        assert len(events) == 1
        assert events[0].event_type == EventType.NEW_HIGH
        assert events[0].symbol == "TEST"
    
    def test_new_low_detected(self):
        prev = make_state(price=100.0, intraday_high=105.0, intraday_low=100.0)
        self.detector.detect(prev, None)  # init
        
        curr = make_state(price=99.0, intraday_high=105.0, intraday_low=99.0)
        events = self.detector.detect(curr, prev)
        
        assert len(events) == 1
        assert events[0].event_type == EventType.NEW_LOW
    
    def test_no_event_if_same_price(self):
        prev = make_state(price=100.0, intraday_high=100.0, intraday_low=95.0)
        self.detector.detect(prev, None)
        
        curr = make_state(price=100.0, intraday_high=100.0, intraday_low=95.0)
        events = self.detector.detect(curr, prev)
        
        assert len(events) == 0
    
    def test_crossed_above_open(self):
        prev = make_state(price=99.0, open_price=100.0)
        curr = make_state(price=101.0, open_price=100.0)
        
        self.detector.detect(prev, None)  # init
        events = self.detector.detect(curr, prev)
        
        assert any(e.event_type == EventType.CROSSED_ABOVE_OPEN for e in events)
    
    def test_crossed_below_open(self):
        prev = make_state(price=101.0, open_price=100.0)
        curr = make_state(price=99.0, open_price=100.0)
        
        self.detector.detect(prev, None)
        events = self.detector.detect(curr, prev)
        
        assert any(e.event_type == EventType.CROSSED_BELOW_OPEN for e in events)
    
    def test_crossed_above_prev_close(self):
        prev = make_state(price=99.0, prev_close=100.0)
        curr = make_state(price=101.0, prev_close=100.0)
        
        self.detector.detect(prev, None)
        events = self.detector.detect(curr, prev)
        
        assert any(e.event_type == EventType.CROSSED_ABOVE_PREV_CLOSE for e in events)
    
    def test_crossed_below_prev_close(self):
        prev = make_state(price=101.0, prev_close=100.0)
        curr = make_state(price=99.0, prev_close=100.0)
        
        self.detector.detect(prev, None)
        events = self.detector.detect(curr, prev)
        
        assert any(e.event_type == EventType.CROSSED_BELOW_PREV_CLOSE for e in events)
    
    def test_low_volume_ignored(self):
        prev = make_state(price=100.0, volume=5_000, intraday_high=100.0, intraday_low=95.0)
        self.detector.detect(prev, None)
        
        curr = make_state(price=101.0, volume=5_000, intraday_high=101.0, intraday_low=95.0)
        events = self.detector.detect(curr, prev)
        
        assert len(events) == 0  # Filtered by MIN_VOLUME


# ============================================================================
# VWAP EVENTS
# ============================================================================

class TestVWAPEvents:
    def setup_method(self):
        self.detector = VWAPEventsDetector()
    
    def test_vwap_cross_up(self):
        prev = make_state(price=99.0, vwap=100.0)
        curr = make_state(price=101.0, vwap=100.0)
        
        events = self.detector.detect(curr, prev)
        
        assert len(events) == 1
        assert events[0].event_type == EventType.VWAP_CROSS_UP
    
    def test_vwap_cross_down(self):
        prev = make_state(price=101.0, vwap=100.0)
        curr = make_state(price=99.0, vwap=100.0)
        
        events = self.detector.detect(curr, prev)
        
        assert len(events) == 1
        assert events[0].event_type == EventType.VWAP_CROSS_DOWN
    
    def test_no_cross_same_side(self):
        prev = make_state(price=101.0, vwap=100.0)
        curr = make_state(price=102.0, vwap=100.0)
        
        events = self.detector.detect(curr, prev)
        assert len(events) == 0
    
    def test_no_vwap_no_event(self):
        prev = make_state(price=99.0, vwap=None)
        curr = make_state(price=101.0, vwap=None)
        
        events = self.detector.detect(curr, prev)
        assert len(events) == 0


# ============================================================================
# VOLUME EVENTS
# ============================================================================

class TestVolumeEvents:
    def setup_method(self):
        self.detector = VolumeEventsDetector()
    
    def test_rvol_spike(self):
        prev = make_state(price=100.0, volume=100_000, rvol=2.5)
        curr = make_state(price=100.0, volume=100_000, rvol=3.5)
        
        events = self.detector.detect(curr, prev)
        
        assert len(events) == 1
        assert events[0].event_type == EventType.RVOL_SPIKE
    
    def test_volume_surge(self):
        prev = make_state(price=100.0, volume=200_000, rvol=4.5)
        curr = make_state(price=100.0, volume=200_000, rvol=5.5)
        
        events = self.detector.detect(curr, prev)
        
        assert len(events) == 1
        assert events[0].event_type == EventType.VOLUME_SURGE
    
    def test_rvol_spike_and_surge_at_same_time(self):
        prev = make_state(price=100.0, volume=200_000, rvol=2.5)
        curr = make_state(price=100.0, volume=200_000, rvol=5.5)
        
        events = self.detector.detect(curr, prev)
        
        types = {e.event_type for e in events}
        assert EventType.RVOL_SPIKE in types
        assert EventType.VOLUME_SURGE in types
    
    def test_block_trade(self):
        prev = make_state(price=100.0, minute_volume=10_000)
        curr = make_state(price=100.0, minute_volume=60_000)
        
        events = self.detector.detect(curr, prev)
        
        assert any(e.event_type == EventType.BLOCK_TRADE for e in events)
    
    def test_unusual_prints(self):
        prev = make_state(price=100.0, trades_z_score=2.5)
        curr = make_state(price=100.0, trades_z_score=3.5)
        
        events = self.detector.detect(curr, prev)
        
        assert any(e.event_type == EventType.UNUSUAL_PRINTS for e in events)


# ============================================================================
# MOMENTUM EVENTS
# ============================================================================

class TestMomentumEvents:
    def setup_method(self):
        self.detector = MomentumEventsDetector()
    
    def test_running_up(self):
        prev = make_state(price=100.0, chg_5min=1.5)
        curr = make_state(price=102.0, chg_5min=2.5)
        
        events = self.detector.detect(curr, prev)
        
        assert len(events) == 1
        assert events[0].event_type == EventType.RUNNING_UP
    
    def test_running_down(self):
        prev = make_state(price=100.0, chg_5min=-1.5)
        curr = make_state(price=98.0, chg_5min=-2.5)
        
        events = self.detector.detect(curr, prev)
        
        assert len(events) == 1
        assert events[0].event_type == EventType.RUNNING_DOWN
    
    def test_percent_up_5(self):
        prev = make_state(price=104.0, change_percent=4.5)
        curr = make_state(price=106.0, change_percent=5.5)
        
        events = self.detector.detect(curr, prev)
        
        assert any(e.event_type == EventType.PERCENT_UP_5 for e in events)
    
    def test_percent_down_5(self):
        prev = make_state(price=96.0, change_percent=-4.5)
        curr = make_state(price=94.0, change_percent=-5.5)
        
        events = self.detector.detect(curr, prev)
        
        assert any(e.event_type == EventType.PERCENT_DOWN_5 for e in events)
    
    def test_percent_up_10(self):
        prev = make_state(price=109.0, change_percent=9.5)
        curr = make_state(price=111.0, change_percent=10.5)
        
        events = self.detector.detect(curr, prev)
        
        assert any(e.event_type == EventType.PERCENT_UP_10 for e in events)
    
    def test_percent_down_10(self):
        prev = make_state(price=91.0, change_percent=-9.5)
        curr = make_state(price=89.0, change_percent=-10.5)
        
        events = self.detector.detect(curr, prev)
        
        assert any(e.event_type == EventType.PERCENT_DOWN_10 for e in events)


# ============================================================================
# PULLBACK EVENTS
# ============================================================================

class TestPullbackEvents:
    def setup_method(self):
        self.detector = PullbackEventsDetector()
    
    def test_pullback_25_from_high(self):
        # Range 90-100 = 10. 25% pullback level = 100 - 2.5 = 97.5
        prev = make_state(price=98.0, intraday_high=100.0, intraday_low=90.0)
        curr = make_state(price=97.0, intraday_high=100.0, intraday_low=90.0)
        
        events = self.detector.detect(curr, prev)
        
        assert any(e.event_type == EventType.PULLBACK_25_FROM_HIGH for e in events)
    
    def test_pullback_75_from_high(self):
        # Range 90-100 = 10. 75% pullback level = 100 - 7.5 = 92.5
        prev = make_state(price=93.0, intraday_high=100.0, intraday_low=90.0)
        curr = make_state(price=92.0, intraday_high=100.0, intraday_low=90.0)
        
        events = self.detector.detect(curr, prev)
        
        assert any(e.event_type == EventType.PULLBACK_75_FROM_HIGH for e in events)
    
    def test_pullback_25_from_low(self):
        # Range 90-100 = 10. 25% bounce level = 90 + 2.5 = 92.5
        prev = make_state(price=92.0, intraday_high=100.0, intraday_low=90.0)
        curr = make_state(price=93.0, intraday_high=100.0, intraday_low=90.0)
        
        events = self.detector.detect(curr, prev)
        
        assert any(e.event_type == EventType.PULLBACK_25_FROM_LOW for e in events)
    
    def test_pullback_75_from_low(self):
        # Range 90-100 = 10. 75% bounce level = 90 + 7.5 = 97.5
        prev = make_state(price=97.0, intraday_high=100.0, intraday_low=90.0)
        curr = make_state(price=98.0, intraday_high=100.0, intraday_low=90.0)
        
        events = self.detector.detect(curr, prev)
        
        assert any(e.event_type == EventType.PULLBACK_75_FROM_LOW for e in events)
    
    def test_no_pullback_small_range(self):
        # Range too small (< 1%)
        prev = make_state(price=100.0, intraday_high=100.2, intraday_low=99.8)
        curr = make_state(price=99.9, intraday_high=100.2, intraday_low=99.8)
        
        events = self.detector.detect(curr, prev)
        assert len(events) == 0


# ============================================================================
# GAP EVENTS
# ============================================================================

class TestGapEvents:
    def setup_method(self):
        self.detector = GapEventsDetector()
    
    def test_gap_up_reversal(self):
        # Gapped up 3%: open=103, prev_close=100
        # Now price falls below open
        prev = make_state(price=103.5, open_price=103.0, prev_close=100.0)
        curr = make_state(price=102.0, open_price=103.0, prev_close=100.0)
        
        events = self.detector.detect(curr, prev)
        
        assert len(events) == 1
        assert events[0].event_type == EventType.GAP_UP_REVERSAL
    
    def test_gap_down_reversal(self):
        # Gapped down 3%: open=97, prev_close=100
        # Now price rises above open
        prev = make_state(price=96.5, open_price=97.0, prev_close=100.0)
        curr = make_state(price=98.0, open_price=97.0, prev_close=100.0)
        
        events = self.detector.detect(curr, prev)
        
        assert len(events) == 1
        assert events[0].event_type == EventType.GAP_DOWN_REVERSAL
    
    def test_no_reversal_small_gap(self):
        # Gap only 1% - below threshold
        prev = make_state(price=101.5, open_price=101.0, prev_close=100.0)
        curr = make_state(price=100.5, open_price=101.0, prev_close=100.0)
        
        events = self.detector.detect(curr, prev)
        assert len(events) == 0
    
    def test_no_reversal_still_above_open(self):
        # Gap up 3% but price still above open
        prev = make_state(price=104.0, open_price=103.0, prev_close=100.0)
        curr = make_state(price=103.5, open_price=103.0, prev_close=100.0)
        
        events = self.detector.detect(curr, prev)
        assert len(events) == 0


# ============================================================================
# COOLDOWN TESTS
# ============================================================================

class TestCooldowns:
    def test_price_detector_cooldown(self):
        detector = PriceEventsDetector()
        
        # First detection
        prev = make_state(price=100.0, intraday_high=100.0, intraday_low=95.0)
        detector.detect(prev, None)
        
        curr1 = make_state(price=101.0, intraday_high=101.0, intraday_low=95.0)
        events1 = detector.detect(curr1, prev)
        assert len(events1) == 1  # First fire
        
        # Second detection immediately - should be cooled down
        curr2 = make_state(price=101.5, intraday_high=101.5, intraday_low=95.0)
        events2 = detector.detect(curr2, curr1)
        assert len(events2) == 0  # Cooldown active
    
    def test_vwap_detector_cooldown(self):
        detector = VWAPEventsDetector()
        
        prev = make_state(price=99.0, vwap=100.0)
        curr = make_state(price=101.0, vwap=100.0)
        
        events1 = detector.detect(curr, prev)
        assert len(events1) == 1
        
        # Immediately again
        prev2 = make_state(price=99.5, vwap=100.0)
        curr2 = make_state(price=100.5, vwap=100.0)
        events2 = detector.detect(curr2, prev2)
        assert len(events2) == 0  # Cooldown


# ============================================================================
# EVENT RECORD SERIALIZATION
# ============================================================================

class TestEventRecord:
    def test_to_dict_no_none_values(self):
        """Redis doesn't accept None values - to_dict must exclude them."""
        from models import EventRecord
        
        event = EventRecord(
            event_type=EventType.NEW_HIGH,
            rule_id="test",
            symbol="TEST",
            timestamp=datetime.utcnow(),
            price=100.0,
        )
        
        d = event.to_dict()
        for k, v in d.items():
            assert v is not None, f"Field {k} is None in to_dict()"
    
    def test_roundtrip(self):
        from models import EventRecord
        
        event = EventRecord(
            event_type=EventType.VWAP_CROSS_UP,
            rule_id="test:rule",
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            price=150.0,
            prev_value=149.0,
            new_value=151.0,
            change_percent=1.5,
            rvol=2.0,
            volume=1_000_000,
            gap_percent=2.5,
            change_from_open=0.8,
            open_price=148.0,
            prev_close=147.0,
            vwap=149.5,
            atr_percent=3.2,
            intraday_high=151.0,
            intraday_low=147.5,
            market_cap=2.5e12,
        )
        
        d = event.to_dict()
        restored = EventRecord.from_dict(d)
        
        assert restored.event_type == event.event_type
        assert restored.symbol == event.symbol
        assert restored.price == event.price
        assert restored.prev_value == event.prev_value
        assert restored.gap_percent == event.gap_percent
        assert restored.change_from_open == event.change_from_open
        assert restored.open_price == event.open_price
        assert restored.prev_close == event.prev_close
        assert restored.vwap == event.vwap
        assert restored.atr_percent == event.atr_percent
        assert restored.intraday_high == event.intraday_high
        assert restored.intraday_low == event.intraday_low
        assert restored.market_cap == event.market_cap
