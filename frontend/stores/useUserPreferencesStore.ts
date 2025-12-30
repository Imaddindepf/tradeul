/**
 * User Preferences Store
 * 
 * Persistencia en localStorage + opcionalmente sync con backend
 * Estilo Bloomberg/Godel Terminal
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

// ============================================================================
// TYPES
// ============================================================================

export type FontFamily = 'oxygen-mono' | 'ibm-plex-mono' | 'jetbrains-mono' | 'fira-code';

export interface WindowLayout {
  id: string;
  type: string;
  title: string;
  position: { x: number; y: number };
  size: { width: number; height: number };
  isMinimized: boolean;
  zIndex: number;
  /** Estado interno del componente (tickers, filtros, búsqueda, etc.) */
  componentState?: Record<string, unknown>;
}

export interface ColorPreferences {
  tickUp: string;      // Color cuando precio sube (default: #10b981 emerald)
  tickDown: string;    // Color cuando precio baja (default: #ef4444 red)
  background: string;  // Color de fondo del dashboard
  primary: string;     // Color primario de la UI
}

// Zonas horarias comunes para trading
export type TimezoneOption = 
  | 'America/New_York'    // ET - Eastern Time (default, mercado US)
  | 'America/Chicago'     // CT - Central Time
  | 'America/Denver'      // MT - Mountain Time
  | 'America/Los_Angeles' // PT - Pacific Time
  | 'Europe/London'       // GMT/BST - London
  | 'Europe/Madrid'       // CET/CEST - Spain
  | 'Europe/Paris'        // CET/CEST - France
  | 'Europe/Berlin'       // CET/CEST - Germany
  | 'Asia/Tokyo'          // JST - Japan
  | 'Asia/Hong_Kong'      // HKT - Hong Kong
  | 'Asia/Singapore'      // SGT - Singapore
  | 'UTC';                // UTC

export interface ThemePreferences {
  font: FontFamily;
  colorScheme: 'light' | 'dark' | 'system';
  newsSquawkEnabled: boolean;
  timezone: TimezoneOption;
}

export interface UserPreferences {
  // Colores
  colors: ColorPreferences;
  
  // Tema
  theme: ThemePreferences;
  
  // Layout de ventanas (snapshot)
  windowLayouts: WindowLayout[];
  
  // Flag para saber si el usuario ya ha interactuado con layouts
  // true = ya usó el sistema (aunque tenga 0 ventanas)
  // false/undefined = primera vez, abrir tablas por defecto
  layoutInitialized: boolean;
  
  // Filtros guardados por lista
  savedFilters: Record<string, any>;
  
  // Columnas visibles por lista
  columnVisibility: Record<string, Record<string, boolean>>;
  
  // Orden de columnas por lista
  columnOrder: Record<string, string[]>;
}

interface UserPreferencesState extends UserPreferences {
  // Actions - Colors
  setTickUpColor: (color: string) => void;
  setTickDownColor: (color: string) => void;
  setBackgroundColor: (color: string) => void;
  setPrimaryColor: (color: string) => void;
  resetColors: () => void;
  
  // Actions - Theme
  setFont: (font: FontFamily) => void;
  setColorScheme: (scheme: 'light' | 'dark' | 'system') => void;
  setNewsSquawkEnabled: (enabled: boolean) => void;
  setTimezone: (timezone: TimezoneOption) => void;
  
  // Actions - Layout
  saveWindowLayouts: (layouts: WindowLayout[]) => void;
  clearWindowLayouts: () => void;
  setLayoutInitialized: (initialized: boolean) => void;
  /** Actualizar estado del componente de una ventana específica */
  updateWindowComponentState: (windowId: string, state: Record<string, unknown>) => void;
  /** Obtener estado del componente de una ventana */
  getWindowComponentState: (windowId: string) => Record<string, unknown> | undefined;
  
  // Actions - Filters
  saveFilters: (listName: string, filters: any) => void;
  clearFilters: (listName: string) => void;
  
  // Actions - Columns
  saveColumnVisibility: (listName: string, visibility: Record<string, boolean>) => void;
  saveColumnOrder: (listName: string, order: string[]) => void;
  
  // Actions - General
  resetAll: () => void;
  exportPreferences: () => string;
  importPreferences: (json: string) => boolean;
}

// ============================================================================
// DEFAULT VALUES
// ============================================================================

const DEFAULT_COLORS: ColorPreferences = {
  tickUp: '#10b981',      // Emerald-500
  tickDown: '#ef4444',    // Red-500
  background: '#ffffff',  // White
  primary: '#3b82f6',     // Blue-500
};

const DEFAULT_THEME: ThemePreferences = {
  font: 'jetbrains-mono',
  colorScheme: 'light',
  newsSquawkEnabled: false,
  timezone: 'America/New_York', // ET - Standard for US markets
};

const DEFAULT_PREFERENCES: UserPreferences = {
  colors: DEFAULT_COLORS,
  theme: DEFAULT_THEME,
  windowLayouts: [],
  layoutInitialized: false,
  savedFilters: {},
  columnVisibility: {},
  columnOrder: {},
};

// ============================================================================
// STORE
// ============================================================================

export const useUserPreferencesStore = create<UserPreferencesState>()(
  persist(
    (set, get) => ({
      ...DEFAULT_PREFERENCES,

      // ========================================
      // Colors Actions
      // ========================================
      setTickUpColor: (color) =>
        set((state) => ({
          colors: { ...state.colors, tickUp: color },
        })),

      setTickDownColor: (color) =>
        set((state) => ({
          colors: { ...state.colors, tickDown: color },
        })),

      setBackgroundColor: (color) =>
        set((state) => ({
          colors: { ...state.colors, background: color },
        })),

      setPrimaryColor: (color) =>
        set((state) => ({
          colors: { ...state.colors, primary: color },
        })),

      resetColors: () =>
        set({ colors: DEFAULT_COLORS }),

      // ========================================
      // Theme Actions
      // ========================================
      setFont: (font) =>
        set((state) => ({
          theme: { ...state.theme, font },
        })),

      setColorScheme: (colorScheme) =>
        set((state) => ({
          theme: { ...state.theme, colorScheme },
        })),

      setNewsSquawkEnabled: (enabled) =>
        set((state) => ({
          theme: { ...state.theme, newsSquawkEnabled: enabled },
        })),

      setTimezone: (timezone) =>
        set((state) => ({
          theme: { ...state.theme, timezone },
        })),

      // ========================================
      // Layout Actions
      // ========================================
      saveWindowLayouts: (layouts) =>
        set({ windowLayouts: layouts, layoutInitialized: true }),

      clearWindowLayouts: () =>
        set({ windowLayouts: [], layoutInitialized: true }),

      setLayoutInitialized: (initialized) =>
        set({ layoutInitialized: initialized }),

      updateWindowComponentState: (windowId, state) =>
        set((s) => ({
          windowLayouts: s.windowLayouts.map((w) =>
            w.id === windowId ? { ...w, componentState: state } : w
          ),
        })),

      getWindowComponentState: (windowId) => {
        const state = get();
        return state.windowLayouts.find((w) => w.id === windowId)?.componentState;
      },

      // ========================================
      // Filters Actions
      // ========================================
      saveFilters: (listName, filters) =>
        set((state) => ({
          savedFilters: { ...state.savedFilters, [listName]: filters },
        })),

      clearFilters: (listName) =>
        set((state) => {
          const { [listName]: _, ...rest } = state.savedFilters;
          return { savedFilters: rest };
        }),

      // ========================================
      // Columns Actions
      // ========================================
      saveColumnVisibility: (listName, visibility) =>
        set((state) => ({
          columnVisibility: { ...state.columnVisibility, [listName]: visibility },
        })),

      saveColumnOrder: (listName, order) =>
        set((state) => ({
          columnOrder: { ...state.columnOrder, [listName]: order },
        })),

      // ========================================
      // General Actions
      // ========================================
      resetAll: () => set(DEFAULT_PREFERENCES),

      exportPreferences: () => {
        const state = get();
        return JSON.stringify({
          colors: state.colors,
          theme: state.theme,
          windowLayouts: state.windowLayouts,
          layoutInitialized: state.layoutInitialized,
          savedFilters: state.savedFilters,
          columnVisibility: state.columnVisibility,
          columnOrder: state.columnOrder,
        }, null, 2);
      },

      importPreferences: (json) => {
        try {
          const data = JSON.parse(json);
          set({
            colors: data.colors || DEFAULT_COLORS,
            theme: data.theme || DEFAULT_THEME,
            windowLayouts: data.windowLayouts || [],
            layoutInitialized: data.layoutInitialized ?? false,
            savedFilters: data.savedFilters || {},
            columnVisibility: data.columnVisibility || {},
            columnOrder: data.columnOrder || {},
          });
          return true;
        } catch {
          return false;
        }
      },
    }),
    {
      name: 'tradeul-user-preferences',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        colors: state.colors,
        theme: state.theme,
        windowLayouts: state.windowLayouts,
        layoutInitialized: state.layoutInitialized,
        savedFilters: state.savedFilters,
        columnVisibility: state.columnVisibility,
        columnOrder: state.columnOrder,
      }),
      // Evitar hidratación automática para prevenir errores SSR/CSR mismatch
      skipHydration: true,
    }
  )
);

// ============================================================================
// SELECTORS
// ============================================================================

export const selectColors = (state: UserPreferencesState) => state.colors;
export const selectTheme = (state: UserPreferencesState) => state.theme;
export const selectFont = (state: UserPreferencesState) => state.theme.font;
export const selectTimezone = (state: UserPreferencesState) => state.theme.timezone || 'America/New_York';
export const selectWindowLayouts = (state: UserPreferencesState) => state.windowLayouts;


