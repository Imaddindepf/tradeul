"""
Cash Runway Service
====================
Servicio para calcular cash runway siguiendo la metodología de DilutionTracker.com:

- Current Cash Estimate: Cash + Marketable Securities + Short-term Investments
- Cash Burn: Quarterly Operating Cash Flow (con ajustes manuales si necesario)
- Capital Raises: Dinero recaudado de offerings completados
- Cash Runway: Cash ÷ (Quarterly Burn ÷ 3)

Fuentes:
- SEC-API.io para datos financieros históricos
- FMP API como fallback
"""

import httpx
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional
from decimal import Decimal

from shared.config.settings import settings
from shared.utils.logger import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)


class CashRunwayService:
    """
    Servicio para calcular cash runway con precisión forense.
    """
    
    def __init__(self, redis: RedisClient):
        self.redis = redis
        self.sec_api_key = settings.SEC_API_IO_KEY
        self.fmp_api_key = settings.FMP_API_KEY
    
    async def get_cash_runway_data(self, ticker: str) -> Dict[str, Any]:
        """
        Obtener datos completos de cash runway.
        
        Returns:
            {
                "ticker": str,
                "current_cash_estimate": {
                    "cash_and_equivalents": number,
                    "marketable_securities": number,
                    "short_term_investments": number,
                    "total": number,
                    "as_of_date": str
                },
                "cash_burn": {
                    "quarterly_operating_cf": number,
                    "monthly_burn_rate": number,
                    "is_cash_positive": bool,
                    "quarters_used": list
                },
                "cash_runway": {
                    "months": number or null,
                    "risk_level": "critical" | "high" | "moderate" | "low" | "healthy",
                    "description": str
                },
                "prorated_operating_cf": {
                    "days_since_report": number,
                    "prorated_burn": number,
                    "adjusted_cash": number
                },
                "capital_raises": {
                    "last_12_months": number,
                    "raises": list
                },
                "historical_cash": list,
                "historical_operating_cf": list
            }
        """
        try:
            ticker = ticker.upper()
            
            # Check cache
            cache_key = f"sec_dilution:cash_runway:{ticker}"
            cached = await self.redis.get(cache_key, deserialize=True)
            if cached:
                logger.info("cash_runway_from_cache", ticker=ticker)
                return cached
            
            # Fetch financial data
            financials = await self._fetch_financials(ticker)
            
            if not financials or "error" in financials:
                return {"error": f"No financial data available for {ticker}"}
            
            # Calculate all components
            current_cash = self._calculate_current_cash(financials)
            cash_burn = self._calculate_cash_burn(financials)
            runway = self._calculate_runway(current_cash["total"], cash_burn["monthly_burn_rate"])
            prorated = self._calculate_prorated_cf(
                current_cash["total"],
                current_cash["as_of_date"],
                cash_burn["monthly_burn_rate"]
            )
            capital_raises = self._extract_capital_raises(financials)
            
            result = {
                "ticker": ticker,
                "current_cash_estimate": current_cash,
                "cash_burn": cash_burn,
                "cash_runway": runway,
                "prorated_operating_cf": prorated,
                "capital_raises": capital_raises,
                "historical_cash": self._build_historical_cash(financials),
                "historical_operating_cf": self._build_historical_cf(financials),
                "chart_data": self._build_chart_data(financials, prorated, capital_raises)
            }
            
            # Cache for 6 hours
            await self.redis.set(cache_key, result, ttl=21600, serialize=True)
            
            logger.info("cash_runway_calculated", ticker=ticker, 
                       runway_months=runway.get("months"),
                       risk_level=runway.get("risk_level"))
            
            return result
            
        except Exception as e:
            logger.error("cash_runway_failed", ticker=ticker, error=str(e))
            return {"error": str(e)}
    
    async def _fetch_financials(self, ticker: str) -> Optional[Dict]:
        """
        Fetch financial statements from SEC-API.io or FMP.
        """
        try:
            # Try SEC-API.io first (more comprehensive)
            if self.sec_api_key:
                data = await self._fetch_from_sec_api(ticker)
                if data:
                    return data
            
            # Fallback to FMP
            if self.fmp_api_key:
                return await self._fetch_from_fmp(ticker)
            
            return None
            
        except Exception as e:
            logger.error("fetch_financials_failed", ticker=ticker, error=str(e))
            return None
    
    async def _fetch_from_sec_api(self, ticker: str) -> Optional[Dict]:
        """Fetch from SEC-API.io XBRL API"""
        try:
            url = f"https://api.sec-api.io/xbrl-to-json"
            
            # Get latest 10-Q and 10-K filings
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Search for recent filings
                search_url = "https://api.sec-api.io"
                query = {
                    "query": {
                        "query_string": {
                            "query": f"ticker:{ticker} AND formType:(\"10-Q\" OR \"10-K\")"
                        }
                    },
                    "from": 0,
                    "size": 12,  # Last 3 years quarterly
                    "sort": [{"filedAt": {"order": "desc"}}]
                }
                
                response = await client.post(
                    search_url,
                    json=query,
                    headers={"Authorization": self.sec_api_key}
                )
                
                if response.status_code != 200:
                    return None
                
                filings = response.json().get("filings", [])
                
                if not filings:
                    return None
                
                # Parse each filing for financial data
                balance_sheets = []
                cash_flows = []
                
                for filing in filings[:8]:  # Last 8 quarters
                    accession = filing.get("accessionNo", "").replace("-", "")
                    if not accession:
                        continue
                    
                    xbrl_url = f"https://api.sec-api.io/xbrl-to-json?accession-no={accession}&token={self.sec_api_key}"
                    
                    try:
                        xbrl_resp = await client.get(xbrl_url, timeout=20.0)
                        if xbrl_resp.status_code == 200:
                            xbrl_data = xbrl_resp.json()
                            
                            # Extract balance sheet data
                            bs = self._extract_balance_sheet(xbrl_data, filing)
                            if bs:
                                balance_sheets.append(bs)
                            
                            # Extract cash flow data
                            cf = self._extract_cash_flow(xbrl_data, filing)
                            if cf:
                                cash_flows.append(cf)
                    except Exception:
                        continue
                
                return {
                    "balance_sheets": balance_sheets,
                    "cash_flows": cash_flows,
                    "source": "SEC-API.io"
                }
                
        except Exception as e:
            logger.warning("sec_api_fetch_failed", ticker=ticker, error=str(e))
            return None
    
    def _extract_balance_sheet(self, xbrl_data: Dict, filing: Dict) -> Optional[Dict]:
        """Extract balance sheet items from XBRL data"""
        try:
            bs = xbrl_data.get("BalanceSheets", {})
            
            # Common XBRL tags for cash items
            cash = (
                self._get_xbrl_value(bs, "CashAndCashEquivalentsAtCarryingValue") or
                self._get_xbrl_value(bs, "Cash") or
                self._get_xbrl_value(bs, "CashCashEquivalentsAndShortTermInvestments") or
                0
            )
            
            marketable_securities = (
                self._get_xbrl_value(bs, "MarketableSecuritiesCurrent") or
                self._get_xbrl_value(bs, "AvailableForSaleSecuritiesCurrent") or
                self._get_xbrl_value(bs, "ShortTermInvestments") or
                0
            )
            
            short_term_investments = (
                self._get_xbrl_value(bs, "ShortTermInvestments") or
                self._get_xbrl_value(bs, "OtherShortTermInvestments") or
                0
            )
            
            # Avoid double counting
            if marketable_securities == short_term_investments:
                short_term_investments = 0
            
            total_assets = self._get_xbrl_value(bs, "Assets") or 0
            total_liabilities = self._get_xbrl_value(bs, "Liabilities") or 0
            
            return {
                "date": filing.get("periodOfReport", filing.get("filedAt", ""))[:10],
                "form": filing.get("formType"),
                "cash_and_equivalents": cash,
                "marketable_securities": marketable_securities,
                "short_term_investments": short_term_investments,
                "total_cash_position": cash + marketable_securities + short_term_investments,
                "total_assets": total_assets,
                "total_liabilities": total_liabilities
            }
        except Exception:
            return None
    
    def _extract_cash_flow(self, xbrl_data: Dict, filing: Dict) -> Optional[Dict]:
        """Extract cash flow items from XBRL data"""
        try:
            cf = xbrl_data.get("StatementsOfCashFlows", {})
            
            operating_cf = (
                self._get_xbrl_value(cf, "NetCashProvidedByUsedInOperatingActivities") or
                self._get_xbrl_value(cf, "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations") or
                0
            )
            
            investing_cf = (
                self._get_xbrl_value(cf, "NetCashProvidedByUsedInInvestingActivities") or
                self._get_xbrl_value(cf, "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations") or
                0
            )
            
            financing_cf = (
                self._get_xbrl_value(cf, "NetCashProvidedByUsedInFinancingActivities") or
                self._get_xbrl_value(cf, "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations") or
                0
            )
            
            # Capital raises from financing activities
            proceeds_from_stock = (
                self._get_xbrl_value(cf, "ProceedsFromIssuanceOfCommonStock") or
                self._get_xbrl_value(cf, "ProceedsFromIssuanceOrSaleOfEquity") or
                self._get_xbrl_value(cf, "ProceedsFromStockOptionsExercised") or
                0
            )
            
            return {
                "date": filing.get("periodOfReport", filing.get("filedAt", ""))[:10],
                "form": filing.get("formType"),
                "operating_cf": operating_cf,
                "investing_cf": investing_cf,
                "financing_cf": financing_cf,
                "proceeds_from_stock": proceeds_from_stock
            }
        except Exception:
            return None
    
    def _get_xbrl_value(self, data: Dict, key: str) -> Optional[float]:
        """Extract value from XBRL data structure"""
        if key in data:
            val = data[key]
            if isinstance(val, dict):
                return float(val.get("value", 0))
            elif isinstance(val, (int, float)):
                return float(val)
            elif isinstance(val, list) and val:
                return float(val[0].get("value", 0) if isinstance(val[0], dict) else val[0])
        return None
    
    async def _fetch_from_fmp(self, ticker: str) -> Optional[Dict]:
        """Fallback to FMP API"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Balance sheets
                bs_url = f"https://financialmodelingprep.com/api/v3/balance-sheet-statement/{ticker}?period=quarter&limit=12&apikey={self.fmp_api_key}"
                bs_resp = await client.get(bs_url)
                
                # Cash flow statements
                cf_url = f"https://financialmodelingprep.com/api/v3/cash-flow-statement/{ticker}?period=quarter&limit=12&apikey={self.fmp_api_key}"
                cf_resp = await client.get(cf_url)
                
                if bs_resp.status_code != 200 or cf_resp.status_code != 200:
                    return None
                
                balance_sheets = []
                for bs in bs_resp.json():
                    balance_sheets.append({
                        "date": bs.get("date"),
                        "form": bs.get("period"),
                        "cash_and_equivalents": bs.get("cashAndCashEquivalents", 0),
                        "marketable_securities": bs.get("shortTermInvestments", 0),
                        "short_term_investments": 0,
                        "total_cash_position": (
                            bs.get("cashAndCashEquivalents", 0) + 
                            bs.get("shortTermInvestments", 0)
                        ),
                        "total_assets": bs.get("totalAssets", 0),
                        "total_liabilities": bs.get("totalLiabilities", 0)
                    })
                
                cash_flows = []
                for cf in cf_resp.json():
                    cash_flows.append({
                        "date": cf.get("date"),
                        "form": cf.get("period"),
                        "operating_cf": cf.get("operatingCashFlow", 0),
                        "investing_cf": cf.get("netCashUsedForInvestingActivites", 0),
                        "financing_cf": cf.get("netCashUsedProvidedByFinancingActivities", 0),
                        "proceeds_from_stock": cf.get("commonStockIssued", 0)
                    })
                
                return {
                    "balance_sheets": balance_sheets,
                    "cash_flows": cash_flows,
                    "source": "FMP"
                }
                
        except Exception as e:
            logger.warning("fmp_fetch_failed", ticker=ticker, error=str(e))
            return None
    
    def _calculate_current_cash(self, financials: Dict) -> Dict:
        """
        Calculate current cash position including marketable securities
        (not just straight cash like other sources)
        """
        balance_sheets = financials.get("balance_sheets", [])
        
        if not balance_sheets:
            return {
                "cash_and_equivalents": 0,
                "marketable_securities": 0,
                "short_term_investments": 0,
                "total": 0,
                "as_of_date": None
            }
        
        # Sort by date descending and get latest
        sorted_bs = sorted(balance_sheets, key=lambda x: x.get("date", ""), reverse=True)
        latest = sorted_bs[0]
        
        cash = latest.get("cash_and_equivalents", 0) or 0
        securities = latest.get("marketable_securities", 0) or 0
        investments = latest.get("short_term_investments", 0) or 0
        
        return {
            "cash_and_equivalents": cash,
            "marketable_securities": securities,
            "short_term_investments": investments,
            "total": cash + securities + investments,
            "as_of_date": latest.get("date")
        }
    
    def _calculate_cash_burn(self, financials: Dict) -> Dict:
        """
        Calculate cash burn using quarterly operating cash flows.
        """
        cash_flows = financials.get("cash_flows", [])
        
        if not cash_flows:
            return {
                "quarterly_operating_cf": 0,
                "monthly_burn_rate": 0,
                "is_cash_positive": False,
                "quarters_used": []
            }
        
        # Sort by date descending
        sorted_cf = sorted(cash_flows, key=lambda x: x.get("date", ""), reverse=True)
        
        # Use last 4 quarters for average (or fewer if not available)
        recent_quarters = sorted_cf[:4]
        
        # Calculate average quarterly operating cash flow
        operating_cfs = [q.get("operating_cf", 0) or 0 for q in recent_quarters]
        avg_quarterly_cf = sum(operating_cfs) / len(operating_cfs) if operating_cfs else 0
        
        # Monthly burn rate (positive = burning cash, negative = generating cash)
        # If operating CF is negative, company is burning cash
        monthly_burn = abs(avg_quarterly_cf) / 3 if avg_quarterly_cf < 0 else 0
        
        return {
            "quarterly_operating_cf": avg_quarterly_cf,
            "monthly_burn_rate": monthly_burn,
            "is_cash_positive": avg_quarterly_cf >= 0,
            "quarters_used": [
                {"date": q.get("date"), "operating_cf": q.get("operating_cf")}
                for q in recent_quarters
            ]
        }
    
    def _calculate_runway(self, total_cash: float, monthly_burn: float) -> Dict:
        """
        Calculate cash runway in months.
        
        Formula: Cash Runway = Total Cash ÷ Monthly Burn Rate
        """
        if monthly_burn <= 0:
            # Company is cash positive or break-even
            return {
                "months": None,
                "risk_level": "healthy",
                "description": "Company is cash flow positive or break-even"
            }
        
        if total_cash <= 0:
            return {
                "months": 0,
                "risk_level": "critical",
                "description": "No cash available"
            }
        
        runway_months = total_cash / monthly_burn
        
        # Determine risk level
        if runway_months < 3:
            risk_level = "critical"
            description = f"Less than 3 months of runway - high dilution risk"
        elif runway_months < 6:
            risk_level = "high"
            description = f"3-6 months runway - likely to raise capital soon"
        elif runway_months < 12:
            risk_level = "moderate"
            description = f"6-12 months runway - may need capital raise within year"
        elif runway_months < 24:
            risk_level = "low"
            description = f"12-24 months runway - comfortable position"
        else:
            risk_level = "healthy"
            description = f"Over 24 months runway - strong cash position"
        
        return {
            "months": round(runway_months, 1),
            "risk_level": risk_level,
            "description": description
        }
    
    def _calculate_prorated_cf(
        self, 
        total_cash: float, 
        report_date: Optional[str],
        monthly_burn: float
    ) -> Dict:
        """
        Calculate prorated cash flow since last report.
        """
        if not report_date:
            return {
                "days_since_report": 0,
                "prorated_burn": 0,
                "adjusted_cash": total_cash
            }
        
        try:
            report_dt = datetime.strptime(report_date, "%Y-%m-%d")
            today = datetime.now()
            days_elapsed = (today - report_dt).days
            
            # Calculate burn since report
            daily_burn = monthly_burn / 30 if monthly_burn > 0 else 0
            prorated_burn = daily_burn * days_elapsed
            
            # Adjusted cash estimate
            adjusted_cash = total_cash - prorated_burn
            
            return {
                "days_since_report": days_elapsed,
                "prorated_burn": round(prorated_burn, 2),
                "adjusted_cash": round(adjusted_cash, 2)
            }
        except Exception:
            return {
                "days_since_report": 0,
                "prorated_burn": 0,
                "adjusted_cash": total_cash
            }
    
    def _extract_capital_raises(self, financials: Dict) -> Dict:
        """
        Extract capital raises from financing cash flows.
        """
        cash_flows = financials.get("cash_flows", [])
        
        if not cash_flows:
            return {"last_12_months": 0, "raises": []}
        
        # Filter last 12 months
        cutoff = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        
        recent_raises = []
        total_raised = 0
        
        for cf in cash_flows:
            cf_date = cf.get("date", "")
            if cf_date >= cutoff:
                proceeds = cf.get("proceeds_from_stock", 0) or 0
                if proceeds > 0:
                    recent_raises.append({
                        "date": cf_date,
                        "amount": proceeds
                    })
                    total_raised += proceeds
        
        return {
            "last_12_months": total_raised,
            "raises": recent_raises
        }
    
    def _build_historical_cash(self, financials: Dict) -> List[Dict]:
        """Build historical cash data for charting"""
        balance_sheets = financials.get("balance_sheets", [])
        
        result = []
        for bs in sorted(balance_sheets, key=lambda x: x.get("date", "")):
            result.append({
                "date": bs.get("date"),
                "cash": bs.get("cash_and_equivalents", 0),
                "marketable_securities": bs.get("marketable_securities", 0),
                "total_cash_position": bs.get("total_cash_position", 0)
            })
        
        return result
    
    def _build_historical_cf(self, financials: Dict) -> List[Dict]:
        """Build historical operating cash flow for charting"""
        cash_flows = financials.get("cash_flows", [])
        
        result = []
        for cf in sorted(cash_flows, key=lambda x: x.get("date", "")):
            result.append({
                "date": cf.get("date"),
                "operating_cf": cf.get("operating_cf", 0),
                "financing_cf": cf.get("financing_cf", 0),
                "proceeds_from_stock": cf.get("proceeds_from_stock", 0)
            })
        
        return result
    
    def _build_chart_data(
        self, 
        financials: Dict,
        prorated: Dict,
        capital_raises: Dict
    ) -> List[Dict]:
        """
        Build chart data with 4 bars:
        1. Historical Cash (from balance sheets)
        2. Prorated Operating Cash Flow (burn since last report)
        3. Capital Raise (if any)
        4. Current Cash Estimate (adjusted)
        """
        balance_sheets = financials.get("balance_sheets", [])
        
        if not balance_sheets:
            return []
        
        # Sort and get historical
        sorted_bs = sorted(balance_sheets, key=lambda x: x.get("date", ""))
        
        chart_data = []
        
        # Historical bars (last 8 quarters)
        for bs in sorted_bs[-8:]:
            chart_data.append({
                "date": bs.get("date"),
                "type": "historical",
                "cash": bs.get("cash_and_equivalents", 0),
                "marketable_securities": bs.get("marketable_securities", 0),
                "total": bs.get("total_cash_position", 0)
            })
        
        # Current estimate bar
        if chart_data:
            last_reported = chart_data[-1]["total"]
            prorated_burn = prorated.get("prorated_burn", 0)
            capital_raised = capital_raises.get("last_12_months", 0)
            
            chart_data.append({
                "date": "Current Est.",
                "type": "estimate",
                "reported_cash": last_reported,
                "prorated_burn": -prorated_burn,  # Negative for outflow
                "capital_raise": capital_raised,
                "total": prorated.get("adjusted_cash", last_reported)
            })
        
        return chart_data

