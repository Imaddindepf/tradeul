"""
Edgar Service - Servicio principal para extracción de datos via edgartools.

Este servicio orquesta la extracción, cache y corrección de datos financieros.
Complementa los datos de SEC-API con información más detallada y corregida.

Uso:
    service = EdgarService()
    
    # Obtener datos enriquecidos
    enrichment = await service.get_enrichment("UNH")
    
    # Aplicar correcciones a datos de SEC-API
    corrections = await service.correct_sec_api_data(
        symbol="UNH",
        sec_api_fields=income_fields,
        periods=periods
    )
"""

import asyncio
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from shared.utils.logger import get_logger
from .models import (
    EnrichmentResult, 
    CompanyInfo,
    CorrectionResult,
)
from .cache import EdgarCache, get_edgar_cache
from .extractors import IncomeStatementExtractor, SegmentsExtractor
from .corrections import DataCorrector

logger = get_logger(__name__)


class EdgarService:
    """
    Servicio principal de Edgar.
    
    Proporciona:
    - Extracción de datos de income statement
    - Cache de dos niveles (memoria + Redis)
    - Corrección de datos incorrectos de SEC-API
    - Información de empresas (SIC code, industria)
    """
    
    def __init__(self, redis_client=None):
        self._cache = get_edgar_cache(redis_client)
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._income_extractor = IncomeStatementExtractor()
        self._segments_extractor = SegmentsExtractor()
        self._corrector = DataCorrector()
        self._company_cache: Dict[str, CompanyInfo] = {}
    
    # =========================================================================
    # Enrichment API
    # =========================================================================
    
    async def get_enrichment(
        self, 
        symbol: str,
        max_years: int = 15,
        use_cache: bool = True
    ) -> EnrichmentResult:
        """
        Obtener datos enriquecidos para un símbolo.
        
        Args:
            symbol: Ticker de la empresa
            max_years: Máximo de años históricos
            use_cache: Usar cache si disponible
            
        Returns:
            EnrichmentResult con campos extraídos
        """
        symbol = symbol.upper()
        
        # Intentar cache
        if use_cache:
            cached = await self._cache.get_enrichment(symbol)
            if cached:
                logger.debug(f"[{symbol}] Using cached enrichment")
                return EnrichmentResult(**cached)
        
        # Extraer datos (síncrono en thread pool)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            self._income_extractor.extract,
            symbol,
            max_years
        )
        
        # Guardar en cache
        if not result.errors:
            await self._cache.set_enrichment(
                symbol,
                result.model_dump(),
                ttl=timedelta(hours=24)
            )
        
        return result
    
    async def get_enrichment_values(
        self,
        symbol: str,
        periods: List[str]
    ) -> Dict[str, List[Optional[float]]]:
        """
        Obtener valores de enriquecimiento alineados con períodos específicos.
        
        Args:
            symbol: Ticker
            periods: Lista de años a alinear
            
        Returns:
            Dict con key -> valores alineados
        """
        enrichment = await self.get_enrichment(symbol, max_years=len(periods))
        
        result = {}
        for key, field in enrichment.fields.items():
            # Alinear valores con los períodos solicitados
            aligned = []
            for period in periods:
                try:
                    idx = enrichment.periods.index(period)
                    aligned.append(field.values[idx] if idx < len(field.values) else None)
                except ValueError:
                    aligned.append(None)
            result[key] = aligned
        
        return result
    
    # =========================================================================
    # Segments API
    # =========================================================================
    
    async def get_segments(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Obtener datos de segmentos y geografía.
        
        Args:
            symbol: Ticker
            
        Returns:
            {
                "symbol": "GOOGL",
                "filing_date": "2025-02-05",
                "segments": {"revenue": {...}, "operating_income": {...}},
                "geography": {"revenue": {...}},
                "products": {"revenue": {...}}
            }
        """
        symbol = symbol.upper()
        
        # Ejecutar en thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._segments_extractor.extract,
            symbol
        )
    
    # =========================================================================
    # Corrections API
    # =========================================================================
    
    async def correct_sec_api_data(
        self,
        symbol: str,
        sec_api_fields: List[Dict],
        periods: List[str]
    ) -> List[CorrectionResult]:
        """
        Corregir datos de SEC-API usando edgartools.
        
        Modifica sec_api_fields in-place si encuentra errores.
        
        Args:
            symbol: Ticker
            sec_api_fields: Lista de campos de SEC-API (se modifican)
            periods: Períodos de los datos
            
        Returns:
            Lista de correcciones aplicadas
        """
        enrichment = await self.get_enrichment(symbol, max_years=len(periods))
        
        if enrichment.errors:
            logger.warning(f"[{symbol}] Enrichment errors: {enrichment.errors}")
            return []
        
        return self._corrector.apply_corrections(
            sec_api_fields,
            enrichment,
            periods
        )
    
    # =========================================================================
    # Company Info API
    # =========================================================================
    
    async def get_company_info(self, symbol: str) -> CompanyInfo:
        """
        Obtener información de la empresa.
        
        Args:
            symbol: Ticker
            
        Returns:
            CompanyInfo con SIC, industria, etc.
        """
        symbol = symbol.upper()
        
        # Check cache
        if symbol in self._company_cache:
            return self._company_cache[symbol]
        
        # Extraer de edgar
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            self._executor,
            self._fetch_company_info,
            symbol
        )
        
        self._company_cache[symbol] = info
        return info
    
    def _fetch_company_info(self, symbol: str) -> CompanyInfo:
        """Fetch company info (síncrono)."""
        try:
            import edgar
            edgar.set_identity("Tradeul API api@tradeul.com")
            
            company = edgar.Company(symbol)
            
            return CompanyInfo(
                symbol=symbol,
                name=company.name,
                cik=company.cik,
                sic=int(company.sic) if company.sic else None,
            )
        except Exception as e:
            logger.error(f"[{symbol}] Failed to fetch company info: {e}")
            return CompanyInfo(symbol=symbol)
    
    # =========================================================================
    # Cache Management
    # =========================================================================
    
    async def invalidate_cache(self, symbol: str = None) -> int:
        """
        Invalidar cache.
        
        Args:
            symbol: Ticker específico o None para todo
            
        Returns:
            Número de entradas invalidadas
        """
        if symbol:
            symbol = symbol.upper()
            self._company_cache.pop(symbol, None)
            return await self._cache.invalidate(symbol)
        else:
            self._company_cache.clear()
            self._cache._memory.clear()
            return -1  # Todo invalidado
    
    def cache_stats(self) -> Dict[str, Any]:
        """Obtener estadísticas del cache."""
        return self._cache.stats()


# Singleton global
_service: Optional[EdgarService] = None


def get_edgar_service(redis_client=None) -> EdgarService:
    """Obtener instancia del servicio."""
    global _service
    if _service is None:
        _service = EdgarService(redis_client)
    return _service

