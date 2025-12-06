"""
Enhanced Data Fetcher for SEC Dilution Analysis
Includes:
- SEC-API /float endpoint for shares outstanding history
- FMP balance sheet + cash flow for cash position/runway
- Pre-screening logic for Grok optimization
- Deduplication utilities
"""

import asyncio
import hashlib
import json
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

import httpx

from shared.config.settings import settings
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# ============== CACHE CONFIG ==============
CACHE_DIR = Path("/tmp/filing_cache")
CACHE_DIR.mkdir(exist_ok=True)

# ============== FILING PRIORITY (PRE-SCREENING) ==============
# Tier 1: SIEMPRE contienen dilución → procesar completo con Grok
TIER1_CRITICAL = {"424B3", "424B4", "424B5", "S-1", "S-1/A", "S-3", "S-3/A", "S-3ASR", "POS AM", "F-1", "F-1/A", "F-3", "F-3/A"}

# Tier 2: PUEDEN contener dilución → pre-screen con keywords antes de Grok
# Incluye DEF 14A (proxy statements que pueden autorizar más shares)
TIER2_PRESCAN = {"8-K", "8-K/A", "6-K", "6-K/A", "EFFECT", "DEF 14A", "DEFA14A", "DEF 14C"}

# Tier 3: SKIP - No procesar con Grok (usar APIs estructuradas en su lugar)
# 10-Q/10-K → datos vienen de SEC-API /float y FMP balance sheet
TIER3_SKIP = {"10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A", "NT 10-K", "NT 10-Q"}

# Keywords críticos para pre-screening (dilución directa)
DILUTION_KEYWORDS_CRITICAL = [
    "securities purchase agreement", "spa", "subscription agreement",
    "warrant", "pre-funded warrant", "prefunded warrant",
    "convertible note", "convertible debenture", "conversion price",
    "at-the-market", "atm offering", "atm program", "sales agreement",
    "equity line", "eloc", "committed equity",
    "registered direct", "pipe", "private placement",
    "shelf registration", "prospectus supplement",
    "exercise price", "shares issuable", "aggregate offering",
]

# Keywords específicos para DEF 14A (proxy statements)
DEF14A_KEYWORDS = [
    "authorize additional shares",
    "increase authorized",
    "authorized share capital",
    "stock split",
    "reverse stock split",
    "equity incentive plan",
    "stock option plan",
    "employee stock purchase",
    "amendment to certificate of incorporation",
    "increase in authorized common stock",
]


class EnhancedDataFetcher:
    """
    Enhanced data fetcher with SEC-API /float, FMP financials, 
    pre-screening, and deduplication.
    """
    
    def __init__(self):
        self.sec_api_key = settings.SEC_API_IO_KEY
        self.fmp_api_key = settings.FMP_API_KEY
        
    # ============== SEC-API /FLOAT - SHARES OUTSTANDING HISTORY ==============
    
    async def fetch_shares_history(self, ticker: str) -> Dict[str, Any]:
        """
        Obtiene el historial de shares outstanding desde SEC-API /float endpoint.
        Fuente oficial de la SEC - más precisa que FMP.
        
        Returns:
            Dict con historial de shares, dilución calculada, y métricas.
        """
        if not self.sec_api_key:
            logger.warning("sec_api_key_missing_for_float")
            return {"error": "SEC_API_KEY not configured"}
        
        url = f"https://api.sec-api.io/float?ticker={ticker}&token={self.sec_api_key}"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.error("fetch_shares_history_failed", ticker=ticker, error=str(e))
            return {"error": f"Error fetching shares history: {e}"}
        
        if not data or not isinstance(data, dict):
            return {"error": "Invalid response from SEC-API"}
        
        records = data.get("data", [])
        if not records:
            return {"error": "No shares history data available"}
        
        # Ordenar por fecha de reporte (más reciente primero)
        records_sorted = sorted(records, key=lambda x: x.get("periodOfReport", ""), reverse=True)
        
        def get_total_outstanding(record: Dict) -> int:
            float_data = record.get("float", {})
            outstanding_list = float_data.get("outstandingShares", [])
            total = 0
            for item in outstanding_list:
                try:
                    total += int(item.get("value", 0))
                except (ValueError, TypeError):
                    continue
            return total
        
        def get_public_float(record: Dict) -> int:
            float_data = record.get("float", {})
            public_float_list = float_data.get("publicFloat", [])
            if public_float_list:
                try:
                    return int(public_float_list[0].get("value", 0))
                except (ValueError, TypeError):
                    pass
            return 0
        
        # Datos actuales (más reciente)
        current = records_sorted[0]
        current_outstanding = get_total_outstanding(current)
        current_public_float = get_public_float(current)
        current_date = current.get("periodOfReport", "")
        source_filing = current.get("sourceFilingAccessionNo", "")
        
        # Calcular dilución histórica
        now = datetime.now()
        one_year_ago = (now - timedelta(days=365)).strftime("%Y-%m-%d")
        six_months_ago = (now - timedelta(days=180)).strftime("%Y-%m-%d")
        three_months_ago = (now - timedelta(days=90)).strftime("%Y-%m-%d")
        
        def find_closest(target_date: str) -> Optional[Dict]:
            closest = None
            min_diff = float('inf')
            for record in records_sorted:
                record_date = record.get("periodOfReport", "")
                if record_date:
                    try:
                        diff = abs((datetime.strptime(record_date[:10], "%Y-%m-%d") -
                                   datetime.strptime(target_date, "%Y-%m-%d")).days)
                        if diff < min_diff:
                            min_diff = diff
                            closest = record
                    except:
                        continue
            return closest if min_diff < 120 else None  # Tolerancia de 120 días
        
        def calc_dilution(old_shares: int, new_shares: int) -> float:
            if old_shares > 0:
                return ((new_shares - old_shares) / old_shares) * 100
            return 0.0
        
        year_ago_data = find_closest(one_year_ago)
        six_mo_data = find_closest(six_months_ago)
        three_mo_data = find_closest(three_months_ago)
        oldest = records_sorted[-1] if records_sorted else None
        
        result = {
            "source": "SEC-API (official SEC data)",
            "current": {
                "date": current_date,
                "outstanding_shares": current_outstanding,
                "public_float_usd": current_public_float,
                "source_filing": source_filing,
            },
            "historical": [],
            "dilution_summary": {},
            "all_records": [],
        }
        
        # Historial para el gráfico
        for record in records_sorted:
            result["all_records"].append({
                "period": record.get("periodOfReport"),
                "outstanding_shares": get_total_outstanding(record),
                "source_filing": record.get("sourceFilingAccessionNo"),
            })
        
        # Calcular métricas de dilución
        if three_mo_data:
            tm_outstanding = get_total_outstanding(three_mo_data)
            dilution = round(calc_dilution(tm_outstanding, current_outstanding), 1)
            result["historical"].append({
                "period": "3 months ago",
                "date": three_mo_data.get("periodOfReport", ""),
                "outstanding_shares": tm_outstanding,
                "dilution_since": dilution,
            })
            result["dilution_summary"]["3_months"] = dilution
        
        if six_mo_data:
            sm_outstanding = get_total_outstanding(six_mo_data)
            dilution = round(calc_dilution(sm_outstanding, current_outstanding), 1)
            result["historical"].append({
                "period": "6 months ago",
                "date": six_mo_data.get("periodOfReport", ""),
                "outstanding_shares": sm_outstanding,
                "dilution_since": dilution,
            })
            result["dilution_summary"]["6_months"] = dilution
        
        if year_ago_data:
            yr_outstanding = get_total_outstanding(year_ago_data)
            dilution = round(calc_dilution(yr_outstanding, current_outstanding), 1)
            result["historical"].append({
                "period": "1 year ago",
                "date": year_ago_data.get("periodOfReport", ""),
                "outstanding_shares": yr_outstanding,
                "dilution_since": dilution,
            })
            result["dilution_summary"]["1_year"] = dilution
        
        if oldest and oldest != current:
            old_outstanding = get_total_outstanding(oldest)
            dilution = round(calc_dilution(old_outstanding, current_outstanding), 1)
            result["dilution_summary"]["all_time"] = dilution
        
        logger.info("shares_history_fetched", ticker=ticker, records=len(records_sorted))
        return result
    
    # ============== FMP CASH POSITION & RUNWAY ==============
    
    async def fetch_cash_data(self, ticker: str) -> Dict[str, Any]:
        """
        Obtiene datos de cash position y cash flow de FMP API.
        Calcula runway estimado basado en burn rate.
        """
        if not self.fmp_api_key:
            return {"error": "FMP_API_KEY not configured"}
        
        result = {
            "error": None,
            "cash_history": [],
            "cashflow_history": [],
            "latest_cash": None,
            "latest_operating_cf": None,
            "last_report_date": None,
            "days_since_report": None,
            "daily_burn_rate": None,
            "prorated_cf": None,
            "estimated_current_cash": None,
            "runway_days": None,
            "runway_risk_level": "unknown",
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Balance Sheet
                bs_url = f"https://financialmodelingprep.com/api/v3/balance-sheet-statement/{ticker}?period=quarter&limit=12&apikey={self.fmp_api_key}"
                bs_resp = await client.get(bs_url)
                bs_resp.raise_for_status()
                bs_data = bs_resp.json()
                
                # Cash Flow Statement
                cf_url = f"https://financialmodelingprep.com/api/v3/cash-flow-statement/{ticker}?period=quarter&limit=12&apikey={self.fmp_api_key}"
                cf_resp = await client.get(cf_url)
                cf_resp.raise_for_status()
                cf_data = cf_resp.json()
            
            if not bs_data or not cf_data:
                result["error"] = "No financial data available"
                return result
            
            # Parse cash history
            for item in bs_data:
                cash = item.get("cashAndCashEquivalents") or item.get("cashAndShortTermInvestments") or 0
                result["cash_history"].append({
                    "date": item.get("date"),
                    "cash": cash,
                    "total_assets": item.get("totalAssets", 0),
                    "total_liabilities": item.get("totalLiabilities", 0),
                })
            
            # Parse cash flow history
            for item in cf_data:
                result["cashflow_history"].append({
                    "date": item.get("date"),
                    "operating_cf": item.get("operatingCashFlow") or item.get("netCashProvidedByOperatingActivities") or 0,
                    "investing_cf": item.get("netCashUsedForInvestingActivites", 0),
                    "financing_cf": item.get("netCashUsedProvidedByFinancingActivities", 0),
                    "net_income": item.get("netIncome", 0),
                })
            
            # Calculate estimates
            if bs_data and cf_data:
                latest_bs = bs_data[0]
                latest_cf = cf_data[0]
                
                result["latest_cash"] = latest_bs.get("cashAndCashEquivalents") or latest_bs.get("cashAndShortTermInvestments") or 0
                result["latest_operating_cf"] = latest_cf.get("operatingCashFlow") or latest_cf.get("netCashProvidedByOperatingActivities") or 0
                result["last_report_date"] = latest_cf.get("date")
                
                # Calculate days since report
                if result["last_report_date"]:
                    try:
                        last_date = datetime.strptime(result["last_report_date"], "%Y-%m-%d")
                        today = datetime.now()
                        result["days_since_report"] = (today - last_date).days
                    except:
                        result["days_since_report"] = 0
                
                # Calculate burn rate and prorated CF
                quarterly_cf = result["latest_operating_cf"] or 0
                result["daily_burn_rate"] = quarterly_cf / 90  # ~90 days per quarter
                
                if result["days_since_report"]:
                    result["prorated_cf"] = result["daily_burn_rate"] * result["days_since_report"]
                    result["estimated_current_cash"] = (result["latest_cash"] or 0) + result["prorated_cf"]
                
                # Calculate runway
                if result["estimated_current_cash"] and result["daily_burn_rate"] and result["daily_burn_rate"] < 0:
                    result["runway_days"] = int(result["estimated_current_cash"] / abs(result["daily_burn_rate"]))
                    runway_months = result["runway_days"] / 30
                    
                    if runway_months < 6:
                        result["runway_risk_level"] = "critical"
                    elif runway_months < 12:
                        result["runway_risk_level"] = "high"
                    elif runway_months < 24:
                        result["runway_risk_level"] = "medium"
                    else:
                        result["runway_risk_level"] = "low"
                elif result["daily_burn_rate"] and result["daily_burn_rate"] >= 0:
                    result["runway_risk_level"] = "low"  # Cash flow positive
            
            logger.info("cash_data_fetched", ticker=ticker, 
                       cash=result["latest_cash"], 
                       runway_days=result["runway_days"])
            
        except Exception as e:
            result["error"] = f"Error fetching cash data: {e}"
            logger.error("fetch_cash_data_failed", ticker=ticker, error=str(e))
        
        return result
    
    async def fetch_current_price(self, ticker: str) -> Optional[float]:
        """Obtiene el precio actual del ticker usando FMP API."""
        if not self.fmp_api_key:
            return None
        
        url = f"https://financialmodelingprep.com/api/v3/quote/{ticker}?apikey={self.fmp_api_key}"
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                if data and len(data) > 0:
                    return data[0].get("price")
        except Exception as e:
            logger.warning("fetch_current_price_failed", ticker=ticker, error=str(e))
        
        return None


# ============== PRE-SCREENING LOGIC ==============

def get_filing_tier(form_type: str) -> int:
    """
    Classify filing by priority tier.
    1 = CRITICAL (always has dilution info) → Always send to Grok
    2 = PRE-SCAN (may have dilution) → Check keywords first
    3 = SKIP (no procesar con Grok, usar APIs estructuradas)
    """
    form_upper = form_type.upper().strip()
    
    if form_upper in TIER1_CRITICAL:
        return 1
    if form_upper in TIER2_PRESCAN:
        return 2
    if form_upper in TIER3_SKIP:
        return 3
    # Default: skip unknown form types
    return 3


def quick_dilution_scan(text: str, form_type: Optional[str] = None) -> Tuple[bool, List[str]]:
    """
    Fast pre-screening for dilution keywords.
    Uses specific keywords for DEF 14A forms.
    Returns (has_dilution, matched_keywords)
    """
    text_lower = text.lower()
    matches = []
    
    # Usar keywords específicos para DEF 14A
    if form_type and form_type.upper() in ("DEF 14A", "DEFA14A", "DEF 14C"):
        keywords_to_check = DEF14A_KEYWORDS + DILUTION_KEYWORDS_CRITICAL
    else:
        keywords_to_check = DILUTION_KEYWORDS_CRITICAL
    
    for kw in keywords_to_check:
        if kw in text_lower:
            matches.append(kw)
    
    return len(matches) > 0, matches


def should_process_with_grok(form_type: str, text: str) -> Tuple[bool, str]:
    """
    Determine if a filing should be processed with Grok.
    Returns (should_process, reason)
    """
    tier = get_filing_tier(form_type)
    
    if tier == 1:
        return True, f"Tier 1 critical filing ({form_type})"
    
    if tier == 2:
        has_dilution, keywords = quick_dilution_scan(text, form_type)
        if has_dilution:
            return True, f"Tier 2 with keywords: {', '.join(keywords[:3])}"
        return False, "Tier 2 but no dilution keywords found"
    
    # Tier 3: SKIP - usar APIs estructuradas (SEC-API /float, FMP)
    return False, f"Tier 3 filing ({form_type}) - use structured APIs instead"


# ============== DEDUPLICATION LOGIC ==============

def normalize_number(val: Any) -> Optional[float]:
    """Normalize numeric values for comparison."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, str):
        cleaned = val.replace(",", "").replace("$", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def generate_instrument_key(item: Dict[str, Any], instrument_type: str) -> str:
    """Generate a unique key for deduplication based on key fields."""
    
    if instrument_type == "warrant":
        issue_date = item.get("issue_date") or "unknown"
        exercise_price = normalize_number(item.get("exercise_price"))
        price_str = f"{exercise_price:.4f}" if exercise_price else "unknown"
        
        notes = (item.get("notes") or "").lower()
        if "pre-funded" in notes or "prefunded" in notes:
            wtype = "prefunded"
        elif "series a" in notes:
            wtype = "series_a"
        elif "exchange" in notes:
            wtype = "exchange"
        elif "ipo" in notes or "public" in notes:
            wtype = "ipo"
        else:
            wtype = "other"
        
        return f"warrant_{issue_date}_{price_str}_{wtype}"
    
    elif instrument_type == "convertible":
        principal = normalize_number(item.get("total_principal_amount"))
        principal_str = f"{principal:.0f}" if principal else "unknown"
        issue_date = item.get("issue_date") or "unknown"
        return f"convertible_{issue_date}_{principal_str}"
    
    elif instrument_type == "atm":
        offering_date = item.get("offering_date") or item.get("filing_date") or "unknown"
        amount = normalize_number(item.get("total_capacity") or item.get("registered_amount"))
        amount_str = f"{amount:.0f}" if amount else "unknown"
        return f"atm_{offering_date}_{amount_str}"
    
    elif instrument_type == "shelf":
        form_type = item.get("registration_statement") or item.get("form_type") or "unknown"
        reg_date = item.get("filing_date") or item.get("registration_date") or "unknown"
        return f"shelf_{form_type}_{reg_date}"
    
    elif instrument_type == "equity_line":
        agreement_date = item.get("agreement_date") or item.get("agreement_start_date") or "unknown"
        counterparty = (item.get("counterparty") or "unknown").lower().replace(" ", "_")[:20]
        return f"eloc_{agreement_date}_{counterparty}"
    
    return f"unknown_{hash(str(item))}"


def merge_items(existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """Merge two items, preferring non-null values and more complete data."""
    merged = existing.copy()
    
    for key, new_val in new.items():
        if key == "source_filings":
            existing_sources = existing.get("source_filings", [])
            new_sources = new.get("source_filings", [])
            merged["source_filings"] = list(set(existing_sources + new_sources))
        elif key == "notes":
            existing_notes = existing.get("notes") or ""
            new_notes = new.get("notes") or ""
            if new_notes and new_notes not in existing_notes:
                merged["notes"] = f"{existing_notes} | {new_notes}" if existing_notes else new_notes
        else:
            existing_val = existing.get(key)
            if new_val is not None and new_val != "" and new_val != "null":
                if existing_val is None or existing_val == "" or existing_val == "null":
                    merged[key] = new_val
                elif key in ["outstanding", "potential_new_shares", "total_principal_amount"]:
                    new_num = normalize_number(new_val)
                    existing_num = normalize_number(existing_val)
                    if new_num and existing_num and new_num > existing_num:
                        merged[key] = new_val
    
    return merged


def deduplicate_instruments(items: List[Dict[str, Any]], instrument_type: str) -> List[Dict[str, Any]]:
    """Deduplicate and consolidate instruments by key fields."""
    if not items:
        return []
    
    consolidated: Dict[str, Dict[str, Any]] = {}
    
    for item in items:
        key = generate_instrument_key(item, instrument_type)
        if key in consolidated:
            consolidated[key] = merge_items(consolidated[key], item)
        else:
            consolidated[key] = item.copy()
    
    # Sort by date descending
    result = list(consolidated.values())
    date_field = {
        "warrant": "issue_date",
        "convertible": "issue_date", 
        "atm": "filing_date",
        "shelf": "filing_date",
        "equity_line": "agreement_date"
    }.get(instrument_type, "issue_date")
    
    result.sort(key=lambda x: x.get(date_field) or "", reverse=True)
    
    return result


def calculate_confidence_score(item: Dict[str, Any], instrument_type: str) -> float:
    """Calculate confidence score (0-1) based on data completeness."""
    
    required_fields = {
        "warrant": ["issue_date", "exercise_price", "outstanding", "expiration_date"],
        "convertible": ["total_principal_amount", "conversion_price", "issue_date", "maturity_date"],
        "atm": ["filing_date", "total_capacity", "status"],
        "shelf": ["filing_date", "registration_statement", "total_capacity"],
        "equity_line": ["agreement_date", "total_capacity", "counterparty"],
    }
    
    required = required_fields.get(instrument_type, [])
    if not required:
        return 0.5
    
    filled = sum(1 for field in required if item.get(field) is not None and item.get(field) != "")
    
    return round(filled / len(required), 2)


# ============== RISK FLAGS ==============

def identify_risk_flags(
    warrants: List[Dict],
    convertibles: List[Dict],
    atm_offerings: List[Dict],
    shares_history: Optional[Dict] = None,
    cash_data: Optional[Dict] = None
) -> List[Dict[str, str]]:
    """Identify dilution risk flags."""
    flags = []
    
    # Check for toxic convertibles (variable conversion price)
    for c in convertibles:
        conv_price = str(c.get("conversion_price") or "").lower()
        if any(kw in conv_price for kw in ["discount", "variable", "floor", "market", "vwap"]):
            flags.append({
                "type": "critical",
                "icon": "⚠️",
                "message": "TOXIC CONVERTIBLE: Variable/discount conversion price detected"
            })
            break
    
    # Check for large warrant overhang
    total_warrant_shares = sum(
        normalize_number(w.get("potential_new_shares") or w.get("outstanding")) or 0
        for w in warrants
    )
    if total_warrant_shares > 10_000_000:
        flags.append({
            "type": "warning",
            "icon": "⚠️",
            "message": f"LARGE WARRANT OVERHANG: {total_warrant_shares:,.0f} potential shares"
        })
    
    # Check for active ATM
    active_atms = [a for a in atm_offerings if (a.get("status") or "").lower() == "active"]
    if active_atms:
        flags.append({
            "type": "warning",
            "icon": "⚠️",
            "message": f"ACTIVE ATM PROGRAM: {len(active_atms)} active ATM(s)"
        })
    
    # Check for recent dilutive filings (last 90 days)
    cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    recent_warrants = [w for w in warrants if (w.get("issue_date") or "") >= cutoff]
    if recent_warrants:
        flags.append({
            "type": "warning",
            "icon": "⚠️",
            "message": f"RECENT DILUTION: {len(recent_warrants)} warrant issuance(s) in last 90 days"
        })
    
    # Check for historical dilution from shares outstanding
    if shares_history and "error" not in shares_history:
        dilution_summary = shares_history.get("dilution_summary", {})
        
        if dilution_summary.get("3_months", 0) > 30:
            flags.append({
                "type": "critical",
                "icon": "🔴",
                "message": f"SEVERE RECENT DILUTION: {dilution_summary['3_months']:+.1f}% shares increase in 3 months"
            })
        elif dilution_summary.get("3_months", 0) > 15:
            flags.append({
                "type": "warning",
                "icon": "⚠️",
                "message": f"HIGH RECENT DILUTION: {dilution_summary['3_months']:+.1f}% shares increase in 3 months"
            })
        
        if dilution_summary.get("1_year", 0) > 100:
            flags.append({
                "type": "critical",
                "icon": "🔴",
                "message": f"EXTREME YEARLY DILUTION: {dilution_summary['1_year']:+.1f}% shares increase in 1 year"
            })
    
    # Check cash runway
    if cash_data and "error" not in cash_data:
        runway_risk = cash_data.get("runway_risk_level", "unknown")
        runway_days = cash_data.get("runway_days")
        
        if runway_risk == "critical" and runway_days:
            flags.append({
                "type": "critical",
                "icon": "🔴",
                "message": f"CRITICAL CASH RUNWAY: Only {runway_days} days ({runway_days/30:.1f} months) remaining"
            })
        elif runway_risk == "high" and runway_days:
            flags.append({
                "type": "warning",
                "icon": "⚠️",
                "message": f"LOW CASH RUNWAY: {runway_days} days ({runway_days/30:.1f} months) remaining"
            })
    
    return flags

