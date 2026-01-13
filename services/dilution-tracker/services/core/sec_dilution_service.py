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
    deduplicate_instruments,
    calculate_confidence_score,
    identify_risk_flags,
)
from services.data.shares_data_service import SharesDataService

# NOTE: Grok services removed - now using ContextualDilutionExtractor v4

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
from services.sec.sec_filing_fetcher import SECFilingFetcher, get_sec_filing_fetcher
from services.sec.sec_fulltext_search import SECFullTextSearch, get_fulltext_search
# NOTE: filing_grouper removed - now using ContextualDilutionExtractor v4

# Extraction services - v4 Contextual Extractor (Gemini long context)
from services.extraction.contextual_extractor import ContextualDilutionExtractor

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
        
        # Enhanced data fetcher for SEC-API /float and FMP cash data
        self.enhanced_fetcher = EnhancedDataFetcher()
        
        # Market data calculator for Baby Shelf, IB6 Float Value, etc.
        polygon_key = settings.POLYGON_API_KEY if hasattr(settings, 'POLYGON_API_KEY') else os.getenv('POLYGON_API_KEY')
        self.market_calculator = get_market_data_calculator(polygon_key) if polygon_key else None
        
        # Semáforo global para limitar requests concurrentes a SEC
        self._sec_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_SCRAPES)
        
        # Full-Text Search for comprehensive dilution discovery
        self._fulltext_search = get_fulltext_search()
        
        # SEC Filing Fetcher con soporte para exhibits
        self._filing_fetcher = get_sec_filing_fetcher(db)
        
        # Stats
        self._stats = {
            "extractions": 0,
            "cache_hits": 0,
            "retries": 0,
            "timeouts": 0
        }
        
        # Inicializar servicios
        self.cache_service = CacheService(redis, self.repository)
        self.filing_fetcher = SECFilingFetcher(db)
        self.shares_service = SharesDataService(redis)
        
        # Deduplication service
        from services.analysis.deduplication_service import DeduplicationService
        self.deduplication_service = DeduplicationService()
        
        # Checkpoints habilitados para debugging de pipeline
        self._checkpoints_enabled = True
        self._checkpoint_ttl = 3600 * 24  # 24 horas
        
        # Contextual Extractor v4 (arquitectura principal - usa contexto largo de Gemini)
        sec_api_key = settings.SEC_API_IO_KEY or os.getenv('SEC_API_IO', '')
        gemini_key = settings.GOOGL_API_KEY_V2 or os.getenv('GOOGL_API_KEY_V2', '')
        if sec_api_key and gemini_key:
            self._contextual_extractor = ContextualDilutionExtractor(
                sec_api_key=sec_api_key,
                gemini_api_key=gemini_key
            )
            logger.info("contextual_extractor_v4_ready")
        else:
            self._contextual_extractor = None
            logger.error("contextual_extractor_v4_disabled - REQUIRED for dilution extraction", 
                        has_sec_api=bool(sec_api_key), 
                        has_gemini=bool(gemini_key))
    
    # ========================================================================
    # CHECKPOINTS: Guardar estado intermedio de cada tier para debugging
    # ========================================================================
    
    async def _save_checkpoint(self, ticker: str, tier: str, data: Dict):
        """
        Guarda el estado de un tier del pipeline para debugging.
        
        Tiers:
        - discovery: filings y exhibits encontrados
        - extraction_raw: datos raw de Gemini Flash
        - pre_merge: datos después de pre-merge
        - consolidated: datos después de Gemini Pro
        - validated: datos después de validación
        - split_adjusted: datos después de split adjustment
        """
        if not self._checkpoints_enabled:
            return
        
        try:
            import json
            key = f"checkpoint:{ticker}:{tier}"
            
            # Serializar con timestamp
            checkpoint = {
                "ticker": ticker,
                "tier": tier,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "data": data
            }
            
            await self.redis.set(
                key, 
                json.dumps(checkpoint, default=str),
                ex=self._checkpoint_ttl
            )
            
            # Log resumen del checkpoint
            summary = {}
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, list):
                        summary[k] = len(v)
                    elif isinstance(v, dict):
                        summary[k] = f"dict({len(v)} keys)"
                    else:
                        summary[k] = type(v).__name__
            
            logger.info("checkpoint_saved",
                       ticker=ticker,
                       tier=tier,
                       summary=summary)
                       
        except Exception as e:
            logger.warning("checkpoint_save_failed", 
                          ticker=ticker, 
                          tier=tier, 
                          error=str(e))
    
    async def get_checkpoint(self, ticker: str, tier: str) -> Optional[Dict]:
        """
        Recupera un checkpoint guardado para análisis/debugging.
        
        Uso: await service.get_checkpoint("AZI", "extraction_raw")
        """
        try:
            import json
            key = f"checkpoint:{ticker}:{tier}"
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning("checkpoint_get_failed", ticker=ticker, tier=tier, error=str(e))
            return None
    
    async def list_checkpoints(self, ticker: str) -> List[str]:
        """Lista todos los checkpoints disponibles para un ticker."""
        try:
            pattern = f"checkpoint:{ticker}:*"
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                tier = key.decode().split(":")[-1] if isinstance(key, bytes) else key.split(":")[-1]
                keys.append(tier)
            return sorted(keys)
        except Exception as e:
            logger.warning("checkpoint_list_failed", ticker=ticker, error=str(e))
            return []
    
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
    
    # ========================================================================
    # ARQUITECTURA v4: CONTEXTUAL EXTRACTION (usa ContextualDilutionExtractor)
    # ========================================================================
    
    async def _extract_with_contextual_v4(
        self,
        ticker: str,
        cik: str,
        company_name: str = "",
        use_gemini_pro_dedup: bool = True,
        all_filings: Optional[List[Dict]] = None
    ) -> Optional[Dict]:
        """
        Extracción v4 basada en contexto largo de Gemini.
        
        VENTAJAS:
        - Contexto acumulado entre filings (mejor correlación)
        - Descarga de archivos .txt completos (no PDFs)
        - ATM detection desde material events
        - Nombres consistentes con patrón [Month Year] [Type]
        
        Args:
            ticker: Símbolo del ticker
            cik: CIK de la empresa
            company_name: Nombre de la empresa (para Gemini Pro dedup)
            use_gemini_pro_dedup: Si True, usa Gemini 3 Pro para deduplicación inteligente
            all_filings: Filings pre-obtenidos (evita re-búsqueda en el extractor)
        
        Returns:
            Dict con formato compatible con _build_profile
        """
        if not self._contextual_extractor:
            logger.warning("contextual_extractor_not_available", ticker=ticker)
            return None
        
        try:
            logger.info("contextual_extraction_starting", 
                       ticker=ticker, cik=cik, 
                       gemini_pro_dedup=use_gemini_pro_dedup,
                       pre_fetched_filings=len(all_filings) if all_filings else 0)
            
            # Ejecutar extracción v4.4 (con Gemini Pro dedup si habilitado)
            # Pasar filings pre-obtenidos para evitar re-búsqueda
            result = await self._contextual_extractor.extract_all(
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                use_gemini_pro_dedup=use_gemini_pro_dedup,
                pre_fetched_filings=all_filings
            )
            
            if not result:
                logger.warning("contextual_extraction_no_result", ticker=ticker)
                return None
            
            # El resultado ya viene en formato dict
            extracted_data = {
                'warrants': result.get('warrants', []),
                'atm_offerings': result.get('atm_offerings', []),
                'shelf_registrations': result.get('shelf_registrations', []),
                'completed_offerings': result.get('completed_offerings', []),  # FIX: Ahora sí extraemos completed offerings
                's1_offerings': result.get('s1_offerings', []),
                'convertible_notes': result.get('convertible_notes', []),
                'convertible_preferred': result.get('convertible_preferred', []),
                'equity_lines': result.get('equity_lines', []),
                # FIX BUG #1: Propagar flag para evitar doble ajuste de splits por Python
                '_gemini_pro_adjusted': result.get('_gemini_pro_adjusted', False),
            }
            
            # Logging detallado
            logger.info("contextual_extraction_complete",
                       ticker=ticker,
                       warrants=len(extracted_data['warrants']),
                       notes=len(extracted_data['convertible_notes']),
                       preferred=len(extracted_data['convertible_preferred']),
                       atm=len(extracted_data['atm_offerings']),
                       shelf=len(extracted_data['shelf_registrations']),
                       s1=len(extracted_data['s1_offerings']))
            
            return extracted_data
            
        except Exception as e:
            logger.error("file_number_extraction_failed", ticker=ticker, error=str(e))
            return None
    
    def _is_valid_note(self, note: Dict) -> bool:
        """
        Validación BÁSICA de nota convertible.
        
        Solo verifica datos mínimos necesarios.
        La limpieza inteligente la hace Gemini 3 Pro en Consolidation Pass.
        """
        series_name = note.get('series_name', '')
        principal = self.deduplication_service.normalize_grok_value(
            note.get('total_principal_amount'), 'number'
        ) or 0
        conversion_price = self.deduplication_service.normalize_grok_value(
            note.get('conversion_price'), 'number'
        ) or 0
        issue_date = note.get('issue_date')
        
        # LOG DETALLADO para debugging
        logger.debug("note_validation_check",
                    series=series_name,
                    principal=principal,
                    conversion_price=conversion_price,
                    has_issue_date=bool(issue_date),
                    raw_conv_price=note.get('conversion_price'))
        
        # Solo validación mínima: debe tener principal > 0
        if principal <= 0:
            logger.info("note_rejected",
                       reason="zero_principal",
                       series=series_name)
            return False
        
        # Debe tener conversion_price numérico > 0
        if conversion_price <= 0:
            logger.info("note_rejected",
                       reason="no_conversion_price",
                       series=series_name,
                       principal=principal,
                       raw_value=str(note.get('conversion_price'))[:50])
            return False
        
        # PASÓ validación básica
        logger.info("note_accepted",
                   series=series_name,
                   principal=principal,
                   conversion_price=conversion_price,
                   has_issue_date=bool(issue_date))
        return True
    
    def _is_valid_warrant(self, warrant: Dict) -> bool:
        """
        Validación de warrant.
        
        FILTRAR warrants que NO diluyen:
        - underlying_type = 'convertible_notes' (warrants para comprar notas, no acciones)
        - underlying_type = 'preferred_stock' (warrants para comprar preferred, no common)
        """
        series_name = warrant.get('series_name', '') or ''
        underlying_type = warrant.get('underlying_type', 'shares') or 'shares'
        exercise_price = self.deduplication_service.normalize_grok_value(
            warrant.get('exercise_price'), 'number'
        ) or 0
        outstanding = self.deduplication_service.normalize_grok_value(
            warrant.get('outstanding'), 'number'
        ) or 0
        total_issued = self.deduplication_service.normalize_grok_value(
            warrant.get('total_issued'), 'number'
        ) or 0
        
        # LOG DETALLADO para debugging
        logger.debug("warrant_validation_check",
                    series=series_name,
                    underlying_type=underlying_type,
                    exercise_price=exercise_price,
                    outstanding=outstanding,
                    total_issued=total_issued)
        
        # FILTRAR warrants que NO son para comprar shares (no diluyen directamente)
        if underlying_type and underlying_type.lower() != 'shares':
            logger.info("warrant_filtered_non_share",
                       series=series_name,
                       underlying_type=underlying_type,
                       reason="Warrant to purchase notes/preferred, not common shares")
            return False
        
        # Solo validación mínima: debe tener exercise_price > 0
        if exercise_price <= 0:
            logger.info("warrant_rejected",
                       reason="no_exercise_price",
                       series=series_name,
                       raw_value=str(warrant.get('exercise_price'))[:50])
            return False
        
        # Debe tener alguna cantidad O ser un warrant reciente con issue_date
        # Los warrants recientes extraídos de exhibits pueden no tener quantity todavía
        quantity = max(outstanding, total_issued)
        issue_date = warrant.get('issue_date', '') or ''
        
        if quantity <= 0:
            # Permitir warrants recientes (2025) sin quantity si tienen issue_date
            # La quantity se puede obtener del 8-K principal o press release
            if issue_date and issue_date.startswith('2025'):
                logger.info("warrant_accepted_recent_no_quantity",
                           series=series_name,
                           exercise_price=exercise_price,
                           issue_date=issue_date,
                           reason="Recent warrant without quantity - will be enriched later")
            else:
                logger.info("warrant_rejected",
                           reason="no_quantity",
                           series=series_name,
                           exercise_price=exercise_price,
                           issue_date=issue_date)
                return False
        
        # PASÓ validación
        logger.info("warrant_accepted",
                   series=series_name,
                   underlying_type=underlying_type,
                   exercise_price=exercise_price,
                   outstanding=outstanding,
                   total_issued=total_issued)
        return True
    
    def _is_valid_shelf(self, shelf: Dict) -> bool:
        """
        Validar que un shelf registration tiene datos mínimos.
        
        FILTRAR:
        - Shelfs sin total_capacity
        - Shelfs de resale/conversion (no son nueva dilución, shares ya contadas en notas)
        """
        series_name = shelf.get('series_name', '') or ''
        registration_purpose = shelf.get('registration_purpose', 'new_issuance') or 'new_issuance'
        total_capacity = self.deduplication_service.normalize_grok_value(
            shelf.get('total_capacity'), 'number'
        ) or 0
        
        if total_capacity <= 0:
            logger.debug("shelf_filtered_no_capacity", 
                        series=series_name,
                        form=shelf.get('registration_statement'))
            return False
        
        # FILTRAR shelfs de resale/conversion (no son nueva dilución)
        # Estas shares ya están contadas en las notas convertibles
        if registration_purpose and registration_purpose.lower() in ['resale', 'conversion_shares']:
            logger.info("shelf_filtered_non_dilutive",
                       series=series_name,
                       registration_purpose=registration_purpose,
                       total_capacity=total_capacity,
                       reason="Resale/conversion registration - shares already counted in convertible notes")
            return False
        
        return True
    
    def _is_valid_atm(self, atm: Dict) -> bool:
        """
        Validar que un ATM tiene datos mínimos.
        
        Allow ATMs with valid name even if capacity is missing - 
        capacity can be enriched later or calculated from market data.
        """
        series_name = str(atm.get('series_name', '') or '').lower()
        total_capacity = self.deduplication_service.normalize_grok_value(
            atm.get('total_capacity'), 'number'
        ) or 0
        
        # Accept if has capacity
        if total_capacity > 0:
            return True
        
        # Accept if name clearly indicates ATM (even without capacity)
        if 'atm' in series_name:
            logger.debug("atm_accepted_by_name", series=atm.get('series_name'))
            return True
        
        logger.debug("atm_filtered_no_capacity_or_name", series=atm.get('series_name'))
        return False
    
    def _is_valid_equity_line(self, el: Dict) -> bool:
        """Validar que un equity line tiene datos mínimos."""
        total_capacity = self.deduplication_service.normalize_grok_value(
            el.get('total_capacity'), 'number'
        ) or 0
        
        if total_capacity <= 0:
            logger.debug("equity_line_filtered_no_capacity", series=el.get('series_name'))
            return False
        
        return True
    
    def _pre_merge_notes(self, notes: List[Dict]) -> List[Dict]:
        """
        Pre-merge SIMPLE: Solo agrupa por mes/año extraído del nombre.
        
        La consolidación inteligente la hace Gemini 3 Pro después.
        Aquí solo hacemos agrupación básica para reducir duplicados obvios.
        """
        if not notes:
            return []
        
        import re
        
        logger.info("pre_merge_notes_start", total_notes=len(notes))
        
        # Extraer mes/año del nombre para agrupar
        def extract_date_key(name: str) -> str:
            if not name:
                return "unknown"
            name_lower = name.lower()
            # Buscar patrón "Month Year" (ej: "january 2025", "february 2025")
            date_match = re.search(
                r'(january|february|march|april|may|june|july|august|september|october|november|december)\s*\d{4}', 
                name_lower
            )
            if date_match:
                return date_match.group().strip()
            return "unknown"
        
        # Agrupar notas
        groups = {}
        for note in notes:
            key = extract_date_key(note.get('series_name', ''))
            if key == "unknown":
                # Usar issue_date como alternativa
                key = note.get('issue_date') or "unknown"
            
            if key not in groups:
                groups[key] = []
            groups[key].append(note)
            
            logger.debug("pre_merge_note_grouped",
                        series=note.get('series_name'),
                        key=key)
        
        logger.info("pre_merge_groups_formed", 
                   groups=len(groups),
                   group_keys=list(groups.keys()))
        
        # Combinar cada grupo: tomar la nota con conversion_price numérico válido
        merged = []
        for key, group in groups.items():
            if len(group) == 1:
                merged.append(group[0])
                logger.debug("pre_merge_single_note", key=key)
            else:
                # Encontrar la nota con mejor conversion_price (numérico válido)
                best_note = None
                best_score = -1
                
                for note in group:
                    score = 0
                    # Tiene conversion_price numérico válido?
                    try:
                        conv = float(note.get('conversion_price', 0))
                        if conv > 0:
                            score += 10
                    except:
                        pass
                    # Tiene issue_date?
                    if note.get('issue_date'):
                        score += 3
                    # Tiene maturity_date?
                    if note.get('maturity_date'):
                        score += 3
                    # Tiene pp_clause?
                    if note.get('pp_clause'):
                        score += 2
                    
                    if score > best_score:
                        best_score = score
                        best_note = note
                
                # Enriquecer la mejor nota con datos de las demás
                combined = dict(best_note)
                for note in group:
                    if note is best_note:
                        continue
                    for field in ['pp_clause', 'known_owners', 'maturity_date', 'floor_price']:
                        if not combined.get(field) and note.get(field):
                            combined[field] = note[field]
                
                logger.info("pre_merge_combined",
                           key=key,
                           count=len(group),
                           best_score=best_score,
                           series=combined.get('series_name'),
                           has_conv_price=bool(combined.get('conversion_price')))
                
                merged.append(combined)
        
        logger.info("pre_merge_notes_complete",
                   input=len(notes),
                   output=len(merged))
        
        return merged
    
    def _pre_merge_warrants(self, warrants: List[Dict]) -> List[Dict]:
        """
        Pre-merge para warrants - combina duplicados que son claramente el mismo instrumento.
        
        IMPORTANTE: No combinar warrants diferentes del mismo mes (Series A vs Series B).
        Solo combinar si son extracciones parciales del MISMO warrant.
        """
        if not warrants:
            return []
        
        import re
        
        def extract_series_identifier(name: str) -> str:
            """
            Extrae identificador único del warrant incluyendo series/tipo.
            'December 2025 PIPE Series A Common Warrants' -> 'december 2025|series a'
            'December 2025 Pre-Funded Warrants' -> 'december 2025|pre-funded'
            """
            if not name:
                return ""
            name_lower = name.lower()
            
            # Extraer fecha (mes + año)
            date_match = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)\s*\d{4}', name_lower)
            date_part = date_match.group().strip() if date_match else ""
            
            # Extraer identificador de serie/tipo
            series_match = re.search(r'series\s*([a-z0-9]+)', name_lower)
            prefunded_match = re.search(r'pre[-\s]?funded', name_lower)
            
            if series_match:
                series_part = f"series {series_match.group(1)}"
            elif prefunded_match:
                series_part = "pre-funded"
            else:
                # Usar palabras distintivas
                distinctive_words = []
                for word in ['pipe', 'sermonix', 'placement', 'agent', 'underwriter']:
                    if word in name_lower:
                        distinctive_words.append(word)
                series_part = '-'.join(distinctive_words) if distinctive_words else ""
            
            # Combinar en key única
            if date_part and series_part:
                return f"{date_part}|{series_part}"
            elif date_part:
                return date_part
            return name_lower.strip()[:50]  # Fallback: primeros 50 chars
        
        # Agrupar por key única
        groups = {}
        for warrant in warrants:
            key = extract_series_identifier(warrant.get('series_name', ''))
            
            # Añadir exercise_price a la key si es significativo
            # Esto evita combinar warrants con diferentes precios
            exercise = warrant.get('exercise_price')
            if exercise:
                try:
                    # Limpiar símbolos de moneda (C$, $, USD, etc.)
                    clean_exercise = str(exercise).replace('C$', '').replace('$', '').replace(',', '').strip()
                    exercise_float = float(clean_exercise)
                    if exercise_float > 0:
                        key = f"{key}|{exercise_float:.2f}"
                except (ValueError, TypeError):
                    pass  # Si no es parseable, ignorar para el key
            
            if not key:
                key = warrant.get('issue_date', 'unknown')
            
            if key not in groups:
                groups[key] = []
            groups[key].append(warrant)
        
        # Combinar grupos (solo para el mismo warrant extraído de múltiples fuentes)
        merged = []
        for key, group in groups.items():
            if len(group) == 1:
                merged.append(group[0])
            else:
                # Combinar datos parciales del mismo warrant
                combined = dict(group[0])
                for field in ['exercise_price', 'outstanding', 'total_issued', 'expiration_date', 'known_owners', 'issue_date']:
                    for warrant in group:
                        val = warrant.get(field)
                        if val is not None and val != '' and val != 0:
                            if field == 'exercise_price':
                                try:
                                    if float(val) > 0:
                                        combined[field] = val
                                        break
                                except:
                                    pass
                            else:
                                combined[field] = val
                                break
                
                merged.append(combined)
        
        return merged
    
    def _deduplicate_with_priority(self, data: Dict) -> Dict:
        """
        Deduplicar instrumentos dando prioridad a fuentes más confiables.
        
        Prioridad:
        1. gemini_exhibit (contratos legales)
        2. grok_424b (prospectus)
        3. grok_filing (narrativo)
        """
        # Deduplicar convertible notes con prioridad
        notes = data.get('convertible_notes', [])
        if len(notes) > 1:
            # Ordenar por prioridad (menor número = mayor prioridad)
            notes.sort(key=lambda x: x.get('_source_priority', 5))
            
            # Usar deduplicación estándar que mantendrá el primero (mayor prioridad)
            notes = deduplicate_convertible_notes(notes)
        
        data['convertible_notes'] = notes
        
        # Deduplicar warrants con prioridad
        warrants = data.get('warrants', [])
        if len(warrants) > 1:
            warrants.sort(key=lambda x: x.get('_source_priority', 5))
            warrants = deduplicate_warrants(warrants)
        
        data['warrants'] = warrants
        
        # Deduplicar otros instrumentos
        if data.get('atm_offerings'):
            data['atm_offerings'] = deduplicate_atm(data['atm_offerings'])
        
        if data.get('shelf_registrations'):
            data['shelf_registrations'] = deduplicate_shelfs(data['shelf_registrations'])
        
        if data.get('completed_offerings'):
            data['completed_offerings'] = deduplicate_completed(data['completed_offerings'])
        
        if data.get('equity_lines'):
            data['equity_lines'] = deduplicate_equity_lines(data['equity_lines'])
        
        return data
    
    def _validate_extracted_data(self, data: Dict, ticker: str) -> Dict:
        """
        Validación final de datos extraídos.
        Marca instrumentos con datos incompletos para revisión.
        """
        # Validar notas
        for note in data.get('convertible_notes', []):
            conversion_price = self.deduplication_service.normalize_grok_value(
                note.get('conversion_price'), 'number'
            ) or 0
            
            if conversion_price <= 0:
                note['_needs_review'] = True
                note['_review_reason'] = 'missing_conversion_price'
                logger.warning("note_needs_review",
                             ticker=ticker,
                             series=note.get('series_name'),
                             reason='missing_conversion_price')
        
        # Validar warrants
        for warrant in data.get('warrants', []):
            exercise_price = self.deduplication_service.normalize_grok_value(
                warrant.get('exercise_price'), 'number'
            ) or 0
            
            if exercise_price <= 0:
                warrant['_needs_review'] = True
                warrant['_review_reason'] = 'missing_exercise_price'
        
        return data
    
    async def _adjust_warrants_for_splits(self, ticker: str, warrants: List[Dict]) -> List[Dict]:
        """Delegar a shares_service"""
        return await self.shares_service.adjust_warrants_for_splits(ticker, warrants)
    
    async def _adjust_convertible_notes_for_splits(self, ticker: str, notes: List[Dict]) -> List[Dict]:
        """Delegar a shares_service para ajustar notas convertibles por splits"""
        return await self.shares_service.adjust_convertible_notes_for_splits(ticker, notes)
    
    async def _adjust_convertible_preferred_for_splits(self, ticker: str, preferred: List[Dict]) -> List[Dict]:
        """Delegar a shares_service para ajustar convertible preferred por splits"""
        return await self.shares_service.adjust_convertible_preferred_for_splits(ticker, preferred)
    
    async def get_shares_history(self, ticker: str, cik: Optional[str] = None) -> Dict[str, Any]:
        """Delegar a shares_service"""
        return await self.shares_service.get_shares_history(ticker, cik)
    
    async def get_from_cache_only(self, ticker: str) -> Optional[SECDilutionProfile]:
        """Delegar a cache_service"""
        return await self.cache_service.get_from_cache_only(ticker)
    
    # ========================================================================
    # FULL-TEXT SEARCH HELPERS
    # ========================================================================
    
    def _convert_fulltext_filings(
        self,
        fulltext_filings: List[Dict]
    ) -> List[Dict]:
        """
        Convierte filings del Full-Text Search al formato esperado por el sistema.
        
        Full-Text Search retorna: {accessionNo, formType, filedAt, linkToFilingDetails, ...}
        Sistema espera: {url, form_type, filing_date, ...}
        """
        converted = []
        
        for f in fulltext_filings:
            # Construir URL del filing
            accession_no = f.get('accessionNo', '')
            filing_url = f.get('linkToFilingDetails', '')
            
            # Si no hay URL, intentar construirla
            if not filing_url and accession_no:
                # accessionNo format: 0001493152-25-014375
                # URL format: https://www.sec.gov/Archives/edgar/data/CIK/ACCESSION/filename.htm
                cik = f.get('cik', '').lstrip('0')
                acc_clean = accession_no.replace('-', '')
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"
            
            # Determinar el archivo principal del filing
            if filing_url and not filing_url.endswith('.htm'):
                # Buscar el archivo principal basado en form_type
                form_type = f.get('formType', '')
                if form_type in ['6-K', '8-K']:
                    filing_url = filing_url + f"{form_type.lower().replace('-', '')}.htm"
                elif form_type in ['10-K', '10-Q']:
                    filing_url = filing_url + f"{form_type.lower().replace('-', '')}.htm"
                elif 'F-1' in form_type or '20-F' in form_type:
                    # Para F-1, a menudo el archivo es filename.htm
                    pass  # Dejar URL base, se manejará en descarga
            
            converted.append({
                'url': filing_url,
                'form_type': f.get('formType', ''),
                'filing_date': f.get('filedAt', '')[:10] if f.get('filedAt') else '',
                'accession_number': accession_no,
                '_from_fulltext': True
            })
        
        logger.debug("fulltext_filings_converted", 
                    input_count=len(fulltext_filings),
                    output_count=len(converted))
        
        return converted
    
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
    
    # ========================================================================
    # GEMINI EXTRACTION - Para datos precisos desde exhibits
    # ========================================================================
    
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
            # ================================================================
            # PROTECTION: Prevent duplicate concurrent requests for same ticker
            # ================================================================
            processing_key = f"dilution:processing:{ticker}"
            
            # Check if already processing
            is_processing = await self.redis.get(processing_key)
            if is_processing:
                logger.warning("ticker_already_processing", 
                              ticker=ticker, 
                              started_at=is_processing,
                              action="waiting_for_existing")
                
                # Wait for existing processing to complete (max 120 seconds)
                wait_start = time.time()
                max_wait = 120
                poll_interval = 2
                
                while time.time() - wait_start < max_wait:
                    await asyncio.sleep(poll_interval)
                    
                    # Check if still processing
                    still_processing = await self.redis.get(processing_key)
                    if not still_processing:
                        # Processing finished, try to get from cache
                        logger.info("existing_processing_completed", 
                                   ticker=ticker, 
                                   wait_time=int(time.time() - wait_start))
                        
                        cached = await self.cache_service.get_from_redis(ticker)
                        if cached:
                            return cached
                        
                        # Also try PostgreSQL
                        db_profile = await self.repository.get_profile(ticker)
                        if db_profile:
                            return db_profile
                        
                        # Still no data, break and continue with fresh scraping
                        break
                    
                    # Log progress while waiting
                    if int(time.time() - wait_start) % 10 == 0:
                        logger.info("waiting_for_existing_processing", 
                                   ticker=ticker, 
                                   elapsed=int(time.time() - wait_start))
                
                # If we waited too long, log and continue anyway
                if time.time() - wait_start >= max_wait:
                    logger.warning("wait_timeout_proceeding_anyway", 
                                  ticker=ticker, 
                                  max_wait=max_wait)
            
            # Mark as processing (TTL 10 minutes to auto-expire if crash)
            await self.redis.set(
                processing_key, 
                datetime.utcnow().isoformat(), 
                ttl=600  # 10 minutes
            )
            
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
                
                # Si no tenemos filings tradicionales pero sí del fulltext, usar esos
                if not filings and priority_filings_from_fulltext:
                    logger.info("using_fulltext_filings_as_primary", 
                               ticker=ticker,
                               fulltext_count=len(priority_filings_from_fulltext))
                    # Convertir priority_filings a formato compatible
                    filings = self._convert_fulltext_filings(priority_filings_from_fulltext)
                
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
                
                # ================================================================
                # 4. CONTEXTUAL EXTRACTION v4 (ÚNICO MÉTODO)
                # ================================================================
                # ContextualDilutionExtractor usa contexto largo de Gemini
                # ================================================================
                
                if not self._contextual_extractor:
                    logger.error("contextual_extractor_not_configured", ticker=ticker)
                    return self._create_empty_profile(ticker, cik, company_name)
                
                # Combinar TODOS los filings disponibles para pasar al extractor
                all_combined_filings = list(filings)  # Ya incluye 424B
                # Añadir priority_filings si no están ya incluidos
                if priority_filings_from_fulltext:
                    existing_accession_nos = {f.get('accessionNo', f.get('accession_number', '')) for f in all_combined_filings}
                    for pf in priority_filings_from_fulltext:
                        acc_no = pf.get('accessionNo', pf.get('accession_number', ''))
                        if acc_no and acc_no not in existing_accession_nos:
                            all_combined_filings.append(pf)
                
                logger.info("starting_contextual_extraction_v4", ticker=ticker, 
                           use_gemini_pro_dedup=True,
                           total_filings_to_process=len(all_combined_filings))
                
                try:
                    # v4.4: Gemini Pro Dedup habilitado por defecto
                    # OPTIMIZACIÓN: Pasar todos los filings pre-buscados para evitar re-búsqueda
                    extracted_data = await self._extract_with_contextual_v4(
                        ticker=ticker,
                        cik=cik,
                        company_name=company_name,
                        use_gemini_pro_dedup=True,  # Usar Gemini 3 Pro para dedup + split adjustment
                        all_filings=all_combined_filings
                    )
                except Exception as e:
                    logger.error("contextual_extraction_v4_failed", ticker=ticker, error=str(e))
                    return self._create_empty_profile(ticker, cik, company_name)
                
                if not extracted_data:
                    logger.warning("contextual_extraction_no_data", ticker=ticker)
                    return self._create_empty_profile(ticker, cik, company_name)
                
                logger.info("extraction_complete", ticker=ticker, source="contextual_v4")
                
                # Enriquecer con datos estructurados de S-1/424B4 API (si hay)
                if prospectus_data:
                    extracted_data = self._enrich_with_prospectus_data(
                        extracted_data, 
                        prospectus_data
                    )
                
                # Añadir metadata del Full-Text Discovery
                if fulltext_discovery:
                    extracted_data['_fulltext_discovery'] = {
                        'categories_detected': fulltext_discovery.get('summary', {}).get('categories_detected', []),
                        'total_filings_scanned': fulltext_discovery.get('summary', {}).get('total_filings_with_dilution', 0),
                        'has_warrants': fulltext_discovery.get('summary', {}).get('has_warrants', False),
                        'has_atm': fulltext_discovery.get('summary', {}).get('has_atm', False),
                        'has_shelf': fulltext_discovery.get('summary', {}).get('has_shelf', False),
                        'has_convertibles': fulltext_discovery.get('summary', {}).get('has_convertibles', False),
                    }
                
                # 6. Ajustar warrants por stock splits
                # ESTRATEGIA: Verificar cada instrumento individualmente
                # Si Gemini marcó split_adjusted=True, no re-ajustar ese instrumento
                # Si no está marcado, Python lo ajusta (incluso si _gemini_pro_adjusted=True)
                gemini_already_adjusted = extracted_data.get('_gemini_pro_adjusted', False)
                
                if extracted_data.get('warrants'):
                    # Filtrar: solo ajustar warrants que NO tienen split_adjusted=True
                    unadjusted_warrants = [
                        w for w in extracted_data['warrants'] 
                        if not w.get('split_adjusted') == True
                    ]
                    already_adjusted_warrants = [
                        w for w in extracted_data['warrants'] 
                        if w.get('split_adjusted') == True
                    ]
                    
                    if unadjusted_warrants:
                        logger.info("adjusting_unadjusted_warrants",
                                   ticker=ticker,
                                   unadjusted_count=len(unadjusted_warrants),
                                   already_adjusted_count=len(already_adjusted_warrants),
                                   gemini_flag=gemini_already_adjusted)
                        
                        adjusted = await self._adjust_warrants_for_splits(
                            ticker, 
                            unadjusted_warrants
                        )
                        # Combinar warrants ya ajustados + recién ajustados
                        extracted_data['warrants'] = already_adjusted_warrants + adjusted
                    elif gemini_already_adjusted:
                        logger.info("skip_warrant_split_adjustment", 
                                   ticker=ticker, 
                                   reason="all_warrants_already_adjusted",
                                   count=len(already_adjusted_warrants))
                
                # 6b. Ajustar convertible notes por stock splits
                if extracted_data.get('convertible_notes'):
                    unadjusted_notes = [
                        n for n in extracted_data['convertible_notes'] 
                        if not n.get('split_adjusted') == True
                    ]
                    already_adjusted_notes = [
                        n for n in extracted_data['convertible_notes'] 
                        if n.get('split_adjusted') == True
                    ]
                    
                    if unadjusted_notes:
                        logger.info("adjusting_unadjusted_notes",
                                   ticker=ticker,
                                   unadjusted_count=len(unadjusted_notes),
                                   already_adjusted_count=len(already_adjusted_notes))
                        
                        adjusted = await self._adjust_convertible_notes_for_splits(
                            ticker, 
                            unadjusted_notes
                        )
                        extracted_data['convertible_notes'] = already_adjusted_notes + adjusted
                
                # 6c. Ajustar convertible preferred por stock splits
                if extracted_data.get('convertible_preferred'):
                    unadjusted_preferred = [
                        p for p in extracted_data['convertible_preferred'] 
                        if not p.get('split_adjusted') == True
                    ]
                    already_adjusted_preferred = [
                        p for p in extracted_data['convertible_preferred'] 
                        if p.get('split_adjusted') == True
                    ]
                    
                    if unadjusted_preferred:
                        adjusted = await self._adjust_convertible_preferred_for_splits(
                            ticker, 
                            unadjusted_preferred
                        )
                        extracted_data['convertible_preferred'] = already_adjusted_preferred + adjusted
                
                # 7. Obtener precio actual y shares outstanding
                current_price, shares_outstanding, free_float = await self._get_current_market_data(ticker)
                
                # 7. Construir profile completo
                profile = self._build_profile(
                    ticker=ticker,
                    cik=cik,
                    company_name=company_name,
                    extracted_data=extracted_data,
                    current_price=current_price,
                    shares_outstanding=shares_outstanding,
                    free_float=free_float,
                    source_filings=relevant_filings
                )
                
                # 8. NUEVO: Calcular métricas de Baby Shelf
                profile = await self._enrich_profile_with_baby_shelf_calculations(
                    profile,
                    free_float=free_float
                )
                
                # 9. VALIDACIÓN CON GEMINI - Corregir precios, completar datos
                try:
                    from services.extraction.gemini_pro_deduplicator import validate_with_gemini_pro
                    
                    instruments_to_validate = {
                        "warrants": [w.dict() if hasattr(w, 'dict') else w for w in profile.warrants],
                        "convertible_notes": [n.dict() if hasattr(n, 'dict') else n for n in profile.convertible_notes],
                        "completed_offerings": [o.dict() if hasattr(o, 'dict') else o for o in profile.completed_offerings],
                        "s1_offerings": [s.dict() if hasattr(s, 'dict') else s for s in profile.s1_offerings],
                        "equity_lines": [e.dict() if hasattr(e, 'dict') else e for e in profile.equity_lines] if hasattr(profile, 'equity_lines') else [],
                        "atm_offerings": [a.dict() if hasattr(a, 'dict') else a for a in profile.atm_offerings],
                    }
                    
                    logger.info("gemini_validation_starting", ticker=ticker)
                    validation_result = await validate_with_gemini_pro(
                        ticker=ticker,
                        company_name=company_name,
                        instruments=instruments_to_validate
                    )
                    
                    # Aplicar correcciones si hay
                    if validation_result and "validated_instruments" in validation_result:
                        profile = self._apply_validation_corrections(profile, validation_result)
                        logger.info("gemini_validation_applied", 
                                   ticker=ticker,
                                   summary=validation_result.get("validation_summary", {}))
                    
                except ImportError as e:
                    logger.warning("gemini_validation_import_error", ticker=ticker, error=str(e))
                except Exception as e:
                    logger.warning("gemini_validation_error", ticker=ticker, error=str(e))
                    # Continuar sin validación - no bloquear el flujo
                
                logger.info("sec_scrape_completed", ticker=ticker)
                return profile
                
            except Exception as e:
                logger.error("scrape_and_analyze_failed", ticker=ticker, error=str(e))
                return None
            
            finally:
                # Always clean up processing lock
                try:
                    await self.redis.delete(processing_key)
                    logger.debug("processing_lock_released", ticker=ticker)
                except Exception as cleanup_error:
                    logger.warning("processing_lock_cleanup_failed", 
                                  ticker=ticker, 
                                  error=str(cleanup_error))
                    
        except Exception as e:
            # Outer exception handler for the initial lock check
            logger.error("scrape_and_analyze_outer_failed", ticker=ticker, error=str(e))
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
            Tuple (current_price, shares_outstanding, free_float)
        """
        try:
            logger.debug("get_current_market_data_starting", ticker=ticker)
            
            # 1. Obtener shares outstanding y float de ticker_metadata
            query = """
            SELECT shares_outstanding, free_float
            FROM ticker_metadata
            WHERE symbol = $1
            """
            
            result = await self.db.fetchrow(query, ticker)
            
            if not result:
                logger.warning("ticker_metadata_not_found", ticker=ticker)
                return None, None, None
            
            shares_outstanding = result['shares_outstanding']
            free_float = result['free_float']
            
            logger.debug("ticker_metadata_found", ticker=ticker, shares=shares_outstanding, float=free_float)
            
            # 2. Obtener precio actual desde Polygon API (snapshot)
            current_price = await self._get_price_from_polygon(ticker)
            
            logger.info("market_data_fetched", ticker=ticker, price=current_price, shares=shares_outstanding, float=free_float)
            
            return current_price, shares_outstanding, free_float
            
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
                logger.warning("polygon_api_key_missing", ticker=ticker)
                return None
            
            url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
            
            logger.debug("polygon_price_request", ticker=ticker, url=url)
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    params={"apiKey": polygon_api_key}
                )
                
                logger.debug("polygon_price_response", ticker=ticker, status=response.status_code)
                
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
                        logger.info("polygon_price_fetched", ticker=ticker, price=price)
                        return Decimal(str(price))
                
                logger.warning("polygon_snapshot_no_price", ticker=ticker, status=response.status_code)
                return None
                
        except Exception as e:
            logger.error("get_price_from_polygon_failed", ticker=ticker, error=str(e))
            return None
    
    def _calculate_atm_remaining_from_sales(
        self, 
        atm_offerings: List, 
        completed_offerings: List,
        ticker: str
    ):
        """
        Calcula el remaining_capacity REAL del ATM basándose en las ventas 
        extraídas de los 10-Q/10-K (completed_offerings con type='ATM Sale').
        
        El proceso:
        1. Filtra completed_offerings con offering_type='ATM Sale'
        2. Suma todos los amount_raised de esas ventas
        3. Para cada ATM, calcula: remaining = total_capacity - sum(sales)
        
        NOTA: Si hay múltiples ATMs, intentamos matchear por fecha/nombre.
        Si solo hay un ATM activo, asumimos que todas las sales van ahí.
        """
        # Filtrar solo ATM Sales
        atm_sales = [
            co for co in completed_offerings
            if hasattr(co, 'offering_type') and co.offering_type == 'ATM Sale'
        ]
        
        if not atm_sales:
            logger.debug("no_atm_sales_found", ticker=ticker)
            return
        
        # Sumar todos los proceeds de ATM Sales
        total_atm_proceeds = Decimal('0')
        for sale in atm_sales:
            if sale.amount_raised:
                try:
                    total_atm_proceeds += Decimal(str(sale.amount_raised))
                except:
                    pass
        
        if total_atm_proceeds <= 0:
            logger.debug("no_atm_proceeds_to_subtract", ticker=ticker)
            return
        
        logger.info("atm_sales_total_found",
                   ticker=ticker,
                   num_sales=len(atm_sales),
                   total_proceeds=float(total_atm_proceeds))
        
        # Aplicar a los ATM offerings
        # Si solo hay un ATM activo, todas las sales van a ese ATM
        active_atms = [
            atm for atm in atm_offerings 
            if hasattr(atm, 'status') and atm.status in ('Active', 'active', None)
        ]
        
        if len(active_atms) == 1:
            atm = active_atms[0]
            if atm.total_capacity:
                try:
                    total = Decimal(str(atm.total_capacity))
                    new_remaining = max(Decimal('0'), total - total_atm_proceeds)
                    
                    # Guardar el remaining calculado
                    atm.remaining_capacity = new_remaining
                    
                    logger.info("atm_remaining_calculated",
                              ticker=ticker,
                              atm_name=getattr(atm, 'series_name', 'Unknown'),
                              total_capacity=float(total),
                              total_sold=float(total_atm_proceeds),
                              calculated_remaining=float(new_remaining))
                except Exception as e:
                    logger.warning("atm_remaining_calc_error", 
                                  ticker=ticker, 
                                  error=str(e))
        elif len(active_atms) > 1:
            # Múltiples ATMs activos - distribuir proporcionalmente
            # (simplificación: asignar todo al más reciente)
            logger.warning("multiple_active_atms_found", 
                          ticker=ticker, 
                          count=len(active_atms))
            # Por ahora, aplicar al primero (el más reciente por orden de creación)
            atm = active_atms[0]
            if atm.total_capacity:
                try:
                    total = Decimal(str(atm.total_capacity))
                    new_remaining = max(Decimal('0'), total - total_atm_proceeds)
                    atm.remaining_capacity = new_remaining
                    
                    logger.info("atm_remaining_calculated_first",
                              ticker=ticker,
                              atm_name=getattr(atm, 'series_name', 'Unknown'),
                              calculated_remaining=float(new_remaining))
                except:
                    pass
    
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
        free_float: Optional[int] = None
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
        
        # Usar free_float del perfil si no se proporciona
        free_float = free_float or profile.free_float
        
        if not free_float:
            logger.warning("no_free_float_for_baby_shelf_calc", ticker=ticker)
            return profile
        
        try:
            # Obtener Highest 60-Day Close
            highest_close = await self.market_calculator.get_highest_60_day_close(ticker)
            
            if not highest_close:
                logger.warning("no_highest_close_for_baby_shelf_calc", ticker=ticker)
                return profile
            
            # Calcular IB6 Float Value
            ib6_float_value = self.market_calculator.calculate_ib6_float_value(
                free_float, highest_close
            )
            
            # Determinar si es Baby Shelf
            is_baby_shelf = self.market_calculator.is_baby_shelf_company(
                free_float, highest_close
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
                shelf.free_float_calc = free_float
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
                            free_float
                        )
                        shelf.price_to_exceed_baby_shelf = price_to_exceed
            
            # Enriquecer ATM Offerings
            # Usar Decimal para evitar errores de tipos
            current_price_decimal = Decimal(str(profile.current_price or 0))
            for atm in profile.atm_offerings:
                atm.last_update_date = datetime.now().date()
                
                if is_baby_shelf and atm.remaining_capacity:
                    # El ATM puede estar limitado por Baby Shelf
                    # IMPORTANTE: Guardar el remaining REAL sin sobrescribirlo
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
                        # FIX: NO sobrescribir remaining_capacity
                        # El remaining_capacity debe ser el valor REAL del ATM
                        # Usar effective_remaining_capacity para el valor limitado
                        atm.effective_remaining_capacity = current_raisable
                    else:
                        atm.atm_limited_by_baby_shelf = False
                        atm.effective_remaining_capacity = atm.remaining_capacity
                else:
                    # Si no es baby shelf, effective = remaining
                    atm.effective_remaining_capacity = atm.remaining_capacity
                
                # SIEMPRE recalcular potential_shares usando el EFFECTIVE remaining (limitado por baby shelf si aplica)
                effective_remaining = atm.effective_remaining_capacity or atm.remaining_capacity
                if current_price_decimal and current_price_decimal > 0 and effective_remaining:
                    atm.potential_shares_at_current_price = int(Decimal(str(effective_remaining)) / current_price_decimal)
            
            return profile
            
        except Exception as e:
            logger.error("baby_shelf_calc_failed", ticker=ticker, error=str(e))
            return profile
    
    def _apply_validation_corrections(
        self,
        profile: SECDilutionProfile,
        validation_result: Dict[str, Any]
    ) -> SECDilutionProfile:
        """
        Aplica las correcciones de la validación Gemini al profile.
        
        Correcciones posibles:
        - Precios de warrants (corregidos por split)
        - Campos faltantes de convertibles
        - Completed offerings adicionales
        - Equity lines detectadas
        - Status de S-1s corregidos
        """
        try:
            validated = validation_result.get("validated_instruments", {})
            
            # 1. Corregir warrants
            if validated.get("warrants"):
                # Crear mapa de warrants validados por nombre
                validated_warrants = {w.get("series_name", "").lower(): w for w in validated["warrants"]}
                
                for warrant in profile.warrants:
                    key = (warrant.series_name or "").lower()
                    if key in validated_warrants:
                        vw = validated_warrants[key]
                        
                        # Si el precio fue corregido
                        if vw.get("exercise_price_was_wrong"):
                            old_price = warrant.exercise_price
                            warrant.exercise_price = Decimal(str(vw.get("exercise_price", old_price)))
                            warrant.original_exercise_price = Decimal(str(vw.get("original_wrong_price", old_price)))
                            logger.info("warrant_price_corrected",
                                       series=warrant.series_name,
                                       old=float(old_price) if old_price else None,
                                       new=float(warrant.exercise_price))
                        
                        # Actualizar outstanding si se encontró
                        if vw.get("outstanding"):
                            warrant.outstanding_warrants = vw["outstanding"]
                        
                        # Actualizar last_update_date
                        if vw.get("last_update_date"):
                            try:
                                warrant.last_update_date = datetime.strptime(
                                    vw["last_update_date"], "%Y-%m-%d"
                                ).date()
                            except:
                                pass
            
            # 2. Completar convertible notes
            if validated.get("convertible_notes"):
                validated_notes = {n.get("series_name", "").lower(): n for n in validated["convertible_notes"]}
                
                for note in profile.convertible_notes:
                    key = (note.series_name or "").lower()
                    if key in validated_notes:
                        vn = validated_notes[key]
                        
                        # Completar campos faltantes
                        if not note.total_principal_amount and vn.get("total_principal_amount"):
                            note.total_principal_amount = Decimal(str(vn["total_principal_amount"]))
                        
                        if not note.conversion_price and vn.get("conversion_price"):
                            note.conversion_price = Decimal(str(vn["conversion_price"]))
                        
                        if not note.total_shares_when_converted and vn.get("total_shares_when_converted"):
                            note.total_shares_when_converted = vn["total_shares_when_converted"]
                        
                        if not note.price_protection and vn.get("price_protection"):
                            note.price_protection = vn["price_protection"]
                        
                        if not note.pp_clause and vn.get("pp_clause"):
                            note.pp_clause = vn["pp_clause"]
            
            # 3. Añadir completed offerings encontrados
            if validated.get("completed_offerings"):
                from models.sec_dilution_models import CompletedOfferingModel
                
                existing_dates = {o.offering_date for o in profile.completed_offerings if o.offering_date}
                
                for vo in validated["completed_offerings"]:
                    offering_date = vo.get("offering_date")
                    if offering_date and offering_date not in existing_dates:
                        try:
                            new_offering = CompletedOfferingModel(
                                ticker=profile.ticker,
                                offering_type=vo.get("offering_type"),
                                shares_issued=vo.get("shares_issued"),
                                price_per_share=Decimal(str(vo["price_per_share"])) if vo.get("price_per_share") else None,
                                amount_raised=Decimal(str(vo["amount_raised"])) if vo.get("amount_raised") else None,
                                offering_date=offering_date,
                                notes=vo.get("source")
                            )
                            profile.completed_offerings.append(new_offering)
                            logger.info("completed_offering_added",
                                       ticker=profile.ticker,
                                       type=vo.get("offering_type"),
                                       date=offering_date)
                        except Exception as e:
                            logger.warning("completed_offering_add_failed", error=str(e))
            
            # 4. Corregir S-1 status
            if validated.get("s1_offerings"):
                validated_s1 = {s.get("series_name", "").lower(): s for s in validated["s1_offerings"]}
                
                for s1 in profile.s1_offerings:
                    key = (s1.series_name or "").lower()
                    if key in validated_s1:
                        vs = validated_s1[key]
                        
                        if vs.get("status_was_wrong") and vs.get("status"):
                            old_status = s1.status
                            s1.status = vs["status"]
                            logger.info("s1_status_corrected",
                                       series=s1.series_name,
                                       old=old_status,
                                       new=s1.status)
            
            return profile
            
        except Exception as e:
            logger.error("apply_validation_corrections_failed", error=str(e))
            return profile
    
    def _build_profile(
        self,
        ticker: str,
        cik: str,
        company_name: str,
        extracted_data: Dict,
        current_price: Optional[Decimal],
        shares_outstanding: Optional[int],
        free_float: Optional[int],
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
                series_name=w.get('series_name'),  # CRITICAL: Pass series_name
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
                original_total_issued=w.get('original_total_issued'),
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
                exercisable_date=w.get('exercisable_date'),
                # Trazabilidad de filings
                source_filing=w.get('_source'),
                source_filings=w.get('_sources'),
                merged_from_count=w.get('_merged_from'),
                filing_url=w.get('filing_url')
            )
            for w in extracted_data.get('warrants', [])
        ]
        
        logger.info("warrants_parsed", ticker=ticker, count=len(warrants))
        
        # Parse ATM offerings (con nuevos campos)
        # Límites de campos string según Pydantic models
        atm_limits = {'placement_agent': 255, 'status': 50, 'series_name': 255}
        atm_offerings = [
            ATMOfferingModel(
                ticker=ticker,
                series_name=a.get('series_name'),  # CRITICAL: Pass series_name
                total_capacity=a.get('total_capacity'),
                remaining_capacity=a.get('remaining_capacity'),
                placement_agent=a.get('placement_agent'),
                status=a.get('status'),
                agreement_start_date=a.get('agreement_start_date'),
                filing_date=a.get('filing_date'),
                filing_url=a.get('filing_url'),
                potential_shares_at_current_price=int(Decimal(str(a.get('remaining_capacity', 0))) / current_price) if current_price and a.get('remaining_capacity') else None,
                notes=a.get('notes')
            )
            for a in [self._sanitize_field_lengths(x, atm_limits) for x in extracted_data.get('atm_offerings', [])]
        ]
        
        # Parse shelf registrations (con nuevos campos)
        shelf_limits = {'security_type': 50, 'registration_statement': 50, 'last_banker': 255, 'status': 50, 'series_name': 255}
        shelf_registrations = [
            ShelfRegistrationModel(
                ticker=ticker,
                series_name=s.get('series_name'),  # CRITICAL: Pass series_name
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
        s1_limits = {'underwriter_agent': 255, 'status': 50, 'series_name': 255}
        s1_offerings = [
            S1OfferingModel(
                ticker=ticker,
                series_name=s1.get('series_name') or s1.get('name'),  # Gemini may use 'name' or 'series_name'
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
                series_name=cp.get('series_name'),  # CRITICAL: Pass series_name
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
                last_update_date=cp.get('last_update_date'),
                # Split adjustment tracking
                split_adjusted=cp.get('split_adjusted'),
                split_factor=cp.get('split_factor'),
                original_conversion_price=cp.get('original_conversion_price'),
                # Trazabilidad de filings
                source_filing=cp.get('_source'),
                source_filings=cp.get('_sources'),
                merged_from_count=cp.get('_merged_from')
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
        
        # =================================================================
        # CALCULAR ATM REMAINING REAL basándose en ATM Sales extraídos
        # =================================================================
        # Los completed_offerings con offering_type='ATM Sale' representan
        # ventas reales bajo el ATM program, extraídas de los 10-Q/10-K.
        # Calculamos el remaining_capacity real = total - sum(sales)
        self._calculate_atm_remaining_from_sales(atm_offerings, completed_offerings, ticker)
        
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
            free_float=free_float,
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

