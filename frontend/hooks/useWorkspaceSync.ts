'use client';

/**
 * useWorkspaceSync — wrapper fino de compatibilidad sobre prefsSyncClient.
 *
 * PR1 (DISENO_SYNC_MULTITAB_IMPL.md): los efectos que vivían aquí (initial
 * load con retries, debounce de escritura, beacon de unload, refresh de token)
 * se movieron a UNA instancia por pestaña en ClientStateProvider/useClientStateSync.
 * Este hook queda solo para los consumidores existentes (Settings) que
 * necesitan forceSync/forceLoad/estado de sesión, sin efectos propios.
 */

import { useCallback } from 'react';
import { useAuth } from '@clerk/nextjs';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { flush, initialLoad } from '@/lib/client-state/prefsSyncClient';

interface UseWorkspaceSyncOptions {
  /** Ignorado desde PR1: la carga inicial la hace useClientStateSync una sola vez. */
  enableInitialLoad?: boolean;
}

export function useWorkspaceSync(_options: UseWorkspaceSyncOptions = {}) {
  const { isSignedIn, getToken } = useAuth();
  const lastSyncedAt = useUserPreferencesStore((s) => s.lastSyncedAt);

  const forceSync = useCallback(() => flush('manual'), []);
  const forceLoad = useCallback(() => initialLoad(), []);

  return {
    lastSyncedAt,
    isAuthenticated: isSignedIn,
    forceSync,
    forceLoad,
    getToken,
  };
}

export default useWorkspaceSync;
