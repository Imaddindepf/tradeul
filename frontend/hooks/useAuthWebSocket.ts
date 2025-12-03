'use client';

/**
 * Hook para WebSocket autenticado con Clerk JWT
 * 
 * IMPORTANTE: Este hook NO conecta hasta tener el token de Clerk.
 * Esto evita que el SharedWorker se conecte sin token y sea rechazado.
 */

import { useEffect, useRef, useState, useMemo } from 'react';
import { useAuth } from '@clerk/nextjs';
import { useRxWebSocket, UseRxWebSocketReturn } from './useRxWebSocket';

interface UseAuthWebSocketOptions {
    debug?: boolean;
    refreshInterval?: number; // ms, default 50000 (50s, antes de que expire el token de 60s)
}

/**
 * Construir URL con token
 */
function buildAuthUrl(baseUrl: string, token: string): string {
    try {
        // Manejar URLs websocket
        const wsProtocol = baseUrl.startsWith('wss://') ? 'wss:' : 'ws:';
        const httpUrl = baseUrl.replace(/^wss?:\/\//, 'http://');
        const url = new URL(httpUrl);
        url.searchParams.set('token', token);
        return url.toString().replace(/^http:\/\//, wsProtocol + '//');
    } catch {
        // Fallback: añadir query param manualmente
        const separator = baseUrl.includes('?') ? '&' : '?';
        return `${baseUrl}${separator}token=${token}`;
    }
}

/**
 * Hook para WebSocket con autenticación Clerk
 * 
 * NO conecta hasta tener el token (evita conexiones rechazadas)
 */
export function useAuthWebSocket(
    baseUrl: string,
    options: UseAuthWebSocketOptions = {}
): UseRxWebSocketReturn & { isAuthenticated: boolean } {
    const { debug = false, refreshInterval = 50000 } = options;
    const { getToken, isSignedIn, isLoaded } = useAuth();

    const [wsUrl, setWsUrl] = useState<string | null>(null); // null = esperando token
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const tokenRef = useRef<string | null>(null);
    const refreshTimerRef = useRef<NodeJS.Timeout | null>(null);
    const hasInitializedRef = useRef(false);
    const previousUrlRef = useRef<string | null>(null);

    // Obtener token ANTES de conectar
    useEffect(() => {
        if (!isLoaded) return;
        if (hasInitializedRef.current) return;

        async function initAuth() {
            hasInitializedRef.current = true;

            if (!isSignedIn) {
                // No autenticado - conectar sin token (si auth no está habilitada en backend)
                if (debug) console.log('🔐 [AuthWS] Not signed in, connecting without auth');
                setWsUrl(baseUrl);
                setIsAuthenticated(false);
                return;
            }

            try {
                const token = await getToken();
                if (token) {
                    tokenRef.current = token;
                    const urlWithToken = buildAuthUrl(baseUrl, token);

                    if (debug) console.log('🔐 [AuthWS] Got token, URL:', urlWithToken.substring(0, 80) + '...');

                    setWsUrl(urlWithToken);
                    setIsAuthenticated(true);
                } else {
                    // No token disponible - conectar sin auth
                    setWsUrl(baseUrl);
                    setIsAuthenticated(false);
                }
            } catch (error) {
                console.error('🔐 [AuthWS] Failed to get token:', error);
                // Fallback: conectar sin auth
                setWsUrl(baseUrl);
                setIsAuthenticated(false);
            }
        }

        initAuth();
    }, [baseUrl, getToken, isSignedIn, isLoaded, debug]);

    // Conectar SOLO cuando tengamos la URL (con o sin token)
    // Si wsUrl es null, esperamos a tener el token antes de conectar
    // Pasamos la URL solo cuando esté lista
    const ws = useRxWebSocket(wsUrl || baseUrl, debug);

    // Cuando tengamos la URL con token, forzar reconexión si cambió
    useEffect(() => {
        if (wsUrl && wsUrl !== previousUrlRef.current) {
            previousUrlRef.current = wsUrl;
            if (debug) console.log('🔐 [AuthWS] URL with token ready, reconnecting...');
            // Forzar reconexión con la nueva URL (el singleton detectará el cambio)
            if (ws.reconnect) {
                setTimeout(() => {
                    ws.reconnect();
                }, 100);
            }
        }
    }, [wsUrl, ws.reconnect, debug]);

    // Refresh del token periódicamente (Clerk tokens expiran en 60s)
    useEffect(() => {
        if (!isSignedIn || !ws.isConnected || !isAuthenticated) return;

        async function refreshToken() {
            try {
                const newToken = await getToken();
                if (newToken && newToken !== tokenRef.current) {
                    tokenRef.current = newToken;
                    const newUrl = buildAuthUrl(baseUrl, newToken);

                    // 🔐 Actualizar token en SharedWorker + enviar refresh al servidor
                    ws.updateToken(newUrl, newToken);

                    if (debug) console.log('🔐 [AuthWS] Token refreshed (URL + server)');
                }
            } catch (error) {
                console.error('🔐 [AuthWS] Token refresh failed:', error);
            }
        }

        // Refresh cada 50 segundos (antes de que expire el token de 60s)
        refreshTimerRef.current = setInterval(refreshToken, refreshInterval);

        return () => {
            if (refreshTimerRef.current) {
                clearInterval(refreshTimerRef.current);
            }
        };
    }, [isSignedIn, ws.isConnected, ws.updateToken, getToken, refreshInterval, debug, isAuthenticated, baseUrl]);

    return useMemo(() => ({
        ...ws,
        isAuthenticated,
    }), [ws, isAuthenticated]);
}

export default useAuthWebSocket;
