"""
Pattern Matcher - Main search and forecast engine
"""

import asyncio
from datetime import datetime, timedelta
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
            if n is not None and 'future_returns' in n and len(n['future_returns']) > 0
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
        
        # Extract future returns - supports both full trajectories and single final_return
        futures_list = [n['future_returns'] for n in neighbors_valid]
        trajectory_length = len(futures_list[0])
        
        # Check if we have full trajectories (15 points) or just final returns (1 point)
        if trajectory_length >= 15:
            # Full 15-point trajectories available
            futures = np.array(futures_list)  # Shape: (n_neighbors, 15)
            
            # Weighted mean trajectory
            mean_trajectory = np.average(futures, axis=0, weights=weights)
            std_trajectory = np.sqrt(np.average((futures - mean_trajectory)**2, axis=0, weights=weights))
            
            # Final returns for probability calculation
            final_returns = futures[:, -1]
            mean_return = float(mean_trajectory[-1])
            std_return = float(std_trajectory[-1])
            
            mean_trajectory_list = [round(float(x), 4) for x in mean_trajectory]
            std_trajectory_list = [round(float(x), 4) for x in std_trajectory]
        else:
            # Only final return available - interpolate simple trajectory
            final_returns = np.array([fr[0] if isinstance(fr, list) else fr for fr in futures_list])
            mean_return = float(np.average(final_returns, weights=weights))
            std_return = float(np.sqrt(np.average((final_returns - mean_return)**2, weights=weights)))
            
            # Interpolate linear trajectory from 0 to final return
            mean_trajectory_list = [round(mean_return * (i / 14), 4) for i in range(15)]
            std_trajectory_list = [round(std_return * (i / 14), 4) for i in range(15)]
        
        # Calculate probabilities
        prob_up = float((final_returns > 0).sum() / len(final_returns))
        prob_down = float((final_returns < 0).sum() / len(final_returns))
        
        # Confidence based on consistency (agreement among neighbors)
        consistency = 1 - (std_return / (np.abs(mean_return) + 1e-6))
        confidence = "high" if consistency > 0.7 else "medium" if consistency > 0.4 else "low"
        
        return {
            "horizon_minutes": 15,
            "mean_return": round(mean_return, 4),
            "mean_trajectory": mean_trajectory_list,
            "std_trajectory": std_trajectory_list,
            "prob_up": round(prob_up, 3),
            "prob_down": round(prob_down, 3),
            "confidence": confidence,
            "best_case": round(float(np.percentile(final_returns, 90)), 4),
            "worst_case": round(float(np.percentile(final_returns, 10)), 4),
            "median_return": round(float(np.median(final_returns)), 4),
            "n_neighbors": len(neighbors_valid),
            "trajectory_points": trajectory_length,
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
            
            # Get the pattern prices used for search (last window_size prices)
            pattern_prices = prices[-settings.window_size:] if len(prices) >= settings.window_size else prices
            
            # Generate pattern times (relative minutes from now)
            now = datetime.now()
            pattern_times = [
                (now - timedelta(minutes=(len(pattern_prices) - i - 1))).strftime('%H:%M')
                for i in range(len(pattern_prices))
            ]
            
            return {
                "status": "success",
                "query": {
                    "symbol": symbol,
                    "window_minutes": settings.window_size,
                    "timestamp": start_time.isoformat(),
                    "cross_asset": cross_asset,
                    "mode": "realtime",
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
                "historical_context": {
                    "mode": "realtime",
                    "pattern_prices": pattern_prices,
                    "pattern_times": pattern_times,
                    "pattern_start": pattern_times[0] if pattern_times else None,
                    "pattern_end": pattern_times[-1] if pattern_times else None,
                },
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
            
            # Get ACTUAL future prices (15 min after the pattern end)
            # This is what actually happened after the pattern
            actual_future_end_mins = end_h * 60 + end_m + 15
            actual_future_end_h = actual_future_end_mins // 60
            actual_future_end_m = actual_future_end_mins % 60
            actual_future_end_time = f"{actual_future_end_h:02d}:{actual_future_end_m:02d}"
            
            actual_data = await self.get_historical_minute_data(
                symbol=symbol,
                date=date,
                start_time=time,  # Start from pattern end
                end_time=actual_future_end_time,
            )
            
            # Calculate actual returns
            actual_returns = None
            actual_final_return = None
            
            if "error" not in actual_data and len(actual_data.get("prices", [])) > 1:
                actual_prices = actual_data["prices"]
                base_price = prices[-1]  # Last price of pattern
                
                if base_price > 0:
                    actual_returns = [
                        round((p / base_price - 1) * 100, 4) 
                        for p in actual_prices[1:]  # Skip first (same as pattern end)
                    ]
                    if actual_returns:
                        actual_final_return = actual_returns[-1] if len(actual_returns) >= 15 else actual_returns[-1]
            
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
                
                # Add ACTUAL (what really happened)
                if actual_returns is not None:
                    forecast_return = result.get("forecast", {}).get("mean_return", 0)
                    forecast_direction = "up" if forecast_return > 0 else "down" if forecast_return < 0 else "neutral"
                    actual_direction = "up" if actual_final_return > 0 else "down" if actual_final_return < 0 else "neutral"
                    
                    result["actual"] = {
                        "returns": actual_returns,
                        "final_return": actual_final_return,
                        "direction": actual_direction,
                        "direction_correct": forecast_direction == actual_direction,
                        "error_vs_forecast": round(abs(forecast_return - actual_final_return), 4) if actual_final_return else None,
                    }
            
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

