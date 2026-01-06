'use client';

import { memo, useMemo } from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface DataTableProps {
  columns: string[];
  rows: Record<string, unknown>[];
  title?: string;
  total?: number;
}

// Formatear valores segun el tipo
function formatValue(value: unknown, column: string): React.ReactNode {
  if (value === null || value === undefined) {
    return <span className="text-gray-400">-</span>;
  }

  const strValue = String(value);

  // Symbol - resaltar
  if (column === 'symbol') {
    return <span className="font-semibold text-blue-600">{strValue}</span>;
  }

  // Porcentajes
  if (column.includes('percent') || column.includes('pct') || column.startsWith('chg_')) {
    const num = Number(value);
    if (isNaN(num)) return strValue;

    const color = num > 0 ? 'text-green-600' : num < 0 ? 'text-red-600' : 'text-gray-500';
    const icon = num > 0 ? <TrendingUp className="w-3 h-3 inline mr-1" /> :
                 num < 0 ? <TrendingDown className="w-3 h-3 inline mr-1" /> :
                 <Minus className="w-3 h-3 inline mr-1" />;

    return (
      <span className={color}>
        {icon}
        {num > 0 ? '+' : ''}{num.toFixed(2)}%
      </span>
    );
  }

  // Precios
  if (column === 'price' || column === 'bid' || column === 'ask' ||
      column === 'open' || column === 'high' || column === 'low' ||
      column === 'prev_close' || column === 'vwap') {
    const num = Number(value);
    if (isNaN(num)) return strValue;
    return <span className="font-mono text-gray-800">${num.toFixed(2)}</span>;
  }

  // Volumen (formatear con K, M)
  if (column.includes('volume') || column.startsWith('vol_')) {
    const num = Number(value);
    if (isNaN(num)) return strValue;

    if (num >= 1_000_000_000) {
      return <span className="font-mono text-gray-700">{(num / 1_000_000_000).toFixed(2)}B</span>;
    }
    if (num >= 1_000_000) {
      return <span className="font-mono text-gray-700">{(num / 1_000_000).toFixed(2)}M</span>;
    }
    if (num >= 1_000) {
      return <span className="font-mono text-gray-700">{(num / 1_000).toFixed(1)}K</span>;
    }
    return <span className="font-mono text-gray-700">{num.toLocaleString()}</span>;
  }

  // RVOL - colorear segun valor
  if (column === 'rvol' || column === 'rvol_slot') {
    const num = Number(value);
    if (isNaN(num)) return strValue;

    const color = num >= 5 ? 'text-purple-600 font-bold' :
                  num >= 3 ? 'text-orange-600' :
                  num >= 2 ? 'text-yellow-600' :
                  'text-gray-500';

    return <span className={`font-mono ${color}`}>{num.toFixed(2)}x</span>;
  }

  // Z-Score
  if (column === 'trades_z_score') {
    const num = Number(value);
    if (isNaN(num)) return strValue;

    const color = num >= 3 ? 'text-red-600 font-bold' :
                  num >= 2 ? 'text-orange-600' :
                  'text-gray-500';

    return <span className={`font-mono ${color}`}>{num.toFixed(2)}</span>;
  }

  // Market Cap
  if (column === 'market_cap' || column === 'dollar_volume') {
    const num = Number(value);
    if (isNaN(num)) return strValue;

    if (num >= 1_000_000_000_000) {
      return <span className="font-mono text-gray-700">${(num / 1_000_000_000_000).toFixed(2)}T</span>;
    }
    if (num >= 1_000_000_000) {
      return <span className="font-mono text-gray-700">${(num / 1_000_000_000).toFixed(2)}B</span>;
    }
    if (num >= 1_000_000) {
      return <span className="font-mono text-gray-700">${(num / 1_000_000).toFixed(2)}M</span>;
    }
    return <span className="font-mono text-gray-700">${num.toLocaleString()}</span>;
  }

  // Numeros genericos
  if (typeof value === 'number') {
    return <span className="font-mono text-gray-700">{value.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>;
  }

  // Boolean
  if (typeof value === 'boolean') {
    return value ?
      <span className="text-green-600">Si</span> :
      <span className="text-gray-400">-</span>;
  }

  // Sector/Industry - capitalizar
  if (column === 'sector' || column === 'industry') {
    return <span className="text-gray-700">{strValue}</span>;
  }

  return <span className="text-gray-700">{strValue}</span>;
}

// Obtener nombre de columna legible
function getColumnLabel(column: string): string {
  const labels: Record<string, string> = {
    symbol: 'Symbol',
    price: 'Price',
    change_percent: 'Change %',
    volume_today: 'Volume',
    rvol_slot: 'RVOL',
    rvol: 'RVOL',
    market_cap: 'Market Cap',
    sector: 'Sector',
    industry: 'Industry',
    chg_5min: '5min',
    chg_1min: '1min',
    trades_z_score: 'Z-Score',
    is_trade_anomaly: 'Anomaly',
    vwap: 'VWAP',
    price_vs_vwap: 'vs VWAP',
    price_from_intraday_high: 'from HOD',
    price_from_intraday_low: 'from LOD',
    avg_volume_10d: 'Avg Vol 10d',
    dollar_volume: 'Dollar Vol',
    free_float: 'Float',
    spread: 'Spread',
    spread_percent: 'Spread %',
  };
  return labels[column] || column.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export const DataTable = memo(function DataTable({
  columns,
  rows,
  title,
  total
}: DataTableProps) {
  // Memoizar el renderizado de filas
  const renderedRows = useMemo(() => {
    return rows.map((row, rowIndex) => (
      <tr
        key={rowIndex}
        className="hover:bg-blue-50 transition-colors"
      >
        {columns.map((column) => (
          <td
            key={column}
            className="px-3 py-2 text-sm whitespace-nowrap"
          >
            {formatValue(row[column], column)}
          </td>
        ))}
      </tr>
    ));
  }, [columns, rows]);

  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden shadow-sm">
      {/* Header */}
      {title && (
        <div className="px-4 py-2 bg-blue-50 border-b border-gray-200">
          <h3 className="text-sm font-medium text-gray-800">
            {title}
            {total !== undefined && (
              <span className="ml-2 text-gray-500">({total} resultados)</span>
            )}
          </h3>
        </div>
      )}

      {/* Table - altura adaptativa al contenedor */}
      <div className="overflow-x-auto max-h-[50vh] overflow-y-auto">
        <table className="w-full">
          <thead className="bg-gray-50 sticky top-0">
            <tr>
              {columns.map((column) => (
                <th
                  key={column}
                  className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider border-b border-gray-200"
                >
                  {getColumnLabel(column)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {renderedRows}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      {rows.length === 0 && (
        <div className="px-4 py-8 text-center text-gray-400">
          Sin resultados
        </div>
      )}
    </div>
  );
});
