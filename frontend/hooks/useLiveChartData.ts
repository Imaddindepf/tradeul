/**
 * useLiveChartData - Hook para datos de chart con actualización en tiempo real
 * 
 * Combina:
 * 1. Datos históricos cargados via API
 * 2. Actualizaciones en tiempo real via WebSocket (SharedWorker)
 * 
 * Sin gap de sincronización porque:
 * - Históricos traen barras cerradas hasta el minuto anterior
 * - WebSocket trae el minuto ACTUAL en progreso
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useRxWebSocket } from './useRxWebSocket';

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

interface MinuteData {
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
  av: number;
  t: number;      // timestamp in milliseconds
  vw?: number;
  n?: number;
}

interface TickerSnapshot {
  ticker: string;
  min?: MinuteData;
  lastTrade?: {
    p: number;
    t: number;
  };
  day?: {
    o: number;
    h: number;
    l: number;
    c: number;
    v: number;
  };
}

interface WebSocketSnapshotMessage {
  type: 'snapshot';
  count: number;
  data: TickerSnapshot[];
  timestamp: string;
}

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
// Hook
// ============================================================================

export function useLiveChartData(
  ticker: string,
  interval: ChartInterval,
  wsUrl?: string
) {
  // State
  const [data, setData] = useState<ChartBar[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [oldestTime, setOldestTime] = useState<number | null>(null);
  const [isLive, setIsLive] = useState(false);

  // Refs para acceso rápido sin re-renders
  const lastBarRef = useRef<ChartBar | null>(null);
  const tickerRef = useRef(ticker);
  const intervalRef = useRef(interval);
  const dataRef = useRef<ChartBar[]>([]);

  // WebSocket connection (usa el singleton existente)
  const { snapshots$, isConnected } = useRxWebSocket(
    wsUrl || process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000'
  );

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
  // Actualizaciones en tiempo real via WebSocket
  // ============================================================================

  useEffect(() => {
    if (!isConnected || !snapshots$) {
      setIsLive(false);
      return;
    }

    // Solo procesar para intervalos de minutos (1min es el más preciso)
    // Para intervalos mayores, podríamos agregar lógica de agregación
    const intervalSecs = INTERVAL_SECONDS[intervalRef.current];

    const subscription = snapshots$.subscribe({
      next: (message: any) => {
        if (message.type !== 'snapshot' || !message.data) return;

        // Buscar nuestro ticker en el snapshot
        const tickerData = message.data.find(
          (t: TickerSnapshot) => t.ticker === tickerRef.current
        );

        if (!tickerData?.min) return;

        const min = tickerData.min;
        
        // Convertir timestamp de ms a segundos y redondear al intervalo
        const wsTimeSecs = Math.floor(min.t / 1000);
        const barTime = Math.floor(wsTimeSecs / intervalSecs) * intervalSecs;
        
        const lastBar = lastBarRef.current;
        const currentData = dataRef.current;

        if (!lastBar || currentData.length === 0) return;

        // Construir nueva barra desde datos del WebSocket
        const wsBar: ChartBar = {
          time: barTime,
          open: min.o,
          high: min.h,
          low: min.l,
          close: min.c,
          volume: min.v,
        };

        if (barTime === lastBar.time) {
          // MISMO período → actualizar última barra (merge)
          // Para 1min: actualizamos directamente
          // Para intervalos mayores: merge high/low/close
          const updatedBar: ChartBar = {
            time: barTime,
            open: lastBar.open,  // Mantener open original
            high: Math.max(lastBar.high, wsBar.high),
            low: Math.min(lastBar.low, wsBar.low),
            close: wsBar.close,  // Último precio
            volume: intervalRef.current === '1min' 
              ? wsBar.volume 
              : lastBar.volume + wsBar.volume,
          };

          setData(prev => {
            const newData = [...prev];
            newData[newData.length - 1] = updatedBar;
            return newData;
          });

          setIsLive(true);

        } else if (barTime > lastBar.time) {
          // NUEVO período → crear nueva barra
          setData(prev => [...prev, wsBar]);
          setIsLive(true);
        }
        // Si barTime < lastBar.time, ignorar (dato viejo)
      },
      error: (err) => {
        console.error('[LiveChart] WebSocket error:', err);
        setIsLive(false);
      }
    });

    setIsLive(true);

    return () => {
      subscription.unsubscribe();
      setIsLive(false);
    };
  }, [isConnected, snapshots$]);

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
  };
}

export default useLiveChartData;

