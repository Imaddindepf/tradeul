'use client';

/**
 * useWorkspaceSync - Hook para sincronización de workspaces con backend
 * 
 * Estrategia: "sync on mutate" — cada cambio estructural se sincroniza
 * inmediatamente. beforeunload usa un token pre-cacheado como fallback.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { useAuth } from '@clerk/nextjs';

export interface UseWorkspaceSyncOptions {
  enableInitialLoad?: boolean;
  periodicSyncInterval?: number;
}

const DEFAULT_OPTIONS: UseWorkspaceSyncOptions = {
  enableInitialLoad: true,
  periodicSyncInterval: 0,
};

export function useWorkspaceSync(options: UseWorkspaceSyncOptions = DEFAULT_OPTIONS) {
  const { isSignedIn, isLoaded, getToken } = useAuth();
  const loadFromBackend = useUserPreferencesStore((s) => s.loadFromBackend);
  const syncWorkspacesToBackend = useUserPreferencesStore((s) => s.syncWorkspacesToBackend);
  const lastSyncedAt = useUserPreferencesStore((s) => s.lastSyncedAt);
  
  const hasLoadedRef = useRef(false);
  const syncIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const cachedTokenRef = useRef<string | null>(null);

  const refreshToken = useCallback(async () => {
    if (!getToken) return;
    try {
      cachedTokenRef.current = await getToken();
    } catch { /* token refresh failed, keep old */ }
  }, [getToken]);

  // Keep a fresh token cached for sendBeacon
  useEffect(() => {
    if (!isSignedIn) return;
    refreshToken();
    const interval = setInterval(refreshToken, 45_000);
    return () => clearInterval(interval);
  }, [isSignedIn, refreshToken]);

  // Initial load from backend
  useEffect(() => {
    if (
      options.enableInitialLoad &&
      isLoaded &&
      isSignedIn &&
      !hasLoadedRef.current
    ) {
      hasLoadedRef.current = true;
      loadFromBackend(getToken);
    }
  }, [isLoaded, isSignedIn, options.enableInitialLoad, loadFromBackend, getToken]);

  // Periodic sync (optional)
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

  // Fallback: sendBeacon on tab close with pre-cached token
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (!isSignedIn || !navigator.sendBeacon) return;

      const state = useUserPreferencesStore.getState();
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const payload = JSON.stringify({
        workspaces: state.workspaces,
        activeWorkspaceId: state.activeWorkspaceId,
        _token: cachedTokenRef.current,
      });
      const blob = new Blob([payload], { type: 'application/json' });
      navigator.sendBeacon(`${apiUrl}/api/v1/user/preferences/workspaces`, blob);
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

