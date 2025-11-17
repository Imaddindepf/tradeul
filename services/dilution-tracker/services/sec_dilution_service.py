"""
SEC Dilution Service
Servicio principal para scraping SEC EDGAR + análisis con Grok API + caché
"""

import sys
sys.path.append('/app')

import httpx
import json
import re
import asyncio
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from decimal import Decimal
from bs4 import BeautifulSoup

from xai_sdk import Client
from xai_sdk.chat import user, system

from shared.utils.timescale_client import TimescaleClient
from shared.utils.redis_client import RedisClient
from shared.config.settings import settings
from shared.utils.logger import get_logger

from models.sec_dilution_models import (
    SECDilutionProfile,
    WarrantModel,
    ATMOfferingModel,
    ShelfRegistrationModel,
    CompletedOfferingModel,
    DilutionProfileMetadata
)
from repositories.sec_dilution_repository import SECDilutionRepository

logger = get_logger(__name__)


class SECDilutionService:
    """
    Servicio principal para análisis de dilución SEC
    
    Flujo:
    1. Chequear Redis (caché L1)
    2. Chequear PostgreSQL (caché L2)
    3. Si no existe -> scraping SEC + Grok API
    4. Guardar en PostgreSQL + Redis
    """
    
    # Constantes
    REDIS_KEY_PREFIX = "sec_dilution:profile"
    REDIS_TTL = 86400  # 24 horas
    SEC_EDGAR_BASE_URL = "https://data.sec.gov"
    SEC_RATE_LIMIT_DELAY = 0.2  # 200ms entre requests (5 req/seg - más conservador)
    MAX_CONCURRENT_SCRAPES = 2  # Máximo 2 scrapes simultáneos
    
    def __init__(self, db: TimescaleClient, redis: RedisClient):
        self.db = db
        self.redis = redis
        self.repository = SECDilutionRepository(db)
        self.grok_api_key = settings.GROK_API_KEY
        
        # Semáforo global para limitar requests concurrentes a SEC
        self._sec_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_SCRAPES)
        
        if not self.grok_api_key:
            logger.warning("grok_api_key_not_configured")
    
    async def _acquire_ticker_lock(self, ticker: str, timeout: int = 300) -> bool:
        """
        Adquirir lock distribuido en Redis para un ticker
        
        Usa SETNX con TTL para garantizar que solo un proceso puede scrapear
        el mismo ticker simultáneamente, incluso con múltiples workers.
        
        Args:
            ticker: Ticker symbol
            timeout: Tiempo máximo de espera en segundos (default 5 minutos)
            
        Returns:
            True si adquirió el lock, False si otro proceso ya lo tiene
        """
        lock_key = f"sec_dilution:lock:{ticker}"
        lock_value = f"{id(self)}:{datetime.now().isoformat()}"  # Identificador único
        
        # Intentar adquirir lock con SETNX (SET if Not eXists)
        # Usar el cliente Redis directamente para SETNX + EXPIRE
        try:
            # SETNX: solo establece si la key no existe
            acquired = await self.redis.client.setnx(lock_key, lock_value)
            
            if acquired:
                # Si adquirimos el lock, establecer TTL de 10 minutos
                await self.redis.client.expire(lock_key, 600)
                logger.debug("ticker_lock_acquired", ticker=ticker, lock_key=lock_key)
                return True
            else:
                logger.debug("ticker_lock_busy", ticker=ticker, lock_key=lock_key)
                return False
        except Exception as e:
            logger.error("ticker_lock_acquire_failed", ticker=ticker, error=str(e))
            return False
    
    async def _release_ticker_lock(self, ticker: str) -> bool:
        """
        Liberar lock distribuido en Redis
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            True si se liberó correctamente
        """
        lock_key = f"sec_dilution:lock:{ticker}"
        try:
            await self.redis.delete(lock_key)
            logger.debug("ticker_lock_released", ticker=ticker, lock_key=lock_key)
            return True
        except Exception as e:
            logger.error("ticker_lock_release_failed", ticker=ticker, error=str(e))
            return False
    
    async def get_dilution_profile(
        self, 
        ticker: str, 
        force_refresh: bool = False
    ) -> Optional[SECDilutionProfile]:
        """
        Obtener perfil de dilución para un ticker
        
        Estrategia de caché:
        1. Redis (instantáneo)
        2. PostgreSQL (rápido)
        3. Scraping + Grok (lento, solo si necesario)
        
        Args:
            ticker: Ticker symbol
            force_refresh: Forzar re-scraping ignorando caché
            
        Returns:
            SECDilutionProfile o None si falla
        """
        try:
            ticker = ticker.upper()
            
            # 1. Intentar desde Redis
            if not force_refresh:
                cached_profile = await self._get_from_redis(ticker)
                if cached_profile:
                    logger.info("dilution_profile_from_redis", ticker=ticker)
                    return cached_profile
            
            # 2. Intentar desde PostgreSQL
            if not force_refresh:
                db_profile = await self.repository.get_profile(ticker)
                if db_profile:
                    logger.info("dilution_profile_from_db", ticker=ticker)
                    # Cachear en Redis para próximas consultas
                    await self._save_to_redis(ticker, db_profile)
                    return db_profile
            
            # 3. No existe o force_refresh -> scraping completo
            # Usar lock distribuido en Redis para evitar múltiples scrapes simultáneos
            # (funciona incluso con múltiples workers/instancias)
            lock_acquired = await self._acquire_ticker_lock(ticker)
            
            if not lock_acquired:
                # Otro proceso ya está scrapeando este ticker
                # Esperar un poco y verificar si ya terminó
                logger.info("ticker_scraping_in_progress", ticker=ticker, action="waiting_for_other_process")
                await asyncio.sleep(2.0)  # Esperar 2 segundos
                
                # Verificar si ya se completó
                cached_profile = await self._get_from_redis(ticker)
                if cached_profile:
                    logger.info("dilution_profile_from_redis_after_wait", ticker=ticker)
                    return cached_profile
                
                db_profile = await self.repository.get_profile(ticker)
                if db_profile:
                    logger.info("dilution_profile_from_db_after_wait", ticker=ticker)
                    await self._save_to_redis(ticker, db_profile)
                    return db_profile
                
                # Si aún no hay datos, devolver None (el otro proceso lo completará)
                logger.warning("ticker_scraping_still_in_progress", ticker=ticker)
                return None
            
            try:
                # Verificar nuevamente caché después de adquirir lock (otro request pudo haberlo completado)
                if not force_refresh:
                    cached_profile = await self._get_from_redis(ticker)
                    if cached_profile:
                        logger.info("dilution_profile_from_redis_after_lock", ticker=ticker)
                        await self._release_ticker_lock(ticker)
                        return cached_profile
                    
                    db_profile = await self.repository.get_profile(ticker)
                    if db_profile:
                        logger.info("dilution_profile_from_db_after_lock", ticker=ticker)
                        await self._save_to_redis(ticker, db_profile)
                        await self._release_ticker_lock(ticker)
                        return db_profile
                
                logger.info("dilution_profile_scraping_required", ticker=ticker, force_refresh=force_refresh)
                
                # Usar semáforo global para limitar requests concurrentes a SEC
                async with self._sec_semaphore:
                    profile = await self._scrape_and_analyze(ticker)
                
                if not profile:
                    logger.error("dilution_profile_scraping_failed", ticker=ticker)
                    await self._release_ticker_lock(ticker)
                    return None
                
                # 4. Guardar en PostgreSQL
                await self.repository.save_profile(profile)
                
                # 5. Guardar en Redis
                await self._save_to_redis(ticker, profile)
                
                logger.info("dilution_profile_created", ticker=ticker)
                return profile
                
            finally:
                # Siempre liberar el lock, incluso si hay error
                await self._release_ticker_lock(ticker)
            
        except Exception as e:
            logger.error("get_dilution_profile_failed", ticker=ticker, error=str(e))
            return None
    
    async def invalidate_cache(self, ticker: str) -> bool:
        """
        Invalidar caché Redis para un ticker
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            True si se invalidó correctamente
        """
        try:
            redis_key = f"{self.REDIS_KEY_PREFIX}:{ticker.upper()}"
            await self.redis.delete(redis_key)
            logger.info("cache_invalidated", ticker=ticker)
            return True
        except Exception as e:
            logger.error("cache_invalidation_failed", ticker=ticker, error=str(e))
            return False
    
    # ========================================================================
    # MÉTODOS DE CACHÉ (REDIS)
    # ========================================================================
    
    async def _get_from_redis(self, ticker: str) -> Optional[SECDilutionProfile]:
        """Obtener profile desde Redis"""
        try:
            redis_key = f"{self.REDIS_KEY_PREFIX}:{ticker}"
            cached_data = await self.redis.get(redis_key, deserialize=True)
            
            if not cached_data:
                return None
            
            # Deserializar a modelo
            return SECDilutionProfile(**cached_data)
            
        except Exception as e:
            logger.error("redis_get_failed", ticker=ticker, error=str(e))
            return None
    
    async def _save_to_redis(self, ticker: str, profile: SECDilutionProfile) -> bool:
        """Guardar profile en Redis"""
        try:
            redis_key = f"{self.REDIS_KEY_PREFIX}:{ticker}"
            
            # Serializar modelo a dict
            profile_dict = profile.dict()
            
            # Convertir Decimal a float para JSON
            profile_dict = self._serialize_for_redis(profile_dict)
            
            # Guardar en Redis con TTL
            await self.redis.set(
                redis_key,
                profile_dict,
                ttl=self.REDIS_TTL,
                serialize=True
            )
            
            logger.info("redis_save_success", ticker=ticker)
            return True
            
        except Exception as e:
            logger.error("redis_save_failed", ticker=ticker, error=str(e))
            return False
    
    def _serialize_for_redis(self, data: Any) -> Any:
        """Convertir Decimals, dates y datetimes a JSON-serializable"""
        from datetime import date
        
        if isinstance(data, dict):
            return {k: self._serialize_for_redis(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._serialize_for_redis(item) for item in data]
        elif isinstance(data, Decimal):
            return float(data)
        elif isinstance(data, datetime):
            return data.isoformat()
        elif isinstance(data, date):
            return data.isoformat()
        else:
            return data
    
    # ========================================================================
    # SCRAPING + GROK API (CORE LOGIC)
    # ========================================================================
    
    async def _scrape_and_analyze(self, ticker: str) -> Optional[SECDilutionProfile]:
        """
        Proceso completo de scraping y análisis con Grok
        
        Pasos:
        1. Obtener CIK del ticker
        2. Buscar filings recientes (10-K, 10-Q, S-3, 8-K, 424B5)
        3. Descargar contenido HTML de filings relevantes
        4. Extraer datos estructurados básicos (si es posible)
        5. Usar Grok API para extraer datos complejos
        6. Combinar y validar
        7. Obtener precio actual y shares outstanding
        """
        try:
            logger.info("starting_sec_scrape", ticker=ticker)
            
            # 1. Obtener CIK
            cik, company_name = await self._get_cik_and_company_name(ticker)
            if not cik:
                logger.error("cik_not_found", ticker=ticker)
                return None
            
            logger.info("cik_found", ticker=ticker, cik=cik, company_name=company_name)
            
            # 2. Buscar TODOS los filings desde 2015 usando SEC-API.io (ACCESO COMPLETO)
            filings = await self._fetch_all_filings_from_sec_api_io(ticker)
            
            # 2.5 CRÍTICO: Buscar TODOS los 424B (tienen detalles de warrants/offerings)
            # Aumentar a 100 para asegurar que capturamos filings recientes
            filings_424b = await self._fetch_424b_filings(cik, max_count=100)
            if filings_424b:
                logger.info("424b_filings_found", ticker=ticker, count=len(filings_424b))
                # Agregar 424B al pool de filings
                filings.extend(filings_424b)
            
            if not filings:
                logger.warning("no_filings_found", ticker=ticker, cik=cik)
                # Crear profile vacío
                return self._create_empty_profile(ticker, cik, company_name)
            
            logger.info("filings_found_total", ticker=ticker, count=len(filings), with_424b=len(filings_424b))
            
            # 3. Filtrar TODOS los filings relevantes (sin límite)
            # Buscar desde 2015 - warrants pueden tener 10 años de vida
            relevant_filings = self._filter_relevant_filings(filings)  # SIN LÍMITE [:50]
            
            logger.info("relevant_filings_selected", ticker=ticker, count=len(relevant_filings), 
                       forms=[f['form_type'] for f in relevant_filings])
            
            filing_contents = await self._download_filings(relevant_filings)
            
            logger.info("filing_contents_downloaded", ticker=ticker, count=len(filing_contents),
                       total_chars=sum(len(f['content']) for f in filing_contents))
            
            # 3.5. Pre-parsear tablas HTML para encontrar warrants (híbrido)
            parsed_tables = await self._parse_warrant_tables(filing_contents)
            
            # 4. MULTI-PASS EXTRACTION: Analizar en múltiples pasadas enfocadas
            logger.info("starting_multipass_extraction", ticker=ticker, total_filings=len(filing_contents))
            
            extracted_data = await self._extract_with_multipass_grok(
                ticker=ticker,
                company_name=company_name,
                filing_contents=filing_contents,
                parsed_tables=parsed_tables
            )
            
            if not extracted_data:
                logger.warning("multipass_extraction_failed", ticker=ticker)
                return self._create_empty_profile(ticker, cik, company_name)
            
            # 5. Obtener precio actual y shares outstanding
            current_price, shares_outstanding, float_shares = await self._get_current_market_data(ticker)
            
            # 6. Construir profile completo
            profile = self._build_profile(
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                extracted_data=extracted_data,
                current_price=current_price,
                shares_outstanding=shares_outstanding,
                float_shares=float_shares,
                source_filings=relevant_filings
            )
            
            logger.info("sec_scrape_completed", ticker=ticker)
            return profile
            
        except Exception as e:
            logger.error("scrape_and_analyze_failed", ticker=ticker, error=str(e))
            return None
    
    async def _get_cik_and_company_name(self, ticker: str) -> tuple[Optional[str], Optional[str]]:
        """
        Obtener CIK desde SEC EDGAR usando el ticker
        
        Returns:
            Tuple (cik, company_name)
        """
        try:
            # Primero intentar desde nuestra BD (ticker_metadata)
            query = """
            SELECT cik, company_name
            FROM ticker_metadata
            WHERE symbol = $1
            """
            
            result = await self.db.fetchrow(query, ticker)
            
            if result and result['cik']:
                return result['cik'], result['company_name']
            
            # Si no está en BD, usar SEC EDGAR API
            url = f"{self.SEC_EDGAR_BASE_URL}/submissions/CIK{ticker}.json"
            
            headers = {
                "User-Agent": "TradeulApp contact@tradeul.com"
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    cik = data.get('cik')
                    company_name = data.get('name')
                    return str(cik).zfill(10), company_name
            
            # Fallback: usar SEC company tickers JSON
            url = "https://www.sec.gov/files/company_tickers.json"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    for key, company in data.items():
                        if company.get('ticker') == ticker:
                            cik = str(company.get('cik_str')).zfill(10)
                            company_name = company.get('title')
                            return cik, company_name
            
            return None, None
            
        except Exception as e:
            logger.error("get_cik_failed", ticker=ticker, error=str(e))
            return None, None
    
    async def _fetch_all_filings_from_sec_api_io(self, ticker: str) -> List[Dict]:
        """
        Buscar TODOS los filings usando SEC-API.io (LA MEJOR API - acceso completo)
        
        SEC-API.io tiene:
        - Acceso a TODOS los archivos históricos
        - Exhibits incluidos
        - Full-text search
        - Sin límites de "recent" (va hasta 1994)
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            Lista COMPLETA de todos los filings desde 2015
        """
        try:
            sec_api_key = settings.SEC_API_IO_KEY
            
            if not sec_api_key:
                logger.warning("sec_api_io_key_missing_using_fmp_fallback")
                return await self._fetch_all_filings_from_fmp(ticker)
            
            base_url = "https://api.sec-api.io"
            
            # Construir query para SEC-API.io usando su sintaxis correcta
            query = {
                "query": {
                    "query_string": {
                        "query": f'ticker:{ticker} AND filedAt:[2015-01-01 TO *] AND (formType:"10-K" OR formType:"10-Q" OR formType:"8-K" OR formType:"S-3" OR formType:"S-1" OR formType:"424B5" OR formType:"424B3" OR formType:"424B7" OR formType:"S-8")'
                    }
                },
                "from": "0",
                "size": "200",
                "sort": [{"filedAt": {"order": "desc"}}]
            }
            
            all_filings = []
            from_index = 0
            max_filings = 1000
            
            logger.info("sec_api_io_search_started", ticker=ticker)
            
            while len(all_filings) < max_filings:
                query["from"] = str(from_index)
                
                params = {"token": sec_api_key}
                
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{base_url}",
                        params=params,
                        json=query
                    )
                    
                    if response.status_code != 200:
                        logger.warning("sec_api_io_error", ticker=ticker, status=response.status_code, body=response.text[:200])
                        break
                    
                    data = response.json()
                    filings_batch = data.get('filings', [])
                    
                    if not filings_batch:
                        break
                    
                    # Convertir formato SEC-API.io a nuestro formato
                    for filing in filings_batch:
                        all_filings.append({
                            'form_type': filing.get('formType', ''),
                            'filing_date': filing.get('filedAt', '')[:10],  # "2024-01-01T00:00:00" -> "2024-01-01"
                            'accession_number': filing.get('accessionNo', ''),
                            'primary_document': '',
                            'url': filing.get('linkToFilingDetails', filing.get('linkToTxt', ''))
                        })
                    
                    logger.info("sec_api_io_batch_processed", ticker=ticker, from_index=from_index, count=len(filings_batch))
                    
                    # Si devuelve menos de 200, es la última página
                    if len(filings_batch) < 200:
                        break
                    
                    from_index += 200
            
            logger.info("sec_api_io_search_completed", ticker=ticker, total=len(all_filings))
            
            # Si encontramos muy pocos resultados (< 20), usar FMP como complemento
            if len(all_filings) < 20:
                logger.info("sec_api_io_few_results_using_fmp_complement", ticker=ticker, sec_api_count=len(all_filings))
                fmp_filings = await self._fetch_all_filings_from_fmp(ticker)
                
                # Combinar resultados, evitando duplicados
                sec_api_urls = {f.get('url', '') for f in all_filings}
                for fmp_filing in fmp_filings:
                    if fmp_filing.get('url', '') not in sec_api_urls:
                        all_filings.append(fmp_filing)
                
                logger.info("combined_filings", ticker=ticker, sec_api=len(sec_api_urls), fmp_added=len(all_filings) - len(sec_api_urls), total=len(all_filings))
            
            return all_filings
            
        except Exception as e:
            logger.error("fetch_sec_api_io_failed", ticker=ticker, error=str(e))
            # Fallback a FMP
            logger.info("falling_back_to_fmp", ticker=ticker)
            return await self._fetch_all_filings_from_fmp(ticker)
    
    async def _fetch_all_filings_from_fmp(self, ticker: str) -> List[Dict]:
        """
        Buscar TODOS los filings desde 2015 usando FMP API
        
        FMP tiene MUCHO mejor API que SEC:
        - Paginación ilimitada
        - Búsqueda por símbolo (no necesita CIK)
        - Filtros de fecha
        - Metadata estructurada
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            Lista completa de TODOS los filings desde 2015
        """
        try:
            fmp_api_key = settings.FMP_API_KEY
            
            if not fmp_api_key:
                logger.warning("fmp_api_key_missing")
                return []
            
            # FMP devuelve TODOS los filings en una sola llamada (no usa paginación real)
            base_url = f"https://financialmodelingprep.com/api/v3/sec_filings/{ticker}"
            
            all_filings = []
            page = 0
            max_pages = 10  # FMP pagina en grupos de ~100
            
            logger.info("fmp_filings_search_started", ticker=ticker)
            
            while page < max_pages:
                params = {
                    "page": page,
                    "apikey": fmp_api_key
                }
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(base_url, params=params)
                    
                    if response.status_code != 200:
                        logger.warning("fmp_api_error", ticker=ticker, page=page, status=response.status_code)
                        break
                    
                    filings_batch = response.json()
                    
                    # Si no hay más filings, terminar
                    if not filings_batch or len(filings_batch) == 0:
                        break
                    
                    # Convertir formato FMP a nuestro formato
                    for filing in filings_batch:
                        # Filtrar solo desde 2015
                        filing_date = filing.get('fillingDate', filing.get('acceptedDate', ''))
                        if filing_date and filing_date >= '2015-01-01':
                            all_filings.append({
                                'form_type': filing.get('type', ''),
                                'filing_date': filing_date,
                                'accession_number': filing.get('accessionNumber', ''),
                                'primary_document': '',  # FMP no lo proporciona
                                'url': filing.get('finalLink', filing.get('link', ''))
                            })
                    
                    logger.info("fmp_page_processed", ticker=ticker, page=page, filings_in_page=len(filings_batch))
                    
                    # Si la página devuelve menos de 100, es la última
                    if len(filings_batch) < 100:
                        break
                    
                    page += 1
            
            logger.info("fmp_filings_search_completed", ticker=ticker, total_filings=len(all_filings), pages=page+1)
            
            return all_filings
            
        except Exception as e:
            logger.error("fetch_fmp_filings_failed", ticker=ticker, error=str(e))
            return []
    
    async def _fetch_recent_filings(self, cik: str) -> List[Dict]:
        """
        Buscar filings recientes del CIK
        
        Returns:
            Lista de filings con metadata
        """
        try:
            url = f"{self.SEC_EDGAR_BASE_URL}/submissions/CIK{cik}.json"
            
            headers = {
                "User-Agent": "TradeulApp contact@tradeul.com"
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                
                if response.status_code != 200:
                    logger.error("sec_api_error", cik=cik, status=response.status_code)
                    return []
                
                data = response.json()
                
                filings_data = data.get('filings', {}).get('recent', {})
                
                if not filings_data:
                    return []
                
                # Construir lista de filings
                filings = []
                
                form_types = filings_data.get('form', [])
                filing_dates = filings_data.get('filingDate', [])
                accession_numbers = filings_data.get('accessionNumber', [])
                primary_documents = filings_data.get('primaryDocument', [])
                
                for i in range(len(form_types)):
                    filings.append({
                        'form_type': form_types[i],
                        'filing_date': filing_dates[i],
                        'accession_number': accession_numbers[i],
                        'primary_document': primary_documents[i],
                        'url': self._construct_filing_url(cik, accession_numbers[i], primary_documents[i])
                    })
                
                return filings
                
        except Exception as e:
            logger.error("fetch_recent_filings_failed", cik=cik, error=str(e))
            return []
    
    async def _fetch_424b_filings(self, cik: str, max_count: int = 100) -> List[Dict]:
        """
        Buscar TODOS los 424B (prospectus supplements) usando búsqueda avanzada
        
        Estos filings contienen detalles específicos de offerings con warrants
        
        Args:
            cik: CIK de la compañía
            max_count: Máximo número de 424B a buscar
            
        Returns:
            Lista de 424B5, 424B3, 424B7 encontrados
        """
        try:
            # Usar el browse-edgar para buscar específicamente 424B
            url = f"https://www.sec.gov/cgi-bin/browse-edgar"
            
            headers = {
                "User-Agent": "TradeulApp contact@tradeul.com"
            }
            
            params = {
                "action": "getcompany",
                "CIK": cik,
                "type": "424",  # Todos los 424B (424B5, 424B3, 424B4, 424B7)
                "dateb": "",  # Sin límite de fecha
                "owner": "exclude",
                "count": max_count,
                "output": "atom"  # Formato XML/Atom para parsear
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers, params=params)
                
                if response.status_code != 200:
                    logger.warning("sec_424b_search_failed", cik=cik, status=response.status_code)
                    return []
                
                # Parsear XML/Atom
                soup = BeautifulSoup(response.text, 'xml')
                
                entries = soup.find_all('entry')
                
                filings_424b = []
                
                for entry in entries:
                    # Extraer datos del entry
                    title_elem = entry.find('title')
                    updated_elem = entry.find('updated')
                    link_elem = entry.find('link', {'type': 'text/html'})
                    
                    if not title_elem or not link_elem:
                        continue
                    
                    title = title_elem.text.strip()
                    filing_url = link_elem.get('href', '')
                    filing_date = updated_elem.text.split('T')[0] if updated_elem else None
                    
                    # Extraer tipo de form del title (ej: "424B5  - Prospectus...")
                    form_match = re.search(r'(424B\d+)', title)
                    form_type = form_match.group(1) if form_match else '424B5'
                    
                    # Extraer accession number y primary document de la URL
                    # URL: https://www.sec.gov/Archives/edgar/data/CIK/accession/filename.htm
                    url_parts = filing_url.split('/')
                    if len(url_parts) >= 3:
                        accession_number = url_parts[-2] if len(url_parts) > 2 else ''
                        primary_document = url_parts[-1] if len(url_parts) > 1 else ''
                        
                        # Convertir accession number a formato con guiones
                        if accession_number and len(accession_number) == 18:
                            accession_number = f"{accession_number[:10]}-{accession_number[10:12]}-{accession_number[12:]}"
                        
                        filings_424b.append({
                            'form_type': form_type,
                            'filing_date': filing_date,
                            'accession_number': accession_number,
                            'primary_document': primary_document,
                            'url': filing_url
                        })
                
                logger.info("424b_search_completed", cik=cik, found=len(filings_424b))
                
                return filings_424b
                
        except Exception as e:
            logger.error("fetch_424b_filings_failed", cik=cik, error=str(e))
            return []
    
    def _construct_filing_url(self, cik: str, accession_number: str, primary_document: str) -> str:
        """Construir URL del filing"""
        accession_no_dashes = accession_number.replace('-', '')
        return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{primary_document}"
    
    def _filter_relevant_filings(self, filings: List[Dict]) -> List[Dict]:
        """
        Filtrar filings relevantes para análisis de dilución
        
        PRIORIDAD DE FILINGS PARA DILUCIÓN:
        
        Tier 1 (CRÍTICOS - Shelf Registrations):
        - S-3, S-3/A, S-3ASR: Universal shelf registrations
        - S-1, S-1/A: Initial registrations (IPO y follow-ons)
        - S-8: Employee stock plans (puede indicar warrants)
        
        Tier 2 (MUY IMPORTANTES - Financial Reports con Equity Info):
        - 10-K: Annual report (equity structure completa)
        - 10-Q: Quarterly report (equity changes)
        - 10-K/A, 10-Q/A: Amendments
        
        Tier 3 (IMPORTANTES - Prospectus Supplements = Offerings Activos):
        - 424B5: Prospectus supplement (indica offering en curso)
        - 424B3: Prospectus supplement for warrants/conversions
        - 424B4: Prospectus for debt/equity offerings
        - 424B7: Prospectus for warrants
        - 424B2: Base prospectus supplement
        - FWP: Free writing prospectus (marketing de offerings)
        
        Tier 4 (ÚTILES - Current Reports):
        - 8-K: Current report (puede tener offerings, warrant exercises)
        - 8-K/A: Amendment
        
        Tier 5 (COMPLEMENTARIOS - Proxy & Info Statements):
        - DEF 14A, DEFM14A: Proxy statements (mergers, equity plans)
        - DEFR14A, DEFA14A: Additional proxy materials
        - SC 13D, SC 13G: Beneficial ownership (puede indicar warrants)
        - SC 13D/A, SC 13G/A: Amendments
        
        Tier 6 (TENDER & EXCHANGE):
        - SC TO-I, SC TO-T: Tender offer statements
        - SC 14D9: Solicitation/recommendation statements
        """
        # Orden de prioridad completo
        priority_order = {
            # Tier 1: Shelf Registrations (CRÍTICOS)
            'S-3': 1, 'S-3/A': 1, 'S-3ASR': 1,
            'S-1': 1, 'S-1/A': 1,
            'S-8': 1,
            
            # Tier 2: Financial Reports (MUY IMPORTANTES)
            '10-K': 2, '10-K/A': 2,
            '10-Q': 2, '10-Q/A': 2,
            
            # Tier 3: Prospectus Supplements (IMPORTANTES)
            '424B5': 3, '424B3': 3, '424B4': 3, '424B7': 3, '424B2': 3,
            'FWP': 3,
            
            # Tier 4: Current Reports (ÚTILES)
            '8-K': 4, '8-K/A': 4,
            
            # Tier 5: Proxy & Ownership (COMPLEMENTARIOS)
            'DEF 14A': 5, 'DEFM14A': 5, 'DEFR14A': 5, 'DEFA14A': 5,
            'SC 13D': 5, 'SC 13G': 5, 'SC 13D/A': 5, 'SC 13G/A': 5,
            
            # Tier 6: Tender & Exchange
            'SC TO-I': 6, 'SC TO-T': 6, 'SC 14D9': 6
        }
        
        # NUEVO ENFOQUE SIMPLE: Tomar todos los filings relevantes sin filtrado complejo
        result = []
        forms_used = set()
        
        # Definir año de corte
        from datetime import date
        year_2015 = date(2015, 1, 1)
        
        # Estrategia SIMPLE: Iterar UNA VEZ por todos los filings y seleccionar los relevantes
        # Incluir S-11 (Real Estate Investment Trust registrations) que puede tener preferred stock
        relevant_types = ['10-K', '10-K/A', '10-Q', '10-Q/A', 'S-3', 'S-3/A', 'S-1', 'S-1/A', 'S-8', 'S-11',
                         '424B5', '424B3', '424B7', '424B4', '424B2', 'FWP', '8-K', '8-K/A',
                         'DEF 14A', 'DEFM14A']
        
        count_8k = 0
        for f in filings:
            form_type = f['form_type']
            
            # Verificar si es tipo relevante
            if form_type not in relevant_types:
                continue
            
            # Verificar fecha (desde 2015)
            try:
                filing_date_str = f['filing_date']
                # Manejar diferentes formatos de fecha
                if ' ' in filing_date_str:
                    filing_date_str = filing_date_str.split(' ')[0]  # "2024-01-01 00:00:00" -> "2024-01-01"
                
                filing_date = datetime.strptime(filing_date_str, '%Y-%m-%d').date()
                
                if filing_date < year_2015:
                    continue
            except:
                continue
            
            # Limitar 8-K a 30 (son muchos y menos útiles)
            if form_type == '8-K':
                if count_8k >= 30:
                    continue
                count_8k += 1
            
            result.append(f)
            forms_used.add(form_type)
        
        logger.info("filings_filtered", total=len(filings), filtered=len(result), forms_used=list(forms_used))
        
        return result
    
    async def _download_filings(self, filings: List[Dict]) -> List[Dict]:
        """
        Descargar contenido HTML de filings con rate limiting
        
        SEC tiene límite de ~10 requests/segundo. Agregamos delay entre requests.
        
        Returns:
            Lista de dicts con {form_type, filing_date, url, content}
        """
        results = []
        
        headers = {
            "User-Agent": "TradeulApp contact@tradeul.com"
        }
        
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            consecutive_429s = 0  # Contador de 429 consecutivos
            for idx, filing in enumerate(filings):
                try:
                    # Rate limiting: delay entre requests (excepto la primera)
                    if idx > 0:
                        await asyncio.sleep(self.SEC_RATE_LIMIT_DELAY)
                    
                    response = await client.get(filing['url'], headers=headers)
                    
                    if response.status_code == 200:
                        results.append({
                            'form_type': filing['form_type'],
                            'filing_date': filing['filing_date'],
                            'url': filing['url'],
                            'content': response.text  # SIN LÍMITE - contenido completo
                        })
                        
                        logger.info("filing_downloaded", form_type=filing['form_type'], url=filing['url'])
                        consecutive_429s = 0  # Reset contador
                    elif response.status_code == 429:
                        # Rate limit excedido - esperar más tiempo
                        consecutive_429s += 1
                        retry_after = response.headers.get('Retry-After')
                        wait_time = float(retry_after) if retry_after and retry_after.isdigit() else (2.0 * consecutive_429s)  # Exponencial: 2s, 4s, 6s...
                        wait_time = min(wait_time, 10.0)  # Máximo 10 segundos
                        
                        logger.warning("filing_rate_limited", url=filing['url'], 
                                     retry_after=retry_after, 
                                     consecutive=consecutive_429s,
                                     wait_seconds=wait_time)
                        await asyncio.sleep(wait_time)
                    else:
                        logger.warning("filing_download_failed", url=filing['url'], status=response.status_code)
                        consecutive_429s = 0  # Reset si no es 429
                    
                except Exception as e:
                    logger.error("filing_download_error", url=filing['url'], error=str(e))
                    consecutive_429s = 0  # Reset en error
        
        return results
    
    async def _parse_warrant_tables(self, filing_contents: List[Dict]) -> Dict:
        """
        Pre-parsear tablas HTML buscando warrants, ATM, shelf - EXHAUSTIVO
        
        Returns:
            Dict con warrant_tables, equity_sections, atm_mentions, shelf_sections
        """
        try:
            warrant_tables = []
            equity_sections = []
            atm_mentions = []
            shelf_sections = []
            
            for filing in filing_contents:
                soup = BeautifulSoup(filing['content'], 'html.parser')
                
                # 1. BUSCAR TODAS LAS TABLAS (no solo en 10-K/10-Q)
                tables = soup.find_all('table')
                
                for table_idx, table in enumerate(tables):
                    table_text = table.get_text().lower()
                    
                    # Tabla de warrants (incluyendo preferred warrants)
                    warrant_keywords = [
                        'warrant', 'exercise price', 'strike', 'expiration', 
                        'series a', 'series b', 'series c', 'preferred warrant',
                        'warrants outstanding', 'warrants exercisable', 'warrants issued',
                        'common stock warrant', 'preferred stock warrant'
                    ]
                    if any(term in table_text for term in warrant_keywords):
                        rows = table.find_all('tr')
                        table_data = []
                        
                        for row in rows:
                            cells = row.find_all(['td', 'th'])
                            row_data = [cell.get_text().strip() for cell in cells]
                            if row_data and len(row_data) > 1:  # Al menos 2 columnas
                                table_data.append(row_data)
                        
                        if len(table_data) > 1:  # Al menos header + 1 fila
                            warrant_tables.append({
                                'form_type': filing['form_type'],
                                'filing_date': filing['filing_date'],
                                'table_index': table_idx,
                                'table_rows': table_data
                            })
                    
                    # Tabla de shelf/ATM
                    if any(term in table_text for term in ['shelf', 'registration', 'at-the-market', 'atm', 'offering']):
                        rows = table.find_all('tr')
                        table_data = []
                        
                        for row in rows[:30]:
                            cells = row.find_all(['td', 'th'])
                            row_data = [cell.get_text().strip() for cell in cells]
                            if row_data:
                                table_data.append(row_data)
                        
                        if table_data:
                            shelf_sections.append({
                                'form_type': filing['form_type'],
                                'filing_date': filing['filing_date'],
                                'content': table_text[:5000]
                            })
                
                # 2. BUSCAR SECCIONES DE TEXTO con keywords
                full_text = soup.get_text()
                
                # Buscar menciones de ATM
                atm_patterns = ['at-the-market', 'atm offering', 'sales agreement', 'equity distribution agreement']
                for pattern in atm_patterns:
                    if pattern in full_text.lower():
                        # Extraer contexto alrededor
                        idx = full_text.lower().find(pattern)
                        context = full_text[max(0, idx-1000):idx+2000]
                        atm_mentions.append({
                            'form_type': filing['form_type'],
                            'filing_date': filing['filing_date'],
                            'context': context
                        })
                        break
                
                # Buscar secciones de Stockholders' Equity (incluyendo preferred warrants)
                equity_keywords = [
                    'stockholders\' equity', 'shareholders\' equity', 
                    'warrants outstanding', 'warrant activity', 'warrants exercisable',
                    'preferred warrant', 'series a warrant', 'series b warrant',
                    'warrant to purchase', 'warrant conversion'
                ]
                for keyword in equity_keywords:
                    if keyword in full_text.lower():
                        idx = full_text.lower().find(keyword)
                        context = full_text[max(0, idx-500):idx+3000]
                        # Incluir si menciona warrants, preferred, o conversión
                        if any(term in context.lower() for term in ['warrant', 'preferred', 'convert', 'exercise']):
                            equity_sections.append({
                                'form_type': filing['form_type'],
                                'filing_date': filing['filing_date'],
                                'section': context
                            })
                            break
            
            logger.info("parsing_completed", 
                       warrant_tables=len(warrant_tables),
                       equity_sections=len(equity_sections),
                       atm_mentions=len(atm_mentions),
                       shelf_sections=len(shelf_sections))
            
            return {
                'warrant_tables': warrant_tables,
                'equity_sections': equity_sections,
                'atm_mentions': atm_mentions,
                'shelf_sections': shelf_sections
            }
            
        except Exception as e:
            logger.error("parse_warrant_tables_failed", error=str(e))
            return {
                'warrant_tables': [],
                'equity_sections': [],
                'atm_mentions': [],
                'shelf_sections': []
            }
    
    async def _extract_with_multipass_grok(
        self,
        ticker: str,
        company_name: str,
        filing_contents: List[Dict],
        parsed_tables: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        MULTI-PASS EXTRACTION: Analizar en múltiples pasadas enfocadas
        
        Pass 1: 10-K (equity structure, warrants table)
        Pass 2: S-3/S-1 (shelf registrations)
        Pass 3: 424B5/424B7 (offering details con warrants)
        Pass 4: 10-Q recientes (cambios equity recientes)
        Pass 5: ATM mentions en cualquier filing
        
        Returns:
            Dict combinado de todas las pasadas
        """
        try:
            all_warrants = []
            all_atm = []
            all_shelfs = []
            all_completed = []
            all_s1 = []
            all_convertible_notes = []
            all_convertible_preferred = []
            all_equity_lines = []
            
            # Pass 1: 10-K (MÁS IMPORTANTE - tiene tabla completa de warrants, convertibles, equity)
            filings_10k = [f for f in filing_contents if f['form_type'] in ['10-K', '10-K/A']][:2]  # 2 más recientes
            if filings_10k:
                logger.info("multipass_pass1_10k", ticker=ticker, count=len(filings_10k))
                result_10k = await self._extract_pass_focused(
                    ticker, company_name, filings_10k, 
                    focus="10-K equity tables - extract ALL warrant series, convertible notes, convertible preferred, ATM programs, shelf info, and equity lines",
                    parsed_tables=parsed_tables
                )
                if result_10k:
                    all_warrants.extend(result_10k.get('warrants', []))
                    all_atm.extend(result_10k.get('atm_offerings', []))
                    all_shelfs.extend(result_10k.get('shelf_registrations', []))
                    all_completed.extend(result_10k.get('completed_offerings', []))
                    all_s1.extend(result_10k.get('s1_offerings', []))
                    all_convertible_notes.extend(result_10k.get('convertible_notes', []))
                    all_convertible_preferred.extend(result_10k.get('convertible_preferred', []))
                    all_equity_lines.extend(result_10k.get('equity_lines', []))
            
            # Pass 2: S-3/S-1/S-11 (Shelf Registrations, S-1 Offerings, Preferred Stock)
            filings_s3 = [f for f in filing_contents if f['form_type'] in ['S-3', 'S-3/A', 'S-1', 'S-1/A', 'S-11']][:5]
            if filings_s3:
                logger.info("multipass_pass2_s3", ticker=ticker, count=len(filings_s3))
                result_s3 = await self._extract_pass_focused(
                    ticker, company_name, filings_s3,
                    focus="S-1 offerings, shelf registrations, and preferred stock registrations (S-11) - extract S-1 offerings with deal sizes and warrant coverage, shelf MAXIMUM registered capacity (NOT actual sales), remaining capacity, expiration, baby shelf restrictions, amounts raised"
                )
                if result_s3:
                    all_shelfs.extend(result_s3.get('shelf_registrations', []))
                    all_s1.extend(result_s3.get('s1_offerings', []))
                    all_convertible_preferred.extend(result_s3.get('convertible_preferred', []))
            
            # Pass 3: 424B5/424B7 (Prospectus Supplements - detalles de cada offering, S-1 pricing)
            filings_424b = [f for f in filing_contents if f['form_type'] in ['424B5', '424B3', '424B7', '424B4']][:10]
            if filings_424b:
                logger.info("multipass_pass3_424b", ticker=ticker, count=len(filings_424b))
                result_424b = await self._extract_pass_focused(
                    ticker, company_name, filings_424b,
                    focus="Prospectus supplements and S-1 pricing - extract S-1 offerings with final pricing and warrant coverage, warrants issued with offerings, offering details, convertible notes details"
                )
                if result_424b:
                    all_warrants.extend(result_424b.get('warrants', []))
                    all_completed.extend(result_424b.get('completed_offerings', []))
                    all_s1.extend(result_424b.get('s1_offerings', []))
                    all_convertible_notes.extend(result_424b.get('convertible_notes', []))
            
            # Pass 4: 10-Q recientes (últimos 4 quarters para cambios recientes)
            # CRÍTICO: 10-Q tiene números REALES de emisión, no capacidad máxima
            filings_10q = [f for f in filing_contents if f['form_type'] in ['10-Q', '10-Q/A']][:4]
            if filings_10q:
                logger.info("multipass_pass4_10q", ticker=ticker, count=len(filings_10q))
                result_10q = await self._extract_pass_focused(
                    ticker, company_name, filings_10q,
                    focus="Recent quarterly reports - extract ACTUAL shares issued/sold (not registration capacity), warrant changes, convertible note conversions, preferred stock conversions, ATM updates, equity line usage. Look for 'we issued X shares', 'we sold X shares', 'proceeds received', actual quarterly numbers"
                )
                if result_10q:
                    all_warrants.extend(result_10q.get('warrants', []))
                    all_atm.extend(result_10q.get('atm_offerings', []))
                    all_completed.extend(result_10q.get('completed_offerings', []))
                    all_convertible_notes.extend(result_10q.get('convertible_notes', []))
                    all_convertible_preferred.extend(result_10q.get('convertible_preferred', []))
                    all_equity_lines.extend(result_10q.get('equity_lines', []))
            
            # Pass 5: S-8 (Employee stock plans con posibles warrants)
            filings_s8 = [f for f in filing_contents if f['form_type'] == 'S-8'][:3]
            if filings_s8:
                logger.info("multipass_pass5_s8", ticker=ticker, count=len(filings_s8))
                result_s8 = await self._extract_pass_focused(
                    ticker, company_name, filings_s8,
                    focus="Employee stock plans - extract any warrants or equity instruments"
                )
                if result_s8:
                    all_warrants.extend(result_s8.get('warrants', []))
            
            # Pass 6: 8-K (Current reports - convertibles, equity lines, ATM updates)
            filings_8k = [f for f in filing_contents if f['form_type'] in ['8-K', '8-K/A']][:5]
            if filings_8k:
                logger.info("multipass_pass6_8k", ticker=ticker, count=len(filings_8k))
                result_8k = await self._extract_pass_focused(
                    ticker, company_name, filings_8k,
                    focus="Current reports - extract convertible notes, convertible preferred, equity lines, ATM agreements, S-1 offerings, warrant issuances"
                )
                if result_8k:
                    all_warrants.extend(result_8k.get('warrants', []))
                    all_atm.extend(result_8k.get('atm_offerings', []))
                    all_s1.extend(result_8k.get('s1_offerings', []))
                    all_convertible_notes.extend(result_8k.get('convertible_notes', []))
                    all_convertible_preferred.extend(result_8k.get('convertible_preferred', []))
                    all_equity_lines.extend(result_8k.get('equity_lines', []))
            
            # Deduplicar y combinar
            combined_data = {
                'warrants': self._deduplicate_warrants(all_warrants),
                'atm_offerings': self._deduplicate_atm(all_atm),
                'shelf_registrations': self._deduplicate_shelfs(all_shelfs),
                'completed_offerings': self._deduplicate_completed(all_completed),
                's1_offerings': self._deduplicate_s1(all_s1),
                'convertible_notes': self._deduplicate_convertible_notes(all_convertible_notes),
                'convertible_preferred': self._deduplicate_convertible_preferred(all_convertible_preferred),
                'equity_lines': self._deduplicate_equity_lines(all_equity_lines)
            }
            
            logger.info("multipass_completed", ticker=ticker,
                       total_warrants=len(combined_data['warrants']),
                       total_atm=len(combined_data['atm_offerings']),
                       total_shelfs=len(combined_data['shelf_registrations']),
                       total_completed=len(combined_data['completed_offerings']),
                       total_s1=len(combined_data['s1_offerings']),
                       total_convertible_notes=len(combined_data['convertible_notes']),
                       total_convertible_preferred=len(combined_data['convertible_preferred']),
                       total_equity_lines=len(combined_data['equity_lines']))
            
            return combined_data
            
        except Exception as e:
            logger.error("multipass_extraction_failed", ticker=ticker, error=str(e))
            return None
    
    async def _extract_pass_focused(
        self,
        ticker: str,
        company_name: str,
        filings: List[Dict],
        focus: str,
        parsed_tables: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        Una pasada enfocada de Grok con 1-10 filings específicos
        
        Args:
            ticker: Ticker symbol
            company_name: Company name
            filings: Lista de 1-10 filings para analizar en esta pasada
            focus: Descripción de qué buscar en esta pasada
            parsed_tables: Tablas pre-parseadas (opcional)
            
        Returns:
            Dict con datos extraídos de esta pasada
        """
        try:
            if not self.grok_api_key:
                return None
            
            # Preparar contenido con límite inteligente por filing
            filings_text_parts = []
            total_chars = 0
            max_chars = 150000  # Límite por pasada (permite análisis profundo de pocos filings)
            
            for f in filings:
                if total_chars >= max_chars:
                    break
                
                # Dar más espacio a filings críticos
                if f['form_type'] in ['10-K', '10-K/A']:
                    limit = 80000
                elif f['form_type'] in ['S-3', 'S-3/A']:
                    limit = 60000
                elif f['form_type'] in ['424B5', '424B3', '424B7']:
                    limit = 40000
                else:
                    limit = 30000
                
                content = f['content'][:limit]
                filings_text_parts.append(
                    f"=== {f['form_type']} filed on {f['filing_date']} ===\n{content}"
                )
                total_chars += len(content)
            
            filings_text = "\n\n".join(filings_text_parts)
            
            # AGREGAR TODAS LAS SECCIONES PRE-PARSEADAS (mucho más eficiente que HTML completo)
            enhanced_context = ""
            
            # 1. Tablas de warrants (LO MÁS IMPORTANTE)
            if parsed_tables and parsed_tables.get('warrant_tables'):
                tables_text = "=== WARRANT TABLES (PRE-PARSED) ===\n\n"
                for idx, table in enumerate(parsed_tables['warrant_tables'][:20]):  # Hasta 20 tablas
                    if any(f['form_type'] == table['form_type'] and f['filing_date'] == table['filing_date'] for f in filings):
                        tables_text += f"Table {idx+1} from {table['form_type']} ({table['filing_date']}):\n"
                        for row in table['table_rows']:
                            tables_text += "  | ".join(row) + "\n"
                        tables_text += "\n"
                enhanced_context += tables_text + "\n\n"
            
            # 2. Secciones de equity con menciones de warrants
            if parsed_tables and parsed_tables.get('equity_sections'):
                equity_text = "=== STOCKHOLDERS' EQUITY SECTIONS ===\n\n"
                for idx, section in enumerate(parsed_tables['equity_sections'][:10]):
                    if any(f['form_type'] == section['form_type'] and f['filing_date'] == section['filing_date'] for f in filings):
                        equity_text += f"From {section['form_type']} ({section['filing_date']}):\n{section['section']}\n\n"
                enhanced_context += equity_text + "\n\n"
            
            # 3. Menciones de ATM
            if parsed_tables and parsed_tables.get('atm_mentions'):
                atm_text = "=== ATM PROGRAM MENTIONS ===\n\n"
                for mention in parsed_tables['atm_mentions'][:5]:
                    if any(f['form_type'] == mention['form_type'] and f['filing_date'] == mention['filing_date'] for f in filings):
                        atm_text += f"From {mention['form_type']} ({mention['filing_date']}):\n{mention['context']}\n\n"
                enhanced_context += atm_text + "\n\n"
            
            # 4. Agregar el enhanced context ANTES del filing completo
            if enhanced_context:
                filings_text = enhanced_context + "\n\n=== FULL FILINGS ===\n\n" + filings_text
            
            # Construir prompt HIPER COMPLETO
            prompt = f"""
You are an EXPERT financial data extraction specialist analyzing SEC EDGAR filings for {company_name} (Ticker: {ticker}).

YOUR MISSION: Extract COMPREHENSIVE dilution data with MAXIMUM detail and accuracy. If information is missing or unclear, use your financial knowledge to INFER and COMPLETE missing data points.

THIS IS A FOCUSED ANALYSIS PASS. Your specific task:
**{focus}**

SEC FILINGS FOR THIS PASS:
{filings_text}

Extract and return ONLY a JSON object with these arrays (return empty arrays [] if nothing found):
{{
  "warrants": [
    {{
      "issue_date": "YYYY-MM-DD or null",
      "outstanding": number or null,
      "exercise_price": number or null,
      "expiration_date": "YYYY-MM-DD or null",
      "potential_new_shares": number or null,
      "notes": "string with series name (Series A/B/C), owner, agent, underwriter, price protection, PP clause, exercisable date, etc. BE DETAILED"
    }}
  ],
  "atm_offerings": [
    {{
      "total_capacity": number or null,
      "remaining_capacity": number or null,
      "placement_agent": "string or null",
      "status": "Active" or "Terminated" or "Replaced" or null,
      "agreement_start_date": "YYYY-MM-DD or null",
      "filing_date": "YYYY-MM-DD or null",
      "filing_url": "string or null",
      "notes": "string or null"
    }}
  ],
  "shelf_registrations": [
    {{
      "total_capacity": number or null,
      "remaining_capacity": number or null,
      "current_raisable_amount": number or null,
      "total_amount_raised": number or null,
      "total_amount_raised_last_12mo": number or null,
      "is_baby_shelf": boolean,
      "baby_shelf_restriction": boolean or null,
      "security_type": "common_stock" or "preferred_stock" or "mixed" or null,
      "filing_date": "YYYY-MM-DD or null",
      "effect_date": "YYYY-MM-DD or null",
      "registration_statement": "S-3 or S-1 or S-11 or null",
      "filing_url": "string or null",
      "expiration_date": "YYYY-MM-DD or null",
      "last_banker": "string or null",
      "notes": "string or null"
    }}
  ],
  "completed_offerings": [
    {{
      "offering_type": "string or null (Public Offering, PIPE, Registered Direct, etc.)",
      "shares_issued": number or null,
      "price_per_share": number or null,
      "amount_raised": number or null,
      "offering_date": "YYYY-MM-DD or null",
      "filing_url": "string or null",
      "notes": "string or null"
    }}
  ],
  "s1_offerings": [
    {{
      "anticipated_deal_size": number or null,
      "final_deal_size": number or null,
      "final_pricing": number or null,
      "final_shares_offered": number or null,
      "warrant_coverage": number or null,
      "final_warrant_coverage": number or null,
      "exercise_price": number or null,
      "underwriter_agent": "string or null",
      "s1_filing_date": "YYYY-MM-DD or null",
      "status": "Priced" or "Registered" or "Pending" or null,
      "filing_url": "string or null",
      "last_update_date": "YYYY-MM-DD or null"
    }}
  ],
  "convertible_notes": [
    {{
      "total_principal_amount": number or null,
      "remaining_principal_amount": number or null,
      "conversion_price": number or null,
      "total_shares_when_converted": number or null,
      "remaining_shares_when_converted": number or null,
      "issue_date": "YYYY-MM-DD or null",
      "convertible_date": "YYYY-MM-DD or null",
      "maturity_date": "YYYY-MM-DD or null",
      "underwriter_agent": "string or null",
      "filing_url": "string or null",
      "notes": "string or null"
    }}
  ],
  "convertible_preferred": [
    {{
      "series": "string or null (Series A, B, C, etc.)",
      "total_dollar_amount_issued": number or null,
      "remaining_dollar_amount": number or null,
      "conversion_price": number or null,
      "total_shares_when_converted": number or null,
      "remaining_shares_when_converted": number or null,
      "issue_date": "YYYY-MM-DD or null",
      "convertible_date": "YYYY-MM-DD or null",
      "maturity_date": "YYYY-MM-DD or null",
      "underwriter_agent": "string or null",
      "filing_url": "string or null",
      "notes": "string or null"
    }}
  ],
  "equity_lines": [
    {{
      "total_capacity": number or null,
      "remaining_capacity": number or null,
      "agreement_start_date": "YYYY-MM-DD or null",
      "agreement_end_date": "YYYY-MM-DD or null",
      "filing_url": "string or null",
      "notes": "string or null"
    }}
  ]
}}

🚀 CRITICAL EXTRACTION RULES - BE EXHAUSTIVE:

1. WARRANTS - EXTRACT EVERYTHING:
   - Extract ALL warrant types: common stock, preferred stock, Series A/B/C/D/E/F, SPAC warrants, consultant warrants, underwriter warrants, pre-funded warrants
   - Look for: "warrants outstanding", "warrants exercisable", "warrants issued", "total warrants", "warrant to purchase"
   - Extract from: equity tables, footnotes, narrative sections, offering documents, 424B filings
   - For each warrant, extract: outstanding count, exercise price, expiration date, issue date, series name, underwriter/agent, price protection clauses
   - Different series (A, B, C) = SEPARATE entries
   - Different expiration dates = SEPARATE entries
   - Different exercise prices = SEPARATE entries
   - If you see "X warrants outstanding" → extract that EXACT number
   - Include warrants that convert preferred stock to common stock
   - Include warrants with vesting conditions (note in notes field)
   - If exercise price is missing but mentioned in context → INFER from context
   - If expiration is missing but typical pattern exists → INFER (usually 5-7 years from issue)

2. S-1 OFFERINGS - DETAILED EXTRACTION:
   - Look for S-1 registration statements and subsequent 424B pricing supplements
   - Extract: anticipated vs final deal size, pricing, shares offered, warrant coverage (initial and final)
   - Status: "Priced" if 424B filed, "Registered" if only S-1, "Pending" if not yet effective
   - Underwriter/placement agent is CRITICAL - extract from S-1 and 424B
   - If warrant coverage mentioned but not exact % → CALCULATE from warrants issued / shares offered
   - Last update date = most recent filing date related to this offering

3. CONVERTIBLE NOTES - COMPREHENSIVE:
   - Look for: "convertible notes", "convertible debt", "convertible promissory notes"
   - Extract: principal amounts (total and remaining), conversion prices, shares when converted
   - Maturity dates are CRITICAL
   - If conversion price not explicit → CALCULATE from principal / shares
   - If remaining principal not stated → check if note was converted/paid (look in 10-Q/10-K)
   - Extract from: 8-K, 424B, 10-Q, 10-K, offering documents

4. CONVERTIBLE PREFERRED STOCK:
   - Look for: "Series X Preferred Stock", "convertible preferred", "preferred shares convertible"
   - Extract: series name (A, B, C, etc.), dollar amounts issued, conversion prices
   - If conversion price not explicit → CALCULATE from stated value / conversion ratio
   - Check if preferred has been converted (look in equity sections of 10-Q/10-K)
   - Extract from: S-1, S-3, 424B, 10-K, 10-Q

5. EQUITY LINES (ELOC):
   - Look for: "equity line", "equity line of credit", "ELOC", "standby equity distribution agreement"
   - Extract: total capacity, remaining capacity, agreement dates
   - Often mentioned in 8-K or S-3 filings
   - If capacity not explicit → look for maximum drawdown amounts

6. ATM OFFERINGS - ENHANCED:
   - Extract: total capacity, remaining capacity, placement agent, status (Active/Terminated/Replaced)
   - Look for: "At-The-Market", "ATM", "sales agreement", "equity distribution agreement"
   - Status: "Active" if current, "Terminated" if explicitly terminated, "Replaced" if superseded by new ATM
   - Agreement start date = filing date of sales agreement (usually 8-K or S-3)
   - If remaining capacity not stated → check if ATM was fully utilized (look in 10-Q for sales)

7. SHELF REGISTRATIONS - MAXIMUM DETAIL:
   - Extract: total capacity, remaining capacity, current raisable amount
   - **SECURITY_TYPE is CRITICAL:**
     * S-11 = "preferred_stock" (REIT preferred stock)
     * S-3/S-1 explicitly for common stock = "common_stock"
     * S-3/S-1 explicitly for preferred stock = "preferred_stock"
     * If mentions both types = "mixed"
     * If unclear = null (conservative)
   - Baby shelf: <$75M total capacity = true
   - Baby shelf restriction: Check if company is subject to baby shelf rules (look for "one-third of public float" language)
   - Amounts raised: Look in 10-Q/10-K for actual amounts raised from shelf (sum of offerings)
   - Last 12 months: Calculate from most recent 4 quarters of 10-Q filings
   - Effect date = date shelf became effective (usually shortly after filing)
   - Last banker = most recent investment banker mentioned in shelf-related offerings
   - Expiration = typically 3 years from filing date (calculate if not explicit)

8. COMPLETED OFFERINGS - ACTUAL SALES ONLY:
   - ONLY extract offerings ACTUALLY COMPLETED/SOLD, NOT registration capacity
   - Look for: "we sold", "we issued", "we raised", "proceeds received", "shares sold", "offering closed"
   - In 10-Q/10-K: "During the quarter we issued X shares for $Y" = COMPLETED
   - In 424B: Look for actual sales, not just registration
   - If "Maximum of $X registered" WITHOUT evidence of sale → DO NOT include
   - Offering type: "Public Offering", "PIPE", "Registered Direct", "Private Placement", etc.

9. MISSING DATA INFERENCE - BE PROACTIVE:
   - If exercise price missing but offering price mentioned → use offering price as exercise price
   - If expiration missing but issue date known → assume 5-7 years (typical warrant term)
   - If outstanding missing but total issued known → assume all outstanding unless stated otherwise
   - If conversion price missing → CALCULATE from principal/amount / shares
   - If remaining capacity missing → check if fully utilized (look for termination language)
   - If status unclear → infer from dates (if old and no recent activity = likely terminated)
   - If agent/underwriter missing → look in related filings (8-K, S-1, 424B)
   - If dates missing → use filing date as proxy

10. GENERAL EXTRACTION PRINCIPLES:
    - Extract REAL numbers from documents (don't make up numbers)
    - If you see warrant tables → extract EVERY row as separate warrant
    - Cross-reference multiple filings for complete picture
    - If information appears in multiple filings → use most recent
    - Return empty arrays [] if nothing found (don't return arrays with null objects)
    - Be THOROUGH - extract ALL warrants, ALL convertibles, ALL offerings
    - If you're unsure about a number → extract it anyway with a note
    - Series names are IMPORTANT - include in notes field
    - Dates are CRITICAL - extract all dates mentioned

11. QUALITY CHECK:
    - Each warrant should have at least: outstanding OR total issued
    - Each offering should have: shares OR amount raised
    - Each shelf should have: total capacity
    - If critical field missing → add note explaining why

RETURN ONLY VALID JSON. Be comprehensive, accurate, and detailed.
"""
            
            # Llamar a Grok
            client = Client(api_key=self.grok_api_key)
            
            try:
                chat = client.chat.create(model="grok-3", temperature=0.1)
            except:
                chat = client.chat.create(model="grok-2-1212", temperature=0.1)
            
            chat.append(system("You are a financial data extraction expert. Return ONLY valid JSON."))
            chat.append(user(prompt))
            
            response = chat.sample()
            
            # Parse JSON
            extracted = json.loads(response.content)
            
            logger.info("pass_extraction_success", ticker=ticker, focus=focus[:50],
                       warrants=len(extracted.get('warrants', [])),
                       atm=len(extracted.get('atm_offerings', [])),
                       shelfs=len(extracted.get('shelf_registrations', [])))
            
            return extracted
            
        except Exception as e:
            logger.error("pass_extraction_failed", ticker=ticker, focus=focus[:50], error=str(e))
            return None
    
    def _deduplicate_warrants(self, warrants: List[Dict]) -> List[Dict]:
        """Deduplicar warrants por exercise_price + expiration"""
        seen = set()
        unique = []
        for w in warrants:
            key = (w.get('exercise_price'), w.get('expiration_date'), w.get('outstanding'))
            if key not in seen and w.get('outstanding'):  # Solo si tiene outstanding
                seen.add(key)
                unique.append(w)
        return unique
    
    def _deduplicate_atm(self, atms: List[Dict]) -> List[Dict]:
        """Deduplicar ATM por placement_agent + filing_date"""
        seen = set()
        unique = []
        for a in atms:
            key = (a.get('placement_agent'), a.get('filing_date'))
            # Incluir si tiene remaining_capacity O total_capacity (no descartar si falta remaining)
            if key not in seen and (a.get('remaining_capacity') or a.get('total_capacity')):
                seen.add(key)
                unique.append(a)
        return unique
    
    def _deduplicate_shelfs(self, shelfs: List[Dict]) -> List[Dict]:
        """Deduplicar shelfs por filing_date + capacity"""
        seen = set()
        unique = []
        for s in shelfs:
            key = (s.get('filing_date'), s.get('total_capacity'))
            if key not in seen and s.get('filing_date'):
                seen.add(key)
                unique.append(s)
        return unique
    
    def _deduplicate_completed(self, completed: List[Dict]) -> List[Dict]:
        """Deduplicar completed offerings por fecha + shares"""
        seen = set()
        unique = []
        for c in completed:
            key = (c.get('offering_date'), c.get('shares_issued'))
            if key not in seen and c.get('offering_date'):
                seen.add(key)
                unique.append(c)
        return unique
    
    def _deduplicate_s1(self, s1_offerings: List[Dict]) -> List[Dict]:
        """Deduplicar S-1 offerings por filing_date + deal_size"""
        seen = set()
        unique = []
        for s1 in s1_offerings:
            key = (s1.get('s1_filing_date'), s1.get('final_deal_size') or s1.get('anticipated_deal_size'))
            if key not in seen and s1.get('s1_filing_date'):
                seen.add(key)
                unique.append(s1)
        return unique
    
    def _deduplicate_convertible_notes(self, notes: List[Dict]) -> List[Dict]:
        """Deduplicar convertible notes por issue_date + principal"""
        seen = set()
        unique = []
        for n in notes:
            key = (n.get('issue_date'), n.get('total_principal_amount'))
            if key not in seen and n.get('issue_date'):
                seen.add(key)
                unique.append(n)
        return unique
    
    def _deduplicate_convertible_preferred(self, preferred: List[Dict]) -> List[Dict]:
        """Deduplicar convertible preferred por series + issue_date"""
        seen = set()
        unique = []
        for p in preferred:
            key = (p.get('series'), p.get('issue_date'), p.get('total_dollar_amount_issued'))
            if key not in seen and p.get('series') and p.get('issue_date'):
                seen.add(key)
                unique.append(p)
        return unique
    
    def _deduplicate_equity_lines(self, equity_lines: List[Dict]) -> List[Dict]:
        """Deduplicar equity lines por agreement_start_date + capacity"""
        seen = set()
        unique = []
        for el in equity_lines:
            key = (el.get('agreement_start_date'), el.get('total_capacity'))
            if key not in seen and el.get('agreement_start_date'):
                seen.add(key)
                unique.append(el)
        return unique
    
    async def _extract_with_grok(
        self,
        ticker: str,
        company_name: str,
        filing_contents: List[Dict],
        filings_metadata: List[Dict],
        parsed_tables: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        Usar Grok API (xAI SDK) para extraer datos de dilución de los filings
        
        Returns:
            Dict con warrants, atm_offerings, shelf_registrations, completed_offerings
        """
        try:
            if not self.grok_api_key:
                logger.error("grok_api_key_missing")
                return None
            
            # Preparar contenido para el prompt
            # Estrategia: Priorizar filings más relevantes, contenido completo pero limitado por tokens
            filings_text_parts = []
            
            # Límite de tokens de Grok: ~200k tokens = ~800k caracteres aproximadamente
            # Enviar máximo 600k caracteres para estar seguros
            total_chars = 0
            max_total_chars = 600000
            
            for idx, f in enumerate(filing_contents):
                if total_chars >= max_total_chars:
                    break
                
                # Límite por tipo de filing (más importante = más espacio)
                if f['form_type'] in ['10-K', '10-K/A']:
                    content_limit = 150000  # 150k para 10-K MÁS RECIENTE
                elif f['form_type'] in ['S-3', 'S-3/A', 'S-1']:
                    content_limit = 80000  # 80k para S-3
                elif f['form_type'] in ['424B5', '424B3', '424B7']:
                    content_limit = 50000  # 50k para 424B (críticos para warrants)
                elif f['form_type'] in ['10-Q', '10-Q/A']:
                    content_limit = 60000  # 60k para 10-Q
                else:
                    content_limit = 30000  # 30k para otros
                
                content = f['content'][:content_limit]
                filings_text_parts.append(
                    f"=== {f['form_type']} filed on {f['filing_date']} ===\n{content}"
                )
                total_chars += len(content) + 100  # +100 por el header
            
            filings_text = "\n\n".join(filings_text_parts)
            
            # Si tenemos tablas pre-parseadas, PRIORIZAR ESAS (mucho más eficiente)
            if parsed_tables and parsed_tables.get('warrant_tables') and len(parsed_tables['warrant_tables']) > 0:
                logger.info("using_parsed_tables_strategy", ticker=ticker, tables_count=len(parsed_tables['warrant_tables']))
                
                # Enviar SOLO tablas + 10-K más reciente + S-3 más recientes
                tables_text = "=== WARRANT TABLES FROM 10-K/10-Q ===\n\n"
                for idx, table in enumerate(parsed_tables['warrant_tables'][:10]):  # Hasta 10 tablas
                    tables_text += f"\n--- Table {idx+1} from {table['form_type']} ({table['filing_date']}) ---\n"
                    for row in table['table_rows']:
                        tables_text += "  | ".join(row) + "\n"
                    tables_text += "\n"
                
                # Agregar solo 10-K y S-3 completos (resto ya está en tablas)
                important_filings = []
                for f in filing_contents[:10]:
                    if f['form_type'] in ['10-K', 'S-3', 'S-3/A']:
                        important_filings.append(
                            f"=== {f['form_type']} filed on {f['filing_date']} ===\n{f['content'][:80000]}"
                        )
                
                filings_text = tables_text + "\n\n" + "\n\n".join(important_filings)
            else:
                # Fallback: estrategia normal si no hay tablas parseadas
                logger.info("using_normal_strategy", ticker=ticker)
            
            logger.info("sending_to_grok", ticker=ticker, 
                       prompt_length=len(filings_text), 
                       filings_sent=len(filing_contents[:15]),
                       warrant_tables_found=len(parsed_tables.get('warrant_tables', [])) if parsed_tables else 0)
            
            # Construir prompt (diferente si tenemos tablas parseadas)
            has_warrant_tables = parsed_tables and len(parsed_tables.get('warrant_tables', [])) > 0
            prompt = self._build_grok_prompt(ticker, company_name, filings_text, has_warrant_tables=has_warrant_tables)
            
            # Usar xAI SDK con modelo más potente
            client = Client(api_key=self.grok_api_key)
            
            # Intentar con grok-3 primero (más potente), fallback a grok-2
            try:
                chat = client.chat.create(
                    model="grok-3",  # Versión más nueva y potente
                    temperature=0.1
                )
            except Exception as e:
                logger.warning("grok_3_not_available", error=str(e))
                # Fallback a grok-2-1212 (versión específica estable)
                chat = client.chat.create(
                    model="grok-2-1212",
                    temperature=0.1
                )
            
            chat.append(system(
                "You are a financial data extraction expert specialized in SEC filings. "
                "Return ONLY valid JSON, no markdown, no explanations."
            ))
            
            chat.append(user(prompt))
            
            response = chat.sample()
            
            # Log respuesta COMPLETA para debugging detallado
            logger.info("grok_full_response", ticker=ticker, response=response.content)
            
            # Parse JSON del contenido
            extracted_data = json.loads(response.content)
            
            # Log estadísticas detalladas
            logger.info("grok_extraction_success", 
                       ticker=ticker, 
                       warrants_count=len(extracted_data.get('warrants', [])), 
                       atm_count=len(extracted_data.get('atm_offerings', [])),
                       shelf_count=len(extracted_data.get('shelf_registrations', [])),
                       completed_count=len(extracted_data.get('completed_offerings', [])))
            
            return extracted_data
                
        except Exception as e:
            logger.error("extract_with_grok_failed", ticker=ticker, error=str(e))
            return None
    
    def _build_grok_prompt(self, ticker: str, company_name: str, filings_text: str, has_warrant_tables: bool = False) -> str:
        """Construir prompt para Grok API"""
        
        if has_warrant_tables:
            # Prompt ESPECIALIZADO cuando hay tablas de warrants pre-parseadas
            return f"""
You are extracting dilution data from SEC EDGAR filings for {company_name} (Ticker: {ticker}).

CRITICAL: I have already PRE-PARSED warrant tables from the 10-K/10-Q filings.
These tables are at the TOP of the filings below marked as "=== WARRANT TABLES FROM 10-K/10-Q ===".

YOUR TASK:
1. Extract EVERY row from the warrant tables
2. Each row represents a DIFFERENT warrant series/tranche
3. Look for columns: "Series", "Outstanding", "Exercise Price", "Expiration"
4. Extract the NUMBERS from each cell
5. For ATM and Shelf, search the S-3 and offering documents below the tables

SEC FILINGS WITH PRE-PARSED TABLES:
{filings_text}

RETURN FORMAT: JSON with arrays of warrants, atm_offerings, shelf_registrations, completed_offerings.
IMPORTANT: If you see warrant tables with rows, EXTRACT EACH ROW as a separate warrant entry."""
        
        # Prompt normal si no hay tablas
        return f"""
You are a FINANCIAL ANALYST extracting dilution data from SEC EDGAR filings for {company_name} (Ticker: {ticker}).

CRITICAL: Be EXHAUSTIVE. Look through ALL sections of the filings for EVERY mention of warrants, ATM, shelfs, and offerings.

SEC FILINGS:
{filings_text}

=== EXHAUSTIVE SEARCH INSTRUCTIONS ===

1. WARRANTS (Search EVERYWHERE for these):
   
   WHERE TO LOOK:
   - Balance sheet → "Warrant liability"
   - Equity section → "Common stock purchase warrants"
   - Notes to financial statements → "Warrant activity" or "Warrants outstanding"
   - MD&A section → "Warrant exercises" or "Outstanding warrants"
   - Exhibits → Warrant agreements
   - Tables with columns: "Series", "Exercise Price", "Expiration", "Outstanding"
   
   SEARCH TERMS:
   - "warrants outstanding"
   - "warrant liability"
   - "registered warrants"
   - "Series A warrants", "Series B warrants"
   - "common stock purchase warrant"
   - "warrant to purchase"
   - "warrant exercises"
   - "warrant holders"
   - "FINRA warrants" or "qualified institutional buyers"
   
   WHAT TO EXTRACT:
   - Issue date (when was the warrant issued?)
   - Outstanding warrants (how many warrants are still valid/unexercised?)
   - Exercise price (strike price in dollars)
   - Expiration date (when do they expire?)
   - Notes (Owner name like "Armistice", "Alto", placement agent, series name)
   
   IMPORTANT: Extract EACH series/tranche separately (Series A, Series B, etc.)
   IMPORTANT: Look for MULTIPLE warrant entries if there are different series or issuances

2. ATM OFFERINGS (At-The-Market Programs):
   
   WHERE TO LOOK:
   - "Sales Agreement"
   - "At-The-Market Offering Agreement"
   - "Equity Distribution Agreement"
   - Prospectus supplements mentioning ATM
   
   SEARCH TERMS:
   - "At-The-Market", "ATM offering", "ATM program"
   - "sales agreement"
   - "equity distribution agreement"
   - "maximum aggregate offering price"
   
   WHAT TO EXTRACT:
   - Total capacity approved (e.g., "$75 million")
   - Amount already used/sold
   - Remaining capacity = Total - Used
   - Placement agent (e.g., "H.C. Wainwright", "Cantor Fitzgerald")
   - Filing date

3. SHELF REGISTRATIONS (S-3, S-1):
   
   WHERE TO LOOK:
   - Form S-3, S-3/A headers
   - "Registration Statement"
   - "Prospectus" section
   
   SEARCH TERMS:
   - "aggregate offering price"
   - "registration statement"
   - "shelf registration"
   - "$X million of securities"
   
   WHAT TO EXTRACT:
   - Total capacity registered
   - Amount already raised from this shelf
   - Remaining = Total - Raised
   - Filing date
   - Expiration (filing date + 3 years typically)
   
   CRITICAL: IGNORE shelfs filed more than 3 years ago (they are expired)
   CRITICAL: Only include shelfs filed after 2022 (anything before is expired)

4. COMPLETED OFFERINGS:
   
   WHERE TO LOOK:
   - "Offering of X shares"
   - "Registered direct offering"
   - "PIPE transaction"
   - Prospectus supplements (424B5)
   
   WHAT TO EXTRACT:
   - Type, shares issued, price per share, amount raised, date

=== RETURN FORMAT ===

Extract and return ONLY a JSON object:

{{
  "warrants": [
    {{
      "issue_date": "YYYY-MM-DD or null",
      "outstanding": number or null,
      "exercise_price": number or null,
      "expiration_date": "YYYY-MM-DD or null",
      "potential_new_shares": number or null,
      "notes": "string or null"
    }}
  ],
  "atm_offerings": [
    {{
      "total_capacity": number or null,
      "remaining_capacity": number or null,
      "placement_agent": "string or null",
      "filing_date": "YYYY-MM-DD or null",
      "filing_url": "string or null"
    }}
  ],
  "shelf_registrations": [
    {{
      "total_capacity": number or null,
      "remaining_capacity": number or null,
      "is_baby_shelf": boolean,
      "filing_date": "YYYY-MM-DD or null",
      "security_type": "common_stock" or "preferred_stock" or "mixed" or null,
      "registration_statement": "S-3 or S-1 or S-11 or null",
      "filing_url": "string or null",
      "expiration_date": "YYYY-MM-DD or null"
    }}
  ],
  "completed_offerings": [
    {{
      "offering_type": "string or null",
      "shares_issued": number or null,
      "price_per_share": number or null,
      "amount_raised": number or null,
      "offering_date": "YYYY-MM-DD or null",
      "filing_url": "string or null",
      "notes": "string or null"
    }}
  ]
}}

CRITICAL INSTRUCTIONS:
1. Return ONLY valid JSON, no markdown, no explanations, no preamble
2. Extract REAL data from the filings - DO NOT return arrays with all null values
3. If you cannot find specific data for a category (e.g., no warrants), return EMPTY ARRAY: []
4. DO NOT return arrays with objects full of nulls - either fill with real data or return empty array
5. Dates in YYYY-MM-DD format
6. Numbers as integers/floats (not strings)
7. For capacity/amounts: extract the dollar amount from text like "$100 million" = 100000000
8. Baby shelf = total capacity under $75,000,000
9. Only include active/recent data (last 3 years for warrants/ATM/shelf, last 2 years for completed offerings)

EXAMPLE GOOD RESPONSE:
{{
  "warrants": [
    {{"outstanding": 5000000, "exercise_price": 11.50, "expiration_date": "2028-05-15", "potential_new_shares": 5000000}}
  ],
  "atm_offerings": [],
  "shelf_registrations": [
    {{"total_capacity": 150000000, "remaining_capacity": 150000000, "registration_statement": "S-3", "filing_date": "2023-10-15", "is_baby_shelf": false}}
  ],
  "completed_offerings": []
}}

EXAMPLE BAD RESPONSE (DO NOT DO THIS):
{{
  "warrants": [{{"outstanding": null, "exercise_price": null}}],
  "atm_offerings": [{{"total_capacity": null}}]
}}
"""
    
    async def _get_current_market_data(self, ticker: str) -> tuple[Optional[Decimal], Optional[int], Optional[int]]:
        """
        Obtener precio actual y shares outstanding
        
        Estrategia:
        1. Shares outstanding y float desde ticker_metadata (siempre están)
        2. Precio desde Polygon API (snapshot actual)
        
        Returns:
            Tuple (current_price, shares_outstanding, float_shares)
        """
        try:
            # 1. Obtener shares outstanding y float de ticker_metadata
            query = """
            SELECT shares_outstanding, float_shares
            FROM ticker_metadata
            WHERE symbol = $1
            """
            
            result = await self.db.fetchrow(query, ticker)
            
            if not result:
                return None, None, None
            
            shares_outstanding = result['shares_outstanding']
            float_shares = result['float_shares']
            
            # 2. Obtener precio actual desde Polygon API (snapshot)
            current_price = await self._get_price_from_polygon(ticker)
            
            return current_price, shares_outstanding, float_shares
            
        except Exception as e:
            logger.error("get_current_market_data_failed", ticker=ticker, error=str(e))
            return None, None, None
    
    async def _get_price_from_polygon(self, ticker: str) -> Optional[Decimal]:
        """
        Obtener precio actual desde Polygon API
        
        Returns:
            Precio actual o None
        """
        try:
            polygon_api_key = settings.POLYGON_API_KEY
            
            if not polygon_api_key:
                logger.warning("polygon_api_key_missing")
                return None
            
            url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    params={"apiKey": polygon_api_key}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Extraer precio del snapshot
                    ticker_data = data.get('ticker', {})
                    
                    # Intentar obtener precio del último trade
                    last_trade = ticker_data.get('lastTrade', {})
                    price = last_trade.get('p')
                    
                    if not price:
                        # Fallback: precio de cierre del día anterior
                        prev_day = ticker_data.get('prevDay', {})
                        price = prev_day.get('c')
                    
                    if not price:
                        # Fallback: precio del día actual
                        day = ticker_data.get('day', {})
                        price = day.get('c')
                    
                    if price:
                        return Decimal(str(price))
                
                logger.warning("polygon_snapshot_no_price", ticker=ticker, status=response.status_code)
                return None
                
        except Exception as e:
            logger.error("get_price_from_polygon_failed", ticker=ticker, error=str(e))
            return None
    
    def _build_profile(
        self,
        ticker: str,
        cik: str,
        company_name: str,
        extracted_data: Dict,
        current_price: Optional[Decimal],
        shares_outstanding: Optional[int],
        float_shares: Optional[int],
        source_filings: List[Dict]
    ) -> SECDilutionProfile:
        """Construir SECDilutionProfile desde datos extraídos"""
        
        # Log datos recibidos de Grok
        logger.info("building_profile", ticker=ticker,
                   extracted_warrants=len(extracted_data.get('warrants', [])),
                   extracted_atm=len(extracted_data.get('atm_offerings', [])),
                   extracted_shelf=len(extracted_data.get('shelf_registrations', [])),
                   extracted_completed=len(extracted_data.get('completed_offerings', [])),
                   extracted_s1=len(extracted_data.get('s1_offerings', [])),
                   extracted_convertible_notes=len(extracted_data.get('convertible_notes', [])),
                   extracted_convertible_preferred=len(extracted_data.get('convertible_preferred', [])),
                   extracted_equity_lines=len(extracted_data.get('equity_lines', [])))
        
        # Parse warrants
        warrants = [
            WarrantModel(
                ticker=ticker,
                issue_date=w.get('issue_date'),
                outstanding=w.get('outstanding'),
                exercise_price=w.get('exercise_price'),
                expiration_date=w.get('expiration_date'),
                potential_new_shares=w.get('potential_new_shares'),
                notes=w.get('notes')
            )
            for w in extracted_data.get('warrants', [])
        ]
        
        logger.info("warrants_parsed", ticker=ticker, count=len(warrants))
        
        # Parse ATM offerings (con nuevos campos)
        atm_offerings = [
            ATMOfferingModel(
                ticker=ticker,
                total_capacity=a.get('total_capacity'),
                remaining_capacity=a.get('remaining_capacity'),
                placement_agent=a.get('placement_agent'),
                status=a.get('status'),
                agreement_start_date=a.get('agreement_start_date'),
                filing_date=a.get('filing_date'),
                filing_url=a.get('filing_url'),
                potential_shares_at_current_price=int(a.get('remaining_capacity', 0) / current_price) if current_price and a.get('remaining_capacity') else None,
                notes=a.get('notes')
            )
            for a in extracted_data.get('atm_offerings', [])
        ]
        
        # Parse shelf registrations (con nuevos campos)
        shelf_registrations = [
            ShelfRegistrationModel(
                ticker=ticker,
                total_capacity=s.get('total_capacity'),
                remaining_capacity=s.get('remaining_capacity'),
                current_raisable_amount=s.get('current_raisable_amount'),
                total_amount_raised=s.get('total_amount_raised'),
                total_amount_raised_last_12mo=s.get('total_amount_raised_last_12mo'),
                is_baby_shelf=s.get('is_baby_shelf', False),
                baby_shelf_restriction=s.get('baby_shelf_restriction'),
                security_type=s.get('security_type'),  # common_stock, preferred_stock, mixed, or null
                filing_date=s.get('filing_date'),
                effect_date=s.get('effect_date'),
                registration_statement=s.get('registration_statement'),
                filing_url=s.get('filing_url'),
                expiration_date=s.get('expiration_date'),
                last_banker=s.get('last_banker'),
                notes=s.get('notes')
            )
            for s in extracted_data.get('shelf_registrations', [])
        ]
        
        # Parse completed offerings
        completed_offerings = [
            CompletedOfferingModel(
                ticker=ticker,
                offering_type=o.get('offering_type'),
                shares_issued=o.get('shares_issued'),
                price_per_share=o.get('price_per_share'),
                amount_raised=o.get('amount_raised'),
                offering_date=o.get('offering_date'),
                filing_url=o.get('filing_url'),
                notes=o.get('notes')
            )
            for o in extracted_data.get('completed_offerings', [])
        ]
        
        # Parse S-1 offerings (NUEVO)
        from models.sec_dilution_models import S1OfferingModel
        s1_offerings = [
            S1OfferingModel(
                ticker=ticker,
                anticipated_deal_size=s1.get('anticipated_deal_size'),
                final_deal_size=s1.get('final_deal_size'),
                final_pricing=s1.get('final_pricing'),
                final_shares_offered=s1.get('final_shares_offered'),
                warrant_coverage=s1.get('warrant_coverage'),
                final_warrant_coverage=s1.get('final_warrant_coverage'),
                exercise_price=s1.get('exercise_price'),
                underwriter_agent=s1.get('underwriter_agent'),
                s1_filing_date=s1.get('s1_filing_date'),
                status=s1.get('status'),
                filing_url=s1.get('filing_url'),
                last_update_date=s1.get('last_update_date')
            )
            for s1 in extracted_data.get('s1_offerings', [])
        ]
        
        # Parse convertible notes (NUEVO)
        from models.sec_dilution_models import ConvertibleNoteModel
        convertible_notes = [
            ConvertibleNoteModel(
                ticker=ticker,
                total_principal_amount=cn.get('total_principal_amount'),
                remaining_principal_amount=cn.get('remaining_principal_amount'),
                conversion_price=cn.get('conversion_price'),
                total_shares_when_converted=cn.get('total_shares_when_converted'),
                remaining_shares_when_converted=cn.get('remaining_shares_when_converted'),
                issue_date=cn.get('issue_date'),
                convertible_date=cn.get('convertible_date'),
                maturity_date=cn.get('maturity_date'),
                underwriter_agent=cn.get('underwriter_agent'),
                filing_url=cn.get('filing_url'),
                notes=cn.get('notes')
            )
            for cn in extracted_data.get('convertible_notes', [])
        ]
        
        # Parse convertible preferred (NUEVO)
        from models.sec_dilution_models import ConvertiblePreferredModel
        convertible_preferred = [
            ConvertiblePreferredModel(
                ticker=ticker,
                series=cp.get('series'),
                total_dollar_amount_issued=cp.get('total_dollar_amount_issued'),
                remaining_dollar_amount=cp.get('remaining_dollar_amount'),
                conversion_price=cp.get('conversion_price'),
                total_shares_when_converted=cp.get('total_shares_when_converted'),
                remaining_shares_when_converted=cp.get('remaining_shares_when_converted'),
                issue_date=cp.get('issue_date'),
                convertible_date=cp.get('convertible_date'),
                maturity_date=cp.get('maturity_date'),
                underwriter_agent=cp.get('underwriter_agent'),
                filing_url=cp.get('filing_url'),
                notes=cp.get('notes')
            )
            for cp in extracted_data.get('convertible_preferred', [])
        ]
        
        # Parse equity lines (NUEVO)
        from models.sec_dilution_models import EquityLineModel
        equity_lines = [
            EquityLineModel(
                ticker=ticker,
                total_capacity=el.get('total_capacity'),
                remaining_capacity=el.get('remaining_capacity'),
                agreement_start_date=el.get('agreement_start_date'),
                agreement_end_date=el.get('agreement_end_date'),
                filing_url=el.get('filing_url'),
                notes=el.get('notes')
            )
            for el in extracted_data.get('equity_lines', [])
        ]
        
        # Metadata
        metadata = DilutionProfileMetadata(
            ticker=ticker,
            cik=cik,
            company_name=company_name,
            last_scraped_at=datetime.now(),
            source_filings=[
                {
                    'form_type': f['form_type'],
                    'filing_date': f['filing_date'],
                    'url': f['url']
                }
                for f in source_filings
            ],
            scrape_success=True
        )
        
        # Profile completo
        return SECDilutionProfile(
            ticker=ticker,
            company_name=company_name,
            cik=cik,
            current_price=current_price,
            shares_outstanding=shares_outstanding,
            float_shares=float_shares,
            warrants=warrants,
            atm_offerings=atm_offerings,
            shelf_registrations=shelf_registrations,
            completed_offerings=completed_offerings,
            s1_offerings=s1_offerings,
            convertible_notes=convertible_notes,
            convertible_preferred=convertible_preferred,
            equity_lines=equity_lines,
            metadata=metadata
        )
    
    def _create_empty_profile(
        self,
        ticker: str,
        cik: str,
        company_name: str,
        error: Optional[str] = None
    ) -> SECDilutionProfile:
        """Crear profile vacío cuando no hay datos"""
        
        metadata = DilutionProfileMetadata(
            ticker=ticker,
            cik=cik,
            company_name=company_name,
            last_scraped_at=datetime.now(),
            source_filings=[],
            scrape_success=False,
            scrape_error=error or "No dilution data found in recent filings"
        )
        
        return SECDilutionProfile(
            ticker=ticker,
            company_name=company_name,
            cik=cik,
            warrants=[],
            atm_offerings=[],
            shelf_registrations=[],
            completed_offerings=[],
            metadata=metadata
        )

