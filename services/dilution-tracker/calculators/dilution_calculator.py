"""
Dilution Calculator
Calcula métricas de dilución histórica y proyecciones
"""

import sys
sys.path.append('/app')

from typing import List, Dict, Optional
from datetime import date
from decimal import Decimal

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class DilutionCalculator:
    """
    Calcula métricas de dilución basado en shares outstanding histórico
    """
    
    def calculate_dilution_percentage(
        self,
        shares_current: int,
        shares_previous: int
    ) -> Optional[Decimal]:
        """
        Calcular % de dilución entre dos períodos
        
        Args:
            shares_current: Shares outstanding actuales
            shares_previous: Shares outstanding anteriores
        
        Returns:
            % de dilución (positivo = dilución, negativo = buyback)
        """
        try:
            if shares_previous == 0:
                return None
            
            change = shares_current - shares_previous
            pct_change = (change / shares_previous) * 100
            
            return round(Decimal(str(pct_change)), 2)
            
        except Exception as e:
            logger.error("calculate_dilution_pct_failed", error=str(e))
            return None
    
    def calculate_historical_dilution(
        self,
        financials: List[Dict]
    ) -> Dict:
        """
        Calcular dilución histórica desde financials
        
        Args:
            financials: Lista de financial statements ordenados por fecha
                       [{'period_date': date, 'shares_outstanding': int}]
        
        Returns:
            Dict con métricas de dilución
        """
        try:
            if not financials or len(financials) < 2:
                return {
                    'shares_current': None,
                    'shares_1y_ago': None,
                    'shares_3y_ago': None,
                    'shares_5y_ago': None,
                    'dilution_pct_1y': None,
                    'dilution_pct_3y': None,
                    'dilution_pct_5y': None
                }
            
            # Ordenar por fecha (más reciente primero)
            sorted_financials = sorted(
                financials,
                key=lambda x: x['period_date'],
                reverse=True
            )
            
            # Filtrar solo los que tienen shares_outstanding
            valid_financials = [
                f for f in sorted_financials
                if f.get('shares_outstanding') is not None
            ]
            
            if not valid_financials:
                return {
                    'shares_current': None,
                    'shares_1y_ago': None,
                    'shares_3y_ago': None,
                    'shares_5y_ago': None,
                    'dilution_pct_1y': None,
                    'dilution_pct_3y': None,
                    'dilution_pct_5y': None
                }
            
            # Shares actuales (más reciente)
            current = valid_financials[0]
            shares_current = current['shares_outstanding']
            current_date = current['period_date']
            
            # Buscar shares históricos
            shares_1y_ago = self._find_shares_n_years_ago(valid_financials, current_date, years=1)
            shares_3y_ago = self._find_shares_n_years_ago(valid_financials, current_date, years=3)
            shares_5y_ago = self._find_shares_n_years_ago(valid_financials, current_date, years=5)
            
            # Calcular dilución
            dilution_1y = None
            if shares_1y_ago:
                dilution_1y = self.calculate_dilution_percentage(shares_current, shares_1y_ago)
            
            dilution_3y = None
            if shares_3y_ago:
                dilution_3y = self.calculate_dilution_percentage(shares_current, shares_3y_ago)
            
            dilution_5y = None
            if shares_5y_ago:
                dilution_5y = self.calculate_dilution_percentage(shares_current, shares_5y_ago)
            
            return {
                'shares_current': shares_current,
                'shares_1y_ago': shares_1y_ago,
                'shares_3y_ago': shares_3y_ago,
                'shares_5y_ago': shares_5y_ago,
                'dilution_pct_1y': dilution_1y,
                'dilution_pct_3y': dilution_3y,
                'dilution_pct_5y': dilution_5y
            }
            
        except Exception as e:
            logger.error("calculate_historical_dilution_failed", error=str(e))
            return {}
    
    def _find_shares_n_years_ago(
        self,
        financials: List[Dict],
        current_date: date,
        years: int
    ) -> Optional[int]:
        """
        Encontrar shares outstanding de N años atrás
        
        Busca el financial más cercano a la fecha objetivo
        """
        from datetime import timedelta
        
        target_date = current_date.replace(year=current_date.year - years)
        
        # Buscar el financial más cercano a target_date
        closest = None
        min_diff = None
        
        for financial in financials:
            date_diff = abs((financial['period_date'] - target_date).days)
            
            # Solo considerar si está dentro de ~6 meses de la fecha objetivo
            if date_diff <= 180:
                if min_diff is None or date_diff < min_diff:
                    min_diff = date_diff
                    closest = financial
        
        return closest['shares_outstanding'] if closest else None
    
    def calculate_dilution_risk_score(
        self,
        dilution_1y: Optional[Decimal],
        dilution_2y: Optional[Decimal],
        recent_offerings_count: int = 0,
        has_active_shelf: bool = False
    ) -> int:
        """
        Calcular score de riesgo de dilución (0-100)
        
        Args:
            dilution_1y: % dilución último año
            dilution_2y: % dilución últimos 2 años
            recent_offerings_count: Número de offerings últimos 12 meses
            has_active_shelf: Si tiene S-3 activo
        
        Returns:
            Score 0-100 (100 = máximo riesgo de dilución)
        """
        score = 0
        
        # 1. Dilución histórica 1 año (30 puntos)
        if dilution_1y is not None:
            if dilution_1y > 50:
                score += 30
            elif dilution_1y > 25:
                score += 25
            elif dilution_1y > 10:
                score += 15
            elif dilution_1y > 5:
                score += 10
        
        # 2. Dilución histórica 2 años (20 puntos)
        if dilution_2y is not None:
            if dilution_2y > 100:
                score += 20
            elif dilution_2y > 50:
                score += 15
            elif dilution_2y > 25:
                score += 10
        
        # 3. Offerings recientes (30 puntos)
        if recent_offerings_count >= 3:
            score += 30
        elif recent_offerings_count >= 2:
            score += 20
        elif recent_offerings_count >= 1:
            score += 10
        
        # 4. Active shelf registration (20 puntos)
        if has_active_shelf:
            score += 20
        
        return min(score, 100)
    
    def project_future_dilution(
        self,
        current_shares: int,
        historical_dilution_rate: Decimal,
        months: int = 12
    ) -> List[Dict]:
        """
        Proyectar dilución futura basado en rate histórico
        
        Args:
            current_shares: Shares actuales
            historical_dilution_rate: Rate de dilución anual histórico (%)
            months: Meses a proyectar
        
        Returns:
            Lista de proyecciones
        """
        try:
            projections = []
            
            # Rate mensual (asumiendo compounding)
            monthly_rate = (1 + historical_dilution_rate / 100) ** (1/12) - 1
            
            shares = current_shares
            
            for month in range(1, months + 1):
                shares = int(shares * (1 + monthly_rate))
                
                projections.append({
                    'month': month,
                    'projected_shares': shares,
                    'dilution_from_current': round(
                        ((shares - current_shares) / current_shares) * 100, 2
                    )
                })
            
            return projections
            
        except Exception as e:
            logger.error("project_future_dilution_failed", error=str(e))
            return []
    
    def analyze_dilution_velocity(
        self,
        financials: List[Dict]
    ) -> Dict:
        """
        Analizar velocidad de dilución (acelerando/desacelerando)
        
        Args:
            financials: Lista de financial statements
        
        Returns:
            Dict con análisis de velocidad
        """
        try:
            if not financials or len(financials) < 4:
                return {'velocity': 'unknown', 'accelerating': None}
            
            # Ordenar por fecha
            sorted_financials = sorted(
                financials,
                key=lambda x: x['period_date']
            )
            
            # Calcular dilución quarter-over-quarter
            qoq_dilutions = []
            
            for i in range(1, len(sorted_financials)):
                prev = sorted_financials[i-1]
                curr = sorted_financials[i]
                
                if prev.get('shares_outstanding') and curr.get('shares_outstanding'):
                    dilution = self.calculate_dilution_percentage(
                        curr['shares_outstanding'],
                        prev['shares_outstanding']
                    )
                    
                    if dilution is not None:
                        qoq_dilutions.append(float(dilution))
            
            if len(qoq_dilutions) < 3:
                return {'velocity': 'unknown', 'accelerating': None}
            
            # Analizar últimos 3 quarters
            recent = qoq_dilutions[-3:]
            
            # Velocidad está acelerando si cada quarter tiene más dilución
            accelerating = recent[0] < recent[1] < recent[2]
            decelerating = recent[0] > recent[1] > recent[2]
            
            if accelerating:
                velocity = 'accelerating'
            elif decelerating:
                velocity = 'decelerating'
            else:
                velocity = 'stable'
            
            avg_qoq = sum(recent) / len(recent)
            
            return {
                'velocity': velocity,
                'accelerating': accelerating,
                'decelerating': decelerating,
                'avg_qoq_dilution': round(avg_qoq, 2),
                'latest_qoq_dilution': round(recent[-1], 2)
            }
            
        except Exception as e:
            logger.error("analyze_dilution_velocity_failed", error=str(e))
            return {'velocity': 'unknown', 'accelerating': None}

