'use client';

import { memo, useEffect, useState } from 'react';
import { Loader2, CheckCircle, AlertCircle, ArrowRight } from 'lucide-react';
import type { Message } from './types';
import { AgentSteps } from './AgentSteps';

interface ChatMessageProps {
  message: Message;
}

/**
 * ChatMessage - Xynth-style
 * 
 * LEFT PANEL: Solo razonamiento y pasos
 * - Usuario: burbuja con query
 * - Asistente: SOLO steps de razonamiento, sin texto completo
 * - El texto completo va al panel derecho (Results)
 */
export const ChatMessage = memo(function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const isAssistant = message.role === 'assistant';
  const [thinkingSeconds, setThinkingSeconds] = useState(0);

  // Timer for thinking state
  useEffect(() => {
    if (message.status === 'thinking' && message.thinkingStartTime) {
      const interval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - message.thinkingStartTime!) / 1000);
        setThinkingSeconds(elapsed);
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [message.status, message.thinkingStartTime]);

  return (
    <div className={`py-2.5 px-3 ${isUser ? '' : ''}`}>
      {/* User message - simple, no colors */}
      {isUser && (
        <div className="border-l-2 border-slate-300 pl-3">
          <p className="text-[13px] text-slate-800 leading-relaxed">{message.content}</p>
          <span className="text-[9px] text-slate-400">
            {message.timestamp.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      )}

      {/* Assistant message - ONLY reasoning steps, NO full text */}
      {isAssistant && (
        <div className="space-y-2">
          {/* Thinking indicator when no steps yet */}
          {message.status === 'thinking' && (!message.steps || message.steps.length === 0) && (
            <ThinkingState seconds={thinkingSeconds} />
          )}

          {/* Steps display - the main content for assistant */}
          {message.steps && message.steps.length > 0 && (
            <AgentSteps
              steps={message.steps}
              thinkingTime={message.status === 'complete' ? thinkingSeconds : undefined}
            />
          )}

          {/* Completion indicator - pointer to Results panel */}
          {message.status === 'complete' && (
            <div className="flex items-center gap-2 text-[11px] text-emerald-600 mt-2 pl-1">
              <CheckCircle className="w-3.5 h-3.5" />
              <span>Completado</span>
              <ArrowRight className="w-3 h-3 text-slate-400" />
              <span className="text-slate-400">Ver resultados</span>
            </div>
          )}

          {/* Error state */}
          {message.status === 'error' && !message.steps?.length && (
            <div className="flex items-center gap-2 text-[11px] text-red-500 pl-1">
              <AlertCircle className="w-3.5 h-3.5" />
              <span>{message.content || 'Error al procesar'}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
});

const ThinkingState = memo(function ThinkingState({ seconds }: { seconds: number }) {
  return (
    <div className="flex items-center gap-2 text-[12px] text-slate-500 pl-1">
      <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
      <span>
        {seconds > 0
          ? `Razonando ${seconds}s...`
          : 'Razonando...'
        }
      </span>
    </div>
  );
});

export default ChatMessage;
