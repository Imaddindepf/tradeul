'use client';

import { useCallback } from 'react';
import { useAuth } from '@clerk/nextjs';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Hook para hacer requests HTTP autenticados con JWT de Clerk.
 * 
 * Uso:
 * ```tsx
 * const { authFetch, isSignedIn } = useAuthFetch();
 * 
 * // GET request
 * const data = await authFetch('/api/v1/ticker/AAPL');
 * 
 * // POST request
 * const result = await authFetch('/api/v1/something', {
 *   method: 'POST',
 *   body: JSON.stringify({ ... })
 * });
 * ```
 */
export function useAuthFetch() {
    const { isSignedIn, getToken } = useAuth();

    /**
     * Fetch autenticado - añade Authorization: Bearer <jwt> automáticamente.
     * Si recibe 401, reintenta UNA vez con skipCache: true para forzar token fresco.
     */
    const authFetch = useCallback(async (
        endpoint: string,
        options: RequestInit = {}
    ): Promise<Response> => {
        // Construir URL completa si es relativa
        const url = endpoint.startsWith('http') 
            ? endpoint 
            : `${API_BASE_URL}${endpoint}`;

        const doFetch = async (skipCache: boolean): Promise<Response> => {
            const token = await getToken({ skipCache });
            
            const headers: HeadersInit = {
                'Content-Type': 'application/json',
                ...(options.headers || {}),
            };
            
            if (token) {
                (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
            }
            
            return fetch(url, {
                ...options,
                headers,
            });
        };

        // First attempt with cached token
        const response = await doFetch(false);
        
        // If 401, retry ONCE with fresh token (skipCache: true)
        if (response.status === 401) {
            console.warn('🔐 [authFetch] 401 received, retrying with fresh token...');
            return doFetch(true);
        }
        
        return response;
    }, [getToken]);

    /**
     * Fetch autenticado que parsea JSON automáticamente
     */
    const authFetchJson = useCallback(async <T = any>(
        endpoint: string,
        options: RequestInit = {}
    ): Promise<T> => {
        const response = await authFetch(endpoint, options);
        
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        return response.json();
    }, [authFetch]);

    return {
        authFetch,
        authFetchJson,
        isSignedIn,
        apiBaseUrl: API_BASE_URL,
    };
}

/**
 * Versión standalone para uso fuera de componentes React
 * (ej: en funciones de utilidad)
 * 
 * NOTA: Requiere pasar getToken manualmente
 */
export async function authFetchStandalone(
    url: string,
    getToken: (opts?: { skipCache?: boolean }) => Promise<string | null>,
    options: RequestInit = {}
): Promise<Response> {
    const doFetch = async (skipCache: boolean): Promise<Response> => {
        const token = await getToken({ skipCache });
        
        const headers: HeadersInit = {
            'Content-Type': 'application/json',
            ...(options.headers || {}),
        };
        
        if (token) {
            (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
        }
        
        return fetch(url, {
            ...options,
            headers,
        });
    };

    const response = await doFetch(false);
    
    // Retry once with fresh token on 401
    if (response.status === 401) {
        console.warn('🔐 [authFetchStandalone] 401 received, retrying with fresh token...');
        return doFetch(true);
    }
    
    return response;
}

