'use client';

import { memo, useMemo } from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';

interface DataTableProps {
  columns: string[];
  rows: Record<string, unknown>[];
  title?: string;
  total?: number;
}

function formatValue(value: unknown, column: string): React.ReactNode {
  if (value === null || value === undefined) {
    return <span className="text-gray-300">-</span>;
  }

  const strValue = String(value);

  if (column === 'symbol') {
    return <span className="font-semibold text-blue-600">{strValue}</span>;
  }

  if (column.includes('percent') || column.includes('pct') || column.startsWith('chg_')) {
    const num = Number(value);
    if (isNaN(num)) return strValue;
    const color = num > 0 ? 'text-green-600' : num < 0 ? 'text-red-500' : 'text-gray-400';
    const icon = num > 0 ? <TrendingUp className="w-3 h-3 inline mr-0.5" /> :
                 num < 0 ? <TrendingDown className="w-3 h-3 inline mr-0.5" /> : null;
    return <span className={color}>{icon}{num > 0 ? '+' : ''}{num.toFixed(2)}%</span>;
  }

  if (['price', 'bid', 'ask', 'open', 'high', 'low', 'prev_close', 'vwap'].includes(column)) {
    const num = Number(value);
    if (isNaN(num)) return strValue;
    return <span className="font-mono">${num.toFixed(2)}</span>;
  }

  if (column.includes('volume') || column.startsWith('vol_')) {
    const num = Number(value);
    if (isNaN(num)) return strValue;
    if (num >= 1e9) return <span className="font-mono">{(num / 1e9).toFixed(1)}B</span>;
    if (num >= 1e6) return <span className="font-mono">{(num / 1e6).toFixed(1)}M</span>;
    if (num >= 1e3) return <span className="font-mono">{(num / 1e3).toFixed(0)}K</span>;
    return <span className="font-mono">{num.toLocaleString()}</span>;
  }

  if (column === 'rvol' || column === 'rvol_slot') {
    const num = Number(value);
    if (isNaN(num)) return strValue;
    const color = num >= 5 ? 'text-purple-600 font-bold' : num >= 3 ? 'text-orange-500' : num >= 2 ? 'text-yellow-600' : '';
    return <span className={`font-mono ${color}`}>{num.toFixed(1)}x</span>;
  }

  if (column === 'market_cap' || column === 'dollar_volume') {
    const num = Number(value);
    if (isNaN(num)) return strValue;
    if (num >= 1e12) return <span className="font-mono">${(num / 1e12).toFixed(1)}T</span>;
    if (num >= 1e9) return <span className="font-mono">${(num / 1e9).toFixed(1)}B</span>;
    if (num >= 1e6) return <span className="font-mono">${(num / 1e6).toFixed(0)}M</span>;
    return <span className="font-mono">${num.toLocaleString()}</span>;
  }

  if (typeof value === 'number') {
    return <span className="font-mono">{value.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>;
  }

  return <span className="text-gray-600 truncate max-w-[150px] block">{strValue}</span>;
}

function getColumnLabel(column: string): string {
  const labels: Record<string, string> = {
    symbol: 'Symbol',
    price: 'Price',
    change_percent: 'Change %',
    volume_today: 'Volume',
    rvol_slot: 'RVOL',
    market_cap: 'Market Cap',
    sector: 'Sector',
  };
  return labels[column] || column.replace(/_/g, ' ').slice(0, 15);
}

export const DataTable = memo(function DataTable({ columns, rows, title, total }: DataTableProps) {
  const displayColumns = useMemo(() => {
    const priority = ['symbol', 'price', 'change_percent', 'volume_today', 'rvol_slot', 'market_cap', 'sector'];
    const sorted = [...columns].sort((a, b) => {
      const ai = priority.indexOf(a);
      const bi = priority.indexOf(b);
      if (ai === -1 && bi === -1) return 0;
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi;
    });
    return sorted.slice(0, 8);
  }, [columns]);

  const renderedRows = useMemo(() => {
    return rows.slice(0, 50).map((row, i) => (
      <tr key={i} className="hover:bg-blue-50/50">
        {displayColumns.map((col) => (
          <td key={col} className="px-2 py-1.5 text-[12px] whitespace-nowrap">
            {formatValue(row[col], col)}
          </td>
        ))}
      </tr>
    ));
  }, [displayColumns, rows]);

  return (
    <div className="rounded border border-gray-200 bg-white overflow-hidden">
      {title && (
        <div className="px-3 py-2 bg-blue-50 border-b border-gray-200">
          <h3 className="text-[12px] font-medium text-gray-700">
            {title}
            {total !== undefined && <span className="ml-2 text-gray-400">({total} resultados)</span>}
          </h3>
        </div>
      )}

      <div className="overflow-x-auto max-h-[45vh] overflow-y-auto">
        <table className="w-full">
          <thead className="bg-gray-50 sticky top-0">
            <tr>
              {displayColumns.map((col) => (
                <th key={col} className="px-2 py-2 text-left text-[11px] font-medium text-gray-500 uppercase border-b border-gray-200">
                  {getColumnLabel(col)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {renderedRows}
          </tbody>
        </table>
      </div>

      {rows.length === 0 && (
        <div className="py-6 text-center text-[12px] text-gray-400">Sin resultados</div>
      )}
    </div>
  );
});
