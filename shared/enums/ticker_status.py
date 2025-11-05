"""
Ticker Status Enumerations
"""

from enum import Enum


class TickerStatus(str, Enum):
    """Status of a ticker in the system"""
    
    ACTIVE = "ACTIVE"              # Active and being scanned
    INACTIVE = "INACTIVE"          # Inactive, not being scanned
    FILTERED = "FILTERED"          # Passed filters, subscribed to WS
    HALTED = "HALTED"              # Trading halted
    DELISTED = "DELISTED"          # Delisted from exchange
    SUSPENDED = "SUSPENDED"        # Temporarily suspended
    
    def __str__(self) -> str:
        return self.value
    
    def is_tradeable(self) -> bool:
        """Check if ticker is tradeable"""
        return self in (TickerStatus.ACTIVE, TickerStatus.FILTERED)
    
    def should_scan(self) -> bool:
        """Check if ticker should be included in scans"""
        return self == TickerStatus.ACTIVE


class FilterMatchStatus(str, Enum):
    """Status of filter matching"""
    
    MATCHED = "MATCHED"            # Ticker matched the filter
    NOT_MATCHED = "NOT_MATCHED"    # Ticker did not match
    SKIPPED = "SKIPPED"            # Filter skipped (disabled or not applicable)
    ERROR = "ERROR"                # Error evaluating filter
    
    def __str__(self) -> str:
        return self.value


class ScanStatus(str, Enum):
    """Status of a scan operation"""
    
    IDLE = "IDLE"                  # Scanner is idle
    INITIALIZING = "INITIALIZING"  # Scanner is initializing
    RUNNING = "RUNNING"            # Scanner is actively scanning
    PAUSED = "PAUSED"              # Scanner is paused
    ERROR = "ERROR"                # Scanner encountered an error
    STOPPED = "STOPPED"            # Scanner is stopped
    
    def __str__(self) -> str:
        return self.value
    
    def is_active(self) -> bool:
        """Check if scanner is actively running"""
        return self == ScanStatus.RUNNING

