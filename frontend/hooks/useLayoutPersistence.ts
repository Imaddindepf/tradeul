'use client';

import { useCallback } from 'react';
import { useFloatingWindow, SerializableWindowLayout } from '@/contexts/FloatingWindowContext';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';

// Mapeo de títulos a tipos de ventana para reconstrucción
const WINDOW_TYPES: Record<string, string> = {
  'Settings': 'settings',
  'Dilution Tracker': 'dt',
  'SEC Filings': 'sec',
  'Financial Analysis': 'fa',
};

/**
 * Hook para guardar y restaurar el layout de ventanas
 * Estilo Godel Terminal: vuelves al día siguiente y todo está igual
 */
export function useLayoutPersistence() {
  const { exportLayout, closeAllWindows } = useFloatingWindow();
  const saveWindowLayouts = useUserPreferencesStore((s) => s.saveWindowLayouts);
  const windowLayouts = useUserPreferencesStore((s) => s.windowLayouts);
  const clearWindowLayouts = useUserPreferencesStore((s) => s.clearWindowLayouts);

  /**
   * Guardar el layout actual de todas las ventanas
   */
  const saveLayout = useCallback(() => {
    const layout = exportLayout();
    
    // Convertir a formato del store
    const layouts = layout.map((w) => ({
      id: w.title,
      type: WINDOW_TYPES[w.title as keyof typeof WINDOW_TYPES] || 'unknown',
      title: w.title,
      position: { x: w.x, y: w.y },
      size: { width: w.width, height: w.height },
      isMinimized: w.isMinimized,
      zIndex: 0, // Se recalcula al restaurar
    }));
    
    saveWindowLayouts(layouts);
    return layouts.length;
  }, [exportLayout, saveWindowLayouts]);

  /**
   * Obtener el layout guardado
   */
  const getSavedLayout = useCallback((): SerializableWindowLayout[] => {
    return windowLayouts.map((w) => ({
      title: w.title,
      x: w.position.x,
      y: w.position.y,
      width: w.size.width,
      height: w.size.height,
      isMinimized: w.isMinimized,
    }));
  }, [windowLayouts]);

  /**
   * Verificar si hay un layout guardado
   */
  const hasLayout = windowLayouts.length > 0;

  /**
   * Limpiar el layout guardado
   */
  const clearLayout = useCallback(() => {
    clearWindowLayouts();
    closeAllWindows();
  }, [clearWindowLayouts, closeAllWindows]);

  return {
    saveLayout,
    getSavedLayout,
    hasLayout,
    clearLayout,
    savedCount: windowLayouts.length,
  };
}

