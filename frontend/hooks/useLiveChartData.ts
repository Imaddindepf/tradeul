/**
 * useLiveChartData - Hook para datos de chart con actualización en tiempo real
 * 
 * ARQUITECTURA:
 * 1. Datos históricos cargados via API → setData (una sola vez)
 * 2. Actualizaciones en tiempo real via WebSocket → callback imperativo (sin re-render)
 * 3. Page Lifecycle recovery: visibilitychange + freeze/resume (Chrome 133+)
 *    Al volver de background, fetch solo barras faltantes + re-subscribe WS.
 */

import { useState, useEffect, useRef, useCallback } from 'react';

// ============================================================================
// Types
// ============================================================================

export interface ChartBar {
  time: number;      // Unix timestamp in seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export type ChartInterval = '1min' | '2min' | '5min' | '15min' | '30min' | '1hour' | '4hour' | '12hour' | '1day' | '1week' | '1month' | '3month' | '1year';

// Handler que el chart registra para recibir updates sin re-render
export type RealtimeUpdateHandler = (bar: ChartBar, isNewBar: boolean) => void;

// ============================================================================
// Constants
// ============================================================================

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const INTERVAL_SECONDS: Record<ChartInterval, number> = {
  '1min': 60,
  '2min': 120,
  '5min': 300,
  '15min': 900,
  '30min': 1800,
  '1hour': 3600,
  '4hour': 14400,
  '12hour': 43200,
  '1day': 86400,
  '1week': 604800,
  '1month': 2592000,
  '3month': 7776000,
  '1year': 31536000,
};

// Recovery thresholds
const GAP_IGNORE_MS = 5_000;       // < 5s away → do nothing
const GAP_PARTIAL_MAX_MS = 300_000; // < 5min → partial fetch
// > 5min → full refetch

// ============================================================================
// WebSocket Manager Access
// ============================================================================

import { useRxWebSocket } from './useRxWebSocket';

// ============================================================================
// Hook
// ============================================================================

export function useLiveChartData(
  ticker: string,
  interval: ChartInterval,
  replayTo?: number | null,
) {
  // State (solo para carga inicial, NO para updates en tiempo real)
  const [data, setData] = useState<ChartBar[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [oldestTime, setOldestTime] = useState<number | null>(null);
  const [isLive, setIsLive] = useState(false);

  // WebSocket connection (uses the existing singleton from useRxWebSocket)
  const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';
  const { isConnected, messages$, send } = useRxWebSocket(wsUrl);

  // Refs para acceso rápido sin re-renders
  const lastBarRef = useRef<ChartBar | null>(null);
  const tickerRef = useRef(ticker);
  const intervalRef = useRef(interval);
  const dataRef = useRef<ChartBar[]>([]);
  const subscribedRef = useRef(false);
  const isLoadingMoreRef = useRef(false);
  const isLoadingForwardRef = useRef(false);
  const hasMoreRef = useRef(false);
  const oldestTimeRef = useRef<number | null>(null);

  // Handler registrado por el chart para updates imperativos
  const updateHandlerRef = useRef<RealtimeUpdateHandler | null>(null);

  // Page Lifecycle: track when the tab went hidden
  const hiddenAtRef = useRef<number | null>(null);
  const isFrozenRef = useRef(false);

  useEffect(() => {
    tickerRef.current = ticker;
    intervalRef.current = interval;
  }, [ticker, interval]);

  useEffect(() => {
    dataRef.current = data;
    if (data.length > 0) {
      lastBarRef.current = data[data.length - 1];
    }
  }, [data]);

  useEffect(() => { hasMoreRef.current = hasMore; }, [hasMore]);
  useEffect(() => { oldestTimeRef.current = oldestTime; }, [oldestTime]);

  // ============================================================================
  // Registrar handler para updates (llamado por TradingChart)
  // ============================================================================

  const registerUpdateHandler = useCallback((handler: RealtimeUpdateHandler | null) => {
    updateHandlerRef.current = handler;
  }, []);

  // ============================================================================
  // Cargar datos históricos
  // ============================================================================

  const fetchHistorical = useCallback(async () => {
    if (!ticker) return;

    setLoading(true);
    setError(null);

    try {
      let url = `${API_URL}/api/v1/chart/${ticker}?interval=${interval}`;
      if (replayTo) url += `&to=${replayTo}`;

      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();
      const bars: ChartBar[] = result.data || [];

      bars.sort((a, b) => a.time - b.time);

      setData(bars);
      setOldestTime(result.oldest_time || null);
      setHasMore(result.has_more || false);

      if (bars.length > 0) {
        lastBarRef.current = bars[bars.length - 1];
      }

    } catch (err) {
      console.error('[LiveChart] Fetch error:', err);
      setError(err instanceof Error ? err.message : 'Failed to load chart');
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [ticker, interval, replayTo]);

  const loadMore = useCallback(async (): Promise<boolean> => {
    if (!tickerRef.current || !oldestTimeRef.current || !hasMoreRef.current || isLoadingMoreRef.current) return false;

    isLoadingMoreRef.current = true;
    setLoadingMore(true);

    try {
      const response = await fetch(
        `${API_URL}/api/v1/chart/${tickerRef.current}?interval=${intervalRef.current}&before=${oldestTimeRef.current}`
      );

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const result = await response.json();
      const newBars: ChartBar[] = result.data || [];

      if (newBars.length > 0) {
        newBars.sort((a, b) => a.time - b.time);

        setData(prev => {
          if (prev.length === 0) return newBars;
          const firstExistingTime = prev[0].time;
          const olderBars = newBars.filter(b => b.time < firstExistingTime);
          return olderBars.length > 0 ? [...olderBars, ...prev] : prev;
        });

        setOldestTime(result.oldest_time || null);
        setHasMore(result.has_more || false);
        return true;
      } else {
        setHasMore(false);
        return false;
      }
    } catch (err) {
      console.error('[LiveChart] Load more error:', err);
      return false;
    } finally {
      isLoadingMoreRef.current = false;
      setLoadingMore(false);
    }
  }, []);

  const loadForward = useCallback(async (): Promise<boolean> => {
    const d = dataRef.current;
    if (!tickerRef.current || d.length === 0 || isLoadingForwardRef.current) return false;

    const newestTime = d[d.length - 1].time;
    const nowSec = Math.floor(Date.now() / 1000);
    if (newestTime >= nowSec - 60) return false;

    isLoadingForwardRef.current = true;
    try {
      const response = await fetch(
        `${API_URL}/api/v1/chart/${tickerRef.current}?interval=${intervalRef.current}&after=${newestTime}`
      );
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const result = await response.json();
      const newBars: ChartBar[] = result.data || [];

      if (newBars.length > 0) {
        newBars.sort((a, b) => a.time - b.time);
        setData(prev => {
          if (prev.length === 0) return newBars;
          const lastExistingTime = prev[prev.length - 1].time;
          const newerBars = newBars.filter(b => b.time > lastExistingTime);
          return newerBars.length > 0 ? [...prev, ...newerBars] : prev;
        });
        return true;
      }
      return false;
    } catch (err) {
      console.error('[LiveChart] Load forward error:', err);
      return false;
    } finally {
      isLoadingForwardRef.current = false;
    }
  }, []);

  // Fetch only the bars missing since `sinceTime` and push them
  // to the chart imperatively (no full re-render).
  const fetchGapBars = useCallback(async (sinceTime: number) => {
    if (!tickerRef.current) return;
    try {
      const response = await fetch(
        `${API_URL}/api/v1/chart/${tickerRef.current}?interval=${intervalRef.current}&after=${sinceTime}`
      );
      if (!response.ok) return;
      const result = await response.json();
      const bars: ChartBar[] = (result.data || []).sort(
        (a: ChartBar, b: ChartBar) => a.time - b.time
      );
      if (bars.length === 0) return;

      // Push each bar to the chart via the imperative handler
      for (const bar of bars) {
        const last = lastBarRef.current;
        const isNew = !last || bar.time > last.time;
        if (updateHandlerRef.current) {
          updateHandlerRef.current(bar, isNew);
        }
        if (isNew) {
          lastBarRef.current = bar;
        } else if (last && bar.time === last.time) {
          // Merge into current bar
          const merged: ChartBar = {
            time: bar.time,
            open: last.open,
            high: Math.max(last.high, bar.high),
            low: Math.min(last.low, bar.low),
            close: bar.close,
            volume: bar.volume, // API returns final volume for bar
          };
          lastBarRef.current = merged;
          if (updateHandlerRef.current) {
            updateHandlerRef.current(merged, false);
          }
        }
      }
    } catch {
      // Silent — will recover on next aggregate
    }
  }, []);

  // Cargar al montar o cambiar ticker/interval
  useEffect(() => {
    fetchHistorical();
  }, [fetchHistorical]);

  // ============================================================================
  // Actualizaciones en tiempo real via WebSocket (SIN setData)
  // ============================================================================

  useEffect(() => {
    const shouldSubscribe = !replayTo && ['1min', '2min', '5min', '15min'].includes(intervalRef.current);

    if (!shouldSubscribe || loading || data.length === 0 || !ticker || !isConnected) {
      setIsLive(false);
      return;
    }

    const intervalSecs = INTERVAL_SECONDS[intervalRef.current];

    // Suscribirse al chart
    if (!subscribedRef.current) {
      send({ action: 'subscribe_chart', symbol: tickerRef.current });
      subscribedRef.current = true;
    }

    // Suscribirse al observable de mensajes
    const subscription = messages$.subscribe({
      next: (message: any) => {
        if (message?.type !== 'chart_aggregate') return;
        if (message.symbol !== tickerRef.current) return;

        const aggData = message.data;

        // Convertir timestamp de ms a segundos y redondear al intervalo
        const timeSecs = Math.floor(aggData.t / 1000);
        const barTime = Math.floor(timeSecs / intervalSecs) * intervalSecs;

        const lastBar = lastBarRef.current;

        if (!lastBar) return;

        // Construir nueva barra desde aggregate
        // v = volumen del aggregate (ese segundo), NO av (acumulado del día)
        const newBar: ChartBar = {
          time: barTime,
          open: aggData.o,
          high: aggData.h,
          low: aggData.l,
          close: aggData.c,
          volume: aggData.v,  // Volumen de este aggregate
        };

        if (barTime === lastBar.time) {
          // MISMO período → actualizar última barra (merge OHLCV)
          // SUMAR volúmenes de cada aggregate del mismo período
          const updatedBar: ChartBar = {
            time: barTime,
            open: lastBar.open,
            high: Math.max(lastBar.high, newBar.high),
            low: Math.min(lastBar.low, newBar.low),
            close: newBar.close,
            volume: lastBar.volume + aggData.v,  // SUMAR volumen del nuevo aggregate
          };

          // Actualizar ref (sin re-render)
          lastBarRef.current = updatedBar;

          // Notificar al chart via callback imperativo
          if (updateHandlerRef.current) {
            updateHandlerRef.current(updatedBar, false);
          }

          setIsLive(true);

        } else if (barTime > lastBar.time) {
          // NUEVO período → verificar si hay gap entre históricos y tiempo real
          const gapBars = Math.floor((barTime - lastBar.time) / intervalSecs) - 1;

          // Si hay gap pequeño (< 10 barras), rellenar con interpolación
          // Esto conecta los datos históricos con el tiempo real
          if (gapBars > 0 && gapBars <= 10) {
            const startPrice = lastBar.close;
            const endPrice = newBar.open;
            const priceStep = (endPrice - startPrice) / (gapBars + 1);

            for (let i = 1; i <= gapBars; i++) {
              const fillBarTime = lastBar.time + (i * intervalSecs);
              const interpolatedPrice = startPrice + (priceStep * i);

              const fillBar: ChartBar = {
                time: fillBarTime,
                open: interpolatedPrice,
                high: interpolatedPrice,
                low: interpolatedPrice,
                close: interpolatedPrice,
                volume: 0,  // Sin volumen (gap)
              };

              if (updateHandlerRef.current) {
                updateHandlerRef.current(fillBar, true);
              }
            }
          }

          // Crear la nueva barra actual
          lastBarRef.current = newBar;

          // Notificar al chart via callback imperativo
          if (updateHandlerRef.current) {
            updateHandlerRef.current(newBar, true);
          }

          setIsLive(true);
        }
      },
      error: (err: any) => {
        console.error('[LiveChart] WebSocket error:', err);
        setIsLive(false);
      }
    });

    setIsLive(true);

    // Cleanup
    return () => {
      if (subscribedRef.current) {
        send({ action: 'unsubscribe_chart', symbol: tickerRef.current });
        subscribedRef.current = false;
      }
      subscription.unsubscribe();
      setIsLive(false);
    };
  }, [loading, data.length, ticker, isConnected, messages$, send]);

  // ============================================================================
  // Page Lifecycle: visibility + freeze/resume recovery
  //
  // Only fetches missing data. WS subscriptions are managed entirely by the
  // real-time useEffect above (reacts to loading / data.length / isConnected).
  // ============================================================================

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        hiddenAtRef.current = Date.now();
        return;
      }

      const hiddenAt = hiddenAtRef.current;
      hiddenAtRef.current = null;
      isFrozenRef.current = false;

      if (!hiddenAt || !tickerRef.current) return;
      const awayMs = Date.now() - hiddenAt;

      if (awayMs < GAP_IGNORE_MS) return;

      const isIntraday = ['1min', '5min', '15min'].includes(intervalRef.current);

      if (awayMs > GAP_PARTIAL_MAX_MS || !isIntraday) {
        // Long absence → full reload (triggers loading=true → WS effect
        // will auto-unsubscribe/resubscribe via its deps)
        fetchHistorical();
      } else {
        // Short absence → fetch only missing bars imperatively
        const lastBar = lastBarRef.current;
        if (lastBar) {
          fetchGapBars(lastBar.time);
        }
      }
    };

    const handleFreeze = () => {
      isFrozenRef.current = true;
      if (!hiddenAtRef.current) {
        hiddenAtRef.current = Date.now();
      }
    };

    const handleResume = () => {
      isFrozenRef.current = false;
      handleVisibilityChange();
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    document.addEventListener('freeze', handleFreeze);
    document.addEventListener('resume', handleResume);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      document.removeEventListener('freeze', handleFreeze);
      document.removeEventListener('resume', handleResume);
    };
  }, [fetchHistorical, fetchGapBars]);

  // ============================================================================
  // Return
  // ============================================================================

  return {
    data,
    loading,
    loadingMore,
    error,
    hasMore,
    isLive,
    isConnected,
    refetch: fetchHistorical,
    loadMore,
    loadForward,
    registerUpdateHandler,
  };
}

export default useLiveChartData;
