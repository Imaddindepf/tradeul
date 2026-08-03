'use client';

/**
 * ClientStateProvider — la ÚNICA instancia por pestaña del ciclo de vida de
 * sincronización de preferencias (PR1 de DISENO_SYNC_MULTITAB_IMPL.md).
 *
 * Sustituye a las 4 instancias de useWorkspaceSync con efectos duplicados.
 * Responsabilidades:
 *  1. cablear auth (getToken + refresh del token cacheado para beacons)
 *  2. carga inicial del backend con retries (fuente de verdad al arrancar)
 *  3. watcher del store: cambio local por dominio → markDirty (payload parcial)
 *  4. beacon condicional en visibilitychange/pagehide (solo si hay dirty)
 */

import { useEffect, useRef, type ReactNode } from 'react';
import { useAuth } from '@clerk/nextjs';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import {
  configureAuth,
  cacheToken,
  initialLoad,
  markDirty,
  flushBeacon,
  isRemoteApply,
} from '@/lib/client-state/prefsSyncClient';

const TOKEN_REFRESH_MS = 45_000;

export function useClientStateSync(): void {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const startedLoadRef = useRef(false);

  // 1. Auth wiring + token cache para beacons
  useEffect(() => {
    configureAuth(getToken);
  }, [getToken]);

  useEffect(() => {
    if (!isSignedIn) return;
    let cancelled = false;
    const refresh = async () => {
      try {
        const token = await getToken();
        if (!cancelled) cacheToken(token);
      } catch { /* mantener el token anterior */ }
    };
    void refresh();
    const interval = setInterval(refresh, TOKEN_REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [isSignedIn, getToken]);

  // 2. Carga inicial con retries (migrado de useWorkspaceSync): un solo GET
  //    fallido no puede dejar la sesión sin estado del server para siempre.
  useEffect(() => {
    if (!isLoaded || !isSignedIn || startedLoadRef.current) return;
    startedLoadRef.current = true;

    let cancelled = false;
    let attempt = 0;
    const tryLoad = () => {
      if (cancelled) return;
      void initialLoad().then(() => {
        const done = useUserPreferencesStore.getState().backendLoadComplete;
        if (!done && !cancelled && attempt < 5) {
          attempt += 1;
          setTimeout(tryLoad, Math.min(2000 * attempt, 8000));
        }
      });
    };
    tryLoad();
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn]);

  // 3. Watcher del store → dirty por dominio. Las aplicaciones de estado
  //    remoto (initialLoad) van entre beginRemoteApply/endRemoteApply y se
  //    ignoran aquí; markDirty además descarta todo hasta backendLoadComplete.
  useEffect(() => {
    const unsubscribe = useUserPreferencesStore.subscribe((state, prev) => {
      if (isRemoteApply()) return;
      if (state.theme !== prev.theme) markDirty('theme');
      if (state.colors !== prev.colors) markDirty('colors');
      if (state.workspaces !== prev.workspaces) markDirty('workspaces');
      if (state.activeWorkspaceId !== prev.activeWorkspaceId) markDirty('activeWorkspace');
      if (state.columnVisibility !== prev.columnVisibility || state.columnOrder !== prev.columnOrder) {
        markDirty('columns');
      }
    });
    return unsubscribe;
  }, []);

  // 4. Beacon condicional: visibilitychange cubre el caso móvil/cierre real;
  //    pagehide cubre F5/navegación. Solo dispara si hay dominios dirty.
  useEffect(() => {
    if (!isSignedIn) return;
    const onHide = () => {
      if (document.visibilityState === 'hidden') flushBeacon();
    };
    const onPageHide = () => flushBeacon();
    document.addEventListener('visibilitychange', onHide);
    window.addEventListener('pagehide', onPageHide);
    return () => {
      document.removeEventListener('visibilitychange', onHide);
      window.removeEventListener('pagehide', onPageHide);
    };
  }, [isSignedIn]);
}

/** Variante componente por si se prefiere montar declarativamente. */
export function ClientStateProvider({ children }: { children?: ReactNode }) {
  useClientStateSync();
  return <>{children}</>;
}

export default ClientStateProvider;
