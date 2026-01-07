'use client';

import { memo } from 'react';
import { Terminal, Table2, BarChart3 } from 'lucide-react';
import { ResultBlock } from './ResultBlock';
import type { ResultBlockData } from './types';

interface ResultsPanelProps {
  blocks: ResultBlockData[];
  onToggleCode: (blockId: string) => void;
}

export const ResultsPanel = memo(function ResultsPanel({ blocks, onToggleCode }: ResultsPanelProps) {
  const tableCount = blocks.filter(b => b.result?.outputs?.some(o => o.type === 'table')).length;
  const chartCount = blocks.filter(b => b.result?.outputs?.some(o => o.type === 'chart')).length;

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-2 border-b border-gray-200 bg-white">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-blue-600" />
            <span className="text-[13px] font-medium text-gray-700">Resultados</span>
          </div>

          {blocks.length > 0 && (
            <div className="flex items-center gap-3 text-[11px] text-gray-400">
              {tableCount > 0 && (
                <span className="flex items-center gap-1">
                  <Table2 className="w-3 h-3" />
                  {tableCount} tabla{tableCount > 1 ? 's' : ''}
                </span>
              )}
              {chartCount > 0 && (
                <span className="flex items-center gap-1">
                  <BarChart3 className="w-3 h-3" />
                  {chartCount} grafico{chartCount > 1 ? 's' : ''}
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {blocks.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mb-3">
              <Terminal className="w-6 h-6 text-gray-300" />
            </div>
            <p className="text-[13px] text-gray-400">
              Los resultados apareceran aqui
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
