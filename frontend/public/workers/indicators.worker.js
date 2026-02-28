/**
 * Dedicated Worker for technical indicator calculations
 *
 * DYNAMIC INSTANCES:
 * - Accepts { id, type, params } configs instead of fixed indicator names
 * - Returns results keyed by instance ID
 * - Each instance can have custom periods/parameters
 */

/* global self, importScripts */

importScripts('/workers/regenerator-runtime.js');
self.window = self.window || {};
importScripts('/workers/technicalindicators.js');
var technicalindicators = self.window;

console.log('[Worker] technicalindicators loaded:', typeof technicalindicators.SMA);

// Cache
const cache = new Map();
const MAX_WORKER_CACHE = 100;

// ============================================================================
// MESSAGE HANDLER
// ============================================================================

self.onmessage = function(event) {
  const { type, requestId, ticker, bars, indicators, interval } = event.data;

  switch (type) {
    case 'calculate':
      handleCalculate(requestId, ticker, bars, indicators, interval);
      break;

    case 'calculate_single':
      handleCalculate(requestId, ticker, bars, indicators, null);
      break;

    case 'clear_cache':
      cache.delete(ticker);
      self.postMessage({ type: 'cache_cleared', ticker });
      break;
  }
};

// ============================================================================
// MAIN CALCULATION
// ============================================================================

function handleCalculate(requestId, ticker, bars, requestedIndicators, interval) {
  const startTime = performance.now();

  try {
    const closes = bars.map(function(b) { return b.close; });
    const highs = bars.map(function(b) { return b.high; });
    const lows = bars.map(function(b) { return b.low; });
    const volumes = bars.map(function(b) { return b.volume; });
    const times = bars.map(function(b) { return b.time; });

    // Results keyed by instance ID
    var results = {};

    for (var i = 0; i < requestedIndicators.length; i++) {
      var indicator = requestedIndicators[i];

      // Support both old format (string) and new format ({ id, type, params })
      var id, indicatorType, params;
      if (typeof indicator === 'string') {
        // Legacy format
        id = indicator;
        indicatorType = mapLegacyType(indicator);
        params = getLegacyParams(indicator);
      } else {
        id = indicator.id;
        indicatorType = indicator.type;
        params = indicator.params || {};
      }

      try {
        var result = calculateByType(
          indicatorType,
          params,
          { closes: closes, highs: highs, lows: lows, volumes: volumes, times: times, bars: bars, interval: interval }
        );

        if (result) {
          results[id] = {
            type: indicatorType,
            data: result,
          };
        }
      } catch (err) {
        console.error('[Worker] Error calculating ' + id + ':', err.message);
      }
    }

    var duration = performance.now() - startTime;

    // Cache
    cache.set(ticker, { barCount: bars.length, results: results, timestamp: Date.now() });
    if (cache.size > MAX_WORKER_CACHE) {
      var keys = Array.from(cache.keys());
      for (var j = 0; j < 20; j++) cache.delete(keys[j]);
    }

    self.postMessage({
      type: 'result',
      requestId: requestId,
      ticker: ticker,
      data: results,
      barCount: bars.length,
      duration: Math.round(duration),
    });

  } catch (error) {
    self.postMessage({
      type: 'error',
      requestId: requestId,
      ticker: ticker,
      error: error.message,
    });
  }
}

// ============================================================================
// LEGACY SUPPORT: Map old fixed names to types
// ============================================================================

function mapLegacyType(name) {
  if (name === 'sma20' || name === 'sma50' || name === 'sma200') return 'sma';
  if (name === 'ema12' || name === 'ema26') return 'ema';
  return name;
}

function getLegacyParams(name) {
  switch (name) {
    case 'sma20': return { length: 20 };
    case 'sma50': return { length: 50 };
    case 'sma200': return { length: 200 };
    case 'ema12': return { length: 12 };
    case 'ema26': return { length: 26 };
    case 'bb': return { length: 20, mult: 2 };
    case 'keltner': return { length: 20, mult: 1.5 };
    case 'rsi': return { length: 14 };
    case 'macd': return { fastLength: 12, slowLength: 26, signalLength: 9 };
    case 'stoch': return { kLength: 14, kSmooth: 1, dSmooth: 3 };
    case 'adx': return { length: 14 };
    case 'atr': return { length: 14 };
    case 'squeeze': return { bbLength: 20, bbMult: 2, kcLength: 20, kcMult: 1.5 };
    default: return {};
  }
}

// ============================================================================
// CALCULATE BY TYPE (dynamic params)
// ============================================================================

function calculateByType(type, params, data) {
  var closes = data.closes, highs = data.highs, lows = data.lows;
  var volumes = data.volumes, times = data.times, bars = data.bars, interval = data.interval;

  switch (type) {
    case 'sma':
      return calculateSMA(closes, times, Number(params.length) || 20);

    case 'ema':
      return calculateEMA(closes, times, Number(params.length) || 12);

    case 'bb':
      return calculateBollingerBands(closes, times, Number(params.length) || 20, Number(params.mult) || 2);

    case 'keltner':
      return calculateKeltner(highs, lows, closes, times, {
        period: Number(params.length) || 20,
        atrPeriod: Number(params.length) || 20,
        multiplier: Number(params.mult) || 1.5
      });

    case 'rsi':
      return calculateRSI(closes, times, Number(params.length) || 14);

    case 'macd':
      return calculateMACD(closes, times, {
        fast: Number(params.fastLength) || 12,
        slow: Number(params.slowLength) || 26,
        signal: Number(params.signalLength) || 9
      });

    case 'stoch':
      return calculateStochastic(highs, lows, closes, times, {
        period: Number(params.kLength) || 14,
        signalPeriod: Number(params.dSmooth) || 3
      });

    case 'adx':
      return calculateADX(highs, lows, closes, times, Number(params.length) || 14);

    case 'atr':
      return calculateATR(highs, lows, closes, times, Number(params.length) || 14);

    case 'squeeze':
      return calculateSqueeze(highs, lows, closes, times, params);

    case 'obv':
      return calculateOBV(closes, volumes, times);

    case 'vwap':
      return calculateVWAP(bars, times);

    case 'rvol':
      return calculateRVOL(bars, times, Number(params.lookbackDays) || 5, interval);

    default:
      console.warn('[Worker] Unknown indicator type:', type);
      return null;
  }
}

// ============================================================================
// IMPLEMENTATIONS
// ============================================================================

function calculateSMA(closes, times, period) {
  var values = technicalindicators.SMA.calculate({ values: closes, period: period });
  var offset = closes.length - values.length;
  return values.map(function(value, i) { return { time: times[i + offset], value: value }; });
}

function calculateEMA(closes, times, period) {
  var values = technicalindicators.EMA.calculate({ values: closes, period: period });
  var offset = closes.length - values.length;
  return values.map(function(value, i) { return { time: times[i + offset], value: value }; });
}

function calculateBollingerBands(closes, times, period, stdDev) {
  var values = technicalindicators.BollingerBands.calculate({ values: closes, period: period, stdDev: stdDev });
  var offset = closes.length - values.length;
  return {
    upper: values.map(function(v, i) { return { time: times[i + offset], value: v.upper }; }),
    middle: values.map(function(v, i) { return { time: times[i + offset], value: v.middle }; }),
    lower: values.map(function(v, i) { return { time: times[i + offset], value: v.lower }; }),
  };
}

function calculateKeltner(highs, lows, closes, times, config) {
  var ema = technicalindicators.EMA.calculate({ values: closes, period: config.period });
  var atr = technicalindicators.ATR.calculate({ high: highs, low: lows, close: closes, period: config.atrPeriod });

  var minLen = Math.min(ema.length, atr.length);
  var emaOffset = closes.length - ema.length;
  var atrOffset = closes.length - atr.length;
  var startOffset = Math.max(emaOffset, atrOffset);

  var result = { upper: [], middle: [], lower: [] };

  for (var i = 0; i < minLen; i++) {
    var emaIdx = i + (ema.length - minLen);
    var atrIdx = i + (atr.length - minLen);
    var timeIdx = startOffset + i;

    if (timeIdx < times.length) {
      var mid = ema[emaIdx];
      var band = atr[atrIdx] * config.multiplier;
      result.upper.push({ time: times[timeIdx], value: mid + band });
      result.middle.push({ time: times[timeIdx], value: mid });
      result.lower.push({ time: times[timeIdx], value: mid - band });
    }
  }

  return result;
}

function calculateRSI(closes, times, period) {
  var values = technicalindicators.RSI.calculate({ values: closes, period: period });
  var offset = closes.length - values.length;
  return values.map(function(value, i) { return { time: times[i + offset], value: value }; });
}

function calculateMACD(closes, times, config) {
  var values = technicalindicators.MACD.calculate({
    values: closes,
    fastPeriod: config.fast,
    slowPeriod: config.slow,
    signalPeriod: config.signal,
    SimpleMAOscillator: false,
    SimpleMASignal: false,
  });

  var offset = closes.length - values.length;

  return {
    macd: values.map(function(v, i) { return { time: times[i + offset], value: v.MACD || 0 }; }),
    signal: values.map(function(v, i) { return { time: times[i + offset], value: v.signal || 0 }; }),
    histogram: values.map(function(v, i) {
      return {
        time: times[i + offset],
        value: v.histogram || 0,
        color: (v.histogram || 0) >= 0 ? 'rgba(16, 185, 129, 0.6)' : 'rgba(239, 68, 68, 0.6)'
      };
    }),
  };
}

function calculateStochastic(highs, lows, closes, times, config) {
  var values = technicalindicators.Stochastic.calculate({
    high: highs, low: lows, close: closes,
    period: config.period,
    signalPeriod: config.signalPeriod,
  });

  var offset = closes.length - values.length;
  return {
    k: values.map(function(v, i) { return { time: times[i + offset], value: v.k }; }),
    d: values.map(function(v, i) { return { time: times[i + offset], value: v.d }; }),
  };
}

function calculateADX(highs, lows, closes, times, period) {
  var values = technicalindicators.ADX.calculate({
    high: highs, low: lows, close: closes, period: period,
  });

  var offset = closes.length - values.length;
  return {
    adx: values.map(function(v, i) { return { time: times[i + offset], value: v.adx }; }),
    pdi: values.map(function(v, i) { return { time: times[i + offset], value: v.pdi }; }),
    mdi: values.map(function(v, i) { return { time: times[i + offset], value: v.mdi }; }),
  };
}

function calculateATR(highs, lows, closes, times, period) {
  var values = technicalindicators.ATR.calculate({
    high: highs, low: lows, close: closes, period: period,
  });
  var offset = closes.length - values.length;
  return values.map(function(value, i) { return { time: times[i + offset], value: value }; });
}

function calculateSqueeze(highs, lows, closes, times, params) {
  var bbPeriod = Number(params.bbLength) || 20;
  var bbStdDev = Number(params.bbMult) || 2;
  var keltnerPeriod = Number(params.kcLength) || 20;
  var atrPeriod = keltnerPeriod;
  var keltnerMult = Number(params.kcMult) || 1.5;

  var bb = technicalindicators.BollingerBands.calculate({ values: closes, period: bbPeriod, stdDev: bbStdDev });
  var ema = technicalindicators.EMA.calculate({ values: closes, period: keltnerPeriod });
  var atr = technicalindicators.ATR.calculate({ high: highs, low: lows, close: closes, period: atrPeriod });

  var minLen = Math.min(bb.length, ema.length, atr.length);
  var baseOffset = closes.length - minLen;

  var result = [];

  for (var i = 0; i < minLen; i++) {
    var bbIdx = i + (bb.length - minLen);
    var emaIdx = i + (ema.length - minLen);
    var atrIdx = i + (atr.length - minLen);

    var bbUpper = bb[bbIdx].upper;
    var bbLower = bb[bbIdx].lower;
    var keltnerUpper = ema[emaIdx] + atr[atrIdx] * keltnerMult;
    var keltnerLower = ema[emaIdx] - atr[atrIdx] * keltnerMult;

    var squeezeOn = bbLower > keltnerLower && bbUpper < keltnerUpper;
    var momentum = closes[baseOffset + i] - ema[emaIdx];

    result.push({
      time: times[baseOffset + i],
      value: momentum,
      squeezeOn: squeezeOn,
      color: squeezeOn ? 'rgba(239, 68, 68, 0.8)' : 'rgba(16, 185, 129, 0.8)',
    });
  }

  return result;
}

function calculateOBV(closes, volumes, times) {
  var values = technicalindicators.OBV.calculate({ close: closes, volume: volumes });
  var offset = closes.length - values.length;
  return values.map(function(value, i) { return { time: times[i + offset], value: value }; });
}

function calculateVWAP(bars, times) {
  var result = [];
  var cumulativeTPV = 0;
  var cumulativeVolume = 0;
  var currentDay = null;

  for (var i = 0; i < bars.length; i++) {
    var bar = bars[i];
    var barDate = new Date(bar.time * 1000).toDateString();

    if (currentDay !== barDate) {
      cumulativeTPV = 0;
      cumulativeVolume = 0;
      currentDay = barDate;
    }

    var tp = (bar.high + bar.low + bar.close) / 3;
    cumulativeTPV += tp * bar.volume;
    cumulativeVolume += bar.volume;

    var vwap = cumulativeVolume > 0 ? cumulativeTPV / cumulativeVolume : tp;
    result.push({ time: times[i], value: vwap });
  }

  return result;
}

function calculateRVOL(bars, times, lookbackDays, interval) {
  if (bars.length < 10) return [];

  var intervalToMinutes = {
    '1min': 1, '5min': 5, '15min': 15, '30min': 30,
    '1hour': 60, '4hour': 240, '1day': 1440,
  };

  var intervalMinutes = intervalToMinutes[interval] || 0;
  if (!intervalMinutes || intervalMinutes >= 60) return [];

  var dayBars = new Map();

  for (var i = 0; i < bars.length; i++) {
    var bar = bars[i];
    var date = new Date(bar.time * 1000);
    var dateStr = date.toISOString().split('T')[0];
    var slotKey = String(date.getHours()).padStart(2, '0') + ':' + String(date.getMinutes()).padStart(2, '0');

    if (!dayBars.has(dateStr)) dayBars.set(dateStr, []);
    dayBars.get(dateStr).push({ time: bar.time, volume: bar.volume, slotKey: slotKey, originalIndex: i });
  }

  var daysCumulative = new Map();

  for (var entry of dayBars.entries()) {
    var dateStr2 = entry[0];
    var dayData = entry[1];
    dayData.sort(function(a, b) { return a.time - b.time; });

    var cumVolume = 0;
    var slotCumVolumes = new Map();

    for (var j = 0; j < dayData.length; j++) {
      cumVolume += dayData[j].volume;
      dayData[j].cumVolume = cumVolume;
      slotCumVolumes.set(dayData[j].slotKey, cumVolume);
    }

    daysCumulative.set(dateStr2, slotCumVolumes);
  }

  var sortedDays = Array.from(dayBars.keys()).sort();
  var result = [];

  for (var i2 = 0; i2 < bars.length; i2++) {
    var bar2 = bars[i2];
    var date2 = new Date(bar2.time * 1000);
    var dateStr3 = date2.toISOString().split('T')[0];
    var slotKey2 = String(date2.getHours()).padStart(2, '0') + ':' + String(date2.getMinutes()).padStart(2, '0');

    var dayData2 = dayBars.get(dateStr3);
    var currentBarData = null;
    if (dayData2) {
      for (var k = 0; k < dayData2.length; k++) {
        if (dayData2[k].originalIndex === i2) { currentBarData = dayData2[k]; break; }
      }
    }
    var currentCumVolume = currentBarData ? currentBarData.cumVolume : 0;

    var historicalCumVolumes = [];
    for (var d = 0; d < sortedDays.length; d++) {
      var hDate = sortedDays[d];
      if (hDate >= dateStr3) continue;
      var hDayCum = daysCumulative.get(hDate);
      if (hDayCum && hDayCum.has(slotKey2)) {
        historicalCumVolumes.push(hDayCum.get(slotKey2));
      }
    }

    var recentCumVolumes = historicalCumVolumes.slice(-lookbackDays);
    var rvol = 1.0;

    if (recentCumVolumes.length >= 1 && currentCumVolume > 0) {
      var avgCumVolume = recentCumVolumes.reduce(function(s, v) { return s + v; }, 0) / recentCumVolumes.length;
      if (avgCumVolume > 0) rvol = currentCumVolume / avgCumVolume;
    }

    var isGreen = bar2.close >= bar2.open;
    var intensity = Math.min(Math.max(rvol * 130, 130), 255);
    var color;
    if (isGreen) {
      color = 'rgba(0, ' + Math.round(intensity) + ', 0, ' + Math.min(0.4 + rvol * 0.2, 1.0) + ')';
    } else {
      color = 'rgba(' + Math.round(intensity) + ', 0, 0, ' + Math.min(0.4 + rvol * 0.2, 1.0) + ')';
    }

    result.push({ time: times[i2], value: Math.round(rvol * 100) / 100, color: color });
  }

  return result;
}

console.log('[IndicatorWorker] Initialized - dynamic instance support enabled');
