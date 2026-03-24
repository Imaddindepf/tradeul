/**
 * useIndicatorWorker - Hook for calculating technical indicators in Web Worker
 *
 * DYNAMIC INSTANCES:
 * - Accepts WorkerIndicatorConfig[] instead of fixed IndicatorType[]
 * - Returns results keyed by instance ID
 * - Backward compatible with old string-based API
 */

import { useRef, useCallback, useEffect, useState } from 'react';

// ============================================================================
// TYPES
// ============================================================================

export interface ChartBar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface WorkerIndicatorConfig {
  id: string;
  type: string;
  params: Record<string, number | string>;
}

interface IndicatorDataPoint {
  time: number;
  value: number;
  color?: string;
}

export interface BandIndicatorData {
  upper: IndicatorDataPoint[];
  middle: IndicatorDataPoint[];
  lower: IndicatorDataPoint[];
}

interface MACDData {
  macd: IndicatorDataPoint[];
  signal: IndicatorDataPoint[];
  histogram: IndicatorDataPoint[];
}

interface StochData {
  k: IndicatorDataPoint[];
  d: IndicatorDataPoint[];
}

interface ADXData {
  adx: IndicatorDataPoint[];
  pdi: IndicatorDataPoint[];
  mdi: IndicatorDataPoint[];
}

interface SqueezeData extends IndicatorDataPoint {
  squeezeOn: boolean;
}

/** Result for a single instance */
interface InstanceResult {
  type: string;
  data: IndicatorDataPoint[] | BandIndicatorData | MACDData | StochData | ADXData | SqueezeData[];
}

/** All results keyed by instance ID */
export type IndicatorResults = Record<string, InstanceResult>;

// Legacy types for backward compat
export type IndicatorType = string;

interface WorkerMessage {
  type: 'result' | 'error' | 'cache_cleared' | 'debug';
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

  const pendingCallbacksRef = useRef<Map<number, (results: IndicatorResults) => void>>(new Map());
  const lastCalculationRef = useRef<{ ticker: string; barCount: number; indicators: string; interval?: string } | null>(null);

  // Initialize Worker
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
            break;

          case 'cache_cleared':
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

  // Calculate indicators (async, non-blocking)
  const calculate = useCallback((
    ticker: string,
    bars: ChartBar[],
    indicators: WorkerIndicatorConfig[],
    interval?: string,
    onResult?: (results: IndicatorResults) => void
  ) => {
    if (!workerRef.current || !isReady) return;
    if (!bars.length || !indicators.length) return;

    // Check if we need to recalculate
    const indicatorsKey = indicators.map(i => `${i.id}:${i.type}:${JSON.stringify(i.params)}`).sort().join(',');
    const lastCalc = lastCalculationRef.current;

    if (
      lastCalc &&
      lastCalc.ticker === ticker &&
      lastCalc.barCount === bars.length &&
      lastCalc.indicators === indicatorsKey &&
      lastCalc.interval === interval
    ) {
      if (onResult && results) {
        onResult(results);
      }
      return;
    }

    setIsCalculating(true);
    setError(null);

    const requestId = ++requestIdRef.current;

    if (onResult) {
      pendingCallbacksRef.current.set(requestId, onResult);
    }

    lastCalculationRef.current = { ticker, barCount: bars.length, indicators: indicatorsKey, interval };

    workerRef.current.postMessage({
      type: 'calculate',
      requestId,
      ticker,
      bars,
      indicators,
      interval,
    });
  }, [isReady, results]);

  // Clear cache
  const clearCache = useCallback((ticker: string) => {
    workerRef.current?.postMessage({ type: 'clear_cache', ticker });
    lastCalculationRef.current = null;
    setResults(null);
  }, []);

  // Force recalculate (ignore cache)
  const forceRecalculate = useCallback((
    ticker: string,
    bars: ChartBar[],
    indicators: WorkerIndicatorConfig[],
    interval?: string,
    onResult?: (results: IndicatorResults) => void
  ) => {
    lastCalculationRef.current = null;
    calculate(ticker, bars, indicators, interval, onResult);
  }, [calculate]);

  return {
    isReady,
    isCalculating,
    results,
    error,
    lastDuration,
    calculate,
    clearCache,
    forceRecalculate,
  };
}

export default useIndicatorWorker;
