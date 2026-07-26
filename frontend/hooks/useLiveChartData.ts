/**
 * useLiveChartData - Hook para datos de chart con actualización en tiempo real
 *
 * ARQUITECTURA:
 * 1. Datos históricos cargados via API → setData (una sola vez)
 * 2. Actualizaciones en tiempo real via WebSocket → callback imperativo (sin re-render)
 * 3. Resiliencia (un chart de trading debe recuperarse SOLO, siempre):
 *    - visibilitychange + freeze/resume: backfill de barras al volver de background
 *    - reconexión WS: gap-check independiente de visibility (suspensión del SO,
 *      restart del servidor, cortes de red)
 *    - retry con backoff de fetchHistorical + evento 'online'; NUNCA se borran
 *      las velas existentes por un error de red
 *    - trading_day_changed: invalida caché y recarga
 *    - watchdog de staleness: el badge LIVE se apaga si el feed se queda mudo
 *      con el mercado abierto
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { applyAggregate, mergeAuthoritativeBar, sealedToChartBar } from '@/lib/barAggregation';
import { isChartAggregateMsg, isChartBarSealedMsg, isTradingDayChangedMsg } from '@/lib/wsContracts';
import { acquireStream, releaseStream } from '@/lib/chartStreams';

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

// Recovery thresholds
const GAP_IGNORE_MS = 5_000;       // < 5s away → do nothing
const GAP_PARTIAL_MAX_MS = 300_000; // < 5min → partial fetch
// > 5min → full refetch

// Retry de fetchHistorical tras error de red (típico: WiFi reconectando al
// despertar el portátil). Backoff exponencial con techo — nunca nos rendimos:
// un chart de trading debe recuperarse solo, como la conexión WS.
const FETCH_RETRY_BASE_MS = 1_000;
const FETCH_RETRY_MAX_MS = 30_000;

// Watchdog de staleness del feed: durante MARKET_OPEN, si un símbolo
// suscrito no emite nada en este tiempo, el feed está roto (o el valor
// halted) → apagar el badge LIVE. En pre/post no aplica: los trades
// esporádicos son normales y el silencio no implica feed caído.
const FEED_STALE_MS = 60_000;
const FEED_WATCHDOG_INTERVAL_MS = 10_000;

// ============================================================================
// WebSocket Manager Access
// ============================================================================

import { useWebSocket } from '@/contexts/AuthWebSocketContext';
import { useMarketSessionStore } from '@/stores/useMarketSessionStore';

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
  /** Símbolo realmente adquirido en chartStreams — el cleanup debe liberar
   *  ESTE (tickerRef ya apunta al ticker nuevo cuando corre el cleanup). */
  const acquiredSymbolRef = useRef<string | null>(null);
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

  // Último mensaje de feed (de cualquier fuente) para nuestro símbolo.
  // Alimenta el watchdog de staleness del badge LIVE.
  const lastFeedMsgAtRef = useRef(0);

  // Secuencia por símbolo del servidor (M5): si seq salta más de +1, el
  // servidor descartó mensajes para esta conexión (backpressure) o la red
  // los perdió → backfill REST en vez de velas silenciosamente incompletas.
  const lastSeqRef = useRef<number | null>(null);
  const lastSeqGapRecoveryAtRef = useRef(0);

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

  // Retry automático de fetchHistorical (backoff exponencial, sin límite de
  // intentos). Un fallo transitorio (WiFi reconectando al despertar el
  // portátil) NUNCA debe dejar el chart vacío ni muerto.
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryAttemptRef = useRef(0);
  // Época de datos: se incrementa al cambiar (ticker, interval, replayTo).
  // Toda petición REST captura la época al arrancar y su respuesta se
  // DESCARTA si al llegar ya no coincide. Sin esto, una respuesta lenta del
  // ticker anterior puede pisar las velas del ticker nuevo (header/precio
  // correctos, histórico de otro símbolo).
  const fetchEpochRef = useRef(0);
  const fetchAbortRef = useRef<AbortController | null>(null);
  // Última clave (ticker:interval[:replay]) cargada con éxito — distingue
  // cold load (cambio de ticker/interval) de revalidación en background.
  // Si montamos con caché de módulo, esa clave ya está "cargada".
  const lastLoadedKeyRef = useRef<string | null>(cached ? cacheKey : null);
  const clearRetryTimer = useCallback(() => {
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, []);

  const fetchHistorical = useCallback(async () => {
    if (!ticker) return;

    clearRetryTimer();

    // Cold load = primera carga de ESTE (ticker, interval) — mostrar overlay
    // y (vía loading=true) pausar la suscripción WS hasta tener velas del
    // ticker correcto. Si ya cargamos esta clave antes, es una revalidación
    // en background: no ocultar el chart ni interrumpir el realtime.
    const fetchKey = barCacheKey(ticker, interval, replayTo);
    const isColdLoad = dataRef.current.length === 0 || lastLoadedKeyRef.current !== fetchKey;
    if (isColdLoad) {
      setLoading(true);
      setError(null);
    }

    // Solo puede haber UN fetchHistorical vigente: abortar el anterior y
    // capturar la época actual para descartar esta respuesta si (ticker,
    // interval, replay) cambia mientras está en vuelo.
    fetchAbortRef.current?.abort();
    const abort = new AbortController();
    fetchAbortRef.current = abort;
    const epoch = fetchEpochRef.current;

    try {
      let url = `${API_URL}/api/v1/chart/${encodeURIComponent(ticker)}?interval=${interval}`;
      if (replayTo) url += `&to=${replayTo}`;

      const response = await fetch(url, { signal: abort.signal });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();
      if (epoch !== fetchEpochRef.current) return; // respuesta obsoleta: el chart ya es de otro símbolo

      const bars: ChartBar[] = result.data || [];

      bars.sort((a, b) => a.time - b.time);

      retryAttemptRef.current = 0;
      lastLoadedKeyRef.current = fetchKey;
      setError(null);
      setData(bars);
      setOldestTime(result.oldest_time || null);
      setHasMore(result.has_more || false);
      setBarCache(fetchKey, bars, result.oldest_time || null, result.has_more || false);

      if (bars.length > 0) {
        lastBarRef.current = bars[bars.length - 1];
      }

    } catch (err) {
      if ((err as Error)?.name === 'AbortError' || epoch !== fetchEpochRef.current) {
        return; // cancelado o superado por un cambio de símbolo: ni error ni retry
      }
      console.error('[LiveChart] Fetch error:', err);
      // NUNCA borrar datos existentes por un error de red: quedarse con las
      // velas (marginalmente stale) es estrictamente mejor que un chart vacío.
      if (isColdLoad) {
        setError(err instanceof Error ? err.message : 'Failed to load chart');
      }

      const attempt = retryAttemptRef.current + 1;
      retryAttemptRef.current = attempt;
      const delay = Math.min(FETCH_RETRY_BASE_MS * 2 ** (attempt - 1), FETCH_RETRY_MAX_MS);
      retryTimerRef.current = setTimeout(() => {
        void fetchHistoricalRef.current();
      }, delay);
    } finally {
      // Si nos abortó un fetch más nuevo, ese fetch es el dueño de `loading`.
      if (isColdLoad && !abort.signal.aborted) setLoading(false);
    }
  }, [ticker, interval, replayTo, clearRetryTimer]);

  // Ref estable para timers/listeners (evita capturar closures obsoletos).
  const fetchHistoricalRef = useRef(fetchHistorical);
  useEffect(() => { fetchHistoricalRef.current = fetchHistorical; }, [fetchHistorical]);

  // Cambio de (ticker, interval, replay): nueva época de datos. Cancelar
  // retries y abortar el fetch en vuelo — su respuesta ya no es aplicable.
  // Además, sincronizar el estado con la caché de la NUEVA clave (o vaciarlo):
  // las velas del símbolo anterior no deben renderizarse ni un frame bajo el
  // ticker nuevo, ni contaminar los refs que consume el flujo realtime.
  useEffect(() => {
    fetchEpochRef.current += 1;
    retryAttemptRef.current = 0;
    fetchAbortRef.current?.abort();

    const key = barCacheKey(ticker, interval, replayTo);
    const entry = getBarCache(key);
    const bars = entry?.bars ?? [];
    setData(bars);
    setOldestTime(entry?.oldestTime ?? null);
    setHasMore(entry?.hasMore ?? false);
    setError(null);
    lastBarRef.current = bars.length > 0 ? bars[bars.length - 1] : null;

    return clearRetryTimer;
  }, [ticker, interval, replayTo, clearRetryTimer]);

  // Recuperación por evento 'online': si el navegador recupera red y hay un
  // retry en cola o un error activo, refetch inmediato sin esperar el backoff.
  useEffect(() => {
    const onOnline = () => {
      if (retryTimerRef.current || retryAttemptRef.current > 0) {
        void fetchHistoricalRef.current();
      }
    };
    window.addEventListener('online', onOnline);
    return () => window.removeEventListener('online', onOnline);
  }, []);

  const loadMore = useCallback(async (): Promise<boolean> => {
    if (!tickerRef.current || !oldestTimeRef.current || !hasMoreRef.current || isLoadingMoreRef.current) return false;

    isLoadingMoreRef.current = true;
    setLoadingMore(true);
    const epoch = fetchEpochRef.current;

    try {
      const response = await fetch(
        `${API_URL}/api/v1/chart/${encodeURIComponent(tickerRef.current)}?interval=${intervalRef.current}&before=${oldestTimeRef.current}`
      );

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const result = await response.json();
      if (epoch !== fetchEpochRef.current) return false; // símbolo/interval cambió en vuelo
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
    const epoch = fetchEpochRef.current;
    try {
      const response = await fetch(
        `${API_URL}/api/v1/chart/${encodeURIComponent(tickerRef.current)}?interval=${intervalRef.current}&after=${newestTime}`
      );
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const result = await response.json();
      if (epoch !== fetchEpochRef.current) return false; // símbolo/interval cambió en vuelo
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
    const epoch = fetchEpochRef.current;
    try {
      const response = await fetch(
        `${API_URL}/api/v1/chart/${encodeURIComponent(tickerRef.current)}?interval=${intervalRef.current}&after=${sinceTime}`
      );
      if (!response.ok) return;
      const result = await response.json();
      if (epoch !== fetchEpochRef.current) return; // símbolo/interval cambió en vuelo
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

  // Cambio de día de trading (emitido por el SharedWorker al reconectar con
  // trading_date distinto, o en la transición de día del servidor): las velas
  // cacheadas son del día anterior → invalidar y recargar.
  useEffect(() => {
    const subscription = messages$.subscribe((message: any) => {
      if (!isTradingDayChangedMsg(message)) return;
      _barCache.clear();
      void fetchHistoricalRef.current();
    });
    return () => subscription.unsubscribe();
  }, [messages$]);

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
      // Refcount global (lib/chartStreams): el multichart TVC y otras ventanas
      // comparten símbolo y conexión; emitir subscribe/unsubscribe directos
      // pisaba las suscripciones del resto.
      acquireStream(send, 'chart', tickerRef.current);
      acquiredSymbolRef.current = tickerRef.current;
      subscribedRef.current = true;
      // La secuencia del servidor es por símbolo y sobrevive a nuestra
      // (re)suscripción: resetear la referencia local para no confundir el
      // primer seq visto con un hueco.
      lastSeqRef.current = null;
    }

    const subscription = messages$.subscribe({
      next: (message: any) => {
        // Validación de contrato en el borde: mensajes malformados se
        // descartan aquí (con contador en wsContracts) y nunca llegan a
        // producir velas con NaN/undefined.
        const isAggregate = isChartAggregateMsg(message);
        const isSealed = !isAggregate && isChartBarSealedMsg(message);
        if (!isAggregate && !isSealed) return;
        if (message.symbol !== tickerRef.current) return;

        // Feed vivo: cualquier mensaje de nuestro símbolo cuenta para el
        // watchdog de staleness, aunque luego se descarte por dedup.
        lastFeedMsgAtRef.current = Date.now();

        // ── M5: detección de mensajes perdidos por secuencia ──────────────
        if (typeof message.seq === 'number') {
          const prev = lastSeqRef.current;
          lastSeqRef.current = message.seq;
          if (prev !== null && message.seq > prev + 1) {
            // Se perdieron (seq - prev - 1) mensajes → la vela local puede
            // estar incompleta. Backfill REST (throttled a 1 por 5s).
            const now = Date.now();
            if (now - lastSeqGapRecoveryAtRef.current > 5_000) {
              lastSeqGapRecoveryAtRef.current = now;
              const lb = lastBarRef.current;
              if (lb) void fetchGapBars(lb.time);
            }
          }
        }

        // ── M4: vela SELLADA (autoritativa) de bar_builder ────────────────
        if (isSealed) {
          const sealed = message.data;
          // Solo aplica si el timeframe sellado coincide con el intervalo visible.
          if (sealed.timeframe * 60 !== intervalSecs) return;
          const authoritative = sealedToChartBar(sealed);
          if (!authoritative) return;

          const lastBar = lastBarRef.current;
          if (!lastBar || authoritative.time !== lastBar.time) return;

          // Reemplazar la vela provisional por la versión consolidada
          // (open real del bucket, volumen exacto). high/low se conservan
          // si localmente vimos extremos que el builder aún no integró.
          const corrected = mergeAuthoritativeBar(lastBar, authoritative);
          lastBarRef.current = corrected;
          applyLiveBar(corrected);
          if (updateHandlerRef.current) {
            updateHandlerRef.current(corrected, false);
          }
          return;
        }

        // ── chart_aggregate: dedup del feed doble ─────────────────────────
        const TRADES_FEED_ALIVE_MS = 10_000;
        if (message.source === 'trades') {
          lastTradesFeedMsgAtRef.current = Date.now();
        } else if (Date.now() - lastTradesFeedMsgAtRef.current < TRADES_FEED_ALIVE_MS) {
          return; // A.* descartado: el feed de trades ya cubre este flujo
        }

        const action = applyAggregate(lastBarRef.current, message.data, intervalSecs, isDailyOrAbove);

        switch (action.kind) {
          case 'extended-hours':
            // Diario+: tick fuera de sesión regular → solo overlay pre/post.
            extendedHoursPriceRef.current?.(action.price);
            return;

          case 'merge':
          case 'new-bar': {
            lastBarRef.current = action.bar;
            applyLiveBar(action.bar);
            updateHandlerRef.current?.(action.bar, action.kind === 'new-bar');
            setIsLive(true);
            return;
          }

          case 'gap-backfill':
            // Hueco de ≥1 vela: NO inventar velas interpoladas. loadForward()
            // trae las barras reales (con live-bar-stitch de bar_builder).
            void loadForward();
            return;

          case 'ignore':
            return;
        }
      },
      error: (err: any) => {
        console.error('[LiveChart] WebSocket error:', err);
        setIsLive(false);
      }
    });

    // NO marcar isLive aquí: suscribirse no garantiza que lleguen datos.
    // isLive se enciende al recibir el primer chart_aggregate real y lo
    // apaga el watchdog de staleness si el feed se queda mudo.

    // Cleanup
    return () => {
      if (subscribedRef.current) {
        releaseStream(send, 'chart', acquiredSymbolRef.current ?? tickerRef.current);
        acquiredSymbolRef.current = null;
        subscribedRef.current = false;
      }
      subscription.unsubscribe();
      setIsLive(false);
    };
  }, [loading, data.length, ticker, isConnected, messages$, send, replayTo, loadForward, applyLiveBar, fetchGapBars]);

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

      const isIntraday = ['1min', '2min', '5min', '15min', '30min', '1hour'].includes(intervalRef.current);

      if (awayMs > GAP_PARTIAL_MAX_MS || !isIntraday) {
        // Long absence → full reload
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
  // Recuperación al RECONECTAR el WebSocket (independiente de visibility).
  //
  // Cubre los casos que visibilitychange no ve: suspensión del SO sin evento
  // (portátil cerrado con la pestaña visible), restart del websocket_server,
  // cortes de red. Sin esto, la recuperación dependía de que llegara un tick
  // con gap — en tickers ilíquidos podía tardar minutos o no llegar nunca.
  // ============================================================================

  const lastDisconnectAtRef = useRef<number | null>(null);
  useEffect(() => {
    if (!isConnected) {
      if (lastDisconnectAtRef.current === null) {
        lastDisconnectAtRef.current = Date.now();
      }
      return;
    }

    const downSince = lastDisconnectAtRef.current;
    lastDisconnectAtRef.current = null;
    if (downSince === null) return; // conexión inicial, no reconexión
    if (replayTo || !tickerRef.current) return;

    const downMs = Date.now() - downSince;
    if (downMs < GAP_IGNORE_MS) return;

    const isIntraday = ['1min', '2min', '5min', '15min', '30min', '1hour'].includes(intervalRef.current);
    const lastBar = lastBarRef.current;

    if (downMs <= GAP_PARTIAL_MAX_MS && isIntraday && lastBar) {
      fetchGapBars(lastBar.time);
    } else {
      void fetchHistoricalRef.current();
    }
  }, [isConnected, replayTo, fetchGapBars]);

  // ============================================================================
  // Watchdog de staleness del feed: con el mercado ABIERTO, si nuestro símbolo
  // no emite nada en FEED_STALE_MS, el badge LIVE se apaga. Un indicador LIVE
  // que no puede ponerse en falso no es un indicador.
  // ============================================================================

  useEffect(() => {
    const timer = setInterval(() => {
      if (!lastFeedMsgAtRef.current) return;
      const stale = Date.now() - lastFeedMsgAtRef.current > FEED_STALE_MS;
      if (stale && useMarketSessionStore.getState().isMarketOpen) {
        setIsLive(false);
      }
    }, FEED_WATCHDOG_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

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
