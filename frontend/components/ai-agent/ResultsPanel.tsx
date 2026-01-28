'use client';

import { memo } from 'react';
import { Terminal, Table2, BarChart3 } from 'lucide-react';
import { ResultBlock } from './ResultBlock';
import type { ResultBlockData } from './types';

interface ResultsPanelProps {
  blocks: ResultBlockData[];
  onToggleCode: (blockId: string) => void;
}


export const ResultsPanel = memo(function ResultsPanel({ 
  blocks, 
  onToggleCode
}: ResultsPanelProps) {
  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-2 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-slate-500" />
          <span className="text-[13px] font-medium text-slate-700">Resultados</span>
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {blocks.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <Terminal className="w-8 h-8 text-slate-200 mb-2" />
            <p className="text-[12px] text-slate-400">
              Los resultados aparecerán aquí
            </p>
          </div>
        ) : (
          blocks.map((block) => (
            <ResultBlock
              key={block.id}
              block={block}
              onToggleCode={() => onToggleCode(block.id)}
            />
          ))
        )}
      </div>
    </div>
  );
});
