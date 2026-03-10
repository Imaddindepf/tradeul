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
    <div className="rounded border border-border bg-surface overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 bg-surface-hover cursor-pointer hover:bg-surface-inset"
        onClick={onToggle}
      >
        <div className="flex items-center gap-2 text-[12px]">
          {isVisible ? (
            <ChevronDown className="w-3.5 h-3.5 text-muted-fg" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-muted-fg" />
          )}
          <span className="text-foreground/80 font-medium">{title}</span>
          <span className="text-muted-fg">({lineCount} lineas)</span>
        </div>

          <button
            onClick={handleCopy}
          className="p-1 rounded hover:bg-surface-inset text-muted-fg hover:text-foreground/80"
            title="Copiar"
          >
          {copied ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
          </button>
      </div>

      {/* Code - fondo claro */}
      {isVisible && (
        <div className="border-t border-border bg-surface-hover overflow-x-auto max-h-[250px]">
          <pre className="p-3 text-[11px] leading-relaxed">
            <code className="font-mono text-foreground whitespace-pre">{code}</code>
          </pre>
        </div>
      )}
    </div>
  );
});
