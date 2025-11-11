"""
Scanner Categories
Clasifica tickers en diferentes categorías profesionales
"""

from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum

import sys
sys.path.append('/app')

from shared.models.scanner import ScannerTicker
from shared.enums.market_session import MarketSession
from shared.utils.logger import get_logger
from shared.config.settings import settings

# Importar GapTracker (para global instance)
from gap_calculator import GapTracker

logger = get_logger(__name__)


class ScannerCategory(str, Enum):
    """Categorías de scanners disponibles"""
    GAPPERS_UP = "gappers_up"           # Gap up desde cierre anterior
    GAPPERS_DOWN = "gappers_down"       # Gap down desde cierre anterior
    MOMENTUM_UP = "momentum_up"          # Momentum alcista fuerte
    MOMENTUM_DOWN = "momentum_down"      # Momentum bajista fuerte
    ANOMALIES = "anomalies"             # Patrones inusuales (RVOL extremo)
    NEW_HIGHS = "new_highs"             # Nuevos máximos del día
    NEW_LOWS = "new_lows"               # Nuevos mínimos del día
    LOSERS = "losers"                   # Mayores perdedores
    WINNERS = "winners"                 # Mayores ganadores
    HIGH_VOLUME = "high_volume"         # Alto volumen inusual
    REVERSALS = "reversals"             # Reversals (cambio de dirección)


class CategoryCriteria:
    """
    Criterios para cada categoría
    Define qué hace que un ticker califique para cada scanner
    """
    
    # GAPPERS
    GAP_UP_MIN = 2.0              # Gap up mínimo: 2%
    GAP_DOWN_MAX = -2.0           # Gap down máximo: -2%
    GAP_EXTREME = 10.0            # Gap extremo: 10%
    
    # MOMENTUM
    MOMENTUM_STRONG = 3.0         # Cambio fuerte: 3%
    MOMENTUM_EXTREME = 5.0        # Cambio extremo: 5%
    
    # ANOMALIES
    RVOL_ANOMALY_MIN = 3.0        # RVOL > 3.0 = anomalía
    RVOL_EXTREME = 5.0            # RVOL > 5.0 = extremo
    
    # VOLUME
    HIGH_VOLUME_MIN = 2.0         # RVOL > 2.0 para high volume
    
    # PRICE POSITION
    NEAR_HIGH_THRESHOLD = 0.5     # Dentro del 0.5% del high = nuevo high
    NEAR_LOW_THRESHOLD = 0.5      # Dentro del 0.5% del low = nuevo low


class ScannerCategorizer:
    """
    Categorizador de tickers en múltiples scanners
    
    Clasifica cada ticker en las categorías relevantes
    basándose en criterios profesionales
    """
    
    def __init__(self):
        self.criteria = CategoryCriteria()
    
    def categorize_ticker(self, ticker: ScannerTicker) -> List[ScannerCategory]:
        """
        Determina a qué categorías pertenece un ticker
        
        Un ticker puede estar en múltiples categorías
        
        Returns:
            Lista de categorías donde califica
        """
        categories = []
        
        # 1. GAPPERS
        gap = ticker.change_percent
        
        # DEBUG: Log inicio para MNOV
        if ticker.symbol == "MNOV":
            logger.info("DEBUG: MNOV categorization START", gap=gap, rvol=ticker.rvol, price=ticker.price)
        
        if gap is not None:
            if gap >= self.criteria.GAP_UP_MIN:
                categories.append(ScannerCategory.GAPPERS_UP)
            elif gap <= self.criteria.GAP_DOWN_MAX:
                categories.append(ScannerCategory.GAPPERS_DOWN)
        
        # 2. MOMENTUM (durante market hours, usar gap_from_open)
        if ticker.session == MarketSession.MARKET_OPEN:
            if ticker.price_from_high is not None:  # Cambio desde open implícito
                # Aproximación: Si está cerca del high, tiene momentum up
                if gap and gap >= self.criteria.MOMENTUM_STRONG:
                    categories.append(ScannerCategory.MOMENTUM_UP)
                elif gap and gap <= -self.criteria.MOMENTUM_STRONG:
                    categories.append(ScannerCategory.MOMENTUM_DOWN)
        
        # 3. WINNERS / LOSERS
        if gap is not None:
            if gap >= self.criteria.MOMENTUM_EXTREME:
                categories.append(ScannerCategory.WINNERS)
            elif gap <= -self.criteria.MOMENTUM_EXTREME:
                categories.append(ScannerCategory.LOSERS)
        
        # 4. ANOMALIES (RVOL extremo)
        if ticker.rvol_slot is not None:
            if ticker.rvol_slot >= self.criteria.RVOL_ANOMALY_MIN:
                categories.append(ScannerCategory.ANOMALIES)
        elif ticker.rvol is not None:
            if ticker.rvol >= self.criteria.RVOL_ANOMALY_MIN:
                categories.append(ScannerCategory.ANOMALIES)
        
        # 5. HIGH VOLUME
        rvol = ticker.rvol_slot or ticker.rvol
        if rvol and rvol >= self.criteria.HIGH_VOLUME_MIN:
            categories.append(ScannerCategory.HIGH_VOLUME)
        
        # 6. NEW HIGHS / LOWS
        if ticker.price_from_high is not None and ticker.price_from_low is not None:
            # Cerca del high del día
            if abs(ticker.price_from_high) <= self.criteria.NEAR_HIGH_THRESHOLD:
                categories.append(ScannerCategory.NEW_HIGHS)
            
            # Cerca del low del día
            if abs(ticker.price_from_low) <= self.criteria.NEAR_LOW_THRESHOLD:
                categories.append(ScannerCategory.NEW_LOWS)
        
        # 7. REVERSALS (cambio de dirección)
        # Si gap up pero ahora está cayendo, o gap down pero ahora está subiendo
        if gap and ticker.open:
            gap_from_open = ((ticker.price - ticker.open) / ticker.open) * 100 if ticker.open > 0 else 0
            
            # Gap up pero precio cayendo
            if gap >= 2.0 and gap_from_open <= -1.0:
                categories.append(ScannerCategory.REVERSALS)
            
            # Gap down pero precio subiendo
            elif gap <= -2.0 and gap_from_open >= 1.0:
                categories.append(ScannerCategory.REVERSALS)
        
        # DEBUG: Log final de categorías para MNOV
        if ticker.symbol == "MNOV":
            logger.info("DEBUG: MNOV categorization END", categories=[c.value for c in categories])
        
        return categories
    
    def get_category_rankings(
        self,
        tickers: List[ScannerTicker],
        category: ScannerCategory,
        limit: int = settings.default_category_limit
    ) -> List[ScannerTicker]:
        """
        Obtiene ranking de tickers para una categoría específica
        
        Args:
            tickers: Lista completa de tickers filtrados
            category: Categoría a rankear
            limit: Top N resultados (por defecto: settings.default_category_limit)
        
        Returns:
            Lista ordenada de tickers para esa categoría
        """
        # Validar límite máximo
        limit = min(limit, settings.max_category_limit)
        # Filtrar tickers que pertenecen a la categoría
        categorized = []
        
        for ticker in tickers:
            categories = self.categorize_ticker(ticker)
            if category in categories:
                categorized.append(ticker)
        
        # DEBUG para gappers_up y MNOV
        if category == ScannerCategory.GAPPERS_UP:
            mnov_in_list = [t for t in categorized if t.symbol == "MNOV"]
            logger.info("DEBUG: gappers_up before sort", 
                       total=len(categorized),
                       mnov_present=len(mnov_in_list) > 0,
                       mnov_data=mnov_in_list[0].change_percent if mnov_in_list else None)
        
        # Ordenar según la categoría
        if category == ScannerCategory.GAPPERS_UP:
            # Ordenar por gap descendente (mayor gap primero)
            categorized.sort(key=lambda t: t.change_percent or 0, reverse=True)
        
        elif category == ScannerCategory.GAPPERS_DOWN:
            # Ordenar por gap ascendente (más negativo primero)
            categorized.sort(key=lambda t: t.change_percent or 0)
        
        elif category in [ScannerCategory.MOMENTUM_UP, ScannerCategory.WINNERS]:
            # Ordenar por cambio % descendente
            categorized.sort(key=lambda t: t.change_percent or 0, reverse=True)
        
        elif category in [ScannerCategory.MOMENTUM_DOWN, ScannerCategory.LOSERS]:
            # Ordenar por cambio % ascendente (más negativo primero)
            categorized.sort(key=lambda t: t.change_percent or 0)
        
        elif category == ScannerCategory.ANOMALIES:
            # Ordenar por RVOL descendente
            categorized.sort(key=lambda t: t.rvol_slot or t.rvol or 0, reverse=True)
        
        elif category == ScannerCategory.HIGH_VOLUME:
            # Ordenar por volumen total descendente
            categorized.sort(key=lambda t: t.volume_today or 0, reverse=True)
        
        elif category == ScannerCategory.NEW_HIGHS:
            # Ordenar por distancia del high (más cerca = primero)
            categorized.sort(key=lambda t: abs(t.price_from_high) if t.price_from_high else 999)
        
        elif category == ScannerCategory.NEW_LOWS:
            # Ordenar por distancia del low (más cerca = primero)
            categorized.sort(key=lambda t: abs(t.price_from_low) if t.price_from_low else 999)
        
        elif category == ScannerCategory.REVERSALS:
            # Ordenar por score (reversals más significativos)
            categorized.sort(key=lambda t: t.score, reverse=True)
        
        return categorized[:limit]
    
    def get_all_categories(
        self,
        tickers: List[ScannerTicker],
        limit_per_category: int = settings.default_category_limit
    ) -> Dict[str, List[ScannerTicker]]:
        """
        Obtiene TODAS las categorías con sus respectivos rankings
        
        Optimización doble:
        1. Pre-calcula categorías UNA VEZ por ticker (evita redundancia)
        2. Agrupa en UNA SOLA PASADA (evita doble bucle)
        
        Complejidad:
        - Antes: O(11 × 500 × 20) = 110,000 operaciones
        - Después paso 1: O(500 × 20 + 11 × 500) = 15,500 ops (-86%)
        - Después paso 2: O(500 × 20 + 500 × 2.5) = 11,250 ops (-90%)
        
        Args:
            tickers: Lista completa de tickers filtrados
            limit_per_category: Límite de resultados por categoría
        
        Returns:
            Dict con {category_name: [tickers_ranked]}
        """
        limit_per_category = min(limit_per_category, settings.max_category_limit)
        
        # Agrupar tickers por categoría en UNA SOLA PASADA
        # Antes: O(11 categorías × 500 tickers) = 5,500 iteraciones
        # Ahora:  O(500 tickers × 2.5 categorías/ticker) = 1,250 iteraciones (-77%)
        results = {cat.value: [] for cat in ScannerCategory}
        
        for ticker in tickers:
            categories = self.categorize_ticker(ticker)
            for category in categories:
                results[category.value].append(ticker)
        
        # Ordenar y limitar cada categoría
        for category in ScannerCategory:
            categorized = results[category.value]
            
            if not categorized:
                continue
            
            # Ordenar según la categoría
            if category == ScannerCategory.GAPPERS_UP:
                categorized.sort(key=lambda t: t.change_percent or 0, reverse=True)
            elif category == ScannerCategory.GAPPERS_DOWN:
                categorized.sort(key=lambda t: t.change_percent or 0)
            elif category in [ScannerCategory.MOMENTUM_UP, ScannerCategory.WINNERS]:
                categorized.sort(key=lambda t: t.change_percent or 0, reverse=True)
            elif category in [ScannerCategory.MOMENTUM_DOWN, ScannerCategory.LOSERS]:
                categorized.sort(key=lambda t: t.change_percent or 0)
            elif category == ScannerCategory.ANOMALIES:
                categorized.sort(key=lambda t: t.rvol_slot or t.rvol or 0, reverse=True)
            elif category == ScannerCategory.HIGH_VOLUME:
                categorized.sort(key=lambda t: t.volume_today or 0, reverse=True)
            elif category == ScannerCategory.NEW_HIGHS:
                categorized.sort(key=lambda t: abs(t.price_from_high) if t.price_from_high else 999)
            elif category == ScannerCategory.NEW_LOWS:
                categorized.sort(key=lambda t: abs(t.price_from_low) if t.price_from_low else 999)
            elif category == ScannerCategory.REVERSALS:
                categorized.sort(key=lambda t: t.score, reverse=True)
            
            results[category.value] = categorized[:limit_per_category]
        
        return results
    
    def get_category_stats(
        self,
        tickers: List[ScannerTicker]
    ) -> Dict[str, int]:
        """
        Obtiene estadísticas de cuántos tickers hay en cada categoría
        
        Returns:
            Dict con {category_name: count}
        """
        stats = {}
        
        for category in ScannerCategory:
            ranked = self.get_category_rankings(tickers, category, limit=999999)
            stats[category.value] = len(ranked)
        
        return stats


# Global tracker instance
_gap_tracker = GapTracker()


def get_gap_tracker() -> GapTracker:
    """Get global gap tracker instance"""
    return _gap_tracker

