'use client';

import { useState, useCallback, memo } from 'react';
import { ChevronDown, ChevronRight, Copy, Check } from 'lucide-react';

interface CodeBlockProps {
  code: string;
  title?: string;
  isVisible?: boolean;
  onToggle?: () => void;
}

export const CodeBlock = memo(function CodeBlock({
  code,
  title = 'Codigo',
  isVisible = false,
  onToggle
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Copy failed:', err);
    }
  }, [code]);

  const lineCount = code.split('\n').length;

  return (
    <div className="rounded border border-gray-200 bg-white overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 bg-gray-50 cursor-pointer hover:bg-gray-100"
        onClick={onToggle}
      >
        <div className="flex items-center gap-2 text-[12px]">
          {isVisible ? (
            <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-gray-400" />
          )}
          <span className="text-gray-600 font-medium">{title}</span>
          <span className="text-gray-400">({lineCount} lineas)</span>
        </div>

          <button
            onClick={handleCopy}
          className="p-1 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600"
            title="Copiar"
          >
          {copied ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
          </button>
      </div>

      {/* Code - fondo claro */}
      {isVisible && (
        <div className="border-t border-gray-200 bg-gray-50 overflow-x-auto max-h-[250px]">
          <pre className="p-3 text-[11px] leading-relaxed">
            <code className="font-mono text-gray-700 whitespace-pre">{code}</code>
          </pre>
        </div>
      )}
    </div>
  );
});
