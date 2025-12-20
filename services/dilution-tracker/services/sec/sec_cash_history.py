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
                    # Recalculate days_since_report and metrics with CURRENT date
                    # So user always sees up-to-date days count
                    last_report = cached.get("last_report_date")
                    if last_report:
                        cached["days_since_report"] = self._days_since(last_report)
                        cached.update(self._calculate_metrics(cached))
                    logger.info("cash_history_from_cache", ticker=ticker, 
                               days_since=cached.get("days_since_report"))
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
                        accession = filing.get("accessionNo", "").replace("-", "")
                        form_type = filing.get("formType", "")
                        
                        if not accession:
                            continue
                        
                        # Get XBRL data
                        xbrl_url = f"{self.base_url}/xbrl-to-json?accession-no={accession}&token={self.sec_api_key}"
                        
                        resp = await client.get(xbrl_url, timeout=20.0)
                        
                        if resp.status_code != 200:
                            continue
                        
                        xbrl_data = resp.json()
                        
                        # Extract ALL periods with cash data from XBRL
                        # This handles both US (10-Q/10-K) and foreign (20-F/6-K) filings
                        # A single filing can contain multiple periods (comparatives)
                        periods_with_cash = self._extract_all_cash_periods(xbrl_data)
                        
                        for period, cash in periods_with_cash:
                            if cash > 0:
                                cash_history.append({
                                    "date": period,
                                    "cash": cash,
                                    "form": form_type,
                                    "source": "SEC-XBRL"
                                })
                        
                        # Extract operating cash flow for each period
                        for period, _ in periods_with_cash:
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
            
            # Deduplicate by date (keep highest cash value for each date)
            cash_by_date = {}
            for entry in cash_history:
                date = entry["date"]
                if date not in cash_by_date or entry["cash"] > cash_by_date[date]["cash"]:
                    cash_by_date[date] = entry
            cash_history = list(cash_by_date.values())
            
            cf_by_date = {}
            for entry in cashflow_history:
                date = entry["date"]
                if date not in cf_by_date:
                    cf_by_date[date] = entry
            cashflow_history = list(cf_by_date.values())
            
            # Sort by date
            cash_history.sort(key=lambda x: x["date"])
            cashflow_history.sort(key=lambda x: x["date"])
            
            # Convert YTD Operating CF to Individual Quarterly OCF
            # SEC XBRL reports YTD values, we need to calculate individual quarters
            individual_cf_history = self._convert_ytd_to_quarterly(cashflow_history)
            
            # Get the latest individual quarterly OCF
            latest_individual_ocf = 0
            if individual_cf_history:
                latest_individual_ocf = individual_cf_history[-1].get("operating_cf", 0)
            
            # Build result
            result = {
                "ticker": ticker,
                "cash_history": cash_history,
                "cashflow_history": individual_cf_history,  # Use converted individual quarters
                "cashflow_history_ytd": cashflow_history,   # Keep original YTD for reference
                "latest_cash": cash_history[-1]["cash"] if cash_history else 0,
                "latest_operating_cf": latest_individual_ocf,  # Individual quarter, not YTD
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
    
    async def _get_cik(self, ticker: str) -> Optional[str]:
        """Get CIK from ticker using SEC-API.io mapping endpoint"""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Try SEC-API.io mapping endpoint
                url = f"https://api.sec-api.io/mapping/ticker/{ticker}?token={self.sec_api_key}"
                resp = await client.get(url)
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data and len(data) > 0:
                        cik = data[0].get("cik")
                        if cik:
                            logger.info("cik_resolved", ticker=ticker, cik=cik)
                            return cik
                
                # Fallback: Search for any filing with this ticker to get CIK
                resp = await client.post(
                    self.base_url,
                    json={
                        "query": {"query_string": {"query": f'ticker:{ticker}'}},
                        "from": 0,
                        "size": 1
                    },
                    headers={"Authorization": self.sec_api_key, "Content-Type": "application/json"}
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    filings = data.get("filings", [])
                    if filings:
                        cik = filings[0].get("cik")
                        if cik:
                            logger.info("cik_resolved_from_filing", ticker=ticker, cik=cik)
                            return cik
                
                logger.warning("cik_not_found", ticker=ticker)
                return None
                
        except Exception as e:
            logger.error("get_cik_failed", ticker=ticker, error=str(e))
            return None
    
    async def _get_all_filings(self, ticker: str, max_filings: int) -> List[Dict]:
        """Get all 10-Q and 10-K filings from SEC-API.io using CIK"""
        try:
            # First resolve CIK from ticker
            cik = await self._get_cik(ticker)
            
            if not cik:
                logger.warning("no_cik_for_ticker", ticker=ticker)
                # Fallback to ticker search
                search_query = f'ticker:{ticker} AND formType:("10-Q" OR "10-K" OR "20-F" OR "6-K")'
            else:
                # Use CIK for more reliable search
                # Include foreign company filings: 20-F (annual) and 6-K (current reports)
                search_query = f'cik:{cik} AND formType:("10-Q" OR "10-K" OR "20-F" OR "6-K")'
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    self.base_url,
                    json={
                        "query": {
                            "query_string": {
                                "query": search_query
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
                filings = data.get("filings", [])
                logger.info("filings_found", ticker=ticker, cik=cik, count=len(filings))
                return filings
                
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
        """
        Get value from XBRL balance sheet for specific period.
        Falls back to most recent value if exact period not found.
        """
        values = data.get(concept, [])
        
        if not values:
            return None
        
        if isinstance(values, dict):
            # Single value
            val_period = values.get("period", {}).get("instant", "")
            val = values.get("value")
            if val is not None and val != "":
                try:
                    return float(val)
                except:
                    return None
        
        if isinstance(values, list):
            # First try exact period match
            for val in values:
                val_period = val.get("period", {}).get("instant", "")
                if val_period[:10] == period[:10]:
                    try:
                        v = val.get("value")
                        if v is not None and v != "":
                            return float(v)
                    except:
                        continue
            
            # Fallback: Get most recent non-null value (sorted by period desc)
            valid_values = []
            for val in values:
                val_period = val.get("period", {}).get("instant", "")
                v = val.get("value")
                # Skip nil values
                if val.get("xsi:nil") == "true":
                    continue
                if v is not None and v != "" and val_period:
                    try:
                        valid_values.append((val_period, float(v)))
                    except:
                        continue
            
            if valid_values:
                # Return most recent value
                valid_values.sort(key=lambda x: x[0], reverse=True)
                return valid_values[0][1]
        
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
    
    def _extract_all_cash_periods(self, xbrl_data: Dict) -> List[tuple]:
        """
        Extract ALL periods with cash data from XBRL.
        Returns list of (period, cash_amount) tuples, sorted by period desc.
        
        This is important because a single filing can contain multiple periods
        (current period + comparatives from previous periods).
        """
        balance_sheet = xbrl_data.get("BalanceSheets", {})
        
        # Cash concepts to check (in priority order)
        cash_concepts = [
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "CashCashEquivalentsAndShortTermInvestments",
            "CashAndCashEquivalentsAtCarryingValue",
            "Cash",
        ]
        
        # Collect cash values by period
        period_cash = {}
        
        for concept in cash_concepts:
            values = balance_sheet.get(concept, [])
            if isinstance(values, list):
                for val in values:
                    if val.get("xsi:nil") == "true":
                        continue
                    period = val.get("period", {}).get("instant", "")
                    cash_val = val.get("value")
                    if period and cash_val and len(period) >= 10:
                        period_key = period[:10]
                        try:
                            cash_float = float(cash_val)
                            # Keep the highest value for each period (in case of duplicates)
                            if period_key not in period_cash or cash_float > period_cash[period_key]:
                                period_cash[period_key] = cash_float
                        except:
                            continue
        
        # Add restricted cash to each period
        restricted_concepts = ["RestrictedCash", "RestrictedCashCurrent"]
        for concept in restricted_concepts:
            values = balance_sheet.get(concept, [])
            if isinstance(values, list):
                for val in values:
                    if val.get("xsi:nil") == "true":
                        continue
                    period = val.get("period", {}).get("instant", "")
                    restricted_val = val.get("value")
                    if period and restricted_val and len(period) >= 10:
                        period_key = period[:10]
                        try:
                            restricted_float = float(restricted_val)
                            if period_key in period_cash:
                                period_cash[period_key] += restricted_float
                        except:
                            continue
        
        # Sort by period descending and return as list of tuples
        result = [(period, cash) for period, cash in period_cash.items()]
        result.sort(key=lambda x: x[0], reverse=True)
        
        return result
    
    def _get_most_recent_period(self, xbrl_data: Dict) -> Optional[str]:
        """
        Extract the most recent period from XBRL data.
        Works for both US (10-Q/10-K) and foreign (20-F/6-K) filings.
        """
        balance_sheet = xbrl_data.get("BalanceSheets", {})
        
        # Collect all periods from balance sheet
        periods = set()
        for concept, values in balance_sheet.items():
            if isinstance(values, list):
                for val in values:
                    period = val.get("period", {}).get("instant", "")
                    if period and len(period) >= 10:
                        periods.add(period[:10])
            elif isinstance(values, dict):
                period = values.get("period", {}).get("instant", "")
                if period and len(period) >= 10:
                    periods.add(period[:10])
        
        if not periods:
            return None
        
        # Return most recent period
        return max(periods)
    
    def _days_since(self, date_str: str) -> int:
        """Calculate days since a date"""
        try:
            report_date = datetime.strptime(date_str, "%Y-%m-%d")
            return (datetime.now() - report_date).days
        except:
            return 0
    
    def _convert_ytd_to_quarterly(self, cashflow_history: List[Dict]) -> List[Dict]:
        """
        Convert Year-To-Date (YTD) Operating CF to Individual Quarterly OCF.
        
        SEC XBRL reports cumulative YTD values:
        - Q1 10-Q: Jan-Mar (Q1 only)
        - Q2 10-Q: Jan-Jun (Q1+Q2)
        - Q3 10-Q: Jan-Sep (Q1+Q2+Q3)
        - Q4 10-K: Full Year
        
        To get individual quarter:
        - Q1: OCF = Q1_YTD
        - Q2: OCF = Q2_YTD - Q1_YTD
        - Q3: OCF = Q3_YTD - Q2_YTD
        - Q4: OCF = Annual - Q3_YTD (or use 10-K directly)
        """
        if not cashflow_history:
            return []
        
        # Sort by date
        sorted_cf = sorted(cashflow_history, key=lambda x: x["date"])
        
        individual_quarters = []
        
        for i, curr in enumerate(sorted_cf):
            curr_date = curr["date"]
            curr_year = curr_date[:4]
            curr_month = curr_date[5:7]
            curr_ocf = curr.get("operating_cf", 0) or 0
            curr_form = curr.get("form", "")
            
            # For 10-K (annual), the OCF is the full year, take as-is or calculate
            if curr_form == "10-K":
                # Find Q3 of same year to calculate Q4
                q3_ocf = None
                for prev in sorted_cf:
                    if prev["date"][:4] == curr_year and prev["date"][5:7] == "09":
                        q3_ocf = prev.get("operating_cf", 0)
                        break
                
                if q3_ocf is not None:
                    individual_ocf = curr_ocf - q3_ocf
                else:
                    # If no Q3, take annual and divide by 4 as approximation
                    individual_ocf = curr_ocf / 4
                    
            # For 10-Q
            elif curr_form == "10-Q":
                # Q1 (March): OCF is already individual
                if curr_month == "03":
                    individual_ocf = curr_ocf
                else:
                    # Q2/Q3: Find previous quarter of same year
                    prev_ocf = None
                    for prev in sorted_cf:
                        prev_year = prev["date"][:4]
                        prev_month = prev["date"][5:7]
                        
                        if prev_year == curr_year and prev.get("form") == "10-Q":
                            # Q2 needs Q1, Q3 needs Q2
                            if curr_month == "06" and prev_month == "03":
                                prev_ocf = prev.get("operating_cf", 0)
                                break
                            elif curr_month == "09" and prev_month == "06":
                                prev_ocf = prev.get("operating_cf", 0)
                                break
                    
                    if prev_ocf is not None:
                        individual_ocf = curr_ocf - prev_ocf
                    else:
                        # No previous quarter found, use as-is (might be first of year)
                        individual_ocf = curr_ocf
            else:
                individual_ocf = curr_ocf
            
            individual_quarters.append({
                "date": curr_date,
                "operating_cf": individual_ocf,
                "operating_cf_ytd": curr_ocf,  # Keep original YTD for reference
                "form": curr_form
            })
        
        return individual_quarters
    
    def _calculate_metrics(self, data: Dict) -> Dict:
        """
        Calculate burn rate, prorated CF, and runway using DilutionTracker methodology:
        - Quarterly CF = YTD Operating CF / Number of quarters in year
        - Prorated CF = (Quarterly CF / 90) × Days since last report
        """
        cf_history = data.get("cashflow_history", [])
        cf_history_ytd = data.get("cashflow_history_ytd", [])
        latest_cash = data.get("latest_cash", 0)
        days_since = data.get("days_since_report", 0)
        
        # DilutionTracker methodology: YTD / quarters in year
        # Get YTD OCF from the last filing
        ytd_ocf = 0
        quarters_in_year = 1
        
        if cf_history_ytd:
            last_cf = cf_history_ytd[-1]
            ytd_ocf = last_cf.get("operating_cf", 0) or 0
            last_date = last_cf.get("date", "")
            
            # Determine quarter number from date (MM = 03, 06, 09, 12)
            if last_date:
                month = last_date[5:7]
                quarter_map = {"03": 1, "06": 2, "09": 3, "12": 4}
                quarters_in_year = quarter_map.get(month, 1)
        
        # Calculate average quarterly CF (DilutionTracker method)
        avg_quarterly_cf = ytd_ocf / quarters_in_year if quarters_in_year > 0 else 0
        
        # Daily burn rate based on average quarterly CF
        daily_burn = abs(avg_quarterly_cf) / 90 if avg_quarterly_cf < 0 else 0
        
        # Prorated CF since last report (DilutionTracker: proportional to days elapsed)
        prorated_cf = (avg_quarterly_cf / 90) * days_since if avg_quarterly_cf else 0
        
        # Estimated current cash = Latest Cash + Prorated CF
        # Note: Capital raises will be added separately by the endpoint
        estimated_cash = latest_cash + prorated_cf
        
        # Runway calculation
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
            "runway_risk_level": risk_level,
            "quarterly_operating_cf": avg_quarterly_cf,  # DilutionTracker: YTD / quarters
            "ytd_operating_cf": ytd_ocf,
            "quarters_in_year": quarters_in_year
        }


# Singleton
_sec_cash_service: Optional[SECCashHistoryService] = None

def get_sec_cash_service(redis: Optional[RedisClient] = None) -> SECCashHistoryService:
    global _sec_cash_service
    if _sec_cash_service is None:
        _sec_cash_service = SECCashHistoryService(redis)
    return _sec_cash_service

