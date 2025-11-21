'use client';

import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
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

  const getMaxZIndex = useCallback(() => {
    return floatingZIndexManager.getCurrent();
  }, []);

  const openWindow = useCallback((config: Omit<FloatingWindow, 'id' | 'zIndex' | 'isMinimized' | 'isMaximized'>) => {
    const id = `window-${++windowIdCounter}`;
    
    // Usar el mismo sistema de z-index que las tablas del scanner
    // para que todas las ventanas compitan en la misma jerarquía
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

  const bringToFront = useCallback((id: string) => {
    // Usar el mismo sistema de z-index que las tablas
    const zIndex = floatingZIndexManager.getNext();
    updateWindow(id, { zIndex });
  }, [updateWindow]);

  const minimizeWindow = useCallback((id: string) => {
    updateWindow(id, { isMinimized: true, isMaximized: false });
  }, [updateWindow]);

  const maximizeWindow = useCallback((id: string) => {
    updateWindow(id, { isMaximized: true, isMinimized: false });
  }, [updateWindow]);

  const restoreWindow = useCallback((id: string) => {
    updateWindow(id, { isMinimized: false, isMaximized: false });
  }, [updateWindow]);

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

