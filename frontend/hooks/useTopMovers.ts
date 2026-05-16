import { useEffect, useRef, useState } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface TopMover {
  symbol: string;
  price: number | null;
  change_percent: number | null;
  volume: number | null;
}

export interface TopMoversState {
  tickers: TopMover[];
  loading: boolean;
  error: string | null;
  source: string | null;
  updatedAt: number | null;
}

interface UseTopMoversOptions {
  limit?: number;
  mix?: 'balanced' | 'gainers' | 'losers' | 'abs';
  minPrice?: number;
  minVolume?: number;
  /** Intervalo de refresh en ms. Default 5000. Poner 0 para desactivar polling. */
  refreshMs?: number;
}

/**
 * Hook público (sin auth) para consumir /api/public/top-movers.
 * Ideal para el ticker tape del landing page.
 * Retorna tickers vacíos si el backend no está disponible (el consumidor
 * debe tener su propio fallback estático).
 */
export function useTopMovers(options: UseTopMoversOptions = {}): TopMoversState {
  const {
    limit = 20,
    mix = 'balanced',
    minPrice = 1,
    minVolume = 100_000,
    refreshMs = 5000,
  } = options;

  const [state, setState] = useState<TopMoversState>({
    tickers: [],
    loading: true,
    error: null,
    source: null,
    updatedAt: null,
  });

  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchMovers = async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const params = new URLSearchParams({
        limit: String(limit),
        mix,
        min_price: String(minPrice),
        min_volume: String(minVolume),
      });

      try {
        const res = await fetch(`${API_URL}/api/public/top-movers?${params}`, {
          signal: controller.signal,
          cache: 'no-store',
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (cancelled) return;
        setState({
          tickers: Array.isArray(data?.tickers) ? data.tickers : [],
          loading: false,
          error: null,
          source: data?.source ?? null,
          updatedAt: typeof data?.updated_at === 'number' ? data.updated_at : Date.now() / 1000,
        });
      } catch (err) {
        if (cancelled) return;
        if ((err as Error).name === 'AbortError') return;
        setState((prev) => ({
          ...prev,
          loading: false,
          error: (err as Error).message || 'fetch_error',
        }));
      }
    };

    fetchMovers();

    if (refreshMs > 0) {
      const id = setInterval(fetchMovers, refreshMs);
      return () => {
        cancelled = true;
        clearInterval(id);
        abortRef.current?.abort();
      };
    }

    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [limit, mix, minPrice, minVolume, refreshMs]);

  return state;
}
