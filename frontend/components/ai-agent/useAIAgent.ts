'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  Message,
  ResultBlockData,
  MarketContext,
  WSMessage,
  WSConnectedMessage,
  WSResponseStartMessage,
  WSAssistantTextMessage,
  WSCodeExecutionMessage,
  WSResultMessage,
  WSResponseEndMessage,
  WSErrorMessage,
  WSMarketUpdateMessage,
  WSAgentStepMessage,
  WSAgentStepUpdateMessage,
} from './types';

const AGENT_URL = process.env.NEXT_PUBLIC_AGENT_URL || 'https://agent.tradeul.com';
const WS_URL = AGENT_URL.replace('https://', 'wss://').replace('http://', 'ws://');

// Timeouts profesionales
const REQUEST_TIMEOUT_MS = 120000;  // 2 min max para una respuesta completa
const ACTIVITY_TIMEOUT_MS = 45000;  // 45s sin actividad = problema

interface UseAIAgentOptions {
  onMarketUpdate?: (session: string) => void;
}

interface PendingRequest {
  messageId: string;
  content: string;
  sentAt: number;
}

export function useAIAgent(options: UseAIAgentOptions = {}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [resultBlocks, setResultBlocks] = useState<ResultBlockData[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [marketContext, setMarketContext] = useState<MarketContext | null>(null);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const clientIdRef = useRef<string>(`agent-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  const conversationIdRef = useRef<string>(clientIdRef.current);
  const currentMessageIdRef = useRef<string | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const optionsRef = useRef(options);
  const isConnectingRef = useRef(false);
  
  // Request lifecycle tracking
  const pendingRequestRef = useRef<PendingRequest | null>(null);
  const requestTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const activityTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastActivityRef = useRef<number>(0);

  // Mantener opciones actualizadas
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  // ============================================================================
  // REQUEST LIFECYCLE MANAGEMENT (como ChatGPT/Slack)
  // ============================================================================
  
  // Cancelar request pendiente y limpiar estado
  const cancelPendingRequest = useCallback((reason: 'timeout' | 'disconnect' | 'error') => {
    const pending = pendingRequestRef.current;
    if (!pending) return;
    
    console.warn(`Request cancelled: ${reason}`, { messageId: pending.messageId });
    
    // Marcar mensaje como error con mensaje descriptivo
    const errorMessages: Record<string, string> = {
      timeout: 'La solicitud tardó demasiado. Por favor, intenta de nuevo.',
      disconnect: 'Se perdió la conexión. Reconectando...',
      error: 'Error al procesar la solicitud.'
    };
    
    setMessages(prev => prev.map(m =>
      m.id === pending.messageId || m.status === 'thinking'
        ? { ...m, status: 'error', content: m.content || errorMessages[reason] }
        : m
    ));
    
    // Limpiar estado
    pendingRequestRef.current = null;
    currentMessageIdRef.current = null;
    setIsLoading(false);
    
    // Limpiar timeouts
    if (requestTimeoutRef.current) {
      clearTimeout(requestTimeoutRef.current);
      requestTimeoutRef.current = null;
    }
    if (activityTimeoutRef.current) {
      clearTimeout(activityTimeoutRef.current);
      activityTimeoutRef.current = null;
    }
  }, []);

  // Resetear activity timeout (llamar cada vez que llega un mensaje)
  const resetActivityTimeout = useCallback(() => {
    lastActivityRef.current = Date.now();
    
    if (activityTimeoutRef.current) {
      clearTimeout(activityTimeoutRef.current);
    }
    
    // Solo si hay request pendiente
    if (pendingRequestRef.current) {
      activityTimeoutRef.current = setTimeout(() => {
        console.warn('Activity timeout - no response from server');
        cancelPendingRequest('timeout');
      }, ACTIVITY_TIMEOUT_MS);
    }
  }, [cancelPendingRequest]);

  // Completar request exitosamente
  const completeRequest = useCallback(() => {
    pendingRequestRef.current = null;
    
    if (requestTimeoutRef.current) {
      clearTimeout(requestTimeoutRef.current);
      requestTimeoutRef.current = null;
    }
    if (activityTimeoutRef.current) {
      clearTimeout(activityTimeoutRef.current);
      activityTimeoutRef.current = null;
    }
  }, []);

  // Procesar mensajes WebSocket
  const handleWSMessage = useCallback((event: MessageEvent) => {
    // Resetear activity timeout en CUALQUIER mensaje recibido
    resetActivityTimeout();
    try {
      const data: WSMessage = JSON.parse(event.data);

      switch (data.type) {
        case 'connected': {
          const msg = data as WSConnectedMessage;
          setMarketContext(msg.market_context);
          setIsConnected(true);
          setError(null);
          break;
        }

        case 'response_start': {
          const msg = data as WSResponseStartMessage;
          currentMessageIdRef.current = msg.message_id;
          setMessages(prev => [...prev, {
            id: msg.message_id,
            role: 'assistant',
            content: '',
            timestamp: new Date(),
            status: 'thinking',
            steps: [],
            thinkingStartTime: Date.now()
          }]);
          break;
        }

        case 'agent_step': {
          const msg = data as unknown as WSAgentStepMessage;
          setMessages(prev => prev.map(m =>
            m.id === msg.message_id
              ? { ...m, steps: [...(m.steps || []), msg.step] }
              : m
          ));
          break;
        }

        case 'agent_step_update': {
          const msg = data as unknown as WSAgentStepUpdateMessage;
          setMessages(prev => prev.map(m =>
            m.id === msg.message_id
              ? {
                ...m,
                steps: (m.steps || []).map(s =>
                  s.id === msg.step_id
                    ? { ...s, status: msg.status, description: msg.description || s.description }
                    : s
                )
              }
              : m
          ));
          break;
        }

        case 'assistant_text': {
          const msg = data as WSAssistantTextMessage;
          setMessages(prev => prev.map(m =>
            m.id === msg.message_id
              ? { ...m, content: m.content + msg.delta, status: 'thinking' }
              : m
          ));
          break;
        }

        case 'code_execution': {
          const msg = data as WSCodeExecutionMessage;
          // ID unico combinando message_id + block_id para no sobrescribir bloques anteriores
          const uniqueBlockId = `${msg.message_id}-${msg.block_id}`;

          setMessages(prev => prev.map(m =>
            m.id === msg.message_id
              ? { ...m, status: 'executing' }
              : m
          ));

          setResultBlocks(prev => {
            const existing = prev.find(b => b.id === uniqueBlockId);
            if (existing) {
              return prev.map(b =>
                b.id === uniqueBlockId
                  ? { ...b, status: msg.status, code: msg.code }
                  : b
              );
            }
            return [...prev, {
              id: uniqueBlockId,
              messageId: msg.message_id,
              title: `Query ${prev.length + 1}`,
              status: msg.status,
              code: msg.code,
              codeVisible: false, // Colapsado por defecto
              timestamp: new Date()
            }];
          });
          break;
        }

        case 'result': {
          const msg = data as WSResultMessage;
          // ID unico combinando message_id + block_id
          const uniqueBlockId = `${msg.message_id}-${msg.block_id}`;

          setResultBlocks(prev => {
            const existing = prev.find(b => b.id === uniqueBlockId);
            const resultData = {
              success: msg.success,
              code: msg.code,
              outputs: msg.outputs,
              error: msg.error,
              execution_time_ms: msg.execution_time_ms,
              timestamp: msg.timestamp
            };

            if (existing) {
              // Update existing block
              return prev.map(b =>
                b.id === uniqueBlockId
                  ? { ...b, status: msg.status, code: msg.code, result: resultData }
                  : b
              );
            } else {
              // Create new block with result (if code_execution was skipped)
              return [...prev, {
                id: uniqueBlockId,
                messageId: msg.message_id,
                title: `Analysis`,
                status: msg.status,
                code: msg.code,
                codeVisible: false,
                result: resultData,
                timestamp: new Date()
              }];
            }
          });
          break;
        }

        case 'response_end': {
          const msg = data as WSResponseEndMessage;
          setMessages(prev => prev.map(m =>
            m.id === msg.message_id
              ? { ...m, status: 'complete' }
              : m
          ));
          setIsLoading(false);
          currentMessageIdRef.current = null;
          completeRequest(); // Limpiar tracking de request
          break;
        }

        case 'error': {
          const msg = data as WSErrorMessage;
          if (msg.message_id) {
            setMessages(prev => prev.map(m =>
              m.id === msg.message_id
                ? { ...m, status: 'error', content: m.content + `\n\nError: ${msg.error}` }
                : m
            ));
          }
          setError(msg.error);
          setIsLoading(false);
          completeRequest(); // Limpiar tracking de request
          break;
        }

        case 'market_update': {
          const msg = data as WSMarketUpdateMessage;
          setMarketContext(prev => prev ? { ...prev, session: msg.session } : null);
          optionsRef.current.onMarketUpdate?.(msg.session);
          break;
        }

        case 'history_cleared': {
          setMessages([]);
          setResultBlocks([]);
          break;
        }

        case 'pong':
          break;

        default:
          console.warn('Unknown WS message type:', data.type);
      }
    } catch (e) {
      console.error('Error parsing WS message:', e);
    }
  }, [resetActivityTimeout, completeRequest]);

  // Conectar WebSocket
  const connect = useCallback(() => {
    if (isConnectingRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    if (wsRef.current?.readyState === WebSocket.CONNECTING) return;

    isConnectingRef.current = true;

    const ws = new WebSocket(`${WS_URL}/ws/chat/${clientIdRef.current}`);

    ws.onopen = () => {
      console.log('AI Agent WebSocket connected');
      isConnectingRef.current = false;
    };

    ws.onmessage = handleWSMessage;

    ws.onclose = (event) => {
      console.log('AI Agent WebSocket closed:', event.code, event.reason);
      setIsConnected(false);
      isConnectingRef.current = false;
      wsRef.current = null;

      // IMPORTANTE: Cancelar cualquier request pendiente al desconectar
      if (pendingRequestRef.current) {
        cancelPendingRequest('disconnect');
      }

      // Reconectar despues de 3 segundos
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, 3000);
    };

    ws.onerror = (error) => {
      console.error('AI Agent WebSocket error:', error);
      setError('Error de conexion con el servidor');
      isConnectingRef.current = false;
    };

    wsRef.current = ws;
  }, [handleWSMessage, cancelPendingRequest]);

  // Desconectar
  const disconnect = useCallback(() => {
    // Limpiar todos los timeouts
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (requestTimeoutRef.current) {
      clearTimeout(requestTimeoutRef.current);
      requestTimeoutRef.current = null;
    }
    if (activityTimeoutRef.current) {
      clearTimeout(activityTimeoutRef.current);
      activityTimeoutRef.current = null;
    }
    
    // Limpiar request pendiente
    pendingRequestRef.current = null;
    
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
    setIsLoading(false);
    isConnectingRef.current = false;
  }, []);

  // Enviar mensaje
  const sendMessage = useCallback((content: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setError('No conectado al servidor');
      return;
    }

    if (!content.trim()) return;

    // Cancelar request pendiente anterior si existe
    if (pendingRequestRef.current) {
      console.warn('Cancelling previous pending request');
      cancelPendingRequest('error');
    }

    const messageId = `user-${Date.now()}`;
    const userMessage: Message = {
      id: messageId,
      role: 'user',
      content: content.trim(),
      timestamp: new Date()
    };
    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);
    setError(null);

    // Trackear request pendiente
    pendingRequestRef.current = {
      messageId,
      content: content.trim(),
      sentAt: Date.now()
    };
    lastActivityRef.current = Date.now();

    // Timeout absoluto de request (2 min max)
    requestTimeoutRef.current = setTimeout(() => {
      console.error('Request timeout - max time exceeded');
      cancelPendingRequest('timeout');
    }, REQUEST_TIMEOUT_MS);

    // Activity timeout (45s sin respuesta)
    activityTimeoutRef.current = setTimeout(() => {
      console.warn('Activity timeout - no initial response');
      cancelPendingRequest('timeout');
    }, ACTIVITY_TIMEOUT_MS);

    // Enviar mensaje
    wsRef.current.send(JSON.stringify({
      type: 'chat_message',
      content: content.trim(),
      conversation_id: conversationIdRef.current
    }));
  }, [cancelPendingRequest]);

  // Limpiar historial
  const clearHistory = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'clear_history',
        conversation_id: conversationIdRef.current
      }));
    }
    setMessages([]);
    setResultBlocks([]);
  }, []);

  // Toggle visibilidad de codigo
  const toggleCodeVisibility = useCallback((blockId: string) => {
    setResultBlocks(prev => prev.map(b =>
      b.id === blockId
        ? { ...b, codeVisible: !b.codeVisible }
        : b
    ));
  }, []);

  // Auto-conectar al montar (solo una vez)
  useEffect(() => {
    connect();
    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Heartbeat - más frecuente durante loading para mantener conexión viva
  useEffect(() => {
    const interval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }));
      }
    }, isLoading ? 10000 : 30000); // 10s durante loading, 30s idle

    return () => clearInterval(interval);
  }, [isLoading]);

  return {
    messages,
    resultBlocks,
    isConnected,
    isLoading,
    marketContext,
    error,
    sendMessage,
    clearHistory,
    toggleCodeVisibility,
    connect,
    disconnect
  };
}
