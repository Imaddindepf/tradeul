"""
Redis Stream Manager con Auto-Trimming
Gestiona streams de Redis con límites automáticos para evitar memory leaks
"""

import asyncio
from typing import Dict, Optional, Any, List
from datetime import datetime
import structlog

from .redis_client import RedisClient

logger = structlog.get_logger(__name__)


class RedisStreamManager:
    """
    Manager automático para Redis Streams con trimming inteligente
    
    Features:
    - MAXLEN automático en cada XADD
    - Background trimming para cleanup
    - Configuración centralizada de límites
    - Métricas de uso
    """
    
    # Configuración de límites por stream
    STREAM_CONFIGS = {
        "snapshots:raw": {
            "maxlen": 1000,           # Solo últimos 1000 (~5 min @ 3/sec)
            "trim_threshold": 1200,   # Trim cuando supere 1200
            "trim_interval": 30,      # Check cada 30s
            "approximate": True,      # Trim aproximado (más rápido)
        },
        "stream:ranking:deltas": {
            "maxlen": 5000,           # Buffer de 1 hora @ 1/sec
            "trim_threshold": 6000,
            "trim_interval": 60,
            "approximate": True,
        },
        "stream:realtime:aggregates": {
            "maxlen": 3000,
            "trim_threshold": 4000,
            "trim_interval": 45,
            "approximate": True,
        },
        "tickers:filtered": {
            "maxlen": 500,            # Solo snapshot actual
            "trim_threshold": 600,
            "trim_interval": 20,
            "approximate": True,
        },
        "events:session": {
            "maxlen": 100,            # Pocos eventos de sesión
            "trim_threshold": 150,
            "trim_interval": 60,
            "approximate": True,
        },
        "polygon_ws:subscriptions": {
            "maxlen": 2000,           # Solo últimos 2000 mensajes (suficiente para estado actual)
            "trim_threshold": 2500,   # Trim cuando supere 2500
            "trim_interval": 60,      # Check cada 60s
            "approximate": True,      # Trim aproximado (más rápido)
        }
    }
    
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client
        self._trim_tasks: Dict[str, asyncio.Task] = {}
        self._is_running = False
        
        # Métricas
        self.stats = {
            "adds": 0,
            "trims": 0,
            "bytes_trimmed": 0
        }
    
    async def start(self):
        """
        Inicia el manager y sus tareas de background
        Se llama automáticamente al iniciar el servicio
        """
        if self._is_running:
            logger.warning("redis_stream_manager_already_running")
            return
        
        self._is_running = True
        
        # Iniciar trim loops para cada stream configurado
        for stream_name, config in self.STREAM_CONFIGS.items():
            task = asyncio.create_task(
                self._trim_loop(stream_name, config),
                name=f"trim_{stream_name}"
            )
            self._trim_tasks[stream_name] = task
        
        logger.info(
            "redis_stream_manager_started",
            streams=list(self.STREAM_CONFIGS.keys()),
            task_count=len(self._trim_tasks)
        )
    
    async def stop(self):
        """
        Detiene todas las tareas de trimming
        Se llama automáticamente al apagar el servicio
        """
        self._is_running = False
        
        # Cancelar todas las tareas
        for stream_name, task in self._trim_tasks.items():
            task.cancel()
            logger.debug("trim_task_cancelled", stream=stream_name)
        
        # Esperar a que terminen
        if self._trim_tasks:
            await asyncio.gather(
                *self._trim_tasks.values(),
                return_exceptions=True
            )
        
        self._trim_tasks.clear()
        logger.info("redis_stream_manager_stopped")
    
    async def xadd(
        self,
        stream: str,
        data: Dict[str, Any],
        maxlen: Optional[int] = None
    ) -> str:
        """
        XADD con MAXLEN automático basado en configuración
        
        Args:
            stream: Nombre del stream
            data: Datos a agregar
            maxlen: Override del maxlen (opcional)
        
        Returns:
            Message ID generado
        """
        config = self.STREAM_CONFIGS.get(stream)
        
        # Usar maxlen de config si no se especificó
        if maxlen is None and config:
            maxlen = config["maxlen"]
        
        # XADD con MAXLEN automático
        try:
            message_id = await self.redis.xadd(
                stream,
                data,
                maxlen=maxlen,
                approximate=config.get("approximate", True) if config else True
            )
            
            self.stats["adds"] += 1
            
            return message_id
            
        except Exception as e:
            logger.error(
                "xadd_failed",
                stream=stream,
                error=str(e),
                data_keys=list(data.keys())
            )
            raise
    
    async def _trim_loop(self, stream_name: str, config: Dict[str, Any]):
        """
        Loop de background que monitorea y trim un stream
        Se ejecuta automáticamente mientras el servicio está activo
        """
        interval = config["trim_interval"]
        threshold = config["trim_threshold"]
        maxlen = config["maxlen"]
        
        logger.info(
            "trim_loop_started",
            stream=stream_name,
            interval=interval,
            threshold=threshold,
            maxlen=maxlen
        )
        
        while self._is_running:
            try:
                # Obtener longitud actual del stream
                length = await self.redis.xlen(stream_name)
                
                # Trim si superó el threshold
                if length > threshold:
                    trimmed = await self.redis.xtrim(
                        stream_name,
                        maxlen=maxlen,
                        approximate=config.get("approximate", True)
                    )
                    
                    self.stats["trims"] += 1
                    self.stats["bytes_trimmed"] += trimmed
                    
                    logger.info(
                        "stream_trimmed",
                        stream=stream_name,
                        old_length=length,
                        new_length=maxlen,
                        trimmed_count=trimmed,
                        threshold=threshold
                    )
                
                # Esperar hasta el próximo check
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                logger.info("trim_loop_cancelled", stream=stream_name)
                break
                
            except Exception as e:
                logger.error(
                    "trim_loop_error",
                    stream=stream_name,
                    error=str(e),
                    exc_info=True
                )
                # Esperar antes de reintentar
                await asyncio.sleep(5)
    
    async def get_stream_info(self, stream: str) -> Dict[str, Any]:
        """
        Obtiene información del stream
        """
        try:
            length = await self.redis.xlen(stream)
            config = self.STREAM_CONFIGS.get(stream, {})
            
            return {
                "stream": stream,
                "length": length,
                "maxlen": config.get("maxlen"),
                "threshold": config.get("threshold"),
                "usage_percent": (length / config.get("maxlen", 1)) * 100 if config.get("maxlen") else None
            }
        except Exception as e:
            logger.error("get_stream_info_failed", stream=stream, error=str(e))
            return {"stream": stream, "error": str(e)}
    
    async def get_all_streams_info(self) -> List[Dict[str, Any]]:
        """
        Obtiene información de todos los streams configurados
        """
        infos = []
        for stream_name in self.STREAM_CONFIGS.keys():
            info = await self.get_stream_info(stream_name)
            infos.append(info)
        return infos
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estadísticas del manager
        """
        return {
            "is_running": self._is_running,
            "active_trim_tasks": len(self._trim_tasks),
            "total_adds": self.stats["adds"],
            "total_trims": self.stats["trims"],
            "bytes_trimmed": self.stats["bytes_trimmed"],
            "configured_streams": len(self.STREAM_CONFIGS)
        }


# Instancia global (se inicializa en cada servicio)
_stream_manager: Optional[RedisStreamManager] = None


def get_stream_manager() -> RedisStreamManager:
    """
    Obtiene la instancia global del stream manager
    """
    global _stream_manager
    if _stream_manager is None:
        raise RuntimeError(
            "RedisStreamManager not initialized. "
            "Call initialize_stream_manager() first."
        )
    return _stream_manager


def initialize_stream_manager(redis_client: RedisClient) -> RedisStreamManager:
    """
    Inicializa la instancia global del stream manager
    Se llama una vez al inicio del servicio
    """
    global _stream_manager
    if _stream_manager is not None:
        logger.warning("stream_manager_already_initialized")
        return _stream_manager
    
    _stream_manager = RedisStreamManager(redis_client)
    return _stream_manager

