'use client';

import React, { createContext, useContext, useState, useCallback, ReactNode, useRef, useEffect, useMemo } from 'react';
import { floatingZIndexManager } from '@/lib/z-index';
import { useUserPreferencesStore, consumePendingComponentStates } from '@/stores/useUserPreferencesStore';
import { getWindowType } from '@/lib/window-config';

// ============================================================================
// Window Component State - Estado interno de componentes por ventana
// ============================================================================

/** Tipo genérico para el estado de un componente */
export type WindowComponentState = Record<string, unknown>;

/** Context para el estado del componente de la ventana actual */
const WindowStateContext = createContext<{
  state: WindowComponentState;
  setState: (state: WindowComponentState) => void;
  updateState: (partial: Partial<WindowComponentState>) => void;
} | null>(null);

// ============================================================================
// WindowId Context - permite que cualquier componente hijo conozca su windowId
// ============================================================================

const WindowIdContext = createContext<string | null>(null);

/** 
 * Provider que envuelve el contenido de cada ventana con su windowId.
 * Usado internamente por FloatingWindowManager.
 */
export function WindowIdProvider({ windowId, children }: { windowId: string; children: ReactNode }) {
  return (
    <WindowIdContext.Provider value={windowId}>
      {children}
    </WindowIdContext.Provider>
  );
}

/**
 * Provider que permite a los componentes de ventana persistir su estado interno.
 * Se usa junto con WindowIdProvider.
 */
export function WindowStateProvider({
  windowId,
  initialState = {},
  children
}: {
  windowId: string;
  initialState?: WindowComponentState;
  children: ReactNode;
}) {
  const updateWindowComponentState = useUserPreferencesStore((s) => s.updateWindowComponentState);
  const getWindowComponentState = useUserPreferencesStore((s) => s.getWindowComponentState);

  // Cargar estado guardado o usar el inicial
  const savedState = useMemo(() => getWindowComponentState(windowId), [windowId, getWindowComponentState]);
  const [state, setStateInternal] = useState<WindowComponentState>(() => savedState || initialState);

  // Refs para debounce y estado pendiente
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isFirstRenderRef = useRef(true);
  const pendingStateRef = useRef<WindowComponentState | null>(null);  // Estado pendiente de guardar
  const hasPendingSaveRef = useRef(false);  // Flag para saber si hay guardado pendiente

  // Función interna para guardar inmediatamente
  const saveImmediately = useCallback((stateToSave: WindowComponentState) => {
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
      saveTimeoutRef.current = null;
    }
    updateWindowComponentState(windowId, stateToSave);
    hasPendingSaveRef.current = false;
    pendingStateRef.current = null;
  }, [windowId, updateWindowComponentState]);

  // Actualizar estado y programar guardado
  const setState = useCallback((newState: WindowComponentState) => {
    setStateInternal(newState);
    pendingStateRef.current = newState;
    hasPendingSaveRef.current = true;

    // Programar guardado con debounce
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }
    saveTimeoutRef.current = setTimeout(() => {
      saveImmediately(newState);
    }, 500);  // Reducido a 500ms para mejor responsividad
  }, [saveImmediately]);

  // Actualizar parcialmente el estado
  const updateState = useCallback((partial: Partial<WindowComponentState>) => {
    setStateInternal((prev) => {
      const newState = { ...prev, ...partial };
      pendingStateRef.current = newState;
      hasPendingSaveRef.current = true;

      // Programar guardado con debounce
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
      saveTimeoutRef.current = setTimeout(() => {
        saveImmediately(newState);
      }, 500);  // Reducido a 500ms para mejor responsividad

      return newState;
    });
  }, [saveImmediately]);

  // Sincronizar estado guardado al montar (si hay)
  useEffect(() => {
    if (isFirstRenderRef.current && savedState) {
      setStateInternal(savedState);
      isFirstRenderRef.current = false;
    }
  }, [savedState]);

  // Cleanup: GUARDAR INMEDIATAMENTE al desmontar si hay cambios pendientes
  // EXCEPCIÓN: NO guardar si estamos en medio de un cambio de workspace
  // (el workspace activo ya cambió y escribiríamos en el workspace equivocado)
  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
      // IMPORTANTE: Solo guardar si NO estamos cambiando de workspace
      const store = useUserPreferencesStore.getState();
      if (store.isWorkspaceSwitching) {
        // Skip: el switchWorkspace ya guardó todo antes de cerrar ventanas
        return;
      }
      if (hasPendingSaveRef.current && pendingStateRef.current) {
        updateWindowComponentState(windowId, pendingStateRef.current);
      }
    };
  }, [windowId, updateWindowComponentState]);

  const contextValue = useMemo(() => ({
    state,
    setState,
    updateState
  }), [state, setState, updateState]);

  return (
    <WindowStateContext.Provider value={contextValue}>
      {children}
    </WindowStateContext.Provider>
  );
}

/**
 * Hook para persistir el estado interno del componente de una ventana.
 * El estado se guarda automáticamente en localStorage y se restaura al reabrir.
 * 
 * @example
 * function MyContent() {
 *   const { state, updateState } = useWindowState<{ search: string; filters: string[] }>();
 *   
 *   return (
 *     <input 
 *       value={state.search || ''} 
 *       onChange={(e) => updateState({ search: e.target.value })} 
 *     />
 *   );
 * }
 */
export function useWindowState<T extends WindowComponentState = WindowComponentState>() {
  const context = useContext(WindowStateContext);

  if (!context) {
    // Si no hay provider, retornar un estado vacío que no persiste
    // Esto permite que el componente funcione fuera de una ventana flotante
    return {
      state: {} as T,
      setState: (() => { }) as (state: T) => void,
      updateState: (() => { }) as (partial: Partial<T>) => void,
    };
  }

  return {
    state: context.state as T,
    setState: context.setState as (state: T) => void,
    updateState: context.updateState as (partial: Partial<T>) => void,
  };
}

/**
 * Hook para obtener el windowId de la ventana actual.
 * Cualquier componente dentro de una FloatingWindow puede usarlo.
 * 
 * @example
 * function MyContent() {
 *   const windowId = useCurrentWindowId();
 *   const { closeWindow } = useFloatingWindow();
 *   
 *   return <button onClick={() => closeWindow(windowId)}>Cerrar</button>;
 * }
 */
export function useCurrentWindowId(): string | null {
  return useContext(WindowIdContext);
}

/**
 * Hook que retorna una función para cerrar la ventana actual.
 * Combina useCurrentWindowId + closeWindow para mayor comodidad.
 * 
 * @example
 * function MyContent() {
 *   const closeCurrentWindow = useCloseCurrentWindow();
 *   return <button onClick={closeCurrentWindow}>Cerrar</button>;
 * }
 */
export function useCloseCurrentWindow(): () => void {
  const windowId = useCurrentWindowId();
  const { closeWindow } = useFloatingWindow();

  return useCallback(() => {
    if (windowId) {
      closeWindow(windowId);
    }
  }, [windowId, closeWindow]);
}

// ============================================================================
// FloatingWindow Types & Context
// ============================================================================

export interface FloatingWindow {
  id: string;
  title: string;
  content: ReactNode;
  width: number;
  height: number;
  x: number;
  y: number;
  minWidth?: number;
  minHeight?: number;
  maxWidth?: number;
  maxHeight?: number;
  zIndex: number;
  isMinimized: boolean;
  isMaximized: boolean;
  /** Si true, no muestra la barra de título (para contenido que ya tiene su propia cabecera) */
  hideHeader?: boolean;
  /** Si true, el contenido ha sido abierto en una ventana externa (about:blank) */
  isPoppedOut?: boolean;
  /** Referencia a la ventana externa (about:blank) para poder cerrarla */
  poppedOutWindow?: Window | null;
  /** Restoration metadata — persisted with the window to avoid race conditions */
  componentState?: Record<string, unknown>;
}

/** Layout serializable de una ventana (sin contenido) */
export interface SerializableWindowLayout {
  id?: string;
  title: string;
  x: number;
  y: number;
  width: number;
  height: number;
  isMinimized: boolean;
}

interface FloatingWindowContextType {
  windows: FloatingWindow[];
  openWindow: (config: Omit<FloatingWindow, 'id' | 'zIndex' | 'isMinimized' | 'isMaximized'> & { id?: string }) => string;
  closeWindow: (id: string) => void;
  updateWindow: (id: string, updates: Partial<FloatingWindow>) => void;
  bringToFront: (id: string) => void;
  minimizeWindow: (id: string) => void;
  maximizeWindow: (id: string) => void;
  restoreWindow: (id: string) => void;
  getMaxZIndex: () => number;
  /** Exportar layout actual de todas las ventanas */
  exportLayout: () => SerializableWindowLayout[];
  /** Cerrar todas las ventanas */
  closeAllWindows: () => void;
}

const FloatingWindowContext = createContext<FloatingWindowContextType | undefined>(undefined);

// Usar timestamp + random para IDs únicos (evita problemas con HMR)
const generateWindowId = () => `window-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

export function FloatingWindowProvider({ children }: { children: ReactNode }) {
  const [windows, setWindows] = useState<FloatingWindow[]>([]);
  const saveWindowLayouts = useUserPreferencesStore((s) => s.saveWindowLayouts);

  // Usar ref para acceder al estado actual en callbacks
  const windowsRef = useRef<FloatingWindow[]>([]);
  windowsRef.current = windows;

  // Ref para debounce del auto-guardado
  const autoSaveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isInitializedRef = useRef(false);

  // Force-save layout on page unload (prevents data loss on reload)
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (autoSaveTimeoutRef.current) {
        clearTimeout(autoSaveTimeoutRef.current);
        autoSaveTimeoutRef.current = null;
      }
      const store = useUserPreferencesStore.getState();
      if (store.isWorkspaceSwitching) return;

      const currentWindows = windowsRef.current;
      if (currentWindows.length === 0) return;

      const activeWorkspaceId = store.activeWorkspaceId;
      const activeWorkspace = store.workspaces.find(w => w.id === activeWorkspaceId);
      const existingLayouts = activeWorkspace?.windowLayouts || store.windowLayouts;
      const csMap = new Map(existingLayouts.map(l => [l.id, l.componentState]));
      const pendingCs = consumePendingComponentStates();

      const layouts = currentWindows.map((w) => ({
        id: w.id,
        type: getWindowType(w.title),
        title: w.title,
        position: { x: w.x, y: w.y },
        size: { width: w.width, height: w.height },
        isMinimized: w.isMinimized,
        zIndex: w.zIndex,
        componentState: w.componentState || csMap.get(w.id) || pendingCs.get(w.id),
      }));

      if (activeWorkspaceId) {
        store.saveWorkspaceLayouts(activeWorkspaceId, layouts);
      } else {
        saveWindowLayouts(layouts);
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [saveWindowLayouts]);

  const getMaxZIndex = useCallback(() => {
    return floatingZIndexManager.getCurrent();
  }, []);

  const bringToFront = useCallback((id: string) => {
    // Todas las ventanas compiten en la misma jerarquía
    const zIndex = floatingZIndexManager.getNext();
    setWindows((prev) =>
      prev.map((w) => (w.id === id ? { ...w, zIndex, isMinimized: false } : w))
    );
  }, []);

  const openWindow = useCallback((config: Omit<FloatingWindow, 'id' | 'zIndex' | 'isMinimized' | 'isMaximized'> & { id?: string }) => {
    const id = config.id || generateWindowId();
    const zIndex = floatingZIndexManager.getNext();

    const currentWindows = windowsRef.current;

    // Prevent duplicate windows with the same ID (race condition guard)
    if (config.id && currentWindows.some((w) => w.id === config.id)) {
      return id;
    }

    const sameTypeCount = currentWindows.filter((w) => w.title === config.title).length;
    const offset = config.id ? 0 : sameTypeCount * 30;

    const newWindow: FloatingWindow = {
      ...config,
      id,
      zIndex,
      x: config.x + offset,
      y: config.y + offset,
      isMinimized: false,
      isMaximized: false,
    };

    setWindows((prev) => [...prev, newWindow]);
    return id;
  }, []);

  const closeWindow = useCallback((id: string) => {
    setWindows((prev) => prev.filter((w) => w.id !== id));
  }, []);

  const updateWindow = useCallback((id: string, updates: Partial<FloatingWindow>) => {
    setWindows((prev) =>
      prev.map((w) => (w.id === id ? { ...w, ...updates } : w))
    );
  }, []);

  const minimizeWindow = useCallback((id: string) => {
    setWindows((prev) =>
      prev.map((w) => (w.id === id ? { ...w, isMinimized: true, isMaximized: false } : w))
    );
  }, []);

  const maximizeWindow = useCallback((id: string) => {
    setWindows((prev) =>
      prev.map((w) => (w.id === id ? { ...w, isMaximized: true, isMinimized: false } : w))
    );
  }, []);

  const restoreWindow = useCallback((id: string) => {
    setWindows((prev) =>
      prev.map((w) => (w.id === id ? { ...w, isMinimized: false, isMaximized: false } : w))
    );
  }, []);

  const exportLayout = useCallback((): SerializableWindowLayout[] => {
    return windowsRef.current.map((w) => ({
      title: w.title,
      x: w.x,
      y: w.y,
      width: w.width,
      height: w.height,
      isMinimized: w.isMinimized,
    }));
  }, []);

  const closeAllWindows = useCallback(() => {
    setWindows([]);
  }, []);

  // Auto-guardar layout cuando cambian las ventanas (después de 3 segundos de inactividad)
  // NUEVO: Guarda en el workspace activo
  // NOTA: Se desactiva durante cambio de workspace (isWorkspaceSwitching)
  useEffect(() => {
    // No guardar en el primer render
    if (!isInitializedRef.current) {
      isInitializedRef.current = true;
      return;
    }

    // Cancelar timeout anterior
    if (autoSaveTimeoutRef.current) {
      clearTimeout(autoSaveTimeoutRef.current);
    }

    // Nuevo timeout de 3 segundos
    autoSaveTimeoutRef.current = setTimeout(() => {
      const store = useUserPreferencesStore.getState();

      // No guardar durante cambio de workspace
      if (store.isWorkspaceSwitching) return;

      const activeWorkspaceId = store.activeWorkspaceId;
      const activeWorkspace = store.workspaces.find(w => w.id === activeWorkspaceId);
      const existingLayouts = activeWorkspace?.windowLayouts || store.windowLayouts;
      const csMap = new Map(existingLayouts.map(l => [l.id, l.componentState]));
      const pendingCs = consumePendingComponentStates();

      const layouts = windows.map((w) => ({
        id: w.id,
        type: getWindowType(w.title),
        title: w.title,
        position: { x: w.x, y: w.y },
        size: { width: w.width, height: w.height },
        isMinimized: w.isMinimized,
        zIndex: w.zIndex,
        componentState: w.componentState || csMap.get(w.id) || pendingCs.get(w.id),
      }));

      if (activeWorkspaceId) {
        store.saveWorkspaceLayouts(activeWorkspaceId, layouts);
      } else {
        saveWindowLayouts(layouts);
      }
    }, 3000);

    return () => {
      if (autoSaveTimeoutRef.current) {
        clearTimeout(autoSaveTimeoutRef.current);
      }
    };
  }, [windows, saveWindowLayouts]);

  return (
    <FloatingWindowContext.Provider
      value={{
        windows,
        openWindow,
        closeWindow,
        updateWindow,
        bringToFront,
        minimizeWindow,
        maximizeWindow,
        restoreWindow,
        getMaxZIndex,
        exportLayout,
        closeAllWindows,
      }}
    >
      {children}
    </FloatingWindowContext.Provider>
  );
}

export function useFloatingWindow() {
  const context = useContext(FloatingWindowContext);
  if (!context) {
    throw new Error('useFloatingWindow must be used within FloatingWindowProvider');
  }
  return context;
}
