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
from datetime import datetime, time as time_type
from typing import Optional, List, Dict, Any, Tuple, Set

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
from calculators import (
    PriceMetricsCalculator,
    VolumeMetricsCalculator,
    SpreadMetricsCalculator,
    EnrichedDataExtractor
)

# Motor de filtros (refactorizacion)
from filters import FilterEngine, apply_filter

# Gestor de suscripciones (refactorizacion)
from subscriptions import SubscriptionManager

# Calculador de deltas (refactorizacion)
from ranking import calculate_ranking_deltas, ticker_data_changed

# Motor RETE para reglas de usuario
from rete import ReteManager, get_system_rules, compile_network, CATEGORY_TO_CHANNEL

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
            scored_tickers = await self._process_snapshots_optimized(enriched_snapshots)
            
            # Limit to max filtered tickers
            if len(scored_tickers) > settings.max_filtered_tickers:
                scored_tickers = scored_tickers[:settings.max_filtered_tickers]
            
            # Guardar tickers filtrados en cache
            if scored_tickers:
                # 1. Cache en memoria (inmediato)
                self.last_filtered_tickers = scored_tickers
                self.last_filtered_time = datetime.now()
                
                # 2. Cache en Redis (persistente, TTL 60 seg)
                await self._save_filtered_tickers_to_cache(scored_tickers)
                
                # 3. Categorizar (usa tickers en memoria)
                await self.categorize_filtered_tickers(scored_tickers)
                
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
        Lee snapshot enriquecido desde Redis Hash (snapshot:enriched:latest).
        
        Cada ticker es un field del hash, serializado como JSON individual.
        El scanner lee todo con HGETALL y parsea cada ticker.
        
        Returns:
            Lista de tuplas (snapshot, rvol, atr_data) del snapshot completo
        """
        try:
            # Leer metadata para verificar si hay nuevo snapshot
            meta_raw = await self.redis.client.hget("snapshot:enriched:latest", "__meta__")
            if not meta_raw:
                logger.debug("No enriched snapshot hash available yet")
                return []
            
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
            
            # Nuevo snapshot - leer todos los tickers del hash
            all_data = await self.redis.client.hgetall("snapshot:enriched:latest")
            
            if not all_data:
                return []
            
            # Remove metadata field
            all_data.pop("__meta__", None)
            
            logger.info(
                "reading_enriched_hash",
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
                    
                    atr_data = {
                        'atr': ticker_data.get('atr'),
                        'atr_percent': ticker_data.get('atr_percent'),
                        'intraday_high': ticker_data.get('intraday_high'),
                        'intraday_low': ticker_data.get('intraday_low'),
                        'vwap': ticker_data.get('vwap'),
                        'vol_1min': ticker_data.get('vol_1min'),
                        'vol_5min': ticker_data.get('vol_5min'),
                        'vol_10min': ticker_data.get('vol_10min'),
                        'vol_15min': ticker_data.get('vol_15min'),
                        'vol_30min': ticker_data.get('vol_30min'),
                        'chg_1min': ticker_data.get('chg_1min'),
                        'chg_5min': ticker_data.get('chg_5min'),
                        'chg_10min': ticker_data.get('chg_10min'),
                        'chg_15min': ticker_data.get('chg_15min'),
                        'chg_30min': ticker_data.get('chg_30min'),
                        'trades_today': ticker_data.get('trades_today'),
                        'avg_trades_5d': ticker_data.get('avg_trades_5d'),
                        'trades_z_score': ticker_data.get('trades_z_score'),
                        'is_trade_anomaly': ticker_data.get('is_trade_anomaly'),
                        # Bid/Ask flattened from lastQuote by enrichment pipeline
                        'bid': ticker_data.get('bid'),
                        'ask': ticker_data.get('ask'),
                        'bid_size': ticker_data.get('bid_size'),
                        'ask_size': ticker_data.get('ask_size'),
                    }
                    
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
            gap_percent = None
            change_from_open = None
            
            if day_data:
                if day_data.h and day_data.h > 0:
                    price_from_high = ((price - day_data.h) / day_data.h) * 100
                
                if day_data.l and day_data.l > 0:
                    price_from_low = ((price - day_data.l) / day_data.l) * 100
                
                # change_from_open: cambio desde la apertura
                if day_data.o and day_data.o > 0:
                    change_from_open = ((price - day_data.o) / day_data.o) * 100
            
            if prev_day and prev_day.c and prev_day.c > 0:
                change_percent = ((price - prev_day.c) / prev_day.c) * 100
                
                # gap_percent: 
                # - Si hay open (market abierto): GAP REAL = (open - prev_close) / prev_close
                # - Si no hay open (pre-market): GAP ESPERADO = (price - prev_close) / prev_close
                if day_data and day_data.o and day_data.o > 0:
                    gap_percent = ((day_data.o - prev_day.c) / prev_day.c) * 100
                else:
                    # Pre-market: usar precio actual como "expected open"
                    gap_percent = change_percent
            
            # Extract ATR data
            atr = None
            atr_percent = None
            if atr_data:
                atr = atr_data.get('atr')
                atr_percent = atr_data.get('atr_percent')
            
            # Extract intraday high/low (from enriched snapshot)
            intraday_high = atr_data.get('intraday_high') if atr_data else None
            intraday_low = atr_data.get('intraday_low') if atr_data else None
            
            # Extract volume window metrics (from enriched snapshot)
            vol_1min = atr_data.get('vol_1min') if atr_data else None
            vol_5min = atr_data.get('vol_5min') if atr_data else None
            vol_10min = atr_data.get('vol_10min') if atr_data else None
            vol_15min = atr_data.get('vol_15min') if atr_data else None
            vol_30min = atr_data.get('vol_30min') if atr_data else None
            
            # Extract price change window metrics (from enriched snapshot - PriceWindowTracker)
            chg_1min = atr_data.get('chg_1min') if atr_data else None
            chg_5min = atr_data.get('chg_5min') if atr_data else None
            chg_10min = atr_data.get('chg_10min') if atr_data else None
            chg_15min = atr_data.get('chg_15min') if atr_data else None
            chg_30min = atr_data.get('chg_30min') if atr_data else None
            
            # Extract trades anomaly data (from enriched snapshot - TradesAnomalyDetector)
            trades_today = atr_data.get('trades_today') if atr_data else None
            avg_trades_5d = atr_data.get('avg_trades_5d') if atr_data else None
            trades_z_score = atr_data.get('trades_z_score') if atr_data else None
            is_trade_anomaly = atr_data.get('is_trade_anomaly') if atr_data else False
            
            # Calculate price distance from intraday high/low (includes pre/post market)
            price_from_intraday_high = None
            price_from_intraday_low = None
            if intraday_high and intraday_high > 0:
                price_from_intraday_high = ((price - intraday_high) / intraday_high) * 100
            if intraday_low and intraday_low > 0:
                price_from_intraday_low = ((price - intraday_low) / intraday_low) * 100
            
            # Calculate spread (in CENTS)
            # Bid/Ask now come as flat fields from enrichment pipeline (pre-converted to shares)
            bid = atr_data.get('bid') if atr_data else (snapshot.lastQuote.p if snapshot.lastQuote else None)
            ask = atr_data.get('ask') if atr_data else (snapshot.lastQuote.P if snapshot.lastQuote else None)
            bid_size = atr_data.get('bid_size') if atr_data else ((snapshot.lastQuote.s * 100) if snapshot.lastQuote and snapshot.lastQuote.s else None)
            ask_size = atr_data.get('ask_size') if atr_data else ((snapshot.lastQuote.S * 100) if snapshot.lastQuote and snapshot.lastQuote.S else None)
            spread = None
            spread_percent = None
            bid_ask_ratio = None
            if bid and ask and bid > 0 and ask > 0:
                spread = (ask - bid) * 100  # Convert to cents
                mid_price = (bid + ask) / 2
                spread_percent = ((ask - bid) / mid_price) * 100
            if bid_size and ask_size and ask_size > 0:
                bid_ask_ratio = bid_size / ask_size
            
            # Distance from Inside Market (NBBO)
            distance_from_nbbo = None
            if price and bid and ask and bid > 0 and ask > 0:
                if price >= bid and price <= ask:
                    distance_from_nbbo = 0.0
                elif price < bid:
                    distance_from_nbbo = ((bid - price) / bid) * 100
                else:
                    distance_from_nbbo = ((price - ask) / ask) * 100
            
            # Build ticker
            return ScannerTicker(
                symbol=snapshot.ticker,
                timestamp=datetime.now(),
                # Real-time data
                price=price,
                bid=bid,
                ask=ask,
                bid_size=bid_size,
                ask_size=ask_size,
                spread=spread,
                spread_percent=spread_percent,
                bid_ask_ratio=bid_ask_ratio,
                distance_from_nbbo=distance_from_nbbo,
                volume=volume_today,
                volume_today=volume_today,
                open=day_data.o if day_data else None,
                high=day_data.h if day_data else None,
                low=day_data.l if day_data else None,
                intraday_high=intraday_high,
                intraday_low=intraday_low,
                # Volume window metrics
                vol_1min=vol_1min,
                vol_5min=vol_5min,
                vol_10min=vol_10min,
                vol_15min=vol_15min,
                vol_30min=vol_30min,
                # Price change window metrics (per-second precision)
                chg_1min=chg_1min,
                chg_5min=chg_5min,
                chg_10min=chg_10min,
                chg_15min=chg_15min,
                chg_30min=chg_30min,
                # Trades anomaly detection (Z-Score based)
                trades_today=trades_today,
                avg_trades_5d=avg_trades_5d,
                trades_z_score=trades_z_score,
                is_trade_anomaly=is_trade_anomaly,
                prev_close=prev_day.c if prev_day else None,
                prev_volume=prev_day.v if prev_day else None,
                change_percent=change_percent,
                # Gap metrics (NUEVOS)
                gap_percent=gap_percent,
                change_from_open=change_from_open,
                # Historical data
                avg_volume_30d=metadata.avg_volume_30d,
                avg_volume_10d=metadata.avg_volume_10d,
                # Volume Today/Yesterday %
                volume_today_pct=round((volume_today / metadata.avg_volume_10d) * 100, 1) if volume_today and metadata.avg_volume_10d else None,
                volume_yesterday_pct=round((prev_day.v / metadata.avg_volume_10d) * 100, 1) if prev_day and prev_day.v and metadata.avg_volume_10d else None,
                free_float=metadata.free_float,
                free_float_percent=metadata.free_float_percent,
                # Float rotation = (volume_today / free_float) * 100
                float_rotation=round((volume_today / metadata.free_float) * 100, 2) if volume_today and metadata.free_float and metadata.free_float > 0 else None,
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
                price_from_intraday_high=price_from_intraday_high,
                price_from_intraday_low=price_from_intraday_low,
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
        atr_data: Optional[Dict] = None,
        avg_volumes: Optional[Dict[str, int]] = None
    ) -> Optional[ScannerTicker]:
        """Build scanner ticker inline usando calculadores."""
        try:
            price = snapshot.current_price
            volume_today = snapshot.current_volume
            day_data = snapshot.day
            prev_day = snapshot.prevDay
            
            # === USAR CALCULADORES ===
            
            # 1. Extraer datos enriquecidos (de Analytics)
            enriched = EnrichedDataExtractor.extract(atr_data)
            
            # 2. Calcular metricas de precio
            price_metrics = PriceMetricsCalculator.calculate(
                price=price,
                open_price=day_data.o if day_data else None,
                high=day_data.h if day_data else None,
                low=day_data.l if day_data else None,
                prev_close=prev_day.c if prev_day else None,
                intraday_high=enriched.intraday_high,
                intraday_low=enriched.intraday_low
            )
            
            # 3. Calcular metricas de volumen
            avg_vol_10d = avg_volumes.get('avg_volume_10d') if avg_volumes else metadata.avg_volume_10d
            volume_metrics = VolumeMetricsCalculator.calculate(
                volume_today=volume_today,
                prev_volume=prev_day.v if prev_day else None,
                avg_volume_10d=avg_vol_10d,
                free_float=metadata.free_float,
                price=price
            )
            
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
            price_vs_vwap = PriceMetricsCalculator.calculate_price_vs_vwap(price, vwap)
            
            # 6. Campos adicionales del snapshot
            minute_volume = snapshot.min.v if snapshot.min else None
            last_trade_timestamp = snapshot.lastTrade.t if snapshot.lastTrade else None
            
            # === PRE/POST MARKET METRICS ===
            postmarket_change_percent = None
            postmarket_volume = None
            premarket_change_percent = None
            prev_close = prev_day.c if prev_day and prev_day.c and prev_day.c > 0 else None
            
            if prev_close:
                if self.current_session == MarketSession.PRE_MARKET:
                    premarket_change_percent = price_metrics.change_percent
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
                change_percent=price_metrics.change_percent,
                gap_percent=price_metrics.gap_percent,
                change_from_open=price_metrics.change_from_open,
                avg_volume_5d=avg_volumes.get('avg_volume_5d') if avg_volumes else None,
                avg_volume_10d=avg_vol_10d,
                avg_volume_3m=avg_volumes.get('avg_volume_3m') if avg_volumes else None,
                avg_volume_30d=metadata.avg_volume_30d,
                dollar_volume=volume_metrics.dollar_volume,
                volume_today_pct=volume_metrics.volume_today_pct,
                volume_yesterday_pct=volume_metrics.volume_yesterday_pct,
                float_rotation=volume_metrics.float_rotation,
                free_float=metadata.free_float,
                free_float_percent=metadata.free_float_percent,
                shares_outstanding=metadata.shares_outstanding,
                market_cap=metadata.market_cap,
                sector=metadata.sector,
                industry=metadata.industry,
                exchange=metadata.exchange,
                rvol=rvol,
                rvol_slot=rvol,
                atr=enriched.atr,
                atr_percent=enriched.atr_percent,
                vwap=vwap,
                price_vs_vwap=price_vs_vwap,
                price_from_high=price_metrics.price_from_high,
                price_from_low=price_metrics.price_from_low,
                price_from_intraday_high=price_metrics.price_from_intraday_high,
                price_from_intraday_low=price_metrics.price_from_intraday_low,
                premarket_change_percent=premarket_change_percent,
                postmarket_change_percent=postmarket_change_percent,
                postmarket_volume=postmarket_volume,
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
            
            # Procesar scans de usuarios (RETE)
            if self._rete_enabled:
                await self._process_user_scans(tickers)
            
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
    
    async def _process_user_scans(self, tickers: List[ScannerTicker]) -> None:
        """
        Procesa y publica resultados de TODOS los user scans habilitados.
        
        ARQUITECTURA COMPLETA:
        1. Evalúa tickers contra reglas RETE de usuario
        2. Calcula deltas respecto al ranking anterior
        3. Publica snapshot a scanner:category:uscan_{id}
        4. Publica deltas a stream:ranking:deltas (mismo que categorías sistema)
        5. Actualiza índice de símbolos por user scan
        """
        if not self._rete_enabled or not self._rete_manager.network:
            return
        
        try:
            # Evaluar todos los tickers contra todas las reglas
            batch_results = self._rete_manager.evaluate_batch(tickers)
            
            # Publicar resultados de reglas de usuario
            user_rules_processed = 0
            total_deltas_emitted = 0
            
            for rule_id, matched in batch_results.items():
                if rule_id.startswith("user:"):
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
                    
            if user_rules_processed > 0:
                logger.info(
                    "user_scans_processed",
                    rules_count=user_rules_processed,
                    deltas_emitted=total_deltas_emitted
                )
        except Exception as e:
            logger.error("error_processing_user_scans", error=str(e))
    
    async def _save_user_scan_to_redis(self, user_id: str, rule_id: str, tickers: List[ScannerTicker]) -> None:
        """
        Guarda resultados de scan de usuario en Redis.
        Usa el mismo formato que las categorías del sistema para compatibilidad con WebSocket.
        
        Key format: scanner:category:uscan_{rule_id}
        """
        try:
            # Usar mismo formato que categorías del sistema
            category_name = f"uscan_{rule_id}"
            ranking_data = [t.model_dump(mode='json') for t in tickers]
            
            # Guardar en key (snapshot) - mismo formato que _save_ranking_to_redis
            await self.redis.set(
                f"scanner:category:{category_name}",
                json.dumps(ranking_data),
                ttl=300  # 5 minutos (user scans se actualizan frecuentemente)
            )
            
            # Guardar sequence number para sincronización
            sequence_key = f"uscan_seq_{rule_id}"
            current_sequence = self.sequence_numbers.get(sequence_key, 0) + 1
            self.sequence_numbers[sequence_key] = current_sequence
            
            await self.redis.set(
                f"scanner:sequence:{category_name}",
                current_sequence,
                ttl=300
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
                'deltas': json.dumps(deltas),
                'timestamp': datetime.now().isoformat(),
                'change_count': len(deltas)
            }
            
            # Publicar al stream compartido
            stream_manager = get_stream_manager()
            await stream_manager.xadd(
                settings.stream_ranking_deltas,
                message
            )
            
            # Actualizar sequence en Redis
            await self.redis.set(
                f"scanner:sequence:{category_name}",
                sequence,
                ttl=300  # 5 min para user scans
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
            'deltas': json.dumps(deltas),
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
            
            # Guardar en key (snapshot)
            # TTL 48 horas para que persista en fin de semana
            await self.redis.set(
                f"scanner:category:{list_name}",
                json.dumps(ranking_data),
                ttl=172800  # 48 horas (igual que cache completo)
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

