"""
Símbolos de índices bursátiles — única fuente de verdad del mapping
interno ↔ FMP.

Convención (estilo TradingView/Bloomberg):
  - Los índices "core" usan un símbolo interno limpio (SPX, VIX, NDX...)
    verificado SIN colisión contra equities/ETFs activos en tickers_unified
    (2026-07-24: DAX, DJIA, CAC, COMP, IBEX y ES colisionan → esos índices
    conservan su símbolo FMP con caret).
  - El resto de índices del firehose de FMP (~425) pasan tal cual con su
    símbolo FMP (^GDAXI, ^TASI.SR, XIN9.FGI...).
  - Las equities SIEMPRE ganan el símbolo: el seed de metadata comprueba la
    colisión en runtime y degrada el alias al símbolo FMP si aparece una.

Reglas de uso:
  - Productor (fmp_indices): traduce FMP→interno con `from_fmp()` ANTES de
    publicar a Redis/minute_bars. Ningún otro servicio traduce.
  - api_gateway (chart): traduce interno→FMP con `to_fmp()` al pedir datos.
  - `is_index_symbol()` es el test canónico para desviar/aceptar símbolos
    de índice en cualquier servicio (guard de polygon_ws, ramas de chart...).
"""

from typing import Optional

# Interno → FMP. Solo aliases verificados sin colisión.
INDEX_ALIASES: dict[str, str] = {
    # US core
    "SPX": "^GSPC",      # S&P 500
    "NDX": "^NDX",       # Nasdaq 100
    "IXIC": "^IXIC",     # Nasdaq Composite (COMP colisiona con Compass Inc.)
    "DJI": "^DJI",       # Dow Jones Industrial Average (DJIA colisiona con ETF)
    "RUT": "^RUT",       # Russell 2000
    "VIX": "^VIX",       # CBOE Volatility Index
    "SOX": "^SOX",       # PHLX Semiconductor
    "NYA": "^NYA",       # NYSE Composite
    # Internacionales (delay ~15-20 min en FMP)
    "FTSE": "^FTSE",     # FTSE 100
    "N225": "^N225",     # Nikkei 225
    "HSI": "^HSI",       # Hang Seng
}

FMP_TO_INTERNAL: dict[str, str] = {v: k for k, v in INDEX_ALIASES.items()}

# Prefijo que identifica símbolos de índice de FMP sin alias (^GDAXI...).
# Nota: la cola larga de FMP también incluye formas sin caret (XIN9.FGI,
# DE000SLA30S3.SG); esas solo entran al sistema vía metadata seed, donde
# market='indices' es la fuente de verdad. Para el data plane, todo símbolo
# que publique fmp_indices ya viene normalizado.
_FMP_CARET_PREFIX = "^"


def from_fmp(fmp_symbol: str) -> str:
    """Símbolo FMP → interno canónico (^GSPC → SPX; ^GDAXI → ^GDAXI)."""
    return FMP_TO_INTERNAL.get(fmp_symbol, fmp_symbol)


def to_fmp(internal_symbol: str) -> str:
    """Símbolo interno → FMP (SPX → ^GSPC; ^GDAXI → ^GDAXI)."""
    return INDEX_ALIASES.get(internal_symbol.upper(), internal_symbol)


def is_index_symbol(symbol: str) -> bool:
    """
    Test canónico de índice para el data plane: alias curado o forma caret.
    NO cubre la cola larga sin caret (esa se resuelve por metadata
    market='indices'); suficiente para chart/quotes/guards del core.
    """
    s = symbol.upper()
    return s in INDEX_ALIASES or s.startswith(_FMP_CARET_PREFIX)


def normalize_index_symbol(symbol: str) -> Optional[str]:
    """
    Cualquier forma → interno canónico, o None si no parece índice.
    Acepta alias (spx), forma FMP (^GSPC) y caret genérico (^GDAXI).
    """
    s = symbol.upper()
    if s in INDEX_ALIASES:
        return s
    if s in FMP_TO_INTERNAL:
        return FMP_TO_INTERNAL[s]
    if s.startswith(_FMP_CARET_PREFIX):
        return s
    return None
