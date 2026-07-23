'use client';

import { memo, useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import dynamic from 'next/dynamic';
import { useTranslation } from 'react-i18next';
import { BellRing, History, Sparkles, Workflow } from 'lucide-react';

const LazyExecutionGraph = dynamic(
  () => import('./ExecutionGraph').then(m => m.ExecutionGraph),
  { ssr: false, loading: () => <div className="h-full min-h-[200px] bg-surface-hover rounded-lg animate-pulse" /> },
);
const LazyLiveWorkflowsCanvas = dynamic(
  () => import('./LiveWorkflowsCanvas').then(m => m.LiveWorkflowsCanvas),
  { ssr: false, loading: () => <div className="h-full min-h-[200px] bg-surface-hover rounded-lg animate-pulse" /> },
);
import { useAIAgent } from './useAIAgent';
import { NodeInspector, type InspectTarget } from './NodeInspector';
import { ResultBlock } from './ResultBlock';
import { SlashCommandMenu, useSlashCommands } from './SlashCommandMenu';
import { ConversationHistory } from './ConversationHistory';
import { useConversationHistory } from './useConversationHistory';
import type { SlashCommand } from './SlashCommandMenu';
import type { AgentStep, ChartContext, Message, ResultBlockData, ClarificationData, SessionMessage } from './types';
import { StepCard } from './StepCard';
import { useAIAlertFiresStore } from '@/stores/useAIAlertFiresStore';

const QUICK_ACTIONS = [
  { label: 'Top Gainers', query: 'top 50 gainers today' },
  { label: 'Sector Performance', query: 'sector performance today' },
  { label: 'Most Active', query: 'most active stocks by volume today' },
  { label: 'Gap Analysis', query: 'stocks gapping up more than 5% today' },
  { label: 'Unusual Volume', query: 'stocks with unusual volume today' },
];

// Alert recipes — one click compiles them through the full
// compile → dry-run → arm loop, so the empty state teaches the killer feature.
const ALERT_TEMPLATE_KEYS = [
  { labelKey: 'aiAgent.quickAlerts.vwapCross', queryKey: 'aiAgent.quickAlerts.vwapCrossQuery', hint: 'evento en vivo · todo el mercado' },
  { labelKey: 'aiAgent.quickAlerts.priceLevels', queryKey: 'aiAgent.quickAlerts.priceLevelsQuery', hint: 'niveles absolutos · 1 ticker' },
  { labelKey: 'aiAgent.quickAlerts.intradaySequence', queryKey: 'aiAgent.quickAlerts.intradaySequenceQuery', hint: 'secuencia A→B · CEP' },
  { labelKey: 'aiAgent.quickAlerts.enterRanking', queryKey: 'aiAgent.quickAlerts.enterRankingQuery', hint: 'membership · scanner' },
] as const;

interface TimelineEntry {
  userMessage: Message;
  assistantMessage?: Message;
  results: ResultBlockData[];
}

/* ================================================================
   MAIN COMPONENT
   ================================================================ */

interface AIAgentContentProps {
  onMarketUpdate?: (session: string) => void;
}

export const AIAgentContent = memo(function AIAgentContent({
  onMarketUpdate,
}: AIAgentContentProps) {
  const { t } = useTranslation();
  const {
    messages,
    resultBlocks,
    isConnected,
    isLoading,
    error,
    chartContext,
    sessionId,
    sendMessage,
    setChartContext,
    sendClarificationChoice,
    clearHistory,
    loadSession,
    toggleCodeVisibility,
  } = useAIAgent({ onMarketUpdate });

  const history = useConversationHistory();

  const [showPipeline, setShowPipeline] = useState(false);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isNearBottomRef = useRef(true);
  const [isNarrow, setIsNarrow] = useState(false);

  // ── Container width detection ──
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver(([entry]) => {
      setIsNarrow(entry.contentRect.width < 680);
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (isNarrow && showPipeline) setShowPipeline(false);
  }, [isNarrow, showPipeline]);

  // ── Auto-abrir el canvas al lanzar una consulta (salvo que el usuario lo cerrara) ──
  const userClosedCanvasRef = useRef(false);
  const prevLoadingRef = useRef(false);
  useEffect(() => {
    if (isLoading && !prevLoadingRef.current && !isNarrow && !userClosedCanvasRef.current) {
      setShowPipeline(true);
    }
    prevLoadingRef.current = isLoading;
  }, [isLoading, isNarrow]);

  // Abrir canvas + Mis workflows cuando un toast/comando pide "ver alertas"
  useEffect(() => {
    const onShowWorkflows = () => {
      userClosedCanvasRef.current = false;
      setShowPipeline(true);
    };
    window.addEventListener('tradeul:ai-agent-show-workflows', onShowWorkflows);
    window.addEventListener('tradeul:ai-alerts-changed', onShowWorkflows);
    return () => {
      window.removeEventListener('tradeul:ai-agent-show-workflows', onShowWorkflows);
      window.removeEventListener('tradeul:ai-alerts-changed', onShowWorkflows);
    };
  }, []);

  const togglePipeline = useCallback(() => {
    setShowPipeline(p => {
      if (p) userClosedCanvasRef.current = true;
      else userClosedCanvasRef.current = false;
      return !p;
    });
  }, []);

  // ── External event listeners ──
  useEffect(() => {
    const handler = (e: CustomEvent<{ message: string }>) => {
      if (e.detail?.message) sendMessage(e.detail.message);
    };
    window.addEventListener('agent:send', handler as EventListener);
    return () => window.removeEventListener('agent:send', handler as EventListener);
  }, [sendMessage]);

  useEffect(() => {
    const handler = (e: CustomEvent<{ chartContext: ChartContext; prompt: string }>) => {
      if (e.detail?.chartContext && e.detail?.prompt) {
        setChartContext(e.detail.chartContext);
        sendMessage(e.detail.prompt, e.detail.chartContext);
      }
    };
    window.addEventListener('agent:chart-ask', handler as EventListener);
    return () => window.removeEventListener('agent:chart-ask', handler as EventListener);
  }, [sendMessage, setChartContext]);

  // ── Smart scroll — only auto-scroll if user is near bottom ──
  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
  }, []);

  useEffect(() => {
    if (isNearBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, resultBlocks]);

  // ── Textarea auto-resize ──
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 120)}px`;
    }
  }, [input]);

  // ── Timeline construction ──
  const timeline = useMemo<TimelineEntry[]>(() => {
    const entries: TimelineEntry[] = [];
    let current: TimelineEntry | null = null;
    for (const msg of messages) {
      if (msg.role === 'user') {
        if (current) entries.push(current);
        current = { userMessage: msg, results: [] };
      } else if (msg.role === 'assistant' && current) {
        current.assistantMessage = msg;
        current.results = resultBlocks.filter(b => b.messageId === msg.id);
      }
    }
    if (current) entries.push(current);
    return entries;
  }, [messages, resultBlocks]);

  // ── Canvas de ejecución: en vivo por defecto, con replay de runs pasados ──
  // Por defecto muestra la última ejecución CON pasos (así no se queda en
  // blanco cuando llega un mensaje posterior sin pasos: aclaraciones, etc.).
  // El usuario puede FIJAR un run anterior desde su chip de pasos en el chat;
  // lanzar una consulta nueva vuelve automáticamente al directo.
  const [pinnedMsgId, setPinnedMsgId] = useState<string | null>(null);

  const latestStepsMsgId = useMemo(
    () => [...messages].reverse().find(m => m.role === 'assistant' && m.steps?.length)?.id ?? null,
    [messages],
  );

  const activeSteps = useMemo(() => {
    const sourceId = pinnedMsgId ?? latestStepsMsgId;
    const msg = sourceId ? messages.find(m => m.id === sourceId) : undefined;
    return msg?.steps || [];
  }, [messages, pinnedMsgId, latestStepsMsgId]);

  // Un run fijado que además es el último no es un replay: trátalo como directo.
  const isReplaying = pinnedMsgId !== null && pinnedMsgId !== latestStepsMsgId;

  // Etiqueta del replay: la pregunta del usuario que originó ese run.
  const pinnedQuery = useMemo(() => {
    if (!isReplaying) return null;
    const entry = timeline.find(e => e.assistantMessage?.id === pinnedMsgId);
    return entry?.userMessage.content ?? '';
  }, [isReplaying, pinnedMsgId, timeline]);

  const unpinRun = useCallback(() => setPinnedMsgId(null), []);

  const pinRun = useCallback((msgId: string) => {
    setPinnedMsgId(msgId);
    setShowPipeline(true);
    // El sidebar escucha este evento y salta a la pestaña de ejecución.
    window.dispatchEvent(new Event('tradeul:ai-agent-show-execution'));
  }, []);

  // Consulta nueva → volver al directo (cubre todos los caminos de envío).
  const wasLoadingRef = useRef(isLoading);
  useEffect(() => {
    if (isLoading && !wasLoadingRef.current) setPinnedMsgId(null);
    wasLoadingRef.current = isLoading;
  }, [isLoading]);

  // ── Submit handler ──
  const handleSubmit = useCallback((e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isLoading || !isConnected) return;
    sendMessage(input);
    setInput('');
    if (inputRef.current) inputRef.current.style.height = 'auto';
  }, [input, isLoading, isConnected, sendMessage]);

  // ── Slash commands ──
  const { slashActive, filtered: slashFiltered } = useSlashCommands(input);
  const [slashMenuOpen, setSlashMenuOpen] = useState(false);

  useEffect(() => {
    setSlashMenuOpen(slashActive && slashFiltered.length > 0);
  }, [slashActive, slashFiltered.length]);

  const handleSlashSelect = useCallback((cmd: SlashCommand) => {
    setInput(cmd.template);
    setSlashMenuOpen(false);
    inputRef.current?.focus();
  }, []);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (slashMenuOpen) return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit, slashMenuOpen]);

  const handleQuickAction = useCallback((query: string) => {
    if (isLoading || !isConnected) return;
    sendMessage(query);
  }, [isLoading, isConnected, sendMessage]);

  // ── Load session from history ──
  const handleSelectSession = useCallback(async (sid: string) => {
    if (sid === sessionId) {
      history.close();
      return;
    }

    const rawMessages = await history.loadSessionMessages(sid);
    if (!rawMessages.length) return;

    // Transform backend messages into Message[] + ResultBlockData[]
    const msgs: Message[] = [];
    const blocks: ResultBlockData[] = [];

    rawMessages.forEach((entry: SessionMessage, i: number) => {
      const ts = new Date(entry.timestamp * 1000);
      const userMsgId = `hist-user-${i}`;
      const assistantMsgId = `hist-assistant-${i}`;

      msgs.push({
        id: userMsgId,
        role: 'user',
        content: entry.query,
        timestamp: ts,
      });

      if (entry.response) {
        msgs.push({
          id: assistantMsgId,
          role: 'assistant',
          content: entry.response,
          timestamp: ts,
          status: 'complete',
        });

        blocks.push({
          id: `${assistantMsgId}-response`,
          messageId: assistantMsgId,
          query: entry.query,
          title: 'Analysis',
          status: 'success',
          code: '',
          codeVisible: false,
          result: {
            success: true,
            code: '',
            outputs: [{
              type: 'research',
              title: 'AI Analysis',
              content: entry.response,
              structured_response: entry.structured_response,
            }],
            execution_time_ms: 0,
            timestamp: ts.toISOString(),
          },
          timestamp: ts,
        });
      }
    });

    loadSession(sid, msgs, blocks);
    history.close();

    // Scroll to bottom after loading
    setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
    }, 100);
  }, [sessionId, history, loadSession]);

  const handleDeleteSession = useCallback(async (sid: string) => {
    await history.deleteSession(sid);
    // If we deleted the active session, start fresh
    if (sid === sessionId) {
      clearHistory();
    }
  }, [history, sessionId, clearHistory]);

  const handleNewSession = useCallback(() => {
    clearHistory();
    if (history.isOpen) history.fetchSessions();
  }, [clearHistory, history]);

  return (
    <div ref={containerRef} className="flex flex-col h-full w-full min-h-0 bg-surface overflow-hidden">
      <div className="flex-1 min-h-0 flex overflow-hidden relative">

        {/* CONVERSATION HISTORY SIDEBAR */}
        <AnimatePresence>
          {history.isOpen && (
            <ConversationHistory
              sessions={history.sessions}
              isLoading={history.isLoading}
              activeSessionId={sessionId}
              onSelectSession={handleSelectSession}
              onDeleteSession={handleDeleteSession}
              onClose={history.close}
            />
          )}
        </AnimatePresence>

        {/* CONVERSATION CANVAS */}
        <div className="flex-1 min-w-0 flex flex-col min-h-0">

          {/* HEADER — always visible */}
          <div className="flex-shrink-0 px-4 py-2 border-b border-border bg-surface/60 backdrop-blur-sm flex items-center justify-between">
            <div className="flex items-center gap-2">
              <button
                onClick={history.toggle}
                className={`p-1.5 rounded-lg transition-all ${history.isOpen ? 'bg-primary/10 text-primary' : 'text-muted-fg hover:text-foreground/80 hover:bg-surface-hover'}`}
                title={t('aiAgent.input.historyTitle')}
              >
                <History className="w-4 h-4" />
              </button>
              <span className="text-[12px] font-medium text-foreground">Chat</span>
            </div>
            <div className="flex items-center gap-3 text-[10px]">
              {messages.length > 0 && (
                <button onClick={handleNewSession} className="text-muted-fg hover:text-foreground/80 transition-colors">
                  {t('aiAgent.newSession')}
                </button>
              )}
              {!isNarrow && (
                <button
                  onClick={togglePipeline}
                  className={`transition-colors ${showPipeline ? 'text-foreground/80 font-medium' : 'text-muted-fg hover:text-foreground/80'}`}
                >
                  Canvas
                </button>
              )}
              <div className="flex items-center gap-1.5">
                <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-muted-fg/50 animate-pulse'}`} />
                <span className="text-muted-fg">{isConnected ? 'Live' : t('aiAgent.status.connecting')}</span>
              </div>
            </div>
          </div>

          {/* Scrollable conversation */}
          <div
            ref={scrollContainerRef}
            onScroll={handleScroll}
            className="flex-1 overflow-y-auto"
          >
            <div className="max-w-[780px] mx-auto px-4 py-3">

              {timeline.length === 0 && !isLoading ? (
                <EmptyState isConnected={isConnected} onQuickAction={handleQuickAction} isNarrow={isNarrow} onOpenHistory={history.toggle} />
              ) : (
                <div className="space-y-3">
                  {timeline.map((entry) => (
                    <TimelineItem
                      key={entry.userMessage.id}
                      entry={entry}
                      onClarificationChoice={sendClarificationChoice}
                      onToggleCode={toggleCodeVisibility}
                      onSendMessage={sendMessage}
                      onPinRun={pinRun}
                      pinnedMsgId={isReplaying ? pinnedMsgId : null}
                    />
                  ))}
                </div>
              )}

              {error && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-3 px-3 py-2 bg-red-500/10 border border-red-500/25 rounded-lg text-[11px] text-red-600 dark:text-red-400 max-w-[600px] mx-auto"
                >
                  {error}
                </motion.div>
              )}
              <div ref={messagesEndRef} className="h-4" />
            </div>
          </div>

          {/* INPUT BAR */}
          <div className="flex-shrink-0 border-t border-border bg-surface/80 backdrop-blur-xl">
            <div className="max-w-[860px] mx-auto px-5 py-2.5">

              {!isLoading && timeline.length <= 1 && (
                <div className="flex items-center gap-1 mb-2 text-[11px] flex-wrap">
                  {QUICK_ACTIONS.slice(0, isNarrow ? 2 : 4).map((a, i) => (
                    <span key={a.query} className="flex items-center gap-1">
                      {i > 0 && <span className="text-muted-fg/50">&middot;</span>}
                      <button
                        onClick={() => handleQuickAction(a.query)}
                        disabled={!isConnected}
                        className="text-muted-fg hover:text-primary transition-colors disabled:opacity-40"
                      >
                        {a.label}
                      </button>
                    </span>
                  ))}
                </div>
              )}

              {chartContext && (
                <ChartContextChip chartContext={chartContext} onClear={() => setChartContext(null)} />
              )}

              <form onSubmit={handleSubmit} className="relative flex items-end gap-2">
                <SlashCommandMenu
                  input={input}
                  visible={slashMenuOpen}
                  onSelect={handleSlashSelect}
                  onClose={() => setSlashMenuOpen(false)}
                  anchorRef={inputRef}
                />
                <div className="relative flex-1">
                  <textarea
                    ref={inputRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={isConnected ? t('aiAgent.input.placeholder') : t('aiAgent.status.connecting')}
                    disabled={!isConnected || isLoading}
                    rows={1}
                    className="w-full px-3.5 py-2.5 text-[13px] bg-surface-hover border border-border rounded-2xl text-foreground placeholder-muted-fg resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary disabled:opacity-50 transition-all"
                    style={{ maxHeight: '120px' }}
                  />
                  {input.startsWith('/backtest ') && (
                    <span className="absolute top-1 right-2 text-[8px] text-indigo-400 bg-indigo-500/10 px-1.5 py-0.5 rounded">
                      BACKTEST
                    </span>
                  )}
                </div>
                <button
                  type="submit"
                  disabled={!input.trim() || isLoading || !isConnected}
                  className="flex-shrink-0 px-3.5 py-2.5 text-[12px] font-medium text-muted-fg bg-surface-hover border border-border rounded-2xl hover:bg-surface-hover hover:text-foreground disabled:opacity-30 transition-all"
                >
                  {isLoading ? '···' : 'Enviar'}
                </button>
              </form>
            </div>
          </div>
        </div>

        {/* PIPELINE SIDEBAR */}
        <AnimatePresence>
          {showPipeline && !isNarrow && (
            <PipelineSidebar
              steps={activeSteps}
              isLoading={isLoading}
              replayQuery={pinnedQuery}
              onBackToLive={unpinRun}
            />
          )}
        </AnimatePresence>
      </div>
    </div>
  );
});

/* ================================================================
   EMPTY STATE
   ================================================================ */

const EmptyState = memo(function EmptyState({
  isConnected,
  onQuickAction,
  isNarrow,
  onOpenHistory,
}: {
  isConnected: boolean;
  onQuickAction: (q: string) => void;
  isNarrow: boolean;
  onOpenHistory: () => void;
}) {
  const { t } = useTranslation();
  const alertTemplates = ALERT_TEMPLATE_KEYS.map((tmpl) => ({
    label: t(tmpl.labelKey),
    query: t(tmpl.queryKey),
    hint: tmpl.hint,
  }));
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="flex flex-col items-center justify-center min-h-[40vh] text-center"
    >
      <h2 className={`font-semibold text-foreground mb-1.5 ${isNarrow ? 'text-[14px]' : 'text-[16px]'}`}>{t('aiAgent.emptyTitle')}</h2>
      <p className="text-[11px] text-muted-fg max-w-[340px] mb-5 leading-relaxed">
        {t('aiAgent.emptySubtitle')}
      </p>

      <div className={`w-full ${isNarrow ? 'max-w-[260px]' : 'max-w-[520px]'}`}>
        <div className="flex items-center gap-1.5 mb-2">
          <Sparkles className="w-3 h-3 text-muted-fg" />
          <span className="text-[9px] font-semibold uppercase tracking-wider text-muted-fg">{t('aiAgent.analyzeSection')}</span>
        </div>
        <div className={`grid gap-2 ${isNarrow ? 'grid-cols-1' : 'grid-cols-2'}`}>
          {QUICK_ACTIONS.slice(0, 4).map((action) => (
            <motion.button
              key={action.query}
              onClick={() => onQuickAction(action.query)}
              disabled={!isConnected}
              whileHover={{ y: -1 }}
              whileTap={{ scale: 0.98 }}
              className="px-3 py-2.5 bg-surface border border-border rounded-lg text-left hover:border-border hover:shadow-sm transition-all disabled:opacity-40"
            >
              <span className="text-[11px] font-medium text-foreground block">{action.label}</span>
              <span className="text-[9px] text-muted-fg block mt-0.5 truncate">{action.query}</span>
            </motion.button>
          ))}
        </div>

        <div className="flex items-center gap-1.5 mt-4 mb-2">
          <BellRing className="w-3 h-3 text-primary" />
          <span className="text-[9px] font-semibold uppercase tracking-wider text-muted-fg">
            {t('aiAgent.createAlertsSection')}
          </span>
        </div>
        <div className={`grid gap-2 ${isNarrow ? 'grid-cols-1' : 'grid-cols-2'}`}>
          {alertTemplates.map((tmpl) => (
            <motion.button
              key={tmpl.query}
              onClick={() => onQuickAction(tmpl.query)}
              disabled={!isConnected}
              whileHover={{ y: -1 }}
              whileTap={{ scale: 0.98 }}
              className="px-3 py-2.5 bg-primary/[0.03] border border-primary/20 rounded-lg text-left
                         hover:border-primary/40 hover:shadow-sm transition-all disabled:opacity-40"
            >
              <span className="text-[11px] font-medium text-foreground block">{tmpl.label}</span>
              <span className="text-[9px] text-muted-fg block mt-0.5 truncate">&ldquo;{tmpl.query}&rdquo;</span>
              <span className="text-[8px] text-primary/70 font-mono block mt-1">{tmpl.hint}</span>
            </motion.button>
          ))}
        </div>
      </div>

      <button
        onClick={onOpenHistory}
        className="mt-5 flex items-center gap-1.5 text-[10px] text-muted-fg hover:text-primary transition-colors"
      >
        <History className="w-3 h-3" />
        <span>{t('aiAgent.viewPastConversations')}</span>
      </button>
    </motion.div>
  );
});

/* ================================================================
   TIMELINE ITEM
   ================================================================ */

const TimelineItem = memo(function TimelineItem({
  entry,
  onClarificationChoice,
  onToggleCode,
  onSendMessage,
  onPinRun,
  pinnedMsgId,
}: {
  entry: TimelineEntry;
  onClarificationChoice: (oq: string, rw: string) => void;
  onToggleCode: (id: string) => void;
  onSendMessage: (msg: string) => void;
  onPinRun: (msgId: string) => void;
  pinnedMsgId: string | null;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="space-y-1.5"
    >
      <UserBubble message={entry.userMessage} />
      {entry.assistantMessage && (
        <AgentResponse
          message={entry.assistantMessage}
          results={entry.results}
          onClarificationChoice={onClarificationChoice}
          onToggleCode={onToggleCode}
          onSendMessage={onSendMessage}
          onPinRun={onPinRun}
          isPinned={pinnedMsgId === entry.assistantMessage.id}
        />
      )}
    </motion.div>
  );
});

/* ================================================================
   USER BUBBLE
   ================================================================ */

/** Locale clocks differ between SSR and client — only render after mount. */
function ClientClock({ date }: { date: Date }) {
  const [label, setLabel] = useState('');
  useEffect(() => {
    setLabel(date.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }));
  }, [date]);
  return (
    <span className="text-[9px] text-muted-fg/50 whitespace-nowrap flex-shrink-0 tabular-nums" suppressHydrationWarning>
      {label || '\u00a0\u00a0:\u00a0\u00a0'}
    </span>
  );
}

const UserBubble = memo(function UserBubble({ message }: { message: Message }) {
  return (
    <div className="flex justify-end">
      <div className="inline-flex items-baseline gap-2 bg-surface border border-border rounded-lg px-2.5 py-1.5 max-w-[80%]">
        <p className="text-[11px] text-foreground leading-normal">{message.content}</p>
        <ClientClock date={message.timestamp} />
      </div>
    </div>
  );
});

/* ================================================================
   AGENT RESPONSE — one unified card per response
   ================================================================ */

/* Resumen plegado de los pasos ya completados: menos ruido bajo cada respuesta */
const CollapsedSteps = memo(function CollapsedSteps({
  steps,
  onShowInCanvas,
  isPinned,
}: {
  steps: AgentStep[];
  onShowInCanvas?: () => void;
  isPinned?: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const totalS = steps.reduce((acc, s) => acc + (s.duration || 0), 0);
  const hasErr = steps.some(s => s.status === 'error');

  return (
    <div>
      <div className="flex items-center gap-1">
        <button
          onClick={() => setOpen(o => !o)}
          className="flex items-center gap-1.5 text-[9.5px] text-muted-fg hover:text-foreground/80 transition-colors py-0.5"
        >
          <span className={`transition-transform duration-200 inline-block ${open ? 'rotate-90' : ''}`}>›</span>
          <span className={hasErr ? 'text-red-400' : 'text-emerald-500'}>{hasErr ? '×' : '✓'}</span>
          <span>{steps.length} pasos</span>
          {totalS > 0 && <span className="tabular-nums font-mono">· {totalS < 1 ? `${Math.round(totalS * 1000)}ms` : `${totalS.toFixed(1)}s`}</span>}
        </button>
        {onShowInCanvas && (
          <button
            onClick={onShowInCanvas}
            title={t('aiAgent.steps.viewInCanvas')}
            aria-label={t('aiAgent.steps.viewInCanvas')}
            className={`p-0.5 rounded transition-colors ${
              isPinned
                ? 'text-primary bg-primary/10'
                : 'text-muted-fg/60 hover:text-primary hover:bg-primary/10'
            }`}
          >
            <Workflow className="w-3 h-3" />
          </button>
        )}
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="space-y-1 pt-1">
              {steps.map((step) => (
                <StepCard key={step.id} step={step} isLatest={false} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
});

const AgentResponse = memo(function AgentResponse({
  message,
  results,
  onClarificationChoice,
  onToggleCode,
  onSendMessage,
  onPinRun,
  isPinned,
}: {
  message: Message;
  results: ResultBlockData[];
  onClarificationChoice: (oq: string, rw: string) => void;
  onToggleCode: (id: string) => void;
  onSendMessage: (msg: string) => void;
  onPinRun?: (msgId: string) => void;
  isPinned?: boolean;
}) {
  const { t } = useTranslation();
  const isThinking = message.status === 'thinking';
  const isComplete = message.status === 'complete';
  const isError = message.status === 'error';
  const isClarification = message.status === 'clarification';
  const hasSteps = message.steps && message.steps.length > 0;
  const [thinkingSeconds, setThinkingSeconds] = useState(0);

  useEffect(() => {
    if (isThinking && message.thinkingStartTime) {
      const tick = () => setThinkingSeconds(Math.floor((Date.now() - message.thinkingStartTime!) / 1000));
      tick();
      const id = setInterval(tick, 1000);
      return () => clearInterval(id);
    }
  }, [isThinking, message.thinkingStartTime]);

  if (isThinking && !hasSteps) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="px-3 py-2 bg-surface border border-border rounded-lg"
      >
        <span className="text-[11px] text-muted-fg">
          {thinkingSeconds > 0
            ? t('aiAgent.status.analyzing', { seconds: thinkingSeconds })
            : t('aiAgent.status.startingAnalysis')}
        </span>
        <LoadingDots className="ml-2" />
      </motion.div>
    );
  }

  if (!isComplete && !isError && !isClarification && hasSteps) {
    const steps = message.steps!;

    return (
      <div className="space-y-1.5">
        {steps.map((step, i) => (
          <StepCard key={step.id} step={step} isLatest={i === steps.length - 1} />
        ))}
      </div>
    );
  }

  if (isClarification && message.clarification) {
    return (
      <ClarificationCard
        data={message.clarification}
        onChoose={onClarificationChoice}
        disabled={message.status !== 'clarification'}
      />
    );
  }

  if (isError) {
    return (
      <div className="px-3 py-2 bg-red-500/10 border border-red-500/25 rounded-lg text-[11px] text-red-600 dark:text-red-400">
        {message.content || t('aiAgent.errors.processFailed')}
      </div>
    );
  }

  if (isComplete && results.length > 0) {
    const execMs = results[0]?.result?.execution_time_ms;
    const ts = results[0]?.timestamp;
    const suggestions = message.suggestedQuestions;

    return (
      <div className="space-y-2">
        {/* Pasos completados: una línea discreta, expandible + replay en canvas */}
        {hasSteps && (
          <CollapsedSteps
            steps={message.steps!}
            onShowInCanvas={onPinRun ? () => onPinRun(message.id) : undefined}
            isPinned={isPinned}
          />
        )}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="bg-surface border border-border rounded-lg overflow-hidden"
        >
          <div className="p-3">
            {results.map((block) => (
              <ResultBlock key={block.id} block={block} onToggleCode={() => onToggleCode(block.id)} />
            ))}
          </div>
          <div className="px-3 py-1.5 border-t border-border-subtle flex items-center justify-end gap-2 text-[9px] text-muted-fg tabular-nums">
            {execMs != null && execMs > 0 && (
              <span>{execMs < 1000 ? `${execMs}ms` : `${(execMs / 1000).toFixed(1)}s`}</span>
            )}
            {ts && <ClientClock date={ts} />}
          </div>
        </motion.div>

        {suggestions && suggestions.length > 0 && (
          <FollowUpSuggestions suggestions={suggestions} onSelect={onSendMessage} />
        )}
      </div>
    );
  }

  if (isComplete) {
    return (
      <div className="px-3 py-2 bg-surface border border-border rounded-lg text-[11px] text-muted-fg">
        {t('aiAgent.analysisCompleted')}
      </div>
    );
  }

  return null;
});

/* ================================================================
   FOLLOW-UP SUGGESTIONS
   ================================================================ */

const FollowUpSuggestions = memo(function FollowUpSuggestions({
  suggestions,
  onSelect,
}: {
  suggestions: string[];
  onSelect: (q: string) => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.15 }}
      className="flex flex-col gap-1"
    >
      {suggestions.slice(0, 3).map((q, i) => (
        <button
          key={i}
          onClick={() => onSelect(q)}
          className="text-left px-2.5 py-1.5 text-[10px] text-muted-fg bg-surface border border-border rounded-lg hover:border-border hover:bg-surface-hover transition-all leading-snug"
        >
          {q}
        </button>
      ))}
    </motion.div>
  );
});

/* ================================================================
   LOADING DOTS
   ================================================================ */

const LoadingDots = memo(function LoadingDots({ className = '' }: { className?: string }) {
  return (
    <motion.span
      className={`inline-flex gap-[3px] align-middle ${className}`}
      animate={{ opacity: [0.3, 1, 0.3] }}
      transition={{ duration: 1.4, repeat: Infinity }}
    >
      <span className="w-[3px] h-[3px] rounded-full bg-muted-fg" />
      <span className="w-[3px] h-[3px] rounded-full bg-muted-fg" />
      <span className="w-[3px] h-[3px] rounded-full bg-muted-fg" />
    </motion.span>
  );
});

/* ================================================================
   CLARIFICATION CARD
   ================================================================ */

const ClarificationCard = memo(function ClarificationCard({
  data,
  onChoose,
  disabled,
}: {
  data: ClarificationData;
  onChoose: (oq: string, rw: string) => void;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  const [chosen, setChosen] = useState<number | null>(null);
  const [showCustom, setShowCustom] = useState(false);
  const [customText, setCustomText] = useState('');
  const customRef = useRef<HTMLInputElement>(null);
  const isLocked = disabled || chosen !== null;

  const pick = (idx: number, rewrite: string) => {
    if (isLocked) return;
    setChosen(idx);
    onChoose(data.originalQuery, rewrite);
  };

  const submitCustom = () => {
    if (isLocked || !customText.trim()) return;
    setChosen(-1);
    setShowCustom(false);
    onChoose(data.originalQuery, customText.trim());
  };

  if (disabled && chosen === null) {
    return (
      <div className="px-3 py-2 bg-surface border border-border rounded-lg text-[10px] text-muted-fg italic">
        {t('aiAgent.clarificationSkipped')}
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-surface border border-amber-500/25 rounded-lg p-3 space-y-2"
    >
      <p className="text-[11px] text-foreground leading-relaxed">{data.message}</p>

      <div className="space-y-1.5">
        {data.options.map((opt, idx) => {
          const sel = chosen === idx;
          const dim = isLocked && !sel;
          return (
            <button
              key={idx}
              onClick={() => pick(idx, opt.rewrite)}
              disabled={isLocked}
              className={`w-full text-left px-2.5 py-2 rounded-lg border text-[11px] leading-snug transition-all
                ${sel ? 'border-primary bg-primary/10 text-primary'
                  : dim ? 'border-border-subtle bg-surface-hover text-muted-fg/50 cursor-default'
                    : 'border-border bg-surface text-foreground hover:border-border hover:bg-surface-hover cursor-pointer'}`}
            >
              <span className="font-medium text-[11px] text-muted-fg mr-2">{String.fromCharCode(65 + idx)}.</span>
              {opt.label}
            </button>
          );
        })}

        {!showCustom && !isLocked && (
          <button
            onClick={() => { setShowCustom(true); setTimeout(() => customRef.current?.focus(), 50); }}
            className="w-full text-left px-2.5 py-2 rounded-lg border border-dashed border-border text-[11px] text-muted-fg hover:border-border hover:bg-surface-hover transition-all cursor-pointer"
          >
            Otra cosa...
          </button>
        )}

        {showCustom && !isLocked && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="flex gap-1.5">
            <input
              ref={customRef}
              value={customText}
              onChange={(e) => setCustomText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submitCustom()}
              placeholder={t('aiAgent.input.placeholderNeeds')}
              className="flex-1 px-2.5 py-1.5 text-[11px] border border-border rounded-lg text-foreground placeholder-muted-fg focus:outline-none focus:border-primary"
            />
            <button
              onClick={submitCustom}
              disabled={!customText.trim()}
              className="px-2.5 py-1.5 rounded-lg text-[11px] font-medium text-white bg-primary disabled:opacity-30 hover:bg-primary-hover transition-colors"
            >
              Enviar
            </button>
          </motion.div>
        )}

        {chosen === -1 && (
          <div className="px-2.5 py-1.5 rounded-lg border border-primary bg-primary/10 text-primary text-[11px]">
            {customText}
          </div>
        )}
      </div>

      {chosen !== null && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-1.5 text-[10px] text-primary">
          <LoadingDots />
          <span>Procesando...</span>
        </motion.div>
      )}
    </motion.div>
  );
});

/* ================================================================
   CHART CONTEXT CHIP
   ================================================================ */

const ChartContextChip = memo(function ChartContextChip({
  chartContext,
  onClear,
}: {
  chartContext: ChartContext;
  onClear: () => void;
}) {
  const snap = chartContext.snapshot;
  const fmt = (ts: number) => new Date(ts * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
  const from = snap.visibleDateRange?.from ? fmt(snap.visibleDateRange.from) : '';
  const to = snap.visibleDateRange?.to ? fmt(snap.visibleDateRange.to) : '';

  return (
    <div className="flex items-center gap-1.5 mb-1.5 px-2.5 py-1 bg-primary/10 border border-primary/30 rounded-lg text-[10px] flex-wrap">
      <span className="font-semibold text-primary">{chartContext.ticker}</span>
      <span className="text-primary font-medium">{chartContext.interval}</span>
      {from && to && <span className="text-primary">{from} &rarr; {to}</span>}
      <span className="text-muted-fg">({snap.recentBars?.length || 0} bars)</span>
      {chartContext.targetCandle && (
        <span className="text-primary font-medium">candle: {fmt(chartContext.targetCandle.date)}</span>
      )}
      {snap.isHistorical && (
        <span className="text-amber-600 dark:text-amber-400 font-semibold bg-amber-500/10 px-1.5 py-0.5 rounded">Historical</span>
      )}
      <button onClick={onClear} className="ml-auto text-primary hover:text-primary-hover text-[14px] leading-none font-light">
        &times;
      </button>
    </div>
  );
});

/* ================================================================
   PIPELINE SIDEBAR
   ================================================================ */

const PIPELINE_W_DEFAULT = 420;
const PIPELINE_W_MIN = 320;
const PIPELINE_W_MAX_RATIO = 0.72; // el canvas puede ocupar hasta ~3/4 de la ventana
const PIPELINE_W_KEY = 'tradeul.agent.canvasWidth';

type CanvasTab = 'execution' | 'workflows';

/* Estado del feed de disparos en el header de la pestaña Workflows. */
const LiveWorkflowsBadge = memo(function LiveWorkflowsBadge() {
  const { t } = useTranslation();
  const connected = useAIAlertFiresStore(s => s.connected);
  return (
    <div className="flex items-center gap-1.5">
      <span className="relative flex h-1.5 w-1.5">
        {connected && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
        )}
        <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${connected ? 'bg-emerald-400' : 'bg-red-400'}`} />
      </span>
      <span className={`text-[8.5px] font-semibold uppercase tracking-wider ${connected ? 'text-emerald-400' : 'text-red-400'}`}>
        {connected ? t('aiAgent.workflow.emitting') : t('aiAgent.workflow.offline')}
      </span>
    </div>
  );
});

const PipelineSidebar = memo(function PipelineSidebar({
  steps,
  isLoading,
  replayQuery,
  onBackToLive,
}: {
  steps: AgentStep[];
  isLoading: boolean;
  /** Pregunta del run fijado cuando el canvas muestra un replay (null = directo). */
  replayQuery: string | null;
  onBackToLive: () => void;
}) {
  const { t } = useTranslation();
  const completedCount = steps.filter(s => s.status === 'complete').length;
  const hasErrors = steps.some(s => s.status === 'error');
  const isProcessing = steps.some(s => s.status === 'running');

  // Inspector de nodo: clic en un nodo del canvas → modal con artifacts completos
  const [inspecting, setInspecting] = useState<InspectTarget | null>(null);
  const closeInspector = useCallback(() => setInspecting(null), []);
  const openInspector = useCallback((t: InspectTarget) => setInspecting(t), []);

  // Pestaña activa: la ejecución manda mientras corre una consulta; si el
  // usuario cambia a mano, se respeta hasta la siguiente consulta.
  const [tab, setTab] = useState<CanvasTab>(steps.length > 0 ? 'execution' : 'workflows');
  const userPickedRef = useRef(false);
  const prevLoadingRef = useRef(isLoading);
  useEffect(() => {
    if (isLoading && !prevLoadingRef.current) {
      setTab('execution');
      userPickedRef.current = false;
    }
    prevLoadingRef.current = isLoading;
  }, [isLoading]);

  // Continuidad ejecución → workflows: al armar/pausar, o al abrir "mis
  // alertas" desde un toast/comando, el canvas salta a Mis workflows.
  useEffect(() => {
    const goWorkflows = () => {
      userPickedRef.current = false;
      setTab('workflows');
    };
    // Replay: fijar un run desde el chat trae el canvas a la ejecución.
    const goExecution = () => {
      userPickedRef.current = false;
      setTab('execution');
    };
    window.addEventListener('tradeul:ai-alerts-changed', goWorkflows);
    window.addEventListener('tradeul:ai-agent-show-workflows', goWorkflows);
    window.addEventListener('tradeul:ai-agent-show-execution', goExecution);
    return () => {
      window.removeEventListener('tradeul:ai-alerts-changed', goWorkflows);
      window.removeEventListener('tradeul:ai-agent-show-workflows', goWorkflows);
      window.removeEventListener('tradeul:ai-agent-show-execution', goExecution);
    };
  }, []);

  const pickTab = useCallback((t: CanvasTab) => {
    userPickedRef.current = true;
    setTab(t);
  }, []);

  const [width, setWidth] = useState(() => {
    if (typeof window === 'undefined') return PIPELINE_W_DEFAULT;
    const saved = Number(window.localStorage.getItem(PIPELINE_W_KEY));
    return Number.isFinite(saved) && saved >= PIPELINE_W_MIN ? saved : PIPELINE_W_DEFAULT;
  });
  const [dragging, setDragging] = useState(false);
  const widthRef = useRef(width);
  widthRef.current = width;

  const onDragStart = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    setDragging(true);
    const startX = e.clientX;
    const startW = widthRef.current;
    const maxW = Math.round(window.innerWidth * PIPELINE_W_MAX_RATIO);

    const onMove = (ev: PointerEvent) => {
      // El panel está a la derecha: arrastrar a la izquierda lo agranda.
      const next = Math.min(maxW, Math.max(PIPELINE_W_MIN, startW + (startX - ev.clientX)));
      setWidth(next);
    };
    const onUp = () => {
      setDragging(false);
      window.localStorage.setItem(PIPELINE_W_KEY, String(widthRef.current));
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, []);

  return (
    <motion.div
      initial={{ width: 0, opacity: 0 }}
      animate={{ width, opacity: 1 }}
      exit={{ width: 0, opacity: 0 }}
      transition={dragging ? { duration: 0 } : { duration: 0.2, ease: 'easeInOut' }}
      className="relative flex-shrink-0 border-l border-border bg-surface overflow-hidden"
    >
      {/* Asa de redimensionado: arrastra el borde izquierdo del canvas */}
      <div
        onPointerDown={onDragStart}
        className={`absolute left-0 top-0 bottom-0 w-[5px] z-20 cursor-col-resize group ${
          dragging ? 'bg-primary/40' : 'hover:bg-primary/25'
        }`}
        title={t('aiAgent.input.resizeCanvas')}
      >
        <div className={`absolute left-[2px] top-1/2 -translate-y-1/2 h-10 w-[2px] rounded-full transition-colors ${
          dragging ? 'bg-primary' : 'bg-border group-hover:bg-primary/70'
        }`} />
      </div>
      <div style={{ width }} className="h-full flex flex-col">
        <div className="flex-shrink-0 px-3 py-1.5 border-b border-border-subtle flex items-center justify-between">
          <div className="flex items-center gap-0.5">
            {([
              ['execution', t('aiAgent.tabs.execution'), t('aiAgent.tabs.executionHint')],
              ['workflows', t('aiAgent.tabs.workflows'), t('aiAgent.tabs.workflowsHint')],
            ] as const).map(([id, label, hint]) => (
              <button
                key={id}
                onClick={() => pickTab(id)}
                title={hint}
                className={`flex items-center gap-1.5 rounded px-2 py-1 text-[9.5px] font-semibold transition-colors ${
                  tab === id
                    ? 'bg-surface-inset text-foreground'
                    : 'text-muted-fg hover:text-foreground/80'
                }`}
              >
                {label}
                {id === 'execution' && isProcessing && (
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
                  </span>
                )}
              </button>
            ))}
          </div>
          {tab === 'execution' && steps.length > 0 && (
            <div className="flex items-center gap-2">
              <span className={`text-[8.5px] font-semibold uppercase tracking-wider ${
                isProcessing ? 'text-primary' : hasErrors ? 'text-red-400' : 'text-emerald-400'
              }`}>
                {isProcessing ? 'ejecutando' : hasErrors ? 'con errores' : 'completado'}
              </span>
              <span className="text-[9px] text-muted-fg tabular-nums">{completedCount}/{steps.length}</span>
            </div>
          )}
          {tab === 'workflows' && <LiveWorkflowsBadge />}
        </div>

        {tab === 'workflows' ? (
          <div className="flex-1 min-h-0 p-2">
            <LazyLiveWorkflowsCanvas height="100%" />
          </div>
        ) : steps.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <p
              className="text-[10px] text-muted-fg text-center px-6 leading-relaxed whitespace-pre-line"
              dangerouslySetInnerHTML={{ __html: t('aiAgent.canvasEmptyHelp') }}
            />
          </div>
        ) : (
          <div className="flex-1 min-h-0 flex flex-col">
            {/* Replay: el canvas muestra un run anterior fijado desde el chat */}
            {replayQuery !== null && (
              <div className="flex-shrink-0 flex items-center gap-2 px-3 py-1.5 border-b border-border-subtle bg-amber-500/[0.07]">
                <span className="relative inline-flex h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-400" />
                <span className="text-[8.5px] font-semibold uppercase tracking-wider text-amber-500 flex-shrink-0">
                  {t('aiAgent.canvas.replayingPrevious')}
                </span>
                <span className="text-[9.5px] text-muted-fg truncate min-w-0 flex-1" title={replayQuery}>
                  {replayQuery}
                </span>
                <button
                  onClick={onBackToLive}
                  className="flex-shrink-0 text-[9px] font-semibold text-primary hover:text-primary/80 transition-colors"
                >
                  {t('aiAgent.canvas.backToLive')}
                </button>
              </div>
            )}

            {/* Barra de progreso fina pegada al header */}
            <div className="h-[2px] bg-surface-inset flex-shrink-0">
              <motion.div
                className={`h-full ${hasErrors ? 'bg-red-400' : isProcessing ? 'bg-primary' : 'bg-emerald-500'}`}
                animate={{ width: `${steps.length > 0 ? (completedCount / steps.length) * 100 : 0}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>

            {/* Canvas en vivo — ocupa todo el panel */}
            <div className="flex-1 min-h-0 p-2">
              <LazyExecutionGraph steps={steps} height="100%" onInspect={openInspector} />
            </div>
          </div>
        )}
      </div>

      {/* Inspector de nodo: artifacts completos (tablas enteras, código, charts) */}
      <NodeInspector target={inspecting} onClose={closeInspector} />
    </motion.div>
  );
});

/* ================================================================
   WINDOW WRAPPER
   ================================================================ */

export function AIAgentWindow() {
  return (
    <div className="h-full w-full bg-surface">
      <AIAgentContent />
    </div>
  );
}
