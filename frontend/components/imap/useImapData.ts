'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { enrichVenue } from './geo';
import type { ImapExchangesResponse, ImapVenue } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const REFRESH_MS = 60_000;
const TICK_MS = 30_000;

export interface UseImapDataResult {
  venues: ImapVenue[];
  loading: boolean;
  error: string | null;
  now: Date;
  refresh: () => void;
}

export function useImapData(): UseImapDataResult {
  const [venues, setVenues] = useState<ImapVenue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date());
  const abortRef = useRef<AbortController | null>(null);

  const fetchVenues = useCallback(async (silent = false) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    if (!silent) setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/v1/imap/exchanges`, {
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ImapExchangesResponse | ImapVenue[] = await res.json();
      const list = Array.isArray(data)
        ? data
        : Array.isArray(data.venues)
          ? data.venues
          : Array.isArray(data.exchanges)
            ? data.exchanges
            : [];
      setVenues(list.map(enrichVenue));
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchVenues();
    const refreshId = setInterval(() => fetchVenues(true), REFRESH_MS);
    return () => {
      clearInterval(refreshId);
      abortRef.current?.abort();
    };
  }, [fetchVenues]);

  useEffect(() => {
    const tickId = setInterval(() => setNow(new Date()), TICK_MS);
    return () => clearInterval(tickId);
  }, []);

  return {
    venues,
    loading,
    error,
    now,
    refresh: () => fetchVenues(false),
  };
}
