"""
Segments Extractor - Extrae datos de segmentos y geografía via dimensiones XBRL.

Usa dimensiones XBRL estándar (US-GAAP) para extraer:
- Segmentos de negocio (StatementBusinessSegmentsAxis)
- Geografía (StatementGeographicalAxis)
- Productos/Servicios (ProductOrServiceAxis)

Funciona automáticamente para cualquier empresa sin hardcodeos.
"""

import re
from typing import Dict, Any, Optional
from datetime import datetime

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class SegmentsExtractor:
    """
    Extractor de segmentos y datos geográficos.
    
    Usa dimensiones XBRL estándar (US-GAAP) para extraer datos
    sin hardcodear patrones específicos por empresa.
    """
    
    # Dimensiones XBRL estándar
    SEGMENT_AXIS = "us-gaap_StatementBusinessSegmentsAxis"
    GEOGRAPHY_AXIS = "srt_StatementGeographicalAxis"
    PRODUCT_AXIS = "srt_ProductOrServiceAxis"
    
    # Keys de dimensión en facts (con guiones)
    DIM_KEYS = {
        "us-gaap_StatementBusinessSegmentsAxis": "dim_us-gaap_StatementBusinessSegmentsAxis",
        "srt_StatementGeographicalAxis": "dim_srt_StatementGeographicalAxis",
        "srt_ProductOrServiceAxis": "dim_srt_ProductOrServiceAxis",
    }
    
    def __init__(self):
        self._edgar = None
    
    def _get_edgar(self):
        """Lazy import de edgar."""
        if self._edgar is None:
            import edgar
            edgar.set_identity("Tradeul API api@tradeul.com")
            self._edgar = edgar
        return self._edgar
    
    def extract(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Extraer datos de segmentos y geografía.
        
        Args:
            symbol: Ticker de la empresa
            
        Returns:
            {
                "symbol": "GOOGL",
                "filing_date": "2025-02-05",
                "period_end": "2024-12-31",
                "segments": {"revenue": {"Google Services": {"2024": 304.9}, ...}},
                "geography": {"revenue": {"United States": {"2024": 170.4}, ...}},
                "products": {"revenue": {"YouTube ads": {"2024": 36.1}, ...}}
            }
        """
        try:
            edgar = self._get_edgar()
            company = edgar.Company(symbol)
            filings = company.get_filings(form="10-K")
            
            if not filings or len(filings) == 0:
                return None
            
            latest = filings[0]
            xbrl = latest.xbrl()
            
            if not xbrl:
                return None
            
            result = {
                "symbol": symbol.upper(),
                "filing_date": str(latest.filing_date),
                "period_end": str(xbrl.period_of_report),
                "segments": self._query_dimension(xbrl, self.SEGMENT_AXIS),
                "geography": self._query_dimension(xbrl, self.GEOGRAPHY_AXIS),
                "products": self._query_dimension(xbrl, self.PRODUCT_AXIS),
            }
            
            logger.info(
                f"[{symbol}] Segments: {len(result['segments'].get('revenue', {}))} segments, "
                f"{len(result['geography'].get('revenue', {}))} regions"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[{symbol}] Segments extraction error: {e}")
            return None
    
    def _query_dimension(self, xbrl, axis: str) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        Consultar facts por dimensión XBRL.
        
        Returns:
            {
                "revenue": {"Google Services": {"2024": 304.9, "2023": 272.5}},
                "operating_income": {"Google Services": {"2024": 123.4}}
            }
        """
        try:
            facts = xbrl.query().by_dimension(axis).execute()
        except Exception as e:
            logger.debug(f"Dimension query error for {axis}: {e}")
            return {}
        
        if not facts:
            return {}
        
        dim_key = self.DIM_KEYS.get(axis, f"dim_{axis.replace('_', '-')}")
        
        result = {
            "revenue": {},
            "operating_income": {},
        }
        
        for fact in facts:
            concept = fact.get("concept", "")
            member = fact.get(dim_key, "")
            value = fact.get("numeric_value")
            period_end = fact.get("period_end", "")
            
            if not member or value is None or not period_end:
                continue
            
            # Solo datos anuales (12 meses)
            period_start = fact.get("period_start", "")
            if period_start and period_end:
                try:
                    start = datetime.strptime(period_start, "%Y-%m-%d")
                    end = datetime.strptime(period_end, "%Y-%m-%d")
                    days = (end - start).days
                    if days < 350:
                        continue
                except:
                    pass
            
            year = period_end[:4]
            name = self._clean_member_name(member)
            
            # Clasificar por tipo
            concept_lower = concept.lower()
            if "revenue" in concept_lower or "netsales" in concept_lower or "sales" in concept_lower:
                category = "revenue"
            elif "operatingincome" in concept_lower or "operatingloss" in concept_lower:
                category = "operating_income"
            else:
                continue
            
            # Guardar (en billones)
            if name not in result[category]:
                result[category][name] = {}
            
            current = result[category][name].get(year, 0)
            new_val = round(value / 1e9, 2)
            if abs(new_val) > abs(current):
                result[category][name][year] = new_val
        
        return result
    
    def _clean_member_name(self, member: str) -> str:
        """Limpiar nombre de miembro XBRL."""
        if ":" in member:
            member = member.split(":")[-1]
        
        if member.endswith("Member"):
            member = member[:-6]
        
        # CamelCase a espacios
        name = re.sub(r'([A-Z])', r' \1', member).strip()
        return name

