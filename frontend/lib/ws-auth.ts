/**
 * WebSocket auth helpers (client-safe).
 *
 * Centralizes the URL-building logic used by every authenticated WebSocket
 * client (scanner, chat, etc.). Previously this lived duplicated in
 * `contexts/AuthWebSocketContext.tsx` and the now-deleted
 * `hooks/useAuthWebSocket.ts`; keeping a single source of truth avoids the
 * two implementations drifting apart.
 */

/**
 * Append a Clerk JWT to a websocket URL as the `token` query parameter.
 * Preserves any existing query string and the original ws/wss scheme.
 */
export function buildWsAuthUrl(baseUrl: string, token: string): string {
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
