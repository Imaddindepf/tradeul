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

// ============================================================================
// Dynamic Indicator Instance
// ============================================================================

export interface IndicatorInstance {
    id: string;           // unique: 'sma_1', 'ema_2', 'rsi_1'
    type: string;         // 'sma' | 'ema' | 'rsi' | 'macd' | 'bb' | 'keltner' | 'vwap' | 'stoch' | 'adx' | 'atr' | 'squeeze' | 'obv' | 'rvol'
    params: Record<string, number | string>;   // { length: 20 }
    styles: Record<string, string | number>;   // { color: '#f59e0b', lineWidth: 1 }
    visible: boolean;
}

export const OVERLAY_TYPES = new Set(['sma', 'ema', 'bb', 'keltner', 'vwap']);
export const PANEL_TYPES = new Set(['rsi', 'macd', 'stoch', 'adx', 'atr', 'squeeze', 'obv', 'rvol']);

export interface ChartWindowState {
    ticker?: string;
    interval?: Interval;
    range?: TimeRange;
    indicators?: IndicatorInstance[];
    showVolume?: boolean;
    nextInstanceId?: number;
    // Legacy fields (for migration)
    showMA?: boolean;
    showEMA?: boolean;
    activeOverlays?: string[];
    activePanels?: string[];
    [key: string]: unknown;
}

// ============================================================================
// Constants
// ============================================================================

export const INTERVALS: IntervalConfig[] = [
    { label: '1 Minute', shortLabel: '1m', interval: '1min' },
    { label: '2 Minutes', shortLabel: '2m', interval: '2min' },
    { label: '5 Minutes', shortLabel: '5m', interval: '5min' },
    { label: '15 Minutes', shortLabel: '15m', interval: '15min' },
    { label: '30 Minutes', shortLabel: '30m', interval: '30min' },
    { label: '1 Hour', shortLabel: '1H', interval: '1hour' },
    { label: '4 Hours', shortLabel: '4H', interval: '4hour' },
    { label: '12 Hours', shortLabel: '12H', interval: '12hour' },
    { label: '1 Day', shortLabel: '1D', interval: '1day' },
    { label: '1 Week', shortLabel: '1W', interval: '1week' },
    { label: '1 Month', shortLabel: '1M', interval: '1month' },
    { label: '3 Months', shortLabel: '3M', interval: '3month' },
    { label: '1 Year', shortLabel: '1Y', interval: '1year' },
];

export const INTERVAL_GROUPS = {
    intraday: [
        { label: '1m', interval: '1min' as Interval },
        { label: '2m', interval: '2min' as Interval },
        { label: '5m', interval: '5min' as Interval },
        { label: '15m', interval: '15min' as Interval },
        { label: '30m', interval: '30min' as Interval },
    ],
    hourly: [
        { label: '1H', interval: '1hour' as Interval },
        { label: '4H', interval: '4hour' as Interval },
        { label: '12H', interval: '12hour' as Interval },
    ],
    daily: [
        { label: '1D', interval: '1day' as Interval },
        { label: '1W', interval: '1week' as Interval },
        { label: '1M', interval: '1month' as Interval },
        { label: '3M', interval: '3month' as Interval },
        { label: '1Y', interval: '1year' as Interval },
    ],
};

export const INTERVAL_SECONDS: Record<Interval, number> = {
    '1min': 60,
    '2min': 120,
    '5min': 300,
    '15min': 900,
    '30min': 1800,
    '1hour': 3600,
    '4hour': 14400,
    '12hour': 43200,
    '1day': 86400,
    '1week': 604800,
    '1month': 2592000,
    '3month': 7776000,
    '1year': 31536000,
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

/** Bars of empty space shown to the right of the last whitespace bar. */
export const RIGHT_OFFSET_BARS = 15;

/** Number of whitespace bars to generate per interval (future dates on the time axis). */
export const WHITESPACE_BAR_COUNT: Record<Interval, number> = {
    '1min': 1200,   // ~3 trading days
    '2min': 600,    // ~3 trading days
    '5min': 360,    // ~5 trading days
    '15min': 160,   // ~5 trading days
    '30min': 100,   // ~6 trading days
    '1hour': 80,    // ~10 trading days
    '4hour': 60,    // ~30 trading days
    '12hour': 40,   // ~20 days
    '1day': 120,    // ~6 months
    '1week': 52,    // ~1 year
    '1month': 24,   // ~2 years
    '3month': 12,   // ~3 years
    '1year': 10,    // ~10 years
};

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

// ============================================================================
// Color palette for auto-assigning colors to new instances
// ============================================================================

export const INDICATOR_COLOR_PALETTE = [
    '#f59e0b', // amber
    '#6366f1', // indigo
    '#ec4899', // pink
    '#8b5cf6', // violet
    '#ef4444', // red
    '#3b82f6', // blue
    '#10b981', // emerald
    '#f97316', // orange
    '#14b8a6', // teal
    '#a855f7', // purple
    '#06b6d4', // cyan
    '#84cc16', // lime
    '#e11d48', // rose
    '#0ea5e9', // sky
    '#d946ef', // fuchsia
    '#eab308', // yellow
];

export function getNextColor(existingInstances: IndicatorInstance[]): string {
    const usedColors = new Set(existingInstances.map(i => i.styles.color as string));
    for (const color of INDICATOR_COLOR_PALETTE) {
        if (!usedColors.has(color)) return color;
    }
    // All used — cycle
    return INDICATOR_COLOR_PALETTE[existingInstances.length % INDICATOR_COLOR_PALETTE.length];
}

// ============================================================================
// Indicator Type Configuration (for settings dialog + defaults)
// ============================================================================

export interface IndicatorInputConfig {
    key: string;
    label: string;
    type: 'number' | 'select';
    default: number | string;
    min?: number;
    max?: number;
    step?: number;
    options?: string[];
}

export interface IndicatorStyleConfig {
    key: string;
    label: string;
    type: 'color' | 'number';
    default: string | number;
    min?: number;
    max?: number;
}

export interface IndicatorTypeConfig {
    name: string;
    category: 'overlay' | 'panel';
    defaultParams: Record<string, number | string>;
    defaultStyles: Record<string, string | number>;
    inputs: IndicatorInputConfig[];
    styles: IndicatorStyleConfig[];
    // For panel indicators: range and reference lines
    range?: [number, number];
    lines?: { value: number; color: string; style: string }[];
    // Sub-series keys (for multi-line indicators)
    subSeries?: string[];
}

export const INDICATOR_TYPE_DEFAULTS: Record<string, IndicatorTypeConfig> = {
    sma: {
        name: 'SMA',
        category: 'overlay',
        defaultParams: { length: 20 },
        defaultStyles: { color: '#f59e0b', lineWidth: 2 },
        inputs: [{ key: 'length', label: 'Length', type: 'number', default: 20, min: 1, max: 500 }],
        styles: [
            { key: 'color', label: 'Color', type: 'color', default: '#f59e0b' },
            { key: 'lineWidth', label: 'Width', type: 'number', default: 2, min: 1, max: 5 },
        ],
    },
    ema: {
        name: 'EMA',
        category: 'overlay',
        defaultParams: { length: 12 },
        defaultStyles: { color: '#ec4899', lineWidth: 1 },
        inputs: [{ key: 'length', label: 'Length', type: 'number', default: 12, min: 1, max: 500 }],
        styles: [
            { key: 'color', label: 'Color', type: 'color', default: '#ec4899' },
            { key: 'lineWidth', label: 'Width', type: 'number', default: 1, min: 1, max: 5 },
        ],
    },
    bb: {
        name: 'Bollinger Bands',
        category: 'overlay',
        defaultParams: { length: 20, mult: 2 },
        defaultStyles: { upperColor: 'rgba(59, 130, 246, 0.5)', middleColor: '#3b82f6', lowerColor: 'rgba(59, 130, 246, 0.5)', lineWidth: 1 },
        inputs: [
            { key: 'length', label: 'Length', type: 'number', default: 20, min: 1, max: 200 },
            { key: 'mult', label: 'StdDev', type: 'number', default: 2, min: 0.5, max: 5, step: 0.5 },
        ],
        styles: [
            { key: 'upperColor', label: 'Upper', type: 'color', default: 'rgba(59, 130, 246, 0.5)' },
            { key: 'middleColor', label: 'Basis', type: 'color', default: '#3b82f6' },
            { key: 'lowerColor', label: 'Lower', type: 'color', default: 'rgba(59, 130, 246, 0.5)' },
            { key: 'lineWidth', label: 'Width', type: 'number', default: 1, min: 1, max: 5 },
        ],
        subSeries: ['upper', 'middle', 'lower'],
    },
    keltner: {
        name: 'Keltner Channels',
        category: 'overlay',
        defaultParams: { length: 20, mult: 1.5 },
        defaultStyles: { upperColor: 'rgba(20, 184, 166, 0.5)', middleColor: '#14b8a6', lowerColor: 'rgba(20, 184, 166, 0.5)', lineWidth: 1 },
        inputs: [
            { key: 'length', label: 'Length', type: 'number', default: 20, min: 1, max: 200 },
            { key: 'mult', label: 'Multiplier', type: 'number', default: 1.5, min: 0.5, max: 5, step: 0.5 },
        ],
        styles: [
            { key: 'upperColor', label: 'Upper', type: 'color', default: 'rgba(20, 184, 166, 0.5)' },
            { key: 'middleColor', label: 'Basis', type: 'color', default: '#14b8a6' },
            { key: 'lowerColor', label: 'Lower', type: 'color', default: 'rgba(20, 184, 166, 0.5)' },
            { key: 'lineWidth', label: 'Width', type: 'number', default: 1, min: 1, max: 5 },
        ],
        subSeries: ['upper', 'middle', 'lower'],
    },
    vwap: {
        name: 'VWAP',
        category: 'overlay',
        defaultParams: {},
        defaultStyles: { color: '#f97316', lineWidth: 2 },
        inputs: [],
        styles: [
            { key: 'color', label: 'Color', type: 'color', default: '#f97316' },
            { key: 'lineWidth', label: 'Width', type: 'number', default: 2, min: 1, max: 5 },
        ],
    },
    rsi: {
        name: 'RSI',
        category: 'panel',
        defaultParams: { length: 14, source: 'close' },
        defaultStyles: { color: '#8b5cf6', lineWidth: 2 },
        inputs: [
            { key: 'length', label: 'Length', type: 'number', default: 14, min: 1, max: 100 },
            { key: 'source', label: 'Source', type: 'select', default: 'close', options: ['close', 'open', 'high', 'low', 'hl2', 'hlc3'] },
        ],
        styles: [
            { key: 'color', label: 'RSI', type: 'color', default: '#8b5cf6' },
            { key: 'lineWidth', label: 'Width', type: 'number', default: 2, min: 1, max: 5 },
        ],
        range: [0, 100],
        lines: [
            { value: 70, color: 'rgba(239, 68, 68, 0.5)', style: 'dashed' },
            { value: 30, color: 'rgba(16, 185, 129, 0.5)', style: 'dashed' },
        ],
    },
    macd: {
        name: 'MACD',
        category: 'panel',
        defaultParams: { fastLength: 12, slowLength: 26, signalLength: 9 },
        defaultStyles: { macdColor: '#3b82f6', signalColor: '#f97316', histUpColor: 'rgba(16, 185, 129, 0.6)', histDownColor: 'rgba(239, 68, 68, 0.6)' },
        inputs: [
            { key: 'fastLength', label: 'Fast Length', type: 'number', default: 12, min: 1, max: 100 },
            { key: 'slowLength', label: 'Slow Length', type: 'number', default: 26, min: 1, max: 200 },
            { key: 'signalLength', label: 'Signal Smoothing', type: 'number', default: 9, min: 1, max: 50 },
        ],
        styles: [
            { key: 'macdColor', label: 'MACD Line', type: 'color', default: '#3b82f6' },
            { key: 'signalColor', label: 'Signal Line', type: 'color', default: '#f97316' },
            { key: 'histUpColor', label: 'Histogram Up', type: 'color', default: 'rgba(16, 185, 129, 0.6)' },
            { key: 'histDownColor', label: 'Histogram Down', type: 'color', default: 'rgba(239, 68, 68, 0.6)' },
        ],
        subSeries: ['macd', 'signal', 'histogram'],
    },
    stoch: {
        name: 'Stochastic',
        category: 'panel',
        defaultParams: { kLength: 14, kSmooth: 1, dSmooth: 3 },
        defaultStyles: { kColor: '#3b82f6', dColor: '#f97316', lineWidth: 1 },
        inputs: [
            { key: 'kLength', label: '%K Length', type: 'number', default: 14, min: 1, max: 100 },
            { key: 'kSmooth', label: '%K Smoothing', type: 'number', default: 1, min: 1, max: 10 },
            { key: 'dSmooth', label: '%D Smoothing', type: 'number', default: 3, min: 1, max: 10 },
        ],
        styles: [
            { key: 'kColor', label: '%K', type: 'color', default: '#3b82f6' },
            { key: 'dColor', label: '%D', type: 'color', default: '#f97316' },
            { key: 'lineWidth', label: 'Width', type: 'number', default: 1, min: 1, max: 5 },
        ],
        range: [0, 100],
        lines: [
            { value: 80, color: 'rgba(239, 68, 68, 0.5)', style: 'dashed' },
            { value: 20, color: 'rgba(16, 185, 129, 0.5)', style: 'dashed' },
        ],
        subSeries: ['k', 'd'],
    },
    adx: {
        name: 'ADX / DMI',
        category: 'panel',
        defaultParams: { length: 14, diLength: 14 },
        defaultStyles: { adxColor: '#8b5cf6', pdiColor: '#10b981', mdiColor: '#ef4444', lineWidth: 1 },
        inputs: [
            { key: 'length', label: 'ADX Length', type: 'number', default: 14, min: 1, max: 100 },
            { key: 'diLength', label: 'DI Length', type: 'number', default: 14, min: 1, max: 100 },
        ],
        styles: [
            { key: 'adxColor', label: 'ADX', type: 'color', default: '#8b5cf6' },
            { key: 'pdiColor', label: '+DI', type: 'color', default: '#10b981' },
            { key: 'mdiColor', label: '-DI', type: 'color', default: '#ef4444' },
            { key: 'lineWidth', label: 'Width', type: 'number', default: 1, min: 1, max: 5 },
        ],
        range: [0, 100],
        lines: [
            { value: 25, color: 'rgba(100, 116, 139, 0.5)', style: 'dashed' },
        ],
        subSeries: ['adx', 'pdi', 'mdi'],
    },
    atr: {
        name: 'ATR',
        category: 'panel',
        defaultParams: { length: 14 },
        defaultStyles: { color: '#6366f1', lineWidth: 1 },
        inputs: [
            { key: 'length', label: 'Length', type: 'number', default: 14, min: 1, max: 100 },
        ],
        styles: [
            { key: 'color', label: 'Color', type: 'color', default: '#6366f1' },
            { key: 'lineWidth', label: 'Width', type: 'number', default: 1, min: 1, max: 5 },
        ],
    },
    squeeze: {
        name: 'TTM Squeeze',
        category: 'panel',
        defaultParams: { bbLength: 20, bbMult: 2, kcLength: 20, kcMult: 1.5 },
        defaultStyles: { onColor: '#ef4444', offColor: '#10b981' },
        inputs: [
            { key: 'bbLength', label: 'BB Length', type: 'number', default: 20, min: 1, max: 100 },
            { key: 'bbMult', label: 'BB Mult', type: 'number', default: 2, min: 0.5, max: 5, step: 0.5 },
            { key: 'kcLength', label: 'KC Length', type: 'number', default: 20, min: 1, max: 100 },
            { key: 'kcMult', label: 'KC Mult', type: 'number', default: 1.5, min: 0.5, max: 5, step: 0.5 },
        ],
        styles: [
            { key: 'onColor', label: 'Squeeze On', type: 'color', default: '#ef4444' },
            { key: 'offColor', label: 'Squeeze Off', type: 'color', default: '#10b981' },
        ],
    },
    obv: {
        name: 'OBV',
        category: 'panel',
        defaultParams: {},
        defaultStyles: { color: '#3b82f6', lineWidth: 1 },
        inputs: [],
        styles: [
            { key: 'color', label: 'Color', type: 'color', default: '#3b82f6' },
            { key: 'lineWidth', label: 'Width', type: 'number', default: 1, min: 1, max: 5 },
        ],
    },
    rvol: {
        name: 'RVOL',
        category: 'panel',
        defaultParams: {},
        defaultStyles: { color: '#f97316' },
        inputs: [],
        styles: [
            { key: 'color', label: 'Color', type: 'color', default: '#f97316' },
        ],
        lines: [
            { value: 1.0, color: 'rgba(100, 116, 139, 0.5)', style: 'dashed' },
            { value: 2.0, color: 'rgba(16, 185, 129, 0.4)', style: 'dashed' },
        ],
    },
};

// ============================================================================
// Backward-compatible INDICATOR_CONFIGS (maps old fixed IDs to type configs)
// Used by IndicatorSettingsDialog until it's fully migrated
// ============================================================================

export type IndicatorConfig = {
    name: string;
    inputs: IndicatorInputConfig[];
    styles: IndicatorStyleConfig[];
};

// Build INDICATOR_CONFIGS from INDICATOR_TYPE_DEFAULTS for backward compat
export const INDICATOR_CONFIGS: Record<string, IndicatorConfig> = {};
for (const [type, config] of Object.entries(INDICATOR_TYPE_DEFAULTS)) {
    INDICATOR_CONFIGS[type] = {
        name: config.name,
        inputs: config.inputs,
        styles: config.styles,
    };
}

// ============================================================================
// Instance label helper
// ============================================================================

export function getInstanceLabel(inst: IndicatorInstance): string {
    const config = INDICATOR_TYPE_DEFAULTS[inst.type];
    if (!config) return inst.type.toUpperCase();

    const name = config.name;
    const p = inst.params;

    switch (inst.type) {
        case 'sma':
        case 'ema':
            return `${name} ${p.length || ''}`.trim();
        case 'rsi':
            return `RSI ${p.length || 14}`;
        case 'atr':
            return `ATR ${p.length || 14}`;
        case 'macd':
            return `MACD ${p.fastLength || 12},${p.slowLength || 26},${p.signalLength || 9}`;
        case 'stoch':
            return `Stoch ${p.kLength || 14},${p.kSmooth || 1},${p.dSmooth || 3}`;
        case 'adx':
            return `ADX ${p.length || 14}`;
        case 'bb':
            return `BB ${p.length || 20},${p.mult || 2}`;
        case 'keltner':
            return `KC ${p.length || 20},${p.mult || 1.5}`;
        case 'squeeze':
            return 'Squeeze';
        case 'vwap':
            return 'VWAP';
        case 'obv':
            return 'OBV';
        case 'rvol':
            return 'RVOL';
        default:
            return name;
    }
}

// ============================================================================
// Instance settings persistence
// ============================================================================

export const VISIBILITY_TIMEFRAMES = ['1m', '5m', '15m', '30m', '1H', '4H', '1D'] as const;

export type IndicatorSettings = Record<string, {
    inputs: Record<string, number | string>;
    styles: Record<string, string | number>;
    visibility: string[];
}>;

export function getIndicatorSettings(): IndicatorSettings {
    try {
        const stored = localStorage.getItem('chart-indicator-settings');
        return stored ? JSON.parse(stored) : {};
    } catch {
        return {};
    }
}

export function saveIndicatorSettings(settings: IndicatorSettings): void {
    try {
        localStorage.setItem('chart-indicator-settings', JSON.stringify(settings));
    } catch { /* ignore */ }
}

/** Get merged settings for a specific instance (by instance ID or type) */
export function getSettingsForIndicator(indicatorId: string): { inputs: Record<string, number | string>; styles: Record<string, string | number>; visibility: string[] } {
    const all = getIndicatorSettings();
    // Try by instance ID first, then by type
    const config = INDICATOR_CONFIGS[indicatorId] || INDICATOR_TYPE_DEFAULTS[indicatorId];
    if (!config) return { inputs: {}, styles: {}, visibility: [...VISIBILITY_TIMEFRAMES] };

    const saved = all[indicatorId];
    const inputs: Record<string, number | string> = {};
    const styles: Record<string, string | number> = {};

    for (const inp of config.inputs) {
        inputs[inp.key] = saved?.inputs?.[inp.key] ?? inp.default;
    }
    for (const sty of config.styles) {
        styles[sty.key] = saved?.styles?.[sty.key] ?? sty.default;
    }
    const visibility = saved?.visibility ?? [...VISIBILITY_TIMEFRAMES];

    return { inputs, styles, visibility };
}

// ============================================================================
// Legacy state migration
// ============================================================================

/** Convert old showMA/showEMA/activeOverlays/activePanels to IndicatorInstance[] */
export function migrateOldIndicatorState(state: ChartWindowState): IndicatorInstance[] {
    const instances: IndicatorInstance[] = [];
    let id = 1;

    if (state.showMA) {
        instances.push({
            id: `sma_${id++}`, type: 'sma',
            params: { length: 20 },
            styles: { color: '#f59e0b', lineWidth: 2 },
            visible: true,
        });
        instances.push({
            id: `sma_${id++}`, type: 'sma',
            params: { length: 50 },
            styles: { color: '#6366f1', lineWidth: 2 },
            visible: true,
        });
    }
    if (state.showEMA) {
        instances.push({
            id: `ema_${id++}`, type: 'ema',
            params: { length: 12 },
            styles: { color: '#ec4899', lineWidth: 1 },
            visible: true,
        });
        instances.push({
            id: `ema_${id++}`, type: 'ema',
            params: { length: 26 },
            styles: { color: '#8b5cf6', lineWidth: 1 },
            visible: true,
        });
    }
    if (state.activeOverlays) {
        for (const overlay of state.activeOverlays) {
            if (overlay === 'sma200') {
                instances.push({
                    id: `sma_${id++}`, type: 'sma',
                    params: { length: 200 },
                    styles: { color: '#ef4444', lineWidth: 2 },
                    visible: true,
                });
            } else if (['bb', 'keltner', 'vwap'].includes(overlay)) {
                const cfg = INDICATOR_TYPE_DEFAULTS[overlay];
                if (cfg) {
                    instances.push({
                        id: `${overlay}_${id++}`, type: overlay,
                        params: { ...cfg.defaultParams },
                        styles: { ...cfg.defaultStyles },
                        visible: true,
                    });
                }
            }
        }
    }
    if (state.activePanels) {
        for (const panel of state.activePanels) {
            const cfg = INDICATOR_TYPE_DEFAULTS[panel];
            if (cfg) {
                instances.push({
                    id: `${panel}_${id++}`, type: panel,
                    params: { ...cfg.defaultParams },
                    styles: { ...cfg.defaultStyles },
                    visible: true,
                });
            }
        }
    }

    return instances;
}

export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
