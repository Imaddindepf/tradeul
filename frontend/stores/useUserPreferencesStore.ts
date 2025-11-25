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
}

export interface ColorPreferences {
  tickUp: string;      // Color cuando precio sube (default: #10b981 emerald)
  tickDown: string;    // Color cuando precio baja (default: #ef4444 red)
  background: string;  // Color de fondo del dashboard
  primary: string;     // Color primario de la UI
}

export interface ThemePreferences {
  font: FontFamily;
  colorScheme: 'light' | 'dark' | 'system';
}

export interface UserPreferences {
  // Colores
  colors: ColorPreferences;
  
  // Tema
  theme: ThemePreferences;
  
  // Layout de ventanas (snapshot)
  windowLayouts: WindowLayout[];
  
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
  
  // Actions - Layout
  saveWindowLayouts: (layouts: WindowLayout[]) => void;
  clearWindowLayouts: () => void;
  
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
};

const DEFAULT_PREFERENCES: UserPreferences = {
  colors: DEFAULT_COLORS,
  theme: DEFAULT_THEME,
  windowLayouts: [],
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

      // ========================================
      // Layout Actions
      // ========================================
      saveWindowLayouts: (layouts) =>
        set({ windowLayouts: layouts }),

      clearWindowLayouts: () =>
        set({ windowLayouts: [] }),

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
        savedFilters: state.savedFilters,
        columnVisibility: state.columnVisibility,
        columnOrder: state.columnOrder,
      }),
    }
  )
);

// ============================================================================
// SELECTORS
// ============================================================================

export const selectColors = (state: UserPreferencesState) => state.colors;
export const selectTheme = (state: UserPreferencesState) => state.theme;
export const selectFont = (state: UserPreferencesState) => state.theme.font;
export const selectWindowLayouts = (state: UserPreferencesState) => state.windowLayouts;

// ============================================================================
// HOOKS
// ============================================================================

/**
 * Hook para obtener los colores con CSS variables aplicadas
 */
export function useApplyTheme() {
  const colors = useUserPreferencesStore(selectColors);
  const theme = useUserPreferencesStore(selectTheme);

  // Aplicar CSS variables al document
  if (typeof window !== 'undefined') {
    const root = document.documentElement;
    root.style.setProperty('--color-tick-up', colors.tickUp);
    root.style.setProperty('--color-tick-down', colors.tickDown);
    root.style.setProperty('--color-background', colors.background);
    root.style.setProperty('--color-primary', colors.primary);
    root.style.setProperty('--font-family', `var(--font-${theme.font})`);
  }

  return { colors, theme };
}

