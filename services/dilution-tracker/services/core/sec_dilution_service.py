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
import os
import tempfile
import time
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
from bs4 import BeautifulSoup

from xai_sdk import Client
from xai_sdk.chat import user, system, file

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
from http_clients import http_clients
# Data services
from services.data.enhanced_data_fetcher import (
    EnhancedDataFetcher,
    get_filing_tier,
    quick_dilution_scan,
    should_process_with_grok,
    deduplicate_instruments,
    calculate_confidence_score,
    identify_risk_flags,
)
from services.data.shares_data_service import SharesDataService

# Grok services
from services.grok.grok_pool import GrokPool, get_grok_pool
from services.grok.chunk_processor import ChunkProcessor, ChunkResult, ChunkStatus
from services.grok.grok_extractor import GrokExtractor, get_grok_extractor
from services.grok.grok_normalizers import (
    normalize_grok_extraction_fields,
    normalize_grok_value,
    safe_get_for_key,
    to_hashable,
    normalize_warrant_fields,
    normalize_atm_fields,
    normalize_shelf_fields,
    normalize_completed_fields,
    normalize_s1_fields,
    normalize_convertible_note_fields,
    normalize_convertible_preferred_fields,
    normalize_equity_line_fields,
)

# Analysis services
from services.analysis.deduplication_service import (
    deduplicate_warrants,
    deduplicate_atm,
    deduplicate_shelfs,
    deduplicate_completed,
    deduplicate_s1,
    deduplicate_convertible_notes,
    deduplicate_convertible_preferred,
    deduplicate_equity_lines,
    filter_summary_warrants,
    impute_missing_exercise_prices,
    classify_warrant_status,
    classify_atm_status,
    classify_shelf_status,
    calculate_remaining_warrants,
    extract_warrant_type,
)
from services.analysis.instrument_linker import InstrumentLinker, InstrumentType, link_instruments_across_filings

# Market services
from services.market.market_data_calculator import MarketDataCalculator, get_market_data_calculator

# SEC services
from services.sec.sec_filing_fetcher import SECFilingFetcher
from services.sec.sec_fulltext_search import SECFullTextSearch, get_fulltext_search

# Extraction services
from services.extraction.html_section_extractor import HTMLSectionExtractor

# Cache services
from services.cache.cache_service import CacheService

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
        self.grok_api_key = settings.GROK_API_KEY  # Mantener para compatibilidad
        
        # Enhanced data fetcher for SEC-API /float and FMP cash data
        self.enhanced_fetcher = EnhancedDataFetcher()
        
        # Market data calculator for Baby Shelf, IB6 Float Value, etc.
        polygon_key = settings.POLYGON_API_KEY if hasattr(settings, 'POLYGON_API_KEY') else os.getenv('POLYGON_API_KEY')
        self.market_calculator = get_market_data_calculator(polygon_key) if polygon_key else None
        
        # Semáforo global para limitar requests concurrentes a SEC
        self._sec_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_SCRAPES)
        
        # GrokPool para múltiples API keys (procesamiento paralelo)
        try:
            self._grok_pool = get_grok_pool()
            logger.info("grok_pool_ready", 
                       num_keys=self._grok_pool.num_keys,
                       max_parallel=self._grok_pool.num_keys * 2)
        except Exception as e:
            self._grok_pool = None
            logger.warning("grok_pool_init_failed", error=str(e))
        
        # Full-Text Search for comprehensive dilution discovery
        self._fulltext_search = get_fulltext_search()
        
        # Stats for pre-screening optimization
        self._stats = {
            "grok_calls": 0,
            "grok_calls_parallel": 0,
            "skipped_prescreening": 0,
            "cache_hits": 0,
            "retries": 0,
            "timeouts": 0
        }
        
        # Inicializar servicios refactorizados
        self.cache_service = CacheService(redis, self.repository)
        self.filing_fetcher = SECFilingFetcher(db)
        self.html_extractor = HTMLSectionExtractor(self._grok_pool, self.grok_api_key)
        self.shares_service = SharesDataService(redis)
        self.grok_extractor = get_grok_extractor(self._grok_pool, self.grok_api_key)
        
        if not self.grok_api_key and not self._grok_pool:
            logger.warning("grok_api_key_not_configured")
    
    # ========================================================================
    # DELEGADORES: Métodos que delegan a servicios refactorizados
    # ========================================================================
    
    async def _get_cik_and_company_name(self, ticker: str) -> tuple[Optional[str], Optional[str]]:
        """Delegar a filing_fetcher"""
        return await self.filing_fetcher.get_cik_and_company_name(ticker)
    
    async def _fetch_all_filings_from_sec_api_io(self, ticker: str, cik: Optional[str] = None) -> List[Dict]:
        """Delegar a filing_fetcher"""
        return await self.filing_fetcher.fetch_all_filings_from_sec_api_io(ticker, cik)
    
    async def _fetch_424b_filings(self, cik: str, max_count: int = 100) -> List[Dict]:
        """Delegar a filing_fetcher"""
        return await self.filing_fetcher.fetch_424b_filings(cik, max_count)
    
    def _filter_relevant_filings(self, filings: List[Dict]) -> List[Dict]:
        """Delegar a filing_fetcher"""
        return self.filing_fetcher.filter_relevant_filings(filings)
    
    async def _download_filings(self, filings: List[Dict]) -> List[Dict]:
        """Delegar a filing_fetcher"""
        return await self.filing_fetcher.download_filings(filings)
    
    async def _extract_with_multipass_grok(
        self, ticker: str, company_name: str, 
        filing_contents: List[Dict], parsed_tables: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Delegar a grok_extractor"""
        return await self.grok_extractor.extract_with_multipass_grok(
            ticker, company_name, filing_contents, parsed_tables
        )
    
    async def _adjust_warrants_for_splits(self, ticker: str, warrants: List[Dict]) -> List[Dict]:
        """Delegar a shares_service"""
        return await self.shares_service.adjust_warrants_for_splits(ticker, warrants)
    
    async def get_shares_history(self, ticker: str, cik: Optional[str] = None) -> Dict[str, Any]:
        """Delegar a shares_service"""
        return await self.shares_service.get_shares_history(ticker, cik)
    
    async def get_from_cache_only(self, ticker: str) -> Optional[SECDilutionProfile]:
        """Delegar a cache_service"""
        return await self.cache_service.get_from_cache_only(ticker)
    
    # ========================================================================
    # FULL-TEXT SEARCH HELPERS
    # ========================================================================
    
    def _boost_priority_filings(
        self, 
        filings: List[Dict], 
        priority_filings: List[Dict]
    ) -> List[Dict]:
        """
        Reordena filings para priorizar los encontrados por Full-Text Search.
        Los filings con matches de instrumentos dilutivos van primero.
        """
        if not priority_filings:
            return filings
        
        # Crear set de accession numbers prioritarios
        priority_accessions = set()
        for pf in priority_filings:
            acc = pf.get('accessionNo', '').replace('-', '')
            if acc:
                priority_accessions.add(acc)
        
        # Separar en prioritarios y resto
        prioritized = []
        rest = []
        
        for f in filings:
            # Normalizar accession number para comparar
            filing_acc = f.get('accession_number', '').replace('-', '')
            if not filing_acc:
                # Intentar construir desde URL
                url = f.get('url', '')
                if url:
                    import re
                    match = re.search(r'/(\d{10})-(\d{2})-(\d{6})/', url)
                    if match:
                        filing_acc = match.group(1) + match.group(2) + match.group(3)
            
            if filing_acc in priority_accessions:
                # Marcar como prioritario
                f['_priority_boost'] = True
                f['_from_fulltext'] = True
                prioritized.append(f)
            else:
                rest.append(f)
        
        # Combinar: prioritarios primero
        result = prioritized + rest
        
        logger.debug("filings_reordered_by_priority",
                    total=len(result),
                    prioritized=len(prioritized),
                    rest=len(rest))
        
        return result
    
    def _enrich_with_prospectus_data(
        self, 
        extracted_data: Dict, 
        prospectus_data: List[Dict]
    ) -> Dict:
        """
        Enriquece extracted_data con datos estructurados de S-1/424B4 API.
        
        La API ya devuelve:
        - Securities (tipo y cantidad)
        - Public offering price (per share y total)
        - Underwriters
        - Proceeds before expenses
        """
        if not prospectus_data:
            return extracted_data
        
        # Inicializar si no existe
        if 'completed_offerings' not in extracted_data:
            extracted_data['completed_offerings'] = []
        
        for prospect in prospectus_data:
            form_type = prospect.get('formType', '')
            filed_at = prospect.get('filedAt', '')[:10] if prospect.get('filedAt') else None
            
            # Solo procesar 424B4 y 424B5 (ofertas completadas)
            if form_type not in ['424B4', '424B5']:
                continue
            
            # Extraer datos estructurados
            pop = prospect.get('publicOfferingPrice', {})
            proceeds = prospect.get('proceedsBeforeExpenses', {})
            securities = prospect.get('securities', [])
            underwriters = prospect.get('underwriters', [])
            
            # Construir offering
            offering = {
                'source': 'SEC-API-S1-424B4',
                'form_type': form_type,
                'filing_date': filed_at,
                'accession_no': prospect.get('accessionNo'),
                'price_per_share': pop.get('perShare'),
                'total_amount': pop.get('total'),
                'total_amount_text': pop.get('totalText'),
                'proceeds_before_expenses': proceeds.get('total'),
                'securities': [s.get('name', '') for s in securities],
                'underwriters': [u.get('name', '') for u in underwriters],
            }
            
            # Evitar duplicados
            existing_accessions = {
                o.get('accession_no') for o in extracted_data['completed_offerings']
                if o.get('accession_no')
            }
            
            if offering['accession_no'] not in existing_accessions:
                extracted_data['completed_offerings'].append(offering)
                logger.debug("prospectus_offering_added",
                           form_type=form_type,
                           total=pop.get('totalText'),
                           underwriters=len(underwriters))
        
        return extracted_data
    
    async def get_dilution_profile(self, ticker: str, force_refresh: bool = False) -> Optional[SECDilutionProfile]:
        """
        Obtener perfil de dilución (con caché multinivel)
        """
        ticker = ticker.upper()
        
        # 1. Si no force_refresh, intentar cache
        if not force_refresh:
            # Redis (L1)
            cached = await self.cache_service.get_from_redis(ticker)
            if cached:
                self._stats["cache_hits"] += 1
                return cached
            
            # PostgreSQL (L2)
            db_profile = await self.repository.get_profile(ticker)
            if db_profile:
                # Guardar en Redis
                await self.cache_service.save_to_redis(ticker, db_profile)
                return db_profile
        
        # 2. Scraping
        profile = await self._scrape_and_analyze(ticker)
        
        if profile:
            # Guardar en PostgreSQL
            await self.repository.save_profile(profile)
            # Guardar en Redis
            await self.cache_service.save_to_redis(ticker, profile)
        
        return profile
    
    async def invalidate_cache(self, ticker: str) -> bool:
        """Delegar a cache_service"""
        return await self.cache_service.invalidate_cache(ticker)
    
    # ========================================================================
    # HELPER: Chunk size optimization
    # ========================================================================
    
    def _calculate_optimal_chunk_size(self, filings: List[Dict], form_type_hint: str = "") -> int:
        """
        Calcula el chunk size óptimo basado en el tamaño promedio de los filings.
        
        OPTIMIZACIÓN: Grok puede manejar ~130K tokens (~500KB de texto).
        Maximizar filings por chunk reduce el número de llamadas API.
        
        REGLAS:
        - <10KB promedio → chunk de 10 filings (424B3 pequeños)
        - 10-30KB promedio → chunk de 7 filings
        - 30-50KB promedio → chunk de 5 filings  
        - 50-100KB promedio → chunk de 3 filings
        - >100KB promedio → chunk de 2 filings (DEF 14A grandes)
        
        Args:
            filings: Lista de filings con contenido
            form_type_hint: Tipo de form para ajustar heurística
            
        Returns:
            Tamaño óptimo de chunk (2-10)
        """
        if not filings:
            return 5  # Default
        
        # Calcular tamaño promedio
        total_size = sum(len(f.get('content', '')) for f in filings)
        avg_size = total_size / len(filings)
        avg_size_kb = avg_size / 1024
        
        # Determinar chunk size basado en tamaño promedio
        if avg_size_kb < 10:
            chunk_size = 10  # 424B3 pequeños, ~7KB cada uno
        elif avg_size_kb < 30:
            chunk_size = 7
        elif avg_size_kb < 50:
            chunk_size = 5
        elif avg_size_kb < 100:
            chunk_size = 3
        else:
            chunk_size = 2  # DEF 14A pueden ser 500KB+
        
        # Ajustar para tipos específicos que sabemos que son pesados
        if 'DEF' in form_type_hint or '14A' in form_type_hint:
            chunk_size = min(chunk_size, 3)
        elif 'S-3' in form_type_hint or 'S-1' in form_type_hint:
            chunk_size = min(chunk_size, 4)
        
        logger.debug("optimal_chunk_size_calculated",
                    filings_count=len(filings),
                    avg_size_kb=f"{avg_size_kb:.1f}",
                    chunk_size=chunk_size,
                    form_type_hint=form_type_hint)
        
        return chunk_size
    
    # ========================================================================
    # NEW: ENHANCED DATA ENDPOINTS (SEC-API /float, FMP Cash)
    # ========================================================================
    
    async def _fetch_shares_from_sec_edgar(self, ticker: str, cik: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch historical shares from SEC EDGAR Company Facts API (XBRL).
        FREE and official SEC data.
        """
        try:
            # Get CIK if not provided
            if not cik:
                cik, _ = await self._get_cik_and_company_name(ticker)
            
            if not cik:
                logger.warning("no_cik_for_edgar_shares", ticker=ticker)
                return None
            
            # Pad CIK to 10 digits
            cik_padded = cik.lstrip('0').zfill(10)
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": "TradeulApp/1.0 (support@tradeul.com)"}
                )
                
                if response.status_code != 200:
                    logger.warning("sec_edgar_shares_failed", ticker=ticker, status=response.status_code)
                    return None
                
                data = response.json()
            
            # Extract shares outstanding from XBRL
            facts = data.get('facts', {}).get('us-gaap', {})
            
            # Try multiple fields
            share_fields = [
                'CommonStockSharesOutstanding',
                'CommonStockSharesIssued',
                'WeightedAverageNumberOfSharesOutstandingBasic',
            ]
            
            records = []
            for field in share_fields:
                field_data = facts.get(field, {})
                shares_list = field_data.get('units', {}).get('shares', [])
                
                if shares_list:
                    for item in shares_list:
                        form = item.get('form', '')
                        if form not in ['10-K', '10-Q', '10-K/A', '10-Q/A']:
                            continue
                        
                        end_date = item.get('end')
                        value = item.get('val')
                        filed = item.get('filed')
                        
                        if end_date and value:
                            records.append({
                                'date': end_date,
                                'shares': int(value),
                                'form': form,
                                'filed': filed
                            })
                    
                    if records:
                        break
            
            if not records:
                return None
            
            # Deduplicate by date (keep latest filed)
            seen = {}
            for r in records:
                d = r['date']
                if d not in seen or r['filed'] > seen[d]['filed']:
                    seen[d] = r
            
            sorted_records = sorted(seen.values(), key=lambda x: x['date'])
            
            # Calculate dilution metrics
            now = datetime.now()
            current = sorted_records[-1] if sorted_records else None
            
            def find_closest(target_date: str) -> Optional[Dict]:
                closest = None
                min_diff = float('inf')
                for rec in sorted_records:
                    try:
                        rec_dt = datetime.strptime(rec['date'][:10], "%Y-%m-%d")
                        tgt_dt = datetime.strptime(target_date, "%Y-%m-%d")
                        diff = abs((rec_dt - tgt_dt).days)
                        if diff < min_diff:
                            min_diff = diff
                            closest = rec
                    except:
                        continue
                return closest if min_diff < 120 else None
            
            one_year_ago = (now - timedelta(days=365)).strftime("%Y-%m-%d")
            three_years_ago = (now - timedelta(days=365*3)).strftime("%Y-%m-%d")
            five_years_ago = (now - timedelta(days=365*5)).strftime("%Y-%m-%d")
            
            yr1_rec = find_closest(one_year_ago)
            yr3_rec = find_closest(three_years_ago)
            yr5_rec = find_closest(five_years_ago)
            
            def calc_dilution(old: int, new: int) -> float:
                if old > 0:
                    return ((new - old) / old) * 100
                return 0.0
            
            result = {
                "source": "SEC EDGAR XBRL (official)",
                "current": {
                    "date": current['date'] if current else None,
                    "outstanding_shares": current['shares'] if current else None,
                    "form": current['form'] if current else None,
                },
                "all_records": [
                    {"period": r['date'], "outstanding_shares": r['shares'], "form": r['form']}
                    for r in sorted_records
                ],
                "dilution_summary": {},
                "history": sorted_records,  # For chart
            }
            
            if current and yr1_rec:
                result["dilution_summary"]["1_year"] = round(calc_dilution(yr1_rec['shares'], current['shares']), 2)
            if current and yr3_rec:
                result["dilution_summary"]["3_years"] = round(calc_dilution(yr3_rec['shares'], current['shares']), 2)
            if current and yr5_rec:
                result["dilution_summary"]["5_years"] = round(calc_dilution(yr5_rec['shares'], current['shares']), 2)
            
            logger.info("sec_edgar_shares_fetched", ticker=ticker, records=len(sorted_records))
            return result
            
        except Exception as e:
            logger.error("sec_edgar_shares_exception", ticker=ticker, error=str(e))
            return None
    
    async def get_cash_data(self, ticker: str) -> Dict[str, Any]:
        """
        Get cash position and runway data from FMP API.
        
        Returns:
            Dict with cash history, burn rate, runway, and risk level.
        """
        try:
            ticker = ticker.upper()
            
            # Check Redis cache first
            cache_key = f"sec_dilution:cash_data:{ticker}"
            cached = await self.redis.get(cache_key, deserialize=True)
            if cached:
                logger.info("cash_data_from_cache", ticker=ticker)
                
                # 🚀 INYECTAR ESTIMACIÓN REAL-TIME
                try:
                    real_time = await self._calculate_real_time_estimation(ticker, cached)
                    if real_time:
                        cached['real_time_estimate'] = real_time
                except Exception as rt_error:
                    logger.error("real_time_estimation_cache_failed", error=str(rt_error))
                
                return cached
            
            # Fetch from FMP
            result = await self.enhanced_fetcher.fetch_cash_data(ticker)
            
            # 🚀 INYECTAR ESTIMACIÓN REAL-TIME
            if result and result.get("error") is None:
                try:
                    real_time = await self._calculate_real_time_estimation(ticker, result)
                    if real_time:
                        result['real_time_estimate'] = real_time
                except Exception as rt_error:
                    logger.error("real_time_estimation_fetch_failed", error=str(rt_error))
            
            # Cache for 4 hours
            if result.get("error") is None:
                await self.redis.set(cache_key, result, ttl=14400, serialize=True)
            
            return result
            
        except Exception as e:
            logger.error("get_cash_data_failed", ticker=ticker, error=str(e))
            return {"error": str(e)}

    async def _calculate_real_time_estimation(self, ticker: str, cash_data: Dict) -> Optional[Dict]:
        """
        Calcula estimación de caja en tiempo real (Ingeniería de Flujo)
        """
        try:
            if not cash_data or not cash_data.get('last_report_date'):
                return None

            last_report_date_str = cash_data.get('last_report_date')
            # Asegurar float y manejar nulos
            last_cash = float(cash_data.get('cash_and_equivalents') or 0)
            quarterly_burn = float(cash_data.get('quarterly_cash_burn') or 0)
            
            # Fechas
            try:
                last_report_date = datetime.strptime(last_report_date_str, "%Y-%m-%d").date()
            except ValueError:
                return None
                
            today = datetime.now().date()
            days_elapsed = (today - last_report_date).days
            if days_elapsed < 0: days_elapsed = 0
            
            # 1. Burn Prorrateado
            daily_burn = quarterly_burn / 91.0
            # Si quarterly_burn es positivo (gasto), prorated es negativo (resta caja)
            prorated_burn = daily_burn * days_elapsed * -1
            
            # 2. Capital Levantado (Desde DB interna)
            capital_raise = 0.0
            raise_details = []
            
            try:
                # Usar cache only para evitar llamadas recursivas o scraping
                profile_response = await self.get_from_cache_only(ticker)
                
                if profile_response and profile_response.profile and profile_response.profile.completed_offerings:
                    for off in profile_response.profile.completed_offerings:
                        # Manejar formato de fecha que puede venir como string o date
                        off_date = off.completion_date
                        if isinstance(off_date, str):
                            try:
                                off_date = datetime.strptime(off_date, "%Y-%m-%d").date()
                            except:
                                continue
                                
                        if off_date > last_report_date:
                            amount = float(off.gross_proceeds or 0)
                            if amount > 0:
                                capital_raise += amount
                                raise_details.append({
                                    "date": str(off_date),
                                    "type": off.offering_type or "Offering",
                                    "amount": amount
                                })
            except Exception as db_e:
                logger.warning(f"Error fetching completed offerings for RT calc: {db_e}")

            # 3. Resultado Final
            current_est = last_cash + prorated_burn + capital_raise
            
            return {
                "report_date": last_report_date_str,
                "days_elapsed": days_elapsed,
                "prorated_burn": prorated_burn,
                "capital_raise": capital_raise,
                "current_cash_estimate": current_est,
                "raise_details": raise_details
            }
        except Exception as e:
            logger.error(f"Error calculating RT estimation: {e}")
            return None
    
    async def get_enhanced_dilution_profile(self, ticker: str, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get complete enhanced dilution profile with:
        - Standard SEC dilution data (warrants, ATM, shelf, etc.)
        - Shares outstanding history from SEC-API /float
        - Cash position and runway from FMP
        - Risk flags
        
        Returns:
            Complete enhanced profile dict.
        """
        try:
            ticker = ticker.upper()
            
            # Get base profile
            profile = await self.get_dilution_profile(ticker, force_refresh)
            
            # Fetch enhanced data in parallel
            shares_history, cash_data, current_price = await asyncio.gather(
                self.get_shares_history(ticker),
                self.get_cash_data(ticker),
                self.enhanced_fetcher.fetch_current_price(ticker),
                return_exceptions=True
            )
            
            # Handle exceptions
            if isinstance(shares_history, Exception):
                shares_history = {"error": str(shares_history)}
            if isinstance(cash_data, Exception):
                cash_data = {"error": str(cash_data)}
            if isinstance(current_price, Exception):
                current_price = None
            
            # Generate risk flags
            risk_flags = []
            if profile:
                risk_flags = identify_risk_flags(
                    warrants=[w.dict() if hasattr(w, 'dict') else w for w in profile.warrants],
                    convertibles=[c.dict() if hasattr(c, 'dict') else c for c in profile.convertible_notes],
                    atm_offerings=[a.dict() if hasattr(a, 'dict') else a for a in profile.atm_offerings],
                    shares_history=shares_history if "error" not in shares_history else None,
                    cash_data=cash_data if cash_data.get("error") is None else None
                )
            
            return {
                "ticker": ticker,
                "profile": profile.dict() if profile else None,
                "dilution_analysis": profile.calculate_potential_dilution() if profile else None,
                "shares_history": shares_history,
                "cash_data": cash_data,
                "current_price": current_price,
                "risk_flags": risk_flags,
                "cached": False,
                "optimization_stats": self._stats.copy()
            }
            
        except Exception as e:
            logger.error("get_enhanced_dilution_profile_failed", ticker=ticker, error=str(e))
            return {"error": str(e), "ticker": ticker}
    
    async def _scrape_and_analyze(self, ticker: str) -> Optional[SECDilutionProfile]:
        """
        Proceso completo de scraping y análisis con Grok
        
        FLUJO HÍBRIDO (Full-Text Search + Grok):
        1. Obtener CIK del ticker
        2. NUEVO: Full-Text Search para discovery de instrumentos dilutivos
        3. NUEVO: Obtener datos estructurados de S-1/424B4 API
        4. Buscar filings adicionales (fallback)
        5. Priorizar filings basado en Full-Text Search
        6. Descargar contenido HTML
        7. Usar Grok API para extraer datos complejos
        8. Combinar Full-Text + S-1 API + Grok
        9. Obtener precio actual y shares outstanding
        """
        try:
            logger.info("starting_sec_scrape_hybrid", ticker=ticker)
            
            # 1. Obtener CIK
            cik, company_name = await self._get_cik_and_company_name(ticker)
            if not cik:
                logger.error("cik_not_found", ticker=ticker)
                return None
            
            logger.info("cik_found", ticker=ticker, cik=cik, company_name=company_name)
            
            # ================================================================
            # 2. NUEVO: Full-Text Search Discovery (TODAS las keywords dilutivas)
            # ================================================================
            fulltext_discovery = None
            priority_filings_from_fulltext = []
            prospectus_data = []
            
            try:
                logger.info("fulltext_discovery_starting", ticker=ticker, cik=cik)
                
                # Comprehensive discovery con TODAS las keywords
                fulltext_discovery = await self._fulltext_search.comprehensive_dilution_discovery(
                    cik=cik,
                    ticker=ticker,
                    start_date="2015-01-01"  # 10 años para warrants de larga duración
                )
                
                if fulltext_discovery:
                    summary = fulltext_discovery.get("summary", {})
                    logger.info("fulltext_discovery_completed",
                              ticker=ticker,
                              total_filings=summary.get("total_filings_with_dilution", 0),
                              categories=len(summary.get("categories_detected", [])),
                              has_warrants=summary.get("has_warrants"),
                              has_atm=summary.get("has_atm"),
                              has_shelf=summary.get("has_shelf"),
                              has_convertibles=summary.get("has_convertibles"))
                    
                    # Obtener filings prioritarios del Full-Text Search
                    priority_filings_from_fulltext = fulltext_discovery.get("priority_filings", [])
                    
                    # Datos estructurados de S-1/424B4 (ya parseados!)
                    prospectus_data = fulltext_discovery.get("prospectus_data", [])
                    if prospectus_data:
                        logger.info("prospectus_structured_data_found",
                                  ticker=ticker,
                                  count=len(prospectus_data))
                    
            except Exception as e:
                logger.warning("fulltext_discovery_failed_continuing", 
                             ticker=ticker, error=str(e))
            
            # ================================================================
            # 3. Buscar filings adicionales (método tradicional como fallback)
            # ================================================================
            filings = await self._fetch_all_filings_from_sec_api_io(ticker, cik)
            
            # 3.5 CRÍTICO: Buscar TODOS los 424B
            filings_424b = await self._fetch_424b_filings(cik, max_count=100)
            if filings_424b:
                logger.info("424b_filings_found", ticker=ticker, count=len(filings_424b))
                filings.extend(filings_424b)
            
            if not filings and not priority_filings_from_fulltext:
                logger.warning("no_filings_found", ticker=ticker, cik=cik)
                return self._create_empty_profile(ticker, cik, company_name)
            
            logger.info("filings_found_total", ticker=ticker, 
                       count=len(filings), 
                       with_424b=len(filings_424b),
                       from_fulltext=len(priority_filings_from_fulltext))
            
            # ================================================================
            # 4. Filtrar y PRIORIZAR filings usando Full-Text Search results
            # ================================================================
            relevant_filings = self._filter_relevant_filings(filings)
            
            # Boost priority para filings encontrados por Full-Text Search
            if priority_filings_from_fulltext:
                relevant_filings = self._boost_priority_filings(
                    relevant_filings, 
                    priority_filings_from_fulltext
                )
            
            logger.info("relevant_filings_selected", ticker=ticker, count=len(relevant_filings), 
                       forms=[f['form_type'] for f in relevant_filings[:20]])
            
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
            
            # 5. NUEVO: Enriquecer con datos estructurados de S-1/424B4 API
            if prospectus_data:
                extracted_data = self._enrich_with_prospectus_data(
                    extracted_data, 
                    prospectus_data
                )
            
            # 5.5. NUEVO: Añadir metadata del Full-Text Discovery
            if fulltext_discovery:
                extracted_data['_fulltext_discovery'] = {
                    'categories_detected': fulltext_discovery.get('summary', {}).get('categories_detected', []),
                    'total_filings_scanned': fulltext_discovery.get('summary', {}).get('total_filings_with_dilution', 0),
                    'has_warrants': fulltext_discovery.get('summary', {}).get('has_warrants', False),
                    'has_atm': fulltext_discovery.get('summary', {}).get('has_atm', False),
                    'has_shelf': fulltext_discovery.get('summary', {}).get('has_shelf', False),
                    'has_convertibles': fulltext_discovery.get('summary', {}).get('has_convertibles', False),
                }
            
            # 6. NUEVO: Ajustar warrants por stock splits
            if extracted_data.get('warrants'):
                extracted_data['warrants'] = await self._adjust_warrants_for_splits(
                    ticker, 
                    extracted_data['warrants']
                )
            
            # 7. Obtener precio actual y shares outstanding
            current_price, shares_outstanding, float_shares = await self._get_current_market_data(ticker)
            
            # 7. Construir profile completo
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
            
            # 8. NUEVO: Calcular métricas de Baby Shelf
            profile = await self._enrich_profile_with_baby_shelf_calculations(
                profile,
                float_shares=float_shares
            )
            
            logger.info("sec_scrape_completed", ticker=ticker)
            return profile
            
        except Exception as e:
            logger.error("scrape_and_analyze_failed", ticker=ticker, error=str(e))
            return None
    
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
    
    def _sanitize_field_lengths(self, item: Dict, field_limits: Dict[str, int]) -> Dict:
        """
        Sanitiza campos string que excedan max_length de Pydantic.
        Si un campo es demasiado largo, lo trunca y mueve el contenido a notes.
        
        Args:
            item: Diccionario con datos del item
            field_limits: Dict con nombre_campo -> max_length
            
        Returns:
            Item sanitizado
        """
        sanitized = item.copy()
        overflow_notes = []
        
        for field, max_len in field_limits.items():
            if field in sanitized and isinstance(sanitized[field], str):
                value = sanitized[field]
                if len(value) > max_len:
                    # Truncar el campo
                    truncated = value[:max_len - 3] + "..."
                    sanitized[field] = truncated
                    # Guardar contenido original en notes
                    overflow_notes.append(f"[{field}]: {value}")
        
        # Si hubo truncaciones, añadir a notes
        if overflow_notes:
            existing_notes = sanitized.get('notes') or ""
            if existing_notes:
                existing_notes += " | "
            sanitized['notes'] = existing_notes + " | ".join(overflow_notes)
        
        return sanitized
    
    async def _enrich_profile_with_baby_shelf_calculations(
        self,
        profile: SECDilutionProfile,
        float_shares: Optional[int] = None
    ) -> SECDilutionProfile:
        """
        Enriquece el perfil con cálculos de Baby Shelf, IB6 Float Value, etc.
        
        Usa MarketDataCalculator para:
        1. Obtener Highest 60-Day Close desde Polygon
        2. Calcular IB6 Float Value = Float × Highest60DayClose × (1/3)
        3. Calcular Current Raisable Amount
        4. Calcular Price To Exceed Baby Shelf
        5. Determinar si ATM está limitado por Baby Shelf
        """
        ticker = profile.ticker
        
        if not self.market_calculator:
            logger.warning("market_calculator_not_available", ticker=ticker)
            return profile
        
        # Usar float_shares del perfil si no se proporciona
        float_shares = float_shares or profile.float_shares
        
        if not float_shares:
            logger.warning("no_float_shares_for_baby_shelf_calc", ticker=ticker)
            return profile
        
        try:
            # Obtener Highest 60-Day Close
            highest_close = await self.market_calculator.get_highest_60_day_close(ticker)
            
            if not highest_close:
                logger.warning("no_highest_close_for_baby_shelf_calc", ticker=ticker)
                return profile
            
            # Calcular IB6 Float Value
            ib6_float_value = self.market_calculator.calculate_ib6_float_value(
                float_shares, highest_close
            )
            
            # Determinar si es Baby Shelf
            is_baby_shelf = self.market_calculator.is_baby_shelf_company(
                float_shares, highest_close
            )
            
            logger.info("baby_shelf_calculated", ticker=ticker,
                       is_baby_shelf=is_baby_shelf,
                       ib6_float_value=float(ib6_float_value),
                       highest_60_day_close=float(highest_close))
            
            # Enriquecer Shelf Registrations
            for shelf in profile.shelf_registrations:
                shelf.highest_60_day_close = highest_close
                shelf.ib6_float_value = ib6_float_value
                shelf.outstanding_shares_calc = profile.shares_outstanding
                shelf.float_shares_calc = float_shares
                shelf.is_baby_shelf = is_baby_shelf
                shelf.baby_shelf_restriction = is_baby_shelf
                shelf.last_update_date = datetime.now().date()
                
                # Calcular Current Raisable Amount
                if shelf.total_capacity:
                    total_raised = shelf.total_amount_raised or Decimal("0")
                    raised_12mo = shelf.total_amount_raised_last_12mo or Decimal("0")
                    
                    current_raisable = self.market_calculator.calculate_current_raisable_amount(
                        ib6_float_value,
                        shelf.total_capacity,
                        total_raised,
                        raised_12mo
                    )
                    shelf.current_raisable_amount = current_raisable
                    
                    # Calcular Price To Exceed Baby Shelf
                    if is_baby_shelf:
                        price_to_exceed = self.market_calculator.calculate_price_to_exceed_baby_shelf(
                            shelf.total_capacity,
                            float_shares
                        )
                        shelf.price_to_exceed_baby_shelf = price_to_exceed
            
            # Enriquecer ATM Offerings
            for atm in profile.atm_offerings:
                atm.last_update_date = datetime.now().date()
                
                if is_baby_shelf and atm.remaining_capacity:
                    # El ATM puede estar limitado por Baby Shelf
                    atm.remaining_capacity_without_restriction = atm.remaining_capacity
                    
                    # Current raisable bajo IB6
                    current_raisable = self.market_calculator.calculate_current_raisable_amount(
                        ib6_float_value,
                        atm.total_capacity or atm.remaining_capacity,
                        Decimal("0"),  # ATM ya descuenta lo usado
                        Decimal("0")
                    )
                    
                    if current_raisable < atm.remaining_capacity:
                        atm.atm_limited_by_baby_shelf = True
                        # El effective remaining es el menor entre IB6 y el remaining real
                        atm.remaining_capacity = current_raisable
                    else:
                        atm.atm_limited_by_baby_shelf = False
            
            return profile
            
        except Exception as e:
            logger.error("baby_shelf_calc_failed", ticker=ticker, error=str(e))
            return profile
    
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
        
        # Parse warrants (incluyendo metadatos de calidad de datos, status, split adjustment y ejercicios)
        warrants = [
            WarrantModel(
                ticker=ticker,
                issue_date=w.get('issue_date'),
                outstanding=w.get('outstanding'),
                exercise_price=w.get('exercise_price'),
                expiration_date=w.get('expiration_date'),
                potential_new_shares=w.get('potential_new_shares'),
                notes=w.get('notes'),
                status=w.get('status'),  # Active, Exercised, Replaced, Historical_Summary
                is_summary_row=w.get('is_summary_row'),
                exclude_from_dilution=w.get('exclude_from_dilution'),
                imputed_fields=w.get('imputed_fields'),
                # Split adjustment fields
                split_adjusted=w.get('split_adjusted'),
                split_factor=w.get('split_factor'),
                original_exercise_price=w.get('original_exercise_price'),
                original_outstanding=w.get('original_outstanding'),
                # Exercise tracking fields
                total_issued=w.get('total_issued'),
                exercised=w.get('exercised_count') or w.get('exercised'),
                expired=w.get('expired_count') or w.get('expired'),
                remaining=w.get('remaining'),
                last_update_date=w.get('last_update_date'),
                # NEW: Additional DilutionTracker fields
                known_owners=w.get('known_owners'),
                underwriter_agent=w.get('underwriter_agent') or w.get('placement_agent'),
                price_protection=w.get('price_protection'),
                pp_clause=w.get('pp_clause'),
                exercisable_date=w.get('exercisable_date')
            )
            for w in extracted_data.get('warrants', [])
        ]
        
        logger.info("warrants_parsed", ticker=ticker, count=len(warrants))
        
        # Parse ATM offerings (con nuevos campos)
        # Límites de campos string según Pydantic models
        atm_limits = {'placement_agent': 255, 'status': 50}
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
            for a in [self._sanitize_field_lengths(x, atm_limits) for x in extracted_data.get('atm_offerings', [])]
        ]
        
        # Parse shelf registrations (con nuevos campos)
        shelf_limits = {'security_type': 50, 'registration_statement': 50, 'last_banker': 255, 'status': 50}
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
                status=s.get('status'),  # Active, Expired, etc.
                notes=s.get('notes')
            )
            for s in [self._sanitize_field_lengths(x, shelf_limits) for x in extracted_data.get('shelf_registrations', [])]
        ]
        
        # Parse completed offerings
        # CRÍTICO: offering_type tiene max_length=50, Grok a veces devuelve descripciones largas
        completed_limits = {'offering_type': 50}
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
            for o in [self._sanitize_field_lengths(x, completed_limits) for x in extracted_data.get('completed_offerings', [])]
        ]
        
        # Parse S-1 offerings (NUEVO)
        from models.sec_dilution_models import S1OfferingModel
        s1_limits = {'underwriter_agent': 255, 'status': 50}
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
            for s1 in [self._sanitize_field_lengths(x, s1_limits) for x in extracted_data.get('s1_offerings', [])]
        ]
        
        # Parse convertible notes (con campos adicionales de DilutionTracker)
        from models.sec_dilution_models import ConvertibleNoteModel
        cn_limits = {'underwriter_agent': 255, 'series_name': 255}
        convertible_notes = [
            ConvertibleNoteModel(
                ticker=ticker,
                series_name=cn.get('series_name'),  # CRITICAL: Include series name
                total_principal_amount=cn.get('total_principal_amount'),
                remaining_principal_amount=cn.get('remaining_principal_amount'),
                conversion_price=cn.get('conversion_price'),
                original_conversion_price=cn.get('original_conversion_price'),
                conversion_ratio=cn.get('conversion_ratio') or cn.get('conversion_rate'),
                total_shares_when_converted=cn.get('total_shares_when_converted'),
                remaining_shares_when_converted=cn.get('remaining_shares_when_converted'),
                interest_rate=cn.get('interest_rate'),
                issue_date=cn.get('issue_date'),
                convertible_date=cn.get('convertible_date'),
                maturity_date=cn.get('maturity_date'),
                underwriter_agent=cn.get('underwriter_agent'),
                filing_url=cn.get('filing_url'),
                notes=cn.get('notes'),
                # Registration and protection fields
                is_registered=cn.get('is_registered'),
                registration_type=cn.get('registration_type'),
                known_owners=cn.get('known_owners'),
                price_protection=cn.get('price_protection'),
                pp_clause=cn.get('pp_clause'),
                # Toxic indicators
                variable_rate_adjustment=cn.get('variable_rate_adjustment'),
                floor_price=cn.get('floor_price'),
                is_toxic=cn.get('is_toxic'),
                last_update_date=cn.get('last_update_date')
            )
            for cn in [self._sanitize_field_lengths(x, cn_limits) for x in extracted_data.get('convertible_notes', [])]
        ]
        
        # Parse convertible preferred (con campos adicionales de DilutionTracker)
        from models.sec_dilution_models import ConvertiblePreferredModel
        cp_limits = {'series': 50, 'underwriter_agent': 255, 'status': 50}
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
                notes=cp.get('notes'),
                # NEW: Additional DilutionTracker fields
                known_owners=cp.get('known_owners'),
                price_protection=cp.get('price_protection'),
                pp_clause=cp.get('pp_clause'),
                status=cp.get('status'),
                last_update_date=cp.get('last_update_date')
            )
            for cp in [self._sanitize_field_lengths(x, cp_limits) for x in extracted_data.get('convertible_preferred', [])]
        ]
        
        # Parse equity lines (con campos adicionales de DilutionTracker)
        from models.sec_dilution_models import EquityLineModel
        el_limits = {'counterparty': 255}
        equity_lines = [
            EquityLineModel(
                ticker=ticker,
                total_capacity=el.get('total_capacity'),
                remaining_capacity=el.get('remaining_capacity'),
                agreement_start_date=el.get('agreement_start_date'),
                agreement_end_date=el.get('agreement_end_date'),
                filing_url=el.get('filing_url'),
                notes=el.get('notes'),
                # NEW: Additional DilutionTracker fields
                counterparty=el.get('counterparty'),
                last_update_date=el.get('last_update_date')
            )
            for el in [self._sanitize_field_lengths(x, el_limits) for x in extracted_data.get('equity_lines', [])]
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

