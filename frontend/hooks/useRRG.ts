import { useState, useEffect, useRef, useCallback } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface RRGTrailPoint {
  date: string;
  x: number;
  y: number;
}

export interface RRGGroup {
  name: string;
  count: number;
  trail: RRGTrailPoint[];
  current: RRGTrailPoint;
  quadrant: 'leading' | 'weakening' | 'lagging' | 'improving';
}

export interface RRGData {
  groups: RRGGroup[];
  quadrant_distribution: Record<string, number>;
  axis_labels: { x: string; y: string };
  rs_metric: string;
  rs_metric_label: string;
  benchmark: string;
  rs_metrics: Record<string, string>;
}

interface UseRRGParams {
  groupBy: string;
  rsMetric: string;
  benchmark: string;
  tailLength: number;
  minMarketCap?: number;
  enabled?: boolean;
}

export function useRRG({ groupBy, rsMetric, benchmark, tailLength, minMarketCap, enabled = true }: UseRRGParams) {
  const [data, setData] = useState<RRGData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchRRG = useCallback(async () => {
    if (!enabled) return;

    abortRef.current?.abort();
    abortRef.current = new AbortController();

    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({
        group_by: groupBy,
        rs_metric: rsMetric,
        benchmark,
        tail_length: String(tailLength),
      });
      if (minMarketCap) params.set('min_market_cap', String(minMarketCap));

      const res = await fetch(`${API_URL}/api/v1/performance/rrg?${params}`, {
        signal: abortRef.current.signal,
        cache: 'no-store',
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setError(err.message);
        console.error('RRG fetch error:', err);
      }
    } finally {
      setLoading(false);
    }
  }, [groupBy, rsMetric, benchmark, tailLength, minMarketCap, enabled]);

  useEffect(() => {
    fetchRRG();
    return () => abortRef.current?.abort();
  }, [fetchRRG]);

  useEffect(() => {
    if (!enabled) return;
    const interval = setInterval(fetchRRG, 30_000);
    return () => clearInterval(interval);
  }, [fetchRRG, enabled]);

  return { data, loading, error, refetch: fetchRRG };
}
