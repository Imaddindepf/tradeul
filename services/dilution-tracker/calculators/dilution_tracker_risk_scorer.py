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
        has_filed_shelf: bool = False,  # Shelf filed but not yet Active/Effective
        filed_shelf_capacity: float = 0,  # Total capacity of filed shelves
        
        # Overhead Supply inputs
        warrants_shares: int = 0,
        atm_shares: int = 0,
        convertible_shares: int = 0,
        equity_line_shares: int = 0,
        shares_outstanding: int = 0,  # Used for Overhead Supply (can be fully diluted)
        
        # Historical inputs
        shares_outstanding_3yr_ago: int = 0,
        shares_outstanding_current_sec: Optional[int] = None,  # SEC-reported current (for Historical)
        has_recent_reverse_split: bool = False,  # Reverse split detected in last 3 years
        reverse_split_factor: float = 1.0,  # e.g., 25.0 for 1:25 reverse split
        shares_history_span_years: float = 3.0,  # How many years of history we actually have
        
        # Cash Need inputs
        runway_months: Optional[float] = None,
        has_positive_operating_cf: bool = False,
        estimated_current_cash: Optional[float] = None,  # Absolute cash amount
        annual_burn_rate: Optional[float] = None,  # Annual operating CF (negative = burning)
        
        # Context
        has_recent_offering: bool = False,  # Company did a recent offering (proves cash need)
        
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
                has_pending_s1=has_pending_s1,
                has_filed_shelf=has_filed_shelf,
                filed_shelf_capacity=filed_shelf_capacity
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
                shares_outstanding_3yr_ago=shares_outstanding_3yr_ago,
                has_recent_reverse_split=has_recent_reverse_split,
                reverse_split_factor=reverse_split_factor,
                shares_history_span_years=shares_history_span_years
            )
            
            # 4. Cash Need
            cash_need, cash_score, cash_details = self._calculate_cash_need(
                runway_months=runway_months,
                has_positive_operating_cf=has_positive_operating_cf,
                estimated_current_cash=estimated_current_cash,
                annual_burn_rate=annual_burn_rate,
                has_recent_offering=has_recent_offering
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
        has_pending_s1: bool,
        has_filed_shelf: bool = False,
        filed_shelf_capacity: float = 0
    ) -> tuple[RiskLevel, int, Dict]:
        """
        Offering Ability Rating
        
        DilutionTracker Definition:
        - High: >$20M shelf capacity, active offerings likely, or pending S-1/F-1
        - Medium: $1M-$20M shelf capacity, or filed shelf with capacity
        - Low: <$1M shelf capacity or no S-1/S-3/F-1
        
        A High rating indicates the company has the ability to conduct 
        a discounted offering through a shelf offering or S-1 offering,
        usually resulting in a sudden and large price drop.
        
        ENHANCED: Also considers:
        - Filed (not yet effective) shelf registrations
        - Pending S-1/F-1 offerings (company actively preparing to offer)
        """
        details = {
            "shelf_capacity_remaining": shelf_capacity_remaining,
            "has_active_shelf": has_active_shelf,
            "has_pending_s1": has_pending_s1,
            "has_filed_shelf": has_filed_shelf,
            "filed_shelf_capacity": filed_shelf_capacity
        }
        
        # Consider combined capacity (active + filed shelves)
        # Filed shelves are nearly as dangerous as active ones - they show intent to dilute
        effective_capacity = shelf_capacity_remaining
        has_any_shelf = has_active_shelf
        
        if has_filed_shelf and filed_shelf_capacity > 0:
            effective_capacity = max(effective_capacity, filed_shelf_capacity)
            has_any_shelf = True
            details["effective_capacity_including_filed"] = effective_capacity
        
        # Pending S-1/F-1 is a STRONG signal of offering ability
        # Company is actively preparing to issue shares
        if has_pending_s1:
            # S-1/F-1 pending = at minimum MEDIUM, but HIGH if combined with shelf
            if has_any_shelf and effective_capacity > 1_000_000:
                return RiskLevel.HIGH, 85, details
            elif effective_capacity > 20_000_000:
                return RiskLevel.HIGH, 90, details
            else:
                # Pending S-1 alone = at least HIGH (company is actively trying to dilute)
                return RiskLevel.HIGH, 80, details
        
        # No shelf and no pending S-1 = Low
        if not has_any_shelf and not has_pending_s1:
            return RiskLevel.LOW, 10, details
        
        # Check capacity thresholds
        if effective_capacity > 20_000_000:  # > $20M
            return RiskLevel.HIGH, 90, details
        elif effective_capacity >= 1_000_000:  # $1M - $20M
            return RiskLevel.MEDIUM, 50, details
        else:  # < $1M but has shelf
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
        shares_outstanding_3yr_ago: int,
        has_recent_reverse_split: bool = False,
        reverse_split_factor: float = 1.0,
        shares_history_span_years: float = 3.0
    ) -> tuple[RiskLevel, int, Dict]:
        """
        Historical Dilution Rating
        
        DilutionTracker Definition:
        - High: >100% O/S increase over past 3 years
        - Medium: 30%-100% O/S increase
        - Low: <30% O/S increase
        
        Higher historical dilution = more likely company will dilute in future.
        
        ENHANCED: Also considers:
        - Reverse splits: A reverse split is a STRONG indicator of past dilution.
          Companies do reverse splits because their share price has dropped below $1,
          typically due to excessive prior dilution. Factor >= 10x = automatic HIGH.
        - Insufficient history: If we only have < 2 years of data (post-split),
          the calculated increase% is unreliable. Use reverse split as proxy.
        """
        details = {
            "shares_outstanding_current": shares_outstanding_current,
            "shares_outstanding_3yr_ago": shares_outstanding_3yr_ago,
            "increase_pct": 0,
            "has_recent_reverse_split": has_recent_reverse_split,
            "reverse_split_factor": reverse_split_factor,
            "shares_history_span_years": round(shares_history_span_years, 1)
        }
        
        # ============================================================
        # STANDARD CALCULATION
        # The shares history is already split-adjusted by SharesDataService.
        # We use the standard DilutionTracker methodology directly:
        # Low: <30%, Medium: 30-100%, High: >100% increase over 3 years.
        # ============================================================
        if shares_outstanding_3yr_ago <= 0 or shares_outstanding_current <= 0:
            # No data - if reverse split happened, that's still informative
            if has_recent_reverse_split:
                return RiskLevel.HIGH, 75, details
            return RiskLevel.UNKNOWN, 0, details
        
        # Calculate percentage increase
        increase_pct = ((shares_outstanding_current - shares_outstanding_3yr_ago) / 
                       shares_outstanding_3yr_ago) * 100
        details["increase_pct"] = round(increase_pct, 2)
        
        # Si el historial es corto (< 2 años, empresa nueva o post-split),
        # usar el incremento real sin extrapolar — igual que DilutionTracker.com.
        # La extrapolación inflaba artificialmente el rating en tickers recientes.
        
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
        has_positive_operating_cf: bool,
        estimated_current_cash: Optional[float] = None,
        annual_burn_rate: Optional[float] = None,
        has_recent_offering: bool = False
    ) -> tuple[RiskLevel, int, Dict]:
        """
        Cash Need Rating
        
        DilutionTracker Definition:
        - High: <6 months of cash runway
        - Medium: 6-24 months of cash runway
        - Low: Positive operating CF or >24 months of runway
        
        A higher cash need = higher probability company will raise capital.
        
        ENHANCED: Also considers:
        - Absolute cash level: < $1M with negative CF = critical regardless of runway
        - Recent offering: If company just did an offering, it PROVES they need cash
        - Borderline cases: 6-9 months with very low cash = effectively HIGH
        """
        details = {
            "runway_months": runway_months,
            "has_positive_operating_cf": has_positive_operating_cf,
            "estimated_current_cash": estimated_current_cash,
            "annual_burn_rate": annual_burn_rate,
            "has_recent_offering": has_recent_offering
        }
        
        # ============================================================
        # RECENT OFFERING OVERRIDE
        # If the company just did an offering, they NEEDED cash.
        # This is the strongest signal of cash need.
        # ============================================================
        if has_recent_offering and not has_positive_operating_cf:
            details["recent_offering_override"] = True
            if runway_months is not None and runway_months < 12:
                return RiskLevel.HIGH, 85, details
            elif estimated_current_cash is not None and estimated_current_cash < 5_000_000:
                return RiskLevel.HIGH, 80, details
        
        # Positive operating CF = Low risk
        if has_positive_operating_cf:
            return RiskLevel.LOW, 10, details
        
        if runway_months is None:
            return RiskLevel.UNKNOWN, 0, details
        
        # Standard DilutionTracker methodology:
        # Low: positive CF or >24 months, Medium: 6-24 months, High: <6 months
        if runway_months > 24:
            return RiskLevel.LOW, 15, details
        elif runway_months >= 6:
            # Scale: 6mo = 70, 24mo = 30
            score = int(70 - (runway_months - 6) * 2)
            return RiskLevel.MEDIUM, max(30, score), details
        else:
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
        Overall Risk Rating — algoritmo exacto de DilutionTracker.com

        Cada sub-rating se convierte: High=2, Medium=1, Low=0
        Suma y = historical + overhead_supply + offering_ability + cash_need
          y >= 6 → High
          y >= 3 → Medium
          y <  3 → Low

        Fuente: código interno DT (función jl / totalDilutionRatingStr)
        """
        def to_num(r: RiskLevel) -> int:
            if r == RiskLevel.HIGH:
                return 2
            elif r == RiskLevel.MEDIUM:
                return 1
            return 0

        total = to_num(historical) + to_num(overhead_supply) + to_num(offering_ability) + to_num(cash_need)

        if total >= 6:
            return RiskLevel.HIGH, total
        elif total >= 3:
            return RiskLevel.MEDIUM, total
        else:
            return RiskLevel.LOW, total
    
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


# ── Redis helpers ─────────────────────────────────────────────────────────────

DILUTION_SCORES_KEY = "dilution:scores:latest"

def _risk_label_to_int(label: str | None) -> Optional[int]:
    """Converts Low/Medium/High to 1/2/3 for numeric filtering."""
    return {"Low": 1, "Medium": 2, "High": 3}.get(label) if label else None


async def write_dilution_scores_to_redis(redis, ticker: str, ratings_dict: dict) -> None:
    """
    Writes dilution risk scores to:
      1. Redis hash dilution:scores:latest  (for real-time enrichment pipeline)
      2. tickers table in dilutiontracker DB  (for SyncDilutionScoresTask batch sync)

    Args:
        redis: RedisClient instance (must be connected)
        ticker: uppercase ticker symbol
        ratings_dict: dict from DilutionRiskRatings.to_dict()
    """
    from datetime import datetime
    import orjson

    _log = None

    overall = ratings_dict.get("overall_risk")
    offering = ratings_dict.get("offering_ability")
    overhead = ratings_dict.get("overhead_supply")
    historical = ratings_dict.get("historical")
    cash_need = ratings_dict.get("cash_need")

    payload = {
        "overall_risk": overall,
        "overall_risk_score": _risk_label_to_int(overall),
        "offering_ability": offering,
        "offering_ability_score": _risk_label_to_int(offering),
        "overhead_supply": overhead,
        "overhead_supply_score": _risk_label_to_int(overhead),
        "historical_dilution": historical,
        "historical_dilution_score": _risk_label_to_int(historical),
        "cash_need": cash_need,
        "cash_need_score": _risk_label_to_int(cash_need),
        "updated_at": datetime.now().isoformat(),
    }

    # 1. Write to Redis hash
    try:
        await redis.client.hset(DILUTION_SCORES_KEY, ticker, orjson.dumps(payload))
    except Exception as exc:
        from shared.utils.logger import get_logger
        _log = get_logger(__name__)
        _log.warning("dilution_scores_redis_write_failed", ticker=ticker, error=str(exc))

    # 2. Persist to local dilution_scores table (so SyncDilutionScoresTask can batch-sync)
    # Uses POSTGRES_HOST/POSTGRES_DB env vars (timescaledb:5432, db=tradeul) — local DB
    # accessible by both dilution-tracker and data_maintenance.
    try:
        import os
        import asyncpg
        _local_conn = await asyncpg.connect(
            host=os.getenv("POSTGRES_HOST", "timescaledb"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            user=os.getenv("POSTGRES_USER", "tradeul_user"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            database=os.getenv("POSTGRES_DB", "tradeul"),
        )
        try:
            await _local_conn.execute(
                """
                INSERT INTO dilution_scores
                    (ticker, overall_risk, overall_risk_score,
                     offering_ability, offering_ability_score,
                     overhead_supply, overhead_supply_score,
                     historical_dilution, historical_dilution_score,
                     cash_need, cash_need_score, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
                ON CONFLICT (ticker) DO UPDATE SET
                    overall_risk              = EXCLUDED.overall_risk,
                    overall_risk_score        = EXCLUDED.overall_risk_score,
                    offering_ability          = EXCLUDED.offering_ability,
                    offering_ability_score    = EXCLUDED.offering_ability_score,
                    overhead_supply           = EXCLUDED.overhead_supply,
                    overhead_supply_score     = EXCLUDED.overhead_supply_score,
                    historical_dilution       = EXCLUDED.historical_dilution,
                    historical_dilution_score = EXCLUDED.historical_dilution_score,
                    cash_need                 = EXCLUDED.cash_need,
                    cash_need_score           = EXCLUDED.cash_need_score,
                    updated_at                = NOW()
                """,
                ticker,
                overall,   _risk_label_to_int(overall),
                offering,  _risk_label_to_int(offering),
                overhead,  _risk_label_to_int(overhead),
                historical, _risk_label_to_int(historical),
                cash_need, _risk_label_to_int(cash_need),
            )
        finally:
            await _local_conn.close()
    except Exception as exc:
        if _log is None:
            from shared.utils.logger import get_logger
            _log = get_logger(__name__)
        _log.debug("dilution_scores_localdb_write_failed", ticker=ticker, error=str(exc))

