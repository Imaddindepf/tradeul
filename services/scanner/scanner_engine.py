"""
Scanner Engine
Core scanning logic: combines real-time data with historical data,
calculates RVOL, applies filters, and publishes results

NOTA: Usa http_clients con connection pooling para llamadas HTTP.
"""

import asyncio
import time
import json
import traceback
from datetime import datetime, date, time as time_type, timedelta
from typing import Optional, List, Dict, Any, Tuple, Set
from zoneinfo import ZoneInfo

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
from shared.utils.redis_stream_manager import get_stream_manager

# Importar nuevos módulos de categorización
from gap_calculator import GapCalculator, GapTracker
from scanner_categories import ScannerCategorizer, ScannerCategory
from http_clients import http_clients
from postmarket_capture import PostMarketVolumeCapture

# Calculadores de metricas (refactorizacion)
# NOTE: PriceMetricsCalculator/VolumeMetricsCalculator removed — enrichment pipeline
# is now the single source of truth for derived price/volume metrics (Ticker Plant pattern)
from calculators import (
    SpreadMetricsCalculator,
    EnrichedDataExtractor
)

# Gestor de suscripciones (refactorizacion)
from subscriptions import SubscriptionManager

# Calculador de deltas (refactorizacion)
from ranking import calculate_ranking_deltas, ticker_data_changed

# Motor RETE para reglas de usuario
from rete import ReteManager, RuleOwnerType

logger = get_logger(__name__)


class ScannerEngine:
    """
    Core scanner engine
    """
    
    def __init__(
        self,
        redis_client: RedisClient,
        timescale_client: TimescaleClient,
        snapshot_manager=None,  # Optional SnapshotManager
        postmarket_capture=None  # Optional PostMarketVolumeCapture
    ):
        self.redis = redis_client
        self.db = timescale_client
        self.snapshot_manager = snapshot_manager  # 🔥 SnapshotManager para deltas
        self.postmarket_capture = postmarket_capture  # 🌙 Post-market volume capture
        
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
        self.last_rankings: Dict[str, List[ScannerTicker]] = {}  # Por categoría sistema
        self.sequence_numbers: Dict[str, int] = {}  # Sequence number por categoría
        
        # User scans: Rankings anteriores para calcular deltas
        self.last_user_scan_rankings: Dict[str, List[ScannerTicker]] = {}  # uscan_X → tickers
        self._user_scans_frozen = False  # Set True when freeze_user_scans_for_close() runs
        
        # Auto-subscription manager (para Polygon WS)
        self._subscription_manager = SubscriptionManager(redis_client)
        
        # Motor RETE para reglas de usuario y sistema
        self._rete_manager = ReteManager(redis_client, timescale_client)
        self._rete_enabled = True  # Feature flag para activar/desactivar RETE
        
        # RVOL viene directamente en las tuplas (snapshot, rvol) - no necesita dict
        
        # Metadata cache (LRU con TTL en memoria de proceso)
        self._metadata_cache: Dict[str, Tuple[float, TickerMetadata]] = {}
        self._metadata_cache_maxsize: int = 200_000
        # TTL por defecto: 30 minutos
        self._metadata_cache_ttl_seconds: int = 1800
        
        # 🌙 Cache local de volúmenes regulares para acceso síncrono en _build_scanner_ticker_inline
        self._regular_volumes_cache: Dict[str, int] = {}
    
    async def initialize(self) -> None:
        """Initialize the scanner engine"""
        logger.info("Initializing ScannerEngine")
        
        # Load filters from database
        await self.reload_filters()
        
        # Get current market session
        await self._update_market_session()
        
        # Initialize RETE engine
        if self._rete_enabled:
            await self._initialize_rete()
        
        logger.info(
            "ScannerEngine initialized",
            filters_loaded=len(self.filters),
            session=self.current_session
        )
    
    async def _initialize_rete(self) -> None:
        """Initialize RETE rule engine"""
        try:
            await self._rete_manager.initialize()
            stats = self._rete_manager.get_stats()
            logger.info("rete_initialized", **stats.get("network", {}))
        except Exception as e:
            logger.error("rete_init_error", error=str(e))
            self._rete_enabled = False
    
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
            all_valid_tickers = await self._process_snapshots_optimized(enriched_snapshots)
            
            # Recortar para categorías del sistema (top N por score)
            scored_tickers = all_valid_tickers[:settings.max_filtered_tickers] if len(all_valid_tickers) > settings.max_filtered_tickers else all_valid_tickers
            
            # Guardar tickers filtrados en cache
            if scored_tickers:
                # 1. Cache en memoria (inmediato)
                self.last_filtered_tickers = scored_tickers
                self.last_filtered_time = datetime.now()
                
                # 2. Cache en Redis (persistente, TTL 60 seg)
                await self._save_filtered_tickers_to_cache(scored_tickers)
                
                # 3. Categorizar sistema (top N) + User scans (universo completo)
                await self.categorize_filtered_tickers(scored_tickers, all_valid_tickers)
                
                # 4. AUTO-SUSCRIPCIÓN a Polygon WS
                await self._publish_filtered_tickers_for_subscription(scored_tickers)
            
      
            # Data Maintenance Service las persiste cada hora desde Redis cache en la tabla scan_results 
       
            
            # Update statistics
            elapsed = (time.time() - start) * 1000
            self.total_scans += 1
            self.total_tickers_scanned += len(enriched_snapshots)
            self.total_tickers_filtered += len(scored_tickers)
            self.last_scan_time = datetime.now()
            self.last_scan_duration_ms = elapsed
            
            # Build result y se usa para razones estadísticas que debo verificar después (pendiente de anañizar)
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
        Lee snapshot enriquecido desde Redis Hash.
        
        Tries snapshot:enriched:latest first, falls back to
        snapshot:enriched:last_close for weekends/holidays when latest expires.
        
        Returns:
            Lista de tuplas (snapshot, rvol, atr_data) del snapshot completo
        """
        try:
            # Try latest first, fall back to last_close (weekends/holidays)
            snapshot_key = "snapshot:enriched:latest"
            meta_raw = await self.redis.client.hget(snapshot_key, "__meta__")
            if not meta_raw:
                snapshot_key = "snapshot:enriched:last_close"
                meta_raw = await self.redis.client.hget(snapshot_key, "__meta__")
                if not meta_raw:
                    logger.debug("No enriched snapshot available (latest or last_close)")
                    return []
                logger.info("using_last_close_snapshot_fallback")
            
            try:
                import orjson
                meta = orjson.loads(meta_raw)
            except Exception:
                meta = json.loads(meta_raw) if isinstance(meta_raw, str) else {}
            
            snapshot_timestamp = meta.get('timestamp')
            
            if not hasattr(self, 'last_snapshot_timestamp'):
                self.last_snapshot_timestamp = None
            
            if snapshot_timestamp == self.last_snapshot_timestamp:
                return []
            
            all_data = await self.redis.client.hgetall(snapshot_key)
            
            if not all_data:
                return []
            
            all_data.pop("__meta__", None)
            
            logger.info(
                "reading_enriched_hash",
                source=snapshot_key,
                tickers=len(all_data),
                timestamp=snapshot_timestamp
            )
            
            # Parse each ticker from hash fields
            enriched_snapshots = []
            parsed_count = 0
            
            for symbol, ticker_json in all_data.items():
                try:
                    try:
                        ticker_data = orjson.loads(ticker_json)
                    except Exception:
                        ticker_data = json.loads(ticker_json) if isinstance(ticker_json, str) else ticker_json
                    
                    snapshot = PolygonSnapshot(**ticker_data)
                    rvol = ticker_data.get('rvol')
                    
                    # Pasar todo el dict enriched como atr_data
                    # Incluye: ATR, volumes, changes, daily indicators, 52-week,
                    # multi-day changes, distances, bid/ask, etc.
                    atr_data = ticker_data
                    
                    enriched_snapshots.append((snapshot, rvol, atr_data))
                    parsed_count += 1
                
                except Exception as e:
                    if parsed_count < 5:
                        logger.error("Error parsing ticker from hash",
                                    ticker=symbol, error=str(e))
            
            self.last_snapshot_timestamp = snapshot_timestamp
            
            logger.info(f"parsed_snapshots total={len(enriched_snapshots)} from_hash={len(all_data)}")
            
            return enriched_snapshots
        
        except Exception as e:
            logger.error("Error reading enriched hash", error=str(e))
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
                    
                    # Parsear address si viene como string JSON
                    if 'address' in data and isinstance(data['address'], str):
                        try:
                            data['address'] = json.loads(data['address'])
                        except (json.JSONDecodeError, TypeError):
                            data['address'] = None
                    
                    meta = TickerMetadata(**data)
                    results[sym] = meta
                    self._metadata_cache_set(sym, meta)
                except Exception as e:
                    logger.error("Error parsing metadata for symbol", symbol=sym, error=str(e))

        return results
    
    async def _get_avg_volumes_batch(self, symbols: List[str]) -> Dict[str, Dict[str, int]]:
        """
        Calcula el promedio de volumen para múltiples períodos (5D, 10D, 3M) para múltiples símbolos.
        
        Returns:
            Dict mapping symbol -> {avg_volume_5d, avg_volume_10d, avg_volume_3m}
        """
        if not symbols:
            return {}
        
        results: Dict[str, Dict[str, int]] = {}
        
        try:
            # Crear placeholders para la query
            placeholders = ', '.join([f"${i+1}" for i in range(len(symbols))])
            
            # Calcular los 3 promedios en una sola query
            query = f"""
                WITH ranked_data AS (
                    SELECT symbol, volume, trading_date,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trading_date DESC) as rn
                    FROM market_data_daily
                    WHERE symbol IN ({placeholders})
                )
                SELECT 
                    symbol,
                    AVG(CASE WHEN rn <= 5 THEN volume END)::bigint as avg_volume_5d,
                    AVG(CASE WHEN rn <= 10 THEN volume END)::bigint as avg_volume_10d,
                    AVG(CASE WHEN rn <= 63 THEN volume END)::bigint as avg_volume_3m
                FROM ranked_data
                WHERE rn <= 63
                GROUP BY symbol
                HAVING COUNT(*) >= 3
            """
            
            rows = await self.db.fetch(query, *symbols)
            
            for row in rows:
                results[row['symbol']] = {
                    'avg_volume_5d': row['avg_volume_5d'],
                    'avg_volume_10d': row['avg_volume_10d'],
                    'avg_volume_3m': row['avg_volume_3m']
                }
            
            logger.debug("avg_volumes_calculated", symbols_count=len(symbols), results_count=len(results))
            
        except Exception as e:
            logger.error("Error calculating avg_volumes batch", error=str(e))

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
        # OPTIMIZACIÓN: Filtrado temprano + MGET batch + procesamiento en una sola pasada
        
        # 1. Primera pasada: filtrar por precio y volumen, recopilar símbolos únicos
        valid_snapshots = []
        seen_symbols = set()

        logger.info(f"🎯 _process_snapshots_optimized called with {len(enriched_snapshots)} snapshots")
        
        for snapshot, rvol, atr_data in enriched_snapshots:
            # Validaciones tempranas (evita MGET innecesarios)
            cp = snapshot.current_price
            cv = snapshot.current_volume
            
            # Skip: precio inválido o muy bajo
            if not cp or cp < 0.5:
                continue
            
            # Skip: volumen inválido
            if not cv or cv <= 0:
                continue
            

            # Deduplicar símbolos
            symbol = snapshot.ticker
            if symbol not in seen_symbols:
                seen_symbols.add(symbol)
                valid_snapshots.append((snapshot, rvol, atr_data))
        
        # 2. MGET de metadata solo para símbolos válidos
        metadatas = await self._get_metadata_batch_cached(list(seen_symbols))
        
        # 2.5 Calcular avg_volumes en batch (5D, 10D, 3M)
        avg_volumes_map = await self._get_avg_volumes_batch(list(seen_symbols))
        
        # 2.6 🌙 Pre-cargar volúmenes regulares si estamos en POST_MARKET
        if self.current_session == MarketSession.POST_MARKET and self.postmarket_capture:
            await self._preload_regular_volumes(list(seen_symbols))
        
        # 3. Procesamiento: construir tickers + filtrar + score (una sola pasada)
        # NOTA: Este bucle aplica filtros que REQUIEREN metadata:
        # - market_cap (requiere market_cap de metadata)  
        # - sector/industry/exchange (requieren metadata)
        # 
        # Filtros que NO requieren metadata (pero ya se aplicaron en bucle 1):
        # - Precio (viene del snapshot)
        # - Volumen (viene del snapshot)
        # 
        # Otros filtros que NO requieren metadata (se aplican aquí):
        # - RVOL (ya calculado por Analytics, viene en enriched_snapshots)
        # - change_percent (usa prev_close del snapshot, no metadata)
        
        filtered_and_scored = []
        
        for snapshot, rvol, atr_data in valid_snapshots:
            try:
                symbol = snapshot.ticker
                
                # Get metadata (ya fetched con MGET batch)
                metadata = metadatas.get(symbol)
                if not metadata:
                    continue  # Sin metadata, skip
                
                # Build ticker completo (incluye cálculos de change_percent, etc)
                # metadata incluye: market_cap, sector, industry, exchange, avg_volume_30d, free_float, free_float_percent
                # NOTA: RVOL ya viene calculado por Analytics (no usa avg_volume_30d aquí)
                avg_vols = avg_volumes_map.get(symbol, {})
                ticker = self._build_scanner_ticker_inline(snapshot, metadata, rvol, atr_data, avg_vols)
                if not ticker:
                    continue
                

                # Enriquecer con gaps (usa prev_close y open del snapshot)
                ticker = self.enhance_ticker_with_gaps(ticker, snapshot)
                
                # Aplicar filtros configurables
                # Filtros que requieren metadata: market_cap, sector, industry, exchange
                # Filtros que NO requieren metadata: RVOL (ya calculado), price, volume, change_percent


                if not self._passes_all_filters(ticker):
                    continue  # No cumple filtros, skip
                

                # Calcular score (solo si paso TODOS los filtros)
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
                # Parsear address si viene como string JSON
                if 'address' in data and isinstance(data['address'], str):
                    try:
                        data['address'] = json.loads(data['address'])
                    except (json.JSONDecodeError, TypeError):
                        data['address'] = None
                
                return TickerMetadata(**data)
            
            # 2. Fallback a BD si no está en cache
            row = await self.db.get_ticker_metadata(symbol)
            
            if row:
                row_dict = dict(row)
                # Parsear address si viene como string JSON desde BD
                if 'address' in row_dict and isinstance(row_dict['address'], str):
                    try:
                        row_dict['address'] = json.loads(row_dict['address'])
                    except (json.JSONDecodeError, TypeError):
                        row_dict['address'] = None
                
                metadata = TickerMetadata(**row_dict)
                
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
        atr_data: Optional[Dict] = None,
        avg_volumes: Optional[Dict[str, int]] = None
    ) -> Optional[ScannerTicker]:
        """Build scanner ticker inline usando calculadores."""
        try:
            price = snapshot.current_price
            volume_today = snapshot.current_volume
            day_data = snapshot.day
            prev_day = snapshot.prevDay
            
            # === TICKER PLANT: enrichment pipeline is single source of truth ===

            # 1. Extraer datos enriquecidos (de Analytics)
            enriched = EnrichedDataExtractor.extract(atr_data)

            # 2. Price metrics — read from enriched snapshot (calculated by pipeline)
            #    Scanner no longer recalculates: change_percent, gap_percent, change_from_open,
            #    price_from_high/low, price_from_intraday_high/low

            # 3. Volume metrics — read from enriched snapshot
            avg_vol_10d = avg_volumes.get('avg_volume_10d') if avg_volumes else metadata.avg_volume_10d
            
            # 4. Calcular metricas de spread
            # Bid/Ask from flat enriched fields (pre-converted to shares by analytics)
            _bid = atr_data.get('bid') if atr_data else (snapshot.lastQuote.p if snapshot.lastQuote else None)
            _ask = atr_data.get('ask') if atr_data else (snapshot.lastQuote.P if snapshot.lastQuote else None)
            _bid_size_shares = atr_data.get('bid_size') if atr_data else None
            _ask_size_shares = atr_data.get('ask_size') if atr_data else None
            # SpreadMetricsCalculator expects lots, convert back if needed
            bid_lots = (_bid_size_shares // 100) if _bid_size_shares else (snapshot.lastQuote.s if snapshot.lastQuote else None)
            ask_lots = (_ask_size_shares // 100) if _ask_size_shares else (snapshot.lastQuote.S if snapshot.lastQuote else None)
            spread_metrics = SpreadMetricsCalculator.calculate(
                price=price,
                bid=_bid,
                ask=_ask,
                bid_size_lots=bid_lots,
                ask_size_lots=ask_lots
            )
            
            # 5. VWAP con fallback (enriched > day.vw)
            day_vwap = day_data.vw if day_data and day_data.vw else None
            vwap = enriched.vwap if enriched.vwap and enriched.vwap > 0 else (day_vwap if day_vwap and day_vwap > 0 else None)
            
            # 6. Campos adicionales del snapshot
            minute_volume = snapshot.min.v if snapshot.min else None
            last_trade_timestamp = snapshot.lastTrade.t if snapshot.lastTrade else None
            
            # === PRE/POST MARKET METRICS ===
            postmarket_change_percent = None
            postmarket_volume = None
            premarket_change_percent = None
            prev_close = prev_day.c if prev_day and prev_day.c and prev_day.c > 0 else None
            
            _change_pct = atr_data.get('todaysChangePerc') if atr_data else None
            if prev_close:
                if self.current_session == MarketSession.PRE_MARKET:
                    premarket_change_percent = _change_pct
                elif day_data and day_data.o and day_data.o > 0:
                    premarket_change_percent = ((day_data.o - prev_close) / prev_close) * 100
            
            if self.current_session == MarketSession.POST_MARKET:
                regular_close = day_data.c if day_data and day_data.c and day_data.c > 0 else None
                if regular_close and price:
                    postmarket_change_percent = ((price - regular_close) / regular_close) * 100
                regular_volume = self._regular_volumes_cache.get(snapshot.ticker)
                if regular_volume is not None and volume_today is not None:
                    postmarket_volume = max(0, volume_today - regular_volume)
            
            # === BUILD TICKER ===
            return ScannerTicker(
                symbol=snapshot.ticker,
                timestamp=datetime.now(),
                price=price,
                bid=spread_metrics.bid,
                ask=spread_metrics.ask,
                bid_size=spread_metrics.bid_size,
                ask_size=spread_metrics.ask_size,
                spread=spread_metrics.spread,
                spread_percent=spread_metrics.spread_percent,
                bid_ask_ratio=spread_metrics.bid_ask_ratio,
                distance_from_nbbo=spread_metrics.distance_from_nbbo,
                volume=volume_today,
                volume_today=volume_today,
                minute_volume=minute_volume,
                last_trade_timestamp=last_trade_timestamp,
                open=day_data.o if day_data else None,
                high=day_data.h if day_data else None,
                low=day_data.l if day_data else None,
                intraday_high=enriched.intraday_high,
                intraday_low=enriched.intraday_low,
                vol_1min=enriched.vol_1min,
                vol_5min=enriched.vol_5min,
                vol_10min=enriched.vol_10min,
                vol_15min=enriched.vol_15min,
                vol_30min=enriched.vol_30min,
                vol_1min_pct=enriched.vol_1min_pct,
                vol_5min_pct=enriched.vol_5min_pct,
                vol_10min_pct=enriched.vol_10min_pct,
                vol_15min_pct=enriched.vol_15min_pct,
                vol_30min_pct=enriched.vol_30min_pct,
                range_2min=enriched.range_2min,
                range_5min=enriched.range_5min,
                range_15min=enriched.range_15min,
                range_30min=enriched.range_30min,
                range_60min=enriched.range_60min,
                range_120min=enriched.range_120min,
                range_2min_pct=enriched.range_2min_pct,
                range_5min_pct=enriched.range_5min_pct,
                range_15min_pct=enriched.range_15min_pct,
                range_30min_pct=enriched.range_30min_pct,
                range_60min_pct=enriched.range_60min_pct,
                range_120min_pct=enriched.range_120min_pct,
                chg_1min=enriched.chg_1min,
                chg_5min=enriched.chg_5min,
                chg_10min=enriched.chg_10min,
                chg_15min=enriched.chg_15min,
                chg_30min=enriched.chg_30min,
                trades_today=enriched.trades_today,
                avg_trades_5d=enriched.avg_trades_5d,
                trades_z_score=enriched.trades_z_score,
                is_trade_anomaly=enriched.is_trade_anomaly,
                prev_close=prev_day.c if prev_day else None,
                prev_volume=prev_day.v if prev_day else None,
                # Price metrics — from enrichment pipeline (Ticker Plant)
                change_percent=_change_pct,
                gap_percent=atr_data.get('gap_percent') if atr_data else None,
                change_from_open=atr_data.get('change_from_open') if atr_data else None,
                change_from_open_dollars=atr_data.get('change_from_open_dollars') if atr_data else None,
                avg_volume_5d=avg_volumes.get('avg_volume_5d') if avg_volumes else None,
                avg_volume_10d=avg_vol_10d,
                avg_volume_3m=avg_volumes.get('avg_volume_3m') if avg_volumes else None,
                avg_volume_30d=metadata.avg_volume_30d,
                # Volume metrics — from enrichment pipeline (Ticker Plant)
                dollar_volume=atr_data.get('dollar_volume') if atr_data else None,
                volume_today_pct=atr_data.get('volume_today_pct') if atr_data else None,
                volume_yesterday_pct=atr_data.get('volume_yesterday_pct') if atr_data else None,
                float_rotation=atr_data.get('float_turnover') if atr_data else None,
                free_float=metadata.free_float,
                free_float_percent=metadata.free_float_percent,
                shares_outstanding=metadata.shares_outstanding,
                market_cap=metadata.market_cap,
                security_type=atr_data.get('security_type') if atr_data else None,
                sector=metadata.sector,
                industry=metadata.industry,
                exchange=metadata.exchange,
                rvol=rvol,
                rvol_slot=rvol,
                atr=enriched.atr,
                atr_percent=enriched.atr_percent,
                vwap=vwap,
                price_vs_vwap=atr_data.get('dist_from_vwap') if atr_data else None,
                # Distance metrics — from enrichment pipeline (Ticker Plant)
                price_from_high=atr_data.get('price_from_high') if atr_data else None,
                price_from_low=atr_data.get('price_from_low') if atr_data else None,
                price_from_intraday_high=atr_data.get('price_from_intraday_high') if atr_data else None,
                price_from_intraday_low=atr_data.get('price_from_intraday_low') if atr_data else None,
                premarket_change_percent=premarket_change_percent,
                postmarket_change_percent=postmarket_change_percent,
                postmarket_volume=postmarket_volume,
                # Streaming Technical Indicators (from BarEngine via enriched cache)
                rsi_14=atr_data.get('rsi_14') if atr_data else None,
                ema_9=atr_data.get('ema_9') if atr_data else None,
                ema_20=atr_data.get('ema_20') if atr_data else None,
                ema_50=atr_data.get('ema_50') if atr_data else None,
                sma_5=atr_data.get('sma_5') if atr_data else None,
                sma_8=atr_data.get('sma_8') if atr_data else None,
                sma_20=atr_data.get('sma_20') if atr_data else None,
                sma_50=atr_data.get('sma_50') if atr_data else None,
                sma_200=atr_data.get('sma_200') if atr_data else None,
                macd_line=atr_data.get('macd_line') if atr_data else None,
                macd_signal=atr_data.get('macd_signal') if atr_data else None,
                macd_hist=atr_data.get('macd_hist') if atr_data else None,
                bb_upper=atr_data.get('bb_upper') if atr_data else None,
                bb_mid=atr_data.get('bb_mid') if atr_data else None,
                bb_lower=atr_data.get('bb_lower') if atr_data else None,
                adx_14=atr_data.get('adx_14') if atr_data else None,
                stoch_k=atr_data.get('stoch_k') if atr_data else None,
                stoch_d=atr_data.get('stoch_d') if atr_data else None,
                chg_60min=atr_data.get('chg_60min') if atr_data else None,
                vol_60min=int(atr_data.get('vol_60min')) if atr_data and atr_data.get('vol_60min') is not None else None,
                bb_position_1m=atr_data.get('bb_position_1m') if atr_data else None,
                # Daily indicators (from screener via enriched cache)
                daily_sma_5=atr_data.get('daily_sma_5') if atr_data else None,
                daily_sma_8=atr_data.get('daily_sma_8') if atr_data else None,
                daily_sma_10=atr_data.get('daily_sma_10') if atr_data else None,
                daily_sma_20=atr_data.get('daily_sma_20') if atr_data else None,
                daily_sma_50=atr_data.get('daily_sma_50') if atr_data else None,
                daily_sma_200=atr_data.get('daily_sma_200') if atr_data else None,
                daily_rsi=atr_data.get('daily_rsi') if atr_data else None,
                daily_adx_14=atr_data.get('daily_adx_14') if atr_data else None,
                daily_atr_percent=atr_data.get('daily_atr_percent') if atr_data else None,
                daily_bb_position=atr_data.get('daily_bb_position') if atr_data else None,
                # 52-week data
                high_52w=atr_data.get('high_52w') if atr_data else None,
                low_52w=atr_data.get('low_52w') if atr_data else None,
                from_52w_high=atr_data.get('from_52w_high') if atr_data else None,
                from_52w_low=atr_data.get('from_52w_low') if atr_data else None,
                # Multi-day changes
                change_1d=atr_data.get('change_1d') if atr_data else None,
                change_3d=atr_data.get('change_3d') if atr_data else None,
                change_5d=atr_data.get('change_5d') if atr_data else None,
                change_10d=atr_data.get('change_10d') if atr_data else None,
                change_20d=atr_data.get('change_20d') if atr_data else None,
                # Average volumes (extended)
                avg_volume_20d=int(atr_data.get('avg_volume_20d')) if atr_data and atr_data.get('avg_volume_20d') is not None else None,
                prev_day_volume=int(atr_data.get('prev_day_volume')) if atr_data and atr_data.get('prev_day_volume') is not None else None,
                # Distance metrics
                dist_from_vwap=atr_data.get('dist_from_vwap') if atr_data else None,
                dist_sma_5=atr_data.get('dist_sma_5') if atr_data else None,
                dist_sma_8=atr_data.get('dist_sma_8') if atr_data else None,
                dist_sma_20=atr_data.get('dist_sma_20') if atr_data else None,
                dist_sma_50=atr_data.get('dist_sma_50') if atr_data else None,
                dist_sma_200=atr_data.get('dist_sma_200') if atr_data else None,
                dist_daily_sma_20=atr_data.get('dist_daily_sma_20') if atr_data else None,
                dist_daily_sma_50=atr_data.get('dist_daily_sma_50') if atr_data else None,
                # Derived fields
                todays_range=atr_data.get('todays_range') if atr_data else None,
                todays_range_pct=atr_data.get('todays_range_pct') if atr_data else None,
                float_turnover=atr_data.get('float_turnover') if atr_data else None,
                pos_in_range=atr_data.get('pos_in_range') if atr_data else None,
                below_high=atr_data.get('below_high') if atr_data else None,
                above_low=atr_data.get('above_low') if atr_data else None,
                pos_of_open=atr_data.get('pos_of_open') if atr_data else None,
                # Position in multi-period ranges
                pos_in_5d_range=atr_data.get('pos_in_5d_range') if atr_data else None,
                pos_in_10d_range=atr_data.get('pos_in_10d_range') if atr_data else None,
                pos_in_20d_range=atr_data.get('pos_in_20d_range') if atr_data else None,
                pos_in_3m_range=atr_data.get('pos_in_3m_range') if atr_data else None,
                pos_in_6m_range=atr_data.get('pos_in_6m_range') if atr_data else None,
                pos_in_9m_range=atr_data.get('pos_in_9m_range') if atr_data else None,
                pos_in_52w_range=atr_data.get('pos_in_52w_range') if atr_data else None,
                pos_in_2y_range=atr_data.get('pos_in_2y_range') if atr_data else None,
                pos_in_lifetime_range=atr_data.get('pos_in_lifetime_range') if atr_data else None,
                pos_in_prev_day_range=atr_data.get('pos_in_prev_day_range') if atr_data else None,
                pos_in_consolidation=atr_data.get('pos_in_consolidation') if atr_data else None,
                consolidation_days=atr_data.get('consolidation_days') if atr_data else None,
                range_contraction=atr_data.get('range_contraction') if atr_data else None,
                lr_divergence_130=atr_data.get('lr_divergence_130') if atr_data else None,
                change_prev_day_pct=atr_data.get('change_prev_day_pct') if atr_data else None,
                # Pre-market range metrics
                premarket_high=atr_data.get('premarket_high') if atr_data else None,
                premarket_low=atr_data.get('premarket_low') if atr_data else None,
                below_premarket_high=atr_data.get('below_premarket_high') if atr_data else None,
                above_premarket_low=atr_data.get('above_premarket_low') if atr_data else None,
                pos_in_premarket_range=atr_data.get('pos_in_premarket_range') if atr_data else None,
                # Multi-TF SMA distances
                dist_sma_5_2m=atr_data.get('dist_sma_5_2m') if atr_data else None,
                dist_sma_5_5m=atr_data.get('dist_sma_5_5m') if atr_data else None,
                dist_sma_5_15m=atr_data.get('dist_sma_5_15m') if atr_data else None,
                dist_sma_5_30m=atr_data.get('dist_sma_5_30m') if atr_data else None,
                dist_sma_5_60m=atr_data.get('dist_sma_5_60m') if atr_data else None,
                dist_sma_8_2m=atr_data.get('dist_sma_8_2m') if atr_data else None,
                dist_sma_8_5m=atr_data.get('dist_sma_8_5m') if atr_data else None,
                dist_sma_8_15m=atr_data.get('dist_sma_8_15m') if atr_data else None,
                dist_sma_8_30m=atr_data.get('dist_sma_8_30m') if atr_data else None,
                dist_sma_8_60m=atr_data.get('dist_sma_8_60m') if atr_data else None,
                dist_sma_10_2m=atr_data.get('dist_sma_10_2m') if atr_data else None,
                dist_sma_10_5m=atr_data.get('dist_sma_10_5m') if atr_data else None,
                dist_sma_10_15m=atr_data.get('dist_sma_10_15m') if atr_data else None,
                dist_sma_10_30m=atr_data.get('dist_sma_10_30m') if atr_data else None,
                dist_sma_10_60m=atr_data.get('dist_sma_10_60m') if atr_data else None,
                dist_sma_20_2m=atr_data.get('dist_sma_20_2m') if atr_data else None,
                dist_sma_20_5m=atr_data.get('dist_sma_20_5m') if atr_data else None,
                dist_sma_20_15m=atr_data.get('dist_sma_20_15m') if atr_data else None,
                dist_sma_20_30m=atr_data.get('dist_sma_20_30m') if atr_data else None,
                dist_sma_20_60m=atr_data.get('dist_sma_20_60m') if atr_data else None,
                dist_sma_130_2m=atr_data.get('dist_sma_130_2m') if atr_data else None,
                dist_sma_130_5m=atr_data.get('dist_sma_130_5m') if atr_data else None,
                dist_sma_130_10m=atr_data.get('dist_sma_130_10m') if atr_data else None,
                dist_sma_130_15m=atr_data.get('dist_sma_130_15m') if atr_data else None,
                dist_sma_130_30m=atr_data.get('dist_sma_130_30m') if atr_data else None,
                dist_sma_130_60m=atr_data.get('dist_sma_130_60m') if atr_data else None,
                dist_sma_200_2m=atr_data.get('dist_sma_200_2m') if atr_data else None,
                dist_sma_200_5m=atr_data.get('dist_sma_200_5m') if atr_data else None,
                dist_sma_200_10m=atr_data.get('dist_sma_200_10m') if atr_data else None,
                dist_sma_200_15m=atr_data.get('dist_sma_200_15m') if atr_data else None,
                dist_sma_200_30m=atr_data.get('dist_sma_200_30m') if atr_data else None,
                dist_sma_200_60m=atr_data.get('dist_sma_200_60m') if atr_data else None,
                # SMA cross metrics
                sma_8_vs_20_2m=atr_data.get('sma_8_vs_20_2m') if atr_data else None,
                sma_8_vs_20_5m=atr_data.get('sma_8_vs_20_5m') if atr_data else None,
                sma_8_vs_20_15m=atr_data.get('sma_8_vs_20_15m') if atr_data else None,
                sma_8_vs_20_60m=atr_data.get('sma_8_vs_20_60m') if atr_data else None,
                sma_20_vs_200_2m=atr_data.get('sma_20_vs_200_2m') if atr_data else None,
                sma_20_vs_200_5m=atr_data.get('sma_20_vs_200_5m') if atr_data else None,
                sma_20_vs_200_15m=atr_data.get('sma_20_vs_200_15m') if atr_data else None,
                sma_20_vs_200_60m=atr_data.get('sma_20_vs_200_60m') if atr_data else None,
                # Extended daily SMA distances
                dist_daily_sma_5=atr_data.get('dist_daily_sma_5') if atr_data else None,
                dist_daily_sma_8=atr_data.get('dist_daily_sma_8') if atr_data else None,
                dist_daily_sma_10=atr_data.get('dist_daily_sma_10') if atr_data else None,
                dist_daily_sma_200=atr_data.get('dist_daily_sma_200') if atr_data else None,
                dist_daily_sma_5_dollars=atr_data.get('dist_daily_sma_5_dollars') if atr_data else None,
                dist_daily_sma_8_dollars=atr_data.get('dist_daily_sma_8_dollars') if atr_data else None,
                dist_daily_sma_10_dollars=atr_data.get('dist_daily_sma_10_dollars') if atr_data else None,
                dist_daily_sma_20_dollars=atr_data.get('dist_daily_sma_20_dollars') if atr_data else None,
                dist_daily_sma_50_dollars=atr_data.get('dist_daily_sma_50_dollars') if atr_data else None,
                dist_daily_sma_200_dollars=atr_data.get('dist_daily_sma_200_dollars') if atr_data else None,
                # Extended changes and ranges
                change_1y=atr_data.get('change_1y') if atr_data else None,
                change_1y_dollars=atr_data.get('change_1y_dollars') if atr_data else None,
                change_ytd=atr_data.get('change_ytd') if atr_data else None,
                change_ytd_dollars=atr_data.get('change_ytd_dollars') if atr_data else None,
                change_5d_dollars=atr_data.get('change_5d_dollars') if atr_data else None,
                change_10d_dollars=atr_data.get('change_10d_dollars') if atr_data else None,
                change_20d_dollars=atr_data.get('change_20d_dollars') if atr_data else None,
                range_5d_pct=atr_data.get('range_5d_pct') if atr_data else None,
                range_10d_pct=atr_data.get('range_10d_pct') if atr_data else None,
                range_20d_pct=atr_data.get('range_20d_pct') if atr_data else None,
                range_5d=atr_data.get('range_5d') if atr_data else None,
                range_10d=atr_data.get('range_10d') if atr_data else None,
                range_20d=atr_data.get('range_20d') if atr_data else None,
                # Misc derived
                yearly_std_dev=atr_data.get('yearly_std_dev') if atr_data else None,
                consecutive_days_up=atr_data.get('consecutive_days_up') if atr_data else None,
                plus_di_minus_di=atr_data.get('plus_di_minus_di') if atr_data else None,
                gap_dollars=atr_data.get('gap_dollars') if atr_data else None,
                gap_ratio=atr_data.get('gap_ratio') if atr_data else None,
                change_from_close=atr_data.get('change_from_close') if atr_data else None,
                change_from_close_ratio=atr_data.get('change_from_close_ratio') if atr_data else None,
                change_from_open_ratio=atr_data.get('change_from_open_ratio') if atr_data else None,
                change_from_open_weighted=atr_data.get('change_from_open_weighted') if atr_data else None,
                postmarket_change_dollars=atr_data.get('postmarket_change_dollars') if atr_data else None,
                decimal=atr_data.get('decimal') if atr_data else None,
                bb_std_dev=atr_data.get('bb_std_dev') if atr_data else None,
                # Multi-TF position in range & BB
                pos_in_range_5m=atr_data.get('pos_in_range_5m') if atr_data else None,
                pos_in_range_15m=atr_data.get('pos_in_range_15m') if atr_data else None,
                pos_in_range_30m=atr_data.get('pos_in_range_30m') if atr_data else None,
                pos_in_range_60m=atr_data.get('pos_in_range_60m') if atr_data else None,
                bb_position_5m=atr_data.get('bb_position_5m') if atr_data else None,
                bb_position_15m=atr_data.get('bb_position_15m') if atr_data else None,
                bb_position_60m=atr_data.get('bb_position_60m') if atr_data else None,
                # Multi-TF RSI
                rsi_14_2m=atr_data.get('rsi_14_2m') if atr_data else None,
                rsi_14_5m=atr_data.get('rsi_14_5m') if atr_data else None,
                rsi_14_15m=atr_data.get('rsi_14_15m') if atr_data else None,
                rsi_14_60m=atr_data.get('rsi_14_60m') if atr_data else None,
                # Extended time window changes
                chg_2min=atr_data.get('chg_2min') if atr_data else None,
                chg_120min=atr_data.get('chg_120min') if atr_data else None,
                chg_1min_dollars=atr_data.get('chg_1min_dollars') if atr_data else None,
                chg_2min_dollars=atr_data.get('chg_2min_dollars') if atr_data else None,
                chg_5min_dollars=atr_data.get('chg_5min_dollars') if atr_data else None,
                chg_10min_dollars=atr_data.get('chg_10min_dollars') if atr_data else None,
                chg_15min_dollars=atr_data.get('chg_15min_dollars') if atr_data else None,
                chg_30min_dollars=atr_data.get('chg_30min_dollars') if atr_data else None,
                chg_60min_dollars=atr_data.get('chg_60min_dollars') if atr_data else None,
                chg_120min_dollars=atr_data.get('chg_120min_dollars') if atr_data else None,
                consecutive_candles=int(atr_data.get('consecutive_candles')) if atr_data and atr_data.get('consecutive_candles') is not None else None,
                consecutive_candles_2m=int(atr_data.get('consecutive_candles_2m')) if atr_data and atr_data.get('consecutive_candles_2m') is not None else None,
                consecutive_candles_5m=int(atr_data.get('consecutive_candles_5m')) if atr_data and atr_data.get('consecutive_candles_5m') is not None else None,
                consecutive_candles_10m=int(atr_data.get('consecutive_candles_10m')) if atr_data and atr_data.get('consecutive_candles_10m') is not None else None,
                consecutive_candles_15m=int(atr_data.get('consecutive_candles_15m')) if atr_data and atr_data.get('consecutive_candles_15m') is not None else None,
                consecutive_candles_30m=int(atr_data.get('consecutive_candles_30m')) if atr_data and atr_data.get('consecutive_candles_30m') is not None else None,
                consecutive_candles_60m=int(atr_data.get('consecutive_candles_60m')) if atr_data and atr_data.get('consecutive_candles_60m') is not None else None,
                # Pivot distances
                dist_pivot=atr_data.get('dist_pivot') if atr_data else None,
                dist_pivot_r1=atr_data.get('dist_pivot_r1') if atr_data else None,
                dist_pivot_s1=atr_data.get('dist_pivot_s1') if atr_data else None,
                dist_pivot_r2=atr_data.get('dist_pivot_r2') if atr_data else None,
                dist_pivot_s2=atr_data.get('dist_pivot_s2') if atr_data else None,
                # Dilution Risk Ratings (null for non-dilutive tickers like AAPL)
                dilution_overall_risk=atr_data.get('dilution_overall_risk') if atr_data else None,
                dilution_overall_risk_score=atr_data.get('dilution_overall_risk_score') if atr_data else None,
                dilution_offering_ability=atr_data.get('dilution_offering_ability') if atr_data else None,
                dilution_offering_ability_score=atr_data.get('dilution_offering_ability_score') if atr_data else None,
                dilution_overhead_supply=atr_data.get('dilution_overhead_supply') if atr_data else None,
                dilution_overhead_supply_score=atr_data.get('dilution_overhead_supply_score') if atr_data else None,
                dilution_historical=atr_data.get('dilution_historical') if atr_data else None,
                dilution_historical_score=atr_data.get('dilution_historical_score') if atr_data else None,
                dilution_cash_need=atr_data.get('dilution_cash_need') if atr_data else None,
                dilution_cash_need_score=atr_data.get('dilution_cash_need_score') if atr_data else None,
                # Time of Day [TOD]
                minutes_since_open=atr_data.get('minutes_since_open') if atr_data else None,
                # Session
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
        
        return True  # Paso todos
    
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
            
            # Si pasó todos los filtros habilitados, agregarlo
            # (incluso si matched_filters está vacío porque no hay filtros habilitados)
            if passed:
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
            
            # Spread filters (in CENTS,)
            if params.min_spread is not None:
                if ticker.spread is None or ticker.spread < params.min_spread:
                    return False
            
            if params.max_spread is not None:
                if ticker.spread is None or ticker.spread > params.max_spread:
                    return False
            
            # Bid/Ask size filters
            if params.min_bid_size is not None:
                if ticker.bid_size is None or ticker.bid_size < params.min_bid_size:
                    return False
            
            if params.max_bid_size is not None:
                if ticker.bid_size is None or ticker.bid_size > params.max_bid_size:
                    return False
            
            if params.min_ask_size is not None:
                if ticker.ask_size is None or ticker.ask_size < params.min_ask_size:
                    return False
            
            if params.max_ask_size is not None:
                if ticker.ask_size is None or ticker.ask_size > params.max_ask_size:
                    return False
            
            # Distance from Inside Market (NBBO) filter -
            if params.min_distance_from_nbbo is not None:
                if ticker.distance_from_nbbo is None or ticker.distance_from_nbbo < params.min_distance_from_nbbo:
                    return False
            if params.max_distance_from_nbbo is not None:
                if ticker.distance_from_nbbo is None or ticker.distance_from_nbbo > params.max_distance_from_nbbo:
                    return False
            
            # Volume filters
            if params.min_volume is not None:
                if ticker.volume_today < params.min_volume:
                    return False
            
            # Minute volume filter (solo tickers con actividad reciente)
            if params.min_minute_volume is not None:
                if ticker.minute_volume is None or ticker.minute_volume < params.min_minute_volume:
                    return False
            
            # Average Daily Volume filters (5D, 10D, 3M)
            if params.min_avg_volume_5d is not None:
                if ticker.avg_volume_5d is None or ticker.avg_volume_5d < params.min_avg_volume_5d:
                    return False
            if params.max_avg_volume_5d is not None:
                if ticker.avg_volume_5d is None or ticker.avg_volume_5d > params.max_avg_volume_5d:
                    return False
            
            if params.min_avg_volume_10d is not None:
                if ticker.avg_volume_10d is None or ticker.avg_volume_10d < params.min_avg_volume_10d:
                    return False
            if params.max_avg_volume_10d is not None:
                if ticker.avg_volume_10d is None or ticker.avg_volume_10d > params.max_avg_volume_10d:
                    return False
            
            if params.min_avg_volume_3m is not None:
                if ticker.avg_volume_3m is None or ticker.avg_volume_3m < params.min_avg_volume_3m:
                    return False
            if params.max_avg_volume_3m is not None:
                if ticker.avg_volume_3m is None or ticker.avg_volume_3m > params.max_avg_volume_3m:
                    return False
            
            # Dollar Volume filters (price × avg_volume_10d)
            if params.min_dollar_volume is not None:
                if ticker.dollar_volume is None or ticker.dollar_volume < params.min_dollar_volume:
                    return False
            if params.max_dollar_volume is not None:
                if ticker.dollar_volume is None or ticker.dollar_volume > params.max_dollar_volume:
                    return False
            
            # Volume Today % filters
            if params.min_volume_today_pct is not None:
                if ticker.volume_today_pct is None or ticker.volume_today_pct < params.min_volume_today_pct:
                    return False
            if params.max_volume_today_pct is not None:
                if ticker.volume_today_pct is None or ticker.volume_today_pct > params.max_volume_today_pct:
                    return False
            
            # Volume Yesterday % filters
            if params.min_volume_yesterday_pct is not None:
                if ticker.volume_yesterday_pct is None or ticker.volume_yesterday_pct < params.min_volume_yesterday_pct:
                    return False
            if params.max_volume_yesterday_pct is not None:
                if ticker.volume_yesterday_pct is None or ticker.volume_yesterday_pct > params.max_volume_yesterday_pct:
                    return False
            
            # Data freshness filter (rechazar tickers con datos muy antiguos)
            if params.max_data_age_seconds is not None:
                if ticker.last_trade_timestamp is not None:
                    current_time_ns = datetime.now().timestamp() * 1_000_000_000
                    age_ns = current_time_ns - ticker.last_trade_timestamp
                    age_seconds = age_ns / 1_000_000_000
                    if age_seconds > params.max_data_age_seconds:
                        return False
                else:
                    # Si no hay last_trade_timestamp, rechazar por seguridad
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
            
            # Float filters (applies to free_float field)
            if params.min_float is not None:
                if ticker.free_float is None or ticker.free_float < params.min_float:
                    return False
            
            if params.max_float is not None:
                if ticker.free_float is None or ticker.free_float > params.max_float:
                    return False
            
            # Security Type filter
            security_type_filter = getattr(params, 'security_type', None)
            if security_type_filter and isinstance(security_type_filter, str) and security_type_filter.strip():
                if ticker.security_type != security_type_filter.strip():
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
            
            # Post-Market filters (only apply during POST_MARKET session)
            if self.current_session == MarketSession.POST_MARKET:
                if params.min_postmarket_change_percent is not None:
                    if ticker.postmarket_change_percent is None or ticker.postmarket_change_percent < params.min_postmarket_change_percent:
                        return False
                
                if params.max_postmarket_change_percent is not None:
                    if ticker.postmarket_change_percent is None or ticker.postmarket_change_percent > params.max_postmarket_change_percent:
                        return False
                
                if params.min_postmarket_volume is not None:
                    if ticker.postmarket_volume is None or ticker.postmarket_volume < params.min_postmarket_volume:
                        return False
                
                if params.max_postmarket_volume is not None:
                    if ticker.postmarket_volume is None or ticker.postmarket_volume > params.max_postmarket_volume:
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
            
            # Guardar en Redis con TTL largo para persistir en fin de semana
            # TTL: 48 horas (172800 seg) - permite ver datos del viernes durante el fin de semana
            await self.redis.set(
                cache_key,
                tickers_data,
                ttl=172800,  # 48 horas en lugar de 60 seg
                serialize=True  # Ya serializa internamente a JSON
            )
            
            # También guardar en clave permanente (sin TTL) para último scan
            last_scan_key = f"scanner:filtered_complete:LAST"
            await self.redis.set(
                last_scan_key,
                {
                    "tickers": tickers_data,
                    "session": self.current_session.value,
                    "timestamp": datetime.now().isoformat()
                },
                ttl=None,  # Sin expiración - siempre disponible
                serialize=True
            )
            
            logger.debug(
                f"Cached {len(tickers)} complete filtered tickers in Redis",
                session=self.current_session.value
            )
        
        except Exception as e:
            logger.error("Error caching filtered tickers", error=str(e))
    
    async def _publish_filtered_tickers_for_subscription(
        self, 
        tickers: List[ScannerTicker]
    ) -> None:
        """Sistema automatico de suscripciones - delegado a SubscriptionManager."""
        await self._subscription_manager.update_subscriptions(tickers, self.current_session)
    
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
        full_universe: Optional[List[ScannerTicker]] = None,
        emit_deltas: bool = True
    ) -> Dict[str, List[ScannerTicker]]:
        """
        Categoriza tickers filtrados en múltiples scanners.
        
        Args:
            tickers: Tickers filtrados (top N para categorías del sistema)
            full_universe: Universo completo de tickers válidos (para user scans).
                           Si None, usa tickers. Esto permite que los user scans
                           evalúen contra TODOS los tickers, no solo el top N.
            emit_deltas: Si True, emite deltas incrementales
        
        Returns:
            Dict con {category_name: [tickers_ranked]}
        """
        try:
            # Obtener todas las categorías
            # Usar RETE si está habilitado, sino usar categorizador tradicional
            if self._rete_enabled and self._rete_manager.network:
                categories = self._categorize_with_rete(
                    tickers,
                    limit_per_category=settings.default_category_limit
                )
            else:
                categories = self.categorizer.get_all_categories(
                    tickers, 
                    limit_per_category=settings.default_category_limit
                )
            
            # NEW: Calcular y emitir deltas para cada categoría
            if emit_deltas:
                for category_name, new_ranking in categories.items():
                    # Obtener ranking anterior
                    old_ranking = self.last_rankings.get(category_name, [])
                    
                    # ✅ FIX: Usar "category_name not in" para distinguir entre:
                    # - Primera vez (key no existe) → emit snapshot
                    # - Categoría vacía pero ya inicializada (key existe, valor=[]) → emit delta
                    if category_name not in self.last_rankings:
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
            
            # Publicar tickers para auto-suscripción en Polygon WS
            await self._publish_filtered_tickers_for_subscription(tickers)
            
            # Procesar scans de usuarios (RETE) contra universo completo
            # Los user scans usan full_universe (todos los tickers válidos, sin recorte)
            # para que filtros específicos del usuario no pierdan tickers que estén
            # fuera del top N por score pero cumplan sus criterios
            if self._rete_enabled:
                user_scan_universe = full_universe if full_universe is not None else tickers
                await self._process_user_scans(user_scan_universe)
            
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
    
    def _categorize_with_rete(
        self,
        tickers: List[ScannerTicker],
        limit_per_category: int = 100
    ) -> Dict[str, List[ScannerTicker]]:
        """
        Categoriza tickers usando motor RETE.
        
        RETE evalua cada ticker contra todas las reglas en una pasada,
        compartiendo evaluaciones de condiciones identicas.
        """
        if not self._rete_manager.network:
            return {}
        
        # Evaluar batch de tickers
        batch_results = self._rete_manager.evaluate_batch(tickers)
        
        # Obtener solo resultados de sistema (categorias)
        system_results = self._rete_manager.get_system_results(batch_results)
        
        # Convertir a formato esperado y ordenar
        categories: Dict[str, List[ScannerTicker]] = {}
        
        for rule_id, matched_tickers in system_results.items():
            # Extraer nombre de categoria (category:gappers_up -> gappers_up)
            category_name = rule_id.replace("category:", "")
            
            # Obtener regla para saber como ordenar
            terminal = self._rete_manager.network.terminal_nodes.get(f"terminal:{rule_id}")
            if terminal and terminal.rule.sort_field:
                sort_field = terminal.rule.sort_field
                reverse = terminal.rule.sort_descending
                matched_tickers.sort(
                    key=lambda t: getattr(t, sort_field, 0) or 0,
                    reverse=reverse
                )
            
            categories[category_name] = matched_tickers[:limit_per_category]
        
        return categories
    
    def _get_all_user_rule_ids(self) -> Set[str]:
        """
        Obtiene todos los rule_ids de usuario registrados en el network RETE.
        Necesario para detectar reglas con 0 matches y refrescar su TTL en Redis.
        """
        user_rule_ids: Set[str] = set()
        if not self._rete_manager.network:
            return user_rule_ids
        for terminal in self._rete_manager.network.terminal_nodes.values():
            if terminal.rule.owner_type == RuleOwnerType.USER:
                user_rule_ids.add(terminal.rule.id)
        return user_rule_ids
    
    async def _process_user_scans(self, tickers: List[ScannerTicker]) -> None:
        """
        Procesa y publica resultados de TODOS los user scans habilitados.
        
        ARQUITECTURA COMPLETA:
        1. Evalúa tickers contra reglas RETE de usuario
        2. Calcula deltas respecto al ranking anterior
        3. Publica snapshot a scanner:category:uscan_{id}
        4. Publica deltas a stream:ranking:deltas (mismo que categorías sistema)
        5. Actualiza índice de símbolos por user scan
        6. Refresca TTL de reglas con 0 matches para evitar expiración en Redis
        """
        if not self._rete_enabled or not self._rete_manager.network:
            return
        
        try:
            # Evaluar todos los tickers contra todas las reglas
            batch_results = self._rete_manager.evaluate_batch(tickers)
            
            # Obtener TODAS las reglas de usuario registradas
            all_user_rule_ids = self._get_all_user_rule_ids()
            processed_rule_ids: Set[str] = set()
            
            # Publicar resultados de reglas de usuario
            user_rules_processed = 0
            total_deltas_emitted = 0
            
            for rule_id, matched in batch_results.items():
                if rule_id.startswith("user:"):
                    processed_rule_ids.add(rule_id)
                    
                    # Extraer filter_id del formato "user:xxx:scan:17"
                    parts = rule_id.split(":")
                    filter_id = parts[-1] if len(parts) >= 4 else rule_id
                    category_name = f"uscan_{filter_id}"
                    
                    # Ordenar por change_percent descendente
                    matched.sort(key=lambda t: t.change_percent or 0, reverse=True)
                    new_ranking = matched[:100]
                    
                    # Obtener ranking anterior
                    old_ranking = self.last_user_scan_rankings.get(category_name, [])
                    
                    # Calcular deltas
                    deltas = self.calculate_ranking_deltas(old_ranking, new_ranking, category_name)
                    
                    # Guardar snapshot en Redis
                    await self._save_user_scan_to_redis("all", filter_id, new_ranking)
                    
                    # Emitir deltas si hay cambios
                    if deltas:
                        await self._emit_user_scan_deltas(category_name, deltas)
                        total_deltas_emitted += len(deltas)
                    
                    # Actualizar ranking anterior
                    self.last_user_scan_rankings[category_name] = new_ranking
                    
                    user_rules_processed += 1
            
            # Procesar reglas con 0 matches: refrescar TTL y emitir deltas de remoción
            unmatched_rules = all_user_rule_ids - processed_rule_ids
            for rule_id in unmatched_rules:
                parts = rule_id.split(":")
                filter_id = parts[-1] if len(parts) >= 4 else rule_id
                category_name = f"uscan_{filter_id}"
                
                new_ranking: List[ScannerTicker] = []
                old_ranking = self.last_user_scan_rankings.get(category_name, [])
                
                # Calcular deltas (remover todos los tickers anteriores)
                if old_ranking:
                    deltas = self.calculate_ranking_deltas(old_ranking, new_ranking, category_name)
                    if deltas:
                        await self._emit_user_scan_deltas(category_name, deltas)
                        total_deltas_emitted += len(deltas)
                
                # Guardar snapshot vacío en Redis (refresca el TTL)
                await self._save_user_scan_to_redis("all", filter_id, new_ranking)
                self.last_user_scan_rankings[category_name] = new_ranking
                user_rules_processed += 1
                    
            if user_rules_processed > 0:
                logger.info(
                    "user_scans_processed",
                    rules_count=user_rules_processed,
                    rules_with_matches=len(processed_rule_ids),
                    rules_empty=len(unmatched_rules),
                    deltas_emitted=total_deltas_emitted
                )
        except Exception as e:
            logger.error("error_processing_user_scans", error=str(e))
    
    async def _save_user_scan_to_redis(self, user_id: str, rule_id: str, tickers: List[ScannerTicker]) -> None:
        """
        Guarda resultados de scan de usuario en Redis.
        Usa el mismo formato que las categorías del sistema para compatibilidad con WebSocket.
        
        Key format: scanner:category:uscan_{rule_id}
        
        TTL is dynamic: 5min during active market (refreshed every ~10s),
        extended until next cache cleanup when market is closed (set by freeze).
        """
        try:
            category_name = f"uscan_{rule_id}"
            ranking_data = [t.model_dump(mode='json') for t in tickers]
            
            ttl = self._ttl_until_next_cache_cleanup() if self._user_scans_frozen else 300
            
            await self.redis.set(
                f"scanner:category:{category_name}",
                json.dumps(ranking_data, allow_nan=False),
                ttl=ttl
            )
            
            sequence_key = f"uscan_seq_{rule_id}"
            current_sequence = self.sequence_numbers.get(sequence_key, 0) + 1
            self.sequence_numbers[sequence_key] = current_sequence
            
            await self.redis.set(
                f"scanner:sequence:{category_name}",
                current_sequence,
                ttl=ttl
            )
            
            logger.debug(
                "user_scan_saved_to_redis",
                user_id=user_id,
                rule_id=rule_id,
                category=category_name,
                count=len(tickers),
                sequence=current_sequence
            )
        except Exception as e:
            logger.error("error_saving_user_scan", user_id=user_id, rule_id=rule_id, error=str(e))
    
    async def _emit_user_scan_deltas(self, category_name: str, deltas: List[Dict]) -> None:
        """
        Emite deltas de user scan al stream de rankings.
        
        Usa el mismo stream que las categorías del sistema (stream:ranking:deltas)
        para que el WebSocket Server los procese de forma unificada.
        
        Args:
            category_name: Nombre de la categoría (uscan_X)
            deltas: Lista de cambios incrementales
        """
        if not deltas:
            return
        
        try:
            # Usar sequence key específico para user scans
            sequence_key = category_name
            self.sequence_numbers[sequence_key] = self.sequence_numbers.get(sequence_key, 0) + 1
            sequence = self.sequence_numbers[sequence_key]
            
            # Crear mensaje en mismo formato que categorías sistema
            message = {
                'type': 'delta',
                'list': category_name,
                'sequence': sequence,
                'deltas': json.dumps(deltas, allow_nan=False),
                'timestamp': datetime.now().isoformat(),
                'change_count': len(deltas)
            }
            
            # Publicar al stream compartido
            stream_manager = get_stream_manager()
            await stream_manager.xadd(
                settings.stream_ranking_deltas,
                message
            )
            
            seq_ttl = self._ttl_until_next_cache_cleanup() if self._user_scans_frozen else 300
            await self.redis.set(
                f"scanner:sequence:{category_name}",
                sequence,
                ttl=seq_ttl
            )
            
            logger.debug(
                "user_scan_deltas_emitted",
                category=category_name,
                sequence=sequence,
                changes=len(deltas),
                adds=sum(1 for d in deltas if d.get('action') == 'add'),
                removes=sum(1 for d in deltas if d.get('action') == 'remove')
            )
            
        except Exception as e:
            logger.error("error_emitting_user_scan_deltas", category=category_name, error=str(e))
    
    def _ttl_until_next_cache_cleanup(self) -> int:
        """
        Calculate seconds until the maintenance service clears scanner caches.
        
        Maintenance runs at 3:45 AM ET on trading days (weekdays, excluding holidays).
        We target the next weekday + 1 day buffer for potential single-day holidays.
        The maintenance DELETE of scanner:category:* is the real cleanup mechanism;
        this TTL is a safety net.
        """
        try:
            NY = ZoneInfo("America/New_York")
            now = datetime.now(NY)
            
            next_weekday = now.date() + timedelta(days=1)
            while next_weekday.weekday() >= 5:
                next_weekday += timedelta(days=1)
            
            # +1 day buffer: if next weekday is a holiday, maintenance runs the day after
            buffered = next_weekday + timedelta(days=1)
            while buffered.weekday() >= 5:
                buffered += timedelta(days=1)
            
            target = datetime.combine(buffered, time_type(3, 45), tzinfo=NY)
            ttl = int((target - now).total_seconds())
            
            return max(600, min(ttl, 604800))
        except Exception:
            return 604800
    
    async def freeze_user_scans_for_close(self) -> int:
        """
        Re-save ALL scanner snapshots (built-in + user) with extended TTL at market close.
        
        Called when session transitions to CLOSED. The maintenance service clears
        scanner:category:* at 3:45 AM ET on the next trading day. This method
        ensures data persists through weekends and holidays so users always see
        the last known state instead of empty tables.
        
        Returns:
            Total number of categories frozen
        """
        self._user_scans_frozen = True
        frozen = 0
        ttl = self._ttl_until_next_cache_cleanup()
        
        all_categories = {
            **{name: tickers for name, tickers in self.last_rankings.items()},
            **{name: tickers for name, tickers in self.last_user_scan_rankings.items()},
        }
        
        for category_name, tickers in all_categories.items():
            try:
                ranking_data = [t.model_dump(mode='json') for t in tickers]
                
                await self.redis.set(
                    f"scanner:category:{category_name}",
                    json.dumps(ranking_data, allow_nan=False),
                    ttl=ttl
                )
                
                current_seq = self.sequence_numbers.get(category_name, 0)
                if category_name.startswith("uscan_"):
                    filter_id = category_name.replace("uscan_", "")
                    seq_key = f"uscan_seq_{filter_id}"
                    current_seq = self.sequence_numbers.get(seq_key, current_seq)
                
                await self.redis.set(
                    f"scanner:sequence:{category_name}",
                    current_seq,
                    ttl=ttl
                )
                
                frozen += 1
            except Exception as e:
                logger.error("error_freezing_scan", category=category_name, error=str(e))
        
        if frozen > 0:
            logger.info(
                "scans_frozen_for_close",
                builtin=len(self.last_rankings),
                user=len(self.last_user_scan_rankings),
                total=frozen,
                ttl_seconds=ttl,
                ttl_hours=round(ttl / 3600, 1)
            )
        
        return frozen
    
    def register_active_user(self, user_id: str) -> None:
        """Registra usuario activo."""
        self._rete_manager.add_active_user(user_id)
    
    def unregister_active_user(self, user_id: str) -> None:
        """Desregistra usuario."""
        self._rete_manager.remove_active_user(user_id)
    
    async def reload_user_rules(self) -> None:
        """Recarga reglas de usuarios."""
        if self._rete_enabled:
            await self._rete_manager.reload_rules()
    
    async def get_category(
        self,
        category: ScannerCategory,
        limit: int = settings.default_category_limit
    ) -> List[ScannerTicker]:
        """
        Obtiene tickers de una categoría específica
        
        Usa cache de última categorización (actualizado cada scan)
        """
        try:
            # Validar y limitar el límite máximo
            limit = min(limit, settings.max_category_limit)
            
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
        """Update current market session from Redis (optimizado)"""
        try:
            # Leer de Redis directamente (sin HTTP overhead)
            session_str = await self.redis.get(f"{settings.key_prefix_market}:session:current")
            
            if session_str:
                self.current_session = MarketSession(session_str)
            else:
                # Fallback: HTTP si no está en Redis (usando cliente compartido)
                current_session = await http_clients.market_session.get_current_session()
                if current_session:
                    self.current_session = MarketSession(current_session)
        
        except Exception as e:
            logger.error("Error updating market session", error=str(e))
    
    async def _preload_regular_volumes(self, symbols: List[str]) -> None:
        """
        🌙 Pre-carga volúmenes regulares para símbolos durante POST_MARKET
        
        Patrón: Local cache → MGET batch Redis → (lazy API fetch para nuevos)
        
        Usa MGET para traer miles de keys en un solo round-trip a Redis,
        igual que _get_metadata_batch_cached. Cada MGET con 1000 keys
        usa UNA sola conexión del pool (no 1000).
        
        Args:
            symbols: Lista de símbolos para pre-cargar
        """
        if not self.postmarket_capture:
            return
        
        # 1) Filtrar símbolos que ya están en cache local (O(1) dict lookup)
        misses = [s for s in symbols if s not in self._regular_volumes_cache]
        
        if not misses:
            return
        
        # 2) MGET batch desde Redis (1 round-trip por chunk de 1000 keys)
        trading_date = self.postmarket_capture._trading_date
        if not trading_date:
            return
        
        date_str = trading_date.replace('-', '')
        prefix = f"{self.postmarket_capture.REDIS_PREFIX}:regular_vol:{date_str}"
        
        CHUNK_SIZE = 1000
        volumes_loaded = 0
        
        for i in range(0, len(misses), CHUNK_SIZE):
            chunk = misses[i:i + CHUNK_SIZE]
            keys = [f"{prefix}:{sym}" for sym in chunk]
            
            try:
                results = await self.redis.client.mget(keys)
            except Exception as e:
                logger.error("mget_regular_volumes_error", chunk_size=len(chunk), error=str(e))
                continue
            
            for sym, raw in zip(chunk, results):
                if raw is not None:
                    try:
                        volume = int(raw)
                        self._regular_volumes_cache[sym] = volume
                        # Sincronizar con postmarket_capture local cache
                        self.postmarket_capture._local_cache[sym] = volume
                        self.postmarket_capture._captured_symbols.add(sym)
                        volumes_loaded += 1
                    except (ValueError, TypeError):
                        pass
        
        if volumes_loaded > 0:
            logger.info(
                "🌙 regular_volumes_preloaded",
                symbols_requested=len(misses),
                volumes_loaded=volumes_loaded,
                cache_size=len(self._regular_volumes_cache)
            )
    
    async def trigger_postmarket_capture(self, trading_date: str) -> None:
        """
        🌙 Trigger inicial de captura de volúmenes regulares
        
        Se llama UNA VEZ cuando la sesión cambia a POST_MARKET.
        Captura el volumen de sesión regular para todos los tickers actualmente
        en el scanner.
        
        Args:
            trading_date: Fecha de trading en formato YYYY-MM-DD
        """
        if not self.postmarket_capture:
            logger.warning("postmarket_capture_not_initialized")
            return
        
        # Obtener tickers actuales del scanner (de memoria o Redis)
        current_tickers = self.last_filtered_tickers or []
        symbols = [t.symbol for t in current_tickers]
        
        if not symbols:
            # Fallback: leer de Redis cache
            try:
                cache_key = f"scanner:filtered_complete:{MarketSession.MARKET_OPEN.value}"
                cached_data = await self.redis.get(cache_key, deserialize=True)
                if cached_data:
                    symbols = [t.get('symbol') for t in cached_data if t.get('symbol')]
            except Exception as e:
                logger.error("error_reading_filtered_cache", error=str(e))
        
        if symbols:
            logger.info(
                "🌙 triggering_postmarket_capture",
                symbols_count=len(symbols),
                trading_date=trading_date
            )
            
            # Capturar volúmenes en paralelo
            volumes = await self.postmarket_capture.on_session_changed_to_postmarket(
                symbols,
                trading_date
            )
            
            # Actualizar cache local
            self._regular_volumes_cache.update(volumes)
            
            logger.info(
                "✅ postmarket_capture_completed",
                volumes_captured=len(volumes),
                cache_size=len(self._regular_volumes_cache)
            )
        else:
            logger.warning("no_symbols_for_postmarket_capture")
    
    def clear_postmarket_cache(self) -> None:
        """Limpia cache de volúmenes regulares (para nuevo día)"""
        self._regular_volumes_cache.clear()
        if self.postmarket_capture:
            self.postmarket_capture.clear_for_new_day()
        logger.info("postmarket_cache_cleared")
    
    async def get_filtered_tickers(self, limit: int = settings.default_query_limit) -> List[ScannerTicker]:
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
            # Validar límite máximo
            limit = min(limit, settings.max_query_limit)
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
    
    def get_cached_ticker(self, symbol: str) -> Optional[ScannerTicker]:
        """
        Obtiene un ticker del cache en memoria.
        
        Args:
            symbol: Símbolo a buscar
        
        Returns:
            ScannerTicker si está en cache, None si no
        """
        if not self.last_filtered_tickers:
            return None
        
        # Búsqueda lineal O(n) - aceptable para ~500-1000 tickers
        # Si se necesita más velocidad, se puede usar un dict auxiliar
        for ticker in self.last_filtered_tickers:
            if ticker.symbol == symbol:
                return ticker
        
        return None
    
    # =============================================
    # DELTA SYSTEM (Snapshot + Incremental Updates)
    # =============================================
    
    def calculate_ranking_deltas(
        self,
        old_ranking: List[ScannerTicker],
        new_ranking: List[ScannerTicker],
        list_name: str
    ) -> List[Dict]:
        """Calcula deltas - delegado a ranking module."""
        return calculate_ranking_deltas(old_ranking, new_ranking, list_name)
    
    
    def _ticker_data_changed(
        self,
        old_ticker: ScannerTicker,
        new_ticker: ScannerTicker
    ) -> bool:
        """Verifica cambios - delegado a ranking module."""
        return ticker_data_changed(old_ticker, new_ticker)
    
    
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
            'deltas': json.dumps(deltas, allow_nan=False),
            'timestamp': datetime.now().isoformat(),
            'change_count': len(deltas)
        }
        
        # Publicar a stream
        try:
            stream_manager = get_stream_manager()
            await stream_manager.xadd(
                settings.stream_ranking_deltas,
                message
                # MAXLEN automático según config
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
            
            await self.redis.set(
                f"scanner:category:{list_name}",
                json.dumps(ranking_data, allow_nan=False),
                ttl=172800
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
            'rows': json.dumps(snapshot_data, allow_nan=False),
            'timestamp': datetime.now().isoformat(),
            'count': len(tickers)
        }
        
        # Publicar a stream
        try:
            stream_manager = get_stream_manager()
            await stream_manager.xadd(
                settings.stream_ranking_deltas,
                message
                # MAXLEN automático según config
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

