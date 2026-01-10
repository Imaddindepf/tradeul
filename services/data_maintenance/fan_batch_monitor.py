"""
FAN Batch Monitor
==================

Monitorea continuamente durante trading hours para detectar tickers nuevos
en las categorías del scanner y genera automáticamente sus FAN reports
usando Gemini Batch API (50% menos costo).

Funcionalidad:
- Cada 15 minutos revisa categorías del scanner
- Detecta tickers SIN FAN report en Redis
- Agrupa y lanza batch de Gemini
- Guarda resultados en Redis con TTL de 8 horas
"""

import asyncio
import json
import os
import httpx
from datetime import datetime, date
from typing import Set, List, Dict, Any
from zoneinfo import ZoneInfo

import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)

NY_TZ = ZoneInfo("America/New_York")

# Configuración
SCANNER_API_URL = os.getenv('SCANNER_API_URL', 'http://scanner:8005')
GOOGLE_API_KEY = os.getenv('GOOGL_API_KEY', '')
# TTL: 20 horas - cubre todo el día de trading + after hours
# Cleanup real ocurre a las 3 AM ET por data_maintenance
CACHE_TTL_SECONDS = 20 * 60 * 60  # 20 horas
CACHE_PREFIX = "fan:report:"

# Categorías del scanner a monitorear
SCANNER_CATEGORIES = [
    'gappers_up', 'gappers_down',
    'momentum_up', 'momentum_down',
    'anomalies',
    'new_highs', 'new_lows',
    'winners', 'losers',
    'high_volume'
]


class FANBatchMonitor:
    """
    Monitor automático de FAN reports para tickers nuevos.
    
    - Revisa cada 15 minutos
    - Detecta tickers sin FAN en Redis
    - Genera FAN usando Gemini Batch API
    - Guarda en Redis automáticamente
    """
    
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client
        self.is_running = False
        
        # Configuración
        self.check_interval = 900  # 15 minutos
        self.min_new_tickers = 3   # Mínimo para lanzar batch
        self.max_batch_size = 30   # Máximo por batch (reducido de 100 para evitar timeouts)
        
        # Tracking
        self.last_check = None
        self.batches_today = 0
        self.tickers_generated_today: Set[str] = set()
        self.last_batch_job = None
        
        # Gemini client (lazy init)
        self._genai_client = None
    
    @property
    def genai_client(self):
        """Lazy initialization del cliente Gemini"""
        if self._genai_client is None:
            try:
                from google import genai
                self._genai_client = genai.Client(api_key=GOOGLE_API_KEY)
                logger.info("fan_batch_monitor_genai_client_initialized")
            except Exception as e:
                logger.error("fan_batch_monitor_genai_init_failed", error=str(e))
        return self._genai_client
    
    async def start(self):
        """Iniciar monitoreo en background"""
        self.is_running = True
        logger.info(
            "fan_batch_monitor_started",
            interval_seconds=self.check_interval,
            min_tickers=self.min_new_tickers
        )
        
        # Esperar un poco al inicio para que otros servicios estén listos
        await asyncio.sleep(60)
        
        while self.is_running:
            try:
                await self._check_and_generate()
                await asyncio.sleep(self.check_interval)
            
            except asyncio.CancelledError:
                logger.info("fan_batch_monitor_cancelled")
                break
            
            except Exception as e:
                logger.error("fan_batch_monitor_error", error=str(e))
                await asyncio.sleep(300)  # 5 min en error
    
    async def stop(self):
        """Detener monitoreo"""
        self.is_running = False
        logger.info("fan_batch_monitor_stopped")
    
    async def _check_and_generate(self):
        """Revisar tickers nuevos y generar FAN"""
        now = datetime.now(NY_TZ)
        
        # Solo ejecutar en horario de mercado extendido (4 AM - 8 PM ET)
        if not (4 <= now.hour < 20):
            logger.debug("fan_batch_monitor_outside_hours", hour=now.hour)
            return
        
        try:
            logger.info("fan_batch_monitor_checking")
            
            # 1. Obtener todos los tickers de categorías
            all_tickers = await self._get_scanner_tickers()
            if not all_tickers:
                logger.info("fan_batch_no_tickers_in_scanner")
                return
            
            # 2. Obtener tickers con FAN en Redis
            existing_fan = await self._get_existing_fan_tickers()
            
            # 3. Calcular nuevos (sin FAN)
            new_tickers = all_tickers - existing_fan
            
            logger.info(
                "fan_batch_monitor_status",
                total_scanner=len(all_tickers),
                existing_fan=len(existing_fan),
                new_tickers=len(new_tickers)
            )
            
            if len(new_tickers) == 0:
                logger.info("fan_batch_no_new_tickers")
                self.last_check = now
                return
            
            # 4. Si hay suficientes nuevos, generar batch
            if len(new_tickers) >= self.min_new_tickers:
                # Limitar tamaño del batch
                tickers_to_process = list(new_tickers)[:self.max_batch_size]
                
                logger.info(
                    "fan_batch_triggering",
                    count=len(tickers_to_process),
                    tickers=tickers_to_process[:10]  # Log solo primeros 10
                )
                
                # Ejecutar batch
                result = await self._run_batch(tickers_to_process)
                
                if result['success']:
                    self.batches_today += 1
                    self.tickers_generated_today.update(result.get('saved', []))
                    logger.info(
                        "fan_batch_completed",
                        saved=result['saved_count'],
                        errors=result['error_count'],
                        time_seconds=result['time_seconds']
                    )
                else:
                    logger.error("fan_batch_failed", error=result.get('error'))
            
            self.last_check = now
        
        except Exception as e:
            logger.error("fan_batch_check_failed", error=str(e))
    
    async def _get_scanner_tickers(self) -> Set[str]:
        """Obtener todos los tickers de las categorías del scanner"""
        tickers = set()
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for category in SCANNER_CATEGORIES:
                try:
                    response = await client.get(f"{SCANNER_API_URL}/api/categories/{category}")
                    if response.status_code == 200:
                        data = response.json()
                        for ticker_data in data.get('tickers', []):
                            symbol = ticker_data.get('symbol')
                            if symbol:
                                tickers.add(symbol)
                except Exception as e:
                    logger.warning(f"fan_batch_scanner_error", category=category, error=str(e))
        
        return tickers
    
    async def _get_existing_fan_tickers(self) -> Set[str]:
        """Obtener tickers que ya tienen FAN en Redis"""
        tickers = set()
        
        try:
            # Buscar todas las keys de FAN
            keys = await self.redis.client.keys(f"{CACHE_PREFIX}*:es")
            for key in keys:
                # Asegurar que key es string
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                # Extraer ticker de "fan:report:AAPL:es"
                parts = key.split(':')
                if len(parts) >= 3:
                    tickers.add(parts[2])
        except Exception as e:
            logger.error("fan_batch_redis_keys_error", error=str(e))
        
        return tickers
    
    async def _run_batch(self, tickers: List[str]) -> Dict[str, Any]:
        """Ejecutar batch de Gemini para generar FAN"""
        if not self.genai_client:
            return {'success': False, 'error': 'Gemini client not available'}
        
        import time
        t_start = time.time()
        
        try:
            # Crear requests
            requests = []
            for ticker in tickers:
                requests.append({
                    'contents': [{'parts': [{'text': self._create_prompt(ticker)}], 'role': 'user'}],
                    'config': {'tools': [{'google_search': {}}]}
                })
            
            # Crear job (síncrono, ejecutar en thread)
            def create_job():
                return self.genai_client.batches.create(
                    model='gemini-2.0-flash',
                    src=requests,
                    config={'display_name': f'fan-auto-{datetime.now().strftime("%H%M%S")}'}
                )
            
            job = await asyncio.to_thread(create_job)
            
            self.last_batch_job = job.name
            logger.info("fan_batch_job_created", job_name=job.name)
            
            # Esperar completación (con timeout de 20 minutos)
            # Gemini Batch con Google Search puede tardar ~30-60s por ticker
            timeout = 1200
            elapsed = 0
            job_name = job.name
            
            while elapsed < timeout:
                # Get job status (síncrono, ejecutar en thread)
                def get_job_status(name=job_name):
                    return self.genai_client.batches.get(name=name)
                
                job = await asyncio.to_thread(get_job_status)
                state = job.state.name
                
                if state == 'JOB_STATE_SUCCEEDED':
                    break
                elif state in ('JOB_STATE_FAILED', 'JOB_STATE_CANCELLED', 'JOB_STATE_EXPIRED'):
                    return {'success': False, 'error': f'Job failed with state: {state}'}
                
                await asyncio.sleep(10)
                elapsed += 10
            
            if elapsed >= timeout:
                return {'success': False, 'error': 'Batch timeout'}
            
            # Procesar resultados
            saved = []
            errors = []
            
            for i, resp in enumerate(job.dest.inlined_responses):
                ticker = tickers[i]
                if resp.response:
                    try:
                        text = resp.response.text
                        if '```json' in text:
                            text = text.split('```json')[1].split('```')[0]
                        elif '```' in text:
                            text = text.split('```')[1]
                        
                        data = json.loads(text.strip())
                        data['generated_at'] = datetime.utcnow().isoformat()
                        data['source'] = 'batch_auto'
                        
                        # Guardar en Redis
                        cache_key = f"{CACHE_PREFIX}{ticker}:es"
                        await self.redis.client.setex(
                            cache_key, 
                            CACHE_TTL_SECONDS, 
                            json.dumps(data, ensure_ascii=False)
                        )
                        saved.append(ticker)
                    
                    except Exception as e:
                        errors.append(f"{ticker}: {str(e)[:50]}")
                else:
                    errors.append(f"{ticker}: No response")
            
            t_total = time.time() - t_start
            
            return {
                'success': True,
                'saved_count': len(saved),
                'error_count': len(errors),
                'saved': saved,
                'errors': errors,
                'time_seconds': round(t_total, 1)
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _create_prompt(self, ticker: str) -> str:
        """Crear prompt FAN para un ticker"""
        return f'''You are a senior financial analyst at a top investment bank. Generate a COMPREHENSIVE real-time analysis for ticker symbol "{ticker}".

Responde en Español.

⚠️ INSTRUCCIONES CRÍTICAS DE PRECISIÓN:
- NUNCA inventes datos, alucinaciones o información falsa
- USA SOLO fuentes confiables: Yahoo Finance, Bloomberg, Reuters, SEC filings
- Si no encuentras un dato, usa null - NO lo inventes
- Verifica cada dato con múltiples fuentes

CRITICAL: Use Google Search EXTENSIVELY to find real-time data.
Search: "{ticker} stock analyst ratings", "{ticker} price target", "{ticker} short interest"

REQUIRED DATA: Analyst ratings, Price targets, P/E ratio, Short interest, Competitors, Financial health, Earnings date, News sentiment, Risk factors.

Return ONLY valid JSON (no markdown):
{{"ticker": "{ticker}", "company_name": "string", "sector": "string", "industry": "string", "exchange": "string",
"business_summary": "2-3 sentences", "special_status": null,
"consensus_rating": "Buy/Hold/Sell/null", "analyst_ratings": [{{"firm": "string", "rating": "string", "price_target": number}}],
"average_price_target": number, "price_target_high": number, "price_target_low": number, "num_analysts": number,
"pe_ratio": number, "forward_pe": number, "pb_ratio": number, "dividend_yield": number, "ex_dividend_date": "YYYY-MM-DD",
"technical": {{"trend": "Bullish/Bearish/Neutral", "support_level": number, "resistance_level": number, "rsi_status": "string"}},
"short_interest": {{"short_percent_of_float": number, "days_to_cover": number, "squeeze_potential": "Low/Medium/High"}},
"competitors": [{{"ticker": "string", "name": "string"}}],
"financial_health": {{"revenue_growth_yoy": number, "debt_to_equity": number, "roe": number, "profit_margin": number}},
"financial_grade": "A/B/C/D/F",
"earnings_date": "YYYY-MM-DD",
"insider_activity": [{{"type": "Buy/Sell", "title": "string", "value": "string"}}],
"insider_sentiment": "Bullish/Bearish/Neutral",
"news_sentiment": {{"overall": "Bullish/Bearish/Neutral", "recent_headlines": ["string"]}},
"risk_factors": [{{"category": "string", "description": "string", "severity": "Low/Medium/High"}}],
"risk_score": 1-10,
"critical_event": null}}

If data not available, use null. Do NOT make up data.'''
    
    def get_stats(self) -> dict:
        """Estadísticas del monitor"""
        return {
            "is_running": self.is_running,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "batches_today": self.batches_today,
            "tickers_generated_today": len(self.tickers_generated_today),
            "last_batch_job": self.last_batch_job,
            "config": {
                "check_interval_seconds": self.check_interval,
                "min_new_tickers": self.min_new_tickers,
                "max_batch_size": self.max_batch_size
            }
        }
    
    async def force_check(self) -> Dict[str, Any]:
        """Forzar check manual (para API)"""
        logger.info("fan_batch_force_check_triggered")
        await self._check_and_generate()
        return self.get_stats()

