'use client';

import { memo, useState, useEffect, useRef } from 'react';
import type { AgentStep } from './types';

interface AgentStepsProps {
  steps: AgentStep[];
  thinkingTime?: number;
}

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
  
  return <span className="text-slate-400">{elapsed}s</span>;
});

const StepItem = memo(function StepItem({ step }: { step: AgentStep }) {
  const isRunning = step.status === 'running';
  const isComplete = step.status === 'complete';
  const isError = step.status === 'error';
  
  return (
    <div className="flex items-center gap-2 py-0.5 text-[11px]">
      <span className={`w-1.5 h-1.5 rounded-full ${
        isRunning ? 'bg-slate-400 animate-pulse' : 
        isComplete ? 'bg-slate-400' : 
        isError ? 'bg-slate-600' : 'bg-slate-300'
      }`} />
      <span className={isError ? 'text-slate-700' : 'text-slate-600'}>
        {step.title}
      </span>
    </div>
  );
});

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
  const runningStep = steps.find(s => s.status === 'running');
  
  return (
    <div className="text-[11px] border border-slate-200 rounded overflow-hidden">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left bg-slate-50 hover:bg-slate-100"
      >
        <span className="flex-1 text-slate-600 truncate">
          {isProcessing && runningStep 
            ? runningStep.title 
            : hasErrors ? 'Error' : 'Completed'
          }
        </span>
        <ElapsedTimer startTime={startTimeRef.current} finalTime={thinkingTime} />
        <span className="text-slate-400">{collapsed ? '+' : '-'}</span>
      </button>
      
      {!collapsed && (
        <div className="px-3 py-2 space-y-0.5 border-t border-slate-100 max-h-40 overflow-y-auto">
          {steps.map((step) => (
            <StepItem key={step.id} step={step} />
          ))}
        </div>
      )}
    </div>
  );
});

export default AgentSteps;
