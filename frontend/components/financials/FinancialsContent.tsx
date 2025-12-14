'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { RefreshCw, AlertTriangle, Copy, Check } from 'lucide-react';
import { TickerSearch } from '@/components/common/TickerSearch';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { SymbioticTable } from './tables/SymbioticTable';
import { SegmentsTable } from './tables/SegmentsTable';
import { FinancialMetricChart, type MetricDataPoint } from './FinancialMetricChart';
import { type FinancialChartData } from '@/lib/window-injector';

// ============================================================================
// Types - Nuevo formato simbiótico
// ============================================================================

interface ConsolidatedField {
    key: string;
    label: string;
    values: (number | null)[];
    importance: number;
    source_fields?: string[];
    data_type?: string;
    balance?: 'debit' | 'credit' | null;  // debit = outflow (rojo), credit = inflow
}

interface SymbioticFinancialData {
    symbol: string;
    currency: string;
    industry?: string;
    sector?: string;
    source: string;
    symbiotic: boolean;
    periods: string[];
    income_statement: ConsolidatedField[];
    balance_sheet: ConsolidatedField[];
    cash_flow: ConsolidatedField[];
    last_updated: string;
    cached?: boolean;
    cache_age_seconds?: number;
}

type TabType = 'income' | 'balance' | 'cashflow' | 'segments';
type PeriodFilter = 'annual' | 'quarterly';

// ============================================================================
// Period Range Slider
// ============================================================================

interface PeriodRangeSliderProps {
    periods: string[];
    startIndex: number;
    endIndex: number;
    onChange: (start: number, end: number) => void;
}

function PeriodRangeSlider({ periods, startIndex, endIndex, onChange }: PeriodRangeSliderProps) {
    const trackRef = useRef<HTMLDivElement>(null);
    const [dragging, setDragging] = useState<'start' | 'end' | 'range' | null>(null);
    const [dragStartX, setDragStartX] = useState(0);
    const [dragStartIndices, setDragStartIndices] = useState({ start: 0, end: 0 });

    const handleMouseDown = useCallback((e: React.MouseEvent, type: 'start' | 'end' | 'range') => {
        e.preventDefault();
        setDragging(type);
        setDragStartX(e.clientX);
        setDragStartIndices({ start: startIndex, end: endIndex });
    }, [startIndex, endIndex]);

    useEffect(() => {
        if (!dragging) return;

        const handleMouseMove = (e: MouseEvent) => {
            if (!trackRef.current) return;
            const rect = trackRef.current.getBoundingClientRect();
            const deltaX = e.clientX - dragStartX;
            const deltaPercent = deltaX / rect.width;
            const deltaIndex = Math.round(deltaPercent * (periods.length - 1));

            if (dragging === 'start') {
                const newStart = Math.max(0, Math.min(endIndex - 1, dragStartIndices.start + deltaIndex));
                onChange(newStart, endIndex);
            } else if (dragging === 'end') {
                const newEnd = Math.max(startIndex + 1, Math.min(periods.length - 1, dragStartIndices.end + deltaIndex));
                onChange(startIndex, newEnd);
            } else if (dragging === 'range') {
                const rangeSize = dragStartIndices.end - dragStartIndices.start;
                let newStart = dragStartIndices.start + deltaIndex;
                let newEnd = dragStartIndices.end + deltaIndex;
                if (newStart < 0) { newStart = 0; newEnd = rangeSize; }
                if (newEnd > periods.length - 1) { newEnd = periods.length - 1; newStart = newEnd - rangeSize; }
                onChange(newStart, newEnd);
            }
        };

        const handleMouseUp = () => setDragging(null);

        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
        return () => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
        };
    }, [dragging, dragStartX, dragStartIndices, startIndex, endIndex, periods.length, onChange]);

    if (periods.length <= 2) return null;

    const startPercent = periods.length > 1 ? (startIndex / (periods.length - 1)) * 100 : 0;
    const endPercent = periods.length > 1 ? (endIndex / (periods.length - 1)) * 100 : 100;

    return (
        <div className="px-3 py-2 bg-slate-50 border-b border-slate-100">
            <div className="relative h-3 mb-1">
                {periods.map((period, idx) => (
                    <span
                        key={idx}
                        className="absolute text-[9px] text-slate-500 font-medium transform -translate-x-1/2"
                        style={{ left: `${(idx / (periods.length - 1)) * 100}%` }}
                    >
                        '{period.slice(-2)}
                    </span>
                ))}
            </div>
            <div
                ref={trackRef}
                className="relative h-1.5 bg-slate-200 rounded-full cursor-pointer"
            >
                {periods.map((_, idx) => (
                    <div
                        key={idx}
                        className={`absolute top-1/2 w-1.5 h-1.5 rounded-full transform -translate-x-1/2 -translate-y-1/2
                            ${idx >= startIndex && idx <= endIndex ? 'bg-blue-500' : 'bg-slate-300'}`}
                        style={{ left: `${(idx / (periods.length - 1)) * 100}%` }}
                    />
                ))}
                <div
                    className="absolute h-full bg-blue-500 rounded-full cursor-grab"
                    style={{ left: `${startPercent}%`, width: `${endPercent - startPercent}%` }}
                    onMouseDown={(e) => handleMouseDown(e, 'range')}
                />
                <div
                    className="absolute top-1/2 w-3 h-3 bg-blue-600 border-2 border-white rounded-full shadow-md transform -translate-x-1/2 -translate-y-1/2 cursor-ew-resize z-10"
                    style={{ left: `${startPercent}%` }}
                    onMouseDown={(e) => handleMouseDown(e, 'start')}
                />
                <div
                    className="absolute top-1/2 w-3 h-3 bg-blue-600 border-2 border-white rounded-full shadow-md transform -translate-x-1/2 -translate-y-1/2 cursor-ew-resize z-10"
                    style={{ left: `${endPercent}%` }}
                    onMouseDown={(e) => handleMouseDown(e, 'end')}
                />
            </div>
            <div className="flex items-center justify-between mt-1 text-[9px] text-slate-500">
                <span className="font-medium text-blue-600">{periods[startIndex]?.startsWith('Q') ? periods[startIndex] : `FY${periods[startIndex]}`}</span>
                <span>{endIndex - startIndex + 1} of {periods.length} periods</span>
                <span className="font-medium text-blue-600">{periods[endIndex]?.startsWith('Q') ? periods[endIndex] : `FY${periods[endIndex]}`}</span>
            </div>
        </div>
    );
}

// ============================================================================
// API
// ============================================================================

const API_URL = process.env.NEXT_PUBLIC_API_GATEWAY_URL || 'http://localhost:8000';

// ============================================================================
// MAIN COMPONENT
// ============================================================================

interface FinancialsContentProps {
    initialTicker?: string;
}

export function FinancialsContent({ initialTicker }: FinancialsContentProps) {
    const [data, setData] = useState<SymbioticFinancialData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [selectedTicker, setSelectedTicker] = useState<string>(initialTicker || '');
    const [inputValue, setInputValue] = useState(initialTicker || '');
    const [activeTab, setActiveTab] = useState<TabType>('income');
    const [periodFilter, setPeriodFilter] = useState<PeriodFilter>('annual');
    const [copied, setCopied] = useState(false);
    const [rangeStart, setRangeStart] = useState(0);
    const [rangeEnd, setRangeEnd] = useState(0);

    const { openWindow } = useFloatingWindow();

    // Fetch data
    const fetchData = useCallback(async (ticker: string, period?: PeriodFilter) => {
        if (!ticker) return;
        setLoading(true);
        setError(null);

        try {
            const effectivePeriod = period ?? periodFilter;
            const url = `${API_URL}/api/v1/financials/${ticker}?period=${effectivePeriod}&limit=12`;
            console.log('[DEBUG] Fetching:', url);
            const response = await fetch(url);

            if (!response.ok) {
                throw new Error(`Failed to fetch: ${response.statusText}`);
            }

            const result = await response.json();
            setData(result);
            setSelectedTicker(ticker);

            // Reset range to show all periods
            if (result.periods?.length > 0) {
                setRangeStart(0);
                setRangeEnd(result.periods.length - 1);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unknown error');
            setData(null);
        } finally {
            setLoading(false);
        }
    }, [periodFilter]);

    // Load initial ticker
    useEffect(() => {
        if (initialTicker) {
            fetchData(initialTicker);
        }
    }, [initialTicker]);

    // Handle period change
    const handlePeriodChange = useCallback((newPeriod: PeriodFilter) => {
        console.log('[DEBUG] handlePeriodChange:', newPeriod);
        setPeriodFilter(newPeriod);
        if (selectedTicker) {
            fetchData(selectedTicker, newPeriod);
        }
    }, [selectedTicker, fetchData]);

    // Copy JSON
    const handleCopyJson = useCallback(() => {
        if (!data) return;
        navigator.clipboard.writeText(JSON.stringify(data, null, 2));
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }, [data]);

    // Handle range change
    const handleRangeChange = useCallback((start: number, end: number) => {
        setRangeStart(start);
        setRangeEnd(end);
    }, []);

    // Get filtered data for selected range
    const filteredData = useCallback(() => {
        if (!data || !data.periods) return { income: [], balance: [], cashflow: [], periods: [] };

        const periods = data.periods || [];
        const slicedPeriods = periods.slice(rangeStart, rangeEnd + 1);

        const sliceValues = (fields: ConsolidatedField[] | undefined) => {
            if (!fields || !Array.isArray(fields)) return [];
            return fields.map(f => ({
                ...f,
                values: (f.values || []).slice(rangeStart, rangeEnd + 1)
            }));
        };

        return {
            income: sliceValues(data.income_statement),
            balance: sliceValues(data.balance_sheet),
            cashflow: sliceValues(data.cash_flow || []),
            periods: slicedPeriods
        };
    }, [data, rangeStart, rangeEnd]);

    // Handle metric click - open chart
    const handleMetricClick = useCallback((metricKey: string, values: (number | null)[], periods: string[]) => {
        if (!data) return;

        const chartDataPoints: MetricDataPoint[] = periods.map((period, idx) => ({
            period: period.startsWith('Q') ? period : `FY${period}`,
            fiscalYear: period,
            value: values[idx],
            isAnnual: !period.startsWith('Q'),
        })).reverse();

        const metricLabel = metricKey.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        const windowTitle = `${data.symbol} — ${metricLabel}`;

        openWindow({
            title: windowTitle,
            content: (
                <div className="h-full flex flex-col">
                    <FinancialMetricChart
                        data={chartDataPoints}
                        metricKey={metricKey}
                        metricLabel={metricLabel}
                        ticker={data.symbol}
                        currency={data.currency}
                    />
                </div>
            ),
            width: 900,
            height: 550,
            x: Math.max(100, (window.innerWidth - 900) / 2),
            y: Math.max(50, (window.innerHeight - 550) / 2),
        });
    }, [data, openWindow]);

    const filtered = filteredData();

    // Loading state
    if (loading && !data) {
        return (
            <div className="flex flex-col h-full">
                <div className="flex items-center gap-2 p-2 border-b border-slate-200 bg-slate-50">
                    <TickerSearch
                        value={inputValue}
                        onChange={setInputValue}
                        onSelect={(ticker) => {
                            setInputValue(ticker.symbol);
                            fetchData(ticker.symbol, periodFilter);
                        }}
                        placeholder="Search ticker..."
                        className="flex-1 text-xs"
                    />
                </div>
                <div className="flex items-center justify-center h-64">
                    <RefreshCw className="h-6 w-6 animate-spin text-slate-400" />
                </div>
            </div>
        );
    }

    // Error state
    if (error && !data) {
        return (
            <div className="flex flex-col h-full">
                <div className="flex items-center gap-2 p-2 border-b border-slate-200 bg-slate-50">
                    <TickerSearch
                        value={inputValue}
                        onChange={setInputValue}
                        onSelect={(ticker) => {
                            setInputValue(ticker.symbol);
                            fetchData(ticker.symbol, periodFilter);
                        }}
                        placeholder="Search ticker..."
                        className="flex-1 text-xs"
                    />
                </div>
                <div className="flex items-center justify-center h-64 text-red-500">
                    <AlertTriangle className="h-5 w-5 mr-2" />
                    <span className="text-xs">{error}</span>
                </div>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="flex items-center gap-2 p-2 border-b border-slate-200 bg-slate-50">
                <TickerSearch
                    value={inputValue}
                    onChange={setInputValue}
                    onSelect={(ticker) => {
                        setInputValue(ticker.symbol);
                        fetchData(ticker.symbol, periodFilter);
                    }}
                    placeholder="Search ticker..."
                    className="flex-1 text-xs"
                />
                {selectedTicker && (
                    <button
                        onClick={() => fetchData(selectedTicker)}
                        disabled={loading}
                        className="p-1.5 text-slate-400 hover:text-slate-600 disabled:opacity-50"
                    >
                        <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                )}
            </div>

            {!data ? (
                <div className="flex items-center justify-center h-64 text-slate-400 text-xs">
                    Search for a ticker to view financials
                </div>
            ) : (
                <div className="flex-1 overflow-auto">
                    {/* Info & Controls */}
                    <div className="flex items-center justify-between p-2 border-b border-slate-100">
                        <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-slate-800">{data.symbol}</span>
                            {data.industry && (
                                <span className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-slate-100 text-slate-700">
                                    {data.industry}
                                </span>
                            )}
                            {data.sector && (
                                <span className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-blue-50 text-blue-700">
                                    {data.sector}
                                </span>
                            )}
                        </div>
                        <div className="flex items-center gap-1">
                            {(['annual', 'quarterly'] as const).map((p) => (
                                <button
                                    key={p}
                                    onClick={() => handlePeriodChange(p)}
                                    className={`px-1.5 py-0.5 text-[9px] font-medium rounded
                                        ${periodFilter === p ? 'bg-slate-700 text-white' : 'text-slate-500 hover:bg-slate-100'}`}
                                >
                                    {p === 'annual' ? 'Annual' : 'Quarterly'}
                                </button>
                            ))}
                            <button
                                onClick={handleCopyJson}
                                className={`px-1.5 py-0.5 text-[9px] rounded flex items-center gap-0.5
                                    ${copied ? 'bg-green-500 text-white' : 'text-slate-400 hover:bg-slate-100'}`}
                            >
                                {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                            </button>
                        </div>
                    </div>

                    {/* Tabs */}
                    <div className="flex border-b border-slate-100">
                        {[
                            { id: 'income' as const, label: 'Income Statement' },
                            { id: 'balance' as const, label: 'Balance Sheet' },
                            { id: 'cashflow' as const, label: 'Cash Flow' },
                            { id: 'segments' as const, label: 'Segments' },
                        ].map((tab) => (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`flex-1 py-1.5 text-[10px] font-medium
                                    ${activeTab === tab.id ? 'text-slate-800 border-b-2 border-slate-800' : 'text-slate-400 hover:text-slate-600'}`}
                            >
                                {tab.label}
                            </button>
                        ))}
                    </div>

                    {/* Period Slider */}
                    {data.periods && data.periods.length > 2 && (
                        <PeriodRangeSlider
                            periods={data.periods}
                            startIndex={rangeStart}
                            endIndex={rangeEnd}
                            onChange={handleRangeChange}
                        />
                    )}

                    {/* Tables */}
                    <div className="overflow-x-auto relative">
                        {loading && (
                            <div className="absolute inset-0 bg-white/70 flex items-center justify-center z-10">
                                <RefreshCw className="h-5 w-5 animate-spin text-slate-400" />
                            </div>
                        )}
                        {activeTab === 'income' && (
                            <SymbioticTable
                                fields={filtered.income}
                                periods={filtered.periods}
                                category="income"
                                currency={data.currency}
                                onMetricClick={handleMetricClick}
                            />
                        )}
                        {activeTab === 'balance' && (
                            <SymbioticTable
                                fields={filtered.balance}
                                periods={filtered.periods}
                                category="balance"
                                currency={data.currency}
                                onMetricClick={handleMetricClick}
                            />
                        )}
                        {activeTab === 'cashflow' && (
                            <SymbioticTable
                                fields={filtered.cashflow}
                                periods={filtered.periods}
                                category="cashflow"
                                currency={data.currency}
                                onMetricClick={handleMetricClick}
                            />
                        )}
                        {activeTab === 'segments' && data?.symbol && (
                            <SegmentsTable symbol={data.symbol} />
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

export default FinancialsContent;
