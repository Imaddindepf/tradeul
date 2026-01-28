'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { useAIAgent } from './useAIAgent';
import { ChatPanel } from './ChatPanel';
import { ResultsPanel } from './ResultsPanel';
import { MessageSquare, Layers } from 'lucide-react';

// Dynamic import for React Flow (avoid SSR issues)
const WorkflowEditor = dynamic(
  () => import('./WorkflowEditor').then((mod) => mod.WorkflowEditor),
  { 
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-full bg-slate-50">
        <div className="text-center">
          <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
          <p className="text-[12px] text-slate-500">Loading editor...</p>
        </div>
      </div>
    )
  }
);

type ViewMode = 'editor' | 'chat';

interface AIAgentContentProps {
  /** Callback cuando cambia la sesion del mercado */
  onMarketUpdate?: (session: string) => void;
  /** Start directly in chat mode */
  startInChat?: boolean;
}

export const AIAgentContent = memo(function AIAgentContent({
  onMarketUpdate,
  startInChat = false
}: AIAgentContentProps) {
  const {
    messages,
    resultBlocks,
    isConnected,
    isLoading,
    marketContext,
    error,
    sendMessage,
    clearHistory,
    toggleCodeVisibility
  } = useAIAgent({ onMarketUpdate });

  const [viewMode, setViewMode] = useState<ViewMode>(startInChat ? 'chat' : 'editor');

  // Listen for agent:send events (from Deep Research button, etc.)
  useEffect(() => {
    const handleAgentSend = (e: CustomEvent<{ message: string }>) => {
      if (e.detail?.message) {
        sendMessage(e.detail.message);
        setViewMode('chat'); // Switch to chat to show the result
      }
    };
    
    window.addEventListener('agent:send', handleAgentSend as EventListener);
    return () => window.removeEventListener('agent:send', handleAgentSend as EventListener);
  }, [sendMessage]);

  const handleWorkflowExecute = useCallback(async () => {
    // Results are shown directly in the workflow nodes
    // No need to switch to chat - the nodes update with status and data
    console.log('Workflow execution completed - results shown in nodes');
  }, []);

  return (
    <div className="flex flex-col h-full w-full min-h-0 bg-white overflow-hidden">
      {/* View Toggle Header */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-2 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-1 p-0.5 bg-slate-100 rounded-lg">
          <button
            onClick={() => setViewMode('editor')}
            className={`
              flex items-center gap-1.5 px-3 py-1.5 rounded text-[12px] font-medium transition-all
              ${viewMode === 'editor' 
                ? 'bg-white text-slate-800 shadow-sm' 
                : 'text-slate-500 hover:text-slate-700'
              }
            `}
          >
            <Layers className="w-3.5 h-3.5" />
            Workflow
          </button>
          <button
            onClick={() => setViewMode('chat')}
            className={`
              flex items-center gap-1.5 px-3 py-1.5 rounded text-[12px] font-medium transition-all
              ${viewMode === 'chat' 
                ? 'bg-white text-slate-800 shadow-sm' 
                : 'text-slate-500 hover:text-slate-700'
              }
            `}
          >
            <MessageSquare className="w-3.5 h-3.5" />
            Chat
          </button>
        </div>

        {/* Connection Status */}
        <div className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-green-500' : 'bg-slate-400'}`} />
          <span className="text-[11px] text-slate-500">
            {isConnected ? 'Connected' : 'Connecting...'}
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {viewMode === 'editor' ? (
          <WorkflowEditor onExecute={handleWorkflowExecute} />
        ) : (
          <div className="flex h-full">
      {/* Chat Panel - 30% width (narrower, just for reasoning) */}
      <div className="w-[30%] min-w-[260px] max-w-[350px] border-r border-slate-200 flex flex-col min-h-0 bg-white">
        <ChatPanel
          messages={messages}
          isConnected={isConnected}
          isLoading={isLoading}
          marketContext={marketContext}
          error={error}
          onSendMessage={sendMessage}
          onClearHistory={clearHistory}
        />
      </div>

      {/* Results Panel */}
      <div className="flex-1 min-w-0 min-h-0 flex flex-col">
        <ResultsPanel
          blocks={resultBlocks}
          onToggleCode={toggleCodeVisibility}
        />
            </div>
          </div>
        )}
      </div>
    </div>
  );
});

// Exportar tambien un componente standalone para uso directo
export function AIAgentWindow() {
  return (
    <div className="h-full w-full bg-white">
      <AIAgentContent />
    </div>
  );
}
