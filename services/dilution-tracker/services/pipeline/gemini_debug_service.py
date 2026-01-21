"""
Gemini Debug Service
====================
Servicio para guardar respuestas raw de Gemini para debugging.

Guarda en Redis:
- La respuesta JSON completa de Gemini
- El prompt enviado (primeros 5000 chars)
- Timestamp
- Metadata del filing

Esto permite diagnosticar falsos positivos/negativos en la extracción.
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# TTL: 2 horas (suficiente para debugging)
DEBUG_TTL = 7200


class GeminiDebugService:
    """
    Guarda respuestas raw de Gemini para debugging.
    """
    
    REDIS_PREFIX = "gemini_debug"
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self._enabled = True  # Puede deshabilitarse para producción
    
    def _get_key(self, ticker: str, step: str, identifier: str) -> str:
        """Genera key de Redis."""
        return f"{self.REDIS_PREFIX}:{ticker}:{step}:{identifier}"
    
    async def save_chain_extraction(
        self,
        ticker: str,
        file_no: str,
        chain_type: str,
        prompt_preview: str,
        raw_response: str,
        parsed_result: Dict,
        filing_urls: list
    ) -> bool:
        """
        Guarda la extracción de una cadena de filings.
        
        Args:
            ticker: Ticker
            file_no: Número de filing (ej: 333-276176)
            chain_type: Tipo de cadena (IPO/Follow-on, Shelf/ATM, etc.)
            prompt_preview: Primeros 5000 chars del prompt
            raw_response: Respuesta raw de Gemini (JSON string)
            parsed_result: Resultado parseado
            filing_urls: URLs de los filings procesados
        """
        if not self._enabled:
            return True
        
        try:
            key = self._get_key(ticker, "chain", file_no.replace("-", ""))
            
            debug_data = {
                "ticker": ticker,
                "file_no": file_no,
                "chain_type": chain_type,
                "timestamp": datetime.utcnow().isoformat(),
                "prompt_preview": prompt_preview[:5000] if prompt_preview else "",
                "raw_response": raw_response[:50000] if raw_response else "",  # Límite 50KB
                "parsed_result_summary": {
                    "warrants": len(parsed_result.get("warrants", [])),
                    "convertible_notes": len(parsed_result.get("convertible_notes", [])),
                    "offerings": len(parsed_result.get("offerings", [])),
                },
                "parsed_warrants": parsed_result.get("warrants", []),  # Guardar warrants completos para debug
                "filing_urls": filing_urls[:10],  # Primeros 10
            }
            
            await self.redis.set(key, debug_data, ttl=DEBUG_TTL, serialize=True)
            
            logger.debug("gemini_debug_saved",
                        ticker=ticker,
                        file_no=file_no,
                        chain_type=chain_type)
            return True
            
        except Exception as e:
            logger.warning("gemini_debug_save_failed", 
                          ticker=ticker, 
                          file_no=file_no,
                          error=str(e))
            return False
    
    async def save_transaction_extraction(
        self,
        ticker: str,
        form_type: str,
        filing_date: str,
        accession_no: str,
        prompt_preview: str,
        raw_response: str,
        parsed_result: Dict
    ) -> bool:
        """
        Guarda la extracción de un filing transaccional (8-K, 10-Q, etc.).
        """
        if not self._enabled:
            return True
        
        try:
            key = self._get_key(ticker, "transaction", accession_no.replace("-", ""))
            
            debug_data = {
                "ticker": ticker,
                "form_type": form_type,
                "filing_date": filing_date,
                "accession_no": accession_no,
                "timestamp": datetime.utcnow().isoformat(),
                "prompt_preview": prompt_preview[:5000] if prompt_preview else "",
                "raw_response": raw_response[:30000] if raw_response else "",  # Límite 30KB
                "parsed_result": parsed_result,
            }
            
            await self.redis.set(key, debug_data, ttl=DEBUG_TTL, serialize=True)
            return True
            
        except Exception as e:
            logger.warning("gemini_debug_save_failed", 
                          ticker=ticker, 
                          accession_no=accession_no,
                          error=str(e))
            return False
    
    async def get_chain_debug(self, ticker: str, file_no: str) -> Optional[Dict]:
        """Recupera datos de debug de una cadena."""
        key = self._get_key(ticker, "chain", file_no.replace("-", ""))
        return await self.redis.get(key, deserialize=True)
    
    async def get_transaction_debug(self, ticker: str, accession_no: str) -> Optional[Dict]:
        """Recupera datos de debug de una transacción."""
        key = self._get_key(ticker, "transaction", accession_no.replace("-", ""))
        return await self.redis.get(key, deserialize=True)
    
    async def get_all_debug_for_ticker(self, ticker: str) -> Dict:
        """Recupera todos los datos de debug para un ticker."""
        # Esto requiere SCAN que puede ser lento, usar con cuidado
        result = {
            "ticker": ticker,
            "chains": [],
            "transactions": []
        }
        
        try:
            # Buscar keys de chains
            chain_pattern = f"{self.REDIS_PREFIX}:{ticker}:chain:*"
            chain_keys = await self.redis.client.keys(chain_pattern)
            
            for key in chain_keys[:10]:  # Límite 10
                data = await self.redis.get(key, deserialize=True)
                if data:
                    result["chains"].append({
                        "file_no": data.get("file_no"),
                        "chain_type": data.get("chain_type"),
                        "warrants_count": data.get("parsed_result_summary", {}).get("warrants", 0),
                        "timestamp": data.get("timestamp"),
                    })
            
            # Buscar keys de transactions
            tx_pattern = f"{self.REDIS_PREFIX}:{ticker}:transaction:*"
            tx_keys = await self.redis.client.keys(tx_pattern)
            
            for key in tx_keys[:20]:  # Límite 20
                data = await self.redis.get(key, deserialize=True)
                if data:
                    result["transactions"].append({
                        "form_type": data.get("form_type"),
                        "filing_date": data.get("filing_date"),
                        "accession_no": data.get("accession_no"),
                        "timestamp": data.get("timestamp"),
                    })
                    
        except Exception as e:
            logger.warning("get_all_debug_failed", ticker=ticker, error=str(e))
        
        return result


# Singleton para uso global
_debug_service: Optional[GeminiDebugService] = None


def get_gemini_debug_service(redis_client) -> GeminiDebugService:
    """Obtiene el servicio de debug (singleton)."""
    global _debug_service
    if _debug_service is None:
        _debug_service = GeminiDebugService(redis_client)
    return _debug_service
