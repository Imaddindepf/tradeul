"""
Industry Detector - Sistema 100% Data-Driven.

NO hay hardcoding de empresas.
La estructura financiera de cada empresa determina automáticamente
qué tipo de presentación usar.

Lógica:
1. Si tiene net_interest_income > 25% de revenue → usa estructura banking
2. Si tiene premiums_earned → usa estructura insurance
3. Si tiene funds_from_operations → usa estructura real_estate
4. Si tiene membership_fees → usa estructura retail
5. Default → estructura estándar GAAP

Esto es cómo lo hacen los profesionales (TIKR, Bloomberg, etc.)
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from shared.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class IndustryDetectionResult:
    """Resultado de detección de industria."""
    industry: Optional[str]  # None = usar estructura estándar
    confidence: float        # 0.0 - 1.0
    reason: str
    metrics: Dict[str, float]  # Métricas usadas para la decisión


# =============================================================================
# DATA-DRIVEN DETECTION - La única forma correcta
# =============================================================================

def _safe_get_value(field_map: Dict, key: str) -> float:
    """Obtener valor más reciente de un campo de forma segura."""
    vals = field_map.get(key, [])
    if isinstance(vals, list):
        for v in vals:
            if v is not None and isinstance(v, (int, float)):
                return abs(float(v))
    elif isinstance(vals, (int, float)):
        return abs(float(vals))
    return 0.0


def detect_from_financial_data(financial_data: Dict) -> IndustryDetectionResult:
    """
    Detectar industria analizando la estructura de datos financieros.
    
    Esta es la ÚNICA forma correcta - basada en los datos reales,
    no en hardcoding de tickers.
    
    Criterios (basados en cómo TIKR/Bloomberg clasifican):
    - Banking: net_interest_income > 25% de revenue
    - Insurance: tiene premiums_earned o policy_benefits
    - Real Estate: tiene funds_from_operations
    - Retail: tiene membership_fees significativo
    - Standard: todo lo demás
    """
    default_result = IndustryDetectionResult(
        industry=None,
        confidence=1.0,
        reason="Standard GAAP structure (default)",
        metrics={}
    )
    
    if not financial_data:
        return default_result
    
    income = financial_data.get('income_statement', [])
    if not income:
        return default_result
    
    # Crear mapa de campos: key -> values
    field_map = {}
    for f in income:
        key = f.get('key')
        values = f.get('values', [])
        if key and values:
            field_map[key] = values
    
    # Obtener métricas clave
    revenue = _safe_get_value(field_map, 'revenue')
    net_interest_income = _safe_get_value(field_map, 'net_interest_income')
    interest_income = _safe_get_value(field_map, 'interest_income')
    noninterest_income = _safe_get_value(field_map, 'noninterest_income')
    premiums = _safe_get_value(field_map, 'premiums_earned_net') or \
               _safe_get_value(field_map, 'premiums_written_gross') or \
               _safe_get_value(field_map, 'premium_revenue')
    ffo = _safe_get_value(field_map, 'funds_from_operations')
    membership_fees = _safe_get_value(field_map, 'membership_fees')
    provision_bad_debts = _safe_get_value(field_map, 'provision_bad_debts') or \
                          _safe_get_value(field_map, 'provision_for_loan_losses')
    
    metrics = {
        'revenue': revenue,
        'net_interest_income': net_interest_income,
        'interest_income': interest_income,
        'noninterest_income': noninterest_income,
        'premiums': premiums,
        'ffo': ffo,
        'membership_fees': membership_fees,
        'provision_bad_debts': provision_bad_debts,
    }
    
    # =================================================================
    # REGLA 1: BANKING
    # Si net_interest_income es significativo (>25% de revenue)
    # Y tiene provision for bad debts/loan losses
    # =================================================================
    if revenue > 0 and net_interest_income > 0:
        nii_ratio = net_interest_income / revenue
        
        # Banking requiere:
        # 1. net_interest_income > 25% de revenue, O
        # 2. noninterest_income existe Y provision_bad_debts existe
        is_banking = (
            nii_ratio > 0.25 or 
            (noninterest_income > 0 and provision_bad_debts > 0 and nii_ratio > 0.10)
        )
        
        if is_banking:
            return IndustryDetectionResult(
                industry="banking",
                confidence=min(nii_ratio + 0.3, 0.95),
                reason=f"Net interest income is {nii_ratio:.0%} of revenue with banking characteristics",
                metrics=metrics
            )
    
    # =================================================================
    # REGLA 2: INSURANCE
    # Si tiene premiums earned
    # =================================================================
    if premiums > 0 and revenue > 0:
        premiums_ratio = premiums / revenue
        if premiums_ratio > 0.30:
            return IndustryDetectionResult(
                industry="insurance",
                confidence=0.90,
                reason=f"Insurance premiums are {premiums_ratio:.0%} of revenue",
                metrics=metrics
            )
    
    # =================================================================
    # REGLA 3: REAL ESTATE / REIT
    # Si tiene Funds From Operations
    # =================================================================
    if ffo > 0:
        return IndustryDetectionResult(
            industry="real_estate",
            confidence=0.85,
            reason="Company reports Funds From Operations (FFO) - REIT characteristic",
            metrics=metrics
        )
    
    # =================================================================
    # REGLA 4: RETAIL (con membership)
    # Si tiene membership fees significativo
    # =================================================================
    if membership_fees > 0 and revenue > 0:
        membership_ratio = membership_fees / revenue
        if membership_ratio > 0.01:  # >1% de revenue viene de memberships
            return IndustryDetectionResult(
                industry="retail",
                confidence=0.80,
                reason=f"Membership fees are {membership_ratio:.1%} of revenue",
                metrics=metrics
            )
    
    # =================================================================
    # REGLA 5: MANUFACTURING WITH FINANCE DIVISION (CAT, GE, Ford, DE)
    # Si tiene Finance Division Revenue significativo (>3% de revenue)
    # Estas empresas requieren fórmula especial de Gross Profit
    # =================================================================
    finance_div_revenue = _safe_get_value(field_map, 'finance_division_revenue')
    finance_div_op_exp = _safe_get_value(field_map, 'finance_div_operating_exp')
    
    if finance_div_revenue > 0 and revenue > 0:
        finance_ratio = finance_div_revenue / revenue
        if finance_ratio > 0.03:  # >3% de revenue viene de finance division
            metrics['finance_div_revenue'] = finance_div_revenue
            metrics['finance_div_ratio'] = finance_ratio
            return IndustryDetectionResult(
                industry="manufacturing_finance",
                confidence=0.90,
                reason=f"Finance Division revenue is {finance_ratio:.1%} of total revenue (CAT/GE/Ford type)",
                metrics=metrics
            )
    
    # También detectar si tiene Finance Div Op Exp (puede no tener revenue separado)
    if finance_div_op_exp > 0:
        metrics['finance_div_op_exp'] = finance_div_op_exp
        return IndustryDetectionResult(
            industry="manufacturing_finance",
            confidence=0.85,
            reason="Company has Finance Division operating expenses - manufacturing with captive finance",
            metrics=metrics
        )
    
    # =================================================================
    # DEFAULT: STANDARD GAAP
    # La mayoría de empresas usan estructura estándar
    # =================================================================
    return IndustryDetectionResult(
        industry=None,  # None = usar estructura estándar
        confidence=1.0,
        reason="Standard GAAP structure - no special industry characteristics detected",
        metrics=metrics
    )


# =============================================================================
# SIC CODE FALLBACK (Solo si no hay datos financieros)
# =============================================================================

# SIC codes que EXCLUIMOS de banking porque son muy genéricos
SIC_BANKING_EXCLUSIONS = {
    6199,  # Finance services NEC - demasiado genérico (COIN, etc.)
    6282,  # Investment advice - puede ser cualquier cosa
}

SIC_RANGES = {
    "banking": [
        (6020, 6029),   # Commercial banks
        (6035, 6036),   # Savings institutions
        (6141, 6163),   # Credit institutions
        (6211, 6221),   # Security brokers
    ],
    "insurance": [
        (6311, 6411),   # All insurance codes
    ],
    "real_estate": [
        (6500, 6553),   # Real estate
        (6798, 6798),   # REITs
    ],
    "retail": [
        (5200, 5399),   # Retail
        (5400, 5499),   # Food stores
        (5500, 5699),   # Auto, apparel
        (5700, 5999),   # Home, misc retail
    ],
}


def _get_industry_from_sic(sic_code: int) -> Optional[str]:
    """Fallback: obtener industria desde SIC code."""
    # Excluir SIC codes problemáticos
    if sic_code in SIC_BANKING_EXCLUSIONS:
        return None
    
    for industry, ranges in SIC_RANGES.items():
        for start, end in ranges:
            if start <= sic_code <= end:
                return industry
    return None


# =============================================================================
# MAIN API
# =============================================================================

class IndustryDetector:
    """
    Detector de industria 100% data-driven.
    
    Prioridad:
    1. Análisis de datos financieros (SIEMPRE preferido)
    2. SIC code (solo como fallback si no hay datos)
    """
    
    def __init__(self):
        self._cache: Dict[str, IndustryDetectionResult] = {}
    
    def detect(
        self,
        ticker: str,
        sic_code: Optional[int] = None,
        financial_data: Optional[Dict] = None,
        force_refresh: bool = False
    ) -> IndustryDetectionResult:
        """
        Detectar industria para un ticker.
        
        Args:
            ticker: Símbolo de la empresa
            sic_code: Código SIC (fallback)
            financial_data: Datos financieros para análisis
            force_refresh: Forzar recálculo
        
        Returns:
            IndustryDetectionResult con industria detectada
        """
        cache_key = ticker.upper()
        
        if not force_refresh and cache_key in self._cache:
            return self._cache[cache_key]
        
        # PRIORIDAD 1: Análisis de datos financieros
        if financial_data:
            result = detect_from_financial_data(financial_data)
            self._cache[cache_key] = result
            
            logger.info(
                f"[{ticker}] Industry: {result.industry or 'standard'} "
                f"(data-driven, confidence={result.confidence:.0%}, "
                f"reason={result.reason})"
            )
            return result
        
        # PRIORIDAD 2: SIC code fallback (solo si no hay datos)
        if sic_code:
            industry = _get_industry_from_sic(sic_code)
            result = IndustryDetectionResult(
                industry=industry,
                confidence=0.60 if industry else 1.0,
                reason=f"SIC code {sic_code} fallback" if industry else "Standard GAAP (no financial data)",
                metrics={}
            )
            self._cache[cache_key] = result
            
            logger.info(
                f"[{ticker}] Industry: {result.industry or 'standard'} "
                f"(SIC fallback, confidence={result.confidence:.0%})"
            )
            return result
        
        # DEFAULT: Standard
        result = IndustryDetectionResult(
            industry=None,
            confidence=1.0,
            reason="Standard GAAP structure (no data available)",
            metrics={}
        )
        self._cache[cache_key] = result
        return result
    
    def clear_cache(self, ticker: Optional[str] = None):
        """Limpiar cache."""
        if ticker:
            self._cache.pop(ticker.upper(), None)
        else:
            self._cache.clear()


# Singleton
_detector: Optional[IndustryDetector] = None


def get_industry_detector() -> IndustryDetector:
    """Obtener instancia singleton del detector."""
    global _detector
    if _detector is None:
        _detector = IndustryDetector()
    return _detector


def detect_industry(
    ticker: str,
    sic_code: Optional[int] = None,
    financial_data: Optional[Dict] = None
) -> Optional[str]:
    """
    Función de conveniencia para detectar industria.
    
    Returns:
        Nombre de industria (str) o None para estructura estándar
    """
    detector = get_industry_detector()
    result = detector.detect(ticker, sic_code, financial_data)
    return result.industry
