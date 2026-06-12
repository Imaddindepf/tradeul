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
type RealtimeUpdateHandler = (bar: ChartBar, isNewBar: boolean) => void;

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

function getETMinuteOfDay(unixSecs: number): number {
  const d = new Date(unixSecs * 1000);
  const parts = d.toLocaleString('en-US', {
    timeZone: 'America/New_York', hour: 'numeric', minute: 'numeric', hour12: false,
  });
  const [h, m] = parts.split(':').map(Number);
  return h * 60 + m;
}

function getDailyBarTime(unixSecs: number, lastBarTime: number): number {
  const d = new Date(unixSecs * 1000);
  const lastD = new Date(lastBarTime * 1000);
  const etOpts: Intl.DateTimeFormatOptions = {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
  };
  if (d.toLocaleDateString('en-US', etOpts) === lastD.toLocaleDateString('en-US', etOpts)) {
    return lastBarTime;
  }
  return lastBarTime + 86400;
}

function isRegularHours(unixSecs: number): boolean {
  const min = getETMinuteOfDay(unixSecs);
  return min >= 570 && min < 960; // 9:30 to 16:00 ET
}

// Recovery thresholds
const GAP_IGNORE_MS = 5_000;       // < 5s away → do nothing
const GAP_PARTIAL_MAX_MS = 300_000; // < 5min → partial fetch
// > 5min → full refetch

// ============================================================================
// WebSocket Manager Access
// ============================================================================

import { useWebSocket } from '@/contexts/AuthWebSocketContext';

// ============================================================================
// Module-level bar cache (survives unmount/remount)
// ============================================================================

interface BarCacheEntry {
  bars: ChartBar[];
  oldestTime: number | null;
  hasMore: boolean;
  ts: number;
}

const _barCache = new Map<string, BarCacheEntry>();
const BAR_CACHE_TTL_MS = 5 * 60 * 1000; // 5 min stale threshold

function barCacheKey(ticker: string, interval: ChartInterval, replayTo?: number | null): string {
  return `${ticker}:${interval}${replayTo ? `:${replayTo}` : ''}`;
}

function getBarCache(key: string): BarCacheEntry | null {
  const entry = _barCache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.ts > BAR_CACHE_TTL_MS) {
    _barCache.delete(key);
    return null;
  }
  return entry;
}

function setBarCache(key: string, bars: ChartBar[], oldestTime: number | null, hasMore: boolean) {
  _barCache.set(key, { bars, oldestTime, hasMore, ts: Date.now() });
}

// ============================================================================
// Hook
// ============================================================================

export function useLiveChartData(
  ticker: string,
  interval: ChartInterval,
  replayTo?: number | null,
) {
  const cacheKey = barCacheKey(ticker, interval, replayTo);
  const cached = getBarCache(cacheKey);

  const [data, setData] = useState<ChartBar[]>(cached?.bars || []);
  const [loading, setLoading] = useState(!cached);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(cached?.hasMore || false);
  const [oldestTime, setOldestTime] = useState<number | null>(cached?.oldestTime ?? null);
  const [isLive, setIsLive] = useState(false);

  // WebSocket: use the already-authenticated singleton from AuthWebSocketProvider.
  // CRITICAL: This hook is mounted EVERY TIME the user opens a chart. Calling
  // useRxWebSocket(WS_BASE_URL) here used to (re)configure the singleton with
  // a tokenless URL, racing against the central provider and triggering 2-3s
  // of "offline" on every chart open. useWebSocket() just reads from the
  // context — zero side effects on the connection.
  const { isConnected, messages$, send } = useWebSocket();

  // Refs para acceso rápido sin re-renders
  const cachedBars = cached?.bars || [];
  const lastBarRef = useRef<ChartBar | null>(cachedBars.length > 0 ? cachedBars[cachedBars.length - 1] : null);

  // Espejo "vivo" de `data`: misma serie histórica + los ticks WS aplicados
  // en sitio (mutación, sin setState). Los consumidores imperativos
  // (crosshair, magnet, OHLC del hover) leen este ref para no quedarse con
  // la última vela congelada en el estado de React.
  const liveBarsRef = useRef<ChartBar[]>(cachedBars.slice());
  const liveSourceRef = useRef<ChartBar[] | null>(cached?.bars ?? null);

  const tickerRef = useRef(ticker);
  const intervalRef = useRef(interval);
  const dataRef = useRef<ChartBar[]>(cachedBars);
  const subscribedRef = useRef(false);
  const isLoadingMoreRef = useRef(false);
  const isLoadingForwardRef = useRef(false);
  const hasMoreRef = useRef(false);
  const oldestTimeRef = useRef<number | null>(null);

  // Handler registrado por el chart para updates imperativos
  const updateHandlerRef = useRef<RealtimeUpdateHandler | null>(null);

  // Extended hours price callback (for daily+ charts, pre/post market)
  const extendedHoursPriceRef = useRef<((price: number) => void) | null>(null);
  const registerExtendedHoursHandler = useCallback((handler: ((price: number) => void) | null) => {
    extendedHoursPriceRef.current = handler;
  }, []);

  // Page Lifecycle: track when the tab went hidden
  const hiddenAtRef = useRef<number | null>(null);
  const isFrozenRef = useRef(false);

  // Dedup de feeds WS: el servidor envía `chart_aggregate` por DOS rutas que
  // representan los mismos trades — micro-velas de chart_aggregator cada
  // ~150ms (source: "trades") y aggregates A.* de Polygon cada 1s (sin
  // source). Procesar ambas duplica el volumen de la vela en curso. Mientras
  // el feed de trades esté vivo, ignoramos A.*; si deja de emitir (p.ej.
  // chart_aggregator caído), A.* actúa de fallback.
  const lastTradesFeedMsgAtRef = useRef(0);

  // Render-phase sync: cuando el estado `data` cambia (load/loadMore/refetch)
  // el espejo vivo se reconstruye desde él, descartando las velas WS
  // provisionales (el fetch ya las trae consolidadas).
  if (liveSourceRef.current !== data) {
    liveSourceRef.current = data;
    liveBarsRef.current = data.slice();
  }

  /** Aplica una vela en vivo al espejo (merge sobre la última o push). */
  const applyLiveBar = useCallback((bar: ChartBar) => {
    const arr = liveBarsRef.current;
    const last = arr.length > 0 ? arr[arr.length - 1] : null;
    if (last && last.time === bar.time) {
      arr[arr.length - 1] = bar;
    } else if (!last || bar.time > last.time) {
      arr.push(bar);
    }
  }, []);

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
      setBarCache(barCacheKey(ticker, interval, replayTo), bars, result.oldest_time || null, result.has_more || false);

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
        if (isNew) {
          lastBarRef.current = bar;
          applyLiveBar(bar);
          if (updateHandlerRef.current) {
            updateHandlerRef.current(bar, true);
          }
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
          applyLiveBar(merged);
          if (updateHandlerRef.current) {
            updateHandlerRef.current(merged, false);
          }
        }
      }
    } catch {
      // Silent — will recover on next aggregate
    }
  }, [applyLiveBar]);

  // Cargar al montar o cambiar ticker/interval.
  // If cache hit, skip the blocking fetch — WebSocket will bring fresh data.
  // Still revalidate in background after a short delay.
  const hadCacheOnMount = useRef(!!cached);
  useEffect(() => {
    if (hadCacheOnMount.current) {
      hadCacheOnMount.current = false;
      const t = setTimeout(() => fetchHistorical(), 3000);
      return () => clearTimeout(t);
    }
    fetchHistorical();
  }, [fetchHistorical]);

  // ============================================================================
  // Actualizaciones en tiempo real via WebSocket (SIN setData)
  // ============================================================================

  useEffect(() => {
    const shouldSubscribe = !replayTo && !['1week', '1month', '3month', '1year'].includes(intervalRef.current);

    if (!shouldSubscribe || loading || data.length === 0 || !ticker || !isConnected) {
      setIsLive(false);
      return;
    }

    const interval = intervalRef.current;
    const intervalSecs = INTERVAL_SECONDS[interval];
    const isDailyOrAbove = interval === '1day';

    if (!subscribedRef.current) {
      send({ action: 'subscribe_chart', symbol: tickerRef.current });
      subscribedRef.current = true;
    }

    const subscription = messages$.subscribe({
      next: (message: any) => {
        if (message?.type !== 'chart_aggregate') return;
        if (message.symbol !== tickerRef.current) return;

        // Dedup feed doble (ver comentario en lastTradesFeedMsgAtRef)
        const TRADES_FEED_ALIVE_MS = 10_000;
        if (message.source === 'trades') {
          lastTradesFeedMsgAtRef.current = Date.now();
        } else if (Date.now() - lastTradesFeedMsgAtRef.current < TRADES_FEED_ALIVE_MS) {
          return; // A.* descartado: el feed de trades ya cubre este flujo
        }

        const aggData = message.data;
        const timeSecs = Math.floor(aggData.t / 1000);

        // Daily candles only reflect regular session (9:30-16:00 ET)
        if (isDailyOrAbove && !isRegularHours(timeSecs)) {
          if (extendedHoursPriceRef.current) {
            extendedHoursPriceRef.current(aggData.c);
          }
          return;
        }

        const lastBar = lastBarRef.current;
        if (!lastBar) return;

        const barTime = isDailyOrAbove
          ? getDailyBarTime(timeSecs, lastBar.time)
          : Math.floor(timeSecs / intervalSecs) * intervalSecs;

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

          // Actualizar refs (sin re-render)
          lastBarRef.current = updatedBar;
          applyLiveBar(updatedBar);

          // Notificar al chart via callback imperativo
          if (updateHandlerRef.current) {
            updateHandlerRef.current(updatedBar, false);
          }

          setIsLive(true);

        } else if (barTime > lastBar.time) {
          // NUEVO período. Si hay un gap real (> 1 barra), no inventamos
          // velas interpoladas — eso pinta una línea falsa y rompe los
          // indicadores. En su lugar, pedimos al backend las barras reales
          // (que ahora incluyen el live-bar-stitch desde bar_builder).
          const gapBars = Math.floor((barTime - lastBar.time) / intervalSecs) - 1;
          if (gapBars > 0) {
            // Fire-and-forget. loadForward() consultará /api/v1/chart?after=
            // que ya viene stitcheado con la barra en formación.
            void loadForward();
            // Importante: NO emitimos la newBar todavía. Esperamos a que
            // loadForward la traiga con el OPEN real del período. Si nunca
            // llega (mercado cerrado, etc.), el siguiente WS chart_aggregate
            // se merge-eará contra lastBar cuando barTime vuelva a coincidir.
            return;
          }

          // Caso normal: nueva vela contigua. El OPEN puede ser inexacto
          // (es solo el primer trade del WS, no el verdadero open del minuto).
          // Marcamos la vela como provisional — el siguiente fetchHistorical
          // o loadForward la sobrescribirá con datos reales del backend.
          lastBarRef.current = newBar;
          applyLiveBar(newBar);

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
  }, [loading, data.length, ticker, isConnected, messages$, send, replayTo, loadForward, applyLiveBar]);

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
    /** Espejo de `data` con los ticks WS aplicados — solo lectura imperativa. */
    liveBarsRef,
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
    registerExtendedHoursHandler,
  };
}

export default useLiveChartData;
