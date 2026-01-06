/**
 * Dedicated Worker para cálculo de indicadores técnicos
 * 
 * ARQUITECTURA 2025:
 * - NO bloquea el main thread
 * - Soporta cálculo incremental (lazy loading de barras)
 * - Cache inteligente por ticker
 * - Todos los indicadores del Screener disponibles
 * 
 * INDICADORES SOPORTADOS:
 * - Overlays: SMA (20/50/200), EMA (12/26), Bollinger Bands, Keltner Channels
 * - Oscillators: RSI, MACD, Stochastic, ADX/DMI
 * - Volatility: ATR, BB Width, Squeeze
 * - Volume: OBV, VWAP (intraday)
 */

/* global self, importScripts */

// Polyfill requerido por technicalindicators (async/await support)
importScripts('/workers/regenerator-runtime.js');

// SHIM: La librería technicalindicators se exporta a this.window que no existe en Workers
// Creamos el objeto window para que la librería pueda exportarse ahí
self.window = self.window || {};

// Importar librería de indicadores técnicos (local para evitar CORS/CSP issues)
importScripts('/workers/technicalindicators.js');

// La librería ahora está disponible en self.window
var technicalindicators = self.window;

// DEBUG: Verificar que la librería se cargó
console.log('[Worker] technicalindicators loaded:', typeof technicalindicators.SMA, Object.keys(technicalindicators).slice(0, 10));

// ============================================================================
// CONFIGURACIONES DE INDICADORES
// ============================================================================

const INDICATOR_CONFIGS = {
  // === OVERLAYS (sobre el precio) ===
  sma20: { type: 'overlay', period: 20 },
  sma50: { type: 'overlay', period: 50 },
  sma200: { type: 'overlay', period: 200 },
  ema12: { type: 'overlay', period: 12 },
  ema26: { type: 'overlay', period: 26 },
  bb: { type: 'overlay', period: 20, stdDev: 2 },
  keltner: { type: 'overlay', period: 20, atrPeriod: 10, multiplier: 1.5 },
  vwap: { type: 'overlay' }, // Solo intraday
  
  // === OSCILLATORS (panel separado) ===
  rsi: { type: 'oscillator', period: 14, panel: 'rsi', range: [0, 100] },
  macd: { type: 'oscillator', fast: 12, slow: 26, signal: 9, panel: 'macd' },
  stoch: { type: 'oscillator', period: 14, signalPeriod: 3, panel: 'stoch', range: [0, 100] },
  adx: { type: 'oscillator', period: 14, panel: 'adx', range: [0, 100] },
  
  // === VOLATILITY (panel o overlay) ===
  atr: { type: 'panel', period: 14, panel: 'atr' },
  bbWidth: { type: 'panel', period: 20, stdDev: 2, panel: 'bbwidth' },
  squeeze: { type: 'panel', panel: 'squeeze' }, // TTM Squeeze
  
  // === VOLUME (panel separado) ===
  obv: { type: 'panel', panel: 'obv' },
  rvol: { type: 'panel', panel: 'rvol', lookbackDays: 5 }, // RVOL por slots (solo intraday < 1H)
};

// Cache de resultados por ticker para evitar recálculos
const cache = new Map();

// ============================================================================
// MESSAGE HANDLER
// ============================================================================

self.onmessage = function(event) {
  const { type, requestId, ticker, bars, indicators, interval, incremental, lastBarCount } = event.data;
  
  switch (type) {
    case 'calculate':
      handleCalculate(requestId, ticker, bars, indicators, interval, incremental, lastBarCount);
      break;
      
    case 'calculate_single':
      // Para updates en tiempo real - solo última barra
      handleIncrementalUpdate(requestId, ticker, bars, indicators);
      break;
      
    case 'clear_cache':
      cache.delete(ticker);
      self.postMessage({ type: 'cache_cleared', ticker });
      break;
      
    case 'get_config':
      self.postMessage({ type: 'config', data: INDICATOR_CONFIGS });
      break;
  }
};

// ============================================================================
// CÁLCULO PRINCIPAL
// ============================================================================

function handleCalculate(requestId, ticker, bars, requestedIndicators, interval, incremental, lastBarCount) {
  const startTime = performance.now();
  
  console.log('[Worker] handleCalculate called:', { ticker, barsCount: bars?.length, indicators: requestedIndicators, interval });
  
  try {
    // Verificar si tenemos cache y solo necesitamos actualizar
    const cacheKey = `${ticker}`;
    const cachedData = cache.get(cacheKey);
    
    // Extraer arrays de precios
    const closes = bars.map(b => b.close);
    const highs = bars.map(b => b.high);
    const lows = bars.map(b => b.low);
    const volumes = bars.map(b => b.volume);
    const times = bars.map(b => b.time);
    
    console.log('[Worker] Data extracted:', { closesLen: closes.length, first: closes[0], last: closes[closes.length-1] });
    
    const results = {
      overlays: {},
      panels: {},
    };
    
    // Calcular cada indicador solicitado
    for (const indicator of requestedIndicators) {
      const config = INDICATOR_CONFIGS[indicator];
      console.log('[Worker] Calculating:', indicator, config);
      if (!config) {
        console.warn('[Worker] No config for:', indicator);
        continue;
      }
      
      try {
        const indicatorResult = calculateIndicator(
          indicator, 
          config, 
          { closes, highs, lows, volumes, times, bars, interval }
        );
        
        console.log('[Worker] Result for', indicator, ':', indicatorResult ? (Array.isArray(indicatorResult) ? indicatorResult.length : Object.keys(indicatorResult)) : 'null');
        
        if (config.type === 'overlay') {
          results.overlays[indicator] = indicatorResult;
        } else {
          results.panels[indicator] = {
            data: indicatorResult,
            config: config,
          };
        }
      } catch (err) {
        console.error(`[Worker] Error calculating ${indicator}:`, err.message, err.stack);
      }
    }
    
    console.log('[Worker] Final results:', { overlays: Object.keys(results.overlays), panels: Object.keys(results.panels) });
    
    // Guardar en cache
    cache.set(cacheKey, {
      barCount: bars.length,
      results,
      timestamp: Date.now(),
    });
    
    const duration = performance.now() - startTime;
    
    // Enviar resultados
    self.postMessage({
      type: 'result',
      requestId,
      ticker,
      data: results,
      barCount: bars.length,
      duration: Math.round(duration),
    });
    
  } catch (error) {
    self.postMessage({
      type: 'error',
      requestId,
      ticker,
      error: error.message,
    });
  }
}

// ============================================================================
// CÁLCULO INCREMENTAL (para tiempo real)
// ============================================================================

function handleIncrementalUpdate(requestId, ticker, bars, indicators) {
  // Para actualizaciones en tiempo real, recalculamos solo los últimos N valores
  // necesarios para cada indicador
  handleCalculate(requestId, ticker, bars, indicators, true, bars.length);
}

// ============================================================================
// CALCULADORES DE INDICADORES
// ============================================================================

function calculateIndicator(name, config, data) {
  const { closes, highs, lows, volumes, times, bars, interval } = data;
  
  switch (name) {
    // === SMAs ===
    case 'sma20':
    case 'sma50':
    case 'sma200':
      return calculateSMA(closes, times, config.period);
      
    // === EMAs ===
    case 'ema12':
    case 'ema26':
      return calculateEMA(closes, times, config.period);
      
    // === Bollinger Bands ===
    case 'bb':
      return calculateBollingerBands(closes, times, config.period, config.stdDev);
      
    // === Keltner Channels ===
    case 'keltner':
      return calculateKeltner(highs, lows, closes, times, config);
      
    // === RSI ===
    case 'rsi':
      return calculateRSI(closes, times, config.period);
      
    // === MACD ===
    case 'macd':
      return calculateMACD(closes, times, config);
      
    // === Stochastic ===
    case 'stoch':
      return calculateStochastic(highs, lows, closes, times, config);
      
    // === ADX/DMI ===
    case 'adx':
      return calculateADX(highs, lows, closes, times, config.period);
      
    // === ATR ===
    case 'atr':
      return calculateATR(highs, lows, closes, times, config.period);
      
    // === Bollinger Band Width ===
    case 'bbWidth':
      return calculateBBWidth(closes, times, config.period, config.stdDev);
      
    // === TTM Squeeze ===
    case 'squeeze':
      return calculateSqueeze(highs, lows, closes, times);
      
    // === OBV ===
    case 'obv':
      return calculateOBV(closes, volumes, times);
      
    // === VWAP ===
    case 'vwap':
      return calculateVWAP(bars, times);
    
    // === RVOL (Relative Volume por slots - con volumen ACUMULATIVO como TradingView) ===
    case 'rvol':
      return calculateRVOL(bars, times, config.lookbackDays || 5, interval);
      
    default:
      throw new Error(`Unknown indicator: ${name}`);
  }
}

// ============================================================================
// IMPLEMENTACIONES DE INDICADORES
// ============================================================================

function calculateSMA(closes, times, period) {
  const values = technicalindicators.SMA.calculate({ values: closes, period });
  const offset = closes.length - values.length;
  return values.map((value, i) => ({ time: times[i + offset], value }));
}

function calculateEMA(closes, times, period) {
  const values = technicalindicators.EMA.calculate({ values: closes, period });
  const offset = closes.length - values.length;
  return values.map((value, i) => ({ time: times[i + offset], value }));
}

function calculateBollingerBands(closes, times, period, stdDev) {
  const values = technicalindicators.BollingerBands.calculate({ values: closes, period, stdDev });
  const offset = closes.length - values.length;
  return {
    upper: values.map((v, i) => ({ time: times[i + offset], value: v.upper })),
    middle: values.map((v, i) => ({ time: times[i + offset], value: v.middle })),
    lower: values.map((v, i) => ({ time: times[i + offset], value: v.lower })),
  };
}

function calculateKeltner(highs, lows, closes, times, config) {
  // Keltner = EMA ± ATR * multiplier
  const ema = technicalindicators.EMA.calculate({ values: closes, period: config.period });
  const atr = technicalindicators.ATR.calculate({ 
    high: highs, low: lows, close: closes, period: config.atrPeriod 
  });
  
  // Alinear arrays
  const minLen = Math.min(ema.length, atr.length);
  const emaOffset = closes.length - ema.length;
  const atrOffset = closes.length - atr.length;
  const startOffset = Math.max(emaOffset, atrOffset);
  
  const result = {
    upper: [],
    middle: [],
    lower: [],
  };
  
  for (let i = 0; i < minLen; i++) {
    const emaIdx = i + (ema.length - minLen);
    const atrIdx = i + (atr.length - minLen);
    const timeIdx = startOffset + i;
    
    if (timeIdx < times.length) {
      const mid = ema[emaIdx];
      const band = atr[atrIdx] * config.multiplier;
      
      result.upper.push({ time: times[timeIdx], value: mid + band });
      result.middle.push({ time: times[timeIdx], value: mid });
      result.lower.push({ time: times[timeIdx], value: mid - band });
    }
  }
  
  return result;
}

function calculateRSI(closes, times, period) {
  const values = technicalindicators.RSI.calculate({ values: closes, period });
  const offset = closes.length - values.length;
  return values.map((value, i) => ({ time: times[i + offset], value }));
}

function calculateMACD(closes, times, config) {
  const values = technicalindicators.MACD.calculate({
    values: closes,
    fastPeriod: config.fast,
    slowPeriod: config.slow,
    signalPeriod: config.signal,
    SimpleMAOscillator: false,
    SimpleMASignal: false,
  });
  
  const offset = closes.length - values.length;
  
  return {
    macd: values.map((v, i) => ({ time: times[i + offset], value: v.MACD || 0 })),
    signal: values.map((v, i) => ({ time: times[i + offset], value: v.signal || 0 })),
    histogram: values.map((v, i) => ({ 
      time: times[i + offset], 
      value: v.histogram || 0,
      color: (v.histogram || 0) >= 0 ? 'rgba(16, 185, 129, 0.6)' : 'rgba(239, 68, 68, 0.6)'
    })),
  };
}

function calculateStochastic(highs, lows, closes, times, config) {
  const values = technicalindicators.Stochastic.calculate({
    high: highs,
    low: lows,
    close: closes,
    period: config.period,
    signalPeriod: config.signalPeriod,
  });
  
  const offset = closes.length - values.length;
  
  return {
    k: values.map((v, i) => ({ time: times[i + offset], value: v.k })),
    d: values.map((v, i) => ({ time: times[i + offset], value: v.d })),
  };
}

function calculateADX(highs, lows, closes, times, period) {
  const values = technicalindicators.ADX.calculate({
    high: highs,
    low: lows,
    close: closes,
    period,
  });
  
  const offset = closes.length - values.length;
  
  return {
    adx: values.map((v, i) => ({ time: times[i + offset], value: v.adx })),
    pdi: values.map((v, i) => ({ time: times[i + offset], value: v.pdi })),
    mdi: values.map((v, i) => ({ time: times[i + offset], value: v.mdi })),
  };
}

function calculateATR(highs, lows, closes, times, period) {
  const values = technicalindicators.ATR.calculate({
    high: highs,
    low: lows,
    close: closes,
    period,
  });
  
  const offset = closes.length - values.length;
  return values.map((value, i) => ({ time: times[i + offset], value }));
}

function calculateBBWidth(closes, times, period, stdDev) {
  const bb = technicalindicators.BollingerBands.calculate({ values: closes, period, stdDev });
  const offset = closes.length - bb.length;
  
  return bb.map((v, i) => ({
    time: times[i + offset],
    value: ((v.upper - v.lower) / v.middle) * 100, // Width as percentage
  }));
}

function calculateSqueeze(highs, lows, closes, times) {
  // TTM Squeeze: BB inside Keltner = squeeze ON
  const bbPeriod = 20, bbStdDev = 2;
  const keltnerPeriod = 20, atrPeriod = 10, keltnerMult = 1.5;
  
  const bb = technicalindicators.BollingerBands.calculate({ 
    values: closes, period: bbPeriod, stdDev: bbStdDev 
  });
  
  const ema = technicalindicators.EMA.calculate({ values: closes, period: keltnerPeriod });
  const atr = technicalindicators.ATR.calculate({ 
    high: highs, low: lows, close: closes, period: atrPeriod 
  });
  
  // Alinear arrays al más corto
  const minLen = Math.min(bb.length, ema.length, atr.length);
  const baseOffset = closes.length - minLen;
  
  const result = [];
  
  for (let i = 0; i < minLen; i++) {
    const bbIdx = i + (bb.length - minLen);
    const emaIdx = i + (ema.length - minLen);
    const atrIdx = i + (atr.length - minLen);
    
    const bbUpper = bb[bbIdx].upper;
    const bbLower = bb[bbIdx].lower;
    const keltnerUpper = ema[emaIdx] + atr[atrIdx] * keltnerMult;
    const keltnerLower = ema[emaIdx] - atr[atrIdx] * keltnerMult;
    
    // Squeeze ON when BB inside Keltner
    const squeezeOn = bbLower > keltnerLower && bbUpper < keltnerUpper;
    
    // Momentum (simplified - using linear regression would be better)
    const momentum = closes[baseOffset + i] - ema[emaIdx];
    
    result.push({
      time: times[baseOffset + i],
      value: momentum,
      squeezeOn,
      color: squeezeOn 
        ? 'rgba(239, 68, 68, 0.8)'  // Red dot = squeeze ON
        : 'rgba(16, 185, 129, 0.8)', // Green dot = squeeze OFF
    });
  }
  
  return result;
}

function calculateOBV(closes, volumes, times) {
  const values = technicalindicators.OBV.calculate({ close: closes, volume: volumes });
  const offset = closes.length - values.length;
  return values.map((value, i) => ({ time: times[i + offset], value }));
}

function calculateVWAP(bars, times) {
  // VWAP = Cumulative(TP * Volume) / Cumulative(Volume)
  // TP = (High + Low + Close) / 3
  // Reset cada día para intraday
  
  const result = [];
  let cumulativeTPV = 0;
  let cumulativeVolume = 0;
  let currentDay = null;
  
  for (let i = 0; i < bars.length; i++) {
    const bar = bars[i];
    const barDate = new Date(bar.time * 1000).toDateString();
    
    // Reset al cambiar de día
    if (currentDay !== barDate) {
      cumulativeTPV = 0;
      cumulativeVolume = 0;
      currentDay = barDate;
    }
    
    const tp = (bar.high + bar.low + bar.close) / 3;
    cumulativeTPV += tp * bar.volume;
    cumulativeVolume += bar.volume;
    
    const vwap = cumulativeVolume > 0 ? cumulativeTPV / cumulativeVolume : tp;
    
    result.push({ time: times[i], value: vwap });
  }
  
  return result;
}

// ============================================================================
// RVOL - Relative Volume por Slots CON VOLUMEN ACUMULATIVO (como TradingView)
// ============================================================================

function calculateRVOL(bars, times, lookbackDays, interval) {
  /**
   * Calcula RVOL usando VOLUMEN ACUMULATIVO como TradingView.
   * 
   * Para cada barra:
   * - Calcula el volumen acumulado desde el inicio del día hasta esa barra
   * - Compara con el promedio del volumen acumulado del MISMO SLOT en días anteriores
   * 
   * RVOL = volumen_acumulado_hoy / promedio_volumen_acumulado_mismo_slot_dias_anteriores
   * 
   * Si RVOL = 1.0: volumen acumulado igual al promedio histórico para este momento del día
   * Si RVOL = 2.0: volumen acumulado es el doble del promedio
   * Si RVOL = 0.5: volumen acumulado es la mitad del promedio
   */
  
  if (bars.length < 10) {
    console.warn('[RVOL] Not enough bars for calculation');
    return [];
  }
  
  // Mapear intervalo de string a minutos
  const intervalToMinutes = {
    '1min': 1,
    '5min': 5,
    '15min': 15,
    '30min': 30,
    '1hour': 60,
    '4hour': 240,
    '1day': 1440,
  };
  
  const intervalMinutes = intervalToMinutes[interval] || 0;
  
  // Solo calcular RVOL para intervalos < 60 minutos (intradía)
  if (!intervalMinutes || intervalMinutes >= 60) {
    console.log('[RVOL] Interval', interval, '(', intervalMinutes, 'min) >= 1H, skipping RVOL');
    return [];
  }
  
  console.log('[RVOL] Using interval from parameter:', interval, '=', intervalMinutes, 'minutes');
  
  // PASO 1: Agrupar barras por día y calcular volumen acumulativo
  const dayBars = new Map(); // key: YYYY-MM-DD, value: [{ time, volume, cumVolume, slotKey }]
  
  for (let i = 0; i < bars.length; i++) {
    const bar = bars[i];
    const date = new Date(bar.time * 1000);
    const dateStr = date.toISOString().split('T')[0]; // YYYY-MM-DD
    const slotKey = `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
    
    if (!dayBars.has(dateStr)) {
      dayBars.set(dateStr, []);
    }
    
    dayBars.get(dateStr).push({
      time: bar.time,
      volume: bar.volume,
      slotKey: slotKey,
      originalIndex: i,
    });
  }
  
  // PASO 2: Calcular volumen acumulativo por día
  const daysCumulative = new Map(); // key: YYYY-MM-DD, value: Map<slotKey, cumVolume>
  
  for (const [dateStr, dayData] of dayBars.entries()) {
    // Ordenar barras del día por tiempo
    dayData.sort((a, b) => a.time - b.time);
    
    let cumVolume = 0;
    const slotCumVolumes = new Map();
    
    for (const barData of dayData) {
      cumVolume += barData.volume;
      barData.cumVolume = cumVolume;
      slotCumVolumes.set(barData.slotKey, cumVolume);
    }
    
    daysCumulative.set(dateStr, slotCumVolumes);
  }
  
  const sortedDays = Array.from(dayBars.keys()).sort();
  
  // IMPORTANTE: Debug info
  self.postMessage({ 
    type: 'debug', 
    message: `[RVOL] ${sortedDays.length} days found: ${sortedDays.slice(-5).join(', ')}. Interval: ${interval}. Total bars: ${bars.length}` 
  });
  
  // PASO 3: Para cada barra, calcular RVOL usando volumen acumulativo
  const result = [];
  
  for (let i = 0; i < bars.length; i++) {
    const bar = bars[i];
    const date = new Date(bar.time * 1000);
    const dateStr = date.toISOString().split('T')[0];
    const slotKey = `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
    
    // Obtener volumen acumulativo de esta barra
    const dayData = dayBars.get(dateStr);
    const currentBarData = dayData?.find(d => d.originalIndex === i);
    const currentCumVolume = currentBarData?.cumVolume || 0;
    
    // Buscar volúmenes acumulativos históricos del mismo slot
    const historicalCumVolumes = [];
    
    for (let d = 0; d < sortedDays.length; d++) {
      const historicalDate = sortedDays[d];
      if (historicalDate >= dateStr) continue; // Solo días anteriores
      
      const historicalDayCum = daysCumulative.get(historicalDate);
      if (historicalDayCum && historicalDayCum.has(slotKey)) {
        historicalCumVolumes.push(historicalDayCum.get(slotKey));
      }
    }
    
    // Usar los últimos N días
    const recentCumVolumes = historicalCumVolumes.slice(-lookbackDays);
    
    let rvol = 1.0;
    
    if (recentCumVolumes.length >= 1 && currentCumVolume > 0) {
      const avgCumVolume = recentCumVolumes.reduce((sum, v) => sum + v, 0) / recentCumVolumes.length;
      if (avgCumVolume > 0) {
        rvol = currentCumVolume / avgCumVolume;
      }
    }
    
    // Colorear según RVOL (como TradingView - verde/rojo por dirección de vela)
    let color;
    const isGreen = bar.close >= bar.open;
    
    // Intensidad basada en RVOL
    const intensity = Math.min(Math.max(rvol * 130, 130), 255);
    
    if (isGreen) {
      color = `rgba(0, ${Math.round(intensity)}, 0, ${Math.min(0.4 + rvol * 0.2, 1.0)})`;
    } else {
      color = `rgba(${Math.round(intensity)}, 0, 0, ${Math.min(0.4 + rvol * 0.2, 1.0)})`;
    }
    
    result.push({
      time: times[i],
      value: Math.round(rvol * 100) / 100,
      color: color
    });
  }
  
  // Log muestra de los últimos valores
  const lastValues = result.slice(-5).map(r => r.value);
  console.log('[RVOL] Last 5 cumulative values:', lastValues, 'Total bars:', result.length);
  
  return result;
}

// Log de inicialización
console.log('[IndicatorWorker] Initialized with indicators:', Object.keys(INDICATOR_CONFIGS));

