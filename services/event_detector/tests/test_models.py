"""
Tests for Event Detector models.
"""

import pytest
from datetime import datetime, timedelta

from models import (
    EventRecord,
    EventType,
    TickerState,
    TickerStateCache,
    EventRule,
    EventTrigger,
    Condition,
    Operator,
)


class TestEventType:
    """Tests for EventType enum."""
    
    def test_core_event_types_exist(self):
        """Verify all core event types exist."""
        assert EventType.NEW_HIGH == "new_high"
        assert EventType.NEW_LOW == "new_low"
        assert EventType.VWAP_CROSS_UP == "vwap_cross_up"
        assert EventType.VWAP_CROSS_DOWN == "vwap_cross_down"
        assert EventType.RVOL_SPIKE == "rvol_spike"
        assert EventType.HALT == "halt"
        assert EventType.RESUME == "resume"
    
    def test_new_event_types_exist(self):
        """Verify new event types exist."""
        assert EventType.CROSSED_ABOVE_OPEN == "crossed_above_open"
        assert EventType.CROSSED_BELOW_OPEN == "crossed_below_open"
        assert EventType.CROSSED_ABOVE_PREV_CLOSE == "crossed_above_prev_close"
        assert EventType.CROSSED_BELOW_PREV_CLOSE == "crossed_below_prev_close"
        assert EventType.VOLUME_SPIKE_1MIN == "volume_spike_1min"
        assert EventType.UNUSUAL_PRINTS == "unusual_prints"
        assert EventType.BLOCK_TRADE == "block_trade"
        assert EventType.RUNNING_UP == "running_up"
        assert EventType.RUNNING_DOWN == "running_down"
        assert EventType.PERCENT_UP_5 == "percent_up_5"
        assert EventType.PERCENT_DOWN_5 == "percent_down_5"
        assert EventType.PERCENT_UP_10 == "percent_up_10"
        assert EventType.PERCENT_DOWN_10 == "percent_down_10"
        assert EventType.PULLBACK_75_FROM_HIGH == "pullback_75_from_high"
        assert EventType.PULLBACK_25_FROM_HIGH == "pullback_25_from_high"
        assert EventType.PULLBACK_75_FROM_LOW == "pullback_75_from_low"
        assert EventType.PULLBACK_25_FROM_LOW == "pullback_25_from_low"
        assert EventType.GAP_UP_REVERSAL == "gap_up_reversal"
        assert EventType.GAP_DOWN_REVERSAL == "gap_down_reversal"
    
    def test_event_type_is_string(self):
        """EventType should be a string enum."""
        assert isinstance(EventType.NEW_HIGH.value, str)
    
    def test_total_event_types(self):
        """Verify we have at least 27 event types."""
        assert len(EventType) >= 27


class TestEventRecord:
    """Tests for EventRecord dataclass."""
    
    def test_create_event_record(self):
        """Create a basic EventRecord."""
        event = EventRecord(
            event_type=EventType.NEW_HIGH,
            rule_id="event:system:new_high",
            symbol="TSLA",
            timestamp=datetime.utcnow(),
            price=250.50,
        )
        
        assert event.symbol == "TSLA"
        assert event.event_type == EventType.NEW_HIGH
        assert event.price == 250.50
        assert event.id is not None  # Auto-generated UUID
    
    def test_event_record_to_dict(self):
        """Test serialization to dictionary."""
        timestamp = datetime.utcnow()
        event = EventRecord(
            event_type=EventType.RVOL_SPIKE,
            rule_id="event:system:rvol_spike",
            symbol="GME",
            timestamp=timestamp,
            price=45.00,
            prev_value=2.5,
            new_value=4.0,
            delta=1.5,
            rvol=4.0,
            volume=5_000_000,
        )
        
        data = event.to_dict()
        
        assert data["event_type"] == "rvol_spike"
        assert data["symbol"] == "GME"
        assert data["price"] == 45.00
        assert data["rvol"] == 4.0
        assert "timestamp" in data
    
    def test_event_record_to_dict_no_none(self):
        """Redis doesn't accept None - to_dict must exclude them."""
        event = EventRecord(
            event_type=EventType.NEW_HIGH,
            rule_id="test",
            symbol="TEST",
            timestamp=datetime.utcnow(),
            price=100.0,
        )
        
        data = event.to_dict()
        for key, value in data.items():
            assert value is not None, f"Field {key} is None"
    
    def test_event_record_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "id": "test-id-123",
            "event_type": "new_high",
            "rule_id": "event:system:new_high",
            "symbol": "AAPL",
            "timestamp": "2024-01-15T10:30:00",
            "price": 185.50,
            "volume": 1000000,
        }
        
        event = EventRecord.from_dict(data)
        
        assert event.id == "test-id-123"
        assert event.event_type == EventType.NEW_HIGH
        assert event.symbol == "AAPL"
        assert event.price == 185.50
    
    def test_event_record_roundtrip(self):
        """Test serialization round-trip."""
        original = EventRecord(
            event_type=EventType.VWAP_CROSS_UP,
            rule_id="event:system:vwap_cross_up",
            symbol="META",
            timestamp=datetime.utcnow(),
            price=350.0,
            prev_value=349.0,
            new_value=351.0,
            change_percent=2.5,
            rvol=1.5,
            volume=2_000_000,
        )
        
        data = original.to_dict()
        restored = EventRecord.from_dict(data)
        
        assert restored.event_type == original.event_type
        assert restored.symbol == original.symbol
        assert restored.price == original.price


class TestTickerState:
    """Tests for TickerState dataclass."""
    
    def test_create_ticker_state(self):
        """Create a TickerState."""
        state = TickerState(
            symbol="NVDA",
            price=500.00,
            volume=2_000_000,
            timestamp=datetime.utcnow(),
            vwap=495.00,
            intraday_high=510.00,
            intraday_low=490.00,
        )
        
        assert state.symbol == "NVDA"
        assert state.price == 500.00
        assert state.vwap == 495.00
    
    def test_ticker_state_with_new_fields(self):
        """Test TickerState with all new fields."""
        state = TickerState(
            symbol="AMD",
            price=150.0,
            volume=1_000_000,
            timestamp=datetime.utcnow(),
            minute_volume=5000,
            chg_1min=-0.5,
            chg_5min=1.2,
            vol_1min=3000,
            trades_z_score=2.1,
            gap_percent=3.5,
            change_from_open=-1.2,
        )
        
        assert state.minute_volume == 5000
        assert state.chg_5min == 1.2
        assert state.gap_percent == 3.5
    
    def test_ticker_state_to_dict(self):
        """Test TickerState serialization."""
        state = TickerState(
            symbol="META",
            price=350.00,
            volume=1_000_000,
            timestamp=datetime.utcnow(),
            rvol=2.0,
        )
        
        data = state.to_dict()
        
        assert data["symbol"] == "META"
        assert data["price"] == 350.00
        assert data["rvol"] == 2.0


class TestTickerStateCache:
    """Tests for TickerStateCache."""
    
    def test_cache_set_and_get(self, state_cache):
        """Test basic set and get operations."""
        state = TickerState(
            symbol="TSLA",
            price=250.00,
            volume=100_000,
            timestamp=datetime.utcnow(),
        )
        
        state_cache.set("TSLA", state)
        retrieved = state_cache.get("TSLA")
        
        assert retrieved is not None
        assert retrieved.symbol == "TSLA"
        assert retrieved.price == 250.00
    
    def test_cache_get_nonexistent(self, state_cache):
        """Getting nonexistent key returns None."""
        result = state_cache.get("NONEXISTENT")
        assert result is None
    
    def test_cache_clear(self, state_cache):
        """Test clearing the cache."""
        state = TickerState(
            symbol="AAPL",
            price=180.00,
            volume=50_000,
            timestamp=datetime.utcnow(),
        )
        
        state_cache.set("AAPL", state)
        assert state_cache.size == 1
        
        state_cache.clear()
        assert state_cache.size == 0
        assert state_cache.get("AAPL") is None
    
    def test_cache_cleanup_old(self):
        """Test cleanup of old entries."""
        cache = TickerStateCache(max_age_seconds=1)
        
        old_time = datetime.utcnow() - timedelta(seconds=5)
        old_state = TickerState(
            symbol="OLD",
            price=10.00,
            volume=1000,
            timestamp=old_time,
        )
        
        cache.set("OLD", old_state)
        
        removed = cache.cleanup_old()
        assert removed == 1
        assert cache.get("OLD") is None


class TestCondition:
    """Tests for Condition evaluation."""
    
    def test_condition_gte(self):
        condition = Condition("volume", Operator.GTE, 10000)
        
        assert condition.evaluate({"volume": 10000}) is True
        assert condition.evaluate({"volume": 15000}) is True
        assert condition.evaluate({"volume": 5000}) is False
    
    def test_condition_lte(self):
        condition = Condition("price", Operator.LTE, 100)
        
        assert condition.evaluate({"price": 100}) is True
        assert condition.evaluate({"price": 50}) is True
        assert condition.evaluate({"price": 150}) is False
    
    def test_condition_eq(self):
        condition = Condition("event_type", Operator.EQ, "halt")
        
        assert condition.evaluate({"event_type": "halt"}) is True
        assert condition.evaluate({"event_type": "resume"}) is False
    
    def test_condition_missing_field(self):
        condition = Condition("missing_field", Operator.GTE, 100)
        
        assert condition.evaluate({"other_field": 200}) is False
