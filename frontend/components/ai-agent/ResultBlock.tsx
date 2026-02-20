'use client';

import React, { memo, useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, Copy, Check,
  ArrowUpRight, ArrowDownRight,
  Minus, BarChart3,
} from 'lucide-react';
import dynamic from 'next/dynamic';
import { CodeBlock } from './CodeBlock';
import { DataTable } from './DataTable';
import { SectorPerformanceTable } from './SectorPerformanceTable';
import { Chart } from './Chart';
import { TradingChart } from '@/components/chart/TradingChart';
import type { ResultBlockData, OutputBlock } from './types';

// Dynamic import: single wrapper component (not individual sub-components)
const LazyAutoChart = dynamic(() => import('./AutoChart').then(m => m.AutoBarChart), {
  ssr: false,
  loading: () => <div className="h-[240px] bg-slate-50 rounded-xl animate-pulse" />,
});

interface ResultBlockProps {
  block: ResultBlockData;
  onToggleCode: () => void;
}

/* ================================================================
   Utility: Copy to clipboard with visual feedback
   ================================================================ */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => () => { clearTimeout(timerRef.current); }, []);
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setCopied(false), 2000);
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className="p-1.5 rounded-md hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-all"
      title="Copy to clipboard"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

/* ================================================================
   Metric Card: Auto-detected KPIs from response content
   ================================================================ */
interface MetricData {
  label: string;
  value: string;
  numericValue?: number;
  trend?: 'up' | 'down' | 'neutral';
}

function MetricCard({ metric }: { metric: MetricData }) {
  const TrendIcon = metric.trend === 'up' ? ArrowUpRight
    : metric.trend === 'down' ? ArrowDownRight : Minus;
  const trendColor = metric.trend === 'up' ? 'text-emerald-500'
    : metric.trend === 'down' ? 'text-red-500' : 'text-slate-400';
  const trendBg = metric.trend === 'up' ? 'bg-emerald-50'
    : metric.trend === 'down' ? 'bg-red-50' : 'bg-slate-50';

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className={'rounded-lg border border-slate-200/80 px-2.5 py-1.5 flex flex-col gap-0 min-w-0 ' + trendBg}
    >
      <span className="text-[9px] font-medium text-slate-500 uppercase tracking-wider truncate">
        {metric.label}
      </span>
      <div className="flex items-center gap-1">
        <span className="text-[13px] font-bold text-slate-800 tabular-nums truncate">
          {metric.value}
        </span>
        <TrendIcon className={'w-3 h-3 flex-shrink-0 ' + trendColor} />
      </div>
    </motion.div>
  );
}

/* ================================================================
   Utility: Strip markdown bold markers from cell text
   ================================================================ */
function stripBold(text: string): string {
  return text.replace(/\*\*/g, '');
}

/* ================================================================
   Interactive Table: Sortable columns, numeric detection, hover
   ================================================================ */
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
    if (isNaN(num)) return 'text-slate-700';
    if (value.includes('%')) {
      if (num > 0) return 'text-emerald-600 font-medium';
      if (num < 0) return 'text-red-500 font-medium';
    }
    return 'text-slate-700';
  };

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200/80 bg-white">
      <table className="w-full text-[10px]">
        <thead>
          <tr className="bg-slate-50/80">
            {cleanHeaders.map((h, i) => (
              <th
                key={i}
                onClick={() => handleSort(i)}
                className={'px-2 py-1.5 font-semibold text-slate-600 cursor-pointer hover:bg-slate-100 transition-colors select-none whitespace-nowrap ' + (isNumeric[i] ? 'text-right' : 'text-left')}
              >
                <span className="inline-flex items-center gap-0.5">
                  {h}
                  {sortCol === i && (
                    <span className="text-[8px] text-indigo-500">
                      {sortAsc ? '\u25B2' : '\u25BC'}
                    </span>
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {(expanded ? sortedRows.slice(0, INLINE_TABLE_MAX) : sortedRows.slice(0, INLINE_TABLE_PREVIEW)).map((row, rowIdx) => (
            <tr key={rowIdx} className="hover:bg-indigo-50/30 transition-colors">
              {row.map((cell, cellIdx) => (
                <td
                  key={cellIdx}
                  className={'px-2 py-1 tabular-nums ' +
                    (isNumeric[cellIdx] ? 'text-right font-mono text-[10px] ' : 'text-left ') +
                    (cellIdx === 0 ? 'font-medium text-slate-800 ' : getCellColor(cell))}
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
          className="w-full py-1.5 text-[10px] text-slate-500 hover:text-slate-700 bg-slate-50 border-t border-slate-200/80 transition-colors"
        >
          Show more ({sortedRows.length - INLINE_TABLE_PREVIEW} more rows)
        </button>
      )}
    </div>
  );
}

/* AutoBarChart is dynamically imported as LazyAutoChart above */

/* ================================================================
   V4 Markdown Parser and Types
   ================================================================ */
interface ParsedElement {
  type: 'h1' | 'h2' | 'h3' | 'text' | 'bullet' | 'numbered' | 'table' | 'divider' | 'code';
  content: string;
  rows?: string[][];
  level?: number;
}

function extractMetrics(content: string): MetricData[] {
  const metrics: MetricData[] = [];
  const rules: { regex: RegExp; label: string; prefix?: string; trendType?: string }[] = [
    { regex: /(?:price|precio)[:\s]*\*?\*?\$?([\d,.]+)/i, label: 'Price', prefix: '$' },
    { regex: /(?:volume|volumen)[:\s]*\*?\*?([\d,.]+[MKB]?)/i, label: 'Volume' },
    { regex: /RSI[^:]*[:\s=]*\*?\*?([\d,.]+)/i, label: 'RSI (14)', trendType: 'rsi' },
    { regex: /(?:change|cambio)[:\s]*\*?\*?([+-]?[\d,.]+%?)/i, label: 'Change', trendType: 'change' },
    { regex: /VWAP[:\s]*\*?\*?\$?([\d,.]+)/i, label: 'VWAP', prefix: '$' },
    { regex: /(?:market\s*cap)[:\s]*\*?\*?\$?([\d,.]+[TBMK]?)/i, label: 'Mkt Cap', prefix: '$' },
    { regex: /ATR[^:]*[:\s=]*\*?\*?([\d,.]+)/i, label: 'ATR' },
    { regex: /52.week\s*high[:\s]*\*?\*?\$?([\d,.]+)/i, label: '52W High', prefix: '$' },
    { regex: /52.week\s*low[:\s]*\*?\*?\$?([\d,.]+)/i, label: '52W Low', prefix: '$' },
    { regex: /(?:avg|average)\s*(?:gain|change)[:\s]*\*?\*?([+-]?[\d,.]+%?)/i, label: 'Avg Gain', trendType: 'change' },
  ];

  for (const { regex, label, prefix, trendType } of rules) {
    const match = content.match(regex);
    if (match) {
      const raw = match[1];
      const num = parseFloat(raw.replace(/[,$%TBMK]/g, ''));
      let trend: MetricData['trend'] = 'neutral';
      if (trendType === 'change') trend = num > 0 ? 'up' : num < 0 ? 'down' : 'neutral';
      if (trendType === 'rsi') trend = num > 50 ? 'up' : num < 50 ? 'down' : 'neutral';
      metrics.push({ label, value: (prefix || '') + raw, numericValue: num, trend });
    }
  }
  return metrics;
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

    // Fenced code blocks
    if (trimmed.startsWith('```')) {
      if (inCode) {
        const codeContent = codeLines.join('\n').trim();
        if (codeContent) {
          elements.push({ type: 'code', content: codeContent });
        }
        codeLines = [];
        inCode = false;
      } else {
        inCode = true;
      }
      continue;
    }
    if (inCode) { codeLines.push(line); continue; }

    // Table rows
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

function fmtInline(text: string): string {
  return text
    .replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold text-slate-800">$1</strong>')
    .replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em class="text-slate-700">$1</em>')
    .replace(/`([^`]+)`/g, '<code class="px-0.5 py-px rounded bg-slate-100 text-indigo-600 text-[10px] font-mono">$1</code>')
    .replace(/\$(\d[\d,.]*)/g, '<span class="font-semibold tabular-nums text-slate-800">$$$1</span>');
}

/* ================================================================
   V4ResponseRenderer: Premium markdown + metrics + interactive charts
   ================================================================ */
const V4ResponseRenderer = memo(function V4ResponseRenderer({ content }: { content: string }) {
  const elements = useMemo(() => parseMarkdown(content), [content]);
  const [showChart, setShowChart] = useState<number | null>(null);

  const tables = useMemo(() => {
    return elements
      .map((el, idx) => ({ el, idx }))
      .filter(({ el }) => el.type === 'table' && el.rows && el.rows.length > 2);
  }, [elements]);

  let tableCounter = 0;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className="space-y-2"
    >
      {elements.map((el, idx) => {
        switch (el.type) {
          case 'h1':
            return (
              <h2 key={idx} className="text-[13px] font-bold text-slate-900 mt-3 first:mt-0 pb-1 border-b border-slate-200/60">
                {el.content}
              </h2>
            );
          case 'h2':
            return (
              <h3 key={idx} className="text-[12px] font-bold text-slate-800 mt-3 first:mt-0 flex items-center gap-1.5">
                <span className="w-0.5 h-3 rounded-full bg-indigo-500 inline-block" />
                {el.content}
              </h3>
            );
          case 'h3':
            return (
              <h4 key={idx} className="text-[11px] font-semibold text-slate-700 mt-2 first:mt-0">
                {el.content}
              </h4>
            );
          case 'divider':
            return <hr key={idx} className="border-slate-200/60 my-2" />;
          case 'bullet':
            return (
              <div key={idx} className="flex gap-1.5 text-[11px] text-slate-600 leading-relaxed pl-0.5">
                <span className="text-indigo-400 mt-0.5 select-none flex-shrink-0">&bull;</span>
                <span dangerouslySetInnerHTML={{ __html: fmtInline(el.content) }} />
              </div>
            );
          case 'numbered':
            return (
              <div key={idx} className="flex gap-1.5 text-[11px] text-slate-600 leading-relaxed pl-0.5">
                <span className="text-indigo-500 font-semibold text-[10px] mt-0.5 select-none flex-shrink-0 min-w-[14px]">
                  {el.level}.
                </span>
                <span dangerouslySetInnerHTML={{ __html: fmtInline(el.content) }} />
              </div>
            );
          case 'text':
            return (
              <p key={idx} className="text-[11px] text-slate-600 leading-relaxed"
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
                      className="inline-flex items-center gap-1 px-2 py-1 text-[9px] font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded transition-colors"
                    >
                      <BarChart3 className="w-3 h-3" />
                      {showChart === tIdx ? 'Hide Chart' : 'Visualize'}
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

/* ================================================================
   Main ResultBlock: Orchestrates V3 + V4 rendering
   ================================================================ */
export const ResultBlock = memo(function ResultBlock({ block, onToggleCode }: ResultBlockProps) {
  const { status, code, codeVisible, result } = block;

  const hasDataOutputs = result?.outputs?.some(o =>
    o.type === 'table' || o.type === 'chart' || o.type === 'plotly_chart' ||
    o.type === 'research' || o.type === 'news'
  );

  const renderOutput = (output: OutputBlock, index: number) => {
    if (output.type === 'stats' && (output as any).content && hasDataOutputs) return null;

    switch (output.type) {
      case 'table': {
        const columns = output.columns || [];
        const rows = output.rows || [];
        const isSectorPerformance =
          columns.includes('sector') && columns.includes('ticker_count') &&
          columns.includes('tickers') && columns.includes('avg_change');
        if (isSectorPerformance) return <SectorPerformanceTable key={index} rows={rows as any} title={output.title} total={output.total} />;
        return <DataTable key={index} columns={columns} rows={rows} title={output.title} total={output.total} />;
      }

      case 'chart':
      case 'plotly_chart':
        if (output.plotly_config) return <Chart key={index} title={output.title} plotlyConfig={output.plotly_config} />;
        if ((output as any).image_base64) {
          return (
            <div key={index} className="rounded-lg border border-slate-200 bg-white overflow-hidden">
              {output.title && <div className="px-3 py-1.5 bg-slate-50 border-b text-[10px] font-medium text-slate-600">{output.title}</div>}
              <img src={'data:image/png;base64,' + (output as any).image_base64} alt={output.title || 'Chart'} className="max-w-full h-auto" />
            </div>
          );
        }
        return null;

      case 'stats':
        if ((output as any).content) return <V4ResponseRenderer key={index} content={(output as any).content} />;
        if (output.stats && Object.keys(output.stats).length > 0) {
          return (
            <div key={index} className="rounded-lg border border-slate-200 bg-white p-3">
              <h3 className="text-[10px] font-semibold text-slate-700 mb-2">{output.title}</h3>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(output.stats).map(([col, stats]) => (
                  <div key={col} className="bg-slate-50 rounded p-2">
                    <div className="text-[9px] text-slate-500 uppercase font-medium">{col}</div>
                    <div className="grid grid-cols-2 gap-0.5 text-[10px] mt-1">
                      <span className="text-slate-400">Min:</span>
                      <span className="font-mono tabular-nums">{stats.min}</span>
                      <span className="text-slate-400">Max:</span>
                      <span className="font-mono tabular-nums">{stats.max}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        }
        return null;

      case 'research': {
        const researchOutput = output as any;
        const citations = researchOutput.citations || [];
        const rawContent = researchOutput.content || '';

        // V4: standard markdown without citations
        if (citations.length === 0 && rawContent) {
          return <V4ResponseRenderer key={index} content={rawContent} />;
        }

        // V3 deep research with citations
        const tickerMatch = researchOutput.title?.match(/Research:\s*([A-Z]{1,5})/i);
        const ticker = tickerMatch ? tickerMatch[1].toUpperCase() : null;

        const CitationBadge = ({ num, url }: { num: number; url?: string }) => {
          const href = url || citations[num - 1];
          if (!href) return <sup className="text-slate-400 text-[9px]">[{num}]</sup>;
          return (
            <a href={href} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center justify-center min-w-[14px] h-[14px] px-0.5 ml-0.5 text-[9px] font-medium bg-indigo-50 text-indigo-600 rounded hover:bg-indigo-100 cursor-pointer align-super transition-colors"
              title={href}
            >
              {num}
            </a>
          );
        };

        const renderTextWithCitations = (text: string) => {
          let cleaned = text
            .replace(/\*\*:/g, ':').replace(/:\*\*/g, ':')
            .replace(/\*\*\s*\*\*/g, '')
            .replace(/\*\*([^*]+)\*\*/g, '<b class="font-semibold text-slate-800">$1</b>')
            .replace(/\*([^*]+)\*/g, '<i>$1</i>')
            .trim();
          const pattern = /(\[\[\d+\]\]\([^)]+\)|\[\d+(?:,\d+)*\])/g;
          const parts = cleaned.split(pattern);
          return parts.map((part, i) => {
            const inlineMatch = part.match(/\[\[(\d+)\]\]\(([^)]+)\)/);
            if (inlineMatch) return <CitationBadge key={i} num={parseInt(inlineMatch[1])} url={inlineMatch[2]} />;
            const simpleMatch = part.match(/\[(\d+(?:,\d+)*)\]/);
            if (simpleMatch) {
              const nums = simpleMatch[1].split(',').map(n => parseInt(n.trim()));
              return <span key={i}>{nums.map((num, j) => <CitationBadge key={j} num={num} />)}</span>;
            }
            if (part.includes('<b') || part.includes('<i>')) return <span key={i} dangerouslySetInnerHTML={{ __html: part }} />;
            return part || null;
          });
        };

        const parseContent = (text: string) => {
          const sections: { title: string; content: string }[] = [];
          const pats = [
            { regex: /\*\*(?:Summary|Resumen|TLDR)\*\*\s*\n([\s\S]*?)(?=\n\*\*[A-Z]|$)/i, title: 'Summary' },
            { regex: /\*\*(?:Breaking News|Noticias[^\*]*)\*\*\s*\n([\s\S]*?)(?=\n\*\*[A-Z]|$)/i, title: 'Breaking News' },
            { regex: /\*\*(?:Analysis|An.lisis)\*\*\s*\n([\s\S]*?)(?=\n\*\*[A-Z]|---|$)/i, title: 'Analysis' },
            { regex: /\*\*(?:Technical View|Vista T.cnica)\*\*\s*\n([\s\S]*?)(?=\n\*\*[A-Z]|---|$)/i, title: 'Technical View' },
          ];
          for (const { regex, title } of pats) {
            const match = text.match(regex);
            if (match?.[1]?.trim()) sections.push({ title, content: match[1].trim() });
          }
          return sections;
        };

        const sections = parseContent(rawContent);

        return (
          <div key={index} className="space-y-3">
            <div className="pb-2 border-b border-slate-200">
              <h3 className="text-[12px] font-bold text-slate-900">{ticker ? ticker + ' Research' : 'Research'}</h3>
              <p className="text-[9px] text-slate-500 mt-0.5">{citations.length} sources cited</p>
            </div>
            {sections.map((section, sidx) => (
              <div key={sidx} className="space-y-1.5">
                <h4 className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">{section.title}</h4>
                <div className="text-[11px] text-slate-800 leading-[1.6] space-y-1.5">
                  {section.content.split('\n').filter(l => l.trim()).map((line, li) => {
                    const t = line.trim();
                    if (t.startsWith('-') || t.startsWith('\u2022')) {
                      return (
                        <div key={li} className="flex gap-2 pl-2">
                          <span className="text-indigo-400 select-none">&bull;</span>
                          <span>{renderTextWithCitations(t.replace(/^[-\u2022]\s*/, ''))}</span>
                        </div>
                      );
                    }
                    return <p key={li}>{renderTextWithCitations(t)}</p>;
                  })}
                </div>
              </div>
            ))}
            {ticker && (
              <div className="border border-slate-200 rounded-lg overflow-hidden mt-3">
                <div className="h-[280px]"><TradingChart ticker={ticker} minimal /></div>
              </div>
            )}
          </div>
        );
      }

      case 'news': {
        const newsOutput = output as any;
        const newsItems = newsOutput.news || [];
        const symbol = newsOutput.symbol || '';
        return (
          <div key={index} className="rounded-lg border border-slate-200 bg-white overflow-hidden">
            <div className="px-3 py-1.5 border-b border-slate-200 flex items-center justify-between">
              <div>
                <h3 className="text-[11px] font-semibold text-slate-800">{symbol ? 'News: ' + symbol : 'News'}</h3>
                <p className="text-[9px] text-slate-500">{newsItems.length} articles</p>
              </div>
              {newsOutput.deep_research_available && (
                <button
                  onClick={() => window.dispatchEvent(new CustomEvent('agent:send', { detail: { message: 'deep research ' + symbol } }))}
                  className="px-2 py-1 text-[9px] text-indigo-600 bg-indigo-50 border border-indigo-200/60 rounded hover:bg-indigo-100 transition-colors flex items-center gap-1"
                >
                  <Search className="w-2.5 h-2.5" />Deep Research
                </button>
              )}
            </div>
            <div className="divide-y divide-slate-100">
              {newsItems.map((news: any, i: number) => (
                <div key={i} className="px-3 py-1.5 hover:bg-indigo-50/30 transition-colors">
                  <h4 className="text-[10px] font-medium text-slate-800 leading-snug">{news.title}</h4>
                  {news.summary && <p className="text-[10px] text-slate-600 mt-0.5 leading-relaxed">{news.summary}</p>}
                  <div className="flex items-center gap-1.5 mt-1 text-[9px] text-slate-400">
                    <span>{news.source}</span>
                    {news.published && (
                      <>
                        <span>-</span>
                        <span>{new Date(news.published).toLocaleString('es-ES', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      }

      case 'error':
        return (
          <div key={index} className="rounded-lg border border-red-200/60 bg-red-50/50 p-3">
            <div className="text-[10px] font-semibold text-red-700">Error</div>
            <p className="mt-0.5 text-[10px] text-red-600 font-mono">{output.title}</p>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="space-y-2">
      {result?.outputs?.[0] && (result.outputs[0] as any).content && (
        <div className="flex justify-end -mt-0.5 -mb-0.5">
          <CopyButton text={(result.outputs[0] as any).content} />
        </div>
      )}

      {/* Code */}
      {code && <CodeBlock code={code} title="Code" isVisible={codeVisible} onToggle={onToggleCode} />}

      {/* Outputs */}
      {result?.outputs && result.outputs.length > 0 && (
        <div className="space-y-2">
          {result.outputs.map((output, index) => renderOutput(output, index))}
        </div>
      )}

      {/* Error */}
      {result?.error && status === 'error' && (
        <div className="rounded-lg border border-red-200/60 bg-red-50/50 p-3">
          <div className="text-[10px] font-semibold text-red-700 mb-1">Execution Error</div>
          <pre className="text-[11px] text-red-600 font-mono whitespace-pre-wrap">{result.error}</pre>
        </div>
      )}
    </div>
  );
});

