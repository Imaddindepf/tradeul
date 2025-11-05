"""
Hot Ticker Manager

Gestiona la promoción/degradación de tickers entre:
- HOT: Tickers activos en rankings (alta frecuencia de actualización)
- COLD: Universo completo (baja frecuencia de actualización)

Responsabilidades:
- Mantener set de tickers "hot"
- Auto-suscribir hot tickers a Polygon WS
- Auto-desuscribir tickers que salen de rankings
"""

import asyncio
from typing import Set, List, Dict
from datetime import datetime

import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from shared.config.settings import settings

logger = get_logger(__name__)


class HotTickerManager:
    """
    Gestiona tickers "hot" (activos en rankings) vs "cold" (universo completo)
    """
    
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client
        self.hot_tickers: Set[str] = set()
        self.last_hot_update: datetime = datetime.now()
        
        # Estadísticas
        self.stats = {
            "total_promotions": 0,
            "total_degradations": 0,
            "current_hot_count": 0,
            "last_update": None
        }
    
    async def promote_to_hot(self, symbols: List[str]):
        """
        Promociona tickers a hot set
        
        - Auto-suscribe a Polygon WS
        - Añade a hot tracking
        
        Args:
            symbols: Lista de símbolos a promocionar
        """
        if not symbols:
            return
        
        # Filtrar solo los que NO están ya en hot
        new_hot = set(symbols) - self.hot_tickers
        
        if not new_hot:
            return
        
        logger.info(f"Promoting {len(new_hot)} tickers to hot", symbols=list(new_hot)[:10])
        
        # Suscribir a Polygon WS
        for symbol in new_hot:
            try:
                await self.redis.xadd(
                    settings.key_polygon_subscriptions,
                    {
                        'symbol': symbol,
                        'action': 'subscribe',
                        'timestamp': datetime.now().isoformat()
                    }
                )
            except Exception as e:
                logger.error(f"Error subscribing {symbol} to Polygon WS", error=str(e))
        
        # Actualizar set local
        self.hot_tickers.update(new_hot)
        
        # Actualizar estadísticas
        self.stats["total_promotions"] += len(new_hot)
        self.stats["current_hot_count"] = len(self.hot_tickers)
        self.stats["last_update"] = datetime.now().isoformat()
        
        logger.info(
            f"✅ Promoted {len(new_hot)} tickers to hot",
            total_hot=len(self.hot_tickers),
            examples=list(new_hot)[:5]
        )
    
    async def degrade_to_cold(self, symbols: List[str]):
        """
        Degrada tickers a cold set
        
        - Desuscribe de Polygon WS
        - Remueve de hot tracking
        
        Args:
            symbols: Lista de símbolos a degradar
        """
        if not symbols:
            return
        
        # Filtrar solo los que están en hot
        to_degrade = set(symbols) & self.hot_tickers
        
        if not to_degrade:
            return
        
        logger.info(f"Degrading {len(to_degrade)} tickers to cold", symbols=list(to_degrade)[:10])
        
        # Desuscribir de Polygon WS
        for symbol in to_degrade:
            try:
                await self.redis.xadd(
                    settings.key_polygon_subscriptions,
                    {
                        'symbol': symbol,
                        'action': 'unsubscribe',
                        'timestamp': datetime.now().isoformat()
                    }
                )
            except Exception as e:
                logger.error(f"Error unsubscribing {symbol} from Polygon WS", error=str(e))
        
        # Actualizar set local
        self.hot_tickers -= to_degrade
        
        # Actualizar estadísticas
        self.stats["total_degradations"] += len(to_degrade)
        self.stats["current_hot_count"] = len(self.hot_tickers)
        self.stats["last_update"] = datetime.now().isoformat()
        
        logger.info(
            f"❄️ Degraded {len(to_degrade)} tickers to cold",
            total_hot=len(self.hot_tickers),
            examples=list(to_degrade)[:5]
        )
    
    async def update_hot_set(self, current_rankings: Dict[str, List[str]]):
        """
        Actualiza hot set basado en rankings actuales
        
        Promociona tickers que entraron a rankings
        Degrada tickers que salieron de rankings
        
        Args:
            current_rankings: Dict con rankings actuales
                Ejemplo: {
                    'gappers_up': ['TSLA', 'AAPL', ...],
                    'gappers_down': ['NVDA', 'AMD', ...],
                    ...
                }
        """
        # Recopilar TODOS los tickers en TODOS los rankings activos
        all_hot_symbols = set()
        for category_name, symbols in current_rankings.items():
            # Top 20 de cada categoría
            all_hot_symbols.update(symbols[:20])
        
        # Calcular diferencias
        to_promote = all_hot_symbols - self.hot_tickers
        to_degrade = self.hot_tickers - all_hot_symbols
        
        # Ejecutar promociones/degradaciones
        if to_promote:
            await self.promote_to_hot(list(to_promote))
        
        if to_degrade:
            await self.degrade_to_cold(list(to_degrade))
        
        # Log resumen
        if to_promote or to_degrade:
            logger.info(
                "Hot set updated",
                promoted=len(to_promote),
                degraded=len(to_degrade),
                total_hot=len(self.hot_tickers)
            )
        
        self.last_hot_update = datetime.now()
    
    def get_hot_tickers(self) -> List[str]:
        """Retorna lista de tickers hot actuales"""
        return list(self.hot_tickers)
    
    def is_hot(self, symbol: str) -> bool:
        """Verifica si un ticker está en hot set"""
        return symbol in self.hot_tickers
    
    def get_stats(self) -> Dict:
        """Retorna estadísticas del hot ticker manager"""
        return {
            **self.stats,
            "hot_tickers_sample": list(self.hot_tickers)[:20],
            "last_hot_update": self.last_hot_update.isoformat()
        }


