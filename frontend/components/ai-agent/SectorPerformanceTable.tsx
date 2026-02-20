'use client';

import { memo, useState, useMemo, useCallback } from 'react';
import { ChevronDown, ChevronRight, ExternalLink } from 'lucide-react';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { ChartContent } from '@/components/chart/ChartContent';

interface SectorRow {
    sector: string;
    ticker_count: number;
    tickers: string;
    avg_change: number;
    median_change: number;
    min_change: number;
    max_change: number;
    total_volume: number;
    [key: string]: unknown;
}

interface SectorPerformanceTableProps {
    rows: SectorRow[];
    title?: string;
    total?: number;
}

const formatVolume = (num: number): string => {
    if (num >= 1e9) return `${(num / 1e9).toFixed(1)}B`;
    if (num >= 1e6) return `${(num / 1e6).toFixed(1)}M`;
    if (num >= 1e3) return `${(num / 1e3).toFixed(0)}K`;
    return num.toLocaleString();
};

const formatPct = (num: number): string => `${num > 0 ? '+' : ''}${num.toFixed(2)}%`;

// Ticker chip clickeable
const TickerChip = memo(function TickerChip({
    ticker,
    onOpenChart
}: {
    ticker: string;
    onOpenChart: (t: string) => void;
}) {
    return (
        <button
            onClick={(e) => {
                e.stopPropagation();
                onOpenChart(ticker);
            }}
            className="px-0.5 py-px bg-slate-100 hover:bg-blue-100 text-slate-700 hover:text-blue-700 rounded text-[9px] font-[family-name:var(--font-mono-selected)] transition-colors cursor-pointer"
            title={`Abrir gráfico de ${ticker}`}
        >
            {ticker}
        </button>
    );
});

const SectorRowComponent = memo(function SectorRowComponent({
    row,
    isExpanded,
    onToggle,
    onOpenChart
}: {
    row: SectorRow;
    isExpanded: boolean;
    onToggle: () => void;
    onOpenChart: (ticker: string) => void;
}) {
    const tickers = row.tickers.split(',').map(t => t.trim()).filter(Boolean);
    const avg = Number(row.avg_change) || 0;
    const avgColor = avg > 0 ? 'text-[var(--color-tick-up)]' : avg < 0 ? 'text-[var(--color-tick-down)]' : 'text-slate-400';

    return (
        <>
            <tr
                onClick={onToggle}
                className="hover:bg-slate-50 cursor-pointer border-b border-slate-100 text-[10px]"
            >
                <td className="px-1.5 py-1 w-5">
                    {isExpanded ? <ChevronDown className="w-3 h-3 text-slate-400" /> : <ChevronRight className="w-3 h-3 text-slate-300" />}
                </td>
                <td className="px-1.5 py-1 font-medium text-slate-800 max-w-[120px] truncate">{row.sector}</td>
                <td className="px-1.5 py-1 text-slate-500 text-center font-[family-name:var(--font-mono-selected)]">{row.ticker_count}</td>
                <td className={`px-1.5 py-1 font-[family-name:var(--font-mono-selected)] ${avgColor}`}>{formatPct(avg)}</td>
                <td className="px-1.5 py-1 font-[family-name:var(--font-mono-selected)] text-slate-500">{formatPct(Number(row.median_change) || 0)}</td>
                <td className="px-1.5 py-1 font-[family-name:var(--font-mono-selected)] text-slate-400 text-[9px]">{formatPct(Number(row.min_change) || 0)}</td>
                <td className="px-1.5 py-1 font-[family-name:var(--font-mono-selected)] text-slate-400 text-[9px]">{formatPct(Number(row.max_change) || 0)}</td>
                <td className="px-1.5 py-1 font-[family-name:var(--font-mono-selected)] text-slate-600">{formatVolume(Number(row.total_volume) || 0)}</td>
            </tr>
            {isExpanded && (
                <tr className="bg-slate-50/50">
                    <td colSpan={8} className="px-2 py-1.5">
                        <div className="flex flex-wrap gap-0.5">
                            {tickers.map((t) => (
                                <TickerChip key={t} ticker={t} onOpenChart={onOpenChart} />
                            ))}
                        </div>
                    </td>
                </tr>
            )}
        </>
    );
});

export const SectorPerformanceTable = memo(function SectorPerformanceTable({
    rows,
    title,
    total
}: SectorPerformanceTableProps) {
    const [expanded, setExpanded] = useState<Set<string>>(new Set());
    const { openWindow } = useFloatingWindow();

    const sorted = useMemo(() =>
        [...rows].sort((a, b) => (Number(b.avg_change) || 0) - (Number(a.avg_change) || 0)),
        [rows]);

    const toggle = (s: string) => setExpanded(prev => {
        const next = new Set(prev);
        next.has(s) ? next.delete(s) : next.add(s);
        return next;
    });

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

    return (
        <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
            {title && (
                <div className="px-2 py-1 bg-slate-50 border-b border-slate-200 flex justify-between text-[10px]">
                    <span className="font-medium text-slate-700">{title}</span>
                    <span className="text-slate-400">{total ?? rows.length}</span>
                </div>
            )}
            <div className="overflow-x-auto max-h-[35vh] overflow-y-auto">
                <table className="w-full">
                    <thead className="bg-slate-50 sticky top-0 text-[8px] text-slate-500 uppercase">
                        <tr>
                            <th className="px-1.5 py-1 w-5"></th>
                            <th className="px-1.5 py-1 text-left">Sector</th>
                            <th className="px-1.5 py-1 text-center">#</th>
                            <th className="px-1.5 py-1 text-left">Avg</th>
                            <th className="px-1.5 py-1 text-left">Med</th>
                            <th className="px-1.5 py-1 text-left">Min</th>
                            <th className="px-1.5 py-1 text-left">Max</th>
                            <th className="px-1.5 py-1 text-left">Vol</th>
                        </tr>
                    </thead>
                    <tbody>
                        {sorted.map((row) => (
                            <SectorRowComponent
                                key={row.sector}
                                row={row}
                                isExpanded={expanded.has(row.sector)}
                                onToggle={() => toggle(row.sector)}
                                onOpenChart={handleOpenChart}
                            />
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
});

export default SectorPerformanceTable;
