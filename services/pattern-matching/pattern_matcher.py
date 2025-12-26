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

