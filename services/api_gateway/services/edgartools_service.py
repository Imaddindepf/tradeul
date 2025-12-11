"""
EdgarTools Service - Datos de segmentos y geografía via XBRL

Usa dimensiones XBRL estándar (US-GAAP) para extraer:
- Segmentos de negocio (StatementBusinessSegmentsAxis)
- Geografía (StatementGeographicalAxis)
- Productos/Servicios (ProductOrServiceAxis)

Funciona automáticamente para cualquier empresa sin hardcodeos.
"""

import os
import asyncio
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Lazy import
_edgar = None


def _get_edgar():
    """Obtener módulo edgar (lazy import)."""
    global _edgar
    if _edgar is None:
        try:
            import edgar
            edgar.set_identity("Tradeul API api@tradeul.com")
            _edgar = edgar
        except ImportError:
            logger.warning("edgartools_not_installed")
            return None
    return _edgar


class EdgarToolsService:
    """
    Extrae datos de segmentos y geografía usando dimensiones XBRL estándar.
    """
    
    # Dimensiones XBRL estándar (US-GAAP)
    SEGMENT_AXIS = "us-gaap_StatementBusinessSegmentsAxis"
    GEOGRAPHY_AXIS = "srt_StatementGeographicalAxis"
    PRODUCT_AXIS = "srt_ProductOrServiceAxis"
    
    # Cache en memoria
    _cache: Dict[str, Dict] = {}
    _cache_timestamps: Dict[str, datetime] = {}
    _cache_ttl = timedelta(hours=24)
    
    # Thread pool para operaciones síncronas
    _executor = ThreadPoolExecutor(max_workers=2)
    
    async def get_segments(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Obtener datos de segmentos y geografía.
        
        Returns:
            {
                "symbol": "GOOGL",
                "filing_date": "2025-02-05",
                "segments": {"Google Services": {"2024": 304.9B, ...}, ...},
                "geography": {"United States": {"2024": 170.4B, ...}, ...},
                "products": {"YouTube ads": {"2024": 36.1B, ...}, ...}
            }
        """
        # Check cache
        cache_key = f"segments:{symbol}"
        if cache_key in self._cache:
            if datetime.now() - self._cache_timestamps.get(cache_key, datetime.min) < self._cache_ttl:
                return self._cache[cache_key]
        
        # Ejecutar en thread pool (edgartools es síncrono)
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                self._executor,
                self._extract_segments,
                symbol
            )
            
            if result:
                self._cache[cache_key] = result
                self._cache_timestamps[cache_key] = datetime.now()
            
            return result
            
        except Exception as e:
            logger.error("edgartools_error", symbol=symbol, error=str(e))
            return None
    
    def _extract_segments(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Extraer segmentos usando dimensiones XBRL (síncrono)."""
        edgar = _get_edgar()
        if not edgar:
            return None
        
        try:
            company = edgar.Company(symbol)
            filings = company.get_filings(form="10-K")
            
            if not filings or len(filings) == 0:
                return None
            
            latest = filings[0]
            xbrl = latest.xbrl()
            
            if not xbrl:
                return None
            
            result = {
                "symbol": symbol,
                "filing_date": str(latest.filing_date),
                "period_end": str(xbrl.period_of_report),
                "segments": self._query_dimension(xbrl, self.SEGMENT_AXIS),
                "geography": self._query_dimension(xbrl, self.GEOGRAPHY_AXIS),
                "products": self._query_dimension(xbrl, self.PRODUCT_AXIS),
            }
            
            return result
            
        except Exception as e:
            logger.error("extract_error", symbol=symbol, error=str(e))
            return None
    
    def _query_dimension(self, xbrl, axis: str) -> Dict[str, Dict[str, float]]:
        """
        Consultar facts por dimensión XBRL.
        
        Returns:
            {
                "revenue": {"Google Services": {"2024": 304.9, "2023": 272.5}, ...},
                "operating_income": {...}
            }
        """
        try:
            facts = xbrl.query().by_dimension(axis).execute()
        except Exception:
            return {}
        
        result = {
            "revenue": {},
            "operating_income": {},
        }
        
        for fact in facts:
            concept = fact.get("concept", "")
            dim_key = f"dim_{axis}"
            member = fact.get(dim_key, "")
            value = fact.get("numeric_value")
            period_end = fact.get("period_end", "")
            
            if not member or not value or not period_end:
                continue
            
            # Extraer año del período
            year = period_end[:4]
            
            # Limpiar nombre del miembro
            name = self._clean_member_name(member)
            
            # Clasificar por tipo de concepto
            concept_lower = concept.lower()
            
            if "revenue" in concept_lower or "netsales" in concept_lower:
                category = "revenue"
            elif "operatingincome" in concept_lower or "operatingloss" in concept_lower:
                category = "operating_income"
            else:
                continue
            
            # Guardar valor (en billones para legibilidad)
            if name not in result[category]:
                result[category][name] = {}
            
            result[category][name][year] = round(value / 1e9, 2)
        
        return result
    
    def _clean_member_name(self, member: str) -> str:
        """Limpiar nombre de miembro XBRL para display."""
        # Quitar prefijo (goog:, us-gaap:, etc.)
        if ":" in member:
            member = member.split(":")[-1]
        
        # Quitar sufijo "Member"
        if member.endswith("Member"):
            member = member[:-6]
        
        # Convertir CamelCase a espacios
        import re
        name = re.sub(r'([A-Z])', r' \1', member).strip()
        
        return name
    
    def clear_cache(self, symbol: str = None):
        """Limpiar cache."""
        if symbol:
            key = f"segments:{symbol}"
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
        else:
            self._cache.clear()
            self._cache_timestamps.clear()


# Singleton
_service: Optional[EdgarToolsService] = None


def get_edgartools_service() -> EdgarToolsService:
    """Obtener instancia del servicio."""
    global _service
    if _service is None:
        _service = EdgarToolsService()
    return _service
