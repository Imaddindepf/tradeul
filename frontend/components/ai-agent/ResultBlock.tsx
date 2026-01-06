'use client';

import { memo } from 'react';
import { Loader2, AlertCircle, CheckCircle, Wrench, Clock } from 'lucide-react';
import { CodeBlock } from './CodeBlock';
import { DataTable } from './DataTable';
import { Chart } from './Chart';
import type { ResultBlockData, OutputBlock } from './types';

interface ResultBlockProps {
  block: ResultBlockData;
  onToggleCode: () => void;
}

export const ResultBlock = memo(function ResultBlock({
  block,
  onToggleCode
}: ResultBlockProps) {
  const { status, code, codeVisible, result } = block;

  // Renderizar output segun su tipo
  const renderOutput = (output: OutputBlock, index: number) => {
    switch (output.type) {
      case 'table':
        return (
          <DataTable
            key={index}
            columns={output.columns || []}
            rows={output.rows || []}
            title={output.title}
            total={output.total}
          />
        );

      case 'chart':
        if (output.plotly_config) {
          return (
            <Chart
              key={index}
              title={output.title}
              plotlyConfig={output.plotly_config}
            />
          );
        }
        return null;

      case 'stats':
        if (output.stats) {
          return (
            <div key={index} className="rounded-lg border border-gray-200 bg-white p-4">
              <h3 className="text-sm font-medium text-gray-800 mb-3">{output.title}</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                {Object.entries(output.stats).map(([col, stats]) => (
                  <div key={col} className="bg-gray-50 rounded p-3">
                    <div className="text-xs text-gray-500 mb-1 uppercase">{col}</div>
                    <div className="grid grid-cols-2 gap-1 text-xs">
                      <span className="text-gray-400">Min:</span>
                      <span className="text-gray-700 font-mono">{stats.min}</span>
                      <span className="text-gray-400">Max:</span>
                      <span className="text-gray-700 font-mono">{stats.max}</span>
                      <span className="text-gray-400">Mean:</span>
                      <span className="text-gray-700 font-mono">{stats.mean}</span>
                      <span className="text-gray-400">Median:</span>
                      <span className="text-gray-700 font-mono">{stats.median}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        }
        return null;

      case 'error':
        return (
          <div key={index} className="rounded-lg border border-red-200 bg-red-50 p-4">
            <div className="flex items-center gap-2 text-red-600">
              <AlertCircle className="w-4 h-4" />
              <span className="text-sm font-medium">Error</span>
            </div>
            <p className="mt-2 text-sm text-red-500 font-mono">{output.title}</p>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="space-y-3">
      {/* Status indicator */}
      <div className="flex items-center gap-2">
        {status === 'running' && (
          <>
            <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
            <span className="text-sm text-blue-600">Ejecutando...</span>
          </>
        )}
        {status === 'fixing' && (
          <>
            <Wrench className="w-4 h-4 text-amber-500 animate-pulse" />
            <span className="text-sm text-amber-600">Auto-corrigiendo codigo...</span>
          </>
        )}
        {status === 'success' && (
          <>
            <CheckCircle className="w-4 h-4 text-green-500" />
            <span className="text-sm text-green-600">Completado</span>
            {result && (
              <span className="text-xs text-gray-400 flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {result.execution_time_ms.toFixed(0)}ms
              </span>
            )}
          </>
        )}
        {status === 'error' && (
          <>
            <AlertCircle className="w-4 h-4 text-red-500" />
            <span className="text-sm text-red-600">Error</span>
          </>
        )}
      </div>

      {/* Code block */}
      <CodeBlock
        code={code}
        title="Codigo DSL"
        isVisible={codeVisible}
        onToggle={onToggleCode}
      />

      {/* Outputs */}
      {result?.outputs && result.outputs.length > 0 && (
        <div className="space-y-3">
          {result.outputs.map((output, index) => renderOutput(output, index))}
        </div>
      )}

      {/* Error message */}
      {result?.error && status === 'error' && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <div className="flex items-center gap-2 text-red-600 mb-2">
            <AlertCircle className="w-4 h-4" />
            <span className="text-sm font-medium">Error de ejecucion</span>
          </div>
          <pre className="text-xs text-red-500 font-mono whitespace-pre-wrap overflow-x-auto">
            {result.error}
          </pre>
        </div>
      )}
    </div>
  );
});
