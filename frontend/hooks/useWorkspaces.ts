'use client';

/**
 * useWorkspaces - Hook para gestionar múltiples workspaces/dashboards
 * 
 * Estilo GODEL Terminal / IBKR:
 * - Main workspace siempre existe (no se puede eliminar)
 * - Crear nuevos workspaces con diferentes layouts
 * - Cambiar entre workspaces preservando estado de cada uno
 * 
 * Sincronización:
 * - Auto-sync a backend con debounce cuando cambian workspaces
 * - Carga inicial desde backend si hay sesión activa
 */

import { useCallback, useMemo, useRef, useEffect } from 'react';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { useAuth } from '@clerk/nextjs';
import { 
  useUserPreferencesStore, 
  Workspace, 
  WindowLayout,
  selectWorkspaces,
  selectActiveWorkspaceId,
  selectActiveWorkspace,
} from '@/stores/useUserPreferencesStore';
import { getWindowType } from '@/lib/window-config';

// Debounce delay para sync al backend (3 segundos)
const SYNC_DEBOUNCE_MS = 3000;

export interface UseWorkspacesReturn {
  /** Lista de todos los workspaces */
  workspaces: Workspace[];
  /** ID del workspace activo */
  activeWorkspaceId: string;
  /** Workspace activo completo */
  activeWorkspace: Workspace | undefined;
  /** Crear nuevo workspace y retornar su ID */
  createWorkspace: (name: string) => string;
  /** Eliminar workspace (no permite eliminar Main) */
  deleteWorkspace: (workspaceId: string) => void;
  /** Renombrar workspace */
  renameWorkspace: (workspaceId: string, newName: string) => void;
  /** Cambiar al workspace especificado (guarda actual, restaura nuevo) */
  switchWorkspace: (workspaceId: string, getWindowContent: (layout: { title: string; componentState?: Record<string, unknown> }) => React.ReactNode) => void;
  /** Guardar layout actual en el workspace activo */
  saveCurrentLayout: () => void;
  /** Verificar si es el workspace Main */
  isMainWorkspace: (workspaceId: string) => boolean;
}

export function useWorkspaces(): UseWorkspacesReturn {
  const { windows, openWindow, closeWindow } = useFloatingWindow();
  const { getToken, isSignedIn } = useAuth();
  const syncTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  // Store actions
  const storeCreateWorkspace = useUserPreferencesStore((s) => s.createWorkspace);
  const storeDeleteWorkspace = useUserPreferencesStore((s) => s.deleteWorkspace);
  const storeRenameWorkspace = useUserPreferencesStore((s) => s.renameWorkspace);
  const storeSetActiveWorkspace = useUserPreferencesStore((s) => s.setActiveWorkspace);
  const storeSaveWorkspaceLayouts = useUserPreferencesStore((s) => s.saveWorkspaceLayouts);
  const syncWorkspacesToBackend = useUserPreferencesStore((s) => s.syncWorkspacesToBackend);
  const setWorkspaceSwitching = useUserPreferencesStore((s) => s.setWorkspaceSwitching);
  
  // Store selectors
  const workspaces = useUserPreferencesStore(selectWorkspaces);
  const activeWorkspaceId = useUserPreferencesStore(selectActiveWorkspaceId);
  const activeWorkspace = useUserPreferencesStore(selectActiveWorkspace);

  /**
   * Debounced sync to backend
   * Se llama después de cualquier cambio en workspaces
   */
  const scheduleSyncToBackend = useCallback(() => {
    // Solo sincronizar si el usuario está autenticado
    if (!isSignedIn) return;
    
    // Cancelar sync pendiente
    if (syncTimeoutRef.current) {
      clearTimeout(syncTimeoutRef.current);
    }
    // Programar nuevo sync con token
    syncTimeoutRef.current = setTimeout(() => {
      syncWorkspacesToBackend(getToken);
    }, SYNC_DEBOUNCE_MS);
  }, [syncWorkspacesToBackend, getToken, isSignedIn]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (syncTimeoutRef.current) {
        clearTimeout(syncTimeoutRef.current);
      }
    };
  }, []);

  /**
   * Exportar layout actual de las ventanas abiertas.
   * Preserva componentState del workspace activo (metadata de restauración).
   */
  const exportCurrentLayout = useCallback((): WindowLayout[] => {
    // Recuperar componentState existente del workspace activo
    const store = useUserPreferencesStore.getState();
    const activeWs = store.workspaces.find(w => w.id === store.activeWorkspaceId);
    const existingLayouts = activeWs?.windowLayouts || store.windowLayouts;
    const componentStateMap = new Map(
      existingLayouts.map(l => [l.id, l.componentState])
    );

    return windows.map((w) => ({
      id: w.id,
      type: getWindowType(w.title),
      title: w.title,
      position: { x: w.x, y: w.y },
      size: { width: w.width, height: w.height },
      isMinimized: w.isMinimized,
      zIndex: w.zIndex,
      componentState: componentStateMap.get(w.id),
    }));
  }, [windows]);

  /**
   * Guardar layout actual en el workspace activo
   */
  const saveCurrentLayout = useCallback(() => {
    const layouts = exportCurrentLayout();
    storeSaveWorkspaceLayouts(activeWorkspaceId, layouts);
    // Sync to backend (debounced)
    scheduleSyncToBackend();
  }, [exportCurrentLayout, activeWorkspaceId, storeSaveWorkspaceLayouts, scheduleSyncToBackend]);

  /**
   * Crear nuevo workspace
   */
  const createWorkspace = useCallback((name: string): string => {
    // Guardar layout actual antes de crear nuevo
    saveCurrentLayout();
    const id = storeCreateWorkspace(name);
    // Sync to backend
    scheduleSyncToBackend();
    return id;
  }, [saveCurrentLayout, storeCreateWorkspace, scheduleSyncToBackend]);

  /**
   * Eliminar workspace
   */
  const deleteWorkspace = useCallback((workspaceId: string) => {
    storeDeleteWorkspace(workspaceId);
    // Sync to backend
    scheduleSyncToBackend();
  }, [storeDeleteWorkspace, scheduleSyncToBackend]);

  /**
   * Renombrar workspace
   */
  const renameWorkspace = useCallback((workspaceId: string, newName: string) => {
    storeRenameWorkspace(workspaceId, newName);
    // Sync to backend
    scheduleSyncToBackend();
  }, [storeRenameWorkspace, scheduleSyncToBackend]);

  /**
   * Cambiar al workspace especificado.
   * Flujo: guardar actual → cerrar ventanas → cambiar ID → restaurar destino.
   */
  const switchWorkspace = useCallback((
    workspaceId: string, 
    getWindowContent: (layout: { title: string; componentState?: Record<string, unknown> }) => React.ReactNode
  ) => {
    // Leer todo del store de forma síncrona (sin depender de closures de React)
    const store = useUserPreferencesStore.getState();
    if (workspaceId === store.activeWorkspaceId) return;

    // ── 1. Bloquear auto-save ──
    setWorkspaceSwitching(true);

    // ── 2. Guardar layout actual al workspace ACTUAL ──
    const currentWs = store.workspaces.find(w => w.id === store.activeWorkspaceId);
    const existingLayouts = currentWs?.windowLayouts || [];
    const csMap = new Map(existingLayouts.map(l => [l.id, l.componentState]));

    const layoutsToSave: WindowLayout[] = windows.map(w => ({
      id: w.id,
      type: getWindowType(w.title),
      title: w.title,
      position: { x: w.x, y: w.y },
      size: { width: w.width, height: w.height },
      isMinimized: w.isMinimized,
      zIndex: w.zIndex,
      componentState: csMap.get(w.id),
    }));
    storeSaveWorkspaceLayouts(store.activeWorkspaceId, layoutsToSave);

    // ── 3. Cerrar todas las ventanas ──
    windows.forEach(w => closeWindow(w.id));

    // ── 4. Cambiar workspace activo ──
    storeSetActiveWorkspace(workspaceId);

    // ── 5. Restaurar ventanas del workspace destino ──
    setTimeout(() => {
      const freshStore = useUserPreferencesStore.getState();
      const target = freshStore.workspaces.find(w => w.id === workspaceId);
      const layouts = (target?.windowLayouts || []).filter(l => l.title);

      layouts.forEach(layout => {
        const content = getWindowContent(layout);
        if (content) {
          openWindow({
            id: layout.id,
            title: layout.title,
            content,
            x: layout.position.x,
            y: layout.position.y,
            width: layout.size.width,
            height: layout.size.height,
            hideHeader: layout.title.startsWith('Scanner:') || layout.title.startsWith('Events:'),
          });
        }
      });

      // ── 6. Desbloquear auto-save ──
      setTimeout(() => {
        setWorkspaceSwitching(false);
        scheduleSyncToBackend();
      }, 100);
    }, 50);
  }, [
    windows,
    storeSaveWorkspaceLayouts,
    storeSetActiveWorkspace,
    setWorkspaceSwitching,
    closeWindow,
    openWindow,
    scheduleSyncToBackend,
  ]);

  /**
   * Verificar si es el workspace Main
   */
  const isMainWorkspace = useCallback((workspaceId: string): boolean => {
    const workspace = workspaces.find(w => w.id === workspaceId);
    return workspace?.isMain ?? false;
  }, [workspaces]);

  return useMemo(() => ({
    workspaces,
    activeWorkspaceId,
    activeWorkspace,
    createWorkspace,
    deleteWorkspace,
    renameWorkspace,
    switchWorkspace,
    saveCurrentLayout,
    isMainWorkspace,
  }), [
    workspaces,
    activeWorkspaceId,
    activeWorkspace,
    createWorkspace,
    deleteWorkspace,
    renameWorkspace,
    switchWorkspace,
    saveCurrentLayout,
    isMainWorkspace,
  ]);
}

