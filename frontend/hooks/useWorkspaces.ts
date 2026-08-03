'use client';

/**
 * useWorkspaces - Hook para gestionar múltiples workspaces/dashboards
 * 
 * Estilo GODEL Terminal / IBKR:
 * - Main workspace siempre existe (no se puede eliminar)
 * - Crear nuevos workspaces con diferentes layouts
 * - Cambiar entre workspaces preservando estado de cada uno
 * 
 * Sincronización (PR1): la hace useClientStateSync/prefsSyncClient — aquí solo
 * se fuerza un flush inmediato en los cambios estructurales.
 */

import { useCallback, useMemo } from 'react';
import { useFloatingWindowActions, useFloatingWindowsList, type LinkGroup } from '@/contexts/FloatingWindowContext';
import {
  useUserPreferencesStore,
  Workspace,
  WindowLayout,
  selectWorkspaces,
  selectActiveWorkspaceId,
  selectActiveWorkspace,
} from '@/stores/useUserPreferencesStore';
import { getWindowType } from '@/lib/window-config';
import { flush } from '@/lib/client-state/prefsSyncClient';

interface UseWorkspacesReturn {
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
  const { openWindow, closeWindow } = useFloatingWindowActions();
  const windows = useFloatingWindowsList();

  // Store actions
  const storeCreateWorkspace = useUserPreferencesStore((s) => s.createWorkspace);
  const storeDeleteWorkspace = useUserPreferencesStore((s) => s.deleteWorkspace);
  const storeRenameWorkspace = useUserPreferencesStore((s) => s.renameWorkspace);
  const storeSetActiveWorkspace = useUserPreferencesStore((s) => s.setActiveWorkspace);
  const storeSaveWorkspaceLayouts = useUserPreferencesStore((s) => s.saveWorkspaceLayouts);
  const setWorkspaceSwitching = useUserPreferencesStore((s) => s.setWorkspaceSwitching);

  // Store selectors
  const workspaces = useUserPreferencesStore(selectWorkspaces);
  const activeWorkspaceId = useUserPreferencesStore(selectActiveWorkspaceId);
  const activeWorkspace = useUserPreferencesStore(selectActiveWorkspace);

  // PR1: el sync al backend ya no vive aquí. El watcher de useClientStateSync
  // detecta los cambios del store y los sincroniza con debounce; las acciones
  // estructurales (crear/borrar/renombrar) fuerzan un flush inmediato.

  /**
   * Exportar layout actual de las ventanas abiertas.
   * Preserva componentState del workspace activo (metadata de restauración).
   */
  const exportCurrentLayout = useCallback((): WindowLayout[] => {
    const store = useUserPreferencesStore.getState();
    const activeWs = store.workspaces.find(w => w.id === store.activeWorkspaceId);
    const existingLayouts = activeWs?.windowLayouts || store.windowLayouts;
    const metadataMap = new Map(
      existingLayouts.map(l => [l.id, { componentState: l.componentState, linkGroup: l.linkGroup }])
    );

    return windows.map((w) => {
      const saved = metadataMap.get(w.id);
      return {
        id: w.id,
        type: getWindowType(w.title),
        title: w.title,
        position: { x: w.x, y: w.y },
        size: { width: w.width, height: w.height },
        isMinimized: w.isMinimized,
        zIndex: w.zIndex,
        componentState: saved?.componentState,
        linkGroup: saved?.linkGroup || w.linkGroup || undefined,
      };
    });
  }, [windows]);

  /**
   * Guardar layout actual en el workspace activo
   */
  const saveCurrentLayout = useCallback(() => {
    const layouts = exportCurrentLayout();
    storeSaveWorkspaceLayouts(activeWorkspaceId, layouts);
    // El watcher de useClientStateSync marca 'workspaces' dirty y sincroniza.
  }, [exportCurrentLayout, activeWorkspaceId, storeSaveWorkspaceLayouts]);

  /**
   * Crear nuevo workspace
   */
  const createWorkspace = useCallback((name: string): string => {
    saveCurrentLayout();
    const id = storeCreateWorkspace(name);
    void flush('manual'); // cambio estructural: no esperar al debounce
    return id;
  }, [saveCurrentLayout, storeCreateWorkspace]);

  /**
   * Eliminar workspace
   */
  const deleteWorkspace = useCallback((workspaceId: string) => {
    storeDeleteWorkspace(workspaceId);
    void flush('manual');
  }, [storeDeleteWorkspace]);

  /**
   * Renombrar workspace
   */
  const renameWorkspace = useCallback((workspaceId: string, newName: string) => {
    storeRenameWorkspace(workspaceId, newName);
    void flush('manual');
  }, [storeRenameWorkspace]);

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
    const metaMap = new Map(
      existingLayouts.map(l => [l.id, { componentState: l.componentState, linkGroup: l.linkGroup }])
    );

    const layoutsToSave: WindowLayout[] = windows.map(w => {
      const saved = metaMap.get(w.id);
      return {
        id: w.id,
        type: getWindowType(w.title),
        title: w.title,
        position: { x: w.x, y: w.y },
        size: { width: w.width, height: w.height },
        isMinimized: w.isMinimized,
        zIndex: w.zIndex,
        componentState: saved?.componentState,
        linkGroup: saved?.linkGroup || w.linkGroup || undefined,
      };
    });
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
          const hideHeader = layout.title.startsWith('Scanner:')
            || layout.title.startsWith('Events:')
            || layout.title === 'Market Pulse';
          openWindow({
            id: layout.id,
            title: layout.title,
            content,
            x: layout.position.x,
            y: layout.position.y,
            width: layout.size.width,
            height: layout.size.height,
            hideHeader,
            componentState: layout.componentState,
            linkGroup: (layout.linkGroup as LinkGroup) || undefined,
          });
        }
      });

      // ── 6. Desbloquear auto-save ──
      // El watcher ya marcó 'workspaces' y 'activeWorkspace' dirty al guardar
      // el layout y cambiar de workspace; el debounce del client sincroniza.
      setTimeout(() => {
        setWorkspaceSwitching(false);
      }, 100);
    }, 50);
  }, [
    windows,
    storeSaveWorkspaceLayouts,
    storeSetActiveWorkspace,
    setWorkspaceSwitching,
    closeWindow,
    openWindow,
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

