'use client';

import { memo, useState, useRef, useEffect, useCallback } from 'react';
import { BarChart3, X } from 'lucide-react';
import { ChatMessage } from './ChatMessage';
import type { Message, MarketContext, ChartContext } from './types';

interface ChatPanelProps {
  messages: Message[];
  isConnected: boolean;
  isLoading: boolean;
  marketContext: MarketContext | null;
  error: string | null;
  chartContext: ChartContext | null;
  onSendMessage: (content: string) => void;
  onClearChartContext: () => void;
  onClarificationChoice: (originalQuery: string, rewrite: string) => void;
  onClearHistory: () => void;
}

export const ChatPanel = memo(function ChatPanel({
  messages,
  isConnected,
  isLoading,
  error,
  chartContext,
  onSendMessage,
  onClearChartContext,
  onClarificationChoice,
  onClearHistory
}: ChatPanelProps) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 80)}px`;
    }
  }, [input]);

  const handleSubmit = useCallback((e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isLoading || !isConnected) return;
    onSendMessage(input);
    setInput('');
    if (inputRef.current) inputRef.current.style.height = 'auto';
  }, [input, isLoading, isConnected, onSendMessage]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  return (
    <div className="flex flex-col h-full bg-surface">
      {/* Header */}
      <div className="flex-shrink-0 px-3 py-2 border-b border-border">
        <div className="flex items-center justify-between">
          <span className="text-[12px] font-medium text-foreground">Chat</span>
          {messages.length > 0 && (
            <button
              onClick={onClearHistory}
              className="text-[10px] text-muted-fg hover:text-foreground/80"
            >
              Nueva
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center p-4">
            <p className="text-[12px] text-muted-fg mb-3">Escribe una consulta</p>
            <p className="text-[10px] text-muted-fg">Ejemplos: top 50 gainers today, gappers this week</p>
          </div>
        ) : (
          <div>
            {messages.map((m) => (
              <ChatMessage
                key={m.id}
                message={m}
                onClarificationChoice={onClarificationChoice}
              />
            ))}
          </div>
        )}

        {error && (
          <div className="mx-3 my-2 p-2 text-[11px] text-foreground/80 border border-border rounded">
            {error}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Chart context bar */}
      {chartContext && (() => {
        const snap = chartContext.snapshot;
        const fmtDate = (ts: number) => new Date(ts * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
        const rangeFrom = snap.visibleDateRange?.from ? fmtDate(snap.visibleDateRange.from) : '';
        const rangeTo = snap.visibleDateRange?.to ? fmtDate(snap.visibleDateRange.to) : '';
        return (
          <div className="flex-shrink-0 mx-2 mt-1 flex items-center gap-1.5 px-2 py-1.5 bg-primary/10 border border-primary/30 rounded text-[10px] flex-wrap">
            <BarChart3 className="w-3 h-3 text-primary flex-shrink-0" />
            <span className="font-semibold text-primary">{chartContext.ticker}</span>
            <span className="text-primary font-medium">{chartContext.interval}</span>
            {rangeFrom && rangeTo && (
              <span className="text-primary">{rangeFrom} → {rangeTo}</span>
            )}
            <span className="text-muted-fg">({snap.recentBars?.length || 0} bars)</span>
            {chartContext.targetCandle && (
              <span className="text-primary font-medium">
                candle: {fmtDate(chartContext.targetCandle.date)}
              </span>
            )}
            {snap.isHistorical && (
              <span className="text-amber-600 dark:text-amber-400 font-semibold bg-amber-500/10 px-1 rounded">Historical</span>
            )}
            <button onClick={onClearChartContext} className="ml-auto text-primary hover:text-primary-hover">
              <X className="w-3 h-3" />
            </button>
          </div>
        );
      })()}

      {/* Input */}
      <div className="flex-shrink-0 p-2 border-t border-border">
        <form onSubmit={handleSubmit} className="flex gap-1.5">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isConnected ? "Escribe tu consulta..." : "Conectando..."}
            disabled={!isConnected || isLoading}
            rows={1}
            className="flex-1 px-3 py-2 text-[12px] border border-border rounded text-foreground placeholder-muted-fg resize-none focus:outline-none focus:border-border disabled:opacity-50"
            style={{ maxHeight: '80px' }}
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading || !isConnected}
            className="flex-shrink-0 px-3 py-2 text-[11px] border border-border rounded text-foreground/80 hover:bg-surface-hover disabled:opacity-30"
          >
            Enviar
          </button>
        </form>
      </div>
    </div>
  );
});
