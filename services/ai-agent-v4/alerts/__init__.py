"""
LLM-Powered Alert System — Phase 1 (compiler + dry-run + persistence).

Architecture (LLM compiles once, deterministic runtime evaluates forever):

  NL sentence ──► compiler (LLM, grounded on the live event catalog)
              ──► AlertSpec IR (versioned, validated Pydantic model)
              ──► dry-run against the real market_events history (evidence!)
              ──► persisted in Postgres (alert_specs)
              ──► armed into the reactive TriggerEngine (single-step specs)

The LLM never runs in the hot path: live evaluation is handled by the
TriggerEngine consuming stream:alerts:market.
"""
from alerts.spec import AlertSpec, SPEC_VERSION
from alerts.store import AlertStore, get_store

__all__ = ["AlertSpec", "SPEC_VERSION", "AlertStore", "get_store"]
