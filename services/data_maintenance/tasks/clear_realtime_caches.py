"""
Clear Realtime Caches Task
Limpia caches en memoria a las 3:00 AM (1h antes del pre-market)
"""

import sys
sys.path.append('/app')

from datetime import date, datetime, time
from typing import Dict
import httpx
from zoneinfo import ZoneInfo

from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class ClearRealtimeCachesTask:
    """
    Tarea: Limpiar caches en memoria al cambio de día
    
    Esta tarea se ejecuta al inicio de cada día de trading (durante pre-market)
    para asegurar que los servicios en tiempo real no mantengan datos del día anterior.
    
    Métodos de limpieza:
    1. Publicar evento en Redis Pub/Sub (servicios suscritos lo reciben)
    2. Reiniciar contenedores si es necesario (último recurso)
    """
    
    name = "clear_realtime_caches"
    
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client
    
    async def execute(self, target_date: date) -> Dict:
        """
        Ejecutar limpieza de caches en tiempo real
        
        Args:
            target_date: Fecha del nuevo día de trading
        
        Returns:
            Dict con resultados de la limpieza
        """
        try:
            logger.info(
                "clear_caches_task_starting",
                target_date=str(target_date),
                reason="new_trading_day"
            )
            
            results = {
                "success": True,
                "target_date": str(target_date),
                "caches_cleared": [],
                "services_notified": [],
                "errors": []
            }
            
            # 1. Publicar evento de cambio de día en Redis Pub/Sub
            # Los servicios suscritos recibirán este mensaje y limpiarán sus caches
            try:
                await self._publish_new_day_event(target_date)
                results["services_notified"].append("redis_pubsub")
                logger.info(
                    "new_day_event_published",
                    channel="trading:new_day",
                    date=str(target_date)
                )
            except Exception as e:
                error_msg = f"Failed to publish new day event: {str(e)}"
                results["errors"].append(error_msg)
                logger.error("pubsub_publish_failed", error=str(e))
            
            # 2. Limpiar caches específicos en Redis (si existen)
            # Estos son caches que sabemos que deben resetearse cada día
            try:
                cleared_count = await self._clear_redis_day_caches(target_date)
                results["caches_cleared"].append({
                    "type": "redis_day_caches",
                    "count": cleared_count
                })
                logger.info(
                    "redis_day_caches_cleared",
                    count=cleared_count
                )
            except Exception as e:
                error_msg = f"Failed to clear Redis day caches: {str(e)}"
                results["errors"].append(error_msg)
                logger.error("redis_clear_failed", error=str(e))
            
            # 3. Notificar al WebSocket Server vía HTTP endpoint (si existe)
            # Esto es un fallback si el servicio no está suscrito a Pub/Sub
            try:
                ws_notified = await self._notify_websocket_server(target_date)
                if ws_notified:
                    results["services_notified"].append("websocket_server")
                    logger.info("websocket_server_notified", date=str(target_date))
            except Exception as e:
                # No es crítico si falla, el Pub/Sub debería funcionar
                logger.warning(
                    "websocket_notification_failed",
                    error=str(e),
                    note="Service should receive pub/sub event instead"
                )
            
            # Log final
            if results["errors"]:
                results["success"] = False
                logger.warning(
                    "clear_caches_completed_with_errors",
                    errors_count=len(results["errors"]),
                    errors=results["errors"]
                )
            else:
                logger.info(
                    "clear_caches_task_completed",
                    services_notified=len(results["services_notified"]),
                    caches_cleared=len(results["caches_cleared"])
                )
            
            return results
        
        except Exception as e:
            logger.error("clear_caches_task_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "target_date": str(target_date)
            }
    
    async def _publish_new_day_event(self, target_date: date):
        """
        Publicar evento de nuevo día en Redis Pub/Sub
        
        Los servicios interesados deben suscribirse al canal 'trading:new_day'
        """
        message = {
            "event": "new_trading_day",
            "date": target_date.isoformat(),
            "timestamp": target_date.isoformat(),
            "action": "clear_caches"
        }
        
        # Publicar en canal Redis Pub/Sub
        import json
        await self.redis.client.publish(
            "trading:new_day",
            json.dumps(message)
        )
        
        logger.info(
            "new_day_event_published_to_channel",
            channel="trading:new_day",
            date=str(target_date)
        )
    
    async def _clear_redis_day_caches(self, target_date: date) -> int:
        """
        Limpiar caches específicos en Redis que son del día anterior
        
        Estos son keys que sabemos que contienen datos del día y deben resetearse:
        - Cualquier cache temporal relacionado al día de trading
        """
        cleared = 0
        
        # Patrón de keys que podrían ser del día anterior
        # Por ahora no hay keys específicas, pero podemos agregar según necesidad
        patterns_to_check = [
            # Scanner caches - DEBEN limpiarse cada día
            "scanner:filtered_complete:*",
            "scanner:category:*",
            "scanner:sequence:*",
            # Snapshot enriched del día anterior
            "snapshot:enriched:*",
        ]
        
        for pattern in patterns_to_check:
            try:
                deleted = await self.redis.delete_pattern(pattern)
                cleared += deleted
                if deleted > 0:
                    logger.info(
                        "redis_pattern_cleared",
                        pattern=pattern,
                        deleted=deleted
                    )
            except Exception as e:
                logger.error(
                    "pattern_clear_failed",
                    pattern=pattern,
                    error=str(e)
                )
        
        return cleared
    
    async def _notify_websocket_server(self, target_date: date) -> bool:
        """
        Notificar al WebSocket Server vía HTTP endpoint (fallback)
        
        El WebSocket Server debería tener un endpoint /api/clear-cache
        que limpia su cache en memoria cuando se llama.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    "http://websocket_server:9000/api/clear-cache",
                    json={
                        "reason": "new_trading_day",
                        "date": target_date.isoformat()
                    }
                )
                
                if response.status_code == 200:
                    logger.info(
                        "websocket_cache_cleared_via_http",
                        status=response.status_code,
                        date=str(target_date)
                    )
                    return True
                else:
                    logger.warning(
                        "websocket_cache_clear_unexpected_response",
                        status=response.status_code,
                        response=response.text[:200]
                    )
                    return False
        
        except httpx.ConnectError:
            # Endpoint no existe, normal si el servicio no lo implementó aún
            logger.debug(
                "websocket_clear_cache_endpoint_not_available",
                note="Service should use pub/sub instead"
            )
            return False
        except Exception as e:
            logger.warning(
                "websocket_notification_error",
                error=str(e)
            )
            return False

