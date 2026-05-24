'use client';

/**
 * AuthWebSocketContext - Autenticación centralizada del WebSocket
 * 
 * ARQUITECTURA:
 * - UN solo Provider maneja la autenticación (token de Clerk)
 * - Todos los componentes usan useWebSocket() que ya está autenticado
 * - El SharedWorker mantiene UNA conexión para todas las ventanas/pestañas
 * 
 * BENEFICIOS:
 * - No hay múltiples getToken() dispersos
 * - El token se refresca en UN solo lugar
 * - Menos reconexiones, menos errores de token expirado
 */

import React, { createContext, useContext, useEffect, useRef, useState, ReactNode, useMemo } from 'react';
import { useAuth } from '@clerk/nextjs';
import { useRxWebSocket, UseRxWebSocketReturn } from '@/hooks/useRxWebSocket';

interface AuthWebSocketContextType {
    ws: UseRxWebSocketReturn;
    isAuthenticated: boolean;
    isReady: boolean; // true cuando la conexión está lista para usar
}

const AuthWebSocketContext = createContext<AuthWebSocketContextType | null>(null);

// URL base del WebSocket
const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';

// Intervalo de refresh del token (50 segundos, antes de que expire el token de 60s)
const TOKEN_REFRESH_INTERVAL = 50000;

/**
 * Construir URL con token
 */
function buildAuthUrl(baseUrl: string, token: string): string {
    try {
        const wsProtocol = baseUrl.startsWith('wss://') ? 'wss:' : 'ws:';
        const httpUrl = baseUrl.replace(/^wss?:\/\//, 'http://');
        const url = new URL(httpUrl);
        url.searchParams.set('token', token);
        return url.toString().replace(/^http:\/\//, wsProtocol + '//');
    } catch {
        const separator = baseUrl.includes('?') ? '&' : '?';
        return `${baseUrl}${separator}token=${token}`;
    }
}

interface AuthWebSocketProviderProps {
    children: ReactNode;
}

export function AuthWebSocketProvider({ children }: AuthWebSocketProviderProps) {
    const { getToken, isSignedIn, isLoaded } = useAuth();

    // wsUrl starts as `null` to prevent useRxWebSocket from triggering an
    // unauthenticated WS_BASE_URL connect during the brief window before
    // Clerk hands us a token. Once the token is fetched, initAuth() below
    // sets the full token-bearing URL.
    //
    // Without this, every remount of this provider would:
    //   1. start with wsUrl = WS_BASE_URL (no token)
    //   2. fire `manager.connect(WS_BASE_URL)`
    //   3. since the singleton has the previous URL (with token) configured,
    //      connect() would call disconnect() and reconnect with the
    //      tokenless URL → backend rejects → 2-3s offline → token refresh
    //      → reconnects.
    // The defensive guard in useRxWebSocket already handles this for
    // already-initialized singletons, but using `null` keeps the contract
    // explicit and protects the cold-start path too.
    const [wsUrl, setWsUrl] = useState<string | null>(null);
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [isReady, setIsReady] = useState(false);

    const tokenRef = useRef<string | null>(null);
    const refreshTimerRef = useRef<NodeJS.Timeout | null>(null);
    const hasInitializedRef = useRef(false);

    // WebSocket singleton (usa SharedWorker internamente).
    // Empty string when wsUrl is null → the hook's `if (!url) skip connect`
    // guard kicks in and we just subscribe to the singleton's state.
    const ws = useRxWebSocket(wsUrl ?? '');

    // =========================================================================
    // INICIALIZACIÓN: Obtener token y conectar
    // =========================================================================
    useEffect(() => {
        if (!isLoaded) return;
        if (hasInitializedRef.current) return;

        async function initAuth() {
            hasInitializedRef.current = true;

            if (!isSignedIn) {
                // Usuario no autenticado - conectar sin token
                setWsUrl(WS_BASE_URL);
                setIsAuthenticated(false);
                setIsReady(true);
                return;
            }

            try {
                // skipCache: true → token fresco garantizado en conexión inicial
                const token = await getToken({ skipCache: true });
                if (token) {
                    tokenRef.current = token;
                    const urlWithToken = buildAuthUrl(WS_BASE_URL, token);
                    setWsUrl(urlWithToken);
                    setIsAuthenticated(true);
                    setIsReady(true);
                } else {
                    setWsUrl(WS_BASE_URL);
                    setIsAuthenticated(false);
                    setIsReady(true);
                }
            } catch (error) {
                console.error('🔐 [AuthWSProvider] Failed to get token:', error);
                setWsUrl(WS_BASE_URL);
                setIsAuthenticated(false);
                setIsReady(true);
            }
        }

        initAuth();
    }, [isLoaded, isSignedIn, getToken]);

    // =========================================================================
    // RESET ON SIGN-OUT: Allow re-initialization when a new user signs in
    // Without this, hasInitializedRef stays true and the init block never
    // re-runs, leaving the WS connection with the previous user's token.
    // =========================================================================
    useEffect(() => {
        if (isLoaded && !isSignedIn) {
            hasInitializedRef.current = false;
            setIsAuthenticated(false);
            tokenRef.current = null;
        }
    }, [isLoaded, isSignedIn]);

    // =========================================================================
    // REFRESH PERIÓDICO DEL TOKEN (cada 50 segundos)
    // NO depende de ws.isConnected — debe refrescar SIEMPRE para que
    // cuando el SharedWorker pida reconectar, tenga un token fresco disponible
    // =========================================================================
    useEffect(() => {
        if (!isSignedIn || !isAuthenticated) return;

        async function refreshToken() {
            try {
                const newToken = await getToken({ skipCache: true });
                if (newToken && newToken !== tokenRef.current) {
                    tokenRef.current = newToken;
                    const newUrl = buildAuthUrl(WS_BASE_URL, newToken);

                    // Actualizar token en SharedWorker:
                    // - Si conectado: envía refresh_token al servidor
                    // - Si esperando: reconecta con token fresco
                    ws.updateToken(newUrl, newToken);
                }
            } catch (error) {
                console.error('🔐 [AuthWSProvider] Token refresh failed:', error);
            }
        }

        refreshTimerRef.current = setInterval(refreshToken, TOKEN_REFRESH_INTERVAL);

        return () => {
            if (refreshTimerRef.current) {
                clearInterval(refreshTimerRef.current);
            }
        };
    }, [isSignedIn, ws.updateToken, getToken, isAuthenticated]);

    // =========================================================================
    // ESCUCHAR SOLICITUDES DE TOKEN DEL SHAREDWORKER (para reconexiones)
    // =========================================================================
    useEffect(() => {
        if (!isSignedIn || !isAuthenticated) return;

        const subscription = ws.tokenRefreshRequest$.subscribe(async () => {
            try {
                const newToken = await getToken({ skipCache: true });
                if (newToken) {
                    tokenRef.current = newToken;
                    const newUrl = buildAuthUrl(WS_BASE_URL, newToken);
                    ws.updateToken(newUrl, newToken);
                }
            } catch (error) {
                console.error('🔐 [AuthWSProvider] Failed to get fresh token:', error);
            }
        });

        return () => subscription.unsubscribe();
    }, [isSignedIn, isAuthenticated, ws.tokenRefreshRequest$, ws.updateToken, getToken]);

    // =========================================================================
    // CONTEXT VALUE
    // =========================================================================
    const contextValue = useMemo(() => ({
        ws,
        isAuthenticated,
        isReady,
    }), [ws, isAuthenticated, isReady]);

    return (
        <AuthWebSocketContext.Provider value={contextValue}>
            {children}
        </AuthWebSocketContext.Provider>
    );
}

/**
 * Hook para usar el WebSocket ya autenticado
 * 
 * Los componentes NO deben manejar tokens - solo usan este hook
 */
export function useWebSocket(): UseRxWebSocketReturn {
    const context = useContext(AuthWebSocketContext);

    if (!context) {
        throw new Error('useWebSocket must be used within AuthWebSocketProvider');
    }

    return context.ws;
}

