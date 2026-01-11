'use client';

import { memo, useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Check, 
  Loader2, 
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Clock,
  ArrowRight
} from 'lucide-react';

interface WorkflowStep {
  id: string;
  type: string;
  label: string;
  icon: React.ReactNode;
  config?: Record<string, any>;
}

interface StepResult {
  status: 'pending' | 'running' | 'success' | 'error';
  data?: any;
  error?: string;
  executionTime?: number;
}

interface WorkflowExecutionProps {
  steps: WorkflowStep[];
  results: Record<string, StepResult>;
  isRunning: boolean;
  currentStepId?: string;
  totalTime?: number;
  onClose: () => void;
}

export const WorkflowExecution = memo(function WorkflowExecution({
  steps,
  results,
  isRunning,
  currentStepId,
  totalTime,
  onClose
}: WorkflowExecutionProps) {
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-expand current step
  useEffect(() => {
    if (currentStepId) {
      setExpandedSteps(prev => new Set([...prev, currentStepId]));
    }
  }, [currentStepId]);

  // Auto-scroll to current step
  useEffect(() => {
    if (currentStepId && scrollRef.current) {
      const element = document.getElementById(`step-${currentStepId}`);
      element?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [currentStepId]);

  const toggleStep = (stepId: string) => {
    setExpandedSteps(prev => {
      const next = new Set(prev);
      if (next.has(stepId)) next.delete(stepId);
      else next.add(stepId);
      return next;
    });
  };

  const getStepStatus = (stepId: string): StepResult['status'] => {
    return results[stepId]?.status || 'pending';
  };

  const completedCount = Object.values(results).filter(r => r.status === 'success').length;
  const progress = steps.length > 0 ? (completedCount / steps.length) * 100 : 0;

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-gray-200">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[13px] font-medium text-gray-800">
            Workflow Execution
          </span>
          <div className="flex items-center gap-2">
            {totalTime && (
              <span className="flex items-center gap-1 text-[11px] text-gray-500">
                <Clock className="w-3 h-3" />
                {(totalTime / 1000).toFixed(1)}s
              </span>
            )}
            {isRunning ? (
              <span className="flex items-center gap-1 px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-[10px] font-medium">
                <Loader2 className="w-3 h-3 animate-spin" />
                Running
              </span>
            ) : completedCount === steps.length ? (
              <span className="flex items-center gap-1 px-2 py-0.5 bg-green-100 text-green-700 rounded text-[10px] font-medium">
                <Check className="w-3 h-3" />
                Complete
              </span>
            ) : null}
          </div>
        </div>
        
        {/* Progress bar */}
        <div className="w-full h-1 bg-gray-100 rounded-full overflow-hidden">
          <motion.div 
            className="h-full bg-blue-500"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.3 }}
          />
        </div>
      </div>

      {/* Steps */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="p-3 space-y-1">
          {steps.map((step, idx) => {
            const status = getStepStatus(step.id);
            const result = results[step.id];
            const isExpanded = expandedSteps.has(step.id);
            const isCurrent = currentStepId === step.id;

            return (
              <div
                key={step.id}
                id={`step-${step.id}`}
                className={`
                  rounded-lg border transition-all
                  ${isCurrent 
                    ? 'border-blue-500 bg-blue-50/50' 
                    : status === 'success'
                    ? 'border-green-200 bg-green-50/30'
                    : status === 'error'
                    ? 'border-red-200 bg-red-50/30'
                    : 'border-gray-200'
                  }
                `}
              >
                {/* Step Header */}
                <button
                  onClick={() => result && toggleStep(step.id)}
                  className="w-full flex items-center gap-2 px-3 py-2 text-left"
                  disabled={!result}
                >
                  {/* Status Icon */}
                  <div className={`
                    flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center
                    ${status === 'running' 
                      ? 'bg-blue-500 text-white' 
                      : status === 'success'
                      ? 'bg-green-500 text-white'
                      : status === 'error'
                      ? 'bg-red-500 text-white'
                      : 'bg-gray-200 text-gray-500'
                    }
                  `}>
                    {status === 'running' ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : status === 'success' ? (
                      <Check className="w-3 h-3" />
                    ) : status === 'error' ? (
                      <AlertCircle className="w-3 h-3" />
                    ) : (
                      <span className="text-[10px] font-medium">{idx + 1}</span>
                    )}
                  </div>

                  {/* Step Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-gray-500">{step.icon}</span>
                      <span className="text-[12px] font-medium text-gray-800">{step.label}</span>
                    </div>
                  </div>

                  {/* Execution Time & Expand */}
                  <div className="flex items-center gap-2">
                    {result?.executionTime && (
                      <span className="text-[10px] text-gray-400">
                        {result.executionTime}ms
                      </span>
                    )}
                    {result && (
                      isExpanded ? (
                        <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5 text-gray-400" />
                      )
                    )}
                  </div>
                </button>

                {/* Expanded Content */}
                <AnimatePresence>
                  {isExpanded && result && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="px-3 pb-3 pt-1 border-t border-gray-100">
                        {result.error ? (
                          <div className="p-2 bg-red-50 rounded text-[11px] text-red-600 font-mono">
                            {result.error}
                          </div>
                        ) : result.data ? (
                          <div className="space-y-2">
                            {/* Data count */}
                            {result.data.count !== undefined && (
                              <div className="text-[11px] text-gray-600">
                                <span className="font-medium text-blue-600">{result.data.count}</span> items returned
                              </div>
                            )}
                            
                            {/* Data preview */}
                            {result.data.preview && (
                              <div className="p-2 bg-gray-50 rounded max-h-24 overflow-y-auto">
                                <pre className="text-[10px] text-gray-600 font-mono whitespace-pre-wrap">
                                  {JSON.stringify(result.data.preview, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="text-[11px] text-gray-400">
                            No output data
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer */}
      <div className="flex-shrink-0 p-3 border-t border-gray-200 bg-gray-50">
        <button
          onClick={onClose}
          disabled={isRunning}
          className={`
            w-full px-3 py-2 text-[12px] font-medium rounded-lg transition-colors
            ${isRunning
              ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
              : 'bg-blue-600 hover:bg-blue-700 text-white'
            }
          `}
        >
          {isRunning ? 'Running...' : 'View Results'}
        </button>
      </div>
    </div>
  );
});
