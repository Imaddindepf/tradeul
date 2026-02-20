'use client';

/**
 * useWorkspaceSync - Hook para sincronización inicial de workspaces con backend
 * 
 * Se usa una vez al inicio de la aplicación para:
 * 1. Cargar preferencias del backend si el usuario está autenticado
 * 2. Sincronizar periódicamente (opcional)
 */

import { useEffect, useRef } from 'react';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { useAuth } from '@clerk/nextjs';

export interface UseWorkspaceSyncOptions {
  /** Habilitar carga inicial desde backend */
  enableInitialLoad?: boolean;
  /** Habilitar sync periódico (ms) - 0 para deshabilitar */
  periodicSyncInterval?: number;
}

const DEFAULT_OPTIONS: UseWorkspaceSyncOptions = {
  enableInitialLoad: true,
  periodicSyncInterval: 0, // Disabled by default, sync on changes instead
};

export function useWorkspaceSync(options: UseWorkspaceSyncOptions = DEFAULT_OPTIONS) {
  const { isSignedIn, isLoaded, getToken } = useAuth();
  const loadFromBackend = useUserPreferencesStore((s) => s.loadFromBackend);
  const syncWorkspacesToBackend = useUserPreferencesStore((s) => s.syncWorkspacesToBackend);
  const lastSyncedAt = useUserPreferencesStore((s) => s.lastSyncedAt);
  
  const hasLoadedRef = useRef(false);
  const syncIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Carga inicial desde backend cuando hay sesión
  useEffect(() => {
    if (
      options.enableInitialLoad &&
      isLoaded &&
      isSignedIn &&
      !hasLoadedRef.current
    ) {
      hasLoadedRef.current = true;
      
      // Intentar cargar desde backend con token
      loadFromBackend(getToken).then((loaded) => {
        if (loaded) {
        } else {
        }
      });
    }
  }, [isLoaded, isSignedIn, options.enableInitialLoad, loadFromBackend, getToken]);

  // Sync periódico (opcional)
  useEffect(() => {
    if (options.periodicSyncInterval && options.periodicSyncInterval > 0 && isSignedIn) {
      syncIntervalRef.current = setInterval(() => {
        syncWorkspacesToBackend(getToken);
      }, options.periodicSyncInterval);

      return () => {
        if (syncIntervalRef.current) {
          clearInterval(syncIntervalRef.current);
        }
      };
    }
  }, [options.periodicSyncInterval, isSignedIn, syncWorkspacesToBackend, getToken]);

  // Sync al cerrar ventana/pestaña
  useEffect(() => {
    const handleBeforeUnload = () => {
      // Sync síncrono usando sendBeacon si está disponible
      if (isSignedIn && navigator.sendBeacon) {
        const state = useUserPreferencesStore.getState();
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const data = JSON.stringify({
          workspaces: state.workspaces,
          activeWorkspaceId: state.activeWorkspaceId,
        });
        navigator.sendBeacon(`${apiUrl}/api/v1/user/preferences/workspaces`, data);
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isSignedIn]);

  return {
    lastSyncedAt,
    isAuthenticated: isSignedIn,
    forceSync: () => syncWorkspacesToBackend(getToken),
    forceLoad: () => loadFromBackend(getToken),
    getToken,
  };
}

export default useWorkspaceSync;

