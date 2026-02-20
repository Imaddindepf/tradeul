/**
 * useIndicatorWorker - Hook para calcular indicadores técnicos en Web Worker
 * 
 * ARQUITECTURA 2025:
 * - NO bloquea el main thread (WebSockets, Scanner, Quotes siguen fluyendo)
 * - Soporta lazy loading (recalcula cuando llegan más barras)
 * - Cache inteligente para evitar recálculos innecesarios
 * - API simple y type-safe
 * 
 * USO:
 * const { calculate, results, isCalculating } = useIndicatorWorker();
 * 
 * useEffect(() => {
 *   calculate(ticker, bars, ['rsi', 'macd', 'bb']);
 * }, [bars]);
 */

import { useRef, useCallback, useEffect, useState } from 'react';

// ============================================================================
// TYPES
// ============================================================================

export type OverlayIndicator =
  | 'sma20' | 'sma50' | 'sma200'
  | 'ema12' | 'ema26'
  | 'bb' | 'keltner' | 'vwap';

export type OscillatorIndicator =
  | 'rsi' | 'macd' | 'stoch' | 'adx';

export type PanelIndicator =
  | 'atr' | 'bbWidth' | 'squeeze' | 'obv' | 'rvol';

export type IndicatorType = OverlayIndicator | OscillatorIndicator | PanelIndicator;

export interface ChartBar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface IndicatorDataPoint {
  time: number;
  value: number;
  color?: string;
}

export interface BandIndicatorData {
  upper: IndicatorDataPoint[];
  middle: IndicatorDataPoint[];
  lower: IndicatorDataPoint[];
}

export interface MACDData {
  macd: IndicatorDataPoint[];
  signal: IndicatorDataPoint[];
  histogram: IndicatorDataPoint[];
}

export interface StochData {
  k: IndicatorDataPoint[];
  d: IndicatorDataPoint[];
}

export interface ADXData {
  adx: IndicatorDataPoint[];
  pdi: IndicatorDataPoint[];  // +DI
  mdi: IndicatorDataPoint[];  // -DI
}

export interface SqueezeData extends IndicatorDataPoint {
  squeezeOn: boolean;
}

export interface IndicatorConfig {
  type: 'overlay' | 'oscillator' | 'panel';
  period?: number;
  panel?: string;
  range?: [number, number];
  [key: string]: any;
}

export interface IndicatorResults {
  overlays: {
    sma20?: IndicatorDataPoint[];
    sma50?: IndicatorDataPoint[];
    sma200?: IndicatorDataPoint[];
    ema12?: IndicatorDataPoint[];
    ema26?: IndicatorDataPoint[];
    bb?: BandIndicatorData;
    keltner?: BandIndicatorData;
    vwap?: IndicatorDataPoint[];
  };
  panels: {
    rsi?: { data: IndicatorDataPoint[]; config: IndicatorConfig };
    macd?: { data: MACDData; config: IndicatorConfig };
    stoch?: { data: StochData; config: IndicatorConfig };
    adx?: { data: ADXData; config: IndicatorConfig };
    atr?: { data: IndicatorDataPoint[]; config: IndicatorConfig };
    bbWidth?: { data: IndicatorDataPoint[]; config: IndicatorConfig };
    squeeze?: { data: SqueezeData[]; config: IndicatorConfig };
    obv?: { data: IndicatorDataPoint[]; config: IndicatorConfig };
    rvol?: { data: IndicatorDataPoint[]; config: IndicatorConfig };
  };
}

interface WorkerMessage {
  type: 'result' | 'error' | 'cache_cleared' | 'config' | 'debug';
  requestId?: number;
  ticker?: string;
  data?: IndicatorResults;
  error?: string;
  message?: string;
  barCount?: number;
  duration?: number;
}

// ============================================================================
// CONSTANTS
// ============================================================================

const WORKER_PATH = '/workers/indicators.worker.js';

// Indicadores que van en paneles separados (como TradingView)
export const PANEL_INDICATORS: Record<string, { label: string; range?: [number, number]; lines?: { value: number; color: string; style: string }[] }> = {
  rsi: {
    label: 'RSI (14)',
    range: [0, 100],
    lines: [
      { value: 70, color: 'rgba(239, 68, 68, 0.5)', style: 'dashed' },
      { value: 30, color: 'rgba(16, 185, 129, 0.5)', style: 'dashed' },
    ]
  },
  macd: { label: 'MACD (12,26,9)' },
  stoch: {
    label: 'Stochastic (14,3)',
    range: [0, 100],
    lines: [
      { value: 80, color: 'rgba(239, 68, 68, 0.5)', style: 'dashed' },
      { value: 20, color: 'rgba(16, 185, 129, 0.5)', style: 'dashed' },
    ]
  },
  adx: {
    label: 'ADX (14)',
    range: [0, 100],
    lines: [
      { value: 25, color: 'rgba(100, 116, 139, 0.5)', style: 'dashed' },
    ]
  },
  atr: { label: 'ATR (14)' },
  bbWidth: { label: 'BB Width %' },
  squeeze: { label: 'TTM Squeeze' },
  obv: { label: 'OBV' },
  rvol: {
    label: 'RVOL',
    lines: [
      { value: 1.0, color: 'rgba(100, 116, 139, 0.5)', style: 'dashed' }, // Línea de referencia en 1.0
      { value: 2.0, color: 'rgba(16, 185, 129, 0.4)', style: 'dashed' }, // Alto
    ]
  },
};

// Indicadores que van sobre el precio (overlays)
export const OVERLAY_INDICATORS: Record<string, { label: string; color: string; lineWidth?: number }> = {
  sma20: { label: 'SMA 20', color: '#f59e0b', lineWidth: 2 },
  sma50: { label: 'SMA 50', color: '#6366f1', lineWidth: 2 },
  sma200: { label: 'SMA 200', color: '#ef4444', lineWidth: 2 },
  ema12: { label: 'EMA 12', color: '#ec4899', lineWidth: 1 },
  ema26: { label: 'EMA 26', color: '#8b5cf6', lineWidth: 1 },
  bb: { label: 'Bollinger Bands', color: '#3b82f6' },
  keltner: { label: 'Keltner Channels', color: '#14b8a6' },
  vwap: { label: 'VWAP', color: '#f97316', lineWidth: 2 },
};

// ============================================================================
// HOOK
// ============================================================================

export function useIndicatorWorker() {
  const workerRef = useRef<Worker | null>(null);
  const requestIdRef = useRef(0);
  const [isReady, setIsReady] = useState(false);
  const [isCalculating, setIsCalculating] = useState(false);
  const [results, setResults] = useState<IndicatorResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastDuration, setLastDuration] = useState<number>(0);

  // Callbacks pendientes por requestId
  const pendingCallbacksRef = useRef<Map<number, (results: IndicatorResults) => void>>(new Map());

  // Último cálculo para detectar si necesitamos recalcular
  const lastCalculationRef = useRef<{ ticker: string; barCount: number; indicators: string[]; interval?: string } | null>(null);

  // ============================================================================
  // Inicializar Worker
  // ============================================================================

  useEffect(() => {
    if (typeof Worker === 'undefined') {
      setError('Web Workers not supported');
      return;
    }

    try {
      workerRef.current = new Worker(WORKER_PATH);

      workerRef.current.onmessage = (event: MessageEvent<WorkerMessage>) => {
        const { type, requestId, data, error: workerError, duration } = event.data;


        switch (type) {
          case 'result':
            setIsCalculating(false);
            setError(null);
            if (data) {
              setResults(data);
            }
            if (duration) {
              setLastDuration(duration);
            }
            // Ejecutar callback si existe
            if (requestId !== undefined) {
              const callback = pendingCallbacksRef.current.get(requestId);
              if (callback && data) {
                callback(data);
                pendingCallbacksRef.current.delete(requestId);
              }
            }
            break;

          case 'error':
            setIsCalculating(false);
            setError(workerError || 'Unknown error');
            console.error('[useIndicatorWorker] Error:', workerError);
            break;

          case 'cache_cleared':
            // Cache limpiado exitosamente
            break;

          case 'debug':
            break;
        }
      };

      workerRef.current.onerror = (err) => {
        console.error('[useIndicatorWorker] Worker error:', err);
        setError('Worker initialization failed');
        setIsCalculating(false);
      };

      setIsReady(true);

    } catch (err) {
      console.error('[useIndicatorWorker] Failed to create worker:', err);
      setError('Failed to create worker');
    }

    return () => {
      workerRef.current?.terminate();
      workerRef.current = null;
      pendingCallbacksRef.current.clear();
    };
  }, []);

  // ============================================================================
  // Calcular indicadores (async, no bloqueante)
  // ============================================================================

  const calculate = useCallback((
    ticker: string,
    bars: ChartBar[],
    indicators: IndicatorType[],
    interval?: string, // Agregar intervalo explícito (1min, 5min, 15min, etc.)
    onResult?: (results: IndicatorResults) => void
  ) => {
    if (!workerRef.current || !isReady) {
      return;
    }

    if (!bars.length || !indicators.length) {
      return;
    }

    // Verificar si realmente necesitamos recalcular
    const lastCalc = lastCalculationRef.current;
    const indicatorsKey = indicators.sort().join(',');

    if (
      lastCalc &&
      lastCalc.ticker === ticker &&
      lastCalc.barCount === bars.length &&
      lastCalc.indicators.sort().join(',') === indicatorsKey &&
      lastCalc.interval === interval
    ) {
      // No hay cambios, usar resultados en cache
      if (onResult && results) {
        onResult(results);
      }
      return;
    }

    setIsCalculating(true);
    setError(null);

    const requestId = ++requestIdRef.current;

    // Guardar callback si existe
    if (onResult) {
      pendingCallbacksRef.current.set(requestId, onResult);
    }

    // Guardar info del último cálculo
    lastCalculationRef.current = { ticker, barCount: bars.length, indicators: [...indicators], interval };

    // Enviar al worker (NO BLOQUEA)
    workerRef.current.postMessage({
      type: 'calculate',
      requestId,
      ticker,
      bars,
      indicators,
      interval, // Pasar intervalo al worker
      incremental: false,
    });
  }, [isReady, results]);

  // ============================================================================
  // Calcular solo para actualización en tiempo real (última barra)
  // ============================================================================

  const calculateIncremental = useCallback((
    ticker: string,
    bars: ChartBar[],
    indicators: IndicatorType[],
    onResult?: (results: IndicatorResults) => void
  ) => {
    if (!workerRef.current || !isReady || !bars.length) return;

    const requestId = ++requestIdRef.current;

    if (onResult) {
      pendingCallbacksRef.current.set(requestId, onResult);
    }

    // Para updates incrementales, enviamos todas las barras pero el worker
    // puede optimizar recalculando solo lo necesario
    workerRef.current.postMessage({
      type: 'calculate_single',
      requestId,
      ticker,
      bars,
      indicators,
    });
  }, [isReady]);

  // ============================================================================
  // Limpiar cache
  // ============================================================================

  const clearCache = useCallback((ticker: string) => {
    workerRef.current?.postMessage({
      type: 'clear_cache',
      ticker,
    });
    lastCalculationRef.current = null;
    setResults(null);
  }, []);

  // ============================================================================
  // Forzar recálculo (ignorar cache)
  // ============================================================================

  const forceRecalculate = useCallback((
    ticker: string,
    bars: ChartBar[],
    indicators: IndicatorType[],
    interval?: string,
    onResult?: (results: IndicatorResults) => void
  ) => {
    lastCalculationRef.current = null;
    calculate(ticker, bars, indicators, interval, onResult);
  }, [calculate]);

  // ============================================================================
  // Return
  // ============================================================================

  return {
    // Estado
    isReady,
    isCalculating,
    results,
    error,
    lastDuration,

    // Métodos
    calculate,
    calculateIncremental,
    clearCache,
    forceRecalculate,

    // Constantes útiles
    OVERLAY_INDICATORS,
    PANEL_INDICATORS,
  };
}

export default useIndicatorWorker;

