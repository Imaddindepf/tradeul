'use client';

import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import {
    Search,
    Loader2,
    AlertCircle,
    X,
    Plus,
    Download,
    LineChart,
    BarChart3,
    CandlestickChart,
    Activity,
    TrendingUp,
} from 'lucide-react';
import { TickerSearch } from '@/components/common/TickerSearch';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { useWindowState } from '@/contexts/FloatingWindowContext';
import { getUserTimezone } from '@/lib/date-utils';

// Estado persistido de la ventana MP
type MPWindowState = {
    tickerSymbols?: string[];
    period?: Period;
    chartType?: ChartType;
    scaleType?: ScaleType;
    [key: string]: unknown;
};

// ============================================================================
// Types
// ============================================================================

interface OHLCBar {
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
}

interface TickerData {
    symbol: string;
    color: string;
    data: OHLCBar[];
    latestPrice: number;
    changePercent: number;
}

interface TooltipData {
    date: string;
    values: { symbol: string; color: string; value: number; open?: number; high?: number; low?: number; close?: number }[];
    x: number;
    y: number;
}

type Period = '1M' | '3M' | '6M' | '1Y' | '5Y' | 'ALL';
type ChartType = 'line' | 'area' | 'candlestick' | 'ohlc' | 'mountain';
type ScaleType = 'percent' | 'price';

type TickerSearchResult = {
    symbol: string;
    name: string;
    exchange: string;
    type: string;
    displayName: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Color palette - colores distintivos
const TICKER_COLORS = [
    '#f43f5e', // rose-500
    '#06b6d4', // cyan-500
    '#10b981', // emerald-500
    '#f59e0b', // amber-500
    '#8b5cf6', // violet-500
    '#ec4899', // pink-500
    '#14b8a6', // teal-500
    '#6366f1', // indigo-500
    '#84cc16', // lime-500
    '#f97316', // orange-500
];

const PERIODS: { id: Period; label: string; days: number }[] = [
    { id: '1M', label: '1M', days: 30 },
    { id: '3M', label: '3M', days: 90 },
    { id: '6M', label: '6M', days: 180 },
    { id: '1Y', label: '1Y', days: 365 },
    { id: '5Y', label: '5Y', days: 1825 },
    { id: 'ALL', label: 'All', days: 3650 },
];

const CHART_TYPES: { id: ChartType; icon: any; label: string }[] = [
    { id: 'line', icon: LineChart, label: 'Line' },
    { id: 'area', icon: BarChart3, label: 'Area' },
    { id: 'mountain', icon: Activity, label: 'Mountain' },
    { id: 'candlestick', icon: CandlestickChart, label: 'Candlestick' },
    { id: 'ohlc', icon: TrendingUp, label: 'OHLC' },
];

// ============================================================================
// SVG Chart Component
// ============================================================================

interface SVGChartProps {
    tickers: TickerData[];
    width: number;
    height: number;
    chartType: ChartType;
    scaleType: ScaleType;
    onTooltip: (tooltip: TooltipData | null) => void;
}

function SVGChart({ tickers, width, height, chartType, scaleType, onTooltip }: SVGChartProps) {
    const svgRef = useRef<SVGSVGElement>(null);
    
    const padding = { top: 20, right: 55, bottom: 30, left: 10 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    // Alinear datos por fecha
    const { alignedData, dateRange, valueRange } = useMemo(() => {
        if (tickers.length === 0 || tickers.every(t => t.data.length === 0)) {
            return { alignedData: [], dateRange: { min: new Date(), max: new Date() }, valueRange: { min: 0, max: 0 } };
        }

        const allDates = new Set<string>();
        tickers.forEach(t => t.data.forEach(d => allDates.add(d.date)));
        const sortedDates = Array.from(allDates).sort();

        const tickerMaps = tickers.map(t => {
            const map = new Map<string, OHLCBar>();
            t.data.forEach(d => map.set(d.date, d));
            return map;
        });

        const firstValues = tickers.map((t, i) => {
            for (const date of sortedDates) {
                const bar = tickerMaps[i].get(date);
                if (bar !== undefined) return bar.close;
            }
            return 1;
        });

        const aligned = sortedDates.map(date => {
            const values = tickers.map((t, i) => {
                const bar = tickerMaps[i].get(date);
                if (bar === undefined) return null;
                
                if (scaleType === 'percent') {
                    const baseValue = firstValues[i];
                    return {
                        close: ((bar.close / baseValue) - 1) * 100,
                        open: ((bar.open / baseValue) - 1) * 100,
                        high: ((bar.high / baseValue) - 1) * 100,
                        low: ((bar.low / baseValue) - 1) * 100,
                    };
                }
                return { close: bar.close, open: bar.open, high: bar.high, low: bar.low };
            });
            return { date, values };
        });

        const filteredData = aligned.filter(d => d.values.some(v => v !== null));

        let minVal = Infinity;
        let maxVal = -Infinity;
        filteredData.forEach(d => {
            d.values.forEach(v => {
                if (v !== null) {
                    minVal = Math.min(minVal, v.low, v.close);
                    maxVal = Math.max(maxVal, v.high, v.close);
                }
            });
        });

        const range = maxVal - minVal;
        minVal = minVal - range * 0.05;
        maxVal = maxVal + range * 0.05;

        const dates = filteredData.map(d => new Date(d.date));
        
        return {
            alignedData: filteredData,
            dateRange: {
                min: dates.length > 0 ? dates[0] : new Date(),
                max: dates.length > 0 ? dates[dates.length - 1] : new Date(),
            },
            valueRange: { min: minVal, max: maxVal },
        };
    }, [tickers, scaleType]);

    const xScale = useCallback((date: string) => {
        const d = new Date(date).getTime();
        const min = dateRange.min.getTime();
        const max = dateRange.max.getTime();
        if (max === min) return padding.left;
        return padding.left + ((d - min) / (max - min)) * chartWidth;
    }, [dateRange, chartWidth, padding.left]);

    const yScale = useCallback((value: number) => {
        const { min, max } = valueRange;
        if (max === min) return padding.top + chartHeight / 2;
        return padding.top + chartHeight - ((value - min) / (max - min)) * chartHeight;
    }, [valueRange, chartHeight, padding.top]);

    // Calculate candle/bar width
    const barWidth = useMemo(() => {
        if (alignedData.length <= 1) return 8;
        const totalBars = alignedData.length;
        const availableWidth = chartWidth * 0.8;
        return Math.max(2, Math.min(12, availableWidth / totalBars));
    }, [alignedData.length, chartWidth]);

    // Line/Area paths
    const paths = useMemo(() => {
        return tickers.map((ticker, tickerIdx) => {
            const points: string[] = [];
            let started = false;
            
            alignedData.forEach((d) => {
                const value = d.values[tickerIdx];
                if (value !== null) {
                    const x = xScale(d.date);
                    const y = yScale(value.close);
                    if (!started) {
                        points.push(`M ${x} ${y}`);
                        started = true;
                    } else {
                        points.push(`L ${x} ${y}`);
                    }
                }
            });
            
            return points.join(' ');
        });
    }, [tickers, alignedData, xScale, yScale]);

    // Area/Mountain paths
    const areaPaths = useMemo(() => {
        if (chartType !== 'area' && chartType !== 'mountain') return [];
        
        return tickers.map((ticker, tickerIdx) => {
            const points: { x: number; y: number }[] = [];
            
            alignedData.forEach(d => {
                const value = d.values[tickerIdx];
                if (value !== null) {
                    points.push({
                        x: xScale(d.date),
                        y: yScale(value.close),
                    });
                }
            });
            
            if (points.length < 2) return '';
            
            const baseline = yScale(scaleType === 'percent' ? 0 : valueRange.min);
            
            let path = `M ${points[0].x} ${baseline}`;
            points.forEach(p => path += ` L ${p.x} ${p.y}`);
            path += ` L ${points[points.length - 1].x} ${baseline} Z`;
            
            return path;
        });
    }, [tickers, alignedData, xScale, yScale, chartType, scaleType, valueRange]);

    const gridLines = useMemo(() => {
        const lines: { y: number; label: string }[] = [];
        const { min, max } = valueRange;
        const range = max - min;
        const step = range / 5;
        
        for (let i = 0; i <= 5; i++) {
            const value = min + step * i;
            lines.push({
                y: yScale(value),
                label: scaleType === 'percent' 
                    ? `${value >= 0 ? '+' : ''}${value.toFixed(0)}%`
                    : value.toFixed(0),
            });
        }
        
        return lines;
    }, [valueRange, yScale, scaleType]);

    const xLabels = useMemo(() => {
        if (alignedData.length === 0) return [];
        
        const labels: { x: number; label: string }[] = [];
        const step = Math.max(1, Math.floor(alignedData.length / 6));
        
        for (let i = 0; i < alignedData.length; i += step) {
            const d = alignedData[i];
            const date = new Date(d.date);
            labels.push({
                x: xScale(d.date),
                label: date.toLocaleDateString('en-US', { timeZone: getUserTimezone(), month: 'short', day: 'numeric' }),
            });
        }
        
        return labels;
    }, [alignedData, xScale]);

    const zeroY = scaleType === 'percent' ? yScale(0) : null;

    const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
        if (alignedData.length === 0 || !svgRef.current) {
            onTooltip(null);
            return;
        }

        const rect = svgRef.current.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        let closestIdx = 0;
        let closestDist = Infinity;

        alignedData.forEach((d, i) => {
            const x = xScale(d.date);
            const dist = Math.abs(x - mouseX);
            if (dist < closestDist) {
                closestDist = dist;
                closestIdx = i;
            }
        });

        const dataPoint = alignedData[closestIdx];
        const values = tickers.map((t, i) => {
            const val = dataPoint.values[i];
            return {
                symbol: t.symbol,
                color: t.color,
                value: val?.close ?? 0,
                open: val?.open,
                high: val?.high,
                low: val?.low,
                close: val?.close,
            };
        }).filter(v => v.value !== null);

        onTooltip({
            date: dataPoint.date,
            values,
            x: xScale(dataPoint.date),
            y: mouseY,
        });
    }, [alignedData, tickers, xScale, onTooltip]);

    const handleMouseLeave = useCallback(() => {
        onTooltip(null);
    }, [onTooltip]);

    if (tickers.length === 0) {
        return (
            <svg width={width} height={height}>
                <text
                    x={width / 2}
                    y={height / 2}
                    textAnchor="middle"
                    fill="#94a3b8"
                    fontSize={12}
                >
                    Add tickers to compare
                </text>
            </svg>
        );
    }

    // Render candlestick/OHLC - works with any number of tickers
    const renderCandlestick = chartType === 'candlestick';
    const renderOHLC = chartType === 'ohlc';

    return (
        <svg
            ref={svgRef}
            width={width}
            height={height}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
            className="select-none"
        >
            <defs>
                {tickers.map((ticker, i) => (
                    <linearGradient
                        key={`gradient-${ticker.symbol}`}
                        id={`area-gradient-${i}`}
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                    >
                        <stop offset="0%" stopColor={ticker.color} stopOpacity={chartType === 'mountain' ? 0.5 : 0.2} />
                        <stop offset="100%" stopColor={ticker.color} stopOpacity={chartType === 'mountain' ? 0.1 : 0.02} />
                    </linearGradient>
                ))}
            </defs>

            {/* Grid lines */}
            {gridLines.map((line, i) => (
                <g key={i}>
                    <line
                        x1={padding.left}
                        y1={line.y}
                        x2={padding.left + chartWidth}
                        y2={line.y}
                        stroke="#e2e8f0"
                        strokeDasharray="3 3"
                        strokeWidth={0.5}
                    />
                    <text
                        x={padding.left + chartWidth + 6}
                        y={line.y + 3}
                        fill="#94a3b8"
                        fontSize={9}
                        fontFamily="JetBrains Mono, monospace"
                    >
                        {line.label}
                    </text>
                </g>
            ))}

            {/* X axis labels */}
            {xLabels.map((label, i) => (
                <text
                    key={i}
                    x={label.x}
                    y={padding.top + chartHeight + 16}
                    fill="#94a3b8"
                    fontSize={9}
                    textAnchor="middle"
                >
                    {label.label}
                </text>
            ))}

            {/* Zero reference line */}
            {zeroY !== null && zeroY >= padding.top && zeroY <= padding.top + chartHeight && (
                <line
                    x1={padding.left}
                    y1={zeroY}
                    x2={padding.left + chartWidth}
                    y2={zeroY}
                    stroke="#94a3b8"
                    strokeWidth={1}
                    strokeDasharray="4 2"
                />
            )}

            {/* Candlestick Chart */}
            {renderCandlestick && tickers.map((ticker, tickerIdx) => {
                const offsetX = tickers.length > 1 ? (tickerIdx - (tickers.length - 1) / 2) * (barWidth + 1) : 0;
                
                return alignedData.map((d, idx) => {
                    const val = d.values[tickerIdx];
                    if (!val) return null;
                    
                    const x = xScale(d.date) + offsetX;
                    const openY = yScale(val.open);
                    const closeY = yScale(val.close);
                    const highY = yScale(val.high);
                    const lowY = yScale(val.low);
                    
                    const isBullish = val.close >= val.open;
                    // Use ticker color for multi-ticker, green/red for single
                    const candleColor = tickers.length === 1 
                        ? (isBullish ? '#10b981' : '#f43f5e')
                        : ticker.color;
                    const bodyTop = Math.min(openY, closeY);
                    const bodyHeight = Math.max(1, Math.abs(closeY - openY));
                    const candleWidth = tickers.length > 1 ? Math.max(2, barWidth / tickers.length) : barWidth;
                    
                    return (
                        <g key={`candle-${tickerIdx}-${idx}`}>
                            {/* Wick */}
                            <line
                                x1={x}
                                y1={highY}
                                x2={x}
                                y2={lowY}
                                stroke={candleColor}
                                strokeWidth={1}
                                opacity={tickers.length > 1 ? 0.7 : 1}
                            />
                            {/* Body */}
                            <rect
                                x={x - candleWidth / 2}
                                y={bodyTop}
                                width={candleWidth}
                                height={bodyHeight}
                                fill={isBullish ? candleColor : 'white'}
                                stroke={candleColor}
                                strokeWidth={1}
                                rx={0.5}
                                opacity={tickers.length > 1 ? 0.8 : 1}
                            />
                        </g>
                    );
                });
            })}

            {/* OHLC Bars */}
            {renderOHLC && tickers.map((ticker, tickerIdx) => {
                const offsetX = tickers.length > 1 ? (tickerIdx - (tickers.length - 1) / 2) * (barWidth + 1) : 0;
                
                return alignedData.map((d, idx) => {
                    const val = d.values[tickerIdx];
                    if (!val) return null;
                    
                    const x = xScale(d.date) + offsetX;
                    const openY = yScale(val.open);
                    const closeY = yScale(val.close);
                    const highY = yScale(val.high);
                    const lowY = yScale(val.low);
                    
                    const isBullish = val.close >= val.open;
                    // Use ticker color for multi-ticker, green/red for single
                    const barColor = tickers.length === 1 
                        ? (isBullish ? '#10b981' : '#f43f5e')
                        : ticker.color;
                    const tickWidth = tickers.length > 1 ? Math.max(2, barWidth / tickers.length / 2) : barWidth / 2;
                    
                    return (
                        <g key={`ohlc-${tickerIdx}-${idx}`}>
                            {/* Vertical line (high-low) */}
                            <line
                                x1={x}
                                y1={highY}
                                x2={x}
                                y2={lowY}
                                stroke={barColor}
                                strokeWidth={1.5}
                                opacity={tickers.length > 1 ? 0.8 : 1}
                            />
                            {/* Open tick (left) */}
                            <line
                                x1={x - tickWidth}
                                y1={openY}
                                x2={x}
                                y2={openY}
                                stroke={barColor}
                                strokeWidth={1.5}
                                opacity={tickers.length > 1 ? 0.8 : 1}
                            />
                            {/* Close tick (right) */}
                            <line
                                x1={x}
                                y1={closeY}
                                x2={x + tickWidth}
                                y2={closeY}
                                stroke={barColor}
                                strokeWidth={1.5}
                                opacity={tickers.length > 1 ? 0.8 : 1}
                            />
                        </g>
                    );
                });
            })}

            {/* Area/Mountain fills */}
            {(chartType === 'area' || chartType === 'mountain') && !renderCandlestick && !renderOHLC && areaPaths.map((path, i) => (
                <path
                    key={`area-${tickers[i].symbol}`}
                    d={path}
                    fill={`url(#area-gradient-${i})`}
                />
            ))}

            {/* Lines */}
            {!renderCandlestick && !renderOHLC && paths.map((path, i) => (
                <path
                    key={`line-${tickers[i].symbol}`}
                    d={path}
                    fill="none"
                    stroke={tickers[i].color}
                    strokeWidth={chartType === 'mountain' ? 2 : 1.5}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                />
            ))}
        </svg>
    );
}

// ============================================================================
// Tooltip Component
// ============================================================================

function ChartTooltip({ tooltip, chartType }: { tooltip: TooltipData | null; chartType: ChartType }) {
    if (!tooltip) return null;

    const date = new Date(tooltip.date);
    const formattedDate = date.toLocaleDateString('en-US', {
        timeZone: getUserTimezone(),
        month: 'short',
        day: 'numeric',
        year: 'numeric',
    });

    const showOHLC = (chartType === 'candlestick' || chartType === 'ohlc') && tooltip.values.length === 1;

    return (
        <div
            className="absolute pointer-events-none bg-white border border-slate-200 rounded shadow-lg px-3 py-2 z-50"
            style={{
                left: tooltip.x + 15,
                top: tooltip.y - 10,
                transform: tooltip.x > 400 ? 'translateX(-100%)' : undefined,
            }}
        >
            <div className="text-[10px] text-slate-500 font-medium mb-1">{formattedDate}</div>
            <div className="space-y-0.5">
                {tooltip.values.map(v => (
                    <div key={v.symbol}>
                        <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-1.5">
                                <div
                                    className="w-2 h-2 rounded-sm"
                                    style={{ backgroundColor: v.color }}
                                />
                                <span className="text-[10px] text-slate-700 font-medium">{v.symbol}</span>
                            </div>
                            <span
                                className="text-[10px] font-mono font-semibold"
                                style={{ color: v.value >= 0 ? '#10b981' : '#f43f5e' }}
                            >
                                {v.value >= 0 ? '+' : ''}{v.value.toFixed(2)}%
                            </span>
                        </div>
                        {/* OHLC details */}
                        {showOHLC && v.open !== undefined && (
                            <div className="mt-1 pt-1 border-t border-slate-100 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px]">
                                <div className="flex justify-between">
                                    <span className="text-slate-400">O</span>
                                    <span className="font-mono text-slate-600">{v.open?.toFixed(2)}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-400">H</span>
                                    <span className="font-mono text-emerald-600">{v.high?.toFixed(2)}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-400">L</span>
                                    <span className="font-mono text-rose-500">{v.low?.toFixed(2)}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-400">C</span>
                                    <span className="font-mono text-slate-700 font-semibold">{v.close?.toFixed(2)}</span>
                                </div>
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}

// ============================================================================
// Main Component
// ============================================================================

export function HistoricalMultipleSecurityContent() {
    const font = useUserPreferencesStore(selectFont);
    const fontFamily = `var(--font-${font})`;

    // Hook para persistir estado de la ventana
    const { state: windowState, updateState: updateWindowState } = useWindowState<MPWindowState>();

    const [tickers, setTickers] = useState<TickerData[]>([]);
    const [tickerInput, setTickerInput] = useState('');
    const [period, setPeriod] = useState<Period>(windowState.period || '1Y');
    const [chartType, setChartType] = useState<ChartType>(windowState.chartType || 'line');
    const [scaleType, setScaleType] = useState<ScaleType>(windowState.scaleType || 'percent');

    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [tooltip, setTooltip] = useState<TooltipData | null>(null);
    const [initialLoadDone, setInitialLoadDone] = useState(false);

    const chartContainerRef = useRef<HTMLDivElement>(null);
    const [chartSize, setChartSize] = useState({ width: 800, height: 400 });

    useEffect(() => {
        if (!chartContainerRef.current) return;

        const observer = new ResizeObserver(entries => {
            const entry = entries[0];
            if (entry) {
                setChartSize({
                    width: entry.contentRect.width,
                    height: Math.max(250, entry.contentRect.height),
                });
            }
        });

        observer.observe(chartContainerRef.current);
        return () => observer.disconnect();
    }, []);

    // Restaurar tickers guardados al montar
    useEffect(() => {
        if (initialLoadDone) return;
        
        const savedTickers = windowState.tickerSymbols;
        if (savedTickers && savedTickers.length > 0) {
            const loadSavedTickers = async () => {
                setLoading(true);
                setError(null);
                
                const loadedTickers: TickerData[] = [];
                for (let i = 0; i < savedTickers.length; i++) {
                    try {
                        const periodConfig = PERIODS.find(p => p.id === period);
                        if (!periodConfig) continue;
                        
                        const response = await fetch(
                            `${API_URL}/api/v1/chart/${savedTickers[i].toUpperCase()}?interval=1day&limit=${periodConfig.days}`
                        );
                        
                        if (!response.ok) continue;
                        
                        const result = await response.json();
                        const data = result.data || [];
                        if (data.length === 0) continue;
                        
                        const chartData: OHLCBar[] = data.map((bar: any) => ({
                            date: new Date(bar.time * 1000).toISOString().split('T')[0],
                            open: bar.open,
                            high: bar.high,
                            low: bar.low,
                            close: bar.close,
                        })).sort((a: OHLCBar, b: OHLCBar) => a.date.localeCompare(b.date));
                        
                        const firstPrice = chartData[0]?.close || 1;
                        const lastPrice = chartData[chartData.length - 1]?.close || firstPrice;
                        const changePercent = ((lastPrice / firstPrice) - 1) * 100;
                        
                        loadedTickers.push({
                            symbol: savedTickers[i].toUpperCase(),
                            color: TICKER_COLORS[i % TICKER_COLORS.length],
                            data: chartData,
                            latestPrice: lastPrice,
                            changePercent,
                        });
                    } catch {
                        // Skip failed tickers
                    }
                }
                
                setTickers(loadedTickers);
                setLoading(false);
                setInitialLoadDone(true);
            };
            
            loadSavedTickers();
        } else {
            setInitialLoadDone(true);
        }
    }, [windowState.tickerSymbols, period, initialLoadDone]);

    // Persistir estado cuando cambian los valores
    useEffect(() => {
        if (!initialLoadDone) return;
        
        updateWindowState({
            tickerSymbols: tickers.map(t => t.symbol),
            period,
            chartType,
            scaleType,
        });
    }, [tickers, period, chartType, scaleType, initialLoadDone, updateWindowState]);

    const fetchTickerData = useCallback(async (symbol: string): Promise<TickerData | null> => {
        const periodConfig = PERIODS.find(p => p.id === period);
        if (!periodConfig) return null;

        try {
            const response = await fetch(
                `${API_URL}/api/v1/chart/${symbol.toUpperCase()}?interval=1day&limit=${periodConfig.days}`
            );

            if (!response.ok) {
                throw new Error(`Failed to fetch ${symbol}`);
            }

            const result = await response.json();
            const data = result.data || [];

            if (data.length === 0) {
                throw new Error(`No data for ${symbol}`);
            }

            const chartData: OHLCBar[] = data.map((bar: any) => ({
                date: new Date(bar.time * 1000).toISOString().split('T')[0],
                open: bar.open,
                high: bar.high,
                low: bar.low,
                close: bar.close,
            })).sort((a: OHLCBar, b: OHLCBar) => a.date.localeCompare(b.date));

            const firstPrice = chartData[0]?.close || 1;
            const lastPrice = chartData[chartData.length - 1]?.close || firstPrice;
            const changePercent = ((lastPrice / firstPrice) - 1) * 100;

            const usedColors = tickers.map(t => t.color);
            const availableColor = TICKER_COLORS.find(c => !usedColors.includes(c)) || TICKER_COLORS[0];

            return {
                symbol: symbol.toUpperCase(),
                color: availableColor,
                data: chartData,
                latestPrice: lastPrice,
                changePercent,
            };
        } catch (e: any) {
            throw new Error(`${symbol}: ${e.message}`);
        }
    }, [period, tickers]);

    const handleAddTicker = useCallback(async () => {
        const symbol = tickerInput.trim().toUpperCase();
        
        if (!symbol) return;
        if (tickers.some(t => t.symbol === symbol)) {
            setError(`${symbol} already added`);
            return;
        }
        if (tickers.length >= 10) {
            setError('Maximum 10 tickers');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const tickerData = await fetchTickerData(symbol);
            if (tickerData) {
                setTickers(prev => [...prev, tickerData]);
                setTickerInput('');
            }
        } catch (e: any) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    }, [tickerInput, tickers, fetchTickerData]);

    const handleRemoveTicker = useCallback((symbol: string) => {
        setTickers(prev => prev.filter(t => t.symbol !== symbol));
    }, []);

    const handleSelectTicker = useCallback(async (selected: TickerSearchResult) => {
        const symbol = selected.symbol.toUpperCase();
        
        if (tickers.some(t => t.symbol === symbol)) {
            setError(`${symbol} already added`);
            return;
        }
        if (tickers.length >= 10) {
            setError('Maximum 10 tickers');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const tickerData = await fetchTickerData(symbol);
            if (tickerData) {
                setTickers(prev => [...prev, tickerData]);
                setTickerInput('');
            }
        } catch (e: any) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    }, [tickers, fetchTickerData]);

    // Refetch when period changes
    useEffect(() => {
        if (tickers.length === 0) return;

        const refetchAll = async () => {
            setLoading(true);
            setError(null);

            try {
                const symbols = tickers.map(t => t.symbol);
                const results = await Promise.all(
                    symbols.map(async (symbol, idx) => {
                        try {
                            const data = await fetchTickerData(symbol);
                            if (data) {
                                return { ...data, color: tickers[idx].color };
                            }
                            return null;
                        } catch {
                            return null;
                        }
                    })
                );

                setTickers(results.filter((r): r is TickerData => r !== null));
            } catch (e: any) {
                setError(e.message);
            } finally {
                setLoading(false);
            }
        };

        refetchAll();
    }, [period]);

    return (
        <div className="h-full flex flex-col bg-white text-slate-800" style={{ fontFamily }}>
            {/* Search Bar */}
            <div className="flex-shrink-0 px-4 py-3 border-b border-slate-100">
                <div className="flex gap-2 items-center">
                    <div className="w-32">
                        <TickerSearch
                            value={tickerInput}
                            onChange={setTickerInput}
                            onSelect={handleSelectTicker}
                            placeholder="Add ticker"
                            className="w-full"
                        />
                    </div>
                    
                    <button
                        onClick={handleAddTicker}
                        disabled={loading || !tickerInput.trim()}
                        className="p-1.5 rounded border border-slate-200 text-slate-400 hover:text-blue-600 hover:border-blue-300 disabled:opacity-50"
                    >
                        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                    </button>

                    {/* Period selector */}
                    <div className="flex items-center gap-1 text-slate-400 ml-2" style={{ fontSize: '10px' }}>
                        {PERIODS.map(p => (
                            <button
                                key={p.id}
                                onClick={() => setPeriod(p.id)}
                                className={`px-1.5 py-0.5 rounded ${
                                    period === p.id 
                                        ? 'bg-slate-100 text-slate-700' 
                                        : 'hover:text-slate-600'
                                }`}
                            >
                                {p.label}
                            </button>
                        ))}
                    </div>

                    <div className="flex-1" />

                    {/* Chart type selector */}
                    <div className="flex items-center gap-0.5 text-slate-400" style={{ fontSize: '9px' }}>
                        {CHART_TYPES.map(ct => {
                            const Icon = ct.icon;
                            return (
                                <button
                                    key={ct.id}
                                    onClick={() => setChartType(ct.id)}
                                    className={`p-1 rounded transition-colors ${
                                        chartType === ct.id 
                                            ? 'bg-slate-100 text-slate-700' 
                                            : 'hover:text-slate-600'
                                    }`}
                                    title={ct.label}
                                >
                                    <Icon className="w-3.5 h-3.5" />
                                </button>
                            );
                        })}
                        <span className="text-slate-200 mx-0.5">|</span>
                        <button
                            onClick={() => setScaleType('percent')}
                            className={`px-1.5 py-0.5 rounded ${scaleType === 'percent' ? 'bg-slate-100 text-slate-700' : 'hover:text-slate-600'}`}
                        >
                            %
                        </button>
                        <button
                            onClick={() => setScaleType('price')}
                            className={`px-1.5 py-0.5 rounded ${scaleType === 'price' ? 'bg-slate-100 text-slate-700' : 'hover:text-slate-600'}`}
                        >
                            $
                        </button>
                    </div>

                    <button
                        className="p-1.5 rounded border border-slate-200 text-slate-400 hover:text-slate-600"
                        title="Export"
                    >
                        <Download className="w-4 h-4" />
                    </button>
                </div>
            </div>

            {/* Tickers legend - inline */}
            {tickers.length > 0 && (
                <div className="flex-shrink-0 px-4 py-2 border-b border-slate-100 flex flex-wrap items-center gap-2">
                    {tickers.map(t => (
                        <div
                            key={t.symbol}
                            className="flex items-center gap-1.5 group"
                        >
                            <div
                                className="w-3 h-0.5 rounded"
                                style={{ backgroundColor: t.color }}
                            />
                            <span className="text-[11px] font-medium" style={{ color: t.color }}>{t.symbol}</span>
                            <span
                                className="text-[10px] font-mono"
                                style={{ color: t.changePercent >= 0 ? '#10b981' : '#f43f5e' }}
                            >
                                {t.changePercent >= 0 ? '+' : ''}{t.changePercent.toFixed(1)}%
                            </span>
                            <button
                                onClick={() => handleRemoveTicker(t.symbol)}
                                className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-300 hover:text-slate-500"
                            >
                                <X className="w-3 h-3" />
                            </button>
                        </div>
                    ))}
                </div>
            )}

            {/* Error */}
            {error && (
                <div className="flex items-center gap-2 text-red-600 px-4 py-2" style={{ fontSize: '11px' }}>
                    <AlertCircle className="w-4 h-4" />
                    {error}
                    <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-600">
                        <X className="w-3.5 h-3.5" />
                    </button>
                </div>
            )}

            {/* Chart area */}
            <div ref={chartContainerRef} className="flex-1 relative px-4 py-3">
                {loading && tickers.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-slate-400">
                        <Loader2 className="w-6 h-6 animate-spin mb-2" />
                        <span style={{ fontSize: '11px' }}>Loading...</span>
                    </div>
                ) : tickers.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-slate-400">
                        <Search className="w-8 h-8 mb-2 opacity-30" />
                        <p style={{ fontSize: '12px' }}>Add tickers to compare their performance</p>
                        <p style={{ fontSize: '10px' }} className="text-slate-300 mt-1">e.g., NVDA, MSFT, AAPL</p>
                    </div>
                ) : (
                    <>
                        <SVGChart
                            tickers={tickers}
                            width={chartSize.width}
                            height={chartSize.height}
                            chartType={chartType}
                            scaleType={scaleType}
                            onTooltip={setTooltip}
                        />
                        <ChartTooltip tooltip={tooltip} chartType={chartType} />
                    </>
                )}
            </div>

            {/* Footer */}
            <div className="flex-shrink-0 px-4 py-1 border-t border-slate-100 flex items-center justify-between text-[9px] text-slate-400">
                <span>
                    {tickers.length > 0
                        ? `${tickers.length} ticker${tickers.length > 1 ? 's' : ''} · ${PERIODS.find(p => p.id === period)?.label} · ${CHART_TYPES.find(c => c.id === chartType)?.label}`
                        : 'Add tickers to begin'}
                </span>
                <span className="font-mono">MP</span>
            </div>
        </div>
    );
}

export default HistoricalMultipleSecurityContent;
