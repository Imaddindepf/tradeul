'use client';

import { memo, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, Clock, Copy, Check } from 'lucide-react';
import { ResultBlock } from './ResultBlock';
import type { ResultBlockData } from './types';
import { useState, useCallback } from 'react';

interface ResultsPanelProps {
  blocks: ResultBlockData[];
  onToggleCode: (blockId: string) => void;
}

export const ResultsPanel = memo(function ResultsPanel({
  blocks,
  onToggleCode,
}: ResultsPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevCountRef = useRef(blocks.length);

  // Auto-scroll to latest result when a new block appears
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
    <div className="flex flex-col h-full bg-gradient-to-b from-slate-50/50 to-white">
      {/* Header */}
      <div className="flex-shrink-0 px-5 py-3 border-b border-slate-200/80 bg-white/80 backdrop-blur-sm">
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
      <div ref={scrollRef} className="flex-1 overflow-y-auto scroll-smooth">
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
            blocks.map((block, index) => (
              <motion.div
                key={block.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
                className="px-5 py-4"
              >
                {/* Separator between blocks */}
                {index > 0 && (
                  <div className="mb-4 border-t border-slate-100" />
                )}
                <ResultBlock
                  block={block}
                  onToggleCode={() => onToggleCode(block.id)}
                />
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </div>
    </div>
  );
});
