'use client';

import { memo, useState, useRef, useEffect, useCallback } from 'react';
import { Send, RotateCcw } from 'lucide-react';
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

const SUGGESTIONS = [
  'Top gainers hoy',
  'Analisis sectorial',
  'Alto volumen',
  'Top losers',
];

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
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 100)}px`;
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
      <div className="flex-shrink-0 px-3 py-2 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <span className="text-[13px] font-medium text-gray-700">Agente</span>
          {messages.length > 0 && (
            <button
              onClick={onClearHistory}
              className="flex items-center gap-1 px-2 py-1 text-[11px] text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded"
              title="Nueva conversacion"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Nueva</span>
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center p-6">
            <p className="text-[12px] text-gray-500 mb-3">Sugerencias:</p>
            <div className="flex flex-wrap gap-2 justify-center">
              {SUGGESTIONS.map((s, i) => (
                <button
                  key={i}
                  onClick={() => onSendMessage(s)}
                  disabled={!isConnected || isLoading}
                  className="px-3 py-1.5 text-[12px] bg-gray-50 hover:bg-gray-100 text-gray-600 rounded-lg border border-gray-200 disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {messages.map((m) => <ChatMessage key={m.id} message={m} />)}
          </div>
        )}

        {error && (
          <div className="mx-3 my-2 p-2 rounded bg-red-50 text-red-600 text-[12px] border border-red-100">
            {error}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="flex-shrink-0 p-3 border-t border-gray-200">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isConnected ? "Escribe tu consulta..." : "Conectando..."}
            disabled={!isConnected || isLoading}
            rows={1}
            className="flex-1 px-3 py-2 text-[13px] bg-gray-50 border border-gray-200 rounded-lg text-gray-800 placeholder-gray-400 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400 disabled:opacity-50"
            style={{ maxHeight: '100px' }}
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading || !isConnected}
            className="flex-shrink-0 px-3 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-200 disabled:text-gray-400 text-white rounded-lg"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
});
