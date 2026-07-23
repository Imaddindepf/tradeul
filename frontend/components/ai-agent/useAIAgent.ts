'use client';

/**
 * useAIAgent Hook - V4 LangGraph Multi-Agent Protocol
 * ====================================================
 * Connects to AI Agent V4 (LangGraph orchestrator) via WebSocket.
 * Maps V4 streaming events (node_started, node_completed, final_response)
 * to the existing Message/AgentStep UI structure.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { useAuth } from '@clerk/nextjs';
import i18n from '@/lib/i18n';
import {
  Message,
  ResultBlockData,
  MarketContext,
  AgentStep,
  ClarificationData,
  ChartContext,
} from './types';
import {
  AGENT_CONTEXT_BRIEF_EVENT,
  consumePendingBrief,
  clearPendingBrief,
  type ContextBriefNews,
} from '@/lib/agentBridge';

// V4 agent runs behind Caddy at agent.tradeul.com/v4/
const AGENT_BASE = process.env.NEXT_PUBLIC_AI_AGENT_V4_API_URL || 'https://agent.tradeul.com/v4';
const WS_BASE = AGENT_BASE.replace('https://', 'wss://').replace('http://', 'ws://');

// Timeouts — progress/keepalive events reset the activity clock.
const REQUEST_TIMEOUT_MS = 600000;  // 10 min hard cap
const ACTIVITY_TIMEOUT_MS = 90000;  // 90s inactivity for normal graph runs
// Context briefs (Opus) routinely take 45–180s; the server HTTP timeout is 240s.
const BRIEF_ACTIVITY_TIMEOUT_MS = 300000;

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
  backtest: 'Backtester',
  synthesizer: 'Synthesizer',
  dilution: 'Dilution Tracker',
  strategy_scanner: 'Strategy Scanner',
  alert_compiler: 'Alert Compiler',
  alert_manager: 'Alert Manager',
  context_enricher: 'Context',
  context_brief: 'Contexto Fundamental',
};

function generateSessionId(): string {
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

interface UseAIAgentOptions {
  onMarketUpdate?: (session: string) => void;
}

interface PendingRequest {
  messageId: string;
  assistantMsgId: string;
  content: string;
  sentAt: number;
  threadId: string;
  mode?: 'auto' | 'context_brief';
}

export function useAIAgent(options: UseAIAgentOptions = {}) {
  const { getToken } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [resultBlocks, setResultBlocks] = useState<ResultBlockData[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [marketContext, setMarketContext] = useState<MarketContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chartContext, setChartContext] = useState<ChartContext | null>(null);
  // Avoid SSR/client hydration mismatch from Date.now()/Math.random.
  const [sessionId, setSessionId] = useState<string>('');
  useEffect(() => {
    setSessionId(prev => prev || generateSessionId());
  }, []);

  const activeChartRef = useRef<{ ticker: string; interval: string; range: string } | null>(null);
  // Si el hilo actual es un "Brief de Contexto", guardamos la noticia para que
  // los follow-ups vayan al mismo motor (context_brief) con su contexto.
  const contextNewsRef = useRef<ContextBriefNews | null>(null);
  const pendingContextRef = useRef<ContextBriefNews | null>(null);

  const MAX_MESSAGES = 200;
  const MAX_RESULT_BLOCKS = 100;

  const wsRef = useRef<WebSocket | null>(null);
  const clientIdRef = useRef<string>(`agent-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  const currentMessageIdRef = useRef<string | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const optionsRef = useRef(options);
  const isConnectingRef = useRef(false);
  const retryTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const pendingRequestRef = useRef<PendingRequest | null>(null);
  const requestTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const activityTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastActivityRef = useRef<number>(0);
  const nodeStartTimesRef = useRef<Record<string, number>>({});
  const completedMsgIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  // REQUEST LIFECYCLE MANAGEMENT

  const tryRecoverBriefFromMemory = useCallback(async (pending: PendingRequest) => {
    // El brief se persiste en Redis aunque el socket se caiga. Si el timeout
    // dispara, recuperamos el último turn del hilo en vez de mostrar error vacío.
    try {
      const token = await getToken({ skipCache: true });
      if (!token) return false;
      const res = await fetch(
        `${AGENT_BASE}/api/sessions/${encodeURIComponent(pending.threadId)}/messages?limit=5`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) return false;
      const data = await res.json();
      const msgs: Array<{ query?: string; response?: string; timestamp?: number }> = data.messages || [];
      // Match by query fragment or take the newest response after we sent.
      const sentAtSec = pending.sentAt / 1000;
      const hit = [...msgs].reverse().find(m =>
        !!m.response
        && (m.timestamp || 0) >= sentAtSec - 5
        && (
          !pending.content
          || (m.query || '').includes(pending.content.slice(0, 80).replace(/^Contexto de la noticia:\s*"?/, '').slice(0, 60))
          || pending.content.includes((m.query || '').slice(0, 60))
        ),
      ) || [...msgs].reverse().find(m => !!m.response && (m.timestamp || 0) >= sentAtSec - 5);
      if (!hit?.response) return false;

      const response = hit.response;
      const lateId = pending.assistantMsgId;
      setMessages(prev => prev.map(m =>
        m.id === lateId || (m.status === 'thinking' || m.status === 'error')
          ? { ...m, id: lateId, content: response, status: 'complete' as const }
          : m,
      ));
      setResultBlocks(prev => {
        const without = prev.filter(b => b.messageId !== lateId);
        return [...without.slice(-(MAX_RESULT_BLOCKS - 1)), {
          id: `${lateId}-response`,
          messageId: lateId,
          query: pending.content,
          title: 'Analysis',
          status: 'success' as const,
          code: '',
          codeVisible: false,
          result: {
            success: true,
            code: '',
            outputs: [{ type: 'research', title: 'AI Analysis', content: response }] as any,
            execution_time_ms: 0,
            timestamp: new Date().toISOString(),
          },
          timestamp: new Date(),
        }];
      });
      return true;
    } catch {
      return false;
    }
  }, [getToken]);

  const cancelPendingRequest = useCallback((reason: 'timeout' | 'disconnect' | 'error') => {
    const pending = pendingRequestRef.current;
    if (!pending) return;

    // Briefs: no mates la UI todavía — el servidor suele terminar y dejar el
    // resultado en memoria. Intentamos recuperarlo antes de mostrar error.
    if (reason === 'timeout' && pending.mode === 'context_brief') {
      const snapshot = pending;
      pendingRequestRef.current = null;
      if (requestTimeoutRef.current) { clearTimeout(requestTimeoutRef.current); requestTimeoutRef.current = null; }
      if (activityTimeoutRef.current) { clearTimeout(activityTimeoutRef.current); activityTimeoutRef.current = null; }

      setMessages(prev => prev.map(m =>
        m.id === snapshot.assistantMsgId
          ? { ...m, content: i18n.t('aiAgent.recoveringBrief'), status: 'thinking' as const }
          : m,
      ));

      void (async () => {
        // Unos segundos extra: el backend reintenta entregar al socket nuevo.
        for (let i = 0; i < 4; i++) {
          await new Promise(r => setTimeout(r, 2500));
          if (completedMsgIdsRef.current.has(snapshot.assistantMsgId)) {
            setIsLoading(false);
            return;
          }
          if (await tryRecoverBriefFromMemory(snapshot)) {
            completedMsgIdsRef.current.add(snapshot.assistantMsgId);
            currentMessageIdRef.current = null;
            nodeStartTimesRef.current = {};
            setIsLoading(false);
            return;
          }
        }
        if (completedMsgIdsRef.current.has(snapshot.assistantMsgId)) {
          setIsLoading(false);
          return;
        }
        setMessages(prev => prev.map(m =>
          m.id === snapshot.assistantMsgId || m.status === 'thinking'
            ? {
                ...m,
                status: 'error' as const,
                content: i18n.t('aiAgent.errors.briefSlow'),
              }
            : m,
        ));
        currentMessageIdRef.current = null;
        nodeStartTimesRef.current = {};
        setIsLoading(false);
      })();
      return;
    }

    const errorMessages: Record<string, string> = {
      timeout: i18n.t('aiAgent.errors.timeout'),
      disconnect: i18n.t('aiAgent.errors.disconnect'),
      error: i18n.t('aiAgent.errors.processFailed'),
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

    if (requestTimeoutRef.current) { clearTimeout(requestTimeoutRef.current); requestTimeoutRef.current = null; }
    if (activityTimeoutRef.current) { clearTimeout(activityTimeoutRef.current); activityTimeoutRef.current = null; }
  }, [tryRecoverBriefFromMemory]);

  const resetActivityTimeout = useCallback(() => {
    lastActivityRef.current = Date.now();
    if (activityTimeoutRef.current) clearTimeout(activityTimeoutRef.current);
    if (pendingRequestRef.current) {
      const limit = pendingRequestRef.current.mode === 'context_brief'
        ? BRIEF_ACTIVITY_TIMEOUT_MS
        : ACTIVITY_TIMEOUT_MS;
      activityTimeoutRef.current = setTimeout(() => {
        cancelPendingRequest('timeout');
      }, limit);
    }
  }, [cancelPendingRequest]);

  const completeRequest = useCallback(() => {
    pendingRequestRef.current = null;
    nodeStartTimesRef.current = {};
    if (requestTimeoutRef.current) { clearTimeout(requestTimeoutRef.current); requestTimeoutRef.current = null; }
    if (activityTimeoutRef.current) { clearTimeout(activityTimeoutRef.current); activityTimeoutRef.current = null; }
  }, []);

  // V4 PROTOCOL HANDLER

  const handleWSMessage = useCallback((event: MessageEvent) => {
    resetActivityTimeout();
    try {
      const data = JSON.parse(event.data);
      const pending = pendingRequestRef.current;

      switch (data.type) {
        case 'ack': {
          if (pending) {
            const assistantId = pending.assistantMsgId;
            currentMessageIdRef.current = assistantId;
            const runId = typeof data.run_id === 'string' ? data.run_id : undefined;
            setMessages(prev => [...prev, {
              id: assistantId,
              role: 'assistant',
              content: '',
              timestamp: new Date(),
              status: 'thinking',
              steps: [],
              thinkingStartTime: Date.now(),
              runId,
            }]);
          }
          break;
        }

        case 'node_started': {
          const nodeName = data.node as string;
          const msgId = currentMessageIdRef.current;
          if (!msgId) break;
          // Brief→graph handoff: a graph node fired on a thread the client had
          // pinned to context_brief. The server routed a live-data follow-up to
          // the full agent, so graduate the thread to normal mode — otherwise
          // later follow-ups keep forcing context_brief and timeout-recovery
          // could surface the stale brief instead of this run's answer.
          if (nodeName !== 'context_brief' && pendingRequestRef.current?.mode === 'context_brief') {
            pendingRequestRef.current.mode = 'auto';
            contextNewsRef.current = null;
            resetActivityTimeout();
          }
          nodeStartTimesRef.current[nodeName] = data.timestamp || Date.now() / 1000;
          const step: AgentStep = {
            id: `step-${nodeName}`,
            type: nodeName === 'supervisor' ? 'reasoning' : 'tool',
            title: NODE_LABELS[nodeName] || nodeName,
            status: 'running',
            icon: nodeName === 'supervisor' ? 'brain' : 'zap',
          };
          setMessages(prev => prev.map(m =>
            m.id === msgId ? { ...m, steps: [...(m.steps || []), step] } : m
          ));
          break;
        }

        case 'node_completed': {
          const nodeName = data.node as string;
          const msgId = currentMessageIdRef.current;
          if (!msgId) break;
          const elapsed = data.elapsed_ms ? data.elapsed_ms / 1000 : 0;
          const preview = data.preview as string || '';
          const cardData = data.data as AgentStep['data'] | undefined;
          // Referencia a artifacts completos persistidos (inspector de nodo)
          const artRaw = data.artifacts as { run_id?: string; kinds?: string[]; count?: number } | undefined;
          const artifacts = artRaw?.run_id
            ? { runId: artRaw.run_id, kinds: artRaw.kinds || [], count: artRaw.count || 0 }
            : undefined;
          setMessages(prev => prev.map(m =>
            m.id === msgId
              ? {
                ...m,
                steps: (m.steps || []).map(s =>
                  s.id === `step-${nodeName}`
                    ? { ...s, status: 'complete' as const, duration: elapsed, description: preview || undefined, data: cardData, artifacts }
                    : s
                )
              }
              : m
          ));
          break;
        }

        // El agente monta un paso interno de su workflow en vivo (upsert por id)
        case 'canvas_step': {
          const nodeName = data.node as string;
          const msgId = currentMessageIdRef.current;
          if (!msgId) break;
          const artRaw = data.artifacts as { run_id?: string; kinds?: string[]; count?: number } | undefined;
          const artifacts = artRaw?.run_id
            ? { runId: artRaw.run_id, kinds: artRaw.kinds || [], count: artRaw.count || 0 }
            : undefined;
          const substep = {
            id: data.step_id as string,
            title: (data.title as string) || '',
            subtitle: (data.subtitle as string) || undefined,
            status: (data.status as 'running' | 'complete' | 'error') || 'running',
            durationMs: (data.duration_ms as number) || undefined,
            blocks: (data.blocks as unknown[]) || [],
            ...(artifacts ? { artifacts } : {}),
          };
          setMessages(prev => prev.map(m => {
            if (m.id !== msgId) return m;
            return {
              ...m,
              steps: (m.steps || []).map(s => {
                if (s.id !== `step-${nodeName}`) return s;
                const subs = [...(s.substeps || [])];
                const idx = subs.findIndex(x => x.id === substep.id);
                if (idx !== -1) {
                  // Preserve previous artifacts if this update is still "running"
                  const prevArt = subs[idx].artifacts;
                  subs[idx] = { ...subs[idx], ...substep, artifacts: substep.artifacts || prevArt };
                } else {
                  subs.push(substep);
                }
                return { ...s, substeps: subs };
              }),
            };
          }));
          break;
        }

        // Protocolo unificado (backend emite además de los legacy). Ignorado
        // aquí: los handlers legacy ya actualizan el estado del canvas.
        case 'node_update':
          break;

        case 'agent_progress': {
          const msgId = currentMessageIdRef.current;
          if (!msgId) break;
          const progressMsg = data.message as string || '';
          setMessages(prev => prev.map(m => {
            if (m.id !== msgId) return m;
            const steps = m.steps || [];
            const runningIdx = steps.findIndex(s => s.status === 'running');
            if (runningIdx === -1) return m;
            const updated = [...steps];
            updated[runningIdx] = { ...updated[runningIdx], description: progressMsg };
            return { ...m, steps: updated };
          }));
          break;
        }

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
                steps: (m.steps || []).map(s => ({ ...s, status: 'complete' as const })),
              }
              : m
          ));
          setIsLoading(false);
          currentMessageIdRef.current = null;
          completeRequest();
          break;
        }

        case 'final_response': {
          const msgId = currentMessageIdRef.current;
          const response = data.response as string || '';

          // Belt-and-suspenders handoff un-stick: if the server served this
          // turn through the graph (metadata.mode != context_brief) while the
          // thread was still pinned to brief mode, graduate it to normal mode.
          const servedMode = (data.metadata as { mode?: string } | undefined)?.mode;
          if (servedMode && servedMode !== 'context_brief' && contextNewsRef.current) {
            contextNewsRef.current = null;
          }

          // Respuesta tardía: el socket se cayó (pestaña en background) y el
          // servidor la entrega en la reconexión. La petición ya fue cancelada
          // (msgId=null), así que reemplazamos el mensaje de error de conexión
          // o añadimos uno nuevo, en vez de descartarla. IMPORTANTE: hay que
          // crear también el ResultBlock — la UI de mensajes completados solo
          // renderiza bloques, no message.content.
          if (!msgId) {
            if (!response) break;
            if (data.thread_id && data.thread_id !== sessionId) break;
            const lateId = `late-${Date.now()}`;
            completedMsgIdsRef.current.add(lateId);
            setMessages(prev => {
              const revIdx = [...prev].reverse().findIndex(
                m => m.role === 'assistant' && (m.status === 'error' || m.status === 'thinking')
              );
              if (revIdx !== -1) {
                const realIdx = prev.length - 1 - revIdx;
                const oldId = prev[realIdx].id;
                completedMsgIdsRef.current.add(oldId);
                return prev.map((m, i) =>
                  i === realIdx
                    ? { ...m, id: lateId, content: response, status: 'complete' as const }
                    : m
                );
              }
              return [...prev, {
                id: lateId,
                role: 'assistant' as const,
                content: response,
                timestamp: new Date(),
                status: 'complete' as const,
              }];
            });
            const lateStructured = data.structured_response as Record<string, unknown> | undefined;
            setResultBlocks(prev => [...prev.slice(-(MAX_RESULT_BLOCKS - 1)), {
              id: `${lateId}-response`,
              messageId: lateId,
              query: '',
              title: 'Analysis',
              status: 'success' as const,
              code: '',
              codeVisible: false,
              result: {
                success: true,
                code: '',
                outputs: [{ type: 'research', title: 'AI Analysis', content: response, structured_response: lateStructured }] as any,
                execution_time_ms: data.metadata?.total_elapsed_ms || 0,
                timestamp: new Date().toISOString(),
              },
              timestamp: new Date(),
            }]);
            setIsLoading(false);
            completeRequest();
            break;
          }
          const totalMs = data.metadata?.total_elapsed_ms;
          const suggestedQuestions = (data.suggested_questions as string[]) || [];

          completedMsgIdsRef.current.add(msgId);
          setMessages(prev => prev.map(m =>
            m.id === msgId
              ? {
                ...m,
                content: response,
                status: 'complete',
                suggestedQuestions: suggestedQuestions.length > 0 ? suggestedQuestions : undefined,
              }
              : m
          ));
          setMessages(prev => prev.length > MAX_MESSAGES ? prev.slice(-MAX_MESSAGES) : prev);

          if (response) {
            const blockId = `${msgId}-response`;
            const userQuery = pendingRequestRef.current?.content || '';
            const structuredOutputs = data.outputs as Array<{type: string; [k: string]: unknown}> | undefined;
            const structuredResponse = data.structured_response as Record<string, unknown> | undefined;
            const outputs: Array<{type: string; title: string; [k: string]: unknown}> = [];

            if (structuredOutputs && structuredOutputs.length > 0) {
              for (const so of structuredOutputs) { outputs.push(so as any); }
              if (response.trim()) {
                outputs.push({ type: 'research' as const, title: 'AI Analysis', content: response, structured_response: structuredResponse });
              }
            } else {
              outputs.push({ type: 'research' as const, title: 'AI Analysis', content: response, structured_response: structuredResponse });
            }

            setResultBlocks(prev => [...prev.slice(-(MAX_RESULT_BLOCKS - 1)), {
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
                outputs: outputs as any,
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

        case 'error': {
          const msgId = currentMessageIdRef.current;
          const errorMsg = data.message as string || i18n.t('aiAgent.errors.unknown');
          const lowerErr = errorMsg.toLowerCase();
          const isRateLimit = ['429', 'rate limit', 'resource exhausted', 'too many requests', 'quota'].some(k => lowerErr.includes(k));

          if (isRateLimit) {
            const retryCount = (data._retryCount as number) || 0;
            const maxAutoRetries = 2;
            if (retryCount < maxAutoRetries && pendingRequestRef.current) {
              const retryDelay = Math.min(3000 * Math.pow(2, retryCount) + Math.random() * 2000, 15000);
              const pending = pendingRequestRef.current;
              if (msgId) {
                setMessages(prev => prev.map(m =>
                  m.id === msgId
                    ? { ...m, content: `Servidor ocupado, reintentando en ${Math.round(retryDelay / 1000)}s...` }
                    : m
                ));
              }
              retryTimeoutRef.current = setTimeout(() => {
                retryTimeoutRef.current = null;
                if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
                const payload: Record<string, unknown> = {
                  query: pending.content,
                  thread_id: sessionId,
                  mode: 'auto',
                  _retryCount: retryCount + 1,
                };
                wsRef.current.send(JSON.stringify(payload));
              }, retryDelay);
              break;
            }
          }

          const friendlyMsg = isRateLimit
            ? i18n.t('aiAgent.errors.saturated')
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
          break;
      }
    } catch (e) {
      console.error('Error parsing WS message:', e);
    }
  }, [resetActivityTimeout, completeRequest, sessionId]);

  // WEBSOCKET CONNECTION

  const connect = useCallback(async () => {
    if (isConnectingRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    if (wsRef.current?.readyState === WebSocket.CONNECTING) return;

    isConnectingRef.current = true;

    // Siempre token fresco: los JWT de Clerk duran ~60s; un token cacheado
    // es la causa #1 de "WebSocket connection failed" tras un blip.
    let token: string | null = null;
    try {
      token = await getToken({ skipCache: true });
    } catch {
      token = null;
    }
    if (!token) {
      isConnectingRef.current = false;
      setIsConnected(false);
      // Solo bloquear si no hay sesión; durante reconnects silenciamos.
      if (reconnectAttemptsRef.current === 0) {
        setError(i18n.t('aiAgent.errors.signIn'));
      }
      return;
    }

    const wsUrl = `${WS_BASE}/ws/chat/${clientIdRef.current}?token=${encodeURIComponent(token)}`;
    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl);
    } catch {
      isConnectingRef.current = false;
      return;
    }

    ws.onopen = () => {
      isConnectingRef.current = false;
      reconnectAttemptsRef.current = 0;
      setIsConnected(true);
      setError(null);
    };

    ws.onmessage = handleWSMessage;

    ws.onclose = () => {
      setIsConnected(false);
      isConnectingRef.current = false;
      wsRef.current = null;
      // NO cancelamos la petición pendiente: el servidor sigue ejecutando y
      // entregará el final_response al socket reconectado (_ACTIVE_SOCKETS).
      if (pendingRequestRef.current) {
        resetActivityTimeout();
      }
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      const attempt = reconnectAttemptsRef.current;
      // Con petición en curso: reconectar casi al instante (deploy/502).
      // Sin petición: backoff, pero nunca dejar de intentar.
      const delay = pendingRequestRef.current
        ? Math.min(200 * Math.pow(2, attempt), 3000)
        : Math.min(800 * Math.pow(2, attempt) + Math.random() * 400, 15000);
      reconnectAttemptsRef.current = attempt + 1;
      // Tras muchos fallos, avisar sin gritar en cada intento.
      if (attempt >= 3) {
        setError(i18n.t('aiAgent.reconnectingAgent'));
      }
      reconnectTimeoutRef.current = setTimeout(() => { connect(); }, delay);
    };

    // No setError aquí: onclose gestiona el retry. console.error en cada
    // intento llenaba la consola y parecía un fallo permanente.
    ws.onerror = () => {
      isConnectingRef.current = false;
    };

    wsRef.current = ws;
  }, [handleWSMessage, resetActivityTimeout, getToken]);

  /** Espera a tener WS OPEN (reconecta si hace falta). */
  const ensureConnected = useCallback(async (timeoutMs = 8000): Promise<boolean> => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return true;
    await connect();
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (wsRef.current?.readyState === WebSocket.OPEN) return true;
      await new Promise(r => setTimeout(r, 150));
    }
    return wsRef.current?.readyState === WebSocket.OPEN;
  }, [connect]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) { clearTimeout(reconnectTimeoutRef.current); reconnectTimeoutRef.current = null; }
    if (requestTimeoutRef.current) { clearTimeout(requestTimeoutRef.current); requestTimeoutRef.current = null; }
    if (activityTimeoutRef.current) { clearTimeout(activityTimeoutRef.current); activityTimeoutRef.current = null; }
    if (retryTimeoutRef.current) { clearTimeout(retryTimeoutRef.current); retryTimeoutRef.current = null; }
    pendingRequestRef.current = null;
    nodeStartTimesRef.current = {};
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    setIsConnected(false);
    setIsLoading(false);
    isConnectingRef.current = false;
  }, []);

  // SEND MESSAGE (V4 protocol) — uses persistent sessionId as thread_id

  const sendMessage = useCallback(async (content: string, chartCtx?: ChartContext | null) => {
    if (!content.trim()) return;
    if (!(await ensureConnected())) {
      setError('No se pudo conectar al agente. Reintentando…');
      connect();
      return;
    }
    if (pendingRequestRef.current) cancelPendingRequest('error');

    const now = Date.now();
    const messageId = `user-${now}`;
    const assistantMsgId = `assistant-${now}`;
    // sessionId se hidrata en useEffect; si aún está vacío, genera uno aquí.
    const threadId = sessionId || generateSessionId();
    if (!sessionId) setSessionId(threadId);

    const userMessage: Message = {
      id: messageId,
      role: 'user',
      content: content.trim(),
      timestamp: new Date()
    };
    setMessages(prev => [
      ...prev.map(m => m.status === 'clarification' ? { ...m, status: 'complete' as const } : m),
      userMessage,
    ]);
    setIsLoading(true);
    setError(null);

    pendingRequestRef.current = {
      messageId, assistantMsgId, content: content.trim(), sentAt: now,
      threadId, mode: 'auto',
    };
    lastActivityRef.current = now;
    nodeStartTimesRef.current = {};

    requestTimeoutRef.current = setTimeout(() => { cancelPendingRequest('timeout'); }, REQUEST_TIMEOUT_MS);
    activityTimeoutRef.current = setTimeout(() => { cancelPendingRequest('timeout'); }, ACTIVITY_TIMEOUT_MS);

    let ctxToSend = chartCtx ?? chartContext;

    if (!ctxToSend && activeChartRef.current) {
      const activeTicker = activeChartRef.current.ticker.toUpperCase();
      const upperContent = content.toUpperCase();
      if (upperContent.includes(activeTicker) || upperContent.includes(`$${activeTicker}`)) {
        ctxToSend = {
          ticker: activeChartRef.current.ticker,
          interval: activeChartRef.current.interval,
          range: activeChartRef.current.range,
          activeIndicators: [],
          currentPrice: null,
          snapshot: { recentBars: [], indicators: {}, levels: [], visibleDateRange: { from: 0, to: 0 }, isHistorical: false },
          targetCandle: null,
        };
      }
    }

    // Use the persistent sessionId as thread_id for conversation continuity
    const payload: Record<string, unknown> = { query: content.trim(), thread_id: threadId, mode: 'auto' };
    // Si estamos en un hilo de Brief de Contexto, los follow-ups van al mismo motor.
    if (contextNewsRef.current) {
      payload.mode = 'context_brief';
      payload.news_context = contextNewsRef.current;
      pendingRequestRef.current = {
        ...pendingRequestRef.current!,
        mode: 'context_brief',
      };
      if (activityTimeoutRef.current) clearTimeout(activityTimeoutRef.current);
      activityTimeoutRef.current = setTimeout(() => { cancelPendingRequest('timeout'); }, BRIEF_ACTIVITY_TIMEOUT_MS);
    }
    if (ctxToSend) { payload.chart_context = ctxToSend; setChartContext(null); }
    wsRef.current?.send(JSON.stringify(payload));
  }, [cancelPendingRequest, chartContext, sessionId, ensureConnected, connect]);

  // SEND CONTEXT BRIEF — abre un hilo NUEVO para una noticia (Opus 4.8 + tools)
  const sendContextBrief = useCallback(async (news: ContextBriefNews) => {
    if (!(await ensureConnected())) {
      pendingContextRef.current = news;
      setError(i18n.t('aiAgent.reconnectingBrief'));
      connect();
      return;
    }
    if (pendingRequestRef.current) cancelPendingRequest('error');

    const newSession = generateSessionId();
    setSessionId(newSession);
    contextNewsRef.current = {
      text: news.text,
      tickers: news.tickers || [],
      created_at: news.created_at,
      received_at: news.received_at,
      id: news.id,
    };

    const now = Date.now();
    const messageId = `user-${now}`;
    const assistantMsgId = `assistant-${now}`;
    const label = `Contexto de la noticia: "${news.text.slice(0, 160)}${news.text.length > 160 ? '…' : ''}"`;

    // Hilo fresco
    setResultBlocks([]);
    setMessages([{ id: messageId, role: 'user', content: label, timestamp: new Date() }]);
    setIsLoading(true);
    setError(null);

    pendingRequestRef.current = {
      messageId, assistantMsgId, content: label, sentAt: now,
      threadId: newSession, mode: 'context_brief',
    };
    lastActivityRef.current = now;
    nodeStartTimesRef.current = {};
    requestTimeoutRef.current = setTimeout(() => { cancelPendingRequest('timeout'); }, REQUEST_TIMEOUT_MS);
    activityTimeoutRef.current = setTimeout(() => { cancelPendingRequest('timeout'); }, BRIEF_ACTIVITY_TIMEOUT_MS);

    wsRef.current?.send(JSON.stringify({
      query: news.text.slice(0, 400),
      thread_id: newSession,
      mode: 'context_brief',
      news_context: contextNewsRef.current,
    }));
  }, [cancelPendingRequest, ensureConnected, connect]);

  const triggerContextBrief = useCallback((news: ContextBriefNews) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      void sendContextBrief(news);
    } else {
      pendingContextRef.current = news;  // se enviará al conectar
      void ensureConnected().then(ok => {
        if (ok && pendingContextRef.current === news) {
          const n = pendingContextRef.current;
          pendingContextRef.current = null;
          void sendContextBrief(n);
        }
      });
    }
  }, [sendContextBrief, ensureConnected]);

  const sendClarificationChoice = useCallback(async (originalQuery: string, rewrite: string) => {
    if (!(await ensureConnected())) {
      setError('No se pudo conectar al agente. Reintentando…');
      connect();
      return;
    }
    if (pendingRequestRef.current) cancelPendingRequest('error');

    const now = Date.now();
    const messageId = `user-${now}`;
    const assistantMsgId = `assistant-${now}`;
    const threadId = sessionId || generateSessionId();
    if (!sessionId) setSessionId(threadId);

    setIsLoading(true);
    setError(null);

    pendingRequestRef.current = {
      messageId, assistantMsgId, content: originalQuery, sentAt: now,
      threadId, mode: 'auto',
    };
    lastActivityRef.current = now;
    nodeStartTimesRef.current = {};

    requestTimeoutRef.current = setTimeout(() => { cancelPendingRequest('timeout'); }, REQUEST_TIMEOUT_MS);
    activityTimeoutRef.current = setTimeout(() => { cancelPendingRequest('timeout'); }, ACTIVITY_TIMEOUT_MS);

    wsRef.current?.send(JSON.stringify({
      query: originalQuery,
      thread_id: threadId,
      mode: 'auto',
      clarification_hint: rewrite,
    }));
  }, [cancelPendingRequest, sessionId, ensureConnected, connect]);

  const clearHistory = useCallback(() => {
    setMessages([]);
    setResultBlocks([]);
    setSessionId(generateSessionId());
    contextNewsRef.current = null;  // vuelve al agente normal
  }, []);

  // Load a past session — replaces current messages and sessionId
  const loadSession = useCallback((id: string, msgs: Message[], blocks: ResultBlockData[]) => {
    setSessionId(id);
    setMessages(msgs);
    setResultBlocks(blocks);
    setError(null);
  }, []);

  const toggleCodeVisibility = useCallback((blockId: string) => {
    setResultBlocks(prev => prev.map(b =>
      b.id === blockId ? { ...b, codeVisible: !b.codeVisible } : b
    ));
  }, []);

  // Auto-connect on mount
  useEffect(() => {
    connect();
    return () => { disconnect(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reconectar al volver a la pestaña / recuperar red (Chrome mata WS en background).
  useEffect(() => {
    const kick = () => {
      if (document.visibilityState === 'hidden') return;
      if (wsRef.current?.readyState === WebSocket.OPEN) return;
      reconnectAttemptsRef.current = 0;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      void connect();
    };
    document.addEventListener('visibilitychange', kick);
    window.addEventListener('online', kick);
    return () => {
      document.removeEventListener('visibilitychange', kick);
      window.removeEventListener('online', kick);
    };
  }, [connect]);

  // Listen for active chart broadcasts from TradingChart
  useEffect(() => {
    const handler = (e: CustomEvent<{ ticker: string; interval: string; range: string } | null>) => {
      activeChartRef.current = e.detail;
    };
    window.addEventListener('agent:chart-active', handler as EventListener);
    return () => window.removeEventListener('agent:chart-active', handler as EventListener);
  }, []);

  // Listen for context-brief requests (from OpenUL/News) when already mounted
  useEffect(() => {
    const handler = (e: CustomEvent<{ news: ContextBriefNews }>) => {
      clearPendingBrief();
      if (e.detail?.news) triggerContextBrief(e.detail.news);
    };
    window.addEventListener(AGENT_CONTEXT_BRIEF_EVENT, handler as EventListener);
    return () => window.removeEventListener(AGENT_CONTEXT_BRIEF_EVENT, handler as EventListener);
  }, [triggerContextBrief]);

  // On mount, consume any pending brief requested before the window existed
  useEffect(() => {
    const pending = consumePendingBrief();
    if (pending) pendingContextRef.current = pending;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Flush a queued context brief once the WS is connected
  useEffect(() => {
    if (isConnected && pendingContextRef.current) {
      const n = pendingContextRef.current;
      pendingContextRef.current = null;
      void sendContextBrief(n);
    }
  }, [isConnected, sendContextBrief]);

  // Heartbeat más agresivo con petición en curso (proxies + keepalive del servidor).
  useEffect(() => {
    const interval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        try {
          wsRef.current.send(JSON.stringify({ query: '', thread_id: '' }));
        } catch { /* noop */ }
      } else if (isLoading || pendingRequestRef.current) {
        // Socket muerto a mitad de un brief: forzar reconnect inmediato.
        reconnectAttemptsRef.current = 0;
        void connect();
      }
    }, isLoading ? 12000 : 40000);
    return () => clearInterval(interval);
  }, [isLoading, connect]);

  return {
    messages,
    resultBlocks,
    isConnected,
    isLoading,
    marketContext,
    error,
    chartContext,
    sessionId,
    sendMessage,
    setChartContext,
    sendClarificationChoice,
    clearHistory,
    loadSession,
    toggleCodeVisibility,
    connect,
    disconnect,
  };
}
