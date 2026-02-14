"""
Enrichment Pipeline - Main enrichment loop with incremental Redis Hash writes.

Extracted from analytics/main.py for clean separation of concerns.

Responsibilities:
- Read raw snapshot from snapshot:polygon:latest
- Enrich each ticker with calculated indicators (RVOL, ATR, intraday, VWAP, etc.)
- Detect which tickers changed since last cycle
- Write only changed tickers to Redis Hash (snapshot:enriched:latest)
- Write snapshot:enriched:last_close ONLY on SESSION_CHANGED event

Data Flow:
    snapshot:polygon:latest (JSON STRING, written by data_ingest)
        ↓ READ
    EnrichmentPipeline.run_cycle()
        ↓ ENRICH (merge snapshot + WebSocket trackers + calculated indicators)
        ↓ CHANGE DETECTION (byte comparison)
        ↓ WRITE only changed tickers
    snapshot:enriched:latest (Redis HASH, each ticker = 1 field)
"""

import asyncio
import json as stdlib_json  # For parsing data with NaN/Inf values (DuckDB screener)
import orjson
from datetime import datetime, date
from typing import Dict, Optional, Any
from zoneinfo import ZoneInfo

from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from shared.events import EventBus, EventType, Event

from .change_detector import ChangeDetector
from bar_engine import BarEngine

logger = get_logger(__name__)

# Redis key constants
SNAPSHOT_POLYGON_KEY = "snapshot:polygon:latest"
SNAPSHOT_ENRICHED_HASH = "snapshot:enriched:latest"
SNAPSHOT_ENRICHED_META = "snapshot:enriched:latest:__meta__"
SNAPSHOT_LAST_CLOSE_HASH = "snapshot:enriched:last_close"
SNAPSHOT_ENRICHED_TTL = 600  # 10 minutes
SNAPSHOT_LAST_CLOSE_TTL = 604800  # 7 days


class EnrichmentPipeline:
    """
    Main enrichment pipeline that reads raw Polygon snapshots,
    enriches them with calculated indicators, and writes the result
    to a Redis Hash with incremental change detection.
    
    Data sources merged into each ticker:
      - snapshot:polygon:latest   → real-time price, volume, OHLC (every ~5s)
      - BarEngine (talipp)        → SMA, EMA, MACD, RSI, Stoch, BB, ADX intraday
      - RVOL calculator           → relative volume
      - ATR calculator            → average true range
      - Intraday tracker          → intraday high/low
      - Volume/Price windows      → vol_1min..30min, chg_1min..30min
      - Trades anomaly detector   → trades_z_score
      - metadata:ticker:*         → market_cap, float, security_type, sector (static, refresh 5min)
      - screener:daily_indicators → daily SMA/RSI/BB, 52w high/low (daily, refresh 5min)
    """
    
    # Refresh intervals for slow-changing caches (seconds)
    _METADATA_REFRESH_INTERVAL = 300   # 5 minutes
    _SCREENER_DAILY_REFRESH_INTERVAL = 300  # 5 minutes
    
    def __init__(
        self,
        redis_client: RedisClient,
        rvol_calculator,
        atr_calculator,
        intraday_tracker,
        volume_window_tracker,
        price_window_tracker,
        trades_anomaly_detector,
        trades_count_tracker,
        vwap_cache: Dict[str, float],
        bar_engine: Optional[BarEngine] = None,
    ):
        self.redis = redis_client
        self.rvol_calculator = rvol_calculator
        self.atr_calculator = atr_calculator
        self.intraday_tracker = intraday_tracker
        self.volume_window_tracker = volume_window_tracker
        self.price_window_tracker = price_window_tracker
        self.trades_anomaly_detector = trades_anomaly_detector
        self.trades_count_tracker = trades_count_tracker
        self.vwap_cache = vwap_cache  # Shared reference with vwap consumer
        self.bar_engine = bar_engine  # BarEngine for AM.* indicators (shared reference)
        
        # Change detection
        self._change_detector = ChangeDetector()
        
        # Fundamentals cache — from metadata:ticker:* (static, refreshed every 5 min)
        self._metadata_cache: Dict[str, dict] = {}
        self._metadata_last_refresh: float = 0.0
        
        # Daily indicators cache — from screener:daily_indicators:latest (refreshed every 5 min)
        self._screener_daily_cache: Dict[str, dict] = {}
        self._screener_daily_last_refresh: float = 0.0
        
        # State
        self._last_processed_timestamp = None
        self._last_slot = -1
        self._is_holiday_mode = False
        self._cycle_count = 0
    
    @property
    def is_holiday_mode(self) -> bool:
        return self._is_holiday_mode
    
    @is_holiday_mode.setter
    def is_holiday_mode(self, value: bool):
        self._is_holiday_mode = value
    
    def clear_change_detector(self) -> None:
        """Clear change detector cache (for new trading day)."""
        self._change_detector.clear()
    
    async def run_loop(self) -> None:
        """
        Main processing loop. Runs continuously.
        
        Each cycle:
        1. Read snapshot:polygon:latest
        2. Enrich all tickers
        3. Detect changes
        4. Write only changed tickers to Redis Hash
        """
        logger.info("enrichment_pipeline_started")
        
        while True:
            try:
                if self._is_holiday_mode:
                    await asyncio.sleep(60)
                    continue
                
                await self._run_single_cycle()
                
            except asyncio.CancelledError:
                logger.info("enrichment_pipeline_cancelled")
                raise
            except Exception as e:
                logger.error(
                    "enrichment_pipeline_error",
                    error=str(e),
                    error_type=type(e).__name__
                )
                await asyncio.sleep(5)
    
    async def _run_single_cycle(self) -> None:
        """Execute one enrichment cycle."""
        now = datetime.now(ZoneInfo("America/New_York"))
        
        # Detect slot change (for RVOL logging)
        current_slot = self.rvol_calculator.slot_manager.get_current_slot(now)
        if current_slot >= 0 and current_slot != self._last_slot:
            logger.info(
                "new_slot_detected",
                slot=current_slot,
                slot_info=self.rvol_calculator.slot_manager.format_slot_info(current_slot)
            )
            self._last_slot = current_slot
        
        # Read raw snapshot
        snapshot_data = await self.redis.get(SNAPSHOT_POLYGON_KEY)
        if not snapshot_data:
            await asyncio.sleep(1)
            return
        
        # Check if already processed
        snapshot_timestamp = snapshot_data.get('timestamp')
        if snapshot_timestamp == self._last_processed_timestamp:
            await asyncio.sleep(0.5)
            return
        
        tickers_data = snapshot_data.get('tickers', [])
        if not tickers_data:
            await asyncio.sleep(1)
            return
        
        # Refresh slow-changing caches (metadata + screener daily) if stale
        await self._maybe_refresh_slow_caches()
        
        # Get ATR batch from cache
        symbols = [t.get('ticker') for t in tickers_data if t.get('ticker')]
        current_prices = {
            t.get('ticker'): t.get('lastTrade', {}).get('p') or t.get('day', {}).get('c')
            for t in tickers_data if t.get('ticker')
        }
        atr_data = await self.atr_calculator._get_batch_from_cache(symbols)
        
        # Update ATR percent with current prices
        for symbol, atr_info in atr_data.items():
            if atr_info and symbol in current_prices:
                price = current_prices[symbol]
                if price and price > 0:
                    atr_info['atr_percent'] = round((atr_info['atr'] / price) * 100, 2)
        
        # Enrich all tickers
        enriched_tickers: Dict[str, dict] = {}
        rvol_mapping: Dict[str, str] = {}
        
        for ticker_data in tickers_data:
            try:
                symbol = ticker_data.get('ticker')
                if not symbol:
                    continue
                
                enriched = await self._enrich_single_ticker(
                    ticker_data, symbol, now, atr_data
                )
                
                if enriched:
                    enriched_tickers[symbol] = enriched
                    if enriched.get('rvol') and enriched['rvol'] > 0:
                        rvol_mapping[symbol] = str(round(enriched['rvol'], 2))
                        
            except Exception as e:
                logger.error("error_enriching_ticker", symbol=ticker_data.get('ticker'), error=str(e))
        
        # Change detection + incremental write to Redis Hash
        if self._change_detector.is_first_cycle:
            # First cycle: write everything
            changed = self._change_detector.force_full_write(enriched_tickers)
            changed_count = len(changed)
            total_count = len(enriched_tickers)
            logger.info("first_cycle_full_write", total=total_count)
        else:
            changed, total_count, changed_count = self._change_detector.detect_changes(enriched_tickers)
        
        # Write to Redis Hash (only changed tickers)
        if changed:
            await self._write_to_hash(changed, snapshot_timestamp, total_count)
        
        # Write RVOLs to hash
        if rvol_mapping:
            await self.redis.client.hset("rvol:current_slot", mapping=rvol_mapping)
            await self.redis.client.expire("rvol:current_slot", 300)
        
        self._last_processed_timestamp = snapshot_timestamp
        self._cycle_count += 1
        
        logger.info(
            "enrichment_cycle_complete",
            total=total_count,
            changed=changed_count,
            change_pct=round(changed_count / total_count * 100, 1) if total_count > 0 else 0,
            slot=current_slot,
            cycle=self._cycle_count
        )
    
    async def _enrich_single_ticker(
        self,
        ticker_data: dict,
        symbol: str,
        now: datetime,
        atr_data: dict
    ) -> Optional[dict]:
        """
        Enrich a single ticker with all calculated indicators.
        
        Merges:
        - Raw Polygon snapshot data
        - RVOL (calculated from snapshot volume)
        - ATR (from historical cache)
        - Intraday high/low (tracked from prices)
        - VWAP (from WebSocket cache, fallback to snapshot)
        - Volume windows (from VolumeWindowTracker, fed by WebSocket consumer)
        - Price windows (from PriceWindowTracker, fed by WebSocket consumer)
        - Trades anomaly (from TradesAnomalyDetector)
        """
        # Volume (priority: min.av > day.v)
        min_data = ticker_data.get('min', {})
        day_data = ticker_data.get('day', {})
        
        volume = 0
        if min_data and min_data.get('av'):
            volume = min_data.get('av', 0)
        elif day_data and day_data.get('v'):
            volume = day_data.get('v', 0)
        
        # RVOL
        rvol = None
        if volume > 0:
            # Update intraday high/low
            current_price = ticker_data.get('lastTrade', {}).get('p')
            if not current_price:
                current_price = day_data.get('c') if day_data else None
            if current_price and current_price > 0:
                self.intraday_tracker.update(symbol, current_price)
            
            # Update volume for RVOL
            await self.rvol_calculator.update_volume_for_symbol(
                symbol=symbol,
                volume_accumulated=volume,
                timestamp=now
            )
            rvol = await self.rvol_calculator.calculate_rvol(symbol, timestamp=now)
            if rvol and rvol > 0:
                ticker_data['rvol'] = round(rvol, 2)
        
        if 'rvol' not in ticker_data:
            ticker_data['rvol'] = None
        
        # ATR
        if symbol in atr_data and atr_data[symbol]:
            ticker_data['atr'] = atr_data[symbol]['atr']
            ticker_data['atr_percent'] = atr_data[symbol]['atr_percent']
        else:
            ticker_data['atr'] = None
            ticker_data['atr_percent'] = None
        
        # Intraday high/low
        intraday_data = self.intraday_tracker.get(symbol)
        if intraday_data:
            ticker_data['intraday_high'] = intraday_data.get('high')
            ticker_data['intraday_low'] = intraday_data.get('low')
        else:
            ticker_data['intraday_high'] = day_data.get('h') if day_data else None
            ticker_data['intraday_low'] = day_data.get('l') if day_data else None
        
        # VWAP (priority: day.vw > vwap_cache from WebSocket)
        day_vwap = day_data.get('vw') if day_data else None
        if day_vwap and day_vwap > 0:
            ticker_data['vwap'] = day_vwap
        elif symbol in self.vwap_cache and self.vwap_cache[symbol] > 0:
            ticker_data['vwap'] = self.vwap_cache[symbol]
        elif 'vwap' not in ticker_data or not ticker_data.get('vwap'):
            ticker_data['vwap'] = None
        
        # ================================================================
        # Volume windows: A.* per-second (priority) > AM.* per-minute (fallback)
        # ================================================================
        has_per_second_vol = False
        if self.volume_window_tracker:
            vol_windows = self.volume_window_tracker.get_all_windows(symbol)
            if vol_windows.vol_1min is not None:
                # A.* per-second data available (higher precision)
                has_per_second_vol = True
                ticker_data['vol_1min'] = vol_windows.vol_1min
                ticker_data['vol_5min'] = vol_windows.vol_5min
                ticker_data['vol_10min'] = vol_windows.vol_10min
                ticker_data['vol_15min'] = vol_windows.vol_15min
                ticker_data['vol_30min'] = vol_windows.vol_30min
        
        if not has_per_second_vol and self.bar_engine and self.bar_engine.has_data(symbol):
            # Fallback: AM.* per-minute data (covers 100% of market)
            ticker_data['vol_1min'] = self.bar_engine.get_volume_window(symbol, 1)
            ticker_data['vol_5min'] = self.bar_engine.get_volume_window(symbol, 5)
            ticker_data['vol_10min'] = self.bar_engine.get_volume_window(symbol, 10)
            ticker_data['vol_15min'] = self.bar_engine.get_volume_window(symbol, 15)
            ticker_data['vol_30min'] = self.bar_engine.get_volume_window(symbol, 30)
        
        # ================================================================
        # Price change windows: A.* per-second (priority) > AM.* per-minute (fallback)
        # ================================================================
        has_per_second_chg = False
        if self.price_window_tracker:
            price_windows = self.price_window_tracker.get_all_windows(symbol)
            if price_windows.chg_1min is not None:
                # A.* per-second data available (higher precision)
                has_per_second_chg = True
                ticker_data['chg_1min'] = price_windows.chg_1min
                ticker_data['chg_5min'] = price_windows.chg_5min
                ticker_data['chg_10min'] = price_windows.chg_10min
                ticker_data['chg_15min'] = price_windows.chg_15min
                ticker_data['chg_30min'] = price_windows.chg_30min
        
        if not has_per_second_chg:
            if self.bar_engine and self.bar_engine.has_data(symbol):
                # Fallback: AM.* per-minute data (covers 100% of market)
                ticker_data['chg_1min'] = self.bar_engine.get_price_change(symbol, 1)
                ticker_data['chg_5min'] = self.bar_engine.get_price_change(symbol, 5)
                ticker_data['chg_10min'] = self.bar_engine.get_price_change(symbol, 10)
                ticker_data['chg_15min'] = self.bar_engine.get_price_change(symbol, 15)
                ticker_data['chg_30min'] = self.bar_engine.get_price_change(symbol, 30)
            else:
                # No data from either source - keep keys as None for backward compat
                ticker_data.setdefault('chg_1min', None)
                ticker_data.setdefault('chg_5min', None)
                ticker_data.setdefault('chg_10min', None)
                ticker_data.setdefault('chg_15min', None)
                ticker_data.setdefault('chg_30min', None)
        
        # ================================================================
        # Streaming indicators from BarEngine (AM.* - covers 100% of market)
        # Always set keys for consistent JSON schema (frontend expects them).
        # ================================================================
        _indicator_keys = ('rsi_14', 'ema_9', 'ema_20', 'ema_50',
                           'sma_5', 'sma_8', 'sma_20', 'sma_50', 'sma_200',
                           'macd_line', 'macd_signal', 'macd_hist',
                           'bb_upper', 'bb_mid', 'bb_lower',
                           'adx_14', 'stoch_k', 'stoch_d',
                           'chg_60min', 'vol_60min')
        
        if self.bar_engine and self.bar_engine.has_data(symbol):
            indicators = self.bar_engine.get_indicators(symbol)
            if indicators is not None:
                ticker_data['rsi_14'] = indicators.rsi_14
                ticker_data['ema_9'] = indicators.ema_9
                ticker_data['ema_20'] = indicators.ema_20
                ticker_data['ema_50'] = indicators.ema_50
                # SMA — Trade Ideas alignment (intraday from 1-min bars)
                ticker_data['sma_5'] = indicators.sma_5
                ticker_data['sma_8'] = indicators.sma_8
                ticker_data['sma_20'] = indicators.sma_20
                ticker_data['sma_50'] = indicators.sma_50
                ticker_data['sma_200'] = indicators.sma_200
                ticker_data['macd_line'] = indicators.macd_line
                ticker_data['macd_signal'] = indicators.macd_signal
                ticker_data['macd_hist'] = indicators.macd_hist
                ticker_data['bb_upper'] = indicators.bb_upper
                ticker_data['bb_mid'] = indicators.bb_mid
                ticker_data['bb_lower'] = indicators.bb_lower
                ticker_data['adx_14'] = indicators.adx_14
                ticker_data['stoch_k'] = indicators.stoch_k
                ticker_data['stoch_d'] = indicators.stoch_d
                ticker_data['chg_60min'] = indicators.chg_60m
                ticker_data['vol_60min'] = indicators.vol_60m

                # Multi-timeframe indicators (flatten into enriched fields)
                # Format: {indicator}_{period}m  e.g. sma_5_5m, macd_line_15m
                if indicators.tf:
                    for tf_period, tf_ind in indicators.tf.items():
                        suffix = f"_{tf_period}m"
                        for key, val in tf_ind.items():
                            if key != 'bar_count' and val is not None:
                                ticker_data[key + suffix] = val
            else:
                # BarEngine has state but indicators not ready (warmup period)
                for key in _indicator_keys:
                    ticker_data.setdefault(key, None)
        else:
            # No BarEngine data - set all to None for consistent schema
            for key in _indicator_keys:
                ticker_data.setdefault(key, None)
        
        # Trades anomaly detection
        trades_today = 0
        if self.trades_count_tracker:
            trades_today = self.trades_count_tracker.get_trades_today(symbol) or 0
        
        if self.trades_anomaly_detector and trades_today > 0:
            anomaly_result = await self.trades_anomaly_detector.detect_anomaly(
                symbol=symbol,
                trades_today=trades_today
            )
            if anomaly_result:
                ticker_data['trades_today'] = anomaly_result.trades_today
                ticker_data['avg_trades_5d'] = round(anomaly_result.avg_trades_5d, 0)
                ticker_data['trades_z_score'] = round(anomaly_result.z_score, 2)
                ticker_data['is_trade_anomaly'] = anomaly_result.is_anomaly
            else:
                ticker_data['trades_today'] = trades_today
                ticker_data['avg_trades_5d'] = None
                ticker_data['trades_z_score'] = None
                ticker_data['is_trade_anomaly'] = False
        else:
            ticker_data['trades_today'] = trades_today if trades_today > 0 else None
            ticker_data['avg_trades_5d'] = None
            ticker_data['trades_z_score'] = None
            ticker_data['is_trade_anomaly'] = False
        
        # ================================================================
        # Fundamentals from metadata cache (static, refreshed every 5 min)
        # Source: metadata:ticker:* ← Polygon Reference API (ticker-metadata-service)
        # ================================================================
        meta = self._metadata_cache.get(symbol, {})
        ticker_data['market_cap'] = meta.get('market_cap')
        ticker_data['float_shares'] = meta.get('float_shares')
        ticker_data['shares_outstanding'] = meta.get('shares_outstanding')
        ticker_data['security_type'] = meta.get('security_type')  # CS, ETF, PFD, WARRANT, etc.
        ticker_data['sector'] = meta.get('sector')
        ticker_data['industry'] = meta.get('industry')
        
        # ================================================================
        # Daily indicators from screener cache (daily, refreshed every 5 min)
        # Source: screener:daily_indicators:latest ← DuckDB screener service
        # These are DAILY timeframe — distinct from intraday BarEngine indicators.
        # ================================================================
        daily = self._screener_daily_cache.get(symbol, {})
        ticker_data['daily_sma_20'] = daily.get('daily_sma_20')
        ticker_data['daily_sma_50'] = daily.get('daily_sma_50')
        ticker_data['daily_sma_200'] = daily.get('daily_sma_200')
        ticker_data['daily_rsi'] = daily.get('daily_rsi')
        ticker_data['daily_bb_upper'] = daily.get('daily_bb_upper')
        ticker_data['daily_bb_lower'] = daily.get('daily_bb_lower')
        ticker_data['high_52w'] = daily.get('high_52w')
        ticker_data['low_52w'] = daily.get('low_52w')
        
        # Flatten lastQuote bid/ask to top-level fields BEFORE stripping.
        # This enables removing the lastQuote nested dict entirely,
        # eliminating ~30% of false "changed" detections from quote-only updates.
        # Downstream consumers (scanner, api_gateway) read from these flat fields.
        last_quote = ticker_data.get('lastQuote')
        if isinstance(last_quote, dict):
            ticker_data['bid'] = last_quote.get('p')
            ticker_data['ask'] = last_quote.get('P')
            # Convert lots to shares (1 lot = 100 shares)
            bid_lots = last_quote.get('s')
            ask_lots = last_quote.get('S')
            ticker_data['bid_size'] = bid_lots * 100 if bid_lots else None
            ticker_data['ask_size'] = ask_lots * 100 if ask_lots else None
        else:
            ticker_data.setdefault('bid', None)
            ticker_data.setdefault('ask', None)
            ticker_data.setdefault('bid_size', None)
            ticker_data.setdefault('ask_size', None)
        
        # ================================================================
        # Computed derived fields (from data already on ticker_data)
        # These fields are computed in real-time from existing enriched data.
        # ================================================================
        self._compute_derived_fields(ticker_data, symbol)
        
        # ================================================================
        # Daily screener fields: multi-day changes, avg volumes, distances
        # Source: screener:daily_indicators:latest (refreshed every 5 min)
        # ================================================================
        daily = self._screener_daily_cache.get(symbol, {})
        ticker_data['daily_sma_20'] = daily.get('daily_sma_20')
        ticker_data['daily_sma_50'] = daily.get('daily_sma_50')
        ticker_data['daily_sma_200'] = daily.get('daily_sma_200')
        ticker_data['daily_rsi'] = daily.get('daily_rsi')
        ticker_data['daily_bb_upper'] = daily.get('daily_bb_upper')
        ticker_data['daily_bb_lower'] = daily.get('daily_bb_lower')
        ticker_data['high_52w'] = daily.get('high_52w')
        ticker_data['low_52w'] = daily.get('low_52w')
        # New: multi-day change percentages
        ticker_data['change_1d'] = daily.get('change_1d')
        ticker_data['change_3d'] = daily.get('change_3d')
        ticker_data['change_5d'] = daily.get('change_5d')
        ticker_data['change_10d'] = daily.get('change_10d')
        ticker_data['change_20d'] = daily.get('change_20d')
        # New: average daily volumes
        ticker_data['avg_volume_5d'] = daily.get('avg_volume_5d')
        ticker_data['avg_volume_10d'] = daily.get('avg_volume_10d')
        ticker_data['avg_volume_20d'] = daily.get('avg_volume_20d')
        # New: daily gap
        ticker_data['daily_gap_percent'] = daily.get('daily_gap_percent')
        # New: distance from daily SMAs (%)
        ticker_data['dist_daily_sma_20'] = daily.get('dist_daily_sma_20')
        ticker_data['dist_daily_sma_50'] = daily.get('dist_daily_sma_50')
        # New: 52w distances
        ticker_data['from_52w_high'] = daily.get('from_52w_high')
        ticker_data['from_52w_low'] = daily.get('from_52w_low')
        # New: daily ADX, ATR
        ticker_data['daily_adx_14'] = daily.get('daily_adx_14')
        ticker_data['daily_atr_percent'] = daily.get('daily_atr_percent')
        # New: Bollinger position
        ticker_data['daily_bb_position'] = daily.get('daily_bb_position')
        
        # ================================================================
        # Additional derived fields (computed AFTER screener merge)
        # These need avg_volume_10d which comes from screener daily cache.
        # ================================================================
        price = ticker_data.get('lastTrade', {}).get('p') if isinstance(ticker_data.get('lastTrade'), dict) else None
        if not price:
            _day = ticker_data.get('day', {})
            price = _day.get('c') if isinstance(_day, dict) else None
        _day_data = ticker_data.get('day', {}) if isinstance(ticker_data.get('day'), dict) else {}
        
        # Volume Today % = (volume / avg_volume_10d) * 100
        _day_vol = _day_data.get('v')
        _avg_vol_10d = ticker_data.get('avg_volume_10d')
        if _day_vol and _avg_vol_10d and _avg_vol_10d > 0:
            ticker_data['volume_today_pct'] = round((_day_vol / _avg_vol_10d) * 100, 1)
        else:
            ticker_data.setdefault('volume_today_pct', None)
        
        # Price from day high (%) = ((price - day.h) / day.h) * 100
        _day_high = _day_data.get('h')
        if price and _day_high and _day_high > 0:
            ticker_data['price_from_high'] = round((price - _day_high) / _day_high * 100, 2)
        else:
            ticker_data.setdefault('price_from_high', None)
        
        # Distance from NBBO (%) = distance from inside market
        _bid = ticker_data.get('bid')
        _ask = ticker_data.get('ask')
        if price and _bid and _ask and _bid > 0 and _ask > 0:
            if price >= _bid and price <= _ask:
                ticker_data['distance_from_nbbo'] = 0.0
            elif price < _bid:
                ticker_data['distance_from_nbbo'] = round((_bid - price) / _bid * 100, 2)
            else:
                ticker_data['distance_from_nbbo'] = round((price - _ask) / _ask * 100, 2)
        else:
            ticker_data.setdefault('distance_from_nbbo', None)
        
        # Minute volume (flat field from nested min.v)
        _min_data = ticker_data.get('min', {}) if isinstance(ticker_data.get('min'), dict) else {}
        _min_vol = _min_data.get('v')
        if _min_vol is not None:
            ticker_data['minute_volume'] = int(_min_vol)
        else:
            ticker_data.setdefault('minute_volume', None)
        
        # Strip noisy/unused fields to reduce serialization and false changes
        self._strip_noisy_fields(ticker_data)
        
        return ticker_data
    
    def _compute_derived_fields(self, ticker_data: dict, symbol: str) -> None:
        """
        Compute derived real-time fields from existing enriched data.
        All computations are simple arithmetic — zero external I/O.
        """
        # Current price
        price = ticker_data.get('lastTrade', {}).get('p') if isinstance(ticker_data.get('lastTrade'), dict) else None
        if not price:
            day = ticker_data.get('day', {})
            price = day.get('c') if isinstance(day, dict) else None
        
        day_data = ticker_data.get('day', {}) if isinstance(ticker_data.get('day'), dict) else {}
        prev_day = ticker_data.get('prevDay', {}) if isinstance(ticker_data.get('prevDay'), dict) else {}
        
        day_open = day_data.get('o')
        day_high = day_data.get('h')
        day_low = day_data.get('l')
        day_volume = day_data.get('v')
        prev_close = prev_day.get('c')
        prev_volume = prev_day.get('v')
        
        bid = ticker_data.get('bid')
        ask = ticker_data.get('ask')
        bid_size = ticker_data.get('bid_size')
        ask_size = ticker_data.get('ask_size')
        
        intraday_high = ticker_data.get('intraday_high')
        intraday_low = ticker_data.get('intraday_low')
        
        vwap = ticker_data.get('vwap')
        float_shares = ticker_data.get('float_shares')
        volume = day_volume or 0
        
        # Gap % (today's open vs prev close)
        if day_open and prev_close and prev_close > 0:
            ticker_data['gap_percent'] = round((day_open - prev_close) / prev_close * 100, 2)
        else:
            ticker_data.setdefault('gap_percent', None)
        
        # Dollar volume = price * volume
        if price and price > 0 and volume > 0:
            ticker_data['dollar_volume'] = round(price * volume, 0)
        else:
            ticker_data['dollar_volume'] = None
        
        # Today's range (dollars and %)
        h = intraday_high or (day_high if day_high else None)
        l = intraday_low or (day_low if day_low else None)
        if h and l and l > 0:
            ticker_data['todays_range'] = round(h - l, 4)
            ticker_data['todays_range_pct'] = round((h - l) / l * 100, 2)
        else:
            ticker_data['todays_range'] = None
            ticker_data['todays_range_pct'] = None
        
        # Bid/Ask ratio
        if bid_size and ask_size and ask_size > 0:
            ticker_data['bid_ask_ratio'] = round(bid_size / ask_size, 2)
        else:
            ticker_data['bid_ask_ratio'] = None
        
        # Float turnover = volume / float_shares
        if float_shares and float_shares > 0 and volume > 0:
            ticker_data['float_turnover'] = round(volume / float_shares, 4)
        else:
            ticker_data['float_turnover'] = None
        
        # Distance from VWAP (%)
        if price and vwap and vwap > 0:
            ticker_data['dist_from_vwap'] = round((price - vwap) / vwap * 100, 2)
        else:
            ticker_data['dist_from_vwap'] = None
        
        # Distance from intraday SMAs (%)
        for sma_key in ('sma_5', 'sma_8', 'sma_20', 'sma_50', 'sma_200'):
            sma_val = ticker_data.get(sma_key)
            if price and sma_val and sma_val > 0:
                ticker_data[f'dist_{sma_key}'] = round((price - sma_val) / sma_val * 100, 2)
            else:
                ticker_data[f'dist_{sma_key}'] = None
        
        # Position in today's range (0-100%)
        if h and l and h != l and price:
            ticker_data['pos_in_range'] = round((price - l) / (h - l) * 100, 2)
        else:
            ticker_data['pos_in_range'] = None
        
        # Below high / Above low ($ distance)
        if intraday_high and price:
            ticker_data['below_high'] = round(intraday_high - price, 4)
        else:
            ticker_data['below_high'] = None
        
        if intraday_low and price:
            ticker_data['above_low'] = round(price - intraday_low, 4)
        else:
            ticker_data['above_low'] = None
        
        # Change from previous day close ($)
        if price and prev_close and prev_close > 0:
            ticker_data['change_from_close'] = round(price - prev_close, 4)
        else:
            ticker_data['change_from_close'] = None
        
        # Position of open in today's range (%)
        if day_open and h and l and h != l:
            ticker_data['pos_of_open'] = round((day_open - l) / (h - l) * 100, 2)
        else:
            ticker_data['pos_of_open'] = None
        
        # Previous day volume
        if prev_volume and prev_volume > 0:
            ticker_data['prev_day_volume'] = prev_volume
        else:
            ticker_data.setdefault('prev_day_volume', None)
    
    @staticmethod
    def _strip_noisy_fields(ticker_data: dict) -> None:
        """
        Remove fields that cause excessive false positives in ChangeDetector
        and/or are not consumed by any downstream service.
        
        Saves ~200 bytes/ticker AND dramatically reduces false "changed" detections.
        
        Fields removed:
        - updated:    Polygon nanosecond timestamp, changes EVERY cycle for ALL tickers.
        - fmv:        Fair market value, almost always null.
        - lastQuote:  ENTIRE dict removed (data pre-flattened to bid/ask/bid_size/ask_size).
                      Eliminates ~30% of false "changed" detections from NBBO quote churn.
        - lastTrade.i/x/c/s: Trade metadata not consumed by any downstream service.
        - min.n/otc:  Transaction count and OTC flag, unused.
        - day.otc:    OTC flag, unused.
        - prevDay.o/h/l/vw: Static fields unused (only prevDay.c and .v are consumed).
        """
        # Top-level volatile/unused fields
        ticker_data.pop('updated', None)
        ticker_data.pop('fmv', None)
        
        # lastTrade: keep only .p (price) and .t (timestamp, used by scanner)
        last_trade = ticker_data.get('lastTrade')
        if isinstance(last_trade, dict):
            last_trade.pop('i', None)   # trade ID - unique per trade
            last_trade.pop('x', None)   # exchange ID - rarely needed
            last_trade.pop('c', None)   # conditions array - unused
            last_trade.pop('s', None)   # trade size - unused downstream
        
        # lastQuote: FULLY REMOVED - data already flattened to bid/ask/bid_size/ask_size
        # This eliminates all quote-only false changes (high-frequency NBBO updates)
        ticker_data.pop('lastQuote', None)
        
        # min: keep OHLCV + .av + .t + .vw (used by realtime route)
        min_data = ticker_data.get('min')
        if isinstance(min_data, dict):
            min_data.pop('n', None)     # transaction count - unused
            min_data.pop('otc', None)   # OTC flag - static/unused
        
        # day: keep .o .h .l .c .v .vw (all used)
        day_data = ticker_data.get('day')
        if isinstance(day_data, dict):
            day_data.pop('otc', None)   # OTC flag - static/unused
        
        # prevDay: keep only .c (prev_close) and .v (prev_volume)
        # Scanner and event detector only use these two fields.
        # Removes .o, .h, .l, .vw (~60 bytes saved, 100% static data)
        prev_day = ticker_data.get('prevDay')
        if isinstance(prev_day, dict):
            prev_day.pop('o', None)     # prev open - unused
            prev_day.pop('h', None)     # prev high - unused
            prev_day.pop('l', None)     # prev low - unused
            prev_day.pop('vw', None)    # prev VWAP - unused
    
    async def _write_to_hash(
        self,
        changed: Dict[str, str],
        timestamp: str,
        total_count: int
    ) -> None:
        """
        Write changed tickers to Redis Hash using pipeline.
        
        Args:
            changed: Dict[symbol, serialized_json_str] of changed tickers
            timestamp: Snapshot timestamp
            total_count: Total number of enriched tickers
        """
        try:
            meta = orjson.dumps({
                "timestamp": timestamp,
                "count": total_count,
                "changed": len(changed),
                "version": 2
            }).decode("utf-8")
            
            pipe = self.redis.client.pipeline()
            
            # Write changed tickers
            if changed:
                pipe.hset(SNAPSHOT_ENRICHED_HASH, mapping=changed)
            
            # Write metadata
            pipe.hset(SNAPSHOT_ENRICHED_HASH, "__meta__", meta)
            
            # Set TTL
            pipe.expire(SNAPSHOT_ENRICHED_HASH, SNAPSHOT_ENRICHED_TTL)
            
            await pipe.execute()
            
        except Exception as e:
            logger.error("error_writing_hash", error=str(e), changed_count=len(changed))
    
    async def write_last_close_snapshot(self) -> None:
        """
        Copy current enriched hash to last_close hash.
        
        Called ONLY on SESSION_CHANGED event (market close),
        NOT every enrichment cycle. This eliminates ~14 MB/s
        of redundant writes.
        """
        try:
            # Read all current enriched data
            all_data = await self.redis.client.hgetall(SNAPSHOT_ENRICHED_HASH)
            
            if not all_data:
                logger.warning("no_enriched_data_for_last_close")
                return
            
            # Write to last_close hash
            pipe = self.redis.client.pipeline()
            pipe.delete(SNAPSHOT_LAST_CLOSE_HASH)
            if all_data:
                pipe.hset(SNAPSHOT_LAST_CLOSE_HASH, mapping=all_data)
            pipe.expire(SNAPSHOT_LAST_CLOSE_HASH, SNAPSHOT_LAST_CLOSE_TTL)
            await pipe.execute()
            
            logger.info(
                "last_close_snapshot_saved",
                fields_count=len(all_data),
                ttl_days=SNAPSHOT_LAST_CLOSE_TTL // 86400
            )
        except Exception as e:
            logger.error("error_writing_last_close", error=str(e))
    
    # ================================================================
    # Slow-changing caches: metadata (fundamentals) + screener (daily indicators)
    # These are refreshed every 5 minutes, NOT every enrichment cycle.
    # In-cycle cost is a single dict lookup per ticker (~0.001ms).
    # ================================================================
    
    async def _maybe_refresh_slow_caches(self) -> None:
        """Refresh metadata and screener daily caches if stale. Called once per cycle."""
        import time
        now = time.monotonic()
        
        if now - self._metadata_last_refresh > self._METADATA_REFRESH_INTERVAL:
            await self._refresh_metadata_cache()
            self._metadata_last_refresh = now
        
        if now - self._screener_daily_last_refresh > self._SCREENER_DAILY_REFRESH_INTERVAL:
            await self._refresh_screener_daily_cache()
            self._screener_daily_last_refresh = now
    
    async def _refresh_metadata_cache(self) -> None:
        """
        Load fundamentals from metadata:ticker:* keys into memory.
        
        Source: ticker-metadata-service (Polygon Reference API, updated daily).
        Fields extracted: market_cap, free_float, type, sector, industry,
                          shares_outstanding, is_etf.
        """
        try:
            # SCAN to get all metadata keys (non-blocking iteration)
            new_cache: Dict[str, dict] = {}
            cursor = b"0"
            while True:
                cursor, keys = await self.redis.client.scan(
                    cursor=cursor, match="metadata:ticker:*", count=2000
                )
                if keys:
                    # Batch GET with pipeline
                    pipe = self.redis.client.pipeline()
                    for key in keys:
                        pipe.get(key)
                    results = await pipe.execute()
                    
                    for key, raw in zip(keys, results):
                        if not raw:
                            continue
                        try:
                            # key is bytes: b"metadata:ticker:AAPL"
                            symbol = key.decode().split(":", 2)[2] if isinstance(key, bytes) else key.split(":", 2)[2]
                            data = orjson.loads(raw)
                            new_cache[symbol] = {
                                "market_cap": data.get("market_cap"),
                                "float_shares": data.get("free_float"),
                                "shares_outstanding": data.get("shares_outstanding"),
                                "security_type": data.get("type"),        # CS, ETF, PFD, WARRANT, etc.
                                "sector": data.get("sector"),
                                "industry": data.get("industry"),
                                "is_etf": data.get("is_etf", False),
                            }
                        except Exception:
                            continue
                
                if cursor == 0 or cursor == b"0":
                    break
            
            self._metadata_cache = new_cache
            logger.info("metadata_cache_refreshed", tickers=len(new_cache))
        except Exception as e:
            logger.error("metadata_cache_refresh_error", error=str(e))
    
    async def _refresh_screener_daily_cache(self) -> None:
        """
        Load daily technical indicators from screener service.
        
        Source: screener:daily_indicators:latest (DuckDB, updated every 5 min).
        Fields extracted: daily SMA 20/50/200, daily RSI, daily Bollinger,
                          52-week high/low, ATR daily.
        These are DAILY indicators — distinct from the intraday ones from BarEngine.
        """
        try:
            raw = await self.redis.client.get("screener:daily_indicators:latest")
            if not raw:
                logger.debug("no_screener_daily_data")
                return
            
            # Use stdlib json.loads because DuckDB may produce NaN/Inf values
            # which are not valid JSON per RFC but Python's json module handles them.
            raw_str = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            data = stdlib_json.loads(raw_str)
            tickers = data.get("tickers", {})
            if not isinstance(tickers, dict):
                return
            
            new_cache: Dict[str, dict] = {}
            sf = self._safe_float
            for symbol, ind in tickers.items():
                if not isinstance(ind, dict):
                    continue
                new_cache[symbol] = {
                    # Daily SMAs
                    "daily_sma_20": sf(ind.get("sma_20")),
                    "daily_sma_50": sf(ind.get("sma_50")),
                    "daily_sma_200": sf(ind.get("sma_200")),
                    # Daily RSI / ADX
                    "daily_rsi": sf(ind.get("rsi")),
                    "daily_adx_14": sf(ind.get("adx_14")),
                    # Daily Bollinger
                    "daily_bb_upper": sf(ind.get("bb_upper")),
                    "daily_bb_lower": sf(ind.get("bb_lower")),
                    "daily_bb_position": sf(ind.get("bb_position")),
                    # 52-week
                    "high_52w": sf(ind.get("high_52w")),
                    "low_52w": sf(ind.get("low_52w")),
                    "from_52w_high": sf(ind.get("from_52w_high")),
                    "from_52w_low": sf(ind.get("from_52w_low")),
                    # ATR daily
                    "daily_atr_percent": sf(ind.get("atr_percent")),
                    # Multi-day changes
                    "change_1d": sf(ind.get("change_1d")),
                    "change_3d": sf(ind.get("change_3d")),
                    "change_5d": sf(ind.get("change_5d")),
                    "change_10d": sf(ind.get("change_10d")),
                    "change_20d": sf(ind.get("change_20d")),
                    # Gap (daily)
                    "daily_gap_percent": sf(ind.get("gap_percent")),
                    # Average volumes
                    "avg_volume_5d": sf(ind.get("avg_volume_5")),
                    "avg_volume_10d": sf(ind.get("avg_volume_10")),
                    "avg_volume_20d": sf(ind.get("avg_volume_20")),
                    # Distance from daily SMAs (%)
                    "dist_daily_sma_20": sf(ind.get("dist_sma_20")),
                    "dist_daily_sma_50": sf(ind.get("dist_sma_50")),
                }
            
            self._screener_daily_cache = new_cache
            logger.info("screener_daily_cache_refreshed", tickers=len(new_cache))
        except Exception as e:
            logger.error("screener_daily_cache_refresh_error", error=str(e))
    
    @staticmethod
    def _safe_float(val) -> Optional[float]:
        """Convert value to float safely, return None if not possible."""
        if val is None:
            return None
        try:
            f = float(val)
            return f if f == f else None  # NaN check
        except (ValueError, TypeError):
            return None
    
    def get_stats(self) -> dict:
        """Get pipeline statistics."""
        return {
            "cycle_count": self._cycle_count,
            "last_processed_timestamp": self._last_processed_timestamp,
            "is_holiday_mode": self._is_holiday_mode,
            "metadata_cache_size": len(self._metadata_cache),
            "screener_daily_cache_size": len(self._screener_daily_cache),
            "change_detector": self._change_detector.get_stats()
        }
