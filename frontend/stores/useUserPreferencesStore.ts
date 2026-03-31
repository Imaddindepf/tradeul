/**
 * User Preferences Store
 * 
 * Persistencia en localStorage + opcionalmente sync con backend
 * Estilo Bloomberg/Godel Terminal
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

// Holds componentState for newly created windows that haven't been auto-saved yet.
// Solves the race condition: openWindow() → updateComponentState() → auto-save (3s later).
const _pendingComponentStates = new Map<string, Record<string, unknown>>();
export function consumePendingComponentStates(): Map<string, Record<string, unknown>> {
  const copy = new Map(_pendingComponentStates);
  _pendingComponentStates.clear();
  return copy;
}

// ============================================================================
// TYPES
// ============================================================================

export type FontFamily = 'oxygen-mono' | 'ibm-plex-mono' | 'jetbrains-mono' | 'fira-code';
export type NewsViewMode = 'table' | 'feed';

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
  /** IBKR-style link group color */
  linkGroup?: string;
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

interface ThemePreferences {
  font: FontFamily;
  colorScheme: 'light' | 'dark' | 'system';
  newsSquawkEnabled: boolean;
  timezone: TimezoneOption;
  newsViewMode: NewsViewMode;
}

export interface UserPreferences {
  colors: ColorPreferences;
  theme: ThemePreferences;
  /** DEPRECATED: usar workspaces[].windowLayouts */
  windowLayouts: WindowLayout[];
  layoutInitialized: boolean;
  workspaces: Workspace[];
  activeWorkspaceId: string;
  /**
   * Timestamp (ms) of last STRUCTURAL workspace change (create/delete/rename).
   * Layout saves (window drag/resize) do NOT update this — only operations that
   * change the workspace list itself. Used for conflict resolution with backend.
   */
  workspacesModifiedAt: number;
  columnVisibility: Record<string, Record<string, boolean>>;
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
  setNewsViewMode: (mode: NewsViewMode) => void;
  
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
  newsViewMode: 'table',
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
  workspacesModifiedAt: 0,
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

      setNewsViewMode: (newsViewMode) =>
        set((state) => ({
          theme: { ...state.theme, newsViewMode },
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

      updateWindowComponentState: (windowId, componentState) => {
        _pendingComponentStates.set(windowId, componentState);
        set((s) => {
          const activeWsId = s.activeWorkspaceId;
          
          const updateExisting = (layouts: WindowLayout[]): WindowLayout[] =>
            layouts.map((w) =>
              w.id === windowId ? { ...w, componentState } : w
            );

          return {
            workspaces: s.workspaces.map((ws) =>
              ws.id === activeWsId
                ? { ...ws, windowLayouts: updateExisting(ws.windowLayouts) }
                : ws
            ),
            windowLayouts: updateExisting(s.windowLayouts),
          };
        });
      },

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
        const now = Date.now();
        const id = `workspace-${now}-${Math.random().toString(36).substr(2, 9)}`;
        const newWorkspace: Workspace = {
          id,
          name,
          windowLayouts: [],
          createdAt: now,
          isMain: false,
        };
        set((state) => ({
          workspaces: [...state.workspaces, newWorkspace],
          workspacesModifiedAt: now,
        }));
        return id;
      },

      deleteWorkspace: (workspaceId) => {
        const now = Date.now();
        set((state) => {
          const workspace = state.workspaces.find(w => w.id === workspaceId);
          if (workspace?.isMain) return state;
          
          const newWorkspaces = state.workspaces.filter(w => w.id !== workspaceId);
          const newActiveId = state.activeWorkspaceId === workspaceId 
            ? 'main' 
            : state.activeWorkspaceId;
          
          return {
            workspaces: newWorkspaces,
            activeWorkspaceId: newActiveId,
            workspacesModifiedAt: now,
          };
        });
      },

      renameWorkspace: (workspaceId, newName) => {
        set((state) => ({
          workspaces: state.workspaces.map(w =>
            w.id === workspaceId ? { ...w, name: newName } : w
          ),
          workspacesModifiedAt: Date.now(),
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
        if (get().isSyncing) return;
        set({ isSyncing: true });
        
        try {
          const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
          const headers: Record<string, string> = { 'Content-Type': 'application/json' };
          
          if (getToken) {
            const token = await getToken();
            if (token) headers['Authorization'] = `Bearer ${token}`;
          }
          
          const fresh = get();
          const response = await fetch(`${apiUrl}/api/v1/user/preferences/workspaces`, {
            method: 'PATCH',
            headers,
            credentials: 'include',
            body: JSON.stringify({
              workspaces: fresh.workspaces,
              activeWorkspaceId: fresh.activeWorkspaceId,
              colors: fresh.colors,
              theme: fresh.theme,
              columnVisibility: fresh.columnVisibility,
              columnOrder: fresh.columnOrder,
            }),
          });
          
          if (response.ok) {
            set({ lastSyncedAt: Date.now() });
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
          const headers: Record<string, string> = { 'Content-Type': 'application/json' };
          
          if (getToken) {
            const token = await getToken();
            if (token) headers['Authorization'] = `Bearer ${token}`;
          }
          
          const response = await fetch(`${apiUrl}/api/v1/user/preferences`, {
            method: 'GET',
            headers,
            credentials: 'include',
          });
          
          if (!response.ok) return false;
          
          const data = await response.json();
          
          if (data.workspaces && data.workspaces.length > 0) {
            const local = get();
            const remoteWorkspaces = data.workspaces as Workspace[];
            const legacyWindowLayouts = Array.isArray(data.windowLayouts)
              ? (data.windowLayouts as WindowLayout[])
              : [];

            const hasWorkspaceLayouts = remoteWorkspaces.some(
              (w) => Array.isArray(w.windowLayouts) && w.windowLayouts.length > 0
            );

            // Backward-compatibility: if backend only has legacy windowLayouts,
            // hydrate Main workspace from that data after fresh browser sessions.
            let hydratedWorkspaces = remoteWorkspaces;
            if (!hasWorkspaceLayouts && legacyWindowLayouts.length > 0) {
              const mainWorkspace = remoteWorkspaces.find((w) => w.id === 'main');
              if (mainWorkspace) {
                hydratedWorkspaces = remoteWorkspaces.map((w) =>
                  w.id === 'main' ? { ...w, windowLayouts: legacyWindowLayouts } : w
                );
              } else {
                hydratedWorkspaces = [
                  {
                    id: 'main',
                    name: 'Main',
                    isMain: true,
                    createdAt: Date.now(),
                    windowLayouts: legacyWindowLayouts,
                  },
                  ...remoteWorkspaces,
                ];
              }
            }

            const remoteActiveId = data.activeWorkspaceId || 'main';
            const validActiveId = hydratedWorkspaces.some((w) => w.id === local.activeWorkspaceId)
              ? local.activeWorkspaceId
              : hydratedWorkspaces.some((w) => w.id === remoteActiveId)
                ? remoteActiveId
                : (hydratedWorkspaces[0]?.id || 'main');

            set({
              workspaces: hydratedWorkspaces,
              activeWorkspaceId: validActiveId,
              colors: data.colors || DEFAULT_COLORS,
              theme: { ...DEFAULT_THEME, ...(data.theme || {}) },
              columnVisibility: data.columnVisibility || {},
              columnOrder: data.columnOrder || {},
              // Keep layoutInitialized in sync so workspace page does not open defaults.
              layoutInitialized:
                hasWorkspaceLayouts || legacyWindowLayouts.length > 0
                  ? true
                  : local.layoutInitialized,
              workspacesModifiedAt: data.updatedAt ? new Date(data.updatedAt).getTime() : Date.now(),
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
        workspacesModifiedAt: Date.now(),
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
          columnVisibility: state.columnVisibility,
          columnOrder: state.columnOrder,
        }, null, 2);
      },

      importPreferences: (json) => {
        try {
          const data = JSON.parse(json);
          set({
            colors: data.colors || DEFAULT_COLORS,
            theme: { ...DEFAULT_THEME, ...(data.theme || {}) },
            windowLayouts: data.windowLayouts || [],
            layoutInitialized: data.layoutInitialized ?? false,
            workspaces: data.workspaces || [DEFAULT_MAIN_WORKSPACE],
            activeWorkspaceId: data.activeWorkspaceId || 'main',
            columnVisibility: data.columnVisibility || {},
            columnOrder: data.columnOrder || {},
            workspacesModifiedAt: Date.now(),
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
        workspacesModifiedAt: state.workspacesModifiedAt,
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
export const selectFont = (state: UserPreferencesState) => state.theme.font;
export const selectTimezone = (state: UserPreferencesState) => state.theme.timezone || 'America/New_York';

// Workspace selectors
export const selectWorkspaces = (state: UserPreferencesState) => state.workspaces;
export const selectActiveWorkspaceId = (state: UserPreferencesState) => state.activeWorkspaceId;
export const selectActiveWorkspace = (state: UserPreferencesState) => 
  state.workspaces.find(w => w.id === state.activeWorkspaceId);


