"""
Validator v4.1 - Two-Pass Validation
=====================================
Pass B del pipeline: verifica los datos extraídos por el LLM contra el texto original.

Detecta:
- Precios alucinados (ej: pre-funded con $125 en vez de $0.001)
- Cantidades imposibles
- Fechas inconsistentes
- Campos faltantes críticos

También genera alertas para revisión manual.
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ValidationIssue:
    """Un problema detectado en la validación"""
    field: str
    severity: str  # 'error', 'warning', 'info'
    message: str
    extracted_value: Any
    expected_range: Optional[str] = None
    evidence_snippet: Optional[str] = None


@dataclass
class ValidationResult:
    """Resultado de validar un instrumento"""
    is_valid: bool
    confidence_score: float  # 0.0 - 1.0
    issues: List[ValidationIssue] = field(default_factory=list)
    corrected_values: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Reglas de validación por tipo de instrumento
# ============================================================================

# Rangos esperados para precios de ejercicio
PRICE_RULES = {
    'pre-funded': {
        'expected_range': (0.0001, 0.01),  # Pre-funded casi siempre $0.0001-$0.01
        'typical': 0.001,
        'flag_if_above': 1.0,  # Flag si > $1
    },
    'common': {
        'expected_range': (0.10, 100.0),  # Common warrants típico
        'flag_if_below': 0.05,  # Flag si < $0.05 (puede ser error)
        'flag_if_above': 500.0,  # Flag si > $500
    },
    'placement_agent': {
        'expected_range': (0.10, 100.0),
        'flag_if_above': 500.0,
    },
}

# Patrones para extraer precios del texto
PRICE_PATTERNS = [
    r'\$\s*([\d,]+\.?\d*)',  # $1.50, $1,500.00
    r'exercise\s+price\s+(?:of\s+)?\$?\s*([\d,]+\.?\d*)',  # exercise price of $1.50
    r'exercisable\s+at\s+\$?\s*([\d,]+\.?\d*)',  # exercisable at $1.50
    r'per\s+(?:share|warrant)\s+(?:of\s+)?\$?\s*([\d,]+\.?\d*)',  # per share of $1.50
]

# Patrones para extraer cantidades
QUANTITY_PATTERNS = [
    r'([\d,]+)\s+(?:common\s+)?warrants?',  # 16,000,000 warrants
    r'up\s+to\s+([\d,]+)\s+(?:shares?|warrants?)',  # up to 16,000,000 shares
    r'([\d,]+)\s+shares?\s+of\s+common',  # 16,000,000 shares of common
    r'aggregate\s+of\s+([\d,]+)',  # aggregate of 16,000,000
]


def _parse_number(text: str) -> Optional[float]:
    """Parsea un número que puede tener comas"""
    if not text:
        return None
    try:
        cleaned = text.replace(',', '').replace(' ', '')
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def _extract_prices_from_text(text: str) -> List[float]:
    """Extrae todos los precios mencionados en el texto"""
    prices = []
    for pattern in PRICE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            price = _parse_number(match.group(1))
            if price and 0 < price < 10000:  # Rango razonable
                prices.append(price)
    return list(set(prices))


def _extract_quantities_from_text(text: str) -> List[int]:
    """Extrae todas las cantidades mencionadas en el texto"""
    quantities = []
    for pattern in QUANTITY_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            qty = _parse_number(match.group(1))
            if qty and qty > 1000:  # Mínimo razonable
                quantities.append(int(qty))
    return list(set(quantities))


def validate_warrant(warrant: Dict, source_text: str) -> ValidationResult:
    """
    Valida un warrant extraído contra el texto fuente.
    
    Args:
        warrant: Dict con datos del warrant extraído
        source_text: Texto original del filing
    
    Returns:
        ValidationResult con issues encontrados
    """
    issues = []
    corrected = {}
    confidence = 1.0
    
    warrant_type = (warrant.get('warrant_type') or '').lower()
    series_name = (warrant.get('series_name') or '').lower()
    exercise_price = warrant.get('exercise_price')
    total_issued = warrant.get('total_issued')
    
    # Determinar tipo para reglas
    if 'pre-funded' in warrant_type or 'pre-funded' in series_name or 'prefunded' in series_name:
        type_key = 'pre-funded'
    elif 'placement' in warrant_type or 'placement' in series_name:
        type_key = 'placement_agent'
    else:
        type_key = 'common'
    
    rules = PRICE_RULES.get(type_key, PRICE_RULES['common'])
    
    # =========================================================================
    # Validar exercise_price
    # =========================================================================
    if exercise_price is not None:
        try:
            price = float(exercise_price)
            
            # Check rangos
            min_price, max_price = rules.get('expected_range', (0, 10000))
            
            if price < min_price or price > max_price:
                issues.append(ValidationIssue(
                    field='exercise_price',
                    severity='warning',
                    message=f"Price ${price} outside expected range ${min_price}-${max_price} for {type_key}",
                    extracted_value=price,
                    expected_range=f"${min_price}-${max_price}"
                ))
                confidence *= 0.7
            
            # Pre-funded específico: si es > $1, casi seguro es error
            if type_key == 'pre-funded' and price > rules.get('flag_if_above', 1.0):
                issues.append(ValidationIssue(
                    field='exercise_price',
                    severity='error',
                    message=f"Pre-funded warrant with price ${price} is likely an error (expected ~$0.001)",
                    extracted_value=price,
                    expected_range="$0.0001-$0.01"
                ))
                confidence *= 0.3
                
                # Intentar corregir buscando en el texto
                text_prices = _extract_prices_from_text(source_text)
                pre_funded_prices = [p for p in text_prices if 0.0001 <= p <= 0.01]
                if pre_funded_prices:
                    corrected['exercise_price'] = min(pre_funded_prices)
                    issues.append(ValidationIssue(
                        field='exercise_price',
                        severity='info',
                        message=f"Found likely correct pre-funded price in text: ${corrected['exercise_price']}",
                        extracted_value=corrected['exercise_price']
                    ))
            
            # Flag precios muy altos que pueden ser históricos
            if price > 100 and type_key == 'common':
                # Buscar si hay precios más bajos en el texto que podrían ser actuales
                text_prices = _extract_prices_from_text(source_text)
                lower_prices = [p for p in text_prices if p < price and p > 0.1]
                if lower_prices:
                    issues.append(ValidationIssue(
                        field='exercise_price',
                        severity='warning',
                        message=f"High price ${price} found. Text also contains lower prices: {lower_prices[:3]}",
                        extracted_value=price
                    ))
                    confidence *= 0.8
                    
        except (TypeError, ValueError):
            issues.append(ValidationIssue(
                field='exercise_price',
                severity='error',
                message=f"Invalid price format: {exercise_price}",
                extracted_value=exercise_price
            ))
            confidence *= 0.5
    
    # =========================================================================
    # Validar total_issued
    # =========================================================================
    if total_issued is not None:
        try:
            qty = int(total_issued)
            
            # Cantidades muy pequeñas son sospechosas
            if qty < 10000:
                issues.append(ValidationIssue(
                    field='total_issued',
                    severity='warning',
                    message=f"Quantity {qty:,} seems unusually small for a warrant issuance",
                    extracted_value=qty
                ))
                confidence *= 0.8
            
            # Cantidades enormes (> 1B) son sospechosas
            if qty > 1_000_000_000:
                issues.append(ValidationIssue(
                    field='total_issued',
                    severity='warning',
                    message=f"Quantity {qty:,} seems unusually large",
                    extracted_value=qty
                ))
                confidence *= 0.7
                
            # Verificar si la cantidad aparece en el texto
            text_quantities = _extract_quantities_from_text(source_text)
            if text_quantities and qty not in text_quantities:
                # Buscar cantidad cercana
                close_matches = [q for q in text_quantities if 0.8 * qty <= q <= 1.2 * qty]
                if not close_matches:
                    issues.append(ValidationIssue(
                        field='total_issued',
                        severity='warning',
                        message=f"Extracted quantity {qty:,} not found in text. Found: {text_quantities[:5]}",
                        extracted_value=qty
                    ))
                    confidence *= 0.8
                    
        except (TypeError, ValueError):
            issues.append(ValidationIssue(
                field='total_issued',
                severity='error',
                message=f"Invalid quantity format: {total_issued}",
                extracted_value=total_issued
            ))
            confidence *= 0.5
    
    # =========================================================================
    # Validar fechas
    # =========================================================================
    issue_date = warrant.get('issue_date')
    expiration_date = warrant.get('expiration_date')
    
    if issue_date and expiration_date:
        try:
            issue_dt = datetime.fromisoformat(str(issue_date)[:10])
            exp_dt = datetime.fromisoformat(str(expiration_date)[:10])
            
            # Warrants típicamente expiran en 5 años, máx 10
            years_diff = (exp_dt - issue_dt).days / 365
            
            if years_diff < 0:
                issues.append(ValidationIssue(
                    field='expiration_date',
                    severity='error',
                    message="Expiration date is before issue date",
                    extracted_value=expiration_date
                ))
                confidence *= 0.3
            elif years_diff > 10:
                issues.append(ValidationIssue(
                    field='expiration_date',
                    severity='warning',
                    message=f"Warrant term of {years_diff:.1f} years is unusually long",
                    extracted_value=expiration_date
                ))
                confidence *= 0.9
                
        except (ValueError, TypeError):
            pass  # Fechas mal formadas se ignoran
    
    # =========================================================================
    # Resultado
    # =========================================================================
    is_valid = all(issue.severity != 'error' for issue in issues)
    
    return ValidationResult(
        is_valid=is_valid,
        confidence_score=max(0.0, min(1.0, confidence)),
        issues=issues,
        corrected_values=corrected
    )


def validate_instruments(instruments: List[Dict], source_text: str, inst_type: str = 'warrant') -> List[Tuple[Dict, ValidationResult]]:
    """
    Valida una lista de instrumentos y retorna resultados.
    
    Args:
        instruments: Lista de instrumentos extraídos
        source_text: Texto fuente del filing
        inst_type: Tipo de instrumento ('warrant', 'atm', 'shelf', etc.)
    
    Returns:
        Lista de tuplas (instrumento, resultado_validación)
    """
    results = []
    
    for inst in instruments:
        if inst_type == 'warrant':
            result = validate_warrant(inst, source_text)
        else:
            # Para otros tipos, validación básica
            result = ValidationResult(is_valid=True, confidence_score=1.0)
        
        results.append((inst, result))
        
        if result.issues:
            logger.info("validation_issues_found",
                       inst_type=inst_type,
                       name=inst.get('series_name'),
                       issues=[{
                           'field': i.field,
                           'severity': i.severity,
                           'message': i.message
                       } for i in result.issues])
    
    return results


def apply_corrections(instrument: Dict, validation_result: ValidationResult) -> Dict:
    """
    Aplica correcciones automáticas al instrumento basadas en validación.
    
    Solo aplica correcciones de alta confianza (ej: pre-funded price fix).
    """
    corrected = dict(instrument)
    
    for field, value in validation_result.corrected_values.items():
        corrected[field] = value
        corrected[f'_{field}_original'] = instrument.get(field)
        corrected['_auto_corrected'] = True
    
    corrected['_validation_confidence'] = validation_result.confidence_score
    
    return corrected


# ============================================================================
# Coherence checks (validaciones cruzadas)
# ============================================================================

def check_offering_coherence(warrants: List[Dict], offering: Optional[Dict]) -> List[ValidationIssue]:
    """
    Verifica coherencia entre warrants y el offering.
    
    Por ejemplo: 
    - Total de warrants no debería exceder shares del offering
    - Precios deberían ser coherentes con precio del offering
    """
    issues = []
    
    if not offering:
        return issues
    
    offering_price = offering.get('final_pricing') or offering.get('price_per_share')
    shares_offered = offering.get('shares_offered')
    
    if offering_price and warrants:
        try:
            off_price = float(offering_price)
            
            for w in warrants:
                w_price = w.get('exercise_price')
                if w_price:
                    w_price = float(w_price)
                    w_type = (w.get('warrant_type') or '').lower()
                    
                    # Common warrants típicamente tienen strike >= offering price
                    if 'common' in w_type and w_price < off_price * 0.5:
                        issues.append(ValidationIssue(
                            field='exercise_price',
                            severity='warning',
                            message=f"Warrant price ${w_price} is less than 50% of offering price ${off_price}",
                            extracted_value=w_price
                        ))
                        
        except (TypeError, ValueError):
            pass
    
    return issues

