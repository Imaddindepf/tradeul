'use client';

import { memo, useEffect, useState, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  Loader2, CheckCircle2, AlertCircle, ArrowRight, User, HelpCircle, PenLine, Send,
} from 'lucide-react';
import type { Message } from './types';
import { AgentSteps } from './AgentSteps';

interface ChatMessageProps {
  message: Message;
  onClarificationChoice?: (originalQuery: string, rewrite: string) => void;
}

/**
 * ChatMessage - Premium 2026 design
 *
 * LEFT PANEL: Reasoning steps only
 * - User: clean query bubble with avatar
 * - Assistant: pipeline steps, NO full text (text goes to Results panel)
 * - Clarification: options as buttons when system needs disambiguation
 */
export const ChatMessage = memo(function ChatMessage({ message, onClarificationChoice }: ChatMessageProps) {
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
          <div className="w-6 h-6 rounded-lg bg-muted flex items-center justify-center flex-shrink-0 mt-0.5">
            <User className="w-3.5 h-3.5 text-muted-fg" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[13px] text-foreground leading-relaxed font-medium">
              {message.content}
            </p>
            <span className="text-[9px] text-muted-fg mt-1 block">
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

          {/* Clarification — interactive options (also show when dismissed but data exists) */}
          {message.clarification && (
            <ClarificationCard
              message={message.clarification.message}
              options={message.clarification.options}
              originalQuery={message.clarification.originalQuery}
              onChoose={onClarificationChoice}
              disabled={message.status !== 'clarification'}
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
              <ArrowRight className="w-3 h-3 text-muted-fg/50" />
              <span className="text-muted-fg">Ver resultados</span>
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
      className="flex items-center gap-2.5 text-[12px] text-muted-fg pl-1 py-1"
    >
      <div className="w-6 h-6 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
        <Loader2 className="w-3.5 h-3.5 text-primary animate-spin" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-foreground/80 font-medium">
          {seconds > 0 ? 'Analyzing ' + seconds + 's...' : 'Starting analysis...'}
        </span>
        <motion.div
          className="flex gap-0.5"
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ duration: 1.5, repeat: Infinity }}
        >
          <span className="w-1 h-1 rounded-full bg-primary" />
          <span className="w-1 h-1 rounded-full bg-primary" />
          <span className="w-1 h-1 rounded-full bg-primary" />
        </motion.div>
      </div>
    </motion.div>
  );
});

interface ClarificationCardProps {
  message: string;
  options: { label: string; rewrite: string }[];
  originalQuery: string;
  onChoose?: (originalQuery: string, rewrite: string) => void;
  disabled?: boolean;
}

const ClarificationCard = memo(function ClarificationCard({
  message,
  options,
  originalQuery,
  onChoose,
  disabled = false,
}: ClarificationCardProps) {
  const [chosen, setChosen] = useState<number | null>(null);
  const [showCustom, setShowCustom] = useState(false);
  const [customText, setCustomText] = useState('');
  const customInputRef = useRef<HTMLInputElement>(null);

  const isLocked = disabled || chosen !== null;

  const handleClick = (idx: number, rewrite: string) => {
    if (isLocked) return;
    setChosen(idx);
    setShowCustom(false);
    onChoose?.(originalQuery, rewrite);
  };

  const handleCustomToggle = () => {
    if (isLocked) return;
    setShowCustom(true);
    setTimeout(() => customInputRef.current?.focus(), 50);
  };

  const handleCustomSubmit = () => {
    if (isLocked || !customText.trim()) return;
    setChosen(-1);
    setShowCustom(false);
    onChoose?.(originalQuery, customText.trim());
  };

  if (disabled && chosen === null) {
    return (
      <div className="mt-2 pl-1 flex items-center gap-2 text-[11px] text-muted-fg">
        <HelpCircle className="w-3.5 h-3.5" />
        <span className="italic">Clarificación omitida</span>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="mt-2 space-y-2"
    >
      <div className="flex items-start gap-2 pl-1">
        <HelpCircle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
        <p className="text-[12px] text-foreground leading-relaxed">{message}</p>
      </div>

      <div className="space-y-1.5 pl-1">
        {options.map((opt, idx) => {
          const isChosen = chosen === idx;
          const isDimmed = isLocked && !isChosen;

          return (
            <motion.button
              key={idx}
              onClick={() => handleClick(idx, opt.rewrite)}
              disabled={isLocked}
              whileHover={!isLocked ? { scale: 1.01 } : {}}
              whileTap={!isLocked ? { scale: 0.99 } : {}}
              className={`
                w-full text-left px-3 py-2.5 rounded-lg border text-[12px] leading-snug
                transition-all duration-200
                ${isChosen
                  ? 'border-primary bg-primary/10 text-primary shadow-sm'
                  : isDimmed
                    ? 'border-border-subtle bg-surface-hover text-muted-fg/50 cursor-default'
                    : 'border-border bg-surface text-foreground hover:border-border hover:bg-surface-hover cursor-pointer'
                }
              `}
            >
              <span className="font-medium text-[11px] text-muted-fg mr-2">
                {String.fromCharCode(65 + idx)}.
              </span>
              {opt.label}
            </motion.button>
          );
        })}

        {/* "Other" option */}
        {!showCustom && !isLocked && (
          <motion.button
            onClick={handleCustomToggle}
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
            className="w-full text-left px-3 py-2.5 rounded-lg border border-dashed border-border text-[12px] text-muted-fg hover:border-border hover:bg-surface-hover transition-all duration-200 cursor-pointer flex items-center gap-2"
          >
            <PenLine className="w-3.5 h-3.5" />
            Otra cosa...
          </motion.button>
        )}

        {/* Custom text input */}
        {showCustom && !isLocked && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            className="flex gap-1.5"
          >
            <input
              ref={customInputRef}
              value={customText}
              onChange={(e) => setCustomText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCustomSubmit()}
              placeholder="Escribe lo que necesitas..."
              className="flex-1 px-3 py-2 text-[12px] border border-border rounded-lg text-foreground placeholder-muted-fg focus:outline-none focus:border-primary"
            />
            <button
              onClick={handleCustomSubmit}
              disabled={!customText.trim()}
              className="px-2.5 py-2 rounded-lg bg-primary text-white disabled:opacity-30 hover:bg-primary-hover transition-colors"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </motion.div>
        )}

        {/* Custom option chosen */}
        {chosen === -1 && (
          <div className="px-3 py-2.5 rounded-lg border border-primary bg-primary/10 text-primary text-[12px]">
            <span className="font-medium text-[11px] text-muted-fg mr-2">
              <PenLine className="w-3 h-3 inline" />
            </span>
            {customText}
          </div>
        )}
      </div>

      {chosen !== null && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center gap-2 text-[11px] text-primary pl-1 pt-1"
        >
          <Loader2 className="w-3 h-3 animate-spin" />
          <span>Procesando...</span>
        </motion.div>
      )}
    </motion.div>
  );
});

export default ChatMessage;
