'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import type { WebSocketMessage } from '@/lib/types';

interface UseWebSocketReturn {
  isConnected: boolean;
  lastMessage: WebSocketMessage | null;
  subscribe: (symbols: string[]) => void;
  unsubscribe: (symbols: string[]) => void;
  subscribeAll: () => void;
  send: (payload: any) => void;
}

export function useWebSocket(url: string): UseWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  const messageHandlerRef = useRef<((message: WebSocketMessage) => void) | null>(null);
  const messageCounterRef = useRef(0); // Contador para forzar actualización

  const sendMessage = useCallback((action: string, payload?: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action, ...payload }));
    }
  }, []);

  const subscribe = useCallback((symbols: string[]) => {
    sendMessage('subscribe', { symbols });
  }, [sendMessage]);

  const unsubscribe = useCallback((symbols: string[]) => {
    sendMessage('unsubscribe', { symbols });
  }, [sendMessage]);

  const subscribeAll = useCallback(() => {
    sendMessage('subscribe_all');
  }, [sendMessage]);

  const send = useCallback((payload: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
    }
  }, []);

  useEffect(() => {
    const connect = () => {
      try {
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log('✅ WebSocket connected');
          setIsConnected(true);
        };

        ws.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data);
            
            // Solo actualizar si el mensaje es diferente (evitar re-renders innecesarios)
            setLastMessage(prevMessage => {
              // Si el tipo de mensaje es el mismo y el contenido no cambió, no actualizar
              if (prevMessage && 
                  prevMessage.type === message.type && 
                  JSON.stringify(prevMessage.data) === JSON.stringify(message.data)) {
                return prevMessage; // No cambiar estado = no re-render
              }
              
              // Mensaje nuevo o diferente: actualizar
              return {
                ...message,
                timestamp: message.timestamp || new Date().toISOString()
              };
            });
            
            // Call custom handler if registered
            if (messageHandlerRef.current) {
              messageHandlerRef.current(message);
            }
          } catch (error) {
            console.error('Error parsing WebSocket message:', error);
          }
        };

        ws.onerror = (error) => {
          console.error('WebSocket error:', error);
        };

        ws.onclose = () => {
          console.log('❌ WebSocket closed');
          setIsConnected(false);
          
          // Auto-reconnect después de 3 segundos
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('🔄 Reconnecting WebSocket...');
            connect();
          }, 3000);
        };
      } catch (error) {
        console.error('Error creating WebSocket:', error);
      }
    };

    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [url]);

  return { 
    isConnected, 
    lastMessage,
    subscribe,
    unsubscribe,
    subscribeAll,
    send
  };
}

