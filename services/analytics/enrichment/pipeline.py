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
import orjson
from datetime import datetime, date
from typing import Dict, Optional, Any
from zoneinfo import ZoneInfo

from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from shared.events import EventBus, EventType, Event

from .change_detector import ChangeDetector

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
    """
    
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
        
        # Change detection
        self._change_detector = ChangeDetector()
        
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
        
        # Volume windows (from WebSocket-fed tracker)
        if self.volume_window_tracker:
            vol_windows = self.volume_window_tracker.get_all_windows(symbol)
            ticker_data['vol_1min'] = vol_windows.vol_1min
            ticker_data['vol_5min'] = vol_windows.vol_5min
            ticker_data['vol_10min'] = vol_windows.vol_10min
            ticker_data['vol_15min'] = vol_windows.vol_15min
            ticker_data['vol_30min'] = vol_windows.vol_30min
        
        # Price change windows (from WebSocket-fed tracker)
        if self.price_window_tracker:
            price_windows = self.price_window_tracker.get_all_windows(symbol)
            ticker_data['chg_1min'] = price_windows.chg_1min
            ticker_data['chg_5min'] = price_windows.chg_5min
            ticker_data['chg_10min'] = price_windows.chg_10min
            ticker_data['chg_15min'] = price_windows.chg_15min
            ticker_data['chg_30min'] = price_windows.chg_30min
        
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
        
        return ticker_data
    
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
    
    def get_stats(self) -> dict:
        """Get pipeline statistics."""
        return {
            "cycle_count": self._cycle_count,
            "last_processed_timestamp": self._last_processed_timestamp,
            "is_holiday_mode": self._is_holiday_mode,
            "change_detector": self._change_detector.get_stats()
        }
