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

export function OpenULProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<OpenULNewsItem[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [unreadCount, setUnreadCount] = useState(0);
  const [isWindowOpen, setWindowOpen] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const initialLoadDone = useRef(false);

  const loadInitialNews = useCallback(async () => {
    if (initialLoadDone.current) return;
    try {
      const res = await fetch('/api/openul/news?limit=100');
      if (res.ok) {
        const data = await res.json();
        if (data.results?.length) {
          setItems(data.results);
        }
      }
      initialLoadDone.current = true;
    } catch {
      // Silent — SSE will provide data
    }
  }, []);

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    setStatus('disconnected');
  }, []);

  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    setStatus('connecting');
    const es = new EventSource('/api/openul/stream');
    eventSourceRef.current = es;

    es.onopen = () => {
      setStatus('connected');
    };

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'connected') {
          setStatus('connected');
          return;
        }

        if (data.id && data.text) {
          const newsItem: OpenULNewsItem = data;
          setItems((prev) => {
            const exists = prev.some((p) => p.id === newsItem.id);
            if (exists) return prev;
            const next = [newsItem, ...prev];
            return next.slice(0, MAX_ITEMS);
          });
          setUnreadCount((c) => c + 1);
        }
      } catch {
        // Ignore keepalive comments
      }
    };

    es.onerror = () => {
      setStatus('error');
      es.close();
      eventSourceRef.current = null;

      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, 5000);
    };
  }, []);

  // Connect/disconnect based on window open state
  useEffect(() => {
    if (isWindowOpen) {
      initialLoadDone.current = false;
      loadInitialNews();
      connect();
    } else {
      disconnect();
      setItems([]);
      setUnreadCount(0);
    }

    return () => {
      disconnect();
    };
  }, [isWindowOpen, connect, disconnect, loadInitialNews]);

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
