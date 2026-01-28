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
    POST_MARKET = "post_market"         # Activos en post-market (16:00-20:00 ET)


class CategoryCriteria:
    """
    Criterios para cada categoría
    Define qué hace que un ticker califique para cada scanner
    """
    
    # GAPPERS
    GAP_UP_MIN = 2.0              # Gap up mínimo: 2%
    GAP_DOWN_MAX = -2.0           # Gap down máximo: -2%
    GAP_EXTREME = 10.0            # Gap extremo: 10%
    
    # MOMENTUM (CRITERIA BASED ON PROFESSIONAL IGNITION DETECTION)
    # MOMENTUM_UP requiere:
    # 1. chg_5min >= 1.5%: Vela de ignición (cambio significativo en 5 min)
    # 2. price_from_intraday_high >= -2.0%: Cerca del HOD (máx 2% debajo)
    # 3. price_vs_vwap > 0: Precio sobre VWAP (compradores en control)
    # 4. rvol >= 5.0: RVOL > 500% (volumen significativo)
    MOMENTUM_5MIN_IGNITION = 1.5  # Cambio en 5 min mínimo: 1.5%
    MOMENTUM_HOD_THRESHOLD = -2.0 # Máximo % debajo del HOD: -2%
    MOMENTUM_RVOL_MIN = 5.0       # RVOL mínimo: 500%
    
    # Fallback para MOMENTUM_DOWN (criterio simple hasta refinar)
    MOMENTUM_STRONG = 3.0         # Cambio fuerte: 3%
    MOMENTUM_EXTREME = 5.0        # Cambio extremo: 5%
    
    # ANOMALIES (Z-Score based on trades count)
    # Z-Score = (trades_today - avg_trades_5d) / std_trades_5d
    # Si Z-Score >= 3.0 → ANOMALÍA ESTADÍSTICA
    TRADES_ZSCORE_ANOMALY_MIN = 3.0  # Z-Score >= 3 = anomalía (3 desviaciones estándar)
    
    # Fallback: RVOL alto también puede indicar anomalía (compatibilidad)
    RVOL_ANOMALY_MIN = 3.0        # RVOL > 3.0 = anomalía (fallback)
    RVOL_EXTREME = 5.0            # RVOL > 5.0 = extremo
    
    # VOLUME
    HIGH_VOLUME_MIN = 2.0         # RVOL > 2.0 para high volume
    
    # PRICE POSITION (usando intraday high/low para incluir pre/post market)
    NEAR_HIGH_THRESHOLD = 2.0     # Dentro del 2% del intraday high = nuevo high
    NEAR_LOW_THRESHOLD = 2.0      # Dentro del 2% del intraday low = nuevo low
    
    # POST-MARKET (16:00-20:00 ET)
    POSTMARKET_MIN_VOLUME = 20000     # Mínimo 20K shares en post-market
    POSTMARKET_MIN_CHANGE = 0.5       # Mínimo 0.5% cambio desde cierre para mostrar


class ScannerCategorizer:
    """
    Categorizador de tickers en múltiples scanners
    
    Clasifica cada ticker en las categorías relevantes
    basándose en criterios profesionales
    """
    
    def __init__(self):
        """
        Inicializa el categorizador con criterios configurables
        """
        self.criteria = CategoryCriteria()
    
    def categorize_ticker(self, ticker: ScannerTicker) -> List[ScannerCategory]:
        """
        Determina a qué categorías pertenece un ticker
        
        Un ticker puede estar en múltiples categorías
        
        Returns:
            Lista de categorías donde califica
        """
        categories = []
        
        # MÉTRICAS (como TradeIdeas):
        # - gap_percent: Siempre tiene valor (expected gap en pre-market, real gap después)
        # - change_percent: Cambio total del día (price vs prev_close) - para WINNERS/LOSERS
        # - change_from_open: Cambio desde apertura (price vs open) - para "running stocks"
        
        gap_percent = ticker.gap_percent  # Gap % (siempre disponible)
        change_total = ticker.change_percent  # Cambio total del día
        change_from_open = ticker.change_from_open  # Desde apertura
        
        # DEBUG: Log inicio para MNOV
        if ticker.symbol == "MNOV":
            logger.info("DEBUG: MNOV categorization START", 
                       session=ticker.session.value if ticker.session else None,
                       gap_percent=gap_percent, 
                       change_total=change_total,
                       change_from_open=change_from_open,
                       rvol=ticker.rvol, 
                       price=ticker.price)
        
        # 1. GAPPERS - Usa gap_percent directamente (ya adaptado por sesión)
        if gap_percent is not None:
            if gap_percent >= self.criteria.GAP_UP_MIN:
                categories.append(ScannerCategory.GAPPERS_UP)
            elif gap_percent <= self.criteria.GAP_DOWN_MAX:
                categories.append(ScannerCategory.GAPPERS_DOWN)
        
        # 2. MOMENTUM_UP (Professional Ignition Criteria)
        # Detecta "vela de ignición" con volumen y momentum real
        # CRITERIOS:
        #   1. chg_5min >= 1.5%: Cambio en 5 minutos significativo
        #   2. price_from_intraday_high >= -2%: Cerca del máximo del día (sin mechas)
        #   3. price_vs_vwap > 0: Precio sobre VWAP (compradores dominan)
        #   4. rvol >= 5.0: RVOL > 500% (volumen relativo alto)
        is_momentum_up = False
        
        # Verificar todos los criterios de MOMENTUM_UP
        chg_5min = ticker.chg_5min
        price_from_hod = ticker.price_from_intraday_high
        price_vs_vwap = ticker.price_vs_vwap
        rvol = ticker.rvol_slot or ticker.rvol
        
        if (chg_5min is not None and chg_5min >= self.criteria.MOMENTUM_5MIN_IGNITION and
            price_from_hod is not None and price_from_hod >= self.criteria.MOMENTUM_HOD_THRESHOLD and
            price_vs_vwap is not None and price_vs_vwap > 0 and
            rvol is not None and rvol >= self.criteria.MOMENTUM_RVOL_MIN):
            is_momentum_up = True
            categories.append(ScannerCategory.MOMENTUM_UP)
        
        # MOMENTUM_DOWN (criterio simple por ahora - cambio fuerte negativo)
        # Usa change_total porque es el cambio del día, no el gap
        if change_total is not None and change_total <= -self.criteria.MOMENTUM_STRONG:
            categories.append(ScannerCategory.MOMENTUM_DOWN)
        
        # 3. WINNERS / LOSERS - Usa change_total (cambio total del día)
        if change_total is not None:
            if change_total >= self.criteria.MOMENTUM_EXTREME:
                categories.append(ScannerCategory.WINNERS)
            elif change_total <= -self.criteria.MOMENTUM_EXTREME:
                categories.append(ScannerCategory.LOSERS)
        
        # 4. ANOMALIES (Z-Score de trades - detección estadística ÚNICAMENTE)
        # Z-Score = (trades_today - avg_trades_5d) / std_trades_5d
        # Threshold: Z >= 3.0 (3 desviaciones estándar = 99.7% probabilidad de anomalía)
        # SOLO entran tickers con Z-Score >= 3.0, NO hay fallback a RVOL
        is_anomaly = False
        
        # Check 1: Z-Score de trades >= 3.0
        if ticker.trades_z_score is not None and ticker.trades_z_score >= self.criteria.TRADES_ZSCORE_ANOMALY_MIN:
            is_anomaly = True
        # Check 2: is_trade_anomaly flag directo (calculado por Analytics con Z >= 3.0)
        elif ticker.is_trade_anomaly is True:
            is_anomaly = True
        
        if is_anomaly:
            categories.append(ScannerCategory.ANOMALIES)
        
        # 5. HIGH VOLUME
        rvol = ticker.rvol_slot or ticker.rvol
        if rvol and rvol >= self.criteria.HIGH_VOLUME_MIN:
            categories.append(ScannerCategory.HIGH_VOLUME)
        
        # 6. NEW HIGHS / LOWS - Comparación directa con intraday_high/low de Analytics
        # intraday_high/low se mantiene correctamente en Analytics (incluye pre/post market)
        # y se recupera desde Polygon al reiniciar
        
        # NEW HIGHS: precio >= 99.9% del máximo intraday
        if ticker.intraday_high and ticker.intraday_high > 0:
            # Calcular % del máximo
            percent_of_high = (ticker.price / ticker.intraday_high) * 100
            
            # Estar al 99.9% o más del máximo = está haciendo máximos
            if percent_of_high >= 99.9:
                categories.append(ScannerCategory.NEW_HIGHS)
        
        # NEW LOWS: precio <= 100.1% del mínimo intraday
        if ticker.intraday_low and ticker.intraday_low > 0:
            # Calcular % del mínimo
            percent_of_low = (ticker.price / ticker.intraday_low) * 100
            
            # Estar al 100.1% o menos del mínimo = está haciendo mínimos
            if percent_of_low <= 100.1:
                categories.append(ScannerCategory.NEW_LOWS)
        
        # 7. REVERSALS (cambio de dirección)
        # Si gap up pero ahora está cayendo, o gap down pero ahora está subiendo
        # Usa gap_percent y change_from_open
        if gap_percent is not None and change_from_open is not None:
            # Gap up pero precio cayendo desde apertura
            if gap_percent >= 2.0 and change_from_open <= -1.0:
                categories.append(ScannerCategory.REVERSALS)
            
            # Gap down pero precio subiendo desde apertura
            elif gap_percent <= -2.0 and change_from_open >= 1.0:
                categories.append(ScannerCategory.REVERSALS)
        
        # 8. POST_MARKET (activos en sesión post-market 16:00-20:00 ET)
        # Solo se categoriza si el ticker tiene datos de post-market
        if ticker.session == MarketSession.POST_MARKET:
            pm_vol = ticker.postmarket_volume
            pm_chg = ticker.postmarket_change_percent
            
            # Califica si:
            # - Tiene volumen significativo en post-market (>= 20K)
            # - O tiene cambio significativo desde el cierre (>= 0.5% en cualquier dirección)
            has_pm_volume = pm_vol is not None and pm_vol >= self.criteria.POSTMARKET_MIN_VOLUME
            has_pm_change = pm_chg is not None and abs(pm_chg) >= self.criteria.POSTMARKET_MIN_CHANGE
            
            if has_pm_volume or has_pm_change:
                categories.append(ScannerCategory.POST_MARKET)
        
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
                       mnov_gap_percent=mnov_in_list[0].gap_percent if mnov_in_list else None)
        
        # Ordenar según la categoría
        if category == ScannerCategory.GAPPERS_UP:
            # gap_percent siempre tiene valor (expected o real)
            categorized.sort(key=lambda t: t.gap_percent or 0, reverse=True)
        
        elif category == ScannerCategory.GAPPERS_DOWN:
            categorized.sort(key=lambda t: t.gap_percent or 0)
        
        elif category == ScannerCategory.MOMENTUM_UP:
            # Ordenar por chg_5min (cambio en 5 minutos) - captura el momentum actual
            categorized.sort(key=lambda t: t.chg_5min or 0, reverse=True)
        
        elif category == ScannerCategory.WINNERS:
            # Ordenar por cambio % descendente
            categorized.sort(key=lambda t: t.change_percent or 0, reverse=True)
        
        elif category in [ScannerCategory.MOMENTUM_DOWN, ScannerCategory.LOSERS]:
            # Ordenar por cambio % ascendente (más negativo primero)
            categorized.sort(key=lambda t: t.change_percent or 0)
        
        elif category == ScannerCategory.ANOMALIES:
            # Ordenar por Z-Score de trades descendente (mayor anomalía primero)
            categorized.sort(key=lambda t: t.trades_z_score or 0, reverse=True)
        
        elif category == ScannerCategory.HIGH_VOLUME:
            # Ordenar por volumen total descendente
            categorized.sort(key=lambda t: t.volume_today or 0, reverse=True)
        
        elif category == ScannerCategory.NEW_HIGHS:
            # Ordenar por distancia del intraday high (más cerca = primero)
            # Priorizar intraday_high, fallback a regular high
            categorized.sort(key=lambda t: abs(t.price_from_intraday_high if t.price_from_intraday_high is not None else (t.price_from_high if t.price_from_high is not None else 999)))
        
        elif category == ScannerCategory.NEW_LOWS:
            # Ordenar por distancia del intraday low (más cerca = primero)
            # Priorizar intraday_low, fallback a regular low
            categorized.sort(key=lambda t: abs(t.price_from_intraday_low if t.price_from_intraday_low is not None else (t.price_from_low if t.price_from_low is not None else 999)))
        
        elif category == ScannerCategory.REVERSALS:
            # Ordenar por score (reversals más significativos)
            categorized.sort(key=lambda t: t.score, reverse=True)
        
        elif category == ScannerCategory.POST_MARKET:
            # Ordenar por cambio % post-market (mayor movimiento primero, en valor absoluto)
            categorized.sort(key=lambda t: abs(t.postmarket_change_percent or 0), reverse=True)
        
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
                categorized.sort(key=lambda t: t.gap_percent or 0, reverse=True)
            elif category == ScannerCategory.GAPPERS_DOWN:
                categorized.sort(key=lambda t: t.gap_percent or 0)
            elif category == ScannerCategory.MOMENTUM_UP:
                categorized.sort(key=lambda t: t.chg_5min or 0, reverse=True)
            elif category == ScannerCategory.WINNERS:
                categorized.sort(key=lambda t: t.change_percent or 0, reverse=True)
            elif category in [ScannerCategory.MOMENTUM_DOWN, ScannerCategory.LOSERS]:
                categorized.sort(key=lambda t: t.change_percent or 0)
            elif category == ScannerCategory.ANOMALIES:
                # Ordenar por Z-Score de trades (mayor anomalía primero)
                # Fallback a RVOL si no hay Z-Score
                categorized.sort(key=lambda t: t.trades_z_score or t.rvol_slot or t.rvol or 0, reverse=True)
            elif category == ScannerCategory.HIGH_VOLUME:
                categorized.sort(key=lambda t: t.volume_today or 0, reverse=True)
            elif category == ScannerCategory.NEW_HIGHS:
                categorized.sort(key=lambda t: abs(t.price_from_intraday_high if t.price_from_intraday_high is not None else (t.price_from_high if t.price_from_high is not None else 999)))
            elif category == ScannerCategory.NEW_LOWS:
                categorized.sort(key=lambda t: abs(t.price_from_intraday_low if t.price_from_intraday_low is not None else (t.price_from_low if t.price_from_low is not None else 999)))
            elif category == ScannerCategory.REVERSALS:
                categorized.sort(key=lambda t: t.score, reverse=True)
            elif category == ScannerCategory.POST_MARKET:
                # Ordenar por cambio % post-market (mayor movimiento primero, en valor absoluto)
                categorized.sort(key=lambda t: abs(t.postmarket_change_percent or 0), reverse=True)
            
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

