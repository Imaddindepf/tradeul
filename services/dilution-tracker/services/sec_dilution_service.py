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
from services.enhanced_data_fetcher import (
    EnhancedDataFetcher,
    get_filing_tier,
    quick_dilution_scan,
    should_process_with_grok,
    deduplicate_instruments,
    calculate_confidence_score,
    identify_risk_flags,
)
from services.grok_pool import GrokPool, get_grok_pool
from services.chunk_processor import ChunkProcessor, ChunkResult, ChunkStatus

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
        
        # Stats for pre-screening optimization
        self._stats = {
            "grok_calls": 0,
            "grok_calls_parallel": 0,
            "skipped_prescreening": 0,
            "cache_hits": 0,
            "retries": 0,
            "timeouts": 0
        }
        
        if not self.grok_api_key and not self._grok_pool:
            logger.warning("grok_api_key_not_configured")
    
    # ========================================================================
    # HELPER: Normalizadores para datos de Grok (robusto, sin asunciones)
    # ========================================================================
    
    def _to_hashable(self, value: Any) -> Any:
        """
        Convierte cualquier valor a un tipo hashable para usar en sets/dicts.
        
        CRÍTICO: Grok a veces devuelve estructuras inesperadas como:
        - {"value": 1.50, "currency": "$"} en lugar de 1.50
        - ["2025-12-31"] en lugar de "2025-12-31"
        - {"date": "2025-12-31", "type": "fixed"} en lugar de "2025-12-31"
        
        Esta función convierte todo a tipos hashables sin perder información.
        
        Returns:
            Valor hashable (str, int, float, bool, None, o tuple para listas)
        """
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            # Convertir dict a string JSON ordenado (determinístico)
            try:
                return json.dumps(value, sort_keys=True, default=str)
            except (TypeError, ValueError):
                return str(value)
        if isinstance(value, (list, tuple)):
            # Convertir lista a tupla recursivamente
            return tuple(self._to_hashable(item) for item in value)
        # Fallback: convertir a string
        return str(value)
    
    def _normalize_grok_value(self, value: Any, expected_type: str = "string") -> Any:
        """
        Normaliza un valor de Grok extrayendo el valor real de estructuras anidadas.
        
        Grok a veces devuelve:
        - {"value": X} → extraemos X
        - {"amount": X} → extraemos X
        - {"date": X} → extraemos X
        - [X] → extraemos X (si es lista de un elemento)
        - {"price": X, "currency": Y} → extraemos X
        
        Args:
            value: Valor crudo de Grok
            expected_type: "string", "number", "date", "any"
            
        Returns:
            Valor normalizado o None si no se puede extraer
        """
        if value is None:
            return None
            
        # Si ya es del tipo esperado, devolverlo
        if expected_type == "number" and isinstance(value, (int, float)):
            return value
        if expected_type == "string" and isinstance(value, str):
            return value
        if expected_type == "date" and isinstance(value, str):
            return value
        if expected_type == "any" and isinstance(value, (str, int, float, bool)):
            return value
            
        # Si es dict, intentar extraer el valor
        if isinstance(value, dict):
            # Campos comunes que contienen el valor real
            value_fields = ['value', 'amount', 'price', 'date', 'count', 'number', 
                           'shares', 'quantity', 'total', 'remaining', 'outstanding']
            
            for field in value_fields:
                if field in value:
                    extracted = value[field]
                    # Recursivamente normalizar el valor extraído
                    return self._normalize_grok_value(extracted, expected_type)
            
            # Si el dict tiene solo un valor, extraerlo
            if len(value) == 1:
                only_value = list(value.values())[0]
                return self._normalize_grok_value(only_value, expected_type)
            
            # No se puede extraer un valor simple, convertir a string
            logger.warning("grok_complex_value_normalized", 
                          original_type="dict",
                          keys=list(value.keys())[:5],
                          action="converting_to_string")
            return str(value)
            
        # Si es lista de un solo elemento, extraerlo
        if isinstance(value, list):
            if len(value) == 1:
                return self._normalize_grok_value(value[0], expected_type)
            elif len(value) == 0:
                return None
            else:
                # Lista con múltiples elementos - devolver el primero con warning
                logger.warning("grok_list_value_normalized",
                              list_length=len(value),
                              action="using_first_element")
                return self._normalize_grok_value(value[0], expected_type)
        
        # Fallback: intentar conversión directa
        if expected_type == "number":
            try:
                if isinstance(value, str):
                    # Limpiar símbolos comunes
                    cleaned = value.replace('$', '').replace(',', '').replace('%', '').strip()
                    if cleaned:
                        return float(cleaned)
                return None
            except (ValueError, TypeError):
                return None
        
        # Default: convertir a string
        return str(value) if value is not None else None
    
    def _safe_get_for_key(self, item: Dict, field: str, expected_type: str = "any") -> Any:
        """
        Obtiene un valor de un dict de forma segura para usar en keys de deduplicación.
        
        Combina _normalize_grok_value y _to_hashable para garantizar:
        1. El valor se extrae correctamente de estructuras anidadas
        2. El resultado es siempre hashable
        
        Args:
            item: Diccionario con los datos
            field: Nombre del campo a extraer
            expected_type: Tipo esperado ("string", "number", "date", "any")
            
        Returns:
            Valor hashable o None
        """
        raw_value = item.get(field)
        normalized = self._normalize_grok_value(raw_value, expected_type)
        return self._to_hashable(normalized)
    
    # ========================================================================
    # NORMALIZACIÓN DE CAMPOS DE RESPUESTA GROK
    # ========================================================================
    
    def _normalize_grok_extraction_fields(self, extracted: Dict) -> Dict:
        """
        Normaliza los campos de la respuesta de Grok a nuestro schema estándar.
        
        PROBLEMA: Grok usa nombres de campos inconsistentes:
        - "number", "number_issued", "shares" → debería ser "outstanding"
        - "issuance_date", "offering_date" → debería ser "issue_date"
        - "type", "description", "series" → debería ser "notes"
        
        Esta función mapea TODOS los campos alternativos a nuestro schema.
        
        Args:
            extracted: Respuesta raw de Grok (dict con warrants, atm_offerings, etc.)
            
        Returns:
            Dict normalizado con campos estandarizados
        """
        if not extracted:
            return extracted
        
        # Normalizar warrants
        if 'warrants' in extracted and isinstance(extracted['warrants'], list):
            extracted['warrants'] = [
                self._normalize_warrant_fields(w) for w in extracted['warrants']
            ]
        
        # Normalizar ATM offerings
        if 'atm_offerings' in extracted and isinstance(extracted['atm_offerings'], list):
            extracted['atm_offerings'] = [
                self._normalize_atm_fields(a) for a in extracted['atm_offerings']
            ]
        
        # Normalizar shelf registrations
        if 'shelf_registrations' in extracted and isinstance(extracted['shelf_registrations'], list):
            extracted['shelf_registrations'] = [
                self._normalize_shelf_fields(s) for s in extracted['shelf_registrations']
            ]
        
        # Normalizar completed offerings
        if 'completed_offerings' in extracted and isinstance(extracted['completed_offerings'], list):
            extracted['completed_offerings'] = [
                self._normalize_completed_fields(c) for c in extracted['completed_offerings']
            ]
        
        # Normalizar S-1 offerings
        if 's1_offerings' in extracted and isinstance(extracted['s1_offerings'], list):
            extracted['s1_offerings'] = [
                self._normalize_s1_fields(s) for s in extracted['s1_offerings']
            ]
        
        # Normalizar convertible notes
        if 'convertible_notes' in extracted and isinstance(extracted['convertible_notes'], list):
            extracted['convertible_notes'] = [
                self._normalize_convertible_note_fields(n) for n in extracted['convertible_notes']
            ]
        
        # Normalizar convertible preferred
        if 'convertible_preferred' in extracted and isinstance(extracted['convertible_preferred'], list):
            extracted['convertible_preferred'] = [
                self._normalize_convertible_preferred_fields(p) for p in extracted['convertible_preferred']
            ]
        
        # Normalizar equity lines
        if 'equity_lines' in extracted and isinstance(extracted['equity_lines'], list):
            extracted['equity_lines'] = [
                self._normalize_equity_line_fields(e) for e in extracted['equity_lines']
            ]
        
        return extracted
    
    def _normalize_warrant_fields(self, w: Dict) -> Dict:
        """
        Normaliza campos de un warrant al schema estándar.
        
        MAPEOS:
        - number, number_issued, shares, total_shares, warrants_outstanding, 
          quantity, amount → outstanding
        - issuance_date, offering_date, filing_date, grant_date, date → issue_date
        - type, description, series, name, warrant_type, title → notes
        - strike_price, price → exercise_price
        - expiry, expiry_date, maturity, expiration → expiration_date
        - potential_shares, dilution_shares, max_shares → potential_new_shares
        """
        if not isinstance(w, dict):
            return w
        
        normalized = dict(w)  # Copiar para no mutar original
        
        # === OUTSTANDING ===
        outstanding_aliases = [
            'number', 'number_issued', 'shares', 'total_shares', 
            'warrants_outstanding', 'quantity', 'amount', 'total_issued',
            'shares_issuable', 'warrant_shares', 'common_stock_issuable'
        ]
        if normalized.get('outstanding') is None:
            for alias in outstanding_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['outstanding'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === ISSUE_DATE ===
        issue_date_aliases = [
            'issuance_date', 'offering_date', 'filing_date', 'grant_date', 
            'date', 'issued_date', 'effective_date', 'agreement_date'
        ]
        if normalized.get('issue_date') is None:
            for alias in issue_date_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['issue_date'] = self._normalize_grok_value(normalized[alias], 'date')
                    break
        
        # === NOTES ===
        notes_aliases = [
            'type', 'description', 'series', 'name', 'warrant_type', 
            'title', 'terms', 'details', 'summary', 'warrant_name'
        ]
        if normalized.get('notes') is None:
            notes_parts = []
            for alias in notes_aliases:
                if alias in normalized and normalized[alias] is not None:
                    val = self._normalize_grok_value(normalized[alias], 'string')
                    if val and val not in notes_parts:
                        notes_parts.append(str(val))
            if notes_parts:
                normalized['notes'] = ' - '.join(notes_parts)
        
        # === EXERCISE_PRICE ===
        price_aliases = ['strike_price', 'price', 'strike', 'warrant_price', 'per_share_price']
        if normalized.get('exercise_price') is None:
            for alias in price_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['exercise_price'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === EXPIRATION_DATE ===
        expiration_aliases = ['expiry', 'expiry_date', 'maturity', 'expiration', 'expires', 'maturity_date']
        if normalized.get('expiration_date') is None:
            for alias in expiration_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['expiration_date'] = self._normalize_grok_value(normalized[alias], 'date')
                    break
        
        # === POTENTIAL_NEW_SHARES ===
        potential_aliases = ['potential_shares', 'dilution_shares', 'max_shares', 'shares_underlying']
        if normalized.get('potential_new_shares') is None:
            # Si no hay potential_new_shares, usar outstanding como fallback
            for alias in potential_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['potential_new_shares'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
            # Fallback: outstanding = potential_new_shares para warrants
            if normalized.get('potential_new_shares') is None and normalized.get('outstanding') is not None:
                normalized['potential_new_shares'] = normalized['outstanding']
        
        return normalized
    
    def _normalize_atm_fields(self, a: Dict) -> Dict:
        """
        Normaliza campos de un ATM offering al schema estándar.
        
        MAPEOS:
        - capacity, amount, aggregate_offering, max_offering, program_size → total_capacity
        - remaining, available, unused → remaining_capacity
        - agent, underwriter, sales_agent, placement_agent_name → placement_agent
        - date, effective_date, agreement_date → filing_date
        """
        if not isinstance(a, dict):
            return a
        
        normalized = dict(a)
        
        # === TOTAL_CAPACITY ===
        capacity_aliases = [
            'capacity', 'amount', 'aggregate_offering', 'max_offering', 
            'program_size', 'total_amount', 'aggregate_amount', 'offering_amount'
        ]
        if normalized.get('total_capacity') is None:
            for alias in capacity_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['total_capacity'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === REMAINING_CAPACITY ===
        remaining_aliases = ['remaining', 'available', 'unused', 'remaining_amount', 'available_capacity']
        if normalized.get('remaining_capacity') is None:
            for alias in remaining_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['remaining_capacity'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === PLACEMENT_AGENT ===
        agent_aliases = [
            'agent', 'underwriter', 'sales_agent', 'placement_agent_name',
            'dealer', 'manager', 'distributor'
        ]
        if normalized.get('placement_agent') is None:
            for alias in agent_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['placement_agent'] = self._normalize_grok_value(normalized[alias], 'string')
                    break
        
        # === FILING_DATE ===
        date_aliases = ['date', 'effective_date', 'agreement_date', 'execution_date']
        if normalized.get('filing_date') is None:
            for alias in date_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['filing_date'] = self._normalize_grok_value(normalized[alias], 'date')
                    break
        
        return normalized
    
    def _normalize_shelf_fields(self, s: Dict) -> Dict:
        """
        Normaliza campos de un shelf registration al schema estándar.
        """
        if not isinstance(s, dict):
            return s
        
        normalized = dict(s)
        
        # === TOTAL_CAPACITY ===
        capacity_aliases = [
            'capacity', 'amount', 'aggregate_offering', 'max_offering',
            'registered_amount', 'total_amount', 'offering_amount'
        ]
        if normalized.get('total_capacity') is None:
            for alias in capacity_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['total_capacity'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === REMAINING_CAPACITY ===
        remaining_aliases = ['remaining', 'available', 'unused', 'remaining_amount']
        if normalized.get('remaining_capacity') is None:
            for alias in remaining_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['remaining_capacity'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === REGISTRATION_STATEMENT ===
        reg_aliases = ['form_type', 'type', 'form', 'statement_type', 'registration_type']
        if normalized.get('registration_statement') is None:
            for alias in reg_aliases:
                if alias in normalized and normalized[alias] is not None:
                    val = self._normalize_grok_value(normalized[alias], 'string')
                    # Normalizar a formato estándar (S-3, S-1, etc.)
                    if val:
                        val_upper = str(val).upper().replace(' ', '')
                        if 'S-3' in val_upper or 'S3' in val_upper:
                            normalized['registration_statement'] = 'S-3'
                        elif 'S-1' in val_upper or 'S1' in val_upper:
                            normalized['registration_statement'] = 'S-1'
                        elif 'S-11' in val_upper or 'S11' in val_upper:
                            normalized['registration_statement'] = 'S-11'
                        else:
                            normalized['registration_statement'] = val
                    break
        
        # === FILING_DATE ===
        date_aliases = ['date', 'effective_date', 'filed_date', 'registration_date']
        if normalized.get('filing_date') is None:
            for alias in date_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['filing_date'] = self._normalize_grok_value(normalized[alias], 'date')
                    break
        
        # === EXPIRATION_DATE ===
        exp_aliases = ['expiration', 'expiry', 'expires', 'valid_until']
        if normalized.get('expiration_date') is None:
            for alias in exp_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['expiration_date'] = self._normalize_grok_value(normalized[alias], 'date')
                    break
        
        return normalized
    
    def _normalize_completed_fields(self, c: Dict) -> Dict:
        """
        Normaliza campos de un completed offering al schema estándar.
        """
        if not isinstance(c, dict):
            return c
        
        normalized = dict(c)
        
        # === SHARES_ISSUED ===
        shares_aliases = ['shares', 'number_of_shares', 'total_shares', 'shares_offered', 'shares_sold']
        if normalized.get('shares_issued') is None:
            for alias in shares_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['shares_issued'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === PRICE_PER_SHARE ===
        price_aliases = ['price', 'offering_price', 'share_price', 'per_share']
        if normalized.get('price_per_share') is None:
            for alias in price_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['price_per_share'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === AMOUNT_RAISED ===
        amount_aliases = ['amount', 'gross_proceeds', 'proceeds', 'total_raised', 'offering_amount']
        if normalized.get('amount_raised') is None:
            for alias in amount_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['amount_raised'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === OFFERING_DATE ===
        date_aliases = ['date', 'closing_date', 'effective_date', 'completion_date']
        if normalized.get('offering_date') is None:
            for alias in date_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['offering_date'] = self._normalize_grok_value(normalized[alias], 'date')
                    break
        
        # === OFFERING_TYPE ===
        type_aliases = ['type', 'offering_name', 'description', 'title']
        if normalized.get('offering_type') is None:
            for alias in type_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['offering_type'] = self._normalize_grok_value(normalized[alias], 'string')
                    break
        
        return normalized
    
    def _normalize_s1_fields(self, s: Dict) -> Dict:
        """
        Normaliza campos de un S-1 offering al schema estándar.
        """
        if not isinstance(s, dict):
            return s
        
        normalized = dict(s)
        
        # === S1_FILING_DATE ===
        date_aliases = ['filing_date', 'date', 'effective_date', 'registration_date']
        if normalized.get('s1_filing_date') is None:
            for alias in date_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['s1_filing_date'] = self._normalize_grok_value(normalized[alias], 'date')
                    break
        
        # === DEAL_SIZE ===
        size_aliases = ['deal_size', 'amount', 'offering_amount', 'gross_proceeds', 'total_raised']
        if normalized.get('deal_size') is None:
            for alias in size_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['deal_size'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === SHARES_OFFERED ===
        shares_aliases = ['shares_offered', 'shares', 'number_of_shares', 'total_shares']
        if normalized.get('shares_offered') is None:
            for alias in shares_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['shares_offered'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === PRICE_RANGE ===
        price_aliases = ['price_range', 'price', 'estimated_price', 'offering_price']
        if normalized.get('price_range') is None:
            for alias in price_aliases:
                if alias in normalized and normalized[alias] is not None:
                    val = normalized[alias]
                    if isinstance(val, (int, float)):
                        normalized['price_range'] = f"${val}"
                    else:
                        normalized['price_range'] = self._normalize_grok_value(val, 'string')
                    break
        
        return normalized
    
    def _normalize_convertible_note_fields(self, n: Dict) -> Dict:
        """
        Normaliza campos de un convertible note al schema estándar.
        """
        if not isinstance(n, dict):
            return n
        
        normalized = dict(n)
        
        # === PRINCIPAL_AMOUNT ===
        principal_aliases = ['principal_amount', 'principal', 'amount', 'face_value', 'note_amount']
        if normalized.get('principal_amount') is None:
            for alias in principal_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['principal_amount'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === CONVERSION_PRICE ===
        conv_price_aliases = ['conversion_price', 'strike_price', 'price', 'conversion_rate']
        if normalized.get('conversion_price') is None:
            for alias in conv_price_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['conversion_price'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === ISSUE_DATE ===
        date_aliases = ['issue_date', 'issuance_date', 'date', 'effective_date']
        if normalized.get('issue_date') is None:
            for alias in date_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['issue_date'] = self._normalize_grok_value(normalized[alias], 'date')
                    break
        
        # === MATURITY_DATE ===
        maturity_aliases = ['maturity_date', 'maturity', 'expiration', 'due_date']
        if normalized.get('maturity_date') is None:
            for alias in maturity_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['maturity_date'] = self._normalize_grok_value(normalized[alias], 'date')
                    break
        
        # === HOLDER ===
        holder_aliases = ['holder', 'investor', 'lender', 'noteholder', 'purchaser']
        if normalized.get('holder') is None:
            for alias in holder_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['holder'] = self._normalize_grok_value(normalized[alias], 'string')
                    break
        
        return normalized
    
    def _normalize_convertible_preferred_fields(self, p: Dict) -> Dict:
        """
        Normaliza campos de un convertible preferred al schema estándar.
        """
        if not isinstance(p, dict):
            return p
        
        normalized = dict(p)
        
        # === SERIES ===
        series_aliases = ['series', 'name', 'title', 'designation', 'series_name']
        if normalized.get('series') is None:
            for alias in series_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['series'] = self._normalize_grok_value(normalized[alias], 'string')
                    break
        
        # === TOTAL_DOLLAR_AMOUNT_ISSUED ===
        amount_aliases = [
            'total_dollar_amount_issued', 'amount', 'total_amount', 
            'proceeds', 'gross_proceeds', 'offering_amount'
        ]
        if normalized.get('total_dollar_amount_issued') is None:
            for alias in amount_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['total_dollar_amount_issued'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === CONVERSION_PRICE ===
        conv_aliases = ['conversion_price', 'strike_price', 'price', 'conversion_rate']
        if normalized.get('conversion_price') is None:
            for alias in conv_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['conversion_price'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === ISSUE_DATE ===
        date_aliases = ['issue_date', 'issuance_date', 'date', 'effective_date']
        if normalized.get('issue_date') is None:
            for alias in date_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['issue_date'] = self._normalize_grok_value(normalized[alias], 'date')
                    break
        
        return normalized
    
    def _normalize_equity_line_fields(self, e: Dict) -> Dict:
        """
        Normaliza campos de un equity line al schema estándar.
        """
        if not isinstance(e, dict):
            return e
        
        normalized = dict(e)
        
        # === TOTAL_CAPACITY ===
        capacity_aliases = [
            'total_capacity', 'capacity', 'amount', 'commitment_amount',
            'max_amount', 'facility_size', 'line_amount'
        ]
        if normalized.get('total_capacity') is None:
            for alias in capacity_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['total_capacity'] = self._normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === COUNTERPARTY ===
        counterparty_aliases = ['counterparty', 'investor', 'purchaser', 'buyer', 'provider']
        if normalized.get('counterparty') is None:
            for alias in counterparty_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['counterparty'] = self._normalize_grok_value(normalized[alias], 'string')
                    break
        
        # === AGREEMENT_START_DATE ===
        date_aliases = ['agreement_start_date', 'start_date', 'date', 'effective_date', 'execution_date']
        if normalized.get('agreement_start_date') is None:
            for alias in date_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['agreement_start_date'] = self._normalize_grok_value(normalized[alias], 'date')
                    break
        
        # === AGREEMENT_END_DATE ===
        end_aliases = ['agreement_end_date', 'end_date', 'expiration', 'termination_date']
        if normalized.get('agreement_end_date') is None:
            for alias in end_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['agreement_end_date'] = self._normalize_grok_value(normalized[alias], 'date')
                    break
        
        return normalized
    
    # ========================================================================
    # HELPER: Chunk size dinámico para optimización
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
    
    async def get_shares_history(self, ticker: str) -> Dict[str, Any]:
        """
        Get historical shares outstanding from SEC-API /float endpoint.
        This provides official SEC data for dilution history.
        
        Returns:
            Dict with shares history, dilution metrics, and all records.
        """
        try:
            ticker = ticker.upper()
            
            # Check Redis cache first
            cache_key = f"sec_dilution:shares_history:{ticker}"
            cached = await self.redis.get(cache_key, deserialize=True)
            if cached:
                logger.info("shares_history_from_cache", ticker=ticker)
                return cached
            
            # Fetch from SEC-API
            result = await self.enhanced_fetcher.fetch_shares_history(ticker)
            
            # Cache for 6 hours (shares don't change that often)
            if "error" not in result:
                await self.redis.set(cache_key, result, ttl=21600, serialize=True)
            
            return result
            
        except Exception as e:
            logger.error("get_shares_history_failed", ticker=ticker, error=str(e))
            return {"error": str(e)}
    
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
                return cached
            
            # Fetch from FMP
            result = await self.enhanced_fetcher.fetch_cash_data(ticker)
            
            # Cache for 4 hours
            if result.get("error") is None:
                await self.redis.set(cache_key, result, ttl=14400, serialize=True)
            
            return result
            
        except Exception as e:
            logger.error("get_cash_data_failed", ticker=ticker, error=str(e))
            return {"error": str(e)}
    
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
    
    def _parse_price(self, value: Any) -> Optional[float]:
        """Parsear precio limpiando símbolos como $ y comas"""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # Limpiar símbolos: $, €, comas, espacios
            cleaned = value.replace('$', '').replace('€', '').replace(',', '').strip()
            if not cleaned:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None
    
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
            
            # Si no está en BD, usar SEC EDGAR API (con cliente compartido)
            url = f"{self.SEC_EDGAR_BASE_URL}/submissions/CIK{ticker}.json"
            
            content = await http_clients.sec_gov.get_filing_content(url)
            if content:
                try:
                    data = json.loads(content)
                    cik = data.get('cik')
                    company_name = data.get('name')
                    return str(cik).zfill(10), company_name
                except json.JSONDecodeError:
                    pass
            
            # Fallback: usar SEC company tickers JSON (con cliente compartido)
            data = await http_clients.sec_gov.get_company_tickers()
            if data:
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
        Buscar TODOS los filings usando SEC-API.io Query API (FUENTE DE VERDAD)
        
        IMPORTANTE: Usamos el Query API correcto, NO full-text-search.
        
        Query API (https://api.sec-api.io):
        - Filtra por METADATA (ticker, formType, filedAt)
        - Devuelve TODOS los filings del ticker desde 1993+
        - Es la fuente primaria para enumerar filings
        
        Full-Text Search (NO LO USAMOS AQUÍ):
        - Busca dentro del CONTENIDO de los filings
        - Indexa desde 2001
        - Se usa para buscar palabras clave dentro de documentos
        
        Estrategia TOP:
        1. Query AMPLIA: ticker + fecha, SIN filtrar formType
        2. Incluye automáticamente 20-F, 6-K, F-1, F-3 (foreign issuers)
        3. Filtrado inteligente después en memoria
        4. Ventana desde 2010 (warrants viven 10-15 años)
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            Lista COMPLETA de todos los filings desde 2010
        """
        try:
            sec_api_key = settings.SEC_API_IO_KEY
            
            if not sec_api_key:
                logger.warning("sec_api_io_key_missing_using_fmp_fallback")
                return await self._fetch_all_filings_from_fmp(ticker)
            
            base_url = "https://api.sec-api.io"
            
            # Query SIMPLE: Solo filtrar ticker y fecha
            # NO filtrar formType aquí - capturamos TODO y filtramos después
            # Ventana ampliada a 2010 (vs 2015 anterior)
            query = {
                "query": {
                    "query_string": {
                        "query": f'ticker:{ticker} AND filedAt:[2010-01-01 TO *]'
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
                
                # Usar cliente SEC-API con connection pooling
                data = await http_clients.sec_api.query_api(query) if http_clients.sec_api else None
                
                if not data:
                    logger.warning("sec_api_io_error", ticker=ticker)
                    break
                
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
            
            # Ya NO usamos FMP como complemento automático
            # SEC-API Query API debe devolvernos TODO
            # FMP solo se usa como fallback en caso de ERROR (catch abajo)
            
            return all_filings
            
        except Exception as e:
            logger.error("fetch_sec_api_io_failed", ticker=ticker, error=str(e))
            # Fallback a FMP
            logger.info("falling_back_to_fmp", ticker=ticker)
            return await self._fetch_all_filings_from_fmp(ticker)
    
    async def _fetch_all_filings_from_fmp(self, ticker: str) -> List[Dict]:
        """
        Buscar TODOS los filings desde 2010 usando FMP API (FALLBACK)
        
        Usamos FMP como fallback/sanity check cuando SEC-API falla.
        
        FMP ventajas:
        - Paginación simple
        - Búsqueda por símbolo (no necesita CIK)
        - Metadata estructurada
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            Lista completa de TODOS los filings desde 2010
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
                # Usar cliente FMP con connection pooling
                filings_batch = await http_clients.fmp.get(
                    f"sec_filings/{ticker}",
                    params={"page": page}
                )
                
                if filings_batch is None:
                    logger.warning("fmp_api_error", ticker=ticker, page=page)
                    break
                
                # Si no hay más filings, terminar
                if not filings_batch or len(filings_batch) == 0:
                    break
                
                # Convertir formato FMP a nuestro formato
                for filing in filings_batch:
                    # Filtrar solo desde 2010 (consistente con SEC-API)
                    filing_date = filing.get('fillingDate', filing.get('acceptedDate', ''))
                    if filing_date and filing_date >= '2010-01-01':
                        # Normalizar tipo de filing (FMP usa "10K" pero necesitamos "10-K")
                        form_type = self._normalize_form_type(filing.get('type', ''))
                        all_filings.append({
                            'form_type': form_type,
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
            
            # Usar cliente SEC.gov con connection pooling
            content = await http_clients.sec_gov.get_filing_content(url)
            
            if not content:
                logger.error("sec_api_error", cik=cik)
                return []
            
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                logger.error("sec_json_parse_error", cik=cik)
                return []
            
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
            url = "https://www.sec.gov/cgi-bin/browse-edgar"
            
            params = {
                "action": "getcompany",
                "CIK": cik,
                "type": "424",  # Todos los 424B (424B5, 424B3, 424B4, 424B7)
                "dateb": "",  # Sin límite de fecha
                "owner": "exclude",
                "count": max_count,
                "output": "atom"  # Formato XML/Atom para parsear
            }
            
            # Construir URL con params para usar cliente SEC.gov
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            full_url = f"{url}?{query_string}"
            
            # Usar cliente SEC.gov con connection pooling
            content = await http_clients.sec_gov.get_filing_content(full_url)
            
            if not content:
                logger.warning("sec_424b_search_failed", cik=cik)
                return []
            
            # Parsear XML/Atom
            soup = BeautifulSoup(content, 'xml')
            
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
    
    def _normalize_form_type(self, form_type: str) -> str:
        """
        Normalizar tipo de filing de FMP al formato estándar SEC
        
        FMP usa formatos como "10K", "10Q", "8K", "S3" pero necesitamos "10-K", "10-Q", "8-K", "S-3"
        """
        if not form_type:
            return ''
        
        form_type = form_type.strip().upper()
        
        # Mapeo de formatos comunes (US y Foreign)
        normalization_map = {
            # US Domestic
            '10K': '10-K',
            '10-K': '10-K',
            '10KA': '10-K/A',
            '10-K/A': '10-K/A',
            '10Q': '10-Q',
            '10-Q': '10-Q',
            '10QA': '10-Q/A',
            '10-Q/A': '10-Q/A',
            '8K': '8-K',
            '8-K': '8-K',
            '8KA': '8-K/A',
            '8-K/A': '8-K/A',
            'S3': 'S-3',
            'S-3': 'S-3',
            'S3A': 'S-3/A',
            'S-3/A': 'S-3/A',
            'S1': 'S-1',
            'S-1': 'S-1',
            'S1A': 'S-1/A',
            'S-1/A': 'S-1/A',
            'S8': 'S-8',
            'S-8': 'S-8',
            'S11': 'S-11',
            'S-11': 'S-11',
            # Foreign Private Issuer
            '20F': '20-F',
            '20-F': '20-F',
            '20FA': '20-F/A',
            '20-F/A': '20-F/A',
            '6K': '6-K',
            '6-K': '6-K',
            '6KA': '6-K/A',
            '6-K/A': '6-K/A',
            'F1': 'F-1',
            'F-1': 'F-1',
            'F1A': 'F-1/A',
            'F-1/A': 'F-1/A',
            'F3': 'F-3',
            'F-3': 'F-3',
            'F3A': 'F-3/A',
            'F-3/A': 'F-3/A',
        }
        
        # Intentar match exacto primero
        if form_type in normalization_map:
            return normalization_map[form_type]
        
        # Si ya tiene el formato correcto, retornarlo
        if '-' in form_type:
            return form_type
        
        # Intentar agregar guión si es un número seguido de letra (ej: "10K" -> "10-K")
        match = re.match(r'^(\d+)([A-Z]+)(.*)$', form_type)
        if match:
            number = match.group(1)
            letters = match.group(2)
            rest = match.group(3)
            normalized = f"{number}-{letters}{rest}"
            # Verificar si el formato normalizado está en el mapa
            if normalized in normalization_map:
                return normalization_map[normalized]
            return normalized
        
        # Si no se puede normalizar, retornar original
        return form_type
    
    def _construct_filing_url(self, cik: str, accession_number: str, primary_document: str) -> str:
        """Construir URL del filing"""
        accession_no_dashes = accession_number.replace('-', '')
        return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{primary_document}"
    
    def _filter_relevant_filings(self, filings: List[Dict]) -> List[Dict]:
        """
        Filtrar filings relevantes para análisis de dilución TOP
        
        CAMBIOS vs versión anterior:
        - ✅ NO limitar 8-K arbitrariamente a 30 (un 8-K de 2018 puede tener warrant activo)
        - ✅ INCLUIR 20-F y 6-K (empresas foreign issuer como GLMD)
        - ✅ NO descartar form types desconocidos (marcar como OTHER)
        - ✅ Ventana desde 2010 (vs 2015 anterior)
        
        PRIORIDAD DE FILINGS PARA DILUCIÓN:
        
        Tier 1 (CRÍTICOS - Shelf Registrations):
        - S-3, S-3/A, S-3ASR: Universal shelf registrations
        - S-1, S-1/A: Initial registrations (IPO y follow-ons)
        - F-3, F-3/A: Foreign issuer shelf (equivalente a S-3)
        - F-1, F-1/A: Foreign issuer initial registration (equivalente a S-1)
        - S-8: Employee stock plans (puede indicar warrants)
        
        Tier 2 (MUY IMPORTANTES - Annual/Quarterly Reports):
        - 10-K, 10-K/A: Annual report (equity structure completa)
        - 10-Q, 10-Q/A: Quarterly report (equity changes)
        - 20-F, 20-F/A: Foreign issuer annual (equivalente a 10-K) 🔥 CRÍTICO
        - 6-K: Foreign issuer current report (equivalente a 8-K y puede tener 10-Q info) 🔥 CRÍTICO
        
        Tier 3 (IMPORTANTES - Prospectus Supplements):
        - 424B5, 424B3, 424B4, 424B7, 424B2: Offerings activos con detalles
        - FWP: Free writing prospectus
        
        Tier 4 (ÚTILES - Current Reports):
        - 8-K, 8-K/A: Current report (offerings, warrant exercises) 🔥 NO LIMITAR
        
        Tier 5 (COMPLEMENTARIOS):
        - DEF 14A, DEFM14A, DEFR14A, DEFA14A: Proxy statements
        - SC 13D, SC 13G: Beneficial ownership
        
        Tier 6 (OTHER):
        - Cualquier otro tipo no reconocido → NO DESCARTAR, marcar como OTHER
        """
        
        result = []
        forms_used = set()
        form_type_counts = {}
        unknown_types = set()  # Para logging de tipos desconocidos
        
        # Año de corte: 2010 (vs 2015 anterior)
        from datetime import date
        year_cutoff = date(2010, 1, 1)
        
        # Tipos relevantes AMPLIADOS (incluye TODO lo importante)
        relevant_types = {
            # Tier 1: Shelf Registrations (US + Foreign)
            'S-3', 'S-3/A', 'S-3ASR', 'S-1', 'S-1/A', 'S-8', 'S-11',
            'F-1', 'F-1/A', 'F-3', 'F-3/A', 'F-4', 'F-4/A',
            
            # Tier 2: Annual/Quarterly Reports (US + Foreign)
            '10-K', '10-K/A', '10-Q', '10-Q/A',
            '20-F', '20-F/A',  # 🔥 Foreign annual report
            '6-K', '6-K/A',    # 🔥 Foreign current report
            
            # Tier 3: Prospectus Supplements
            '424B5', '424B3', '424B4', '424B7', '424B2', 'FWP',
            
            # Tier 4: Current Reports
            '8-K', '8-K/A',  # 🔥 NO LIMITAR arbitrariamente
            
            # Tier 5: Proxy & Ownership
            'DEF 14A', 'DEFM14A', 'DEFR14A', 'DEFA14A',
            'SC 13D', 'SC 13G', 'SC 13D/A', 'SC 13G/A',
            
            # Tier 6: Otros
            'SC TO-I', 'SC TO-T', 'SC 14D9',
        }
        
        for f in filings:
            form_type = f['form_type']
            
            # Contar TODOS los tipos (para analytics)
            form_type_counts[form_type] = form_type_counts.get(form_type, 0) + 1
            
            # Verificar fecha
            try:
                filing_date_str = f['filing_date']
                if ' ' in filing_date_str:
                    filing_date_str = filing_date_str.split(' ')[0]
                
                filing_date = datetime.strptime(filing_date_str, '%Y-%m-%d').date()
                
                if filing_date < year_cutoff:
                    continue
            except:
                # Si no tiene fecha válida, skip
                continue
            
            # Estrategia nueva: INCLUIR tipos relevantes + marcar unknown como OTHER
            if form_type in relevant_types:
                result.append(f)
                forms_used.add(form_type)
            else:
                # NO descartar tipos desconocidos - puede ser importante
                # Ejemplos: 20FR, 6-KR, FWP/A, etc.
                unknown_types.add(form_type)
                # Agregar de todas formas pero marcar internamente
                f_copy = f.copy()
                f_copy['_marked_as_other'] = True
                result.append(f_copy)
        
        # Log COMPLETO para debugging
        logger.info("filings_filtered_top", 
                   total_input=len(filings), 
                   total_output=len(result), 
                   forms_used=sorted(list(forms_used)),
                   unknown_types=sorted(list(unknown_types)),
                   form_type_counts_top_20=dict(sorted(form_type_counts.items(), key=lambda x: x[1], reverse=True)[:20]),
                   has_20f='20-F' in forms_used or '20-F/A' in forms_used,
                   has_6k='6-K' in forms_used or '6-K/A' in forms_used,
                   count_8k=form_type_counts.get('8-K', 0),
                   count_20f=form_type_counts.get('20-F', 0) + form_type_counts.get('20-F/A', 0),
                   count_6k=form_type_counts.get('6-K', 0) + form_type_counts.get('6-K/A', 0))
        
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
    
    async def _process_chunks_parallel(
        self,
        ticker: str,
        company_name: str,
        chunks: List[List[Dict]],
        focus: str,
        parsed_tables: Optional[Dict] = None,
        max_concurrent: Optional[int] = None
    ) -> List[Optional[Dict]]:
        """
        Procesar múltiples chunks en PARALELO con ChunkProcessor profesional.
        
        Características:
        - Timeout dinámico basado en tamaño de archivos
        - Retry inteligente con rotación de keys
        - Workers independientes (un chunk lento no bloquea otros)
        - Recovery pass para chunks fallidos
        - NUNCA se pierde un filing
        
        Args:
            ticker: Ticker symbol
            company_name: Company name  
            chunks: Lista de chunks (cada chunk es una lista de filings)
            focus: Descripción de qué buscar
            parsed_tables: Tablas pre-parseadas (opcional)
            max_concurrent: Límite de concurrencia (default: num_keys * 2)
            
        Returns:
            Lista de resultados (uno por chunk, puede contener None si falló)
        """
        if not chunks:
            return []
        
        # Determinar número de workers
        if max_concurrent is None:
            if self._grok_pool:
                max_concurrent = self._grok_pool.num_keys * 2
            else:
                max_concurrent = 2
        
        # Crear procesador con configuración optimizada
        processor = ChunkProcessor(
            extract_fn=self._extract_pass_focused,
            max_workers=max_concurrent,
            base_timeout=30,      # 30s base
            timeout_per_10kb=1.0  # +1s por cada 10KB
        )
        
        # Procesar todos los chunks
        chunk_results = await processor.process_all(
            chunks=chunks,
            ticker=ticker,
            company_name=company_name,
            focus=focus,
            parsed_tables=parsed_tables
        )
        
        # Actualizar estadísticas
        stats = processor.get_stats()
        self._stats["grok_calls_parallel"] += stats.total_chunks
        self._stats["retries"] += stats.retries
        self._stats["timeouts"] += stats.timeouts
        
        # Convertir ChunkResult a Dict (manteniendo compatibilidad)
        results: List[Optional[Dict]] = []
        for cr in chunk_results:
            if cr.status in (ChunkStatus.COMPLETED, ChunkStatus.RECOVERED):
                results.append(cr.data)
            else:
                results.append(None)
        
        # Log de chunks fallidos para análisis
        failed = processor.get_failed_chunks()
        if failed:
            logger.warning("chunks_failed_after_recovery",
                          ticker=ticker,
                          failed_count=len(failed),
                          failed_indices=[w["idx"] for w in failed])
        
        return results
    
    async def _extract_with_multipass_grok(
        self,
        ticker: str,
        company_name: str,
        filing_contents: List[Dict],
        parsed_tables: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        MULTI-PASS EXTRACTION: Analizar en múltiples pasadas enfocadas
        
        ARQUITECTURA OPTIMIZADA:
        - Pass 1: ❌ ELIMINADO (10-K) → datos vienen de SEC-API /float
        - Pass 2: S-3/S-1/F-3/F-1 (Tier 1: shelf registrations) → Grok directo
        - Pass 3: 424B (Tier 1: prospectus supplements) → Grok PARALELO
        - Pass 4: ❌ 10-Q ELIMINADO → datos vienen de FMP API
                  6-K (Tier 2: foreign reports) → pre-screen + Grok
        - Pass 5: S-8 (Tier 2: employee stock plans) → pre-screen + Grok
        - Pass 6: 8-K (Tier 2: current reports) → pre-screen + Grok
        - Pass 7: DEF 14A (Tier 2: proxy statements) → pre-screen + Grok
        
        TIER SYSTEM:
        - Tier 1 (424B, S-1, S-3, etc.): Siempre procesar
        - Tier 2 (8-K, 6-K, DEF 14A, S-8): Pre-screen con keywords
        - Tier 3 (10-K, 10-Q): SKIP - usar APIs estructuradas
        
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
            
            # ELIMINADO Pass 1: 10-K/20-F
            # Los datos de 10-K/20-F ahora vienen de APIs estructuradas:
            # - SEC-API /float → shares outstanding history
            # - FMP API → balance sheet, cash flow
            # Esto ahorra ~40% del tiempo de procesamiento y reduce costos de Grok
            logger.info("pass1_skipped_using_structured_apis", ticker=ticker)
            
            # Pass 2: S-3/S-1/S-11 y F-3/F-1 (Shelf Registrations, S-1 Offerings, Preferred Stock)
            # F-3 y F-1 son equivalentes para empresas extranjeras
            # SIN LÍMITE - analizar TODOS (con chunking automático si hay muchos)
            filings_s3 = [f for f in filing_contents if f['form_type'] in ['S-3', 'S-3/A', 'S-1', 'S-1/A', 'S-11', 'F-3', 'F-3/A', 'F-1', 'F-1/A']]
            if filings_s3:
                logger.info("multipass_pass2_s3", ticker=ticker, count=len(filings_s3))
                # Chunking automático - REDUCIDO de 20→5 para evitar saturar Grok
                # S-3/F-3 pueden ser grandes, 5 a la vez es más seguro
                chunk_size = 5  # Analizar 5 filings por vez
                for i in range(0, len(filings_s3), chunk_size):
                    chunk = filings_s3[i:i+chunk_size]
                    self._stats["grok_calls"] += 1
                    logger.info("multipass_pass2_s3_chunk", ticker=ticker, chunk_num=i//chunk_size+1, total_chunks=(len(filings_s3)+chunk_size-1)//chunk_size, chunk_size=len(chunk))
                    result_s3 = await self._extract_pass_focused(
                        ticker, company_name, chunk,
                        focus="S-1 offerings, shelf registrations, and preferred stock registrations (S-11) - extract S-1 offerings with deal sizes and warrant coverage, shelf MAXIMUM registered capacity (NOT actual sales), remaining capacity, expiration, baby shelf restrictions, amounts raised"
                    )
                    if result_s3:
                        logger.info("pass2_chunk_extracted", ticker=ticker, chunk_num=i//chunk_size+1,
                                   shelfs=len(result_s3.get('shelf_registrations', [])),
                                   s1=len(result_s3.get('s1_offerings', [])))
                    else:
                        logger.warning("pass2_chunk_empty", ticker=ticker, chunk_num=i//chunk_size+1)
                    if result_s3:
                        all_shelfs.extend(result_s3.get('shelf_registrations', []))
                        all_s1.extend(result_s3.get('s1_offerings', []))
                        all_convertible_preferred.extend(result_s3.get('convertible_preferred', []))
            
            # Pass 3: 424B5/424B7 (Prospectus Supplements - detalles de cada offering, S-1 pricing)
            # SIN LÍMITE - analizar TODOS
            # 🚀 OPTIMIZADO: Chunk size dinámico + procesamiento paralelo
            filings_424b = [f for f in filing_contents if f['form_type'] in ['424B5', '424B3', '424B7', '424B4']]
            if filings_424b:
                # 🚀 OPTIMIZACIÓN: Chunk size dinámico basado en tamaño promedio
                chunk_size = self._calculate_optimal_chunk_size(filings_424b, "424B")
                
                logger.info("multipass_pass3_424b", ticker=ticker, count=len(filings_424b), 
                           optimal_chunk_size=chunk_size)
                
                chunks_424b = [
                    filings_424b[i:i+chunk_size] 
                    for i in range(0, len(filings_424b), chunk_size)
                ]
                
                # Decidir si usar paralelo o secuencial
                use_parallel = self._grok_pool is not None and self._grok_pool.num_keys > 1 and len(chunks_424b) > 2
                
                if use_parallel:
                    # 🚀 PARALELO: Procesar todos los chunks simultáneamente
                    logger.info("pass3_parallel_start", 
                               ticker=ticker, 
                               total_chunks=len(chunks_424b),
                               num_keys=self._grok_pool.num_keys)
                    
                    results_424b = await self._process_chunks_parallel(
                        ticker, company_name, chunks_424b,
                        focus="Prospectus supplements and S-1 pricing - extract S-1 offerings with final pricing and warrant coverage, warrants issued with offerings, offering details, convertible notes details"
                    )
                    
                    # Agregar resultados de todos los chunks
                    for result_424b in results_424b:
                        if result_424b:
                            all_warrants.extend(result_424b.get('warrants', []))
                            all_atm.extend(result_424b.get('atm_offerings', []))
                            all_shelfs.extend(result_424b.get('shelf_registrations', []))
                            all_completed.extend(result_424b.get('completed_offerings', []))
                            all_s1.extend(result_424b.get('s1_offerings', []))
                            all_convertible_notes.extend(result_424b.get('convertible_notes', []))
                            all_convertible_preferred.extend(result_424b.get('convertible_preferred', []))
                            all_equity_lines.extend(result_424b.get('equity_lines', []))
                else:
                    # Secuencial (fallback si solo hay 1 key o pocos chunks)
                    for i, chunk in enumerate(chunks_424b):
                        self._stats["grok_calls"] += 1
                        logger.info("multipass_pass3_424b_chunk", ticker=ticker, chunk_num=i+1, total_chunks=len(chunks_424b), chunk_size=len(chunk))
                        result_424b = await self._extract_pass_focused(
                            ticker, company_name, chunk,
                            focus="Prospectus supplements and S-1 pricing - extract S-1 offerings with final pricing and warrant coverage, warrants issued with offerings, offering details, convertible notes details"
                        )
                        if result_424b:
                            logger.info("pass3_chunk_extracted", ticker=ticker, chunk_num=i+1,
                                       warrants=len(result_424b.get('warrants', [])),
                                       atm=len(result_424b.get('atm_offerings', [])),
                                       s1=len(result_424b.get('s1_offerings', [])))
                            all_warrants.extend(result_424b.get('warrants', []))
                            all_atm.extend(result_424b.get('atm_offerings', []))
                            all_shelfs.extend(result_424b.get('shelf_registrations', []))
                            all_completed.extend(result_424b.get('completed_offerings', []))
                            all_s1.extend(result_424b.get('s1_offerings', []))
                            all_convertible_notes.extend(result_424b.get('convertible_notes', []))
                            all_convertible_preferred.extend(result_424b.get('convertible_preferred', []))
                            all_equity_lines.extend(result_424b.get('equity_lines', []))
                        else:
                            logger.warning("pass3_chunk_empty", ticker=ticker, chunk_num=i+1)
            
            # ❌ ELIMINADO Pass 4: 10-Q
            # Los datos de 10-Q ahora vienen de APIs estructuradas:
            # - SEC-API /float → shares outstanding
            # - FMP API → cash flow, balance sheet
            # Esto ahorra ~30% del tiempo (10-Q son documentos muy grandes)
            logger.info("pass4_10q_skipped_using_structured_apis", ticker=ticker)
            
            # Pass 4: 6-K SOLAMENTE (Tier 2 para empresas extranjeras)
            # 6-K sigue siendo necesario porque puede contener anuncios de dilución
            filings_6k_raw = [f for f in filing_contents if f['form_type'] in ['6-K', '6-K/A']]
            
            if filings_6k_raw:
                # Pre-screen 6-K (pueden ser cientos)
                filings_6k_filtered = []
                skipped_6k = 0
                for f in filings_6k_raw:
                    content = f.get('content', '')
                    has_dilution, _ = quick_dilution_scan(content, f['form_type'])
                    if has_dilution:
                        filings_6k_filtered.append(f)
                    else:
                        skipped_6k += 1
                
                self._stats["skipped_prescreening"] += skipped_6k
                logger.info("pass4_6k_prescreened", ticker=ticker, 
                           original=len(filings_6k_raw), filtered=len(filings_6k_filtered), skipped=skipped_6k)
                
                if filings_6k_filtered:
                    # Chunking automático
                    chunk_size = 5  # 6-K son más pequeños que 10-Q
                    for i in range(0, len(filings_6k_filtered), chunk_size):
                        chunk = filings_6k_filtered[i:i+chunk_size]
                        self._stats["grok_calls"] += 1
                        logger.info("multipass_pass4_6k_chunk", ticker=ticker, chunk_num=i//chunk_size+1, 
                                   total_chunks=(len(filings_6k_filtered)+chunk_size-1)//chunk_size, chunk_size=len(chunk))
                        result_6k = await self._extract_pass_focused(
                            ticker, company_name, chunk,
                            focus="Foreign company reports (6-K) - extract actual shares issued/sold, warrant issuances, offering announcements, ATM updates"
                        )
                        if result_6k:
                            logger.info("pass4_6k_chunk_extracted", ticker=ticker, chunk_num=i//chunk_size+1,
                                       warrants=len(result_6k.get('warrants', [])),
                                       atm=len(result_6k.get('atm_offerings', [])))
                            all_warrants.extend(result_6k.get('warrants', []))
                            all_atm.extend(result_6k.get('atm_offerings', []))
                            all_completed.extend(result_6k.get('completed_offerings', []))
                            all_convertible_notes.extend(result_6k.get('convertible_notes', []))
                            all_convertible_preferred.extend(result_6k.get('convertible_preferred', []))
                            all_equity_lines.extend(result_6k.get('equity_lines', []))
                        else:
                            logger.warning("pass4_6k_chunk_empty", ticker=ticker, chunk_num=i//chunk_size+1)
            
            # Pass 5: S-8 (Employee stock plans - Tier 2: pre-screen)
            # S-8 rara vez contiene dilución relevante para traders, solo si tiene keywords
            filings_s8_raw = [f for f in filing_contents if f['form_type'] == 'S-8']
            if filings_s8_raw:
                # Pre-screen S-8 (usualmente no tiene dilución relevante)
                filings_s8_filtered = []
                skipped_s8 = 0
                for f in filings_s8_raw:
                    content = f.get('content', '')
                    has_dilution, _ = quick_dilution_scan(content)
                    if has_dilution:
                        filings_s8_filtered.append(f)
                    else:
                        skipped_s8 += 1
                
                self._stats["skipped_prescreening"] += skipped_s8
                logger.info("pass5_s8_prescreened", ticker=ticker, 
                           original=len(filings_s8_raw), filtered=len(filings_s8_filtered), skipped=skipped_s8)
                
                if filings_s8_filtered:
                    self._stats["grok_calls"] += 1
                    result_s8 = await self._extract_pass_focused(
                        ticker, company_name, filings_s8_filtered,
                        focus="Employee stock plans - extract any warrants or equity instruments"
                    )
                    if result_s8:
                        all_warrants.extend(result_s8.get('warrants', []))
            
            # Pass 6: 8-K y 6-K (Current reports - convertibles, equity lines, ATM updates)
            # 6-K es el equivalente para empresas extranjeras
            # PRE-SCREENING: Solo procesar 8-K/6-K que tienen keywords de dilución
            filings_8k = [f for f in filing_contents if f['form_type'] in ['8-K', '8-K/A', '6-K', '6-K/A']]
            if filings_8k:
                # PRE-SCREENING: Filtrar solo los que tienen keywords de dilución
                filings_8k_filtered = []
                skipped_count = 0
                for f in filings_8k:
                    content = f.get('content', '')
                    has_dilution, matched_kw = quick_dilution_scan(content)
                    if has_dilution:
                        filings_8k_filtered.append(f)
                    else:
                        skipped_count += 1
                
                self._stats["skipped_prescreening"] += skipped_count
                logger.info("multipass_pass6_8k_prescreened", 
                           ticker=ticker, 
                           original=len(filings_8k), 
                           filtered=len(filings_8k_filtered),
                           skipped=skipped_count,
                           grok_calls_saved=skipped_count)
                
                if filings_8k_filtered:
                    # ⚡ PARALELO: Usar ChunkProcessor para 8-K con chunk dinámico
                    chunk_size = self._calculate_optimal_chunk_size(filings_8k_filtered, "8-K")
                    chunks_8k = [filings_8k_filtered[i:i+chunk_size] for i in range(0, len(filings_8k_filtered), chunk_size)]
                    logger.info("pass6_parallel_start", ticker=ticker, total_chunks=len(chunks_8k), 
                               optimal_chunk_size=chunk_size)
                    
                    results_8k = await self._process_chunks_parallel(
                        chunks=chunks_8k,
                        ticker=ticker,
                        company_name=company_name,
                        focus="Current reports - extract convertible notes, convertible preferred, equity lines, ATM agreements, S-1 offerings, warrant issuances"
                    )
                    
                    for result_8k in results_8k:
                        if result_8k:
                            all_warrants.extend(result_8k.get('warrants', []))
                            all_atm.extend(result_8k.get('atm_offerings', []))
                            all_s1.extend(result_8k.get('s1_offerings', []))
                            all_convertible_notes.extend(result_8k.get('convertible_notes', []))
                            all_convertible_preferred.extend(result_8k.get('convertible_preferred', []))
                            all_equity_lines.extend(result_8k.get('equity_lines', []))
            
            # Pass 7: DEF 14A (Proxy Statements) - Tier 2 con pre-screening
            # Pueden contener: autorización de shares adicionales, stock splits, equity incentive plans
            filings_def14a = [f for f in filing_contents if f['form_type'] in ['DEF 14A', 'DEFA14A', 'DEF 14C']]
            if filings_def14a:
                # Pre-screen DEF 14A con keywords específicos
                filings_def14a_filtered = []
                skipped_def14a = 0
                for f in filings_def14a:
                    content = f.get('content', '')
                    has_dilution, matched_kw = quick_dilution_scan(content, f['form_type'])
                    if has_dilution:
                        filings_def14a_filtered.append(f)
                        logger.debug("def14a_has_dilution", ticker=ticker, keywords=matched_kw[:3])
                    else:
                        skipped_def14a += 1
                
                self._stats["skipped_prescreening"] += skipped_def14a
                logger.info("pass7_def14a_prescreened", 
                           ticker=ticker, 
                           original=len(filings_def14a), 
                           filtered=len(filings_def14a_filtered),
                           skipped=skipped_def14a)
                
                if filings_def14a_filtered:
                    # ⚡ PARALELO: Usar ChunkProcessor para DEF 14A con chunk dinámico
                    chunk_size = self._calculate_optimal_chunk_size(filings_def14a_filtered, "DEF 14A")
                    chunks_def14a = [filings_def14a_filtered[i:i+chunk_size] for i in range(0, len(filings_def14a_filtered), chunk_size)]
                    logger.info("pass7_parallel_start", ticker=ticker, total_chunks=len(chunks_def14a),
                               optimal_chunk_size=chunk_size)
                    
                    results_def14a = await self._process_chunks_parallel(
                        chunks=chunks_def14a,
                        ticker=ticker,
                        company_name=company_name,
                        focus="Proxy statements - extract proposals to authorize additional shares, increase authorized capital, stock splits, reverse splits, equity incentive plans, stock option plans"
                    )
                    
                    for result_def14a in results_def14a:
                        if result_def14a:
                            all_shelfs.extend(result_def14a.get('shelf_registrations', []))
                            all_equity_lines.extend(result_def14a.get('equity_lines', []))
            
            # 🔍 LOG PRE-DEDUP: Ver qué está devolviendo Grok ANTES de deduplicar
            logger.info(
                "pre_dedup_counts",
                ticker=ticker,
                raw_warrants=len(all_warrants),
                raw_atm=len(all_atm),
                raw_shelfs=len(all_shelfs),
                raw_completed=len(all_completed),
                raw_s1=len(all_s1),
                raw_convertible_notes=len(all_convertible_notes),
                raw_convertible_preferred=len(all_convertible_preferred),
                raw_equity_lines=len(all_equity_lines),
            )
            
            # 🔧 PROCESO DE LIMPIEZA DE WARRANTS (3 pasos):
            # 1. Deduplicate inicial
            warrants_deduped = self._deduplicate_warrants(all_warrants)
            logger.info("warrants_after_initial_dedup", ticker=ticker, count=len(warrants_deduped))
            
            # 2. Filtrar summary rows de 10-Q/10-K (para evitar doble conteo)
            warrants_filtered = self._filter_summary_warrants(warrants_deduped)
            summary_count = sum(1 for w in warrants_filtered if w.get('is_summary_row'))
            logger.info("warrants_summary_filtered", ticker=ticker, 
                       total=len(warrants_filtered), 
                       summary_rows=summary_count)
            
            # 3. Imputar exercise_price faltantes cuando se puede inferir
            warrants_imputed = self._impute_missing_exercise_prices(warrants_filtered)
            
            # 4. Clasificar estado de warrants (Active, Exercised, Replaced, Historical_Summary)
            warrants_classified = self._classify_warrant_status(warrants_imputed, ticker)
            
            # 5. Deduplicate final (por si el impute creó duplicados con la misma key)
            warrants_final = self._deduplicate_warrants(warrants_classified)
            logger.info("warrants_after_final_processing", ticker=ticker, count=len(warrants_final))
            
            # 🔧 PROCESO DE LIMPIEZA DE ATM:
            atm_deduped = self._deduplicate_atm(all_atm, ticker=ticker)
            atm_classified = self._classify_atm_status(atm_deduped, ticker)
            
            # 🔧 PROCESO DE LIMPIEZA DE SHELFS:
            shelfs_deduped = self._deduplicate_shelfs(all_shelfs, ticker=ticker)
            shelfs_classified = self._classify_shelf_status(shelfs_deduped, ticker)
            
            # Deduplicar y combinar
            combined_data = {
                'warrants': warrants_final,
                'atm_offerings': atm_classified,
                'shelf_registrations': shelfs_classified,
                'completed_offerings': self._deduplicate_completed(all_completed, ticker=ticker),
                's1_offerings': self._deduplicate_s1(all_s1),
                'convertible_notes': self._deduplicate_convertible_notes(all_convertible_notes),
                'convertible_preferred': self._deduplicate_convertible_preferred(all_convertible_preferred),
                'equity_lines': self._deduplicate_equity_lines(all_equity_lines)
            }
            
            # 📊 LOG OPTIMIZATION STATS
            logger.info("grok_optimization_stats", 
                       ticker=ticker,
                       grok_calls=self._stats["grok_calls"],
                       skipped_prescreening=self._stats["skipped_prescreening"],
                       estimated_savings=f"~{self._stats['skipped_prescreening'] * 15}s saved")
            
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
    
    async def _upload_filing_to_grok(
        self,
        ticker: str,
        form_type: str,
        filing_date: str,
        filing_content: str,
        grok_client: Optional[Client] = None
    ) -> Optional[str]:
        """
        Subir un filing como archivo a Grok Files API
        
        Args:
            ticker: Ticker symbol
            form_type: Tipo de filing (10-K, 424B5, etc.)
            filing_date: Fecha del filing
            filing_content: Contenido completo del filing
            grok_client: Cliente Grok pre-configurado (del pool)
            
        Returns:
            file_id de Grok o None si falla
        """
        try:
            # Usar cliente proporcionado o crear uno nuevo
            if grok_client is None:
                if not self.grok_api_key:
                    logger.error("grok_api_key_missing_for_file_upload")
                    return None
                grok_client = Client(api_key=self.grok_api_key, timeout=120)
            
            # Crear archivo temporal
            temp_file = tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.html',
                prefix=f'{ticker}_{form_type}_{filing_date}_',
                delete=False,
                encoding='utf-8'
            )
            
            try:
                # Escribir contenido
                temp_file.write(filing_content)
                temp_file.close()
                
                # Subir a Grok
                uploaded_file = grok_client.files.upload(temp_file.name)
                
                logger.info("filing_uploaded_to_grok", 
                           ticker=ticker, 
                           form_type=form_type,
                           filing_date=filing_date,
                           file_id=uploaded_file.id,
                           file_size=uploaded_file.size)
                
                return uploaded_file.id
                
            finally:
                # Limpiar archivo temporal del disco
                try:
                    os.unlink(temp_file.name)
                except:
                    pass
                    
        except Exception as e:
            logger.error("upload_filing_to_grok_failed", 
                        ticker=ticker, 
                        form_type=form_type, 
                        error=str(e))
            return None
    
    async def _cleanup_grok_files(self, file_ids: List[str], grok_client: Optional[Client] = None):
        """
        Limpiar archivos de Grok después de usarlos
        
        Args:
            file_ids: Lista de file_ids a borrar
            grok_client: Cliente Grok pre-configurado (del pool)
        """
        if not file_ids:
            return
        
        try:
            # Usar cliente proporcionado o crear uno nuevo
            if grok_client is None:
                if not self.grok_api_key:
                    return
                grok_client = Client(api_key=self.grok_api_key, timeout=120)
            
            for file_id in file_ids:
                try:
                    grok_client.files.delete(file_id)
                    logger.info("grok_file_deleted", file_id=file_id)
                except Exception as e:
                    logger.warning("grok_file_delete_failed", file_id=file_id, error=str(e))
                    
        except Exception as e:
            logger.error("cleanup_grok_files_failed", error=str(e))
    
    async def _extract_pass_with_files_api(
        self,
        ticker: str,
        company_name: str,
        filings: List[Dict],
        focus: str,
        parsed_tables: Optional[Dict] = None,
        max_retries: int = 3
    ) -> Optional[Dict]:
        """
        Extracción usando Grok Files API - CON POOL + RETRY + UPLOAD PARALELO
        
        OPTIMIZACIONES IMPLEMENTADAS:
        1. Upload paralelo: asyncio.gather en lugar de loop secuencial
        2. Direct prompt para docs <300KB: evita overhead de Files API
        3. Pool de keys con semáforos para máximo paralelismo
        
        MÉTRICAS DE MEJORA:
        - Upload paralelo: 3 filings × 2s = 6s → 2s (3x más rápido)
        - Direct prompt: ~8s vs ~17s con Files API (2x más rápido para docs pequeños)
        
        Args:
            ticker: Ticker symbol
            company_name: Company name
            filings: Lista de filings para analizar
            focus: Descripción de qué buscar
            parsed_tables: Tablas pre-parseadas (opcional)
            max_retries: Número máximo de reintentos
            
        Returns:
            Dict con datos extraídos
        """
        # 🚀 OPTIMIZACIÓN: Si el contenido total es pequeño, usar direct prompt
        total_content_size = sum(len(f.get('content', '')) for f in filings)
        if total_content_size < 300_000:  # <300KB → direct prompt más rápido
            logger.info("using_direct_prompt_optimization", 
                       ticker=ticker, 
                       total_size_kb=total_content_size // 1024,
                       filings_count=len(filings))
            return await self._extract_pass_direct_prompt(
                ticker, company_name, filings, focus, parsed_tables, max_retries
            )
        
        uploaded_file_ids = []
        grok_client = None
        key_name = None
        pool_idx = None
        
        for attempt in range(max_retries):
            try:
                # Obtener cliente del pool (si disponible) o usar el default
                if self._grok_pool and self._grok_pool.num_keys > 0:
                    grok_client, key_name, pool_idx = await self._grok_pool.get_client()
                    logger.debug("grok_pool_client_acquired", 
                                key_name=key_name, 
                                ticker=ticker,
                                attempt=attempt + 1)
                elif self.grok_api_key:
                    grok_client = Client(api_key=self.grok_api_key, timeout=120)
                    key_name = "default"
                else:
                    logger.error("no_grok_api_key_available")
                    return None
                
                logger.info("extract_with_files_api_started", 
                           ticker=ticker, 
                           filings_count=len(filings),
                           grok_key=key_name,
                           attempt=attempt + 1 if attempt > 0 else None)
                
                # 🚀 OPTIMIZACIÓN: SUBIR FILINGS EN PARALELO (antes era secuencial)
                # Antes: 3 filings × 2-3s = 6-9s
                # Ahora: max(2-3s) = 2-3s (3x más rápido)
                upload_tasks = [
                    self._upload_filing_to_grok(
                        ticker=ticker,
                        form_type=f['form_type'],
                        filing_date=f['filing_date'],
                        filing_content=f['content'],
                        grok_client=grok_client
                    )
                    for f in filings
                ]
                
                upload_results = await asyncio.gather(*upload_tasks, return_exceptions=True)
                
                # Procesar resultados de uploads
                file_references = []
                for i, result in enumerate(upload_results):
                    if isinstance(result, Exception):
                        logger.warning("parallel_upload_failed", 
                                      ticker=ticker, 
                                      filing_idx=i, 
                                      error=str(result))
                        continue
                    if result:  # result es file_id
                        uploaded_file_ids.append(result)
                        file_references.append({
                            'file_id': result,
                            'form_type': filings[i]['form_type'],
                            'filing_date': filings[i]['filing_date']
                        })
                
                if not file_references:
                    logger.warning("no_files_uploaded", ticker=ticker)
                    # Liberar cliente del pool
                    if self._grok_pool and pool_idx is not None:
                        self._grok_pool.release(pool_idx, success=False, error="no_files_uploaded")
                    return None
                
                logger.info("files_uploaded", ticker=ticker, count=len(file_references))
                
                # 2. CONSTRUIR PROMPT CON REFERENCIAS A ARCHIVOS
                files_list = "\n".join([
                    f"- {ref['form_type']} filed on {ref['filing_date']} (file_id: {ref['file_id']})"
                    for ref in file_references
                ])
                
                prompt = f"""
You are an EXPERT financial data extraction specialist analyzing SEC EDGAR filings for {company_name} (Ticker: {ticker}).

YOUR MISSION: Extract COMPREHENSIVE dilution data with MAXIMUM detail and accuracy.

THIS IS A FOCUSED ANALYSIS PASS. Your specific task:
**{focus}**

FILES PROVIDED ({len(file_references)} filings):
{files_list}

INSTRUCTIONS:
1. Search through ALL provided files systematically
2. Extract ALL relevant data for the focus area
3. Be THOROUGH - don't miss anything
4. If data is incomplete, use financial knowledge to infer missing details
5. Return ONLY valid JSON with the extracted data

RETURN FORMAT (JSON only, no markdown):
{{
  "warrants": [...],
  "atm_offerings": [...],
  "shelf_registrations": [...],
  "completed_offerings": [...],
  "s1_offerings": [...],
  "convertible_notes": [...],
  "convertible_preferred": [...],
  "equity_lines": [...]
}}

Each array should contain objects with relevant fields. Return empty arrays [] if nothing found for a category.
DO NOT return arrays with null-filled objects.
"""
                
                # 3. LLAMAR A GROK CON ARCHIVOS ADJUNTOS
                try:
                    chat = grok_client.chat.create(model="grok-4-fast", temperature=0.1)
                except:
                    # Fallback a grok-4 si grok-4-fast no está disponible
                    chat = grok_client.chat.create(model="grok-4", temperature=0.1)
                
                chat.append(system("You are a financial data extraction expert. Return ONLY valid JSON."))
                
                # Crear mensaje con archivos adjuntos
                file_attachments = [file(fid) for fid in uploaded_file_ids]
                chat.append(user(prompt, *file_attachments))
                
                response = chat.sample()
                
                # 🔍 LOG: Ver respuesta RAW de Grok Files API
                logger.info(
                    "files_api_raw_response",
                    ticker=ticker,
                    focus=focus[:80],
                    raw_content=str(response.content)[:2000],
                    content_type=type(response.content).__name__
                )
                
                # Parse JSON
                extracted_raw = json.loads(response.content)
                
                # 🔧 NORMALIZACIÓN: Mapear campos alternativos de Grok a nuestro schema
                extracted = self._normalize_grok_extraction_fields(extracted_raw)
                
                logger.info("files_api_extraction_success", 
                           ticker=ticker,
                           focus=focus[:50],
                           warrants=len(extracted.get('warrants', [])),
                           atm=len(extracted.get('atm_offerings', [])),
                           shelfs=len(extracted.get('shelf_registrations', [])),
                           grok_key=key_name)
                
                # Liberar cliente del pool (éxito)
                if self._grok_pool and pool_idx is not None:
                    self._grok_pool.release(pool_idx, success=True)
                
                return extracted
                
            except Exception as e:
                error_str = str(e)
                is_timeout = "deadline" in error_str.lower() or "timeout" in error_str.lower()
                
                # Registrar estadísticas
                if is_timeout:
                    self._stats["timeouts"] += 1
                
                logger.warning("extract_with_files_api_attempt_failed", 
                              ticker=ticker, 
                              focus=focus[:50], 
                              error=error_str,
                              attempt=attempt + 1,
                              max_retries=max_retries,
                              is_timeout=is_timeout,
                              grok_key=key_name)
                
                # Liberar cliente del pool (error)
                if self._grok_pool and pool_idx is not None:
                    self._grok_pool.release(pool_idx, success=False, error=error_str, is_timeout=is_timeout)
                    pool_idx = None  # Reset para siguiente intento
                
                # Limpiar archivos de este intento
                if uploaded_file_ids:
                    await self._cleanup_grok_files(uploaded_file_ids, grok_client)
                    uploaded_file_ids = []
                
                # Retry con backoff exponencial
                if attempt < max_retries - 1:
                    backoff_time = (2 ** attempt) * 10  # 10s, 20s, 40s
                    self._stats["retries"] += 1
                    logger.info("extract_retry_scheduled", 
                               ticker=ticker,
                               backoff_seconds=backoff_time,
                               next_attempt=attempt + 2)
                    await asyncio.sleep(backoff_time)
                else:
                    logger.error("extract_with_files_api_failed_all_retries", 
                                ticker=ticker, 
                                focus=focus[:50], 
                                error=error_str,
                                total_attempts=max_retries)
                    return None
                    
        return None  # Nunca debería llegar aquí
    
    async def _extract_pass_direct_prompt(
        self,
        ticker: str,
        company_name: str,
        filings: List[Dict],
        focus: str,
        parsed_tables: Optional[Dict] = None,
        max_retries: int = 3
    ) -> Optional[Dict]:
        """
        Extracción usando DIRECT PROMPT - Para documentos pequeños (<300KB)
        
        🚀 OPTIMIZACIÓN: Evita el overhead de Files API (~2-3s por archivo)
        Para documentos pequeños, es más rápido incluir el contenido directamente.
        
        CUÁNDO USAR:
        - Total contenido < 300KB
        - Filings pequeños (424B3 típicamente 5-10KB)
        
        MÉTRICAS:
        - Direct prompt: ~8-12s para 3 filings pequeños
        - Files API: ~17-25s para los mismos filings (upload overhead)
        
        Args:
            ticker: Ticker symbol
            company_name: Company name
            filings: Lista de filings para analizar
            focus: Descripción de qué buscar
            parsed_tables: Tablas pre-parseadas (opcional)
            max_retries: Número máximo de reintentos
            
        Returns:
            Dict con datos extraídos
        """
        grok_client = None
        key_name = None
        pool_idx = None
        
        for attempt in range(max_retries):
            try:
                # Obtener cliente del pool
                if self._grok_pool and self._grok_pool.num_keys > 0:
                    grok_client, key_name, pool_idx = await self._grok_pool.get_client()
                    logger.debug("grok_pool_client_acquired_direct", 
                                key_name=key_name, 
                                ticker=ticker,
                                attempt=attempt + 1)
                elif self.grok_api_key:
                    grok_client = Client(api_key=self.grok_api_key, timeout=120)
                    key_name = "default"
                else:
                    logger.error("no_grok_api_key_available")
                    return None
                
                # Construir contenido inline
                filings_content = []
                for f in filings:
                    content = f.get('content', '')
                    # Limpiar HTML básico para reducir tokens
                    content_clean = re.sub(r'<[^>]+>', ' ', content)
                    content_clean = re.sub(r'\s+', ' ', content_clean)[:50000]  # Límite por filing
                    
                    filings_content.append(f"""
--- {f['form_type']} filed on {f['filing_date']} ---
{content_clean}
--- END {f['form_type']} ---
""")
                
                all_content = "\n".join(filings_content)
                
                prompt = f"""You are an EXPERT financial data extraction specialist analyzing SEC EDGAR filings for {company_name} (Ticker: {ticker}).

YOUR MISSION: Extract COMPREHENSIVE dilution data with MAXIMUM detail and accuracy.

THIS IS A FOCUSED ANALYSIS PASS. Your specific task:
**{focus}**

FILINGS PROVIDED ({len(filings)} documents):
{all_content}

RETURN FORMAT (JSON only, no markdown, no explanations):
{{
  "warrants": [...],
  "atm_offerings": [...],
  "shelf_registrations": [...],
  "completed_offerings": [...],
  "s1_offerings": [...],
  "convertible_notes": [...],
  "convertible_preferred": [...],
  "equity_lines": [...]
}}

Return empty arrays [] if nothing found. Do NOT include null values or placeholder objects.
"""
                
                # Llamar a Grok
                try:
                    chat = grok_client.chat.create(model="grok-4-fast", temperature=0.1)
                except:
                    chat = grok_client.chat.create(model="grok-4", temperature=0.1)
                
                chat.append(system("You are a financial data extraction expert. Return ONLY valid JSON."))
                chat.append(user(prompt))
                
                response = chat.sample()
                
                # Parse JSON
                extracted_raw = json.loads(response.content)
                
                # 🔧 NORMALIZACIÓN: Mapear campos alternativos de Grok a nuestro schema
                extracted = self._normalize_grok_extraction_fields(extracted_raw)
                
                logger.info("direct_prompt_extraction_success", 
                           ticker=ticker,
                           focus=focus[:50],
                           warrants=len(extracted.get('warrants', [])),
                           atm=len(extracted.get('atm_offerings', [])),
                           shelfs=len(extracted.get('shelf_registrations', [])),
                           grok_key=key_name)
                
                # Liberar cliente del pool (éxito)
                if self._grok_pool and pool_idx is not None:
                    self._grok_pool.release(pool_idx, success=True)
                
                return extracted
                
            except Exception as e:
                error_str = str(e)
                is_timeout = "deadline" in error_str.lower() or "timeout" in error_str.lower()
                
                logger.warning("direct_prompt_attempt_failed", 
                              ticker=ticker, 
                              error=error_str,
                              attempt=attempt + 1,
                              is_timeout=is_timeout,
                              grok_key=key_name)
                
                # Liberar cliente del pool (error)
                if self._grok_pool and pool_idx is not None:
                    self._grok_pool.release(pool_idx, success=False, error=error_str, is_timeout=is_timeout)
                    pool_idx = None
                
                # Retry con backoff
                if attempt < max_retries - 1:
                    backoff_time = (2 ** attempt) * 5  # 5s, 10s, 20s
                    await asyncio.sleep(backoff_time)
                else:
                    return None
        
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
        Una pasada enfocada de Grok - ELIGE automáticamente el mejor método
        
        OPTIMIZACIÓN AUTOMÁTICA:
        - <300KB total → Direct prompt (más rápido, sin overhead de upload)
        - ≥300KB total → Files API (mejor para documentos grandes)
        
        Args:
            ticker: Ticker symbol
            company_name: Company name
            filings: Lista de TODOS los filings para analizar en esta pasada
            focus: Descripción de qué buscar en esta pasada
            parsed_tables: Tablas pre-parseadas (opcional)
            
        Returns:
            Dict con datos extraídos de esta pasada
        """
        # La decisión de usar direct prompt o files API ahora está en _extract_pass_with_files_api
        return await self._extract_pass_with_files_api(
            ticker, company_name, filings, focus, parsed_tables
        )
    
    def _extract_warrant_type(self, notes: str) -> str:
        """
        Extraer el tipo de warrant de las notes para agrupar duplicados.
        
        Tipos reconocidos: Public, Private, SPA, Pre-Funded, Common, Unknown
        """
        if not notes:
            return "Unknown"
        
        notes_lower = notes.lower()
        
        # Orden importa - más específico primero
        if 'pre-funded' in notes_lower or 'prefunded' in notes_lower:
            return "Pre-Funded"
        if 'spa warrant' in notes_lower or 'securities purchase agreement' in notes_lower:
            return "SPA"
        if 'private' in notes_lower:
            return "Private"
        if 'public' in notes_lower:
            return "Public"
        if 'common warrant' in notes_lower or 'common stock warrant' in notes_lower:
            return "Common"
        
        return "Unknown"
    
    def _deduplicate_warrants(self, warrants: List[Dict]) -> List[Dict]:
        """
        Deduplicar warrants inteligentemente por TIPO + exercise_price.
        
        ESTRATEGIA:
        1. Extraer tipo de warrant (Public, Private, SPA, Pre-Funded, Common)
        2. Agrupar por (tipo, exercise_price)
        3. Para cada grupo, tomar el registro más COMPLETO (más campos con datos)
        4. Si hay empate, tomar el más reciente por issue_date
        
        Esto evita duplicados como:
        - Public Warrants $11.50 (Sep 2024) + Public Warrants $11.50 (Aug 2024)
        """
        # Paso 1: Normalizar todos los warrants
        for w in warrants:
            outstanding = self._normalize_grok_value(w.get('outstanding'), 'number')
            potential = self._normalize_grok_value(w.get('potential_new_shares'), 'number')
            
            if outstanding is None and potential is not None:
                w['outstanding'] = potential
            elif outstanding is not None:
                w['outstanding'] = outstanding
        
        # Paso 2: Agrupar por (tipo, exercise_price)
        groups = {}
        for w in warrants:
            try:
                notes = self._normalize_grok_value(w.get('notes'), 'string') or ''
                warrant_type = self._extract_warrant_type(notes)
                exercise_price = self._safe_get_for_key(w, 'exercise_price', 'number')
                
                # Key: (tipo, exercise_price)
                key = (warrant_type, exercise_price)
                
                if key not in groups:
                    groups[key] = []
                groups[key].append(w)
            except Exception as e:
                logger.warning("warrant_grouping_error", error=str(e))
        
        # Paso 3: Para cada grupo, seleccionar el mejor registro
        unique = []
        for (warrant_type, exercise_price), group in groups.items():
            if len(group) == 1:
                best = group[0]
            else:
                # Calcular "completeness score" para cada warrant
                def completeness_score(w):
                    score = 0
                    if w.get('outstanding'):
                        score += 3
                    if w.get('exercise_price'):
                        score += 2
                    if w.get('expiration_date'):
                        score += 2
                    if w.get('issue_date'):
                        score += 1
                    if w.get('potential_new_shares'):
                        score += 1
                    return score
                
                # Ordenar por completeness (desc) y luego por issue_date (desc, más reciente)
                def sort_key(w):
                    score = completeness_score(w)
                    issue_date = self._safe_get_for_key(w, 'issue_date', 'date') or ''
                    return (score, str(issue_date))
                
                sorted_group = sorted(group, key=sort_key, reverse=True)
                best = sorted_group[0]
                
                # Log para debug
                if len(group) > 2:
                    logger.info("warrant_dedup_merged",
                               warrant_type=warrant_type,
                               exercise_price=str(exercise_price),
                               merged_count=len(group),
                               selected_outstanding=best.get('outstanding'))
            
            unique.append(best)
        
        logger.info("warrant_dedup_result",
                   input_count=len(warrants),
                   output_count=len(unique),
                   types_found=list(set(self._extract_warrant_type(
                       self._normalize_grok_value(w.get('notes'), 'string') or ''
                   ) for w in unique)))
        
        return unique
    
    def _filter_summary_warrants(self, warrants: List[Dict]) -> List[Dict]:
        """
        Filtrar warrants "summary" de 10-Q/10-K para evitar doble conteo.
        
        Los 10-Q/10-K suelen tener tablas resumen tipo "warrants outstanding as of X date"
        que agregan todos los warrants. Estos NO deben sumarse al cálculo de dilución
        porque ya tenemos los warrants detallados por serie de los 424B/8-K.
        
        También detectar warrants históricos que fueron ejercidos o reemplazados.
        """
        filtered = []
        excluded_count = 0
        
        for w in warrants:
            notes_raw = self._normalize_grok_value(w.get('notes'), 'string')
            notes_lower = (notes_raw or '').lower()
            
            # Detectar si es un resumen agregado
            is_summary = (
                ('as of' in notes_lower and 
                ('outstanding warrants' in notes_lower or 
                 'weighted average' in notes_lower or
                  'total outstanding' in notes_lower or
                  'aggregate' in notes_lower)) or
                'no specific series' in notes_lower
            )
            
            # Detectar eventos históricos (no warrants activos)
            is_historical = (
                'cashless exercise' in notes_lower or
                'exercised' in notes_lower.split()[-10:] or  # "was exercised" al final
                'adjustment' in notes_lower or
                'restructuring' in notes_lower or
                'waiver' in notes_lower or
                'amended' in notes_lower and 'exercise price' not in notes_lower
            )
            
            if is_summary or is_historical:
                w['is_summary_row'] = True
                w['exclude_from_dilution'] = True
                excluded_count += 1
                logger.debug("warrant_excluded", 
                           reason="summary" if is_summary else "historical",
                           outstanding=w.get('outstanding'),
                           notes_snippet=notes_lower[:60])
            
            filtered.append(w)
        
        if excluded_count > 0:
            logger.info("warrants_excluded_from_dilution", count=excluded_count)
        
        return filtered
    
    def _impute_missing_exercise_prices(self, warrants: List[Dict]) -> List[Dict]:
        """
        Imputar exercise_price faltantes cuando se puede inferir de otros warrants
        de la misma serie (mismo issue_date, expiration_date, y tipo).
        
        ROBUSTO: Usa _safe_get_for_key para manejar valores de Grok que pueden ser
        dicts anidados en lugar de valores simples.
        """
        # Agrupar por (issue_date, expiration_date, snippet de notes)
        by_key = {}
        for w in warrants:
            try:
                key = (
                    self._safe_get_for_key(w, 'issue_date', 'date'),
                    self._safe_get_for_key(w, 'expiration_date', 'date'),
                    self._to_hashable((self._normalize_grok_value(w.get('notes'), 'string') or '')[:60])
                )
                by_key.setdefault(key, []).append(w)
            except Exception as e:
                logger.warning("impute_grouping_error", error=str(e))
                # Crear key único para no perder el warrant
                by_key.setdefault(('error', id(w), str(e)[:20]), []).append(w)
        
        imputed_count = 0
        for group in by_key.values():
            try:
                # Si al menos uno tiene exercise_price, propágalo a los que no lo tienen
                # Normalizar cada precio y filtrar Nones
                prices = set()
                for w in group:
                    normalized_price = self._normalize_grok_value(w.get('exercise_price'), 'number')
                    if normalized_price is not None:
                        prices.add(self._to_hashable(normalized_price))
                
                if len(prices) == 1:
                    price = list(prices)[0]
                    for w in group:
                        if self._normalize_grok_value(w.get('exercise_price'), 'number') is None:
                            w['exercise_price'] = price
                            if 'imputed_fields' not in w:
                                w['imputed_fields'] = []
                            w['imputed_fields'].append('exercise_price')
                            imputed_count += 1
                            logger.info("exercise_price_imputed",
                                       ticker=w.get('ticker'),
                                       outstanding=w.get('outstanding'),
                                       imputed_price=price,
                                       issue_date=w.get('issue_date'))
            except Exception as e:
                logger.warning("impute_price_error", error=str(e))
        
        if imputed_count > 0:
            logger.info("total_exercise_prices_imputed", count=imputed_count)
        
        return warrants
    
    def _classify_warrant_status(self, warrants: List[Dict], ticker: str) -> List[Dict]:
        """
        Clasificar warrants por su estado actual: Active, Exercised, Replaced, Historical_Summary.
        
        Esto permite al frontend mostrar solo los warrants activos y evitar confusión
        al usuario cuando suma todos los warrants.
        """
        try:
            return self._classify_warrant_status_impl(warrants, ticker)
        except Exception as e:
            logger.error("warrant_classification_failed", ticker=ticker, error=str(e), 
                        action="returning_unclassified_warrants")
            # Si falla la clasificación, devolver warrants con status Active por defecto
            for w in warrants:
                if 'status' not in w:
                    w['status'] = 'Active'
            return warrants
    
    def _classify_warrant_status_impl(self, warrants: List[Dict], ticker: str) -> List[Dict]:
        """Implementación de clasificación de warrants (puede lanzar excepciones)"""
        # Primero, identificar inducement/replacement deals
        inducement_dates = set()
        replacement_notes_keywords = ['inducement', 'replacement', 'in exchange for', 'existing warrants']
        
        for w in warrants:
            # Normalizar notes para evitar errores si es dict
            notes_raw = self._normalize_grok_value(w.get('notes'), 'string')
            notes_lower = (notes_raw or '').lower()
            if any(keyword in notes_lower for keyword in replacement_notes_keywords):
                # Este es un warrant de reemplazo, guardar su fecha (normalizada)
                issue_date = self._safe_get_for_key(w, 'issue_date', 'date')
                if issue_date:
                    inducement_dates.add(issue_date)
        
        # Clasificar cada warrant
        for w in warrants:
            # Normalizar notes para evitar errores si es dict
            notes_raw = self._normalize_grok_value(w.get('notes'), 'string')
            notes_lower = (notes_raw or '').lower()
            
            # 1. Historical Summary (ya detectado)
            if w.get('is_summary_row') or w.get('exclude_from_dilution'):
                w['status'] = 'Historical_Summary'
                continue
            
            # 2. Ejercidos (buscar keywords en notes)
            exercised_keywords = [
                'exercised',
                'fully exercised',
                'exercise of',
                'upon exercise',
                'warrant exercise'
            ]
            # Si el warrant menciona "ejercicio" pero es de tipo "Warrant Exercise" en completed_offerings,
            # probablemente es una nota sobre el ejercicio, no el warrant original
            if any(keyword in notes_lower for keyword in exercised_keywords):
                # Verificar si no es una nota sobre un ejercicio futuro/potencial
                if 'exercise price' not in notes_lower or 'upon exercise' in notes_lower:
                    w['status'] = 'Exercised'
                    continue
            
            # 3. Reemplazados (warrants que fueron sustituidos por inducement)
            issue_date = self._safe_get_for_key(w, 'issue_date', 'date')
            if issue_date:
                # Si hay un inducement DESPUÉS de este warrant, este fue reemplazado
                # Comparar strings de fechas de forma segura
                try:
                    later_inducements = [d for d in inducement_dates if str(d) > str(issue_date)]
                except TypeError:
                    later_inducements = []
                
                if later_inducements and not any(keyword in notes_lower for keyword in replacement_notes_keywords):
                    # Este warrant es ANTERIOR a un inducement y no ES el inducement
                    # Verificar si las notas sugieren que fue reemplazado
                    if 'november 2024' in notes_lower or 'series a' in notes_lower:
                        # Este podría ser uno de los "Existing Warrants" que fueron reemplazados
                        w['status'] = 'Replaced'
                        w['notes'] = (notes_raw or '') + ' [REPLACED by Inducement Warrants]'
                        continue
            
            # 4. Pre-funded con ejercicio mínimo (técnicamente activos pero casi ejercidos)
            exercise_price = self._normalize_grok_value(w.get('exercise_price'), 'number')
            if exercise_price is not None:
                try:
                    if float(exercise_price) <= 0.01:
                        if 'pre-funded' in notes_lower or 'prefunded' in notes_lower:
                            w['status'] = 'Active'  # Pero son casi como shares comunes
                            continue
                except (ValueError, TypeError):
                    pass
            
            # 5. Por defecto: Active
            w['status'] = 'Active'
        
        # Log estadísticas
        status_counts = {}
        for w in warrants:
            status = w.get('status', 'Unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        logger.info("warrant_status_classification",
                   ticker=ticker,
                   total=len(warrants),
                   active=status_counts.get('Active', 0),
                   exercised=status_counts.get('Exercised', 0),
                   replaced=status_counts.get('Replaced', 0),
                   historical_summary=status_counts.get('Historical_Summary', 0))
        
        return warrants
    
    def _classify_shelf_status(self, shelfs: List[Dict], ticker: str) -> List[Dict]:
        """
        Clasificar shelf registrations por su estado: Active o Expired.
        
        Un shelf está expirado si:
        - Tiene expiration_date y esa fecha ya pasó
        """
        from datetime import datetime, timezone
        
        now = datetime.now(timezone.utc)
        
        for s in shelfs:
            exp_date_str = s.get('expiration_date')
            
            if exp_date_str:
                try:
                    # Parse expiration date - puede ser string de fecha o datetime
                    if isinstance(exp_date_str, str):
                        exp_date = datetime.fromisoformat(exp_date_str.replace('Z', '+00:00'))
                    else:
                        # Si ya es datetime/date, convertir a datetime con timezone
                        exp_date = datetime.combine(exp_date_str, datetime.min.time()).replace(tzinfo=timezone.utc)
                    
                    # Asegurar que exp_date tenga timezone
                    if exp_date.tzinfo is None:
                        exp_date = exp_date.replace(tzinfo=timezone.utc)
                    
                    logger.debug("shelf_expiration_check",
                               ticker=ticker,
                               filing_date=s.get('filing_date'),
                               expiration=str(exp_date),
                               now=str(now),
                               is_expired=exp_date < now)
                    
                    if exp_date < now:
                        s['status'] = 'Expired'
                    else:
                        s['status'] = 'Active'
                except Exception as e:
                    # Si no se puede parsear la fecha, asumir Active
                    logger.warning("shelf_date_parse_failed",
                                 ticker=ticker,
                                 exp_date_str=str(exp_date_str),
                                 error=str(e))
                    s['status'] = 'Active'
            else:
                # Sin fecha de expiración, asumir Active
                s['status'] = 'Active'
        
        # Log estadísticas
        active_count = sum(1 for s in shelfs if s.get('status') == 'Active')
        expired_count = sum(1 for s in shelfs if s.get('status') == 'Expired')
        
        logger.info("shelf_status_classification",
                   ticker=ticker,
                   total=len(shelfs),
                   active=active_count,
                   expired=expired_count)
        
        return shelfs
    
    def _classify_atm_status(self, atms: List[Dict], ticker: str) -> List[Dict]:
        """
        Clasificar ATM offerings por su estado: Active, Terminated, Replaced.
        
        Un ATM está:
        - Terminated: si status ya dice "Terminated"
        - Replaced: si status dice "Replaced"
        - Active: por defecto
        """
        for a in atms:
            # El status puede venir ya del LLM
            existing_status = a.get('status', '').lower()
            
            if 'terminated' in existing_status or 'termination' in existing_status:
                a['status'] = 'Terminated'
            elif 'replaced' in existing_status or 'superseded' in existing_status:
                a['status'] = 'Replaced'
            else:
                a['status'] = 'Active'
        
        # Log estadísticas
        status_counts = {}
        for a in atms:
            status = a.get('status', 'Unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        logger.info("atm_status_classification",
                   ticker=ticker,
                   total=len(atms),
                   active=status_counts.get('Active', 0),
                   terminated=status_counts.get('Terminated', 0),
                   replaced=status_counts.get('Replaced', 0))
        
        return atms
    
    def _deduplicate_atm(self, atms: List[Dict], ticker: str = "") -> List[Dict]:
        """
        Deduplicar ATM inteligentemente.
        
        ESTRATEGIA:
        1. DESCARTAR ATMs sin total_capacity ni remaining_capacity (son inútiles para dilución)
        2. Agrupar por placement_agent
        3. Para cada grupo, tomar el registro más COMPLETO y RECIENTE
        """
        # Paso 1: Filtrar ATMs sin datos de capacidad
        atms_with_data = []
        atms_without_data = 0
        
        for a in atms:
            remaining = self._normalize_grok_value(a.get('remaining_capacity'), 'number')
            total = self._normalize_grok_value(a.get('total_capacity'), 'number')
            
            if remaining or total:
                atms_with_data.append(a)
            else:
                atms_without_data += 1
        
        if atms_without_data > 0:
            logger.info("atm_filtered_no_capacity", ticker=ticker, filtered_count=atms_without_data)
        
        # Paso 2: Agrupar por placement_agent
        groups = {}
        for a in atms_with_data:
            agent = self._safe_get_for_key(a, 'placement_agent', 'string') or 'Unknown'
            if agent not in groups:
                groups[agent] = []
            groups[agent].append(a)
        
        # Paso 3: Para cada grupo, seleccionar el mejor
        unique = []
        for agent, group in groups.items():
            if len(group) == 1:
                unique.append(group[0])
            else:
                # Ordenar por completeness y recency
                def score(a):
                    s = 0
                    if a.get('remaining_capacity'):
                        s += 3
                    if a.get('total_capacity'):
                        s += 2
                    if a.get('filing_date'):
                        s += 1
                    return s
                
                sorted_group = sorted(group, key=lambda x: (score(x), str(self._safe_get_for_key(x, 'filing_date', 'date') or '')), reverse=True)
                unique.append(sorted_group[0])
                
                logger.info("atm_dedup_merged",
                           ticker=ticker,
                           agent=agent,
                           merged_count=len(group))
                
        logger.info("atm_deduplication", ticker=ticker, total_input=len(atms), 
                   filtered_no_data=atms_without_data, total_output=len(unique))
        return unique
    
    def _deduplicate_shelfs(self, shelfs: List[Dict], ticker: str = "") -> List[Dict]:
        """
        Deduplicar shelfs inteligentemente.
        
        ESTRATEGIA:
        1. DESCARTAR shelfs sin total_capacity ni remaining_capacity (inútiles para dilución)
        2. Agrupar por registration_statement (S-3, S-1, etc.)
        3. Para cada grupo, tomar el registro más COMPLETO y RECIENTE
        """
        # Paso 1: Filtrar shelfs sin datos de capacidad
        shelfs_with_data = []
        shelfs_without_data = 0
        
        for s in shelfs:
            remaining = self._normalize_grok_value(s.get('remaining_capacity'), 'number')
            total = self._normalize_grok_value(s.get('total_capacity'), 'number')
            
            if remaining or total:
                shelfs_with_data.append(s)
            else:
                shelfs_without_data += 1
        
        if shelfs_without_data > 0:
            logger.info("shelf_filtered_no_capacity", ticker=ticker, filtered_count=shelfs_without_data)
        
        # Paso 2: Agrupar por registration_statement
        groups = {}
        for s in shelfs_with_data:
            reg_stmt = self._safe_get_for_key(s, 'registration_statement', 'string') or 'Unknown'
            if reg_stmt not in groups:
                groups[reg_stmt] = []
            groups[reg_stmt].append(s)
        
        # Paso 3: Para cada grupo, seleccionar el mejor
        unique = []
        for reg_stmt, group in groups.items():
            if len(group) == 1:
                unique.append(group[0])
            else:
                # Ordenar por completeness y recency
                def score(s):
                    sc = 0
                    if s.get('remaining_capacity'):
                        sc += 3
                    if s.get('total_capacity'):
                        sc += 2
                    if s.get('filing_date'):
                        sc += 1
                    if s.get('expiration_date'):
                        sc += 1
                    return sc
                
                sorted_group = sorted(group, key=lambda x: (score(x), str(self._safe_get_for_key(x, 'filing_date', 'date') or '')), reverse=True)
                unique.append(sorted_group[0])
                
                logger.info("shelf_dedup_merged",
                           ticker=ticker,
                           registration=reg_stmt,
                           merged_count=len(group))
                
        logger.info("shelf_deduplication", ticker=ticker, total_input=len(shelfs), 
                   filtered_no_data=shelfs_without_data, total_output=len(unique))
        return unique
    
    def _deduplicate_shelfs_old(self, shelfs: List[Dict]) -> List[Dict]:
        """DEPRECATED - Old deduplication logic"""
        seen = set()
        unique = []
        for s in shelfs:
            try:
                filing_date = self._safe_get_for_key(s, 'filing_date', 'date')
                total_capacity = self._safe_get_for_key(s, 'total_capacity', 'number')
                
                key = (filing_date, total_capacity)
                # Si no tiene filing_date, incluir igual (no descartar datos)
                if not filing_date:
                    unique.append(s)
                elif key not in seen:
                    seen.add(key)
                    unique.append(s)
            except Exception as e:
                logger.warning("shelf_dedup_error", error=str(e))
                unique.append(s)
        return unique
    
    def _deduplicate_completed(self, completed: List[Dict], ticker: str = "") -> List[Dict]:
        """
        Deduplicar completed offerings inteligentemente.
        
        ESTRATEGIA:
        1. Filtrar offerings sin datos útiles (sin shares_issued ni amount_raised)
        2. Agrupar por (offering_type, offering_date, amount_raised)
        3. Para cada grupo, tomar el más completo
        """
        # Paso 1: Filtrar offerings sin datos útiles
        with_data = []
        without_data = 0
        
        for c in completed:
            shares = self._normalize_grok_value(c.get('shares_issued'), 'number')
            amount = self._normalize_grok_value(c.get('amount_raised'), 'number')
            
            if shares or amount:
                with_data.append(c)
            else:
                without_data += 1
        
        if without_data > 0:
            logger.info("completed_filtered_no_data", ticker=ticker, filtered_count=without_data)
        
        # Paso 2: Deduplicar por key más inteligente
        seen = set()
        unique = []
        
        for c in with_data:
            try:
                offering_type = self._safe_get_for_key(c, 'offering_type', 'string') or ''
                offering_date = self._safe_get_for_key(c, 'offering_date', 'date')
                amount = self._safe_get_for_key(c, 'amount_raised', 'number')
                shares = self._safe_get_for_key(c, 'shares_issued', 'number')
                
                # Key más robusta
                key = (offering_type[:30], offering_date, amount or shares)
                
                if key not in seen:
                    seen.add(key)
                    unique.append(c)
            except Exception as e:
                logger.warning("completed_dedup_error", error=str(e))
                unique.append(c)
        
        logger.info("completed_deduplication", ticker=ticker, 
                   input_count=len(completed), output_count=len(unique))
        return unique
    
    def _deduplicate_s1(self, s1_offerings: List[Dict]) -> List[Dict]:
        """
        Deduplicar S-1 offerings por filing_date + deal_size. NO descartar sin fecha.
        
        ROBUSTO: Usa _safe_get_for_key para manejar valores de Grok que pueden ser
        dicts anidados en lugar de valores simples.
        """
        seen = set()
        unique = []
        for s1 in s1_offerings:
            try:
                filing_date = self._safe_get_for_key(s1, 's1_filing_date', 'date')
                final_size = self._safe_get_for_key(s1, 'final_deal_size', 'number')
                anticipated_size = self._safe_get_for_key(s1, 'anticipated_deal_size', 'number')
                deal_size = final_size or anticipated_size
                
                key = (filing_date, deal_size)
                # Si no tiene s1_filing_date, incluir igual (no descartar datos)
                if not filing_date:
                    unique.append(s1)
                elif key not in seen:
                    seen.add(key)
                    unique.append(s1)
            except Exception as e:
                logger.warning("s1_dedup_error", error=str(e))
                unique.append(s1)
        return unique
    
    def _deduplicate_convertible_notes(self, notes: List[Dict]) -> List[Dict]:
        """
        Deduplicar convertible notes con merge inteligente.
        
        Si hay múltiples entries con el mismo issue_date pero campos distintos
        (ej: uno tiene principal, otro tiene maturity_date), los mergea en uno solo.
        
        ROBUSTO: Usa _safe_get_for_key para manejar valores de Grok que pueden ser
        dicts anidados en lugar de valores simples.
        """
        merged_by_date = {}
        no_date_notes = []  # Guardar notes sin issue_date
        
        for n in notes:
            try:
                # Normalizar issue_date para usarlo como key
                issue_date = self._safe_get_for_key(n, 'issue_date', 'date')
                
                if not issue_date:
                    # NO descartar, guardar para incluir al final
                    no_date_notes.append(n)
                    continue
                
                    # Convertir issue_date a string para usar como key de dict
                    issue_date_key = str(issue_date) if issue_date else None
                    
                    if issue_date_key not in merged_by_date:
                        merged_by_date[issue_date_key] = n.copy()
                else:
                    # Merge inteligente: rellenar campos faltantes en base con los del nuevo
                    base = merged_by_date[issue_date_key]
                    
                    for field in [
                        'total_principal_amount',
                        'remaining_principal_amount',
                        'conversion_price',
                        'total_shares_when_converted',
                        'remaining_shares_when_converted',
                        'maturity_date',
                        'convertible_date',
                        'underwriter_agent',
                        'filing_url'
                    ]:
                        if base.get(field) is None and n.get(field) is not None:
                            base[field] = n[field]
                    
                        # Combinar notes de ambas entradas
                            base_notes = self._normalize_grok_value(base.get('notes'), 'string') or ''
                            new_notes = self._normalize_grok_value(n.get('notes'), 'string') or ''
                        if base_notes and new_notes and base_notes != new_notes:
                            # Evitar duplicar texto idéntico
                            combined = ' / '.join([base_notes, new_notes])
                            base['notes'] = combined
                        elif new_notes and not base_notes:
                            base['notes'] = new_notes
                    
                        logger.info("convertible_notes_merged",
                                    issue_date=issue_date_key,
                                base_principal=base.get('total_principal_amount'),
                                merged_fields=[k for k in ['maturity_date', 'conversion_price'] 
                                                if base.get(k) is not None])
            except Exception as e:
                logger.warning("convertible_notes_dedup_error", error=str(e))
                no_date_notes.append(n)
        
        # Incluir tanto los mergeados como los que no tenían issue_date
        return list(merged_by_date.values()) + no_date_notes
    
    def _deduplicate_convertible_preferred(self, preferred: List[Dict]) -> List[Dict]:
        """
        Deduplicar convertible preferred por series + issue_date. NO descartar sin campos.
        
        ROBUSTO: Usa _safe_get_for_key para manejar valores de Grok que pueden ser
        dicts anidados en lugar de valores simples.
        """
        seen = set()
        unique = []
        for p in preferred:
            try:
                series = self._safe_get_for_key(p, 'series', 'string')
                issue_date = self._safe_get_for_key(p, 'issue_date', 'date')
                amount = self._safe_get_for_key(p, 'total_dollar_amount_issued', 'number')
                
                key = (series, issue_date, amount)
            # Si no tiene series o issue_date, incluir igual (no descartar datos)
                if not series or not issue_date:
                    unique.append(p)
                elif key not in seen:
                    seen.add(key)
                    unique.append(p)
            except Exception as e:
                logger.warning("convertible_preferred_dedup_error", error=str(e))
                unique.append(p)
        return unique
    
    def _deduplicate_equity_lines(self, equity_lines: List[Dict]) -> List[Dict]:
        """
        Deduplicar equity lines por agreement_start_date + capacity. NO descartar sin fecha.
        
        ROBUSTO: Usa _safe_get_for_key para manejar valores de Grok que pueden ser
        dicts anidados en lugar de valores simples.
        """
        seen = set()
        unique = []
        for el in equity_lines:
            try:
                start_date = self._safe_get_for_key(el, 'agreement_start_date', 'date')
                capacity = self._safe_get_for_key(el, 'total_capacity', 'number')
                    
                key = (start_date, capacity)
                # Si no tiene agreement_start_date, incluir igual (no descartar datos)
                if not start_date:
                    unique.append(el)
                if key not in seen:
                    seen.add(key)
                    unique.append(el)
            except Exception as e:
                logger.warning("equity_lines_dedup_error", error=str(e))
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
            client = Client(api_key=self.grok_api_key, timeout=120)
            
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
            extracted_data_raw = json.loads(response.content)
            
            # 🔧 NORMALIZACIÓN: Mapear campos alternativos de Grok a nuestro schema
            extracted_data = self._normalize_grok_extraction_fields(extracted_data_raw)
            
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
        
        # Parse warrants (incluyendo metadatos de calidad de datos y status)
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
                imputed_fields=w.get('imputed_fields')
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
        
        # Parse convertible notes (NUEVO)
        from models.sec_dilution_models import ConvertibleNoteModel
        cn_limits = {'underwriter_agent': 255}
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
            for cn in [self._sanitize_field_lengths(x, cn_limits) for x in extracted_data.get('convertible_notes', [])]
        ]
        
        # Parse convertible preferred (NUEVO)
        from models.sec_dilution_models import ConvertiblePreferredModel
        cp_limits = {'series': 50, 'underwriter_agent': 255}
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
            for cp in [self._sanitize_field_lengths(x, cp_limits) for x in extracted_data.get('convertible_preferred', [])]
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

