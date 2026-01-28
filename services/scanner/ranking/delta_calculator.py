"""
Delta Calculator
Calcula cambios incrementales entre rankings para actualizaciones eficientes.

Uso:
    deltas = calculate_ranking_deltas(old_ranking, new_ranking, "gappers_up")
    # deltas = [{"action": "add", ...}, {"action": "remove", ...}, ...]
"""

from typing import List, Dict

import sys
sys.path.append('/app')

from shared.models.scanner import ScannerTicker


# Umbrales para detectar cambios significativos
PRICE_THRESHOLD = 0.01      # 1 centavo
VOLUME_THRESHOLD = 1000     # 1k shares
PERCENT_THRESHOLD = 0.01    # 0.01%
RVOL_THRESHOLD = 0.05       # 5%


def ticker_data_changed(old_ticker: ScannerTicker, new_ticker: ScannerTicker) -> bool:
    """
    Verifica si los datos relevantes de un ticker cambiaron.
    
    Compara campos importantes: precio, volumen, gap, rvol.
    Usa umbrales para evitar ruido.
    
    Args:
        old_ticker: Estado anterior del ticker
        new_ticker: Estado nuevo del ticker
    
    Returns:
        True si hay cambios significativos
    """
    # Precio cambio significativamente
    if old_ticker.price and new_ticker.price:
        if abs(new_ticker.price - old_ticker.price) > PRICE_THRESHOLD:
            return True
    
    # Volumen cambio significativamente
    if old_ticker.volume_today and new_ticker.volume_today:
        if abs(new_ticker.volume_today - old_ticker.volume_today) > VOLUME_THRESHOLD:
            return True
    
    # Gap% cambio
    if old_ticker.change_percent and new_ticker.change_percent:
        if abs(new_ticker.change_percent - old_ticker.change_percent) > PERCENT_THRESHOLD:
            return True
    
    # RVOL cambio
    if old_ticker.rvol and new_ticker.rvol:
        if abs(new_ticker.rvol - old_ticker.rvol) > RVOL_THRESHOLD:
            return True
    
    return False


def calculate_ranking_deltas(
    old_ranking: List[ScannerTicker],
    new_ranking: List[ScannerTicker],
    list_name: str
) -> List[Dict]:
    """
    Calcula cambios incrementales entre dos rankings.
    
    Args:
        old_ranking: Ranking anterior
        new_ranking: Ranking nuevo
        list_name: Nombre de la categoria (gappers_up, etc.)
    
    Returns:
        Lista de deltas en formato:
        [
            {"action": "add", "rank": 1, "symbol": "TSLA", "data": {...}},
            {"action": "remove", "symbol": "NVDA"},
            {"action": "update", "rank": 2, "symbol": "AAPL", "data": {...}},
            {"action": "rerank", "symbol": "GOOGL", "old_rank": 5, "new_rank": 3}
        ]
    """
    deltas = []
    
    # Convertir a dicts para comparacion rapida
    old_dict = {t.symbol: (i, t) for i, t in enumerate(old_ranking)}
    new_dict = {t.symbol: (i, t) for i, t in enumerate(new_ranking)}
    
    # 1. Detectar tickers NUEVOS (anadidos al ranking)
    for symbol in new_dict:
        if symbol not in old_dict:
            rank, ticker = new_dict[symbol]
            deltas.append({
                "action": "add",
                "rank": rank,
                "symbol": symbol,
                "data": ticker.model_dump(mode='json')
            })
    
    # 2. Detectar tickers REMOVIDOS (salieron del ranking)
    for symbol in old_dict:
        if symbol not in new_dict:
            deltas.append({
                "action": "remove",
                "symbol": symbol
            })
    
    # 3. Detectar CAMBIOS en tickers existentes
    for symbol in new_dict:
        if symbol in old_dict:
            old_rank, old_ticker = old_dict[symbol]
            new_rank, new_ticker = new_dict[symbol]
            
            # 3a. Cambio de RANK (posicion)
            if old_rank != new_rank:
                deltas.append({
                    "action": "rerank",
                    "symbol": symbol,
                    "old_rank": old_rank,
                    "new_rank": new_rank
                })
            
            # 3b. Cambio de DATOS (precio, gap, volumen, rvol, etc.)
            if ticker_data_changed(old_ticker, new_ticker):
                deltas.append({
                    "action": "update",
                    "rank": new_rank,
                    "symbol": symbol,
                    "data": new_ticker.model_dump(mode='json')
                })
    
    return deltas


class DeltaCalculator:
    """
    Clase wrapper para calcular deltas con estado.
    
    Uso:
        calculator = DeltaCalculator()
        deltas = calculator.calculate(old_ranking, new_ranking, "gappers_up")
    """
    
    @staticmethod
    def calculate(
        old_ranking: List[ScannerTicker],
        new_ranking: List[ScannerTicker],
        list_name: str
    ) -> List[Dict]:
        """Calcula deltas entre rankings."""
        return calculate_ranking_deltas(old_ranking, new_ranking, list_name)
    
    @staticmethod
    def data_changed(old_ticker: ScannerTicker, new_ticker: ScannerTicker) -> bool:
        """Verifica si datos del ticker cambiaron."""
        return ticker_data_changed(old_ticker, new_ticker)
