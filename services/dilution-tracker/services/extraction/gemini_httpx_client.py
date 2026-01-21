"""
Cliente Gemini usando httpx directamente.

Motivación: El SDK oficial de Google GenAI usa internamente `requests` (síncrono)
envuelto en asyncio.to_thread, lo que hace que los timeouts de asyncio.wait_for
NO puedan cancelar las operaciones bloqueadas.

Este cliente usa httpx.AsyncClient con timeouts a nivel de socket.
"""

import httpx
import json
import socket
import structlog
from typing import Dict, Any, Optional

logger = structlog.get_logger()

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Configurar timeout a nivel de socket OS (esto SÍ funciona)
socket.setdefaulttimeout(60.0)


class GeminiHttpxClient:
    """Cliente httpx para Gemini que es verdaderamente asíncrono y cancelable."""
    
    def __init__(self, api_key: str, timeout: float = 60.0):
        self.api_key = api_key
        self.timeout = timeout
    
    async def generate_content(
        self,
        model: str,
        contents: list,
        temperature: float = 0.1,
        response_mime_type: str = "application/json"
    ) -> Dict[str, Any]:
        """
        Genera contenido usando la API REST de Gemini.
        Crea un cliente FRESCO por cada llamada para evitar conexiones zombie.
        """
        import time
        start_time = time.time()
        
        # Construir URL
        url = GEMINI_API_URL.format(model=model)
        logger.debug("gemini_httpx_starting", url=url, model=model)
        
        # Construir payload
        parts = []
        for content in contents:
            if isinstance(content, str):
                parts.append({"text": content})
            elif isinstance(content, dict) and "text" in content:
                parts.append(content)
            else:
                parts.append({"text": str(content)})
        
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": response_mime_type
            }
        }
        
        # Crear cliente FRESCO por cada llamada (evita conexiones zombie)
        logger.debug("gemini_httpx_creating_client", timeout=self.timeout)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=self.timeout,
                write=30.0,
                pool=5.0
            ),
            http2=False  # HTTP/1.1 más predecible con timeouts
        ) as client:
            try:
                logger.debug("gemini_httpx_sending_request", url=url, payload_size=len(json.dumps(payload)))
                response = await client.post(
                    url,
                    params={"key": self.api_key},
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                logger.debug("gemini_httpx_response_received", status=response.status_code, elapsed=time.time()-start_time)
                
                if response.status_code == 429:
                    raise Exception("RESOURCE_EXHAUSTED: Rate limit exceeded")
                
                if response.status_code != 200:
                    error_text = response.text[:500]
                    logger.error("gemini_api_error", 
                                status=response.status_code, 
                                error=error_text)
                    raise Exception(f"Gemini API error {response.status_code}: {error_text}")
                
                data = response.json()
                
                # Extraer texto de la respuesta
                candidates = data.get("candidates", [])
                if not candidates:
                    raise Exception("No candidates in Gemini response")
                
                text = ""
                if candidates[0].get("content", {}).get("parts"):
                    text = candidates[0]["content"]["parts"][0].get("text", "")
                
                return {
                    "text": text,
                    "candidates": candidates,
                    "usage_metadata": data.get("usageMetadata", {})
                }
                
            except httpx.TimeoutException as e:
                logger.error("gemini_httpx_timeout", timeout=self.timeout, error=str(e))
                raise
            except httpx.HTTPStatusError as e:
                logger.error("gemini_httpx_http_error", 
                            status=e.response.status_code,
                            error=str(e))
                raise


class GeminiHttpxClientWrapper:
    """
    Wrapper que simula la interfaz del SDK de Google para facilitar el reemplazo.
    """
    
    def __init__(self, api_key: str, timeout_seconds: float = 60.0):
        self._client = GeminiHttpxClient(api_key, timeout=timeout_seconds)
        # UPGRADE: gemini-3-pro-preview es el modelo PRO más potente
        self._default_model = "gemini-2.5-flash"
    
    async def generate_content(
        self,
        model: str,
        contents: list,
        config: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Genera contenido simulando la interfaz del SDK.
        """
        config = config or {}
        
        temperature = config.get("temperature", 0.1)
        response_mime_type = config.get("response_mime_type", "application/json")
        
        return await self._client.generate_content(
            model=model,
            contents=contents,
            temperature=temperature,
            response_mime_type=response_mime_type
        )
    
    async def close(self):
        """Cierra el cliente."""
        pass  # httpx.AsyncClient se cierra automáticamente con el context manager
