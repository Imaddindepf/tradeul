'use client';

import React, { createContext, useContext, useState, useCallback, ReactNode, useRef, useEffect } from 'react';
import { floatingZIndexManager } from '@/lib/z-index';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { getWindowType } from '@/lib/window-config';

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
}

/** Layout serializable de una ventana (sin contenido) */
export interface SerializableWindowLayout {
  title: string;
  x: number;
  y: number;
  width: number;
  height: number;
  isMinimized: boolean;
}

interface FloatingWindowContextType {
  windows: FloatingWindow[];
  openWindow: (config: Omit<FloatingWindow, 'id' | 'zIndex' | 'isMinimized' | 'isMaximized'>) => string;
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

  const openWindow = useCallback((config: Omit<FloatingWindow, 'id' | 'zIndex' | 'isMinimized' | 'isMaximized'>) => {
    // Siempre crear una nueva ventana (permite múltiples instancias del mismo tipo)
    // El usuario puede tener varios Screeners, Ratio Analysis, etc. con datos diferentes
    const id = generateWindowId();
    const zIndex = floatingZIndexManager.getNext();

    // Offset para ventanas con el mismo título (cascade effect)
    const currentWindows = windowsRef.current;
    const sameTypeCount = currentWindows.filter((w) => w.title === config.title).length;
    const offset = sameTypeCount * 30; // 30px offset por cada ventana del mismo tipo

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
      const layouts = windows.map((w) => ({
        id: w.id,
        type: getWindowType(w.title),
        title: w.title,
        position: { x: w.x, y: w.y },
        size: { width: w.width, height: w.height },
        isMinimized: w.isMinimized,
        zIndex: w.zIndex,
      }));

      saveWindowLayouts(layouts);
      // console.log('[Layout] Auto-guardado:', layouts.length, 'ventanas');
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
