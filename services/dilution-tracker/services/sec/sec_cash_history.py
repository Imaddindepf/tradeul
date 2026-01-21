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
                        
                        # Extract ALL operating cash flow periods from this filing
                        # This captures annual CF from 10-K/20-F that period matching might miss
                        all_ocf = self._extract_all_operating_cf(xbrl_data, form_type)
                        cashflow_history.extend(all_ocf)
                        
                        # Also try period-by-period extraction as fallback
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
            
            # Deduplicate cashflow - keep highest absolute value for each date
            # This ensures we keep annual CF over quarterly CF
            cf_by_date = {}
            for entry in cashflow_history:
                date = entry["date"]
                ocf = entry.get("operating_cf", 0) or 0
                if date not in cf_by_date:
                    cf_by_date[date] = entry
                else:
                    # Keep the one with larger absolute value (annual > quarterly)
                    existing_ocf = cf_by_date[date].get("operating_cf", 0) or 0
                    if abs(ocf) > abs(existing_ocf):
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
            
            # ============================================================
            # FALLBACK: Si no hay datos XBRL, usar Gemini Pro para extraer
            # Esto es común en empresas extranjeras (IFRS, F-1, 20-F, 6-K)
            # ============================================================
            if not cash_history:
                logger.info("no_xbrl_cash_data_trying_ai_extraction", ticker=ticker)
                try:
                    from services.extraction.foreign_financials_extractor import extract_foreign_financials
                    
                    # Obtener company name del primer filing si existe
                    company_name = ""
                    if filings:
                        company_name = filings[0].get("companyName", ticker)
                    
                    ai_result = await extract_foreign_financials(ticker, company_name)
                    
                    if ai_result.get("data_found") and ai_result.get("cash_position", {}).get("total_cash"):
                        cash_data = ai_result["cash_position"]
                        ocf_data = ai_result.get("operating_cash_flow", {})
                        burn_data = ai_result.get("burn_rate_analysis", {})
                        
                        # Construir resultado desde AI
                        result["latest_cash"] = cash_data.get("total_cash", 0)
                        result["last_report_date"] = cash_data.get("period_end_date")
                        result["days_since_report"] = self._days_since(cash_data.get("period_end_date")) if cash_data.get("period_end_date") else 0
                        result["source"] = "gemini_ai_extraction"
                        result["ai_extraction"] = ai_result
                        
                        # Operating CF desde AI
                        if ocf_data.get("quarterly_ocf") is not None:
                            result["latest_operating_cf"] = ocf_data["quarterly_ocf"]
                        elif ocf_data.get("annual_ocf") is not None:
                            # Convertir anual a trimestral
                            result["latest_operating_cf"] = ocf_data["annual_ocf"] / 4
                        
                        # Burn rate y runway desde AI
                        if burn_data.get("monthly_burn_rate"):
                            result["burn_rate_monthly"] = burn_data["monthly_burn_rate"]
                        if burn_data.get("runway_months"):
                            result["estimated_runway_months"] = burn_data["runway_months"]
                        
                        # Recalcular métricas con los nuevos datos
                        result.update(self._calculate_metrics(result))
                        
                        logger.info("ai_cash_extraction_success", 
                                   ticker=ticker, 
                                   cash=result["latest_cash"],
                                   confidence=ai_result.get("data_quality", {}).get("confidence"))
                    else:
                        logger.info("ai_cash_extraction_no_data", ticker=ticker)
                        result["ai_extraction"] = ai_result
                        
                except Exception as ai_err:
                    logger.warning("ai_cash_extraction_failed", ticker=ticker, error=str(ai_err))
                    result["ai_extraction_error"] = str(ai_err)
            
            # Calculate burn rate and runway
            result.update(self._calculate_metrics(result))
            
            # Cache for 6 hours
            if self.redis and (cash_history or result.get("latest_cash")):
                await self.redis.set(cache_key, result, ttl=21600, serialize=True)
            
            logger.info("cash_history_fetched", ticker=ticker, quarters=len(cash_history), source=result.get("source"))
            
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
        """Get all financial filings from SEC-API.io using CIK"""
        try:
            # First resolve CIK from ticker
            cik = await self._get_cik(ticker)
            
            if not cik:
                logger.warning("no_cik_for_ticker", ticker=ticker)
                cik_query = f'ticker:{ticker}'
            else:
                cik_query = f'cik:{cik}'
            
            all_filings = []
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Search 1: Get annual reports (10-K, 20-F) - these have the full year CF
                annual_query = f'{cik_query} AND formType:("10-K" OR "20-F")'
                resp = await client.post(
                    self.base_url,
                    json={
                        "query": {"query_string": {"query": annual_query}},
                        "from": 0,
                        "size": 10,
                        "sort": [{"filedAt": {"order": "desc"}}]
                    },
                    headers={
                        "Authorization": self.sec_api_key,
                        "Content-Type": "application/json"
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    annual_filings = data.get("filings", [])
                    all_filings.extend(annual_filings)
                    logger.info("annual_filings_found", count=len(annual_filings))
                
                # Search 2: Get quarterly/interim reports (10-Q, 6-K)
                interim_query = f'{cik_query} AND formType:("10-Q" OR "6-K" OR "6-K/A")'
                resp = await client.post(
                    self.base_url,
                    json={
                        "query": {"query_string": {"query": interim_query}},
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
                    return all_filings
                
                data = resp.json()
                interim_filings = data.get("filings", [])
                all_filings.extend(interim_filings)
                
                # Deduplicate by accession number
                seen = set()
                unique_filings = []
                for f in all_filings:
                    acc = f.get("accessionNo", "")
                    if acc not in seen:
                        seen.add(acc)
                        unique_filings.append(f)
                
                logger.info("filings_found", ticker=ticker, cik=cik, 
                           annual=len(all_filings) - len(interim_filings),
                           interim=len(interim_filings),
                           total=len(unique_filings))
                return unique_filings
                
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
        """Extract operating cash flow from XBRL for a specific period"""
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
    
    def _extract_all_operating_cf(self, xbrl_data: Dict, form_type: str) -> List[Dict]:
        """
        Extract ALL operating cash flow periods from XBRL.
        This captures annual CF from 10-K/20-F that might be missed.
        """
        cash_flows = xbrl_data.get("StatementsOfCashFlows", {})
        
        ocf_concepts = [
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ]
        
        results = []
        seen_periods = set()
        
        for concept in ocf_concepts:
            values = cash_flows.get(concept, [])
            if not isinstance(values, list):
                continue
            
            for val in values:
                period_data = val.get("period", {})
                end_date = period_data.get("endDate", "")
                
                if not end_date or len(end_date) < 10:
                    continue
                
                period_key = end_date[:10]
                if period_key in seen_periods:
                    continue
                
                try:
                    ocf_value = float(val.get("value", 0))
                    # Skip zero values and keep non-zero
                    if ocf_value != 0:
                        seen_periods.add(period_key)
                        results.append({
                            "date": period_key,
                            "operating_cf": ocf_value,
                            "form": form_type
                        })
                except:
                    continue
        
        return results
    
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
        
        IMPORTANTE: Busca en AMBOS Balance Sheet y Cash Flow Statement.
        El Cash Flow Statement tiene datos de períodos intermedios (Q1, Q2, etc.)
        que no siempre están en el Balance Sheet, especialmente para foreign issuers.
        """
        balance_sheet = xbrl_data.get("BalanceSheets", {})
        cash_flow = xbrl_data.get("StatementsOfCashFlows", {})
        
        # Cash concepts to check in Balance Sheet (in priority order)
        bs_cash_concepts = [
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "CashCashEquivalentsAndShortTermInvestments",
            "CashAndCashEquivalentsAtCarryingValue",
            "Cash",
        ]
        
        # Cash concepts in Cash Flow Statement (ending balance)
        # Este campo tiene datos de todos los períodos intermedios
        cf_cash_concepts = [
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "CashAndCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
        ]
        
        # Collect cash values by period
        period_cash = {}
        
        # 1. Extract from Balance Sheet
        for concept in bs_cash_concepts:
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
                            if cash_float > 0 and (period_key not in period_cash or cash_float > period_cash[period_key]):
                                period_cash[period_key] = cash_float
                        except:
                            continue
        
        # 2. Extract from Cash Flow Statement (has intermediate periods!)
        for concept in cf_cash_concepts:
            values = cash_flow.get(concept, [])
            if isinstance(values, list):
                for val in values:
                    if val.get("xsi:nil") == "true":
                        continue
                    # Cash Flow uses "instant" for ending balance
                    period = val.get("period", {}).get("instant", "")
                    cash_val = val.get("value")
                    if period and cash_val and len(period) >= 10:
                        period_key = period[:10]
                        try:
                            cash_float = float(cash_val)
                            # Only use if > 0 and we don't have a value yet or this is higher
                            if cash_float > 0 and (period_key not in period_cash or cash_float > period_cash[period_key]):
                                period_cash[period_key] = cash_float
                                logger.debug("cash_from_cashflow_statement", 
                                           period=period_key, 
                                           cash=cash_float,
                                           concept=concept)
                        except:
                            continue
        
        # 3. Add restricted cash to each period (from Balance Sheet)
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
        
        logger.info("cash_periods_extracted", 
                   count=len(result),
                   periods=[p[0] for p in result[:5]])
        
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
        - Quarterly CF = Annual Operating CF / 4
        - Prorated CF = (Annual CF / 365) × Days since last report
        
        DilutionTracker uses the most recent ANNUAL operating CF (from 10-K or 20-F),
        not the quarterly CF from interim reports.
        
        IMPORTANTE: Si hay datos de AI extraction, RESPETARLOS en lugar de sobrescribir.
        Esto es crítico para empresas extranjeras (IFRS) sin datos XBRL.
        """
        cf_history_ytd = data.get("cashflow_history_ytd", [])
        latest_cash = data.get("latest_cash", 0)
        days_since = data.get("days_since_report", 0)
        
        # =========================================================================
        # PRIORIDAD 1: Usar datos de AI extraction si existen y son válidos
        # =========================================================================
        ai_extraction = data.get("ai_extraction", {})
        ai_ocf = ai_extraction.get("operating_cash_flow", {})
        ai_burn = ai_extraction.get("burn_rate_analysis", {})
        
        # Si el AI ya calculó annual_ocf, usarlo
        ai_annual_ocf = ai_ocf.get("annual_ocf")
        ai_monthly_burn = ai_burn.get("monthly_burn_rate")
        ai_runway_months = ai_burn.get("runway_months")
        
        has_ai_data = ai_annual_ocf is not None and ai_annual_ocf != 0
        
        if has_ai_data:
            # Usar datos del AI
            annual_ocf = ai_annual_ocf
            quarterly_ocf = annual_ocf / 4
            
            # Calcular daily burn desde monthly burn del AI o desde annual_ocf
            if ai_monthly_burn:
                daily_burn = ai_monthly_burn / 30
            else:
                daily_burn = abs(annual_ocf) / 365 if annual_ocf < 0 else 0
            
            # Prorated CF
            prorated_cf = (annual_ocf / 365) * days_since if annual_ocf else 0
            estimated_cash = latest_cash + prorated_cf
            
            # Runway: usar el del AI si existe, sino calcular
            if ai_runway_months is not None:
                runway_months = ai_runway_months
                runway_days = int(runway_months * 30)
            elif daily_burn > 0:
                runway_days = int(estimated_cash / daily_burn)
                runway_months = runway_days / 30
            else:
                runway_days = None
                runway_months = None
            
            logger.debug("using_ai_extraction_metrics", 
                        annual_ocf=annual_ocf,
                        daily_burn=daily_burn,
                        runway_months=runway_months)
        else:
            # =========================================================================
            # PRIORIDAD 2: Calcular desde XBRL cashflow_history_ytd
            # =========================================================================
            annual_ocf = 0
            quarterly_ocf = 0
            
            # Find the most recent ANNUAL operating CF (from 10-K/20-F, not 10-Q/6-K)
            for cf in reversed(cf_history_ytd):
                ocf = cf.get("operating_cf", 0) or 0
                form = cf.get("form", "")
                date = cf.get("date", "")
                
                # 10-K and 20-F are annual reports
                if form in ["10-K", "20-F"] and ocf != 0:
                    annual_ocf = ocf
                    break
                # Also check for full-year periods (ending in 12 or fiscal year end)
                elif date and date[5:7] in ["12", "09"] and ocf != 0:
                    annual_ocf = ocf
                    break
            
            # Fallback: if no annual found, use the most recent with highest absolute value
            if annual_ocf == 0 and cf_history_ytd:
                annual_ocf = max(cf_history_ytd, key=lambda x: abs(x.get("operating_cf", 0) or 0)).get("operating_cf", 0)
            
            # Calculate quarterly CF = Annual / 4 (DilutionTracker method)
            quarterly_ocf = annual_ocf / 4 if annual_ocf else 0
            
            # Daily burn rate = Annual CF / 365 (DilutionTracker method)
            daily_burn = abs(annual_ocf) / 365 if annual_ocf < 0 else 0
            
            # Prorated CF
            prorated_cf = (annual_ocf / 365) * days_since if annual_ocf else 0
            estimated_cash = latest_cash + prorated_cf
            
            # Runway calculation
            if daily_burn > 0:
                runway_days = int(estimated_cash / daily_burn)
                runway_months = runway_days / 30
            else:
                runway_days = None
                runway_months = None
        
        # =========================================================================
        # RISK LEVEL (común para ambos casos)
        # =========================================================================
        if runway_months is None:
            risk_level = "low" if annual_ocf >= 0 else "unknown"
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
            "quarterly_operating_cf": quarterly_ocf,
            "annual_operating_cf": annual_ocf,
            "ytd_operating_cf": cf_history_ytd[-1].get("operating_cf", 0) if cf_history_ytd else 0,
            "_source": "ai_extraction" if has_ai_data else "xbrl"
        }


# Singleton
_sec_cash_service: Optional[SECCashHistoryService] = None

def get_sec_cash_service(redis: Optional[RedisClient] = None) -> SECCashHistoryService:
    global _sec_cash_service
    if _sec_cash_service is None:
        _sec_cash_service = SECCashHistoryService(redis)
    return _sec_cash_service

