'use client';

import { memo, useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAIAgent } from './useAIAgent';
import { ResultBlock } from './ResultBlock';
import type { AgentStep, ChartContext, Message, ResultBlockData, ClarificationData } from './types';

const QUICK_ACTIONS = [
  { label: 'Top Gainers', query: 'top 50 gainers today' },
  { label: 'Sector Performance', query: 'sector performance today' },
  { label: 'Most Active', query: 'most active stocks by volume today' },
  { label: 'Gap Analysis', query: 'stocks gapping up more than 5% today' },
  { label: 'Unusual Volume', query: 'stocks with unusual volume today' },
];

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
  const {
    messages,
    resultBlocks,
    isConnected,
    isLoading,
    error,
    chartContext,
    sendMessage,
    setChartContext,
    sendClarificationChoice,
    clearHistory,
    toggleCodeVisibility,
  } = useAIAgent({ onMarketUpdate });

  const [showPipeline, setShowPipeline] = useState(false);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isNarrow, setIsNarrow] = useState(false);

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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, resultBlocks]);

  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 120)}px`;
    }
  }, [input]);

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

  const activeSteps = useMemo(() => {
    const last = [...messages].reverse().find(m => m.role === 'assistant');
    return last?.steps || [];
  }, [messages]);

  const handleSubmit = useCallback((e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isLoading || !isConnected) return;
    sendMessage(input);
    setInput('');
    if (inputRef.current) inputRef.current.style.height = 'auto';
  }, [input, isLoading, isConnected, sendMessage]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  const handleQuickAction = useCallback((query: string) => {
    if (isLoading || !isConnected) return;
    sendMessage(query);
  }, [isLoading, isConnected, sendMessage]);

  return (
    <div ref={containerRef} className="flex flex-col h-full w-full min-h-0 bg-[#f7f8fb] overflow-hidden">
      <div className="flex-1 min-h-0 flex overflow-hidden">

        {/* CONVERSATION CANVAS */}
        <div className="flex-1 min-w-0 flex flex-col min-h-0">

          {/* Scrollable conversation */}
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-[780px] mx-auto px-4 py-3">

              {/* Inline controls */}
              {(messages.length > 0 || showPipeline) && (
                <div className="flex items-center justify-end gap-3 mb-2 text-[10px]">
                  {messages.length > 0 && (
                    <button onClick={clearHistory} className="text-slate-400 hover:text-slate-600 transition-colors">
                      Nueva sesión
                    </button>
                  )}
                  {!isNarrow && (
                    <button
                      onClick={() => setShowPipeline(p => !p)}
                      className={`transition-colors ${showPipeline ? 'text-slate-600 font-medium' : 'text-slate-400 hover:text-slate-600'}`}
                    >
                      Pipeline
                    </button>
                  )}
                  <div className="flex items-center gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-slate-300 animate-pulse'}`} />
                    <span className="text-slate-400">{isConnected ? 'Live' : 'Connecting...'}</span>
                  </div>
                </div>
              )}

              {timeline.length === 0 && !isLoading ? (
                <EmptyState isConnected={isConnected} onQuickAction={handleQuickAction} isNarrow={isNarrow} />
              ) : (
                <div className="space-y-3">
                  {timeline.map((entry) => (
                    <TimelineItem
                      key={entry.userMessage.id}
                      entry={entry}
                      onClarificationChoice={sendClarificationChoice}
                      onToggleCode={toggleCodeVisibility}
                      onSendMessage={sendMessage}
                    />
                  ))}
                </div>
              )}

              {error && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-3 px-3 py-2 bg-red-50 border border-red-200/60 rounded-lg text-[11px] text-red-600 max-w-[600px] mx-auto"
                >
                  {error}
                </motion.div>
              )}
              <div ref={messagesEndRef} className="h-4" />
            </div>
          </div>

          {/* INPUT BAR */}
          <div className="flex-shrink-0 border-t border-slate-200/60 bg-white/80 backdrop-blur-xl">
            <div className="max-w-[860px] mx-auto px-5 py-2.5">

              {!isLoading && timeline.length <= 1 && (
                <div className="flex items-center gap-1 mb-2 text-[11px] flex-wrap">
                  {QUICK_ACTIONS.slice(0, isNarrow ? 2 : 4).map((a, i) => (
                    <span key={a.query} className="flex items-center gap-1">
                      {i > 0 && <span className="text-slate-200">·</span>}
                      <button
                        onClick={() => handleQuickAction(a.query)}
                        disabled={!isConnected}
                        className="text-slate-400 hover:text-indigo-600 transition-colors disabled:opacity-40"
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

              <form onSubmit={handleSubmit} className="flex items-end gap-2">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={isConnected ? 'Escribe tu consulta...' : 'Conectando...'}
                  disabled={!isConnected || isLoading}
                  rows={1}
                  className="flex-1 px-3.5 py-2.5 text-[13px] bg-slate-50 border border-slate-200 rounded-2xl text-slate-800 placeholder-slate-400 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-300 disabled:opacity-50 transition-all"
                  style={{ maxHeight: '120px' }}
                />
                <button
                  type="submit"
                  disabled={!input.trim() || isLoading || !isConnected}
                  className="flex-shrink-0 px-3.5 py-2.5 text-[12px] font-medium text-slate-500 bg-slate-50 border border-slate-200 rounded-2xl hover:bg-slate-100 hover:text-slate-700 disabled:opacity-30 transition-all"
                >
                  {isLoading ? '···' : 'Enviar'}
                </button>
              </form>
            </div>
          </div>
        </div>

        {/* PIPELINE SIDEBAR */}
        <AnimatePresence>
          {showPipeline && !isNarrow && <PipelineSidebar steps={activeSteps} />}
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
}: {
  isConnected: boolean;
  onQuickAction: (q: string) => void;
  isNarrow: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="flex flex-col items-center justify-center min-h-[40vh] text-center"
    >
      <h2 className={`font-semibold text-slate-800 mb-1.5 ${isNarrow ? 'text-[14px]' : 'text-[16px]'}`}>¿Qué quieres analizar?</h2>
      <p className="text-[11px] text-slate-400 max-w-[340px] mb-6 leading-relaxed">
        Sistema multi-agente: mercados, screeners, financials y noticias en tiempo real.
      </p>
      <div className={`grid gap-2 w-full ${isNarrow ? 'grid-cols-1 max-w-[240px]' : 'grid-cols-2 max-w-[380px]'}`}>
        {QUICK_ACTIONS.map((action) => (
          <motion.button
            key={action.query}
            onClick={() => onQuickAction(action.query)}
            disabled={!isConnected}
            whileHover={{ y: -1 }}
            whileTap={{ scale: 0.98 }}
            className="px-3 py-2.5 bg-white border border-slate-200/80 rounded-lg text-left hover:border-slate-300 hover:shadow-sm transition-all disabled:opacity-40"
          >
            <span className="text-[11px] font-medium text-slate-700 block">{action.label}</span>
            <span className="text-[9px] text-slate-400 block mt-0.5 truncate">{action.query}</span>
          </motion.button>
        ))}
      </div>
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
}: {
  entry: TimelineEntry;
  onClarificationChoice: (oq: string, rw: string) => void;
  onToggleCode: (id: string) => void;
  onSendMessage: (msg: string) => void;
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
        />
      )}
    </motion.div>
  );
});

/* ================================================================
   USER BUBBLE
   ================================================================ */

const UserBubble = memo(function UserBubble({ message }: { message: Message }) {
  return (
    <div className="flex justify-end">
      <div className="inline-flex items-baseline gap-2 bg-white border border-slate-200/80 rounded-lg px-2.5 py-1.5 max-w-[80%]">
        <p className="text-[11px] text-slate-800 leading-normal">{message.content}</p>
        <span className="text-[9px] text-slate-300 whitespace-nowrap flex-shrink-0">
          {message.timestamp.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
    </div>
  );
});

/* ================================================================
   AGENT RESPONSE — one unified card per response
   ================================================================ */

const AgentResponse = memo(function AgentResponse({
  message,
  results,
  onClarificationChoice,
  onToggleCode,
  onSendMessage,
}: {
  message: Message;
  results: ResultBlockData[];
  onClarificationChoice: (oq: string, rw: string) => void;
  onToggleCode: (id: string) => void;
  onSendMessage: (msg: string) => void;
}) {
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
        className="px-3 py-2 bg-white border border-slate-200/80 rounded-lg"
      >
        <span className="text-[11px] text-slate-500">
          {thinkingSeconds > 0 ? `Analizando... ${thinkingSeconds}s` : 'Iniciando análisis...'}
        </span>
        <LoadingDots className="ml-2" />
      </motion.div>
    );
  }

  if (!isComplete && !isError && !isClarification && hasSteps) {
    const steps = message.steps!;
    const completed = steps.filter(s => s.status === 'complete').length;
    const running = steps.find(s => s.status === 'running');

    return (
      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        className="px-3 py-2 bg-white border border-indigo-100 rounded-lg"
      >
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[11px] font-medium text-slate-600">
            {running ? running.title : 'Procesando...'}
          </span>
          <span className="text-[9px] text-slate-400 tabular-nums">{completed}/{steps.length}</span>
        </div>
        <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-indigo-500 rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${(completed / steps.length) * 100}%` }}
            transition={{ duration: 0.5 }}
          />
        </div>
      </motion.div>
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
      <div className="px-3 py-2 bg-red-50 border border-red-200/60 rounded-lg text-[11px] text-red-600">
        {message.content || 'Error al procesar la solicitud'}
      </div>
    );
  }

  if (isComplete && results.length > 0) {
    const execMs = results[0]?.result?.execution_time_ms;
    const ts = results[0]?.timestamp;
    const suggestions = message.suggestedQuestions;

    return (
      <div className="space-y-2">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="bg-white border border-slate-200/80 rounded-lg overflow-hidden"
        >
          <div className="p-3">
            {results.map((block) => (
              <ResultBlock key={block.id} block={block} onToggleCode={() => onToggleCode(block.id)} />
            ))}
          </div>
          <div className="px-3 py-1.5 border-t border-slate-100 flex items-center justify-end gap-2 text-[9px] text-slate-400 tabular-nums">
            {execMs != null && execMs > 0 && (
              <span>{execMs < 1000 ? `${execMs}ms` : `${(execMs / 1000).toFixed(1)}s`}</span>
            )}
            {ts && (
              <span className="text-slate-300">
                {ts.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
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
      <div className="px-3 py-2 bg-white border border-slate-200/80 rounded-lg text-[11px] text-slate-500">
        Análisis completado
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
          className="text-left px-2.5 py-1.5 text-[10px] text-slate-500 bg-white border border-slate-200/80 rounded-lg hover:border-slate-300 hover:bg-slate-50 transition-all leading-snug"
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
      <span className="w-[3px] h-[3px] rounded-full bg-slate-400" />
      <span className="w-[3px] h-[3px] rounded-full bg-slate-400" />
      <span className="w-[3px] h-[3px] rounded-full bg-slate-400" />
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
      <div className="px-3 py-2 bg-white border border-slate-200/80 rounded-lg text-[10px] text-slate-400 italic">
        Clarificación omitida
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-white border border-amber-200/60 rounded-lg p-3 space-y-2"
    >
      <p className="text-[11px] text-slate-700 leading-relaxed">{data.message}</p>

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
                ${sel ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
                  : dim ? 'border-slate-100 bg-slate-50 text-slate-300 cursor-default'
                    : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50 cursor-pointer'}`}
            >
              <span className="font-medium text-[11px] text-slate-400 mr-2">{String.fromCharCode(65 + idx)}.</span>
              {opt.label}
            </button>
          );
        })}

        {!showCustom && !isLocked && (
          <button
            onClick={() => { setShowCustom(true); setTimeout(() => customRef.current?.focus(), 50); }}
            className="w-full text-left px-2.5 py-2 rounded-lg border border-dashed border-slate-200 text-[11px] text-slate-500 hover:border-slate-300 hover:bg-slate-50 transition-all cursor-pointer"
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
              placeholder="Escribe lo que necesitas..."
              className="flex-1 px-2.5 py-1.5 text-[11px] border border-slate-200 rounded-lg text-slate-700 placeholder-slate-400 focus:outline-none focus:border-indigo-300"
            />
            <button
              onClick={submitCustom}
              disabled={!customText.trim()}
              className="px-2.5 py-1.5 rounded-lg text-[11px] font-medium text-white bg-indigo-500 disabled:opacity-30 hover:bg-indigo-600 transition-colors"
            >
              Enviar
            </button>
          </motion.div>
        )}

        {chosen === -1 && (
          <div className="px-2.5 py-1.5 rounded-lg border border-indigo-300 bg-indigo-50 text-indigo-700 text-[11px]">
            {customText}
          </div>
        )}
      </div>

      {chosen !== null && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-1.5 text-[10px] text-indigo-500">
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
    <div className="flex items-center gap-1.5 mb-1.5 px-2.5 py-1 bg-blue-50 border border-blue-200/60 rounded-lg text-[10px] flex-wrap">
      <span className="font-semibold text-blue-700">{chartContext.ticker}</span>
      <span className="text-blue-500 font-medium">{chartContext.interval}</span>
      {from && to && <span className="text-blue-600">{from} → {to}</span>}
      <span className="text-slate-400">({snap.recentBars?.length || 0} bars)</span>
      {chartContext.targetCandle && (
        <span className="text-blue-400 font-medium">candle: {fmt(chartContext.targetCandle.date)}</span>
      )}
      {snap.isHistorical && (
        <span className="text-amber-600 font-semibold bg-amber-50 px-1.5 py-0.5 rounded">Historical</span>
      )}
      <button onClick={onClear} className="ml-auto text-blue-400 hover:text-blue-600 text-[14px] leading-none font-light">
        ×
      </button>
    </div>
  );
});

/* ================================================================
   PIPELINE SIDEBAR
   ================================================================ */

const PipelineSidebar = memo(function PipelineSidebar({ steps }: { steps: AgentStep[] }) {
  const completedCount = steps.filter(s => s.status === 'complete').length;
  const hasErrors = steps.some(s => s.status === 'error');
  const isProcessing = steps.some(s => s.status === 'running');

  return (
    <motion.div
      initial={{ width: 0, opacity: 0 }}
      animate={{ width: 200, opacity: 1 }}
      exit={{ width: 0, opacity: 0 }}
      transition={{ duration: 0.2, ease: 'easeInOut' }}
      className="flex-shrink-0 border-l border-slate-200/60 bg-white overflow-hidden"
    >
      <div className="w-[200px] h-full flex flex-col">
        <div className="flex-shrink-0 px-3 py-2 border-b border-slate-100">
          <span className="text-[10px] font-semibold text-slate-700">Pipeline</span>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-2">
          {steps.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <p className="text-[10px] text-slate-400 text-center px-2 leading-relaxed">
                Los pasos del agente aparecerán aquí.
              </p>
            </div>
          ) : (
            <div>
              <div className="mb-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[9px] text-slate-400 font-medium uppercase tracking-wider">
                    {isProcessing ? 'En progreso' : hasErrors ? 'Error' : 'Completado'}
                  </span>
                  <span className="text-[9px] text-slate-400 tabular-nums">{completedCount}/{steps.length}</span>
                </div>
                <div className="h-1 bg-slate-100 rounded-full overflow-hidden">
                  <motion.div
                    className={`h-full rounded-full ${hasErrors ? 'bg-red-400' : isProcessing ? 'bg-indigo-500' : 'bg-emerald-500'}`}
                    animate={{ width: `${steps.length > 0 ? (completedCount / steps.length) * 100 : 0}%` }}
                    transition={{ duration: 0.5 }}
                  />
                </div>
              </div>

              {steps.map((step, idx) => {
                const running = step.status === 'running';
                const done = step.status === 'complete';
                const err = step.status === 'error';
                return (
                  <motion.div
                    key={step.id}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.2, delay: idx * 0.04 }}
                    className="flex items-center gap-2 py-1.5 border-b border-slate-50 last:border-0"
                  >
                    <span className={`text-[9px] leading-none font-medium ${
                      running ? 'text-indigo-500' : done ? 'text-emerald-500' : err ? 'text-red-400' : 'text-slate-300'
                    }`}>
                      {running ? '●' : done ? '✓' : err ? '×' : '○'}
                    </span>
                    <span className={`text-[10px] flex-1 truncate ${
                      running ? 'text-indigo-700 font-medium' : done ? 'text-slate-600' : err ? 'text-red-600' : 'text-slate-400'
                    }`}>
                      {step.title}
                    </span>
                    {running && <LoadingDots />}
                  </motion.div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
});

/* ================================================================
   WINDOW WRAPPER
   ================================================================ */

export function AIAgentWindow() {
  return (
    <div className="h-full w-full bg-[#f7f8fb]">
      <AIAgentContent />
    </div>
  );
}
