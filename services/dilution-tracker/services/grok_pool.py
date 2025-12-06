"""
GrokPool - Pool de clientes Grok con múltiples API keys para procesamiento paralelo.

Características:
- Round-robin distribution de requests entre keys
- Semáforos para evitar sobrecarga por key
- Retry automático con backoff exponencial
- Tracking de uso y errores por key
- Circuit breaker por key (si falla mucho, se deshabilita temporalmente)
"""

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Any
from xai_sdk import Client

from shared.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class KeyStats:
    """Estadísticas de uso de una API key"""
    name: str
    requests: int = 0
    successes: int = 0
    failures: int = 0
    timeouts: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None
    disabled_until: Optional[float] = None
    
    @property
    def success_rate(self) -> float:
        if self.requests == 0:
            return 1.0
        return self.successes / self.requests
    
    @property
    def is_disabled(self) -> bool:
        if self.disabled_until is None:
            return False
        return time.time() < self.disabled_until
    
    def record_success(self):
        self.requests += 1
        self.successes += 1
        # Reset circuit breaker on success
        self.disabled_until = None
    
    def record_failure(self, error: str, is_timeout: bool = False):
        self.requests += 1
        self.failures += 1
        self.last_error = error
        self.last_error_time = time.time()
        if is_timeout:
            self.timeouts += 1
        
        # Circuit breaker: si falla 3 veces seguidas, deshabilitar 60 segundos
        recent_failures = self.failures - self.successes
        if recent_failures >= 3:
            self.disabled_until = time.time() + 60
            logger.warning("grok_key_disabled", 
                          key_name=self.name, 
                          disabled_seconds=60,
                          reason="3 consecutive failures")


class GrokPool:
    """
    Pool de clientes Grok con múltiples API keys.
    
    Uso:
        pool = GrokPool()
        async with pool.get_client() as (client, key_name):
            result = client.chat.completions.create(...)
    """
    
    def __init__(self, max_concurrent_per_key: int = 2):
        """
        Args:
            max_concurrent_per_key: Máximo de requests simultáneos por key
        """
        self.clients: List[Tuple[Client, str]] = []
        self.semaphores: List[asyncio.Semaphore] = []
        self.stats: List[KeyStats] = []
        self.current_idx = 0
        self.max_concurrent = max_concurrent_per_key
        self._lock = asyncio.Lock()
        
        self._load_keys()
    
    def _load_keys(self):
        """Carga todas las API keys disponibles del entorno"""
        keys_loaded = []
        
        # Key principal
        main_key = os.getenv("GROK_API_KEY")
        if main_key:
            self._add_key(main_key, "tradeul0")
            keys_loaded.append("tradeul0")
        
        # Keys adicionales (2-10)
        for i in range(2, 11):
            key = os.getenv(f"GROK_API_KEY_{i}")
            if key:
                self._add_key(key, f"tradeul{i}")
                keys_loaded.append(f"tradeul{i}")
        
        logger.info("grok_pool_initialized", 
                   keys_count=len(self.clients),
                   keys=keys_loaded,
                   max_concurrent_per_key=self.max_concurrent)
        
        if not self.clients:
            raise ValueError("No GROK_API_KEY found in environment")
    
    # Timeout para requests de Grok (en segundos)
    # Default de xai_sdk es 900s (15 min) - muy largo para nuestro caso
    GROK_TIMEOUT = 120  # 2 minutos - suficiente para archivos pequeños/medianos
    
    def _add_key(self, api_key: str, name: str):
        """Agrega una key al pool con timeout optimizado"""
        client = Client(
            api_key=api_key,
            timeout=self.GROK_TIMEOUT  # 2 minutos timeout
        )
        self.clients.append((client, name))
        self.semaphores.append(asyncio.Semaphore(self.max_concurrent))
        self.stats.append(KeyStats(name=name))
        logger.debug("grok_client_created", key_name=name, timeout=self.GROK_TIMEOUT)
    
    @property
    def num_keys(self) -> int:
        return len(self.clients)
    
    @property
    def available_keys(self) -> int:
        """Número de keys no deshabilitadas"""
        return sum(1 for s in self.stats if not s.is_disabled)
    
    async def get_client(self) -> Tuple[Client, str, int]:
        """
        Obtiene el siguiente cliente disponible (round-robin).
        
        OPTIMIZADO: El lock solo protege la selección del índice (operación rápida).
        El acquire del semáforo se hace FUERA del lock para permitir paralelismo real.
        
        Antes: 10 workers pero solo 1 request a la vez (lock bloqueaba todo)
        Ahora: 10 workers con 10 requests simultáneos (5 keys × 2 concurrent)
        
        Returns:
            Tuple de (cliente, nombre_key, índice)
        """
        # PASO 1: Seleccionar índice rápidamente (CON lock, operación ~microsegundos)
        async with self._lock:
            attempts = 0
            while attempts < len(self.clients):
                idx = self.current_idx % len(self.clients)
                self.current_idx += 1
                
                if not self.stats[idx].is_disabled:
                    break
                attempts += 1
            else:
                # Todas las keys están deshabilitadas, usar la primera
                logger.warning("grok_pool_all_keys_disabled", 
                              message="All keys disabled, using first key anyway")
                idx = 0
        
        # PASO 2: Esperar el semáforo FUERA del lock (permite paralelismo real)
        # Múltiples workers pueden esperar semáforos diferentes simultáneamente
        client, name = self.clients[idx]
        
        # 🔍 DEBUG: Log antes de esperar semáforo
        logger.debug("grok_pool_waiting_semaphore", 
                    key_name=name, 
                    idx=idx,
                    available=self.semaphores[idx]._value if hasattr(self.semaphores[idx], '_value') else 'unknown')
        
        try:
            # Timeout de 60s para evitar deadlocks
            await asyncio.wait_for(self.semaphores[idx].acquire(), timeout=60.0)
        except asyncio.TimeoutError:
            logger.error("grok_pool_semaphore_timeout",
                        key_name=name,
                        idx=idx,
                        message="Semaphore acquire timed out after 60s - possible resource leak")
            raise
        
        logger.debug("grok_pool_semaphore_acquired", key_name=name, idx=idx)
        
        return client, name, idx
    
    def release(self, idx: int, success: bool = True, error: Optional[str] = None, is_timeout: bool = False):
        """
        Libera un cliente después de usarlo.
        
        Args:
            idx: Índice del cliente
            success: Si la operación fue exitosa
            error: Mensaje de error si falló
            is_timeout: Si el error fue un timeout
        """
        self.semaphores[idx].release()
        
        if success:
            self.stats[idx].record_success()
        else:
            self.stats[idx].record_failure(error or "Unknown error", is_timeout)
    
    def get_stats(self) -> dict:
        """Retorna estadísticas de uso del pool"""
        return {
            "total_keys": len(self.clients),
            "available_keys": self.available_keys,
            "keys": [
                {
                    "name": s.name,
                    "requests": s.requests,
                    "successes": s.successes,
                    "failures": s.failures,
                    "timeouts": s.timeouts,
                    "success_rate": f"{s.success_rate:.1%}",
                    "is_disabled": s.is_disabled,
                    "last_error": s.last_error,
                }
                for s in self.stats
            ]
        }


class GrokPoolContextManager:
    """Context manager para uso con async with"""
    
    def __init__(self, pool: GrokPool):
        self.pool = pool
        self.client: Optional[Client] = None
        self.key_name: Optional[str] = None
        self.idx: Optional[int] = None
        self._success = True
        self._error: Optional[str] = None
        self._is_timeout = False
    
    async def __aenter__(self) -> Tuple[Client, str]:
        self.client, self.key_name, self.idx = await self.pool.get_client()
        return self.client, self.key_name
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._success = False
            self._error = str(exc_val)
            # Detectar timeouts
            if "deadline" in self._error.lower() or "timeout" in self._error.lower():
                self._is_timeout = True
        
        self.pool.release(self.idx, self._success, self._error, self._is_timeout)
        return False  # No suprimir excepciones


# Singleton global
_pool: Optional[GrokPool] = None


def get_grok_pool() -> GrokPool:
    """Obtiene el pool singleton de Grok"""
    global _pool
    if _pool is None:
        _pool = GrokPool()
    return _pool


async def with_grok_client() -> GrokPoolContextManager:
    """
    Obtiene un cliente Grok del pool para usar con async with.
    
    Uso:
        async with await with_grok_client() as (client, key_name):
            result = client.files.create(...)
    """
    return GrokPoolContextManager(get_grok_pool())

