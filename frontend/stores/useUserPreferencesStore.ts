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

// ============================================================================
// WORKSPACE TYPES (Multi-dashboard support)
// ============================================================================

export interface Workspace {
  id: string;
  name: string;
  windowLayouts: WindowLayout[];
  createdAt: number;
  /** Main workspace cannot be deleted */
  isMain?: boolean;
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
  
  // Layout de ventanas (snapshot) - DEPRECATED: usar workspaces
  windowLayouts: WindowLayout[];
  
  // Flag para saber si el usuario ya ha interactuado con layouts
  // true = ya usó el sistema (aunque tenga 0 ventanas)
  // false/undefined = primera vez, abrir tablas por defecto
  layoutInitialized: boolean;
  
  // ============================================================================
  // WORKSPACES (Multi-dashboard support)
  // ============================================================================
  workspaces: Workspace[];
  activeWorkspaceId: string;
  
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
  
  // Actions - Layout (DEPRECATED - usar workspaces)
  saveWindowLayouts: (layouts: WindowLayout[]) => void;
  clearWindowLayouts: () => void;
  setLayoutInitialized: (initialized: boolean) => void;
  /** Actualizar estado del componente de una ventana específica */
  updateWindowComponentState: (windowId: string, state: Record<string, unknown>) => void;
  /** Obtener estado del componente de una ventana */
  getWindowComponentState: (windowId: string) => Record<string, unknown> | undefined;
  
  // Actions - Workspaces
  createWorkspace: (name: string) => string;
  deleteWorkspace: (workspaceId: string) => void;
  renameWorkspace: (workspaceId: string, newName: string) => void;
  setActiveWorkspace: (workspaceId: string) => void;
  saveWorkspaceLayouts: (workspaceId: string, layouts: WindowLayout[]) => void;
  getActiveWorkspace: () => Workspace | undefined;
  getWorkspace: (workspaceId: string) => Workspace | undefined;
  /** Migrar del sistema antiguo (windowLayouts) al nuevo (workspaces) */
  migrateToWorkspaces: () => void;
  
  // Actions - Backend Sync
  /** Sincronizar workspaces al backend (debounced) */
  syncWorkspacesToBackend: (getToken?: () => Promise<string | null>) => Promise<void>;
  /** Cargar preferencias del backend */
  loadFromBackend: (getToken?: () => Promise<string | null>) => Promise<boolean>;
  /** Flag para saber si se está sincronizando */
  isSyncing: boolean;
  /** Última vez que se sincronizó */
  lastSyncedAt: number | null;
  
  // Workspace Switching Flag
  /** Flag para indicar que se está cambiando de workspace (desactiva auto-save) */
  isWorkspaceSwitching: boolean;
  setWorkspaceSwitching: (switching: boolean) => void;
  
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

// Default Main workspace
const DEFAULT_MAIN_WORKSPACE: Workspace = {
  id: 'main',
  name: 'Main',
  windowLayouts: [],
  createdAt: Date.now(),
  isMain: true,
};

const DEFAULT_PREFERENCES: UserPreferences & { isSyncing: boolean; lastSyncedAt: number | null; isWorkspaceSwitching: boolean } = {
  colors: DEFAULT_COLORS,
  theme: DEFAULT_THEME,
  windowLayouts: [], // DEPRECATED
  layoutInitialized: false,
  workspaces: [DEFAULT_MAIN_WORKSPACE],
  activeWorkspaceId: 'main',
  savedFilters: {},
  // Sync state (not persisted)
  isSyncing: false,
  lastSyncedAt: null,
  isWorkspaceSwitching: false,
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
        set((s) => {
          // CORREGIDO: Guardar en workspace activo, no en legacy
          const activeWsId = s.activeWorkspaceId;
          
          // Función helper para actualizar o crear layout en un array
          const updateOrCreateLayout = (layouts: WindowLayout[]): WindowLayout[] => {
            const existingIndex = layouts.findIndex((w) => w.id === windowId);
            if (existingIndex !== -1) {
              // Layout existe: actualizar componentState
              return layouts.map((w) =>
                w.id === windowId ? { ...w, componentState: state } : w
              );
            } else {
              // Layout no existe: crear uno temporal con solo el componentState
              // (el resto se llenará cuando se auto-guarde el layout completo)
              return [
                ...layouts,
                {
                  id: windowId,
                  type: 'unknown',
                  title: '',
                  position: { x: 0, y: 0 },
                  size: { width: 400, height: 300 },
                  isMinimized: false,
                  zIndex: 0,
                  componentState: state,
                } as WindowLayout,
              ];
            }
          };
          
          return {
            // Actualizar en workspaces (sistema nuevo)
            workspaces: s.workspaces.map((ws) =>
              ws.id === activeWsId
                ? { ...ws, windowLayouts: updateOrCreateLayout(ws.windowLayouts) }
                : ws
            ),
            // También actualizar en legacy por compatibilidad
            windowLayouts: updateOrCreateLayout(s.windowLayouts),
          };
        }),

      getWindowComponentState: (windowId) => {
        const state = get();
        // Buscar en workspace activo primero, luego en windowLayouts (legacy)
        const activeWs = state.workspaces.find(w => w.id === state.activeWorkspaceId);
        const fromWorkspace = activeWs?.windowLayouts.find((w) => w.id === windowId)?.componentState;
        if (fromWorkspace) return fromWorkspace;
        return state.windowLayouts.find((w) => w.id === windowId)?.componentState;
      },

      // ========================================
      // Workspaces Actions
      // ========================================
      createWorkspace: (name) => {
        const id = `workspace-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const newWorkspace: Workspace = {
          id,
          name,
          windowLayouts: [],
          createdAt: Date.now(),
          isMain: false,
        };
        set((state) => ({
          workspaces: [...state.workspaces, newWorkspace],
        }));
        return id;
      },

      deleteWorkspace: (workspaceId) => {
        set((state) => {
          const workspace = state.workspaces.find(w => w.id === workspaceId);
          // No permitir eliminar Main
          if (workspace?.isMain) return state;
          
          const newWorkspaces = state.workspaces.filter(w => w.id !== workspaceId);
          // Si eliminamos el workspace activo, cambiar a Main
          const newActiveId = state.activeWorkspaceId === workspaceId 
            ? 'main' 
            : state.activeWorkspaceId;
          
          return {
            workspaces: newWorkspaces,
            activeWorkspaceId: newActiveId,
          };
        });
      },

      renameWorkspace: (workspaceId, newName) => {
        set((state) => ({
          workspaces: state.workspaces.map(w =>
            w.id === workspaceId ? { ...w, name: newName } : w
          ),
        }));
      },

      setActiveWorkspace: (workspaceId) => {
        set({ activeWorkspaceId: workspaceId });
      },

      saveWorkspaceLayouts: (workspaceId, layouts) => {
        set((state) => ({
          workspaces: state.workspaces.map(w =>
            w.id === workspaceId ? { ...w, windowLayouts: layouts } : w
          ),
          layoutInitialized: true,
        }));
      },

      getActiveWorkspace: () => {
        const state = get();
        return state.workspaces.find(w => w.id === state.activeWorkspaceId);
      },

      getWorkspace: (workspaceId) => {
        const state = get();
        return state.workspaces.find(w => w.id === workspaceId);
      },

      migrateToWorkspaces: () => {
        const state = get();
        // Si ya hay workspaces con layouts, no migrar
        const mainWs = state.workspaces.find(w => w.isMain);
        if (mainWs && mainWs.windowLayouts.length > 0) return;
        
        // Si hay layouts antiguos, migrarlos a Main
        if (state.windowLayouts.length > 0) {
          set((s) => ({
            workspaces: s.workspaces.map(w =>
              w.isMain ? { ...w, windowLayouts: s.windowLayouts } : w
            ),
            windowLayouts: [], // Limpiar legacy
          }));
        }
      },

      // ========================================
      // Backend Sync Actions
      // ========================================
      syncWorkspacesToBackend: async (getToken?: () => Promise<string | null>) => {
        const state = get();
        if (state.isSyncing) return; // Evitar sincronizaciones paralelas
        
        set({ isSyncing: true });
        
        try {
          const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
          
          // Obtener token de autenticación
          const headers: Record<string, string> = {
            'Content-Type': 'application/json',
          };
          
          if (getToken) {
            const token = await getToken();
            if (token) {
              headers['Authorization'] = `Bearer ${token}`;
            }
          }
          
          const response = await fetch(`${apiUrl}/api/v1/user/preferences/workspaces`, {
            method: 'PATCH',
            headers,
            credentials: 'include',
            body: JSON.stringify({
              workspaces: state.workspaces,
              activeWorkspaceId: state.activeWorkspaceId,
            }),
          });
          
          if (response.ok) {
            const data = await response.json();
            console.log('[WorkspaceSync] Synced to backend:', {
              workspaces: data.workspaceCount,
              windows: data.totalWindows,
            });
            set({ lastSyncedAt: Date.now() });
          } else {
            console.warn('[WorkspaceSync] Failed to sync:', response.status, await response.text());
          }
        } catch (error) {
          console.error('[WorkspaceSync] Error syncing to backend:', error);
        } finally {
          set({ isSyncing: false });
        }
      },

      loadFromBackend: async (getToken?: () => Promise<string | null>) => {
        try {
          const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
          
          // Obtener token de autenticación
          const headers: Record<string, string> = {
            'Content-Type': 'application/json',
          };
          
          if (getToken) {
            const token = await getToken();
            if (token) {
              headers['Authorization'] = `Bearer ${token}`;
            }
          }
          
          const response = await fetch(`${apiUrl}/api/v1/user/preferences`, {
            method: 'GET',
            headers,
            credentials: 'include',
          });
          
          if (!response.ok) {
            console.warn('[WorkspaceSync] Failed to load from backend:', response.status);
            return false;
          }
          
          const data = await response.json();
          
          // Solo cargar si hay workspaces del backend
          if (data.workspaces && data.workspaces.length > 0) {
            console.log('[WorkspaceSync] Loaded from backend:', {
              workspaces: data.workspaces.length,
              activeId: data.activeWorkspaceId,
            });
            
            set({
              workspaces: data.workspaces,
              activeWorkspaceId: data.activeWorkspaceId || 'main',
              colors: data.colors || DEFAULT_COLORS,
              theme: data.theme || DEFAULT_THEME,
              savedFilters: data.savedFilters || {},
              columnVisibility: data.columnVisibility || {},
              columnOrder: data.columnOrder || {},
              lastSyncedAt: Date.now(),
            });
            
            return true;
          }
          
          return false;
        } catch (error) {
          console.error('[WorkspaceSync] Error loading from backend:', error);
          return false;
        }
      },

      // Workspace Switching Flag
      setWorkspaceSwitching: (switching: boolean) => set({ isWorkspaceSwitching: switching }),

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
      resetAll: () => set({
        ...DEFAULT_PREFERENCES,
        workspaces: [{ ...DEFAULT_MAIN_WORKSPACE, createdAt: Date.now() }],
      }),

      exportPreferences: () => {
        const state = get();
        return JSON.stringify({
          colors: state.colors,
          theme: state.theme,
          windowLayouts: state.windowLayouts,
          layoutInitialized: state.layoutInitialized,
          workspaces: state.workspaces,
          activeWorkspaceId: state.activeWorkspaceId,
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
            workspaces: data.workspaces || [DEFAULT_MAIN_WORKSPACE],
            activeWorkspaceId: data.activeWorkspaceId || 'main',
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
        workspaces: state.workspaces,
        activeWorkspaceId: state.activeWorkspaceId,
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

// Workspace selectors
export const selectWorkspaces = (state: UserPreferencesState) => state.workspaces;
export const selectActiveWorkspaceId = (state: UserPreferencesState) => state.activeWorkspaceId;
export const selectActiveWorkspace = (state: UserPreferencesState) => 
  state.workspaces.find(w => w.id === state.activeWorkspaceId);
export const selectActiveWorkspaceLayouts = (state: UserPreferencesState) => {
  const activeWs = state.workspaces.find(w => w.id === state.activeWorkspaceId);
  return activeWs?.windowLayouts || [];
};


