"""
Alert Registry - Complete catalog of all market alert types.

Inspired by Trade Ideas' alert system. Each alert has:
- code: Short identifier (e.g., "NHP" for New High)
- event_type: Maps to EventType enum for detection
- category: Grouping for UI/filtering
- direction: Bullish (+), Bearish (-), Neutral (~)
- phase: Implementation phase (1=live, 2=daily indicators, 3=bar builder, 4=advanced)
"""

from registry.alert_catalog import (
    AlertDefinition,
    AlertCategory,
    ALERT_CATALOG,
    CATEGORY_CATALOG,
    get_alert_by_code,
    get_alert_by_event_type,
    get_alerts_by_category,
    get_alerts_by_phase,
    get_active_alerts,
)

__all__ = [
    "AlertDefinition",
    "AlertCategory",
    "ALERT_CATALOG",
    "CATEGORY_CATALOG",
    "get_alert_by_code",
    "get_alert_by_event_type",
    "get_alerts_by_category",
    "get_alerts_by_phase",
    "get_active_alerts",
]
