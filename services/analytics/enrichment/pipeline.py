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
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from .change_detector import ChangeDetector
from bar_engine import BarEngine
from shared.enums.market_session import MarketSession

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
    _DILUTION_SCORES_REFRESH_INTERVAL = 300  # 5 minutes
    
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

        # Dilution scores cache — from dilution:scores:latest (refreshed every 5 min)
        self._dilution_scores_cache: Dict[str, dict] = {}
        self._dilution_scores_last_refresh: float = 0.0
        
        # State
        self._last_processed_timestamp = None
        self._last_slot = -1
        self._is_holiday_mode = False
        self._cycle_count = 0
        
        # Pre-market high/low tracker (reset at market open 9:30 ET)
        self._premarket_highs: Dict[str, float] = {}
        self._premarket_lows: Dict[str, float] = {}
        self._premarket_frozen = False

        # Post-market: freeze regular close at 16:00 ET and cache regular volumes
        self._regular_close_cache: Dict[str, float] = {}
        self._regular_close_frozen = False
        self._regular_volumes_cache: Dict[str, int] = {}
        self._regular_volumes_loaded = False
    
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
        
        # Determine current market session (stored as instance attr for per-ticker use)
        session = MarketSession.from_time_et(now.hour, now.minute)
        self._current_session = session
        
        # Freeze regular close prices at market close for accurate post-market calculations
        if session == MarketSession.POST_MARKET and not self._regular_close_frozen:
            for td in tickers_data:
                sym = td.get('ticker')
                day_d = td.get('day', {})
                if sym and isinstance(day_d, dict) and day_d.get('c') and day_d['c'] > 0:
                    self._regular_close_cache[sym] = float(day_d['c'])
            self._regular_close_frozen = True
            logger.info("regular_close_frozen", tickers=len(self._regular_close_cache))
        elif session != MarketSession.POST_MARKET:
            if self._regular_close_frozen:
                self._regular_close_cache.clear()
                self._regular_close_frozen = False
                self._regular_volumes_cache.clear()
                self._regular_volumes_loaded = False

        # Pre-market high/low: track during pre-market, freeze at open
        if session == MarketSession.PRE_MARKET:
            self._premarket_frozen = False
            for td in tickers_data:
                sym = td.get('ticker')
                lt = td.get('lastTrade', {})
                p = lt.get('p') if isinstance(lt, dict) else None
                if sym and p and p > 0:
                    cur_h = self._premarket_highs.get(sym, 0)
                    cur_l = self._premarket_lows.get(sym, float('inf'))
                    if p > cur_h:
                        self._premarket_highs[sym] = p
                    if p < cur_l:
                        self._premarket_lows[sym] = p
        elif session == MarketSession.MARKET_OPEN and not self._premarket_frozen:
            self._premarket_frozen = True
        elif session == MarketSession.CLOSED:
            self._premarket_highs.clear()
            self._premarket_lows.clear()
            self._premarket_frozen = False
        
        # Load regular session volumes from scanner's PostMarketVolumeCapture (once per post-market)
        if session == MarketSession.POST_MARKET and not self._regular_volumes_loaded:
            await self._load_regular_volumes(now)
        
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
            changed, total_count, changed_count, _removed_symbols = self._change_detector.detect_changes(enriched_tickers)
        
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

        # Pre-market high/low
        pm_h = self._premarket_highs.get(symbol)
        pm_l = self._premarket_lows.get(symbol)
        ticker_data['premarket_high'] = pm_h
        ticker_data['premarket_low'] = pm_l
        price_now = ticker_data.get('lastTrade', {}).get('p') if isinstance(ticker_data.get('lastTrade'), dict) else None
        if price_now and pm_h:
            ticker_data['below_premarket_high'] = round(pm_h - price_now, 4)
        else:
            ticker_data['below_premarket_high'] = None
        if price_now and pm_l:
            ticker_data['above_premarket_low'] = round(price_now - pm_l, 4)
        else:
            ticker_data['above_premarket_low'] = None
        if pm_h and pm_l and pm_h != pm_l and price_now:
            ticker_data['pos_in_premarket_range'] = round((price_now - pm_l) / (pm_h - pm_l) * 100, 2)
        else:
            ticker_data['pos_in_premarket_range'] = None
        
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
                ticker_data['chg_2min'] = price_windows.chg_2min if hasattr(price_windows, 'chg_2min') else None
                ticker_data['chg_5min'] = price_windows.chg_5min
                ticker_data['chg_10min'] = price_windows.chg_10min
                ticker_data['chg_15min'] = price_windows.chg_15min
                ticker_data['chg_30min'] = price_windows.chg_30min
                ticker_data['chg_1min_dollars'] = price_windows.chg_1min_dollars
                ticker_data['chg_2min_dollars'] = price_windows.chg_2min_dollars
                ticker_data['chg_5min_dollars'] = price_windows.chg_5min_dollars
                ticker_data['chg_10min_dollars'] = price_windows.chg_10min_dollars
                ticker_data['chg_15min_dollars'] = price_windows.chg_15min_dollars
                ticker_data['chg_30min_dollars'] = price_windows.chg_30min_dollars
        
        if not has_per_second_chg:
            if self.bar_engine and self.bar_engine.has_data(symbol):
                # Fallback: AM.* per-minute data (covers 100% of market)
                ticker_data['chg_1min'] = self.bar_engine.get_price_change(symbol, 1)
                ticker_data['chg_2min'] = self.bar_engine.get_price_change(symbol, 2)
                ticker_data['chg_5min'] = self.bar_engine.get_price_change(symbol, 5)
                ticker_data['chg_10min'] = self.bar_engine.get_price_change(symbol, 10)
                ticker_data['chg_15min'] = self.bar_engine.get_price_change(symbol, 15)
                ticker_data['chg_30min'] = self.bar_engine.get_price_change(symbol, 30)
                ticker_data['chg_1min_dollars'] = self.bar_engine.get_price_change_dollars(symbol, 1)
                ticker_data['chg_2min_dollars'] = self.bar_engine.get_price_change_dollars(symbol, 2)
                ticker_data['chg_5min_dollars'] = self.bar_engine.get_price_change_dollars(symbol, 5)
                ticker_data['chg_10min_dollars'] = self.bar_engine.get_price_change_dollars(symbol, 10)
                ticker_data['chg_15min_dollars'] = self.bar_engine.get_price_change_dollars(symbol, 15)
                ticker_data['chg_30min_dollars'] = self.bar_engine.get_price_change_dollars(symbol, 30)
            else:
                ticker_data.setdefault('chg_1min', None)
                ticker_data.setdefault('chg_2min', None)
                ticker_data.setdefault('chg_5min', None)
                ticker_data.setdefault('chg_10min', None)
                ticker_data.setdefault('chg_15min', None)
                ticker_data.setdefault('chg_30min', None)
                ticker_data.setdefault('chg_1min_dollars', None)
                ticker_data.setdefault('chg_2min_dollars', None)
                ticker_data.setdefault('chg_5min_dollars', None)
                ticker_data.setdefault('chg_10min_dollars', None)
                ticker_data.setdefault('chg_15min_dollars', None)
                ticker_data.setdefault('chg_30min_dollars', None)
        
        # ================================================================
        # Price range windows: Range2..Range120 ($) and Range2P..Range120P (% of ATR)
        # Tradeul: range_Nmin = high - low in last N minutes
        #              range_Nmin_pct = (range_Nmin / ATR) * 100
        # ================================================================
        _range_windows = ('range_2min', 'range_5min', 'range_15min',
                          'range_30min', 'range_60min', 'range_120min')
        if self.price_window_tracker:
            pr = self.price_window_tracker.get_range_windows(symbol)
            _atr_for_range = ticker_data.get('atr')
            for _rkey, _rval in zip(_range_windows, pr):
                ticker_data[_rkey] = _rval
                _pct_key = _rkey + '_pct'
                if _rval is not None and _atr_for_range and _atr_for_range > 0:
                    ticker_data[_pct_key] = round(_rval / _atr_for_range * 100, 1)
                else:
                    ticker_data[_pct_key] = None
        else:
            for _rkey in _range_windows:
                ticker_data.setdefault(_rkey, None)
                ticker_data.setdefault(_rkey + '_pct', None)

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
                # SMA — Tradeul alignment (intraday from 1-min bars)
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
                ticker_data['chg_120min'] = indicators.chg_120m if hasattr(indicators, 'chg_120m') else self.bar_engine.get_price_change(symbol, 120)
                ticker_data['chg_60min_dollars'] = self.bar_engine.get_price_change_dollars(symbol, 60)
                ticker_data['chg_120min_dollars'] = self.bar_engine.get_price_change_dollars(symbol, 120)
                ticker_data['vol_60min'] = indicators.vol_60m
                ticker_data['consecutive_candles'] = self.bar_engine.get_consecutive_candles(symbol)

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

        # Ensure dollar change windows are always present in schema
        ticker_data.setdefault('chg_1min_dollars', None)
        ticker_data.setdefault('chg_2min_dollars', None)
        ticker_data.setdefault('chg_5min_dollars', None)
        ticker_data.setdefault('chg_10min_dollars', None)
        ticker_data.setdefault('chg_15min_dollars', None)
        ticker_data.setdefault('chg_30min_dollars', None)
        ticker_data.setdefault('chg_60min_dollars', None)
        ticker_data.setdefault('chg_120min_dollars', None)
        
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
        ticker_data['avg_volume_3m'] = daily.get('avg_volume_3m')
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
        # Directional indicators (+DI / -DI) for PDIMDI filter
        ticker_data['daily_plus_di_14'] = daily.get('daily_plus_di_14')
        ticker_data['daily_minus_di_14'] = daily.get('daily_minus_di_14')
        # Daily SMAs 5/8/10
        ticker_data['daily_sma_5'] = daily.get('daily_sma_5')
        ticker_data['daily_sma_8'] = daily.get('daily_sma_8')
        ticker_data['daily_sma_10'] = daily.get('daily_sma_10')
        # Distance from daily SMAs (%) — 5/8/10
        ticker_data['dist_daily_sma_5'] = daily.get('dist_daily_sma_5')
        ticker_data['dist_daily_sma_8'] = daily.get('dist_daily_sma_8')
        ticker_data['dist_daily_sma_10'] = daily.get('dist_daily_sma_10')
        # Multi-day high/low/range (from screener)
        ticker_data['high_5d'] = daily.get('high_5d')
        ticker_data['low_5d'] = daily.get('low_5d')
        ticker_data['range_5d'] = daily.get('range_5d')
        ticker_data['high_10d'] = daily.get('high_10d')
        ticker_data['low_10d'] = daily.get('low_10d')
        ticker_data['range_10d'] = daily.get('range_10d')
        ticker_data['high_20d'] = daily.get('high_20d')
        ticker_data['low_20d'] = daily.get('low_20d')
        ticker_data['range_20d'] = daily.get('range_20d')
        # Multi-day changes ($)
        ticker_data['change_5d_dollars'] = daily.get('change_5d_dollars')
        ticker_data['change_10d_dollars'] = daily.get('change_10d_dollars')
        ticker_data['change_20d_dollars'] = daily.get('change_20d_dollars')
        # 1-year change
        ticker_data['change_1y'] = daily.get('change_1y')
        ticker_data['change_1y_dollars'] = daily.get('change_1y_dollars')
        # YTD change
        ticker_data['change_ytd'] = daily.get('change_ytd')
        ticker_data['change_ytd_dollars'] = daily.get('change_ytd_dollars')
        # Yearly standard deviation
        ticker_data['yearly_std_dev'] = daily.get('yearly_std_dev')
        # Consecutive days up/down
        ticker_data['consecutive_days_up'] = daily.get('consecutive_days_up')
        # Multi-month / lifetime high/low (for pos_in_3m_range, etc.)
        ticker_data['high_3m'] = daily.get('high_3m')
        ticker_data['low_3m'] = daily.get('low_3m')
        ticker_data['high_6m'] = daily.get('high_6m')
        ticker_data['low_6m'] = daily.get('low_6m')
        ticker_data['high_9m'] = daily.get('high_9m')
        ticker_data['low_9m'] = daily.get('low_9m')
        ticker_data['high_2y'] = daily.get('high_2y')
        ticker_data['low_2y'] = daily.get('low_2y')
        ticker_data['high_all'] = daily.get('high_all')
        ticker_data['low_all'] = daily.get('low_all')
        # Consolidation / range contraction / LR divergence
        ticker_data['consolidation_days'] = daily.get('consolidation_days')
        ticker_data['consolidation_high'] = daily.get('consolidation_high')
        ticker_data['consolidation_low'] = daily.get('consolidation_low')
        ticker_data['range_contraction'] = daily.get('range_contraction')
        ticker_data['lr_divergence_130'] = daily.get('lr_divergence_130')
        
        # ================================================================
        # Additional derived fields (computed AFTER screener merge)
        # These need screener daily cache fields (high_5d, low_5d, etc.)
        # ================================================================
        price = ticker_data.get('lastTrade', {}).get('p') if isinstance(ticker_data.get('lastTrade'), dict) else None
        if not price:
            _day = ticker_data.get('day', {})
            price = _day.get('c') if isinstance(_day, dict) else None
        _day_data = ticker_data.get('day', {}) if isinstance(ticker_data.get('day'), dict) else {}

        # Position in multi-day ranges [R5D, R10D, R20D]
        for _period in ('5d', '10d', '20d'):
            _h_val = ticker_data.get(f'high_{_period}')
            _l_val = ticker_data.get(f'low_{_period}')
            _pos_key = f'pos_in_{_period}_range'
            if price and _h_val and _l_val and _h_val != _l_val:
                ticker_data[_pos_key] = round((price - _l_val) / (_h_val - _l_val) * 100, 2)
            else:
                ticker_data[_pos_key] = None

        # Position in 52-Week Range [R52W]
        _h52 = ticker_data.get('high_52w')
        _l52 = ticker_data.get('low_52w')
        if price and _h52 and _l52 and _h52 != _l52:
            ticker_data['pos_in_52w_range'] = round((price - _l52) / (_h52 - _l52) * 100, 2)
        else:
            ticker_data['pos_in_52w_range'] = None

        # Position in 3M/6M/9M/2Y/Lifetime Range [R3MO, R6MO, R9MO, R2Y, RL]
        for _rng_key, _pos_key in (
            ('3m', 'pos_in_3m_range'), ('6m', 'pos_in_6m_range'),
            ('9m', 'pos_in_9m_range'), ('2y', 'pos_in_2y_range'),
            ('all', 'pos_in_lifetime_range'),
        ):
            _h = ticker_data.get(f'high_{_rng_key}')
            _l = ticker_data.get(f'low_{_rng_key}')
            if price and _h and _l and _h != _l:
                ticker_data[_pos_key] = round((price - _l) / (_h - _l) * 100, 2)
            else:
                ticker_data[_pos_key] = None

        # Position in Consolidation [RCon] = position within the consolidation range
        # Tradeul: based on the high/low of the consolidation period (inside-day streak),
        # not today's intraday range. >100 = broken out above, <0 = broken down below.
        _con_days = ticker_data.get('consolidation_days')
        if _con_days and _con_days > 0 and price:
            _con_high = ticker_data.get('consolidation_high')
            _con_low = ticker_data.get('consolidation_low')
            if _con_high and _con_low and _con_high != _con_low:
                ticker_data['pos_in_consolidation'] = round((price - _con_low) / (_con_high - _con_low) * 100, 2)
            else:
                ticker_data['pos_in_consolidation'] = None
        else:
            ticker_data['pos_in_consolidation'] = None

        # Change Previous Day % [FCDP] = prev_close change vs 2-days-ago close
        _prev_close = ticker_data.get('prevDay', {}).get('c') if isinstance(ticker_data.get('prevDay'), dict) else None
        _change_1d = ticker_data.get('change_1d')
        ticker_data.setdefault('change_prev_day_pct', _change_1d)

        # Directional Indicator [PDIMDI] = +DI - -DI
        _plus_di = ticker_data.get('daily_plus_di_14')
        _minus_di = ticker_data.get('daily_minus_di_14')
        if _plus_di is not None and _minus_di is not None:
            ticker_data['plus_di_minus_di'] = round(_plus_di - _minus_di, 2)
        else:
            ticker_data['plus_di_minus_di'] = None

        # Distance from daily SMAs in $ [MA5P, MA8P, MA10P, MA20P, MA50P, MA200P]
        for _sma_key, _dist_key in (
            ('daily_sma_5', 'dist_daily_sma_5_dollars'),
            ('daily_sma_8', 'dist_daily_sma_8_dollars'),
            ('daily_sma_10', 'dist_daily_sma_10_dollars'),
            ('daily_sma_200', 'dist_daily_sma_200_dollars'),
            ('daily_sma_50', 'dist_daily_sma_50_dollars'),
            ('daily_sma_20', 'dist_daily_sma_20_dollars'),
        ):
            _sma_val = ticker_data.get(_sma_key)
            if price and _sma_val:
                ticker_data[_dist_key] = round(price - _sma_val, 4)
            else:
                ticker_data[_dist_key] = None

        # Distance from Daily SMAs (%) — real-time with current price
        # Tradeul [MA50P] formula: ((Last Price) - (SMA)) / (SMA) * 100
        for _sma_period in ('5', '8', '10', '20', '50', '200'):
            _sma_val = ticker_data.get(f'daily_sma_{_sma_period}')
            _dist_key = f'dist_daily_sma_{_sma_period}'
            if price and _sma_val and _sma_val > 0:
                ticker_data[_dist_key] = round((price - _sma_val) / _sma_val * 100, 2)
            else:
                ticker_data.setdefault(_dist_key, None)

        # Range % (ATR-normalized) [Range5DP, Range10DP, Range20DP]
        _atr = ticker_data.get('atr')
        for _period in ('5d', '10d', '20d'):
            _range_val = ticker_data.get(f'range_{_period}')
            _pct_key = f'range_{_period}_pct'
            if _range_val and _atr and _atr > 0:
                ticker_data[_pct_key] = round(_range_val / _atr * 100, 2)
            else:
                ticker_data[_pct_key] = None

        # Change from Open Weighted [FOW] = change_from_open_dollars / ATR
        _cfo_d = ticker_data.get('change_from_open_dollars')
        if _cfo_d is not None and _atr and _atr > 0:
            ticker_data['change_from_open_weighted'] = round(_cfo_d / _atr, 2)
        else:
            ticker_data['change_from_open_weighted'] = None

        # 20 vs 200 SMA cross per multi-TF [2Sma20a200, 5Sma20a200, 15Sma20a200, 60Sma20a200]
        for _tf in (2, 5, 15, 60):
            _s20 = ticker_data.get(f'sma_20_{_tf}m')
            _s200 = ticker_data.get(f'sma_200_{_tf}m')
            _cross_key = f'sma_20_vs_200_{_tf}m'
            if _s20 and _s200 and _s200 > 0:
                ticker_data[_cross_key] = round((_s20 - _s200) / _s200 * 100, 2)
            else:
                ticker_data[_cross_key] = None

        # Volume Today % = (volume / avg_volume_10d) * 100
        _day_vol = _day_data.get('v')
        _avg_vol_10d = ticker_data.get('avg_volume_10d')
        if _day_vol and _avg_vol_10d and _avg_vol_10d > 0:
            ticker_data['volume_today_pct'] = round((_day_vol / _avg_vol_10d) * 100, 1)
        else:
            ticker_data.setdefault('volume_today_pct', None)

        # Volume yesterday % = (prev_volume / avg_volume_10d) * 100
        _prev_vol = ticker_data.get('prev_day_volume')
        if _prev_vol and _avg_vol_10d and _avg_vol_10d > 0:
            ticker_data['volume_yesterday_pct'] = round((_prev_vol / _avg_vol_10d) * 100, 1)
        else:
            ticker_data.setdefault('volume_yesterday_pct', None)

        # Volume N-minute % = ((vol_Nmin / avg_volume_10d) * periods_per_day) * 100
        # periods_per_day = 390 / N  (390 = minutes in a 6.5h trading day)
        _WINDOW_PERIODS = {1: 390, 5: 78, 10: 39, 15: 26, 30: 13}
        for _win, _periods in _WINDOW_PERIODS.items():
            _vol_key = f'vol_{_win}min'
            _pct_key = f'vol_{_win}min_pct'
            _vol_win = ticker_data.get(_vol_key)
            if _vol_win and _avg_vol_10d and _avg_vol_10d > 0:
                ticker_data[_pct_key] = round((_vol_win / _avg_vol_10d) * _periods * 100, 1)
            else:
                ticker_data.setdefault(_pct_key, None)

        # Price from day high (%) = ((price - day.h) / day.h) * 100
        _day_high = _day_data.get('h')
        if price and _day_high and _day_high > 0:
            ticker_data['price_from_high'] = round((price - _day_high) / _day_high * 100, 2)
        else:
            ticker_data.setdefault('price_from_high', None)

        # Price from day low (%) = ((price - day.l) / day.l) * 100
        _day_low = _day_data.get('l')
        if price and _day_low and _day_low > 0:
            ticker_data['price_from_low'] = round((price - _day_low) / _day_low * 100, 2)
        else:
            ticker_data.setdefault('price_from_low', None)

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
        
        # ================================================================
        # Session-aware fields: premarket/postmarket change %, postmarket volume
        # ================================================================
        _prev_close = ticker_data.get('prevDay', {}).get('c') if isinstance(ticker_data.get('prevDay'), dict) else None
        _day_open = _day_data.get('o')
        _day_vol_total = _day_data.get('v')
        _session = getattr(self, '_current_session', None)

        # premarket_change_percent
        if _session == MarketSession.PRE_MARKET:
            if price and _prev_close and _prev_close > 0:
                ticker_data['premarket_change_percent'] = round((price - _prev_close) / _prev_close * 100, 2)
            else:
                ticker_data['premarket_change_percent'] = None
        elif _day_open and _prev_close and _prev_close > 0:
            ticker_data['premarket_change_percent'] = round((_day_open - _prev_close) / _prev_close * 100, 2)
        else:
            ticker_data.setdefault('premarket_change_percent', None)

        # postmarket_change_percent (uses frozen regular close to avoid Polygon drift)
        if _session == MarketSession.POST_MARKET:
            _sym = ticker_data.get('ticker', '')
            _reg_close = self._regular_close_cache.get(_sym)
            if _reg_close and price and _reg_close > 0:
                ticker_data['postmarket_change_percent'] = round((price - _reg_close) / _reg_close * 100, 2)
            else:
                ticker_data['postmarket_change_percent'] = None
        else:
            ticker_data['postmarket_change_percent'] = None

        # postmarket_volume = total volume today - regular session volume
        if _session == MarketSession.POST_MARKET:
            _sym = ticker_data.get('ticker', '')
            _reg_vol = self._regular_volumes_cache.get(_sym)
            if _reg_vol is not None and _day_vol_total is not None:
                ticker_data['postmarket_volume'] = max(0, int(_day_vol_total) - _reg_vol)
            else:
                ticker_data['postmarket_volume'] = None
        else:
            ticker_data['postmarket_volume'] = None

        # ================================================================
        # Dilution risk scores (from dilution:scores:latest, refreshed every 5 min)
        # Null for tickers not in the dilution tracker DB (e.g. AAPL, MSFT).
        # ================================================================
        dil = self._dilution_scores_cache.get(symbol, {})
        ticker_data['dilution_overall_risk'] = dil.get('overall_risk')
        ticker_data['dilution_overall_risk_score'] = dil.get('overall_risk_score')
        ticker_data['dilution_offering_ability'] = dil.get('offering_ability')
        ticker_data['dilution_offering_ability_score'] = dil.get('offering_ability_score')
        ticker_data['dilution_overhead_supply'] = dil.get('overhead_supply')
        ticker_data['dilution_overhead_supply_score'] = dil.get('overhead_supply_score')
        ticker_data['dilution_historical'] = dil.get('historical_dilution')
        ticker_data['dilution_historical_score'] = dil.get('historical_dilution_score')
        ticker_data['dilution_cash_need'] = dil.get('cash_need')
        ticker_data['dilution_cash_need_score'] = dil.get('cash_need_score')

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
        
        # Gap % (today's open vs prev close, pre-market fallback: use price as expected open)
        if day_open and prev_close and prev_close > 0:
            ticker_data['gap_percent'] = round((day_open - prev_close) / prev_close * 100, 2)
        elif price and prev_close and prev_close > 0 and not day_open:
            # Pre-market fallback: current price as expected open
            ticker_data['gap_percent'] = round((price - prev_close) / prev_close * 100, 2)
        else:
            ticker_data.setdefault('gap_percent', None)
        
        # Dollar volume = price * volume
        if price and price > 0 and volume > 0:
            ticker_data['dollar_volume'] = round(price * volume, 0)
        else:
            ticker_data['dollar_volume'] = None
        
        # Today's range: TRangeD = high - low ($), TRangeP = (range / ATR) * 100
        h = intraday_high or (day_high if day_high else None)
        l = intraday_low or (day_low if day_low else None)
        _atr_val = ticker_data.get('atr')
        if h and l and l > 0:
            _trange = round(h - l, 4)
            ticker_data['todays_range'] = _trange
            ticker_data['todays_range_pct'] = round(_trange / _atr_val * 100, 1) if _atr_val and _atr_val > 0 else None
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

        # Change from today's open (%) — Tradeul FOP
        if price and day_open and day_open > 0:
            ticker_data['change_from_open'] = round((price - day_open) / day_open * 100, 4)
        else:
            ticker_data['change_from_open'] = None

        # Change from today's open ($) — Tradeul FOD
        if price and day_open:
            ticker_data['change_from_open_dollars'] = round(price - day_open, 4)
        else:
            ticker_data['change_from_open_dollars'] = None

        # Price from intraday high (%) — includes pre/post market
        if price and intraday_high and intraday_high > 0:
            ticker_data['price_from_intraday_high'] = round((price - intraday_high) / intraday_high * 100, 2)
        else:
            ticker_data['price_from_intraday_high'] = None

        # Price from intraday low (%) — includes pre/post market
        if price and intraday_low and intraday_low > 0:
            ticker_data['price_from_intraday_low'] = round((price - intraday_low) / intraday_low * 100, 2)
        else:
            ticker_data['price_from_intraday_low'] = None

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

        self._compute_pivot_and_extra(ticker_data, price, prev_day, prev_close)
        self._compute_extended_derived(ticker_data, price, prev_day, prev_close, day_open, _atr_val)

    def _compute_extended_derived(self, ticker_data, price, prev_day, prev_close, day_open, atr_val):
        """Extended derived fields — Tradeul parity."""
        prev_high = prev_day.get('h') if isinstance(prev_day, dict) else None
        prev_low = prev_day.get('l') if isinstance(prev_day, dict) else None

        # Gap $ [GUD] = open - prev_close
        if day_open and prev_close:
            ticker_data['gap_dollars'] = round(day_open - prev_close, 4)
        else:
            ticker_data['gap_dollars'] = None

        # Gap Ratio [GUR] = gap$ / ATR
        gap_d = ticker_data.get('gap_dollars')
        if gap_d is not None and atr_val and atr_val > 0:
            ticker_data['gap_ratio'] = round(gap_d / atr_val, 2)
        else:
            ticker_data['gap_ratio'] = None

        # Change from Close $ [FCD]  (already have change_from_close)
        # Change from Close Ratio [FCR] = change_from_close / ATR
        cfc = ticker_data.get('change_from_close')
        if cfc is not None and atr_val and atr_val > 0:
            ticker_data['change_from_close_ratio'] = round(cfc / atr_val, 2)
        else:
            ticker_data['change_from_close_ratio'] = None

        # Change from Open Ratio [FOR] = change_from_open_dollars / ATR
        cfo_d = ticker_data.get('change_from_open_dollars')
        if cfo_d is not None and atr_val and atr_val > 0:
            ticker_data['change_from_open_ratio'] = round(cfo_d / atr_val, 2)
        else:
            ticker_data['change_from_open_ratio'] = None

        # Post-Market Change $ [PostD]
        post_pct = ticker_data.get('postmarket_change_percent')
        if post_pct is not None and prev_close and prev_close > 0:
            ticker_data['postmarket_change_dollars'] = round(prev_close * post_pct / 100, 4)
        else:
            ticker_data['postmarket_change_dollars'] = None

        # Decimal [Dec] — fractional part of price
        if price:
            ticker_data['decimal'] = round(price % 1, 4)
        else:
            ticker_data['decimal'] = None

        # Position in Previous Day Range [RPD]
        if price and prev_high and prev_low and prev_high != prev_low:
            ticker_data['pos_in_prev_day_range'] = round(
                (price - prev_low) / (prev_high - prev_low) * 100, 2)
        else:
            ticker_data['pos_in_prev_day_range'] = None

        # Spread (already exists as bid-ask spread, but ensure it's set)
        bid = ticker_data.get('bid')
        ask = ticker_data.get('ask')
        if bid and ask and bid > 0:
            ticker_data.setdefault('spread', round(ask - bid, 4))

        # Multi-TF SMA distances (% from price to SMA on each timeframe)
        for tf in (2, 5, 10, 15, 30, 60):
            suffix = f'_{tf}m'
            for sma_period in (5, 8, 10, 20, 130, 200):
                sma_key = f'sma_{sma_period}{suffix}'
                sma_val = ticker_data.get(sma_key)
                dist_key = f'dist_sma_{sma_period}{suffix}'
                if price and sma_val and sma_val > 0:
                    ticker_data[dist_key] = round((price - sma_val) / sma_val * 100, 2)
                else:
                    ticker_data[dist_key] = None

        # SMA cross: 8 vs 20 per timeframe
        for tf in (2, 5, 15, 60):
            suffix = f'_{tf}m'
            sma8 = ticker_data.get(f'sma_8{suffix}')
            sma20 = ticker_data.get(f'sma_20{suffix}')
            cross_key = f'sma_8_vs_20{suffix}'
            if sma8 and sma20 and sma20 > 0:
                ticker_data[cross_key] = round((sma8 - sma20) / sma20 * 100, 2)
            else:
                ticker_data[cross_key] = None

        # Bollinger position per multi-TF (5m, 15m, 60m already from bar_engine)
        for tf_suffix in ('_5m', '_15m', '_60m'):
            bb_u = ticker_data.get(f'bb_upper{tf_suffix}')
            bb_l = ticker_data.get(f'bb_lower{tf_suffix}')
            pos_key = f'bb_position{tf_suffix}'
            if bb_u and bb_l and bb_u != bb_l and price:
                ticker_data[pos_key] = round((price - bb_l) / (bb_u - bb_l) * 100, 2)
            else:
                ticker_data.setdefault(pos_key, None)

        # Standard Deviation [BB] from Bollinger Bands width
        bb_u_1m = ticker_data.get('bb_upper')
        bb_l_1m = ticker_data.get('bb_lower')
        if bb_u_1m and bb_l_1m and bb_u_1m > bb_l_1m:
            ticker_data['bb_std_dev'] = round((bb_u_1m - bb_l_1m) / 4, 4)
        else:
            ticker_data['bb_std_dev'] = None

        # Distance from intraday SMAs in $
        for sma_key in ('sma_5', 'sma_8', 'sma_20', 'sma_50', 'sma_200'):
            sma_val = ticker_data.get(sma_key)
            if price and sma_val:
                ticker_data[f'dist_{sma_key}_dollars'] = round(price - sma_val, 4)
            else:
                ticker_data[f'dist_{sma_key}_dollars'] = None

    def _compute_pivot_and_extra(self, ticker_data, price, prev_day, prev_close):
        """Pivot points, position-in-range (multi-TF), Bollinger position."""
        prev_high = prev_day.get('h') if isinstance(prev_day, dict) else None
        prev_low = prev_day.get('l') if isinstance(prev_day, dict) else None
        if prev_high and prev_low and prev_close and prev_high > 0:
            pv = (prev_high + prev_low + prev_close) / 3
            r1 = 2 * pv - prev_low
            s1 = 2 * pv - prev_high
            r2 = pv + (prev_high - prev_low)
            s2 = pv - (prev_high - prev_low)
            ticker_data['pivot'] = round(pv, 4)
            ticker_data['pivot_r1'] = round(r1, 4)
            ticker_data['pivot_s1'] = round(s1, 4)
            ticker_data['pivot_r2'] = round(r2, 4)
            ticker_data['pivot_s2'] = round(s2, 4)
            if price:
                ticker_data['dist_pivot'] = round((price - pv) / pv * 100, 2)
                ticker_data['dist_pivot_r1'] = round((price - r1) / r1 * 100, 2) if r1 else None
                ticker_data['dist_pivot_s1'] = round((price - s1) / s1 * 100, 2) if s1 else None
                ticker_data['dist_pivot_r2'] = round((price - r2) / r2 * 100, 2) if r2 else None
                ticker_data['dist_pivot_s2'] = round((price - s2) / s2 * 100, 2) if s2 else None
            else:
                for k in ('dist_pivot', 'dist_pivot_r1', 'dist_pivot_s1', 'dist_pivot_r2', 'dist_pivot_s2'):
                    ticker_data[k] = None
        else:
            for k in ('pivot', 'pivot_r1', 'pivot_s1', 'pivot_r2', 'pivot_s2',
                       'dist_pivot', 'dist_pivot_r1', 'dist_pivot_s1', 'dist_pivot_r2', 'dist_pivot_s2'):
                ticker_data[k] = None

        for suffix in ('5m', '15m', '30m', '60m'):
            tf_h = ticker_data.get(f'tf_high_{suffix}')
            tf_l = ticker_data.get(f'tf_low_{suffix}')
            if tf_h and tf_l and tf_h != tf_l and price:
                ticker_data[f'pos_in_range_{suffix}'] = round((price - tf_l) / (tf_h - tf_l) * 100, 2)
            else:
                ticker_data[f'pos_in_range_{suffix}'] = None

        bb_u = ticker_data.get('bb_upper')
        bb_l = ticker_data.get('bb_lower')
        if bb_u and bb_l and bb_u != bb_l and price:
            ticker_data['bb_position_1m'] = round((price - bb_l) / (bb_u - bb_l) * 100, 2)
        else:
            ticker_data['bb_position_1m'] = None

        # Minutes since NYSE market open (9:30 ET). Negative before open, >390 after close.
        # Same value for all tickers at any instant — used as a Time of Day filter [TOD].
        _now_et = datetime.now(ZoneInfo("America/New_York"))
        _market_open = _now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        ticker_data['minutes_since_open'] = round(
            (_now_et - _market_open).total_seconds() / 60, 2
        )

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
        - lastTrade.i/c: Trade ID (noisy) and conditions array (unused).
        - min.n/otc:  Transaction count and OTC flag, unused.
        - day.otc:    OTC flag, unused.
        - prevDay.h/l/vw: Static fields unused.
        """
        # Top-level volatile/unused fields
        ticker_data.pop('updated', None)
        ticker_data.pop('fmv', None)
        
        # lastTrade: keep .p (price), .t (timestamp), .s (trade size), .x (exchange)
        # .s needed by alert_engine for block trade detection
        # .x needed by alert_engine for exchange-specific alerts (TRAS/TRBS)
        last_trade = ticker_data.get('lastTrade')
        if isinstance(last_trade, dict):
            last_trade.pop('i', None)   # trade ID - unique per trade, noisy
            last_trade.pop('c', None)   # conditions array - unused
        
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
        
        # prevDay: keep .c (prev_close), .v (prev_volume), .o (prev_open), .h, .l
        # .h/.l needed for pivot point calculations
        prev_day = ticker_data.get('prevDay')
        if isinstance(prev_day, dict):
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
        
        Guards against overwriting valid last_close data with
        a nearly-empty snapshot (e.g. after a late restart).
        """
        MIN_TICKERS_FOR_VALID_SNAPSHOT = 500
        
        try:
            all_data = await self.redis.client.hgetall(SNAPSHOT_ENRICHED_HASH)
            
            if not all_data:
                logger.warning("no_enriched_data_for_last_close")
                return
            
            ticker_count = sum(
                1 for k in all_data
                if (k if isinstance(k, str) else k.decode("utf-8", errors="ignore")) != "__meta__"
            )
            
            if ticker_count < MIN_TICKERS_FOR_VALID_SNAPSHOT:
                existing_count = await self.redis.client.hlen(SNAPSHOT_LAST_CLOSE_HASH)
                if existing_count > ticker_count:
                    logger.warning(
                        "skipping_last_close_write_insufficient_data",
                        current_tickers=ticker_count,
                        existing_last_close_fields=existing_count,
                        min_required=MIN_TICKERS_FOR_VALID_SNAPSHOT,
                    )
                    return
            
            pipe = self.redis.client.pipeline()
            pipe.delete(SNAPSHOT_LAST_CLOSE_HASH)
            pipe.hset(SNAPSHOT_LAST_CLOSE_HASH, mapping=all_data)
            pipe.expire(SNAPSHOT_LAST_CLOSE_HASH, SNAPSHOT_LAST_CLOSE_TTL)
            await pipe.execute()
            
            logger.info(
                "last_close_snapshot_saved",
                ticker_count=ticker_count,
                ttl_days=SNAPSHOT_LAST_CLOSE_TTL // 86400,
            )
        except Exception as e:
            logger.error("error_writing_last_close", error=str(e))
    
    async def _load_regular_volumes(self, now: datetime) -> None:
        """
        Load regular-session volumes captured by scanner's PostMarketVolumeCapture.
        Keys: scanner:postmarket:regular_vol:{YYYYMMDD}:{SYMBOL}
        Called once when entering post-market session.
        """
        try:
            date_str = now.strftime("%Y%m%d")
            pattern = f"scanner:postmarket:regular_vol:{date_str}:*"
            cursor = b"0"
            count = 0
            while True:
                cursor, keys = await self.redis.client.scan(cursor=cursor, match=pattern, count=500)
                if keys:
                    values = await self.redis.client.mget(*keys)
                    for key, val in zip(keys, values):
                        if val is None:
                            continue
                        key_str = key.decode() if isinstance(key, bytes) else key
                        symbol = key_str.rsplit(":", 1)[-1]
                        try:
                            self._regular_volumes_cache[symbol] = int(float(val))
                            count += 1
                        except (ValueError, TypeError):
                            pass
                if cursor == b"0" or cursor == 0:
                    break
            self._regular_volumes_loaded = True
            logger.info("regular_volumes_loaded", count=count, date=date_str)
        except Exception as e:
            logger.error("regular_volumes_load_error", error=str(e))
    
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

        if now - self._dilution_scores_last_refresh > self._DILUTION_SCORES_REFRESH_INTERVAL:
            await self._refresh_dilution_scores_cache()
            self._dilution_scores_last_refresh = now
    
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
                    "avg_volume_3m": sf(ind.get("avg_volume_63")),
                    # Daily SMAs (5/8/10)
                    "daily_sma_5": sf(ind.get("sma_5")),
                    "daily_sma_8": sf(ind.get("sma_8")),
                    "daily_sma_10": sf(ind.get("sma_10")),
                    # Distance from daily SMAs (%)
                    "dist_daily_sma_5": sf(ind.get("dist_sma_5")),
                    "dist_daily_sma_8": sf(ind.get("dist_sma_8")),
                    "dist_daily_sma_10": sf(ind.get("dist_sma_10")),
                    "dist_daily_sma_20": sf(ind.get("dist_sma_20")),
                    "dist_daily_sma_50": sf(ind.get("dist_sma_50")),
                    "dist_daily_sma_200": sf(ind.get("dist_sma_200")),
                    # Directional indicators (+DI / -DI)
                    "daily_plus_di_14": sf(ind.get("plus_di_14")),
                    "daily_minus_di_14": sf(ind.get("minus_di_14")),
                    # Multi-day high/low/range
                    "high_5d": sf(ind.get("high_5d")),
                    "low_5d": sf(ind.get("low_5d")),
                    "range_5d": sf(ind.get("range_5d")),
                    "high_10d": sf(ind.get("high_10d")),
                    "low_10d": sf(ind.get("low_10d")),
                    "range_10d": sf(ind.get("range_10d")),
                    "high_20d": sf(ind.get("high_20d")),
                    "low_20d": sf(ind.get("low_20d")),
                    "range_20d": sf(ind.get("range_20d")),
                    # Multi-day changes ($)
                    "change_5d_dollars": sf(ind.get("change_5d_dollars")),
                    "change_10d_dollars": sf(ind.get("change_10d_dollars")),
                    "change_20d_dollars": sf(ind.get("change_20d_dollars")),
                    # 1-year change
                    "change_1y": sf(ind.get("change_1y")),
                    "change_1y_dollars": sf(ind.get("change_1y_dollars")),
                    # YTD change
                    "change_ytd": sf(ind.get("change_ytd")),
                    "change_ytd_dollars": sf(ind.get("change_ytd_dollars")),
                    # Yearly standard deviation
                    "yearly_std_dev": sf(ind.get("yearly_std_dev")),
                    # Consecutive days up/down
                    "consecutive_days_up": sf(ind.get("consecutive_days_up")),
                    # Position in range: high/low for 3M/6M/9M/2Y/lifetime
                    "high_3m": sf(ind.get("high_3m")),
                    "low_3m": sf(ind.get("low_3m")),
                    "high_6m": sf(ind.get("high_6m")),
                    "low_6m": sf(ind.get("low_6m")),
                    "high_9m": sf(ind.get("high_9m")),
                    "low_9m": sf(ind.get("low_9m")),
                    "high_2y": sf(ind.get("high_2y")),
                    "low_2y": sf(ind.get("low_2y")),
                    "high_all": sf(ind.get("high_all")),
                    "low_all": sf(ind.get("low_all")),
                    # Consolidation / Range Contraction / Linear Regression
                    "consolidation_days": sf(ind.get("consolidation_days")),
                    "consolidation_high": sf(ind.get("consolidation_high")),
                    "consolidation_low": sf(ind.get("consolidation_low")),
                    "range_contraction": sf(ind.get("range_contraction")),
                    "lr_divergence_130": sf(ind.get("lr_divergence_130")),
                }
            
            self._screener_daily_cache = new_cache
            logger.info("screener_daily_cache_refreshed", tickers=len(new_cache))
        except Exception as e:
            logger.error("screener_daily_cache_refresh_error", error=str(e))
    
    async def _refresh_dilution_scores_cache(self) -> None:
        """
        Load dilution risk scores from dilution:scores:latest Redis hash into memory.
        Refreshed every 5 minutes (same cadence as screener daily cache).
        Tickers absent from the hash will have dilution_* fields as None.
        """
        try:
            raw = await self.redis.client.hgetall("dilution:scores:latest")
            if not raw:
                logger.debug("dilution_scores_cache_empty")
                return

            new_cache: Dict[str, dict] = {}
            for ticker_bytes, payload_bytes in raw.items():
                try:
                    ticker = ticker_bytes.decode() if isinstance(ticker_bytes, bytes) else ticker_bytes
                    payload = orjson.loads(payload_bytes)
                    new_cache[ticker] = payload
                except Exception:
                    continue

            self._dilution_scores_cache = new_cache
            logger.debug("dilution_scores_cache_refreshed", tickers=len(new_cache))
        except Exception as e:
            logger.error("dilution_scores_cache_refresh_error", error=str(e))

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
