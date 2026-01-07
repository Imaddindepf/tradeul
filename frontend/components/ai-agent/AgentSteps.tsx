'use client';

import { memo, useState } from 'react';
import { 
  ChevronDown, 
  ChevronRight,
  Brain,
  Scan,
  Code2,
  CheckCircle2,
  Loader2,
  AlertCircle,
  BarChart3
} from 'lucide-react';
import type { AgentStep } from './types';

interface AgentStepsProps {
  steps: AgentStep[];
  thinkingTime?: number;
}

const stepIcons: Record<string, React.ElementType> = {
  reasoning: Brain,
  tool: Scan,
  code: Code2,
  result: BarChart3,
};

const StepCard = memo(function StepCard({ step }: { step: AgentStep }) {
  const [expanded, setExpanded] = useState(step.expanded ?? false);
  const Icon = stepIcons[step.type] || Brain;

  const statusStyles = {
    pending: 'bg-gray-100 border-gray-200 text-gray-500',
    running: 'bg-blue-50 border-blue-200 text-blue-700',
    complete: 'bg-emerald-50 border-emerald-200 text-emerald-700',
    error: 'bg-red-50 border-red-200 text-red-700',
  };

  const iconBgStyles = {
    pending: 'bg-gray-200 text-gray-500',
    running: 'bg-blue-100 text-blue-600',
    complete: 'bg-emerald-100 text-emerald-600',
    error: 'bg-red-100 text-red-600',
  };

  return (
    <div 
      className={`
        rounded-xl border px-4 py-3 transition-all duration-300 ease-out
        ${statusStyles[step.status]}
        ${step.expandable ? 'cursor-pointer hover:shadow-md' : ''}
      `}
      onClick={() => step.expandable && setExpanded(!expanded)}
    >
      <div className="flex items-center gap-3">
        {/* Icon */}
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${iconBgStyles[step.status]}`}>
          {step.status === 'running' ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : step.status === 'complete' ? (
            <CheckCircle2 className="w-4 h-4" />
          ) : step.status === 'error' ? (
            <AlertCircle className="w-4 h-4" />
          ) : (
            <Icon className="w-4 h-4" />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="font-medium text-sm">{step.title}</div>
          {step.description && (
            <div className="text-xs opacity-75 truncate">{step.description}</div>
          )}
        </div>

        {/* Status indicator */}
        <div className="flex items-center gap-2">
          {step.status === 'complete' && (
            <CheckCircle2 className="w-5 h-5 text-emerald-500" />
          )}
          {step.expandable && (
            expanded ? (
              <ChevronDown className="w-4 h-4 opacity-50" />
            ) : (
              <ChevronRight className="w-4 h-4 opacity-50" />
            )
          )}
        </div>
      </div>

      {/* Expanded details */}
      {expanded && step.details && (
        <div className="mt-3 pt-3 border-t border-current/10">
          <pre className="text-xs font-mono whitespace-pre-wrap opacity-80 max-h-40 overflow-y-auto">
            {step.details}
          </pre>
        </div>
      )}
    </div>
  );
});

const ThinkingIndicator = memo(function ThinkingIndicator({ 
  duration, 
  expanded,
  onToggle 
}: { 
  duration?: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 transition-colors py-2"
    >
      <Brain className="w-4 h-4" />
      <span>
        {duration 
          ? `Reasoned for ${duration} second${duration !== 1 ? 's' : ''}`
          : 'Reasoning...'
        }
      </span>
      {expanded ? (
        <ChevronDown className="w-4 h-4" />
      ) : (
        <ChevronRight className="w-4 h-4" />
      )}
    </button>
  );
});

export const AgentSteps = memo(function AgentSteps({ steps, thinkingTime }: AgentStepsProps) {
  const [showThinking, setShowThinking] = useState(false);

  if (!steps || steps.length === 0) return null;

  // Group steps by type for display
  const reasoningSteps = steps.filter(s => s.type === 'reasoning');
  const actionSteps = steps.filter(s => s.type !== 'reasoning');

  return (
    <div className="space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-300">
      {/* Thinking/Reasoning section */}
      {reasoningSteps.length > 0 && (
        <div>
          <ThinkingIndicator 
            duration={thinkingTime}
            expanded={showThinking}
            onToggle={() => setShowThinking(!showThinking)}
          />
          
          {showThinking && (
            <div className="ml-6 mt-2 space-y-2 animate-in fade-in slide-in-from-top-2 duration-200">
              {reasoningSteps.map(step => (
                <div key={step.id} className="text-sm text-gray-600 pl-3 border-l-2 border-gray-200">
                  {step.description || step.title}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Action steps - Tools and Code */}
      {actionSteps.map(step => (
        <StepCard key={step.id} step={step} />
      ))}
    </div>
  );
});

export default AgentSteps;

