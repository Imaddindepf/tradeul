"""
Historical Loader
Loads historical and reference data from FMP API using BATCH endpoints
Caches in Redis and persists to TimescaleDB

NOTA: Usa http_clients.fmp con connection pooling.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import sys
sys.path.append('/app')

from shared.config.settings import settings
from shared.config.fmp_endpoints import FMPEndpoints, LoadingStrategy
from shared.models.scanner import TickerMetadata
from shared.models.fmp import (
    FMPProfile, FMPQuote, FMPScreenerResult,
    FMPFloat, FMPFloatBulkResponse, FMPMarketCap
)
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger
from http_clients import http_clients

logger = get_logger(__name__)


class HistoricalLoader:
    """
    Loads and caches historical data using BATCH/BULK endpoints
    """
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
        self.fmp_api_key = settings.fmp_api_key
        self.endpoints = FMPEndpoints
        
        # Statistics
        self.tickers_loaded = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.api_calls = 0
        self.errors = 0
        self.start_time = time.time()
    
    # =============================================
    # TICKER METADATA
    # =============================================
    
    async def get_ticker_metadata(
        self,
        symbol: str,
        use_cache: bool = True
    ) -> Optional[TickerMetadata]:
        """
        Get ticker metadata (from cache or load from FMP)
        
        Args:
            symbol: Ticker symbol
            use_cache: Whether to use cached data
        
        Returns:
            TickerMetadata or None if not found
        """
        symbol = symbol.upper()
        
        # Try cache first
        if use_cache:
            cached = await self._get_from_cache(symbol)
            if cached:
                self.cache_hits += 1
                return cached
            self.cache_misses += 1
        
        # Load from FMP
        metadata = await self.load_and_cache_ticker(symbol)
        return metadata
    
    async def get_bulk_metadata(
        self,
        symbols: List[str],
        use_cache: bool = True
    ) -> Dict[str, TickerMetadata]:
        """
        Get metadata for multiple tickers using BATCH endpoints
        
        Args:
            symbols: List of ticker symbols
            use_cache: Whether to use cached data
        
        Returns:
            Dict of {symbol: metadata}
        """
        results = {}
        symbols_to_load = []
        
        # Check cache first
        if use_cache:
            for symbol in symbols:
                cached = await self._get_from_cache(symbol)
                if cached:
                    results[symbol] = cached
                    self.cache_hits += 1
                else:
                    symbols_to_load.append(symbol)
                    self.cache_misses += 1
        else:
            symbols_to_load = symbols
        
        # Load remaining symbols in batches
        if symbols_to_load:
            logger.info(f"Loading {len(symbols_to_load)} symbols in batches")
            
            # Split into chunks of 100 for batch API
            chunks = LoadingStrategy.chunk_symbols(symbols_to_load, chunk_size=100)
            
            for chunk in chunks:
                try:
                    # Load quotes and profiles in batch
                    quotes = await self._fetch_batch_quotes(chunk)
                    profiles = await self._fetch_batch_profiles(chunk)
                    
                    # Combine and create metadata
                    for symbol in chunk:
                        quote = quotes.get(symbol)
                        profile = profiles.get(symbol)
                        
                        if quote or profile:
                            metadata = self._build_metadata(symbol, profile, quote)
                            results[symbol] = metadata
                            
                            # Cache and save
                            await self._save_to_cache(metadata)
                            await self._save_to_database(metadata)
                    
                    # Rate limiting
                    await asyncio.sleep(0.2)  # Brief pause between batches
                
                except Exception as e:
                    logger.error(f"Error loading batch", error=str(e))
        
        return results
    
    async def load_and_cache_ticker(self, symbol: str) -> Optional[TickerMetadata]:
        """
        Load ticker data from FMP and cache it (single ticker fallback)
        
        Args:
            symbol: Ticker symbol
        
        Returns:
            TickerMetadata or None
        """
        try:
            logger.info("Loading ticker from FMP", symbol=symbol)
            
            # Load profile and quote from FMP
            profile = await self._fetch_fmp_profile(symbol)
            quote = await self._fetch_fmp_quote(symbol)
            
            if not profile and not quote:
                logger.warning("No data found for ticker", symbol=symbol)
                return None
            
            # Build metadata
            metadata = self._build_metadata(symbol, profile, quote)
            
            # Cache in Redis
            await self._save_to_cache(metadata)
            
            # Save to database
            await self._save_to_database(metadata)
            
            self.tickers_loaded += 1
            
            logger.info("Ticker loaded", symbol=symbol)
            
            return metadata
        
        except Exception as e:
            self.errors += 1
            logger.error("Error loading ticker", symbol=symbol, error=str(e))
            return None
    
    # =============================================
    # UNIVERSE LOADING (OPTIMIZED)
    # =============================================
    
    async def load_universe_from_polygon_symbols(self) -> int:
        """
        Carga datos FMP para TODOS los símbolos del universo de Polygon
        
        Strategy OPTIMIZADO:
        1. Obtener símbolos activos de ticker_universe (ya cargados de Polygon)
        2. Load float data for all (paginated bulk, ~11 calls)
        3. Load quotes in batches of 100 (~120 calls)
        4. Load profiles in batches of 100 (~120 calls)
        
        Total: ~250 API calls para 11,882 tickers (vs 11,882 calls individuales)
        
        Returns:
            Number of tickers loaded with FMP data
        """
        logger.info("🚀 Pre-cargando datos FMP para universo de Polygon")
        
        try:
            # Step 1: Obtener símbolos del universo de Polygon
            logger.info("Step 1: Obteniendo símbolos del universo (Polygon)...")
            query = "SELECT symbol FROM ticker_universe WHERE is_active = true ORDER BY symbol"
            rows = await self.db.fetch(query)
            symbols = [row["symbol"] for row in rows]
            
            if not symbols:
                logger.warning("No symbols found in ticker_universe")
                return 0
            
            logger.info(f"✓ Found {len(symbols)} symbols from Polygon universe")
            
            # Step 2: Load float data (bulk, paginated)
            logger.info("Step 2: Loading float data (bulk)...")
            float_data = await self._fetch_all_float_data()
            logger.info(f"✓ Loaded float data for {len(float_data)} tickers")
            
            # Step 3: Load quotes in batches of 100
            logger.info("Step 3: Loading quotes (batched)...")
            quotes_data = await self._fetch_all_quotes_batched(symbols)
            logger.info(f"✓ Loaded quotes for {len(quotes_data)} tickers")
            
            # Step 4: Load profiles in batches of 100
            logger.info("Step 4: Loading profiles (batched)...")
            profiles_data = await self._fetch_all_profiles_batched(symbols)
            logger.info(f"✓ Loaded profiles for {len(profiles_data)} tickers")
            
            # Step 5: Combine all data and create metadata
            logger.info("Step 5: Combining data and saving...")
            loaded_count = 0
            
            for symbol in symbols:
                try:
                    profile = profiles_data.get(symbol)
                    quote = quotes_data.get(symbol)
                    float_info = float_data.get(symbol)
                    
                    # Build metadata
                    metadata = self._build_metadata(symbol, profile, quote)
                    
                    # Add float data if available
                    if float_info:
                        metadata.float_shares = float_info.get("floatShares")
                        metadata.shares_outstanding = float_info.get("outstandingShares")
                    
                    # Cache and save
                    await self._save_to_cache(metadata)
                    await self._save_to_database(metadata)
                    
                    loaded_count += 1
                    
                    # Progress logging
                    if loaded_count % 1000 == 0:
                        logger.info(f"Progress: {loaded_count}/{len(symbols)} tickers")
                
                except Exception as e:
                    logger.error(f"Error processing {symbol}", error=str(e))
            
            self.tickers_loaded += loaded_count
            
            logger.info(f"✅ Universe loaded: {loaded_count} tickers")
            
            return loaded_count
        
        except Exception as e:
            logger.error("Error loading universe", error=str(e))
            return 0
    
    async def get_universe_symbols(self, active_only: bool = True) -> List[str]:
        """Get list of symbols in the universe"""
        try:
            if active_only:
                query = "SELECT symbol FROM ticker_universe WHERE is_active = true ORDER BY symbol"
            else:
                query = "SELECT symbol FROM ticker_universe ORDER BY symbol"
            
            rows = await self.db.fetch(query)
            return [row["symbol"] for row in rows]
        
        except Exception as e:
            logger.error("Error getting universe symbols", error=str(e))
            return []
    
    # =============================================
    # FMP BULK/BATCH API CALLS
    # =============================================
    
    async def _fetch_available_traded(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Fetch all available traded stocks (1 API call)
        Endpoint: /api/v3/available-traded/list
        """
        try:
            # Usar cliente FMP con connection pooling
            data = await http_clients.fmp.get_available_traded()
            self.api_calls += 1
            
            if data:
                # Filter US exchanges
                us_stocks = [
                    item for item in data
                    if item.get("exchangeShortName") in ["NASDAQ", "NYSE", "AMEX"]
                    and item.get("type") == "stock"
                ]
                
                if limit:
                    us_stocks = us_stocks[:limit]
                
                return us_stocks
            
            return []
        
        except Exception as e:
            logger.error("Error fetching available traded", error=str(e))
            return []
    
    async def _fetch_all_float_data(self) -> Dict[str, Dict]:
        """
        Fetch ALL float data using paginated bulk endpoint
        Endpoint: /stable/shares-float-all
        """
        float_data = {}
        page = 0
        
        try:
            while True:
                # Usar cliente FMP con connection pooling
                data = await http_clients.fmp.get_float_all(page=page, limit=1000)
                self.api_calls += 1
                
                if not data or len(data) == 0:
                    break  # No more data
                
                # Process page
                for item in data:
                    symbol = item.get("symbol")
                    if symbol:
                        float_data[symbol] = {
                            "floatShares": item.get("floatShares"),
                            "outstandingShares": item.get("outstandingShares"),
                            "freeFloat": item.get("freeFloat")
                        }
                
                logger.info(f"Loaded float page {page}: {len(data)} items")
                
                # Continue to next page
                page += 1
                await asyncio.sleep(0.2)  # Rate limiting
            
            return float_data
        
        except Exception as e:
            logger.error("Error fetching float data", error=str(e))
            return float_data
    
    async def _fetch_all_quotes_batched(self, symbols: List[str]) -> Dict[str, FMPQuote]:
        """
        Fetch quotes for all symbols in batches of 100
        Endpoint: /api/v3/quote?symbols=AAPL,MSFT,...
        """
        quotes = {}
        chunks = LoadingStrategy.chunk_symbols(symbols, chunk_size=100)
        
        for idx, chunk in enumerate(chunks):
            try:
                batch_quotes = await self._fetch_batch_quotes(chunk)
                quotes.update(batch_quotes)
                
                if (idx + 1) % 10 == 0:
                    logger.info(f"Loaded {(idx + 1) * 100} quotes")
                
                await asyncio.sleep(0.15)  # Rate limiting
            
            except Exception as e:
                logger.error(f"Error loading quote batch {idx}", error=str(e))
        
        return quotes
    
    async def _fetch_all_profiles_batched(self, symbols: List[str]) -> Dict[str, FMPProfile]:
        """
        Fetch profiles for all symbols in batches of 100
        Endpoint: /api/v3/profile?symbols=AAPL,MSFT,...
        """
        profiles = {}
        chunks = LoadingStrategy.chunk_symbols(symbols, chunk_size=100)
        
        for idx, chunk in enumerate(chunks):
            try:
                batch_profiles = await self._fetch_batch_profiles(chunk)
                profiles.update(batch_profiles)
                
                if (idx + 1) % 10 == 0:
                    logger.info(f"Loaded {(idx + 1) * 100} profiles")
                
                await asyncio.sleep(0.15)  # Rate limiting
            
            except Exception as e:
                logger.error(f"Error loading profile batch {idx}", error=str(e))
        
        return profiles
    
    async def _fetch_batch_quotes(self, symbols: List[str]) -> Dict[str, FMPQuote]:
        """Fetch quotes for a batch of symbols (max 100)"""
        try:
            # Usar cliente FMP con connection pooling
            data = await http_clients.fmp.get_batch_quotes(symbols)
            self.api_calls += 1
            
            if data:
                return {
                    item["symbol"]: FMPQuote(**item)
                    for item in data
                    if "symbol" in item
                }
            
            return {}
        
        except Exception as e:
            logger.error("Error fetching batch quotes", error=str(e))
            return {}
    
    async def _fetch_batch_profiles(self, symbols: List[str]) -> Dict[str, FMPProfile]:
        """Fetch profiles for a batch of symbols (max 100)"""
        try:
            # Usar cliente FMP con connection pooling
            data = await http_clients.fmp.get_batch_profiles(symbols)
            self.api_calls += 1
            
            if data:
                return {
                    item["symbol"]: FMPProfile(**item)
                    for item in data
                    if "symbol" in item
                }
            
            return {}
        
        except Exception as e:
            logger.error("Error fetching batch profiles", error=str(e))
            return {}
    
    # =============================================
    # SINGLE TICKER API CALLS (FALLBACK)
    # =============================================
    
    async def _fetch_fmp_profile(self, symbol: str) -> Optional[FMPProfile]:
        """Fetch company profile from FMP (single ticker)"""
        try:
            # Usar cliente FMP con connection pooling
            data = await http_clients.fmp.get_profile(symbol)
            self.api_calls += 1
            
            if data and len(data) > 0:
                return FMPProfile(**data[0])
            
            return None
        
        except Exception as e:
            logger.error("Error fetching FMP profile", symbol=symbol, error=str(e))
            return None
    
    async def _fetch_fmp_quote(self, symbol: str) -> Optional[FMPQuote]:
        """Fetch quote from FMP (single ticker)"""
        try:
            # Usar cliente FMP con connection pooling
            data = await http_clients.fmp.get_quote(symbol)
            self.api_calls += 1
            
            if data and len(data) > 0:
                return FMPQuote(**data[0])
            
            return None
        
        except Exception as e:
            logger.error("Error fetching FMP quote", symbol=symbol, error=str(e))
            return None
    
    # =============================================
    # DATA TRANSFORMATION
    # =============================================
    
    def _build_metadata(
        self,
        symbol: str,
        profile: Optional[FMPProfile],
        quote: Optional[FMPQuote]
    ) -> TickerMetadata:
        """Build TickerMetadata from FMP data"""
        return TickerMetadata(
            symbol=symbol,
            company_name=profile.companyName if profile else None,
            exchange=profile.exchange if profile else (quote.exchange if quote else None),
            sector=profile.sector if profile else None,
            industry=profile.industry if profile else None,
            market_cap=profile.mktCap if profile else (quote.marketCap if quote else None),
            float_shares=None,  # Will be populated from float data
            shares_outstanding=quote.sharesOutstanding if quote else None,
            avg_volume_30d=profile.volAvg if profile else (quote.avgVolume if quote else None),
            avg_volume_10d=None,
            avg_price_30d=None,
            beta=profile.beta if profile else None,
            is_etf=profile.isEtf if profile else False,
            is_actively_trading=profile.isActivelyTrading if profile else True,
            updated_at=datetime.now()
        )
    
    # =============================================
    # CACHE OPERATIONS
    # =============================================
    
    async def _get_from_cache(self, symbol: str) -> Optional[TickerMetadata]:
        """Get ticker metadata from Redis cache"""
        try:
            key = f"{settings.key_prefix_metadata}:ticker:{symbol}"
            data = await self.redis.get(key, deserialize=True)
            
            if data:
                return TickerMetadata(**data)
            
            return None
        
        except Exception as e:
            logger.error("Error getting from cache", symbol=symbol, error=str(e))
            return None
    
    async def _save_to_cache(self, metadata: TickerMetadata) -> None:
        """Save ticker metadata to Redis cache"""
        try:
            key = f"{settings.key_prefix_metadata}:ticker:{metadata.symbol}"
            await self.redis.set(
                key,
                metadata.model_dump(mode='json'),  # Serializa datetime correctamente
                ttl=settings.cache_ttl_metadata
            )
        
        except Exception as e:
            logger.error("Error saving to cache", symbol=metadata.symbol, error=str(e))
    
    async def clear_cache(self, symbol: str) -> None:
        """Clear cache for a specific symbol"""
        key = f"{settings.key_prefix_metadata}:ticker:{symbol}"
        await self.redis.delete(key)
    
    async def clear_all_cache(self) -> None:
        """Clear all metadata cache"""
        logger.warning("Clear all cache not fully implemented")
    
    # =============================================
    # DATABASE OPERATIONS
    # =============================================
    
    async def _save_to_database(self, metadata: TickerMetadata) -> None:
        """
        MODIFICADO: Ya NO guarda en ticker_metadata (responsabilidad de data_maintenance)
        Solo actualiza ticker_universe para mantener símbolos activos
        """
        try:
            # Solo actualizar ticker_universe (mantener símbolo activo)
            await self._upsert_universe_entry(metadata.symbol)
            
            logger.debug("universe_entry_updated", symbol=metadata.symbol)
        
        except Exception as e:
            logger.error("Error updating universe", symbol=metadata.symbol, error=str(e))
    
    async def _upsert_universe_entry(self, symbol: str) -> None:
        """Update ticker in universe table"""
        query = """
            INSERT INTO ticker_universe (symbol, is_active, last_seen)
            VALUES ($1, true, NOW())
            ON CONFLICT (symbol) DO UPDATE SET
                is_active = true,
                last_seen = NOW()
        """
        await self.db.execute(query, symbol)
    
    # =============================================
    # STATISTICS
    # =============================================
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get loader statistics"""
        uptime = time.time() - self.start_time
        
        # Get universe stats from database
        universe_count = await self.db.fetchval(
            "SELECT COUNT(*) FROM ticker_universe WHERE is_active = true"
        )
        
        return {
            "tickers_loaded": self.tickers_loaded,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": (
                self.cache_hits / (self.cache_hits + self.cache_misses)
                if (self.cache_hits + self.cache_misses) > 0
                else 0
            ),
            "api_calls": self.api_calls,
            "errors": self.errors,
            "uptime_seconds": int(uptime),
            "universe_size": universe_count or 0
        }
