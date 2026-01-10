'use client';

import { memo, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Scan,
  Code2,
  CheckCircle2,
  Loader2,
  AlertCircle,
  Database,
  TrendingUp,
  Clock
} from 'lucide-react';
import type { AgentStep } from './types';

interface AgentStepsProps {
  steps: AgentStep[];
  thinkingTime?: number;
}

// Tool card component - similar to "Market Scanner Enabled"
const ToolCard = memo(function ToolCard({ step }: { step: AgentStep }) {
  const isComplete = step.status === 'complete';
  const isRunning = step.status === 'running';
  const isError = step.status === 'error';

  const getIcon = () => {
    if (step.title.toLowerCase().includes('scanner') || step.title.toLowerCase().includes('market')) {
      return <Scan className="w-5 h-5" />;
    }
    if (step.title.toLowerCase().includes('data') || step.title.toLowerCase().includes('historical')) {
      return <Database className="w-5 h-5" />;
    }
    if (step.title.toLowerCase().includes('code') || step.title.toLowerCase().includes('analysis')) {
      return <Code2 className="w-5 h-5" />;
    }
    return <TrendingUp className="w-5 h-5" />;
  };

  return (
    <div className={`
      flex items-center gap-3 p-3 rounded-xl border transition-all duration-300
      ${isComplete ? 'bg-white border-gray-200' : ''}
      ${isRunning ? 'bg-blue-50/50 border-blue-200' : ''}
      ${isError ? 'bg-red-50/50 border-red-200' : ''}
      ${!isComplete && !isRunning && !isError ? 'bg-gray-50 border-gray-200' : ''}
    `}>
      {/* Icon container */}
      <div className={`
        w-10 h-10 rounded-lg flex items-center justify-center
        ${isComplete ? 'bg-gray-100 text-gray-600' : ''}
        ${isRunning ? 'bg-blue-100 text-blue-600' : ''}
        ${isError ? 'bg-red-100 text-red-600' : ''}
        ${!isComplete && !isRunning && !isError ? 'bg-gray-100 text-gray-500' : ''}
      `}>
        {isRunning ? (
          <Loader2 className="w-5 h-5 animate-spin" />
        ) : (
          getIcon()
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className={`font-medium text-[14px] ${isError ? 'text-red-700' : 'text-gray-900'}`}>
          {step.title}
        </div>
        {step.description && (
          <div className={`text-[12px] ${isError ? 'text-red-600' : 'text-gray-500'}`}>
            {step.description}
          </div>
        )}
      </div>

      {/* Status indicator */}
      <div className="flex-shrink-0">
        {isComplete && <CheckCircle2 className="w-5 h-5 text-emerald-500" />}
        {isRunning && <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />}
        {isError && <AlertCircle className="w-5 h-5 text-red-500" />}
      </div>
    </div>
  );
});

// Reasoning section - ALWAYS VISIBLE with real-time updates
const ReasoningSection = memo(function ReasoningSection({
  steps,
  duration,
  expanded,
  onToggle
}: {
  steps: AgentStep[];
  duration?: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  const isStillProcessing = !duration || steps.some(s => s.status === 'running');

  return (
    <div className="space-y-2">
      {/* Header - "Reasoning for X seconds" - clickable to collapse */}
      <button
        onClick={onToggle}
        className="flex items-center gap-2 text-[13px] text-gray-500 hover:text-gray-700 transition-colors group"
      >
        {isStillProcessing ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
        ) : (
          <Clock className="w-3.5 h-3.5 opacity-60" />
        )}
        <span className="font-medium">
          {duration
            ? `Reasoned for ${duration} second${duration !== 1 ? 's' : ''}`
            : `Reasoning for ${Math.floor((Date.now() - (steps[0]?.id ? Date.now() : Date.now())) / 1000) || '...'} seconds`
          }
        </span>
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 opacity-50 group-hover:opacity-100" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 opacity-50 group-hover:opacity-100" />
        )}
      </button>

      {/* ALWAYS show reasoning content when expanded - even if empty show loading */}
      {expanded && (
        <div className="pl-2 space-y-3 animate-in fade-in slide-in-from-top-2 duration-200">
          <div className="pl-3 border-l-2 border-blue-200 space-y-3">
            {steps.length === 0 ? (
              // Show loading state when no steps yet
              <div className="flex items-center gap-2 text-[13px] text-gray-500">
                <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                <span>Analyzing your query...</span>
              </div>
            ) : (
              // Show each step as it arrives
              steps.map((step, index) => {
                const isRunning = step.status === 'running';
                const isComplete = step.status === 'complete';
                const hasDetails = step.details && step.details.length > 0;
                // Show thinking details for any reasoning step with details
                const showThinkingDetails = step.type === 'reasoning' && hasDetails;

                return (
                  <div key={step.id} className="animate-in fade-in slide-in-from-left-2 duration-200">
                    <div className="flex items-start gap-3">
                      {/* Step indicator */}
                      <div className="flex-shrink-0 mt-0.5">
                        {isRunning ? (
                          <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                        ) : isComplete ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                        ) : (
                          <div className="w-4 h-4 rounded-full border-2 border-gray-300" />
                        )}
                      </div>

                      {/* Step content */}
                      <div className="flex-1 min-w-0">
                        <div className={`text-[13px] font-medium ${isRunning ? 'text-blue-700' : 'text-gray-800'}`}>
                          {step.title}
                        </div>
                        {step.description && !showThinkingDetails && (
                          <div className="text-[12px] text-gray-500 mt-0.5">
                            {step.description}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Show thinking details for reasoning steps */}
                    {showThinkingDetails && step.details && (
                      <div className="ml-7 mt-2 pl-3 border-l-2 border-blue-200 bg-blue-50/30 rounded-r py-2 px-3">
                        <div className="text-[12px] text-gray-700 leading-relaxed whitespace-pre-wrap">
                          {step.details.length > 800
                            ? step.details.substring(0, 800) + '...'
                            : step.details
                          }
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
});

// Code execution card - expandable with details
const CodeCard = memo(function CodeCard({ step }: { step: AgentStep }) {
  const [expanded, setExpanded] = useState(false);
  const isComplete = step.status === 'complete';
  const isRunning = step.status === 'running';
  const isError = step.status === 'error';

  return (
    <div className={`
      rounded-xl border transition-all duration-300 overflow-hidden
      ${isComplete ? 'bg-emerald-50/50 border-emerald-200' : ''}
      ${isRunning ? 'bg-blue-50/50 border-blue-200' : ''}
      ${isError ? 'bg-red-50/50 border-red-200' : ''}
    `}>
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 p-3 hover:bg-black/5 transition-colors"
      >
        <div className={`
          w-8 h-8 rounded-lg flex items-center justify-center
          ${isComplete ? 'bg-emerald-100 text-emerald-600' : ''}
          ${isRunning ? 'bg-blue-100 text-blue-600' : ''}
          ${isError ? 'bg-red-100 text-red-600' : ''}
        `}>
          {isRunning ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Code2 className="w-4 h-4" />
          )}
        </div>

        <div className="flex-1 text-left min-w-0">
          <div className={`font-medium text-[13px] ${isError ? 'text-red-700' : 'text-gray-900'}`}>
            {step.title}
          </div>
          {step.description && (
            <div className={`text-[11px] ${isError ? 'text-red-600' : 'text-gray-500'}`}>
              {step.description}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {isComplete && <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
          {isError && <AlertCircle className="w-4 h-4 text-red-500" />}
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-400" />
          )}
        </div>
      </button>

      {/* Expanded code content */}
      {expanded && step.details && (
        <div className="border-t border-gray-200 bg-gray-50 p-3 animate-in fade-in duration-200">
          <pre className="text-[11px] font-mono text-gray-800 whitespace-pre-wrap overflow-x-auto max-h-60 overflow-y-auto">
            {step.details}
          </pre>
        </div>
      )}
    </div>
  );
});

export const AgentSteps = memo(function AgentSteps({ steps, thinkingTime }: AgentStepsProps) {
  // Auto-expand reasoning while processing, collapse when done
  const hasRunningSteps = steps.some(s => s.status === 'running');
  const [showReasoning, setShowReasoning] = useState(true); // Start expanded

  if (!steps || steps.length === 0) return null;

  // Categorize steps
  const reasoningSteps = steps.filter(s => s.type === 'reasoning');
  const toolSteps = steps.filter(s => s.type === 'tool');
  const codeSteps = steps.filter(s => s.type === 'code');

  return (
    <div className="space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-300">
      {/* Reasoning section header */}
      {reasoningSteps.length > 0 && (
        <ReasoningSection
          steps={reasoningSteps}
          duration={thinkingTime}
          expanded={showReasoning}
          onToggle={() => setShowReasoning(!showReasoning)}
        />
      )}

      {/* Tool cards - Market Scanner, Data Sources, etc. */}
      {toolSteps.map(step => (
        <ToolCard key={step.id} step={step} />
      ))}

      {/* Code execution cards */}
      {codeSteps.map(step => (
        <CodeCard key={step.id} step={step} />
      ))}
    </div>
  );
});

export default AgentSteps;
