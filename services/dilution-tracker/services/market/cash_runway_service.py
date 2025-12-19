"""
Cash Runway Service
Calculates cash runway using SEC-API.io XBRL data as primary source,
incorporating capital raises and using DilutionTracker.com's methodology:

Formula:
  Estimated Current Cash = Historical Cash + Prorated Operating CF + Capital Raises

Uses:
- SEC-API.io XBRL for financial data (10-Q/10-K)
- Capital raises from 8-K filings
- FMP API as fallback
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

import httpx

from shared.config.settings import settings
from shared.utils.logger import get_logger
from .capital_raise_extractor import get_total_capital_raises

logger = get_logger(__name__)


@dataclass
class CashRunwayResult:
    """Result of cash runway calculation"""
    # Historical data
    historical_cash: float
    historical_cash_date: str
    
    # Cash flow
    quarterly_operating_cf: float
    daily_burn_rate: float
    days_since_report: int
    prorated_cf: float
    
    # Capital raises
    capital_raises_total: float
    capital_raises_count: int
    capital_raises_details: List[Dict]
    
    # Calculated estimates
    estimated_current_cash: float
    runway_days: Optional[int]
    runway_months: Optional[float]
    runway_risk_level: str  # 'critical', 'high', 'medium', 'low'
    
    # Metadata
    data_source: str  # 'sec_xbrl', 'fmp', 'combined'
    last_updated: str
    error: Optional[str]


class CashRunwayService:
    """
    Service to calculate accurate cash runway using SEC data and capital raises.
    Follows DilutionTracker.com methodology.
    """
    
    def __init__(self):
        self.sec_api_key = settings.SEC_API_IO_KEY
        self.fmp_api_key = settings.FMP_API_KEY
        self.base_url = "https://api.sec-api.io"
    
    async def calculate_cash_runway(
        self,
        ticker: str,
        cik: Optional[str] = None
    ) -> CashRunwayResult:
        """
        Calculate cash runway for a ticker using multiple data sources.
        
        Priority:
        1. SEC-API.io XBRL (most accurate, official SEC data)
        2. FMP API (fallback)
        
        Plus capital raises from 8-K filings.
        """
        logger.info("calculating_cash_runway", ticker=ticker)
        
        # Get CIK if not provided
        if not cik:
            cik = await self._get_cik(ticker)
        
        # Try SEC-API.io XBRL first
        xbrl_data = await self._fetch_sec_xbrl_cash(ticker, cik)
        
        if xbrl_data and not xbrl_data.get("error"):
            historical_cash = xbrl_data["cash"]
            historical_date = xbrl_data["date"]
            quarterly_cf = xbrl_data["operating_cf"]
            data_source = "sec_xbrl"
        else:
            # Fallback to FMP
            fmp_data = await self._fetch_fmp_cash(ticker)
            if fmp_data and not fmp_data.get("error"):
                historical_cash = fmp_data["cash"]
                historical_date = fmp_data["date"]
                quarterly_cf = fmp_data["operating_cf"]
                data_source = "fmp"
            else:
                return CashRunwayResult(
                    historical_cash=0,
                    historical_cash_date="",
                    quarterly_operating_cf=0,
                    daily_burn_rate=0,
                    days_since_report=0,
                    prorated_cf=0,
                    capital_raises_total=0,
                    capital_raises_count=0,
                    capital_raises_details=[],
                    estimated_current_cash=0,
                    runway_days=None,
                    runway_months=None,
                    runway_risk_level="unknown",
                    data_source="none",
                    last_updated=datetime.now().isoformat(),
                    error="Could not fetch financial data from any source"
                )
        
        # Calculate days since report
        try:
            report_date = datetime.strptime(historical_date[:10], "%Y-%m-%d")
            days_since = (datetime.now() - report_date).days
        except Exception:
            days_since = 0
        
        # Calculate prorated operating CF
        daily_burn = quarterly_cf / 90 if quarterly_cf else 0  # ~90 days per quarter
        prorated_cf = daily_burn * days_since
        
        # Get capital raises since last report
        capital_raises = await get_total_capital_raises(
            ticker=ticker,
            since_date=historical_date[:10],
            cik=cik
        )
        
        capital_raises_total = capital_raises.get("total_net_proceeds", 0) or capital_raises.get("total_gross_proceeds", 0)
        
        # Calculate estimated current cash using DilutionTracker formula
        # Estimated Cash = Historical Cash + Prorated CF + Capital Raises
        estimated_cash = historical_cash + prorated_cf + capital_raises_total
        
        # Calculate runway
        runway_days = None
        runway_months = None
        runway_risk = "unknown"
        
        if daily_burn < 0:  # Burning cash
            if estimated_cash > 0:
                runway_days = int(estimated_cash / abs(daily_burn))
                runway_months = runway_days / 30
                
                if runway_months < 6:
                    runway_risk = "critical"
                elif runway_months < 12:
                    runway_risk = "high"
                elif runway_months < 24:
                    runway_risk = "medium"
                else:
                    runway_risk = "low"
            else:
                runway_days = 0
                runway_months = 0
                runway_risk = "critical"
        elif daily_burn >= 0:
            runway_risk = "low"  # Cash flow positive or neutral
        
        result = CashRunwayResult(
            historical_cash=historical_cash,
            historical_cash_date=historical_date,
            quarterly_operating_cf=quarterly_cf,
            daily_burn_rate=daily_burn,
            days_since_report=days_since,
            prorated_cf=prorated_cf,
            capital_raises_total=capital_raises_total,
            capital_raises_count=capital_raises.get("raise_count", 0),
            capital_raises_details=capital_raises.get("raises", []),
            estimated_current_cash=estimated_cash,
            runway_days=runway_days,
            runway_months=runway_months,
            runway_risk_level=runway_risk,
            data_source=data_source,
            last_updated=datetime.now().isoformat(),
            error=None
        )
        
        logger.info(
            "cash_runway_calculated",
            ticker=ticker,
            historical_cash=historical_cash,
            prorated_cf=prorated_cf,
            capital_raises=capital_raises_total,
            estimated_cash=estimated_cash,
            runway_months=runway_months,
            source=data_source
        )
        
        return result
    
    async def _get_cik(self, ticker: str) -> Optional[str]:
        """Get CIK for a ticker from SEC-API.io."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self.base_url}?token={self.sec_api_key}",
                    json={
                        "query": {"query_string": {"query": f'ticker:{ticker}'}},
                        "from": "0",
                        "size": "1"
                    },
                    headers={"Content-Type": "application/json"}
                )
                resp.raise_for_status()
                data = resp.json()
                filings = data.get("filings", [])
                if filings:
                    return filings[0].get("cik")
        except Exception as e:
            logger.warning("cik_lookup_failed", ticker=ticker, error=str(e))
        return None
    
    async def _fetch_sec_xbrl_cash(
        self,
        ticker: str,
        cik: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch cash and operating CF from SEC-API.io XBRL endpoint.
        Uses the latest 10-Q or 10-K filing.
        """
        if not self.sec_api_key:
            return None
        
        # Find latest 10-Q or 10-K
        try:
            if cik:
                query = f'cik:{cik} AND (formType:"10-Q" OR formType:"10-K")'
            else:
                query = f'ticker:{ticker} AND (formType:"10-Q" OR formType:"10-K")'
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Search for latest quarterly/annual report
                search_resp = await client.post(
                    f"{self.base_url}?token={self.sec_api_key}",
                    json={
                        "query": {"query_string": {"query": query}},
                        "from": "0",
                        "size": "1",
                        "sort": [{"filedAt": {"order": "desc"}}]
                    },
                    headers={"Content-Type": "application/json"}
                )
                search_resp.raise_for_status()
                search_data = search_resp.json()
                
                filings = search_data.get("filings", [])
                if not filings:
                    logger.warning("no_10q_10k_found", ticker=ticker)
                    return None
                
                filing = filings[0]
                filing_url = filing.get("linkToFilingDetails", "")
                period = filing.get("periodOfReport", "")
                
                # Get XBRL data
                xbrl_url = f"{self.base_url}/xbrl-to-json?htm-url={filing_url}&token={self.sec_api_key}"
                xbrl_resp = await client.get(xbrl_url)
                
                if xbrl_resp.status_code != 200:
                    logger.warning("xbrl_fetch_failed", ticker=ticker, status=xbrl_resp.status_code)
                    return None
                
                xbrl_data = xbrl_resp.json()
                
                # Extract cash
                cash = self._extract_cash_from_xbrl(xbrl_data, period)
                
                # Extract operating cash flow
                operating_cf = self._extract_operating_cf_from_xbrl(xbrl_data, period)
                
                if cash is not None:
                    return {
                        "cash": cash,
                        "date": period,
                        "operating_cf": operating_cf or 0,
                        "source": "sec_xbrl",
                        "filing_url": filing_url
                    }
                
        except Exception as e:
            logger.error("sec_xbrl_fetch_failed", ticker=ticker, error=str(e))
        
        return None
    
    def _extract_cash_from_xbrl(self, xbrl_data: Dict, period: str) -> Optional[float]:
        """Extract cash and cash equivalents from XBRL data."""
        balance_sheet = xbrl_data.get("BalanceSheets", {})
        
        # Priority order of cash concepts
        cash_concepts = [
            # Total cash + short-term investments (most complete)
            "CashCashEquivalentsAndShortTermInvestments",
            # Just cash and equivalents
            "CashAndCashEquivalentsAtCarryingValue",
            # Including restricted cash
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ]
        
        for concept in cash_concepts:
            values = balance_sheet.get(concept, [])
            if not values:
                continue
            
            # Find value for the period
            for val in values:
                val_period = val.get("period", {})
                instant = val_period.get("instant", "")
                
                if instant and instant[:10] == period[:10]:
                    try:
                        return float(val.get("value", 0))
                    except (ValueError, TypeError):
                        continue
        
        # Fallback: sum cash + short-term investments manually
        cash = self._get_xbrl_value(balance_sheet, "CashAndCashEquivalentsAtCarryingValue", period)
        short_term = self._get_xbrl_value(balance_sheet, "ShortTermInvestments", period) or 0
        
        if cash is not None:
            return cash + short_term
        
        return None
    
    def _extract_operating_cf_from_xbrl(self, xbrl_data: Dict, period: str) -> Optional[float]:
        """
        Extract operating cash flow from XBRL data.
        
        Strategy:
        1. First look for quarterly data (80-100 days)
        2. If not found, use YTD data and convert to quarterly average
        """
        cash_flows = xbrl_data.get("StatementsOfCashFlows", {})
        
        cf_concepts = [
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ]
        
        quarterly_cf = None
        ytd_cf = None
        ytd_months = None
        
        for concept in cf_concepts:
            values = cash_flows.get(concept, [])
            if not values:
                continue
            
            for val in values:
                val_period = val.get("period", {})
                end_date = val_period.get("endDate", "")
                start_date = val_period.get("startDate", "")
                
                # Match period end date
                if end_date and end_date[:10] == period[:10]:
                    if start_date:
                        try:
                            start = datetime.strptime(start_date[:10], "%Y-%m-%d")
                            end = datetime.strptime(end_date[:10], "%Y-%m-%d")
                            days = (end - start).days
                            value = float(val.get("value", 0))
                            
                            # Quarterly data (80-100 days)
                            if 80 <= days <= 100:
                                quarterly_cf = value
                                logger.info("found_quarterly_cf", days=days, value=value)
                            # YTD data (more than 100 days) - convert to monthly
                            elif days > 100:
                                months = days / 30
                                ytd_cf = value
                                ytd_months = months
                                logger.info("found_ytd_cf", days=days, months=months, value=value)
                        except Exception:
                            pass
                    else:
                        # No start date, try to use it
                        try:
                            quarterly_cf = float(val.get("value", 0))
                        except (ValueError, TypeError):
                            continue
        
        # Prefer quarterly, but use YTD converted to quarterly if needed
        if quarterly_cf is not None:
            return quarterly_cf
        
        if ytd_cf is not None and ytd_months:
            # Convert YTD to quarterly (3-month) equivalent
            monthly_avg = ytd_cf / ytd_months
            quarterly_avg = monthly_avg * 3
            logger.info("converted_ytd_to_quarterly", 
                       ytd_cf=ytd_cf, 
                       ytd_months=ytd_months, 
                       quarterly_avg=quarterly_avg)
            return quarterly_avg
        
        return None
    
    def _get_xbrl_value(
        self,
        section: Dict,
        concept: str,
        period: str
    ) -> Optional[float]:
        """Get a specific XBRL value for a period."""
        values = section.get(concept, [])
        for val in values:
            val_period = val.get("period", {})
            instant = val_period.get("instant", "")
            if instant and instant[:10] == period[:10]:
                try:
                    return float(val.get("value", 0))
                except (ValueError, TypeError):
                    continue
        return None
    
    async def _fetch_fmp_cash(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Fallback: Fetch cash data from FMP API."""
        if not self.fmp_api_key:
            return None
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Balance Sheet
                bs_url = f"https://financialmodelingprep.com/api/v3/balance-sheet-statement/{ticker}?period=quarter&limit=1&apikey={self.fmp_api_key}"
                bs_resp = await client.get(bs_url)
                bs_resp.raise_for_status()
                bs_data = bs_resp.json()
                
                # Cash Flow
                cf_url = f"https://financialmodelingprep.com/api/v3/cash-flow-statement/{ticker}?period=quarter&limit=1&apikey={self.fmp_api_key}"
                cf_resp = await client.get(cf_url)
                cf_resp.raise_for_status()
                cf_data = cf_resp.json()
                
                if not bs_data or not cf_data:
                    return None
                
                latest_bs = bs_data[0]
                latest_cf = cf_data[0]
                
                # Use cashAndShortTermInvestments (includes liquid assets)
                cash = latest_bs.get("cashAndShortTermInvestments") or (
                    (latest_bs.get("cashAndCashEquivalents") or 0) +
                    (latest_bs.get("shortTermInvestments") or 0)
                )
                
                operating_cf = latest_cf.get("operatingCashFlow") or latest_cf.get("netCashProvidedByOperatingActivities") or 0
                
                return {
                    "cash": cash,
                    "date": latest_bs.get("date"),
                    "operating_cf": operating_cf,
                    "source": "fmp"
                }
                
        except Exception as e:
            logger.error("fmp_cash_fetch_failed", ticker=ticker, error=str(e))
        
        return None


# Convenience function for API endpoints
async def get_enhanced_cash_runway(ticker: str, cik: Optional[str] = None) -> Dict[str, Any]:
    """
    Get enhanced cash runway data for API response.
    
    Returns a dict suitable for JSON serialization.
    """
    service = CashRunwayService()
    result = await service.calculate_cash_runway(ticker, cik)
    
    return {
        "ticker": ticker,
        "historical_cash": result.historical_cash,
        "historical_cash_date": result.historical_cash_date,
        "quarterly_operating_cf": result.quarterly_operating_cf,
        "daily_burn_rate": result.daily_burn_rate,
        "days_since_report": result.days_since_report,
        "prorated_cf": result.prorated_cf,
        "capital_raises": {
            "total": result.capital_raises_total,
            "count": result.capital_raises_count,
            "details": result.capital_raises_details
        },
        "estimated_current_cash": result.estimated_current_cash,
        "runway_days": result.runway_days,
        "runway_months": result.runway_months,
        "runway_risk_level": result.runway_risk_level,
        "data_source": result.data_source,
        "last_updated": result.last_updated,
        "error": result.error,
        "formula": "Estimated Cash = Historical Cash + Prorated CF + Capital Raises"
    }

