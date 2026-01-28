"""
Subscription Manager
Gestiona suscripciones automáticas a Polygon WebSocket basadas en rankings del scanner.

Ventajas:
- Frontend NO gestiona suscripciones manualmente
- Scanner decide QUÉ es relevante → Polygon WS se suscribe
- Tickers que salen del ranking → auto-desuscripción
- Centralizado: 1 suscripción por ticker (no por cliente)
- Eficiente: max 1000 suscripciones a Polygon (límite del plan)
"""

import traceback
from datetime import datetime
from typing import List, Set, Dict, Optional

import sys
sys.path.append('/app')

from shared.models.scanner import ScannerTicker
from shared.enums.market_session import MarketSession
from shared.utils.redis_client import RedisClient
from shared.utils.redis_stream_manager import get_stream_manager
from shared.utils.logger import get_logger
from shared.config.settings import settings

logger = get_logger(__name__)

# Categorías del scanner
ALL_CATEGORY_NAMES = [
    'gappers_up', 'gappers_down', 'momentum_up', 'momentum_down',
    'winners', 'losers', 'high_volume', 'new_highs', 'new_lows',
    'anomalies', 'reversals'
]


class SubscriptionManager:
    """
    Gestiona suscripciones automáticas a Polygon WebSocket.
    
    Uso:
        manager = SubscriptionManager(redis_client)
        await manager.update_subscriptions(tickers, session)
    """
    
    def __init__(self, redis: RedisClient):
        self.redis = redis
        self._previous_symbols: Set[str] = set()
    
    async def get_category_symbols(self) -> tuple[Set[str], Dict[str, int]]:
        """
        Obtiene símbolos de todas las categorías de Redis.
        
        Returns:
            Tuple de (set de símbolos únicos, dict de conteos por categoría)
        """
        category_symbols = set()
        categories_read = {}
        
        for category_name in ALL_CATEGORY_NAMES:
            category_key = f"scanner:category:{category_name}"
            try:
                category_data = await self.redis.get(category_key, deserialize=True)
                if category_data and isinstance(category_data, list):
                    cat_tickers = []
                    for ticker in category_data:
                        if ticker.get('symbol'):
                            category_symbols.add(ticker['symbol'])
                            cat_tickers.append(ticker['symbol'])
                    categories_read[category_name] = len(cat_tickers)
            except Exception as e:
                logger.error(
                    "error_reading_category_for_subscription",
                    category=category_name,
                    error=str(e)
                )
        
        return category_symbols, categories_read
    
    async def publish_subscriptions(
        self,
        symbols: Set[str],
        action: str,
        session: MarketSession
    ) -> None:
        """
        Publica suscripciones/desuscripciones al stream de Polygon WS.
        
        Args:
            symbols: Set de símbolos
            action: "subscribe" o "unsubscribe"
            session: Sesión actual del mercado
        """
        if not symbols:
            return
        
        stream_manager = get_stream_manager()
        for symbol in symbols:
            await stream_manager.xadd(
                settings.key_polygon_subscriptions,
                {
                    "symbol": symbol,
                    "action": action,
                    "source": "scanner_auto",
                    "session": session.value,
                    "timestamp": datetime.now().isoformat()
                }
            )
        
        emoji = "🔔" if action == "subscribe" else "🔕"
        logger.info(
            f"{emoji} Auto-{action} tickers",
            count=len(symbols),
            examples=list(symbols)[:10]
        )
    
    async def save_active_tickers_snapshot(self, symbols: Set[str]) -> None:
        """
        Guarda snapshot de tickers activos en Redis SET.
        
        Usado para inicialización rápida de Polygon WS.
        """
        try:
            logger.info(
                "Intentando guardar snapshot",
                current_symbols_count=len(symbols),
                has_symbols=bool(symbols)
            )
            
            await self.redis.client.delete("polygon_ws:active_tickers")
            
            if symbols:
                result = await self.redis.client.sadd("polygon_ws:active_tickers", *symbols)
                await self.redis.client.expire("polygon_ws:active_tickers", 3600)
                logger.info(
                    "✅ Snapshot de tickers activos guardado",
                    key="polygon_ws:active_tickers",
                    count=len(symbols),
                    sadd_result=result
                )
            else:
                logger.warning("current_symbols está vacío, no se guardará snapshot")
                
        except Exception as e:
            logger.error(
                "Error guardando snapshot de tickers",
                error=str(e),
                traceback=traceback.format_exc()
            )
    
    async def update_subscriptions(
        self,
        tickers: List[ScannerTicker],
        session: MarketSession
    ) -> None:
        """
        Actualiza suscripciones basándose en los tickers filtrados.
        
        Detecta nuevos tickers y tickers removidos, y publica las
        acciones correspondientes al stream de Polygon WS.
        
        Args:
            tickers: Lista de tickers filtrados
            session: Sesión actual del mercado
        """
        try:
            # 1. Obtener símbolos de categorías
            category_symbols, categories_read = await self.get_category_symbols()
            
            logger.info(
                "categories_read_for_subscription",
                categories_with_data=list(categories_read.keys()),
                category_counts=categories_read,
                unique_symbols=len(category_symbols)
            )
            
            # Usar símbolos de categorías, fallback a tickers filtrados
            current_symbols = category_symbols if category_symbols else {t.symbol for t in tickers[:500]}
            
            if not category_symbols:
                logger.warning(
                    "category_symbols_empty_using_fallback",
                    fallback_count=len(current_symbols)
                )
            
            # 2. Detectar cambios
            new_symbols = current_symbols - self._previous_symbols
            removed_symbols = self._previous_symbols - current_symbols
            
            # Debug: detectar falsos removals
            if removed_symbols:
                false_removals = [s for s in removed_symbols if s in category_symbols]
                if false_removals:
                    logger.error(
                        "false_removal_detected",
                        symbols=false_removals,
                        message="Estos tickers están en categorías pero se marcaron como removed"
                    )
            
            # 3. Publicar suscripciones
            await self.publish_subscriptions(new_symbols, "subscribe", session)
            await self.publish_subscriptions(removed_symbols, "unsubscribe", session)
            
            # 4. Actualizar tracking
            self._previous_symbols = current_symbols
            
            # 5. Guardar snapshot
            await self.save_active_tickers_snapshot(current_symbols)
            
            # 6. Log resumen
            logger.info(
                "✅ Auto-subscription actualizada",
                total_active=len(current_symbols),
                new=len(new_symbols),
                removed=len(removed_symbols),
                session=session.value
            )
        
        except Exception as e:
            logger.error("Error en auto-subscription", error=str(e))
    
    def reset(self) -> None:
        """Resetea el tracking de símbolos."""
        self._previous_symbols = set()
