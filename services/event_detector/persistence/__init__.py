"""
Persistence module for Event Detector.

Handles batch writing of market events to TimescaleDB.
"""

from .event_writer import EventWriter

__all__ = ["EventWriter"]
