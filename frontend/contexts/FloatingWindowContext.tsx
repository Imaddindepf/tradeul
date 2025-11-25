'use client';

import React, { createContext, useContext, useState, useCallback, ReactNode, useRef } from 'react';
import { floatingZIndexManager } from '@/lib/z-index';

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
}

const FloatingWindowContext = createContext<FloatingWindowContextType | undefined>(undefined);

let windowIdCounter = 0;

export function FloatingWindowProvider({ children }: { children: ReactNode }) {
  const [windows, setWindows] = useState<FloatingWindow[]>([]);

  // Usar ref para acceder al estado actual en callbacks
  const windowsRef = useRef<FloatingWindow[]>([]);
  windowsRef.current = windows;

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
    // Usar ref para ver el estado actual (no el del momento de crear el callback)
    const currentWindows = windowsRef.current;
    const existingWindow = currentWindows.find((w) => w.title === config.title);

    if (existingWindow) {
      // Si existe, traerla al frente y restaurarla
      const zIndex = floatingZIndexManager.getNext();
      setWindows((prev) =>
        prev.map((w) => (w.id === existingWindow.id ? { ...w, zIndex, isMinimized: false } : w))
      );
      return existingWindow.id;
    }

    // Si no existe, crear una nueva
    const id = `window-${++windowIdCounter}`;
    const zIndex = floatingZIndexManager.getNext();

    const newWindow: FloatingWindow = {
      ...config,
      id,
      zIndex,
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
