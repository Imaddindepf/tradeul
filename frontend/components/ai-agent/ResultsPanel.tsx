'use client';

import { memo } from 'react';
import { Terminal, BarChart3, Table2 } from 'lucide-react';
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
  // Contar tipos de outputs
  const tableCount = blocks.filter(b =>
    b.result?.outputs?.some(o => o.type === 'table')
  ).length;

  const chartCount = blocks.filter(b =>
    b.result?.outputs?.some(o => o.type === 'chart')
  ).length;

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-gray-200 bg-white">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Terminal className="w-4 h-4 text-blue-600" />
            <h2 className="text-sm font-semibold text-gray-800">Resultados</h2>
          </div>

          {/* Stats */}
          {blocks.length > 0 && (
            <div className="flex items-center gap-3 text-xs text-gray-500">
              {tableCount > 0 && (
                <div className="flex items-center gap-1">
                  <Table2 className="w-3 h-3" />
                  <span>{tableCount} tabla{tableCount !== 1 ? 's' : ''}</span>
                </div>
              )}
              {chartCount > 0 && (
                <div className="flex items-center gap-1">
                  <BarChart3 className="w-3 h-3" />
                  <span>{chartCount} grafico{chartCount !== 1 ? 's' : ''}</span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Results area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {blocks.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-full bg-blue-50 flex items-center justify-center mb-4">
              <Terminal className="w-8 h-8 text-blue-300" />
            </div>
            <h3 className="text-sm font-medium text-gray-600 mb-2">
              Sin resultados aun
            </h3>
            <p className="text-xs text-gray-400 max-w-xs">
              Los resultados de tus consultas apareceran aqui.
              Podras ver el codigo generado, tablas y graficos.
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
