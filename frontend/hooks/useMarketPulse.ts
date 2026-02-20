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
  avg_rsi: number;
  avg_daily_rsi: number;
  avg_atr_pct: number;
  avg_daily_atr_pct: number;
  avg_gap_pct: number;
  avg_adx: number;
  avg_daily_adx: number;
  avg_dist_vwap: number;
  avg_change_5d: number;
  avg_change_10d: number;
  avg_change_20d: number;
  avg_from_52w_high: number;
  avg_from_52w_low: number;
  avg_float_turnover: number;
  avg_bid_ask_ratio: number;
  avg_pos_in_range: number;
  avg_bb_position: number;
  avg_trades_z: number;
  avg_range_pct: number;
  avg_dist_sma20: number;
  avg_dist_sma50: number;
  avg_vol_today_pct: number;
  movers?: {
    gainers: DrilldownTicker[];
    losers: DrilldownTicker[];
  };
  _prev?: Record<string, number>;
  _changedKeys?: Set<string>;
}

export interface DrilldownTicker {
  symbol: string;
  price: number | null;
  change_percent: number;
  volume: number | null;
  market_cap: number | null;
  sector?: string;
  industry?: string;
  rvol?: number;
  dollar_volume?: number;
  gap_percent?: number;
  atr_percent?: number;
  rsi_14?: number;
  daily_rsi?: number;
  daily_atr_percent?: number;
  adx_14?: number;
  daily_adx_14?: number;
  vwap?: number;
  dist_from_vwap?: number;
  change_5d?: number;
  change_10d?: number;
  change_20d?: number;
  from_52w_high?: number;
  from_52w_low?: number;
  float_turnover?: number;
  bid_ask_ratio?: number;
  pos_in_range?: number;
  daily_bb_position?: number;
  trades_z_score?: number;
  avg_volume_20d?: number;
  _relative?: number;
  _changedKeys?: Set<string>;
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

const TRACKED_KEYS = [
  'weighted_change', 'avg_change', 'median_change', 'breadth', 'avg_rvol',
  'avg_rsi', 'avg_daily_rsi', 'avg_atr_pct', 'avg_gap_pct', 'avg_adx',
  'avg_change_5d', 'avg_change_10d', 'avg_change_20d', 'avg_from_52w_high',
  'avg_pos_in_range', 'avg_bb_position', 'avg_dist_vwap', 'avg_vol_today_pct',
  'avg_dist_sma20', 'avg_dist_sma50', 'avg_range_pct',
];

const DD_TRACKED_KEYS = [
  'change_percent', 'price', 'volume', 'rsi_14', 'daily_rsi',
  'gap_percent', 'dist_from_vwap', 'pos_in_range', 'daily_bb_position',
  'rvol', 'atr_percent', 'adx_14', 'market_cap',
];

export function useMarketPulse({
  tab,
  refreshInterval = 3000,
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
  const [tickCount, setTickCount] = useState(0);
  const prevMapRef = useRef<Map<string, Record<string, number>>>(new Map());
  const intervalRef = useRef<ReturnType<typeof setInterval>>();

  const fetchData = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (minMarketCap) params.set('min_market_cap', String(minMarketCap));
      if (sectorFilter) params.set('sector', sectorFilter);
      const url = `${API_BASE}/api/v1/performance/${tab}?${params}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: PerformanceResponse = await res.json();

      const prevMap = prevMapRef.current;
      const enriched = json.data.map(entry => {
        const prev = prevMap.get(entry.name);
        const changedKeys = new Set<string>();
        if (prev) {
          for (const key of TRACKED_KEYS) {
            const cur = (entry as any)[key];
            const old = prev[key];
            if (cur !== undefined && old !== undefined && Math.abs(cur - old) >= 0.0005) {
              changedKeys.add(key);
            }
          }
        }
        return { ...entry, _prev: prev || undefined, _changedKeys: changedKeys };
      });

      const newMap = new Map<string, Record<string, number>>();
      json.data.forEach(e => {
        const snap: Record<string, number> = {};
        for (const key of TRACKED_KEYS) {
          const v = (e as any)[key];
          if (v !== undefined) snap[key] = v;
        }
        newMap.set(e.name, snap);
      });
      prevMapRef.current = newMap;

      setData(enriched);
      setLastUpdate(json.timestamp);
      setTotalTickers(json.total_tickers);
      setTickCount(c => c + 1);
      setError(null);
    } catch (e: any) {
      setError(e.message || 'Failed to fetch');
    } finally {
      setLoading(false);
    }
  }, [tab, minMarketCap, sectorFilter]);

  useEffect(() => {
    prevMapRef.current = new Map();
    setLoading(true);
    fetchData();
    intervalRef.current = setInterval(fetchData, refreshInterval);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchData, refreshInterval]);

  return { data, loading, error, lastUpdate, totalTickers, tickCount, refetch: fetchData };
}

export function useDrilldown() {
  const [data, setData] = useState<DrilldownTicker[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [ddTickCount, setDdTickCount] = useState(0);
  const prevMapRef = useRef<Map<string, Record<string, number>>>(new Map());

  const fetchDrilldown = useCallback(async (
    groupType: string,
    groupName: string,
    groupAvgChange?: number,
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

      const prevMap = prevMapRef.current;
      const enriched = json.data.map(t => {
        const prev = prevMap.get(t.symbol);
        const changedKeys = new Set<string>();
        if (prev) {
          for (const key of DD_TRACKED_KEYS) {
            const cur = (t as any)[key];
            const old = prev[key];
            if (cur != null && old != null && Math.abs(cur - old) >= 0.0005) {
              changedKeys.add(key);
            }
          }
        }
        const relative = groupAvgChange != null ? (t.change_percent || 0) - groupAvgChange : undefined;
        return { ...t, _relative: relative, _changedKeys: changedKeys };
      });

      const newMap = new Map<string, Record<string, number>>();
      json.data.forEach(t => {
        const snap: Record<string, number> = {};
        for (const key of DD_TRACKED_KEYS) {
          const v = (t as any)[key];
          if (v != null) snap[key] = v;
        }
        newMap.set(t.symbol, snap);
      });
      prevMapRef.current = newMap;

      setData(enriched);
      setTotal(json.total);
      setDdTickCount(c => c + 1);
    } catch {
      setData([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  const resetPrevMap = useCallback(() => { prevMapRef.current = new Map(); }, []);

  return { data, loading, total, ddTickCount, fetchDrilldown, resetPrevMap };
}
