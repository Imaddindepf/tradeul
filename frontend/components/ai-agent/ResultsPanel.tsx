'use client';

import { memo, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, Clock, MessageSquare, ChevronDown } from 'lucide-react';
import { ResultBlock } from './ResultBlock';
import type { ResultBlockData } from './types';
import { useState, useCallback } from 'react';

interface ResultsPanelProps {
  blocks: ResultBlockData[];
  onToggleCode: (blockId: string) => void;
}

function formatTime(date: Date) {
  return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function truncateQuery(query: string, maxLen = 80) {
  if (query.length <= maxLen) return query;
  return query.slice(0, maxLen) + '…';
}

export const ResultsPanel = memo(function ResultsPanel({
  blocks,
  onToggleCode,
}: ResultsPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevCountRef = useRef(blocks.length);

  useEffect(() => {
    if (blocks.length > prevCountRef.current && scrollRef.current) {
      requestAnimationFrame(() => {
        scrollRef.current?.scrollTo({
          top: scrollRef.current.scrollHeight,
          behavior: 'smooth',
        });
      });
    }
    prevCountRef.current = blocks.length;
  }, [blocks.length]);

  return (
    <div className="flex flex-col h-full bg-[#f8f9fb]">
      {/* Header */}
      <div className="flex-shrink-0 px-5 py-3 border-b border-slate-200/80 bg-white/90 backdrop-blur-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center">
              <Sparkles className="w-3.5 h-3.5 text-white" />
            </div>
            <div>
              <span className="text-[13px] font-semibold text-slate-800">Results</span>
              {blocks.length > 0 && (
                <span className="ml-2 text-[10px] text-slate-400 tabular-nums">
                  {blocks.length} {blocks.length === 1 ? 'analysis' : 'analyses'}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Results */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto scroll-smooth p-4 space-y-4">
        <AnimatePresence mode="popLayout">
          {blocks.length === 0 ? (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center justify-center h-full text-center px-8"
            >
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-slate-100 to-slate-50 border border-slate-200/60 flex items-center justify-center mb-4">
                <Sparkles className="w-7 h-7 text-slate-300" />
              </div>
              <p className="text-[13px] font-medium text-slate-400">
                AI analysis results will appear here
              </p>
              <p className="text-[11px] text-slate-300 mt-1.5 max-w-[240px]">
                Ask a question using the chat panel and the multi-agent system will analyze it
              </p>
            </motion.div>
          ) : (
            blocks.map((block) => (
              <ResultCard
                key={block.id}
                block={block}
                onToggleCode={() => onToggleCode(block.id)}
              />
            ))
          )}
        </AnimatePresence>
      </div>
    </div>
  );
});

/* ================================================================
   ResultCard: Professional wrapper for each analysis result
   ================================================================ */
interface ResultCardProps {
  block: ResultBlockData;
  onToggleCode: () => void;
}

const ResultCard = memo(function ResultCard({ block, onToggleCode }: ResultCardProps) {
  const [collapsed, setCollapsed] = useState(false);
  const isRunning = block.status === 'running' || block.status === 'fixing';
  const isError = block.status === 'error';
  const execTime = block.result?.execution_time_ms;

  const borderColor = isRunning
    ? 'border-indigo-300/60'
    : isError
      ? 'border-red-300/60'
      : 'border-slate-200/80';

  const headerGlow = isRunning
    ? 'bg-gradient-to-r from-indigo-50 to-white'
    : isError
      ? 'bg-gradient-to-r from-red-50 to-white'
      : 'bg-gradient-to-r from-slate-50/80 to-white';

  return (
    <motion.div
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.98 }}
      transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
      className={`rounded-xl border ${borderColor} bg-white shadow-sm overflow-hidden`}
    >
      {/* Card Header */}
      <div
        className={`px-4 py-2.5 ${headerGlow} border-b border-slate-100/80 flex items-center justify-between cursor-pointer select-none`}
        onClick={() => !isRunning && setCollapsed(c => !c)}
      >
        <div className="flex items-center gap-2.5 min-w-0 flex-1">
          {/* Status dot */}
          {isRunning ? (
            <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse flex-shrink-0" />
          ) : isError ? (
            <span className="w-2 h-2 rounded-full bg-red-400 flex-shrink-0" />
          ) : (
            <span className="w-2 h-2 rounded-full bg-emerald-400 flex-shrink-0" />
          )}

          {/* Query text */}
          <div className="min-w-0 flex-1">
            {block.query ? (
              <div className="flex items-center gap-1.5">
                <MessageSquare className="w-3 h-3 text-slate-400 flex-shrink-0" />
                <span className="text-[12px] font-medium text-slate-700 truncate">
                  {truncateQuery(block.query)}
                </span>
              </div>
            ) : (
              <span className="text-[12px] font-medium text-slate-600">
                {isRunning ? 'Processing...' : 'Analysis'}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2.5 flex-shrink-0 ml-2">
          {/* Execution time */}
          {execTime != null && execTime > 0 && (
            <span className="inline-flex items-center gap-1 text-[10px] text-slate-400 tabular-nums">
              <Clock className="w-3 h-3" />
              {execTime < 1000 ? `${execTime}ms` : `${(execTime / 1000).toFixed(1)}s`}
            </span>
          )}

          {/* Timestamp */}
          <span className="text-[10px] text-slate-300 tabular-nums">
            {formatTime(block.timestamp)}
          </span>

          {/* Collapse chevron */}
          {!isRunning && (
            <ChevronDown
              className={`w-3.5 h-3.5 text-slate-400 transition-transform duration-200 ${collapsed ? '-rotate-90' : ''}`}
            />
          )}
        </div>
      </div>

      {/* Card Body */}
      <AnimatePresence initial={false}>
        {!collapsed && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            className="overflow-hidden"
          >
            <div className="p-5">
              <ResultBlock
                block={block}
                onToggleCode={onToggleCode}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
});
