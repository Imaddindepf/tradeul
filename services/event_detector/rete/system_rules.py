"""
System Event Rules - Pre-built event detection rules.

NOTE: These rule definitions are NOT currently used by the detector plugins.
The 6 detector plugins (price, vwap, volume, momentum, pullback, gap) use
hardcoded detection logic for performance and edge-case handling.

These rules serve as a REFERENCE MODEL for the future RuleEvaluator engine
that will enable user-created custom event rules (UserEventRule).

When the RuleEvaluator is built, system rules will be evaluated alongside
user rules using the same Condition/Operator evaluation engine.
"""

from typing import List
from models import EventRule, EventTrigger, Condition, Operator, RuleOwnerType


def get_system_event_rules() -> List[EventRule]:
    """
    Get all system-defined event rules.
    
    These are enabled by default and available to all users.
    They detect fundamental market events that traders need to know about.
    """
    return [
        # ============= PRICE EVENTS =============
        
        EventRule(
            id="event:system:new_high",
            owner_type=RuleOwnerType.SYSTEM,
            name="New Intraday High",
            trigger=EventTrigger.PRICE_CROSSES_ABOVE,
            trigger_field="price",
            reference_field="intraday_high",
            conditions=[
                # Only trigger for stocks with decent volume
                Condition("volume", Operator.GTE, 10000),
            ],
            cooldown_seconds=30,  # Max 1 new high event per 30 seconds per symbol
        ),
        
        EventRule(
            id="event:system:new_low",
            owner_type=RuleOwnerType.SYSTEM,
            name="New Intraday Low",
            trigger=EventTrigger.PRICE_CROSSES_BELOW,
            trigger_field="price",
            reference_field="intraday_low",
            conditions=[
                Condition("volume", Operator.GTE, 10000),
            ],
            cooldown_seconds=30,
        ),
        
        EventRule(
            id="event:system:vwap_cross_up",
            owner_type=RuleOwnerType.SYSTEM,
            name="VWAP Cross Up",
            trigger=EventTrigger.PRICE_CROSSES_ABOVE,
            trigger_field="price",
            reference_field="vwap",
            conditions=[
                Condition("volume", Operator.GTE, 10000),
            ],
            cooldown_seconds=60,
        ),
        
        EventRule(
            id="event:system:vwap_cross_down",
            owner_type=RuleOwnerType.SYSTEM,
            name="VWAP Cross Down",
            trigger=EventTrigger.PRICE_CROSSES_BELOW,
            trigger_field="price",
            reference_field="vwap",
            conditions=[
                Condition("volume", Operator.GTE, 10000),
            ],
            cooldown_seconds=60,
        ),
        
        # ============= VOLUME EVENTS =============
        
        EventRule(
            id="event:system:rvol_spike",
            owner_type=RuleOwnerType.SYSTEM,
            name="RVOL Spike",
            trigger=EventTrigger.VALUE_CROSSES_ABOVE,
            trigger_field="rvol",
            threshold=3.0,  # RVOL crosses above 3x
            conditions=[
                Condition("volume", Operator.GTE, 50000),
            ],
            cooldown_seconds=300,  # Only once every 5 minutes
        ),
        
        EventRule(
            id="event:system:volume_surge",
            owner_type=RuleOwnerType.SYSTEM,
            name="Volume Surge",
            trigger=EventTrigger.VALUE_CROSSES_ABOVE,
            trigger_field="rvol",
            threshold=5.0,  # RVOL crosses above 5x
            conditions=[
                Condition("volume", Operator.GTE, 100000),
            ],
            cooldown_seconds=600,  # Only once every 10 minutes
        ),
        
        # ============= TRADING EVENTS (External) =============
        
        EventRule(
            id="event:system:halt",
            owner_type=RuleOwnerType.SYSTEM,
            name="Trading Halt",
            trigger=EventTrigger.EXTERNAL_EVENT,
            external_source="stream:halt:events",
            external_filter={"event_type": "halt"},
            cooldown_seconds=0,  # Always fire (halts are rare)
        ),
        
        EventRule(
            id="event:system:resume",
            owner_type=RuleOwnerType.SYSTEM,
            name="Trading Resume",
            trigger=EventTrigger.EXTERNAL_EVENT,
            external_source="stream:halt:events",
            external_filter={"event_type": "resume"},
            cooldown_seconds=0,
        ),
    ]


def get_rule_by_id(rule_id: str) -> EventRule | None:
    """Get a system rule by its ID."""
    for rule in get_system_event_rules():
        if rule.id == rule_id:
            return rule
    return None
