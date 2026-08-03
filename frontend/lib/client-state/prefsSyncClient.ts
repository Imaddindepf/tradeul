'use client';

/**
 * prefsSyncClient — el ÚNICO camino de sincronización de preferencias con el
 * backend (PR1 del plan DISENO_SYNC_MULTITAB_IMPL.md).
 *
 * - dirty-tracking por dominio: cada PATCH lleva SOLO lo que cambió esta
 *   pestaña (con el flag de compat activado, añade workspaces/activeWorkspace
 *   hasta que el api_gateway con payload parcial esté desplegado).
 * - un solo debounce por pestaña (antes había dos de 3 s en hooks distintos).
 * - beacon SOLO si hay cambios pendientes, en visibilitychange/pagehide
 *   (antes: beforeunload incondicional con el estado completo en cada F5).
 * - la red vive aquí, no en el store.
 */

import { useUserPreferencesStore, Workspace, WindowLayout } from '@/stores/useUserPreferencesStore';

export type PrefsDomain = 'workspaces' | 'theme' | 'colors' | 'columns' | 'activeWorkspace';
export type FlushReason = 'debounce' | 'hide' | 'manual';

const DEBOUNCE_MS = 3000;
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const ENDPOINT = `${API_URL}/api/v1/user/preferences/workspaces`;

/**
 * Compat con el api_gateway anterior a PR1: aquel PATCH trataba un body sin
 * `workspaces` como lista vacía (los BORRABA). El gateway con COALESCE por
 * campo se desplegó el 2026-08-03 (verificado: PATCH {theme} conserva los
 * workspaces), así que los PATCH son parciales. Si hubiera que volver a una
 * imagen anterior del api_gateway, poner a true ANTES.
 */
const LEGACY_BACKEND_COMPAT = false;

let getTokenRef: (() => Promise<string | null>) | null = null;
let cachedToken: string | null = null;
let debounceTimer: ReturnType<typeof setTimeout> | null = null;
let flushing = false;
let remoteApplyDepth = 0;

const dirty = new Set<PrefsDomain>();

// ── Auth wiring (lo llama ClientStateProvider) ──────────────────────────────

export function configureAuth(getToken: () => Promise<string | null>): void {
  getTokenRef = getToken;
}

export function cacheToken(token: string | null): void {
  cachedToken = token;
}

// ── Guard para aplicar estado remoto sin auto-marcarse dirty ────────────────

export function beginRemoteApply(): void {
  remoteApplyDepth += 1;
}

export function endRemoteApply(): void {
  remoteApplyDepth = Math.max(0, remoteApplyDepth - 1);
}

export function isRemoteApply(): boolean {
  return remoteApplyDepth > 0;
}

// ── Dirty tracking ──────────────────────────────────────────────────────────

export function markDirty(domain: PrefsDomain): void {
  // Read-before-write: nunca escribir al backend antes de haberlo leído; un
  // navegador frío con localStorage viejo/vacío pisaría el layout real.
  if (!useUserPreferencesStore.getState().backendLoadComplete) return;
  dirty.add(domain);
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    void flush('debounce');
  }, DEBOUNCE_MS);
}

export function dirtySize(): number {
  return dirty.size;
}

function buildBody(domains: ReadonlySet<PrefsDomain>): Record<string, unknown> {
  const s = useUserPreferencesStore.getState();
  const body: Record<string, unknown> = {};
  if (domains.has('workspaces') || LEGACY_BACKEND_COMPAT) body.workspaces = s.workspaces;
  if (domains.has('activeWorkspace') || LEGACY_BACKEND_COMPAT) body.activeWorkspaceId = s.activeWorkspaceId;
  if (domains.has('theme')) body.theme = s.theme;
  if (domains.has('colors')) body.colors = s.colors;
  if (domains.has('columns')) {
    body.columnVisibility = s.columnVisibility;
    body.columnOrder = s.columnOrder;
  }
  return body;
}

// ── Escritura ───────────────────────────────────────────────────────────────

export async function flush(reason: FlushReason): Promise<boolean> {
  const store = useUserPreferencesStore;
  if (flushing) return false;
  if (!store.getState().backendLoadComplete) return false;
  if (dirty.size === 0) return true;

  if (debounceTimer) {
    clearTimeout(debounceTimer);
    debounceTimer = null;
  }

  const sending = new Set(dirty);
  flushing = true;
  store.setState({ isSyncing: true });
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (getTokenRef) {
      const token = await getTokenRef();
      if (token) {
        cachedToken = token;
        headers['Authorization'] = `Bearer ${token}`;
      }
    }
    const response = await fetch(ENDPOINT, {
      method: 'PATCH',
      headers,
      credentials: 'include',
      body: JSON.stringify(buildBody(sending)),
    });
    if (response.ok) {
      sending.forEach((d) => dirty.delete(d));
      store.setState({ lastSyncedAt: Date.now() });
      return true;
    }
    return false;
  } catch (error) {
    console.error(`[PrefsSync] flush(${reason}) failed:`, error);
    return false; // los dominios siguen dirty; reintenta el próximo debounce/flush
  } finally {
    flushing = false;
    store.setState({ isSyncing: false });
  }
}

/** Beacon al ocultar/cerrar la pestaña — SOLO si hay cambios sin sincronizar. */
export function flushBeacon(): void {
  if (dirty.size === 0) return;
  if (!useUserPreferencesStore.getState().backendLoadComplete) return;
  if (typeof navigator === 'undefined' || !navigator.sendBeacon) return;

  const body = buildBody(dirty);
  body['_token'] = cachedToken; // auth de beacon soportada por el endpoint
  const blob = new Blob([JSON.stringify(body)], { type: 'application/json' });
  if (navigator.sendBeacon(ENDPOINT, blob)) {
    dirty.clear();
  }
}

// ── Carga inicial (migrada de useUserPreferencesStore.loadFromBackend) ──────

export async function initialLoad(): Promise<boolean> {
  const store = useUserPreferencesStore;
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (getTokenRef) {
      const token = await getTokenRef();
      if (token) {
        cachedToken = token;
        headers['Authorization'] = `Bearer ${token}`;
      }
    }

    const response = await fetch(`${API_URL}/api/v1/user/preferences`, {
      method: 'GET',
      headers,
      credentials: 'include',
      // Safari cachea GETs sin cache headers de forma agresiva; una respuesta
      // vieja aquí resucitaría un layout antiguo y lo re-sincronizaría.
      cache: 'no-store',
    });

    if (!response.ok) return false;

    // Respuesta OK (aunque sean defaults de usuario nuevo) = "conocemos el
    // estado del server"; desde aquí es seguro sincronizar hacia fuera.
    store.setState({ backendLoadComplete: true });

    const data = await response.json();
    if (!data.workspaces || data.workspaces.length === 0) return false;

    beginRemoteApply();
    try {
      const local = store.getState();
      const remoteWorkspaces = data.workspaces as Workspace[];
      const legacyWindowLayouts = Array.isArray(data.windowLayouts)
        ? (data.windowLayouts as WindowLayout[])
        : [];

      const hasWorkspaceLayouts = remoteWorkspaces.some(
        (w) => Array.isArray(w.windowLayouts) && w.windowLayouts.length > 0
      );

      // Backward-compat: backend solo con windowLayouts legacy → hidratar Main.
      let hydratedWorkspaces = remoteWorkspaces;
      if (!hasWorkspaceLayouts && legacyWindowLayouts.length > 0) {
        const mainWorkspace = remoteWorkspaces.find((w) => w.id === 'main');
        if (mainWorkspace) {
          hydratedWorkspaces = remoteWorkspaces.map((w) =>
            w.id === 'main' ? { ...w, windowLayouts: legacyWindowLayouts } : w
          );
        } else {
          hydratedWorkspaces = [
            {
              id: 'main',
              name: 'Main',
              isMain: true,
              createdAt: Date.now(),
              windowLayouts: legacyWindowLayouts,
            },
            ...remoteWorkspaces,
          ];
        }
      }

      // Usuarios nuevos reciben un Main sintético con createdAt=0; cualquier
      // workspace real guardado tiene createdAt > 0 (ver comentario original).
      const serverHasRealWorkspaces = remoteWorkspaces.some((w) => (w.createdAt ?? 0) > 0);

      const remoteActiveId = data.activeWorkspaceId || 'main';
      const validActiveId = hydratedWorkspaces.some((w) => w.id === local.activeWorkspaceId)
        ? local.activeWorkspaceId
        : hydratedWorkspaces.some((w) => w.id === remoteActiveId)
          ? remoteActiveId
          : (hydratedWorkspaces[0]?.id || 'main');

      store.setState({
        workspaces: hydratedWorkspaces,
        activeWorkspaceId: validActiveId,
        colors: data.colors || local.colors,
        theme: { ...local.theme, ...(data.theme || {}) },
        columnVisibility: data.columnVisibility || {},
        columnOrder: data.columnOrder || {},
        layoutInitialized:
          hasWorkspaceLayouts || legacyWindowLayouts.length > 0 || serverHasRealWorkspaces
            ? true
            : local.layoutInitialized,
        workspacesModifiedAt: data.updatedAt ? new Date(data.updatedAt).getTime() : Date.now(),
        lastSyncedAt: Date.now(),
      });
    } finally {
      endRemoteApply();
    }
    return true;
  } catch (error) {
    console.error('[PrefsSync] initialLoad failed:', error);
    return false;
  }
}
