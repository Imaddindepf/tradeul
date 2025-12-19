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
            return self._build_shares_result(records, "SEC-API.io /float", ticker)
            
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
            
            return self._build_shares_result(sorted_records, "SEC EDGAR XBRL (official)", ticker)
            
        except Exception as e:
            logger.error("sec_edgar_shares_exception", ticker=ticker, error=str(e))
            return None
    
    def _build_shares_result(
        self, 
        records: List[Dict], 
        source: str, 
        ticker: str
    ) -> Dict[str, Any]:
        """Build the result dict with dilution metrics."""
        now = datetime.now()
        current = records[-1] if records else None
        
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
                "date": current['date'] if current else None,
                "outstanding_shares": current['shares'] if current else None,
            },
            "all_records": [
                {"period": r['date'], "outstanding_shares": r['shares']}
                for r in records
            ],
            "dilution_summary": {},
            "history": records,
        }
        
        if current and yr1_rec:
            result["dilution_summary"]["1_year"] = round(calc_dilution(yr1_rec['shares'], current['shares']), 2)
        if current and yr3_rec:
            result["dilution_summary"]["3_years"] = round(calc_dilution(yr3_rec['shares'], current['shares']), 2)
        if current and yr5_rec:
            result["dilution_summary"]["5_years"] = round(calc_dilution(yr5_rec['shares'], current['shares']), 2)
        
        logger.info("shares_history_built", ticker=ticker, records=len(records), source=source)
        return result
    
    async def adjust_for_splits(self, ticker: str, records: List[Dict]) -> List[Dict]:
        """
        Adjust historical shares for stock splits using FMP split history.
        """
        if not records or len(records) < 2:
            return records
        
        try:
            splits = await self.get_split_history(ticker)
            if not splits:
                return records
            
            logger.info(
                "splits_detected",
                ticker=ticker,
                count=len(splits),
                splits=[(s['date'], f"{s['numerator']}:{s['denominator']}") for s in splits]
            )
            
            # Adjust each record for all splits that occurred AFTER that record date
            adjusted = []
            for record in records:
                record_date = record['date']
                factor = 1.0
                
                for split in splits:
                    if split['date'] > record_date:
                        factor *= split['denominator'] / split['numerator']
                
                if factor != 1.0:
                    adjusted.append({
                        **record,
                        'shares': int(record['shares'] / factor),
                        'original_shares': record['shares'],
                        'split_adjusted': True
                    })
                else:
                    adjusted.append({
                        **record,
                        'split_adjusted': False
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
        Fetch stock split history from FMP.
        """
        try:
            fmp_key = settings.FMP_API_KEY
            if not fmp_key:
                return []
            
            # Check cache first
            cache_key = f"sec_dilution:splits:{ticker}"
            cached = await self.redis.get(cache_key, deserialize=True)
            if cached is not None:
                return cached
            
            url = f"https://financialmodelingprep.com/api/v3/historical-price-full/stock_split/{ticker}?apikey={fmp_key}"
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return []
                data = response.json()
            
            splits = data.get('historical', [])
            splits = sorted(splits, key=lambda x: x['date'])
            
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
                
                issue_date = warrant.get('issue_date')
                if not issue_date:
                    issue_date = '2000-01-01'
                elif hasattr(issue_date, 'isoformat'):
                    issue_date = issue_date.isoformat()[:10]
                else:
                    issue_date = str(issue_date)[:10]
                
                # Calculate cumulative split factor
                factor = 1.0
                for split in splits:
                    split_date = split.get('date', '')
                    if split_date > issue_date:
                        factor *= split['denominator'] / split['numerator']
                
                if factor != 1.0:
                    original_price = warrant.get('exercise_price')
                    original_outstanding = warrant.get('outstanding')
                    
                    # Adjust exercise price (multiply for reverse split)
                    if original_price is not None:
                        try:
                            price_float = float(original_price)
                            warrant['exercise_price'] = round(price_float * factor, 4)
                            warrant['original_exercise_price'] = original_price
                        except (ValueError, TypeError):
                            pass
                    
                    # Adjust outstanding shares (divide for reverse split)
                    if original_outstanding is not None:
                        try:
                            outstanding_int = int(original_outstanding)
                            warrant['outstanding'] = int(outstanding_int / factor)
                            warrant['original_outstanding'] = original_outstanding
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


# Singleton instance
_shares_service: Optional[SharesDataService] = None


def get_shares_data_service(redis: RedisClient = None) -> Optional[SharesDataService]:
    """Get or create shares data service instance"""
    global _shares_service
    if _shares_service is None and redis:
        _shares_service = SharesDataService(redis)
    return _shares_service

