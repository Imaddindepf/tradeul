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
  const workspaces = useUserPreferencesStore((s) => s.workspaces);
  const activeWorkspaceId = useUserPreferencesStore((s) => s.activeWorkspaceId);
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

      // Retry with backoff: a single failed GET would leave the session
      // without server state forever — layout restore falls back to stale
      // localStorage and outbound sync stays blocked for the whole session.
      let cancelled = false;
      let attempt = 0;
      const tryLoad = () => {
        if (cancelled) return;
        isLoadingRef.current = true;
        loadFromBackend(getToken)
          .then(() => {
            const done = useUserPreferencesStore.getState().backendLoadComplete;
            if (!done && !cancelled && attempt < 5) {
              attempt += 1;
              setTimeout(tryLoad, Math.min(2000 * attempt, 8000));
            }
          })
          .finally(() => {
            isLoadingRef.current = false;
          });
      };
      tryLoad();
      return () => { cancelled = true; };
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
      // Never write to the backend before we've read it: a cold browser with
      // stale/empty localStorage would overwrite the user's real layout.
      if (!useUserPreferencesStore.getState().backendLoadComplete) return;
      syncWorkspacesToBackend(getToken);
    }, PREFS_SYNC_DEBOUNCE_MS);

    return () => {
      if (prefsSyncTimeoutRef.current) {
        clearTimeout(prefsSyncTimeoutRef.current);
      }
    };
  }, [
    colors,
    theme,
    workspaces,
    activeWorkspaceId,
    columnVisibility,
    columnOrder,
    isSignedIn,
    syncWorkspacesToBackend,
    getToken,
  ]);

  useEffect(() => {
    const handleBeforeUnload = () => {
      if (!isSignedIn || !navigator.sendBeacon) return;

      const state = useUserPreferencesStore.getState();
      // Same guard as the debounced sync: if this session never loaded the
      // server state, beaconing the (possibly default) local store on unload
      // would wipe the user's real layout saved from another browser.
      if (!state.backendLoadComplete) return;
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
