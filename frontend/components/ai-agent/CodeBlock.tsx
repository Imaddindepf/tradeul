'use client';

import { useState, useCallback, memo } from 'react';
import { ChevronDown, ChevronRight, Copy, Check, Download } from 'lucide-react';

interface CodeBlockProps {
  code: string;
  title?: string;
  isVisible?: boolean;
  onToggle?: () => void;
  onCopy?: () => void;
}

export const CodeBlock = memo(function CodeBlock({
  code,
  title = 'Codigo DSL',
  isVisible = false,
  onToggle,
  onCopy
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      onCopy?.();
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  }, [code, onCopy]);

  const handleDownload = useCallback(() => {
    const blob = new Blob([code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'query.py';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [code]);

  const lineCount = code.split('\n').length;

  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      {/* Header - siempre visible */}
      <div
        className="flex items-center justify-between px-3 py-2 bg-gray-50 cursor-pointer hover:bg-gray-100 transition-colors"
        onClick={onToggle}
      >
        <div className="flex items-center gap-2 text-sm">
          {isVisible ? (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-400" />
          )}
          <span className="text-gray-600 font-medium">{title}</span>
          <span className="text-gray-400 text-xs">({lineCount} lineas)</span>
        </div>

        <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
          <button
            onClick={handleCopy}
            className="p-1.5 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600 transition-colors"
            title="Copiar"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
          <button
            onClick={handleDownload}
            className="p-1.5 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600 transition-colors"
            title="Descargar"
          >
            <Download className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Code - solo visible si expandido */}
      {isVisible && (
        <div className="border-t border-gray-100 bg-gray-50 overflow-x-auto">
          <pre className="p-3 text-sm leading-relaxed">
            <code className="font-mono text-gray-700 whitespace-pre">
              {code}
            </code>
          </pre>
        </div>
      )}
    </div>
  );
});
