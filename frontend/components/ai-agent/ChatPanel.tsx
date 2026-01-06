'use client';

import { memo, useState, useRef, useEffect, useCallback } from 'react';
import { Send, MessageSquarePlus } from 'lucide-react';
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

// Sugerencias de queries comunes
const SUGGESTIONS = [
  'Muestra los top gappers con RVOL > 3x',
  'Acciones cayendo mas del 3% con alto volumen',
  'Momentum alcista cerca de maximos',
  'Anomalias de trading de hoy',
  'Que sectores tienen mas actividad?',
];

export const ChatPanel = memo(function ChatPanel({
  messages,
  isConnected,
  isLoading,
  marketContext,
  error,
  onSendMessage,
  onClearHistory
}: ChatPanelProps) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll cuando hay nuevos mensajes
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Auto-resize del textarea
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 120)}px`;
    }
  }, [input]);

  const handleSubmit = useCallback((e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isLoading || !isConnected) return;

    onSendMessage(input);
    setInput('');

    // Reset height
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }
  }, [input, isLoading, isConnected, onSendMessage]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  const handleSuggestionClick = useCallback((suggestion: string) => {
    setInput(suggestion);
    inputRef.current?.focus();
  }, []);

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header - Estilo profesional como Xynth */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {/* Logo TradeUL */}
            <svg className="w-5 h-5 text-blue-600" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
            <span className="text-gray-300">/</span>
            <span className="text-sm font-medium text-gray-800">New Chat</span>
          </div>

          {/* Boton nuevo chat */}
          {messages.length > 0 && (
            <button
              onClick={onClearHistory}
              className="flex items-center gap-1.5 px-2 py-1 text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors"
              title="Nuevo chat"
            >
              <MessageSquarePlus className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
        {/* Welcome message */}
        {messages.length === 0 && (
          <div className="text-center py-8">
            {/* Suggestions */}
            <div className="space-y-2">
              <p className="text-xs text-gray-400 mb-2">Prueba con:</p>
              <div className="flex flex-wrap gap-2 justify-center">
                {SUGGESTIONS.map((suggestion, index) => (
                  <button
                    key={index}
                    onClick={() => handleSuggestionClick(suggestion)}
                    className="px-3 py-1.5 text-xs bg-white hover:bg-blue-50 text-gray-600 rounded-full border border-gray-200 hover:border-blue-300 transition-colors"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Messages */}
        {messages.map((message) => (
          <ChatMessage key={message.id} message={message} />
        ))}

        {/* Error */}
        {error && (
          <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-600 text-sm">
            {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="flex-shrink-0 p-4 border-t border-gray-200 bg-white">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <div className="flex-1 relative">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isConnected ? "Escribe tu consulta..." : "Conectando..."}
              disabled={!isConnected || isLoading}
              rows={1}
              className="w-full px-4 py-2.5 pr-10 bg-gray-50 border border-gray-200 rounded-xl text-sm text-gray-800 placeholder-gray-400 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 disabled:opacity-50"
              style={{ maxHeight: '120px' }}
            />
          </div>

          <button
            type="submit"
            disabled={!input.trim() || isLoading || !isConnected}
            className="flex-shrink-0 p-2.5 bg-gray-800 hover:bg-gray-700 disabled:bg-gray-300 disabled:text-gray-400 text-white rounded-lg transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
});
