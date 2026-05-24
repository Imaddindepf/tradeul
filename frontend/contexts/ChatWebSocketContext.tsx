'use client';

/**
 * ChatWebSocketContext — Singleton chat WebSocket provider.
 *
 * Why this exists (it replaces the old `useChatWebSocket` hook):
 *
 *   1. The previous hook was instantiated independently in both
 *      `ChatContent` and `ChatInput`, opening *two* WebSockets per user.
 *      Doubling presence, typing indicators, server load and bandwidth.
 *
 *   2. It captured a Clerk JWT once at connect time and never refreshed
 *      it. The chat WS server only validates the token on connect, so
 *      the connection itself remains valid for its lifetime — but every
 *      reconnect (which happens often: 3s after any drop) reused the
 *      cached, possibly-expired token. We now request a fresh token on
 *      every (re)connect via `skipCache: true`, and proactively warm the
 *      Clerk token cache every 50 s so the next reconnect is instant.
 *
 *   3. Lifecycle was tied to the chat windows being mounted. Closing the
 *      chat tore down the connection and lost incoming notifications
 *      (group invites, mentions). Now the provider sits inside `AppShell`,
 *      so the chat WS is alive whenever the user is in the dashboard.
 *
 * Public API (via `useChatWebSocket()`):
 *   - `subscribe(target)` / `unsubscribe(target)` — channel/group scoping
 *   - `sendTyping(target)` — throttled typing indicator
 *   - `isConnected$` — RxJS BehaviorSubject for status UI
 *   - `reconnect()` — escape hatch for manual reconnects
 */

import React, {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    type ReactNode,
} from 'react';
import { useAuth } from '@clerk/nextjs';
import { BehaviorSubject, Subject } from 'rxjs';
import { takeUntil, throttleTime } from 'rxjs/operators';
import { useChatStore, type ChatMessage } from '@/stores/useChatStore';

// ============================================================================
// CONFIG
// ============================================================================

const CHAT_WS_URL = process.env.NEXT_PUBLIC_CHAT_WS_URL || 'wss://wschat.tradeul.com';
const RECONNECT_DELAY = 3000;
const HEARTBEAT_INTERVAL = 30000;
const TOKEN_REFRESH_INTERVAL = 50000; // Clerk JWTs expire at 60s
const TYPING_THROTTLE = 2000;

// ============================================================================
// TYPES
// ============================================================================

type ChatWSMessage =
    | { type: 'connected'; payload: { userId: string; userName: string } }
    | { type: 'new_message'; payload: ChatMessage }
    | { type: 'message_edited'; payload: { id: string; content: string; edited_at: string } }
    | { type: 'message_deleted'; payload: { id: string } }
    | { type: 'typing'; payload: { user_id: string; user_name: string; target: string } }
    | { type: 'presence'; payload: { target: string; online: string[] } }
    | { type: 'reaction_added'; payload: { message_id: string; emoji: string; user_id: string } }
    | { type: 'reaction_removed'; payload: { message_id: string; emoji: string; user_id: string } }
    | { type: 'group_invite'; payload: { group: { id: string; name: string }; inviter_id: string; inviter_name: string } }
    | { type: 'pong' };

type ChatTarget = { type: 'channel' | 'group'; id: string };

interface ChatWebSocketAPI {
    isConnected$: BehaviorSubject<boolean>;
    subscribe: (target: ChatTarget) => void;
    unsubscribe: (target: ChatTarget) => void;
    sendTyping: (target: ChatTarget) => void;
    reconnect: () => void;
}

const ChatWebSocketContext = createContext<ChatWebSocketAPI | null>(null);

// ============================================================================
// PROVIDER
// ============================================================================

export function ChatWebSocketProvider({ children }: { children: ReactNode }) {
    const { getToken, isSignedIn, isLoaded } = useAuth();

    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
    const heartbeatTimerRef = useRef<NodeJS.Timeout | null>(null);
    const tokenRefreshTimerRef = useRef<NodeJS.Timeout | null>(null);
    const shouldReconnectRef = useRef(true);

    // Stable singletons that outlive every render of this provider.
    const destroy$ = useRef(new Subject<void>()).current;
    const message$ = useRef(new Subject<ChatWSMessage>()).current;
    const isConnected$ = useRef(new BehaviorSubject<boolean>(false)).current;
    const typingThrottle$ = useRef(new Subject<ChatTarget>()).current;

    const setConnected = useChatStore((s) => s.setConnected);

    // ------------------------------------------------------------------------
    // CONNECT — always grabs a fresh token. The chat WS server validates the
    // JWT on the connection upgrade only, so a fresh token on each reconnect
    // is enough; we do NOT need an in-band `refresh_token` protocol.
    // ------------------------------------------------------------------------
    const connect = useCallback(async () => {
        if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) {
            return;
        }

        try {
            const token = isSignedIn ? await getToken({ skipCache: true }) : null;
            const url = token ? `${CHAT_WS_URL}?token=${token}` : CHAT_WS_URL;

            const ws = new WebSocket(url);
            wsRef.current = ws;

            ws.onopen = () => {
                setConnected(true);
                isConnected$.next(true);

                if (heartbeatTimerRef.current) clearInterval(heartbeatTimerRef.current);
                heartbeatTimerRef.current = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({ type: 'ping' }));
                    }
                }, HEARTBEAT_INTERVAL);

                // Re-subscribe to active target after a reconnect.
                const currentTarget = useChatStore.getState().activeTarget;
                if (currentTarget) {
                    ws.send(JSON.stringify({
                        type: 'subscribe',
                        payload: currentTarget.type === 'channel'
                            ? { channel_id: currentTarget.id }
                            : { group_id: currentTarget.id },
                    }));
                }
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data) as ChatWSMessage;
                    message$.next(data);
                } catch (e) {
                    console.error('[ChatWS] Parse error:', e);
                }
            };

            ws.onerror = (error) => {
                console.error('[ChatWS] Error:', error);
                setConnected(false, 'Connection error');
                isConnected$.next(false);
            };

            ws.onclose = () => {
                setConnected(false);
                isConnected$.next(false);
                wsRef.current = null;

                if (heartbeatTimerRef.current) {
                    clearInterval(heartbeatTimerRef.current);
                    heartbeatTimerRef.current = null;
                }

                if (shouldReconnectRef.current) {
                    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
                    reconnectTimerRef.current = setTimeout(connect, RECONNECT_DELAY);
                }
            };
        } catch (error) {
            console.error('[ChatWS] Connection failed:', error);
            setConnected(false, 'Failed to connect');
            if (shouldReconnectRef.current) {
                if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
                reconnectTimerRef.current = setTimeout(connect, RECONNECT_DELAY);
            }
        }
    }, [isSignedIn, getToken, setConnected, message$, isConnected$]);

    const disconnect = useCallback(() => {
        shouldReconnectRef.current = false;
        if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
        if (heartbeatTimerRef.current) clearInterval(heartbeatTimerRef.current);
        if (tokenRefreshTimerRef.current) clearInterval(tokenRefreshTimerRef.current);
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        isConnected$.next(false);
    }, [isConnected$]);

    const send = useCallback((msg: { type: string; payload?: unknown }) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(msg));
        }
    }, []);

    // ------------------------------------------------------------------------
    // ROUTE INCOMING MESSAGES INTO THE STORE
    // ------------------------------------------------------------------------
    useEffect(() => {
        const sub = message$.pipe(takeUntil(destroy$)).subscribe((msg) => {
            const store = useChatStore.getState();
            switch (msg.type) {
                case 'new_message': {
                    const targetKey = msg.payload.channel_id
                        ? `channel:${msg.payload.channel_id}`
                        : `group:${msg.payload.group_id}`;
                    store.addMessage(targetKey, msg.payload);
                    break;
                }
                case 'message_edited': {
                    if (store.activeTarget) {
                        const key = store.getTargetKey(store.activeTarget);
                        store.updateMessage(key, msg.payload.id, {
                            content: msg.payload.content,
                            edited_at: msg.payload.edited_at,
                        });
                    }
                    break;
                }
                case 'message_deleted': {
                    if (store.activeTarget) {
                        const key = store.getTargetKey(store.activeTarget);
                        store.removeMessage(key, msg.payload.id);
                    }
                    break;
                }
                case 'typing': {
                    store.addTypingUser(msg.payload.target, {
                        user_id: msg.payload.user_id,
                        user_name: msg.payload.user_name,
                        timestamp: Date.now(),
                    });
                    break;
                }
                case 'presence': {
                    store.setOnlineUsers(msg.payload.target, msg.payload.online);
                    break;
                }
                case 'reaction_added': {
                    if (store.activeTarget) {
                        const key = store.getTargetKey(store.activeTarget);
                        store.addReaction(key, msg.payload.message_id, msg.payload.emoji, msg.payload.user_id);
                    }
                    break;
                }
                case 'reaction_removed': {
                    if (store.activeTarget) {
                        const key = store.getTargetKey(store.activeTarget);
                        store.removeReaction(key, msg.payload.message_id, msg.payload.emoji, msg.payload.user_id);
                    }
                    break;
                }
                case 'group_invite': {
                    const payload = msg.payload;
                    if (!payload?.group) {
                        console.warn('[ChatWS] Invalid group_invite message:', msg);
                        break;
                    }
                    const { group, inviter_id, inviter_name } = payload;
                    store.addInvite({
                        id: `invite_${group.id}`,
                        group_id: group.id,
                        group_name: group.name,
                        inviter_id,
                        inviter_name,
                        status: 'pending',
                        created_at: new Date().toISOString(),
                        expires_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
                    });
                    break;
                }
            }
        });
        return () => sub.unsubscribe();
    }, [destroy$, message$]);

    // ------------------------------------------------------------------------
    // THROTTLED TYPING PIPE
    // ------------------------------------------------------------------------
    useEffect(() => {
        const sub = typingThrottle$
            .pipe(throttleTime(TYPING_THROTTLE), takeUntil(destroy$))
            .subscribe((target) => {
                send({
                    type: 'typing',
                    payload: target.type === 'channel'
                        ? { channel_id: target.id }
                        : { group_id: target.id },
                });
            });
        return () => sub.unsubscribe();
    }, [destroy$, typingThrottle$, send]);

    // ------------------------------------------------------------------------
    // LIFECYCLE — wait until Clerk has loaded before opening the connection.
    // ------------------------------------------------------------------------
    useEffect(() => {
        if (!isLoaded) return;

        shouldReconnectRef.current = true;
        connect();

        // Proactively warm Clerk's JWT cache so the next reconnect (if it
        // happens) gets a token that hasn't already expired. This is cheap
        // (Clerk reuses the cached token if still valid).
        if (isSignedIn) {
            tokenRefreshTimerRef.current = setInterval(() => {
                getToken({ skipCache: true }).catch(() => { /* ignore */ });
            }, TOKEN_REFRESH_INTERVAL);
        }

        return () => {
            destroy$.next();
            disconnect();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isLoaded, isSignedIn]);

    // ------------------------------------------------------------------------
    // PUBLIC API
    // ------------------------------------------------------------------------
    const subscribe = useCallback((target: ChatTarget) => {
        send({
            type: 'subscribe',
            payload: target.type === 'channel'
                ? { channel_id: target.id }
                : { group_id: target.id },
        });
    }, [send]);

    const unsubscribe = useCallback((target: ChatTarget) => {
        send({
            type: 'unsubscribe',
            payload: target.type === 'channel'
                ? { channel_id: target.id }
                : { group_id: target.id },
        });
    }, [send]);

    const sendTyping = useCallback((target: ChatTarget) => {
        typingThrottle$.next(target);
    }, [typingThrottle$]);

    const reconnect = useCallback(() => { connect(); }, [connect]);

    const api = useMemo<ChatWebSocketAPI>(() => ({
        isConnected$,
        subscribe,
        unsubscribe,
        sendTyping,
        reconnect,
    }), [isConnected$, subscribe, unsubscribe, sendTyping, reconnect]);

    return (
        <ChatWebSocketContext.Provider value={api}>
            {children}
        </ChatWebSocketContext.Provider>
    );
}

// ============================================================================
// HOOK — drop-in replacement for the old useChatWebSocket()
// ============================================================================

export function useChatWebSocket(): ChatWebSocketAPI {
    const ctx = useContext(ChatWebSocketContext);
    if (!ctx) {
        throw new Error('useChatWebSocket must be used within ChatWebSocketProvider');
    }
    return ctx;
}
