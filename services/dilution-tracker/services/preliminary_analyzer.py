"""
PRELIMINARY DILUTION ANALYZER
=============================
Servicio que usa Gemini con Google Search para análisis preliminar de dilución.
Soporta tanto streaming (terminal real-time) como JSON estructurado.

IMPORTANTE: Este servicio es 100% Gemini (no usa Grok).
"""

import asyncio
import json
import os
from typing import AsyncGenerator, Optional, Dict, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import queue
import threading

import httpx

from shared.utils.logger import get_logger
from prompts.preliminary_analysis_prompt import (
    PRELIMINARY_DILUTION_ANALYSIS_PROMPT,
    TERMINAL_STREAMING_PROMPT,
    TERMINAL_SYSTEM_PROMPT,
    JSON_SYSTEM_PROMPT,
    QUICK_LOOKUP_PROMPT,
)

logger = get_logger(__name__)

# Gemini Configuration - Using Gemini 3 Flash for faster responses in interactive terminal
# (Pro was too slow - 30-60s to start responding)
GEMINI_MODEL = "gemini-3-flash-preview"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Thread pool dedicado para streaming (independiente del event loop principal)
_streaming_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="gemini_stream_")


class PreliminaryAnalyzer:
    """
    Analizador preliminar de dilución usando Gemini con Google Search.
    
    Modos:
    - streaming: Devuelve chunks de texto en tiempo real (formato terminal)
    - json: Devuelve JSON estructurado completo
    - quick: Devuelve análisis rápido en <5 segundos
    """
    
    def __init__(self):
        # Gemini API Key (única key necesaria)
        self.api_key = os.environ.get("GOOGL_API_KEY")
        
        if not self.api_key:
            logger.warning("gemini_api_key_not_configured (GOOGL_API_KEY missing)")
    
    def _stream_gemini_sync(
        self,
        ticker: str,
        prompt: str,
        result_queue: queue.Queue,
        timeout: float = 300.0
    ) -> None:
        """
        Ejecuta streaming de Gemini en un thread separado.
        Gemini streaming devuelve un JSON array con múltiples objetos.
        """
        if not self.api_key:
             result_queue.put(("error", "API key not configured (GOOGL_API_KEY missing)"))
             return

        # URL de Gemini Stream
        gemini_url = f"{GEMINI_API_BASE}/{GEMINI_MODEL}:streamGenerateContent?key={self.api_key}"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Payload de Gemini (Con Google Search y System Prompt)
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "systemInstruction": {
                "parts": [{"text": TERMINAL_SYSTEM_PROMPT}]
            },
            "tools": [{"googleSearch": {}}]
        }
        
        try:
            logger.info("gemini_sync_thread_starting", ticker=ticker, thread=threading.current_thread().name)
            
            with httpx.Client(timeout=timeout) as client:
                with client.stream("POST", gemini_url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        try:
                            error_text = response.read().decode()
                        except:
                            error_text = "Unknown error"
                        logger.error("gemini_api_error", status=response.status_code, body=error_text[:500])
                        result_queue.put(("error", f"Gemini API error: {response.status_code}"))
                        return

                    # Read full response and parse JSON array
                    full_response = ""
                    for chunk in response.iter_bytes():
                        full_response += chunk.decode('utf-8', errors='ignore')
                    
                    # Parse the JSON array
                    try:
                        # Remove leading/trailing whitespace and parse
                        full_response = full_response.strip()
                        
                        # Gemini returns a JSON array like [{...}, {...}, ...]
                        if full_response.startswith('['):
                            chunks = json.loads(full_response)
                        else:
                            # Single object response
                            chunks = [json.loads(full_response)]
                        
                        # Extract text from each chunk
                        for chunk_data in chunks:
                            candidates = chunk_data.get("candidates", [])
                            if candidates:
                                content = candidates[0].get("content", {})
                                parts = content.get("parts", [])
                                for part in parts:
                                    text_chunk = part.get("text", "")
                                    if text_chunk:
                                        result_queue.put(("data", text_chunk))
                        
                    except json.JSONDecodeError as e:
                        logger.error("gemini_json_parse_error", error=str(e), response_preview=full_response[:500])
                        result_queue.put(("error", f"Failed to parse Gemini response: {str(e)}"))
                        return
                    
            result_queue.put(("done", None))
            
        except httpx.TimeoutException:
            result_queue.put(("error", "Analysis timeout. Please try again."))
        except Exception as e:
            logger.error("gemini_stream_unexpected_error", error=str(e))
            result_queue.put(("error", f"Unexpected error: {str(e)}"))

    async def analyze_streaming(
        self,
        ticker: str,
        company_name: str = "",
        timeout: float = 300.0  # Gemini 3 needs more time for deep thinking (5 min)
    ) -> AsyncGenerator[str, None]:
        """
        Genera análisis en streaming para experiencia de terminal real-time.
        
        IMPORTANTE: Usa un thread separado para no bloquearse con el scraping.
        """
        if not self.api_key:
            yield "[ERROR] Gemini API key not configured\n"
            return
        
        if not company_name:
            company_name = ticker
        
        prompt = TERMINAL_STREAMING_PROMPT.format(
            ticker=ticker,
            company_name=company_name
        )
        
        logger.info("preliminary_analysis_streaming_start", ticker=ticker)
        
        # Yield connecting message (diferente al output de Gemini)
        logger.info("preliminary_yielding_header", ticker=ticker)
        yield f"[CONNECTING] Initializing Gemini analysis for {ticker}...\n"
        logger.info("preliminary_header_yielded", ticker=ticker)
        
        # Cola para comunicación thread -> async generator
        result_queue: queue.Queue = queue.Queue()
        
        # Ejecutar streaming en thread separado (NO bloquea el event loop)
        logger.info("preliminary_starting_thread", ticker=ticker)
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(
            _streaming_executor,
            self._stream_gemini_sync,
            ticker,
            prompt,
            result_queue,
            timeout
        )
        logger.info("preliminary_thread_submitted", ticker=ticker)
        
        # Yield chunks mientras el thread está trabajando
        start_time = asyncio.get_event_loop().time()
        max_wait_time = timeout + 10  # Extra buffer
        
        try:
            while True:
                # Esperar un poco y verificar la cola
                await asyncio.sleep(0.05)
                
                # Verificar timeout global
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > max_wait_time:
                    logger.error("preliminary_analysis_global_timeout", ticker=ticker, elapsed=elapsed)
                    yield "\n[ERROR] Analysis timeout exceeded\n"
                    break
                
                try:
                    msg_type, content = result_queue.get_nowait()
                    
                    if msg_type == "data":
                        yield content
                    elif msg_type == "done":
                        logger.info("preliminary_analysis_streaming_complete", ticker=ticker)
                        break
                    elif msg_type == "error":
                        logger.error("preliminary_analysis_error", ticker=ticker, error=content)
                        yield f"\n[ERROR] {content}\n"
                        break
                        
                except queue.Empty:
                    # Verificar si el future terminó (con error)
                    if future.done():
                        try:
                            future.result()  # Esto lanzará excepción si hubo error
                        except Exception as e:
                            logger.error("preliminary_analysis_thread_error", ticker=ticker, error=str(e))
                            yield f"\n[ERROR] Thread error: {str(e)}\n"
                        break
                    continue
                    
        except asyncio.CancelledError:
            logger.warning("preliminary_analysis_cancelled", ticker=ticker)
            raise
    
    async def analyze_json(
        self,
        ticker: str,
        company_name: str = "",
        timeout: float = 45.0
    ) -> Dict[str, Any]:
        """
        Devuelve análisis completo en formato JSON estructurado.
        Ideal para guardar en caché y procesamiento backend.
        """
        if not self.api_key:
            return self._error_response(ticker, "Gemini API key not configured")
        
        if not company_name:
            company_name = ticker
        
        prompt = PRELIMINARY_DILUTION_ANALYSIS_PROMPT.format(
            ticker=ticker,
            company_name=company_name
        )
        
        # URL de Gemini (no streaming)
        gemini_url = f"{GEMINI_API_BASE}/{GEMINI_MODEL}:generateContent?key={self.api_key}"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "systemInstruction": {
                "parts": [{"text": JSON_SYSTEM_PROMPT}]
            },
            "tools": [{"googleSearch": {}}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 3000
            }
        }
        
        logger.info("preliminary_analysis_json_start", ticker=ticker)
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    gemini_url,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                
                data = response.json()
                
                # Extraer contenido de respuesta Gemini
                candidates = data.get("candidates", [])
                if not candidates:
                    return self._error_response(ticker, "No response from Gemini")
                
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if not parts:
                    return self._error_response(ticker, "Empty response from Gemini")
                
                text_content = parts[0].get("text", "")
                
                # Parse JSON from response (handle markdown code blocks)
                parsed = self._parse_json_response(text_content)
                
                # Add metadata
                parsed["_metadata"] = {
                    "source": "gemini_preliminary_analysis",
                    "analyzed_at": datetime.utcnow().isoformat(),
                    "is_preliminary": True,
                    "full_analysis_status": "pending"
                }
                
                logger.info("preliminary_analysis_json_complete", 
                           ticker=ticker,
                           risk_score=parsed.get("dilution_risk_score"))
                
                return parsed
                
        except httpx.TimeoutException:
            logger.error("preliminary_analysis_json_timeout", ticker=ticker)
            return self._error_response(ticker, "Analysis timeout")
        except httpx.HTTPStatusError as e:
            logger.error("preliminary_analysis_json_http_error",
                        ticker=ticker,
                        status_code=e.response.status_code)
            return self._error_response(ticker, f"API error: {e.response.status_code}")
        except Exception as e:
            logger.error("preliminary_analysis_json_error", ticker=ticker, error=str(e))
            return self._error_response(ticker, str(e))
    
    async def quick_lookup(
        self,
        ticker: str,
        timeout: float = 15.0
    ) -> Dict[str, Any]:
        """
        Búsqueda ultra-rápida para obtener nivel de riesgo en <5 segundos.
        Útil para mostrar mientras carga el análisis completo.
        """
        if not self.api_key:
            return {"ticker": ticker, "quick_risk_level": "UNKNOWN", "data_found": False}
        
        prompt = QUICK_LOOKUP_PROMPT.format(ticker=ticker)
        
        # URL de Gemini (no streaming)
        gemini_url = f"{GEMINI_API_BASE}/{GEMINI_MODEL}:generateContent?key={self.api_key}"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "systemInstruction": {
                "parts": [{"text": JSON_SYSTEM_PROMPT}]
            },
            "tools": [{"googleSearch": {}}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 500
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    gemini_url,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                
                data = response.json()
                
                # Extraer contenido de respuesta Gemini
                candidates = data.get("candidates", [])
                if not candidates:
                    return {"ticker": ticker, "quick_risk_level": "UNKNOWN", "data_found": False}
                
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if not parts:
                    return {"ticker": ticker, "quick_risk_level": "UNKNOWN", "data_found": False}
                
                text_content = parts[0].get("text", "")
                return self._parse_json_response(text_content)
                
        except Exception as e:
            logger.error("quick_lookup_error", ticker=ticker, error=str(e))
            return {
                "ticker": ticker,
                "quick_risk_level": "UNKNOWN",
                "one_liner": "Unable to fetch quick analysis",
                "data_found": False
            }
    
    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """Parse JSON from Gemini response, handling markdown code blocks."""
        cleaned = content.strip()
        
        # Remove markdown code blocks if present
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first and last lines (```json and ```)
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error("json_parse_error", error=str(e), content=cleaned[:500])
            return {
                "error": "Failed to parse JSON response",
                "raw_content": cleaned[:1000]
            }
    
    def _error_response(self, ticker: str, error_message: str) -> Dict[str, Any]:
        """Generate error response structure."""
        return {
            "ticker": ticker,
            "error": error_message,
            "dilution_risk_score": None,
            "dilution_risk_level": "UNKNOWN",
            "executive_summary": f"Unable to analyze {ticker}: {error_message}",
            "confidence_level": "LOW",
            "data_quality": {
                "completeness": "LOW",
                "reliability": "LOW",
                "limitations": error_message
            },
            "_metadata": {
                "source": "gemini_preliminary_analysis",
                "analyzed_at": datetime.utcnow().isoformat(),
                "is_preliminary": True,
                "error": True
            }
        }


# Singleton instance
_analyzer: Optional[PreliminaryAnalyzer] = None

def get_preliminary_analyzer() -> PreliminaryAnalyzer:
    """Get singleton instance of PreliminaryAnalyzer."""
    global _analyzer
    if _analyzer is None:
        _analyzer = PreliminaryAnalyzer()
    return _analyzer
