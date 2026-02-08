/**
 * Heatmap Data Hook
 * 
 * Fetches market heatmap data with intelligent polling.
 * - Smooth updates without visible refresh
 * - Automatic retry on error
 * - Configurable polling interval
 * - Deduplication of requests
 */

import { useState, useEffect, useCallback, useRef } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Default polling interval (10 seconds)
const DEFAULT_POLL_INTERVAL = 10000;

// Retry delay on error (5 seconds)
const ERROR_RETRY_DELAY = 5000;

export type ColorMetric = 'change_percent' | 'rvol' | 'chg_5min' | 'price_vs_vwap';
export type SizeMetric = 'market_cap' | 'volume_today' | 'dollar_volume';

export interface HeatmapTicker {
  symbol: string;
  name: string;
  sector: string;
  industry: string;
  price: number;
  change_percent: number;
  market_cap: number;
  volume_today: number;
  dollar_volume: number;
  rvol: number;
  chg_5min: number;
  price_vs_vwap: number;
  logo_url?: string;
  icon_url?: string;
}

export interface HeatmapIndustry {
  industry: string;
  ticker_count: number;
  total_market_cap: number;
  avg_change_percent: number;
  tickers: HeatmapTicker[];
}

export interface HeatmapSector {
  sector: string;
  color: string;
  ticker_count: number;
  total_market_cap: number;
  total_volume: number;
  avg_change_percent: number;
  industries: HeatmapIndustry[];
}

export interface HeatmapData {
  timestamp: string;
  total_tickers: number;
  total_market_cap: number;
  market_avg_change: number;
  metric: string;
  size_by: string;
  sectors: HeatmapSector[];
  is_realtime: boolean;  // false cuando el mercado está cerrado y usa datos del último cierre
}

export interface HeatmapFilters {
  metric: ColorMetric;
  sizeBy: SizeMetric;
  minMarketCap: number | null;
  maxTickersPerSector: number;
  excludeEtfs: boolean;
  sectors: string[] | null;
}

export interface UseHeatmapDataOptions {
  pollInterval?: number;
  enabled?: boolean;
}

export interface UseHeatmapDataReturn {
  data: HeatmapData | null;
  isLoading: boolean;
  isUpdating: boolean;
  error: string | null;
  lastUpdate: Date | null;
  filters: HeatmapFilters;
  setFilters: (filters: Partial<HeatmapFilters>) => void;
  refresh: () => Promise<void>;
}

const DEFAULT_FILTERS: HeatmapFilters = {
  metric: 'change_percent',
  sizeBy: 'market_cap',
  minMarketCap: null,
  maxTickersPerSector: 100,
  excludeEtfs: true,
  sectors: null,
};

export function useHeatmapData(
  options: UseHeatmapDataOptions = {}
): UseHeatmapDataReturn {
  const { pollInterval = DEFAULT_POLL_INTERVAL, enabled = true } = options;
  
  const [data, setData] = useState<HeatmapData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isUpdating, setIsUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [filters, setFiltersState] = useState<HeatmapFilters>(DEFAULT_FILTERS);
  
  // Refs for managing polling
  const pollTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isFetchingRef = useRef(false);
  const mountedRef = useRef(true);
  
  // Build query string from filters
  const buildQueryString = useCallback((f: HeatmapFilters): string => {
    const params = new URLSearchParams();
    params.set('metric', f.metric);
    params.set('size_by', f.sizeBy);
    params.set('max_tickers_per_sector', f.maxTickersPerSector.toString());
    params.set('exclude_etfs', f.excludeEtfs.toString());
    
    if (f.minMarketCap !== null) {
      params.set('min_market_cap', f.minMarketCap.toString());
    }
    
    if (f.sectors && f.sectors.length > 0) {
      params.set('sectors', f.sectors.join(','));
    }
    
    return params.toString();
  }, []);
  
  // Fetch data from API
  const fetchData = useCallback(async (showUpdating = false) => {
    // Prevent concurrent fetches
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    
    // Show updating indicator if we already have data
    if (showUpdating && data) {
      setIsUpdating(true);
    }
    
    try {
      const queryString = buildQueryString(filters);
      const response = await fetch(`${API_URL}/api/v1/heatmap?${queryString}`);
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const newData: HeatmapData = await response.json();
      
      // Only update if component is still mounted
      if (mountedRef.current) {
        setData(newData);
        setLastUpdate(new Date());
        setError(null);
        setIsLoading(false);
        setIsUpdating(false);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to fetch heatmap data');
        setIsLoading(false);
        setIsUpdating(false);
      }
    } finally {
      isFetchingRef.current = false;
    }
  }, [filters, buildQueryString, data]);
  
  // Manual refresh
  const refresh = useCallback(async () => {
    if (data) {
      setIsUpdating(true);
    } else {
      setIsLoading(true);
    }
    await fetchData(true);
  }, [fetchData, data]);
  
  // Update filters
  const setFilters = useCallback((newFilters: Partial<HeatmapFilters>) => {
    setFiltersState(prev => ({ ...prev, ...newFilters }));
  }, []);
  
  // Setup polling
  useEffect(() => {
    mountedRef.current = true;
    
    if (!enabled) {
      return;
    }
    
    // Initial fetch
    fetchData();
    
    // Setup polling interval
    const scheduleNextPoll = (delay: number) => {
      if (pollTimeoutRef.current) {
        clearTimeout(pollTimeoutRef.current);
      }
      
      pollTimeoutRef.current = setTimeout(async () => {
        if (!mountedRef.current || !enabled) return;
        
        await fetchData();
        
        // Schedule next poll (use error delay if there was an error)
        if (mountedRef.current && enabled) {
          scheduleNextPoll(error ? ERROR_RETRY_DELAY : pollInterval);
        }
      }, delay);
    };
    
    // Start polling after initial fetch
    scheduleNextPoll(pollInterval);
    
    // Cleanup
    return () => {
      mountedRef.current = false;
      if (pollTimeoutRef.current) {
        clearTimeout(pollTimeoutRef.current);
        pollTimeoutRef.current = null;
      }
    };
  }, [enabled, pollInterval, fetchData, error]);
  
  // Refetch when filters change - show updating indicator
  useEffect(() => {
    if (enabled && data !== null) {
      // Show updating indicator for filter changes
      fetchData(true);
    }
  }, [filters]); // eslint-disable-line react-hooks/exhaustive-deps
  
  return {
    data,
    isLoading,
    isUpdating,
    error,
    lastUpdate,
    filters,
    setFilters,
    refresh,
  };
}
