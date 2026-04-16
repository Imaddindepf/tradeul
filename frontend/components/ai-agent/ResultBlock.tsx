'use client';

import { memo, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowDownRight, ArrowUpRight, BarChart3, Minus } from 'lucide-react';
import dynamic from 'next/dynamic';
import { CodeBlock } from './CodeBlock';
import { StructuredResponseRenderer, type StructuredResponse } from './StructuredResponseRenderer';
import type { ResultBlockData, OutputItem } from './types';

const LazyAutoChart = dynamic(() => import('./AutoChart').then(m => m.AutoBarChart), {
  ssr: false,
  loading: () => <div className="h-[240px] bg-surface-hover rounded-xl animate-pulse" />,
});

interface ResultBlockProps {
  block: ResultBlockData;
  onToggleCode: () => void;
}

// ── Inline markdown formatter ────────────────────────────────────
function fmtInline(text: string): string {
  return text
    .replace(/\s*\\\\\s*$/, '')                                                   // strip trailing \\ line breaks
    .replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold text-foreground">$1</strong>')
    .replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em class="text-foreground">$1</em>')
    .replace(/`([^`]+)`/g, '<code class="px-0.5 py-px rounded bg-surface-inset text-primary text-[10px] font-mono">$1</code>')
    .replace(/\$(\d[\d,.]*)/g, '<span class="font-semibold tabular-nums text-foreground">$$$1</span>');
}

function stripBold(text: string): string {
  return text.replace(/\*\*/g, '');
}

// ── Markdown parser ──────────────────────────────────────────────
interface ParsedElement {
  type: 'h1' | 'h2' | 'h3' | 'text' | 'bullet' | 'numbered' | 'table' | 'divider' | 'code';
  content: string;
  rows?: string[][];
  level?: number;
}

function parseMarkdown(content: string): ParsedElement[] {
  const lines = content.split('\n');
  const elements: ParsedElement[] = [];
  let currentTable: string[][] = [];
  let inTable = false;
  let inCode = false;
  let codeLines: string[] = [];

  for (const line of lines) {
    const trimmed = line.trim();

    if (trimmed.startsWith('```')) {
      if (inCode) {
        const codeContent = codeLines.join('\n').trim();
        if (codeContent) elements.push({ type: 'code', content: codeContent });
        codeLines = [];
        inCode = false;
      } else {
        inCode = true;
      }
      continue;
    }
    if (inCode) { codeLines.push(line); continue; }

    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      if (trimmed.includes('---')) continue;
      const cells = trimmed.split('|').filter(c => c.trim()).map(c => c.trim());
      if (cells.length > 0) { currentTable.push(cells); inTable = true; }
      continue;
    }
    if (inTable && currentTable.length > 0) {
      elements.push({ type: 'table', content: '', rows: [...currentTable] });
      currentTable = [];
      inTable = false;
    }

    if (!trimmed) continue;
    if (trimmed === '---' || trimmed === '***') { elements.push({ type: 'divider', content: '' }); continue; }
    if (trimmed.startsWith('# ') && !trimmed.startsWith('##')) { elements.push({ type: 'h1', content: trimmed.slice(2) }); continue; }
    if (trimmed.startsWith('## ') && !trimmed.startsWith('###')) { elements.push({ type: 'h2', content: trimmed.slice(3) }); continue; }
    if (/^#{3,4}\s/.test(trimmed)) { elements.push({ type: 'h3', content: trimmed.replace(/^#{3,4}\s*/, '') }); continue; }
    if (trimmed.startsWith('**') && trimmed.endsWith('**') && !trimmed.slice(2, -2).includes('**')) {
      elements.push({ type: 'h3', content: trimmed.slice(2, -2) });
      continue;
    }
    if (/^\d+\.\s/.test(trimmed)) {
      const match = trimmed.match(/^(\d+)\.\s*(.*)/);
      if (match) { elements.push({ type: 'numbered', content: match[2], level: parseInt(match[1]) }); continue; }
    }
    if (/^[\*\-]\s/.test(trimmed)) {
      elements.push({ type: 'bullet', content: trimmed.replace(/^[\*\-]\s*/, '') });
      continue;
    }
    elements.push({ type: 'text', content: trimmed });
  }
  if (currentTable.length > 0) elements.push({ type: 'table', content: '', rows: currentTable });
  return elements;
}

// ── Interactive sortable table ───────────────────────────────────
const INLINE_TABLE_PREVIEW = 10;
const INLINE_TABLE_MAX = 500;

function InteractiveTable({ headers, rows }: { headers: string[]; rows: string[][] }) {
  const [sortCol, setSortCol] = useState<number | null>(null);
  const [sortAsc, setSortAsc] = useState(true);
  const [expanded, setExpanded] = useState(false);

  const cleanHeaders = useMemo(() => headers.map(stripBold), [headers]);
  const cleanRows = useMemo(() => rows.map(r => r.map(stripBold)), [rows]);

  const sortedRows = useMemo(() => {
    if (sortCol === null) return cleanRows;
    return [...cleanRows].sort((a, b) => {
      const av = a[sortCol] || '';
      const bv = b[sortCol] || '';
      const an = parseFloat(av.replace(/[,$%]/g, ''));
      const bn = parseFloat(bv.replace(/[,$%]/g, ''));
      if (!isNaN(an) && !isNaN(bn)) return sortAsc ? an - bn : bn - an;
      return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
    });
  }, [cleanRows, sortCol, sortAsc]);

  const handleSort = (colIdx: number) => {
    if (sortCol === colIdx) setSortAsc(!sortAsc);
    else { setSortCol(colIdx); setSortAsc(true); }
  };

  const isNumeric = useMemo(() => {
    return cleanHeaders.map((_, colIdx) => {
      const vals = cleanRows.map(r => r[colIdx] || '').filter(Boolean);
      const numCount = vals.filter(v => !isNaN(parseFloat(v.replace(/[,$%]/g, '')))).length;
      return numCount > vals.length * 0.5;
    });
  }, [cleanHeaders, cleanRows]);

  const getCellColor = (value: string): string => {
    const num = parseFloat(value.replace(/[,$%]/g, ''));
    if (isNaN(num)) return 'text-foreground';
    if (value.includes('%')) {
      if (num > 0) return 'text-emerald-600 font-medium';
      if (num < 0) return 'text-red-500 font-medium';
    }
    return 'text-foreground';
  };

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface">
      <table className="w-full text-[10px]">
        <thead>
          <tr className="bg-surface-hover/80">
            {cleanHeaders.map((h, i) => (
              <th
                key={i}
                onClick={() => handleSort(i)}
                className={'px-2 py-1.5 font-semibold text-foreground/80 cursor-pointer hover:bg-surface-hover transition-colors select-none whitespace-nowrap ' + (isNumeric[i] ? 'text-right' : 'text-left')}
              >
                <span className="inline-flex items-center gap-0.5">
                  {h}
                  {sortCol === i && (
                    <span className="text-[8px] text-primary">{sortAsc ? '▲' : '▼'}</span>
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {(expanded ? sortedRows.slice(0, INLINE_TABLE_MAX) : sortedRows.slice(0, INLINE_TABLE_PREVIEW)).map((row, rowIdx) => (
            <tr key={rowIdx} className="hover:bg-primary/10 transition-colors">
              {row.map((cell, cellIdx) => (
                <td
                  key={cellIdx}
                  className={'px-2 py-1 tabular-nums ' +
                    (isNumeric[cellIdx] ? 'text-right font-mono text-[10px] ' : 'text-left ') +
                    (cellIdx === 0 ? 'font-medium text-foreground ' : getCellColor(cell))}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {sortedRows.length > INLINE_TABLE_PREVIEW && !expanded && (
        <button
          onClick={() => setExpanded(true)}
          className="w-full py-1.5 text-[10px] text-muted-fg hover:text-foreground bg-surface-hover border-t border-border transition-colors"
        >
          Mostrar más ({sortedRows.length - INLINE_TABLE_PREVIEW} filas más)
        </button>
      )}
    </div>
  );
}

// ── V4ResponseRenderer: markdown completo con tablas interactivas ─
const V4ResponseRenderer = memo(function V4ResponseRenderer({ content }: { content: string }) {
  const elements = useMemo(() => parseMarkdown(content), [content]);
  const [showChart, setShowChart] = useState<number | null>(null);

  let tableCounter = 0;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
      className="space-y-2"
    >
      {elements.map((el, idx) => {
        switch (el.type) {
          case 'h1':
            return (
              <h2 key={idx} className="text-[13px] font-bold text-foreground mt-3 first:mt-0 pb-1 border-b border-border">
                {el.content}
              </h2>
            );
          case 'h2':
            return (
              <h3 key={idx} className="text-[12px] font-bold text-foreground mt-3 first:mt-0 flex items-center gap-1.5">
                <span className="w-0.5 h-3 rounded-full bg-primary inline-block" />
                {el.content}
              </h3>
            );
          case 'h3':
            return (
              <h4 key={idx} className="text-[11px] font-semibold text-foreground mt-2 first:mt-0">
                {el.content}
              </h4>
            );
          case 'divider':
            return <hr key={idx} className="border-border my-2" />;
          case 'bullet':
            return (
              <div key={idx} className="flex gap-1.5 text-[11px] text-foreground/80 leading-relaxed pl-0.5">
                <span className="text-primary mt-0.5 select-none flex-shrink-0">&bull;</span>
                <span dangerouslySetInnerHTML={{ __html: fmtInline(el.content) }} />
              </div>
            );
          case 'numbered':
            return (
              <div key={idx} className="flex gap-1.5 text-[11px] text-foreground/80 leading-relaxed pl-0.5">
                <span className="text-primary font-semibold text-[10px] mt-0.5 select-none flex-shrink-0 min-w-[14px]">
                  {el.level}.
                </span>
                <span dangerouslySetInnerHTML={{ __html: fmtInline(el.content) }} />
              </div>
            );
          case 'text':
            return (
              <p key={idx} className="text-[11px] text-foreground/80 leading-relaxed"
                dangerouslySetInnerHTML={{ __html: fmtInline(el.content) }}
              />
            );
          case 'code':
            return (
              <pre key={idx} className="rounded-lg bg-slate-900 text-slate-200 p-3 text-[10px] font-mono overflow-x-auto leading-relaxed">
                {el.content}
              </pre>
            );
          case 'table': {
            if (!el.rows || el.rows.length < 2) return null;
            const tHeaders = el.rows[0].map(stripBold);
            const tRows = el.rows.slice(1).map(r => r.map(stripBold));
            const tIdx = tableCounter++;
            return (
              <div key={idx} className="space-y-1.5">
                <InteractiveTable headers={tHeaders} rows={tRows} />
                {tRows.length >= 2 && (
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => setShowChart(showChart === tIdx ? null : tIdx)}
                      className="inline-flex items-center gap-1 px-2 py-1 text-[9px] font-medium text-primary bg-primary/10 hover:bg-primary/15 rounded transition-colors"
                    >
                      <BarChart3 className="w-3 h-3" />
                      {showChart === tIdx ? 'Ocultar gráfico' : 'Visualizar'}
                    </button>
                  </div>
                )}
                <AnimatePresence>
                  {showChart === tIdx && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.25 }}
                    >
                      <LazyAutoChart headers={tHeaders} rows={tRows} />
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          }
          default:
            return null;
        }
      })}
    </motion.div>
  );
});

// ── renderOutput ─────────────────────────────────────────────────
function renderOutput(output: OutputItem, idx: number) {
  const type = output.type || 'text';

  if (type === 'research' || type === 'text' || type === 'markdown') {
    const sr = output.structured_response;
    if (sr && typeof sr === 'object' && 'sections' in sr) {
      return <StructuredResponseRenderer key={idx} data={sr as unknown as StructuredResponse} />;
    }
    const content = (output.content as string) || '';
    return <V4ResponseRenderer key={idx} content={content} />;
  }

  if (type === 'table') {
    const rows = (output.data as Record<string, unknown>[] | null) || [];
    if (!rows.length) return null;
    const headers = Object.keys(rows[0]);
    const tableRows = rows.map(r => headers.map(h => String(r[h] ?? '')));
    return (
      <div key={idx}>
        {output.title && (
          <div className="text-[11px] font-semibold text-muted-fg uppercase tracking-wide mb-1.5">
            {output.title}
          </div>
        )}
        <InteractiveTable headers={headers} rows={tableRows} />
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

  // code_exec sandbox outputs
  if (type === 'code_exec') {
    const ce = output as any;
    const ceCharts: Record<string, string> = ce.charts || {};
    const ceOutputs: Record<string, unknown> = ce.outputs || {};
    const ceCode: string = ce.code || '';
    const cePrints: string[] = ce.prints || [];
    const chartEntries = Object.entries(ceCharts);
    const outputEntries = Object.entries(ceOutputs);
    if (!chartEntries.length && !outputEntries.length) return null;
    return (
      <div key={idx} className="space-y-2">
        {chartEntries.map(([label, b64]) => (
          <div key={label}>
            <div className="text-[10px] text-muted-fg mb-1">{label}</div>
            <img src={`data:image/png;base64,${b64}`} alt={label} className="rounded-lg max-w-full" />
          </div>
        ))}
        {outputEntries.map(([label, val]) => {
          if (Array.isArray(val) && val.length && typeof val[0] === 'object') {
            const headers = Object.keys(val[0] as object);
            const rows = (val as Record<string, unknown>[]).map(r => headers.map(h => String(r[h] ?? '')));
            return (
              <div key={label}>
                <div className="text-[10px] text-muted-fg mb-1">{label}</div>
                <InteractiveTable headers={headers} rows={rows} />
              </div>
            );
          }
          if (typeof val === 'object' && val !== null) {
            const entries = Object.entries(val as object);
            return (
              <div key={label} className="grid grid-cols-2 gap-1.5">
                {entries.map(([k, v]) => (
                  <div key={k} className="rounded bg-surface-hover px-2 py-1.5">
                    <div className="text-[9px] text-muted-fg uppercase tracking-wide">{k}</div>
                    <div className="text-[12px] font-semibold text-foreground tabular-nums">{String(v)}</div>
                  </div>
                ))}
              </div>
            );
          }
          return (
            <div key={label} className="rounded bg-surface-hover px-2 py-1.5">
              <div className="text-[9px] text-muted-fg uppercase tracking-wide">{label}</div>
              <div className="text-[12px] font-semibold text-foreground tabular-nums">{String(val)}</div>
            </div>
          );
        })}
        {cePrints.length > 0 && (
          <pre className="rounded bg-slate-900 text-slate-200 p-2 text-[10px] font-mono overflow-x-auto max-h-40">
            {cePrints.join('\n')}
          </pre>
        )}
        {ceCode && (
          <CodeBlock code={ceCode} title="Código generado" isVisible={false} onToggle={() => {}} />
        )}
      </div>
    );
  }

  // Fallback
  const raw = output.content ?? JSON.stringify(output.data ?? output, null, 2);
  return (
    <div key={idx} className="text-[13px] text-foreground/80 whitespace-pre-wrap font-mono">
      {String(raw)}
    </div>
  );
}

// ── ResultBlock ──────────────────────────────────────────────────
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
        {String(errorText)}
      </div>
    );
  }

  const outputs = result?.outputs || [];

  return (
    <div className="space-y-3">
      {code && (
        <CodeBlock
          code={code}
          title="Código generado"
          isVisible={codeVisible}
          onToggle={onToggleCode}
        />
      )}
      {outputs.map((output, idx) => (
        <div key={idx}>
          {output.title && output.type !== 'research' && output.type !== 'text' && output.type !== 'markdown' && (
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
