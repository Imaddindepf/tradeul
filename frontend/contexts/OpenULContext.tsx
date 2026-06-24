'use client';

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

export interface OpenULMedia {
  type: string;   // "photo" | "video" | "animated_gif"
  url: string;
}

export interface OpenULNewsItem {
  id: string;
  text: string;
  tickers?: string[];
  type?: 'reaction';
  direction?: 'up' | 'down';
  change_pct?: number;
  price?: number;
  ref_id?: string;
  created_at: string;
  received_at: string;
  received_ts: number;
  stream_id?: string;
  media?: OpenULMedia[];
  urls?: string[];
}

type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

interface OpenULContextValue {
  items: OpenULNewsItem[];
  status: ConnectionStatus;
  unreadCount: number;
  clearUnread: () => void;
  isWindowOpen: boolean;
  setWindowOpen: (open: boolean) => void;
  loadOlder: () => void;
  loadingOlder: boolean;
  hasMore: boolean;
}

const OpenULContext = createContext<OpenULContextValue | null>(null);

// Tope de memoria. La virtualizacion (react-virtuoso) mantiene el DOM
// acotado a unos pocos nodos sin importar el tamano del array, asi que un
// tope alto solo limita el heap de JS. Solo se recorta la cola (lo mas
// antiguo) en el merge de items NUEVOS; nunca al cargar historial.
const MAX_ITEMS = 5000;

// Items por pagina al cargar historial hacia atras (scroll al fondo).
const HISTORY_PAGE_SIZE = 50;

// Freno duro de paginacion: dejamos de pedir mas alla de esto para que un
// scroll infinito accidental no agote memoria.
const HISTORY_HARD_CEILING = 10000;

// If the tab has been hidden for at least this long we assume the SSE
// connection might be zombie and force an explicit gap-fill on return.
const STALE_AFTER_HIDDEN_MS = 5_000;

// If we go this long while visible without any SSE activity (data or
// keepalive comments are filtered by the browser, so we only see data),
// we proactively reconnect. A typical busy day produces a message at
// least every ~30 s; this threshold is generous on quiet days.
const SSE_WATCHDOG_MS = 90_000;

export function OpenULProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<OpenULNewsItem[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [unreadCount, setUnreadCount] = useState(0);
  const [isWindowOpen, setWindowOpen] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [hasMore, setHasMore] = useState(true);

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const watchdogIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const initialLoadDone = useRef(false);

  // Refs sincronizados para leer estado actual dentro de callbacks estables
  // (loadOlder se dispara desde el onScroll de Virtuoso).
  const itemsRef = useRef<OpenULNewsItem[]>([]);
  const loadingOlderRef = useRef(false);
  const hasMoreRef = useRef(true);

  useEffect(() => { itemsRef.current = items; }, [items]);
  useEffect(() => { loadingOlderRef.current = loadingOlder; }, [loadingOlder]);
  useEffect(() => { hasMoreRef.current = hasMore; }, [hasMore]);

  // The last stream id we have actually delivered to React state. We use
  // this to ask the backend for a precise gap-fill on reconnect.
  const lastStreamIdRef = useRef<string | null>(null);
  // Timestamp (ms) of the last SSE event received from the server.
  const lastSseAtRef = useRef<number>(0);
  // Timestamp (ms) when the tab last became hidden, or 0 if visible.
  const hiddenSinceRef = useRef<number>(0);

  // ── helpers ──────────────────────────────────────────────────────────

  const applyIncomingItems = useCallback((incoming: OpenULNewsItem[]) => {
    if (incoming.length === 0) return;
    setItems((prev) => {
      const seen = new Set(prev.map((p) => p.id));
      const fresh = incoming.filter((it) => it.id && !seen.has(it.id));
      if (fresh.length === 0) return prev;
      // Merge: new ones first, sorted by received_ts desc — defensive in
      // case backfill arrives out of order with live messages.
      const merged = [...fresh, ...prev]
        .sort((a, b) => (b.received_ts ?? 0) - (a.received_ts ?? 0))
        .slice(0, MAX_ITEMS);
      return merged;
    });
    setUnreadCount((c) => c + incoming.length);
    // Track the highest stream id we have observed.
    for (const it of incoming) {
      if (it.stream_id && (!lastStreamIdRef.current || it.stream_id > lastStreamIdRef.current)) {
        lastStreamIdRef.current = it.stream_id;
      }
    }
  }, []);

  const fetchBackfill = useCallback(async () => {
    const sinceId = lastStreamIdRef.current;
    if (!sinceId) return;
    try {
      const res = await fetch(`/api/openul/backfill?since_id=${encodeURIComponent(sinceId)}`, {
        cache: 'no-store',
      });
      if (!res.ok) return;
      const data = await res.json();
      if (Array.isArray(data.results) && data.results.length > 0) {
        applyIncomingItems(data.results as OpenULNewsItem[]);
      }
    } catch {
      // Network/abort — the SSE reconnect below will retry via Last-Event-ID.
    }
  }, [applyIncomingItems]);

  // Carga de historial hacia atras (mas antiguo) desde la BD via cursor.
  const loadOlder = useCallback(async () => {
    if (loadingOlderRef.current || !hasMoreRef.current) return;

    const current = itemsRef.current;
    if (current.length >= HISTORY_HARD_CEILING) {
      setHasMore(false);
      return;
    }

    const oldest = current[current.length - 1];
    const beforeTs = oldest?.received_ts;
    if (beforeTs == null) return;

    loadingOlderRef.current = true;
    setLoadingOlder(true);
    try {
      const res = await fetch(
        `/api/openul/history?before_ts=${encodeURIComponent(beforeTs)}&limit=${HISTORY_PAGE_SIZE}`,
        { cache: 'no-store' },
      );
      if (!res.ok) return;
      const data = await res.json();
      const older = (Array.isArray(data.results) ? data.results : []) as OpenULNewsItem[];

      // Si el backend devolvio menos de una pagina completa, no hay mas.
      if (older.length < HISTORY_PAGE_SIZE) setHasMore(false);

      if (older.length > 0) {
        setItems((prev) => {
          const seen = new Set(prev.map((p) => p.id));
          const fresh = older.filter((it) => it.id && !seen.has(it.id));
          // Sin items nuevos => el cursor no avanza: paramos para no entrar
          // en un bucle de fetch contra el mismo borde.
          if (fresh.length === 0) {
            setHasMore(false);
            return prev;
          }
          return [...prev, ...fresh].sort(
            (a, b) => (b.received_ts ?? 0) - (a.received_ts ?? 0),
          );
        });
      }
    } catch {
      // Silencioso: el usuario puede reintentar haciendo scroll de nuevo.
    } finally {
      loadingOlderRef.current = false;
      setLoadingOlder(false);
    }
  }, []);

  const loadInitialNews = useCallback(async () => {
    if (initialLoadDone.current) return;
    try {
      const res = await fetch('/api/openul/news?limit=100');
      if (res.ok) {
        const data = await res.json();
        if (data.results?.length) {
          const initial: OpenULNewsItem[] = data.results;
          setItems(initial);
          // Seed lastStreamIdRef with the highest id from the initial load
          // so the very first reconnect can resume cleanly.
          for (const it of initial) {
            if (it.stream_id && (!lastStreamIdRef.current || it.stream_id > lastStreamIdRef.current)) {
              lastStreamIdRef.current = it.stream_id;
            }
          }
        }
      }
      initialLoadDone.current = true;
    } catch {
      // Silent — SSE will provide data
    }
  }, []);

  // ── connection lifecycle ─────────────────────────────────────────────

  const closeEventSource = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    closeEventSource();

    setStatus('connecting');

    // Pass our last stream id as a query-string fallback so the very first
    // connect — when the browser has no Last-Event-ID — can still resume
    // cleanly. Native auto-reconnects after this point use the standard
    // Last-Event-ID header (set automatically from `id:` lines).
    const url = lastStreamIdRef.current
      ? `/api/openul/stream?last_event_id=${encodeURIComponent(lastStreamIdRef.current)}`
      : '/api/openul/stream';
    const es = new EventSource(url);
    eventSourceRef.current = es;
    lastSseAtRef.current = Date.now();

    es.onopen = () => {
      setStatus('connected');
      lastSseAtRef.current = Date.now();
    };

    es.onmessage = (event) => {
      lastSseAtRef.current = Date.now();
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'connected') {
          setStatus('connected');
          return;
        }

        if (data.id && data.text) {
          applyIncomingItems([data as OpenULNewsItem]);
        }
      } catch {
        // Ignore keepalive comments and anything non-JSON
      }
    };

    es.onerror = () => {
      setStatus('error');
      closeEventSource();
      reconnectTimeoutRef.current = setTimeout(() => {
        // Fill any gap explicitly before reopening, in case the browser
        // didn't preserve Last-Event-ID across the failure.
        void fetchBackfill().finally(() => connect());
      }, 5_000);
    };
  }, [applyIncomingItems, closeEventSource, fetchBackfill]);

  const forceResync = useCallback(async () => {
    // Belt and suspenders: explicit backfill, then close + reopen SSE.
    await fetchBackfill();
    connect();
  }, [connect, fetchBackfill]);

  // ── visibility + watchdog ────────────────────────────────────────────

  useEffect(() => {
    if (!isWindowOpen || typeof document === 'undefined') return;

    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        hiddenSinceRef.current = Date.now();
        return;
      }
      // visibilityState === 'visible'
      const wasHiddenFor = hiddenSinceRef.current
        ? Date.now() - hiddenSinceRef.current
        : 0;
      hiddenSinceRef.current = 0;

      // If the tab was hidden long enough that the SSE connection is
      // likely zombie (or the browser throttled it), proactively resync.
      if (wasHiddenFor >= STALE_AFTER_HIDDEN_MS) {
        void forceResync();
      }
    };

    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('focus', onVisibility);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('focus', onVisibility);
    };
  }, [isWindowOpen, forceResync]);

  useEffect(() => {
    if (!isWindowOpen) {
      if (watchdogIntervalRef.current) {
        clearInterval(watchdogIntervalRef.current);
        watchdogIntervalRef.current = null;
      }
      return;
    }

    watchdogIntervalRef.current = setInterval(() => {
      // Only run while the tab is visible — hidden tabs have their own path.
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
        return;
      }
      const sinceLast = Date.now() - lastSseAtRef.current;
      if (sinceLast > SSE_WATCHDOG_MS) {
        void forceResync();
      }
    }, 30_000);

    return () => {
      if (watchdogIntervalRef.current) {
        clearInterval(watchdogIntervalRef.current);
        watchdogIntervalRef.current = null;
      }
    };
  }, [isWindowOpen, forceResync]);

  // ── window open/close ────────────────────────────────────────────────

  useEffect(() => {
    if (isWindowOpen) {
      initialLoadDone.current = false;
      lastStreamIdRef.current = null;
      lastSseAtRef.current = Date.now();
      hiddenSinceRef.current = 0;
      hasMoreRef.current = true;
      loadingOlderRef.current = false;
      setHasMore(true);
      setLoadingOlder(false);

      // Order matters: load history → seed stream id → connect SSE so the
      // very first connect resumes from the latest known event.
      void loadInitialNews().finally(() => connect());
    } else {
      closeEventSource();
      setStatus('disconnected');
      setItems([]);
      setUnreadCount(0);
      lastStreamIdRef.current = null;
      setHasMore(true);
      setLoadingOlder(false);
    }

    return () => {
      closeEventSource();
      setStatus('disconnected');
    };
  }, [isWindowOpen, connect, closeEventSource, loadInitialNews]);

  const clearUnread = useCallback(() => {
    setUnreadCount(0);
  }, []);

  const value: OpenULContextValue = {
    items,
    status,
    unreadCount,
    clearUnread,
    isWindowOpen,
    setWindowOpen,
    loadOlder,
    loadingOlder,
    hasMore,
  };

  return (
    <OpenULContext.Provider value={value}>
      {children}
    </OpenULContext.Provider>
  );
}

export function useOpenUL() {
  const ctx = useContext(OpenULContext);
  if (!ctx) throw new Error('useOpenUL must be used within OpenULProvider');
  return ctx;
}
