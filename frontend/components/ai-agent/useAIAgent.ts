'use client';

/**
 * useAIAgent Hook - V4 LangGraph Multi-Agent Protocol
 * ====================================================
 * Connects to AI Agent V4 (LangGraph orchestrator) via WebSocket.
 * Maps V4 streaming events (node_started, node_completed, final_response)
 * to the existing Message/AgentStep UI structure.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  Message,
  ResultBlockData,
  MarketContext,
  AgentStep,
  ClarificationData,
  ChartContext,
} from './types';

// V4 agent runs behind Caddy at agent.tradeul.com/v4/
const AGENT_BASE = process.env.NEXT_PUBLIC_AI_AGENT_V4_API_URL || 'https://agent.tradeul.com/v4';
const WS_BASE = AGENT_BASE.replace('https://', 'wss://').replace('http://', 'ws://');

// Timeouts
const REQUEST_TIMEOUT_MS = 180000;  // 3 min max (LangGraph multi-agent can take time)
const ACTIVITY_TIMEOUT_MS = 60000;  // 60s sin actividad = problema

// Node display names
const NODE_LABELS: Record<string, string> = {
  query_planner: 'Query Planner',
  supervisor: 'Query Planner',
  market_data: 'Market Data',
  news_events: 'News & Events',
  financial: 'Financials',
  research: 'Research (Grok)',
  code_exec: 'Code Execution',
  screener: 'Screener',
  synthesizer: 'Synthesizer',
};

interface UseAIAgentOptions {
  onMarketUpdate?: (session: string) => void;
}

interface PendingRequest {
  messageId: string;
  assistantMsgId: string;
  content: string;
  sentAt: number;
  threadId: string;
}

export function useAIAgent(options: UseAIAgentOptions = {}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [resultBlocks, setResultBlocks] = useState<ResultBlockData[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [marketContext, setMarketContext] = useState<MarketContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chartContext, setChartContext] = useState<ChartContext | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const clientIdRef = useRef<string>(`agent-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  const currentMessageIdRef = useRef<string | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const optionsRef = useRef(options);
  const isConnectingRef = useRef(false);

  // Request lifecycle tracking
  const pendingRequestRef = useRef<PendingRequest | null>(null);
  const requestTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const activityTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastActivityRef = useRef<number>(0);
  const nodeStartTimesRef = useRef<Record<string, number>>({});

  // Mantener opciones actualizadas
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  // ============================================================================
  // REQUEST LIFECYCLE MANAGEMENT
  // ============================================================================

  const cancelPendingRequest = useCallback((reason: 'timeout' | 'disconnect' | 'error') => {
    const pending = pendingRequestRef.current;
    if (!pending) return;

    console.warn(`Request cancelled: ${reason}`, { messageId: pending.messageId });

    const errorMessages: Record<string, string> = {
      timeout: 'La solicitud tardó demasiado. Por favor, intenta de nuevo.',
      disconnect: 'Se perdió la conexión. Reconectando...',
      error: 'Error al procesar la solicitud.'
    };

    setMessages(prev => prev.map(m =>
      m.id === pending.assistantMsgId || m.status === 'thinking'
        ? { ...m, status: 'error', content: m.content || errorMessages[reason] }
        : m
    ));

    pendingRequestRef.current = null;
    currentMessageIdRef.current = null;
    nodeStartTimesRef.current = {};
    setIsLoading(false);

    if (requestTimeoutRef.current) {
      clearTimeout(requestTimeoutRef.current);
      requestTimeoutRef.current = null;
    }
    if (activityTimeoutRef.current) {
      clearTimeout(activityTimeoutRef.current);
      activityTimeoutRef.current = null;
    }
  }, []);

  const resetActivityTimeout = useCallback(() => {
    lastActivityRef.current = Date.now();

    if (activityTimeoutRef.current) {
      clearTimeout(activityTimeoutRef.current);
    }

    if (pendingRequestRef.current) {
      activityTimeoutRef.current = setTimeout(() => {
        console.warn('Activity timeout - no response from server');
        cancelPendingRequest('timeout');
      }, ACTIVITY_TIMEOUT_MS);
    }
  }, [cancelPendingRequest]);

  const completeRequest = useCallback(() => {
    pendingRequestRef.current = null;
    nodeStartTimesRef.current = {};

    if (requestTimeoutRef.current) {
      clearTimeout(requestTimeoutRef.current);
      requestTimeoutRef.current = null;
    }
    if (activityTimeoutRef.current) {
      clearTimeout(activityTimeoutRef.current);
      activityTimeoutRef.current = null;
    }
  }, []);

  // ============================================================================
  // V4 PROTOCOL HANDLER
  // Maps V4 events to existing UI message structure
  // ============================================================================

  const handleWSMessage = useCallback((event: MessageEvent) => {
    resetActivityTimeout();
    try {
      const data = JSON.parse(event.data);
      const pending = pendingRequestRef.current;

      switch (data.type) {
        // V4: Server acknowledges the query
        case 'ack': {
          if (pending) {
            // Create assistant message in thinking state
            const assistantId = pending.assistantMsgId;
            currentMessageIdRef.current = assistantId;
            setMessages(prev => [...prev, {
              id: assistantId,
              role: 'assistant',
              content: '',
              timestamp: new Date(),
              status: 'thinking',
              steps: [],
              thinkingStartTime: Date.now()
            }]);
          }
          break;
        }

        // V4: A LangGraph node started executing
        case 'node_started': {
          const nodeName = data.node as string;
          const msgId = currentMessageIdRef.current;
          if (!msgId) break;

          nodeStartTimesRef.current[nodeName] = data.timestamp || Date.now() / 1000;

          const step: AgentStep = {
            id: `step-${nodeName}`,
            type: nodeName === 'supervisor' ? 'reasoning' : 'tool',
            title: NODE_LABELS[nodeName] || nodeName,
            status: 'running',
            icon: nodeName === 'supervisor' ? 'brain' : 'zap',
          };

          setMessages(prev => prev.map(m =>
            m.id === msgId
              ? { ...m, steps: [...(m.steps || []), step] }
              : m
          ));
          break;
        }

        // V4: A LangGraph node completed
        case 'node_completed': {
          const nodeName = data.node as string;
          const msgId = currentMessageIdRef.current;
          if (!msgId) break;

          const startTime = nodeStartTimesRef.current[nodeName] || 0;
          const elapsed = data.elapsed_ms ? data.elapsed_ms / 1000 : 0;
          const preview = data.preview as string || '';

          setMessages(prev => prev.map(m =>
            m.id === msgId
              ? {
                ...m,
                steps: (m.steps || []).map(s =>
                  s.id === `step-${nodeName}`
                    ? {
                      ...s,
                      status: 'complete' as const,
                      duration: elapsed,
                      description: preview || undefined,
                    }
                    : s
                )
              }
              : m
          ));
          break;
        }

        // V4: Node error
        case 'node_error': {
          const nodeName = data.node as string;
          const msgId = currentMessageIdRef.current;
          if (!msgId) break;

          setMessages(prev => prev.map(m =>
            m.id === msgId
              ? {
                ...m,
                steps: (m.steps || []).map(s =>
                  s.id === `step-${nodeName}`
                    ? { ...s, status: 'error' as const, description: data.error || 'Error' }
                    : s
                )
              }
              : m
          ));
          break;
        }

        // V5: Clarification needed — show options to user
        case 'clarification': {
          const msgId = currentMessageIdRef.current;
          if (!msgId) break;

          const clarificationData: ClarificationData = {
            message: (data.message as string) || '',
            options: (data.options as ClarificationData['options']) || [],
            originalQuery: (data.original_query as string) || '',
          };

          setMessages(prev => prev.map(m =>
            m.id === msgId
              ? {
                ...m,
                content: clarificationData.message,
                status: 'clarification' as const,
                clarification: clarificationData,
                steps: (m.steps || []).map(s => ({
                  ...s,
                  status: 'complete' as const,
                })),
              }
              : m
          ));

          setIsLoading(false);
          currentMessageIdRef.current = null;
          completeRequest();
          break;
        }

        // V4: Final synthesized response
        case 'final_response': {
          const msgId = currentMessageIdRef.current;
          if (!msgId) break;

          const response = data.response as string || '';
          const totalMs = data.metadata?.total_elapsed_ms;

          // Update message status
          setMessages(prev => prev.map(m =>
            m.id === msgId
              ? {
                ...m,
                content: response,
                status: 'complete',
              }
              : m
          ));

          // Create a resultBlock so the response shows in the Results panel
          if (response) {
            const blockId = `${msgId}-response`;
            const userQuery = pendingRequestRef.current?.content || '';
            setResultBlocks(prev => [...prev, {
              id: blockId,
              messageId: msgId,
              query: userQuery,
              title: `Analysis`,
              status: 'success' as const,
              code: '',
              codeVisible: false,
              result: {
                success: true,
                code: '',
                outputs: [{
                  type: 'research' as const,
                  title: 'AI Analysis',
                  content: response,
                }],
                execution_time_ms: totalMs || 0,
                timestamp: new Date().toISOString(),
              },
              timestamp: new Date(),
            }]);
          }

          setIsLoading(false);
          currentMessageIdRef.current = null;
          completeRequest();
          break;
        }

        // V4: Error
        case 'error': {
          const msgId = currentMessageIdRef.current;
          const errorMsg = data.message as string || 'Error desconocido';
          const lowerErr = errorMsg.toLowerCase();
          const isRateLimit = ['429', 'rate limit', 'resource exhausted', 'too many requests', 'quota'].some(k => lowerErr.includes(k));

          if (isRateLimit) {
            const retryCount = (data._retryCount as number) || 0;
            const maxAutoRetries = 2;
            if (retryCount < maxAutoRetries && pendingRequestRef.current) {
              const retryDelay = Math.min(3000 * Math.pow(2, retryCount) + Math.random() * 2000, 15000);
              const pending = pendingRequestRef.current;
              console.warn(`Rate limit hit, auto-retrying in ${Math.round(retryDelay)}ms (attempt ${retryCount + 1}/${maxAutoRetries})`);

              if (msgId) {
                setMessages(prev => prev.map(m =>
                  m.id === msgId
                    ? { ...m, content: `Servidor ocupado, reintentando en ${Math.round(retryDelay / 1000)}s...` }
                    : m
                ));
              }

              setTimeout(() => {
                if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
                const payload: Record<string, unknown> = {
                  query: pending.content,
                  thread_id: `${clientIdRef.current}-${Date.now()}`,
                  mode: 'auto',
                  _retryCount: retryCount + 1,
                };
                wsRef.current.send(JSON.stringify(payload));
              }, retryDelay);
              break;
            }
          }

          const friendlyMsg = isRateLimit
            ? 'El servicio está temporalmente saturado. Por favor, espera unos segundos e intenta de nuevo.'
            : errorMsg;

          if (msgId) {
            setMessages(prev => prev.map(m =>
              m.id === msgId
                ? { ...m, status: 'error', content: m.content || `Error: ${friendlyMsg}` }
                : m
            ));
          }
          setError(friendlyMsg);
          setIsLoading(false);
          completeRequest();
          break;
        }

        default:
          // Ignore unknown types silently
          break;
      }
    } catch (e) {
      console.error('Error parsing WS message:', e);
    }
  }, [resetActivityTimeout, completeRequest]);

  // ============================================================================
  // WEBSOCKET CONNECTION
  // ============================================================================

  const connect = useCallback(() => {
    if (isConnectingRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    if (wsRef.current?.readyState === WebSocket.CONNECTING) return;

    isConnectingRef.current = true;

    const wsUrl = `${WS_BASE}/ws/chat/${clientIdRef.current}`;
    console.log('Connecting to AI Agent V4:', wsUrl);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('AI Agent V4 WebSocket connected');
      isConnectingRef.current = false;
      reconnectAttemptsRef.current = 0;
      setIsConnected(true);
      setError(null);
    };

    ws.onmessage = handleWSMessage;

    ws.onclose = (event) => {
      console.log('AI Agent V4 WebSocket closed:', event.code, event.reason);
      setIsConnected(false);
      isConnectingRef.current = false;
      wsRef.current = null;

      if (pendingRequestRef.current) {
        cancelPendingRequest('disconnect');
      }

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      const attempt = reconnectAttemptsRef.current;
      const baseDelay = 1000;
      const maxDelay = 30000;
      const delay = Math.min(baseDelay * Math.pow(2, attempt) + Math.random() * 1000, maxDelay);
      reconnectAttemptsRef.current = attempt + 1;
      console.log(`WebSocket reconnect in ${Math.round(delay)}ms (attempt ${attempt + 1})`);
      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, delay);
    };

    ws.onerror = (error) => {
      console.error('AI Agent V4 WebSocket error:', error);
      setError('Error de conexión con AI Agent V4');
      isConnectingRef.current = false;
    };

    wsRef.current = ws;
  }, [handleWSMessage, cancelPendingRequest]);

  const disconnect = useCallback(() => {
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

    pendingRequestRef.current = null;
    nodeStartTimesRef.current = {};

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
    setIsLoading(false);
    isConnectingRef.current = false;
  }, []);

  // ============================================================================
  // SEND MESSAGE (V4 protocol)
  // ============================================================================

  const sendMessage = useCallback((content: string, chartCtx?: ChartContext | null) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setError('No conectado al servidor');
      return;
    }

    if (!content.trim()) return;

    if (pendingRequestRef.current) {
      console.warn('Cancelling previous pending request');
      cancelPendingRequest('error');
    }

    const now = Date.now();
    const messageId = `user-${now}`;
    const assistantMsgId = `assistant-${now}`;
    // Fresh thread_id per query — prevents state contamination via merge_dicts reducer
    const threadId = `${clientIdRef.current}-${now}`;

    const userMessage: Message = {
      id: messageId,
      role: 'user',
      content: content.trim(),
      timestamp: new Date()
    };
    setMessages(prev => [
      ...prev.map(m =>
        m.status === 'clarification'
          ? { ...m, status: 'complete' as const }
          : m
      ),
      userMessage,
    ]);
    setIsLoading(true);
    setError(null);

    pendingRequestRef.current = {
      messageId,
      assistantMsgId,
      content: content.trim(),
      sentAt: now,
      threadId,
    };
    lastActivityRef.current = now;
    nodeStartTimesRef.current = {};

    requestTimeoutRef.current = setTimeout(() => {
      console.error('Request timeout - max time exceeded');
      cancelPendingRequest('timeout');
    }, REQUEST_TIMEOUT_MS);

    activityTimeoutRef.current = setTimeout(() => {
      console.warn('Activity timeout - no initial response');
      cancelPendingRequest('timeout');
    }, ACTIVITY_TIMEOUT_MS);

    // chartCtx passed directly avoids React state timing issues
    const ctxToSend = chartCtx ?? chartContext;
    const payload: Record<string, unknown> = {
      query: content.trim(),
      thread_id: threadId,
      mode: 'auto',
    };
    if (ctxToSend) {
      payload.chart_context = ctxToSend;
      setChartContext(null);
    }
    wsRef.current.send(JSON.stringify(payload));
  }, [cancelPendingRequest, chartContext]);

  const sendClarificationChoice = useCallback((originalQuery: string, rewrite: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setError('No conectado al servidor');
      return;
    }

    if (pendingRequestRef.current) {
      cancelPendingRequest('error');
    }

    const now = Date.now();
    const messageId = `user-${now}`;
    const assistantMsgId = `assistant-${now}`;
    // Clarification re-sends use a fresh thread (no stale state needed)
    const threadId = `${clientIdRef.current}-${now}`;

    setIsLoading(true);
    setError(null);

    pendingRequestRef.current = {
      messageId,
      assistantMsgId,
      content: originalQuery,
      sentAt: now,
      threadId,
    };
    lastActivityRef.current = now;
    nodeStartTimesRef.current = {};

    requestTimeoutRef.current = setTimeout(() => {
      cancelPendingRequest('timeout');
    }, REQUEST_TIMEOUT_MS);

    activityTimeoutRef.current = setTimeout(() => {
      cancelPendingRequest('timeout');
    }, ACTIVITY_TIMEOUT_MS);

    wsRef.current.send(JSON.stringify({
      query: originalQuery,
      thread_id: threadId,
      mode: 'auto',
      clarification_hint: rewrite,
    }));
  }, [cancelPendingRequest]);

  const clearHistory = useCallback(() => {
    setMessages([]);
    setResultBlocks([]);
  }, []);

  const toggleCodeVisibility = useCallback((blockId: string) => {
    setResultBlocks(prev => prev.map(b =>
      b.id === blockId
        ? { ...b, codeVisible: !b.codeVisible }
        : b
    ));
  }, []);

  // Auto-connect on mount
  useEffect(() => {
    connect();
    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Heartbeat (V4 expects JSON, we send a minimal ping)
  useEffect(() => {
    const interval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        // V4 ignores unknown messages gracefully
        wsRef.current.send(JSON.stringify({ query: '', thread_id: '' }));
      }
    }, isLoading ? 15000 : 45000);

    return () => clearInterval(interval);
  }, [isLoading]);

  return {
    messages,
    resultBlocks,
    isConnected,
    isLoading,
    marketContext,
    error,
    chartContext,
    sendMessage,
    setChartContext,
    sendClarificationChoice,
    clearHistory,
    toggleCodeVisibility,
    connect,
    disconnect,
  };
}
