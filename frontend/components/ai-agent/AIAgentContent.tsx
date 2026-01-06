'use client';

import { memo } from 'react';
import { useAIAgent } from './useAIAgent';
import { ChatPanel } from './ChatPanel';
import { ResultsPanel } from './ResultsPanel';

interface AIAgentContentProps {
  /** Callback cuando cambia la sesion del mercado */
  onMarketUpdate?: (session: string) => void;
}

export const AIAgentContent = memo(function AIAgentContent({
  onMarketUpdate
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

  return (
    <div className="flex h-full w-full min-h-0 bg-white overflow-hidden">
      {/* Chat Panel - 35% width */}
      <div className="w-[35%] min-w-[280px] max-w-[400px] border-r border-gray-200 flex flex-col min-h-0">
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

      {/* Results Panel - resto del ancho */}
      <div className="flex-1 min-w-0 min-h-0 flex flex-col">
        <ResultsPanel
          blocks={resultBlocks}
          onToggleCode={toggleCodeVisibility}
        />
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
