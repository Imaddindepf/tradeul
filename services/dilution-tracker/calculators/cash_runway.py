"""
Cash Runway Calculator
Calcula runway de efectivo y proyecciones basado en burn rate
"""

import sys
sys.path.append('/app')

from typing import Dict, Optional
from datetime import date, datetime, timedelta
from decimal import Decimal

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class CashRunwayCalculator:
    """
    Calcula cash runway y proyecciones de efectivo
    
    Runway = Current Cash / Quarterly Burn Rate
    """
    
    def calculate_runway(
        self,
        current_cash: Decimal,
        quarterly_burn_rate: Decimal
    ) -> Optional[Decimal]:
        """
        Calcular meses de runway
        
        Args:
            current_cash: Efectivo actual (cash + investments)
            quarterly_burn_rate: Burn rate trimestral (negativo si quema cash)
        
        Returns:
            Meses de runway o None
        """
        try:
            if current_cash <= 0:
                return Decimal(0)
            
            if quarterly_burn_rate >= 0:
                # Compañía genera cash, runway infinito
                return None
            
            # Burn rate mensual (dividir entre 3)
            monthly_burn = abs(Decimal(str(quarterly_burn_rate))) / Decimal(3)
            
            if monthly_burn == 0:
                return None
            
            # Runway en meses
            runway_months = current_cash / monthly_burn
            
            return round(runway_months, 2)
            
        except Exception as e:
            logger.error("calculate_runway_failed", error=str(e))
            return None
    
    def calculate_quarterly_burn_rate(
        self,
        cash_flows: list
    ) -> Optional[Decimal]:
        """
        Calcular burn rate trimestral promedio
        
        Args:
            cash_flows: Lista de cash flows (últimos 4 quarters)
                       [{'period_date': date, 'operating_cash_flow': Decimal}]
        
        Returns:
            Burn rate promedio o None
        """
        try:
            if not cash_flows or len(cash_flows) < 2:
                return None
            
            # Ordenar por fecha (más reciente primero)
            sorted_flows = sorted(
                cash_flows,
                key=lambda x: x['period_date'],
                reverse=True
            )
            
            # Tomar últimos 4 quarters
            recent_flows = sorted_flows[:4]
            
            # Calcular promedio de operating cash flow
            total = sum(
                cf['operating_cash_flow']
                for cf in recent_flows
                if cf['operating_cash_flow'] is not None
            )
            
            count = len([
                cf for cf in recent_flows
                if cf['operating_cash_flow'] is not None
            ])
            
            if count == 0:
                return None
            
            avg_quarterly_burn = total / count
            
            return round(avg_quarterly_burn, 2)
            
        except Exception as e:
            logger.error("calculate_burn_rate_failed", error=str(e))
            return None
    
    def project_cash_position(
        self,
        current_cash: Decimal,
        quarterly_burn_rate: Decimal,
        months: int = 12
    ) -> list:
        """
        Proyectar posición de efectivo para próximos N meses
        
        Args:
            current_cash: Cash actual
            quarterly_burn_rate: Burn rate trimestral
            months: Meses a proyectar
        
        Returns:
            Lista de proyecciones mensuales
        """
        try:
            projections = []
            
            # Burn rate mensual
            monthly_burn = Decimal(str(quarterly_burn_rate)) / Decimal(3)
            
            # Proyectar cada mes
            cash_balance = current_cash
            base_date = datetime.now().date()
            
            for month in range(1, months + 1):
                # Aplicar burn rate
                cash_balance = cash_balance + monthly_burn
                
                # No puede ser negativo
                if cash_balance < 0:
                    cash_balance = Decimal(0)
                
                # Fecha del mes
                projected_date = base_date + timedelta(days=30 * month)
                
                projections.append({
                    'month': month,
                    'date': projected_date.strftime('%Y-%m-%d'),
                    'estimated_cash': float(cash_balance)
                })
                
                # Si llega a 0, detener proyección
                if cash_balance == 0:
                    break
            
            return projections
            
        except Exception as e:
            logger.error("project_cash_position_failed", error=str(e))
            return []
    
    def get_runway_risk_level(
        self,
        runway_months: Optional[Decimal]
    ) -> str:
        """
        Determinar nivel de riesgo basado en runway
        
        Returns:
            'critical', 'high', 'medium', 'low', 'unknown'
        """
        if runway_months is None:
            return "unknown"
        
        if runway_months < 6:
            return "critical"
        elif runway_months < 12:
            return "high"
        elif runway_months < 24:
            return "medium"
        else:
            return "low"
    
    def analyze_burn_trend(
        self,
        cash_flows: list
    ) -> dict:
        """
        Analizar tendencia de burn rate
        
        Args:
            cash_flows: Lista de cash flows ordenados por fecha
        
        Returns:
            Dict con análisis de tendencia
        """
        try:
            if not cash_flows or len(cash_flows) < 3:
                return {'trend': 'unknown', 'improving': None}
            
            # Ordenar por fecha (más antiguo primero)
            sorted_flows = sorted(
                cash_flows,
                key=lambda x: x['period_date']
            )
            
            # Comparar últimos 3 quarters
            recent = sorted_flows[-3:]
            
            burns = [
                cf['operating_cash_flow']
                for cf in recent
                if cf['operating_cash_flow'] is not None
            ]
            
            if len(burns) < 3:
                return {'trend': 'unknown', 'improving': None}
            
            # Analizar tendencia
            # Si los números están mejorando (menos negativos o más positivos)
            q1, q2, q3 = burns
            
            # Tendencia mejorando si cada quarter es mejor que el anterior
            improving = q2 > q1 and q3 > q2
            deteriorating = q2 < q1 and q3 < q2
            
            if improving:
                trend = 'improving'
            elif deteriorating:
                trend = 'deteriorating'
            else:
                trend = 'stable'
            
            # Calcular rate of change
            avg_change = ((q3 - q1) / 2) if q1 != 0 else 0
            
            return {
                'trend': trend,
                'improving': improving,
                'deteriorating': deteriorating,
                'latest_quarter': float(q3),
                'previous_quarter': float(q2),
                'avg_quarterly_change': float(avg_change)
            }
            
        except Exception as e:
            logger.error("analyze_burn_trend_failed", error=str(e))
            return {'trend': 'unknown', 'improving': None}
    
    def calculate_cash_need_score(
        self,
        runway_months: Optional[Decimal],
        burn_trend: str,
        current_ratio: Optional[Decimal],
        debt_to_equity: Optional[Decimal]
    ) -> int:
        """
        Calcular score de necesidad de cash (0-100)
        
        Args:
            runway_months: Meses de runway
            burn_trend: 'improving', 'stable', 'deteriorating'
            current_ratio: Current assets / Current liabilities
            debt_to_equity: Total debt / Equity
        
        Returns:
            Score 0-100 (100 = máxima necesidad de cash)
        """
        score = 0
        
        # 1. Runway (40 puntos)
        if runway_months is not None:
            if runway_months < 6:
                score += 40
            elif runway_months < 12:
                score += 30
            elif runway_months < 18:
                score += 20
            elif runway_months < 24:
                score += 10
        
        # 2. Burn trend (30 puntos)
        if burn_trend == 'deteriorating':
            score += 30
        elif burn_trend == 'stable':
            score += 15
        # improving = 0 puntos
        
        # 3. Current ratio (15 puntos)
        if current_ratio is not None:
            if current_ratio < 0.5:
                score += 15
            elif current_ratio < 1.0:
                score += 10
            elif current_ratio < 1.5:
                score += 5
        
        # 4. Debt to equity (15 puntos)
        if debt_to_equity is not None:
            if debt_to_equity > 2.0:
                score += 15
            elif debt_to_equity > 1.0:
                score += 10
            elif debt_to_equity > 0.5:
                score += 5
        
        return min(score, 100)

