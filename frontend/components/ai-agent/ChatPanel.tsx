'use client';

import { memo, useState, useRef, useEffect, useCallback } from 'react';
import { ChatMessage } from './ChatMessage';
import type { Message, MarketContext } from './types';

interface ChatPanelProps {
  messages: Message[];
  isConnected: boolean;
  isLoading: boolean;
  marketContext: MarketContext | null;
  error: string | null;
  onSendMessage: (content: string) => void;
  onClearHistory: () => void;
}

export const ChatPanel = memo(function ChatPanel({
  messages,
  isConnected,
  isLoading,
  error,
  onSendMessage,
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
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="flex-shrink-0 px-3 py-2 border-b border-slate-200">
        <div className="flex items-center justify-between">
          <span className="text-[12px] font-medium text-slate-700">Chat</span>
          {messages.length > 0 && (
            <button
              onClick={onClearHistory}
              className="text-[10px] text-slate-400 hover:text-slate-600"
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
            <p className="text-[12px] text-slate-500 mb-3">Escribe una consulta</p>
            <p className="text-[10px] text-slate-400">Ejemplos: top 50 gainers today, gappers this week</p>
          </div>
        ) : (
          <div>
            {messages.map((m) => <ChatMessage key={m.id} message={m} />)}
          </div>
        )}

        {error && (
          <div className="mx-3 my-2 p-2 text-[11px] text-slate-600 border border-slate-200 rounded">
            {error}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="flex-shrink-0 p-2 border-t border-slate-200">
        <form onSubmit={handleSubmit} className="flex gap-1.5">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isConnected ? "Escribe tu consulta..." : "Conectando..."}
            disabled={!isConnected || isLoading}
            rows={1}
            className="flex-1 px-3 py-2 text-[12px] border border-slate-200 rounded text-slate-800 placeholder-slate-400 resize-none focus:outline-none focus:border-slate-400 disabled:opacity-50"
            style={{ maxHeight: '80px' }}
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading || !isConnected}
            className="flex-shrink-0 px-3 py-2 text-[11px] border border-slate-300 rounded text-slate-600 hover:bg-slate-50 disabled:opacity-30"
          >
            Enviar
          </button>
        </form>
      </div>
    </div>
  );
});
