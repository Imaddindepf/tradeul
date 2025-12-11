"""
XBRL Enricher - Extrae campos adicionales del XBRL completo via edgartools.

Complementa los datos de SEC-API con campos que SEC-API no extrae,
como los componentes detallados de revenue para empresas de seguros.
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class XBRLEnricher:
    """Extrae campos adicionales del XBRL que SEC-API no proporciona."""
    
    # Cache en memoria (24h TTL)
    _cache: Dict[str, Dict] = {}
    _cache_timestamps: Dict[str, datetime] = {}
    _cache_ttl = timedelta(hours=24)
    _executor = ThreadPoolExecutor(max_workers=2)
    
    # Campos principales a extraer - labels exactos del XBRL
    MAIN_FIELDS = {
        # Revenue breakdown
        'Premiums': ('premiums', 'Premiums', 10, 'Revenue'),
        'Investment and other income': ('investment_income', 'Investment & Other Income', 20, 'Revenue'),
        'Products': ('products_revenue', 'Products Revenue', 25, 'Revenue'),
        'Services': ('services_revenue', 'Services Revenue', 26, 'Revenue'),
        'Revenue': ('revenue_total', 'Total Revenue', 50, 'Revenue'),
        
        # Operating costs
        'Medical costs': ('medical_costs', 'Medical Costs', 100, 'Operating Costs'),
        'Cost of Goods and Services Sold': ('cogs', 'Cost of Goods Sold', 105, 'Operating Costs'),
        'Selling, General and Administrative Expense': ('sga', 'SG&A Expenses', 110, 'Operating Costs'),
        'Depreciation and Amortization': ('da', 'D&A', 120, 'Operating Costs'),
        'Costs and Expenses': ('total_costs', 'Total Operating Costs', 150, 'Operating Costs'),
        
        # Operating Income
        'Operating Income': ('operating_income', 'Operating Income', 200, 'Operating Income'),
        'Earnings from Operations': ('operating_income', 'Operating Income', 200, 'Operating Income'),
        
        # Non-Operating
        'Interest Expense': ('interest_expense', 'Interest Expense', 300, 'Non-Operating'),
        
        # Earnings
        'Income Before Tax from Continuing Operations': ('pretax_income', 'Pretax Income', 400, 'Earnings'),
        'Income Tax Expense': ('income_tax', 'Income Tax', 410, 'Earnings'),
        'Net Income': ('net_income', 'Net Income', 500, 'Earnings'),
    }
    
    async def get_income_statement_details(
        self, 
        symbol: str, 
        years: int = 5
    ) -> Optional[Dict[str, Any]]:
        """Obtener income statement completo con componentes de revenue."""
        cache_key = f"income_details:{symbol}:{years}"
        
        if cache_key in self._cache:
            if datetime.now() - self._cache_timestamps.get(cache_key, datetime.min) < self._cache_ttl:
                return self._cache[cache_key]
        
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                self._executor,
                self._extract_income_details,
                symbol,
                years
            )
            
            if result:
                self._cache[cache_key] = result
                self._cache_timestamps[cache_key] = datetime.now()
                logger.info(f"[{symbol}] Extracted {len(result.get('fields', []))} fields")
            
            return result
            
        except Exception as e:
            logger.error(f"[{symbol}] Error: {e}")
            return None
    
    def _extract_income_details(self, symbol: str, years: int) -> Optional[Dict[str, Any]]:
        """Extraer detalles del income statement (síncrono)."""
        try:
            import edgar
            edgar.set_identity("Tradeul API api@tradeul.com")
            
            company = edgar.Company(symbol)
            filings = company.get_filings(form="10-K")
            
            if not filings or len(filings) == 0:
                return None
            
            # Obtener el filing más reciente
            latest = filings[0]
            xbrl = latest.xbrl()
            
            if not xbrl:
                return None
            
            # Obtener income statement
            income = xbrl.statements.income_statement()
            if not income:
                return None
            
            df = income.to_dataframe()
            
            # Identificar columnas de fecha
            date_cols = [c for c in df.columns if '-' in str(c) and any(y in str(c) for y in ['2024', '2023', '2022', '2021', '2020'])]
            date_cols = sorted(date_cols, reverse=True)[:years]
            
            # Extraer períodos (años)
            periods = [str(c)[:4] for c in date_cols]
            
            # Extraer campos
            fields = []
            seen_keys = set()
            
            for idx, row in df.iterrows():
                label = str(row.get('label', '')).strip()
                level = row.get('level', 0)
                
                # Niveles 3-4 son los campos principales
                # Niveles 5+ son desgloses por segmento
                if level > 4:
                    continue
                
                # Buscar en nuestro mapeo
                if label in self.MAIN_FIELDS:
                    key, display_label, order, section = self.MAIN_FIELDS[label]
                    
                    # Extraer valores primero para verificar si tiene datos válidos
                    values = []
                    has_valid_data = False
                    for col in date_cols:
                        val = row.get(col)
                        if val is not None:
                            try:
                                float_val = float(val)
                                if not (float_val != float_val):  # Check for NaN
                                    values.append(float_val)
                                    if float_val != 0:
                                        has_valid_data = True
                                else:
                                    values.append(None)
                            except:
                                values.append(None)
                        else:
                            values.append(None)
                    
                    # Solo procesar si tiene datos válidos y no es duplicado
                    if has_valid_data:
                        # Si ya existe este key, solo actualizar si tiene mejor data
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        
                        fields.append({
                            'key': key,
                            'label': display_label,
                            'values': values,
                            'order': order,
                            'section': section,
                            'data_type': 'monetary',
                            'source': 'edgartools'
                        })
            
            # Ordenar por order
            fields.sort(key=lambda x: x['order'])
            
            return {
                "symbol": symbol,
                "periods": periods,
                "fields": fields,
                "source": "edgartools",
                "filing_date": str(latest.filing_date)
            }
            
        except Exception as e:
            logger.error(f"[{symbol}] _extract_income_details error: {e}")
            return None
    
    def clear_cache(self, symbol: str = None):
        """Limpiar cache."""
        if symbol:
            keys_to_remove = [k for k in self._cache if symbol in k]
            for key in keys_to_remove:
                self._cache.pop(key, None)
                self._cache_timestamps.pop(key, None)
        else:
            self._cache.clear()
            self._cache_timestamps.clear()


# Singleton
_enricher: Optional[XBRLEnricher] = None


def get_xbrl_enricher() -> XBRLEnricher:
    """Obtener instancia del enricher."""
    global _enricher
    if _enricher is None:
        _enricher = XBRLEnricher()
    return _enricher
