import type { ChartInterval } from '@/hooks/useLiveChartData';

// ============================================================================
// Types
// ============================================================================

export interface ChartBar {
    time: number;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
}

export interface TradingChartProps {
    ticker: string;
    exchange?: string;
    onTickerChange?: (ticker: string) => void;
    minimal?: boolean;
    onOpenChart?: () => void;
    onOpenNews?: () => void;
}

export type Interval = ChartInterval;
export type TimeRange = '1M' | '3M' | '6M' | '1Y' | '2Y' | '5Y' | 'ALL';

export interface IntervalConfig {
    label: string;
    shortLabel: string;
    interval: Interval;
}

export interface ChartWindowState {
    ticker?: string;
    interval?: Interval;
    range?: TimeRange;
    showMA?: boolean;
    showEMA?: boolean;
    showVolume?: boolean;
    activeOverlays?: string[];
    activePanels?: string[];
    [key: string]: unknown;
}

// ============================================================================
// Constants
// ============================================================================

export const INTERVALS: IntervalConfig[] = [
    { label: '1 Minute', shortLabel: '1m', interval: '1min' },
    { label: '5 Minutes', shortLabel: '5m', interval: '5min' },
    { label: '15 Minutes', shortLabel: '15m', interval: '15min' },
    { label: '30 Minutes', shortLabel: '30m', interval: '30min' },
    { label: '1 Hour', shortLabel: '1H', interval: '1hour' },
    { label: '4 Hours', shortLabel: '4H', interval: '4hour' },
    { label: '1 Day', shortLabel: '1D', interval: '1day' },
];

export const INTERVAL_GROUPS = {
    intraday: [
        { label: '1m', interval: '1min' as Interval },
        { label: '5m', interval: '5min' as Interval },
        { label: '15m', interval: '15min' as Interval },
        { label: '30m', interval: '30min' as Interval },
    ],
    hourly: [
        { label: '1H', interval: '1hour' as Interval },
        { label: '4H', interval: '4hour' as Interval },
    ],
    daily: [
        { label: '1D', interval: '1day' as Interval },
    ],
};

export const INTERVAL_SECONDS: Record<Interval, number> = {
    '1min': 60,
    '5min': 300,
    '15min': 900,
    '30min': 1800,
    '1hour': 3600,
    '4hour': 14400,
    '1day': 86400,
};

export const TIME_RANGES: { id: TimeRange; label: string; days: number }[] = [
    { id: '1M', label: '1M', days: 30 },
    { id: '3M', label: '3M', days: 90 },
    { id: '6M', label: '6M', days: 180 },
    { id: '1Y', label: '1Y', days: 365 },
    { id: '2Y', label: '2Y', days: 730 },
    { id: '5Y', label: '5Y', days: 1825 },
    { id: 'ALL', label: 'ALL', days: 0 },
];

export const CHART_COLORS = {
    background: '#ffffff',
    gridColor: '#f1f5f9',
    borderColor: '#e2e8f0',
    textColor: '#64748b',
    textStrong: '#334155',
    upColor: '#10b981',
    downColor: '#ef4444',
    upColorLight: '#d1fae5',
    downColorLight: '#fee2e2',
    volumeUp: 'rgba(16, 185, 129, 0.3)',
    volumeDown: 'rgba(239, 68, 68, 0.3)',
    crosshair: '#3b82f6',
    ma20: '#f59e0b',
    ma50: '#6366f1',
    ema12: '#ec4899',
    ema26: '#8b5cf6',
    watermark: 'rgba(100, 116, 139, 0.07)',
};

export const INDICATOR_COLORS = {
    rsi: '#8b5cf6',
    macdLine: '#3b82f6',
    macdSignal: '#f97316',
    macdHistogramUp: 'rgba(16, 185, 129, 0.6)',
    macdHistogramDown: 'rgba(239, 68, 68, 0.6)',
    stochK: '#3b82f6',
    stochD: '#f97316',
    adxLine: '#8b5cf6',
    pdiLine: '#10b981',
    mdiLine: '#ef4444',
    atr: '#6366f1',
    bbWidth: '#14b8a6',
    squeezeOn: '#ef4444',
    squeezeOff: '#10b981',
    obv: '#3b82f6',
};

export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
