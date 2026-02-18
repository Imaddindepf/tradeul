import { useState, useEffect, useCallback, useRef } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export type PulseTab = 'sectors' | 'industries' | 'themes';

export interface PerformanceEntry {
  name: string;
  count: number;
  advancing: number;
  declining: number;
  unchanged: number;
  breadth: number;
  avg_change: number;
  median_change: number;
  weighted_change: number;
  avg_rvol: number;
  total_volume: number;
  total_dollar_volume: number;
  total_market_cap: number;
  movers?: {
    gainers: DrilldownTicker[];
    losers: DrilldownTicker[];
  };
}

export interface DrilldownTicker {
  symbol: string;
  price: number | null;
  change_percent: number;
  volume: number | null;
  market_cap: number | null;
  sector?: string;
  industry?: string;
}

export interface PerformanceResponse {
  group_by: string;
  data: PerformanceEntry[];
  timestamp: number;
  total_tickers: number;
}

export interface DrilldownResponse {
  group_type: string;
  group_name: string;
  data: DrilldownTicker[];
  total: number;
}

export function useMarketPulse({
  tab,
  refreshInterval = 15000,
  minMarketCap,
  sectorFilter,
}: {
  tab: PulseTab;
  refreshInterval?: number;
  minMarketCap?: number;
  sectorFilter?: string;
}) {
  const [data, setData] = useState<PerformanceEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<number>(0);
  const [totalTickers, setTotalTickers] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval>>();

  const fetchData = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (minMarketCap) params.set('min_market_cap', String(minMarketCap));
      params.set('include_movers', 'true');

      let endpoint: string;
      if (tab === 'sectors') {
        endpoint = '/api/v1/performance/sectors';
      } else if (tab === 'industries') {
        endpoint = '/api/v1/performance/industries';
        if (sectorFilter) params.set('sector', sectorFilter);
      } else {
        endpoint = '/api/v1/performance/themes';
        params.set('min_tickers', '3');
      }

      const url = `${API_BASE}${endpoint}?${params.toString()}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const json: PerformanceResponse = await res.json();
      setData(json.data);
      setLastUpdate(json.timestamp);
      setTotalTickers(json.total_tickers);
      setError(null);
    } catch (e: any) {
      setError(e.message || 'Failed to fetch');
    } finally {
      setLoading(false);
    }
  }, [tab, minMarketCap, sectorFilter]);

  useEffect(() => {
    setLoading(true);
    fetchData();
    intervalRef.current = setInterval(fetchData, refreshInterval);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchData, refreshInterval]);

  return { data, loading, error, lastUpdate, totalTickers, refetch: fetchData };
}

export function useDrilldown() {
  const [data, setData] = useState<DrilldownTicker[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);

  const fetchDrilldown = useCallback(async (
    groupType: string,
    groupName: string,
    minMarketCap?: number,
    sortBy: string = 'change_percent',
  ) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ sort_by: sortBy, limit: '100' });
      if (minMarketCap) params.set('min_market_cap', String(minMarketCap));
      const encoded = encodeURIComponent(groupName);
      const url = `${API_BASE}/api/v1/performance/drilldown/${groupType}/${encoded}?${params}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: DrilldownResponse = await res.json();
      setData(json.data);
      setTotal(json.total);
    } catch {
      setData([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, total, fetchDrilldown };
}
