"""
Shares Data Service
===================
Servicio para obtener historial de acciones y ajustes por splits.

Este módulo maneja:
- Historial de shares outstanding desde SEC-API.io
- Fallback a SEC EDGAR XBRL
- Ajuste por stock splits (FMP)
- Ajuste de warrants por splits
"""

import httpx
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from shared.config.settings import settings
from shared.utils.logger import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)


def _parse_price_value(value) -> float:
    """
    Parse price value that may have currency prefixes like CAD$, US$, $.
    Returns 0.0 if parsing fails.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    # Convert to string and clean
    s = str(value).strip()
    # Remove common currency prefixes
    for prefix in ['CAD$', 'CA$', 'USD$', 'US$', 'EUR$', 'GBP$', '$']:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    # Remove commas and whitespace
    s = s.replace(',', '').strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


class SharesDataService:
    """
    Servicio para obtener historial de acciones y realizar ajustes por splits.
    """
    
    def __init__(self, redis: RedisClient):
        """
        Args:
            redis: Cliente Redis para caché
        """
        self.redis = redis
    
    async def get_shares_history(self, ticker: str, cik: Optional[str] = None) -> Dict[str, Any]:
        """
        Get historical shares outstanding from SEC-API.io /float endpoint.
        Falls back to SEC EDGAR XBRL if SEC-API fails.
        
        Returns:
            Dict with shares history, dilution metrics, and all records.
        """
        try:
            ticker = ticker.upper()
            
            # Check Redis cache first
            cache_key = f"sec_dilution:shares_history:{ticker}"
            cached = await self.redis.get(cache_key, deserialize=True)
            if cached:
                logger.info("shares_history_from_cache", ticker=ticker)
                return cached
            
            # PRIMARY: SEC-API.io /float
            result = await self._fetch_shares_from_sec_api(ticker)
            
            # FALLBACK: SEC EDGAR XBRL
            if not result or "error" in result:
                logger.info("falling_back_to_sec_edgar", ticker=ticker)
                result = await self._fetch_shares_from_sec_edgar(ticker, cik)
            
            # Cache for 6 hours
            if result and "error" not in result:
                await self.redis.set(cache_key, result, ttl=21600, serialize=True)
            
            return result
            
        except Exception as e:
            logger.error("get_shares_history_failed", ticker=ticker, error=str(e))
            return {"error": str(e)}
    
    async def _fetch_shares_from_sec_api(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Fetch historical shares from SEC-API.io /float endpoint.
        """
        try:
            sec_api_key = settings.SEC_API_IO_KEY
            if not sec_api_key:
                logger.warning("sec_api_io_key_missing")
                return None
            
            url = f"https://api.sec-api.io/float?ticker={ticker}&token={sec_api_key}"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                
                if response.status_code != 200:
                    logger.warning("sec_api_float_failed", ticker=ticker, status=response.status_code)
                    return None
                
                data = response.json()
            
            records_list = data.get('data', [])
            if not records_list:
                logger.warning("no_float_data_from_sec_api", ticker=ticker)
                return None
            
            # Process records - sum all share classes
            records = []
            for item in records_list:
                period = item.get('periodOfReport')
                float_data = item.get('float', {})
                outstanding_list = float_data.get('outstandingShares', [])
                
                if not period or not outstanding_list:
                    continue
                
                total_shares = sum(s.get('value', 0) for s in outstanding_list)
                
                if total_shares > 0:
                    records.append({
                        'date': period,
                        'shares': total_shares,
                        'form': 'SEC-API',
                        'filed': item.get('reportedAt', '')[:10]
                    })
            
            if not records:
                return None
            
            # Sort by date ascending
            records.sort(key=lambda x: x['date'])
            
            # Adjust for stock splits
            records = await self.adjust_for_splits(ticker, records)
            
            # Calculate dilution metrics
            return await self._build_shares_result(records, "SEC-API.io /float", ticker)
            
        except Exception as e:
            logger.error("sec_api_float_exception", ticker=ticker, error=str(e))
            return None
    
    async def _fetch_shares_from_sec_edgar(
        self, 
        ticker: str, 
        cik: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch historical shares from SEC EDGAR Company Facts API (XBRL).
        """
        try:
            # Get CIK if not provided
            if not cik:
                from services.sec.sec_filing_fetcher import get_sec_filing_fetcher
                fetcher = get_sec_filing_fetcher()
                cik, _ = await fetcher.get_cik_and_company_name(ticker)
            
            if not cik:
                logger.warning("no_cik_for_edgar_shares", ticker=ticker)
                return None
            
            cik_padded = cik.lstrip('0').zfill(10)
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": "TradeulApp/1.0 (support@tradeul.com)"}
                )
                
                if response.status_code != 200:
                    logger.warning("sec_edgar_shares_failed", ticker=ticker, status=response.status_code)
                    return None
                
                data = response.json()
            
            # Extract shares outstanding from XBRL
            facts = data.get('facts', {}).get('us-gaap', {})
            
            share_fields = [
                'CommonStockSharesOutstanding',
                'CommonStockSharesIssued',
                'WeightedAverageNumberOfSharesOutstandingBasic',
            ]
            
            records = []
            for field in share_fields:
                field_data = facts.get(field, {})
                shares_list = field_data.get('units', {}).get('shares', [])
                
                if shares_list:
                    for item in shares_list:
                        form = item.get('form', '')
                        if form not in ['10-K', '10-Q', '10-K/A', '10-Q/A']:
                            continue
                        
                        end_date = item.get('end')
                        value = item.get('val')
                        filed = item.get('filed')
                        
                        if end_date and value:
                            records.append({
                                'date': end_date,
                                'shares': int(value),
                                'form': form,
                                'filed': filed
                            })
                    
                    if records:
                        break
            
            if not records:
                return None
            
            # Deduplicate by date (keep latest filed)
            seen = {}
            for r in records:
                d = r['date']
                if d not in seen or r['filed'] > seen[d]['filed']:
                    seen[d] = r
            
            sorted_records = sorted(seen.values(), key=lambda x: x['date'])
            
            return await self._build_shares_result(sorted_records, "SEC EDGAR XBRL (official)", ticker)
            
        except Exception as e:
            logger.error("sec_edgar_shares_exception", ticker=ticker, error=str(e))
            return None
    
    async def _build_shares_result(
        self, 
        records: List[Dict], 
        source: str, 
        ticker: str
    ) -> Dict[str, Any]:
        """Build the result dict with dilution metrics."""
        now = datetime.now()
        
        # Get current shares from Polygon (more up-to-date than SEC filings)
        current_polygon = await self._get_current_shares_polygon(ticker)
        
        # If Polygon has more recent data, add it as current
        if current_polygon and current_polygon > 0:
            today = now.strftime("%Y-%m-%d")
            
            # Check if we need to add current as a new record
            last_record_date = records[-1]['date'] if records else None
            if last_record_date and last_record_date < today:
                # Add current as new record if significantly different (>5% change)
                last_shares = records[-1]['shares'] if records else 0
                if last_shares > 0:
                    change_pct = abs(current_polygon - last_shares) / last_shares
                    if change_pct > 0.05:  # More than 5% change
                        records.append({
                            'date': today,
                            'shares': current_polygon,
                            'form': 'Polygon-Current',
                            'filed': today,
                            'split_adjusted': False
                        })
                        logger.info("added_polygon_current", ticker=ticker, 
                                   shares=current_polygon, change_pct=round(change_pct*100, 1))
        
        current = records[-1] if records else None
        current_shares = current_polygon if current_polygon else (current['shares'] if current else None)
        
        def find_closest(target_date: str) -> Optional[Dict]:
            closest = None
            min_diff = float('inf')
            for rec in records:
                try:
                    rec_dt = datetime.strptime(rec['date'][:10], "%Y-%m-%d")
                    tgt_dt = datetime.strptime(target_date, "%Y-%m-%d")
                    diff = abs((rec_dt - tgt_dt).days)
                    if diff < min_diff:
                        min_diff = diff
                        closest = rec
                except:
                    continue
            return closest if min_diff < 120 else None
        
        one_year_ago = (now - timedelta(days=365)).strftime("%Y-%m-%d")
        three_years_ago = (now - timedelta(days=365*3)).strftime("%Y-%m-%d")
        five_years_ago = (now - timedelta(days=365*5)).strftime("%Y-%m-%d")
        
        yr1_rec = find_closest(one_year_ago)
        yr3_rec = find_closest(three_years_ago)
        yr5_rec = find_closest(five_years_ago)
        
        def calc_dilution(old: int, new: int) -> float:
            if old > 0:
                return ((new - old) / old) * 100
            return 0.0
        
        result = {
            "source": source,
            "current": {
                "date": now.strftime("%Y-%m-%d"),
                "outstanding_shares": current_shares,
            },
            "current_shares": current_shares,
            "current_as_of": now.strftime("%Y-%m-%d"),
            "all_records": [
                {"period": r['date'], "outstanding_shares": r['shares']}
                for r in records
            ],
            "dilution_summary": {},
            "history": records,
        }
        
        if current_shares and yr1_rec:
            result["dilution_summary"]["1_year"] = round(calc_dilution(yr1_rec['shares'], current_shares), 2)
        if current_shares and yr3_rec:
            result["dilution_summary"]["3_years"] = round(calc_dilution(yr3_rec['shares'], current_shares), 2)
        if current_shares and yr5_rec:
            result["dilution_summary"]["5_years"] = round(calc_dilution(yr5_rec['shares'], current_shares), 2)
        
        logger.info("shares_history_built", ticker=ticker, records=len(records), 
                   source=source, current_shares=current_shares)
        return result
    
    async def _get_current_shares_polygon(self, ticker: str) -> Optional[int]:
        """Get current shares outstanding from Polygon."""
        try:
            polygon_api_key = settings.POLYGON_API_KEY
            if not polygon_api_key:
                return None
            
            url = f"https://api.polygon.io/v3/reference/tickers/{ticker}?apiKey={polygon_api_key}"
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return None
                
                data = response.json().get('results', {})
                
                # Prefer weighted_shares_outstanding (more accurate for multi-class)
                shares = data.get('weighted_shares_outstanding') or data.get('share_class_shares_outstanding')
                
                if shares and shares > 0:
                    logger.debug("polygon_current_shares", ticker=ticker, shares=shares)
                    return int(shares)
                
                return None
                
        except Exception as e:
            logger.warning("polygon_shares_error", ticker=ticker, error=str(e))
            return None
    
    async def adjust_for_splits(self, ticker: str, records: List[Dict]) -> List[Dict]:
        """
        Adjust historical shares for stock splits using Polygon split history.
        
        IMPORTANT: SEC filings report shares in the BASIS OF THE FILING DATE,
        not the period date. When a company files their 20-F/10-K, they
        retroactively adjust historical shares for any splits that occurred
        between the period end and the filing date.
        
        Example: VMAR 2024-08-31 period, filed 2024-12-20
        - Split 15:1 occurred 2024-08-22 (before period end)
        - Split 9:1 occurred 2024-10-08 (after period, before filing)
        - The filed value (163,403) ALREADY includes both splits
        - We only need to adjust for splits AFTER the filing date
        
        Polygon provides historical_adjustment_factor which is CUMULATIVE.
        For SHARES, we divide by the factor.
        """
        if not records:
            return records
        
        try:
            splits = await self.get_split_history(ticker)
            if not splits:
                return records
            
            logger.info(
                "splits_detected",
                ticker=ticker,
                count=len(splits),
                splits=[(s['date'], s['adjustment_type'], f"{s['split_from']}:{s['split_to']}") for s in splits]
            )
            
            # Adjust each record for splits that occurred AFTER the FILING date
            # SEC retroactively adjusts values for splits between period and filing
            # So we only need to adjust for splits AFTER the filing was submitted
            adjusted = []
            for record in records:
                record_date = record['date']
                # Use filing date if available, otherwise fall back to period date
                filing_date = record.get('filed', record_date)
                
                adjustment_factor = 1.0
                applied_split = None
                
                # Find the FIRST split after the FILING date
                # The filed value already includes splits up to the filing date
                for split in splits:
                    if split['date'] > filing_date:
                        factor = split.get('historical_adjustment_factor')
                        if factor and factor != 1.0:
                            adjustment_factor = factor
                            applied_split = split
                            logger.debug(
                                "applying_split_to_shares",
                                ticker=ticker,
                                period_date=record_date,
                                filing_date=filing_date,
                                split_date=split['date'],
                                split_type=split['adjustment_type'],
                                factor=factor
                            )
                            break  # Use only first split (factor is already cumulative)
                
                if adjustment_factor != 1.0:
                    adjusted_shares = int(record['shares'] / adjustment_factor)
                    adjusted.append({
                        **record,
                        'shares': adjusted_shares,
                        'original_shares': record['shares'],
                        'split_adjusted': True,
                        'adjustment_factor': adjustment_factor,
                        'applied_split_date': applied_split['date'] if applied_split else None,
                        'filing_date_used': filing_date
                    })
                    logger.info(
                        "shares_adjusted_for_split",
                        ticker=ticker,
                        period_date=record_date,
                        filing_date=filing_date,
                        original=record['shares'],
                        adjusted=adjusted_shares,
                        factor=adjustment_factor,
                        split_date=applied_split['date'] if applied_split else None
                    )
                else:
                    adjusted.append({
                        **record,
                        'split_adjusted': False,
                        'filing_date_used': filing_date
                    })
            
            adjusted_count = sum(1 for r in adjusted if r.get('split_adjusted'))
            if adjusted_count > 0:
                logger.info("shares_split_adjusted", ticker=ticker, adjusted=adjusted_count, total=len(adjusted))
            
            return adjusted
            
        except Exception as e:
            logger.warning("split_adjustment_error", ticker=ticker, error=str(e))
            return records
    
    async def get_split_history(self, ticker: str) -> List[Dict]:
        """
        Fetch stock split history from Polygon.io /stocks/v1/splits endpoint.
        
        Polygon provides:
        - adjustment_type: "reverse_split", "forward_split", "stock_dividend"
        - historical_adjustment_factor: factor to multiply old prices by
        - split_from, split_to: ratio (e.g., 50:1 = split_from=50, split_to=1)
        
        For shares adjustment (opposite of price adjustment):
        - historical_shares / historical_adjustment_factor = current_basis_shares
        """
        try:
            polygon_key = settings.POLYGON_API_KEY
            if not polygon_key:
                return []
            
            # Check cache first
            cache_key = f"sec_dilution:splits:{ticker}"
            cached = await self.redis.get(cache_key, deserialize=True)
            if cached is not None:
                return cached
            
            url = f"https://api.polygon.io/stocks/v1/splits?ticker={ticker}&limit=100&apiKey={polygon_key}"
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    logger.warning("polygon_splits_api_error", ticker=ticker, status=response.status_code)
                    return []
                data = response.json()
            
            results = data.get('results', [])
            if not results:
                await self.redis.set(cache_key, [], ttl=86400, serialize=True)
                return []
            
            # Convert to our format
            splits = []
            for r in results:
                splits.append({
                    'date': r.get('execution_date'),
                    'adjustment_type': r.get('adjustment_type'),  # reverse_split, forward_split, stock_dividend
                    'split_from': r.get('split_from'),  # old shares (denominator)
                    'split_to': r.get('split_to'),      # new shares (numerator)
                    'historical_adjustment_factor': r.get('historical_adjustment_factor'),
                    'ticker': r.get('ticker')
                })
            
            # Sort by date ascending
            splits = sorted(splits, key=lambda x: x['date'])
            
            logger.info(
                "polygon_splits_fetched",
                ticker=ticker,
                count=len(splits),
                splits=[(s['date'], s['adjustment_type'], f"{s['split_from']}:{s['split_to']}") for s in splits]
            )
            
            # Cache for 24 hours
            await self.redis.set(cache_key, splits, ttl=86400, serialize=True)
            
            return splits
            
        except Exception as e:
            logger.warning("get_split_history_error", ticker=ticker, error=str(e))
            return []
    
    async def adjust_warrants_for_splits(self, ticker: str, warrants: List[Dict]) -> List[Dict]:
        """
        Adjust warrants for stock splits.
        
        For a reverse split 1:10:
        - exercise_price is MULTIPLIED by 10 (more expensive)
        - outstanding is DIVIDED by 10 (fewer shares)
        
        EXCEPTION: Warrants to purchase convertible NOTES (not shares) are NOT adjusted.
        These have exercise_price = note principal amount, not price per share.
        """
        if not warrants:
            return warrants
        
        try:
            splits = await self.get_split_history(ticker)
            if not splits:
                return warrants
            
            logger.info("adjusting_warrants_for_splits", 
                       ticker=ticker, 
                       warrant_count=len(warrants),
                       split_count=len(splits))
            
            adjusted_warrants = []
            for w in warrants:
                warrant = dict(w)  # Copy
                
                # CRITICAL: Skip split adjustment for warrants that purchase NOTES (not shares)
                # These are identified by:
                # 1. Notes mentioning "purchase" + "note" or "convertible note"
                # 2. Very high exercise prices (> $100,000 per "share")
                notes_text = str(warrant.get('notes', '')).lower()
                exercise_price = _parse_price_value(warrant.get('exercise_price'))
                
                is_note_warrant = (
                    ('purchase' in notes_text and 'note' in notes_text) or
                    ('convertible note' in notes_text) or
                    (exercise_price > 100000)  # No warrant is $100K+ per share
                )
                
                if is_note_warrant:
                    logger.debug("warrant_skip_split_adjustment",
                               ticker=ticker,
                               reason="note_warrant",
                               exercise_price=exercise_price,
                               notes_preview=notes_text[:100])
                    warrant['split_adjusted'] = False
                    warrant['original_exercise_price'] = warrant.get('exercise_price')
                    adjusted_warrants.append(warrant)
                    continue
                
                issue_date = warrant.get('issue_date')
                
                # CRITICAL: If no issue_date, do NOT adjust - SEC documents already show
                # current prices. Only adjust if we have a confirmed historical date.
                if not issue_date:
                    logger.debug("warrant_skip_no_issue_date",
                               ticker=ticker,
                               exercise_price=exercise_price,
                               reason="no_issue_date_assume_current")
                    warrant['split_adjusted'] = False
                    adjusted_warrants.append(warrant)
                    continue
                
                if hasattr(issue_date, 'isoformat'):
                    issue_date = issue_date.isoformat()[:10]
                else:
                    issue_date = str(issue_date)[:10]
                
                # Use Polygon's historical_adjustment_factor (already cumulative)
                # Only use the FIRST split after the issue date - its factor already
                # accounts for all subsequent splits (e.g., factor=90 means 9×10)
                factor = 1.0
                for split in splits:
                    split_date = split.get('date', '')
                    if split_date > issue_date:
                        adj_factor = split.get('historical_adjustment_factor', 1.0)
                        if adj_factor and adj_factor != 1.0:
                            factor = adj_factor  # Use directly (Polygon factors are cumulative)
                            break  # Only use first split after issue date
                
                if factor != 1.0:
                    original_price = warrant.get('exercise_price')
                    original_outstanding = warrant.get('outstanding')
                    
                    # Adjust exercise price (multiply by factor for reverse split)
                    # E.g., reverse 50:1: $0.10 * 50 = $5.00
                    if original_price is not None:
                        price_float = _parse_price_value(original_price)
                        if price_float > 0:
                            # HEURISTIC: If price seems already adjusted (very high), skip adjustment
                            # Typical pre-split prices are $0.001-$50. If price > $100 and would
                            # become > $1000 after adjustment, it was likely already adjusted
                            # in a recent SEC filing that reports post-split values
                            would_be = price_float * factor
                            if price_float > 100 and would_be > 1000 and factor > 10:
                                logger.warning("warrant_skip_likely_already_adjusted",
                                             ticker=ticker,
                                             price=price_float,
                                             factor=factor,
                                             would_be=would_be,
                                             reason="price_seems_post_split")
                                warrant['split_adjusted'] = False
                                warrant['_skip_reason'] = 'price_already_adjusted'
                                adjusted_warrants.append(warrant)
                                continue
                            
                            warrant['exercise_price'] = round(price_float * factor, 4)
                            # Store original as numeric (Pydantic expects Decimal)
                            warrant['original_exercise_price'] = price_float
                    
                    # Adjust outstanding shares (divide by factor for reverse split)
                    # E.g., reverse 50:1: 1,000,000 / 50 = 20,000
                    if original_outstanding is not None:
                        try:
                            outstanding_int = int(str(original_outstanding).replace(',', ''))
                            warrant['outstanding'] = int(outstanding_int / factor)
                            warrant['original_outstanding'] = original_outstanding
                        except (ValueError, TypeError):
                            pass
                    
                    # CRITICAL: Adjust total_issued (divide by factor for reverse split)
                    original_issued = warrant.get('total_issued')
                    if original_issued is not None:
                        try:
                            issued_int = int(str(original_issued).replace(',', ''))
                            warrant['total_issued'] = int(issued_int / factor)
                            warrant['original_total_issued'] = original_issued
                        except (ValueError, TypeError):
                            pass
                    
                    # Adjust potential_new_shares
                    original_potential = warrant.get('potential_new_shares')
                    if original_potential is not None:
                        try:
                            potential_int = int(original_potential)
                            warrant['potential_new_shares'] = int(potential_int / factor)
                            warrant['original_potential_new_shares'] = original_potential
                        except (ValueError, TypeError):
                            pass
                    
                    warrant['split_adjusted'] = True
                    warrant['split_factor'] = factor
                    
                    logger.debug("warrant_split_adjusted",
                               ticker=ticker,
                               factor=factor,
                               original_price=original_price,
                               adjusted_price=warrant.get('exercise_price'))
                else:
                    warrant['split_adjusted'] = False
                
                adjusted_warrants.append(warrant)
            
            adjusted_count = sum(1 for w in adjusted_warrants if w.get('split_adjusted'))
            if adjusted_count > 0:
                logger.info("warrants_split_adjusted", 
                           ticker=ticker, 
                           adjusted=adjusted_count, 
                           total=len(adjusted_warrants))
            
            return adjusted_warrants
            
        except Exception as e:
            logger.warning("warrant_split_adjustment_error", ticker=ticker, error=str(e))
            return warrants

    async def adjust_convertible_notes_for_splits(self, ticker: str, notes: List[Dict]) -> List[Dict]:
        """
        Adjust convertible notes for stock splits.
        
        For a reverse split 1:50:
        - conversion_price is MULTIPLIED by 50 (more expensive per share)
        - shares_when_converted is DIVIDED by 50 (fewer shares)
        - principal_amount stays the same (it's a dollar amount)
        
        Note: Some notes have anti-dilution protection that may reset prices
        after splits, but we adjust based on the split ratio first.
        """
        if not notes:
            return notes
        
        try:
            splits = await self.get_split_history(ticker)
            if not splits:
                return notes
            
            logger.info("adjusting_notes_for_splits", 
                       ticker=ticker, 
                       note_count=len(notes),
                       split_count=len(splits))
            
            adjusted_notes = []
            for n in notes:
                note = dict(n)  # Copy
                
                issue_date = note.get('issue_date')
                
                # CRITICAL: If no issue_date, do NOT adjust - SEC documents already show
                # current prices. Only adjust if we have a confirmed historical date.
                if not issue_date:
                    logger.debug("note_skip_no_issue_date",
                               ticker=ticker,
                               conversion_price=note.get('conversion_price'),
                               reason="no_issue_date_assume_current")
                    note['split_adjusted'] = False
                    adjusted_notes.append(note)
                    continue
                
                if hasattr(issue_date, 'isoformat'):
                    issue_date = issue_date.isoformat()[:10]
                else:
                    issue_date = str(issue_date)[:10]
                
                # Use Polygon's historical_adjustment_factor (already cumulative)
                # Only use the FIRST split after the issue date - its factor already
                # accounts for all subsequent splits (e.g., factor=90 means 9×10)
                factor = 1.0
                for split in splits:
                    split_date = split.get('date', '')
                    if split_date > issue_date:
                        adj_factor = split.get('historical_adjustment_factor', 1.0)
                        if adj_factor and adj_factor != 1.0:
                            factor = adj_factor  # Use directly (Polygon factors are cumulative)
                            break  # Only use first split after issue date
                
                if factor != 1.0:
                    # Adjust conversion_price (multiply by factor for reverse split)
                    original_price = note.get('conversion_price')
                    price_float = _parse_price_value(original_price)
                    if price_float > 0:
                        note['conversion_price'] = round(price_float * factor, 4)
                        # Store original as numeric (Pydantic expects Decimal)
                        note['original_conversion_price'] = price_float
                    
                    # Adjust floor_price if exists
                    original_floor = note.get('floor_price')
                    if original_floor is not None and original_floor > 0:
                        try:
                            floor_float = float(original_floor)
                            note['floor_price'] = round(floor_float * factor, 4)
                            note['original_floor_price'] = original_floor
                        except (ValueError, TypeError):
                            pass
                    
                    # Adjust total_shares_when_converted (divide for reverse split)
                    original_shares = note.get('total_shares_when_converted')
                    if original_shares is not None:
                        try:
                            shares_int = int(original_shares)
                            note['total_shares_when_converted'] = int(shares_int / factor)
                            note['original_total_shares'] = original_shares
                        except (ValueError, TypeError):
                            pass
                    
                    # Adjust remaining_shares_when_converted
                    original_remaining = note.get('remaining_shares_when_converted')
                    if original_remaining is not None:
                        try:
                            remaining_int = int(original_remaining)
                            note['remaining_shares_when_converted'] = int(remaining_int / factor)
                            note['original_remaining_shares'] = original_remaining
                        except (ValueError, TypeError):
                            pass
                    
                    note['split_adjusted'] = True
                    note['split_factor'] = factor
                    
                    logger.debug("note_split_adjusted",
                               ticker=ticker,
                               factor=factor,
                               original_price=original_price,
                               adjusted_price=note.get('conversion_price'))
                else:
                    note['split_adjusted'] = False
                
                adjusted_notes.append(note)
            
            adjusted_count = sum(1 for n in adjusted_notes if n.get('split_adjusted'))
            if adjusted_count > 0:
                logger.info("convertible_notes_split_adjusted", 
                           ticker=ticker, 
                           adjusted=adjusted_count, 
                           total=len(adjusted_notes))
            
            return adjusted_notes
            
        except Exception as e:
            logger.warning("note_split_adjustment_error", ticker=ticker, error=str(e))
            return notes

    async def adjust_convertible_preferred_for_splits(self, ticker: str, preferred: List[Dict]) -> List[Dict]:
        """
        Adjust convertible preferred stock for stock splits.
        
        Similar to notes: conversion_price is MULTIPLIED by split factor,
        shares are DIVIDED by split factor.
        
        IMPORTANT: We extract the RAW price from documents and adjust here in Python,
        NOT in the LLM (LLMs are bad at split calculations).
        """
        if not preferred:
            return preferred
        
        try:
            splits = await self.get_split_history(ticker)
            if not splits:
                return preferred
            
            logger.info("adjusting_preferred_for_splits", 
                       ticker=ticker, 
                       preferred_count=len(preferred),
                       split_count=len(splits))
            
            adjusted_preferred = []
            for p in preferred:
                pref = dict(p)  # Copy
                
                issue_date = pref.get('issue_date')
                
                # If no issue_date, don't adjust - assume price is already current
                if not issue_date:
                    logger.debug("preferred_skip_no_issue_date",
                               ticker=ticker,
                               conversion_price=pref.get('conversion_price'),
                               reason="no_issue_date_assume_current")
                    pref['split_adjusted'] = False
                    adjusted_preferred.append(pref)
                    continue
                
                if hasattr(issue_date, 'isoformat'):
                    issue_date = issue_date.isoformat()[:10]
                else:
                    issue_date = str(issue_date)[:10]
                
                # Use Polygon's historical_adjustment_factor (cumulative)
                factor = 1.0
                for split in splits:
                    split_date = split.get('date', '')
                    if split_date > issue_date:
                        adj_factor = split.get('historical_adjustment_factor', 1.0)
                        if adj_factor and adj_factor != 1.0:
                            factor = adj_factor
                            break  # Only first split after issue date
                
                if factor != 1.0:
                    # Adjust conversion_price (multiply by factor for reverse split)
                    original_price = pref.get('conversion_price')
                    price_float = _parse_price_value(original_price)
                    if price_float > 0:
                        pref['conversion_price'] = round(price_float * factor, 4)
                        # Store original as numeric (Pydantic expects Decimal)
                        pref['original_conversion_price'] = price_float
                    
                    # Adjust total_shares_when_converted
                    original_shares = pref.get('total_shares_when_converted')
                    if original_shares is not None:
                        try:
                            shares_int = int(original_shares)
                            pref['total_shares_when_converted'] = int(shares_int / factor)
                            pref['original_total_shares'] = original_shares
                        except (ValueError, TypeError):
                            pass
                    
                    # Adjust remaining_shares_when_converted
                    original_remaining = pref.get('remaining_shares_when_converted')
                    if original_remaining is not None:
                        try:
                            remaining_int = int(original_remaining)
                            pref['remaining_shares_when_converted'] = int(remaining_int / factor)
                            pref['original_remaining_shares'] = original_remaining
                        except (ValueError, TypeError):
                            pass
                    
                    pref['split_adjusted'] = True
                    pref['split_factor'] = factor
                    
                    logger.debug("preferred_split_adjusted",
                               ticker=ticker,
                               factor=factor,
                               original_price=original_price,
                               adjusted_price=pref.get('conversion_price'))
                else:
                    pref['split_adjusted'] = False
                
                adjusted_preferred.append(pref)
            
            adjusted_count = sum(1 for p in adjusted_preferred if p.get('split_adjusted'))
            if adjusted_count > 0:
                logger.info("convertible_preferred_split_adjusted", 
                           ticker=ticker, 
                           adjusted=adjusted_count, 
                           total=len(adjusted_preferred))
            
            return adjusted_preferred
            
        except Exception as e:
            logger.warning("preferred_split_adjustment_error", ticker=ticker, error=str(e))
            return preferred


# Singleton instance
_shares_service: Optional[SharesDataService] = None


def get_shares_data_service(redis: RedisClient = None) -> Optional[SharesDataService]:
    """Get or create shares data service instance"""
    global _shares_service
    if _shares_service is None and redis:
        _shares_service = SharesDataService(redis)
    return _shares_service

