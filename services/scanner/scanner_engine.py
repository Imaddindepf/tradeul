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

logger = get_logger(__name__)


class ScannerEngine:
    """
    Core scanner engine
    """
    
    def __init__(
        self,
        redis_client: RedisClient,
        timescale_client: TimescaleClient,
        snapshot_manager=None  # Optional SnapshotManager
    ):
        self.redis = redis_client
        self.db = timescale_client
        self.snapshot_manager = snapshot_manager  # 🔥 SnapshotManager para deltas
        
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
        
        # Auto-subscription tracking (para Polygon WS)
        self._previous_filtered_symbols: Set[str] = set()  # Track símbolos previos
        
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
            
            # Si ya es un dict, usarlo directamente
            if isinstance(enriched_data, dict):
                pass
            # Si es string, parsearlo como JSON
            elif isinstance(enriched_data, str):
                try:
                    enriched_data = json.loads(enriched_data)
                except json.JSONDecodeError as e:
                    logger.error("Failed to parse snapshot as JSON", error=str(e))
                    return []
            else:
                logger.error("Unexpected data type for snapshot", 
                           data_type=type(enriched_data).__name__)
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
            
            parsed_count = 0
            for ticker_data in tickers_data:
                try:
                    # Parsear snapshot
                    snapshot = PolygonSnapshot(**ticker_data)
                    rvol = ticker_data.get('rvol')
                    
                    # Extraer ATR data, intraday high/low y VWAP del snapshot enriquecido
                    atr_data = {
                        'atr': ticker_data.get('atr'),
                        'atr_percent': ticker_data.get('atr_percent'),
                        'intraday_high': ticker_data.get('intraday_high'),
                        'intraday_low': ticker_data.get('intraday_low'),
                        'vwap': ticker_data.get('vwap')  # VWAP enriquecido por analytics
                    }
                    
                    enriched_snapshots.append((snapshot, rvol, atr_data))
                    parsed_count += 1
                
                except Exception as e:
                    if parsed_count < 5:  # Log solo los primeros errores
                        logger.error("Error parsing ticker", 
                                    ticker=ticker_data.get('ticker'), 
                                    error=str(e))
            
            # Guardar timestamp para no reprocesar
            self.last_snapshot_timestamp = snapshot_timestamp
            
            logger.info(f"parsed_snapshots total={len(enriched_snapshots)} from_raw={len(tickers_data)}")
            
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
            # DEBUG: Log para MNDR al inicio del bucle
            if snapshot.ticker == "MNDR":
                logger.info(f"🚀 MNDR entered processing loop, snapshot={snapshot.ticker}, price={snapshot.current_price}")

            # Validaciones tempranas (evita MGET innecesarios)
            cp = snapshot.current_price
            cv = snapshot.current_volume
            
            # DEBUG logging para tickers específicos o primeros 5
            if snapshot.ticker in ['NVDA', 'MNDR', 'SHPH', 'AAPL', 'TSLA'] or len(valid_snapshots) < 5:
                logger.info(f"early_filter_check symbol={snapshot.ticker} price={cp} volume={cv} min.av={snapshot.min.av if snapshot.min else 'NO MIN'}")
            
            # Skip: precio inválido o muy bajo
            if snapshot.ticker == "MNDR":
                logger.info(f"🔍 MNDR price check: cp={cp}, type={type(cp)}, bool(cp)={bool(cp)}, cp < 0.5 = {cp < 0.5 if cp else 'N/A'}")
            if not cp or cp < 0.5:
                if snapshot.ticker in ['NVDA', 'MNDR', 'SHPH', 'AAPL', 'TSLA']:
                    logger.warning(f"rejected_by_price symbol={snapshot.ticker} price={cp}")
                continue
            
            # Skip: volumen inválido
            if snapshot.ticker == "MNDR":
                logger.info(f"🔍 MNDR volume check: cv={cv}, type={type(cv)}, bool(cv)={bool(cv)}, cv <= 0 = {cv <= 0 if cv else 'N/A'}")
            if not cv or cv <= 0:
                if snapshot.ticker in ['NVDA', 'MNDR', 'SHPH', 'AAPL', 'TSLA'] or len(valid_snapshots) < 5:
                    logger.warning(f"rejected_by_volume symbol={snapshot.ticker} cv={cv}")
                continue
            
            # DEBUG: MNDR llegó hasta aquí
            if snapshot.ticker == "MNDR":
                logger.info(f"🎯 MNDR passed volume check, going to deduplication")

            # Deduplicar símbolos
            symbol = snapshot.ticker
            if symbol not in seen_symbols:
                seen_symbols.add(symbol)
                valid_snapshots.append((snapshot, rvol, atr_data))
                if symbol == "MNDR":
                    logger.info(f"✅ MNDR added to valid_snapshots, total_valid={len(valid_snapshots)}")
            elif symbol == "MNDR":
                logger.warning(f"⚠️ MNDR already in seen_symbols, skipping duplicate")
        
        # 2. MGET de metadata solo para símbolos válidos
        metadatas = await self._get_metadata_batch_cached(list(seen_symbols))
        
        # 2.5 Calcular avg_volumes en batch (5D, 10D, 3M)
        avg_volumes_map = await self._get_avg_volumes_batch(list(seen_symbols))
        
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
                    if symbol == "MNDR":
                        logger.error(f"❌ MNDR missing metadata, available_symbols={list(metadatas.keys())[:10]}")
                    continue  # Sin metadata, skip
                
                # Build ticker completo (incluye cálculos de change_percent, etc)
                # metadata incluye: market_cap, sector, industry, exchange, avg_volume_30d, float_shares
                # NOTA: RVOL ya viene calculado por Analytics (no usa avg_volume_30d aquí)
                avg_vols = avg_volumes_map.get(symbol, {})
                ticker = self._build_scanner_ticker_inline(snapshot, metadata, rvol, atr_data, avg_vols)
                if not ticker:
                    if symbol == "MNDR":
                        logger.error(f"❌ MNDR _build_scanner_ticker_inline returned None")
                    continue
                
                if symbol == "MNDR":
                    logger.info(f"✅ MNDR ticker built successfully, price={ticker.price}, rvol={ticker.rvol}")

                # Enriquecer con gaps (usa prev_close y open del snapshot)
                ticker = self.enhance_ticker_with_gaps(ticker, snapshot)

                if symbol == "MNDR":
                    logger.info(f"🚀 MNDR after gap enhancement: ticker={ticker is not None}, going to filters")
                
                # intraday_high/low ya vienen de Analytics, no necesitamos tracker adicional
                
                # DEBUG: Log antes de filtros para IVVD
                if snapshot.ticker == "IVVD":
                    logger.info(f"🔍 DEBUG IVVD: Antes de filtros", 
                               ticker_created=ticker is not None,
                               rvol=ticker.rvol if ticker else None,
                               price=ticker.price if ticker else None,
                               change_percent=ticker.change_percent if ticker else None)
                
                # Aplicar filtros configurables
                # Filtros que requieren metadata: market_cap, sector, industry, exchange
                # Filtros que NO requieren metadata: RVOL (ya calculado), price, volume, change_percent
                if symbol == "MNDR":
                    logger.info(f"🎯 MNDR checking filters: market_cap={ticker.market_cap}, sector={ticker.sector}, rvol={ticker.rvol}")

                if symbol == "MNDR":
                    logger.info(f"🚨 MNDR about to call _passes_all_filters")

                if not self._passes_all_filters(ticker):
                    if symbol == "MNDR":
                        logger.warning(f"❌ MNDR failed filters")
                    continue  # No cumple filtros, skip
                
                if symbol == "MNDR":
                    logger.info(f"✅ MNDR passed all filters, calculating score")

                # Calcular score (solo si pasó TODOS los filtros)
                ticker.score = self._calculate_score_inline(ticker)
                
                # DEBUG: Log para IVVD después de score
                if snapshot.ticker == "IVVD":
                    logger.info(f"🔍 DEBUG IVVD: Pasó filtros, score calculado", 
                               score=ticker.score, rank=ticker.rank)
                
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
            
            # Calculate price distance from intraday high/low (includes pre/post market)
            price_from_intraday_high = None
            price_from_intraday_low = None
            if intraday_high and intraday_high > 0:
                price_from_intraday_high = ((price - intraday_high) / intraday_high) * 100
            if intraday_low and intraday_low > 0:
                price_from_intraday_low = ((price - intraday_low) / intraday_low) * 100
            
            # Calculate spread (in CENTS)
            bid = snapshot.lastQuote.p if snapshot.lastQuote else None
            ask = snapshot.lastQuote.P if snapshot.lastQuote else None
            bid_size = (snapshot.lastQuote.s * 100) if snapshot.lastQuote and snapshot.lastQuote.s else None  # lots to shares
            ask_size = (snapshot.lastQuote.S * 100) if snapshot.lastQuote and snapshot.lastQuote.S else None  # lots to shares
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
        """Build scanner ticker inline (sin awaits innecesarios)"""
        try:
            # DEBUG: Log para IVVD
            if snapshot.ticker == "IVVD":
                logger.info(f"🔍 DEBUG IVVD: Construyendo ScannerTicker", 
                           current_price=snapshot.current_price,
                           current_volume=snapshot.current_volume,
                           rvol=rvol,
                           has_metadata=metadata is not None)
            
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
            
            # Calculate price distance from intraday high/low (includes pre/post market)
            price_from_intraday_high = None
            price_from_intraday_low = None
            if intraday_high and intraday_high > 0:
                price_from_intraday_high = ((price - intraday_high) / intraday_high) * 100
            if intraday_low and intraday_low > 0:
                price_from_intraday_low = ((price - intraday_low) / intraday_low) * 100
            
            # Extract minute volume
            minute_volume = snapshot.min.v if snapshot.min else None
            
            # Extract last trade timestamp (for freshness filtering)
            last_trade_timestamp = snapshot.lastTrade.t if snapshot.lastTrade else None
            
            # Extract VWAP (prioridad: snapshot enriquecido > day.vw original)
            # El snapshot enriquecido tiene VWAP actualizado por analytics desde WebSocket
            enriched_vwap = atr_data.get('vwap') if atr_data else None
            day_vwap = day_data.vw if day_data and day_data.vw else None
            
            # Usar el VWAP enriquecido primero, luego day.vw como fallback
            vwap = enriched_vwap if enriched_vwap and enriched_vwap > 0 else (day_vwap if day_vwap and day_vwap > 0 else None)
            
            # Calculate price vs VWAP (% distance)
            price_vs_vwap = None
            if vwap and vwap > 0:
                price_vs_vwap = ((price - vwap) / vwap) * 100
            
            # Calculate spread (in CENTS)
            bid = snapshot.lastQuote.p if snapshot.lastQuote else None
            ask = snapshot.lastQuote.P if snapshot.lastQuote else None
            bid_size = (snapshot.lastQuote.s * 100) if snapshot.lastQuote and snapshot.lastQuote.s else None  # lots to shares
            ask_size = (snapshot.lastQuote.S * 100) if snapshot.lastQuote and snapshot.lastQuote.S else None  # lots to shares
            spread = None
            spread_percent = None
            bid_ask_ratio = None
            if bid and ask and bid > 0 and ask > 0:
                spread = (ask - bid) * 100  # Convert to cents
                mid_price = (bid + ask) / 2
                spread_percent = ((ask - bid) / mid_price) * 100
            if bid_size and ask_size and ask_size > 0:
                bid_ask_ratio = bid_size / ask_size
            
            # Distance from Inside Market (NBBO) -
            # 0 = price is at or between bid/ask (tradeable)
            # >0 = price is outside the NBBO (potential bad print)
            distance_from_nbbo = None
            if price and bid and ask and bid > 0 and ask > 0:
                if price >= bid and price <= ask:
                    distance_from_nbbo = 0.0
                elif price < bid:
                    distance_from_nbbo = ((bid - price) / bid) * 100
                else:  # price > ask
                    distance_from_nbbo = ((price - ask) / ask) * 100
            
            return ScannerTicker(
                symbol=snapshot.ticker,
                timestamp=datetime.now(),
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
                minute_volume=minute_volume,
                last_trade_timestamp=last_trade_timestamp,
                open=day_data.o if day_data else None,
                high=day_data.h if day_data else None,
                low=day_data.l if day_data else None,
                intraday_high=intraday_high,
                intraday_low=intraday_low,
                prev_close=prev_day.c if prev_day else None,
                prev_volume=prev_day.v if prev_day else None,
                change_percent=change_percent,
                avg_volume_5d=avg_volumes.get('avg_volume_5d') if avg_volumes else None,
                avg_volume_10d=avg_volumes.get('avg_volume_10d') if avg_volumes else metadata.avg_volume_10d,
                avg_volume_3m=avg_volumes.get('avg_volume_3m') if avg_volumes else None,
                avg_volume_30d=metadata.avg_volume_30d,
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
                price_from_intraday_high=price_from_intraday_high,
                price_from_intraday_low=price_from_intraday_low,
                vwap=vwap,
                price_vs_vwap=price_vs_vwap,
                session=self.current_session,
                score=0.0,
                filters_matched=[]
            )
        except Exception as e:
            logger.error("Error building ticker inline", error=str(e))
            return None
    
    def _passes_all_filters(self, ticker: ScannerTicker) -> bool:
        """Verifica si ticker pasa TODOS los filtros (sin await)"""
        if ticker.symbol == "MNDR":
            logger.info(f"🔍 MNDR _passes_all_filters called, filters_count={len(self.filters)}")

        for filter_config in self.filters:
            if not filter_config.enabled:
                continue
            
            if not filter_config.applies_to_session(self.current_session):
                continue
            
            if ticker.symbol == "MNDR":
                logger.info(f"🔍 MNDR testing filter: {filter_config.name} (enabled={filter_config.enabled})")

            if not self._apply_single_filter(ticker, filter_config):
                if ticker.symbol == "MNDR":
                    logger.warning(f"❌ MNDR failed filter: {filter_config.name}")
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
        """
        SISTEMA AUTOMÁTICO DE SUSCRIPCIONES (PROFESIONAL)
        
        Publica símbolos filtrados para que Polygon WS se suscriba automáticamente.
        Gestiona suscripciones/desuscripciones dinámicas basadas en rankings.
        
        Ventajas:
        - Frontend NO gestiona suscripciones manualmente
        - Scanner decide QUÉ es relevante → Polygon WS se suscribe
        - Tickers que salen del ranking → auto-desuscripción
        - Centralizado: 1 suscripción por ticker (no por cliente)
        - Eficiente: max 1000 suscripciones a Polygon (límite del plan)
        
        Args:
            tickers: Lista de tickers filtrados (top 500-1000)
        """
        try:
            # 1. Obtener símbolos SOLO de los que están en categorías (no todos los filtrados)
            # Esto evita suscribir a 1,000 tickers cuando solo 400 están en rankings
            all_category_names = ['gappers_up', 'gappers_down', 'momentum_up', 'momentum_down', 
                                 'winners', 'losers', 'high_volume', 'new_highs', 'new_lows', 
                                 'anomalies', 'reversals']
            
            category_symbols = set()
            categories_read = {}
            
            for category_name in all_category_names:
                category_key = f"scanner:category:{category_name}"
                try:
                    category_data = await self.redis.get(category_key, deserialize=True)
                    if category_data and isinstance(category_data, list):
                        cat_tickers = []
                        for ticker in category_data:
                            if ticker.get('symbol'):
                                category_symbols.add(ticker['symbol'])
                                cat_tickers.append(ticker['symbol'])
                        categories_read[category_name] = len(cat_tickers)
                except Exception as cat_error:
                    logger.error(
                        "error_reading_category_for_subscription",
                        category=category_name,
                        error=str(cat_error),
                        error_type=type(cat_error).__name__
                    )
            
            # Log detalle de lo que se leyó
            logger.info(
                "categories_read_for_subscription",
                categories_with_data=list(categories_read.keys()),
                category_counts=categories_read,
                unique_symbols=len(category_symbols)
            )
            
            current_symbols = category_symbols if category_symbols else {t.symbol for t in tickers[:500]}
            
            # Log para debug
            if not category_symbols:
                logger.warning(
                    "category_symbols_empty_using_fallback",
                    fallback_count=len(current_symbols)
                )
            
            # 2. Detectar NUEVOS símbolos (entraron al ranking)
            new_symbols = current_symbols - self._previous_filtered_symbols
            
            # 3. Detectar símbolos REMOVIDOS (salieron del ranking)
            removed_symbols = self._previous_filtered_symbols - current_symbols
            
            # Debug: Log si hay removed symbols que todavía están en las categorías
            if removed_symbols:
                false_removals = []
                for sym in removed_symbols:
                    if sym in category_symbols:
                        false_removals.append(sym)
                
                if false_removals:
                    logger.error(
                        "false_removal_detected",
                        symbols=false_removals,
                        message="Estos tickers están en categorías pero se marcaron como removed"
                    )
            
            # 4. Publicar SUSCRIPCIONES para nuevos símbolos
            if new_symbols:
                stream_manager = get_stream_manager()
                for symbol in new_symbols:
                    await stream_manager.xadd(
                        settings.key_polygon_subscriptions,  # "polygon_ws:subscriptions"
                        {
                            "symbol": symbol,
                            "action": "subscribe",
                            "source": "scanner_auto",
                            "session": self.current_session.value,
                            "timestamp": datetime.now().isoformat()
                        }
                        # MAXLEN automático según config
                    )
                
                logger.info(
                    "🔔 Auto-subscribe nuevos tickers",
                    count=len(new_symbols),
                    examples=list(new_symbols)[:10]
                )
            
            # 5. Publicar DESUSCRIPCIONES para símbolos removidos
            if removed_symbols:
                stream_manager = get_stream_manager()
                for symbol in removed_symbols:
                    await stream_manager.xadd(
                        settings.key_polygon_subscriptions,
                        {
                            "symbol": symbol,
                            "action": "unsubscribe",
                            "source": "scanner_auto",
                            "session": self.current_session.value,
                            "timestamp": datetime.now().isoformat()
                        }
                        # MAXLEN automático según config
                    )
                
                logger.info(
                    "🔕 Auto-unsubscribe tickers removidos",
                    count=len(removed_symbols),
                    examples=list(removed_symbols)[:10]
                )
            
            # 6. Actualizar tracking para próximo ciclo
            self._previous_filtered_symbols = current_symbols
            
            # 7. Guardar snapshot de tickers activos en Redis SET (para inicialización rápida de Polygon WS)
            try:
                logger.info(
                    "Intentando guardar snapshot",
                    current_symbols_count=len(current_symbols),
                    has_symbols=bool(current_symbols)
                )
                await self.redis.client.delete("polygon_ws:active_tickers")
                if current_symbols:
                    result = await self.redis.client.sadd("polygon_ws:active_tickers", *current_symbols)
                    await self.redis.client.expire("polygon_ws:active_tickers", 3600)  # 1 hora
                    logger.info(
                        "✅ Snapshot de tickers activos guardado",
                        key="polygon_ws:active_tickers",
                        count=len(current_symbols),
                        sadd_result=result
                    )
                else:
                    logger.warning("current_symbols está vacío, no se guardará snapshot")
            except Exception as snapshot_error:
                logger.error(
                    "Error guardando snapshot de tickers",
                    error=str(snapshot_error),
                    error_type=type(snapshot_error).__name__,
                    traceback=traceback.format_exc()
                )
            
            # 8. Log resumen
            logger.info(
                "✅ Auto-subscription actualizada",
                total_active=len(current_symbols),
                new=len(new_symbols),
                removed=len(removed_symbols),
                session=self.current_session.value
            )
        
        except Exception as e:
            logger.error("Error en auto-subscription", error=str(e))
    
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
            categories = self.categorizer.get_all_categories(
                tickers, 
                limit_per_category=settings.default_category_limit
            )
            
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
            
            # Publicar tickers para auto-suscripción en Polygon WS
            await self._publish_filtered_tickers_for_subscription(tickers)
            
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

