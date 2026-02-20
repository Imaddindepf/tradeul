/**
 * IncrementalIndicatorEngine — O(1) real-time indicator updates.
 *
 * Maintains running state for each active indicator. On each tick:
 *   - isNewBar=true  → advance windows, push new values
 *   - isNewBar=false → undo last contribution, redo with updated bar
 *
 * All math runs on the main thread — no Worker round-trip needed
 * for single-bar updates (~0.01ms per update for all indicators).
 */

import type { ChartBar } from './constants';

// ─── Result types ─────────────────────────────────────────────────────────────

export interface IncrementalResults {
  sma20?: number;
  sma50?: number;
  sma200?: number;
  ema12?: number;
  ema26?: number;
  rsi?: number;
  macd?: { macd: number; signal: number; histogram: number };
  bb?: { upper: number; middle: number; lower: number };
  keltner?: { upper: number; middle: number; lower: number };
  vwap?: number;
  atr?: number;
  obv?: number;
  stoch?: { k: number; d: number };
  adx?: { adx: number; pdi: number; mdi: number };
  squeeze?: { value: number; isOn: boolean };
}

// ─── Circular buffer ──────────────────────────────────────────────────────────

class CircularBuffer {
  private buf: number[];
  private head = 0;
  private _count = 0;
  readonly capacity: number;

  constructor(capacity: number) {
    this.capacity = capacity;
    this.buf = new Array(capacity).fill(0);
  }

  push(val: number): number | undefined {
    let evicted: number | undefined;
    if (this._count === this.capacity) {
      evicted = this.buf[this.head];
    }
    this.buf[this.head] = val;
    this.head = (this.head + 1) % this.capacity;
    if (this._count < this.capacity) this._count++;
    return evicted;
  }

  replaceLast(val: number): number {
    const idx = (this.head - 1 + this.capacity) % this.capacity;
    const old = this.buf[idx];
    this.buf[idx] = val;
    return old;
  }

  get count(): number { return this._count; }
  get full(): boolean { return this._count === this.capacity; }

  // Get element by index (0 = oldest)
  at(i: number): number {
    const start = this._count < this.capacity ? 0 : this.head;
    return this.buf[(start + i) % this.capacity];
  }

  // Get all values in order (oldest to newest)
  toArray(): number[] {
    const arr: number[] = [];
    for (let i = 0; i < this._count; i++) arr.push(this.at(i));
    return arr;
  }

  last(): number {
    return this.buf[(this.head - 1 + this.capacity) % this.capacity];
  }

  min(): number {
    let m = Infinity;
    for (let i = 0; i < this._count; i++) {
      const v = this.at(i);
      if (v < m) m = v;
    }
    return m;
  }

  max(): number {
    let m = -Infinity;
    for (let i = 0; i < this._count; i++) {
      const v = this.at(i);
      if (v > m) m = v;
    }
    return m;
  }
}

// ─── SMA state ────────────────────────────────────────────────────────────────

interface SMAState {
  buffer: CircularBuffer;
  sum: number;
  period: number;
  lastValue: number | undefined;
}

function createSMA(period: number): SMAState {
  return { buffer: new CircularBuffer(period), sum: 0, period, lastValue: undefined };
}

function updateSMA(s: SMAState, close: number, isNewBar: boolean): number | undefined {
  if (isNewBar) {
    const evicted = s.buffer.push(close);
    s.sum += close;
    if (evicted !== undefined) s.sum -= evicted;
  } else {
    const old = s.buffer.replaceLast(close);
    s.sum += close - old;
  }
  if (!s.buffer.full) return undefined;
  s.lastValue = s.sum / s.period;
  return s.lastValue;
}

// ─── EMA state ────────────────────────────────────────────────────────────────

interface EMAState {
  k: number;
  period: number;
  ema: number;
  count: number;
  sum: number;
  ready: boolean;
  // For same-bar undo
  prevEma: number;
}

function createEMA(period: number): EMAState {
  return { k: 2 / (period + 1), period, ema: 0, count: 0, sum: 0, ready: false, prevEma: 0 };
}

function updateEMA(s: EMAState, close: number, isNewBar: boolean): number | undefined {
  if (!s.ready) {
    if (isNewBar) {
      s.count++;
      s.sum += close;
      if (s.count === s.period) {
        s.ema = s.sum / s.period;
        s.prevEma = s.ema;
        s.ready = true;
        return s.ema;
      }
    }
    return undefined;
  }

  if (isNewBar) {
    s.prevEma = s.ema;
    s.ema = close * s.k + s.ema * (1 - s.k);
  } else {
    // Undo last, redo
    s.ema = close * s.k + s.prevEma * (1 - s.k);
  }
  return s.ema;
}

// ─── RSI state (Wilder smoothing) ─────────────────────────────────────────────

interface RSIState {
  period: number;
  avgGain: number;
  avgLoss: number;
  prevClose: number;
  count: number;
  ready: boolean;
  gains: number[];
  losses: number[];
  // Same-bar undo
  prevAvgGain: number;
  prevAvgLoss: number;
}

function createRSI(period = 14): RSIState {
  return {
    period, avgGain: 0, avgLoss: 0, prevClose: 0,
    count: 0, ready: false, gains: [], losses: [],
    prevAvgGain: 0, prevAvgLoss: 0,
  };
}

function updateRSI(s: RSIState, close: number, isNewBar: boolean): number | undefined {
  if (s.count === 0) {
    s.prevClose = close;
    s.count = 1;
    return undefined;
  }

  const change = close - s.prevClose;
  const gain = change > 0 ? change : 0;
  const loss = change < 0 ? -change : 0;

  if (!s.ready) {
    if (isNewBar) {
      s.gains.push(gain);
      s.losses.push(loss);
      s.count++;

      if (s.gains.length === s.period) {
        s.avgGain = s.gains.reduce((a, b) => a + b, 0) / s.period;
        s.avgLoss = s.losses.reduce((a, b) => a + b, 0) / s.period;
        s.prevAvgGain = s.avgGain;
        s.prevAvgLoss = s.avgLoss;
        s.ready = true;
        s.prevClose = close;
        const rs = s.avgLoss === 0 ? 100 : s.avgGain / s.avgLoss;
        return 100 - 100 / (1 + rs);
      }
      s.prevClose = close;
    }
    return undefined;
  }

  if (isNewBar) {
    s.prevAvgGain = s.avgGain;
    s.prevAvgLoss = s.avgLoss;
    s.avgGain = (s.avgGain * (s.period - 1) + gain) / s.period;
    s.avgLoss = (s.avgLoss * (s.period - 1) + loss) / s.period;
    s.prevClose = close;
  } else {
    // Undo: restore previous averages, redo with current close vs prevClose
    // Note: for same-bar, prevClose doesn't change — the change is recalculated
    const c = close - s.prevClose;
    const g = c > 0 ? c : 0;
    const l = c < 0 ? -c : 0;
    s.avgGain = (s.prevAvgGain * (s.period - 1) + g) / s.period;
    s.avgLoss = (s.prevAvgLoss * (s.period - 1) + l) / s.period;
  }

  const rs = s.avgLoss === 0 ? 100 : s.avgGain / s.avgLoss;
  return 100 - 100 / (1 + rs);
}

// ─── MACD state ───────────────────────────────────────────────────────────────

interface MACDState {
  ema12: EMAState;
  ema26: EMAState;
  signal: EMAState;
  ready: boolean;
}

function createMACD(): MACDState {
  return {
    ema12: createEMA(12),
    ema26: createEMA(26),
    signal: createEMA(9),
    ready: false,
  };
}

function updateMACD(s: MACDState, close: number, isNewBar: boolean): { macd: number; signal: number; histogram: number } | undefined {
  const e12 = updateEMA(s.ema12, close, isNewBar);
  const e26 = updateEMA(s.ema26, close, isNewBar);

  if (e12 === undefined || e26 === undefined) return undefined;

  const macdLine = e12 - e26;
  const sig = updateEMA(s.signal, macdLine, isNewBar);

  if (sig === undefined) return undefined;

  s.ready = true;
  return { macd: macdLine, signal: sig, histogram: macdLine - sig };
}

// ─── Bollinger Bands state ────────────────────────────────────────────────────

interface BBState {
  sma: SMAState;
  buffer: CircularBuffer;
  mult: number;
}

function createBB(period = 20, mult = 2): BBState {
  return { sma: createSMA(period), buffer: new CircularBuffer(period), mult };
}

function updateBB(s: BBState, close: number, isNewBar: boolean): { upper: number; middle: number; lower: number } | undefined {
  const mid = updateSMA(s.sma, close, isNewBar);

  if (isNewBar) {
    s.buffer.push(close);
  } else {
    s.buffer.replaceLast(close);
  }

  if (mid === undefined || !s.buffer.full) return undefined;

  // Compute stddev
  let sumSq = 0;
  for (let i = 0; i < s.buffer.count; i++) {
    const diff = s.buffer.at(i) - mid;
    sumSq += diff * diff;
  }
  const std = Math.sqrt(sumSq / s.buffer.count);

  return {
    upper: mid + s.mult * std,
    middle: mid,
    lower: mid - s.mult * std,
  };
}

// ─── VWAP state ───────────────────────────────────────────────────────────────

interface VWAPState {
  cumTPV: number;
  cumVol: number;
  lastDayStart: number;
  // Same-bar undo
  prevTPV: number;
  prevVol: number;
}

function createVWAP(): VWAPState {
  return { cumTPV: 0, cumVol: 0, lastDayStart: 0, prevTPV: 0, prevVol: 0 };
}

function isDifferentDay(t1: number, t2: number): boolean {
  const d1 = new Date(t1 * 1000);
  const d2 = new Date(t2 * 1000);
  // Compare in ET (market time) — approximate with UTC for simplicity
  return d1.getUTCDate() !== d2.getUTCDate() ||
         d1.getUTCMonth() !== d2.getUTCMonth() ||
         d1.getUTCFullYear() !== d2.getUTCFullYear();
}

function updateVWAP(s: VWAPState, bar: { time: number; high: number; low: number; close: number; volume: number }, isNewBar: boolean): number | undefined {
  if (bar.volume <= 0) return s.cumVol > 0 ? s.cumTPV / s.cumVol : undefined;

  const tp = (bar.high + bar.low + bar.close) / 3;

  if (isNewBar) {
    // Check for day reset
    if (s.lastDayStart > 0 && isDifferentDay(bar.time, s.lastDayStart)) {
      s.cumTPV = 0;
      s.cumVol = 0;
    }
    s.lastDayStart = bar.time;
    s.prevTPV = s.cumTPV;
    s.prevVol = s.cumVol;
    s.cumTPV += tp * bar.volume;
    s.cumVol += bar.volume;
  } else {
    // Undo last bar, redo
    s.cumTPV = s.prevTPV + tp * bar.volume;
    s.cumVol = s.prevVol + bar.volume;
  }

  return s.cumVol > 0 ? s.cumTPV / s.cumVol : undefined;
}

// ─── ATR state (Wilder smoothing) ─────────────────────────────────────────────

interface ATRState {
  period: number;
  atr: number;
  prevBar: { high: number; low: number; close: number } | null;
  count: number;
  ready: boolean;
  trSum: number;
  // Same-bar undo
  prevATR: number;
}

function createATR(period = 14): ATRState {
  return { period, atr: 0, prevBar: null, count: 0, ready: false, trSum: 0, prevATR: 0 };
}

function updateATR(s: ATRState, bar: { high: number; low: number; close: number }, isNewBar: boolean): number | undefined {
  if (!s.prevBar) {
    s.prevBar = { high: bar.high, low: bar.low, close: bar.close };
    return undefined;
  }

  const tr = Math.max(
    bar.high - bar.low,
    Math.abs(bar.high - s.prevBar.close),
    Math.abs(bar.low - s.prevBar.close)
  );

  if (!s.ready) {
    if (isNewBar) {
      s.trSum += tr;
      s.count++;
      if (s.count === s.period) {
        s.atr = s.trSum / s.period;
        s.prevATR = s.atr;
        s.ready = true;
        s.prevBar = { high: bar.high, low: bar.low, close: bar.close };
        return s.atr;
      }
      s.prevBar = { high: bar.high, low: bar.low, close: bar.close };
    }
    return undefined;
  }

  if (isNewBar) {
    s.prevATR = s.atr;
    s.atr = (s.atr * (s.period - 1) + tr) / s.period;
    s.prevBar = { high: bar.high, low: bar.low, close: bar.close };
  } else {
    s.atr = (s.prevATR * (s.period - 1) + tr) / s.period;
  }

  return s.atr;
}

// ─── OBV state ────────────────────────────────────────────────────────────────

interface OBVState {
  obv: number;
  prevClose: number;
  initialized: boolean;
  // Same-bar
  prevOBV: number;
}

function createOBV(): OBVState {
  return { obv: 0, prevClose: 0, initialized: false, prevOBV: 0 };
}

function updateOBV(s: OBVState, close: number, volume: number, isNewBar: boolean): number {
  if (!s.initialized) {
    s.initialized = true;
    s.prevClose = close;
    s.obv = 0;
    s.prevOBV = 0;
    return 0;
  }

  if (isNewBar) {
    s.prevOBV = s.obv;
    if (close > s.prevClose) s.obv += volume;
    else if (close < s.prevClose) s.obv -= volume;
    s.prevClose = close;
  } else {
    // Undo and redo with current values
    s.obv = s.prevOBV;
    if (close > s.prevClose) s.obv += volume;
    else if (close < s.prevClose) s.obv -= volume;
  }

  return s.obv;
}

// ─── Stochastic state ─────────────────────────────────────────────────────────

interface StochState {
  highBuf: CircularBuffer;
  lowBuf: CircularBuffer;
  closeBuf: CircularBuffer;
  kBuf: CircularBuffer;
  period: number;
  smoothK: number;
  smoothD: number;
}

function createStoch(period = 14, smoothK = 1, smoothD = 3): StochState {
  return {
    highBuf: new CircularBuffer(period),
    lowBuf: new CircularBuffer(period),
    closeBuf: new CircularBuffer(period),
    kBuf: new CircularBuffer(smoothD),
    period, smoothK, smoothD,
  };
}

function updateStoch(s: StochState, bar: { high: number; low: number; close: number }, isNewBar: boolean): { k: number; d: number } | undefined {
  if (isNewBar) {
    s.highBuf.push(bar.high);
    s.lowBuf.push(bar.low);
    s.closeBuf.push(bar.close);
  } else {
    s.highBuf.replaceLast(bar.high);
    s.lowBuf.replaceLast(bar.low);
    s.closeBuf.replaceLast(bar.close);
  }

  if (!s.highBuf.full) return undefined;

  const highN = s.highBuf.max();
  const lowN = s.lowBuf.min();
  const range = highN - lowN;
  const rawK = range > 0 ? ((bar.close - lowN) / range) * 100 : 50;

  if (isNewBar) {
    s.kBuf.push(rawK);
  } else {
    s.kBuf.replaceLast(rawK);
  }

  if (!s.kBuf.full) return undefined;

  // %D = SMA of %K values
  let kSum = 0;
  for (let i = 0; i < s.kBuf.count; i++) kSum += s.kBuf.at(i);
  const d = kSum / s.kBuf.count;

  return { k: rawK, d };
}

// ─── ADX state ────────────────────────────────────────────────────────────────

interface ADXState {
  period: number;
  smoothedPDI: number;
  smoothedMDI: number;
  smoothedTR: number;
  adx: number;
  prevBar: { high: number; low: number; close: number } | null;
  count: number;
  adxCount: number;
  dxSum: number;
  ready: boolean;
  adxReady: boolean;
  // Same-bar undo
  prevSmoothedPDI: number;
  prevSmoothedMDI: number;
  prevSmoothedTR: number;
  prevADX: number;
}

function createADX(period = 14): ADXState {
  return {
    period, smoothedPDI: 0, smoothedMDI: 0, smoothedTR: 0,
    adx: 0, prevBar: null, count: 0, adxCount: 0, dxSum: 0,
    ready: false, adxReady: false,
    prevSmoothedPDI: 0, prevSmoothedMDI: 0, prevSmoothedTR: 0, prevADX: 0,
  };
}

function updateADX(s: ADXState, bar: { high: number; low: number; close: number }, isNewBar: boolean): { adx: number; pdi: number; mdi: number } | undefined {
  if (!s.prevBar) {
    if (isNewBar) s.prevBar = { high: bar.high, low: bar.low, close: bar.close };
    return undefined;
  }

  const tr = Math.max(
    bar.high - bar.low,
    Math.abs(bar.high - s.prevBar.close),
    Math.abs(bar.low - s.prevBar.close)
  );
  const upMove = bar.high - s.prevBar.high;
  const downMove = s.prevBar.low - bar.low;
  const plusDM = upMove > downMove && upMove > 0 ? upMove : 0;
  const minusDM = downMove > upMove && downMove > 0 ? downMove : 0;

  if (!s.ready) {
    if (isNewBar) {
      s.smoothedTR += tr;
      s.smoothedPDI += plusDM;
      s.smoothedMDI += minusDM;
      s.count++;

      if (s.count === s.period) {
        s.ready = true;
        s.prevSmoothedTR = s.smoothedTR;
        s.prevSmoothedPDI = s.smoothedPDI;
        s.prevSmoothedMDI = s.smoothedMDI;
      }
      s.prevBar = { high: bar.high, low: bar.low, close: bar.close };
    }
    if (!s.ready) return undefined;
  }

  if (isNewBar && s.count > s.period) {
    s.prevSmoothedTR = s.smoothedTR;
    s.prevSmoothedPDI = s.smoothedPDI;
    s.prevSmoothedMDI = s.smoothedMDI;
    s.smoothedTR = s.smoothedTR - s.smoothedTR / s.period + tr;
    s.smoothedPDI = s.smoothedPDI - s.smoothedPDI / s.period + plusDM;
    s.smoothedMDI = s.smoothedMDI - s.smoothedMDI / s.period + minusDM;
    s.prevBar = { high: bar.high, low: bar.low, close: bar.close };
  } else if (!isNewBar && s.ready) {
    s.smoothedTR = s.prevSmoothedTR - s.prevSmoothedTR / s.period + tr;
    s.smoothedPDI = s.prevSmoothedPDI - s.prevSmoothedPDI / s.period + plusDM;
    s.smoothedMDI = s.prevSmoothedMDI - s.prevSmoothedMDI / s.period + minusDM;
  }

  if (s.count <= s.period && isNewBar) s.count++;

  const pdi = s.smoothedTR > 0 ? (s.smoothedPDI / s.smoothedTR) * 100 : 0;
  const mdi = s.smoothedTR > 0 ? (s.smoothedMDI / s.smoothedTR) * 100 : 0;
  const diSum = pdi + mdi;
  const dx = diSum > 0 ? (Math.abs(pdi - mdi) / diSum) * 100 : 0;

  if (!s.adxReady) {
    if (isNewBar) {
      s.dxSum += dx;
      s.adxCount++;
      if (s.adxCount === s.period) {
        s.adx = s.dxSum / s.period;
        s.prevADX = s.adx;
        s.adxReady = true;
      }
    }
    if (!s.adxReady) return undefined;
  } else {
    if (isNewBar) {
      s.prevADX = s.adx;
      s.adx = (s.adx * (s.period - 1) + dx) / s.period;
    } else {
      s.adx = (s.prevADX * (s.period - 1) + dx) / s.period;
    }
  }

  return { adx: s.adx, pdi, mdi };
}

// ─── Keltner Channels ─────────────────────────────────────────────────────────

interface KeltnerState {
  ema: EMAState;
  atr: ATRState;
  mult: number;
}

function createKeltner(emaPeriod = 20, atrPeriod = 10, mult = 1.5): KeltnerState {
  return { ema: createEMA(emaPeriod), atr: createATR(atrPeriod), mult };
}

function updateKeltner(s: KeltnerState, bar: { high: number; low: number; close: number }, isNewBar: boolean): { upper: number; middle: number; lower: number } | undefined {
  const ema = updateEMA(s.ema, bar.close, isNewBar);
  const atr = updateATR(s.atr, bar, isNewBar);

  if (ema === undefined || atr === undefined) return undefined;

  return {
    upper: ema + s.mult * atr,
    middle: ema,
    lower: ema - s.mult * atr,
  };
}

// ─── Squeeze Momentum ─────────────────────────────────────────────────────────

interface SqueezeState {
  bb: BBState;
  keltner: KeltnerState;
  // Momentum: close - midline of (highest high + lowest low)/2 + SMA(close, period))/2
  highBuf: CircularBuffer;
  lowBuf: CircularBuffer;
  momSMA: SMAState;
}

function createSqueeze(period = 20): SqueezeState {
  return {
    bb: createBB(period, 2),
    keltner: createKeltner(period, period, 1.5),
    highBuf: new CircularBuffer(period),
    lowBuf: new CircularBuffer(period),
    momSMA: createSMA(period),
  };
}

function updateSqueeze(s: SqueezeState, bar: { high: number; low: number; close: number }, isNewBar: boolean): { value: number; isOn: boolean } | undefined {
  const bb = updateBB(s.bb, bar.close, isNewBar);
  const kc = updateKeltner(s.keltner, bar, isNewBar);

  if (isNewBar) {
    s.highBuf.push(bar.high);
    s.lowBuf.push(bar.low);
  } else {
    s.highBuf.replaceLast(bar.high);
    s.lowBuf.replaceLast(bar.low);
  }

  if (!bb || !kc || !s.highBuf.full) return undefined;

  const isOn = bb.lower > kc.lower && bb.upper < kc.upper;

  // Momentum = close - average of (mid-range donchian + SMA)
  const highestHigh = s.highBuf.max();
  const lowestLow = s.lowBuf.min();
  const midDonchian = (highestHigh + lowestLow) / 2;
  const midComposite = (midDonchian + bb.middle) / 2;
  const momentum = bar.close - midComposite;

  return { value: momentum, isOn };
}

// ═══════════════════════════════════════════════════════════════════════════════
// Main Engine
// ═══════════════════════════════════════════════════════════════════════════════

export class IncrementalIndicatorEngine {
  private active = new Set<string>();

  // State objects
  private sma20: SMAState | null = null;
  private sma50: SMAState | null = null;
  private sma200: SMAState | null = null;
  private ema12: EMAState | null = null;
  private ema26: EMAState | null = null;
  private rsi: RSIState | null = null;
  private macd: MACDState | null = null;
  private bb: BBState | null = null;
  private vwap: VWAPState | null = null;
  private atrState: ATRState | null = null;
  private obv: OBVState | null = null;
  private stoch: StochState | null = null;
  private adxState: ADXState | null = null;
  private keltner: KeltnerState | null = null;
  private squeeze: SqueezeState | null = null;

  /**
   * Initialize from historical bars. Iterates through all bars to build state.
   * Only initializes indicators in the activeIndicators list.
   */
  initialize(bars: ChartBar[], activeIndicators: string[]): void {
    this.active = new Set(activeIndicators.map(s => s.toLowerCase()));

    // Create state objects for active indicators
    this.sma20 = this.active.has('sma20') ? createSMA(20) : null;
    this.sma50 = this.active.has('sma50') ? createSMA(50) : null;
    this.sma200 = this.active.has('sma200') ? createSMA(200) : null;
    this.ema12 = this.active.has('ema12') ? createEMA(12) : null;
    this.ema26 = this.active.has('ema26') ? createEMA(26) : null;
    this.rsi = this.active.has('rsi') ? createRSI(14) : null;
    this.macd = this.active.has('macd') ? createMACD() : null;
    this.bb = this.active.has('bb') ? createBB(20, 2) : null;
    this.vwap = this.active.has('vwap') ? createVWAP() : null;
    this.atrState = this.active.has('atr') ? createATR(14) : null;
    this.obv = this.active.has('obv') ? createOBV() : null;
    this.stoch = this.active.has('stoch') ? createStoch(14, 1, 3) : null;
    this.adxState = this.active.has('adx') ? createADX(14) : null;
    this.keltner = this.active.has('keltner') ? createKeltner(20, 10, 1.5) : null;
    this.squeeze = this.active.has('squeeze') ? createSqueeze(20) : null;

    // Feed all historical bars (all are "new bars")
    for (const bar of bars) {
      this._compute(bar, true);
    }
  }

  /**
   * Update with a new tick. Returns computed values for all active indicators.
   */
  update(bar: ChartBar, isNewBar: boolean): IncrementalResults {
    return this._compute(bar, isNewBar);
  }

  reset(): void {
    this.active.clear();
    this.sma20 = this.sma50 = this.sma200 = null;
    this.ema12 = this.ema26 = null;
    this.rsi = null;
    this.macd = null;
    this.bb = null;
    this.vwap = null;
    this.atrState = null;
    this.obv = null;
    this.stoch = null;
    this.adxState = null;
    this.keltner = null;
    this.squeeze = null;
  }

  private _compute(bar: ChartBar, isNewBar: boolean): IncrementalResults {
    const r: IncrementalResults = {};

    if (this.sma20) r.sma20 = updateSMA(this.sma20, bar.close, isNewBar);
    if (this.sma50) r.sma50 = updateSMA(this.sma50, bar.close, isNewBar);
    if (this.sma200) r.sma200 = updateSMA(this.sma200, bar.close, isNewBar);
    if (this.ema12) r.ema12 = updateEMA(this.ema12, bar.close, isNewBar);
    if (this.ema26) r.ema26 = updateEMA(this.ema26, bar.close, isNewBar);
    if (this.rsi) r.rsi = updateRSI(this.rsi, bar.close, isNewBar);
    if (this.macd) r.macd = updateMACD(this.macd, bar.close, isNewBar);
    if (this.bb) r.bb = updateBB(this.bb, bar.close, isNewBar);
    if (this.vwap) r.vwap = updateVWAP(this.vwap, bar, isNewBar);
    if (this.atrState) r.atr = updateATR(this.atrState, bar, isNewBar);
    if (this.obv) r.obv = updateOBV(this.obv, bar.close, bar.volume, isNewBar);
    if (this.stoch) r.stoch = updateStoch(this.stoch, bar, isNewBar);
    if (this.adxState) r.adx = updateADX(this.adxState, bar, isNewBar);
    if (this.keltner) r.keltner = updateKeltner(this.keltner, bar, isNewBar);
    if (this.squeeze) r.squeeze = updateSqueeze(this.squeeze, bar, isNewBar);

    return r;
  }
}
