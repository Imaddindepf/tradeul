"""
Tests for System Event Rules.

These tests verify the legacy rule-based configuration.
System rules are kept as reference; the actual detection now uses detector plugins.
"""

import pytest

from rete.system_rules import (
    get_system_event_rules,
    get_rule_by_id,
)
from models import EventTrigger


class TestSystemRules:
    """Tests for system event rules configuration."""
    
    def test_system_rules_not_empty(self):
        """System rules should have at least the core events."""
        rules = get_system_event_rules()
        assert len(rules) >= 6  # At least core rules
    
    def test_all_rules_have_required_fields(self):
        """All rules should have id, name, and trigger."""
        rules = get_system_event_rules()
        
        for rule in rules:
            assert rule.id is not None, f"Rule missing id"
            assert rule.name is not None, f"Rule {rule.id} missing name"
            assert rule.trigger is not None, f"Rule {rule.id} missing trigger"
            assert rule.owner_type == "system", f"Rule {rule.id} should be system-owned"
    
    def test_all_rules_enabled_by_default(self):
        """All system rules should be enabled by default."""
        rules = get_system_event_rules()
        
        for rule in rules:
            assert rule.enabled is True, f"Rule {rule.id} should be enabled"
    
    def test_price_rules_have_reference_field(self):
        """Price crossing rules should have reference_field."""
        rules = get_system_event_rules()
        
        price_rules = [r for r in rules if r.trigger in (
            EventTrigger.PRICE_CROSSES_ABOVE,
            EventTrigger.PRICE_CROSSES_BELOW,
        )]
        
        for rule in price_rules:
            assert rule.trigger_field is not None, f"Rule {rule.id} missing trigger_field"
            assert rule.reference_field is not None, f"Rule {rule.id} missing reference_field"
    
    def test_threshold_rules_have_threshold(self):
        """Threshold crossing rules should have threshold value."""
        rules = get_system_event_rules()
        
        threshold_rules = [r for r in rules if r.trigger in (
            EventTrigger.VALUE_CROSSES_ABOVE,
            EventTrigger.VALUE_CROSSES_BELOW,
        )]
        
        for rule in threshold_rules:
            assert rule.threshold is not None, f"Rule {rule.id} missing threshold"
            assert rule.threshold > 0, f"Rule {rule.id} threshold should be positive"
    
    def test_get_rule_by_id(self):
        """Should be able to retrieve rule by ID."""
        rule = get_rule_by_id("event:system:new_high")
        
        assert rule is not None
        assert rule.name == "New Intraday High"
        assert rule.trigger == EventTrigger.PRICE_CROSSES_ABOVE
    
    def test_get_rule_by_id_not_found(self):
        """Getting nonexistent rule returns None."""
        rule = get_rule_by_id("nonexistent:rule")
        assert rule is None
    
    def test_cooldowns_are_sensible(self):
        """Cooldowns should be reasonable values."""
        rules = get_system_event_rules()
        
        for rule in rules:
            assert rule.cooldown_seconds >= 0, f"Rule {rule.id} has negative cooldown"
            assert rule.cooldown_seconds <= 3600, f"Rule {rule.id} cooldown too long"
