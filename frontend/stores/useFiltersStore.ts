/**
 * Zustand Store para Filtros del Scanner
 * Estado global compartido entre FilterManager y las tablas
 * 
 * PERSISTENCIA: Los filtros se guardan en localStorage y se sincronizan con la BD
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { FilterParameters } from '@/lib/types/scannerFilters';

// ============================================================================
// Types
// ============================================================================

export interface ActiveFilters extends FilterParameters {
  // Hereda todos los campos de FilterParameters
}

interface FiltersState {
  // Filtros activos (aplicados en tiempo real)
  activeFilters: ActiveFilters;
  
  // ¿Hay filtros aplicados?
  hasActiveFilters: boolean;
  
  // Actions
  setFilter: (key: keyof ActiveFilters, value: number | null) => void;
  clearFilter: (key: keyof ActiveFilters) => void;
  clearAllFilters: () => void;
  setAllFilters: (filters: ActiveFilters) => void;
}

// ============================================================================
// Store con Persistencia
// ============================================================================

export const useFiltersStore = create<FiltersState>()(
  persist(
    (set, get) => ({
  activeFilters: {},
  hasActiveFilters: false,

  setFilter: (key, value) => {
    set((state) => {
      const newFilters = { ...state.activeFilters };
      if (value === null || value === undefined) {
        delete newFilters[key];
      } else {
        newFilters[key] = value;
      }
      const hasActive = Object.keys(newFilters).length > 0;
      return { activeFilters: newFilters, hasActiveFilters: hasActive };
    });
  },

  clearFilter: (key) => {
    set((state) => {
      const newFilters = { ...state.activeFilters };
      delete newFilters[key];
      const hasActive = Object.keys(newFilters).length > 0;
      return { activeFilters: newFilters, hasActiveFilters: hasActive };
    });
  },

  clearAllFilters: () => {
    set({ activeFilters: {}, hasActiveFilters: false });
  },

  setAllFilters: (filters) => {
    const cleanFilters: ActiveFilters = {};
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== null && value !== undefined) {
        cleanFilters[key as keyof ActiveFilters] = value;
      }
    });
    const hasActive = Object.keys(cleanFilters).length > 0;
    set({ activeFilters: cleanFilters, hasActiveFilters: hasActive });
  },
    }),
    {
      name: 'tradeul-scanner-filters',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        activeFilters: state.activeFilters,
        hasActiveFilters: state.hasActiveFilters,
      }),
    }
  )
);
