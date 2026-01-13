'use client';

import { memo, useState, useMemo, useCallback } from 'react';
import { Search, Download, ArrowUpDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { ChartContent } from '@/components/chart/ChartContent';

interface DataTableContentProps {
  columns: string[];
  rows: Record<string, unknown>[];
  title: string;
  total: number;
}

const formatValue = (value: unknown, column: string, onOpenChart?: (t: string) => void): React.ReactNode => {
  if (value === null || value === undefined) return <span className="text-slate-300">-</span>;
  const str = String(value);

  // Symbol: clickeable para abrir gráfico
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

  if (['price', 'bid', 'ask', 'open', 'high', 'low'].includes(column)) {
    const n = Number(value);
    return isNaN(n) ? str : <span className="font-[family-name:var(--font-mono-selected)]">${n.toFixed(2)}</span>;
  }

  if (column.includes('volume')) {
    const n = Number(value);
    if (isNaN(n)) return str;
    const fmt = n >= 1e9 ? `${(n/1e9).toFixed(1)}B` : n >= 1e6 ? `${(n/1e6).toFixed(1)}M` : n >= 1e3 ? `${(n/1e3).toFixed(0)}K` : n.toLocaleString();
    return <span className="font-[family-name:var(--font-mono-selected)]">{fmt}</span>;
  }

  if (column === 'market_cap') {
    const n = Number(value);
    if (isNaN(n)) return str;
    const fmt = n >= 1e9 ? `$${(n/1e9).toFixed(1)}B` : n >= 1e6 ? `$${(n/1e6).toFixed(0)}M` : `$${n.toLocaleString()}`;
    return <span className="font-[family-name:var(--font-mono-selected)]">{fmt}</span>;
  }

  return <span className="text-slate-600 truncate max-w-[120px] block">{str}</span>;
};

const COL_LABELS: Record<string, string> = {
  symbol: 'Sym', price: 'Price', change_percent: 'Chg%', premarket_change_percent: 'Pre%',
  volume_today: 'Vol', market_cap: 'MCap', sector: 'Sector', synthetic_sector: 'Synth',
};
const getLabel = (c: string) => COL_LABELS[c] || c.replace(/_/g, ' ').slice(0, 10);

const PER_PAGE = 100;

// Contenido de la tabla - se usa dentro de una ventana flotante
export const DataTableContent = memo(function DataTableContent({ 
  columns: rawCols, rows: allRows, title, total 
}: DataTableContentProps) {
  const [search, setSearch] = useState('');
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(1);
  const { openWindow } = useFloatingWindow();

  const cols = useMemo(() => {
    const priority = ['symbol', 'price', 'change_percent', 'premarket_change_percent', 'volume_today', 'market_cap', 'synthetic_sector', 'sector'];
    return [...rawCols].sort((a, b) => {
      const ai = priority.indexOf(a), bi = priority.indexOf(b);
      if (ai === -1 && bi === -1) return 0;
      return ai === -1 ? 1 : bi === -1 ? -1 : ai - bi;
    });
  }, [rawCols]);

  const filtered = useMemo(() => {
    let r = allRows;
    if (search) {
      const s = search.toLowerCase();
      r = r.filter(row => Object.values(row).some(v => String(v).toLowerCase().includes(s)));
    }
    if (sortCol) {
      r = [...r].sort((a, b) => {
        const av = a[sortCol], bv = b[sortCol];
        if (av == null) return 1;
        if (bv == null) return -1;
        if (typeof av === 'number' && typeof bv === 'number') return sortDir === 'asc' ? av - bv : bv - av;
        return sortDir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
      });
    }
    return r;
  }, [allRows, search, sortCol, sortDir]);

  const pages = Math.ceil(filtered.length / PER_PAGE);
  const pageRows = useMemo(() => filtered.slice((page - 1) * PER_PAGE, page * PER_PAGE), [filtered, page]);

  const sort = (c: string) => {
    if (sortCol === c) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(c); setSortDir('desc'); }
  };

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

  const exportCSV = useCallback(() => {
    const hdr = cols.join(',');
    const csv = [hdr, ...filtered.map(r => cols.map(c => {
      const v = r[c];
      if (v == null) return '';
      const s = String(v);
      return s.includes(',') || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s;
    }).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `${title.replace(/\s+/g, '_')}.csv`; a.click();
    URL.revokeObjectURL(url);
  }, [cols, filtered, title]);

  // Reset page cuando cambia search
  const handleSearch = (val: string) => {
    setSearch(val);
    setPage(1);
  };

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Header con búsqueda */}
      <div className="flex-shrink-0 px-2 py-1.5 border-b border-slate-200 flex items-center justify-between bg-slate-50">
        <div className="text-[11px]">
          <span className="text-slate-400">{filtered.length}/{total}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400" />
            <input
              type="text"
              placeholder="Buscar..."
              value={search}
              onChange={e => handleSearch(e.target.value)}
              className="pl-6 pr-2 py-1 bg-white border border-slate-200 rounded text-[11px] w-28 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <button onClick={exportCSV} className="p-1 hover:bg-slate-100 rounded" title="Exportar CSV">
            <Download className="w-3.5 h-3.5 text-slate-500" />
          </button>
        </div>
      </div>

      {/* Tabla */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-[11px]">
          <thead className="bg-slate-50 sticky top-0 text-[9px] text-slate-500 uppercase">
            <tr>
              {cols.map(c => (
                <th key={c} onClick={() => sort(c)} className="px-1.5 py-1 text-left cursor-pointer hover:bg-slate-100 whitespace-nowrap">
                  <span className="flex items-center gap-0.5">
                    {getLabel(c)}
                    {sortCol === c && <ArrowUpDown className={`w-2 h-2 ${sortDir === 'asc' ? 'rotate-180' : ''}`} />}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {pageRows.map((row, i) => (
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
        {pageRows.length === 0 && <div className="py-6 text-center text-[11px] text-slate-400">Sin resultados</div>}
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex-shrink-0 px-2 py-1 border-t border-slate-200 flex items-center justify-between text-[10px] text-slate-500 bg-slate-50">
          <span>{(page-1)*PER_PAGE+1}-{Math.min(page*PER_PAGE, filtered.length)} / {filtered.length}</span>
          <div className="flex items-center gap-1">
            <button onClick={() => setPage(p => Math.max(1, p-1))} disabled={page === 1} className="p-0.5 rounded hover:bg-slate-100 disabled:opacity-30">
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="px-1">{page}/{pages}</span>
            <button onClick={() => setPage(p => Math.min(pages, p+1))} disabled={page === pages} className="p-0.5 rounded hover:bg-slate-100 disabled:opacity-30">
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
});

// Hook para abrir la tabla como ventana flotante
export function useOpenDataTable() {
  const { openWindow } = useFloatingWindow();

  return useCallback((props: DataTableContentProps) => {
    const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
    const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;

    openWindow({
      title: props.title,
      content: <DataTableContent {...props} />,
      width: 900,
      height: 600,
      x: Math.max(50, screenWidth / 2 - 450),
      y: Math.max(80, screenHeight / 2 - 300),
      minWidth: 500,
      minHeight: 300,
    });
  }, [openWindow]);
}

// Legacy export para compatibilidad - ya no hace nada
export const DataTableModal = memo(function DataTableModal() {
  return null;
});

export default DataTableContent;
