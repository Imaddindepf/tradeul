'use client';

import { memo } from 'react';
import { CodeBlock } from './CodeBlock';
import type { ResultBlockData, OutputItem } from './types';

interface ResultBlockProps {
  block: ResultBlockData;
  onToggleCode: () => void;
}

function renderOutput(output: OutputItem, idx: number) {
  const type = output.type || 'text';

  if (type === 'research' || type === 'text' || type === 'markdown') {
    const content = (output.content as string) || '';
    return (
      <div key={idx} className="prose prose-sm max-w-none text-foreground/90">
        {content.split('\n').map((line, i) => (
          <p key={i} className="mb-1 last:mb-0 text-[13px] leading-relaxed whitespace-pre-wrap">
            {line}
          </p>
        ))}
      </div>
    );
  }

  if (type === 'table') {
    const rows = (output.data as Record<string, unknown>[] | null) || [];
    if (!rows.length) return null;
    const headers = Object.keys(rows[0]);
    return (
      <div key={idx} className="overflow-x-auto rounded border border-border">
        {output.title && (
          <div className="px-3 py-1.5 text-[11px] font-semibold text-muted-fg border-b border-border bg-surface-hover">
            {output.title}
          </div>
        )}
        <table className="w-full text-[12px]">
          <thead>
            <tr className="bg-surface-hover">
              {headers.map((h) => (
                <th key={h} className="px-3 py-1.5 text-left font-medium text-muted-fg border-b border-border">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri} className="border-b border-border last:border-0 hover:bg-surface-hover/50">
                {headers.map((h) => (
                  <td key={h} className="px-3 py-1.5 text-foreground/80">
                    {String(row[h] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (type === 'code' || type === 'python') {
    return (
      <CodeBlock
        key={idx}
        code={(output.content as string) || ''}
        title={output.title || 'Code'}
        isVisible
      />
    );
  }

  // Fallback: render as text
  const raw = output.content ?? JSON.stringify(output.data ?? output, null, 2);
  return (
    <div key={idx} className="text-[13px] text-foreground/80 whitespace-pre-wrap font-mono">
      {String(raw)}
    </div>
  );
}

export const ResultBlock = memo(function ResultBlock({ block, onToggleCode }: ResultBlockProps) {
  const { result, code, codeVisible, status } = block;

  if (status === 'running' || status === 'fixing') {
    return (
      <div className="flex items-center gap-2 text-[13px] text-muted-fg py-2">
        <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
        <span>Procesando...</span>
      </div>
    );
  }

  if (status === 'error' || !result?.success) {
    const errorText = result?.outputs?.[0]?.content || 'Error al procesar la solicitud.';
    return (
      <div className="text-[13px] text-red-500 rounded bg-red-50 border border-red-200 px-3 py-2">
        {errorText}
      </div>
    );
  }

  const outputs = result?.outputs || [];

  return (
    <div className="space-y-3">
      {/* Code section */}
      {code && (
        <CodeBlock
          code={code}
          title="Código generado"
          isVisible={codeVisible}
          onToggle={onToggleCode}
        />
      )}

      {/* Output sections */}
      {outputs.map((output, idx) => (
        <div key={idx}>
          {output.title && output.type !== 'research' && (
            <div className="text-[11px] font-semibold text-muted-fg uppercase tracking-wide mb-1.5">
              {output.title}
            </div>
          )}
          {renderOutput(output, idx)}
        </div>
      ))}
    </div>
  );
});
