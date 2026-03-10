'use client';

import React, { memo, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowUpRight, ArrowDownRight, Minus, BarChart3,
} from 'lucide-react';
import dynamic from 'next/dynamic';

const LazyAutoChart = dynamic(() => import('./AutoChart').then(m => m.AutoBarChart), {
  ssr: false,
  loading: () => <div className="h-[240px] bg-surface-hover rounded-xl animate-pulse" />,
});

interface MetricsCard {
  ticker: string;
  company_name: string;
  sector: string;
  price: string;
  change: string;
  volume: string;
  rvol: string;
  rsi: string;
  vwap_dist: string;
  adx: string;
  week52_range: string;
  float_shares: string;
  market_cap: string;
}

interface TableRow { cells: string[]; }
interface DataTable { headers: string[]; rows: TableRow[]; }
interface Section { title: string; content: string; table: DataTable | null; bullets: string[]; }
interface Citation { title: string; url: string; }

export interface StructuredResponse {
  session_context: string;
  metrics: MetricsCard | null;
  sections: Section[];
  citations: Citation[];
  key_takeaways: string[];
}

function fmtInline(text: string): string {
  return text
    .replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold text-foreground">$1</strong>')
    .replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em class="text-foreground">$1</em>')
    .replace(/`([^`]+)`/g, '<code class="px-0.5 py-px rounded bg-surface-inset text-primary text-[10px] font-mono">$1</code>')
    .replace(/\$(\d[\d,.]*)/g, '<span class="font-semibold tabular-nums text-foreground">$$$1</span>');
}

function MetricPill({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  const num = parseFloat(value.replace(/[^-\d.]/g, ''));
  const color = highlight
    ? (num > 0 ? 'text-emerald-600 font-semibold' : num < 0 ? 'text-red-500 font-semibold' : 'text-foreground')
    : 'text-foreground';
  return (
    <div className="min-w-0">
      <div className="text-[8px] font-medium text-muted-fg uppercase tracking-wider truncate">{label}</div>
      <div className={`tabular-nums truncate ${color}`}>{value}</div>
    </div>
  );
}

function MetricsCardBlock({ m }: { m: MetricsCard }) {
  const changeNum = parseFloat(m.change.replace(/[^-\d.]/g, ''));
  const isUp = changeNum > 0;
  const isDown = changeNum < 0;
  const TrendIcon = isUp ? ArrowUpRight : isDown ? ArrowDownRight : Minus;
  const trendColor = isUp ? 'text-emerald-600' : isDown ? 'text-red-500' : 'text-muted-fg';
  const trendBg = isUp ? 'bg-emerald-500/10' : isDown ? 'bg-red-500/10' : 'bg-surface-hover';

  return (
    <div className={`rounded-lg border border-border p-2.5 ${trendBg}`}>
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className="text-[13px] font-bold text-foreground">{m.ticker}</span>
        <span className="text-[10px] text-muted-fg">{'\u2014'} {m.company_name}</span>
        {m.sector && <span className="text-[9px] text-muted-fg">({m.sector})</span>}
        <TrendIcon className={`w-3.5 h-3.5 ml-auto ${trendColor}`} />
      </div>
      <div className="grid grid-cols-3 sm:grid-cols-4 gap-x-3 gap-y-1 text-[10px]">
        {m.price && <MetricPill label="Price" value={m.price} />}
        {m.change && <MetricPill label="Change" value={m.change} highlight />}
        {m.volume && <MetricPill label="Volume" value={m.volume} />}
        {m.rvol && <MetricPill label="RVOL" value={m.rvol} />}
        {m.rsi && <MetricPill label="RSI(14)" value={m.rsi} />}
        {m.vwap_dist && <MetricPill label="VWAP Dist" value={m.vwap_dist} />}
        {m.adx && <MetricPill label="ADX(14)" value={m.adx} />}
        {m.week52_range && <MetricPill label="52W Range" value={m.week52_range} />}
        {m.float_shares && <MetricPill label="Float" value={m.float_shares} />}
        {m.market_cap && <MetricPill label="Mkt Cap" value={m.market_cap} />}
      </div>
    </div>
  );
}

const TABLE_PREVIEW = 10;

function StructuredTable({ table }: { table: DataTable }) {
  const [sortCol, setSortCol] = useState<number | null>(null);
  const [sortAsc, setSortAsc] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [showChart, setShowChart] = useState(false);

  const rows = useMemo(() => table.rows.map(r => r.cells), [table.rows]);

  const isNumeric = useMemo(() => {
    return table.headers.map((_, colIdx) => {
      const vals = rows.map(r => r[colIdx] || '').filter(Boolean);
      const numCount = vals.filter(v => !isNaN(parseFloat(v.replace(/[,$%x]/g, '')))).length;
      return numCount > vals.length * 0.5;
    });
  }, [table.headers, rows]);

  const sortedRows = useMemo(() => {
    if (sortCol === null) return rows;
    return [...rows].sort((a, b) => {
      const av = a[sortCol] || '';
      const bv = b[sortCol] || '';
      const an = parseFloat(av.replace(/[,$%x]/g, ''));
      const bn = parseFloat(bv.replace(/[,$%x]/g, ''));
      if (!isNaN(an) && !isNaN(bn)) return sortAsc ? an - bn : bn - an;
      return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
    });
  }, [rows, sortCol, sortAsc]);

  const handleSort = (colIdx: number) => {
    if (sortCol === colIdx) setSortAsc(!sortAsc);
    else { setSortCol(colIdx); setSortAsc(true); }
  };

  const getCellColor = (value: string): string => {
    const num = parseFloat(value.replace(/[,$%x]/g, ''));
    if (isNaN(num)) return 'text-foreground';
    if (value.includes('%')) {
      if (num > 0) return 'text-emerald-600 font-medium';
      if (num < 0) return 'text-red-500 font-medium';
    }
    return 'text-foreground';
  };

  const visibleRows = expanded ? sortedRows : sortedRows.slice(0, TABLE_PREVIEW);

  return (
    <div className="space-y-1.5">
      <div className="overflow-x-auto rounded-lg border border-border bg-surface">
        <table className="w-full text-[10px]">
          <thead>
            <tr className="bg-surface-hover/80">
              {table.headers.map((h, i) => (
                <th
                  key={i}
                  onClick={() => handleSort(i)}
                  className={'px-2 py-1.5 font-semibold text-foreground/80 cursor-pointer hover:bg-surface-hover transition-colors select-none whitespace-nowrap ' + (isNumeric[i] ? 'text-right' : 'text-left')}
                >
                  <span className="inline-flex items-center gap-0.5">
                    {h}
                    {sortCol === i && (
                      <span className="text-[8px] text-primary">
                        {sortAsc ? '\u25B2' : '\u25BC'}
                      </span>
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {visibleRows.map((row, rowIdx) => (
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
        {sortedRows.length > TABLE_PREVIEW && !expanded && (
          <button
            onClick={() => setExpanded(true)}
            className="w-full py-1.5 text-[10px] text-muted-fg hover:text-foreground bg-surface-hover border-t border-border transition-colors"
          >
            Show more ({sortedRows.length - TABLE_PREVIEW} more rows)
          </button>
        )}
      </div>
      {rows.length >= 2 && (
        <button
          onClick={() => setShowChart(!showChart)}
          className="inline-flex items-center gap-1 px-2 py-1 text-[9px] font-medium text-primary bg-primary/10 hover:bg-primary/15 rounded transition-colors"
        >
          <BarChart3 className="w-3 h-3" />
          {showChart ? 'Hide Chart' : 'Visualize'}
        </button>
      )}
      <AnimatePresence>
        {showChart && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25 }}
          >
            <LazyAutoChart headers={table.headers} rows={rows} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function SectionBlock({ section }: { section: Section }) {
  const contentLines = section.content ? section.content.split('\n').filter(l => l.trim()) : [];

  return (
    <div className="space-y-1.5">
      {section.title && (
        <h3 className="text-[12px] font-bold text-foreground flex items-center gap-1.5">
          <span className="w-0.5 h-3 rounded-full bg-primary inline-block" />
          {section.title}
        </h3>
      )}

      {contentLines.map((line, i) => {
        const trimmed = line.trim();
        if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
          return (
            <div key={i} className="flex gap-1.5 text-[11px] text-foreground/80 leading-relaxed pl-0.5">
              <span className="text-primary mt-0.5 select-none flex-shrink-0">&bull;</span>
              <span dangerouslySetInnerHTML={{ __html: fmtInline(trimmed.slice(2)) }} />
            </div>
          );
        }
        if (/^#{2,4}\s/.test(trimmed)) {
          return (
            <h4 key={i} className="text-[11px] font-semibold text-foreground mt-1.5">
              {trimmed.replace(/^#{2,4}\s*/, '')}
            </h4>
          );
        }
        return (
          <p key={i} className="text-[11px] text-foreground/80 leading-relaxed"
            dangerouslySetInnerHTML={{ __html: fmtInline(trimmed) }}
          />
        );
      })}

      {section.table && section.table.headers.length > 0 && section.table.rows.length > 0 && (
        <StructuredTable table={section.table} />
      )}

      {section.bullets.length > 0 && (
        <div className="space-y-0.5">
          {section.bullets.map((b, i) => (
            <div key={i} className="flex gap-1.5 text-[11px] text-foreground/80 leading-relaxed pl-0.5">
              <span className="text-primary mt-0.5 select-none flex-shrink-0">&bull;</span>
              <span dangerouslySetInnerHTML={{ __html: fmtInline(b) }} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export const StructuredResponseRenderer = memo(function StructuredResponseRenderer({
  data,
}: {
  data: StructuredResponse;
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className="space-y-2.5"
    >
      {data.session_context && (
        <p className="text-[10px] text-muted-fg italic">
          {data.session_context}
        </p>
      )}

      {data.metrics && data.metrics.ticker && (
        <MetricsCardBlock m={data.metrics} />
      )}

      {data.sections.map((section, idx) => (
        <SectionBlock key={idx} section={section} />
      ))}

      {data.key_takeaways.length > 0 && (
        <div className="space-y-1">
          <h3 className="text-[12px] font-bold text-foreground flex items-center gap-1.5">
            <span className="w-0.5 h-3 rounded-full bg-amber-500 inline-block" />
            Key Takeaways
          </h3>
          {data.key_takeaways.map((t, i) => (
            <div key={i} className="flex gap-1.5 text-[11px] text-foreground leading-relaxed pl-0.5">
              <span className="text-amber-500 mt-0.5 select-none flex-shrink-0">&bull;</span>
              <span dangerouslySetInnerHTML={{ __html: fmtInline(t) }} />
            </div>
          ))}
        </div>
      )}

      {data.citations.length > 0 && (
        <div className="pt-1.5 border-t border-border">
          <div className="text-[9px] text-muted-fg font-medium uppercase tracking-wider mb-1">Sources</div>
          <div className="flex flex-wrap gap-1">
            {data.citations.map((c, i) => {
              let host = '';
              try { host = new URL(c.url).hostname; } catch { host = c.url; }
              return (
                <a
                  key={i}
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[9px] font-medium bg-primary/10 text-primary rounded hover:bg-primary/15 transition-colors"
                  title={c.url}
                >
                  [{i + 1}] {c.title || host}
                </a>
              );
            })}
          </div>
        </div>
      )}
    </motion.div>
  );
});
