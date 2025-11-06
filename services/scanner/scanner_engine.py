"""
Scanner Engine
Core scanning logic: combines real-time data with historical data,
calculates RVOL, applies filters, and publishes results
"""

import asyncio
import time
import json
from datetime import datetime, time as time_type
from typing import Optional, List, Dict, Any, Tuple
import httpx

import sys
sys.path.append('/app')

from shared.config.settings import settings
from shared.models.polygon import PolygonSnapshot
from shared.models.scanner import (
    ScannerTicker,
    ScannerResult,
    FilterConfig,
    FilterParameters,
    TickerMetadata
)
from shared.enums.market_session import MarketSession
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

# Importar nuevos módulos de categorización
from gap_calculator import GapCalculator, GapTracker
from scanner_categories import ScannerCategorizer, ScannerCategory

logger = get_logger(__name__)


class ScannerEngine:
    """
    Core scanner engine
    """
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
        
        # Filters
        self.filters: List[FilterConfig] = []
        self.last_filter_load: Optional[datetime] = None
        
        # Current market session
        self.current_session: MarketSession = MarketSession.CLOSED
        
        # Statistics
        self.total_scans = 0
        self.total_tickers_scanned = 0
        self.total_tickers_filtered = 0
        self.last_scan_time: Optional[datetime] = None
        self.last_scan_duration_ms: Optional[float] = None
        self.start_time = time.time()
        
        # Stream position (for reading snapshots)
        self.stream_position = "0"
        
        # Categorization (NUEVO)
        self.gap_calculator = GapCalculator()
        self.gap_tracker = GapTracker()
        self.categorizer = ScannerCategorizer()
        
        # Cache de categorías (última categorización)
        self.last_categories: Dict[str, List[ScannerTicker]] = {}
        self.last_categorization_time: Optional[datetime] = None
        
        # Cache de tickers filtrados completos (en memoria)
        self.last_filtered_tickers: List[ScannerTicker] = []
        self.last_filtered_time: Optional[datetime] = None
        
        # NEW: Sistema de deltas (snapshot + incremental updates)
        self.last_rankings: Dict[str, List[ScannerTicker]] = {}  # Por categoría
        self.sequence_numbers: Dict[str, int] = {}  # Sequence number por categoría
        
        # RVOL viene directamente en las tuplas (snapshot, rvol) - no necesita dict
        
        # Metadata cache (LRU con TTL en memoria de proceso)
        self._metadata_cache: Dict[str, Tuple[float, TickerMetadata]] = {}
        self._metadata_cache_maxsize: int = 200_000
        # TTL por defecto: 30 minutos
        self._metadata_cache_ttl_seconds: int = 1800
    
    async def initialize(self) -> None:
        """Initialize the scanner engine"""
        logger.info("Initializing ScannerEngine")
        
        # Load filters from database
        await self.reload_filters()
        
        # Get current market session
        await self._update_market_session()
        
        logger.info(
            "ScannerEngine initialized",
            filters_loaded=len(self.filters),
            session=self.current_session
        )
    
    # =============================================
    # MAIN SCAN LOGIC
    # =============================================
    
    async def run_scan(self) -> Optional[ScannerResult]:
        """
        Run a complete scan cycle
        
        Returns:
            ScannerResult with filtered tickers
        """
        start = time.time()
        
        try:
            # Update market session
            await self._update_market_session()
            
            # Read enriched snapshots from Redis stream (tuplas de snapshot + rvol)
            enriched_snapshots = await self._read_snapshots()
            
            if not enriched_snapshots:
                logger.debug("No new snapshots to process")
                return None
            
            logger.info(f"Processing {len(enriched_snapshots)} enriched snapshots")
            
            # OPTIMIZADO: Enriquecer + Filtrar + Score en UN SOLO bucle
            scored_tickers = await self._process_snapshots_optimized(enriched_snapshots)
            
            # Limit to max filtered tickers
            if len(scored_tickers) > settings.max_filtered_tickers:
                scored_tickers = scored_tickers[:settings.max_filtered_tickers]
            
            # Guardar tickers filtrados en cache (PROFESIONAL)
            if scored_tickers:
                # 1. Cache en memoria (inmediato)
                self.last_filtered_tickers = scored_tickers
                self.last_filtered_time = datetime.now()
                
                # 2. Cache en Redis (persistente, TTL 60 seg)
                await self._save_filtered_tickers_to_cache(scored_tickers)
                
                # 3. Categorizar (usa tickers en memoria)
                await self.categorize_filtered_tickers(scored_tickers)
            
            # Publish filtered tickers to stream (DESACTIVADO - stream huérfano sin consumidores)
            # await self._publish_filtered_tickers(scored_tickers)
            
            # Save scan results to database
            await self._save_scan_results(scored_tickers)
            
            # Update statistics
            elapsed = (time.time() - start) * 1000
            self.total_scans += 1
            self.total_tickers_scanned += len(enriched_snapshots)
            self.total_tickers_filtered += len(scored_tickers)
            self.last_scan_time = datetime.now()
            self.last_scan_duration_ms = elapsed
            
            # Build result
            result = ScannerResult(
                timestamp=datetime.now(),
                session=self.current_session,
                total_universe_size=len(enriched_snapshots),
                filtered_count=len(scored_tickers),
                tickers=scored_tickers,
                filters_applied=[f.name for f in self.filters if f.enabled],
                scan_duration_ms=elapsed
            )
            
            return result
        
        except Exception as e:
            logger.error("Error running scan", error=str(e))
            return None
    
    # =============================================
    # DATA ENRICHMENT
    # =============================================
    
    async def _read_snapshots(self):
        """
        NUEVO: Lee snapshot COMPLETO enriquecido desde cache
        
        Esto asegura que:
        - Todos los tickers son del MISMO momento
        - No mezclamos datos de diferentes snapshots
        - Procesamiento consistente y profesional
        
        Returns:
            Lista de tuplas (snapshot, rvol, atr_data) de UN SOLO snapshot completo
        """
        try:
            # Leer snapshot enriquecido completo
            enriched_data = await self.redis.get("snapshot:enriched:latest")
            
            if not enriched_data:
                logger.debug("No enriched snapshot available yet")
                return []
            
            # Verificar si ya procesamos este snapshot
            snapshot_timestamp = enriched_data.get('timestamp')
            
            if not hasattr(self, 'last_snapshot_timestamp'):
                self.last_snapshot_timestamp = None
            
            if snapshot_timestamp == self.last_snapshot_timestamp:
                # Ya procesado, esperar nuevo snapshot
                return []
            
            # Nuevo snapshot! Procesarlo
            tickers_data = enriched_data.get('tickers', [])
            
            if not tickers_data:
                return []
            
            logger.info(f"Reading complete enriched snapshot",
                       tickers=len(tickers_data),
                       timestamp=snapshot_timestamp)
            
            # Convertir a lista de tuplas (snapshot, rvol, atr_data)
            enriched_snapshots = []
            
            for ticker_data in tickers_data:
                try:
                    # Parsear snapshot
                    snapshot = PolygonSnapshot(**ticker_data)
                    rvol = ticker_data.get('rvol')
                    
                    # Extraer ATR data e intraday high/low
                    atr_data = {
                        'atr': ticker_data.get('atr'),
                        'atr_percent': ticker_data.get('atr_percent'),
                        'intraday_high': ticker_data.get('intraday_high'),
                        'intraday_low': ticker_data.get('intraday_low')
                    }
                    
                    enriched_snapshots.append((snapshot, rvol, atr_data))
                
                except Exception as e:
                    logger.error("Error parsing ticker", 
                                ticker=ticker_data.get('ticker'), 
                                error=str(e))
            
            # Guardar timestamp para no reprocesar
            self.last_snapshot_timestamp = snapshot_timestamp
            
            return enriched_snapshots
        
        except Exception as e:
            logger.error("Error reading enriched snapshot", error=str(e))
            return []

    # =============================================
    # METADATA BATCH WITH IN-PROCESS CACHE
    # =============================================
    
    def _metadata_cache_get(self, symbol: str) -> Optional[TickerMetadata]:
        entry = self._metadata_cache.get(symbol)
        if not entry:
            return None
        expires_at, metadata = entry
        if time.time() > expires_at:
            # Expirado
            self._metadata_cache.pop(symbol, None)
            return None
        return metadata

    def _metadata_cache_set(self, symbol: str, metadata: TickerMetadata) -> None:
        # Evict simple: si excede tamaño, eliminar items antiguos arbitrariamente
        # (para simplicidad; dict no mantiene orden. Para LRU real usar OrderedDict)
        if len(self._metadata_cache) >= self._metadata_cache_maxsize:
            # eliminar ~1% para evitar churning excesivo
            to_remove = max(1, self._metadata_cache_maxsize // 100)
            for k in list(self._metadata_cache.keys())[:to_remove]:
                self._metadata_cache.pop(k, None)
        self._metadata_cache[symbol] = (time.time() + self._metadata_cache_ttl_seconds, metadata)

    async def _get_metadata_batch_cached(self, symbols: List[str]) -> Dict[str, TickerMetadata]:
        """Obtiene metadata para símbolos combinando caché local + Redis en chunks.
        No cambia la cadencia de snapshots.
        """
        results: Dict[str, TickerMetadata] = {}

        # 1) Hits de caché
        misses: List[str] = []
        for sym in symbols:
            meta = self._metadata_cache_get(sym)
            if meta is not None:
                results[sym] = meta
            else:
                misses.append(sym)

        if not misses:
            return results

        # 2) Fetch de Redis en chunks con MGET (pipeline implícito en redis-py para MGET)
        CHUNK_SIZE = 1000
        for i in range(0, len(misses), CHUNK_SIZE):
            chunk = misses[i:i+CHUNK_SIZE]
            keys = [f"{settings.key_prefix_metadata}:ticker:{sym}" for sym in chunk]
            try:
                metadata_results = await self.redis.client.mget(keys)
            except Exception as e:
                logger.error("Error MGET metadata chunk", size=len(chunk), error=str(e))
                continue

            for sym, raw in zip(chunk, metadata_results):
                if not raw:
                    continue
                try:
                    data = json.loads(raw) if isinstance(raw, str) else raw
                    meta = TickerMetadata(**data)
                    results[sym] = meta
                    self._metadata_cache_set(sym, meta)
                except Exception as e:
                    logger.error("Error parsing metadata for symbol", symbol=sym, error=str(e))

        return results
    
    async def _process_snapshots_optimized(
        self,
        enriched_snapshots
    ) -> List[ScannerTicker]:
        """
        OPTIMIZADO: Procesa snapshots en UN SOLO bucle
        Combina: enriquecimiento + filtrado + deduplicación + scoring
        
        Args:
            enriched_snapshots: Lista de tuplas (snapshot, rvol, atr_data)
        """
        # OPTIMIZACIÓN CRÍTICA: Batch MGET de TODAS las metadatas de una vez
        
        # 1. Recopilar símbolos únicos con filtro temprano de precio
        unique_snapshots = []
        seen_symbols = set()
        
        for snapshot, rvol, atr_data in enriched_snapshots:
            # Filtro temprano: excluir precios < 0.5 para evitar MGET masivo
            cp = snapshot.current_price
            if cp is not None and cp < 0.5:
                continue
            symbol = snapshot.ticker
            if symbol not in seen_symbols:
                seen_symbols.add(symbol)
                unique_snapshots.append((snapshot, rvol, atr_data))
        
        # 2-4. Metadata con caché local + MGET paginado solo para misses
        symbols = [s.ticker for s, r, a in unique_snapshots]
        metadatas = await self._get_metadata_batch_cached(symbols)
        
        # 5. Procesar con metadatas ya disponibles
        filtered_and_scored = []
        
        for snapshot, rvol, atr_data in unique_snapshots:
            try:
                symbol = snapshot.ticker
                
                # Validaciones básicas
                if not snapshot.current_price or snapshot.current_price <= 0:
                    continue
                
                if not snapshot.current_volume or snapshot.current_volume <= 0:
                    continue
                
                # Get metadata del dict (ya fue fetched con MGET)
                metadata = metadatas.get(symbol)
                if not metadata:
                    continue  # EARLY EXIT
                
                # 4. RVOL ya lo tenemos (parámetro de la tupla)
                # No necesita buscar en dict
                
                # 5. Build ticker inline
                ticker = self._build_scanner_ticker_inline(snapshot, metadata, rvol, atr_data)
                if not ticker:
                    continue
                
                # 6. Enhance con gaps (solo cálculos)
                ticker = self.enhance_ticker_with_gaps(ticker, snapshot)
                
                # 7. FILTRAR INMEDIATAMENTE
                if not self._passes_all_filters(ticker):
                    continue  # EARLY EXIT - no procesa más
                
                # 8. Calcular score SOLO si pasó filtros
                ticker.score = self._calculate_score_inline(ticker)
                
                filtered_and_scored.append(ticker)
            
            except Exception as e:
                logger.error("Error processing ticker", ticker=snapshot.ticker, error=str(e))
        
        # Sort por score (necesario como operación separada)
        filtered_and_scored.sort(key=lambda t: t.score, reverse=True)
        
        # Asignar ranks
        for idx, ticker in enumerate(filtered_and_scored):
            ticker.rank = idx + 1
        
        return filtered_and_scored
    
    async def _enrich_and_calculate(
        self,
        snapshots: List[PolygonSnapshot]
    ) -> List[ScannerTicker]:
        """
        Enrich snapshots with historical data and calculate indicators
        
        Args:
            snapshots: Raw snapshots from Polygon
        
        Returns:
            List of enriched ScannerTicker objects
        """
        enriched = []
        
        for snapshot in snapshots:
            try:
                # Get metadata from cache/database
                metadata = await self._get_ticker_metadata(snapshot.ticker)
                
                if not metadata:
                    continue
                
                # Build scanner ticker
                ticker = await self._build_scanner_ticker(snapshot, metadata, atr_data)
                
                if ticker:
                    # Enriquecer con cálculos de gaps (NUEVO)
                    ticker = self.enhance_ticker_with_gaps(ticker, snapshot)
                    enriched.append(ticker)
            
            except Exception as e:
                logger.error("Error enriching ticker", ticker=snapshot.ticker, error=str(e))
        
        return enriched
    
    async def _get_ticker_metadata(self, symbol: str) -> Optional[TickerMetadata]:
        """
        Get ticker metadata from Redis cache with BD fallback
        
        Strategy:
        1. Buscar en Redis cache (rápido)
        2. Si no existe, buscar en TimescaleDB (fallback)
        3. Guardar en cache para próximas consultas
        """
        try:
            # 1. Intentar cache primero
            key = f"{settings.key_prefix_metadata}:ticker:{symbol}"
            data = await self.redis.get(key, deserialize=True)
            
            if data:
                return TickerMetadata(**data)
            
            # 2. Fallback a BD si no está en cache
            row = await self.db.get_ticker_metadata(symbol)
            
            if row:
                metadata = TickerMetadata(**dict(row))
                
                # Guardar en cache para próximas consultas (TTL 1 hora)
                await self.redis.set(
                    key,
                    metadata.model_dump(mode='json'),
                    ttl=3600
                )
                
                return metadata
            
            return None
        
        except Exception as e:
            logger.error("Error getting metadata", symbol=symbol, error=str(e))
            return None
    
    async def _build_scanner_ticker(
        self,
        snapshot: PolygonSnapshot,
        metadata: TickerMetadata,
        atr_data: Optional[Dict] = None
    ) -> Optional[ScannerTicker]:
        """Build ScannerTicker from snapshot, metadata, and ATR data"""
        try:
            price = snapshot.current_price
            volume_today = snapshot.current_volume
            
            if not price or not volume_today:
                return None
            
            # Get RVOL from Analytics service (pre-calculated and cached in Redis)
            rvol = await self._get_rvol_from_analytics(snapshot.ticker)
            rvol_slot = rvol  # Analytics ya calcula el RVOL por slot
            
            # Calculate price position metrics
            day_data = snapshot.day
            prev_day = snapshot.prevDay
            
            price_from_high = None
            price_from_low = None
            change_percent = None
            
            if day_data:
                if day_data.h and day_data.h > 0:
                    price_from_high = ((price - day_data.h) / day_data.h) * 100
                
                if day_data.l and day_data.l > 0:
                    price_from_low = ((price - day_data.l) / day_data.l) * 100
            
            if prev_day and prev_day.c and prev_day.c > 0:
                change_percent = ((price - prev_day.c) / prev_day.c) * 100
            
            # Extract ATR data
            atr = None
            atr_percent = None
            if atr_data:
                atr = atr_data.get('atr')
                atr_percent = atr_data.get('atr_percent')
            
            # Build ticker
            return ScannerTicker(
                symbol=snapshot.ticker,
                timestamp=datetime.now(),
                # Real-time data
                price=price,
                bid=snapshot.lastQuote.p if snapshot.lastQuote else None,
                ask=snapshot.lastQuote.P if snapshot.lastQuote else None,
                volume=volume_today,
                volume_today=volume_today,
                open=day_data.o if day_data else None,
                high=day_data.h if day_data else None,
                low=day_data.l if day_data else None,
                prev_close=prev_day.c if prev_day else None,
                prev_volume=prev_day.v if prev_day else None,
                change_percent=change_percent,
                # Historical data
                avg_volume_30d=metadata.avg_volume_30d,
                avg_volume_10d=metadata.avg_volume_10d,
                float_shares=metadata.float_shares,
                shares_outstanding=metadata.shares_outstanding,
                market_cap=metadata.market_cap,
                sector=metadata.sector,
                industry=metadata.industry,
                exchange=metadata.exchange,
                # Calculated indicators
                rvol=rvol,
                rvol_slot=rvol_slot,
                atr=atr,
                atr_percent=atr_percent,
                price_from_high=price_from_high,
                price_from_low=price_from_low,
                # Context
                session=self.current_session,
                score=0.0,  # Will be calculated later
                filters_matched=[]
            )
        
        except Exception as e:
            logger.error("Error building scanner ticker", error=str(e))
            return None
    
    async def _get_rvol_from_analytics(self, symbol: str) -> Optional[float]:
        """
        Obtiene RVOL del stream enriquecido (ya viene incluido)
        
        Fallback a hash si no está en enriched_data (compatibilidad)
        """
        try:
            # Primero intenta obtener del stream enriquecido
            if symbol in self.enriched_data:
                return self.enriched_data[symbol]
            
            # Fallback al hash (por compatibilidad)
            rvol_str = await self.redis.hget("rvol:current_slot", symbol)
            if rvol_str:
                return float(rvol_str)
            
            return None
        except Exception as e:
            logger.debug(f"Error getting RVOL", symbol=symbol, error=str(e))
            return None
    
    def _build_scanner_ticker_inline(
        self,
        snapshot: PolygonSnapshot,
        metadata: TickerMetadata,
        rvol: Optional[float],
        atr_data: Optional[Dict] = None
    ) -> Optional[ScannerTicker]:
        """Build scanner ticker inline (sin awaits innecesarios)"""
        try:
            price = snapshot.current_price
            volume_today = snapshot.current_volume
            
            # Calcular métricas
            day_data = snapshot.day
            prev_day = snapshot.prevDay
            
            price_from_high = None
            price_from_low = None
            change_percent = None
            
            if day_data:
                if day_data.h and day_data.h > 0:
                    price_from_high = ((price - day_data.h) / day_data.h) * 100
                if day_data.l and day_data.l > 0:
                    price_from_low = ((price - day_data.l) / day_data.l) * 100
            
            if prev_day and prev_day.c and prev_day.c > 0:
                change_percent = ((price - prev_day.c) / prev_day.c) * 100
            
            # Extract ATR data
            atr = None
            atr_percent = None
            if atr_data:
                atr = atr_data.get('atr')
                atr_percent = atr_data.get('atr_percent')
            
            # Extract intraday high/low (from enriched snapshot)
            intraday_high = atr_data.get('intraday_high') if atr_data else None
            intraday_low = atr_data.get('intraday_low') if atr_data else None
            
            return ScannerTicker(
                symbol=snapshot.ticker,
                timestamp=datetime.now(),
                price=price,
                bid=snapshot.lastQuote.p if snapshot.lastQuote else None,
                ask=snapshot.lastQuote.P if snapshot.lastQuote else None,
                volume=volume_today,
                volume_today=volume_today,
                open=day_data.o if day_data else None,
                high=day_data.h if day_data else None,
                low=day_data.l if day_data else None,
                intraday_high=intraday_high,
                intraday_low=intraday_low,
                prev_close=prev_day.c if prev_day else None,
                prev_volume=prev_day.v if prev_day else None,
                change_percent=change_percent,
                avg_volume_30d=metadata.avg_volume_30d,
                avg_volume_10d=metadata.avg_volume_10d,
                float_shares=metadata.float_shares,
                shares_outstanding=metadata.shares_outstanding,
                market_cap=metadata.market_cap,
                sector=metadata.sector,
                industry=metadata.industry,
                exchange=metadata.exchange,
                rvol=rvol,
                rvol_slot=rvol,
                atr=atr,
                atr_percent=atr_percent,
                price_from_high=price_from_high,
                price_from_low=price_from_low,
                session=self.current_session,
                score=0.0,
                filters_matched=[]
            )
        except Exception as e:
            logger.error("Error building ticker inline", error=str(e))
            return None
    
    def _passes_all_filters(self, ticker: ScannerTicker) -> bool:
        """Verifica si ticker pasa TODOS los filtros (sin await)"""
        for filter_config in self.filters:
            if not filter_config.enabled:
                continue
            
            if not filter_config.applies_to_session(self.current_session):
                continue
            
            if not self._apply_single_filter(ticker, filter_config):
                return False  # Falla un filtro
        
        return True  # Pasó todos
    
    def _calculate_score_inline(self, ticker: ScannerTicker) -> float:
        """Calcula score inline (sin await)"""
        score = 0.0
        
        if ticker.rvol:
            score += ticker.rvol * 10
        
        if ticker.volume_today and ticker.avg_volume_30d:
            volume_ratio = ticker.volume_today / ticker.avg_volume_30d
            score += volume_ratio * 5
        
        return score
    
    
    # =============================================
    # FILTERING
    # =============================================
    
    async def _apply_filters(
        self,
        tickers: List[ScannerTicker]
    ) -> List[ScannerTicker]:
        """Apply all enabled filters to tickers"""
        if not self.filters:
            return tickers
        
        filtered = []
        
        for ticker in tickers:
            # Check if ticker passes all filters
            passed = True
            matched_filters = []
            
            for filter_config in self.filters:
                if not filter_config.enabled:
                    continue
                
                # Check if filter applies to current session
                if not filter_config.applies_to_session(self.current_session):
                    continue
                
                # Apply filter
                if self._apply_single_filter(ticker, filter_config):
                    matched_filters.append(filter_config.name)
                else:
                    passed = False
                    break
            
            if passed and matched_filters:
                ticker.filters_matched = matched_filters
                filtered.append(ticker)
        
        return filtered
    
    def _apply_single_filter(
        self,
        ticker: ScannerTicker,
        filter_config: FilterConfig
    ) -> bool:
        """Apply a single filter to a ticker"""
        params = filter_config.parameters
        
        try:
            # RVOL filters
            # MODIFICADO: Si RVOL es None (sin volumen), no filtrar por RVOL
            # Útil para premarket temprano donde aún no hay actividad
            if params.min_rvol is not None and ticker.rvol is not None:
                if ticker.rvol < params.min_rvol:
                    return False
            
            if params.max_rvol is not None and ticker.rvol is not None:
                if ticker.rvol > params.max_rvol:
                    return False
            
            # Price filters
            if params.min_price is not None:
                if ticker.price < params.min_price:
                    return False
            
            if params.max_price is not None:
                if ticker.price > params.max_price:
                    return False
            
            # Volume filters
            if params.min_volume is not None:
                if ticker.volume_today < params.min_volume:
                    return False
            
            # Change filters
            if params.min_change_percent is not None:
                if ticker.change_percent is None or ticker.change_percent < params.min_change_percent:
                    return False
            
            if params.max_change_percent is not None:
                if ticker.change_percent is None or ticker.change_percent > params.max_change_percent:
                    return False
            
            # Market cap filters
            if params.min_market_cap is not None:
                if ticker.market_cap is None or ticker.market_cap < params.min_market_cap:
                    return False
            
            if params.max_market_cap is not None:
                if ticker.market_cap is None or ticker.market_cap > params.max_market_cap:
                    return False
            
            # Sector/Industry filters
            if params.sectors:
                if ticker.sector not in params.sectors:
                    return False
            
            if params.industries:
                if ticker.industry not in params.industries:
                    return False
            
            if params.exchanges:
                if ticker.exchange not in params.exchanges:
                    return False
            
            return True
        
        except Exception as e:
            logger.error("Error applying filter", filter=filter_config.name, error=str(e))
            return False
    
    # =============================================
    # SCORING AND RANKING
    # =============================================
    
    async def _score_and_rank(
        self,
        tickers: List[ScannerTicker]
    ) -> List[ScannerTicker]:
        """Calculate score and rank tickers"""
        # ELIMINAR DUPLICADOS primero (por symbol)
        seen = set()
        unique_tickers = []
        for ticker in tickers:
            if ticker.symbol not in seen:
                seen.add(ticker.symbol)
                unique_tickers.append(ticker)
        
        # Simple scoring: prioritize high RVOL and volume
        for ticker in unique_tickers:
            score = 0.0
            
            if ticker.rvol:
                score += ticker.rvol * 10
            
            if ticker.volume_today and ticker.avg_volume_30d:
                volume_ratio = ticker.volume_today / ticker.avg_volume_30d
                score += volume_ratio * 5
            
            ticker.score = score
        
        # Sort by score descending
        unique_tickers.sort(key=lambda t: t.score, reverse=True)
        
        # Assign ranks
        for idx, ticker in enumerate(unique_tickers):
            ticker.rank = idx + 1
        
        return unique_tickers
    
    # =============================================
    # PUBLISHING
    # =============================================
    
    async def _save_filtered_tickers_to_cache(self, tickers: List[ScannerTicker]) -> None:
        """
        Guarda tickers filtrados COMPLETOS en Redis
        
        Strategy (PROFESIONAL):
        1. Serializa tickers completos a JSON
        2. Guarda en Redis con TTL de 60 segundos
        3. Permite consultas rápidas sin re-procesamiento
        """
        try:
            if not tickers:
                return
            
            # Clave por sesión (PRE_MARKET, MARKET_OPEN, etc.)
            cache_key = f"scanner:filtered_complete:{self.current_session.value}"
            
            # Serializar todos los tickers a JSON
            tickers_data = [ticker.model_dump(mode='json') for ticker in tickers]
            
            # Guardar en Redis (TTL 60 seg - se refresca cada scan)
            await self.redis.set(
                cache_key,
                tickers_data,
                ttl=60,
                serialize=True  # Ya serializa internamente a JSON
            )
            
            logger.debug(
                f"Cached {len(tickers)} complete filtered tickers in Redis",
                session=self.current_session.value
            )
        
        except Exception as e:
            logger.error("Error caching filtered tickers", error=str(e))
    
    async def _publish_filtered_tickers(self, tickers: List[ScannerTicker]) -> None:
        """Publish filtered tickers to stream (para Analytics)"""
        try:
            # Publish to stream - IMPORTANTE: incluir volume_accumulated para Analytics
            for ticker in tickers:
                await self.redis.xadd(
                    settings.stream_filtered_tickers,
                    {
                        "symbol": ticker.symbol,
                        "price": ticker.price,
                        "volume_accumulated": ticker.volume_today,  # CRÍTICO para Analytics
                        "vwap": ticker.price,  # Aproximación
                        "rvol": ticker.rvol or 0,
                        "score": ticker.score,
                        "data": ticker.model_dump_json()
                    },
                    maxlen=10000
                )
            
            # Also save to sorted set for ranking quick access
            if tickers:
                mapping = {ticker.symbol: ticker.score for ticker in tickers}
                await self.redis.zadd(
                    f"{settings.key_prefix_scanner}:filtered:{self.current_session.value}",
                    mapping
                )
            
            logger.debug(f"Published {len(tickers)} filtered tickers to stream")
        
        except Exception as e:
            logger.error("Error publishing filtered tickers", error=str(e))
    
    async def _save_scan_results(self, tickers: List[ScannerTicker]) -> None:
        """Save scan results to database (OPTIMIZADO con batch insert)"""
        try:
            if not tickers:
                return
            
            # Preparar batch de datos
            batch_data = []
            for ticker in tickers:
                metadata_json = json.dumps(ticker.metadata) if ticker.metadata else None
                
                batch_data.append((
                    ticker.timestamp,
                    ticker.symbol,
                    ticker.session.value,
                    ticker.price,
                    ticker.volume,
                    ticker.volume_today,
                    ticker.change_percent,
                    ticker.rvol,
                    ticker.rvol_slot,
                    ticker.price_from_high,
                    ticker.price_from_low,
                    ticker.market_cap,
                    ticker.float_shares,
                    ticker.score,
                    ticker.filters_matched,
                    metadata_json
                ))
            
            # Batch INSERT (una sola query)
            query = """
                INSERT INTO scan_results (
                    time, symbol, session, price, volume, volume_today,
                    change_percent, rvol, rvol_slot, price_from_high, price_from_low,
                    market_cap, float_shares, score, filters_matched, metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            """
            
            await self.db.executemany(query, batch_data)
            
        except Exception as e:
            logger.error("Error saving scan results", error=str(e))
    
    # =============================================
    # FILTER MANAGEMENT
    # =============================================
    
    async def reload_filters(self) -> None:
        """Reload filters from database"""
        try:
            logger.info("Reloading filters from database")
            
            query = """
                SELECT id, name, description, enabled, filter_type, 
                       parameters, priority, created_at, updated_at
                FROM scanner_filters
                ORDER BY priority DESC, id
            """
            
            rows = await self.db.fetch(query)
            
            self.filters = []
            for row in rows:
                # Parse parameters (puede ser string JSON o dict)
                params = row["parameters"]
                if isinstance(params, str):
                    params = json.loads(params)
                
                filter_config = FilterConfig(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"],
                    enabled=row["enabled"],
                    filter_type=row["filter_type"],
                    parameters=FilterParameters(**params),
                    priority=row["priority"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"]
                )
                self.filters.append(filter_config)
            
            self.last_filter_load = datetime.now()
            
            logger.info(f"Loaded {len(self.filters)} filters")
        
        except Exception as e:
            logger.error("Error reloading filters", error=str(e))
    
    async def get_filters(self) -> List[FilterConfig]:
        """Get current filters"""
        return self.filters
    
    # =============================================
    # CATEGORIZATION (NUEVO - Sistema de Scanners Múltiples)
    # =============================================
    
    async def categorize_filtered_tickers(
        self,
        tickers: List[ScannerTicker],
        emit_deltas: bool = True
    ) -> Dict[str, List[ScannerTicker]]:
        """
        Categoriza tickers filtrados en múltiples scanners
        
        Args:
            tickers: Tickers filtrados
            emit_deltas: Si True, emite deltas incrementales
        
        Returns:
            Dict con {category_name: [tickers_ranked]}
        """
        try:
            # Obtener todas las categorías
            categories = self.categorizer.get_all_categories(tickers, limit_per_category=20)
            
            # NEW: Calcular y emitir deltas para cada categoría
            if emit_deltas:
                for category_name, new_ranking in categories.items():
                    # Obtener ranking anterior
                    old_ranking = self.last_rankings.get(category_name, [])
                    
                    if not old_ranking:
                        # Primera vez: emitir snapshot completo
                        logger.info(f"📸 First time for {category_name}, emitting snapshot")
                        await self.emit_full_snapshot(category_name, new_ranking)
                    else:
                        # Calcular deltas
                        deltas = self.calculate_ranking_deltas(
                            old_ranking,
                            new_ranking,
                            category_name
                        )
                        
                        # Emitir deltas si hay cambios
                        if deltas:
                            await self.emit_ranking_deltas(category_name, deltas)
                    
                    # Guardar ranking en Redis key (para que WebSocket Server pueda obtener snapshots)
                    await self._save_ranking_to_redis(category_name, new_ranking)
                    
                    # Guardar para próxima comparación
                    self.last_rankings[category_name] = new_ranking
            
            # Actualizar cache
            self.last_categories = categories
            self.last_categorization_time = datetime.now()
            
            logger.info(
                "tickers_categorized",
                total_tickers=len(tickers),
                categories_count=len(categories)
            )
            
            return categories
        
        except Exception as e:
            logger.error("Error categorizing tickers", error=str(e))
            return {}
    
    async def get_category(
        self,
        category: ScannerCategory,
        limit: int = 20
    ) -> List[ScannerTicker]:
        """
        Obtiene tickers de una categoría específica
        
        Usa cache de última categorización (actualizado cada scan)
        """
        try:
            # Usar cache de categorías (se actualiza en cada scan)
            if self.last_categories and category.value in self.last_categories:
                return self.last_categories.get(category.value, [])[:limit]
            
            # Si no hay categorías, devolver vacío
            # (Las categorías se actualizan automáticamente en cada scan)
            return []
        
        except Exception as e:
            logger.error("Error getting category", category=category, error=str(e))
            return []
    
    async def get_category_stats(self) -> Dict[str, int]:
        """
        Obtiene estadísticas de cuántos tickers hay en cada categoría
        
        Usa cache de última categorización
        """
        try:
            # Usar cache de categorías (se actualiza en cada scan)
            if self.last_categories:
                return {
                    category: len(tickers)
                    for category, tickers in self.last_categories.items()
                }
            
            return {}
        
        except Exception as e:
            logger.error("Error getting category stats", error=str(e))
            return {}
    
    def enhance_ticker_with_gaps(
        self,
        ticker: ScannerTicker,
        snapshot: PolygonSnapshot
    ) -> ScannerTicker:
        """
        Enriquece ticker con cálculos de gaps
        
        Agrega todos los tipos de gaps al metadata del ticker
        """
        try:
            # Calcular todos los gaps
            gaps = self.gap_calculator.calculate_all_gaps(ticker, snapshot)
            
            # Agregar a metadata
            if not ticker.metadata:
                ticker.metadata = {}
            
            ticker.metadata.update({
                'gaps': gaps,
                'gap_size_classification': self.gap_calculator.classify_gap_size(
                    gaps.get('gap_from_prev_close')
                ),
                'gap_metrics': self.gap_calculator.calculate_gap_metrics(ticker)
            })
            
            # Track gap en el tracker global
            if gaps.get('gap_from_prev_close') is not None:
                self.gap_tracker.track_gap(
                    ticker.symbol,
                    ticker.session,
                    gaps['gap_from_prev_close'],
                    ticker.timestamp
                )
            
            return ticker
        
        except Exception as e:
            logger.error("Error enhancing ticker with gaps", symbol=ticker.symbol, error=str(e))
            return ticker
    
    # =============================================
    # UTILITIES
    # =============================================
    
    async def _update_market_session(self) -> None:
        """Update current market session from Market Session Service"""
        try:
            url = f"http://{settings.market_session_host}:{settings.market_session_port}/api/session/current"
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                
                if response.status_code == 200:
                    data = response.json()
                    self.current_session = MarketSession(data["current_session"])
        
        except Exception as e:
            logger.error("Error updating market session", error=str(e))
    
    async def get_filtered_tickers(self, limit: int = 100) -> List[ScannerTicker]:
        """
        Obtiene tickers filtrados COMPLETOS
        
        Strategy (PROFESIONAL - Triple Capa):
        1. Cache en memoria (más rápido, <1ms)
        2. Redis persistente (rápido, ~5ms, sobrevive restart)
        3. Fallback: devolver vacío y esperar próximo scan
        
        Returns:
            Lista de ScannerTicker COMPLETOS (con todos los datos)
        """
        try:
            # CAPA 1: Memoria (más rápido)
            if (self.last_filtered_tickers and 
                self.last_filtered_time and 
                (datetime.now() - self.last_filtered_time).seconds < 60):
                
                logger.debug(f"Returning {len(self.last_filtered_tickers)} tickers from memory cache")
                return self.last_filtered_tickers[:limit]
            
            # CAPA 2: Redis persistente
            cache_key = f"scanner:filtered_complete:{self.current_session.value}"
            cached_data = await self.redis.get(cache_key, deserialize=True)
            
            if cached_data and isinstance(cached_data, list):
                # Reconstruir tickers desde JSON
                tickers = []
                for ticker_data in cached_data[:limit]:
                    try:
                        ticker = ScannerTicker(**ticker_data)
                        tickers.append(ticker)
                    except Exception as e:
                        logger.error(f"Error parsing cached ticker", error=str(e))
                        continue
                
                if tickers:
                    logger.debug(f"Returning {len(tickers)} tickers from Redis cache")
                    
                    # Actualizar cache en memoria
                    self.last_filtered_tickers = tickers
                    self.last_filtered_time = datetime.now()
                    
                    return tickers
            
            # CAPA 3: Sin datos - esperar próximo scan
            logger.debug("No filtered tickers in cache, waiting for next scan")
            return []
        
        except Exception as e:
            logger.error("Error getting filtered tickers", error=str(e))
            # En caso de error, intentar devolver memoria si existe
            if self.last_filtered_tickers:
                logger.warning("Returning stale memory cache due to error")
                return self.last_filtered_tickers[:limit]
            return []
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get scanner statistics"""
        uptime = time.time() - self.start_time
        
        return {
            "total_scans": self.total_scans,
            "total_tickers_scanned": self.total_tickers_scanned,
            "total_tickers_filtered": self.total_tickers_filtered,
            "filter_rate": (
                self.total_tickers_filtered / self.total_tickers_scanned
                if self.total_tickers_scanned > 0 else 0
            ),
            "last_scan_time": self.last_scan_time.isoformat() if self.last_scan_time else None,
            "last_scan_duration_ms": self.last_scan_duration_ms,
            "current_session": self.current_session.value,
            "filters_loaded": len(self.filters),
            "filters_enabled": sum(1 for f in self.filters if f.enabled),
            "uptime_seconds": int(uptime)
        }
    
    # =============================================
    # DELTA SYSTEM (Snapshot + Incremental Updates)
    # =============================================
    
    def calculate_ranking_deltas(
        self,
        old_ranking: List[ScannerTicker],
        new_ranking: List[ScannerTicker],
        list_name: str
    ) -> List[Dict]:
        """
        Calcula cambios incrementales entre dos rankings
        
        Args:
            old_ranking: Ranking anterior
            new_ranking: Ranking nuevo
            list_name: Nombre de la categoría (gappers_up, etc.)
        
        Returns:
            Lista de deltas en formato:
            [
                {"action": "add", "rank": 1, "symbol": "TSLA", "data": {...}},
                {"action": "remove", "symbol": "NVDA"},
                {"action": "update", "rank": 2, "symbol": "AAPL", "data": {...}},
                {"action": "rerank", "symbol": "GOOGL", "old_rank": 5, "new_rank": 3}
            ]
        """
        deltas = []
        
        # Convertir a dicts para comparación rápida
        old_dict = {t.symbol: (i, t) for i, t in enumerate(old_ranking)}
        new_dict = {t.symbol: (i, t) for i, t in enumerate(new_ranking)}
        
        # 1. Detectar tickers NUEVOS (añadidos al ranking)
        for symbol in new_dict:
            if symbol not in old_dict:
                rank, ticker = new_dict[symbol]
                deltas.append({
                    "action": "add",
                    "rank": rank,
                    "symbol": symbol,
                    "data": ticker.model_dump(mode='json')
                })
        
        # 2. Detectar tickers REMOVIDOS (salieron del ranking)
        for symbol in old_dict:
            if symbol not in new_dict:
                deltas.append({
                    "action": "remove",
                    "symbol": symbol
                })
        
        # 3. Detectar CAMBIOS en tickers existentes
        for symbol in new_dict:
            if symbol in old_dict:
                old_rank, old_ticker = old_dict[symbol]
                new_rank, new_ticker = new_dict[symbol]
                
                # 3a. Cambio de RANK (posición)
                if old_rank != new_rank:
                    deltas.append({
                        "action": "rerank",
                        "symbol": symbol,
                        "old_rank": old_rank,
                        "new_rank": new_rank
                    })
                
                # 3b. Cambio de DATOS (precio, gap, volumen, rvol, etc.)
                if self._ticker_data_changed(old_ticker, new_ticker):
                    deltas.append({
                        "action": "update",
                        "rank": new_rank,
                        "symbol": symbol,
                        "data": new_ticker.model_dump(mode='json')
                    })
        
        return deltas
    
    def _ticker_data_changed(
        self,
        old_ticker: ScannerTicker,
        new_ticker: ScannerTicker
    ) -> bool:
        """
        Verifica si los datos relevantes de un ticker cambiaron
        
        Compara campos importantes: precio, volumen, gap, rvol
        """
        # Umbral mínimo para considerar cambio (evitar ruido)
        PRICE_THRESHOLD = 0.01  # 1 centavo
        VOLUME_THRESHOLD = 1000  # 1k shares
        PERCENT_THRESHOLD = 0.01  # 0.01%
        
        # Precio cambió significativamente
        if old_ticker.price and new_ticker.price:
            if abs(new_ticker.price - old_ticker.price) > PRICE_THRESHOLD:
                return True
        
        # Volumen cambió significativamente
        if old_ticker.volume_today and new_ticker.volume_today:
            if abs(new_ticker.volume_today - old_ticker.volume_today) > VOLUME_THRESHOLD:
                return True
        
        # Gap% cambió
        if old_ticker.change_percent and new_ticker.change_percent:
            if abs(new_ticker.change_percent - old_ticker.change_percent) > PERCENT_THRESHOLD:
                return True
        
        # RVOL cambió
        if old_ticker.rvol and new_ticker.rvol:
            if abs(new_ticker.rvol - old_ticker.rvol) > 0.05:
                return True
        
        return False
    
    async def emit_ranking_deltas(
        self,
        list_name: str,
        deltas: List[Dict]
    ):
        """
        Emite deltas a Redis stream para que WebSocket Server los broadcaste
        
        IMPORTANTE: También actualiza el snapshot en Redis para que nuevos clientes
        reciban el estado actualizado.
        
        Args:
            list_name: Nombre de la categoría (gappers_up, etc.)
            deltas: Lista de cambios incrementales
        """
        if not deltas:
            return
        
        # Incrementar sequence number
        self.sequence_numbers[list_name] = self.sequence_numbers.get(list_name, 0) + 1
        sequence = self.sequence_numbers[list_name]
        
        # Crear mensaje
        message = {
            'type': 'delta',
            'list': list_name,
            'sequence': sequence,
            'deltas': json.dumps(deltas),
            'timestamp': datetime.now().isoformat(),
            'change_count': len(deltas)
        }
        
        # Publicar a stream
        try:
            await self.redis.xadd(
                settings.stream_ranking_deltas,
                message,
                maxlen=20000,
                approximate=True
            )
            
            # CRÍTICO: Actualizar sequence number en Redis para nuevos clientes
            await self.redis.set(
                f"scanner:sequence:{list_name}",
                sequence,
                ttl=86400  # 24 horas
            )
            
            logger.info(
                f"✅ Emitted ranking deltas",
                list=list_name,
                sequence=sequence,
                changes=len(deltas),
                adds=sum(1 for d in deltas if d['action'] == 'add'),
                removes=sum(1 for d in deltas if d['action'] == 'remove'),
                updates=sum(1 for d in deltas if d['action'] == 'update'),
                reranks=sum(1 for d in deltas if d['action'] == 'rerank')
            )
        
        except Exception as e:
            logger.error(f"Error emitting ranking deltas", error=str(e), list=list_name)
    
    async def _save_ranking_to_redis(
        self,
        list_name: str,
        tickers: List[ScannerTicker]
    ):
        """
        Guarda ranking en Redis key (para que WebSocket Server pueda obtener snapshots)
        
        IMPORTANTE: También guarda el sequence number actual para mantener sincronizado
        el snapshot que nuevos clientes recibirán.
        
        Args:
            list_name: Nombre de la categoría
            tickers: Ranking completo
        """
        try:
            # Convertir tickers a JSON
            ranking_data = [t.model_dump(mode='json') for t in tickers]
            
            # Obtener sequence number actual
            current_sequence = self.sequence_numbers.get(list_name, 0)
            
            # Guardar en key (snapshot)
            await self.redis.set(
                f"scanner:category:{list_name}",
                json.dumps(ranking_data),
                ttl=3600  # 1 hora
            )
            
            # Guardar sequence number (para sincronización)
            await self.redis.set(
                f"scanner:sequence:{list_name}",
                current_sequence,
                ttl=86400  # 24 horas
            )
            
            logger.debug(
                f"💾 Saved ranking to Redis",
                list=list_name,
                count=len(tickers),
                sequence=current_sequence
            )
        
        except Exception as e:
            logger.error(f"Error saving ranking to Redis", error=str(e), list=list_name)
    
    async def emit_full_snapshot(
        self,
        list_name: str,
        tickers: List[ScannerTicker]
    ):
        """
        Emite snapshot completo (usado en inicialización o resync)
        
        Args:
            list_name: Nombre de la categoría
            tickers: Ranking completo
        """
        # Incrementar sequence number
        self.sequence_numbers[list_name] = self.sequence_numbers.get(list_name, 0) + 1
        sequence = self.sequence_numbers[list_name]
        
        # Crear snapshot
        snapshot_data = [t.model_dump(mode='json') for t in tickers]
        
        message = {
            'type': 'snapshot',
            'list': list_name,
            'sequence': sequence,
            'rows': json.dumps(snapshot_data),
            'timestamp': datetime.now().isoformat(),
            'count': len(tickers)
        }
        
        # Publicar a stream
        try:
            await self.redis.xadd(
                settings.stream_ranking_deltas,
                message,
                maxlen=20000,
                approximate=True
            )
            
            # También guardar en key para consulta directa
            await self.redis.set(
                f"scanner:sequence:{list_name}",
                sequence,
                ttl=86400  # 24 horas
            )
            
            logger.info(
                f"📸 Emitted full snapshot",
                list=list_name,
                sequence=sequence,
                tickers_count=len(tickers)
            )
        
        except Exception as e:
            logger.error(f"Error emitting snapshot", error=str(e), list=list_name)

