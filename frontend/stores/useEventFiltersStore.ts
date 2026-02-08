/**
 * Zustand Store para Filtros de Eventos
 * 
 * FILTROS PER-CATEGORY: Cada tabla de eventos (categoryId) tiene sus propios filtros.
 * Esto permite tener "EVN evt_new_highs" con precio > $10 y "EVN evt_all" sin filtros
 * al mismo tiempo en ventanas separadas.
 * 
 * PERSISTENCIA: Se guardan en localStorage y se sincronizan con la BD
 * via useClerkSync (usando el campo savedFilters.eventFilters)
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

// ============================================================================
// Types
// ============================================================================

export interface EventFilterParameters {
  // Event type filters (which events to show)
  event_types?: string[];

  // Price filters
  min_price?: number;
  max_price?: number;

  // Change % filters
  min_change_percent?: number;
  max_change_percent?: number;

  // RVOL filters
  min_rvol?: number;
  max_rvol?: number;

  // Volume filters
  min_volume?: number;
  max_volume?: number;

  // Market Cap filters
  min_market_cap?: number;
  max_market_cap?: number;

  // Gap % filters
  min_gap_percent?: number;
  max_gap_percent?: number;

  // Change from open filters
  min_change_from_open?: number;
  max_change_from_open?: number;

  // VWAP filters
  min_vwap?: number;
  max_vwap?: number;

  // ATR % filters
  min_atr_percent?: number;
  max_atr_percent?: number;

  // Time-window change filters
  min_chg_1min?: number;
  max_chg_1min?: number;
  min_chg_5min?: number;
  max_chg_5min?: number;
  min_chg_10min?: number;
  max_chg_10min?: number;
  min_chg_15min?: number;
  max_chg_15min?: number;
  min_chg_30min?: number;
  max_chg_30min?: number;

  // Time-window volume filters
  min_vol_1min?: number;
  max_vol_1min?: number;
  min_vol_5min?: number;
  max_vol_5min?: number;

  // Float filters
  min_float_shares?: number;
  max_float_shares?: number;

  // RSI filters
  min_rsi?: number;
  max_rsi?: number;

  // SMA filters (price vs SMA)
  min_sma_20?: number;
  max_sma_20?: number;
  min_sma_50?: number;
  max_sma_50?: number;
  min_sma_200?: number;
  max_sma_200?: number;

  // Symbol filters
  symbols_include?: string[];
  symbols_exclude?: string[];
  watchlist_only?: boolean;
}

export interface ActiveEventFilters extends EventFilterParameters { }

interface EventFiltersState {
  // Per-category filters (key = categoryId, e.g. "evt_new_highs")
  filtersMap: Record<string, ActiveEventFilters>;

  // Actions (all take categoryId for per-window isolation)
  getFilters: (categoryId: string) => ActiveEventFilters;
  setFilter: <K extends keyof ActiveEventFilters>(categoryId: string, key: K, value: ActiveEventFilters[K]) => void;
  clearFilter: (categoryId: string, key: keyof ActiveEventFilters) => void;
  clearAllFilters: (categoryId: string) => void;
  setAllFilters: (categoryId: string, filters: ActiveEventFilters) => void;
  hasActiveFilters: (categoryId: string) => boolean;

  // Event type specific actions
  toggleEventType: (categoryId: string, eventType: string) => void;
  setEventTypes: (categoryId: string, eventTypes: string[]) => void;
  clearEventTypes: (categoryId: string) => void;
}

// ============================================================================
// Available Event Types
// ============================================================================

export const ALL_EVENT_TYPES = [
  // Price
  'new_high',
  'new_low',
  'crossed_above_open',
  'crossed_below_open',
  'crossed_above_prev_close',
  'crossed_below_prev_close',
  // VWAP
  'vwap_cross_up',
  'vwap_cross_down',
  // Volume
  'rvol_spike',
  'volume_surge',
  'volume_spike_1min',
  'unusual_prints',
  'block_trade',
  // Momentum
  'running_up',
  'running_down',
  'percent_up_5',
  'percent_down_5',
  'percent_up_10',
  'percent_down_10',
  // Pullbacks
  'pullback_75_from_high',
  'pullback_25_from_high',
  'pullback_75_from_low',
  'pullback_25_from_low',
  // Gap
  'gap_up_reversal',
  'gap_down_reversal',
  // Halts
  'halt',
  'resume',
] as const;

export type EventType = typeof ALL_EVENT_TYPES[number];

// ============================================================================
// Helpers
// ============================================================================

function cleanFilters(filters: ActiveEventFilters): ActiveEventFilters {
  const clean: ActiveEventFilters = {};
  for (const [key, value] of Object.entries(filters)) {
    if (value !== null && value !== undefined) {
      (clean as any)[key] = value;
    }
  }
  return clean;
}

function isNotEmpty(filters: ActiveEventFilters): boolean {
  return Object.keys(filters).length > 0;
}

// ============================================================================
// Store con Persistencia (per-category)
// ============================================================================

export const useEventFiltersStore = create<EventFiltersState>()(
  persist(
    (set, get) => ({
      filtersMap: {},

      getFilters: (categoryId) => {
        return get().filtersMap[categoryId] || {};
      },

      setFilter: (categoryId, key, value) => {
        set((state) => {
          const current = { ...(state.filtersMap[categoryId] || {}) };
          if (value === null || value === undefined) {
            delete current[key];
          } else {
            current[key] = value;
          }
          return {
            filtersMap: { ...state.filtersMap, [categoryId]: current },
          };
        });
      },

      clearFilter: (categoryId, key) => {
        set((state) => {
          const current = { ...(state.filtersMap[categoryId] || {}) };
          delete current[key];
          return {
            filtersMap: { ...state.filtersMap, [categoryId]: current },
          };
        });
      },

      clearAllFilters: (categoryId) => {
        set((state) => ({
          filtersMap: { ...state.filtersMap, [categoryId]: {} },
        }));
      },

      setAllFilters: (categoryId, filters) => {
        set((state) => ({
          filtersMap: { ...state.filtersMap, [categoryId]: cleanFilters(filters) },
        }));
      },

      hasActiveFilters: (categoryId) => {
        return isNotEmpty(get().filtersMap[categoryId] || {});
      },

      // Event type specific actions
      toggleEventType: (categoryId, eventType) => {
        set((state) => {
          const current = { ...(state.filtersMap[categoryId] || {}) };
          const types = current.event_types || [];
          let newTypes: string[];

          if (types.includes(eventType)) {
            newTypes = types.filter(t => t !== eventType);
          } else {
            newTypes = [...types, eventType];
          }

          if (newTypes.length === 0) {
            delete current.event_types;
          } else {
            current.event_types = newTypes;
          }

          return {
            filtersMap: { ...state.filtersMap, [categoryId]: current },
          };
        });
      },

      setEventTypes: (categoryId, eventTypes) => {
        set((state) => {
          const current = { ...(state.filtersMap[categoryId] || {}) };
          if (eventTypes.length === 0) {
            delete current.event_types;
          } else {
            current.event_types = eventTypes;
          }
          return {
            filtersMap: { ...state.filtersMap, [categoryId]: current },
          };
        });
      },

      clearEventTypes: (categoryId) => {
        set((state) => {
          const current = { ...(state.filtersMap[categoryId] || {}) };
          delete current.event_types;
          return {
            filtersMap: { ...state.filtersMap, [categoryId]: current },
          };
        });
      },
    }),
    {
      name: 'tradeul-event-filters',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        filtersMap: state.filtersMap,
      }),
    }
  )
);
