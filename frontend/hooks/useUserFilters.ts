/**
 * useUserFilters Hook
 * Hook para gestionar filtros personalizados del scanner por usuario
 */

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@clerk/nextjs';
import type { UserFilter, UserFilterCreate, UserFilterUpdate } from '@/lib/types/scannerFilters';
import {
  getUserFilters,
  createUserFilter,
  updateUserFilter,
  deleteUserFilter,
} from '@/lib/api/userFilters';

// ============================================================================
// Hook Return Type
// ============================================================================

export interface UseUserFiltersReturn {
  // State
  filters: UserFilter[];
  loading: boolean;
  error: string | null;
  
  // Actions
  loadFilters: () => Promise<void>;
  createFilter: (filter: UserFilterCreate) => Promise<UserFilter | null>;
  updateFilter: (id: number, filter: UserFilterUpdate) => Promise<UserFilter | null>;
  deleteFilter: (id: number) => Promise<boolean>;
  refreshFilters: () => Promise<void>;
  
  // Helpers
  getEnabledFilters: () => UserFilter[];
  getFilterById: (id: number) => UserFilter | undefined;
}

// ============================================================================
// Hook Implementation
// ============================================================================

export function useUserFilters(): UseUserFiltersReturn {
  const { getToken } = useAuth();
  const [filters, setFilters] = useState<UserFilter[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // ======================================================================
  // Load Filters
  // ======================================================================

  const loadFilters = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getUserFilters(getToken);
      setFilters(data);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load filters';
      setError(errorMessage);
      console.error('Error loading user filters:', err);
      setFilters([]); // Reset on error
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  // ======================================================================
  // Create Filter
  // ======================================================================

  const createFilter = useCallback(async (filter: UserFilterCreate): Promise<UserFilter | null> => {
    try {
      setError(null);
      const newFilter = await createUserFilter(filter, getToken);
      // Forzar actualización del estado creando un nuevo array
      setFilters(prev => {
        const updated = [...prev, newFilter];
        return [...updated].sort((a, b) => b.priority - a.priority);
      });
      return newFilter;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to create filter';
      setError(errorMessage);
      console.error('Error creating filter:', err);
      return null;
    }
  }, [getToken]);

  // ======================================================================
  // Update Filter
  // ======================================================================

  const updateFilter = useCallback(async (
    id: number,
    filter: UserFilterUpdate
  ): Promise<UserFilter | null> => {
    try {
      setError(null);
      const updatedFilter = await updateUserFilter(id, filter, getToken);
      // Forzar actualización del estado creando nuevos objetos para asegurar que React detecte el cambio
      setFilters(prev => {
        const updated = prev.map(f => {
          if (f.id === id) {
            // Crear un nuevo objeto para forzar la actualización
            return { ...updatedFilter };
          }
          return f;
        });
        // Crear un nuevo array para forzar la actualización
        return [...updated].sort((a, b) => b.priority - a.priority);
      });
      return updatedFilter;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to update filter';
      setError(errorMessage);
      console.error('Error updating filter:', err);
      return null;
    }
  }, [getToken]);

  // ======================================================================
  // Delete Filter
  // ======================================================================

  const deleteFilter = useCallback(async (id: number): Promise<boolean> => {
    try {
      setError(null);
      await deleteUserFilter(id, getToken);
      setFilters(prev => prev.filter(f => f.id !== id));
      return true;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to delete filter';
      setError(errorMessage);
      console.error('Error deleting filter:', err);
      return false;
    }
  }, [getToken]);

  // ======================================================================
  // Refresh Filters
  // ======================================================================

  const refreshFilters = useCallback(async () => {
    await loadFilters();
  }, [loadFilters]);

  // ======================================================================
  // Helpers
  // ======================================================================

  const getEnabledFilters = useCallback((): UserFilter[] => {
    return filters.filter(f => f.enabled);
  }, [filters]);

  const getFilterById = useCallback((id: number): UserFilter | undefined => {
    return filters.find(f => f.id === id);
  }, [filters]);

  // ======================================================================
  // Initial Load
  // ======================================================================

  useEffect(() => {
    loadFilters();
  }, [loadFilters]);

  // ======================================================================
  // Return
  // ======================================================================

  return {
    // State
    filters,
    loading,
    error,
    
    // Actions
    loadFilters,
    createFilter,
    updateFilter,
    deleteFilter,
    refreshFilters,
    
    // Helpers
    getEnabledFilters,
    getFilterById,
  };
}

