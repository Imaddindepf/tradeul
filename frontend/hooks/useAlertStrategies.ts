'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { useAuth } from '@clerk/nextjs';

// ============================================================================
// Types
// ============================================================================

export interface AlertStrategyFilters {
  min_price?: number;
  max_price?: number;
  min_change_percent?: number;
  max_change_percent?: number;
  min_rvol?: number;
  max_rvol?: number;
  min_volume?: number;
  max_volume?: number;
}

export interface AlertStrategy {
  id: number;
  userId: string;
  name: string;
  description: string | null;
  category: string;          // 'bullish' | 'bearish' | 'neutral' | 'custom'
  eventTypes: string[];
  filters: AlertStrategyFilters;
  isFavorite: boolean;
  useCount: number;
  lastUsedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface CreateStrategyData {
  name: string;
  description?: string;
  category?: string;
  event_types: string[];
  filters: AlertStrategyFilters;
  is_favorite?: boolean;
}

export interface UpdateStrategyData {
  name?: string;
  description?: string;
  category?: string;
  event_types?: string[];
  filters?: AlertStrategyFilters;
  is_favorite?: boolean;
}

// ============================================================================
// Hook
// ============================================================================

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export function useAlertStrategies() {
  const { getToken } = useAuth();
  const [strategies, setStrategies] = useState<AlertStrategy[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadedRef = useRef(false);

  const fetchWithAuth = useCallback(async (
    endpoint: string,
    options: RequestInit = {}
  ) => {
    const doFetch = async (skipCache: boolean) => {
      const token = await getToken({ skipCache });
      if (!token) throw new Error('Not authenticated');

      return fetch(`${API_BASE}/api/v1/alert-strategies${endpoint}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
          ...options.headers,
        },
      });
    };

    // First attempt with cached token
    let response = await doFetch(false);

    // If 401 (JWT expired), retry ONCE with fresh token
    if (response.status === 401) {
      response = await doFetch(true);
    }

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || `HTTP ${response.status}`);
    }

    if (response.status === 204) return null;
    return response.json();
  }, [getToken]);

  // List all strategies
  const listStrategies = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchWithAuth('');
      setStrategies(data.strategies || []);
      return data.strategies as AlertStrategy[];
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load strategies';
      setError(msg);
      return [];
    } finally {
      setLoading(false);
    }
  }, [fetchWithAuth]);

  // Auto-load on mount (once)
  useEffect(() => {
    if (!loadedRef.current) {
      loadedRef.current = true;
      listStrategies();
    }
  }, [listStrategies]);

  // Create strategy
  const createStrategy = useCallback(async (data: CreateStrategyData) => {
    setLoading(true);
    setError(null);
    try {
      const strategy = await fetchWithAuth('', {
        method: 'POST',
        body: JSON.stringify(data),
      });
      setStrategies(prev => [strategy, ...prev]);
      return strategy as AlertStrategy;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to create strategy';
      setError(msg);
      return null;
    } finally {
      setLoading(false);
    }
  }, [fetchWithAuth]);

  // Update strategy
  const updateStrategy = useCallback(async (id: number, data: UpdateStrategyData) => {
    setLoading(true);
    setError(null);
    try {
      const strategy = await fetchWithAuth(`/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      });
      setStrategies(prev => prev.map(s => s.id === id ? strategy : s));
      return strategy as AlertStrategy;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to update strategy';
      setError(msg);
      return null;
    } finally {
      setLoading(false);
    }
  }, [fetchWithAuth]);

  // Delete strategy
  const deleteStrategy = useCallback(async (id: number) => {
    setLoading(true);
    setError(null);
    try {
      await fetchWithAuth(`/${id}`, { method: 'DELETE' });
      setStrategies(prev => prev.filter(s => s.id !== id));
      return true;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to delete strategy';
      setError(msg);
      return false;
    } finally {
      setLoading(false);
    }
  }, [fetchWithAuth]);

  // Track usage
  const useStrategy = useCallback(async (id: number) => {
    try {
      const strategy = await fetchWithAuth(`/${id}/use`, { method: 'POST' });
      setStrategies(prev => prev.map(s => s.id === id ? strategy : s));
      return strategy as AlertStrategy;
    } catch {
      return null;
    }
  }, [fetchWithAuth]);

  // Duplicate
  const duplicateStrategy = useCallback(async (id: number) => {
    setLoading(true);
    setError(null);
    try {
      const strategy = await fetchWithAuth(`/${id}/duplicate`, { method: 'POST' });
      setStrategies(prev => [...prev, strategy]);
      return strategy as AlertStrategy;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to duplicate strategy';
      setError(msg);
      return null;
    } finally {
      setLoading(false);
    }
  }, [fetchWithAuth]);

  // Toggle favorite
  const toggleFavorite = useCallback(async (id: number) => {
    const strategy = strategies.find(s => s.id === id);
    if (!strategy) return null;
    return updateStrategy(id, { is_favorite: !strategy.isFavorite });
  }, [strategies, updateStrategy]);

  // Helpers
  const getRecent = useCallback((limit = 10) => {
    return strategies
      .filter(s => s.lastUsedAt)
      .sort((a, b) => new Date(b.lastUsedAt!).getTime() - new Date(a.lastUsedAt!).getTime())
      .slice(0, limit);
  }, [strategies]);

  const getFavorites = useCallback(() => {
    return strategies.filter(s => s.isFavorite);
  }, [strategies]);

  const getByCategory = useCallback((cat: string) => {
    return strategies.filter(s => s.category === cat);
  }, [strategies]);

  return {
    strategies,
    loading,
    error,
    listStrategies,
    createStrategy,
    updateStrategy,
    deleteStrategy,
    useStrategy,
    duplicateStrategy,
    toggleFavorite,
    getRecent,
    getFavorites,
    getByCategory,
  };
}
