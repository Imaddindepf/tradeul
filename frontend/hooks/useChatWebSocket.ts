/**
 * Chat WebSocket Hook
 * 
 * Manages WebSocket connection to chat server (port 9001).
 * COMPLETELY SEPARATE from scanner WebSocket (port 9000).
 * 
 * Uses RxJS for reactive message handling.
 */

'use client';

import { useEffect, useRef, useCallback, useMemo } from 'react';
import { useAuth } from '@clerk/nextjs';
import { Subject, BehaviorSubject, timer, fromEvent } from 'rxjs';
import { filter, throttleTime, map, takeUntil } from 'rxjs/operators';
import { useChatStore, type ChatMessage } from '@/stores/useChatStore';

// ============================================================================
// CONFIGURATION
// ============================================================================

const CHAT_WS_URL = process.env.NEXT_PUBLIC_CHAT_WS_URL || 'ws://localhost:9001';
const RECONNECT_DELAY = 3000;
const HEARTBEAT_INTERVAL = 30000;
const TYPING_THROTTLE = 2000;

// ============================================================================
// MESSAGE TYPES
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
  | { type: 'pong' };

// ============================================================================
// HOOK
// ============================================================================

export function useChatWebSocket() {
  const { getToken, isSignedIn } = useAuth();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  const heartbeatIntervalRef = useRef<NodeJS.Timeout>();
  
  // RxJS Subjects
  const destroy$ = useRef(new Subject<void>()).current;
  const message$ = useRef(new Subject<ChatWSMessage>()).current;
  const isConnected$ = useRef(new BehaviorSubject<boolean>(false)).current;
  
  // Store actions
  const {
    setConnected,
    activeTarget,
    getTargetKey,
    addMessage,
    updateMessage,
    removeMessage,
    addTypingUser,
    setOnlineUsers,
    addReaction,
    removeReaction,
  } = useChatStore();

  // ============================================================================
  // CONNECTION
  // ============================================================================

  const connect = useCallback(async () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      // Get auth token
      const token = isSignedIn ? await getToken() : null;
      const url = token ? `${CHAT_WS_URL}?token=${token}` : CHAT_WS_URL;

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[ChatWS] Connected');
        setConnected(true);
        isConnected$.next(true);

        // Start heartbeat
        heartbeatIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, HEARTBEAT_INTERVAL);

        // Re-subscribe to active target
        if (activeTarget) {
          send({
            type: 'subscribe',
            payload: activeTarget.type === 'channel'
              ? { channel_id: activeTarget.id }
              : { group_id: activeTarget.id }
          });
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
        console.log('[ChatWS] Disconnected');
        setConnected(false);
        isConnected$.next(false);
        wsRef.current = null;

        // Clear heartbeat
        if (heartbeatIntervalRef.current) {
          clearInterval(heartbeatIntervalRef.current);
        }

        // Schedule reconnect
        reconnectTimeoutRef.current = setTimeout(connect, RECONNECT_DELAY);
      };
    } catch (error) {
      console.error('[ChatWS] Connection failed:', error);
      setConnected(false, 'Failed to connect');
      reconnectTimeoutRef.current = setTimeout(connect, RECONNECT_DELAY);
    }
  }, [isSignedIn, getToken, setConnected, activeTarget, message$, isConnected$]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const send = useCallback((message: { type: string; payload?: unknown }) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  // ============================================================================
  // MESSAGE HANDLERS
  // ============================================================================

  useEffect(() => {
    // Handle incoming messages via RxJS
    const subscription = message$.pipe(
      takeUntil(destroy$)
    ).subscribe((msg) => {
      switch (msg.type) {
        case 'new_message': {
          const targetKey = msg.payload.channel_id
            ? `channel:${msg.payload.channel_id}`
            : `group:${msg.payload.group_id}`;
          addMessage(targetKey, msg.payload);
          break;
        }

        case 'message_edited': {
          // Find which target this message belongs to
          if (activeTarget) {
            const key = getTargetKey(activeTarget);
            updateMessage(key, msg.payload.id, {
              content: msg.payload.content,
              edited_at: msg.payload.edited_at,
            });
          }
          break;
        }

        case 'message_deleted': {
          if (activeTarget) {
            const key = getTargetKey(activeTarget);
            removeMessage(key, msg.payload.id);
          }
          break;
        }

        case 'typing': {
          addTypingUser(msg.payload.target, {
            user_id: msg.payload.user_id,
            user_name: msg.payload.user_name,
            timestamp: Date.now(),
          });
          break;
        }

        case 'presence': {
          setOnlineUsers(msg.payload.target, msg.payload.online);
          break;
        }

        case 'reaction_added': {
          if (activeTarget) {
            const key = getTargetKey(activeTarget);
            addReaction(key, msg.payload.message_id, msg.payload.emoji, msg.payload.user_id);
          }
          break;
        }

        case 'reaction_removed': {
          if (activeTarget) {
            const key = getTargetKey(activeTarget);
            removeReaction(key, msg.payload.message_id, msg.payload.emoji, msg.payload.user_id);
          }
          break;
        }
      }
    });

    return () => subscription.unsubscribe();
  }, [
    message$, destroy$, activeTarget, getTargetKey,
    addMessage, updateMessage, removeMessage,
    addTypingUser, setOnlineUsers, addReaction, removeReaction
  ]);

  // ============================================================================
  // ACTIONS
  // ============================================================================

  const subscribe = useCallback((target: { type: 'channel' | 'group'; id: string }) => {
    send({
      type: 'subscribe',
      payload: target.type === 'channel'
        ? { channel_id: target.id }
        : { group_id: target.id }
    });
  }, [send]);

  const unsubscribe = useCallback((target: { type: 'channel' | 'group'; id: string }) => {
    send({
      type: 'unsubscribe',
      payload: target.type === 'channel'
        ? { channel_id: target.id }
        : { group_id: target.id }
    });
  }, [send]);

  // Throttled typing indicator
  const typingThrottle$ = useMemo(
    () => new Subject<{ type: 'channel' | 'group'; id: string }>(),
    []
  );

  useEffect(() => {
    const subscription = typingThrottle$.pipe(
      throttleTime(TYPING_THROTTLE),
      takeUntil(destroy$)
    ).subscribe((target) => {
      send({
        type: 'typing',
        payload: target.type === 'channel'
          ? { channel_id: target.id }
          : { group_id: target.id }
      });
    });

    return () => subscription.unsubscribe();
  }, [typingThrottle$, send, destroy$]);

  const sendTyping = useCallback((target: { type: 'channel' | 'group'; id: string }) => {
    typingThrottle$.next(target);
  }, [typingThrottle$]);

  // ============================================================================
  // LIFECYCLE
  // ============================================================================

  useEffect(() => {
    connect();

    return () => {
      destroy$.next();
      destroy$.complete();
      disconnect();
    };
  }, [connect, disconnect, destroy$]);

  // Re-subscribe when active target changes
  useEffect(() => {
    if (activeTarget) {
      subscribe(activeTarget);
    }
    
    return () => {
      if (activeTarget) {
        unsubscribe(activeTarget);
      }
    };
  }, [activeTarget, subscribe, unsubscribe]);

  return {
    isConnected$,
    subscribe,
    unsubscribe,
    sendTyping,
    reconnect: connect,
  };
}

