'use client';

import { memo, useState, useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Brain, Database, Search, Filter, Sparkles, ChevronDown,
  Zap, CheckCircle2, Loader2, AlertCircle, Clock,
} from 'lucide-react';
import type { AgentStep } from './types';

interface AgentStepsProps {
  steps: AgentStep[];
  thinkingTime?: number;
}

/* ─── Step icon mapping ─── */
const STEP_ICONS: Record<string, typeof Brain> = {
  supervisor: Brain,
  'theme resolver': Search,
  'market data': Database,
  screener: Filter,
  scanner: Search,
  financial: Zap,
  synthesizer: Sparkles,
  research: Search,
};

function getStepIcon(title: string) {
  const lower = title.toLowerCase();
  for (const [key, Icon] of Object.entries(STEP_ICONS)) {
    if (lower.includes(key)) return Icon;
  }
  return Zap;
}

/* ─── Elapsed timer ─── */
const ElapsedTimer = memo(function ElapsedTimer({
  startTime,
  finalTime,
}: {
  startTime: number;
  finalTime?: number;
}) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (finalTime) {
      setElapsed(finalTime);
      return;
    }
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [startTime, finalTime]);

  const formatted = elapsed < 60 ? elapsed + 's' : Math.floor(elapsed / 60) + 'm ' + (elapsed % 60) + 's';

  return (
    <span className="text-[10px] tabular-nums text-slate-400 font-mono">
      {formatted}
    </span>
  );
});

/* ─── Individual step item ─── */
const StepItem = memo(function StepItem({ step, index, total }: { step: AgentStep; index: number; total: number }) {
  const isRunning = step.status === 'running';
  const isComplete = step.status === 'complete';
  const isError = step.status === 'error';
  const Icon = getStepIcon(step.title);
  const isLast = index === total - 1;

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.2, delay: index * 0.05 }}
      className="flex items-start gap-2.5 relative"
    >
      {/* Timeline connector */}
      {!isLast && (
        <div className="absolute left-[11px] top-[22px] w-[1.5px] h-[calc(100%+4px)] bg-slate-200" />
      )}

      {/* Icon circle */}
      <div className={
        'relative z-10 flex-shrink-0 w-[23px] h-[23px] rounded-full flex items-center justify-center transition-all duration-300 ' +
        (isRunning
          ? 'bg-indigo-100 ring-2 ring-indigo-300/50 ring-offset-1'
          : isComplete
            ? 'bg-emerald-50 border border-emerald-200'
            : isError
              ? 'bg-red-50 border border-red-200'
              : 'bg-slate-100 border border-slate-200')
      }>
        {isRunning ? (
          <Loader2 className="w-3 h-3 text-indigo-600 animate-spin" />
        ) : isComplete ? (
          <CheckCircle2 className="w-3 h-3 text-emerald-500" />
        ) : isError ? (
          <AlertCircle className="w-3 h-3 text-red-500" />
        ) : (
          <Icon className="w-3 h-3 text-slate-400" />
        )}
      </div>

      {/* Step content */}
      <div className="flex-1 min-w-0 pt-[2px] pb-2.5">
        <div className="flex items-center gap-2">
          <span className={
            'text-[11px] font-medium truncate ' +
            (isRunning ? 'text-indigo-700' : isError ? 'text-red-600' : 'text-slate-600')
          }>
            {step.title}
          </span>
          {isRunning && (
            <motion.span
              animate={{ opacity: [0.4, 1, 0.4] }}
              transition={{ duration: 1.5, repeat: Infinity }}
              className="text-[9px] text-indigo-400 font-medium"
            >
              processing
            </motion.span>
          )}
        </div>
      </div>
    </motion.div>
  );
});

/* ─── Main AgentSteps component ─── */
export const AgentSteps = memo(function AgentSteps({ steps, thinkingTime }: AgentStepsProps) {
  const [collapsed, setCollapsed] = useState(false);
  const startTimeRef = useRef<number>(Date.now());

  useEffect(() => {
    if (steps.length === 1 && steps[0].status === 'running') {
      startTimeRef.current = Date.now();
    }
  }, [steps.length]);

  if (!steps || steps.length === 0) return null;

  const isProcessing = steps.some(s => s.status === 'running');
  const hasErrors = steps.some(s => s.status === 'error');
  const completedCount = steps.filter(s => s.status === 'complete').length;
  const runningStep = steps.find(s => s.status === 'running');

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-slate-200/80 overflow-hidden bg-white shadow-sm"
    >
      {/* Header */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left bg-slate-50/60 hover:bg-slate-100/60 transition-colors"
      >
        {/* Status indicator */}
        {isProcessing ? (
          <div className="w-5 h-5 rounded-full bg-indigo-100 flex items-center justify-center flex-shrink-0">
            <Loader2 className="w-3 h-3 text-indigo-600 animate-spin" />
          </div>
        ) : hasErrors ? (
          <div className="w-5 h-5 rounded-full bg-red-50 flex items-center justify-center flex-shrink-0">
            <AlertCircle className="w-3 h-3 text-red-500" />
          </div>
        ) : (
          <div className="w-5 h-5 rounded-full bg-emerald-50 flex items-center justify-center flex-shrink-0">
            <CheckCircle2 className="w-3 h-3 text-emerald-500" />
          </div>
        )}

        <div className="flex-1 min-w-0">
          <span className="text-[11px] font-medium text-slate-700 truncate block">
            {isProcessing && runningStep
              ? runningStep.title
              : hasErrors ? 'Error in pipeline' : 'Analysis complete'}
          </span>
          {/* Progress bar */}
          <div className="mt-1.5 h-[3px] w-full bg-slate-200 rounded-full overflow-hidden">
            <motion.div
              className={
                'h-full rounded-full ' +
                (hasErrors ? 'bg-red-400' : isProcessing ? 'bg-indigo-500' : 'bg-emerald-500')
              }
              initial={{ width: 0 }}
              animate={{ width: (completedCount / steps.length * 100) + '%' }}
              transition={{ duration: 0.5, ease: 'easeOut' }}
            />
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-[10px] text-slate-400 tabular-nums">
            {completedCount}/{steps.length}
          </span>
          <ElapsedTimer startTime={startTimeRef.current} finalTime={thinkingTime} />
          <ChevronDown className={
            'w-3.5 h-3.5 text-slate-400 transition-transform duration-200 ' +
            (collapsed ? '-rotate-90' : '')
          } />
        </div>
      </button>

      {/* Steps list */}
      <AnimatePresence>
        {!collapsed && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-3.5 py-2.5 border-t border-slate-100 space-y-0">
              {steps.map((step, idx) => (
                <StepItem key={step.id} step={step} index={idx} total={steps.length} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
});

export default AgentSteps;
