"""
Polygon Helpers

Utilidades para trabajar con la API de Polygon.io
Con fallback a FMP para datos no disponibles en Polygon.
"""

import re
import os
from typing import Optional, Dict, Any
import httpx


# API Keys from environment
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
FMP_API_KEY = os.getenv("FMP_API_KEY", "")


async def get_polygon_free_float(ticker: str, api_key: str = None) -> Optional[Dict[str, Any]]:
    """
    Obtiene el free float real de un ticker desde Polygon /stocks/vX/float.
    
    El free float representa las acciones disponibles para trading público,
    excluyendo insiders, 5%+ holders, restricted shares, etc.
    
    IMPORTANTE: Solo disponible para Common Stock (CS), no para:
    - ETFs, Warrants, Units, Preferred, etc.
    
    Args:
        ticker: Símbolo del ticker (ej: "AAPL", "LVRO")
        api_key: API key de Polygon (usa env var si no se proporciona)
    
    Returns:
        Dict con:
        - free_float: int - Número de acciones en free float
        - free_float_percent: float - Porcentaje del total
        - effective_date: str - Fecha efectiva del dato
        O None si no hay datos
    
    Example:
        >>> result = await get_polygon_free_float("LVRO")
        >>> print(result)
        {'free_float': 7574118, 'free_float_percent': 6.6, 'effective_date': '2025-09-04'}
    """
    key = api_key or POLYGON_API_KEY
    if not key:
        return None
    
    url = f"https://api.polygon.io/stocks/vX/float"
    params = {
        "ticker": ticker.upper(),
        "apiKey": key
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                return None
            
            # Tomar el primer resultado (más reciente)
            result = results[0]
            
        return {
            "free_float": result.get("free_float"),
            "free_float_percent": result.get("free_float_percent"),
            "effective_date": result.get("effective_date"),
            "ticker": result.get("ticker"),
            "source": "polygon"
        }
            
    except Exception:
        return None


async def get_fmp_free_float(ticker: str, api_key: str = None) -> Optional[Dict[str, Any]]:
    """
    Obtiene el free float de un ticker desde FMP /stable/shares-float.
    
    Usado como fallback cuando Polygon no tiene datos (ADRs, etc.)
    
    Args:
        ticker: Símbolo del ticker (ej: "ASML")
        api_key: API key de FMP (usa env var si no se proporciona)
    
    Returns:
        Dict con:
        - free_float: int - Número de acciones en free float (floatShares)
        - free_float_percent: float - Porcentaje del total (freeFloat)
        - shares_outstanding: int - Total de acciones
        O None si no hay datos
    
    Example:
        >>> result = await get_fmp_free_float("ASML")
        >>> print(result)
        {'free_float': 387179937, 'free_float_percent': 99.89, 'shares_outstanding': 387601028}
    """
    key = api_key or FMP_API_KEY
    if not key:
        return None
    
    url = f"https://financialmodelingprep.com/stable/shares-float"
    params = {
        "symbol": ticker.upper(),
        "apikey": key
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            # FMP devuelve una lista, tomamos el primer elemento
            if not data or not isinstance(data, list) or len(data) == 0:
                return None
            
            result = data[0]
            
            # Mapear campos de FMP a nuestro formato
            float_shares = result.get("floatShares")
            free_float_pct = result.get("freeFloat")
            
            if float_shares is None:
                return None
            
            return {
                "free_float": int(float_shares) if float_shares else None,
                "free_float_percent": float(free_float_pct) if free_float_pct else None,
                "shares_outstanding": int(result.get("outstandingShares")) if result.get("outstandingShares") else None,
                "effective_date": result.get("date", "").split(" ")[0] if result.get("date") else None,
                "ticker": ticker.upper(),
                "source": "fmp"
            }
            
    except Exception:
        return None


async def get_free_float_with_fallback(ticker: str, polygon_api_key: str = None, fmp_api_key: str = None) -> Optional[Dict[str, Any]]:
    """
    Obtiene free float con fallback: Polygon primero, luego FMP.
    
    Jerarquía:
    1. Polygon /stocks/vX/float - Mejor para Common Stock (CS)
    2. FMP /stable/shares-float - Fallback para ADRs, ETFs, etc.
    
    Args:
        ticker: Símbolo del ticker
        polygon_api_key: API key de Polygon (opcional)
        fmp_api_key: API key de FMP (opcional)
    
    Returns:
        Dict con free_float, free_float_percent, source, etc.
        O None si ninguna fuente tiene datos
    """
    # Intentar Polygon primero
    result = await get_polygon_free_float(ticker, polygon_api_key)
    if result:
        return result
    
    # Fallback a FMP
    result = await get_fmp_free_float(ticker, fmp_api_key)
    if result:
        return result
    
    return None


def get_polygon_free_float_sync(ticker: str, api_key: str = None) -> Optional[Dict[str, Any]]:
    """
    Versión síncrona de get_polygon_free_float.
    Útil para scripts de migración.
    """
    import requests
    
    key = api_key or POLYGON_API_KEY
    if not key:
        return None
    
    url = f"https://api.polygon.io/stocks/vX/float"
    params = {
        "ticker": ticker.upper(),
        "apiKey": key
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        results = data.get("results", [])
        
        if not results:
            return None
        
        result = results[0]
        
        return {
            "free_float": result.get("free_float"),
            "free_float_percent": result.get("free_float_percent"),
            "effective_date": result.get("effective_date"),
            "ticker": result.get("ticker"),
            "source": "polygon"
        }
        
    except Exception:
        return None


def get_fmp_free_float_sync(ticker: str, api_key: str = None) -> Optional[Dict[str, Any]]:
    """
    Versión síncrona de get_fmp_free_float.
    """
    import requests
    
    key = api_key or FMP_API_KEY
    if not key:
        return None
    
    url = f"https://financialmodelingprep.com/stable/shares-float"
    params = {
        "symbol": ticker.upper(),
        "apikey": key
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        
        if not data or not isinstance(data, list) or len(data) == 0:
            return None
        
        result = data[0]
        float_shares = result.get("floatShares")
        free_float_pct = result.get("freeFloat")
        
        if float_shares is None:
            return None
        
        return {
            "free_float": int(float_shares) if float_shares else None,
            "free_float_percent": float(free_float_pct) if free_float_pct else None,
            "shares_outstanding": int(result.get("outstandingShares")) if result.get("outstandingShares") else None,
            "effective_date": result.get("date", "").split(" ")[0] if result.get("date") else None,
            "ticker": ticker.upper(),
            "source": "fmp"
        }
        
    except Exception:
        return None


def get_free_float_with_fallback_sync(ticker: str, polygon_api_key: str = None, fmp_api_key: str = None) -> Optional[Dict[str, Any]]:
    """
    Versión síncrona de get_free_float_with_fallback.
    Polygon primero, FMP como fallback.
    """
    result = get_polygon_free_float_sync(ticker, polygon_api_key)
    if result:
        return result
    
    result = get_fmp_free_float_sync(ticker, fmp_api_key)
    if result:
        return result
    
    return None


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

