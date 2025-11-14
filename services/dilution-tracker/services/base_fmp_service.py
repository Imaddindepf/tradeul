"""
Base FMP Service
Cliente base para todas las integraciones con Financial Modeling Prep API
"""

import sys
sys.path.append('/app')

import httpx
from typing import Optional, Dict, Any, List
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class BaseFMPService:
    """
    Servicio base para FMP API
    Maneja autenticación, rate limiting y errores comunes
    """
    
    BASE_URL_V3 = "https://financialmodelingprep.com/api/v3"
    BASE_URL_V4 = "https://financialmodelingprep.com/api/v4"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.timeout = 30.0
    
    async def _get(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        version: str = "v3"
    ) -> Optional[Any]:
        """
        Hacer GET request a FMP API
        
        Args:
            endpoint: Endpoint (sin base URL)
            params: Query parameters
            version: API version ('v3' o 'v4')
        
        Returns:
            Response JSON o None si falla
        """
        base_url = self.BASE_URL_V4 if version == "v4" else self.BASE_URL_V3
        url = f"{base_url}/{endpoint}"
        
        # Agregar API key a params
        if params is None:
            params = {}
        params['apikey'] = self.api_key
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # FMP a veces retorna {"Error Message": "..."}
                    if isinstance(data, dict) and "Error Message" in data:
                        logger.warning(
                            "fmp_error_response",
                            endpoint=endpoint,
                            error=data["Error Message"]
                        )
                        return None
                    
                    logger.debug("fmp_success", endpoint=endpoint)
                    return data
                
                elif response.status_code == 429:
                    logger.warning("fmp_rate_limited", endpoint=endpoint)
                    return None
                
                elif response.status_code == 404:
                    logger.warning("fmp_not_found", endpoint=endpoint)
                    return None
                
                else:
                    logger.error(
                        "fmp_error",
                        endpoint=endpoint,
                        status_code=response.status_code
                    )
                    return None
                    
        except httpx.TimeoutException:
            logger.error("fmp_timeout", endpoint=endpoint)
            return None
        
        except Exception as e:
            logger.error("fmp_exception", endpoint=endpoint, error=str(e))
            return None
    
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

