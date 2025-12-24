"""
DilutionTracker Risk Scorer
===========================
Implementa los 5 ratings exactos de DilutionTracker.com:

1. Overall Risk - Combinación de los 4 sub-ratings
2. Offering Ability - Capacidad de hacer ofertas dilutivas (shelf capacity)
3. Overhead Supply - Dilución potencial de warrants, ATM, convertibles
4. Historical - Patrón histórico de dilución (O/S growth 3yr)
5. Cash Need - Necesidad de cash basada en runway

Cada rating es: Low / Medium / High
"""

from typing import Dict, Optional, List
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class RiskLevel(Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    UNKNOWN = "Unknown"


@dataclass
class DilutionRiskRatings:
    """Estructura de los 5 ratings de DilutionTracker"""
    overall_risk: RiskLevel
    offering_ability: RiskLevel
    overhead_supply: RiskLevel
    historical: RiskLevel
    cash_need: RiskLevel
    
    # Numeric scores (0-100) for each
    overall_score: int = 0
    offering_ability_score: int = 0
    overhead_supply_score: int = 0
    historical_score: int = 0
    cash_need_score: int = 0
    
    # Details
    details: Dict = None
    
    def to_dict(self) -> Dict:
        return {
            "overall_risk": self.overall_risk.value,
            "offering_ability": self.offering_ability.value,
            "overhead_supply": self.overhead_supply.value,
            "historical": self.historical.value,
            "cash_need": self.cash_need.value,
            "scores": {
                "overall": self.overall_score,
                "offering_ability": self.offering_ability_score,
                "overhead_supply": self.overhead_supply_score,
                "historical": self.historical_score,
                "cash_need": self.cash_need_score
            },
            "details": self.details or {}
        }


class DilutionTrackerRiskScorer:
    """
    Calcula los 5 risk ratings exactos de DilutionTracker.com
    """
    
    def calculate_all_ratings(
        self,
        # Offering Ability inputs
        shelf_capacity_remaining: float = 0,
        has_active_shelf: bool = False,
        has_pending_s1: bool = False,
        
        # Overhead Supply inputs
        warrants_shares: int = 0,
        atm_shares: int = 0,
        convertible_shares: int = 0,
        equity_line_shares: int = 0,
        shares_outstanding: int = 0,  # Used for Overhead Supply (can be fully diluted)
        
        # Historical inputs
        shares_outstanding_3yr_ago: int = 0,
        shares_outstanding_current_sec: Optional[int] = None,  # SEC-reported current (for Historical)
        
        # Cash Need inputs
        runway_months: Optional[float] = None,
        has_positive_operating_cf: bool = False,
        
        # Current price for calculations
        current_price: float = 0
    ) -> DilutionRiskRatings:
        """
        Calculate all 5 DilutionTracker risk ratings
        
        Returns:
            DilutionRiskRatings with all ratings and scores
        """
        try:
            # 1. Offering Ability
            offering_ability, offering_score, offering_details = self._calculate_offering_ability(
                shelf_capacity_remaining=shelf_capacity_remaining,
                has_active_shelf=has_active_shelf,
                has_pending_s1=has_pending_s1
            )
            
            # 2. Overhead Supply
            overhead_supply, overhead_score, overhead_details = self._calculate_overhead_supply(
                warrants_shares=warrants_shares,
                atm_shares=atm_shares,
                convertible_shares=convertible_shares,
                equity_line_shares=equity_line_shares,
                shares_outstanding=shares_outstanding
            )
            
            # 3. Historical
            # Use SEC-reported shares for Historical (not fully diluted)
            # This ensures we compare apples-to-apples: SEC current vs SEC 3yr ago
            shares_for_historical = shares_outstanding_current_sec if shares_outstanding_current_sec else shares_outstanding
            historical, historical_score, historical_details = self._calculate_historical(
                shares_outstanding_current=shares_for_historical,
                shares_outstanding_3yr_ago=shares_outstanding_3yr_ago
            )
            
            # 4. Cash Need
            cash_need, cash_score, cash_details = self._calculate_cash_need(
                runway_months=runway_months,
                has_positive_operating_cf=has_positive_operating_cf
            )
            
            # 5. Overall Risk (combination of the 4 above)
            overall_risk, overall_score = self._calculate_overall_risk(
                offering_ability=offering_ability,
                overhead_supply=overhead_supply,
                historical=historical,
                cash_need=cash_need,
                offering_score=offering_score,
                overhead_score=overhead_score,
                historical_score=historical_score,
                cash_score=cash_score
            )
            
            return DilutionRiskRatings(
                overall_risk=overall_risk,
                offering_ability=offering_ability,
                overhead_supply=overhead_supply,
                historical=historical,
                cash_need=cash_need,
                overall_score=overall_score,
                offering_ability_score=offering_score,
                overhead_supply_score=overhead_score,
                historical_score=historical_score,
                cash_need_score=cash_score,
                details={
                    "offering_ability": offering_details,
                    "overhead_supply": overhead_details,
                    "historical": historical_details,
                    "cash_need": cash_details
                }
            )
            
        except Exception as e:
            logger.error("calculate_all_ratings_failed", error=str(e))
            return DilutionRiskRatings(
                overall_risk=RiskLevel.UNKNOWN,
                offering_ability=RiskLevel.UNKNOWN,
                overhead_supply=RiskLevel.UNKNOWN,
                historical=RiskLevel.UNKNOWN,
                cash_need=RiskLevel.UNKNOWN
            )
    
    def _calculate_offering_ability(
        self,
        shelf_capacity_remaining: float,
        has_active_shelf: bool,
        has_pending_s1: bool
    ) -> tuple[RiskLevel, int, Dict]:
        """
        Offering Ability Rating
        
        DilutionTracker Definition:
        - High: >$20M shelf capacity, active offerings likely
        - Medium: $1M-$20M shelf capacity
        - Low: <$1M shelf capacity or no S-1/S-3
        
        A High rating indicates the company has the ability to conduct 
        a discounted offering through a shelf offering or S-1 offering,
        usually resulting in a sudden and large price drop.
        """
        details = {
            "shelf_capacity_remaining": shelf_capacity_remaining,
            "has_active_shelf": has_active_shelf,
            "has_pending_s1": has_pending_s1
        }
        
        # No shelf and no pending S-1 = Low
        if not has_active_shelf and not has_pending_s1:
            return RiskLevel.LOW, 10, details
        
        # Check capacity thresholds
        if shelf_capacity_remaining > 20_000_000:  # > $20M
            return RiskLevel.HIGH, 90, details
        elif shelf_capacity_remaining >= 1_000_000:  # $1M - $20M
            return RiskLevel.MEDIUM, 50, details
        else:  # < $1M
            return RiskLevel.LOW, 20, details
    
    def _calculate_overhead_supply(
        self,
        warrants_shares: int,
        atm_shares: int,
        convertible_shares: int,
        equity_line_shares: int,
        shares_outstanding: int
    ) -> tuple[RiskLevel, int, Dict]:
        """
        Overhead Supply Rating
        
        DilutionTracker Definition:
        - High: >50% dilution relative to current O/S
        - Medium: 20%-50% dilution
        - Low: <20% dilution
        
        Computes potential dilution relative to current O/S from:
        Warrants, ATM, Convertibles, Equity Lines, and S-1 offerings.
        Note: Does NOT include shelf amounts (covered in Offering Ability).
        """
        total_potential_shares = (
            warrants_shares + 
            atm_shares + 
            convertible_shares + 
            equity_line_shares
        )
        
        details = {
            "warrants_shares": warrants_shares,
            "atm_shares": atm_shares,
            "convertible_shares": convertible_shares,
            "equity_line_shares": equity_line_shares,
            "total_potential_shares": total_potential_shares,
            "shares_outstanding": shares_outstanding,
            "dilution_pct": 0
        }
        
        if shares_outstanding <= 0:
            return RiskLevel.UNKNOWN, 0, details
        
        # Calculate dilution percentage
        dilution_pct = (total_potential_shares / shares_outstanding) * 100
        details["dilution_pct"] = round(dilution_pct, 2)
        
        if dilution_pct > 50:  # >50%
            score = min(90, 50 + int(dilution_pct))
            return RiskLevel.HIGH, score, details
        elif dilution_pct >= 20:  # 20%-50%
            score = 40 + int(dilution_pct)
            return RiskLevel.MEDIUM, score, details
        else:  # <20%
            score = max(10, int(dilution_pct))
            return RiskLevel.LOW, score, details
    
    def _calculate_historical(
        self,
        shares_outstanding_current: int,
        shares_outstanding_3yr_ago: int
    ) -> tuple[RiskLevel, int, Dict]:
        """
        Historical Dilution Rating
        
        DilutionTracker Definition:
        - High: >100% O/S increase over past 3 years
        - Medium: 30%-100% O/S increase
        - Low: <30% O/S increase
        
        Higher historical dilution = more likely company will dilute in future.
        """
        details = {
            "shares_outstanding_current": shares_outstanding_current,
            "shares_outstanding_3yr_ago": shares_outstanding_3yr_ago,
            "increase_pct": 0
        }
        
        if shares_outstanding_3yr_ago <= 0 or shares_outstanding_current <= 0:
            return RiskLevel.UNKNOWN, 0, details
        
        # Calculate percentage increase
        increase_pct = ((shares_outstanding_current - shares_outstanding_3yr_ago) / 
                       shares_outstanding_3yr_ago) * 100
        details["increase_pct"] = round(increase_pct, 2)
        
        # Handle negative (reverse split or buyback scenarios)
        if increase_pct < 0:
            return RiskLevel.LOW, 5, details
        
        if increase_pct > 100:  # >100%
            score = min(95, 70 + int(increase_pct / 5))
            return RiskLevel.HIGH, score, details
        elif increase_pct >= 30:  # 30%-100%
            score = 30 + int(increase_pct / 2)
            return RiskLevel.MEDIUM, score, details
        else:  # <30%
            score = max(5, int(increase_pct))
            return RiskLevel.LOW, score, details
    
    def _calculate_cash_need(
        self,
        runway_months: Optional[float],
        has_positive_operating_cf: bool
    ) -> tuple[RiskLevel, int, Dict]:
        """
        Cash Need Rating
        
        DilutionTracker Definition:
        - High: <6 months of cash runway
        - Medium: 6-24 months of cash runway
        - Low: Positive operating CF or >24 months of runway
        
        A higher cash need = higher probability company will raise capital.
        """
        details = {
            "runway_months": runway_months,
            "has_positive_operating_cf": has_positive_operating_cf
        }
        
        # Positive operating CF = Low risk
        if has_positive_operating_cf:
            return RiskLevel.LOW, 10, details
        
        if runway_months is None:
            return RiskLevel.UNKNOWN, 0, details
        
        if runway_months > 24:  # >24 months
            return RiskLevel.LOW, 15, details
        elif runway_months >= 6:  # 6-24 months
            # Scale: 6mo = 60, 24mo = 30
            score = int(70 - (runway_months - 6) * 2)
            return RiskLevel.MEDIUM, score, details
        else:  # <6 months
            # Scale: 0mo = 100, 6mo = 70
            score = int(100 - runway_months * 5)
            return RiskLevel.HIGH, max(70, score), details
    
    def _calculate_overall_risk(
        self,
        offering_ability: RiskLevel,
        overhead_supply: RiskLevel,
        historical: RiskLevel,
        cash_need: RiskLevel,
        offering_score: int,
        overhead_score: int,
        historical_score: int,
        cash_score: int
    ) -> tuple[RiskLevel, int]:
        """
        Overall Risk Rating
        
        DilutionTracker Definition:
        Higher the dilution risk, higher the probability that share count 
        will increase in the near future due to dilution.
        
        - High rating indicates short bias
        - Low rating indicates long bias
        
        Derived from the four sub ratings with weighted average.
        """
        # Weights for each factor
        # Cash Need and Offering Ability are most important (immediate threats)
        weights = {
            "offering_ability": 0.30,  # Can they offer?
            "overhead_supply": 0.25,   # How much potential dilution?
            "historical": 0.15,        # Track record
            "cash_need": 0.30          # Do they NEED to offer?
        }
        
        # Calculate weighted score
        overall_score = int(
            offering_score * weights["offering_ability"] +
            overhead_score * weights["overhead_supply"] +
            historical_score * weights["historical"] +
            cash_score * weights["cash_need"]
        )
        
        # Alternative: Count High ratings
        high_count = sum([
            1 for r in [offering_ability, overhead_supply, historical, cash_need]
            if r == RiskLevel.HIGH
        ])
        
        # Boost score if multiple HIGH ratings
        if high_count >= 3:
            overall_score = max(overall_score, 85)
        elif high_count >= 2:
            overall_score = max(overall_score, 70)
        
        # Determine level
        if overall_score >= 70:
            return RiskLevel.HIGH, overall_score
        elif overall_score >= 40:
            return RiskLevel.MEDIUM, overall_score
        else:
            return RiskLevel.LOW, overall_score
    
    def get_rating_explanation(self, rating_name: str) -> str:
        """Get explanation text for a rating"""
        explanations = {
            "overall_risk": (
                "Higher the dilution risk, higher the probability that share count "
                "will increase in the near future due to dilution. "
                "High = short bias, Low = long bias."
            ),
            "offering_ability": (
                "Ability to conduct a discounted offering through S-3 shelf or S-1. "
                "High (>$20M) = offerings likely, Low (<$1M) = limited capacity."
            ),
            "overhead_supply": (
                "Potential dilution from Warrants, ATM, Convertibles, Equity Lines "
                "relative to current O/S. High (>50%), Medium (20-50%), Low (<20%)."
            ),
            "historical": (
                "Past dilution pattern over 3 years. "
                "High (>100% O/S increase), Medium (30-100%), Low (<30%)."
            ),
            "cash_need": (
                "Probability of imminent capital raise based on runway. "
                "High (<6mo), Medium (6-24mo), Low (>24mo or positive CF)."
            )
        }
        return explanations.get(rating_name, "")


# Singleton
_dt_risk_scorer: Optional[DilutionTrackerRiskScorer] = None

def get_dt_risk_scorer() -> DilutionTrackerRiskScorer:
    global _dt_risk_scorer
    if _dt_risk_scorer is None:
        _dt_risk_scorer = DilutionTrackerRiskScorer()
    return _dt_risk_scorer

