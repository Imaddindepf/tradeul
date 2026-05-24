/**
 * Authenticated API Client for Tradeul
 * 
 * Provides a centralized way to make authenticated API calls using Clerk tokens.
 * Use this for all backend API calls that require authentication.
 */

// API URLs from environment
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
export const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000';

/**
 * Type for the getToken function from Clerk
 */
type GetTokenFn = () => Promise<string | null>;

/**
 * Make an authenticated API request
 * 
 * @param url - Full URL or path (if path, API_BASE_URL is prepended)
 * @param options - Fetch options
 * @param getToken - Clerk's getToken function
 * @returns Response object
 * @throws Error if no token is available
 */
export async function authenticatedFetch(
    url: string,
    options: RequestInit,
    getToken: GetTokenFn
): Promise<Response> {
    const token = await getToken();
    
    if (!token) {
        throw new Error('No authentication token available');
    }
    
    const fullUrl = url.startsWith('http') ? url : `${API_BASE_URL}${url}`;
    
    return fetch(fullUrl, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
            'Authorization': `Bearer ${token}`,
        },
    });
}

/**
 * Create a WebSocket connection with authentication
 * 
 * @param path - WebSocket path (e.g., '/ws/scanner')
 * @param token - JWT token from Clerk
 * @returns WebSocket instance
 */
export function createAuthenticatedWebSocket(
    path: string,
    token: string
): WebSocket {
    const wsUrl = new URL(path, WS_BASE_URL);
    wsUrl.searchParams.set('token', token);
    
    return new WebSocket(wsUrl.toString());
}

/**
 * API client class for more complex use cases
 */
export class ApiClient {
    private getToken: GetTokenFn;
    
    constructor(getToken: GetTokenFn) {
        this.getToken = getToken;
    }
    
    async get<T>(url: string): Promise<T> {
        const response = await authenticatedFetch(url, { method: 'GET' }, this.getToken);
        
        if (!response.ok) {
            throw new ApiError(response.status, await response.text());
        }
        
        return response.json();
    }
    
    async post<T>(url: string, body: unknown): Promise<T> {
        const response = await authenticatedFetch(
            url,
            {
                method: 'POST',
                body: JSON.stringify(body),
            },
            this.getToken
        );
        
        if (!response.ok) {
            throw new ApiError(response.status, await response.text());
        }
        
        return response.json();
    }
    
    async put<T>(url: string, body: unknown): Promise<T> {
        const response = await authenticatedFetch(
            url,
            {
                method: 'PUT',
                body: JSON.stringify(body),
            },
            this.getToken
        );
        
        if (!response.ok) {
            throw new ApiError(response.status, await response.text());
        }
        
        return response.json();
    }
    
    async patch<T>(url: string, body: unknown): Promise<T> {
        const response = await authenticatedFetch(
            url,
            {
                method: 'PATCH',
                body: JSON.stringify(body),
            },
            this.getToken
        );
        
        if (!response.ok) {
            throw new ApiError(response.status, await response.text());
        }
        
        return response.json();
    }
    
    async delete(url: string): Promise<void> {
        const response = await authenticatedFetch(
            url,
            { method: 'DELETE' },
            this.getToken
        );
        
        if (!response.ok) {
            throw new ApiError(response.status, await response.text());
        }
    }
}

/**
 * Custom error class for API errors
 */
export class ApiError extends Error {
    status: number;
    
    constructor(status: number, message: string) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
    }
    
    get isUnauthorized(): boolean {
        return this.status === 401;
    }
    
    get isForbidden(): boolean {
        return this.status === 403;
    }
    
    get isNotFound(): boolean {
        return this.status === 404;
    }
}

/**
 * Hook helper to create an API client from Clerk's useAuth
 * 
 * Usage:
 * const { getToken } = useAuth();
 * const api = useApiClient(getToken);
 * const data = await api.get('/api/v1/user/preferences');
 */
export function createApiClient(getToken: GetTokenFn): ApiClient {
    return new ApiClient(getToken);
}


