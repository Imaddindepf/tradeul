/**
 * useLiveChartData - Hook para datos de chart con actualización en tiempo real
 * 
 * ARQUITECTURA PROFESIONAL:
 * 1. Datos históricos cargados via API → setData (una sola vez)
 * 2. Actualizaciones en tiempo real via WebSocket → callback imperativo (sin re-render)
 * 
 * El componente TradingChart registra un handler que recibe las actualizaciones
 * y usa series.update() directamente, evitando re-renders de React.
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

export type ChartInterval = '1min' | '5min' | '15min' | '30min' | '1hour' | '4hour' | '1day';

// Handler que el chart registra para recibir updates sin re-render
export type RealtimeUpdateHandler = (bar: ChartBar, isNewBar: boolean) => void;

// ============================================================================
// Constants
// ============================================================================

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Intervalo en segundos para cada tipo de barra
const INTERVAL_SECONDS: Record<ChartInterval, number> = {
  '1min': 60,
  '5min': 300,
  '15min': 900,
  '30min': 1800,
  '1hour': 3600,
  '4hour': 14400,
  '1day': 86400,
};

// ============================================================================
// WebSocket Manager Access
// ============================================================================

// Importar WebSocket hook principal
import { useRxWebSocket } from './useRxWebSocket';

// ============================================================================
// Hook
// ============================================================================

export function useLiveChartData(
  ticker: string,
  interval: ChartInterval
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

  // Handler registrado por el chart para updates imperativos
  const updateHandlerRef = useRef<RealtimeUpdateHandler | null>(null);

  // Actualizar refs cuando cambien
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
      const response = await fetch(
        `${API_URL}/api/v1/chart/${ticker}?interval=${interval}`
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();
      const bars: ChartBar[] = result.data || [];

      // Ordenar por tiempo ascendente
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
  }, [ticker, interval]);

  // Cargar más datos históricos (lazy loading)
  const loadMore = useCallback(async (): Promise<boolean> => {
    if (!ticker || !oldestTime || !hasMore || loadingMore) return false;

    setLoadingMore(true);

    try {
      const response = await fetch(
        `${API_URL}/api/v1/chart/${ticker}?interval=${interval}&before=${oldestTime}`
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();
      const newBars: ChartBar[] = result.data || [];

      if (newBars.length > 0) {
        // Merge y ordenar
        setData(prev => {
          const timeMap = new Map<number, ChartBar>();
          [...newBars, ...prev].forEach(bar => timeMap.set(bar.time, bar));
          return Array.from(timeMap.values()).sort((a, b) => a.time - b.time);
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
      setLoadingMore(false);
    }
  }, [ticker, interval, oldestTime, hasMore, loadingMore]);

  // Cargar al montar o cambiar ticker/interval
  useEffect(() => {
    fetchHistorical();
  }, [fetchHistorical]);

  // ============================================================================
  // Actualizaciones en tiempo real via WebSocket (SIN setData)
  // ============================================================================

  useEffect(() => {
    // Solo activar para intervalos cortos
    const shouldSubscribe = ['1min', '5min', '15min'].includes(intervalRef.current);

    if (!shouldSubscribe || loading || data.length === 0 || !ticker || !isConnected) {
      setIsLive(false);
      return;
    }

    const intervalSecs = INTERVAL_SECONDS[intervalRef.current];

    // Suscribirse al chart
    if (!subscribedRef.current) {
      send({ action: 'subscribe_chart', symbol: tickerRef.current });
      subscribedRef.current = true;
      console.log(`📈 [LiveChart] Subscribed to ${tickerRef.current}`);
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
        const newBar: ChartBar = {
          time: barTime,
          open: aggData.o,
          high: aggData.h,
          low: aggData.l,
          close: aggData.c,
          volume: aggData.v,
        };

        if (barTime === lastBar.time) {
          // MISMO período → actualizar última barra (merge OHLCV)
          const updatedBar: ChartBar = {
            time: barTime,
            open: lastBar.open,
            high: Math.max(lastBar.high, newBar.high),
            low: Math.min(lastBar.low, newBar.low),
            close: newBar.close,
            volume: newBar.volume,
          };

          // Actualizar ref (sin re-render)
          lastBarRef.current = updatedBar;

          // Notificar al chart via callback imperativo
          if (updateHandlerRef.current) {
            updateHandlerRef.current(updatedBar, false);
          }

          setIsLive(true);

        } else if (barTime > lastBar.time) {
          // NUEVO período → crear nueva barra
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
        console.log(`📉 [LiveChart] Unsubscribed from ${tickerRef.current}`);
      }
      subscription.unsubscribe();
      setIsLive(false);
    };
  }, [loading, data.length, ticker, isConnected, messages$, send]);

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
    // Método para que el chart registre su handler de updates
    registerUpdateHandler,
  };
}

export default useLiveChartData;
