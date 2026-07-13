"""Contratos de datos compartidos entre servicios (streams/canales Redis)."""

from shared.contracts.realtime import (
    REALTIME_AGGREGATE_FIELDS,
    RealtimeAggregate,
    build_realtime_aggregate_payload,
    parse_realtime_aggregate,
)

__all__ = [
    "REALTIME_AGGREGATE_FIELDS",
    "RealtimeAggregate",
    "build_realtime_aggregate_payload",
    "parse_realtime_aggregate",
]
