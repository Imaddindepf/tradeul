#!/usr/bin/env python3
"""
Script de prueba para verificar el fix de preferred stocks

Prueba la normalización de símbolos para el Reference API de Polygon
"""

import re
import sys


def normalize_ticker_for_reference_api(symbol: str) -> str:
    """
    Normaliza el formato del ticker para el Reference API de Polygon.
    
    Polygon usa formatos diferentes para preferred stocks entre APIs:
    - Market Data API (snapshots): usa P mayúscula → BACPM, WFCPC
    - Reference API (metadata): usa p minúscula → BACpM, WFCpC
    
    Preferred stocks terminan en P seguido de UNA letra (PA, PB, PC, etc.)
    Requiere al menos 3 caracteres antes del sufijo P+letra para evitar
    false positives como AAPL.
    """
    # Patrón: al menos 3 caracteres, luego P mayúscula seguida de exactamente UNA letra al final
    # Ejemplos: BACPM (BAC + PM), WFCPC (WFC + PC), PSAPO (PSA + PO)
    # No captura: AAPL (solo 4 letras totales, AAP + L no tiene sentido como preferred)
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
    """Detecta si un símbolo es una acción preferida (preferred stock)."""
    pattern = r'^[A-Z]{3,}P[A-Z]$'
    return bool(re.match(pattern, symbol))


def test_normalization():
    """
    Prueba la normalización de símbolos
    """
    test_cases = [
        # (input, expected_output, is_preferred)
        ("BACPM", "BACpM", True),
        ("BACPN", "BACpN", True),
        ("WFCPC", "WFCpC", True),
        ("PSAPO", "PSApO", True),
        ("USBPQ", "USBpQ", True),
        ("AAPL", "AAPL", False),
        ("TSLA", "TSLA", False),
        ("MSFT", "MSFT", False),
        ("AVX", "AVX", False),  # No es preferred
        ("FISV", "FISV", False),
    ]
    
    print("=" * 60)
    print("TEST: Normalización de Preferred Stocks")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for symbol, expected, is_pref in test_cases:
        result = normalize_ticker_for_reference_api(symbol)
        detected_pref = is_preferred_stock(symbol)
        
        status = "✅" if result == expected and detected_pref == is_pref else "❌"
        
        if result == expected and detected_pref == is_pref:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} {symbol:10} → {result:10} (Expected: {expected:10}) | Pref: {detected_pref}")
    
    print("=" * 60)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = test_normalization()
    sys.exit(0 if success else 1)

