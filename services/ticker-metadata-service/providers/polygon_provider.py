"""
Polygon Provider

Cliente para Polygon.io API - obtiene metadatos de tickers.
"""

from typing import Optional, Dict, Any
import httpx

import sys
sys.path.append('/app')

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class PolygonProvider:
    """
    Provider para Polygon.io Ticker Details API
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.polygon.io"
        self.timeout = 10.0
    
    async def get_ticker_details(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene detalles completos de un ticker desde Polygon
        
        Endpoint: GET /v3/reference/tickers/{symbol}
        """
        url = f"{self.base_url}/v3/reference/tickers/{symbol}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url,
                    params={"apiKey": self.api_key}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results")
                    
                    if results:
                        logger.debug("polygon_success", symbol=symbol)
                        return results
                    
                    logger.warning("polygon_no_results", symbol=symbol)
                    return None
                
                elif response.status_code == 429:
                    logger.warning("polygon_rate_limited", symbol=symbol)
                    return None
                
                elif response.status_code == 404:
                    logger.warning("polygon_not_found", symbol=symbol)
                    return None
                
                else:
                    logger.error(
                        "polygon_error",
                        symbol=symbol,
                        status_code=response.status_code
                    )
                    return None
        
        except httpx.TimeoutException:
            logger.error("polygon_timeout", symbol=symbol)
            return None
        
        except Exception as e:
            logger.error("polygon_exception", symbol=symbol, error=str(e))
            return None







