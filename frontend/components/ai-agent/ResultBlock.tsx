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

export const ResultBlock = memo(function ResultBlock({ block, onToggleCode }: ResultBlockProps) {
  const { status, code, codeVisible, result } = block;

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
          return <Chart key={index} title={output.title} plotlyConfig={output.plotly_config} />;
        }
        if ((output as any).image_base64) {
          return (
            <div key={index} className="rounded border border-gray-200 bg-white overflow-hidden">
              {output.title && (
                <div className="px-3 py-2 bg-gray-50 border-b text-[12px] font-medium text-gray-600">
                  {output.title}
                </div>
              )}
              <img 
                src={`data:image/png;base64,${(output as any).image_base64}`}
                alt={output.title || 'Chart'}
                className="max-w-full h-auto"
              />
            </div>
          );
        }
        return null;

      case 'stats':
        if ((output as any).content) {
          return (
            <div key={index} className="rounded border border-gray-200 bg-gray-50 p-3">
              <pre className="text-[11px] text-gray-700 font-mono whitespace-pre-wrap overflow-x-auto">
                {(output as any).content}
              </pre>
            </div>
          );
        }
        if (output.stats && Object.keys(output.stats).length > 0) {
          return (
            <div key={index} className="rounded border border-gray-200 bg-white p-3">
              <h3 className="text-[12px] font-medium text-gray-700 mb-2">{output.title}</h3>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(output.stats).map(([col, stats]) => (
                  <div key={col} className="bg-gray-50 rounded p-2">
                    <div className="text-[10px] text-gray-500 uppercase">{col}</div>
                    <div className="grid grid-cols-2 gap-1 text-[11px] mt-1">
                      <span className="text-gray-400">Min:</span>
                      <span className="font-mono">{stats.min}</span>
                      <span className="text-gray-400">Max:</span>
                      <span className="font-mono">{stats.max}</span>
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
          <div key={index} className="rounded border border-red-200 bg-red-50 p-3">
            <div className="flex items-center gap-2 text-red-600 text-[12px]">
              <AlertCircle className="w-4 h-4" />
              <span className="font-medium">Error</span>
            </div>
            <p className="mt-1 text-[11px] text-red-500 font-mono">{output.title}</p>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="space-y-3">
      {/* Status */}
      <div className="flex items-center gap-2">
        {status === 'running' && (
          <>
            <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
            <span className="text-[12px] text-blue-600">Ejecutando...</span>
          </>
        )}
        {status === 'fixing' && (
          <>
            <Wrench className="w-4 h-4 text-amber-500 animate-pulse" />
            <span className="text-[12px] text-amber-600">Corrigiendo...</span>
          </>
        )}
        {status === 'success' && (
          <>
            <CheckCircle className="w-4 h-4 text-green-500" />
            <span className="text-[12px] text-green-600">Completado</span>
            {result && (
              <span className="text-[11px] text-gray-400 flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {result.execution_time_ms}ms
              </span>
            )}
          </>
        )}
        {status === 'error' && (
          <>
            <AlertCircle className="w-4 h-4 text-red-500" />
            <span className="text-[12px] text-red-600">Error</span>
          </>
        )}
      </div>

      {/* Code */}
      <CodeBlock code={code} title="Codigo" isVisible={codeVisible} onToggle={onToggleCode} />

      {/* Outputs */}
      {result?.outputs && result.outputs.length > 0 && (
        <div className="space-y-3">
          {result.outputs.map((output, index) => renderOutput(output, index))}
        </div>
      )}

      {/* Error */}
      {result?.error && status === 'error' && (
        <div className="rounded border border-red-200 bg-red-50 p-3">
          <div className="flex items-center gap-2 text-red-600 mb-2 text-[12px]">
            <AlertCircle className="w-4 h-4" />
            <span className="font-medium">Error de ejecucion</span>
          </div>
          <pre className="text-[11px] text-red-500 font-mono whitespace-pre-wrap">{result.error}</pre>
        </div>
      )}
    </div>
  );
});
