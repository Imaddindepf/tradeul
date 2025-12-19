"""
Base FMP Service
Cliente base para todas las integraciones con Financial Modeling Prep API

NOTA: Usa http_clients.fmp con connection pooling para mejor rendimiento.
"""

import sys
sys.path.append('/app')

from typing import Optional, Dict, Any, List
from shared.utils.logger import get_logger
from http_clients import http_clients

logger = get_logger(__name__)


class BaseFMPService:
    """
    Servicio base para FMP API
    Maneja autenticación, rate limiting y errores comunes
    
    NOTA: Usa cliente HTTP compartido con connection pooling
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        # El cliente HTTP compartido se inicializa en el lifespan de FastAPI
    
    async def _get(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        version: str = "v3"
    ) -> Optional[Any]:
        """
        Hacer GET request a FMP API usando cliente compartido
        
        Args:
            endpoint: Endpoint (sin base URL)
            params: Query parameters
            version: API version ('v3' o 'v4')
        
        Returns:
            Response JSON o None si falla
        """
        # Usar cliente FMP compartido con connection pooling
        return await http_clients.fmp.get(endpoint, params, version)
    
    async def _batch_get(
        self,
        endpoint: str,
        symbols: List[str],
        max_batch_size: int = 100,
        params: Optional[Dict] = None,
        version: str = "v3"
    ) -> Optional[List[Dict]]:
        """
        Hacer batch GET request a FMP API
        
        FMP permite hasta 100 symbols por request en endpoints batch
        
        Args:
            endpoint: Endpoint
            symbols: Lista de symbols
            max_batch_size: Máximo símbolos por batch
            params: Query parameters adicionales
            version: API version
        
        Returns:
            Lista combinada de resultados
        """
        if not symbols:
            return []
        
        # Dividir en batches
        batches = [
            symbols[i:i + max_batch_size]
            for i in range(0, len(symbols), max_batch_size)
        ]
        
        all_results = []
        
        for batch in batches:
            symbols_param = ",".join(batch)
            
            if params is None:
                params = {}
            params['symbols'] = symbols_param
            
            result = await self._get(endpoint, params, version)
            
            if result and isinstance(result, list):
                all_results.extend(result)
        
        return all_results if all_results else None
    
    def _safe_get(self, data: Dict, key: str, default=None):
        """Safely get value from dict"""
        return data.get(key, default)
    
    def _safe_int(self, value: Any) -> Optional[int]:
        """Safely convert to int"""
        try:
            return int(value) if value is not None else None
        except (ValueError, TypeError):
            return None
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert to float"""
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None

