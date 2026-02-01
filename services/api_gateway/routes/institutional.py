"""
Institutional Holdings API - Form 13F Data
Provides access to SEC Form 13F institutional holdings data via SEC-API.io

FULL DATA - No simplifications. Maximum detail level.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/institutional", tags=["institutional"])

# SEC API client will be injected from main.py
sec_api_client = None


async def warmup_sec_api_connection():
    """Warmup the SEC-API connection to avoid slow first request"""
    global sec_api_client
    if sec_api_client:
        try:
            # Make a minimal request to establish connection
            await sec_api_client.search_13f_holdings(ticker="AAPL", size=1)
            logger.info("sec_api_connection_warmed_up")
        except Exception as e:
            logger.warning("sec_api_warmup_failed", error=str(e))

def set_sec_api_client(client):
    global sec_api_client
    sec_api_client = client


def get_previous_quarter(period: str) -> str:
    """Get the previous quarter end date from a period string (e.g., 2025-12-31 -> 2025-09-30)"""
    try:
        d = datetime.strptime(period, "%Y-%m-%d")
        # Go back 3 months
        if d.month <= 3:
            prev = d.replace(year=d.year - 1, month=12, day=31)
        elif d.month <= 6:
            prev = d.replace(month=3, day=31)
        elif d.month <= 9:
            prev = d.replace(month=6, day=30)
        else:
            prev = d.replace(month=9, day=30)
        return prev.strftime("%Y-%m-%d")
    except:
        return ""


def aggregate_holdings_by_cik(filings: List[Dict], ticker: str) -> Dict[str, Dict]:
    """
    Aggregate holdings by CIK (fund) from a list of filings.
    Preserves ALL data - no simplifications.
    """
    holders_by_cik: Dict[str, Dict[str, Any]] = {}
    
    for filing in filings:
        cik = filing.get("cik", "")
        if not cik:
            continue
            
        holdings = filing.get("holdings", [])
        period_of_report = filing.get("periodOfReport", "")
        filed_at = filing.get("filedAt", "")
        
        # Find all holdings for this ticker in this filing
        ticker_holdings = [
            h for h in holdings 
            if h.get("ticker", "").upper() == ticker.upper()
        ]
        
        if not ticker_holdings:
            continue
        
        # Aggregate by investment discretion type
        by_discretion = {}
        for h in ticker_holdings:
            disc = h.get("investmentDiscretion", "UNKNOWN")
            if disc not in by_discretion:
                by_discretion[disc] = {
                    "shares": 0,
                    "value": 0,
                    "votingSole": 0,
                    "votingShared": 0,
                    "votingNone": 0,
                }
            by_discretion[disc]["shares"] += h.get("shrsOrPrnAmt", {}).get("sshPrnamt", 0)
            by_discretion[disc]["value"] += h.get("value", 0)
            va = h.get("votingAuthority", {})
            by_discretion[disc]["votingSole"] += va.get("Sole", 0)
            by_discretion[disc]["votingShared"] += va.get("Shared", 0)
            by_discretion[disc]["votingNone"] += va.get("None", 0)
        
        # Total shares and value
        total_shares = sum(d["shares"] for d in by_discretion.values())
        total_value = sum(d["value"] for d in by_discretion.values())
        total_voting_sole = sum(d["votingSole"] for d in by_discretion.values())
        total_voting_shared = sum(d["votingShared"] for d in by_discretion.values())
        total_voting_none = sum(d["votingNone"] for d in by_discretion.values())
        
        # Get additional info from first holding
        first_holding = ticker_holdings[0]
        
        # Check for puts/calls
        has_put = any(h.get("putCall") == "Put" for h in ticker_holdings)
        has_call = any(h.get("putCall") == "Call" for h in ticker_holdings)
        
        # Only add if this is the first or more recent filing for this CIK
        if cik not in holders_by_cik or filed_at > holders_by_cik[cik].get("filedAt", ""):
            holders_by_cik[cik] = {
                "cik": cik,
                "name": filing.get("companyName", "Unknown"),
                "nameOfIssuer": first_holding.get("nameOfIssuer", ""),
                "cusip": first_holding.get("cusip", ""),
                "titleOfClass": first_holding.get("titleOfClass", ""),
                "shares": total_shares,
                "value": total_value,
                "sharesType": first_holding.get("shrsOrPrnAmt", {}).get("sshPrnamtType", "SH"),
                "filedAt": filed_at,
                "periodOfReport": period_of_report,
                "accessionNo": filing.get("accessionNo", ""),
                "formType": filing.get("formType", ""),
                "linkToFilingDetails": filing.get("linkToFilingDetails", ""),
                "linkToHtml": filing.get("linkToHtml", ""),
                "hasPut": has_put,
                "hasCall": has_call,
                "investmentDiscretion": by_discretion,
                "votingAuthority": {
                    "sole": total_voting_sole,
                    "shared": total_voting_shared,
                    "none": total_voting_none,
                },
            }
    
    return holders_by_cik


@router.get("/holders/{ticker}")
async def get_holders_by_ticker(
    ticker: str,
    period: Optional[str] = Query(None, description="Quarter period (e.g., 2024-09-30)"),
    size: int = Query(50, ge=1, le=100, description="Number of results to return"),
    from_index: int = Query(0, ge=0, description="Pagination offset"),
):
    """
    Get all institutional holders for a specific ticker.
    
    Returns FULL DATA - no simplifications:
    - Aggregated by CIK (fund)
    - Investment discretion breakdown (SOLE, DFND, OTR)
    - Voting authority details
    - QoQ changes when available
    - Links to SEC filings
    
    IMPORTANT: Fetches multiple pages to get accurate QoQ comparisons.
    """
    if not sec_api_client:
        raise HTTPException(status_code=503, detail="SEC API client not available")
    
    try:
        import asyncio
        import time
        from datetime import datetime, date
        start_time = time.time()
        ticker_upper = ticker.upper()
        
        # Calculate current and previous quarter end dates
        def get_quarter_end_dates():
            today = date.today()
            year = today.year
            month = today.month
            
            # 13F filings are due 45 days after quarter end
            # Q4 (Dec 31) -> filed by Feb 14
            # Q1 (Mar 31) -> filed by May 15
            # Q2 (Jun 30) -> filed by Aug 14
            # Q3 (Sep 30) -> filed by Nov 14
            # Use the most recent quarter with available filings
            if month == 1:
                # January: Q4 filings arriving, use Q4 of previous year
                current_q_end = date(year - 1, 12, 31)
            elif month == 2:
                # February: Q4 filings should be complete
                current_q_end = date(year - 1, 12, 31)
            elif month in [3, 4]:
                # Mar-Apr: Q4 complete
                current_q_end = date(year - 1, 12, 31)
            elif month == 5:
                # May: Q1 filings arriving
                current_q_end = date(year, 3, 31)
            elif month in [6, 7]:
                # Jun-Jul: Q1 complete
                current_q_end = date(year, 3, 31)
            elif month == 8:
                # Aug: Q2 filings arriving
                current_q_end = date(year, 6, 30)
            elif month in [9, 10]:
                # Sep-Oct: Q2 complete
                current_q_end = date(year, 6, 30)
            elif month == 11:
                # Nov: Q3 filings arriving
                current_q_end = date(year, 9, 30)
            else:  # month == 12
                # Dec: Q3 complete
                current_q_end = date(year, 9, 30)
            
            prev_q_end = get_previous_quarter(current_q_end.strftime("%Y-%m-%d"))
            return current_q_end.strftime("%Y-%m-%d"), prev_q_end
        
        current_period, prev_period = get_quarter_end_dates()
        if period:  # User specified a period
            current_period = period
            prev_period = get_previous_quarter(period)
        
        logger.info("holders_fetch_start", ticker=ticker_upper, current_period=current_period, prev_period=prev_period)
        
        # Helper to fetch a single page with timing
        async def fetch_page(ticker: str, period_filter: str, page: int):
            t0 = time.time()
            try:
                data = await sec_api_client.search_13f_holdings(
                    ticker=ticker,
                    period_of_report=period_filter,
                    size=50,
                    from_index=page * 50
                )
                logger.info("fetch_page_done", period=period_filter, page=page, elapsed_ms=int((time.time()-t0)*1000))
                return data
            except Exception as e:
                logger.warning("fetch_page_failed", period=period_filter, page=page, error=str(e))
                return {"data": [], "total": {"value": 0}}
        
        # Fetch BOTH quarters page 0 in parallel (2 calls)
        initial_tasks = [
            fetch_page(ticker_upper, current_period, 0),
            fetch_page(ticker_upper, prev_period, 0)
        ]
        initial_results = await asyncio.gather(*initial_tasks)
        
        current_page0 = initial_results[0]
        prev_page0 = initial_results[1]
        total = current_page0.get("total", {}).get("value", 0)
        
        all_current_filings = current_page0.get("data", [])
        all_prev_filings = prev_page0.get("data", [])
        
        logger.info("holders_initial_done", total=total, current=len(all_current_filings), prev=len(all_prev_filings), elapsed_ms=int((time.time()-start_time)*1000))
        
        # Fetch additional pages if needed (2 more pages per quarter = 100 more filings each)
        if total > 50:
            pages_to_fetch = min(2, (total // 50))  # 1-2 more pages
            
            extra_tasks = []
            for page in range(1, pages_to_fetch + 1):
                extra_tasks.append(fetch_page(ticker_upper, current_period, page))
                extra_tasks.append(fetch_page(ticker_upper, prev_period, page))
            
            extra_results = await asyncio.gather(*extra_tasks)
            
            for i, result in enumerate(extra_results):
                if i % 2 == 0:  # Current quarter
                    all_current_filings.extend(result.get("data", []))
                else:  # Previous quarter
                    all_prev_filings.extend(result.get("data", []))
        
        logger.info("holders_fetch_done", 
                   ticker=ticker_upper,
                   current_filings=len(all_current_filings),
                   prev_filings=len(all_prev_filings),
                   elapsed_ms=int((time.time()-start_time)*1000))
        
        # Aggregate by CIK
        current_by_cik = aggregate_holdings_by_cik(all_current_filings, ticker_upper)
        prev_by_cik = aggregate_holdings_by_cik(all_prev_filings, ticker_upper) if all_prev_filings else {}
        
        # Calculate changes
        holders = []
        for cik, current in current_by_cik.items():
            prev = prev_by_cik.get(cik)
            
            if prev:
                # Existing position - calculate change
                prev_shares = prev["shares"]
                current_shares = current["shares"]
                change_shares = current_shares - prev_shares
                change_percent = ((current_shares - prev_shares) / prev_shares * 100) if prev_shares > 0 else 0
                
                current["changeShares"] = change_shares
                current["changePercent"] = round(change_percent, 2)
                current["prevShares"] = prev_shares
                current["prevValue"] = prev["value"]
                current["isNew"] = False
            else:
                # New position (not in previous quarter)
                current["changeShares"] = current["shares"]
                current["changePercent"] = None  # null = new position, not 100%
                current["isNew"] = True
            
            holders.append(current)
        
        # Check for closed positions (in prev but not in current)
        for cik, prev in prev_by_cik.items():
            if cik not in current_by_cik:
                holders.append({
                    **prev,
                    "shares": 0,
                    "value": 0,
                    "changeShares": -prev["shares"],
                    "changePercent": -100.0,
                    "prevShares": prev["shares"],
                    "prevValue": prev["value"],
                    "isClosed": True,
                })
        
        # Sort by value (largest first)
        holders.sort(key=lambda x: x["value"], reverse=True)
        
        # Calculate totals
        active_holders = [h for h in holders if h["value"] > 0]
        total_value = sum(h["value"] for h in active_holders)
        total_shares = sum(h["shares"] for h in active_holders)
        
        # Stats
        new_positions = sum(1 for h in holders if h.get("isNew"))
        increased = sum(1 for h in holders if h.get("changePercent") is not None and h.get("changePercent", 0) > 0)
        decreased = sum(1 for h in holders if h.get("changePercent") is not None and h.get("changePercent", 0) < 0 and h.get("changePercent") != -100)
        closed = sum(1 for h in holders if h.get("isClosed"))
        unchanged = sum(1 for h in holders if h.get("changePercent") == 0)
        
        return {
            "ticker": ticker_upper,
            "currentPeriod": current_period,
            "previousPeriod": prev_period,
            "totalHolders": len(active_holders),
            "totalValue": total_value,
            "totalShares": total_shares,
            "totalFilings": total,
            "stats": {
                "newPositions": new_positions,
                "increased": increased,
                "decreased": decreased,
                "unchanged": unchanged,
                "closed": closed,
            },
            "holders": holders[:size],
        }
        
    except Exception as e:
        logger.error("get_holders_by_ticker_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fund/{cik}")
async def get_fund_holdings(
    cik: str,
    size: int = Query(100, ge=1, le=200, description="Number of holdings to return"),
):
    """
    Get FULL fund profile and ALL holdings for a specific fund (by CIK).
    
    Returns complete 13F filing data including:
    - Fund profile from cover page
    - All holdings with full details
    - Voting authority breakdown
    - Investment discretion types
    """
    if not sec_api_client:
        raise HTTPException(status_code=503, detail="SEC API client not available")
    
    try:
        # Fetch cover page for fund profile
        cover_data = await sec_api_client.search_13f_cover_pages(cik=cik, size=1)
        cover_pages = cover_data.get("data", [])
        
        # Fetch holdings
        holdings_data = await sec_api_client.search_13f_holdings(cik=cik, size=1)
        filings = holdings_data.get("data", [])
        
        if not filings:
            raise HTTPException(status_code=404, detail=f"No 13F filings found for CIK {cik}")
        
        filing = filings[0]
        holdings = filing.get("holdings", [])
        
        # Build comprehensive profile from cover page
        profile = {
            "cik": filing.get("cik", cik),
            "name": filing.get("companyName", "Unknown"),
            "accessionNo": filing.get("accessionNo", ""),
            "formType": filing.get("formType", "13F-HR"),
            "periodOfReport": filing.get("periodOfReport", ""),
            "filedAt": filing.get("filedAt", ""),
            "linkToFilingDetails": filing.get("linkToFilingDetails", ""),
            "linkToHtml": filing.get("linkToHtml", ""),
        }
        
        # Add cover page info if available
        if cover_pages:
            cp = cover_pages[0]
            profile.update({
                "crdNumber": cp.get("crdNumber", ""),
                "form13FFileNumber": cp.get("form13FFileNumber", ""),
                "isAmendment": cp.get("isAmendment", False),
                "reportType": cp.get("reportType", ""),
                "tableEntryTotal": cp.get("tableEntryTotal", 0),
                "tableValueTotal": cp.get("tableValueTotal", 0),
                "additionalInformation": cp.get("additionalInformation", ""),
                "filingManager": cp.get("filingManager", {}),
                "signature": cp.get("signature", {}),
                "otherIncludedManagersCount": cp.get("otherIncludedManagersCount", 0),
                "otherIncludedManagers": cp.get("otherIncludedManagers", []),
            })
        
        # Calculate totals
        total_value = sum(h.get("value", 0) for h in holdings)
        total_shares = sum(h.get("shrsOrPrnAmt", {}).get("sshPrnamt", 0) for h in holdings)
        
        # Group by investment discretion
        by_discretion = {}
        for h in holdings:
            disc = h.get("investmentDiscretion", "UNKNOWN")
            if disc not in by_discretion:
                by_discretion[disc] = {"count": 0, "value": 0}
            by_discretion[disc]["count"] += 1
            by_discretion[disc]["value"] += h.get("value", 0)
        
        # Sort holdings by value
        holdings.sort(key=lambda x: x.get("value", 0), reverse=True)
        
        # Enrich holdings with additional info
        enriched_holdings = []
        for h in holdings[:size]:
            enriched_holdings.append({
                "ticker": h.get("ticker", ""),
                "cusip": h.get("cusip", ""),
                "nameOfIssuer": h.get("nameOfIssuer", ""),
                "titleOfClass": h.get("titleOfClass", ""),
                "value": h.get("value", 0),
                "shares": h.get("shrsOrPrnAmt", {}).get("sshPrnamt", 0),
                "sharesType": h.get("shrsOrPrnAmt", {}).get("sshPrnamtType", "SH"),
                "investmentDiscretion": h.get("investmentDiscretion", ""),
                "votingAuthority": h.get("votingAuthority", {}),
                "putCall": h.get("putCall"),
                "cik": h.get("cik", ""),  # Issuer CIK
            })
        
        return {
            "profile": profile,
            "summary": {
                "totalHoldings": len(holdings),
                "totalValue": total_value,
                "totalShares": total_shares,
                "byDiscretion": by_discretion,
            },
            "holdings": enriched_holdings,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_fund_holdings_error", cik=cik, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/funds")
async def search_funds(
    q: str = Query(..., min_length=2, description="Search query (name or CIK)"),
    size: int = Query(20, ge=1, le=50, description="Number of results"),
):
    """
    Search for funds by name or CIK.
    
    Returns a list of matching funds with full profile data.
    """
    if not sec_api_client:
        raise HTTPException(status_code=503, detail="SEC API client not available")
    
    try:
        # Try to search by CIK first (if query looks like a number)
        if q.isdigit():
            data = await sec_api_client.search_13f_cover_pages(cik=q, size=size)
        else:
            # Search by fund name
            data = await sec_api_client.search_13f_cover_pages(fund_name=q, size=size)
        
        cover_pages = data.get("data", [])
        
        funds = []
        seen_ciks = set()
        
        for cp in cover_pages:
            cik = cp.get("cik", "")
            if cik in seen_ciks:
                continue
            seen_ciks.add(cik)
            
            manager = cp.get("filingManager", {})
            address = manager.get("address", {})
            
            funds.append({
                "cik": cik,
                "name": manager.get("name", "Unknown"),
                "crdNumber": cp.get("crdNumber"),
                "form13FFileNumber": cp.get("form13FFileNumber"),
                "tableValueTotal": cp.get("tableValueTotal", 0),
                "tableEntryTotal": cp.get("tableEntryTotal", 0),
                "periodOfReport": cp.get("periodOfReport", ""),
                "filedAt": cp.get("filedAt", ""),
                "reportType": cp.get("reportType", ""),
                "address": {
                    "street": address.get("street", ""),
                    "city": address.get("city", ""),
                    "state": address.get("stateOrCountry", ""),
                    "zip": address.get("zipCode", ""),
                },
            })
        
        return {
            "query": q,
            "total": len(funds),
            "funds": funds,
        }
        
    except Exception as e:
        logger.error("search_funds_error", query=q, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top-holders")
async def get_top_holders(
    ticker: str,
    limit: int = Query(50, ge=1, le=200, description="Number of top holders"),
):
    """
    Get the top institutional holders for a ticker across multiple pages.
    
    Fetches more data for comprehensive analysis.
    """
    if not sec_api_client:
        raise HTTPException(status_code=503, detail="SEC API client not available")
    
    try:
        ticker_upper = ticker.upper()
        
        # Fetch multiple pages to get more holders
        all_filings = []
        for page in range(4):  # Fetch 4 pages (200 filings max)
            data = await sec_api_client.search_13f_holdings(
                ticker=ticker_upper,
                size=50,
                from_index=page * 50
            )
            filings = data.get("data", [])
            if not filings:
                break
            all_filings.extend(filings)
        
        # Aggregate by CIK
        holders_by_cik = aggregate_holdings_by_cik(all_filings, ticker_upper)
        
        # Sort by value
        holders = sorted(
            holders_by_cik.values(),
            key=lambda x: x["value"],
            reverse=True
        )[:limit]
        
        # Calculate totals
        total_shares = sum(h["shares"] for h in holders)
        total_value = sum(h["value"] for h in holders)
        
        return {
            "ticker": ticker_upper,
            "totalHolders": len(holders),
            "totalShares": total_shares,
            "totalValue": total_value,
            "holders": holders,
        }
        
    except Exception as e:
        logger.error("get_top_holders_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/filing/{accession_no}")
async def get_filing_details(
    accession_no: str,
):
    """
    Get full details of a specific 13F filing by accession number.
    """
    if not sec_api_client:
        raise HTTPException(status_code=503, detail="SEC API client not available")
    
    try:
        # Search by accession number
        data = await sec_api_client.search_13f_holdings(
            size=1,
            from_index=0
        )
        
        # This would need a direct query - for now return error
        raise HTTPException(status_code=501, detail="Not implemented - use CIK search")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_filing_details_error", accession_no=accession_no, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
