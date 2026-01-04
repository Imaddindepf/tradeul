"""
Risk Scorer
Calcula scores de riesgo de dilución generales
"""

import sys
sys.path.append('/app')

from typing import Optional, Dict
from decimal import Decimal

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class RiskScorer:
    """
    Calcula overall risk score combinando múltiples factores
    """
    
    def calculate_overall_risk_score(
        self,
        cash_need_score: int,
        dilution_risk_score: int,
        market_cap: Optional[int] = None,
        free_float: Optional[int] = None,
        recent_filings_count: int = 0
    ) -> int:
        """
        Calcular overall risk score (0-100)
        
        Combina múltiples factores de riesgo:
        - Cash need (40% weight)
        - Dilution risk (40% weight)
        - Market factors (20% weight)
        
        Args:
            cash_need_score: Score de necesidad de cash (0-100)
            dilution_risk_score: Score de riesgo de dilución (0-100)
            market_cap: Market capitalization
            free_float: Float shares
            recent_filings_count: Filings dilutivos últimos 6 meses
        
        Returns:
            Overall risk score (0-100)
        """
        try:
            # Base score: promedio ponderado de cash need y dilution risk
            base_score = (
                cash_need_score * 0.4 +
                dilution_risk_score * 0.4
            )
            
            # Market factors score (20% weight)
            market_score = self._calculate_market_risk_score(
                market_cap=market_cap,
                free_float=free_float,
                recent_filings=recent_filings_count
            )
            
            overall = base_score + (market_score * 0.2)
            
            return min(int(overall), 100)
            
        except Exception as e:
            logger.error("calculate_overall_risk_failed", error=str(e))
            return 0
    
    def _calculate_market_risk_score(
        self,
        market_cap: Optional[int],
        free_float: Optional[int],
        recent_filings: int
    ) -> int:
        """
        Calcular market risk score (0-100)
        
        Factores:
        - Market cap pequeño = más riesgo
        - Float pequeño = más riesgo
        - Filings dilutivos recientes = más riesgo
        """
        score = 0
        
        # 1. Market cap (40 puntos)
        if market_cap is not None:
            if market_cap < 50_000_000:  # < $50M
                score += 40
            elif market_cap < 100_000_000:  # < $100M
                score += 30
            elif market_cap < 300_000_000:  # < $300M
                score += 20
            elif market_cap < 1_000_000_000:  # < $1B
                score += 10
        
        # 2. Float (30 puntos)
        if free_float is not None:
            if free_float < 5_000_000:  # < 5M
                score += 30
            elif free_float < 10_000_000:  # < 10M
                score += 20
            elif free_float < 20_000_000:  # < 20M
                score += 10
        
        # 3. Recent dilutive filings (30 puntos)
        if recent_filings >= 3:
            score += 30
        elif recent_filings >= 2:
            score += 20
        elif recent_filings >= 1:
            score += 10
        
        return min(score, 100)
    
    def get_risk_level_label(self, score: int) -> str:
        """
        Convertir score numérico a label descriptivo
        
        Returns:
            'low', 'medium', 'high', 'critical'
        """
        if score >= 80:
            return 'critical'
        elif score >= 60:
            return 'high'
        elif score >= 40:
            return 'medium'
        else:
            return 'low'
    
    def get_risk_description(self, score: int) -> str:
        """
        Obtener descripción del nivel de riesgo
        """
        level = self.get_risk_level_label(score)
        
        descriptions = {
            'low': 'Bajo riesgo de dilución. Compañía tiene runway saludable y dilución histórica controlada.',
            'medium': 'Riesgo moderado. Monitorear cash position y posibles ofertas futuras.',
            'high': 'Alto riesgo de dilución. Cash runway limitado o dilución histórica significativa.',
            'critical': 'Riesgo crítico. Alta probabilidad de offering inminente o dilución severa.'
        }
        
        return descriptions.get(level, '')
    
    def calculate_offering_probability(
        self,
        overall_risk_score: int,
        runway_months: Optional[Decimal],
        has_active_shelf: bool,
        days_since_last_offering: Optional[int]
    ) -> Dict:
        """
        Estimar probabilidad de offering en próximos 6 meses
        
        Args:
            overall_risk_score: Overall risk score
            runway_months: Meses de runway
            has_active_shelf: Si tiene S-3 activo
            days_since_last_offering: Días desde último offering
        
        Returns:
            Dict con probabilidad y factores
        """
        try:
            probability = 0.0
            factors = []
            
            # 1. Overall risk score
            if overall_risk_score >= 80:
                probability += 0.40
                factors.append("very_high_risk_score")
            elif overall_risk_score >= 60:
                probability += 0.25
                factors.append("high_risk_score")
            elif overall_risk_score >= 40:
                probability += 0.10
                factors.append("medium_risk_score")
            
            # 2. Cash runway
            if runway_months is not None:
                if runway_months < 6:
                    probability += 0.35
                    factors.append("critical_runway")
                elif runway_months < 12:
                    probability += 0.20
                    factors.append("low_runway")
                elif runway_months < 18:
                    probability += 0.05
                    factors.append("moderate_runway")
            
            # 3. Active shelf
            if has_active_shelf:
                probability += 0.15
                factors.append("active_shelf")
            
            # 4. Recent offering pattern
            if days_since_last_offering is not None:
                if days_since_last_offering < 90:
                    probability += 0.10
                    factors.append("very_recent_offering")
                elif days_since_last_offering < 180:
                    probability += 0.05
                    factors.append("recent_offering")
            
            # Cap at 95%
            probability = min(probability, 0.95)
            
            # Determine level
            if probability >= 0.70:
                level = "very_high"
            elif probability >= 0.50:
                level = "high"
            elif probability >= 0.30:
                level = "moderate"
            elif probability >= 0.10:
                level = "low"
            else:
                level = "very_low"
            
            return {
                'probability': round(probability, 2),
                'probability_pct': round(probability * 100, 1),
                'level': level,
                'factors': factors,
                'timeframe': '6 months'
            }
            
        except Exception as e:
            logger.error("calculate_offering_probability_failed", error=str(e))
            return {
                'probability': 0.0,
                'probability_pct': 0.0,
                'level': 'unknown',
                'factors': [],
                'timeframe': '6 months'
            }
    
    def generate_risk_summary(
        self,
        overall_score: int,
        cash_need_score: int,
        dilution_risk_score: int,
        runway_months: Optional[Decimal]
    ) -> Dict:
        """
        Generar resumen completo de riesgo
        
        Returns:
            Dict con resumen ejecutivo
        """
        risk_level = self.get_risk_level_label(overall_score)
        description = self.get_risk_description(overall_score)
        
        # Key concerns
        concerns = []
        if cash_need_score >= 70:
            concerns.append("Limited cash runway")
        if dilution_risk_score >= 70:
            concerns.append("High historical dilution")
        if runway_months and runway_months < 12:
            concerns.append("Insufficient runway")
        
        # Positive factors
        positives = []
        if cash_need_score < 30:
            positives.append("Healthy cash position")
        if dilution_risk_score < 30:
            positives.append("Controlled dilution history")
        if runway_months and runway_months > 24:
            positives.append("Strong runway")
        
        return {
            'overall_score': overall_score,
            'risk_level': risk_level,
            'description': description,
            'component_scores': {
                'cash_need': cash_need_score,
                'dilution_risk': dilution_risk_score
            },
            'key_concerns': concerns,
            'positive_factors': positives,
            'recommendation': self._get_recommendation(risk_level)
        }
    
    def _get_recommendation(self, risk_level: str) -> str:
        """Obtener recomendación basada en nivel de riesgo"""
        recommendations = {
            'low': 'Ticker seguro para inversión a largo plazo desde perspectiva de dilución.',
            'medium': 'Monitorear quarterly results y cash position. Dilución moderada esperada.',
            'high': 'Alto riesgo de dilución. Considerar posición más pequeña o esperar por offering.',
            'critical': 'Evitar o esperar. Offering altamente probable en corto plazo.'
        }
        
        return recommendations.get(risk_level, '')

