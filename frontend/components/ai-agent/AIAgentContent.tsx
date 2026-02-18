'use client';

import { memo, useEffect } from 'react';
import { useAIAgent } from './useAIAgent';
import { ChatPanel } from './ChatPanel';
import { ResultsPanel } from './ResultsPanel';
import type { ChartContext } from './types';

interface AIAgentContentProps {
  onMarketUpdate?: (session: string) => void;
}

export const AIAgentContent = memo(function AIAgentContent({
  onMarketUpdate,
}: AIAgentContentProps) {
  const {
    messages,
    resultBlocks,
    isConnected,
    isLoading,
    marketContext,
    error,
    chartContext,
    sendMessage,
    setChartContext,
    sendClarificationChoice,
    clearHistory,
    toggleCodeVisibility,
  } = useAIAgent({ onMarketUpdate });

  // Listen for agent:send events (from Deep Research button, etc.)
  useEffect(() => {
    const handleAgentSend = (e: CustomEvent<{ message: string }>) => {
      if (e.detail?.message) {
        sendMessage(e.detail.message);
      }
    };

    window.addEventListener('agent:send', handleAgentSend as EventListener);
    return () => window.removeEventListener('agent:send', handleAgentSend as EventListener);
  }, [sendMessage]);

  // Listen for agent:chart-ask events (from TradingChart context menu)
  useEffect(() => {
    const handleChartAsk = (e: CustomEvent<{ chartContext: ChartContext; prompt: string }>) => {
      if (e.detail?.chartContext && e.detail?.prompt) {
        setChartContext(e.detail.chartContext);
        // Pass chartContext directly to avoid React state timing issues
        sendMessage(e.detail.prompt, e.detail.chartContext);
      }
    };

    window.addEventListener('agent:chart-ask', handleChartAsk as EventListener);
    return () => window.removeEventListener('agent:chart-ask', handleChartAsk as EventListener);
  }, [sendMessage, setChartContext]);

  return (
    <div className="flex flex-col h-full w-full min-h-0 bg-white overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 flex items-center justify-end px-4 py-2 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-green-500' : 'bg-slate-400'}`} />
          <span className="text-[11px] text-slate-500">
            {isConnected ? 'Connected' : 'Connecting...'}
          </span>
        </div>
      </div>

      {/* Content: Chat + Results */}
      <div className="flex-1 min-h-0 overflow-hidden flex">
        {/* Chat Panel - 30% */}
        <div className="w-[30%] min-w-[260px] max-w-[350px] border-r border-slate-200 flex flex-col min-h-0 bg-white">
          <ChatPanel
            messages={messages}
            isConnected={isConnected}
            isLoading={isLoading}
            marketContext={marketContext}
            error={error}
            chartContext={chartContext}
            onSendMessage={sendMessage}
            onClearChartContext={() => setChartContext(null)}
            onClarificationChoice={sendClarificationChoice}
            onClearHistory={clearHistory}
          />
        </div>

        {/* Results Panel - 70% */}
        <div className="flex-1 min-w-0 min-h-0 flex flex-col">
          <ResultsPanel
            blocks={resultBlocks}
            onToggleCode={toggleCodeVisibility}
          />
        </div>
      </div>
    </div>
  );
});

export function AIAgentWindow() {
  return (
    <div className="h-full w-full bg-white">
      <AIAgentContent />
    </div>
  );
}
