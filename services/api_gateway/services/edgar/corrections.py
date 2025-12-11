"""
Edgar Corrections - Correcciones de datos incorrectos de SEC-API.

SEC-API a veces extrae campos incorrectos o valores erróneos.
Este módulo detecta y corrige estos problemas usando datos de edgartools.
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from shared.utils.logger import get_logger
from .models import CorrectionResult, EnrichmentResult

logger = get_logger(__name__)


@dataclass
class CorrectionRule:
    """Regla de corrección."""
    field_key: str
    description: str
    threshold: float  # Ratio mínimo para considerar incorrecto
    
    def should_correct(self, original: float, corrected: float) -> bool:
        """Determinar si debe corregirse."""
        if original is None or corrected is None:
            return False
        if corrected == 0:
            return False
        return original < corrected * self.threshold


# Reglas de corrección conocidas
CORRECTION_RULES = [
    CorrectionRule(
        field_key="revenue",
        description="SEC-API extrae Product Revenue en lugar de Total Revenue para insurance companies",
        threshold=0.5,  # Si es menos del 50%, corregir
    ),
]


class DataCorrector:
    """
    Corrector de datos financieros.
    
    Detecta y corrige inconsistencias entre SEC-API y edgartools.
    
    Uso:
        corrector = DataCorrector()
        corrections = corrector.apply_corrections(
            sec_api_fields,
            edgartools_enrichment,
            periods
        )
    """
    
    def __init__(self, rules: List[CorrectionRule] = None):
        self.rules = rules or CORRECTION_RULES
    
    def apply_corrections(
        self,
        sec_api_fields: List[Dict],
        enrichment: EnrichmentResult,
        periods: List[str]
    ) -> List[CorrectionResult]:
        """
        Aplicar correcciones a los datos de SEC-API.
        
        Args:
            sec_api_fields: Lista de campos de SEC-API (se modifican in-place)
            enrichment: Datos de enriquecimiento de edgartools
            periods: Lista de períodos
            
        Returns:
            Lista de correcciones aplicadas
        """
        corrections = []
        
        for rule in self.rules:
            correction = self._apply_rule(
                rule, 
                sec_api_fields, 
                enrichment, 
                periods
            )
            if correction:
                corrections.append(correction)
        
        return corrections
    
    def _apply_rule(
        self,
        rule: CorrectionRule,
        sec_api_fields: List[Dict],
        enrichment: EnrichmentResult,
        periods: List[str]
    ) -> Optional[CorrectionResult]:
        """Aplicar una regla de corrección."""
        # Buscar campo en SEC-API
        sec_field = next(
            (f for f in sec_api_fields if f.get('key') == rule.field_key), 
            None
        )
        if not sec_field:
            return None
        
        # Buscar campo corregido en enrichment
        # Para revenue, usamos revenue_total de edgartools
        edgartools_key = f"{rule.field_key}_total" if rule.field_key == "revenue" else rule.field_key
        
        if edgartools_key not in enrichment.fields:
            return None
        
        edgartools_field = enrichment.fields[edgartools_key]
        
        # Alinear valores con períodos
        original_values = sec_field.get('values', [])
        corrected_values = self._align_values(
            edgartools_field.values,
            enrichment.periods,
            periods
        )
        
        # Detectar y aplicar correcciones
        periods_corrected = []
        new_values = list(original_values)
        
        for i, period in enumerate(periods):
            if i >= len(original_values) or i >= len(corrected_values):
                continue
            
            orig = original_values[i]
            corr = corrected_values[i]
            
            if rule.should_correct(orig, corr):
                new_values[i] = corr
                periods_corrected.append(period)
        
        if not periods_corrected:
            return None
        
        # Aplicar corrección
        sec_field['values'] = new_values
        sec_field['corrected'] = True
        sec_field['correction_source'] = 'edgartools'
        
        logger.info(
            f"Corrected {rule.field_key} for periods: {periods_corrected}. "
            f"Reason: {rule.description}"
        )
        
        return CorrectionResult(
            field_key=rule.field_key,
            original_values=original_values,
            corrected_values=new_values,
            reason=rule.description,
            periods_affected=periods_corrected
        )
    
    def _align_values(
        self,
        source_values: List[Optional[float]],
        source_periods: List[str],
        target_periods: List[str]
    ) -> List[Optional[float]]:
        """Alinear valores de source a target periods."""
        # Crear mapeo period -> value
        period_to_value = {}
        for i, period in enumerate(source_periods):
            if i < len(source_values):
                period_to_value[period] = source_values[i]
        
        # Alinear con target
        return [period_to_value.get(p) for p in target_periods]


def detect_revenue_anomaly(
    revenue_values: List[Optional[float]],
    operating_expenses_values: List[Optional[float]]
) -> List[int]:
    """
    Detectar anomalías en revenue comparando con operating expenses.
    
    Si revenue < operating expenses, probablemente es un error.
    
    Returns:
        Lista de índices con anomalías
    """
    anomalies = []
    
    for i in range(len(revenue_values)):
        rev = revenue_values[i] if i < len(revenue_values) else None
        exp = operating_expenses_values[i] if i < len(operating_expenses_values) else None
        
        if rev is not None and exp is not None:
            # Revenue debería ser mayor que operating expenses en la mayoría de casos
            if rev < exp * 0.5:
                anomalies.append(i)
    
    return anomalies

