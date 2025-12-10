/**
 * Hook for managing watchlists with real-time quotes
 */

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@clerk/nextjs';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface WatchlistTicker {
  symbol: string;
  exchange: string;
  section_id: string | null;
  added_at: string;
  notes: string | null;
  alert_price_above: number | null;
  alert_price_below: number | null;
  alert_change_percent: number | null;
  position_size: number | null;
  weight: number | null;
  tags: string[];
  position: number;
}

export interface WatchlistSection {
  id: string;
  watchlist_id: string;
  name: string;
  color: string | null;
  icon: string | null;
  is_collapsed: boolean;
  position: number;
  created_at: string;
  updated_at: string;
  tickers: WatchlistTicker[];
}

export interface Watchlist {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  color: string | null;
  icon: string | null;
  is_synthetic_etf: boolean;
  columns: string[];
  sections: WatchlistSection[];  // Secciones con sus tickers
  tickers: WatchlistTicker[];    // Tickers sin sección (unsorted)
  sort_by: string | null;
  sort_order: string;
  position: number;
  created_at: string;
  updated_at: string;
}

export interface WatchlistCreate {
  name: string;
  description?: string;
  color?: string;
  icon?: string;
  is_synthetic_etf?: boolean;
}

export interface WatchlistUpdate {
  name?: string;
  description?: string;
  color?: string;
  icon?: string;
  is_synthetic_etf?: boolean;
  columns?: string[];
  sort_by?: string;
  sort_order?: string;
  position?: number;
}

export function useWatchlists() {
  const { userId } = useAuth();
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [activeWatchlistId, setActiveWatchlistId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch watchlists
  const fetchWatchlists = useCallback(async () => {
    if (!userId) return;

    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/api/v1/watchlists?user_id=${userId}`);
      if (!res.ok) throw new Error('Failed to fetch watchlists');

      const data = await res.json();
      setWatchlists(data);

      // Set active watchlist if not set
      if (!activeWatchlistId && data.length > 0) {
        setActiveWatchlistId(data[0].id);
      }

      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [userId, activeWatchlistId]);

  // Initial fetch
  useEffect(() => {
    fetchWatchlists();
  }, [fetchWatchlists]);

  // Create watchlist
  const createWatchlist = useCallback(async (data: WatchlistCreate): Promise<Watchlist | null> => {
    if (!userId) return null;

    try {
      const res = await fetch(`${API_URL}/api/v1/watchlists?user_id=${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });

      if (!res.ok) throw new Error('Failed to create watchlist');

      const newWatchlist = await res.json();
      setWatchlists(prev => [...prev, newWatchlist]);
      setActiveWatchlistId(newWatchlist.id);

      return newWatchlist;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      return null;
    }
  }, [userId]);

  // Update watchlist
  const updateWatchlist = useCallback(async (id: string, data: WatchlistUpdate): Promise<boolean> => {
    if (!userId) return false;

    try {
      const res = await fetch(`${API_URL}/api/v1/watchlists/${id}?user_id=${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });

      if (!res.ok) throw new Error('Failed to update watchlist');

      const updated = await res.json();
      setWatchlists(prev => prev.map(w => w.id === id ? updated : w));

      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      return false;
    }
  }, [userId]);

  // Delete watchlist
  const deleteWatchlist = useCallback(async (id: string): Promise<boolean> => {
    if (!userId) return false;

    try {
      const res = await fetch(`${API_URL}/api/v1/watchlists/${id}?user_id=${userId}`, {
        method: 'DELETE',
      });

      if (!res.ok) throw new Error('Failed to delete watchlist');

      setWatchlists(prev => prev.filter(w => w.id !== id));

      // Set new active if deleted was active
      if (activeWatchlistId === id) {
        const remaining = watchlists.filter(w => w.id !== id);
        setActiveWatchlistId(remaining.length > 0 ? remaining[0].id : null);
      }

      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      return false;
    }
  }, [userId, activeWatchlistId, watchlists]);

  // Add ticker
  const addTicker = useCallback(async (watchlistId: string, symbol: string): Promise<boolean> => {
    if (!userId) return false;

    try {
      const res = await fetch(`${API_URL}/api/v1/watchlists/${watchlistId}/tickers?user_id=${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: symbol.toUpperCase() }),
      });

      if (!res.ok) throw new Error('Failed to add ticker');

      const newTicker = await res.json();
      setWatchlists(prev => prev.map(w =>
        w.id === watchlistId
          ? { ...w, tickers: [...w.tickers, newTicker] }
          : w
      ));

      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      return false;
    }
  }, [userId]);

  // Add batch tickers
  const addTickersBatch = useCallback(async (watchlistId: string, symbols: string[]): Promise<number> => {
    if (!userId) return 0;

    try {
      const res = await fetch(`${API_URL}/api/v1/watchlists/${watchlistId}/tickers/batch?user_id=${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(symbols.map(s => s.toUpperCase())),
      });

      if (!res.ok) throw new Error('Failed to add tickers');

      const result = await res.json();

      // Refresh watchlists to get updated tickers
      await fetchWatchlists();

      return result.added;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      return 0;
    }
  }, [userId, fetchWatchlists]);

  // Remove ticker
  const removeTicker = useCallback(async (watchlistId: string, symbol: string): Promise<boolean> => {
    if (!userId) return false;

    try {
      const res = await fetch(
        `${API_URL}/api/v1/watchlists/${watchlistId}/tickers/${symbol.toUpperCase()}?user_id=${userId}`,
        { method: 'DELETE' }
      );

      if (!res.ok) throw new Error('Failed to remove ticker');

      setWatchlists(prev => prev.map(w =>
        w.id === watchlistId
          ? { ...w, tickers: w.tickers.filter(t => t.symbol !== symbol.toUpperCase()) }
          : w
      ));

      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      return false;
    }
  }, [userId]);

  // ============================================================================
  // Section CRUD
  // ============================================================================

  // Create section
  const createSection = useCallback(async (
    watchlistId: string,
    data: { name: string; color?: string; icon?: string }
  ): Promise<WatchlistSection | null> => {
    if (!userId) return null;

    try {
      const res = await fetch(`${API_URL}/api/v1/watchlists/${watchlistId}/sections?user_id=${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });

      if (!res.ok) throw new Error('Failed to create section');

      const newSection = await res.json();
      setWatchlists(prev => prev.map(w =>
        w.id === watchlistId
          ? { ...w, sections: [...w.sections, newSection] }
          : w
      ));

      return newSection;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      return null;
    }
  }, [userId]);

  // Update section
  const updateSection = useCallback(async (
    watchlistId: string,
    sectionId: string,
    data: { name?: string; color?: string; icon?: string; is_collapsed?: boolean }
  ): Promise<boolean> => {
    if (!userId) return false;

    try {
      const res = await fetch(`${API_URL}/api/v1/watchlists/${watchlistId}/sections/${sectionId}?user_id=${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });

      if (!res.ok) throw new Error('Failed to update section');

      const updated = await res.json();
      setWatchlists(prev => prev.map(w =>
        w.id === watchlistId
          ? { ...w, sections: w.sections.map(s => s.id === sectionId ? updated : s) }
          : w
      ));

      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      return false;
    }
  }, [userId]);

  // Delete section
  const deleteSection = useCallback(async (
    watchlistId: string,
    sectionId: string,
    moveTickersTo?: string  // Another section ID or undefined for unsorted
  ): Promise<boolean> => {
    if (!userId) return false;

    try {
      const url = new URL(`${API_URL}/api/v1/watchlists/${watchlistId}/sections/${sectionId}`);
      url.searchParams.set('user_id', userId);
      if (moveTickersTo) {
        url.searchParams.set('move_tickers_to', moveTickersTo);
      }

      const res = await fetch(url.toString(), { method: 'DELETE' });

      if (!res.ok) throw new Error('Failed to delete section');

      // Refresh to get updated state
      await fetchWatchlists();

      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      return false;
    }
  }, [userId, fetchWatchlists]);

  // Move tickers to section
  const moveTickersToSection = useCallback(async (
    watchlistId: string,
    sectionId: string,  // Use 'unsorted' for no section
    symbols: string[]
  ): Promise<boolean> => {
    if (!userId) return false;

    try {
      const res = await fetch(
        `${API_URL}/api/v1/watchlists/${watchlistId}/sections/${sectionId}/tickers?user_id=${userId}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ symbols }),
        }
      );

      if (!res.ok) throw new Error('Failed to move tickers');

      // Refresh to get updated state
      await fetchWatchlists();

      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      return false;
    }
  }, [userId, fetchWatchlists]);

  // Toggle section collapsed state
  const toggleSectionCollapsed = useCallback(async (
    watchlistId: string,
    sectionId: string
  ): Promise<boolean> => {
    const watchlist = watchlists.find(w => w.id === watchlistId);
    const section = watchlist?.sections.find(s => s.id === sectionId);
    if (!section) return false;

    return updateSection(watchlistId, sectionId, { is_collapsed: !section.is_collapsed });
  }, [watchlists, updateSection]);

  // Get active watchlist
  const activeWatchlist = watchlists.find(w => w.id === activeWatchlistId) || null;

  return {
    watchlists,
    activeWatchlist,
    activeWatchlistId,
    setActiveWatchlistId,
    loading,
    error,
    createWatchlist,
    updateWatchlist,
    deleteWatchlist,
    addTicker,
    addTickersBatch,
    removeTicker,
    // Section operations
    createSection,
    updateSection,
    deleteSection,
    moveTickersToSection,
    toggleSectionCollapsed,
    refetch: fetchWatchlists,
  };
}

