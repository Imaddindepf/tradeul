'use client';

import { memo, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Loader2, CheckCircle2, AlertCircle, ArrowRight, User, Sparkles,
} from 'lucide-react';
import type { Message } from './types';
import { AgentSteps } from './AgentSteps';

interface ChatMessageProps {
  message: Message;
}

/**
 * ChatMessage - Premium 2026 design
 *
 * LEFT PANEL: Reasoning steps only
 * - User: clean query bubble with avatar
 * - Assistant: pipeline steps, NO full text (text goes to Results panel)
 */
export const ChatMessage = memo(function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const isAssistant = message.role === 'assistant';
  const [thinkingSeconds, setThinkingSeconds] = useState(0);

  useEffect(() => {
    if (message.status === 'thinking' && message.thinkingStartTime) {
      const interval = setInterval(() => {
        setElapsed();
      }, 1000);
      function setElapsed() {
        const elapsed = Math.floor((Date.now() - message.thinkingStartTime!) / 1000);
        setThinkingSeconds(elapsed);
      }
      setElapsed();
      return () => clearInterval(interval);
    }
  }, [message.status, message.thinkingStartTime]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="py-2 px-3"
    >
      {/* User message */}
      {isUser && (
        <div className="flex gap-2.5 items-start">
          <div className="w-6 h-6 rounded-lg bg-slate-200 flex items-center justify-center flex-shrink-0 mt-0.5">
            <User className="w-3.5 h-3.5 text-slate-500" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[13px] text-slate-800 leading-relaxed font-medium">
              {message.content}
            </p>
            <span className="text-[9px] text-slate-400 mt-1 block">
              {message.timestamp.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
        </div>
      )}

      {/* Assistant message - ONLY reasoning steps */}
      {isAssistant && (
        <div className="space-y-2">
          {/* Thinking indicator when no steps yet */}
          {message.status === 'thinking' && (!message.steps || message.steps.length === 0) && (
            <ThinkingState seconds={thinkingSeconds} />
          )}

          {/* Steps display */}
          {message.steps && message.steps.length > 0 && (
            <AgentSteps
              steps={message.steps}
              thinkingTime={message.status === 'complete' ? thinkingSeconds : undefined}
            />
          )}

          {/* Completion indicator */}
          {message.status === 'complete' && (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-2 text-[11px] mt-1.5 pl-1"
            >
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
              <span className="text-emerald-600 font-medium">Completado</span>
              <ArrowRight className="w-3 h-3 text-slate-300" />
              <span className="text-slate-400">Ver resultados</span>
            </motion.div>
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
    </motion.div>
  );
});

const ThinkingState = memo(function ThinkingState({ seconds }: { seconds: number }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex items-center gap-2.5 text-[12px] text-slate-500 pl-1 py-1"
    >
      <div className="w-6 h-6 rounded-lg bg-indigo-50 flex items-center justify-center flex-shrink-0">
        <Loader2 className="w-3.5 h-3.5 text-indigo-500 animate-spin" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-slate-600 font-medium">
          {seconds > 0 ? 'Analyzing ' + seconds + 's...' : 'Starting analysis...'}
        </span>
        <motion.div
          className="flex gap-0.5"
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ duration: 1.5, repeat: Infinity }}
        >
          <span className="w-1 h-1 rounded-full bg-indigo-400" />
          <span className="w-1 h-1 rounded-full bg-indigo-400" />
          <span className="w-1 h-1 rounded-full bg-indigo-400" />
        </motion.div>
      </div>
    </motion.div>
  );
});

export default ChatMessage;
