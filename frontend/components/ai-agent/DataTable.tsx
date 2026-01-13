'use client';

import { memo, useMemo, useCallback } from 'react';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { ChartContent } from '@/components/chart/ChartContent';
import { DataTableContent } from './DataTableModal';

interface DataTableProps {
  columns: string[];
  rows: Record<string, unknown>[];
  title?: string;
  total?: number;
}

function formatValue(value: unknown, column: string, onOpenChart?: (t: string) => void): React.ReactNode {
  if (value === null || value === undefined) return <span className="text-slate-300">-</span>;
  const str = String(value);

  // Symbol clickeable
  if (column === 'symbol' && onOpenChart) {
    return (
      <button
        onClick={() => onOpenChart(str)}
        className="font-semibold text-blue-600 hover:text-blue-800 hover:underline cursor-pointer"
      >
        {str}
      </button>
    );
  }

  if (column === 'symbol') return <span className="font-semibold text-blue-600">{str}</span>;

  if (column.includes('percent') || column.includes('pct') || column.includes('change')) {
    const n = Number(value);
    if (isNaN(n)) return str;
    const c = n > 0 ? 'text-[var(--color-tick-up)]' : n < 0 ? 'text-[var(--color-tick-down)]' : 'text-slate-400';
    return <span className={c}>{n > 0 ? '+' : ''}{n.toFixed(2)}%</span>;
  }

  if (['price', 'bid', 'ask', 'open', 'high', 'low', 'prev_close', 'vwap'].includes(column)) {
    const n = Number(value);
    return isNaN(n) ? str : <span className="font-[family-name:var(--font-mono-selected)]">${n.toFixed(2)}</span>;
  }

  if (column.includes('volume') || column.startsWith('vol_')) {
    const n = Number(value);
    if (isNaN(n)) return str;
    const fmt = n >= 1e9 ? `${(n/1e9).toFixed(1)}B` : n >= 1e6 ? `${(n/1e6).toFixed(1)}M` : n >= 1e3 ? `${(n/1e3).toFixed(0)}K` : n.toLocaleString();
    return <span className="font-[family-name:var(--font-mono-selected)]">{fmt}</span>;
  }

  if (column === 'market_cap' || column === 'dollar_volume') {
    const n = Number(value);
    if (isNaN(n)) return str;
    const fmt = n >= 1e12 ? `$${(n/1e12).toFixed(1)}T` : n >= 1e9 ? `$${(n/1e9).toFixed(1)}B` : n >= 1e6 ? `$${(n/1e6).toFixed(0)}M` : `$${n.toLocaleString()}`;
    return <span className="font-[family-name:var(--font-mono-selected)]">{fmt}</span>;
  }

  if (column === 'rvol' || column === 'rvol_slot') {
    const n = Number(value);
    if (isNaN(n) || n === 0) return <span className="text-slate-400">-</span>;
    const c = n >= 5 ? 'text-purple-600 font-bold' : n >= 3 ? 'text-orange-500' : n >= 2 ? 'text-amber-600' : '';
    return <span className={`font-[family-name:var(--font-mono-selected)] ${c}`}>{n.toFixed(1)}x</span>;
  }

  if (column === 'synthetic_sector' || column === 'synthetic_secto') {
    return <span className="text-indigo-600 text-[10px]">{str}</span>;
  }

  if (typeof value === 'number') {
    return <span className="font-[family-name:var(--font-mono-selected)]">{value.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>;
  }

  return <span className="text-slate-600 truncate max-w-[100px] block">{str}</span>;
}

const COL_LABELS: Record<string, string> = {
  symbol: 'Sym', price: 'Price', change_percent: 'Chg%', premarket_change_percent: 'Pre%',
  volume_today: 'Vol', rvol: 'RVOL', rvol_slot: 'RVOL', market_cap: 'MCap', sector: 'Sector',
  synthetic_sector: 'Synth', synthetic_secto: 'Synth',
};

const getLabel = (c: string) => COL_LABELS[c] || c.replace(/_/g, ' ').slice(0, 8);

const PREVIEW = 30;
const THRESHOLD = 50;

export const DataTable = memo(function DataTable({ columns, rows, title, total }: DataTableProps) {
  const { openWindow } = useFloatingWindow();

  const cols = useMemo(() => {
    const priority = ['symbol', 'price', 'change_percent', 'premarket_change_percent', 'volume_today', 'rvol', 'rvol_slot', 'market_cap', 'synthetic_sector', 'synthetic_secto', 'sector'];
    return [...columns].sort((a, b) => {
      const ai = priority.indexOf(a), bi = priority.indexOf(b);
      if (ai === -1 && bi === -1) return 0;
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi;
    }).slice(0, 8);
  }, [columns]);

  const preview = useMemo(() => rows.slice(0, PREVIEW), [rows]);
  const hasMore = rows.length > THRESHOLD;
  const count = total ?? rows.length;

  // Abrir gráfico en ventana flotante
  const handleOpenChart = useCallback((ticker: string) => {
    const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
    const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;
    openWindow({
      title: 'Chart',
      content: <ChartContent ticker={ticker.toUpperCase()} />,
      width: 900,
      height: 600,
      x: Math.max(50, screenWidth / 2 - 450),
      y: Math.max(80, screenHeight / 2 - 300),
      minWidth: 600,
      minHeight: 400,
    });
  }, [openWindow]);

  // Abrir tabla completa en ventana flotante
  const handleOpenFullTable = useCallback(() => {
    const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
    const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;
    openWindow({
      title: title || 'Datos',
      content: <DataTableContent columns={columns} rows={rows} title={title || 'Datos'} total={count} />,
      width: 900,
      height: 600,
      x: Math.max(50, screenWidth / 2 - 450),
      y: Math.max(80, screenHeight / 2 - 300),
      minWidth: 500,
      minHeight: 300,
    });
  }, [openWindow, columns, rows, title, count]);

  return (
    <div className="rounded border border-slate-200 bg-white overflow-hidden">
      {title && (
        <div className="px-2 py-1 bg-slate-50 border-b border-slate-200 flex justify-between text-[11px]">
          <span className="font-medium text-slate-700">{title}</span>
          <div className="flex items-center gap-2">
            <span className="text-slate-400">{count}</span>
            {hasMore && (
              <button onClick={handleOpenFullTable} className="text-blue-600 hover:underline">
                ver todos
              </button>
            )}
          </div>
        </div>
      )}
      <div className="overflow-x-auto max-h-[40vh] overflow-y-auto">
        <table className="w-full text-[11px]">
          <thead className="bg-slate-50 sticky top-0 text-[9px] text-slate-500 uppercase">
            <tr>
              {cols.map(c => <th key={c} className="px-1.5 py-1 text-left whitespace-nowrap">{getLabel(c)}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {preview.map((row, i) => (
              <tr key={i} className="hover:bg-slate-50/50">
                {cols.map(c => (
                  <td key={c} className="px-1.5 py-1 whitespace-nowrap">
                    {formatValue(row[c], c, c === 'symbol' ? handleOpenChart : undefined)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length === 0 && <div className="py-3 text-center text-[11px] text-slate-400">Sin resultados</div>}
    </div>
  );
});
