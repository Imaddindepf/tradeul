"""
Bar Engine - In-memory minute bar processing with streaming indicators.

Core component that:
1. Receives 1-minute bars from AM.* WebSocket (via MinuteBarConsumer)
2. Maintains per-symbol state: ring buffers (deques) + talipp indicator instances
3. Detects minute close (new `s` timestamp) and triggers indicator updates
4. Provides computed indicators to EnrichmentPipeline

Architecture:
    stream:market:minutes → MinuteBarConsumer → BarEngine.on_bar()
        → on_bar_close() triggers:
            - ring buffer append (closes, volumes, acc_volumes)
            - talipp indicator updates (RSI, EMA, MACD, BB, ATR, ADX, Stoch)
            - periodic purge of old indicator output history
            - multi-timeframe builders (5m, 15m)
            - intraday high/low tracking
        → EnrichmentPipeline reads via get_indicators(symbol)

Memory management:
    talipp indicators store their entire output history by default. With 15K+
    symbols, this grows unbounded and causes OOM. We use purge_oldest() to keep
    only the last TALIPP_MAX_OUTPUT_LENGTH values per indicator. The internal
    calculation state (EMA smoothing, RSI avg gain/loss, etc.) is preserved,
    so incremental O(1) computation remains correct.

    Verified: keep >= 50 produces results identical to never-purged indicators.
    We use 60 (matching the ring buffer) for safety margin.

    Memory with purge:  ~156 KB/symbol × 15K = ~2.3 GB (bounded)
    Memory without:     grows ~2.7 KB/symbol/minute → OOM in hours

CPU:    ~100-200ms per minute burst (15K symbols)

Design for sharding:
    - All state is per-symbol, no cross-symbol dependencies
    - Dict can be split by hash(symbol) % N for N workers
    - BarEngine code does NOT change when sharding
"""

import time
import resource
from collections import deque
from typing import Dict, Optional, Any, List, NamedTuple
from dataclasses import dataclass, field

from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Lazy import talipp - fail fast at init, not at import
_talipp_available = False
try:
    from talipp.indicators import RSI, EMA, SMA, MACD, BB, ATR, ADX, Stoch
    from talipp.ohlcv import OHLCV
    _talipp_available = True
except ImportError:
    logger.warning("talipp_not_installed", hint="pip install talipp")


# ============================================================================
# Data structures
# ============================================================================

class BarData(NamedTuple):
    """Normalized minute bar data."""
    sym: str
    s: int      # start timestamp (ms)
    e: int      # end timestamp (ms)
    o: float    # open
    h: float    # high
    l: float    # low
    c: float    # close
    v: int      # volume this bar
    av: int     # accumulated volume today
    vw: float   # VWAP this bar


class IndicatorValues(NamedTuple):
    """Snapshot of all indicator values for a symbol."""
    # Price windows (from ring buffers)
    chg_1m: Optional[float]
    chg_2m: Optional[float]
    chg_5m: Optional[float]
    chg_10m: Optional[float]
    chg_15m: Optional[float]
    chg_30m: Optional[float]
    chg_60m: Optional[float]
    # Volume windows (from ring buffers)
    vol_1m: Optional[int]
    vol_5m: Optional[int]
    vol_10m: Optional[int]
    vol_15m: Optional[int]
    vol_30m: Optional[int]
    vol_60m: Optional[int]
    # Streaming indicators (from talipp)
    rsi_14: Optional[float]
    ema_9: Optional[float]
    ema_20: Optional[float]
    ema_50: Optional[float]
    # SMA — aligned with Trade Ideas (intraday from 1-min bars)
    sma_5: Optional[float]
    sma_8: Optional[float]
    sma_20: Optional[float]
    sma_50: Optional[float]
    sma_200: Optional[float]
    macd_line: Optional[float]
    macd_signal: Optional[float]
    macd_hist: Optional[float]
    bb_upper: Optional[float]
    bb_mid: Optional[float]
    bb_lower: Optional[float]
    atr_14: Optional[float]
    adx_14: Optional[float]
    stoch_k: Optional[float]
    stoch_d: Optional[float]
    # Intraday extremes
    bar_high_intraday: Optional[float]
    bar_low_intraday: Optional[float]
    # Bar count (for warmup tracking)
    bar_count: int
    # Multi-timeframe indicators: {period_minutes: {indicator_name: value}}
    tf: Optional[dict] = None


# ============================================================================
# Per-symbol state
# ============================================================================

# Ring buffer size: 210 bars ≈ 3.5 hours of 1-minute bars.
# Must be >= 201 to support SMA(200) warmup in _calc_change and ring-based lookbacks.
# chg_60min needs 61 bars, SMA(200) needs 200 bars for first valid output.
DEFAULT_RING_SIZE = 210

# Maximum number of output values to retain in each talipp indicator.
# talipp stores every computed value in a list that grows without limit.
# With 15K+ symbols × 9 indicators × 390 bars/day, this causes OOM.
#
# purge_oldest() trims old OUTPUT values but preserves internal state,
# so incremental computation stays correct. Verified: keep >= 50 yields
# results identical to never-purged indicators across all 9 indicator types
# (RSI, EMA, MACD, BB, ATR, ADX, Stoch) over 800-bar simulations.
#
# Matches DEFAULT_RING_SIZE for architectural consistency.
TALIPP_MAX_OUTPUT_LENGTH = 210

# How often (in bar closes) to run the purge. Purging every single bar
# adds unnecessary overhead; batching amortizes the cost.
TALIPP_PURGE_INTERVAL = 50


# Attribute names of all talipp indicators on TickerBarState.
# Used by _purge_indicators() and get_stats() to iterate generically.
_TALIPP_ATTRS = ('rsi_14', 'ema_9', 'ema_20', 'ema_50',
                 'sma_5', 'sma_8', 'sma_20', 'sma_50', 'sma_200',
                 'macd', 'bb_20', 'atr_14', 'adx_14', 'stoch')

# ============================================================================
# Multi-timeframe configuration
# ============================================================================

# Clock-aligned timeframe periods (minutes)
MULTI_TIMEFRAMES = (2, 5, 10, 15, 30, 60)

# Per-timeframe indicator config — only allocate what the alert catalog needs.
# This keeps memory bounded: ~1.5 GB for 15K symbols across all 6 timeframes.
_TF_INDICATOR_CONFIG = {
    2:  {'sma_periods': (5, 8, 20), 'macd': False, 'stoch': False},
    5:  {'sma_periods': (5, 8, 20), 'macd': True,  'stoch': True},
    10: {'sma_periods': (5, 8, 20), 'macd': True,  'stoch': False},
    15: {'sma_periods': (5, 8, 20), 'macd': True,  'stoch': True},
    30: {'sma_periods': (5, 8, 20), 'macd': True,  'stoch': False},
    60: {'sma_periods': (),          'macd': True,  'stoch': True},
}

# talipp attribute names on TimeframeState (for purging)
_TF_TALIPP_ATTRS = ('sma_5', 'sma_8', 'sma_20', 'macd', 'stoch')


class TimeframeState:
    """
    Per-symbol, per-timeframe state for multi-TF bar aggregation.

    Clock-aligned: bars are grouped by floor(timestamp / period).
    When the group changes, the previous bar is closed and indicators updated.

    Memory per instance: ~7-22 KB depending on indicator config.
    Total: 15K symbols × 6 TFs × avg 16 KB ≈ 1.4 GB (bounded via purge).
    """
    __slots__ = (
        'period', 'builder', 'bar_count',
        'current_group',       # clock-aligned group ID (for detecting bar boundaries)
        'sma_5', 'sma_8', 'sma_20',
        'macd', 'stoch',
        'tf_high', 'tf_low',  # intraday extremes for this timeframe
    )

    def __init__(self, period: int):
        self.period = period
        self.builder: list = []
        self.bar_count: int = 0
        self.current_group: int = 0

        # Intraday extremes for this timeframe's bars
        self.tf_high: float = 0.0
        self.tf_low: float = float('inf')

        cfg = _TF_INDICATOR_CONFIG.get(period, {})
        sma_periods = cfg.get('sma_periods', ())

        if _talipp_available:
            self.sma_5 = SMA(period=5) if 5 in sma_periods else None
            self.sma_8 = SMA(period=8) if 8 in sma_periods else None
            self.sma_20 = SMA(period=20) if 20 in sma_periods else None
            self.macd = MACD(fast_period=12, slow_period=26, signal_period=9) if cfg.get('macd') else None
            self.stoch = Stoch(period=14, smoothing_period=3) if cfg.get('stoch') else None
        else:
            self.sma_5 = None
            self.sma_8 = None
            self.sma_20 = None
            self.macd = None
            self.stoch = None


class TickerBarState:
    """
    Per-symbol state maintained by the BarEngine.

    Uses __slots__ to minimize memory footprint across 11K+ instances.
    Each instance holds ring buffers (deques) and talipp indicator objects.

    Memory estimate per instance (with purge to 60):
        - deques (5 × 60 entries): ~6 KB
        - talipp (9 indicators, max 60 outputs): ~156 KB
        - total: ~162 KB
        - 15K symbols: ~2.3 GB (bounded, does not grow)
    """
    __slots__ = (
        'closes', 'volumes', 'acc_volumes', 'highs', 'lows',
        'high_intraday', 'low_intraday',
        'current_s', 'current_bar', 'bar_count',
        'last_close',
        'rsi_14', 'ema_9', 'ema_20', 'ema_50',
        'sma_5', 'sma_8', 'sma_20', 'sma_50', 'sma_200',
        'macd', 'bb_20', 'atr_14', 'adx_14', 'stoch',
        'tf_states',  # Dict[int, TimeframeState] — multi-TF aggregation
    )

    def __init__(self, ring_size: int = DEFAULT_RING_SIZE):
        # Ring buffers
        self.closes: deque = deque(maxlen=ring_size)
        self.volumes: deque = deque(maxlen=ring_size)
        self.acc_volumes: deque = deque(maxlen=ring_size)
        self.highs: deque = deque(maxlen=ring_size)
        self.lows: deque = deque(maxlen=ring_size)

        # Intraday extremes
        self.high_intraday: float = 0.0
        self.low_intraday: float = float('inf')

        # Minute close detection
        self.current_s: int = 0       # start timestamp of current bar
        self.current_bar: Optional[BarData] = None
        self.bar_count: int = 0
        self.last_close: float = 0.0

        # talipp indicator instances (O(1) incremental)
        if _talipp_available:
            self.rsi_14 = RSI(period=14)
            self.ema_9 = EMA(period=9)
            self.ema_20 = EMA(period=20)
            self.ema_50 = EMA(period=50)
            # SMA for intraday (Trade Ideas alignment)
            self.sma_5 = SMA(period=5)
            self.sma_8 = SMA(period=8)
            self.sma_20 = SMA(period=20)
            self.sma_50 = SMA(period=50)
            self.sma_200 = SMA(period=200)
            self.macd = MACD(fast_period=12, slow_period=26, signal_period=9)
            self.bb_20 = BB(period=20, std_dev_mult=2.0)
            self.atr_14 = ATR(period=14)
            self.adx_14 = ADX(di_period=14, adx_period=14)
            self.stoch = Stoch(period=14, smoothing_period=3)
        else:
            self.rsi_14 = None
            self.ema_9 = None
            self.ema_20 = None
            self.ema_50 = None
            self.sma_5 = None
            self.sma_8 = None
            self.sma_20 = None
            self.sma_50 = None
            self.sma_200 = None
            self.macd = None
            self.bb_20 = None
            self.atr_14 = None
            self.adx_14 = None
            self.stoch = None

        # Multi-timeframe states (clock-aligned bar aggregation + indicators)
        self.tf_states: dict = {tf: TimeframeState(tf) for tf in MULTI_TIMEFRAMES}


# ============================================================================
# Bar Engine
# ============================================================================

class BarEngine:
    """
    In-memory engine for processing minute bars and computing indicators.

    Thread-safety: designed for single-threaded asyncio. No locks needed.
    Sharding: state is per-symbol. Split self._states by key for N workers.
    """

    def __init__(self, ring_size: int = DEFAULT_RING_SIZE):
        self._ring_size = ring_size
        self._states: Dict[str, TickerBarState] = {}
        self._bars_closed_buffer: List[dict] = []  # for TimescaleDB persistence

        # Metrics
        self._total_bars_received = 0
        self._total_bars_closed = 0
        self._last_batch_time_ms = 0.0
        self._last_batch_size = 0
        self._batch_times: deque = deque(maxlen=100)  # last 100 batch times

        logger.info(
            "bar_engine_initialized",
            ring_size=ring_size,
            talipp_available=_talipp_available,
        )

    @property
    def symbol_count(self) -> int:
        return len(self._states)

    @property
    def closed_bars_buffer(self) -> List[dict]:
        """Access closed bars buffer for TimescaleDB writer."""
        return self._bars_closed_buffer

    def drain_closed_bars(self) -> List[dict]:
        """Take all closed bars from buffer (for TimescaleDB batch write)."""
        bars = self._bars_closed_buffer
        self._bars_closed_buffer = []
        return bars

    def _get_or_create_state(self, symbol: str) -> TickerBarState:
        """Get existing state or create new one for a symbol."""
        state = self._states.get(symbol)
        if state is None:
            state = TickerBarState(self._ring_size)
            self._states[symbol] = state
        return state

    # ========================================================================
    # Core: process incoming bar
    # ========================================================================

    def on_bar(self, bar: BarData) -> bool:
        """
        Process an incoming minute bar message.

        Handles intra-minute updates (same `s`) and minute closes (new `s`).

        Returns True if a bar was closed (indicators updated).
        """
        self._total_bars_received += 1
        state = self._get_or_create_state(bar.sym)

        if state.current_s == 0:
            # First bar ever for this symbol
            state.current_s = bar.s
            state.current_bar = bar
            return False

        if bar.s == state.current_s:
            # Intra-minute update: replace with latest data
            state.current_bar = bar
            return False

        if bar.s > state.current_s:
            # NEW minute detected → close the previous bar
            self._close_bar(bar.sym, state, state.current_bar)

            # Start tracking the new bar
            state.current_s = bar.s
            state.current_bar = bar
            return True

        # bar.s < state.current_s → late/out-of-order bar, ignore
        return False

    def process_batch(self, bars: List[BarData]) -> int:
        """
        Process a batch of bars (from stream consumer).

        Returns number of bars closed.
        """
        t_start = time.perf_counter()
        closed = 0

        for bar in bars:
            if self.on_bar(bar):
                closed += 1

        elapsed_ms = (time.perf_counter() - t_start) * 1000
        self._last_batch_time_ms = elapsed_ms
        self._last_batch_size = len(bars)
        self._batch_times.append(elapsed_ms)

        if len(bars) > 0:
            logger.info(
                "bar_engine_batch_processed",
                bars=len(bars),
                closed=closed,
                elapsed_ms=round(elapsed_ms, 1),
                symbols=self.symbol_count,
            )

        return closed

    # ========================================================================
    # Bar close: update ring buffers + indicators
    # ========================================================================

    def _close_bar(self, symbol: str, state: TickerBarState, bar: BarData) -> None:
        """
        Close a minute bar and update all state.

        This is the hot path - called once per symbol per minute.
        Everything here must be O(1).
        """
        if bar is None:
            return

        self._total_bars_closed += 1
        state.bar_count += 1
        state.last_close = bar.c

        # ---- Ring buffers ----
        state.closes.append(bar.c)
        state.volumes.append(bar.v)
        state.acc_volumes.append(bar.av)
        state.highs.append(bar.h)
        state.lows.append(bar.l)

        # ---- Intraday extremes ----
        if bar.h > state.high_intraday:
            state.high_intraday = bar.h
        if bar.l < state.low_intraday:
            state.low_intraday = bar.l

        # ---- talipp indicators (O(1) each) ----
        if _talipp_available:
            ohlcv = OHLCV(bar.o, bar.h, bar.l, bar.c, bar.v)

            # Price-based indicators
            state.rsi_14.add(bar.c)
            state.ema_9.add(bar.c)
            state.ema_20.add(bar.c)
            state.ema_50.add(bar.c)
            state.sma_5.add(bar.c)
            state.sma_8.add(bar.c)
            state.sma_20.add(bar.c)
            state.sma_50.add(bar.c)
            state.sma_200.add(bar.c)
            state.macd.add(bar.c)
            state.bb_20.add(bar.c)

            # OHLCV-based indicators
            state.atr_14.add(ohlcv)
            state.adx_14.add(ohlcv)
            state.stoch.add(ohlcv)

            # ---- Purge old indicator outputs (memory management) ----
            # talipp keeps the full history of computed values. Without
            # purging, 15K symbols × 9 indicators × 390 bars/day → OOM.
            # purge_oldest(n) removes n oldest OUTPUT values but preserves
            # internal calculation state, so next add() stays correct.
            if state.bar_count % TALIPP_PURGE_INTERVAL == 0:
                self._purge_indicators(state)

        # ---- Multi-timeframe aggregation (clock-aligned) ----
        bar_dict = {'o': bar.o, 'h': bar.h, 'l': bar.l, 'c': bar.c, 'v': bar.v}
        bar_group_base = bar.s // 60000  # minutes since epoch

        for tf_state in state.tf_states.values():
            group = bar_group_base // tf_state.period
            # Detect TF bar boundary (group changed)
            if tf_state.current_group != 0 and group != tf_state.current_group and tf_state.builder:
                self._close_tf_bar(tf_state)
            tf_state.current_group = group
            tf_state.builder.append(bar_dict)

        # ---- Persistence buffer (for TimescaleDB async write) ----
        self._bars_closed_buffer.append({
            'symbol': symbol,
            'ts': bar.s,
            'open': bar.o,
            'high': bar.h,
            'low': bar.l,
            'close': bar.c,
            'volume': bar.v,
        })

    # ========================================================================
    # Multi-timeframe bar close
    # ========================================================================

    @staticmethod
    def _close_tf_bar(tf_state: TimeframeState) -> None:
        """
        Close a multi-timeframe bar by aggregating accumulated 1-min bars.
        Updates timeframe-specific indicators (SMA, MACD, Stoch).
        """
        bars = tf_state.builder
        if not bars:
            return

        # Aggregate OHLCV from constituent 1-min bars
        o = bars[0]['o']
        h = max(b['h'] for b in bars)
        l_val = min(b['l'] for b in bars)
        c = bars[-1]['c']
        v = sum(b['v'] for b in bars)

        tf_state.bar_count += 1

        # Track intraday extremes for this timeframe
        if h > tf_state.tf_high:
            tf_state.tf_high = h
        if l_val < tf_state.tf_low:
            tf_state.tf_low = l_val

        # Update indicators
        if _talipp_available:
            # SMA indicators (close-based)
            for sma_attr in ('sma_5', 'sma_8', 'sma_20'):
                ind = getattr(tf_state, sma_attr, None)
                if ind is not None:
                    ind.add(c)

            # MACD (close-based)
            if tf_state.macd is not None:
                tf_state.macd.add(c)

            # Stochastic (OHLCV-based)
            if tf_state.stoch is not None:
                ohlcv = OHLCV(o, h, l_val, c, v)
                tf_state.stoch.add(ohlcv)

            # Purge periodically (same cadence as 1m indicators)
            if tf_state.bar_count % TALIPP_PURGE_INTERVAL == 0:
                for attr in _TF_TALIPP_ATTRS:
                    ind = getattr(tf_state, attr, None)
                    if ind is not None:
                        excess = len(ind) - TALIPP_MAX_OUTPUT_LENGTH
                        if excess > 0:
                            ind.purge_oldest(excess)

        # Clear builder for next TF bar
        tf_state.builder.clear()

    # ========================================================================
    # Read: get computed indicators for a symbol
    # ========================================================================

    def has_data(self, symbol: str) -> bool:
        """Check if we have any bar data for a symbol."""
        state = self._states.get(symbol)
        return state is not None and state.bar_count > 0

    def get_indicators(self, symbol: str) -> Optional[IndicatorValues]:
        """
        Get all computed indicator values for a symbol.

        Returns None if no data available.
        Called by EnrichmentPipeline during its enrichment cycle.
        """
        state = self._states.get(symbol)
        if state is None or state.bar_count == 0:
            return None

        # ---- Price change windows (from closes ring buffer) ----
        chg_1m = self._calc_change(state.closes, 1)
        chg_2m = self._calc_change(state.closes, 2)
        chg_5m = self._calc_change(state.closes, 5)
        chg_10m = self._calc_change(state.closes, 10)
        chg_15m = self._calc_change(state.closes, 15)
        chg_30m = self._calc_change(state.closes, 30)
        chg_60m = self._calc_change(state.closes, 60)

        # ---- Volume windows (from volumes ring buffer) ----
        vol_1m = self._calc_volume(state.volumes, 1)
        vol_5m = self._calc_volume(state.volumes, 5)
        vol_10m = self._calc_volume(state.volumes, 10)
        vol_15m = self._calc_volume(state.volumes, 15)
        vol_30m = self._calc_volume(state.volumes, 30)
        vol_60m = self._calc_volume(state.volumes, 60)

        # ---- talipp indicators ----
        rsi_14 = self._read_talipp(state.rsi_14)
        ema_9 = self._read_talipp(state.ema_9)
        ema_20 = self._read_talipp(state.ema_20)
        ema_50 = self._read_talipp(state.ema_50)

        # SMA (intraday, from 1-min bars — Trade Ideas alignment)
        sma_5 = self._read_talipp(state.sma_5)
        sma_8 = self._read_talipp(state.sma_8)
        sma_20 = self._read_talipp(state.sma_20)
        sma_50 = self._read_talipp(state.sma_50)
        sma_200 = self._read_talipp(state.sma_200)

        macd_line = None
        macd_signal = None
        macd_hist = None
        if _talipp_available and state.macd and len(state.macd) > 0:
            last_macd = state.macd[-1]
            if last_macd is not None:
                macd_line = self._round_safe(last_macd.macd)
                macd_signal = self._round_safe(last_macd.signal)
                macd_hist = self._round_safe(last_macd.histogram)

        bb_upper = None
        bb_mid = None
        bb_lower = None
        if _talipp_available and state.bb_20 and len(state.bb_20) > 0:
            last_bb = state.bb_20[-1]
            if last_bb is not None:
                bb_upper = self._round_safe(last_bb.ub)
                bb_mid = self._round_safe(last_bb.cb)
                bb_lower = self._round_safe(last_bb.lb)

        atr_14 = self._read_talipp(state.atr_14)

        adx_14 = None
        if _talipp_available and state.adx_14 and len(state.adx_14) > 0:
            last_adx = state.adx_14[-1]
            if last_adx is not None:
                adx_14 = self._round_safe(last_adx.adx if hasattr(last_adx, 'adx') else last_adx)

        stoch_k = None
        stoch_d = None
        if _talipp_available and state.stoch and len(state.stoch) > 0:
            last_stoch = state.stoch[-1]
            if last_stoch is not None:
                stoch_k = self._round_safe(last_stoch.k if hasattr(last_stoch, 'k') else None)
                stoch_d = self._round_safe(last_stoch.d if hasattr(last_stoch, 'd') else None)

        # ---- Multi-timeframe indicators ----
        tf_data = {}
        for tf_period, tf_state in state.tf_states.items():
            if tf_state.bar_count == 0:
                continue
            tf_ind = {'bar_count': tf_state.bar_count}

            # SMA values
            for sma_attr in ('sma_5', 'sma_8', 'sma_20'):
                ind = getattr(tf_state, sma_attr, None)
                if ind is not None:
                    tf_ind[sma_attr] = self._read_talipp(ind)

            # MACD
            if tf_state.macd is not None and len(tf_state.macd) > 0:
                last_macd = tf_state.macd[-1]
                if last_macd is not None:
                    tf_ind['macd_line'] = self._round_safe(last_macd.macd)
                    tf_ind['macd_signal'] = self._round_safe(last_macd.signal)
                    tf_ind['macd_hist'] = self._round_safe(last_macd.histogram)

            # Stochastic
            if tf_state.stoch is not None and len(tf_state.stoch) > 0:
                last_stoch = tf_state.stoch[-1]
                if last_stoch is not None:
                    tf_ind['stoch_k'] = self._round_safe(last_stoch.k if hasattr(last_stoch, 'k') else None)
                    tf_ind['stoch_d'] = self._round_safe(last_stoch.d if hasattr(last_stoch, 'd') else None)

            # Timeframe highs/lows
            if tf_state.tf_high > 0:
                tf_ind['tf_high'] = tf_state.tf_high
            if tf_state.tf_low < float('inf'):
                tf_ind['tf_low'] = tf_state.tf_low

            tf_data[tf_period] = tf_ind

        return IndicatorValues(
            chg_1m=chg_1m, chg_2m=chg_2m, chg_5m=chg_5m,
            chg_10m=chg_10m, chg_15m=chg_15m, chg_30m=chg_30m,
            chg_60m=chg_60m,
            vol_1m=vol_1m, vol_5m=vol_5m, vol_10m=vol_10m,
            vol_15m=vol_15m, vol_30m=vol_30m, vol_60m=vol_60m,
            rsi_14=rsi_14, ema_9=ema_9, ema_20=ema_20, ema_50=ema_50,
            sma_5=sma_5, sma_8=sma_8, sma_20=sma_20, sma_50=sma_50, sma_200=sma_200,
            macd_line=macd_line, macd_signal=macd_signal, macd_hist=macd_hist,
            bb_upper=bb_upper, bb_mid=bb_mid, bb_lower=bb_lower,
            atr_14=atr_14, adx_14=adx_14,
            stoch_k=stoch_k, stoch_d=stoch_d,
            bar_high_intraday=state.high_intraday if state.high_intraday > 0 else None,
            bar_low_intraday=state.low_intraday if state.low_intraday < float('inf') else None,
            bar_count=state.bar_count,
            tf=tf_data if tf_data else None,
        )

    def get_volume_window(self, symbol: str, minutes: int) -> Optional[int]:
        """Get volume accumulated in the last N minutes (per-minute resolution)."""
        state = self._states.get(symbol)
        if state is None:
            return None
        return self._calc_volume(state.volumes, minutes)

    def get_price_change(self, symbol: str, minutes: int) -> Optional[float]:
        """Get price change % in the last N minutes (per-minute resolution)."""
        state = self._states.get(symbol)
        if state is None:
            return None
        return self._calc_change(state.closes, minutes)

    # ========================================================================
    # Warmup: load historical bars (from TimescaleDB on startup)
    # ========================================================================

    def warmup(self, symbol: str, bars: List[dict]) -> None:
        """
        Feed historical bars to warm up indicators.

        Args:
            symbol: Ticker symbol
            bars: List of dicts with keys: o, h, l, c, v, av, s
                  Must be sorted by s (ascending).
        """
        state = self._get_or_create_state(symbol)

        for bar_dict in bars:
            bar = BarData(
                sym=symbol,
                s=bar_dict.get('s', bar_dict.get('ts', 0)),
                e=bar_dict.get('e', 0),
                o=float(bar_dict['open'] if 'open' in bar_dict else bar_dict.get('o', 0)),
                h=float(bar_dict['high'] if 'high' in bar_dict else bar_dict.get('h', 0)),
                l=float(bar_dict['low'] if 'low' in bar_dict else bar_dict.get('l', 0)),
                c=float(bar_dict['close'] if 'close' in bar_dict else bar_dict.get('c', 0)),
                v=int(bar_dict['volume'] if 'volume' in bar_dict else bar_dict.get('v', 0)),
                av=int(bar_dict.get('av', 0)),
                vw=float(bar_dict.get('vw', 0)),
            )
            # Directly close each bar (warmup = all bars are already closed)
            self._close_bar(symbol, state, bar)
            state.current_s = bar.s

        # Don't persist warmup bars to TimescaleDB
        # (they came FROM TimescaleDB, no need to write back)

    def warmup_complete(self) -> None:
        """Clear persistence buffer after warmup (bars came from DB, don't re-persist)."""
        self._bars_closed_buffer.clear()

        # Purge indicator history accumulated during warmup.
        # Warmup feeds ~200 historical bars per symbol, growing indicator
        # output lists to 200 entries each. Purge now to start lean.
        if _talipp_available:
            purged = 0
            for state in self._states.values():
                purged += self._purge_indicators(state)
            if purged > 0:
                logger.info(
                    "bar_engine_warmup_purge",
                    symbols=self.symbol_count,
                    total_values_purged=purged,
                    max_output_length=TALIPP_MAX_OUTPUT_LENGTH,
                )

        logger.info(
            "bar_engine_warmup_complete",
            symbols=self.symbol_count,
            total_bars=self._total_bars_closed,
        )

    # ========================================================================
    # Reset (new trading day)
    # ========================================================================

    def reset(self) -> None:
        """
        Reset all state for a new trading day.

        Clears ring buffers, re-initializes talipp indicators,
        resets intraday extremes. Called on DAY_CHANGED event.
        """
        old_count = len(self._states)
        self._states.clear()
        self._bars_closed_buffer.clear()
        self._total_bars_received = 0
        self._total_bars_closed = 0

        logger.info(
            "bar_engine_reset",
            symbols_cleared=old_count,
            reason="new_trading_day",
        )

    # ========================================================================
    # Memory management
    # ========================================================================

    @staticmethod
    def _purge_indicators(state: TickerBarState) -> int:
        """
        Trim old output values from all talipp indicators on a TickerBarState,
        including multi-timeframe indicators.

        Returns total number of values purged (for logging/metrics).
        """
        total_purged = 0
        # 1-minute indicators
        for attr in _TALIPP_ATTRS:
            ind = getattr(state, attr, None)
            if ind is not None:
                n = len(ind)
                excess = n - TALIPP_MAX_OUTPUT_LENGTH
                if excess > 0:
                    ind.purge_oldest(excess)
                    total_purged += excess
        # Multi-timeframe indicators
        for tf_state in state.tf_states.values():
            for attr in _TF_TALIPP_ATTRS:
                ind = getattr(tf_state, attr, None)
                if ind is not None:
                    n = len(ind)
                    excess = n - TALIPP_MAX_OUTPUT_LENGTH
                    if excess > 0:
                        ind.purge_oldest(excess)
                        total_purged += excess
        return total_purged

    # ========================================================================
    # Observability
    # ========================================================================

    def get_stats(self) -> dict:
        """Get engine statistics for monitoring."""
        batch_times = list(self._batch_times)
        p95 = sorted(batch_times)[int(len(batch_times) * 0.95)] if batch_times else 0

        rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

        # Sample indicator output length from first available symbol
        sample_ind_len = 0
        for state in self._states.values():
            if state.rsi_14 is not None and len(state.rsi_14) > 0:
                sample_ind_len = len(state.rsi_14)
                break

        return {
            "symbols": self.symbol_count,
            "total_bars_received": self._total_bars_received,
            "total_bars_closed": self._total_bars_closed,
            "last_batch_time_ms": round(self._last_batch_time_ms, 1),
            "last_batch_size": self._last_batch_size,
            "p95_batch_time_ms": round(p95, 1),
            "pending_persistence": len(self._bars_closed_buffer),
            "rss_mb": round(rss_mb, 1),
            "talipp_available": _talipp_available,
            "talipp_max_output_length": TALIPP_MAX_OUTPUT_LENGTH,
            "talipp_purge_interval": TALIPP_PURGE_INTERVAL,
            "sample_indicator_len": sample_ind_len,
        }

    # ========================================================================
    # Internal helpers
    # ========================================================================

    @staticmethod
    def _calc_change(closes: deque, minutes: int) -> Optional[float]:
        """
        Calculate price change % over the last N minutes.

        chg_5m = ((close_now - close_5_bars_ago) / close_5_bars_ago) * 100
        """
        if len(closes) < minutes + 1:
            return None
        old_price = closes[-(minutes + 1)]
        if old_price <= 0:
            return None
        current_price = closes[-1]
        return round(((current_price - old_price) / old_price) * 100, 4)

    @staticmethod
    def _calc_volume(volumes: deque, minutes: int) -> Optional[int]:
        """
        Calculate total volume over the last N minutes.

        vol_5m = sum of last 5 volume entries.
        """
        if len(volumes) < minutes:
            return None
        total = 0
        for i in range(1, minutes + 1):
            total += volumes[-i]
        return total

    @staticmethod
    def _read_talipp(indicator) -> Optional[float]:
        """Safely read the last value from a talipp indicator."""
        if indicator is None:
            return None
        try:
            if len(indicator) == 0:
                return None
            val = indicator[-1]
            if val is None:
                return None
            return round(float(val), 4)
        except (IndexError, TypeError):
            return None

    @staticmethod
    def _round_safe(val) -> Optional[float]:
        """Safely round a value."""
        if val is None:
            return None
        try:
            return round(float(val), 4)
        except (TypeError, ValueError):
            return None


# ============================================================================
# Utility: parse raw stream message to BarData
# ============================================================================

def parse_bar_from_stream(raw_data: dict) -> Optional[BarData]:
    """
    Parse a raw Redis stream message into a BarData.

    Handles both string and numeric values (Redis streams store everything as strings).
    Also handles bytes keys (Redis returns bytes by default).
    """
    try:
        # Normalize: decode bytes keys/values to strings
        data = {}
        for k, v in raw_data.items():
            key = k.decode() if isinstance(k, bytes) else k
            val = v.decode() if isinstance(v, bytes) else v
            data[key] = val

        sym = data.get('sym', '')
        if not sym:
            return None

        return BarData(
            sym=sym,
            s=int(data.get('s', 0)),
            e=int(data.get('e', 0)),
            o=float(data.get('o', 0)),
            h=float(data.get('h', 0)),
            l=float(data.get('l', 0)),
            c=float(data.get('c', 0)),
            v=int(float(data.get('v', 0))),
            av=int(float(data.get('av', 0))),
            vw=float(data.get('vw', 0)),
        )
    except (ValueError, TypeError) as e:
        logger.error("bar_parse_error", data=str(raw_data)[:200], error=str(e))
        return None
