'use client';

import { useCallback } from 'react';
import { useFloatingWindow, SerializableWindowLayout } from '@/contexts/FloatingWindowContext';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { getWindowType } from '@/lib/window-config';

/**
 * Hook para guardar y restaurar el layout de ventanas
 * Estilo Godel Terminal: vuelves al día siguiente y todo está igual
 */
export function useLayoutPersistence() {
  const { exportLayout, closeAllWindows } = useFloatingWindow();
  const saveWindowLayouts = useUserPreferencesStore((s) => s.saveWindowLayouts);
  const windowLayouts = useUserPreferencesStore((s) => s.windowLayouts);
  const clearWindowLayouts = useUserPreferencesStore((s) => s.clearWindowLayouts);
  const layoutInitialized = useUserPreferencesStore((s) => s.layoutInitialized);

  /**
   * Guardar el layout actual de todas las ventanas
   * NOTA: Usamos un ID único para cada ventana (no el título)
   * para permitir múltiples ventanas del mismo tipo
   */
  const saveLayout = useCallback(() => {
    const layout = exportLayout();

    // Convertir a formato del store con ID único
    const layouts = layout.map((w, index) => ({
      id: `${w.title}-${index}-${Date.now()}`, // ID único para múltiples ventanas del mismo tipo
      type: getWindowType(w.title),
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
   * Obtener el layout guardado (incluyendo ID para restaurar estado)
   */
  const getSavedLayout = useCallback((): SerializableWindowLayout[] => {
    return windowLayouts.map((w) => ({
      id: w.id, // Preservar ID para restaurar componentState
      title: w.title,
      x: w.position.x,
      y: w.position.y,
      width: w.size.width,
      height: w.size.height,
      isMinimized: w.isMinimized,
    }));
  }, [windowLayouts]);

  /**
   * Verificar si hay un layout guardado con ventanas
   */
  const hasLayout = windowLayouts.length > 0;

  /**
   * Verificar si el usuario ya ha interactuado con el sistema de layouts
   * (true = ya usó, aunque tenga 0 ventanas. false = primera vez)
   */
  const isLayoutInitialized = layoutInitialized;

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
    isLayoutInitialized,
    clearLayout,
    savedCount: windowLayouts.length,
  };
}

