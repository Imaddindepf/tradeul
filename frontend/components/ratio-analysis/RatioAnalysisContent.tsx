'use client';

import { useState, useCallback, useEffect, useMemo } from 'react';
import {
    Search,
    Loader2,
    AlertCircle,
    Settings2,
    TrendingUp,
    TrendingDown,
    ArrowRightLeft,
} from 'lucide-react';
import {
    ComposedChart,
    Line,
    Area,
    XAxis,
    YAxis,
    Tooltip,
    ResponsiveContainer,
    CartesianGrid,
    ReferenceLine,
    ReferenceDot,
    ScatterChart,
    Scatter,
    Cell,
} from 'recharts';
import { TickerSearch } from '@/components/common/TickerSearch';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';

// ============================================================================
// Types
// ============================================================================

interface RatioAnalysisData {
    status: string;
    symbols: { y: string; x: string };
    period: string;
    data_points: number;
    prices: {
        dates: string[];
        y: { symbol: string; values: number[]; latest: number };
        x: { symbol: string; values: number[]; latest: number };
    };
    ratio: {
        values: number[];
        latest: number;
        min: { value: number; date: string; index: number };
        max: { value: number; date: string; index: number };
    };
    correlation: {
        window: number;
        dates: string[];
        values: number[];
        latest: number;
        min: number;
        max: number;
    };
    regression: {
        beta: number;
        alpha: number;
        r_squared: number;
        pearson_r: number;
        std_error: number;
        std_error_alpha: number;
        std_error_beta: number;
    } | null;
    scatter: { x: number; y: number }[];
    // New advanced metrics
    zscore?: {
        lookback: number;
        values: number[];
        current: number;
        mean: number;
        std: number;
        signal: string;
        signal_strength: number;
        upper_band: number;
        lower_band: number;
    };
    half_life?: number | null;
    hedge_ratio?: {
        beta_hedge: number;
        example: {
            capital: number;
            shares_y: number;
            shares_x: number;
            dollar_y: number;
            dollar_x: number;
            net_exposure: number;
        };
    };
    rolling_beta?: {
        window: number;
        dates: string[];
        values: number[];
        latest: number;
        min: number;
        max: number;
    };
    volatility?: {
        y_annual: number;
        x_annual: number;
        ratio: number;
        y_daily: number;
        x_daily: number;
    };
    backtest?: {
        total_trades: number;
        win_rate: number;
        avg_pnl: number;
        total_pnl: number;
        avg_duration: number;
        sharpe: number;
        max_drawdown: number;
        best_trade: number;
        worst_trade: number;
    } | null;
    summary?: {
        signal: string;
        signal_strength: number;
        zscore: number;
        half_life_days: number | null;
        correlation: number;
        beta: number;
        r_squared: number;
        vol_ratio: number;
        recommendation: string;
    };
}

type Period = '1M' | '3M' | '6M' | '1Y' | '2Y';

type TickerSearchResult = {
    symbol: string;
    name: string;
    exchange: string;
    type: string;
    displayName: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Custom triangle markers for min/max
const TriangleDown = (props: any) => {
    const { cx, cy, fill = '#f43f5e' } = props;
    if (!cx || !cy) return null;
    return (
        <polygon
            points={`${cx},${cy + 6} ${cx - 5},${cy - 4} ${cx + 5},${cy - 4}`}
            fill={fill}
            stroke="#fff"
            strokeWidth={1.5}
        />
    );
};

const TriangleUp = (props: any) => {
    const { cx, cy, fill = '#10b981' } = props;
    if (!cx || !cy) return null;
    return (
        <polygon
            points={`${cx},${cy - 6} ${cx - 5},${cy + 4} ${cx + 5},${cy + 4}`}
            fill={fill}
            stroke="#fff"
            strokeWidth={1.5}
        />
    );
};

const PERIODS: { id: Period; label: string }[] = [
    { id: '1M', label: '1M' },
    { id: '3M', label: '3M' },
    { id: '6M', label: '6M' },
    { id: '1Y', label: '1Y' },
    { id: '2Y', label: '2Y' },
];

// ============================================================================
// Chart Components
// ============================================================================

// Price Comparison Chart (Panel 1)
function PriceChart({ data }: { data: RatioAnalysisData }) {
    const chartData = useMemo(() => {
        return data.prices.dates.map((date, i) => ({
            date,
            dateShort: date.slice(5), // MM-DD
            y: data.prices.y.values[i],
            x: data.prices.x.values[i],
        }));
    }, [data]);

    // Normalize prices to percentage change from first value
    const normalizedData = useMemo(() => {
        if (chartData.length === 0) return [];
        const firstY = chartData[0].y;
        const firstX = chartData[0].x;
        
        const normalized = chartData.map(d => ({
            ...d,
            yNorm: ((d.y / firstY) - 1) * 100,
            xNorm: ((d.x / firstX) - 1) * 100,
        }));
        
        // Find min/max indices
        const yValues = normalized.map(d => d.yNorm);
        const xValues = normalized.map(d => d.xNorm);
        const yMinIdx = yValues.indexOf(Math.min(...yValues));
        const yMaxIdx = yValues.indexOf(Math.max(...yValues));
        const xMinIdx = xValues.indexOf(Math.min(...xValues));
        const xMaxIdx = xValues.indexOf(Math.max(...xValues));
        
        return normalized.map((d, i) => ({
            ...d,
            yIsMin: i === yMinIdx,
            yIsMax: i === yMaxIdx,
            xIsMin: i === xMinIdx,
            xIsMax: i === xMaxIdx,
        }));
    }, [chartData]);

    return (
        <div className="h-[180px]">
            <div className="flex items-center justify-between px-3 py-1 border-b border-slate-100">
                <div className="flex items-center gap-4 text-[10px]">
                    <span className="flex items-center gap-1.5">
                        <span className="w-3 h-0.5 bg-rose-500 rounded"></span>
                        <span className="text-rose-600 font-medium">{data.symbols.y}</span>
                        <span className="text-slate-500 text-[9px]">(buy)</span>
                        <span className="text-slate-400">${data.prices.y.latest}</span>
                    </span>
                    <span className="flex items-center gap-1.5">
                        <span className="w-3 h-0.5 bg-cyan-500 rounded"></span>
                        <span className="text-cyan-600 font-medium">{data.symbols.x}</span>
                        <span className="text-slate-500 text-[9px]">(sell)</span>
                        <span className="text-slate-400">${data.prices.x.latest}</span>
                    </span>
                </div>
                <div className="flex items-center gap-2 text-[9px] text-slate-400">
                    <span className="flex items-center gap-0.5">
                        <span className="text-rose-500">▼</span>Min
                    </span>
                    <span className="flex items-center gap-0.5">
                        <span className="text-emerald-500">▲</span>Max
                    </span>
                </div>
            </div>
            <ResponsiveContainer width="100%" height="85%">
                <ComposedChart data={normalizedData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                    <XAxis
                        dataKey="dateShort"
                        tick={{ fontSize: 9, fill: '#94a3b8' }}
                        tickLine={false}
                        axisLine={{ stroke: '#e2e8f0' }}
                        interval="preserveStartEnd"
                    />
                    <YAxis
                        tick={{ fontSize: 9, fill: '#94a3b8' }}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v) => v != null ? `${v > 0 ? '+' : ''}${v.toFixed(0)}%` : ''}
                        width={45}
                    />
                    <Tooltip
                        contentStyle={{
                            backgroundColor: '#1e293b',
                            border: 'none',
                            borderRadius: '6px',
                            fontSize: '11px',
                            padding: '8px 12px',
                            color: '#f1f5f9',
                        }}
                        labelStyle={{ color: '#94a3b8', marginBottom: '4px' }}
                        itemStyle={{ color: '#f1f5f9' }}
                        formatter={(value: number, name: string) => [
                            value != null ? `${value > 0 ? '+' : ''}${value.toFixed(2)}%` : '-',
                            name === 'yNorm' ? data.symbols.y : data.symbols.x
                        ]}
                    />
                    <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="3 3" />
                    <Line
                        type="monotone"
                        dataKey="yNorm"
                        stroke="#f43f5e"
                        strokeWidth={2}
                        dot={false}
                        name="yNorm"
                    />
                    <Line
                        type="monotone"
                        dataKey="xNorm"
                        stroke="#06b6d4"
                        strokeWidth={2}
                        dot={false}
                        name="xNorm"
                    />
                    {/* Y (buy) min/max markers */}
                    <Line
                        type="monotone"
                        dataKey={(d: any) => d.yIsMin ? d.yNorm : null}
                        stroke="none"
                        dot={<TriangleDown fill="#f43f5e" />}
                        isAnimationActive={false}
                    />
                    <Line
                        type="monotone"
                        dataKey={(d: any) => d.yIsMax ? d.yNorm : null}
                        stroke="none"
                        dot={<TriangleUp fill="#f43f5e" />}
                        isAnimationActive={false}
                    />
                    {/* X (sell) min/max markers */}
                    <Line
                        type="monotone"
                        dataKey={(d: any) => d.xIsMin ? d.xNorm : null}
                        stroke="none"
                        dot={<TriangleDown fill="#06b6d4" />}
                        isAnimationActive={false}
                    />
                    <Line
                        type="monotone"
                        dataKey={(d: any) => d.xIsMax ? d.xNorm : null}
                        stroke="none"
                        dot={<TriangleUp fill="#06b6d4" />}
                        isAnimationActive={false}
                    />
                </ComposedChart>
            </ResponsiveContainer>
        </div>
    );
}

// Ratio Chart (Panel 2)
function RatioChart({ data }: { data: RatioAnalysisData }) {
    const chartData = useMemo(() => {
        return data.prices.dates.map((date, i) => ({
            date,
            dateShort: date.slice(5),
            ratio: data.ratio.values[i],
            isMin: i === data.ratio.min?.index,
            isMax: i === data.ratio.max?.index,
        }));
    }, [data]);

    // Encontrar índices para ReferenceDot
    const minPoint = data.ratio.min?.index != null ? chartData[data.ratio.min.index] : null;
    const maxPoint = data.ratio.max?.index != null ? chartData[data.ratio.max.index] : null;

    return (
        <div className="h-[140px]">
            <div className="flex items-center justify-between px-3 py-1 border-b border-slate-100">
                <div className="flex items-center gap-2 text-[10px]">
                    <span className="text-slate-600 font-medium">{data.symbols.y}/{data.symbols.x}</span>
                    <span className="text-emerald-600 font-mono">{data.ratio.latest?.toFixed(4) ?? '-'}</span>
                </div>
                <div className="flex items-center gap-3 text-[9px]">
                    <span className="text-slate-400 flex items-center gap-1">
                        <TrendingDown className="w-3 h-3 text-rose-500" />
                        Min: <span className="text-rose-500 font-mono">{data.ratio.min?.value?.toFixed(4) ?? '-'}</span>
                    </span>
                    <span className="text-slate-400 flex items-center gap-1">
                        <TrendingUp className="w-3 h-3 text-emerald-500" />
                        Max: <span className="text-emerald-500 font-mono">{data.ratio.max?.value?.toFixed(4) ?? '-'}</span>
                    </span>
                </div>
            </div>
            <ResponsiveContainer width="100%" height="85%">
                <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                        <linearGradient id="ratioGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                    <XAxis
                        dataKey="dateShort"
                        tick={{ fontSize: 9, fill: '#94a3b8' }}
                        tickLine={false}
                        axisLine={{ stroke: '#e2e8f0' }}
                        interval="preserveStartEnd"
                    />
                    <YAxis
                        tick={{ fontSize: 9, fill: '#94a3b8' }}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v) => v != null ? v.toFixed(3) : ''}
                        width={50}
                        domain={['auto', 'auto']}
                    />
                    <Tooltip
                        contentStyle={{
                            backgroundColor: '#1e293b',
                            border: 'none',
                            borderRadius: '6px',
                            fontSize: '11px',
                            color: '#f1f5f9',
                        }}
                        labelStyle={{ color: '#94a3b8' }}
                        itemStyle={{ color: '#f1f5f9' }}
                        formatter={(value: number) => [value != null ? value.toFixed(4) : '-', 'Ratio']}
                    />
                    <Area
                        type="monotone"
                        dataKey="ratio"
                        stroke="#10b981"
                        strokeWidth={2}
                        fill="url(#ratioGradient)"
                    />
                    {/* Min/Max markers */}
                    <Line
                        type="monotone"
                        dataKey={(d: any) => d.isMin ? d.ratio : null}
                        stroke="none"
                        dot={<TriangleDown fill="#f43f5e" />}
                        isAnimationActive={false}
                    />
                    <Line
                        type="monotone"
                        dataKey={(d: any) => d.isMax ? d.ratio : null}
                        stroke="none"
                        dot={<TriangleUp fill="#10b981" />}
                        isAnimationActive={false}
                    />
                </ComposedChart>
            </ResponsiveContainer>
        </div>
    );
}

// Correlation Chart (Panel 3)
function CorrelationChart({ data }: { data: RatioAnalysisData }) {
    const chartData = useMemo(() => {
        const values = data.correlation.values;
        const minVal = Math.min(...values);
        const maxVal = Math.max(...values);
        const minIdx = values.indexOf(minVal);
        const maxIdx = values.indexOf(maxVal);
        
        return data.correlation.dates.map((date, i) => ({
            date,
            dateShort: date.slice(5),
            corr: data.correlation.values[i],
            isMin: i === minIdx,
            isMax: i === maxIdx,
        }));
    }, [data]);
    
    const minCorr = data.correlation.min;
    const maxCorr = data.correlation.max;

    return (
        <div className="h-[140px]">
            <div className="flex items-center justify-between px-3 py-1 border-b border-slate-100">
                <div className="flex items-center gap-2 text-[10px]">
                    <span className="text-slate-600 font-medium">
                        Corr({data.symbols.y}/{data.symbols.x})
                    </span>
                    <span className={`font-mono ${(data.correlation.latest ?? 0) >= 0.7 ? 'text-emerald-600' : (data.correlation.latest ?? 0) >= 0.4 ? 'text-amber-600' : 'text-rose-600'}`}>
                        {data.correlation.latest?.toFixed(3) ?? '-'}
                    </span>
                </div>
                <div className="flex items-center gap-3 text-[9px]">
                    <span className="text-slate-400 flex items-center gap-1">
                        <TrendingDown className="w-3 h-3 text-rose-500" />
                        <span className="text-rose-500 font-mono">{minCorr?.toFixed(2) ?? '-'}</span>
                    </span>
                    <span className="text-slate-400 flex items-center gap-1">
                        <TrendingUp className="w-3 h-3 text-emerald-500" />
                        <span className="text-emerald-500 font-mono">{maxCorr?.toFixed(2) ?? '-'}</span>
                    </span>
                    <span className="text-slate-400">
                        {data.correlation.window}d
                    </span>
                </div>
            </div>
            <ResponsiveContainer width="100%" height="85%">
                <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                        <linearGradient id="corrGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                    <XAxis
                        dataKey="dateShort"
                        tick={{ fontSize: 9, fill: '#94a3b8' }}
                        tickLine={false}
                        axisLine={{ stroke: '#e2e8f0' }}
                        interval="preserveStartEnd"
                    />
                    <YAxis
                        tick={{ fontSize: 9, fill: '#94a3b8' }}
                        tickLine={false}
                        axisLine={false}
                        domain={[0, 1]}
                        ticks={[0, 0.25, 0.5, 0.75, 1]}
                        tickFormatter={(v) => v != null ? v.toFixed(2) : ''}
                        width={35}
                    />
                    <Tooltip
                        contentStyle={{
                            backgroundColor: '#1e293b',
                            border: 'none',
                            borderRadius: '6px',
                            fontSize: '11px',
                            color: '#f1f5f9',
                        }}
                        labelStyle={{ color: '#94a3b8' }}
                        itemStyle={{ color: '#f1f5f9' }}
                        formatter={(value: number) => [value != null ? value.toFixed(3) : '-', 'Correlation']}
                    />
                    <ReferenceLine y={0.5} stroke="#94a3b8" strokeDasharray="3 3" />
                    <Area
                        type="monotone"
                        dataKey="corr"
                        stroke="#8b5cf6"
                        strokeWidth={2}
                        fill="url(#corrGradient)"
                    />
                    {/* Min/Max markers */}
                    <Line
                        type="monotone"
                        dataKey={(d: any) => d.isMin ? d.corr : null}
                        stroke="none"
                        dot={<TriangleDown fill="#f43f5e" />}
                        isAnimationActive={false}
                    />
                    <Line
                        type="monotone"
                        dataKey={(d: any) => d.isMax ? d.corr : null}
                        stroke="none"
                        dot={<TriangleUp fill="#10b981" />}
                        isAnimationActive={false}
                    />
                </ComposedChart>
            </ResponsiveContainer>
        </div>
    );
}

// Regression Scatter + Stats (Panel 4)
function RegressionPanel({ data }: { data: RatioAnalysisData }) {
    const reg = data.regression;

    if (!reg) {
        return (
            <div className="h-[180px] flex items-center justify-center text-slate-400 text-sm">
                Insufficient data for regression
            </div>
        );
    }

    // Generate trend line points
    const scatterData = data.scatter;
    const xMin = Math.min(...scatterData.map(p => p.x));
    const xMax = Math.max(...scatterData.map(p => p.x));
    const trendLine = [
        { x: xMin, y: reg.alpha + reg.beta * xMin },
        { x: xMax, y: reg.alpha + reg.beta * xMax },
    ];

    return (
        <div className="h-[200px] flex">
            {/* Scatter Plot */}
            <div className="flex-1">
                <div className="px-3 py-1 border-b border-slate-100">
                    <span className="text-[10px] text-slate-500">
                        y = {reg.beta.toFixed(3)}x + {reg.alpha.toFixed(3)}
                    </span>
                </div>
                <ResponsiveContainer width="100%" height="85%">
                    <ScatterChart margin={{ top: 10, right: 10, left: 0, bottom: 20 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                        <XAxis
                            type="number"
                            dataKey="x"
                            tick={{ fontSize: 9, fill: '#94a3b8' }}
                            tickLine={false}
                            axisLine={{ stroke: '#e2e8f0' }}
                            label={{ value: `${data.symbols.x} Returns (%)`, position: 'bottom', fontSize: 9, fill: '#94a3b8', offset: 5 }}
                            domain={['auto', 'auto']}
                        />
                        <YAxis
                            type="number"
                            dataKey="y"
                            tick={{ fontSize: 9, fill: '#94a3b8' }}
                            tickLine={false}
                            axisLine={false}
                            label={{ value: `${data.symbols.y} Returns (%)`, angle: -90, position: 'insideLeft', fontSize: 9, fill: '#94a3b8' }}
                            width={40}
                            domain={['auto', 'auto']}
                        />
                        <Tooltip
                            contentStyle={{
                                backgroundColor: '#1e293b',
                                border: 'none',
                                borderRadius: '6px',
                                fontSize: '10px',
                                color: '#f1f5f9',
                            }}
                            labelStyle={{ color: '#94a3b8' }}
                            itemStyle={{ color: '#f1f5f9' }}
                            formatter={(value: number, name: string) => [
                                value != null ? `${value.toFixed(2)}%` : '-',
                                name === 'x' ? data.symbols.x : data.symbols.y
                            ]}
                        />
                        <Scatter data={scatterData} fill="#8b5cf6" opacity={0.6}>
                            {scatterData.map((_, index) => (
                                <Cell key={`cell-${index}`} />
                            ))}
                        </Scatter>
                        {/* Trend line as scatter with 2 points connected */}
                        <Scatter data={trendLine} fill="none" line={{ stroke: '#f59e0b', strokeWidth: 2 }} />
                    </ScatterChart>
                </ResponsiveContainer>
            </div>

            {/* Stats Table */}
            <div className="w-[180px] border-l border-slate-200 bg-slate-50">
                <div className="px-3 py-1 border-b border-slate-200 bg-slate-100">
                    <span className="text-[10px] font-semibold text-slate-600">Regression Stats</span>
                </div>
                <div className="p-2 space-y-1">
                    <StatRow label="Beta (β)" value={reg.beta.toFixed(3)} />
                    <StatRow label="Alpha (α)" value={reg.alpha.toFixed(3)} />
                    <StatRow label="Pearson R" value={reg.pearson_r.toFixed(3)} />
                    <StatRow label="R-squared" value={reg.r_squared.toFixed(3)} />
                    <div className="border-t border-slate-200 pt-1 mt-1">
                        <StatRow label="Std Dev Error" value={reg.std_error.toFixed(3)} muted />
                        <StatRow label="Std Error (α)" value={reg.std_error_alpha.toFixed(3)} muted />
                        <StatRow label="Std Error (β)" value={reg.std_error_beta.toFixed(3)} muted />
                    </div>
                </div>
            </div>
        </div>
    );
}

function StatRow({ label, value, muted = false, color }: { label: string; value: string; muted?: boolean; color?: string }) {
    return (
        <div className="flex items-center justify-between">
            <span className={`text-[10px] ${muted ? 'text-slate-400' : 'text-slate-600'}`}>{label}</span>
            <span className={`text-[10px] font-mono ${color || (muted ? 'text-slate-500' : 'text-slate-800 font-semibold')}`}>{value}</span>
        </div>
    );
}

// Signal Panel - Trading Signal with Z-Score
function SignalPanel({ data }: { data: RatioAnalysisData }) {
    const summary = data.summary;
    const zscore = data.zscore;
    
    if (!summary || !zscore) return null;
    
    const getSignalColor = (signal: string) => {
        if (signal.includes('LONG')) return 'bg-emerald-500';
        if (signal.includes('SHORT')) return 'bg-rose-500';
        return 'bg-slate-400';
    };
    
    const getSignalBg = (signal: string) => {
        if (signal.includes('LONG')) return 'bg-emerald-50 border-emerald-200';
        if (signal.includes('SHORT')) return 'bg-rose-50 border-rose-200';
        return 'bg-slate-50 border-slate-200';
    };
    
    return (
        <div className={`px-3 py-2 border-b ${getSignalBg(summary.signal)}`}>
            <div className="flex items-center justify-between">
                {/* Signal Badge */}
                <div className="flex items-center gap-3">
                    <div className={`px-3 py-1.5 rounded ${getSignalColor(summary.signal)} text-white text-xs font-bold`}>
                        {summary.signal.replace('_', ' ')}
                    </div>
                    <div className="text-[10px]">
                        <span className="text-slate-500">Strength:</span>
                        <span className="ml-1 font-semibold">{summary.signal_strength}%</span>
                    </div>
                </div>
                
                {/* Z-Score Gauge */}
                <div className="flex items-center gap-4">
                    <div className="text-center">
                        <div className={`text-lg font-bold font-mono ${
                            zscore.current >= 2 ? 'text-rose-600' :
                            zscore.current <= -2 ? 'text-emerald-600' :
                            Math.abs(zscore.current) >= 1 ? 'text-amber-600' : 'text-slate-600'
                        }`}>
                            {zscore.current >= 0 ? '+' : ''}{zscore.current.toFixed(2)}
                        </div>
                        <div className="text-[9px] text-slate-400">Z-Score</div>
                    </div>
                    
                    {/* Visual gauge */}
                    <div className="w-24 h-2 bg-slate-200 rounded-full overflow-hidden relative">
                        <div className="absolute inset-y-0 left-1/2 w-px bg-slate-400" />
                        <div 
                            className={`absolute top-0 h-full ${zscore.current >= 0 ? 'bg-rose-500' : 'bg-emerald-500'} transition-all`}
                            style={{
                                left: zscore.current >= 0 ? '50%' : `${50 + (zscore.current / 4) * 50}%`,
                                width: `${Math.min(50, Math.abs(zscore.current / 4) * 50)}%`,
                            }}
                        />
                    </div>
                </div>
                
                {/* Quick Stats */}
                <div className="flex items-center gap-4 text-[10px]">
                    <div>
                        <span className="text-slate-400">Half-Life:</span>
                        <span className={`ml-1 font-mono font-semibold ${
                            summary.half_life_days && summary.half_life_days < 30 ? 'text-emerald-600' :
                            summary.half_life_days && summary.half_life_days < 60 ? 'text-amber-600' : 'text-slate-600'
                        }`}>
                            {summary.half_life_days ? `${summary.half_life_days.toFixed(0)}d` : '-'}
                        </span>
                    </div>
                    <div>
                        <span className="text-slate-400">Vol Ratio:</span>
                        <span className="ml-1 font-mono font-semibold">{summary.vol_ratio?.toFixed(2) ?? '-'}</span>
                    </div>
                </div>
            </div>
            
            {/* Recommendation */}
            <div className="mt-1.5 text-[10px] text-slate-600">
                {summary.recommendation}
            </div>
        </div>
    );
}

// Z-Score Chart
function ZScoreChart({ data }: { data: RatioAnalysisData }) {
    const zscore = data.zscore;
    if (!zscore || !zscore.values.length) return null;
    
    const offset = data.prices.dates.length - zscore.values.length;
    const chartData = zscore.values.map((z, i) => ({
        date: data.prices.dates[i + offset],
        dateShort: data.prices.dates[i + offset]?.slice(5) || '',
        zscore: z,
        isHigh: z >= 2,
        isLow: z <= -2,
    }));
    
    return (
        <div className="h-[120px]">
            <div className="flex items-center justify-between px-3 py-1 border-b border-slate-100">
                <div className="flex items-center gap-2 text-[10px]">
                    <span className="text-slate-600 font-medium">Z-Score</span>
                    <span className={`font-mono font-semibold ${
                        zscore.current >= 2 ? 'text-rose-600' :
                        zscore.current <= -2 ? 'text-emerald-600' : 'text-slate-600'
                    }`}>
                        {zscore.current >= 0 ? '+' : ''}{zscore.current.toFixed(2)}
                    </span>
                </div>
                <div className="flex items-center gap-2 text-[9px] text-slate-400">
                    <span className="text-rose-500">+2 Short</span>
                    <span className="text-emerald-500">-2 Long</span>
                </div>
            </div>
            <ResponsiveContainer width="100%" height="85%">
                <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                        <linearGradient id="zscoreGradientPos" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#f43f5e" stopOpacity={0.3} />
                            <stop offset="100%" stopColor="#f43f5e" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="zscoreGradientNeg" x1="0" y1="1" x2="0" y2="0">
                            <stop offset="0%" stopColor="#10b981" stopOpacity={0.3} />
                            <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                    <XAxis
                        dataKey="dateShort"
                        tick={{ fontSize: 9, fill: '#94a3b8' }}
                        tickLine={false}
                        axisLine={{ stroke: '#e2e8f0' }}
                        interval="preserveStartEnd"
                    />
                    <YAxis
                        tick={{ fontSize: 9, fill: '#94a3b8' }}
                        tickLine={false}
                        axisLine={false}
                        domain={[-3, 3]}
                        ticks={[-2, -1, 0, 1, 2]}
                        width={25}
                    />
                    <Tooltip
                        contentStyle={{
                            backgroundColor: '#1e293b',
                            border: 'none',
                            borderRadius: '6px',
                            fontSize: '11px',
                            color: '#f1f5f9',
                        }}
                        formatter={(value: number) => [value?.toFixed(2) ?? '-', 'Z-Score']}
                    />
                    <ReferenceLine y={2} stroke="#f43f5e" strokeDasharray="3 3" />
                    <ReferenceLine y={-2} stroke="#10b981" strokeDasharray="3 3" />
                    <ReferenceLine y={0} stroke="#94a3b8" />
                    <Area
                        type="monotone"
                        dataKey="zscore"
                        stroke="#6366f1"
                        strokeWidth={1.5}
                        fill="url(#zscoreGradientPos)"
                    />
                </ComposedChart>
            </ResponsiveContainer>
        </div>
    );
}

// Trading Panel - Hedge Ratio & Backtest
function TradingPanel({ data }: { data: RatioAnalysisData }) {
    const hedge = data.hedge_ratio;
    const backtest = data.backtest;
    const vol = data.volatility;
    
    if (!hedge) return null;
    
    return (
        <div className="flex border-t border-slate-200">
            {/* Hedge Ratio */}
            <div className="flex-1 p-3 border-r border-slate-200">
                <div className="text-[10px] font-semibold text-slate-600 mb-2">Position Sizing ($10K)</div>
                <div className="flex items-center gap-4">
                    <div className="text-center">
                        <div className="text-lg font-bold text-rose-600">{hedge.example.shares_y}</div>
                        <div className="text-[9px] text-slate-400">Buy {data.symbols.y}</div>
                    </div>
                    <ArrowRightLeft className="w-4 h-4 text-slate-300" />
                    <div className="text-center">
                        <div className="text-lg font-bold text-cyan-600">{hedge.example.shares_x}</div>
                        <div className="text-[9px] text-slate-400">Sell {data.symbols.x}</div>
                    </div>
                </div>
                <div className="mt-2 text-[9px] text-slate-400">
                    Hedge: {hedge.beta_hedge.toFixed(2)}x | Net: ${Math.abs(hedge.example.net_exposure).toFixed(0)}
                </div>
            </div>
            
            {/* Volatility */}
            {vol && (
                <div className="w-[140px] p-3 border-r border-slate-200 bg-slate-50">
                    <div className="text-[10px] font-semibold text-slate-600 mb-2">Volatility (Ann.)</div>
                    <div className="space-y-1">
                        <StatRow label={data.symbols.y} value={`${vol.y_annual.toFixed(1)}%`} color="text-rose-600" />
                        <StatRow label={data.symbols.x} value={`${vol.x_annual.toFixed(1)}%`} color="text-cyan-600" />
                        <StatRow label="Ratio" value={vol.ratio.toFixed(2)} />
                    </div>
                </div>
            )}
            
            {/* Backtest Stats */}
            {backtest && backtest.total_trades > 0 && (
                <div className="w-[160px] p-3 bg-slate-50">
                    <div className="text-[10px] font-semibold text-slate-600 mb-2">Backtest (Z=2)</div>
                    <div className="space-y-1">
                        <StatRow 
                            label="Win Rate" 
                            value={`${backtest.win_rate.toFixed(0)}%`} 
                            color={backtest.win_rate >= 50 ? 'text-emerald-600' : 'text-rose-600'}
                        />
                        <StatRow 
                            label="Avg P&L" 
                            value={`${backtest.avg_pnl >= 0 ? '+' : ''}${backtest.avg_pnl.toFixed(1)}%`}
                            color={backtest.avg_pnl >= 0 ? 'text-emerald-600' : 'text-rose-600'}
                        />
                        <StatRow label="Trades" value={backtest.total_trades.toString()} />
                        <StatRow 
                            label="Sharpe" 
                            value={backtest.sharpe.toFixed(2)}
                            color={backtest.sharpe >= 1 ? 'text-emerald-600' : backtest.sharpe >= 0 ? 'text-amber-600' : 'text-rose-600'}
                        />
                    </div>
                </div>
            )}
        </div>
    );
}

// ============================================================================
// Main Component
// ============================================================================

export function RatioAnalysisContent({
    initialSymbolY,
    initialSymbolX,
}: {
    initialSymbolY?: string;
    initialSymbolX?: string;
}) {
    const font = useUserPreferencesStore(selectFont);
    const fontFamily = `var(--font-${font})`;

    const [symbolY, setSymbolY] = useState(initialSymbolY || '');
    const [symbolX, setSymbolX] = useState(initialSymbolX || 'SPY');
    const [period, setPeriod] = useState<Period>('1Y');
    const [corrWindow, setCorrWindow] = useState(120);
    const [showSettings, setShowSettings] = useState(false);

    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [data, setData] = useState<RatioAnalysisData | null>(null);

    const handleSearch = useCallback(async () => {
        if (!symbolY.trim() || !symbolX.trim()) {
            setError('Enter both symbols');
            return;
        }

        if (symbolY.toUpperCase() === symbolX.toUpperCase()) {
            setError('Symbols must be different');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const params = new URLSearchParams({
                symbol_y: symbolY.toUpperCase(),
                symbol_x: symbolX.toUpperCase(),
                period,
                corr_window: corrWindow.toString(),
            });

            const response = await fetch(`${API_URL}/api/v1/ratio-analysis?${params}`);
            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || 'Analysis failed');
            }

            setData(result);
        } catch (e: any) {
            setError(e.message);
            setData(null);
        } finally {
            setLoading(false);
        }
    }, [symbolY, symbolX, period, corrWindow]);

    const handleSelectY = useCallback((selected: TickerSearchResult) => {
        setSymbolY(selected.symbol);
    }, []);

    const handleSelectX = useCallback((selected: TickerSearchResult) => {
        setSymbolX(selected.symbol);
    }, []);

    // Auto-search when symbols change (if both are set)
    useEffect(() => {
        if (initialSymbolY && initialSymbolX) {
            handleSearch();
        }
    }, []); // Only on mount

    return (
        <div className="h-full flex flex-col bg-white text-slate-800" style={{ fontFamily }}>
            {/* Header / Search Bar */}
            <div className="flex-shrink-0 px-3 py-2 border-b border-slate-200">
                <div className="flex items-center gap-2">
                    {/* Symbol Y (buy/long) */}
                    <div className="flex items-center gap-1">
                        <span className="text-[10px] text-rose-500 font-medium">Y (buy):</span>
                        <div className="w-24">
                            <TickerSearch
                                value={symbolY}
                                onChange={setSymbolY}
                                onSelect={handleSelectY}
                                placeholder="AAPL"
                                className="text-xs"
                            />
                        </div>
                    </div>

                    <ArrowRightLeft className="w-3.5 h-3.5 text-slate-300" />

                    {/* Symbol X (sell/short) */}
                    <div className="flex items-center gap-1">
                        <span className="text-[10px] text-cyan-500 font-medium">X (sell):</span>
                        <div className="w-24">
                            <TickerSearch
                                value={symbolX}
                                onChange={setSymbolX}
                                onSelect={handleSelectX}
                                placeholder="SPY"
                                className="text-xs"
                            />
                        </div>
                    </div>

                    {/* Period selector */}
                    <div className="flex border border-slate-200 rounded overflow-hidden ml-2">
                        {PERIODS.map((p) => (
                            <button
                                key={p.id}
                                onClick={() => setPeriod(p.id)}
                                className={`px-2 py-1 text-[10px] font-medium transition-colors ${
                                    period === p.id
                                        ? 'bg-blue-500 text-white'
                                        : 'text-slate-500 hover:bg-slate-50'
                                }`}
                            >
                                {p.label}
                            </button>
                        ))}
                    </div>

                    {/* Settings toggle */}
                    <button
                        onClick={() => setShowSettings(!showSettings)}
                        className={`p-1.5 rounded border ${
                            showSettings
                                ? 'border-blue-300 bg-blue-50 text-blue-600'
                                : 'border-slate-200 text-slate-400 hover:text-slate-600'
                        }`}
                    >
                        <Settings2 className="w-3.5 h-3.5" />
                    </button>

                    {/* Search button */}
                    <button
                        onClick={handleSearch}
                        disabled={loading || !symbolY.trim() || !symbolX.trim()}
                        className="px-3 py-1.5 rounded bg-blue-500 text-white text-[11px] font-medium hover:bg-blue-600 disabled:opacity-50 flex items-center gap-1.5 ml-auto"
                    >
                        {loading ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                            <Search className="w-3.5 h-3.5" />
                        )}
                        Analyze
                    </button>
                </div>

                {/* Settings row */}
                {showSettings && (
                    <div className="mt-2 pt-2 border-t border-slate-100 flex items-center gap-4 text-[10px]">
                        <div className="flex items-center gap-1">
                            <span className="text-slate-400">Corr. Window:</span>
                            <input
                                type="number"
                                value={corrWindow}
                                onChange={(e) => setCorrWindow(Math.min(252, Math.max(20, parseInt(e.target.value) || 120)))}
                                className="w-12 px-1 py-0.5 rounded border border-slate-200 text-center"
                            />
                            <span className="text-slate-400">days</span>
                        </div>
                    </div>
                )}
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto">
                {/* Error */}
                {error && (
                    <div className="flex items-center gap-2 text-rose-600 p-4 text-sm">
                        <AlertCircle className="w-4 h-4" />
                        {error}
                    </div>
                )}

                {/* Empty state */}
                {!data && !loading && !error && (
                    <div className="h-full flex flex-col items-center justify-center text-slate-400">
                        <ArrowRightLeft className="w-10 h-10 mb-3 opacity-30" />
                        <p className="text-sm">Enter two symbols to analyze their relationship</p>
                        <p className="text-xs text-slate-300 mt-1">e.g., AAPL vs SPY</p>
                    </div>
                )}

                {/* Loading */}
                {loading && (
                    <div className="h-full flex flex-col items-center justify-center text-slate-400">
                        <Loader2 className="w-6 h-6 animate-spin mb-2" />
                        <p className="text-sm">Analyzing {symbolY} vs {symbolX}...</p>
                    </div>
                )}

                {/* Results */}
                {data && !loading && (
                    <div className="divide-y divide-slate-200">
                        {/* Signal Panel (New!) */}
                        <SignalPanel data={data} />

                        {/* Summary header */}
                        <div className="px-3 py-2 bg-slate-50 flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <span className="text-sm font-semibold text-slate-800">
                                    {data.symbols.y}
                                    <span className="text-slate-400 mx-1">/</span>
                                    {data.symbols.x}
                                </span>
                                <span className="text-xs text-slate-400">
                                    {data.data_points} pts
                                </span>
                            </div>
                            <div className="flex items-center gap-4 text-[11px]">
                                <div className="flex items-center gap-1">
                                    <span className="text-slate-400">Beta:</span>
                                    <span className={`font-mono font-semibold ${
                                        data.regression && data.regression.beta > 1
                                            ? 'text-rose-600'
                                            : data.regression && data.regression.beta < 1
                                            ? 'text-emerald-600'
                                            : 'text-slate-600'
                                    }`}>
                                        {data.regression?.beta.toFixed(2) ?? '-'}
                                    </span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <span className="text-slate-400">R²:</span>
                                    <span className="font-mono font-semibold text-slate-700">
                                        {data.regression?.r_squared.toFixed(2) ?? '-'}
                                    </span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <span className="text-slate-400">Corr:</span>
                                    <span className="font-mono font-semibold text-violet-600">
                                        {data.correlation.latest?.toFixed(2) ?? '-'}
                                    </span>
                                </div>
                            </div>
                        </div>

                        {/* Panel: Z-Score (New!) */}
                        <ZScoreChart data={data} />

                        {/* Panel: Price Comparison */}
                        <PriceChart data={data} />

                        {/* Panel: Ratio */}
                        <RatioChart data={data} />

                        {/* Panel: Correlation */}
                        <CorrelationChart data={data} />

                        {/* Panel: Regression */}
                        <RegressionPanel data={data} />

                        {/* Panel: Trading Stats - Al final */}
                        <TradingPanel data={data} />
                    </div>
                )}
            </div>

            {/* Footer */}
            <div className="flex-shrink-0 px-3 py-1 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-[9px] text-slate-400">
                <span>
                    {data ? `${period} period` : 'Select symbols and period'}
                </span>
                <span className="font-mono">GR</span>
            </div>
        </div>
    );
}

export default RatioAnalysisContent;

