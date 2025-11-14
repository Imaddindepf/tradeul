"""
Polygon Helpers

Utilidades para trabajar con la API de Polygon.io
"""

import re


def normalize_ticker_for_reference_api(symbol: str) -> str:
    """
    Normaliza el formato del ticker para el Reference API de Polygon.
    
    Polygon usa formatos diferentes para preferred stocks entre APIs:
    - Market Data API (snapshots): usa P mayúscula → BACPM, WFCPC
    - Reference API (metadata): usa p minúscula → BACpM, WFCpC
    
    Esta función convierte el formato de Market Data al formato de Reference API.
    
    Preferred stocks terminan en P seguido de UNA letra (PA, PB, PC, etc.)
    Requiere al menos 3 caracteres antes del sufijo P+letra para evitar
    false positives como AAPL.
    
    Args:
        symbol: Símbolo del ticker en formato Market Data (ej: BACPM)
    
    Returns:
        Símbolo normalizado para Reference API (ej: BACpM)
    
    Examples:
        >>> normalize_ticker_for_reference_api("BACPM")
        "BACpM"
        >>> normalize_ticker_for_reference_api("WFCPC")
        "WFCpC"
        >>> normalize_ticker_for_reference_api("AAPL")
        "AAPL"
        >>> normalize_ticker_for_reference_api("PSAPO")
        "PSApO"
    """
    # Patrón: al menos 3 caracteres, luego P mayúscula seguida de exactamente UNA letra al final
    # Ejemplos: BACPM (BAC + PM), WFCPC (WFC + PC), PSAPO (PSA + PO)
    # No captura: AAPL (solo 4 letras totales, no es formato de preferred)
    pattern = r'^([A-Z]{3,})P([A-Z])$'
    
    match = re.match(pattern, symbol)
    if match:
        # Reconstruir: base + p minúscula + serie
        base = match.group(1)
        series = match.group(2)
        normalized = f"{base}p{series}"
        return normalized
    
    # Si no es preferred stock, devuelve el símbolo sin cambios
    return symbol


def is_preferred_stock(symbol: str) -> bool:
    """
    Detecta si un símbolo es una acción preferida (preferred stock).
    
    Args:
        symbol: Símbolo del ticker
    
    Returns:
        True si es preferred stock, False si no
    
    Examples:
        >>> is_preferred_stock("BACPM")
        True
        >>> is_preferred_stock("AAPL")
        False
        >>> is_preferred_stock("PSAPO")
        True
    """
    pattern = r'^[A-Z]{3,}P[A-Z]$'
    return bool(re.match(pattern, symbol))

