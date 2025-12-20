"""
SEC Cash History Service
========================
Obtiene historial completo de cash desde SEC-API.io XBRL.
NO usa FMP - solo datos oficiales de la SEC.

Metodología DilutionTracker:
- Cash = Cash & Equivalents + Short-Term Investments + Restricted Cash
"""

import httpx
from datetime import datetime
from typing import Any, Dict, List, Optional

from shared.config.settings import settings
from shared.utils.logger import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)


class SECCashHistoryService:
    """
    Servicio para obtener historial completo de cash desde SEC-API.io.
    """
    
    def __init__(self, redis: Optional[RedisClient] = None):
        self.redis = redis
        self.sec_api_key = getattr(settings, 'SEC_API_IO_KEY', None) or getattr(settings, 'SEC_API_IO', None)
        self.base_url = "https://api.sec-api.io"
    
    async def get_full_cash_history(self, ticker: str, max_quarters: int = 40) -> Dict[str, Any]:
        """
        Obtener historial COMPLETO de cash desde SEC-API.io XBRL.
        
        Args:
            ticker: Símbolo del ticker
            max_quarters: Máximo de trimestres a obtener (default 40 = 10 años)
        
        Returns:
            {
                "ticker": str,
                "cash_history": [...],
                "cashflow_history": [...],
                "latest_cash": number,
                "latest_operating_cf": number,
                "last_report_date": str,
                "days_since_report": number,
                "source": "sec_xbrl"
            }
        """
        try:
            ticker = ticker.upper()
            
            # Check cache
            if self.redis:
                cache_key = f"sec_dilution:cash_history_full:{ticker}"
                cached = await self.redis.get(cache_key, deserialize=True)
                if cached:
                    logger.info("cash_history_from_cache", ticker=ticker)
                    return cached
            
            if not self.sec_api_key:
                return {"error": "SEC_API_IO key not configured"}
            
            # 1. Get all 10-Q and 10-K filings
            filings = await self._get_all_filings(ticker, max_quarters)
            
            if not filings:
                return {"error": f"No SEC filings found for {ticker}"}
            
            # 2. Extract cash from each filing's XBRL
            cash_history = []
            cashflow_history = []
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                for filing in filings:
                    try:
                        period = filing.get("periodOfReport", "")[:10]
                        accession = filing.get("accessionNo", "").replace("-", "")
                        form_type = filing.get("formType", "")
                        
                        if not accession or not period:
                            continue
                        
                        # Get XBRL data
                        xbrl_url = f"{self.base_url}/xbrl-to-json?accession-no={accession}&token={self.sec_api_key}"
                        
                        resp = await client.get(xbrl_url, timeout=20.0)
                        
                        if resp.status_code != 200:
                            continue
                        
                        xbrl_data = resp.json()
                        
                        # Extract cash (DilutionTracker methodology)
                        cash = self._extract_total_cash(xbrl_data, period)
                        
                        if cash is not None and cash > 0:
                            cash_history.append({
                                "date": period,
                                "cash": cash,
                                "form": form_type,
                                "source": "SEC-XBRL"
                            })
                        
                        # Extract operating cash flow
                        ocf = self._extract_operating_cf(xbrl_data, period)
                        if ocf is not None:
                            cashflow_history.append({
                                "date": period,
                                "operating_cf": ocf,
                                "form": form_type
                            })
                        
                    except Exception as e:
                        logger.warning("filing_xbrl_parse_failed", 
                                      accession=filing.get("accessionNo"), 
                                      error=str(e))
                        continue
            
            # Sort by date
            cash_history.sort(key=lambda x: x["date"])
            cashflow_history.sort(key=lambda x: x["date"])
            
            # Build result
            result = {
                "ticker": ticker,
                "cash_history": cash_history,
                "cashflow_history": cashflow_history,
                "latest_cash": cash_history[-1]["cash"] if cash_history else 0,
                "latest_operating_cf": cashflow_history[-1]["operating_cf"] if cashflow_history else 0,
                "last_report_date": cash_history[-1]["date"] if cash_history else None,
                "days_since_report": self._days_since(cash_history[-1]["date"]) if cash_history else 0,
                "total_quarters": len(cash_history),
                "source": "sec_xbrl",
                "error": None
            }
            
            # Calculate burn rate and runway
            result.update(self._calculate_metrics(result))
            
            # Cache for 6 hours
            if self.redis and cash_history:
                await self.redis.set(cache_key, result, ttl=21600, serialize=True)
            
            logger.info("cash_history_fetched", ticker=ticker, quarters=len(cash_history))
            
            return result
            
        except Exception as e:
            logger.error("get_full_cash_history_failed", ticker=ticker, error=str(e))
            return {"error": str(e)}
    
    async def _get_all_filings(self, ticker: str, max_filings: int) -> List[Dict]:
        """Get all 10-Q and 10-K filings from SEC-API.io"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    self.base_url,
                    json={
                        "query": {
                            "query_string": {
                                "query": f'ticker:{ticker} AND formType:("10-Q" OR "10-K")'
                            }
                        },
                        "from": 0,
                        "size": max_filings,
                        "sort": [{"filedAt": {"order": "desc"}}]
                    },
                    headers={
                        "Authorization": self.sec_api_key,
                        "Content-Type": "application/json"
                    }
                )
                
                if resp.status_code != 200:
                    logger.warning("sec_api_search_failed", status=resp.status_code)
                    return []
                
                data = resp.json()
                return data.get("filings", [])
                
        except Exception as e:
            logger.error("get_all_filings_failed", ticker=ticker, error=str(e))
            return []
    
    def _extract_total_cash(self, xbrl_data: Dict, period: str) -> Optional[float]:
        """
        Extract TOTAL cash following DilutionTracker methodology:
        Cash + Cash Equivalents + Short-Term Investments + Restricted Cash
        """
        balance_sheet = xbrl_data.get("BalanceSheets", {})
        
        total = 0.0
        found_any = False
        
        # 1. Try combined concepts first
        combined_concepts = [
            "CashCashEquivalentsAndShortTermInvestments",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ]
        
        for concept in combined_concepts:
            val = self._get_xbrl_value(balance_sheet, concept, period)
            if val is not None:
                total = val
                found_any = True
                break
        
        # 2. If not found, try individual components
        if not found_any:
            # Cash and Cash Equivalents
            cash = self._get_xbrl_value(balance_sheet, "CashAndCashEquivalentsAtCarryingValue", period)
            if cash:
                total += cash
                found_any = True
            
            # Short-term investments
            investments = self._get_xbrl_value(balance_sheet, "ShortTermInvestments", period)
            if investments:
                total += investments
        
        # 3. Add Restricted Cash (DilutionTracker includes this!)
        restricted_concepts = [
            "RestrictedCash",
            "RestrictedCashCurrent", 
            "RestrictedCashAndCashEquivalents",
        ]
        
        for concept in restricted_concepts:
            val = self._get_xbrl_value(balance_sheet, concept, period)
            if val is not None and val > 0:
                # Only add if not already included in combined concept
                if "Restricted" not in (combined_concepts[0] if found_any else ""):
                    total += val
                break
        
        return total if found_any or total > 0 else None
    
    def _extract_operating_cf(self, xbrl_data: Dict, period: str) -> Optional[float]:
        """Extract operating cash flow from XBRL"""
        cash_flows = xbrl_data.get("StatementsOfCashFlows", {})
        
        ocf_concepts = [
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ]
        
        for concept in ocf_concepts:
            val = self._get_xbrl_value_cf(cash_flows, concept, period)
            if val is not None:
                return val
        
        return None
    
    def _get_xbrl_value(self, data: Dict, concept: str, period: str) -> Optional[float]:
        """Get value from XBRL balance sheet for specific period"""
        values = data.get(concept, [])
        
        if not values:
            return None
        
        if isinstance(values, dict):
            # Single value
            val_period = values.get("period", {}).get("instant", "")
            if val_period[:10] == period[:10]:
                try:
                    return float(values.get("value", 0))
                except:
                    return None
        
        if isinstance(values, list):
            for val in values:
                val_period = val.get("period", {}).get("instant", "")
                if val_period[:10] == period[:10]:
                    try:
                        return float(val.get("value", 0))
                    except:
                        continue
        
        return None
    
    def _get_xbrl_value_cf(self, data: Dict, concept: str, period: str) -> Optional[float]:
        """Get value from XBRL cash flow for specific period"""
        values = data.get(concept, [])
        
        if not values:
            return None
        
        if isinstance(values, list):
            for val in values:
                val_period = val.get("period", {})
                end_date = val_period.get("endDate", "")
                if end_date[:10] == period[:10]:
                    try:
                        return float(val.get("value", 0))
                    except:
                        continue
        
        return None
    
    def _days_since(self, date_str: str) -> int:
        """Calculate days since a date"""
        try:
            report_date = datetime.strptime(date_str, "%Y-%m-%d")
            return (datetime.now() - report_date).days
        except:
            return 0
    
    def _calculate_metrics(self, data: Dict) -> Dict:
        """Calculate burn rate, prorated CF, and runway"""
        cf_history = data.get("cashflow_history", [])
        latest_cash = data.get("latest_cash", 0)
        days_since = data.get("days_since_report", 0)
        
        # Calculate average quarterly burn
        if cf_history and len(cf_history) >= 2:
            recent_cf = [c["operating_cf"] for c in cf_history[-4:]]  # Last 4 quarters
            avg_quarterly_cf = sum(recent_cf) / len(recent_cf)
        else:
            avg_quarterly_cf = data.get("latest_operating_cf", 0)
        
        # Daily burn rate
        daily_burn = abs(avg_quarterly_cf) / 90 if avg_quarterly_cf < 0 else 0
        
        # Prorated CF since last report
        prorated_cf = (avg_quarterly_cf / 90) * days_since if avg_quarterly_cf else 0
        
        # Estimated current cash
        estimated_cash = latest_cash + prorated_cf
        
        # Runway
        if daily_burn > 0:
            runway_days = int(estimated_cash / daily_burn)
            runway_months = runway_days / 30
        else:
            runway_days = None
            runway_months = None
        
        # Risk level
        if runway_months is None:
            risk_level = "low" if avg_quarterly_cf >= 0 else "unknown"
        elif runway_months < 3:
            risk_level = "critical"
        elif runway_months < 6:
            risk_level = "high"
        elif runway_months < 12:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        return {
            "daily_burn_rate": daily_burn,
            "prorated_cf": prorated_cf,
            "estimated_current_cash": estimated_cash,
            "runway_days": runway_days,
            "runway_risk_level": risk_level
        }


# Singleton
_sec_cash_service: Optional[SECCashHistoryService] = None

def get_sec_cash_service(redis: Optional[RedisClient] = None) -> SECCashHistoryService:
    global _sec_cash_service
    if _sec_cash_service is None:
        _sec_cash_service = SECCashHistoryService(redis)
    return _sec_cash_service

