"""
Pattern Matcher - Main search and forecast engine
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import numpy as np
from scipy.special import softmax
import httpx
import structlog

from config import settings
from data_processor import DataProcessor
from pattern_indexer import PatternIndexer

logger = structlog.get_logger(__name__)


class ForecastGenerator:
    """Generates forecasts from pattern matches"""
    
    @staticmethod
    def generate(
        neighbors: List[Dict],
        distances: np.ndarray,
        temperature: float = 1.0
    ) -> Dict:
        """
        Generate forecast from matched neighbors
        
        Uses softmax weighting: closer patterns have more influence
        
        Args:
            neighbors: List of neighbor metadata (with future_returns)
            distances: Distance to each neighbor
            temperature: Softmax temperature (lower = more weight to closest)
            
        Returns:
            Forecast dict with mean, std, probabilities
        """
        # Filter valid neighbors
        valid = [
            (n, d) for n, d in zip(neighbors, distances)
            if n is not None and 'future_returns' in n
        ]
        
        if not valid:
            return {
                "error": "No valid neighbors with future data",
                "n_neighbors": 0
            }
        
        neighbors_valid = [v[0] for v in valid]
        distances_valid = np.array([v[1] for v in valid])
        
        # Calculate weights using softmax on negative distances
        # Closer (lower distance) = higher weight
        weights = softmax(-distances_valid / temperature)
        
        # Extract future returns
        futures = np.array([n['future_returns'] for n in neighbors_valid])
        
        # Weighted average forecast
        mean_forecast = np.average(futures, axis=0, weights=weights)
        std_forecast = np.sqrt(np.average((futures - mean_forecast)**2, axis=0, weights=weights))
        
        # Final return statistics (last point of forecast)
        final_returns = futures[:, -1]
        
        # Calculate probabilities
        prob_up = float((final_returns > 0).sum() / len(final_returns))
        prob_down = float((final_returns < 0).sum() / len(final_returns))
        
        # Confidence based on consistency
        consistency = 1 - (std_forecast[-1] / (np.abs(mean_forecast[-1]) + 1e-6))
        confidence = "high" if consistency > 0.7 else "medium" if consistency > 0.4 else "low"
        
        return {
            "horizon_minutes": len(mean_forecast),
            "mean_return": round(float(mean_forecast[-1]), 3),
            "mean_trajectory": [round(float(x), 3) for x in mean_forecast],
            "std_trajectory": [round(float(x), 3) for x in std_forecast],
            "prob_up": round(prob_up, 3),
            "prob_down": round(prob_down, 3),
            "confidence": confidence,
            "best_case": round(float(np.percentile(final_returns, 90)), 3),
            "worst_case": round(float(np.percentile(final_returns, 10)), 3),
            "median_return": round(float(np.median(final_returns)), 3),
            "n_neighbors": len(neighbors_valid),
        }


class PatternMatcher:
    """
    Main pattern matching engine
    
    Handles:
    - Loading FAISS index
    - Fetching real-time prices
    - Searching for similar patterns
    - Generating forecasts
    """
    
    def __init__(self):
        self.indexer = PatternIndexer()
        self.processor = DataProcessor()
        self.forecast_gen = ForecastGenerator()
        self.http_client: Optional[httpx.AsyncClient] = None
        self.is_ready = False
        
        logger.info("PatternMatcher initialized")
    
    async def initialize(self) -> bool:
        """Load index and initialize HTTP client"""
        # Load FAISS index
        if self.indexer.load():
            self.is_ready = True
            logger.info("PatternMatcher ready", stats=self.indexer.get_stats())
        else:
            logger.warning("No index loaded - service will be in limited mode")
        
        # Initialize HTTP client for real-time data
        self.http_client = httpx.AsyncClient(timeout=10.0)
        
        return self.is_ready
    
    async def close(self):
        """Cleanup resources"""
        if self.http_client:
            await self.http_client.aclose()
    
    async def get_realtime_prices(
        self,
        symbol: str,
        minutes: int = None
    ) -> List[float]:
        """
        Fetch real-time minute bars from Polygon
        
        Args:
            symbol: Ticker symbol
            minutes: Number of minutes to fetch
            
        Returns:
            List of close prices
        """
        minutes = minutes or settings.window_size
        
        # Calculate time range
        end = datetime.now()
        # Add buffer for market hours
        from_ts = int((end.timestamp() - (minutes + 30) * 60) * 1000)
        to_ts = int(end.timestamp() * 1000)
        
        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute"
            f"/{from_ts}/{to_ts}"
            f"?adjusted=true&sort=asc&limit={minutes + 60}"
            f"&apiKey={settings.polygon_api_key}"
        )
        
        try:
            response = await self.http_client.get(url)
            response.raise_for_status()
            data = response.json()
            
            results = data.get('results', [])
            if not results:
                raise ValueError(f"No price data for {symbol}")
            
            # Extract close prices
            prices = [bar['c'] for bar in results]
            
            # Return last N minutes
            return prices[-minutes:]
            
        except Exception as e:
            logger.error("Failed to fetch prices", symbol=symbol, error=str(e))
            raise
    
    async def search(
        self,
        symbol: str,
        prices: Optional[List[float]] = None,
        k: int = None,
        cross_asset: bool = True,
        nprobe: int = None
    ) -> Dict:
        """
        Search for similar patterns
        
        Args:
            symbol: Ticker symbol (for context and real-time fetch)
            prices: Optional price array (if None, fetches real-time)
            k: Number of neighbors
            cross_asset: Search all tickers or just same ticker
            nprobe: FAISS search parameter
            
        Returns:
            Search results with forecast
        """
        if not self.is_ready:
            return {"error": "Index not loaded", "status": "not_ready"}
        
        k = min(k or settings.default_k, settings.max_k)
        start_time = datetime.now()
        
        try:
            # Get prices if not provided
            if prices is None:
                prices = await self.get_realtime_prices(symbol)
            
            if len(prices) < settings.window_size:
                return {
                    "error": f"Need at least {settings.window_size} prices, got {len(prices)}",
                    "status": "insufficient_data"
                }
            
            # Normalize query pattern
            query_vector = self.processor.get_realtime_pattern(prices)
            
            # Search FAISS
            distances, indices, neighbors = self.indexer.search(
                query_vector, 
                k=k * 2 if not cross_asset else k,  # Get more if filtering
                nprobe=nprobe
            )
            
            # Filter by symbol if not cross_asset
            if not cross_asset:
                filtered = [
                    (d, i, n) for d, i, n in zip(distances, indices, neighbors)
                    if n and n.get('symbol') == symbol
                ]
                distances = np.array([f[0] for f in filtered[:k]])
                indices = np.array([f[1] for f in filtered[:k]])
                neighbors = [f[2] for f in filtered[:k]]
            
            # Generate forecast
            forecast = self.forecast_gen.generate(neighbors, distances)
            
            # Build response
            query_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return {
                "status": "success",
                "query": {
                    "symbol": symbol,
                    "window_minutes": settings.window_size,
                    "timestamp": start_time.isoformat(),
                    "cross_asset": cross_asset,
                },
                "forecast": forecast,
                "neighbors": [
                    {
                        "symbol": n['symbol'],
                        "date": n['date'],
                        "start_time": n['start_time'],
                        "end_time": n['end_time'],
                        "distance": round(float(d), 4),
                        "future_returns": n.get('future_returns', []),
                    }
                    for n, d in zip(neighbors[:k], distances[:k])
                    if n is not None
                ],
                "stats": {
                    "query_time_ms": round(query_time, 2),
                    "index_size": self.indexer.index.ntotal if self.indexer.index else 0,
                    "k_requested": k,
                    "k_returned": len([n for n in neighbors if n]),
                }
            }
            
        except Exception as e:
            logger.error("Search failed", symbol=symbol, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "symbol": symbol,
            }
    
    async def search_with_prices(
        self,
        prices: List[float],
        k: int = None,
        nprobe: int = None
    ) -> Dict:
        """
        Search with raw prices (no symbol context)
        
        Args:
            prices: Price array
            k: Number of neighbors
            
        Returns:
            Search results
        """
        return await self.search(
            symbol="UNKNOWN",
            prices=prices,
            k=k,
            cross_asset=True,
            nprobe=nprobe
        )
    
    async def get_historical_minute_data(
        self,
        symbol: str,
        date: str,
        start_time: str = "09:30",
        end_time: str = "16:00",
    ) -> Dict:
        """
        Get historical minute data from flat files
        
        Args:
            symbol: Ticker symbol
            date: Date string (YYYY-MM-DD)
            start_time: Start time (HH:MM) in ET (Eastern Time)
            end_time: End time (HH:MM) in ET (Eastern Time)
            
        Returns:
            Dict with prices, timestamps, and OHLCV data
        """
        import gzip
        import csv
        from datetime import datetime as dt, timezone, timedelta
        
        file_path = f"{settings.data_dir}/minute_aggs/{date}.csv.gz"
        
        try:
            # Parse time range (input is in ET)
            start_h, start_m = map(int, start_time.split(':'))
            end_h, end_m = map(int, end_time.split(':'))
            
            # Determine if date is in DST (Eastern Time)
            # Simple heuristic: March-November is EDT (UTC-4), else EST (UTC-5)
            date_parts = date.split('-')
            month = int(date_parts[1])
            is_dst = 3 <= month <= 11  # Rough DST approximation
            utc_offset = 4 if is_dst else 5  # Hours to add to ET to get UTC
            
            bars = []
            
            with gzip.open(file_path, 'rt') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    if row['ticker'] != symbol:
                        continue
                    
                    # Parse timestamp (nanoseconds) - data is in UTC
                    ts = int(row['window_start']) // 1_000_000_000
                    bar_time_utc = dt.fromtimestamp(ts, tz=timezone.utc)
                    
                    # Convert to ET
                    bar_time_et = bar_time_utc - timedelta(hours=utc_offset)
                    bar_hour = bar_time_et.hour
                    bar_min = bar_time_et.minute
                    
                    # Filter by time range (in ET)
                    if (bar_hour > start_h or (bar_hour == start_h and bar_min >= start_m)) and \
                       (bar_hour < end_h or (bar_hour == end_h and bar_min <= end_m)):
                        bars.append({
                            'timestamp': ts * 1000,  # Convert to ms for JS
                            'time': bar_time_et.strftime('%H:%M'),
                            'open': float(row['open']),
                            'high': float(row['high']),
                            'low': float(row['low']),
                            'close': float(row['close']),
                            'volume': int(row['volume']),
                        })
            
            if not bars:
                return {"error": f"No data found for {symbol} on {date}"}
            
            # Sort by timestamp
            bars.sort(key=lambda x: x['timestamp'])
            
            return {
                "symbol": symbol,
                "date": date,
                "bars": bars,
                "prices": [b['close'] for b in bars],
                "times": [b['time'] for b in bars],
                "count": len(bars),
            }
            
        except FileNotFoundError:
            return {"error": f"No data file for {date}"}
        except Exception as e:
            logger.error("Failed to load historical data", error=str(e))
            return {"error": str(e)}
    
    async def search_historical(
        self,
        symbol: str,
        date: str,
        time: str,
        k: int = None,
        cross_asset: bool = True,
        window_minutes: int = None,
    ) -> Dict:
        """
        Search using historical data from flat files
        
        Args:
            symbol: Ticker symbol
            date: Date string (YYYY-MM-DD)
            time: End time of pattern (HH:MM)
            k: Number of neighbors
            cross_asset: Search all tickers
            window_minutes: Pattern window size
            
        Returns:
            Search results with forecast and pattern context
        """
        if not self.is_ready:
            return {"error": "Index not loaded", "status": "not_ready"}
        
        window_minutes = window_minutes or settings.window_size
        k = min(k or settings.default_k, settings.max_k)
        
        try:
            # Parse end time
            end_h, end_m = map(int, time.split(':'))
            
            # Calculate start time (window_minutes before)
            total_mins = end_h * 60 + end_m - window_minutes
            start_h = total_mins // 60
            start_m = total_mins % 60
            start_time = f"{start_h:02d}:{start_m:02d}"
            
            # Get historical prices
            hist_data = await self.get_historical_minute_data(
                symbol=symbol,
                date=date,
                start_time=start_time,
                end_time=time,
            )
            
            if "error" in hist_data:
                return {"status": "error", "error": hist_data["error"]}
            
            prices = hist_data["prices"]
            
            if len(prices) < 15:  # Minimum viable pattern
                return {
                    "status": "error",
                    "error": f"Insufficient data: got {len(prices)} bars, need at least 15"
                }
            
            # Get full day context for charting (before and after pattern)
            full_day = await self.get_historical_minute_data(
                symbol=symbol,
                date=date,
                start_time="09:30",
                end_time="16:00",
            )
            
            # Perform search
            result = await self.search(
                symbol=symbol,
                prices=prices,
                k=k,
                cross_asset=cross_asset,
            )
            
            # Enrich with historical context
            if result.get("status") == "success":
                result["historical_context"] = {
                    "mode": "historical",
                    "date": date,
                    "pattern_start": start_time,
                    "pattern_end": time,
                    "pattern_prices": prices,
                    "pattern_times": hist_data.get("times", []),
                    "full_day_prices": full_day.get("prices", []) if "error" not in full_day else [],
                    "full_day_times": full_day.get("times", []) if "error" not in full_day else [],
                }
                result["query"]["mode"] = "historical"
                result["query"]["date"] = date
                result["query"]["pattern_time"] = time
            
            return result
            
        except Exception as e:
            logger.error("Historical search failed", error=str(e))
            return {"status": "error", "error": str(e)}
    
    def get_stats(self) -> Dict:
        """Get matcher statistics"""
        return {
            "is_ready": self.is_ready,
            "index": self.indexer.get_stats() if self.indexer else None,
            "config": {
                "window_size": settings.window_size,
                "future_size": settings.future_size,
                "default_k": settings.default_k,
            }
        }


# Singleton instance
_matcher: Optional[PatternMatcher] = None


async def get_matcher() -> PatternMatcher:
    """Get or create matcher singleton"""
    global _matcher
    if _matcher is None:
        _matcher = PatternMatcher()
        await _matcher.initialize()
    return _matcher


# CLI for testing
if __name__ == "__main__":
    import asyncio
    
    async def test():
        matcher = PatternMatcher()
        await matcher.initialize()
        
        print("\n📊 Matcher Stats:")
        print(matcher.get_stats())
        
        # Test with random prices
        if matcher.is_ready:
            prices = list(np.cumsum(np.random.randn(50)) + 100)
            result = await matcher.search_with_prices(prices, k=10)
            print("\n🔍 Search Result:")
            print(f"  Status: {result.get('status')}")
            print(f"  Forecast: {result.get('forecast', {})}")
        
        await matcher.close()
    
    asyncio.run(test())

