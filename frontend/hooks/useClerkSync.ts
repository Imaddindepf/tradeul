'use client';

import { useCallback, useEffect, useRef } from 'react';
import { useAuth, useUser } from '@clerk/nextjs';
import { useUserPreferencesStore, UserPreferences, ColorPreferences, FontFamily } from '@/stores/useUserPreferencesStore';

/**
 * Helper para hacer fetch autenticado con JWT de Clerk
 */
async function authFetch(
    url: string,
    getToken: () => Promise<string | null>,
    options: RequestInit = {}
): Promise<Response> {
    const token = await getToken();

    const headers: HeadersInit = {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
    };

    // Añadir Authorization header si tenemos token
    if (token) {
        (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
    }

    return fetch(url, {
        ...options,
        headers,
    });
}

// Tipos para la API
interface WindowLayoutAPI {
    id: string;
    type: string;
    title: string;
    position: { x: number; y: number };
    size: { width: number; height: number };
    isMinimized: boolean;
    zIndex: number;
}

interface UserPreferencesAPI {
    userId: string;
    colors: ColorPreferences;
    theme: { font: FontFamily; colorScheme: 'light' | 'dark' | 'system'; newsSquawkEnabled?: boolean };
    windowLayouts: WindowLayoutAPI[];
    savedFilters: Record<string, any>;
    columnVisibility: Record<string, Record<string, boolean>>;
    columnOrder: Record<string, string[]>;
    updatedAt: string;
}

// API Gateway URL (usa la misma variable que el resto del frontend)
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Hook para sincronizar preferencias de usuario con el backend (PostgreSQL)
 * 
 * Flujo:
 * 1. Al hacer login → cargar preferencias del servidor
 * 2. Al cambiar preferencias locales → sincronizar con servidor (debounced)
 * 3. Al hacer logout → limpiar estado local
 */
export function useClerkSync() {
    const { isSignedIn, userId, getToken } = useAuth();
    const { user } = useUser();

    // Estado del store
    const colors = useUserPreferencesStore((s) => s.colors);
    const theme = useUserPreferencesStore((s) => s.theme);
    const windowLayouts = useUserPreferencesStore((s) => s.windowLayouts);
    const savedFilters = useUserPreferencesStore((s) => s.savedFilters);
    const columnVisibility = useUserPreferencesStore((s) => s.columnVisibility);
    const columnOrder = useUserPreferencesStore((s) => s.columnOrder);

    // Acciones del store
    const setTickUpColor = useUserPreferencesStore((s) => s.setTickUpColor);
    const setTickDownColor = useUserPreferencesStore((s) => s.setTickDownColor);
    const setBackgroundColor = useUserPreferencesStore((s) => s.setBackgroundColor);
    const setPrimaryColor = useUserPreferencesStore((s) => s.setPrimaryColor);
    const setFont = useUserPreferencesStore((s) => s.setFont);
    const setColorScheme = useUserPreferencesStore((s) => s.setColorScheme);
    const saveWindowLayouts = useUserPreferencesStore((s) => s.saveWindowLayouts);

    // Refs para debounce y tracking
    const syncTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const lastSyncRef = useRef<string>('');
    const isLoadingRef = useRef(false);
    const hasLoadedRef = useRef(false);

    /**
     * Cargar preferencias del servidor
     */
    const loadFromServer = useCallback(async () => {
        if (!userId || isLoadingRef.current) return;

        isLoadingRef.current = true;

        try {
            // Usar JWT en lugar de X-User-ID (más seguro)
            const response = await authFetch(
                `${API_BASE_URL}/api/v1/user/preferences`,
                getToken,
                { method: 'GET' }
            );

            if (response.ok) {
                const data: UserPreferencesAPI = await response.json();

                // Aplicar preferencias del servidor al store local
                if (data.colors) {
                    setTickUpColor(data.colors.tickUp);
                    setTickDownColor(data.colors.tickDown);
                    setBackgroundColor(data.colors.background);
                    setPrimaryColor(data.colors.primary);
                }

                if (data.theme) {
                    setFont(data.theme.font);
                    setColorScheme(data.theme.colorScheme);
                    if (data.theme.newsSquawkEnabled !== undefined) {
                        useUserPreferencesStore.getState().setNewsSquawkEnabled(data.theme.newsSquawkEnabled);
                    }
                }

                if (data.windowLayouts && data.windowLayouts.length > 0) {
                    // Convertir formato API a formato del store
                    const layouts = data.windowLayouts.map((w) => ({
                        id: w.id,
                        type: w.type,
                        title: w.title,
                        position: w.position,
                        size: w.size,
                        isMinimized: w.isMinimized,
                        zIndex: w.zIndex,
                    }));
                    saveWindowLayouts(layouts);
                }

                // Guardar timestamp de última sincronización
                lastSyncRef.current = data.updatedAt;
                hasLoadedRef.current = true;

                // console.log('[ClerkSync] Preferencias cargadas del servidor');
            }
        } catch (error) {
            console.error('[ClerkSync] Error cargando preferencias:', error);
        } finally {
            isLoadingRef.current = false;
        }
    }, [userId, getToken, setTickUpColor, setTickDownColor, setBackgroundColor, setPrimaryColor, setFont, setColorScheme, saveWindowLayouts]);

    /**
     * Guardar preferencias en el servidor
     */
    const saveToServer = useCallback(async () => {
        if (!userId) return;

        try {
            // Preparar datos para la API
            const payload = {
                colors: {
                    tickUp: colors.tickUp,
                    tickDown: colors.tickDown,
                    background: colors.background,
                    primary: colors.primary,
                },
                theme: {
                    font: theme.font,
                    colorScheme: theme.colorScheme,
                    newsSquawkEnabled: theme.newsSquawkEnabled ?? false,
                },
                windowLayouts: windowLayouts.map((w) => ({
                    id: w.id,
                    type: w.type,
                    title: w.title,
                    position: w.position,
                    size: w.size,
                    isMinimized: w.isMinimized,
                    zIndex: w.zIndex,
                })),
                savedFilters,
                columnVisibility,
                columnOrder,
            };

            // Usar JWT en lugar de X-User-ID (más seguro)
            const response = await authFetch(
                `${API_BASE_URL}/api/v1/user/preferences`,
                getToken,
                {
                    method: 'PUT',
                    body: JSON.stringify(payload),
                }
            );

            if (response.ok) {
                const result = await response.json();
                lastSyncRef.current = result.updatedAt;
                // console.log('[ClerkSync] Preferencias guardadas en servidor');
            }
        } catch (error) {
            console.error('[ClerkSync] Error guardando preferencias:', error);
        }
    }, [userId, getToken, colors, theme, windowLayouts, savedFilters, columnVisibility, columnOrder]);

    /**
     * Sincronización debounced (evita muchas llamadas al servidor)
     */
    const debouncedSync = useCallback(() => {
        if (!isSignedIn || !hasLoadedRef.current) return;

        // Cancelar timeout anterior
        if (syncTimeoutRef.current) {
            clearTimeout(syncTimeoutRef.current);
        }

        // Nuevo timeout de 2 segundos
        syncTimeoutRef.current = setTimeout(() => {
            saveToServer();
        }, 2000);
    }, [isSignedIn, saveToServer]);

    // Efecto: Cargar preferencias al hacer login
    useEffect(() => {
        if (isSignedIn && userId && !hasLoadedRef.current) {
            loadFromServer();
        }
    }, [isSignedIn, userId, loadFromServer]);

    // Efecto: Sincronizar cambios con el servidor
    useEffect(() => {
        if (isSignedIn && hasLoadedRef.current) {
            debouncedSync();
        }

        return () => {
            if (syncTimeoutRef.current) {
                clearTimeout(syncTimeoutRef.current);
            }
        };
    }, [isSignedIn, colors, theme, windowLayouts, savedFilters, columnVisibility, columnOrder, debouncedSync]);

    // Efecto: Limpiar al desloguearse
    useEffect(() => {
        if (!isSignedIn) {
            hasLoadedRef.current = false;
            lastSyncRef.current = '';
        }
    }, [isSignedIn]);

    return {
        isSignedIn,
        userId,
        userName: user?.firstName || user?.username || 'Usuario',
        loadFromServer,
        saveToServer,
        lastSync: lastSyncRef.current,
        isLoading: isLoadingRef.current,
    };
}

/**
 * Hook simplificado para solo guardar el layout
 */
export function useSaveLayoutToCloud() {
    const { isSignedIn, userId, getToken } = useAuth();
    const windowLayouts = useUserPreferencesStore((s) => s.windowLayouts);

    const saveLayout = useCallback(async () => {
        if (!isSignedIn || !userId) {
            console.warn('[ClerkSync] Usuario no autenticado, guardando solo en local');
            return false;
        }

        try {
            const layouts = windowLayouts.map((w) => ({
                id: w.id,
                type: w.type,
                title: w.title,
                position: w.position,
                size: w.size,
                isMinimized: w.isMinimized,
                zIndex: w.zIndex,
            }));

            // Usar JWT en lugar de X-User-ID (más seguro)
            const response = await authFetch(
                `${API_BASE_URL}/api/v1/user/preferences/layout`,
                getToken,
                {
                    method: 'PATCH',
                    body: JSON.stringify(layouts),
                }
            );

            return response.ok;
        } catch (error) {
            console.error('[ClerkSync] Error guardando layout:', error);
            return false;
        }
    }, [isSignedIn, userId, getToken, windowLayouts]);

    return { saveLayout, isSignedIn };
}

