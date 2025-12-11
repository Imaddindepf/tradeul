"""
Income Statement Extractor - Extrae datos del Income Statement via edgartools.

Este extractor procesa múltiples 10-K filings para obtener datos históricos
completos de campos que SEC-API no extrae correctamente.
"""

import re
from typing import Dict, List, Optional, Any
from datetime import datetime

from shared.utils.logger import get_logger
from ..models import (
    FinancialField, 
    EnrichmentResult, 
    DataType,
    INCOME_LABEL_TO_MAPPING,
)

logger = get_logger(__name__)


class IncomeStatementExtractor:
    """
    Extractor de Income Statement.
    
    Procesa múltiples filings 10-K para extraer:
    - Campos que SEC-API no captura
    - Valores históricos completos
    - Correcciones de datos incorrectos
    
    Uso:
        extractor = IncomeStatementExtractor()
        result = extractor.extract("UNH", max_years=15)
    """
    
    # Labels XBRL que queremos extraer (SEC-API no los captura bien)
    TARGET_LABELS = {
        # Revenue breakdown
        'Revenue',                           # Total revenue (para correcciones)
        'Premiums',                          # Insurance premiums
        'Investment and other income',       # Investment income
        'Products',                          # Products revenue
        'Services',                          # Services revenue
        
        # Costs
        'Medical costs',
        'Cost of Goods and Services Sold',
        'Selling, General and Administrative Expense',
        'Depreciation and Amortization',
        'Costs and Expenses',
        
        # Operating
        'Operating Income',
        'Earnings from Operations',
        
        # Non-Operating
        'Interest Expense',
        
        # Earnings
        'Income Before Tax from Continuing Operations',
        'Income Tax Expense',
        'Net Income',
    }
    
    # Niveles de indentación máximos a considerar (evita datos de segmentos)
    MAX_LEVEL = 4
    
    def __init__(self):
        self._edgar = None
    
    def _get_edgar(self):
        """Lazy import de edgar."""
        if self._edgar is None:
            import edgar
            edgar.set_identity("Tradeul API api@tradeul.com")
            self._edgar = edgar
        return self._edgar
    
    def extract(self, symbol: str, max_years: int = 15) -> EnrichmentResult:
        """
        Extraer datos del Income Statement.
        
        Args:
            symbol: Ticker de la empresa
            max_years: Máximo de años a extraer
            
        Returns:
            EnrichmentResult con los campos extraídos
        """
        start_time = datetime.utcnow()
        result = EnrichmentResult(symbol=symbol.upper())
        
        try:
            edgar = self._get_edgar()
            company = edgar.Company(symbol)
            filings = company.get_filings(form="10-K")
            
            if not filings or len(filings) == 0:
                result.errors.append("No 10-K filings found")
                return result
            
            # Diccionario para acumular datos: key -> {year: value}
            all_data: Dict[str, Dict[str, float]] = {}
            all_periods: set = set()
            
            # Procesar todos los filings disponibles
            for i in range(len(filings)):
                try:
                    self._process_filing(filings[i], all_data, all_periods)
                except Exception as e:
                    result.errors.append(f"Filing {i}: {str(e)}")
                    continue
            
            # Convertir a campos
            result.filings_processed = min(len(filings), len(all_periods) // 3 + 1)
            result.periods = sorted(all_periods, reverse=True)[:max_years]
            
            for key, year_values in all_data.items():
                field = self._create_field(key, year_values, result.periods)
                if field and any(v is not None for v in field.values):
                    result.fields[key] = field
            
            # Tiempo de extracción
            result.extraction_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            logger.info(
                f"[{symbol}] Extracted {len(result.fields)} fields, "
                f"{len(result.periods)} periods in {result.extraction_time_ms:.0f}ms"
            )
            
        except Exception as e:
            result.errors.append(str(e))
            logger.error(f"[{symbol}] Extraction error: {e}")
        
        return result
    
    def _process_filing(
        self, 
        filing, 
        all_data: Dict[str, Dict[str, float]],
        all_periods: set
    ) -> None:
        """Procesar un filing individual."""
        xbrl = filing.xbrl()
        if not xbrl:
            return
        
        income = xbrl.statements.income_statement()
        if not income:
            return
        
        df = income.to_dataframe()
        
        # Obtener columnas de fecha
        date_cols = [c for c in df.columns if re.match(r'\d{4}-\d{2}-\d{2}', str(c))]
        
        for date_col in date_cols:
            year = str(date_col)[:4]
            all_periods.add(year)
            
            for idx, row in df.iterrows():
                self._process_row(row, date_col, year, all_data)
    
    def _process_row(
        self,
        row,
        date_col: str,
        year: str,
        all_data: Dict[str, Dict[str, float]]
    ) -> None:
        """Procesar una fila del dataframe."""
        label = str(row.get('label', '')).strip()
        level = row.get('level', 0)
        
        # Solo campos principales (no segmentos)
        if level > self.MAX_LEVEL:
            return
        
        # Solo labels que nos interesan
        if label not in self.TARGET_LABELS:
            return
        
        # Obtener valor
        val = row.get(date_col)
        if val is None:
            return
        
        try:
            float_val = float(val)
            # Validar: no NaN, no 0
            if float_val != float_val or float_val == 0:
                return
        except (ValueError, TypeError):
            return
        
        # Obtener key del mapeo
        mapping = INCOME_LABEL_TO_MAPPING.get(label)
        if not mapping:
            # Usar label como key si no hay mapeo
            key = label.lower().replace(' ', '_').replace(',', '')
        else:
            key = mapping.key
        
        # Guardar valor (prioridad a datos más recientes)
        if key not in all_data:
            all_data[key] = {}
        if year not in all_data[key]:
            all_data[key][year] = float_val
    
    def _create_field(
        self,
        key: str,
        year_values: Dict[str, float],
        periods: List[str]
    ) -> Optional[FinancialField]:
        """Crear un FinancialField a partir de los datos."""
        # Buscar mapeo
        mapping = None
        for m in INCOME_LABEL_TO_MAPPING.values():
            if m.key == key:
                mapping = m
                break
        
        # Alinear valores con períodos
        values = [year_values.get(year) for year in periods]
        
        if mapping:
            return FinancialField(
                key=key,
                label=mapping.label,
                values=values,
                data_type=mapping.data_type,
                section=mapping.section,
                order=mapping.order,
                indent=mapping.indent,
                is_subtotal=mapping.is_subtotal,
                xbrl_concept=mapping.xbrl_label,
            )
        else:
            # Campo sin mapeo definido
            return FinancialField(
                key=key,
                label=key.replace('_', ' ').title(),
                values=values,
                section="Other",
            )

