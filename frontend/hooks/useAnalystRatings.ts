'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '@clerk/nextjs';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export interface AnalystConsensus {
  averagePriceTarget: number;
  medianPriceTarget: number;
  highPriceTarget: number;
  lowPriceTarget: number;
  totalRatings: number;
  bullishCount: number;
  neutralCount: number;
  bearishCount: number;
  consensusRating: string;
  bullishPercentage: number;
  neutralPercentage: number;
  bearishPercentage: number;
}

export interface AnalystRating {
  releaseDate: string;
  firm: string;
  analystName: string;
  actionCompany: string;
  ratingCurrent: string;
  ratingPrior: string;
  priceTargetCurrent: number;
  priceTargetPrior: number;
  currency: string;
  sentiment: string;
}

export interface AnalystRatingsData {
  consensus: AnalystConsensus;
  ratings: AnalystRating[];
}

export function useAnalystRatings(initialTicker?: string) {
  const { getToken } = useAuth();
  const [ticker, setTicker] = useState(initialTicker?.toUpperCase() || '');
  const [data, setData] = useState<AnalystRatingsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchRatings = useCallback(async (symbol: string) => {
    if (!symbol) return;
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setLoading(true);
    setError(null);

    try {
      const token = await getToken();
      const res = await fetch(`${API_BASE}/api/v1/analyst-ratings/${symbol.toUpperCase()}`, {
        signal: ac.signal,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        if (res.status === 401) throw new Error('Authentication required');
        if (res.status === 502) throw new Error('Data unavailable');
        throw new Error(`Error ${res.status}`);
      }
      const json: AnalystRatingsData = await res.json();
      if (!ac.signal.aborted) setData(json);
    } catch (e: any) {
      if (e.name !== 'AbortError' && !ac.signal.aborted) {
        setError(e.message || 'Failed to fetch');
      }
    } finally {
      if (!ac.signal.aborted) setLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    if (ticker) fetchRatings(ticker);
    return () => { abortRef.current?.abort(); };
  }, [ticker, fetchRatings]);

  const search = useCallback((sym: string) => {
    const upper = sym.toUpperCase().trim();
    if (upper && upper !== ticker) {
      setTicker(upper);
    }
  }, [ticker]);

  return { data, loading, error, ticker, search, refetch: () => fetchRatings(ticker) };
}
