"""
Enrichment Pipeline - Snapshot enrichment with incremental Redis Hash writes.

Components:
- pipeline.py: Main enrichment loop
- change_detector.py: Byte-level change detection for incremental writes
"""

from .pipeline import EnrichmentPipeline
from .change_detector import ChangeDetector

__all__ = ["EnrichmentPipeline", "ChangeDetector"]
