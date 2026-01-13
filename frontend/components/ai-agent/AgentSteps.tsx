'use client';

import { memo, useState, useEffect, useRef } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  Check,
  AlertCircle,
  Cpu,
  Database,
  Search,
  Code2,
  Sparkles,
  TrendingUp,
  Zap
} from 'lucide-react';
import type { AgentStep } from './types';

interface AgentStepsProps {
  steps: AgentStep[];
  thinkingTime?: number;
}

// Real-time elapsed timer component
const ElapsedTimer = memo(function ElapsedTimer({ 
  startTime, 
  finalTime 
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
    }, 100);
    
    return () => clearInterval(interval);
  }, [startTime, finalTime]);
  
  return (
    <span className="tabular-nums text-slate-400">
      {elapsed}s
    </span>
  );
});

// Get icon for step type/title
function getStepIcon(step: AgentStep) {
  const title = step.title.toLowerCase();
  const type = step.type;
  
  if (title.includes('analyz') || title.includes('routing') || title.includes('query')) {
    return <Cpu className="w-3 h-3" />;
  }
  if (title.includes('scanner') || title.includes('market') || title.includes('snapshot')) {
    return <TrendingUp className="w-3 h-3" />;
  }
  if (title.includes('data') || title.includes('historical') || title.includes('classify') || title.includes('synthetic')) {
    return <Database className="w-3 h-3" />;
  }
  if (title.includes('search') || title.includes('research')) {
    return <Search className="w-3 h-3" />;
  }
  if (type === 'code' || title.includes('code') || title.includes('execut')) {
    return <Code2 className="w-3 h-3" />;
  }
  if (title.includes('select') || title.includes('tool') || title.includes('using')) {
    return <Zap className="w-3 h-3" />;
  }
  return <Sparkles className="w-3 h-3" />;
}

// Individual step item - Claude Code style
const StepItem = memo(function StepItem({ 
  step,
  showDetails
}: { 
  step: AgentStep;
  showDetails?: boolean;
}) {
  const isRunning = step.status === 'running';
  const isComplete = step.status === 'complete';
  const isError = step.status === 'error';
  
  return (
    <div className="animate-in fade-in slide-in-from-left-2 duration-200">
      <div className="flex items-start gap-2 py-0.5">
        {/* Status indicator */}
        <div className={`
          w-4 h-4 rounded flex items-center justify-center flex-shrink-0 mt-0.5
          ${isRunning ? 'text-blue-500 bg-blue-50' : ''}
          ${isComplete ? 'text-emerald-600 bg-emerald-50' : ''}
          ${isError ? 'text-red-500 bg-red-50' : ''}
          ${!isRunning && !isComplete && !isError ? 'text-slate-400 bg-slate-50' : ''}
        `}>
          {isRunning ? (
            <Loader2 className="w-2.5 h-2.5 animate-spin" />
          ) : isComplete ? (
            <Check className="w-2.5 h-2.5" />
          ) : isError ? (
            <AlertCircle className="w-2.5 h-2.5" />
          ) : (
            getStepIcon(step)
          )}
        </div>
        
        {/* Content */}
        <div className="flex-1 min-w-0">
          <span className={`
            text-[11px] font-[family-name:var(--font-mono-selected)]
            ${isRunning ? 'text-blue-700' : ''}
            ${isComplete ? 'text-slate-700' : ''}
            ${isError ? 'text-red-600' : ''}
            ${!isRunning && !isComplete && !isError ? 'text-slate-500' : ''}
          `}>
            {step.title}
          </span>
          {step.description && step.description !== step.title && (
            <span className={`
              text-[10px] ml-1.5
              ${isRunning ? 'text-blue-500' : 'text-slate-400'}
            `}>
              {step.description}
            </span>
          )}
        </div>
      </div>
      
      {/* Show details inline if available and running */}
      {showDetails && step.details && step.details.length > 10 && (
        <div className="ml-6 mt-1 mb-2 p-2 bg-slate-50 rounded text-[10px] font-mono text-slate-600 max-h-32 overflow-y-auto whitespace-pre-wrap border-l-2 border-blue-200">
          {step.details.length > 500 ? step.details.substring(0, 500) + '...' : step.details}
        </div>
      )}
    </div>
  );
});

export const AgentSteps = memo(function AgentSteps({ steps, thinkingTime }: AgentStepsProps) {
  const [collapsed, setCollapsed] = useState(false);
  const startTimeRef = useRef<number>(Date.now());
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Reset start time when steps change from 0 to >0
  useEffect(() => {
    if (steps.length === 1 && steps[0].status === 'running') {
      startTimeRef.current = Date.now();
    }
  }, [steps.length]);
  
  // Auto-scroll to show new steps
  useEffect(() => {
    if (containerRef.current && !collapsed) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [steps.length, collapsed]);
  
  if (!steps || steps.length === 0) return null;
  
  const isProcessing = steps.some(s => s.status === 'running');
  const hasErrors = steps.some(s => s.status === 'error');
  const toolSteps = steps.filter(s => s.type === 'tool');
  const runningStep = steps.find(s => s.status === 'running');
  
  return (
    <div className="text-[11px] border border-slate-200 rounded-lg overflow-hidden bg-white">
      {/* Header */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className={`
          w-full flex items-center gap-2 px-3 py-2 text-left
          ${isProcessing ? 'bg-blue-50/50' : hasErrors ? 'bg-red-50/50' : 'bg-slate-50'}
          hover:bg-slate-100 transition-colors
        `}
      >
        {/* Status icon */}
        {isProcessing ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500 flex-shrink-0" />
        ) : hasErrors ? (
          <AlertCircle className="w-3.5 h-3.5 text-red-500 flex-shrink-0" />
        ) : (
          <Check className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
        )}
        
        {/* Status text - show current action if processing */}
        <span className={`
          font-medium font-[family-name:var(--font-mono-selected)] flex-1 truncate
          ${isProcessing ? 'text-blue-700' : hasErrors ? 'text-red-700' : 'text-slate-600'}
        `}>
          {isProcessing && runningStep 
            ? runningStep.title 
            : hasErrors 
              ? 'Error' 
              : 'Completed'
          }
        </span>
        
        {/* Timer */}
        <ElapsedTimer 
          startTime={startTimeRef.current} 
          finalTime={thinkingTime} 
        />
        
        {/* Tool count */}
        {toolSteps.length > 0 && (
          <span className="text-[9px] px-1.5 py-0.5 bg-slate-200/60 text-slate-500 rounded">
            {toolSteps.length} tool{toolSteps.length > 1 ? 's' : ''}
          </span>
        )}
        
        {/* Collapse icon */}
        {collapsed ? (
          <ChevronRight className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
        ) : (
          <ChevronDown className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
        )}
      </button>
      
      {/* Steps list */}
      {!collapsed && (
        <div 
          ref={containerRef}
          className="px-3 py-2 space-y-0.5 max-h-48 overflow-y-auto border-t border-slate-100"
        >
          {steps.map((step, index) => (
            <StepItem 
              key={step.id} 
              step={step} 
              showDetails={step.status === 'running' || (step.status === 'complete' && index === steps.length - 1)}
            />
          ))}
        </div>
      )}
    </div>
  );
});

export default AgentSteps;
