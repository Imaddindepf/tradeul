'use client';

/**
 * Re-export shim for backwards compat.
 *
 * The chat WebSocket logic now lives in `ChatWebSocketContext` so the
 * connection is a singleton and shares one Clerk-authenticated socket
 * across every component (ChatContent, ChatInput, etc.). Existing imports
 * keep working because of this re-export.
 */
export { useChatWebSocket } from '@/contexts/ChatWebSocketContext';
