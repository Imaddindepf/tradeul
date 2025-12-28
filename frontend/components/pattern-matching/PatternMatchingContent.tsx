'use client';

import { useState, useCallback, useEffect, useMemo } from 'react';
import {
    Search,
    TrendingUp,
    TrendingDown,
    Clock,
    Loader2,
    AlertCircle,
    Settings2,
    Maximize2,
} from 'lucide-react';
import { TickerSearch } from '@/components/common/TickerSearch';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { CandlestickSelector } from './CandlestickSelector';

// ============================================================================
// Types
// ============================================================================

interface PatternNeighbor {
    symbol: string;
    date: string;
    start_time: string;
    end_time: string;
    distance: number;
    future_returns: number[];
}

interface PatternForecast {
    horizon_minutes: number;
    mean_return: number;
    mean_trajectory: number[];
    std_trajectory: number[];
    prob_up: number;
    prob_down: number;
    confidence: 'high' | 'medium' | 'low';
    best_case: number;
    worst_case: number;
    median_return: number;
    n_neighbors: number;
}

interface SearchResult {
    status: string;
    query: {
        symbol: string;
        window_minutes: number;
        cross_asset: boolean;
        mode?: string;
        date?: string;
        pattern_time?: string;
    };
    forecast: PatternForecast;
    neighbors: PatternNeighbor[];
    stats: {
        query_time_ms: number;
        index_size: number;
    };
    historical_context?: {
        pattern_prices?: number[];
        pattern_times?: string[];
        pattern_start?: string;
        pattern_end?: string;
    };
    actual?: {
        returns: number[];
        final_return: number;
        direction: string;
        direction_correct: boolean;
        error_vs_forecast: number | null;
    };
}

interface IndexStats {
    n_vectors: number;
}

interface AvailableDates {
    dates: string[];
    last: string;
}

type SearchMode = 'realtime' | 'historical';

type TickerSearchResult = {
    symbol: string;
    name: string;
    exchange: string;
    type: string;
    displayName: string;
};

const API_BASE = process.env.NEXT_PUBLIC_PATTERN_API_URL || 'https://api.tradeul.com/patterns';

// ============================================================================
// Expanded Chart Component (for floating window) - Same as GodelChart but larger
// ============================================================================

function ExpandedChart({
    forecast,
    neighbors,
    historicalContext,
    symbol,
    date,
    actual,
    showActual,
}: {
    forecast: PatternForecast;
    neighbors: PatternNeighbor[];
    historicalContext?: HistoricalContext;
    symbol: string;
    date?: string;
    actual?: { returns: number[]; final_return: number; direction: string; direction_correct: boolean };
    showActual?: boolean;
}) {
    const font = useUserPreferencesStore(selectFont);
    const fontFamily = `var(--font-${font})`;

    const width = 700;
    const height = 380;
    const padding = { top: 50, right: 70, bottom: 50, left: 65 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    // Normalize pattern prices to cumulative returns (like neighbors)
    const queryPattern = useMemo(() => {
        if (!historicalContext?.pattern_prices || historicalContext.pattern_prices.length < 2) {
            return null;
        }
        const prices = historicalContext.pattern_prices;
        const basePrice = prices[0];
        return prices.map(p => ((p / basePrice) - 1) * 100);
    }, [historicalContext]);

    const beforeLength = queryPattern?.length || 45;
    const afterLength = forecast.mean_trajectory.length;
    const totalLength = beforeLength + afterLength;
    const t0Index = beforeLength;

    // Offset for continuity: value at t₀ (end of query pattern)
    const t0Offset = queryPattern ? queryPattern[queryPattern.length - 1] : 0;

    const { maxAbs, xScale, yScale } = useMemo(() => {
        const allVals: number[] = [];

        if (queryPattern) {
            allVals.push(...queryPattern);
        }

        neighbors.slice(0, 30).forEach(n => {
            allVals.push(...n.future_returns.map(v => v + t0Offset));
        });
        allVals.push(...forecast.mean_trajectory.map((m, i) => m + forecast.std_trajectory[i] + t0Offset));
        allVals.push(...forecast.mean_trajectory.map((m, i) => m - forecast.std_trajectory[i] + t0Offset));

        if (showActual && actual?.returns) {
            allVals.push(...actual.returns.map(v => v + t0Offset));
        }

        const mAbs = Math.max(
            Math.abs(Math.min(...allVals, -0.5)),
            Math.abs(Math.max(...allVals, 0.5)),
            0.5
        );

        const xS = (i: number) => padding.left + (i / (totalLength - 1)) * chartWidth;
        const yS = (v: number) => padding.top + chartHeight / 2 - (v / mAbs) * (chartHeight / 2);

        return { maxAbs: mAbs, xScale: xS, yScale: yS };
    }, [forecast, neighbors, queryPattern, totalLength, chartWidth, chartHeight, showActual, actual, t0Offset]);

    const queryLine = queryPattern
        ? queryPattern.map((v, i) => `${xScale(i)},${yScale(v)}`).join(' ')
        : '';

    const forecastLine = forecast.mean_trajectory
        .map((v, i) => `${xScale(t0Index + i)},${yScale(v + t0Offset)}`)
        .join(' ');

    const upperBand = forecast.mean_trajectory
        .map((m, i) => `${xScale(t0Index + i)},${yScale(m + forecast.std_trajectory[i] + t0Offset)}`)
        .join(' ');
    const lowerBand = forecast.mean_trajectory
        .map((m, i) => `${xScale(t0Index + i)},${yScale(m - forecast.std_trajectory[i] + t0Offset)}`)
        .reverse()
        .join(' ');
    const bandPath = `M${upperBand} L${lowerBand} Z`;

    return (
        <div className="h-full bg-white p-5" style={{ fontFamily }}>
            {/* Header */}
            <div className="flex items-baseline justify-between mb-3">
                <div className="flex items-baseline gap-3">
                    <span className="text-xl font-bold text-slate-800">{symbol}</span>
                    {date && <span className="text-slate-400" style={{ fontSize: '12px' }}>{date} {historicalContext?.pattern_end}</span>}
                    <span className="text-slate-400" style={{ fontSize: '12px' }}>+{forecast.horizon_minutes}min forecast</span>
                </div>
                <div className="flex items-center gap-4" style={{ fontSize: '11px' }}>
                    <span className="flex items-center gap-1">
                        <span className="w-4 h-0.5 bg-slate-700 inline-block"></span>
                        <span className="text-slate-500">Query</span>
                    </span>
                    <span className="flex items-center gap-1">
                        <span className="w-4 h-0.5 bg-blue-500 inline-block" style={{ borderStyle: 'dashed' }}></span>
                        <span className="text-slate-500">Forecast</span>
                    </span>
                    <span className="flex items-center gap-1">
                        <span className="w-4 h-0.5 bg-slate-400 inline-block opacity-50"></span>
                        <span className="text-slate-500">Neighbors</span>
                    </span>
                    {showActual && actual && (
                        <span className="flex items-center gap-1">
                            <span className={`w-4 h-0.5 inline-block ${actual.final_return >= 0 ? 'bg-emerald-500' : 'bg-red-500'}`}></span>
                            <span className="text-slate-500">Actual</span>
                        </span>
                    )}
                </div>
            </div>

            <svg width={width} height={height}>
                {/* Background regions */}
                <rect
                    x={padding.left}
                    y={padding.top}
                    width={xScale(t0Index) - padding.left}
                    height={chartHeight}
                    fill="#f8fafc"
                />
                <rect
                    x={xScale(t0Index)}
                    y={padding.top}
                    width={padding.left + chartWidth - xScale(t0Index)}
                    height={chartHeight}
                    fill="#fefefe"
                />

                {/* Grid */}
                {[-maxAbs, -maxAbs / 2, 0, maxAbs / 2, maxAbs].map((v, i) => (
                    <g key={i}>
                        <line
                            x1={padding.left}
                            y1={yScale(v)}
                            x2={padding.left + chartWidth}
                            y2={yScale(v)}
                            stroke={v === 0 ? '#94a3b8' : '#e2e8f0'}
                            strokeWidth={v === 0 ? 1 : 0.5}
                        />
                        <text x={padding.left - 10} y={yScale(v) + 4} textAnchor="end" fill="#94a3b8" style={{ fontSize: '11px' }}>
                            {v > 0 ? '+' : ''}{v.toFixed(2)}%
                        </text>
                    </g>
                ))}

                {/* t₀ vertical line */}
                <line
                    x1={xScale(t0Index)}
                    y1={padding.top - 5}
                    x2={xScale(t0Index)}
                    y2={padding.top + chartHeight + 5}
                    stroke="#64748b"
                    strokeWidth="1"
                    strokeDasharray="4,3"
                />
                <text
                    x={xScale(t0Index)}
                    y={padding.top - 12}
                    textAnchor="middle"
                    fill="#64748b"
                    style={{ fontSize: '11px', fontWeight: 600 }}
                >
                    t₀
                </text>

                {/* X axis labels */}
                <text x={padding.left + 5} y={height - 15} fill="#94a3b8" style={{ fontSize: '10px' }}>
                    before
                </text>
                <text x={padding.left + chartWidth - 5} y={height - 15} textAnchor="end" fill="#94a3b8" style={{ fontSize: '10px' }}>
                    after (+{forecast.horizon_minutes}min)
                </text>

                {/* Neighbor trajectories (after t₀) */}
                {neighbors.slice(0, 30).map((n, idx) => {
                    const pts = [
                        `${xScale(t0Index)},${yScale(t0Offset)}`,
                        ...n.future_returns.map((v, i) => `${xScale(t0Index + i + 1)},${yScale(v + t0Offset)}`)
                    ].join(' ');
                    return (
                        <polyline
                            key={idx}
                            points={pts}
                            fill="none"
                            stroke="#64748b"
                            strokeWidth="1.2"
                            opacity="0.25"
                        />
                    );
                })}

                {/* Confidence band */}
                <path d={bandPath} fill="rgba(59, 130, 246, 0.1)" />

                {/* Query pattern line (before t₀) */}
                {queryLine && (
                    <polyline
                        points={queryLine}
                        fill="none"
                        stroke="#1e293b"
                        strokeWidth="2.5"
                        strokeLinecap="round"
                    />
                )}

                {/* Forecast mean line (after t₀) */}
                <polyline
                    points={`${xScale(t0Index)},${yScale(t0Offset)} ${forecastLine}`}
                    fill="none"
                    stroke="#3b82f6"
                    strokeWidth="2.5"
                    strokeDasharray="6,3"
                    strokeLinecap="round"
                />

                {/* Actual line (after t₀) */}
                {showActual && actual?.returns && actual.returns.length > 0 && (
                    <>
                        <polyline
                            points={[
                                `${xScale(t0Index)},${yScale(t0Offset)}`,
                                ...actual.returns.map((v, i) => `${xScale(t0Index + i + 1)},${yScale(v + t0Offset)}`)
                            ].join(' ')}
                            fill="none"
                            stroke={actual.final_return >= 0 ? '#10b981' : '#ef4444'}
                            strokeWidth="3"
                            strokeLinecap="round"
                        />
                        <circle
                            cx={xScale(t0Index + actual.returns.length)}
                            cy={yScale(actual.final_return + t0Offset)}
                            r="6"
                            fill={actual.final_return >= 0 ? '#10b981' : '#ef4444'}
                            stroke="white"
                            strokeWidth="2"
                        />
                        <text
                            x={xScale(t0Index + actual.returns.length) + 12}
                            y={yScale(actual.final_return + t0Offset) - 8}
                            fill={actual.final_return >= 0 ? '#10b981' : '#ef4444'}
                            fontWeight="700"
                            style={{ fontSize: '13px' }}
                        >
                            {actual.final_return >= 0 ? '+' : ''}{actual.final_return.toFixed(2)}% actual
                        </text>
                    </>
                )}

                {/* Forecast end marker */}
                <circle
                    cx={xScale(totalLength - 1)}
                    cy={yScale(forecast.mean_return + t0Offset)}
                    r="6"
                    fill={forecast.mean_return >= 0 ? '#10b981' : '#ef4444'}
                    stroke="white"
                    strokeWidth="2"
                    opacity={showActual && actual ? 0.5 : 1}
                />
                <text
                    x={xScale(totalLength - 1) + 12}
                    y={yScale(forecast.mean_return + t0Offset) + 5}
                    fill={forecast.mean_return >= 0 ? '#10b981' : '#ef4444'}
                    fontWeight="700"
                    style={{ fontSize: '13px' }}
                    opacity={showActual && actual ? 0.5 : 1}
                >
                    {forecast.mean_return >= 0 ? '+' : ''}{forecast.mean_return.toFixed(2)}%
                </text>

                {/* t₀ marker dot */}
                <circle
                    cx={xScale(t0Index)}
                    cy={yScale(queryPattern ? queryPattern[queryPattern.length - 1] : 0)}
                    r="4"
                    fill="#1e293b"
                    stroke="white"
                    strokeWidth="2"
                />
            </svg>

            {/* Stats */}
            <div className="flex gap-6 mt-3 pt-3 border-t border-slate-100" style={{ fontSize: '12px' }}>
                <div>
                    <span className="text-slate-400">Mean</span>
                    <span className={`ml-2 font-mono font-bold ${forecast.mean_return >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                        {forecast.mean_return >= 0 ? '+' : ''}{forecast.mean_return.toFixed(2)}%
                    </span>
                </div>
                <div>
                    <span className="text-slate-400">Median</span>
                    <span className={`ml-2 font-mono font-bold ${forecast.median_return >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                        {forecast.median_return >= 0 ? '+' : ''}{forecast.median_return.toFixed(2)}%
                    </span>
                </div>
                <div>
                    <span className="text-slate-400">Prob Up</span>
                    <span className="ml-2 font-mono font-bold text-emerald-600">{(forecast.prob_up * 100).toFixed(0)}%</span>
                </div>
                <div>
                    <span className="text-slate-400">Best</span>
                    <span className="ml-2 font-mono font-bold text-emerald-600">+{forecast.best_case.toFixed(2)}%</span>
                </div>
                <div>
                    <span className="text-slate-400">Worst</span>
                    <span className="ml-2 font-mono font-bold text-red-500">{forecast.worst_case.toFixed(2)}%</span>
                </div>
                <div>
                    <span className="text-slate-400">Confidence</span>
                    <span className={`ml-2 font-bold ${forecast.confidence === 'high' ? 'text-emerald-600' : forecast.confidence === 'medium' ? 'text-amber-500' : 'text-slate-500'}`}>
                        {forecast.confidence}
                    </span>
                </div>
            </div>
        </div>
    );
}

// ============================================================================
// Godel-style Chart - Before + After with t₀ separator
// ============================================================================

interface HistoricalContext {
    pattern_prices?: number[];
    pattern_times?: string[];
    pattern_start?: string;
    pattern_end?: string;
}

function GodelChart({
    forecast,
    neighbors,
    historicalContext,
    symbol,
    date,
    actual,
    showActual,
}: {
    forecast: PatternForecast;
    neighbors: PatternNeighbor[];
    historicalContext?: HistoricalContext;
    symbol: string;
    date?: string;
    actual?: { returns: number[]; final_return: number; direction: string; direction_correct: boolean };
    showActual?: boolean;
}) {
    const width = 600;
    const height = 220;
    const padding = { top: 35, right: 55, bottom: 35, left: 55 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    // Normalize pattern prices to cumulative returns (like neighbors)
    const queryPattern = useMemo(() => {
        if (!historicalContext?.pattern_prices || historicalContext.pattern_prices.length < 2) {
            return null;
        }
        const prices = historicalContext.pattern_prices;
        const basePrice = prices[0];
        return prices.map(p => ((p / basePrice) - 1) * 100);
    }, [historicalContext]);

    const beforeLength = queryPattern?.length || 45;
    const afterLength = forecast.mean_trajectory.length;
    const totalLength = beforeLength + afterLength;
    const t0Index = beforeLength; // Index where t₀ is

    // Offset for continuity: value at t₀ (end of query pattern)
    const t0Offset = queryPattern ? queryPattern[queryPattern.length - 1] : 0;

    const { maxAbs, xScale, yScale } = useMemo(() => {
        const allVals: number[] = [];

        // Before values (query pattern)
        if (queryPattern) {
            allVals.push(...queryPattern);
        }

        // After values (neighbors + forecast) - WITH OFFSET for continuity
        neighbors.slice(0, 30).forEach(n => {
            allVals.push(...n.future_returns.map(v => v + t0Offset));
        });
        allVals.push(...forecast.mean_trajectory.map((m, i) => m + forecast.std_trajectory[i] + t0Offset));
        allVals.push(...forecast.mean_trajectory.map((m, i) => m - forecast.std_trajectory[i] + t0Offset));

        // Include actual returns if showing - WITH OFFSET
        if (showActual && actual?.returns) {
            allVals.push(...actual.returns.map(v => v + t0Offset));
        }

        const mAbs = Math.max(
            Math.abs(Math.min(...allVals, -0.5)),
            Math.abs(Math.max(...allVals, 0.5)),
            0.5
        );

        const xS = (i: number) => padding.left + (i / (totalLength - 1)) * chartWidth;
        const yS = (v: number) => padding.top + chartHeight / 2 - (v / mAbs) * (chartHeight / 2);

        return { maxAbs: mAbs, xScale: xS, yScale: yS };
    }, [forecast, neighbors, queryPattern, totalLength, chartWidth, chartHeight, showActual, actual, t0Offset]);

    // Generate paths
    const queryLine = queryPattern
        ? queryPattern.map((v, i) => `${xScale(i)},${yScale(v)}`).join(' ')
        : '';

    // Forecast line WITH OFFSET for continuity
    const forecastLine = forecast.mean_trajectory
        .map((v, i) => `${xScale(t0Index + i)},${yScale(v + t0Offset)}`)
        .join(' ');

    // Confidence band WITH OFFSET
    const upperBand = forecast.mean_trajectory
        .map((m, i) => `${xScale(t0Index + i)},${yScale(m + forecast.std_trajectory[i] + t0Offset)}`)
        .join(' ');
    const lowerBand = forecast.mean_trajectory
        .map((m, i) => `${xScale(t0Index + i)},${yScale(m - forecast.std_trajectory[i] + t0Offset)}`)
        .reverse()
        .join(' ');
    const bandPath = `M${upperBand} L${lowerBand} Z`;

    return (
        <div className="relative">
            {/* Header */}
            <div className="flex items-center justify-between mb-2 px-1">
                <span className="text-slate-600 font-medium" style={{ fontSize: '11px' }}>
                    {symbol} @ {date} {historicalContext?.pattern_end} — Pattern window
                </span>
                <div className="flex items-center gap-4" style={{ fontSize: '10px' }}>
                    <span className="flex items-center gap-1">
                        <span className="w-3 h-0.5 bg-slate-700 inline-block"></span>
                        <span className="text-slate-500">Query</span>
                    </span>
                    <span className="flex items-center gap-1">
                        <span className="w-3 h-0.5 bg-blue-500 inline-block" style={{ borderStyle: 'dashed' }}></span>
                        <span className="text-slate-500">Forecast</span>
                    </span>
                    <span className="flex items-center gap-1">
                        <span className="w-3 h-0.5 bg-slate-400 inline-block opacity-50"></span>
                        <span className="text-slate-500">Neighbors</span>
                    </span>
                    {showActual && actual && (
                        <span className="flex items-center gap-1">
                            <span className={`w-3 h-0.5 inline-block ${actual.final_return >= 0 ? 'bg-emerald-500' : 'bg-red-500'}`}></span>
                            <span className="text-slate-500">Actual</span>
                        </span>
                    )}
                </div>
            </div>

            <svg width={width} height={height} className="block">
                {/* Background regions */}
                <rect
                    x={padding.left}
                    y={padding.top}
                    width={xScale(t0Index) - padding.left}
                    height={chartHeight}
                    fill="#f8fafc"
                />
                <rect
                    x={xScale(t0Index)}
                    y={padding.top}
                    width={padding.left + chartWidth - xScale(t0Index)}
                    height={chartHeight}
                    fill="#fefefe"
                />

                {/* Grid lines */}
                {[-maxAbs, -maxAbs / 2, 0, maxAbs / 2, maxAbs].map((v, i) => (
                    <g key={i}>
                        <line
                            x1={padding.left}
                            y1={yScale(v)}
                            x2={padding.left + chartWidth}
                            y2={yScale(v)}
                            stroke={v === 0 ? '#94a3b8' : '#e2e8f0'}
                            strokeWidth={v === 0 ? 1 : 0.5}
                        />
                        <text
                            x={padding.left - 8}
                            y={yScale(v) + 3}
                            textAnchor="end"
                            fill="#94a3b8"
                            style={{ fontSize: '9px' }}
                        >
                            {v > 0 ? '+' : ''}{v.toFixed(2)}%
                        </text>
                    </g>
                ))}

                {/* t₀ vertical line */}
                <line
                    x1={xScale(t0Index)}
                    y1={padding.top - 5}
                    x2={xScale(t0Index)}
                    y2={padding.top + chartHeight + 5}
                    stroke="#64748b"
                    strokeWidth="1"
                    strokeDasharray="4,3"
                />
                <text
                    x={xScale(t0Index)}
                    y={padding.top - 10}
                    textAnchor="middle"
                    fill="#64748b"
                    style={{ fontSize: '10px' }}
                >
                    t₀
                </text>

                {/* X axis labels */}
                <text x={padding.left + 5} y={height - 10} fill="#94a3b8" style={{ fontSize: '9px' }}>
                    before
                </text>
                <text x={padding.left + chartWidth - 5} y={height - 10} textAnchor="end" fill="#94a3b8" style={{ fontSize: '9px' }}>
                    after
                </text>

                {/* Neighbor trajectories (after t₀) - WITH OFFSET for continuity */}
                {neighbors.slice(0, 30).map((n, idx) => {
                    // Connect from t₀ (at t0Offset) to future returns + offset
                    const pts = [
                        `${xScale(t0Index)},${yScale(t0Offset)}`,
                        ...n.future_returns.map((v, i) => `${xScale(t0Index + i + 1)},${yScale(v + t0Offset)}`)
                    ].join(' ');
                    const finalReturn = n.future_returns[n.future_returns.length - 1];
                    const isUp = finalReturn > 0;
                    return (
                        <polyline
                            key={idx}
                            points={pts}
                            fill="none"
                            stroke={isUp ? '#64748b' : '#64748b'}
                            strokeWidth="1"
                            opacity="0.25"
                        />
                    );
                })}

                {/* Confidence band (after t₀) */}
                <path d={bandPath} fill="rgba(59, 130, 246, 0.08)" />

                {/* Query pattern line (before t₀) */}
                {queryLine && (
                    <polyline
                        points={queryLine}
                        fill="none"
                        stroke="#1e293b"
                        strokeWidth="2"
                        strokeLinecap="round"
                    />
                )}

                {/* Forecast mean line (after t₀) - dashed blue, WITH OFFSET for continuity */}
                <polyline
                    points={`${xScale(t0Index)},${yScale(t0Offset)} ${forecastLine}`}
                    fill="none"
                    stroke="#3b82f6"
                    strokeWidth="2"
                    strokeDasharray="6,3"
                    strokeLinecap="round"
                />

                {/* Actual line (after t₀) - solid green/red, WITH OFFSET for continuity */}
                {showActual && actual?.returns && actual.returns.length > 0 && (
                    <>
                        <polyline
                            points={[
                                `${xScale(t0Index)},${yScale(t0Offset)}`,
                                ...actual.returns.map((v, i) => `${xScale(t0Index + i + 1)},${yScale(v + t0Offset)}`)
                            ].join(' ')}
                            fill="none"
                            stroke={actual.final_return >= 0 ? '#10b981' : '#ef4444'}
                            strokeWidth="2.5"
                            strokeLinecap="round"
                        />
                        {/* Actual end marker */}
                        <circle
                            cx={xScale(t0Index + actual.returns.length)}
                            cy={yScale(actual.final_return + t0Offset)}
                            r="5"
                            fill={actual.final_return >= 0 ? '#10b981' : '#ef4444'}
                            stroke="white"
                            strokeWidth="2"
                        />
                        {/* Actual end value label */}
                        <text
                            x={xScale(t0Index + actual.returns.length) + 10}
                            y={yScale(actual.final_return + t0Offset) - 8}
                            fill={actual.final_return >= 0 ? '#10b981' : '#ef4444'}
                            fontWeight="700"
                            style={{ fontSize: '11px' }}
                        >
                            {actual.final_return >= 0 ? '+' : ''}{actual.final_return.toFixed(2)}%
                        </text>
                    </>
                )}

                {/* Forecast end marker - WITH OFFSET */}
                <circle
                    cx={xScale(totalLength - 1)}
                    cy={yScale(forecast.mean_return + t0Offset)}
                    r="4"
                    fill={forecast.mean_return >= 0 ? '#10b981' : '#ef4444'}
                    stroke="white"
                    strokeWidth="2"
                    opacity={showActual && actual ? 0.5 : 1}
                />

                {/* Forecast end value label */}
                <text
                    x={xScale(totalLength - 1) + 8}
                    y={yScale(forecast.mean_return + t0Offset) + 4}
                    fill={forecast.mean_return >= 0 ? '#10b981' : '#ef4444'}
                    fontWeight="600"
                    style={{ fontSize: '11px' }}
                    opacity={showActual && actual ? 0.5 : 1}
                >
                    {forecast.mean_return >= 0 ? '+' : ''}{forecast.mean_return.toFixed(2)}%
                </text>

                {/* t₀ marker dot */}
                <circle
                    cx={xScale(t0Index)}
                    cy={yScale(queryPattern ? queryPattern[queryPattern.length - 1] : 0)}
                    r="3"
                    fill="#1e293b"
                    stroke="white"
                    strokeWidth="1.5"
                />
            </svg>
        </div>
    );
}

// Live Forecast Chart - Enhanced design for realtime mode
function LiveForecastChart({
    forecast,
    neighbors,
    symbol,
}: {
    forecast: PatternForecast;
    neighbors: PatternNeighbor[];
    symbol: string;
}) {
    const width = 600;
    const height = 220;
    const padding = { top: 35, right: 55, bottom: 35, left: 55 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    const afterLength = forecast.mean_trajectory.length;
    const t0Index = 0; // Start from now

    const { maxAbs, xScale, yScale } = useMemo(() => {
        const allVals: number[] = [];

        // Neighbor values
        neighbors.slice(0, 30).forEach(n => {
            allVals.push(...n.future_returns);
        });
        // Forecast + std band
        allVals.push(...forecast.mean_trajectory.map((m, i) => m + forecast.std_trajectory[i]));
        allVals.push(...forecast.mean_trajectory.map((m, i) => m - forecast.std_trajectory[i]));

        const mAbs = Math.max(
            Math.abs(Math.min(...allVals, -0.5)),
            Math.abs(Math.max(...allVals, 0.5)),
            0.5
        );

        const xS = (i: number) => padding.left + (i / (afterLength - 1)) * chartWidth;
        const yS = (v: number) => padding.top + chartHeight / 2 - (v / mAbs) * (chartHeight / 2);

        return { maxAbs: mAbs, xScale: xS, yScale: yS };
    }, [forecast, neighbors, afterLength, chartWidth, chartHeight]);

    // Generate paths
    const forecastLine = forecast.mean_trajectory
        .map((v, i) => `${xScale(i)},${yScale(v)}`)
        .join(' ');

    const upperBand = forecast.mean_trajectory
        .map((m, i) => `${xScale(i)},${yScale(m + forecast.std_trajectory[i])}`)
        .join(' ');
    const lowerBand = forecast.mean_trajectory
        .map((m, i) => `${xScale(i)},${yScale(m - forecast.std_trajectory[i])}`)
        .reverse()
        .join(' ');
    const bandPath = `M${upperBand} L${lowerBand} Z`;

    // Current time string
    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });

    return (
        <div className="relative">
            {/* Header */}
            <div className="flex items-center justify-between mb-2 px-1">
                <span className="text-slate-600 font-medium" style={{ fontSize: '11px' }}>
                    {symbol} — Live pattern @ {timeStr}
                </span>
                <div className="flex items-center gap-4" style={{ fontSize: '10px' }}>
                    <span className="flex items-center gap-1">
                        <span className="w-3 h-0.5 bg-blue-500 inline-block"></span>
                        <span className="text-slate-500">Forecast</span>
                    </span>
                    <span className="flex items-center gap-1">
                        <span className="w-3 h-0.5 bg-slate-400 inline-block opacity-50"></span>
                        <span className="text-slate-500">Neighbors</span>
                    </span>
                    <span className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                        <span className="text-emerald-600 font-medium">Live</span>
                    </span>
                </div>
            </div>

            <svg width={width} height={height} className="block">
                {/* Background gradient - subtle future projection area */}
                <defs>
                    <linearGradient id="futureGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stopColor="#f8fafc" />
                        <stop offset="100%" stopColor="#fefefe" />
                    </linearGradient>
                </defs>
                <rect
                    x={padding.left}
                    y={padding.top}
                    width={chartWidth}
                    height={chartHeight}
                    fill="url(#futureGradient)"
                />

                {/* Grid lines */}
                {[-maxAbs, -maxAbs / 2, 0, maxAbs / 2, maxAbs].map((v, i) => (
                    <g key={i}>
                        <line
                            x1={padding.left}
                            y1={yScale(v)}
                            x2={padding.left + chartWidth}
                            y2={yScale(v)}
                            stroke={v === 0 ? '#94a3b8' : '#e2e8f0'}
                            strokeWidth={v === 0 ? 1 : 0.5}
                        />
                        <text
                            x={padding.left - 8}
                            y={yScale(v) + 3}
                            textAnchor="end"
                            fill="#94a3b8"
                            style={{ fontSize: '9px' }}
                        >
                            {v > 0 ? '+' : ''}{v.toFixed(2)}%
                        </text>
                    </g>
                ))}

                {/* t₀ "NOW" vertical line at start */}
                <line
                    x1={padding.left}
                    y1={padding.top - 5}
                    x2={padding.left}
                    y2={padding.top + chartHeight + 5}
                    stroke="#3b82f6"
                    strokeWidth="2"
                />
                <text
                    x={padding.left}
                    y={padding.top - 10}
                    textAnchor="middle"
                    fill="#3b82f6"
                    fontWeight="600"
                    style={{ fontSize: '10px' }}
                >
                    NOW
                </text>

                {/* X axis time labels */}
                {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => {
                    const min = Math.round(pct * forecast.horizon_minutes);
                    const idx = Math.floor(pct * (afterLength - 1));
                    return (
                        <text
                            key={i}
                            x={xScale(idx)}
                            y={height - 10}
                            textAnchor="middle"
                            fill="#94a3b8"
                            style={{ fontSize: '9px' }}
                        >
                            {pct === 0 ? 't₀' : `+${min}m`}
                        </text>
                    );
                })}

                {/* Neighbor trajectories */}
                {neighbors.slice(0, 30).map((n, idx) => {
                    const pts = n.future_returns.map((v, i) => `${xScale(i)},${yScale(v)}`).join(' ');
                    const finalReturn = n.future_returns[n.future_returns.length - 1];
                    const isUp = finalReturn > 0;
                    return (
                        <polyline
                            key={idx}
                            points={pts}
                            fill="none"
                            stroke={isUp ? '#10b981' : '#ef4444'}
                            strokeWidth="1"
                            opacity="0.2"
                        />
                    );
                })}

                {/* Confidence band */}
                <path d={bandPath} fill="rgba(59, 130, 246, 0.1)" />

                {/* Forecast mean line - solid blue */}
                <polyline
                    points={forecastLine}
                    fill="none"
                    stroke="#3b82f6"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                />

                {/* Start marker at t₀ */}
                <circle
                    cx={xScale(0)}
                    cy={yScale(0)}
                    r="4"
                    fill="#3b82f6"
                    stroke="white"
                    strokeWidth="2"
                />

                {/* End marker */}
                <circle
                    cx={xScale(afterLength - 1)}
                    cy={yScale(forecast.mean_return)}
                    r="5"
                    fill={forecast.mean_return >= 0 ? '#10b981' : '#ef4444'}
                    stroke="white"
                    strokeWidth="2"
                />

                {/* End value label */}
                <text
                    x={xScale(afterLength - 1) + 10}
                    y={yScale(forecast.mean_return) + 4}
                    fill={forecast.mean_return >= 0 ? '#10b981' : '#ef4444'}
                    fontWeight="600"
                    style={{ fontSize: '12px' }}
                >
                    {forecast.mean_return >= 0 ? '+' : ''}{forecast.mean_return.toFixed(2)}%
                </text>

                {/* Horizon label */}
                <text
                    x={padding.left + chartWidth}
                    y={padding.top - 10}
                    textAnchor="end"
                    fill="#64748b"
                    style={{ fontSize: '10px' }}
                >
                    +{forecast.horizon_minutes}min forecast
                </text>
            </svg>
        </div>
    );
}

// ============================================================================
// Main Component
// ============================================================================

export function PatternMatchingContent({ initialTicker }: { initialTicker?: string }) {
    const { openWindow } = useFloatingWindow();
    const font = useUserPreferencesStore(selectFont);
    const fontFamily = `var(--font-${font})`;

    const [ticker, setTicker] = useState(initialTicker || '');
    const [mode, setMode] = useState<SearchMode>('historical');
    const [k, setK] = useState(50);
    const [crossAsset, setCrossAsset] = useState(true);
    const [windowMinutes, setWindowMinutes] = useState(45);

    const [historicalDate, setHistoricalDate] = useState('');
    const [historicalTime, setHistoricalTime] = useState('15:00');
    const [availableDates, setAvailableDates] = useState<AvailableDates | null>(null);

    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [result, setResult] = useState<SearchResult | null>(null);
    const [indexStats, setIndexStats] = useState<IndexStats | null>(null);
    const [showSettings, setShowSettings] = useState(false);
    const [showActual, setShowActual] = useState(false);
    const [showVisualSelector, setShowVisualSelector] = useState(false);
    const [visualSelection, setVisualSelection] = useState<{ start: string | null, end: string | null, minutes: number }>({ start: null, end: null, minutes: 0 });

    useEffect(() => {
        const fetchData = async () => {
            try {
                console.log('[PM] Fetching from:', API_BASE);
                const [statsRes, datesRes] = await Promise.all([
                    fetch(`${API_BASE}/api/index/stats`),
                    fetch(`${API_BASE}/api/available-dates`),
                ]);
                console.log('[PM] Stats status:', statsRes.status, 'Dates status:', datesRes.status);
                if (statsRes.ok) setIndexStats(await statsRes.json());
                if (datesRes.ok) {
                    const dates = await datesRes.json();
                    console.log('[PM] Dates loaded:', dates?.dates?.length, 'Last:', dates?.last);
                    setAvailableDates(dates);
                    if (dates.last) setHistoricalDate(dates.last);
                } else {
                    console.error('[PM] Failed to load dates:', datesRes.status);
                }
            } catch (e) {
                console.error('[PM] Init error:', e);
            }
        };
        fetchData();
    }, []);

    const handleSearch = useCallback(async () => {
        if (!ticker.trim()) {
            setError('Enter a ticker');
            return;
        }

        setLoading(true);
        setError(null);
        setResult(null); // Clear previous result

        try {
            let res: Response;

            if (mode === 'historical') {
                if (!historicalDate || !historicalTime) {
                    throw new Error('Select date and time');
                }
                res = await fetch(`${API_BASE}/api/search/historical`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        symbol: ticker.toUpperCase(),
                        date: historicalDate,
                        time: historicalTime,
                        k,
                        cross_asset: crossAsset,
                        window_minutes: windowMinutes,
                    }),
                });
            } else {
                res = await fetch(`${API_BASE}/api/search/${ticker.toUpperCase()}?k=${k}&cross_asset=${crossAsset}`);
            }

            const data = await res.json();
            console.log('Pattern search response:', data);

            if (!res.ok) {
                const msg = data.detail || 'Search failed';
                if (msg.includes('insufficient') || msg.includes('Insufficient')) {
                    throw new Error(`Not enough data on ${historicalDate}. Try earlier time or different date.`);
                }
                throw new Error(msg);
            }
            if (data.status === 'error' || data.status === 'insufficient_data' || data.status === 'not_ready') {
                const msg = data.error || 'Search failed';
                if (msg.includes('insufficient') || msg.includes('Insufficient') || msg.includes('Need at least')) {
                    throw new Error(`Not enough data on ${historicalDate}. Try earlier time (before 16:00) or different date.`);
                }
                if (msg.includes('No')) {
                    throw new Error(mode === 'realtime' ? 'Market closed. Use Historical mode.' : `No data for ${ticker} on ${historicalDate}`);
                }
                throw new Error(msg);
            }

            setResult(data);
        } catch (e: any) {
            setError(e.message);
            setResult(null);
        } finally {
            setLoading(false);
        }
    }, [ticker, mode, k, crossAsset, historicalDate, historicalTime, windowMinutes]);

    const handleTickerSelect = useCallback((selected: TickerSearchResult) => {
        setTicker(selected.symbol);
    }, []);

    const handleExpandChart = useCallback(() => {
        if (!result?.forecast) return;
        openWindow({
            title: `${result.query.symbol} Forecast`,
            content: (
                <ExpandedChart
                    forecast={result.forecast}
                    neighbors={result.neighbors}
                    historicalContext={result.historical_context}
                    symbol={result.query.symbol}
                    date={result.query.date}
                    actual={result.actual}
                    showActual={showActual}
                />
            ),
            width: 800,
            height: 550,
            x: 150,
            y: 100,
            minWidth: 700,
            minHeight: 450,
        });
    }, [result, openWindow, showActual]);

    // Handler for visual selection change (doesn't search, just updates state)
    const handleVisualSelectionChange = useCallback((startTime: string | null, endTime: string | null, minutes: number) => {
        setVisualSelection({ start: startTime, end: endTime, minutes });
        if (startTime) {
            setHistoricalTime(startTime);
            setWindowMinutes(minutes);
        }
    }, []);

    return (
        <div className="h-full flex flex-col bg-white text-slate-800" style={{ fontFamily }}>
            {/* Search Bar */}
            <div className="flex-shrink-0 px-4 py-3 border-b border-slate-100">
                <div className="flex gap-2 items-center">
                    <div className="flex-1">
                        <TickerSearch
                            value={ticker}
                            onChange={setTicker}
                            onSelect={handleTickerSelect}
                            placeholder="Ticker"
                            className="w-full"
                            autoFocus
                        />
                    </div>

                    {mode === 'historical' && (
                        <div className="flex items-center text-slate-500" style={{ fontSize: '10px', fontFamily }}>
                            <select
                                value={historicalDate}
                                onChange={(e) => setHistoricalDate(e.target.value)}
                                className="bg-transparent border-none outline-none cursor-pointer text-slate-600 hover:text-slate-800 appearance-none pr-1"
                                style={{ fontSize: '10px', fontFamily }}
                                disabled={!availableDates}
                            >
                                {!availableDates ? (
                                    <option value="">...</option>
                                ) : !historicalDate ? (
                                    <option value="">date</option>
                                ) : null}
                                {availableDates?.dates?.slice(-60).reverse().map((d) => (
                                    <option key={d} value={d}>{d}</option>
                                ))}
                            </select>
                            <span className="text-slate-300 mx-0.5">@</span>
                            <input
                                type="text"
                                value={historicalTime}
                                onChange={(e) => setHistoricalTime(e.target.value)}
                                placeholder="15:00"
                                className="bg-transparent border-none outline-none text-slate-600 hover:text-slate-800 w-[38px] text-center"
                                style={{ fontSize: '10px', fontFamily }}
                            />
                        </div>
                    )}

                    <div className="flex items-center gap-1 text-slate-400" style={{ fontSize: '9px', fontFamily }}>
                        <button
                            onClick={() => setMode('realtime')}
                            className={`px-1.5 py-0.5 rounded ${mode === 'realtime' ? 'bg-slate-100 text-slate-700' : 'hover:text-slate-600'}`}
                        >
                            live
                        </button>
                        <span className="text-slate-200">|</span>
                        <button
                            onClick={() => setMode('historical')}
                            className={`px-1.5 py-0.5 rounded ${mode === 'historical' ? 'bg-slate-100 text-slate-700' : 'hover:text-slate-600'}`}
                        >
                            hist
                        </button>
                        {mode === 'historical' && (
                            <>
                                <span className="text-slate-200">|</span>
                                <button
                                    onClick={() => setShowVisualSelector(!showVisualSelector)}
                                    className={`px-1.5 py-0.5 rounded ${showVisualSelector ? 'bg-slate-100 text-slate-700' : 'hover:text-slate-600'}`}
                                    title="Visual selector"
                                >
                                    chart
                                </button>
                            </>
                        )}
                    </div>

                    <button
                        onClick={() => setShowSettings(!showSettings)}
                        className={`p-1.5 rounded border ${showSettings ? 'border-blue-300 bg-blue-50 text-blue-600' : 'border-slate-200 text-slate-400'}`}
                    >
                        <Settings2 className="w-4 h-4" />
                    </button>

                    <button
                        onClick={handleSearch}
                        disabled={loading || !ticker.trim()}
                        className="px-3 py-1.5 rounded bg-blue-500 text-white font-medium hover:bg-blue-600 disabled:opacity-50 flex items-center gap-1.5"
                        style={{ fontSize: '11px' }}
                    >
                        {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
                        Search
                    </button>
                </div>

                {showSettings && (
                    <div className="mt-2 pt-2 border-t border-slate-100 flex gap-4" style={{ fontSize: '10px' }}>
                        <div className="flex items-center gap-1">
                            <span className="text-slate-400">k:</span>
                            <input
                                type="number"
                                value={k}
                                onChange={(e) => setK(Math.min(200, Math.max(1, parseInt(e.target.value) || 50)))}
                                className="w-10 px-1 py-0.5 rounded border border-slate-200"
                            />
                        </div>
                        <div className="flex items-center gap-1">
                            <span className="text-slate-400">Window:</span>
                            <input
                                type="number"
                                value={windowMinutes}
                                onChange={(e) => setWindowMinutes(Math.min(120, Math.max(15, parseInt(e.target.value) || 45)))}
                                className="w-10 px-1 py-0.5 rounded border border-slate-200"
                            />
                            <span className="text-slate-400">min</span>
                        </div>
                        <button
                            onClick={() => setCrossAsset(!crossAsset)}
                            className={`px-2 py-0.5 rounded border ${crossAsset ? 'border-blue-300 bg-blue-50 text-blue-600' : 'border-slate-200 text-slate-500'}`}
                        >
                            {crossAsset ? 'Cross-asset' : 'Same ticker'}
                        </button>
                    </div>
                )}

                {/* Visual Pattern Selector */}
                {showVisualSelector && mode === 'historical' && ticker && historicalDate && (
                    <div className="mt-3 pt-3 border-t border-slate-100">
                        <CandlestickSelector
                            symbol={ticker.toUpperCase()}
                            date={historicalDate}
                            onSelectionChange={handleVisualSelectionChange}
                            fontFamily={fontFamily}
                            maxMinutes={120}
                        />
                    </div>
                )}
            </div>

            {/* Content - Pizarra */}
            <div className="flex-1 overflow-auto px-4 py-4">
                {error && (
                    <div className="flex items-center gap-2 text-red-600 mb-4" style={{ fontSize: '11px' }}>
                        <AlertCircle className="w-4 h-4" />
                        {error}
                    </div>
                )}

                {!result && !loading && !error && (
                    <div className="h-full flex flex-col items-center justify-center text-slate-400">
                        <Search className="w-8 h-8 mb-2 opacity-30" />
                        <p style={{ fontSize: '12px' }}>Search a ticker to find similar patterns</p>
                    </div>
                )}

                {loading && (
                    <div className="h-full flex flex-col items-center justify-center text-slate-400">
                        <Loader2 className="w-6 h-6 animate-spin mb-2" />
                        <p style={{ fontSize: '11px' }}>Searching {indexStats ? `${(indexStats.n_vectors / 1_000_000).toFixed(1)}M` : ''} patterns...</p>
                    </div>
                )}

                {result && result.forecast && (
                    <div className="space-y-5">
                        {/* Header */}
                        <div className="flex items-baseline justify-between">
                            <div className="flex items-baseline gap-3">
                                <span className="text-xl font-semibold text-slate-800">{result.query.symbol}</span>
                                {result.query.date && (
                                    <span className="text-slate-400" style={{ fontSize: '11px' }}>{result.query.date}</span>
                                )}
                            </div>
                            <span className="text-slate-400" style={{ fontSize: '10px' }}>
                                {result.stats?.query_time_ms?.toFixed(1) || '0'}ms · {result.forecast.n_neighbors || 0} matches
                            </span>
                        </div>

                        {/* Probability Bar - only show if we have valid forecast data */}
                        {'error' in result.forecast ? (
                            <div className="text-center py-4 text-slate-400" style={{ fontSize: '12px' }}>
                                <span>No se encontraron patrones similares con datos históricos completos</span>
                            </div>
                        ) : (
                        <>
                        <div>
                            <div className="flex items-center justify-between mb-1.5">
                                <div className="flex items-center gap-1.5 text-emerald-600" style={{ fontSize: '12px' }}>
                                    <TrendingUp className="w-4 h-4" />
                                    <span className="font-semibold">{((result.forecast.prob_up ?? 0) * 100).toFixed(0)}%</span>
                                    <span className="text-slate-400 font-normal">bullish</span>
                                </div>
                                <div className="flex items-center gap-1.5 text-red-500" style={{ fontSize: '12px' }}>
                                    <span className="text-slate-400 font-normal">bearish</span>
                                    <span className="font-semibold">{((result.forecast.prob_down ?? 0) * 100).toFixed(0)}%</span>
                                    <TrendingDown className="w-4 h-4" />
                                </div>
                            </div>
                            <div className="h-2.5 rounded-full overflow-hidden bg-slate-100 flex">
                                <div className="bg-emerald-500 transition-all" style={{ width: `${(result.forecast.prob_up ?? 0) * 100}%` }} />
                                <div className="bg-red-500 transition-all" style={{ width: `${(result.forecast.prob_down ?? 0) * 100}%` }} />
                            </div>
                        </div>

                        {/* Stats Row */}
                        <div className="flex gap-6" style={{ fontSize: '11px' }}>
                            <div>
                                <span className="text-slate-400">Mean</span>
                                <span className={`ml-1.5 font-mono font-semibold ${(result.forecast.mean_return ?? 0) >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                                    {(result.forecast.mean_return ?? 0) >= 0 ? '+' : ''}{(result.forecast.mean_return ?? 0).toFixed(2)}%
                                </span>
                            </div>
                            <div>
                                <span className="text-slate-400">Median</span>
                                <span className={`ml-1.5 font-mono font-semibold ${(result.forecast.median_return ?? 0) >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                                    {(result.forecast.median_return ?? 0) >= 0 ? '+' : ''}{(result.forecast.median_return ?? 0).toFixed(2)}%
                                </span>
                            </div>
                            <div>
                                <span className="text-slate-400">Best</span>
                                <span className="ml-1.5 font-mono font-semibold text-emerald-600">+{(result.forecast.best_case ?? 0).toFixed(2)}%</span>
                            </div>
                            <div>
                                <span className="text-slate-400">Worst</span>
                                <span className="ml-1.5 font-mono font-semibold text-red-500">{(result.forecast.worst_case ?? 0).toFixed(2)}%</span>
                            </div>
                            <div>
                                <span className="text-slate-400">Confidence</span>
                                <span className={`ml-1.5 font-semibold ${result.forecast.confidence === 'high' ? 'text-emerald-600' :
                                    result.forecast.confidence === 'medium' ? 'text-amber-500' : 'text-slate-500'
                                    }`}>
                                    {result.forecast.confidence ?? 'N/A'}
                                </span>
                            </div>
                        </div>
                        </>
                        )}

                        {/* Chart */}
                        <div className="py-2">
                            {/* Controls row - above chart */}
                            <div className="flex items-center justify-end gap-2 mb-2">
                                {/* Show Actual toggle - only when actual data exists */}
                                {result.actual && result.historical_context && (
                                    <label className="flex items-center gap-1.5 px-2 py-0.5 rounded border border-slate-200 bg-white cursor-pointer hover:border-blue-300 transition-colors" style={{ fontSize: '10px' }}>
                                        <input
                                            type="checkbox"
                                            checked={showActual}
                                            onChange={(e) => setShowActual(e.target.checked)}
                                            className="w-3 h-3 rounded border-slate-300 text-blue-500 focus:ring-blue-500"
                                        />
                                        <span className="text-slate-500">Actual</span>
                                        {showActual && (
                                            <span className={`font-mono font-semibold ${result.actual.final_return >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                                                {result.actual.final_return >= 0 ? '+' : ''}{result.actual.final_return.toFixed(2)}%
                                            </span>
                                        )}
                                    </label>
                                )}
                                <button
                                    onClick={handleExpandChart}
                                    className="p-1 rounded border border-slate-200 bg-white text-slate-400 hover:text-blue-500 hover:border-blue-300 transition-colors"
                                    title="Expand chart"
                                >
                                    <Maximize2 className="w-3.5 h-3.5" />
                                </button>
                            </div>
                            {/* Chart */}
                            <div className="flex justify-center">
                                {result.historical_context ? (
                                    <GodelChart
                                        forecast={result.forecast}
                                        neighbors={result.neighbors}
                                        historicalContext={result.historical_context}
                                        symbol={result.query.symbol}
                                        date={result.query.date}
                                        actual={result.actual}
                                        showActual={showActual}
                                    />
                                ) : (
                                    <LiveForecastChart
                                        forecast={result.forecast}
                                        neighbors={result.neighbors}
                                        symbol={result.query.symbol}
                                    />
                                )}
                            </div>
                        </div>

                        {/* Similar Patterns */}
                        <div>
                            <div className="text-slate-400 mb-2" style={{ fontSize: '10px' }}>
                                Similar patterns ({result.neighbors.length})
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                                {result.neighbors.slice(0, 20).map((n, i) => {
                                    const ret = n.future_returns && n.future_returns.length > 0
                                        ? n.future_returns[n.future_returns.length - 1]
                                        : 0;
                                    const isUp = ret > 0;
                                    return (
                                        <div
                                            key={i}
                                            className={`px-2 py-1 rounded ${isUp ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}
                                            style={{ fontSize: '10px' }}
                                            title={`${n.date} ${n.start_time}-${n.end_time}`}
                                        >
                                            <span className="font-medium">{n.symbol}</span>
                                            <span className="ml-1 font-mono">{isUp ? '+' : ''}{ret.toFixed(1)}%</span>
                                        </div>
                                    );
                                })}
                                {result.neighbors.length > 20 && (
                                    <span className="px-2 py-1 text-slate-400" style={{ fontSize: '10px' }}>
                                        +{result.neighbors.length - 20}
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* Footer */}
            <div className="flex-shrink-0 px-4 py-1 border-t border-slate-100 flex items-center justify-between text-slate-400" style={{ fontSize: '9px' }}>
                <div className="flex items-center gap-2">
                    <Clock className="w-3 h-3" />
                    <span>{windowMinutes}min · {crossAsset ? 'cross-asset' : 'same ticker'}</span>
                </div>
                <span className="font-mono">FAISS</span>
            </div>
        </div>
    );
}

export default PatternMatchingContent;
