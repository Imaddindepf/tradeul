'use client';

import { memo, useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Compass, Activity, Radio, Landmark, Search, Code2,
  SlidersHorizontal, FlaskConical, Layers, Circle,
  Check, ChevronRight, Loader2, AlertCircle,
} from 'lucide-react';
import type { AgentStep } from './types';

const STEP_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  'step-query_planner': Compass,
  'step-supervisor': Compass,
  'step-market_data': Activity,
  'step-news_events': Radio,
  'step-financial': Landmark,
  'step-research': Search,
  'step-code_exec': Code2,
  'step-screener': SlidersHorizontal,
  'step-backtest': FlaskConical,
  'step-synthesizer': Layers,
};

function getIcon(step: AgentStep) {
  return STEP_ICONS[step.id] || Circle;
}

function fmtDuration(s: number): string {
  return s < 1 ? `${Math.round(s * 1000)}ms` : `${s.toFixed(1)}s`;
}

interface StepCardProps {
  step: AgentStep;
  isLatest: boolean;
}

export const StepCard = memo(function StepCard({ step, isLatest }: StepCardProps) {
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (step.status === 'running') setExpanded(true);
    else if (step.status === 'complete') setExpanded(false);
    else if (step.status === 'error') setExpanded(true);
  }, [step.status]);

  const Icon = getIcon(step);
  const isRunning = step.status === 'running';
  const isComplete = step.status === 'complete';
  const isError = step.status === 'error';
  const isPending = step.status === 'pending';
  const hasContent = !!(step.description || step.details);
  const canExpand = hasContent;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={`relative overflow-hidden rounded-lg border bg-white ${
        isRunning ? 'border-indigo-200 shadow-sm' :
        isError ? 'border-red-200' :
        isComplete ? 'border-slate-200/80' : 'border-slate-100'
      } ${isPending ? 'opacity-40' : ''}`}
    >
      {/* Left accent bar */}
      {(isRunning || isError) && (
        <motion.div
          className={`absolute left-0 top-0 bottom-0 w-[2px] rounded-l ${
            isError ? 'bg-red-400' : 'bg-indigo-500'
          }`}
          {...(isRunning ? { animate: { opacity: [1, 0.3, 1] }, transition: { duration: 1.5, repeat: Infinity } } : {})}
        />
      )}

      {/* Header row — fixed layout for alignment */}
      <button
        onClick={() => canExpand && setExpanded(e => !e)}
        className={`w-full flex items-center px-3 py-1.5 text-left ${
          canExpand ? 'cursor-pointer hover:bg-slate-50/50' : 'cursor-default'
        } transition-colors`}
      >
        {/* Left: icon — fixed 20px box */}
        <span className={`w-5 shrink-0 flex items-center justify-center ${
          isRunning ? 'text-indigo-500' :
          isError ? 'text-red-400' :
          isComplete ? 'text-slate-400' : 'text-slate-300'
        }`}>
          <Icon className="w-3.5 h-3.5" />
        </span>

        {/* Center: title — fills remaining space */}
        <span className={`flex-1 text-[11px] font-medium truncate ml-2 ${
          isRunning ? 'text-slate-700' :
          isError ? 'text-red-600' :
          isComplete ? 'text-slate-500' : 'text-slate-400'
        }`}>
          {step.title}
        </span>

        {/* Right: status + duration + chevron — fixed widths for alignment */}
        <span className="flex items-center shrink-0 ml-2">
          {/* Status icon — always 16px box */}
          <span className="w-4 flex items-center justify-center">
            {isRunning && <Loader2 className="w-3 h-3 text-indigo-500 animate-spin" />}
            {isComplete && <Check className="w-3 h-3 text-emerald-500" />}
            {isError && <AlertCircle className="w-3 h-3 text-red-400" />}
          </span>

          {/* Duration — always 36px box */}
          <span className="w-9 text-right text-[9px] text-slate-400 tabular-nums font-mono">
            {step.duration != null && step.duration > 0 ? fmtDuration(step.duration) : ''}
          </span>

          {/* Chevron — always 16px box (invisible when nothing to expand) */}
          <span className={`w-4 flex items-center justify-center ${canExpand ? '' : 'invisible'}`}>
            <ChevronRight className={`w-3 h-3 text-slate-300 transition-transform duration-200 ${
              expanded ? 'rotate-90' : ''
            }`} />
          </span>
        </span>
      </button>

      {/* Expandable detail */}
      <AnimatePresence initial={false}>
        {expanded && hasContent && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className={`px-3 pb-2 text-[10px] leading-relaxed ${
              isError ? 'text-red-500' : 'text-slate-400'
            }`} style={{ paddingLeft: '2rem' }}>
              {step.description || step.details}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
});
