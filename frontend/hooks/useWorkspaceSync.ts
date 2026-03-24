'use client';

/**
 * useWorkspaceSync - Unified sync hook for all user preferences
 *
 * Architecture: each browser tab is independent.
 * - On mount: load from backend (source of truth)
 * - On preference change: debounced sync to backend
 * - On tab close: sendBeacon to backend with pre-cached token
 * - No cross-tab communication (no BroadcastChannel, no shared localStorage sync)
 */

import { useEffect, useRef, useCallback } from 'react';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { useAuth } from '@clerk/nextjs';

const PREFS_SYNC_DEBOUNCE_MS = 3000;

interface UseWorkspaceSyncOptions {
  enableInitialLoad?: boolean;
}

const DEFAULT_OPTIONS: UseWorkspaceSyncOptions = {
  enableInitialLoad: true,
};

export function useWorkspaceSync(options: UseWorkspaceSyncOptions = DEFAULT_OPTIONS) {
  const { isSignedIn, isLoaded, getToken } = useAuth();
  const loadFromBackend = useUserPreferencesStore((s) => s.loadFromBackend);
  const syncWorkspacesToBackend = useUserPreferencesStore((s) => s.syncWorkspacesToBackend);
  const lastSyncedAt = useUserPreferencesStore((s) => s.lastSyncedAt);

  const colors = useUserPreferencesStore((s) => s.colors);
  const theme = useUserPreferencesStore((s) => s.theme);
  const columnVisibility = useUserPreferencesStore((s) => s.columnVisibility);
  const columnOrder = useUserPreferencesStore((s) => s.columnOrder);

  const hasLoadedRef = useRef(false);
  const cachedTokenRef = useRef<string | null>(null);
  const prefsSyncTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isFirstPrefsRenderRef = useRef(true);
  const isLoadingRef = useRef(false);

  const refreshToken = useCallback(async () => {
    if (!getToken) return;
    try {
      cachedTokenRef.current = await getToken();
    } catch { /* token refresh failed, keep old */ }
  }, [getToken]);

  useEffect(() => {
    if (!isSignedIn) return;
    refreshToken();
    const interval = setInterval(refreshToken, 45_000);
    return () => clearInterval(interval);
  }, [isSignedIn, refreshToken]);

  useEffect(() => {
    if (
      options.enableInitialLoad &&
      isLoaded &&
      isSignedIn &&
      !hasLoadedRef.current
    ) {
      hasLoadedRef.current = true;
      isLoadingRef.current = true;
      loadFromBackend(getToken).finally(() => {
        isLoadingRef.current = false;
      });
    }
  }, [isLoaded, isSignedIn, options.enableInitialLoad, loadFromBackend, getToken]);

  useEffect(() => {
    if (isFirstPrefsRenderRef.current) {
      isFirstPrefsRenderRef.current = false;
      return;
    }
    if (!isSignedIn || !hasLoadedRef.current) return;
    if (isLoadingRef.current) return;

    if (prefsSyncTimeoutRef.current) {
      clearTimeout(prefsSyncTimeoutRef.current);
    }
    prefsSyncTimeoutRef.current = setTimeout(() => {
      if (isLoadingRef.current) return;
      syncWorkspacesToBackend(getToken);
    }, PREFS_SYNC_DEBOUNCE_MS);

    return () => {
      if (prefsSyncTimeoutRef.current) {
        clearTimeout(prefsSyncTimeoutRef.current);
      }
    };
  }, [colors, theme, columnVisibility, columnOrder, isSignedIn, syncWorkspacesToBackend, getToken]);

  useEffect(() => {
    const handleBeforeUnload = () => {
      if (!isSignedIn || !navigator.sendBeacon) return;

      const state = useUserPreferencesStore.getState();
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const payload = JSON.stringify({
        workspaces: state.workspaces,
        activeWorkspaceId: state.activeWorkspaceId,
        colors: state.colors,
        theme: state.theme,
        columnVisibility: state.columnVisibility,
        columnOrder: state.columnOrder,
        _token: cachedTokenRef.current,
      });
      const blob = new Blob([payload], { type: 'application/json' });
      navigator.sendBeacon(`${apiUrl}/api/v1/user/preferences/workspaces`, blob);
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isSignedIn]);

  useEffect(() => {
    return () => {
      if (prefsSyncTimeoutRef.current) clearTimeout(prefsSyncTimeoutRef.current);
    };
  }, []);

  return {
    lastSyncedAt,
    isAuthenticated: isSignedIn,
    forceSync: () => syncWorkspacesToBackend(getToken),
    forceLoad: () => loadFromBackend(getToken),
    getToken,
  };
}

export default useWorkspaceSync;
