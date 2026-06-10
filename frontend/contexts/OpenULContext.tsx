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
}

const OpenULContext = createContext<OpenULContextValue | null>(null);

const MAX_ITEMS = 200;

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

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const watchdogIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const initialLoadDone = useRef(false);

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

      // Order matters: load history → seed stream id → connect SSE so the
      // very first connect resumes from the latest known event.
      void loadInitialNews().finally(() => connect());
    } else {
      closeEventSource();
      setStatus('disconnected');
      setItems([]);
      setUnreadCount(0);
      lastStreamIdRef.current = null;
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
