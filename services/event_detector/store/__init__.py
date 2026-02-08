"""Event Store - Stores and retrieves events."""

from datetime import datetime, timedelta
from typing import List, Optional, Dict
from collections import deque
from models import EventRecord, EventType


class EventStore:
    """
    In-memory store for recent events.
    
    Keeps events for a configurable time window.
    For persistence, events are also written to Redis stream.
    """
    
    def __init__(self, max_age_seconds: int = 3600, max_events: int = 10000):
        self._events: deque = deque(maxlen=max_events)
        self._max_age = timedelta(seconds=max_age_seconds)
        self._by_symbol: Dict[str, List[EventRecord]] = {}
        self._by_type: Dict[EventType, List[EventRecord]] = {}
    
    def add(self, event: EventRecord) -> None:
        """Add an event to the store."""
        self._events.append(event)
        
        # Index by symbol
        if event.symbol not in self._by_symbol:
            self._by_symbol[event.symbol] = []
        self._by_symbol[event.symbol].append(event)
        
        # Index by type
        if event.event_type not in self._by_type:
            self._by_type[event.event_type] = []
        self._by_type[event.event_type].append(event)
    
    def get_recent(self, limit: int = 100) -> List[EventRecord]:
        """Get most recent events."""
        return list(self._events)[-limit:]
    
    def get_by_symbol(self, symbol: str, limit: int = 50) -> List[EventRecord]:
        """Get events for a specific symbol."""
        return self._by_symbol.get(symbol, [])[-limit:]
    
    def get_by_type(self, event_type: EventType, limit: int = 50) -> List[EventRecord]:
        """Get events of a specific type."""
        return self._by_type.get(event_type, [])[-limit:]
    
    def cleanup_old(self) -> int:
        """Remove events older than max_age. Returns count removed."""
        cutoff = datetime.utcnow() - self._max_age
        removed = 0
        
        while self._events and self._events[0].timestamp < cutoff:
            old = self._events.popleft()
            removed += 1
            
            # Clean indices
            if old.symbol in self._by_symbol:
                self._by_symbol[old.symbol] = [
                    e for e in self._by_symbol[old.symbol] if e.timestamp >= cutoff
                ]
            if old.event_type in self._by_type:
                self._by_type[old.event_type] = [
                    e for e in self._by_type[old.event_type] if e.timestamp >= cutoff
                ]
        
        return removed
    
    @property
    def size(self) -> int:
        return len(self._events)
