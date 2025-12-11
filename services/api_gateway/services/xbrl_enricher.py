"""
XBRL Enricher - Complementa datos de SEC-API con campos adicionales via edgartools.

SEC-API extrae los campos principales (Revenue, Net Income, EPS, etc.)
edgartools extrae campos que SEC-API no proporciona:
- Componentes de revenue (Investment Income, Products/Services breakdown)
- Solo para años con XBRL estructurado disponible (~2010+)

NO intenta replicar toda la historia - solo enriquece donde hay datos.
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import re

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class XBRLEnricher:
    """
    Enriquece datos financieros con campos adicionales del XBRL.
    
    Diseño:
    - Procesa TODOS los 10-K disponibles automáticamente
    - Extrae campos que SEC-API no proporciona
    - Cache de 24h para evitar reprocesar
    """
    
    _cache: Dict[str, Dict] = {}
    _cache_timestamps: Dict[str, datetime] = {}
    _cache_ttl = timedelta(hours=24)
    _executor = ThreadPoolExecutor(max_workers=2)
    
    # Campos a extraer - labels exactos del XBRL que SEC-API no captura o extrae mal
    ENRICHMENT_FIELDS = {
        # Revenue breakdown
        'Investment and other income': ('investment_income', 'Investment & Other Income', 20, 'Revenue'),
        'Products': ('products_revenue', 'Products Revenue', 25, 'Revenue'),
        'Services': ('services_revenue', 'Services Revenue', 26, 'Revenue'),
        # Revenue total - SEC-API a veces extrae Product Revenue en lugar del total
        'Revenue': ('revenue_corrected', 'Revenue (Corrected)', 50, 'Revenue'),
    }
    
    async def get_enrichment_fields(
        self, 
        symbol: str, 
        target_periods: List[str]
    ) -> Dict[str, List[Optional[float]]]:
        """
        Obtener campos adicionales alineados con los períodos de SEC-API.
        
        Args:
            symbol: Ticker
            target_periods: Lista de años de SEC-API ["2024", "2023", ...]
            
        Returns:
            {
                "investment_income": [5.2B, 4.1B, 2.0B, None, None, ...],
                "products_revenue": [50.2B, 42.6B, ...],
                ...
            }
        """
        cache_key = f"enrichment:{symbol}"
        
        # Check cache
        if cache_key in self._cache:
            if datetime.now() - self._cache_timestamps.get(cache_key, datetime.min) < self._cache_ttl:
                cached = self._cache[cache_key]
                return self._align_to_periods(cached, target_periods)
        
        # Extraer datos
        loop = asyncio.get_event_loop()
        try:
            raw_data = await loop.run_in_executor(
                self._executor,
                self._extract_enrichment_fields,
                symbol
            )
            
            if raw_data:
                self._cache[cache_key] = raw_data
                self._cache_timestamps[cache_key] = datetime.now()
                years_extracted = len(set(y for field_data in raw_data.values() for y in field_data.keys()))
                logger.info(f"[{symbol}] Enrichment: {len(raw_data)} fields, {years_extracted} years")
                return self._align_to_periods(raw_data, target_periods)
            
            return {}
            
        except Exception as e:
            logger.error(f"[{symbol}] Enrichment error: {e}")
            return {}
    
    def _extract_enrichment_fields(self, symbol: str) -> Dict[str, Dict[str, float]]:
        """
        Extraer campos adicionales de TODOS los 10-K disponibles.
        
        Returns:
            {
                "investment_income": {"2024": 5.2e9, "2023": 4.1e9, ...},
                "products_revenue": {"2024": 50.2e9, ...},
                ...
            }
        """
        try:
            import edgar
            edgar.set_identity("Tradeul API api@tradeul.com")
            
            company = edgar.Company(symbol)
            filings = company.get_filings(form="10-K")
            
            if not filings or len(filings) == 0:
                return {}
            
            result = {}  # key -> {year: value}
            
            # Procesar todos los filings disponibles
            for i in range(len(filings)):
                try:
                    filing = filings[i]
                    xbrl = filing.xbrl()
                    
                    if not xbrl:
                        continue
                    
                    income = xbrl.statements.income_statement()
                    if not income:
                        continue
                    
                    df = income.to_dataframe()
                    
                    # Obtener columnas de fecha
                    date_cols = [c for c in df.columns if re.match(r'\d{4}-\d{2}-\d{2}', str(c))]
                    
                    for date_col in date_cols:
                        year = str(date_col)[:4]
                        
                        for idx, row in df.iterrows():
                            label = str(row.get('label', '')).strip()
                            level = row.get('level', 0)
                            
                            # Solo campos principales (no segmentos)
                            if level > 4:
                                continue
                            
                            if label in self.ENRICHMENT_FIELDS:
                                key = self.ENRICHMENT_FIELDS[label][0]
                                
                                val = row.get(date_col)
                                if val is not None:
                                    try:
                                        float_val = float(val)
                                        # Validar: no NaN, no 0
                                        if float_val == float_val and float_val != 0:
                                            if key not in result:
                                                result[key] = {}
                                            # Prioridad a datos más recientes
                                            if year not in result[key]:
                                                result[key][year] = float_val
                                    except:
                                        pass
                                        
                except Exception as e:
                    # Si falla un filing, continuar con el siguiente
                    continue
            
            return result
            
        except Exception as e:
            logger.error(f"[{symbol}] _extract_enrichment_fields error: {e}")
            return {}
    
    def _align_to_periods(
        self, 
        raw_data: Dict[str, Dict[str, float]], 
        target_periods: List[str]
    ) -> Dict[str, List[Optional[float]]]:
        """Alinear datos extraídos con los períodos objetivo."""
        result = {}
        
        for key, year_values in raw_data.items():
            aligned = []
            for period in target_periods:
                aligned.append(year_values.get(period))
            result[key] = aligned
        
        return result
    
    def clear_cache(self, symbol: str = None):
        """Limpiar cache."""
        if symbol:
            keys_to_remove = [k for k in self._cache if symbol.upper() in k]
            for key in keys_to_remove:
                self._cache.pop(key, None)
                self._cache_timestamps.pop(key, None)
        else:
            self._cache.clear()
            self._cache_timestamps.clear()


# Singleton
_enricher: Optional[XBRLEnricher] = None


def get_xbrl_enricher() -> XBRLEnricher:
    global _enricher
    if _enricher is None:
        _enricher = XBRLEnricher()
    return _enricher
