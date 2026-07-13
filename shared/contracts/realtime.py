"""
Contrato canónico de `stream:realtime:aggregates` y `stream:agg:p{N}`.

Este módulo es la ÚNICA fuente de verdad sobre los nombres de campo del
payload de agregados por segundo que publica polygon_ws. La clase de bug que
motiva esto: bar_builder leía `v`/`vol` mientras polygon_ws escribe `volume`,
y el `or 0` silencioso hizo que TODAS las velas salieran con volumen 0 sin
que ningún servicio se quejara.

Reglas:
  - Productor (polygon_ws): usa build_realtime_aggregate_payload().
  - Consumidores (bar_builder, snapshot loops, analytics, ...): usan
    parse_realtime_aggregate(). Acepta también los alias cortos de Polygon
    (o/h/l/c/v/n/a/s) por si el payload viene directo del WS de Polygon,
    pero el formato del stream es SIEMPRE el de nombres largos.
  - Si añades un campo: añádelo aquí, en el builder y en el parser, y solo
    después en los servicios.
"""

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

# Campos canónicos del payload en el stream (todos serializados como str,
# porque Redis streams solo transportan strings).
REALTIME_AGGREGATE_FIELDS = (
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "volume_accumulated",
    "vwap",
    "avg_trade_size",
    "trades",
    "timestamp_start",
    "timestamp_end",
    "otc",
)


@dataclass(slots=True)
class RealtimeAggregate:
    """Agregado por segundo ya parseado y validado."""

    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    trades: int
    vwap: float
    timestamp_start_ms: int
    timestamp_end_ms: int
    volume_accumulated: int = 0
    avg_trade_size: float = 0.0
    otc: bool = False


def build_realtime_aggregate_payload(
    *,
    symbol: str,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int,
    volume_accumulated: int,
    vwap: float,
    avg_trade_size: float,
    trades: int,
    timestamp_start_ms: int,
    timestamp_end_ms: int,
    otc: bool = False,
) -> Dict[str, str]:
    """Construye el payload canónico (todo str) para XADD."""
    return {
        "symbol": symbol,
        "open": str(open_),
        "high": str(high),
        "low": str(low),
        "close": str(close),
        "volume": str(volume),
        "volume_accumulated": str(volume_accumulated),
        "vwap": str(vwap),
        "avg_trade_size": str(avg_trade_size),
        "trades": str(trades),
        "timestamp_start": str(timestamp_start_ms),
        "timestamp_end": str(timestamp_end_ms),
        "otc": "true" if otc else "false",
    }


def _first(data: Mapping[str, Any], *keys: str) -> Any:
    """Primer valor no-None/no-vacío entre los alias dados (0 y 0.0 son válidos)."""
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return value
    return None


def parse_realtime_aggregate(data: Mapping[str, Any]) -> Optional[RealtimeAggregate]:
    """
    Parsea un entry del stream (o un mensaje A.* crudo de Polygon) al contrato.

    Devuelve None si el mensaje no cumple el contrato mínimo (símbolo, close>0
    y timestamp>0). No hace defaults silenciosos en los campos críticos: si
    `volume` no viene con ningún nombre conocido, el mensaje se considera
    inválido en lugar de producir velas con volumen 0.
    """
    symbol = _first(data, "symbol", "sym")
    if not symbol:
        return None

    try:
        close = float(_first(data, "close", "c") or 0)
        timestamp_start = int(float(_first(data, "timestamp_start", "s") or 0))
        if close <= 0 or timestamp_start <= 0:
            return None

        raw_volume = _first(data, "volume", "v", "vol")
        if raw_volume is None:
            # Campo crítico ausente == ruptura de contrato, no un "0 legítimo".
            return None

        open_ = float(_first(data, "open", "o") or 0) or close
        high = float(_first(data, "high", "h") or 0) or close
        low = float(_first(data, "low", "l") or 0) or close

        return RealtimeAggregate(
            symbol=str(symbol),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=int(float(raw_volume)),
            trades=int(float(_first(data, "trades", "n") or 0)),
            vwap=float(_first(data, "vwap", "a") or 0),
            timestamp_start_ms=timestamp_start,
            timestamp_end_ms=int(float(_first(data, "timestamp_end", "e") or 0)) or timestamp_start + 1000,
            volume_accumulated=int(float(_first(data, "volume_accumulated", "av") or 0)),
            avg_trade_size=float(_first(data, "avg_trade_size", "z") or 0),
            otc=str(_first(data, "otc") or "").lower() in ("true", "1"),
        )
    except (ValueError, TypeError):
        return None
