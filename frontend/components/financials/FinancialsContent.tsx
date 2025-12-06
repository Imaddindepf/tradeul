'use client';

import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { RefreshCw, AlertTriangle, Copy, Check } from 'lucide-react';
import { TickerSearch } from '@/components/common/TickerSearch';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';

// Local imports - modular structure
import type { FinancialData, TabType, PeriodFilter, FinancialPeriod } from './types';
import { INDUSTRY_PROFILES } from './constants/profiles';
import { mapFMPIndustryToCategory } from './constants/industryCategories';
import { IncomeStatementTable, BalanceSheetTable, CashFlowTable } from './tables';
import { KPISection } from './components/KPISection';
import { FinancialMetricChart, type MetricDataPoint } from './FinancialMetricChart';
import { openFinancialChartWindow, type FinancialChartData } from '@/lib/window-injector';

// ============================================================================
// Period Range Slider Component
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

    const getIndexFromPosition = useCallback((clientX: number): number => {
        if (!trackRef.current) return 0;
        const rect = trackRef.current.getBoundingClientRect();
        const x = clientX - rect.left;
        const percent = Math.max(0, Math.min(1, x / rect.width));
        return Math.round(percent * (periods.length - 1));
    }, [periods.length]);

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

                if (newStart < 0) {
                    newStart = 0;
                    newEnd = rangeSize;
                }
                if (newEnd > periods.length - 1) {
                    newEnd = periods.length - 1;
                    newStart = newEnd - rangeSize;
                }
                onChange(newStart, newEnd);
            }
        };

        const handleMouseUp = () => {
            setDragging(null);
        };

        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);

        return () => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
        };
    }, [dragging, dragStartX, dragStartIndices, startIndex, endIndex, periods.length, onChange]);

    // Extract unique years for display
    const yearMarkers = useMemo(() => {
        const years: { year: string; index: number }[] = [];
        let lastYear = '';

        periods.forEach((period, idx) => {
            const yearMatch = period.match(/\d{4}/);
            const year = yearMatch ? yearMatch[0] : '';
            if (year && year !== lastYear) {
                years.push({ year: `'${year.slice(-2)}`, index: idx });
                lastYear = year;
            }
        });
        return years;
    }, [periods]);

    const startPercent = periods.length > 1 ? (startIndex / (periods.length - 1)) * 100 : 0;
    const endPercent = periods.length > 1 ? (endIndex / (periods.length - 1)) * 100 : 100;

    if (periods.length <= 2) return null;

    return (
        <div className="px-3 py-2 bg-slate-50 border-b border-slate-100">
            {/* Year labels */}
            <div className="relative h-3 mb-1">
                {yearMarkers.map(({ year, index }) => (
                    <span
                        key={`${year}-${index}`}
                        className="absolute text-[9px] text-slate-500 font-medium transform -translate-x-1/2"
                        style={{ left: `${(index / (periods.length - 1)) * 100}%` }}
                    >
                        {year}
                    </span>
                ))}
            </div>

            {/* Slider Track */}
            <div
                ref={trackRef}
                className="relative h-1.5 bg-slate-200 rounded-full cursor-pointer"
                onClick={(e) => {
                    const index = getIndexFromPosition(e.clientX);
                    const distToStart = Math.abs(index - startIndex);
                    const distToEnd = Math.abs(index - endIndex);
                    if (distToStart < distToEnd) {
                        onChange(Math.min(index, endIndex - 1), endIndex);
                    } else {
                        onChange(startIndex, Math.max(index, startIndex + 1));
                    }
                }}
            >
                {/* Period dots on track */}
                {periods.map((_, idx) => (
                    <div
                        key={idx}
                        className={`absolute top-1/2 w-1.5 h-1.5 rounded-full transform -translate-x-1/2 -translate-y-1/2 transition-colors
                            ${idx >= startIndex && idx <= endIndex ? 'bg-blue-500' : 'bg-slate-300'}`}
                        style={{ left: `${(idx / (periods.length - 1)) * 100}%` }}
                    />
                ))}

                {/* Selected Range */}
                <div
                    className="absolute h-full bg-blue-500 rounded-full cursor-grab active:cursor-grabbing"
                    style={{
                        left: `${startPercent}%`,
                        width: `${endPercent - startPercent}%`,
                    }}
                    onMouseDown={(e) => handleMouseDown(e, 'range')}
                />

                {/* Start Handle */}
                <div
                    className={`absolute top-1/2 w-3 h-3 bg-blue-600 border-2 border-white rounded-full shadow-md 
                        transform -translate-x-1/2 -translate-y-1/2 cursor-ew-resize z-10 hover:scale-110 transition-transform
                        ${dragging === 'start' ? 'scale-110 ring-2 ring-blue-300' : ''}`}
                    style={{ left: `${startPercent}%` }}
                    onMouseDown={(e) => handleMouseDown(e, 'start')}
                />

                {/* End Handle */}
                <div
                    className={`absolute top-1/2 w-3 h-3 bg-blue-600 border-2 border-white rounded-full shadow-md 
                        transform -translate-x-1/2 -translate-y-1/2 cursor-ew-resize z-10 hover:scale-110 transition-transform
                        ${dragging === 'end' ? 'scale-110 ring-2 ring-blue-300' : ''}`}
                    style={{ left: `${endPercent}%` }}
                    onMouseDown={(e) => handleMouseDown(e, 'end')}
                />
            </div>

            {/* Range Info */}
            <div className="flex items-center justify-between mt-1 text-[9px] text-slate-500">
                <span className="font-medium text-blue-600">{periods[startIndex]}</span>
                <span className="text-slate-400">
                    {endIndex - startIndex + 1} of {periods.length} periods
                </span>
                <span className="font-medium text-blue-600">{periods[endIndex]}</span>
            </div>
        </div>
    );
}

// ============================================================================
// API URL
// ============================================================================

const API_URL = process.env.NEXT_PUBLIC_API_GATEWAY_URL || 'http://localhost:8000';

// ============================================================================
// MAIN COMPONENT
// ============================================================================

interface FinancialsContentProps {
    initialTicker?: string;
}

export function FinancialsContent({ initialTicker }: FinancialsContentProps) {
    const [data, setData] = useState<FinancialData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [selectedTicker, setSelectedTicker] = useState<string>(initialTicker || '');
    const [inputValue, setInputValue] = useState(initialTicker || '');
    const [activeTab, setActiveTab] = useState<TabType>('income');
    const [periodFilter, setPeriodFilter] = useState<PeriodFilter>('quarter');
    const [copied, setCopied] = useState(false);
    const [rangeStart, setRangeStart] = useState(0);
    const [rangeEnd, setRangeEnd] = useState(0);

    const { openWindow } = useFloatingWindow();

    // Fetch data from API Gateway
    const fetchData = useCallback(async (ticker: string, period?: PeriodFilter) => {
        if (!ticker) return;

        setLoading(true);
        setError(null);

        try {
            const effectivePeriod = period ?? periodFilter;
            const response = await fetch(`${API_URL}/api/v1/financials/${ticker}?period=${effectivePeriod}&limit=10`);

            if (!response.ok) {
                throw new Error(`Failed to fetch financial data: ${response.statusText}`);
            }

            const result = await response.json();
            setData(result);
            setSelectedTicker(ticker);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unknown error');
            setData(null);
        } finally {
            setLoading(false);
        }
    }, [periodFilter]);

    // Load initial ticker data
    useEffect(() => {
        if (initialTicker) {
            fetchData(initialTicker);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [initialTicker]);

    // Handle period filter change
    const handlePeriodChange = useCallback((newPeriod: PeriodFilter) => {
        setPeriodFilter(newPeriod);
        if (selectedTicker) {
            fetchData(selectedTicker, newPeriod);
        }
    }, [selectedTicker, fetchData]);

    // Copy JSON functionality
    const handleCopyJson = useCallback(() => {
        if (!data) return;
        navigator.clipboard.writeText(JSON.stringify(data, null, 2));
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }, [data]);

    // Get industry profile
    const industryProfile = useMemo(() => {
        if (!data) return INDUSTRY_PROFILES.general;
        const category = mapFMPIndustryToCategory(data.industry);
        return INDUSTRY_PROFILES[category];
    }, [data]);

    // Get all available periods (for slider)
    const availablePeriods = useMemo(() => {
        if (!data) return [];

        const filterByType = <T extends { period: FinancialPeriod }>(statements: T[]): T[] => {
            if (periodFilter === 'all') return statements;
            if (periodFilter === 'annual') return statements.filter(s => s.period.period === 'FY');
            return statements.filter(s => s.period.period !== 'FY');
        };

        const statements = filterByType(data.income_statements);
        return statements.map(s => {
            const p = s.period;
            return p.period === 'FY' ? `FY ${p.fiscal_year}` : `${p.period} ${p.fiscal_year}`;
        });
    }, [data, periodFilter]);

    // Reset range when periods change
    useEffect(() => {
        if (availablePeriods.length > 0) {
            setRangeStart(0);
            setRangeEnd(availablePeriods.length - 1);
        }
    }, [availablePeriods.length]);

    // Handle range change
    const handleRangeChange = useCallback((start: number, end: number) => {
        setRangeStart(start);
        setRangeEnd(end);
    }, []);

    // Filter statements by period type and then by range
    const filteredStatements = useMemo(() => {
        if (!data) return { income: [], balance: [], cashflow: [] };

        const filterByPeriod = <T extends { period: FinancialPeriod }>(statements: T[]): T[] => {
            if (periodFilter === 'all') return statements;
            if (periodFilter === 'annual') return statements.filter(s => s.period.period === 'FY');
            return statements.filter(s => s.period.period !== 'FY');
        };

        // First filter by period type
        const incomeFiltered = filterByPeriod(data.income_statements);
        const balanceFiltered = filterByPeriod(data.balance_sheets);
        const cashflowFiltered = filterByPeriod(data.cash_flows);

        // Then slice by range
        return {
            income: incomeFiltered.slice(rangeStart, rangeEnd + 1),
            balance: balanceFiltered.slice(rangeStart, rangeEnd + 1),
            cashflow: cashflowFiltered.slice(rangeStart, rangeEnd + 1),
        };
    }, [data, periodFilter, rangeStart, rangeEnd]);

    // Handle metric click - opens floating window with chart
    const handleMetricClick = useCallback((metricKey: string, values: (number | undefined)[], periods: string[]) => {
        if (!data) return;

        const chartDataPoints: MetricDataPoint[] = periods.map((period, idx) => {
            const isAnnual = period.startsWith('FY');
            const fiscalYear = period.match(/\d{4}/)?.[0] || '';
            return {
                period,
                fiscalYear,
                value: values[idx] ?? null,
                isAnnual,
            };
        }).reverse();

        const metricLabel = metricKey.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        // Format: "TICKER — MetricLabel" for compatibility with FloatingWindow pop-out
        const windowTitle = `${data.symbol} — ${metricLabel}`;

        // Prepare chart data for external window
        const chartConfig: FinancialChartData = {
            ticker: data.symbol,
            metricKey,
            metricLabel,
            currency: data.currency,
            valueType: 'currency',
            isNegativeBad: true,
            data: chartDataPoints,
        };

        // Open floating window with chart
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
            minWidth: 700,
            minHeight: 400,
            maxWidth: 1400,
            maxHeight: 900,
            x: Math.max(100, (window.innerWidth - 900) / 2),
            y: Math.max(50, (window.innerHeight - 550) / 2),
            hideHeader: false,
        });

        // Store chart data for pop-out window support
        if (typeof window !== 'undefined') {
            (window as any).__pendingChartData = chartConfig;
        }
    }, [data, openWindow]);

    const IconComponent = industryProfile.icon;

    // Render loading state (only when no data yet)
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

    // Render error state
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
            {/* Header with Search */}
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
                        title="Refresh"
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
                    {/* Industry Badge & Controls */}
                    <div className="flex items-center justify-between p-2 border-b border-slate-100">
                        <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-slate-800">{data.symbol}</span>
                            <div className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium bg-slate-100 text-slate-700">
                                <IconComponent className="w-3 h-3" />
                                <span>{data.industry || industryProfile.label}</span>
                            </div>
                            {data.sector && (
                                <div className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-blue-50 text-blue-700">
                                    {data.sector}
                                </div>
                            )}
                        </div>
                        <div className="flex items-center gap-1">
                            {/* Period Filter */}
                            {(['annual', 'quarter'] as const).map((p) => (
                                <button
                                    key={p}
                                    onClick={() => handlePeriodChange(p)}
                                    className={`px-1.5 py-0.5 text-[9px] font-medium rounded transition-colors
                                        ${periodFilter === p
                                            ? 'bg-slate-700 text-white'
                                            : 'text-slate-500 hover:bg-slate-100'}`}
                                >
                                    {p === 'annual' ? 'Annual' : 'Quarterly'}
                                </button>
                            ))}
                            {/* Copy JSON */}
                            <button
                                onClick={handleCopyJson}
                                className={`px-1.5 py-0.5 text-[9px] font-medium rounded transition-colors flex items-center gap-0.5
                                    ${copied ? 'bg-green-500 text-white' : 'text-slate-400 hover:bg-slate-100'}`}
                                title="Copy as JSON"
                            >
                                {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                            </button>
                        </div>
                    </div>

                    {/* KPIs Section */}
                    <KPISection industryProfile={industryProfile} data={data} />

                    {/* Tabs */}
                    <div className="flex border-b border-slate-100">
                        {[
                            { id: 'income' as const, label: 'Income Statement' },
                            { id: 'balance' as const, label: 'Balance Sheet' },
                            { id: 'cashflow' as const, label: 'Cash Flow' },
                        ].map((tab) => (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`flex-1 py-1.5 text-[10px] font-medium transition-colors
                                    ${activeTab === tab.id
                                        ? 'text-slate-800 border-b-2 border-slate-800'
                                        : 'text-slate-400 hover:text-slate-600'}`}
                            >
                                {tab.label}
                            </button>
                        ))}
                    </div>

                    {/* Period Range Slider */}
                    <PeriodRangeSlider
                        periods={availablePeriods}
                        startIndex={rangeStart}
                        endIndex={rangeEnd}
                        onChange={handleRangeChange}
                    />

                    {/* Financial Tables */}
                    <div className="overflow-x-auto relative">
                        {/* Loading overlay when refreshing data */}
                        {loading && (
                            <div className="absolute inset-0 bg-white/70 flex items-center justify-center z-10">
                                <RefreshCw className="h-5 w-5 animate-spin text-slate-400" />
                            </div>
                        )}
                        {activeTab === 'income' && (
                            <IncomeStatementTable
                                statements={filteredStatements.income}
                                currency={data.currency}
                                onMetricClick={handleMetricClick}
                            />
                        )}
                        {activeTab === 'balance' && (
                            <BalanceSheetTable
                                statements={filteredStatements.balance}
                                currency={data.currency}
                                onMetricClick={handleMetricClick}
                            />
                        )}
                        {activeTab === 'cashflow' && (
                            <CashFlowTable
                                statements={filteredStatements.cashflow}
                                currency={data.currency}
                                onMetricClick={handleMetricClick}
                            />
                        )}
                    </div>

                </div>
            )}
        </div>
    );
}

export default FinancialsContent;
