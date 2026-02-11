/**
 * Zustand Store para Alert Presets (Estrategias de usuario)
 * 
 * Los presets son combinaciones guardadas de:
 * - Event types seleccionados
 * - Filtros numericos (precio, volumen, rvol, etc.)
 * 
 * Funciona similar a las "Strategies" de Trade Ideas:
 * el usuario configura una ventana de alertas y puede guardar/cargar
 * esa configuracion como un preset reutilizable.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

// ============================================================================
// Types
// ============================================================================

export interface AlertPresetFilters {
  min_price?: number;
  max_price?: number;
  min_change_percent?: number;
  max_change_percent?: number;
  min_rvol?: number;
  max_rvol?: number;
  min_volume?: number;
  max_volume?: number;
  min_market_cap?: number;
  max_market_cap?: number;
  min_gap_percent?: number;
  max_gap_percent?: number;
  min_change_from_open?: number;
  max_change_from_open?: number;
  min_float_shares?: number;
  max_float_shares?: number;
  min_rsi?: number;
  max_rsi?: number;
  min_atr_percent?: number;
  max_atr_percent?: number;
}

export interface UserAlertPreset {
  id: string;
  name: string;
  eventTypes: string[];
  filters: AlertPresetFilters;
  createdAt: number;   // Unix timestamp ms
  updatedAt: number;
}

interface AlertPresetsState {
  presets: UserAlertPreset[];

  // Actions
  savePreset: (name: string, eventTypes: string[], filters: AlertPresetFilters) => UserAlertPreset;
  updatePreset: (id: string, updates: Partial<Pick<UserAlertPreset, 'name' | 'eventTypes' | 'filters'>>) => void;
  deletePreset: (id: string) => void;
  getPreset: (id: string) => UserAlertPreset | undefined;
}

// ============================================================================
// Store
// ============================================================================

export const useAlertPresetsStore = create<AlertPresetsState>()(
  persist(
    (set, get) => ({
      presets: [],

      savePreset: (name, eventTypes, filters) => {
        const now = Date.now();
        const preset: UserAlertPreset = {
          id: `preset_${now}_${Math.random().toString(36).slice(2, 8)}`,
          name,
          eventTypes,
          filters,
          createdAt: now,
          updatedAt: now,
        };

        set((state) => ({
          presets: [preset, ...state.presets],
        }));

        return preset;
      },

      updatePreset: (id, updates) => {
        set((state) => ({
          presets: state.presets.map(p =>
            p.id === id
              ? { ...p, ...updates, updatedAt: Date.now() }
              : p
          ),
        }));
      },

      deletePreset: (id) => {
        set((state) => ({
          presets: state.presets.filter(p => p.id !== id),
        }));
      },

      getPreset: (id) => {
        return get().presets.find(p => p.id === id);
      },
    }),
    {
      name: 'tradeul-alert-presets',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        presets: state.presets,
      }),
    }
  )
);
