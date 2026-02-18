'use client';

import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import {
    Search,
    TrendingUp,
    TrendingDown,
    Filter,
    Loader2,
    AlertCircle,
    Settings2,
    X,
    Plus,
    ChevronDown,
    ArrowUpDown,
    RefreshCw,
    Zap,
    Target,
    BarChart3,
    Activity,
    HelpCircle,
    Save,
    Star,
} from 'lucide-react';
import { TickerSearch } from '@/components/common/TickerSearch';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { useScreenerTemplates, type ScreenerTemplate, type FilterCondition as TemplateFilterCondition } from '@/hooks/useScreenerTemplates';
import { useWindowState } from '@/contexts/FloatingWindowContext';

interface ScreenerWindowState {
    filters?: FilterCondition[];
    sortBy?: string;
    sortOrder?: 'asc' | 'desc';
    limit?: number;
    activePreset?: string | null;
    activeUserTemplate?: number | null;
    autoExecute?: boolean;
    [key: string]: unknown;
}
import {
    useReactTable,
    getCoreRowModel,
    getSortedRowModel,
    createColumnHelper,
    flexRender,
} from '@tanstack/react-table';
import type { SortingState, ColumnOrderState, RowData } from '@tanstack/react-table';
import { TableSettings } from '@/components/table/TableSettings';
import { useVirtualizer } from '@tanstack/react-virtual';

// Extend TanStack Table meta type
declare module '@tanstack/react-table' {
    interface TableMeta<TData extends RowData> {
        onSymbolClick?: (symbol: string) => void;
    }
}

// ============================================================================
// Types
// ============================================================================

interface FilterCondition {
    field: string;
    operator: string;
    value: number | number[] | boolean | string;
    // For 'units' type fields (market_cap, float)
    displayValue?: number;
    multiplier?: number;
    // For parametric indicators (SMA, RSI, ATR, etc.)
    params?: {
        period?: number;
    };
    // Compare mode: 'value' = numeric, 'field' = compare against another indicator
    compareMode?: 'value' | 'field';
}

interface ScreenerResult {
    symbol: string;
    date: string;
    open: number | null;
    price: number;
    volume: number;
    change_1d: number | null;
    change_3d: number | null;
    change_5d: number | null;
    change_10d: number | null;
    change_20d: number | null;
    gap_percent: number | null;
    high_52w: number | null;
    low_52w: number | null;
    from_52w_high: number | null;
    from_52w_low: number | null;
    avg_volume_5: number | null;
    avg_volume_10: number | null;
    avg_volume_20: number | null;
    relative_volume: number | null;
    sma_20: number | null;
    sma_50: number | null;
    sma_200: number | null;
    dist_sma_20: number | null;
    dist_sma_50: number | null;
    rsi_14: number | null;
    atr_14: number | null;
    atr_percent: number | null;
    bb_upper: number | null;
    bb_middle: number | null;
    bb_lower: number | null;
    bb_width: number | null;
    bb_position: number | null;
    keltner_upper: number | null;
    keltner_middle: number | null;
    keltner_lower: number | null;
    squeeze_on: number | null;
    squeeze_momentum: number | null;
    adx_14: number | null;
    plus_di_14: number | null;
    minus_di_14: number | null;
    adx_trend: number | null;
    market_cap: number | null;
    free_float: number | null;
    sector: string | null;
}

interface ScreenerResponse {
    status: string;
    results: ScreenerResult[];
    count: number;
    total_matched: number | null;
    query_time_ms: number;
    filters_applied: number | null;
    errors: string[] | null;
}

interface Preset {
    id: string;
    name: string;
    description: string;
    icon: any;
    filters: FilterCondition[];
    sort_by: string;
    sort_order: string;
}

type TickerSearchResult = {
    symbol: string;
    name: string;
    exchange: string;
    type: string;
    displayName: string;
};

const API_BASE = 'https://screener.tradeul.com/api/v1/screener';

// ============================================================================
// Constants
// ============================================================================

// Unit multipliers for Market Cap / Float
const UNIT_MULTIPLIERS = [
    { value: 1, label: '' },
    { value: 1_000, label: 'K' },
    { value: 1_000_000, label: 'M' },
    { value: 1_000_000_000, label: 'B' },
];

// Parametric indicators - user can change the period
// Only simple indicators support dynamic periods (complex like RSI, ADX use precomputed)
const PARAMETRIC_PERIODS = {
    sma: [5, 10, 20, 50, 100, 200],
    atr: [7, 10, 14, 21],
    vol_avg: [5, 10, 20, 50],
};

// All backend-supported indicators, organized by category
const AVAILABLE_FIELDS = [
    // ── Price & Fundamentals ──
    { value: 'price', label: 'Price', type: 'number', unit: '$', category: 'Price' },
    { value: 'market_cap', label: 'Market Cap', type: 'units', category: 'Price' },
    { value: 'free_float', label: 'Free Float', type: 'units', category: 'Price' },
    { value: 'high_52w', label: '52W High', type: 'number', unit: '$', category: 'Price' },
    { value: 'low_52w', label: '52W Low', type: 'number', unit: '$', category: 'Price' },
    { value: 'from_52w_high', label: 'From 52W High', type: 'percent', unit: '%', category: 'Price' },
    { value: 'from_52w_low', label: 'From 52W Low', type: 'percent', unit: '%', category: 'Price' },
    // ── Price Changes ──
    { value: 'change_1d', label: 'Change 1D', type: 'percent', unit: '%', category: 'Changes' },
    { value: 'change_3d', label: 'Change 3D', type: 'percent', unit: '%', category: 'Changes' },
    { value: 'change_5d', label: 'Change 5D', type: 'percent', unit: '%', category: 'Changes' },
    { value: 'change_10d', label: 'Change 10D', type: 'percent', unit: '%', category: 'Changes' },
    { value: 'change_20d', label: 'Change 20D', type: 'percent', unit: '%', category: 'Changes' },
    { value: 'gap_percent', label: 'Gap', type: 'percent', unit: '%', category: 'Changes' },
    // ── Volume ──
    { value: 'volume', label: 'Volume', type: 'units', category: 'Volume' },
    { value: 'avg_volume_20', label: 'Avg Vol', type: 'units', parametric: 'vol_avg', defaultPeriod: 20, category: 'Volume' },
    { value: 'relative_volume', label: 'Rel. Volume', type: 'number', unit: 'x', category: 'Volume' },
    { value: 'dollar_volume', label: '$ Volume', type: 'units', category: 'Volume' },
    // ── Momentum ──
    { value: 'rsi_14', label: 'RSI (14)', type: 'number', min: 0, max: 100, category: 'Momentum' },
    // ── Trend / Moving Averages ──
    { value: 'sma_20', label: 'SMA', type: 'number', unit: '$', parametric: 'sma', defaultPeriod: 20, category: 'Trend' },
    { value: 'sma_50', label: 'SMA 50', type: 'number', unit: '$', category: 'Trend' },
    { value: 'sma_200', label: 'SMA 200', type: 'number', unit: '$', category: 'Trend' },
    { value: 'dist_sma_20', label: 'Dist SMA 20', type: 'percent', unit: '%', category: 'Trend' },
    { value: 'dist_sma_50', label: 'Dist SMA 50', type: 'percent', unit: '%', category: 'Trend' },
    // ── Volatility / Bollinger Bands ──
    { value: 'atr_14', label: 'ATR (14)', type: 'number', unit: '$', category: 'Volatility' },
    { value: 'atr_percent', label: 'ATR %', type: 'percent', unit: '%', parametric: 'atr', defaultPeriod: 14, category: 'Volatility' },
    { value: 'bb_upper', label: 'BB Upper', type: 'number', unit: '$', category: 'Volatility' },
    { value: 'bb_middle', label: 'BB Middle', type: 'number', unit: '$', category: 'Volatility' },
    { value: 'bb_lower', label: 'BB Lower', type: 'number', unit: '$', category: 'Volatility' },
    { value: 'bb_width', label: 'BB Width', type: 'percent', unit: '%', category: 'Volatility' },
    { value: 'bb_position', label: 'BB Position', type: 'percent', unit: '%', category: 'Volatility' },
    // ── Keltner Channels ──
    { value: 'keltner_upper', label: 'Keltner Upper', type: 'number', unit: '$', category: 'Keltner' },
    { value: 'keltner_middle', label: 'Keltner Middle', type: 'number', unit: '$', category: 'Keltner' },
    { value: 'keltner_lower', label: 'Keltner Lower', type: 'number', unit: '$', category: 'Keltner' },
    // ── TTM Squeeze ──
    { value: 'squeeze_momentum', label: 'Squeeze Mom.', type: 'number', category: 'Squeeze' },
    // ── ADX / Directional ──
    { value: 'adx_14', label: 'ADX (14)', type: 'number', min: 0, max: 100, category: 'ADX' },
    { value: 'plus_di_14', label: '+DI (14)', type: 'number', min: 0, max: 100, category: 'ADX' },
    { value: 'minus_di_14', label: '-DI (14)', type: 'number', min: 0, max: 100, category: 'ADX' },
    { value: 'adx_trend', label: 'ADX Trend', type: 'number', min: -1, max: 1, category: 'ADX' },
];

// Signal/boolean indicators — quick toggle conditions
const SIGNAL_FIELDS = [
    { value: 'squeeze_on', label: 'TTM Squeeze ON', category: 'Squeeze' },
    { value: 'volume_spike', label: 'Volume Spike (2x+)', category: 'Volume' },
    { value: 'rsi_oversold', label: 'RSI Oversold (<30)', category: 'Momentum' },
    { value: 'rsi_overbought', label: 'RSI Overbought (>70)', category: 'Momentum' },
    { value: 'above_sma_20', label: 'Price > SMA 20', category: 'Trend' },
    { value: 'above_sma_50', label: 'Price > SMA 50', category: 'Trend' },
    { value: 'above_sma_200', label: 'Price > SMA 200', category: 'Trend' },
    { value: 'sma_50_above_200', label: 'Golden Cross (SMA50>200)', category: 'Trend' },
    { value: 'bb_squeeze', label: 'BB Squeeze (Low Vol)', category: 'Volatility' },
    { value: 'above_bb_upper', label: 'Price > BB Upper', category: 'Volatility' },
    { value: 'below_bb_lower', label: 'Price < BB Lower', category: 'Volatility' },
    { value: 'strong_uptrend', label: 'Strong Uptrend (ADX)', category: 'ADX' },
    { value: 'strong_downtrend', label: 'Strong Downtrend (ADX)', category: 'ADX' },
];

// Group fields by category for optgroup rendering
const FIELD_CATEGORIES = Array.from(new Set(AVAILABLE_FIELDS.map(f => f.category)));

// Comparable fields for field-vs-field (exclude 'units' type — they use different scales)
const COMPARABLE_FIELDS = AVAILABLE_FIELDS.filter(f => f.type === 'number' || f.type === 'percent');

const VALUE_OPERATORS = [
    { value: 'gt', label: '>' },
    { value: 'gte', label: '≥' },
    { value: 'lt', label: '<' },
    { value: 'lte', label: '≤' },
    { value: 'eq', label: '=' },
    { value: 'neq', label: '≠' },
    { value: 'between', label: 'Between' },
];

const FIELD_OPERATORS = [
    { value: 'gt', label: '>' },
    { value: 'gte', label: '≥' },
    { value: 'lt', label: '<' },
    { value: 'lte', label: '≤' },
    { value: 'eq', label: '=' },
    { value: 'neq', label: '≠' },
    { value: 'cross_above', label: '↗ Cross Above' },
    { value: 'cross_below', label: '↘ Cross Below' },
];

const SORT_OPTIONS = [
    { value: 'relative_volume', label: 'Rel. Volume' },
    { value: 'change_1d', label: 'Change 1D' },
    { value: 'change_3d', label: 'Change 3D' },
    { value: 'change_5d', label: 'Change 5D' },
    { value: 'change_10d', label: 'Change 10D' },
    { value: 'change_20d', label: 'Change 20D' },
    { value: 'gap_percent', label: 'Gap %' },
    { value: 'market_cap', label: 'Market Cap' },
    { value: 'free_float', label: 'Free Float' },
    { value: 'rsi_14', label: 'RSI' },
    { value: 'price', label: 'Price' },
    { value: 'volume', label: 'Volume' },
    { value: 'from_52w_high', label: 'From 52W High' },
    { value: 'from_52w_low', label: 'From 52W Low' },
    { value: 'dist_sma_20', label: 'Dist SMA 20' },
    { value: 'dist_sma_50', label: 'Dist SMA 50' },
    { value: 'adx_14', label: 'ADX' },
    { value: 'atr_percent', label: 'ATR %' },
    { value: 'bb_width', label: 'BB Width' },
    { value: 'bb_position', label: 'BB Position' },
    { value: 'squeeze_momentum', label: 'Squeeze Mom.' },
    { value: 'bb_width', label: 'BB Width' },
    { value: 'squeeze_momentum', label: 'Squeeze Mom.' },
    { value: 'dist_sma_50', label: 'Dist SMA 50' },
    { value: 'from_52w_high', label: 'From 52W High' },
    { value: 'from_52w_low', label: 'From 52W Low' },
    { value: 'from_52w_high', label: '52W High' },
    { value: 'bb_width', label: 'BB Width' },
    { value: 'atr_percent', label: 'ATR %' },
    { value: 'adx_14', label: 'ADX' },
    { value: 'squeeze_momentum', label: 'Squeeze Mom.' },
];

// ============================================================================
// Presets - Editable Templates
// ============================================================================

const PRESETS: Preset[] = [
    {
        id: 'oversold-bounce',
        name: 'Oversold Bounce',
        description: 'RSI oversold with recent bounce',
        icon: TrendingUp,
        filters: [
            { field: 'rsi_14', operator: 'lt', value: 35 },
            { field: 'change_1d', operator: 'gt', value: 2 },
            { field: 'volume', operator: 'gt', value: 500000 },
            { field: 'price', operator: 'between', value: [2, 100] },
        ],
        sort_by: 'change_1d',
        sort_order: 'desc',
    },
    {
        id: 'momentum-breakout',
        name: 'Momentum Breakout',
        description: 'Strong momentum with high relative volume',
        icon: Zap,
        filters: [
            { field: 'change_1d', operator: 'gt', value: 5 },
            { field: 'relative_volume', operator: 'gt', value: 2 },
            { field: 'rsi_14', operator: 'between', value: [50, 80] },
            { field: 'volume', operator: 'gt', value: 1000000 },
        ],
        sort_by: 'relative_volume',
        sort_order: 'desc',
    },
    {
        id: 'high-volume-gappers',
        name: 'High Volume Gappers',
        description: 'Gap up/down with volume spike',
        icon: BarChart3,
        filters: [
            { field: 'gap_percent', operator: 'gt', value: 3 },
            { field: 'relative_volume', operator: 'gt', value: 1.5 },
            { field: 'volume', operator: 'gt', value: 500000 },
            { field: 'price', operator: 'between', value: [1, 200] },
        ],
        sort_by: 'gap_percent',
        sort_order: 'desc',
    },
    {
        id: '52w-high-breakout',
        name: '52W High Breakout',
        description: 'Near or breaking 52-week highs',
        icon: Target,
        filters: [
            { field: 'from_52w_high', operator: 'gt', value: -3 },
            { field: 'change_1d', operator: 'gt', value: 0 },
            { field: 'relative_volume', operator: 'gt', value: 1 },
            { field: 'volume', operator: 'gt', value: 500000 },
        ],
        sort_by: 'from_52w_high',
        sort_order: 'desc',
    },
    {
        id: 'ttm-squeeze-bullish',
        name: 'TTM Squeeze Bullish',
        description: 'Squeeze ON with bullish momentum - breakout coming',
        icon: Activity,
        filters: [
            { field: 'squeeze_on', operator: 'eq', value: 1 },
            { field: 'squeeze_momentum', operator: 'gt', value: 0 },
            { field: 'volume', operator: 'gt', value: 500000 },
            { field: 'price', operator: 'between', value: [5, 500] },
        ],
        sort_by: 'squeeze_momentum',
        sort_order: 'desc',
    },
    {
        id: 'ttm-squeeze-bearish',
        name: 'TTM Squeeze Bearish',
        description: 'Squeeze ON with bearish momentum',
        icon: Activity,
        filters: [
            { field: 'squeeze_on', operator: 'eq', value: 1 },
            { field: 'squeeze_momentum', operator: 'lt', value: 0 },
            { field: 'volume', operator: 'gt', value: 500000 },
        ],
        sort_by: 'squeeze_momentum',
        sort_order: 'asc',
    },
    {
        id: 'strong-uptrend',
        name: 'Strong Uptrend (ADX)',
        description: 'ADX > 25 with bullish direction',
        icon: TrendingUp,
        filters: [
            { field: 'adx_14', operator: 'gt', value: 25 },
            { field: 'plus_di_14', operator: 'gt', value: 20 },
            { field: 'volume', operator: 'gt', value: 500000 },
        ],
        sort_by: 'adx_14',
        sort_order: 'desc',
    },
    {
        id: 'bullish-trend',
        name: 'Bullish Trend',
        description: 'Price above all major SMAs',
        icon: TrendingUp,
        filters: [
            { field: 'dist_sma_20', operator: 'gt', value: 0 },
            { field: 'dist_sma_50', operator: 'gt', value: 0 },
            { field: 'rsi_14', operator: 'between', value: [40, 70] },
            { field: 'volume', operator: 'gt', value: 500000 },
        ],
        sort_by: 'change_5d',
        sort_order: 'desc',
    },
];

// ============================================================================
// NumberInput - Uncontrolled number input that allows free typing of negatives/decimals
// ============================================================================

function NumberInput({
    value,
    onChange,
    className,
    style,
}: {
    value: number;
    onChange: (val: number) => void;
    className?: string;
    style?: React.CSSProperties;
}) {
    // Key to force re-mount when value changes externally (preset, template, etc.)
    const [resetKey, setResetKey] = useState(0);
    const lastEmittedValue = useRef(value);

    // When parent value changes externally, reset the uncontrolled input
    useEffect(() => {
        if (value !== lastEmittedValue.current) {
            lastEmittedValue.current = value;
            setResetKey(k => k + 1);
        }
    }, [value]);

    return (
        <input
            key={resetKey}
            type="number"
            step="any"
            defaultValue={value}
            onChange={(e) => {
                const raw = e.target.value;
                if (raw === '') return; // intermediate state (typing "-", clearing, etc.)
                const parsed = parseFloat(raw);
                if (!Number.isNaN(parsed)) {
                    lastEmittedValue.current = parsed;
                    onChange(parsed);
                }
            }}
            onBlur={(e) => {
                // On blur, if empty or invalid, reset to last valid value
                const raw = e.target.value;
                if (raw === '' || Number.isNaN(parseFloat(raw))) {
                    setResetKey(k => k + 1);
                }
            }}
            className={className}
            style={style}
        />
    );
}

// ============================================================================
// Custom Dropdown Select (replaces native <select>)
// ============================================================================

function FieldSelect({
    value,
    onChange,
    options,
    categories,
    exclude,
    variant = 'default',
    fontFamily,
    minWidth = 120,
}: {
    value: string;
    onChange: (value: string) => void;
    options: typeof AVAILABLE_FIELDS;
    categories?: string[];
    exclude?: string;
    variant?: 'default' | 'field-compare';
    fontFamily: string;
    minWidth?: number;
}) {
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState('');
    const containerRef = useRef<HTMLDivElement>(null);
    const searchRef = useRef<HTMLInputElement>(null);

    const currentOption = options.find(o => o.value === value);
    const cats = categories || FIELD_CATEGORIES;

    const filtered = search
        ? options.filter(o =>
            o.label.toLowerCase().includes(search.toLowerCase()) &&
            o.value !== exclude
        )
        : options.filter(o => o.value !== exclude);

    useEffect(() => {
        if (open && searchRef.current) {
            setTimeout(() => searchRef.current?.focus(), 0);
        }
        if (!open) setSearch('');
    }, [open]);

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        if (open) document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [open]);

    const triggerClass = variant === 'field-compare'
        ? 'bg-transparent text-blue-600 border-slate-200 hover:border-blue-400'
        : 'bg-transparent text-slate-900 border-slate-200 hover:border-blue-400';

    return (
        <div ref={containerRef} className="relative" style={{ fontFamily }}>
            <button
                onClick={() => setOpen(!open)}
                className={`flex items-center gap-1 px-1.5 py-0.5 rounded border font-medium truncate ${triggerClass}`}
                style={{ fontSize: '12px', minWidth, maxWidth: 160 }}
            >
                <span className="truncate">{currentOption?.label || value}</span>
                <ChevronDown className={`w-3 h-3 shrink-0 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>

            {open && (
                <div
                    className="absolute top-full left-0 mt-0.5 bg-white border border-slate-200 rounded shadow-lg z-50 overflow-hidden"
                    style={{ minWidth: Math.max(minWidth, 180), maxHeight: 280, fontFamily }}
                >
                    <div className="px-1.5 py-1 border-b border-slate-100">
                        <input
                            ref={searchRef}
                            type="text"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder="Search..."
                            className="w-full px-1.5 py-0.5 rounded bg-slate-50 border border-slate-200 text-slate-800 outline-none focus:border-blue-300"
                            style={{ fontSize: '12px', fontFamily }}
                        />
                    </div>
                    <div className="overflow-y-auto" style={{ maxHeight: 240 }}>
                        {search ? (
                            filtered.length === 0 ? (
                                <div className="px-2 py-2 text-slate-400" style={{ fontSize: '11px' }}>No results</div>
                            ) : (
                                filtered.map(o => (
                                    <button
                                        key={o.value}
                                        onClick={() => { onChange(o.value); setOpen(false); }}
                                        className={`w-full text-left px-2 py-1 hover:bg-slate-50 transition-colors ${
                                            o.value === value ? 'text-blue-600 font-medium' : 'text-slate-900'
                                        }`}
                                        style={{ fontSize: '12px', fontFamily }}
                                    >
                                        {o.label}
                                    </button>
                                ))
                            )
                        ) : (
                            cats.map(cat => {
                                const catOptions = filtered.filter(o => o.category === cat);
                                if (catOptions.length === 0) return null;
                                return (
                                    <div key={cat}>
                                        <div className="px-2 py-0.5 text-slate-500 font-medium uppercase tracking-wider bg-slate-50 border-b border-slate-100" style={{ fontSize: '10px', fontFamily }}>
                                            {cat}
                                        </div>
                                        {catOptions.map(o => (
                                            <button
                                                key={o.value}
                                                onClick={() => { onChange(o.value); setOpen(false); }}
                                                className={`w-full text-left px-2 py-1 hover:bg-slate-50 transition-colors ${
                                                    o.value === value ? 'text-blue-600 font-medium' : 'text-slate-900'
                                                }`}
                                                style={{ fontSize: '12px', fontFamily }}
                                            >
                                                {o.label}
                                            </button>
                                        ))}
                                    </div>
                                );
                            })
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

function OperatorSelect({
    value,
    onChange,
    options,
    fontFamily,
}: {
    value: string;
    onChange: (value: string) => void;
    options: { value: string; label: string }[];
    fontFamily: string;
}) {
    const [open, setOpen] = useState(false);
    const containerRef = useRef<HTMLDivElement>(null);
    const current = options.find(o => o.value === value);

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        if (open) document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [open]);

    return (
        <div ref={containerRef} className="relative" style={{ fontFamily }}>
            <button
                onClick={() => setOpen(!open)}
                className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-transparent text-slate-900 font-medium hover:border-blue-400 transition-colors border border-slate-200"
                style={{ fontSize: '12px', minWidth: 44 }}
            >
                {current?.label || value}
                <ChevronDown className={`w-2.5 h-2.5 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>

            {open && (
                <div
                    className="absolute top-full left-0 mt-0.5 bg-white border border-slate-200 rounded shadow-lg z-50 overflow-hidden"
                    style={{ minWidth: 100, fontFamily }}
                >
                    {options.map(op => (
                        <button
                            key={op.value}
                            onClick={() => { onChange(op.value); setOpen(false); }}
                            className={`w-full text-left px-2 py-1 hover:bg-slate-50 transition-colors ${
                                op.value === value ? 'text-blue-600 font-medium' : 'text-slate-900'
                            }`}
                            style={{ fontSize: '12px', fontFamily }}
                        >
                            {op.label}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

// ============================================================================
// Filter Builder Component
// ============================================================================

function FilterBuilder({
    filters,
    onFiltersChange,
    fontFamily,
}: {
    filters: FilterCondition[];
    onFiltersChange: (filters: FilterCondition[]) => void;
    fontFamily: string;
}) {
    const addFilter = () => {
        onFiltersChange([
            ...filters,
            { field: 'rsi_14', operator: 'lt', value: 30, compareMode: 'value' },
        ]);
    };

    const addSignal = (signalField: string) => {
        if (filters.some(f => f.field === signalField)) return;
        onFiltersChange([
            ...filters,
            { field: signalField, operator: 'eq', value: true, compareMode: 'value' },
        ]);
    };

    const removeFilter = (index: number) => {
        onFiltersChange(filters.filter((_, i) => i !== index));
    };

    const updateFilter = (index: number, updates: Partial<FilterCondition>) => {
        const newFilters = [...filters];
        newFilters[index] = { ...newFilters[index], ...updates };

        // Switching to field compare mode
        if (updates.compareMode === 'field' && typeof newFilters[index].value !== 'string') {
            const currentField = newFilters[index].field;
            const firstOther = COMPARABLE_FIELDS.find(f => f.value !== currentField);
            newFilters[index].value = firstOther?.value || 'sma_50';
            if (newFilters[index].operator === 'between') {
                newFilters[index].operator = 'gt';
            }
        }

        // Switching to value mode
        if (updates.compareMode === 'value' && typeof newFilters[index].value === 'string') {
            newFilters[index].value = 0;
        }

        // Handle between operator switch
        if (updates.operator === 'between' && !Array.isArray(newFilters[index].value)) {
            const currentField = AVAILABLE_FIELDS.find(f => f.value === newFilters[index].field);
            const currentVal = typeof newFilters[index].value === 'number' ? newFilters[index].value as number : 0;
            if (currentField?.value === 'from_52w_high') {
                newFilters[index].value = [-30, 0];
            } else if (currentField?.value === 'rsi_14') {
                newFilters[index].value = [30, 70];
            } else if (currentField?.value === 'bb_position') {
                newFilters[index].value = [0, 100];
            } else if (currentField?.type === 'percent') {
                newFilters[index].value = [currentVal, currentVal + 10];
            } else {
                newFilters[index].value = [currentVal, currentVal || 100];
            }
            newFilters[index].compareMode = 'value';
        } else if (updates.operator && updates.operator !== 'between' && Array.isArray(newFilters[index].value)) {
            newFilters[index].value = 0;
        }

        onFiltersChange(newFilters);
    };

    const getFieldInfo = (fieldName: string) => {
        return AVAILABLE_FIELDS.find(f => f.value === fieldName);
    };

    const isParametric = (fieldInfo: typeof AVAILABLE_FIELDS[0] | undefined): boolean => {
        return !!fieldInfo?.parametric;
    };

    // Check if a filter is a signal/boolean
    const isSignalFilter = (field: string) => SIGNAL_FIELDS.some(s => s.value === field);

    // Active signal fields
    const activeSignals = filters.filter(f => isSignalFilter(f.field)).map(f => f.field);

    return (
        <div className="space-y-2">
            {/* ── Signal Toggles (boolean conditions) ── */}
            <div className="flex flex-wrap gap-1">
                {SIGNAL_FIELDS.map((signal) => {
                    const isActive = activeSignals.includes(signal.value);
                    return (
                        <button
                            key={signal.value}
                            onClick={() => {
                                if (isActive) {
                                    const idx = filters.findIndex(f => f.field === signal.value);
                                    if (idx >= 0) removeFilter(idx);
                                } else {
                                    addSignal(signal.value);
                                }
                            }}
                            className={`px-2 py-0.5 rounded-full border transition-all ${
                                isActive
                                    ? 'text-blue-600 border-blue-400 bg-blue-50/40'
                                    : 'text-slate-800 border-slate-200 hover:border-slate-300 hover:text-slate-900'
                            }`}
                            style={{ fontSize: '11px', fontFamily }}
                            title={signal.label}
                        >
                            {signal.label}
                        </button>
                    );
                })}
            </div>

            {/* ── Dynamic Filters (numeric / field-vs-field) ── */}
            {filters.filter(f => !isSignalFilter(f.field)).map((filter, _visibleIdx) => {
                const realIndex = filters.indexOf(filter);
                const fieldInfo = getFieldInfo(filter.field);
                const hasParams = isParametric(fieldInfo);
                const currentPeriod = filter.params?.period ?? fieldInfo?.defaultPeriod ?? 14;
                const isFieldMode = filter.compareMode === 'field';
                const operators = isFieldMode ? FIELD_OPERATORS : VALUE_OPERATORS;

                return (
                    <div key={realIndex} className="flex items-center gap-1 bg-white rounded-md border border-slate-200 px-1.5 py-1 shadow-sm">
                        {/* ── Left Field ── */}
                        <FieldSelect
                            value={filter.field}
                            onChange={(val) => updateFilter(realIndex, { field: val, params: undefined })}
                            options={AVAILABLE_FIELDS}
                            fontFamily={fontFamily}
                            minWidth={120}
                        />

                        {/* Period for parametric */}
                        {hasParams && (
                            <input
                                type="number"
                                value={currentPeriod}
                                onChange={(e) => {
                                    const val = parseInt(e.target.value) || 14;
                                    updateFilter(realIndex, {
                                        params: { period: Math.max(2, Math.min(200, val)) }
                                    });
                                }}
                                min={2}
                                max={200}
                                className="w-[36px] px-1 py-0.5 rounded bg-transparent text-blue-600 font-medium border border-blue-200 text-center"
                                style={{ fontSize: '11px', fontFamily }}
                                title="Period (2-200)"
                            />
                        )}

                        {/* ── Operator ── */}
                        <OperatorSelect
                            value={filter.operator}
                            onChange={(val) => updateFilter(realIndex, { operator: val })}
                            options={operators}
                            fontFamily={fontFamily}
                        />

                        {/* ── Mode toggle: Value vs Field ── */}
                        <div className="flex rounded overflow-hidden border border-slate-200">
                            <button
                                onClick={() => updateFilter(realIndex, { compareMode: 'value' })}
                                className={`px-1.5 py-0.5 transition-colors ${
                                    !isFieldMode
                                        ? 'text-blue-600 bg-blue-50/50'
                                        : 'text-slate-800 hover:text-slate-900'
                                }`}
                                style={{ fontSize: '12px', fontWeight: 600, fontFamily }}
                                title="Compare to numeric value"
                            >
                                123
                            </button>
                            <button
                                onClick={() => updateFilter(realIndex, { compareMode: 'field' })}
                                className={`px-1.5 py-0.5 transition-colors border-l border-slate-200 ${
                                    isFieldMode
                                        ? 'text-blue-600 bg-blue-50/50'
                                        : 'text-slate-800 hover:text-slate-900'
                                }`}
                                style={{ fontSize: '12px', fontWeight: 600, fontStyle: 'italic', fontFamily }}
                                title="Compare to another indicator"
                            >
                                fx
                            </button>
                        </div>

                        {/* ── Right Side: Value or Field selector ── */}
                        {isFieldMode ? (
                            <FieldSelect
                                value={typeof filter.value === 'string' ? filter.value : 'sma_50'}
                                onChange={(val) => updateFilter(realIndex, { value: val })}
                                options={AVAILABLE_FIELDS}
                                exclude={filter.field}
                                variant="field-compare"
                                fontFamily={fontFamily}
                                minWidth={120}
                            />
                        ) : filter.operator === 'between' && fieldInfo?.type === 'units' ? (
                            <div className="flex items-center gap-1">
                                <input
                                    type="number"
                                    value={(filter as any).displayMin ?? 0}
                                    onChange={(e) => {
                                        const num = parseFloat(e.target.value) || 0;
                                        const mult = (filter as any).multiplier || 1_000_000;
                                        const max = (filter as any).displayMax ?? 100;
                                        updateFilter(realIndex, {
                                            value: [num * mult, max * mult],
                                            displayMin: num,
                                            displayMax: max,
                                            multiplier: mult
                                        } as any);
                                    }}
                                    className="w-[42px] px-1 py-0.5 rounded border border-slate-300 bg-white text-slate-900 font-medium"
                                    style={{ fontSize: '12px', fontFamily }}
                                />
                                <span className="text-slate-700" style={{ fontSize: '12px', fontFamily }}>to</span>
                                <input
                                    type="number"
                                    value={(filter as any).displayMax ?? 100}
                                    onChange={(e) => {
                                        const num = parseFloat(e.target.value) || 0;
                                        const mult = (filter as any).multiplier || 1_000_000;
                                        const min = (filter as any).displayMin ?? 0;
                                        updateFilter(realIndex, {
                                            value: [min * mult, num * mult],
                                            displayMin: min,
                                            displayMax: num,
                                            multiplier: mult
                                        } as any);
                                    }}
                                    className="w-[42px] px-1 py-0.5 rounded border border-slate-300 bg-white text-slate-900 font-medium"
                                    style={{ fontSize: '12px', fontFamily }}
                                />
                                <select
                                    value={(filter as any).multiplier || 1_000_000}
                                    onChange={(e) => {
                                        const mult = parseInt(e.target.value);
                                        const min = (filter as any).displayMin ?? 0;
                                        const max = (filter as any).displayMax ?? 100;
                                        updateFilter(realIndex, {
                                            value: [min * mult, max * mult],
                                            multiplier: mult
                                        } as any);
                                    }}
                                    className="px-1 py-0.5 rounded border border-slate-300 bg-slate-50 text-slate-900"
                                    style={{ fontSize: '11px', fontFamily }}
                                >
                                    <option value={1000}>K</option>
                                    <option value={1000000}>M</option>
                                    <option value={1000000000}>B</option>
                                </select>
                            </div>
                        ) : filter.operator === 'between' ? (
                            <div className="flex items-center gap-1">
                                <NumberInput
                                    value={Array.isArray(filter.value) ? filter.value[0] : 0}
                                    onChange={(val) => updateFilter(realIndex, {
                                        value: [val, Array.isArray(filter.value) ? filter.value[1] : 0]
                                    })}
                                    className="w-[55px] px-1.5 py-0.5 rounded border border-slate-300 bg-white text-slate-900 font-medium"
                                    style={{ fontSize: '12px' }}
                                />
                                <span className="text-slate-700" style={{ fontSize: '12px', fontFamily }}>to</span>
                                <NumberInput
                                    value={Array.isArray(filter.value) ? filter.value[1] : 0}
                                    onChange={(val) => updateFilter(realIndex, {
                                        value: [Array.isArray(filter.value) ? filter.value[0] : 0, val]
                                    })}
                                    className="w-[55px] px-1.5 py-0.5 rounded border border-slate-300 bg-white text-slate-900 font-medium"
                                    style={{ fontSize: '12px', fontFamily }}
                                />
                                {fieldInfo?.unit && (
                                    <span className="text-slate-700" style={{ fontSize: '11px', fontFamily }}>{fieldInfo.unit}</span>
                                )}
                            </div>
                        ) : fieldInfo?.type === 'units' ? (
                            <div className="flex items-center gap-0.5">
                                <input
                                    type="number"
                                    value={(filter as any).displayValue ?? (typeof filter.value === 'number' ? filter.value : 0)}
                                    onChange={(e) => {
                                        const num = parseFloat(e.target.value) || 0;
                                        const mult = (filter as any).multiplier || 1_000_000;
                                        updateFilter(realIndex, { value: num * mult, displayValue: num, multiplier: mult } as any);
                                    }}
                                    className="w-[48px] px-1.5 py-0.5 rounded-l border border-slate-300 bg-white text-slate-900 font-medium"
                                    style={{ fontSize: '12px', fontFamily }}
                                />
                                <select
                                    value={(filter as any).multiplier || 1_000_000}
                                    onChange={(e) => {
                                        const mult = parseInt(e.target.value);
                                        const num = (filter as any).displayValue ?? 0;
                                        updateFilter(realIndex, { value: num * mult, multiplier: mult } as any);
                                    }}
                                    className="px-1 py-0.5 rounded-r border border-l-0 border-slate-300 bg-slate-50 text-slate-900"
                                    style={{ fontSize: '12px', fontFamily }}
                                >
                                    <option value={1000}>K</option>
                                    <option value={1000000}>M</option>
                                    <option value={1000000000}>B</option>
                                </select>
                            </div>
                        ) : (
                            <div className="flex items-center gap-1">
                                <NumberInput
                                    value={typeof filter.value === 'number' ? filter.value : 0}
                                    onChange={(val) => updateFilter(realIndex, { value: val })}
                                    className="w-[60px] px-1.5 py-0.5 rounded border border-slate-300 bg-white text-slate-900 font-medium"
                                    style={{ fontSize: '12px', fontFamily }}
                                />
                                {fieldInfo?.unit && (
                                    <span className="text-slate-700" style={{ fontSize: '11px', fontFamily }}>{fieldInfo.unit}</span>
                                )}
                            </div>
                        )}

                        {/* Remove */}
                        <button
                            onClick={() => removeFilter(realIndex)}
                            className="p-0.5 text-slate-400 hover:text-red-500 ml-auto"
                        >
                            <X className="w-3 h-3" />
                        </button>
                    </div>
                );
            })}

            <button
                onClick={addFilter}
                className="flex items-center gap-1 px-2 py-1 text-blue-600 hover:bg-blue-50 rounded border border-dashed border-blue-200"
                style={{ fontSize: '12px' }}
            >
                <Plus className="w-3 h-3" />
                Add Filter
            </button>
        </div>
    );
}

// ============================================================================
// Results Table Component with TanStack Table (drag & drop columns)
// ============================================================================

const screenerColumnHelper = createColumnHelper<ScreenerResult>();

// Formatters
const formatPrice = (value: number | null) => {
    if (value === null || value === undefined) return '-';
    if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
    if (value >= 1) return `$${value.toFixed(2)}`;
    return `$${value.toFixed(4)}`;
};

const formatPercent = (value: number | null) => {
    if (value === null || value === undefined) return '-';
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(2)}%`;
};

const formatVolume = (value: number | null) => {
    if (value === null || value === undefined) return '-';
    if (value >= 1000000000) return `${(value / 1000000000).toFixed(1)}B`;
    if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
    if (value >= 1000) return `${(value / 1000).toFixed(0)}K`;
    return value.toString();
};

const formatMultiplier = (value: number | null) => {
    if (value === null || value === undefined) return '-';
    return `${value.toFixed(2)}x`;
};

const formatRSI = (value: number | null) => {
    if (value === null || value === undefined) return '-';
    return value.toFixed(0);
};

const formatNumber = (value: number | null, decimals = 1) => {
    if (value === null || value === undefined) return '-';
    return value.toFixed(decimals);
};

const getChangeColor = (value: number | null) => {
    if (value === null) return 'text-slate-400';
    return value >= 0 ? 'text-emerald-600' : 'text-red-500';
};

// Storage helpers for persistence
const SCREENER_STORAGE_KEY = 'screener_table';
const loadScreenerStorage = <T,>(key: string, defaultValue: T): T => {
    if (typeof window === 'undefined') return defaultValue;
    try {
        const stored = localStorage.getItem(`${SCREENER_STORAGE_KEY}_${key}`);
        return stored ? JSON.parse(stored) : defaultValue;
    } catch {
        return defaultValue;
    }
};

const saveScreenerStorage = (key: string, value: unknown) => {
    if (typeof window === 'undefined') return;
    try {
        localStorage.setItem(`${SCREENER_STORAGE_KEY}_${key}`, JSON.stringify(value));
    } catch {
        // Silent fail
    }
};

// Default visible columns (the rest start hidden)
const DEFAULT_VISIBLE_COLUMNS: Record<string, boolean> = {
    symbol: true, price: true, change_1d: true, change_5d: true,
    market_cap: true, rsi_14: true, relative_volume: true, from_52w_high: true,
    volume: true, sector: true,
};

// Column definitions — all available indicators
const screenerColumns = [
    // ── Identity ──
    screenerColumnHelper.accessor('symbol', {
        header: 'Symbol',
        size: 80,
        enableHiding: false,
        cell: (info) => {
            const symbol = info.getValue();
            const onSymbolClick = info.table.options.meta?.onSymbolClick;
            return (
                <button
                    onClick={() => onSymbolClick?.(symbol)}
                    className="font-semibold text-blue-600 hover:text-blue-800 hover:underline cursor-pointer"
                >
                    {symbol}
                </button>
            );
        },
    }),
    screenerColumnHelper.accessor('sector', {
        header: 'Sector',
        size: 90,
        cell: (info) => <span className="text-slate-700 truncate">{info.getValue() || '-'}</span>,
    }),

    // ── Price ──
    screenerColumnHelper.accessor('price', {
        header: 'Price',
        size: 75,
        cell: (info) => <span className="text-slate-900">{formatPrice(info.getValue())}</span>,
    }),

    // ── Changes ──
    screenerColumnHelper.accessor('change_1d', {
        header: '1D%',
        size: 65,
        cell: (info) => {
            const v = info.getValue();
            return <span className={`font-medium ${getChangeColor(v)}`}>{formatPercent(v)}</span>;
        },
    }),
    screenerColumnHelper.accessor('change_3d', {
        header: '3D%',
        size: 65,
        cell: (info) => {
            const v = info.getValue();
            return <span className={`font-medium ${getChangeColor(v)}`}>{formatPercent(v)}</span>;
        },
    }),
    screenerColumnHelper.accessor('change_5d', {
        header: '5D%',
        size: 65,
        cell: (info) => {
            const v = info.getValue();
            return <span className={`font-medium ${getChangeColor(v)}`}>{formatPercent(v)}</span>;
        },
    }),
    screenerColumnHelper.accessor('change_10d', {
        header: '10D%',
        size: 65,
        cell: (info) => {
            const v = info.getValue();
            return <span className={`font-medium ${getChangeColor(v)}`}>{formatPercent(v)}</span>;
        },
    }),
    screenerColumnHelper.accessor('change_20d', {
        header: '20D%',
        size: 65,
        cell: (info) => {
            const v = info.getValue();
            return <span className={`font-medium ${getChangeColor(v)}`}>{formatPercent(v)}</span>;
        },
    }),
    screenerColumnHelper.accessor('gap_percent', {
        header: 'Gap%',
        size: 65,
        cell: (info) => {
            const v = info.getValue();
            return <span className={`font-medium ${getChangeColor(v)}`}>{formatPercent(v)}</span>;
        },
    }),

    // ── Volume ──
    screenerColumnHelper.accessor('volume', {
        header: 'Volume',
        size: 80,
        cell: (info) => <span className="text-slate-900">{formatVolume(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('relative_volume', {
        header: 'RVol',
        size: 65,
        cell: (info) => <span className="text-slate-900">{formatMultiplier(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('avg_volume_20', {
        header: 'AvgVol 20',
        size: 80,
        cell: (info) => <span className="text-slate-900">{formatVolume(info.getValue())}</span>,
    }),

    // ── Fundamentals ──
    screenerColumnHelper.accessor('market_cap', {
        header: 'MCap',
        size: 80,
        cell: (info) => <span className="text-slate-900">{formatVolume(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('free_float', {
        id: 'free_float',
        header: 'Float',
        size: 80,
        cell: (info) => <span className="text-slate-900">{formatVolume(info.getValue())}</span>,
    }),

    // ── 52 Week ──
    screenerColumnHelper.accessor('from_52w_high', {
        header: 'Fr. 52H',
        size: 70,
        cell: (info) => {
            const v = info.getValue();
            const near = v !== null && v > -5;
            return <span className={near ? 'text-emerald-600 font-medium' : 'text-slate-900'}>{formatPercent(v)}</span>;
        },
    }),
    screenerColumnHelper.accessor('from_52w_low', {
        header: 'Fr. 52L',
        size: 70,
        cell: (info) => {
            const v = info.getValue();
            return <span className={`font-medium ${getChangeColor(v)}`}>{formatPercent(v)}</span>;
        },
    }),
    screenerColumnHelper.accessor('high_52w', {
        header: '52W High',
        size: 75,
        cell: (info) => <span className="text-slate-900">{formatPrice(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('low_52w', {
        header: '52W Low',
        size: 75,
        cell: (info) => <span className="text-slate-900">{formatPrice(info.getValue())}</span>,
    }),

    // ── Momentum ──
    screenerColumnHelper.accessor('rsi_14', {
        header: 'RSI',
        size: 55,
        cell: (info) => {
            const v = info.getValue();
            if (v === null) return <span className="text-slate-400">-</span>;
            const color = v < 30 ? 'text-red-500' : v > 70 ? 'text-emerald-600' : 'text-slate-900';
            return <span className={color}>{v.toFixed(0)}</span>;
        },
    }),

    // ── Trend / SMAs ──
    screenerColumnHelper.accessor('sma_20', {
        header: 'SMA 20',
        size: 75,
        cell: (info) => <span className="text-slate-900">{formatPrice(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('sma_50', {
        header: 'SMA 50',
        size: 75,
        cell: (info) => <span className="text-slate-900">{formatPrice(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('sma_200', {
        header: 'SMA 200',
        size: 75,
        cell: (info) => <span className="text-slate-900">{formatPrice(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('dist_sma_20', {
        header: 'Dist SMA20',
        size: 75,
        cell: (info) => {
            const v = info.getValue();
            return <span className={`font-medium ${getChangeColor(v)}`}>{formatPercent(v)}</span>;
        },
    }),
    screenerColumnHelper.accessor('dist_sma_50', {
        header: 'Dist SMA50',
        size: 75,
        cell: (info) => {
            const v = info.getValue();
            return <span className={`font-medium ${getChangeColor(v)}`}>{formatPercent(v)}</span>;
        },
    }),

    // ── Volatility / ATR ──
    screenerColumnHelper.accessor('atr_14', {
        header: 'ATR',
        size: 65,
        cell: (info) => <span className="text-slate-900">{formatPrice(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('atr_percent', {
        header: 'ATR%',
        size: 65,
        cell: (info) => <span className="text-slate-900">{formatPercent(info.getValue())}</span>,
    }),

    // ── Bollinger Bands ──
    screenerColumnHelper.accessor('bb_upper', {
        header: 'BB Up',
        size: 70,
        cell: (info) => <span className="text-slate-900">{formatPrice(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('bb_lower', {
        header: 'BB Low',
        size: 70,
        cell: (info) => <span className="text-slate-900">{formatPrice(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('bb_width', {
        header: 'BB W%',
        size: 65,
        cell: (info) => {
            const v = info.getValue();
            return <span className="text-slate-900">{v !== null ? `${v.toFixed(1)}%` : '-'}</span>;
        },
    }),
    screenerColumnHelper.accessor('bb_position', {
        header: 'BB Pos%',
        size: 65,
        cell: (info) => <span className="text-slate-900">{formatPercent(info.getValue())}</span>,
    }),

    // ── Keltner Channels ──
    screenerColumnHelper.accessor('keltner_upper', {
        header: 'KC Up',
        size: 70,
        cell: (info) => <span className="text-slate-900">{formatPrice(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('keltner_lower', {
        header: 'KC Low',
        size: 70,
        cell: (info) => <span className="text-slate-900">{formatPrice(info.getValue())}</span>,
    }),

    // ── TTM Squeeze ──
    screenerColumnHelper.accessor('squeeze_on', {
        header: 'Squeeze',
        size: 65,
        cell: (info) => {
            const v = info.getValue();
            if (v === null) return <span className="text-slate-400">-</span>;
            return <span className={v === 1 ? 'text-amber-600 font-medium' : 'text-slate-500'}>{v === 1 ? 'ON' : 'OFF'}</span>;
        },
    }),
    screenerColumnHelper.accessor('squeeze_momentum', {
        header: 'Sq. Mom',
        size: 70,
        cell: (info) => {
            const v = info.getValue();
            return <span className={`font-medium ${getChangeColor(v)}`}>{formatNumber(v, 2)}</span>;
        },
    }),

    // ── ADX / Directional ──
    screenerColumnHelper.accessor('adx_14', {
        header: 'ADX',
        size: 55,
        cell: (info) => {
            const v = info.getValue();
            if (v === null) return <span className="text-slate-400">-</span>;
            const strong = v > 25;
            return <span className={strong ? 'text-slate-900 font-medium' : 'text-slate-600'}>{v.toFixed(0)}</span>;
        },
    }),
    screenerColumnHelper.accessor('plus_di_14', {
        header: '+DI',
        size: 55,
        cell: (info) => <span className="text-emerald-600">{formatNumber(info.getValue(), 0)}</span>,
    }),
    screenerColumnHelper.accessor('minus_di_14', {
        header: '-DI',
        size: 55,
        cell: (info) => <span className="text-red-500">{formatNumber(info.getValue(), 0)}</span>,
    }),
];

function ResultsTable({
    results,
    onSymbolClick,
    fontFamily,
}: {
    results: ScreenerResult[];
    onSymbolClick?: (symbol: string) => void;
    fontFamily?: string;
}) {
    // Load persisted state
    const [sorting, setSorting] = useState<SortingState>(() =>
        loadScreenerStorage('sorting', [])
    );
    const [columnOrder, setColumnOrder] = useState<ColumnOrderState>(() =>
        loadScreenerStorage('columnOrder', [])
    );
    const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>(() => {
        const stored = loadScreenerStorage<Record<string, boolean> | null>('columnVisibility', null);
        if (stored !== null) return stored;
        const defaults: Record<string, boolean> = {};
        screenerColumns.forEach(col => {
            const id = (col as any).accessorKey || (col as any).id;
            if (id && id !== 'symbol') {
                defaults[id] = !!DEFAULT_VISIBLE_COLUMNS[id];
            }
        });
        return defaults;
    });

    // Persist changes
    useEffect(() => {
        saveScreenerStorage('sorting', sorting);
    }, [sorting]);

    useEffect(() => {
        saveScreenerStorage('columnOrder', columnOrder);
    }, [columnOrder]);

    useEffect(() => {
        saveScreenerStorage('columnVisibility', columnVisibility);
    }, [columnVisibility]);

    const table = useReactTable({
        data: results,
        columns: screenerColumns,
        state: {
            sorting,
            columnOrder,
            columnVisibility,
        },
        onSortingChange: setSorting,
        onColumnOrderChange: setColumnOrder,
        onColumnVisibilityChange: setColumnVisibility,
        getCoreRowModel: getCoreRowModel(),
        getSortedRowModel: getSortedRowModel(),
        meta: {
            onSymbolClick,
        },
    });

    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const rows = table.getRowModel().rows;

    const rowVirtualizer = useVirtualizer({
        count: rows.length,
        getScrollElement: () => scrollContainerRef.current,
        estimateSize: () => 30,
        overscan: 10,
    });

    const virtualRows = rowVirtualizer.getVirtualItems();
    const totalSize = rowVirtualizer.getTotalSize();
    const paddingTop = virtualRows.length > 0 ? virtualRows[0].start : 0;
    const paddingBottom = virtualRows.length > 0
        ? totalSize - virtualRows[virtualRows.length - 1].end
        : 0;

    return (
        <div className="flex-1 flex flex-col overflow-hidden">
            {/* Table Settings */}
            <div className="flex-shrink-0 flex justify-end px-2 py-1 bg-slate-50/50 border-b border-slate-100">
                <TableSettings
                    table={table}
                    fontFamily={fontFamily}
                    onResetToDefaults={() => {
                        const defaults: Record<string, boolean> = {};
                        screenerColumns.forEach(col => {
                            const id = (col as any).accessorKey || (col as any).id;
                            if (id && id !== 'symbol') {
                                defaults[id] = !!DEFAULT_VISIBLE_COLUMNS[id];
                            }
                        });
                        table.setColumnVisibility(defaults);
                    }}
                />
            </div>

            {/* Table (virtualized) */}
            <div ref={scrollContainerRef} className="overflow-auto flex-1">
                <table className="w-full text-left" style={{ fontSize: '12px', fontFamily }}>
                    <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 z-10">
                        {table.getHeaderGroups().map((headerGroup) => (
                            <tr key={headerGroup.id}>
                                {headerGroup.headers.map((header, headerIndex) => {
                                    const isFirstColumn = headerIndex === 0;
                                    return (
                                        <th
                                            key={header.id}
                                            draggable={true}
                                            onDragStart={(e) => {
                                                e.dataTransfer.effectAllowed = 'move';
                                                e.dataTransfer.setData('text/plain', header.column.id);
                                            }}
                                            onDragOver={(e) => {
                                                e.preventDefault();
                                                e.dataTransfer.dropEffect = 'move';
                                            }}
                                            onDrop={(e) => {
                                                e.preventDefault();
                                                const draggedColumnId = e.dataTransfer.getData('text/plain');
                                                const targetColumnId = header.column.id;

                                                if (draggedColumnId !== targetColumnId) {
                                                    const currentOrder = table.getState().columnOrder.length > 0
                                                        ? table.getState().columnOrder
                                                        : table.getAllLeafColumns().map((c) => c.id);

                                                    const draggedIndex = currentOrder.indexOf(draggedColumnId);
                                                    const targetIndex = currentOrder.indexOf(targetColumnId);

                                                    const newOrder = [...currentOrder];
                                                    newOrder.splice(draggedIndex, 1);
                                                    newOrder.splice(targetIndex, 0, draggedColumnId);

                                                    table.setColumnOrder(newOrder);
                                                }
                                            }}
                                            className={`px-2 py-1.5 font-semibold text-slate-900 cursor-grab select-none hover:bg-slate-100 ${isFirstColumn ? 'text-left' : 'text-right'}`}
                                            style={{ width: header.getSize(), fontSize: '11px' }}
                                            onClick={header.column.getToggleSortingHandler()}
                                        >
                                            <div className={`flex items-center gap-1 ${isFirstColumn ? 'justify-start' : 'justify-end'}`}>
                                                {flexRender(header.column.columnDef.header, header.getContext())}
                                                {{
                                                    asc: ' ↑',
                                                    desc: ' ↓',
                                                }[header.column.getIsSorted() as string] ?? null}
                                            </div>
                                        </th>
                                    );
                                })}
                            </tr>
                        ))}
                    </thead>
                    <tbody>
                        {paddingTop > 0 && (
                            <tr><td colSpan={table.getVisibleLeafColumns().length} style={{ height: paddingTop, padding: 0, border: 'none' }} /></tr>
                        )}
                        {virtualRows.map((virtualRow) => {
                            const row = rows[virtualRow.index];
                            const i = virtualRow.index;
                            return (
                                <tr
                                    key={row.id}
                                    className={`border-b border-slate-50 hover:bg-slate-50/80 ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/30'}`}
                                >
                                    {row.getVisibleCells().map((cell, cellIndex) => {
                                        const isFirstColumn = cellIndex === 0;
                                        return (
                                            <td
                                                key={cell.id}
                                                className={`px-2 py-1.5 ${isFirstColumn ? 'text-left' : 'text-right'}`}
                                            >
                                                {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                            </td>
                                        );
                                    })}
                                </tr>
                            );
                        })}
                        {paddingBottom > 0 && (
                            <tr><td colSpan={table.getVisibleLeafColumns().length} style={{ height: paddingBottom, padding: 0, border: 'none' }} /></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

// ============================================================================
// Main Component
// ============================================================================

export function ScreenerContent() {
    const font = useUserPreferencesStore(selectFont);
    const fontFamily = `var(--font-${font})`;
    const { state: windowState, updateState: updateWindowState } = useWindowState<ScreenerWindowState>();

    // Default filters
    const defaultFilters: FilterCondition[] = [
        { field: 'price', operator: 'between', value: [5, 500] },
        { field: 'volume', operator: 'gt', value: 500000 },
    ];

    // State - use persisted values if available
    const [filters, setFilters] = useState<FilterCondition[]>(windowState.filters || defaultFilters);
    const [symbols, setSymbols] = useState<string[]>([]);
    const [symbolInput, setSymbolInput] = useState('');
    const [sortBy, setSortBy] = useState(windowState.sortBy || 'relative_volume');
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(windowState.sortOrder || 'desc');
    const [limit, setLimit] = useState(windowState.limit || 50);

    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [results, setResults] = useState<ScreenerResult[]>([]);
    const [queryTime, setQueryTime] = useState<number | null>(null);

    const [activePreset, setActivePreset] = useState<string | null>(windowState.activePreset ?? null);
    const [showFilters, setShowFilters] = useState(true);
    const { executeCommand, executeTickerCommand } = useCommandExecutor();

    // User templates
    const {
        templates: userTemplates,
        loading: templatesLoading,
        listTemplates,
        createTemplate,
        deleteTemplate,
        useTemplate,
        toggleFavorite,
    } = useScreenerTemplates();
    const [showSaveModal, setShowSaveModal] = useState(false);
    const [templateName, setTemplateName] = useState('');
    const [activeUserTemplate, setActiveUserTemplate] = useState<number | null>(windowState.activeUserTemplate ?? null);

    // Track if auto-execute has been done
    const autoExecutedRef = useRef(false);
    // Ref to handleSearch for use in effect
    const handleSearchRef = useRef<(() => void) | null>(null);

    // Load user templates on mount
    useEffect(() => {
        listTemplates();
    }, [listTemplates]);

    // Persist state changes (only after first render with results)
    const hasResultsRef = useRef(false);
    useEffect(() => {
        if (results.length > 0) hasResultsRef.current = true;

        // Only persist if we have meaningful state
        if (hasResultsRef.current || filters !== defaultFilters) {
            updateWindowState({
                filters,
                sortBy,
                sortOrder,
                limit,
                activePreset,
                activeUserTemplate,
                autoExecute: hasResultsRef.current,
            });
        }
    }, [filters, sortBy, sortOrder, limit, activePreset, activeUserTemplate, results.length, updateWindowState]);

    // Auto-execute when windowState becomes available (may be delayed due to hydration)
    useEffect(() => {
        // Only execute once, when we have saved state
        if (!autoExecutedRef.current && windowState.autoExecute && windowState.filters && windowState.filters.length > 0) {
            autoExecutedRef.current = true;

            // Update local state from windowState if different
            if (JSON.stringify(filters) !== JSON.stringify(windowState.filters)) {
                setFilters(windowState.filters as FilterCondition[]);
            }
            if (windowState.sortBy && sortBy !== windowState.sortBy) {
                setSortBy(windowState.sortBy);
            }
            if (windowState.sortOrder && sortOrder !== windowState.sortOrder) {
                setSortOrder(windowState.sortOrder);
            }
            if (windowState.limit && limit !== windowState.limit) {
                setLimit(windowState.limit);
            }

            // Execute search after state update
            const timer = setTimeout(() => {
                handleSearchRef.current?.();
            }, 200);
            return () => clearTimeout(timer);
        }
    }, [windowState.autoExecute, windowState.filters, windowState.sortBy, windowState.sortOrder, windowState.limit]);

    // Search handler
    const handleSearch = useCallback(async () => {
        setLoading(true);
        setError(null);

        try {
            const cleanFilters = filters.map(f => {
                const clean: any = { field: f.field, operator: f.operator, value: f.value };
                if (f.params) clean.params = f.params;
                return clean;
            });

            const body: any = {
                filters: cleanFilters,
                sort_by: sortBy,
                sort_order: sortOrder,
                limit,
            };

            if (symbols.length > 0) {
                body.symbols = symbols;
            }

            const res = await fetch(`${API_BASE}/screen`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            const data: ScreenerResponse = await res.json();

            if (data.status === 'error') {
                throw new Error(data.errors?.join(', ') || 'Search failed');
            }

            setResults(data.results);
            setQueryTime(data.query_time_ms);
        } catch (e: any) {
            setError(e.message);
            setResults([]);
        } finally {
            setLoading(false);
        }
    }, [filters, symbols, sortBy, sortOrder, limit]);

    // Update ref for auto-execute
    useEffect(() => {
        handleSearchRef.current = handleSearch;
    }, [handleSearch]);

    // Add symbol to filter
    const handleAddSymbol = useCallback((selected: TickerSearchResult) => {
        if (!symbols.includes(selected.symbol)) {
            setSymbols([...symbols, selected.symbol]);
        }
        setSymbolInput('');
    }, [symbols]);

    const handleRemoveSymbol = (symbol: string) => {
        setSymbols(symbols.filter(s => s !== symbol));
    };

    // Apply preset - loads filters as editable template
    const applyPreset = (preset: Preset) => {
        const clonedFilters = preset.filters.map(f => ({
            ...f,
            value: Array.isArray(f.value) ? [...f.value] : f.value,
            compareMode: 'value' as const,
        }));
        setFilters(clonedFilters);
        setSortBy(preset.sort_by);
        setSortOrder(preset.sort_order as 'asc' | 'desc');
        setActivePreset(preset.id);
        setShowFilters(true); // Always show filters when selecting a preset
    };

    // Clear preset selection when filters are manually modified
    const handleFiltersChange = (newFilters: FilterCondition[]) => {
        setFilters(newFilters);
        // Don't clear activePreset here - let user see which preset they started from
    };

    // Save current config as template
    const handleSaveTemplate = async () => {
        if (!templateName.trim()) return;

        const templateFilters: TemplateFilterCondition[] = filters.map(f => ({
            field: f.field,
            operator: f.operator,
            value: f.compareMode === 'field' ? undefined : (typeof f.value === 'string' ? undefined : f.value),
            compare_field: f.compareMode === 'field' && typeof f.value === 'string' ? f.value : undefined,
            params: f.params ?? undefined,
        }));

        const result = await createTemplate({
            name: templateName.trim(),
            filters: templateFilters,
            sort_by: sortBy,
            sort_order: sortOrder,
            limit_results: limit,
        });

        if (result) {
            setShowSaveModal(false);
            setTemplateName('');
        }
    };

    // Apply user template
    const applyUserTemplate = async (template: ScreenerTemplate) => {
        const loadedFilters: FilterCondition[] = template.filters.map(f => ({
            field: f.field,
            operator: f.operator,
            value: f.compare_field ? f.compare_field : (f.value as number | number[] | boolean),
            compareMode: f.compare_field ? 'field' as const : 'value' as const,
            params: f.params ?? undefined,
        }));

        setFilters(loadedFilters);
        setSortBy(template.sortBy);
        setSortOrder(template.sortOrder as 'asc' | 'desc');
        setLimit(template.limitResults);
        setActivePreset(null);
        setActiveUserTemplate(template.id);
        setShowFilters(true);

        // Track usage
        useTemplate(template.id);
    };

    return (
        <div className="h-full flex flex-col bg-white text-slate-800" style={{ fontFamily }}>
            {/* Compact Header */}
            <div className="flex-shrink-0 px-2 py-1.5 border-b border-slate-100 flex items-center gap-2" style={{ fontFamily }}>
                <div className="w-[140px]">
                    <TickerSearch
                        value={symbolInput}
                        onChange={setSymbolInput}
                        onSelect={handleAddSymbol}
                        placeholder="Symbol..."
                        className="w-full"
                    />
                </div>
                {symbols.length > 0 && (
                    <div className="flex items-center gap-0.5">
                        {symbols.map((s) => (
                            <span
                                key={s}
                                className="inline-flex items-center gap-0.5 px-1 py-0.5 bg-blue-50 text-blue-700 rounded"
                                style={{ fontSize: '11px' }}
                            >
                                {s}
                                <button onClick={() => handleRemoveSymbol(s)} className="hover:text-red-500">
                                    <X className="w-2 h-2" />
                                </button>
                            </span>
                        ))}
                    </div>
                )}
                <div className="flex-1" />
                {queryTime !== null && (
                    <span className="text-slate-500" style={{ fontSize: '11px', fontFamily }}>
                        {queryTime < 1000 ? `${queryTime.toFixed(0)}ms` : `${(queryTime / 1000).toFixed(1)}s`}
                    </span>
                )}
                <button
                    onClick={() => setShowFilters(!showFilters)}
                    className={`p-1 rounded transition-colors ${showFilters ? 'bg-blue-50 text-blue-600' : 'text-slate-500 hover:text-slate-700'}`}
                >
                    <Settings2 className="w-3.5 h-3.5" />
                </button>
                <button
                    onClick={handleSearch}
                    disabled={loading}
                    className="flex items-center gap-1 px-2.5 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                    style={{ fontSize: '12px', fontFamily }}
                >
                    {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
                    Scan
                </button>
            </div>

            {/* Templates Row - Compact with dropdown for system presets */}
            <div className="flex-shrink-0 px-2 py-1.5 border-b border-slate-100 bg-slate-50/30" style={{ fontFamily }}>
                <div className="flex items-center gap-1.5">
                    {/* System Presets Dropdown */}
                    <div className="relative">
                        <select
                            value={activePreset || ''}
                            onChange={(e) => {
                                const preset = PRESETS.find(p => p.id === e.target.value);
                                if (preset) {
                                    applyPreset(preset);
                                    setActiveUserTemplate(null);
                                }
                            }}
                            className={`px-2 py-1 rounded border text-slate-900 bg-white cursor-pointer appearance-none pr-6 ${activePreset && !activeUserTemplate ? 'border-blue-400 bg-blue-50/50 text-blue-700' : 'border-slate-200 hover:border-slate-300'
                                }`}
                            style={{ fontSize: '12px', fontFamily }}
                        >
                            <option value="">Presets</option>
                            {PRESETS.map((preset) => (
                                <option key={preset.id} value={preset.id}>{preset.name}</option>
                            ))}
                        </select>
                        <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400 pointer-events-none" />
                    </div>

                    {/* Separator */}
                    <div className="h-4 w-px bg-slate-200" />

                    {/* User templates */}
                    <div className="flex items-center gap-1 overflow-x-auto">
                        {userTemplates.map((template) => (
                            <div key={template.id} className="flex-shrink-0 flex items-center group">
                                <button
                                    onClick={() => applyUserTemplate(template)}
                                    className={`flex items-center gap-1 px-2 py-1 rounded-l border transition-all ${activeUserTemplate === template.id
                                        ? 'border-blue-400 bg-blue-50/50 text-blue-700 shadow-sm'
                                        : 'border-slate-200 text-slate-900 hover:border-blue-300 hover:bg-blue-50/50'
                                        }`}
                                    style={{ fontSize: '12px', fontFamily }}
                                    title={`${template.name} (${template.useCount}x)`}
                                >
                                    {template.isFavorite && <Star className="w-2.5 h-2.5 fill-amber-400 text-amber-400" />}
                                    {template.name}
                                </button>
                                <button
                                    onClick={() => deleteTemplate(template.id)}
                                    className="px-1 py-1 border border-l-0 border-slate-200 rounded-r text-slate-500 hover:text-red-500 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-opacity"
                                    style={{ fontSize: '12px' }}
                                    title="Delete"
                                >
                                    <X className="w-2.5 h-2.5" />
                                </button>
                            </div>
                        ))}

                        {/* Save button */}
                        <button
                            onClick={() => setShowSaveModal(true)}
                            className="flex-shrink-0 flex items-center gap-1 px-2 py-1 rounded border border-dashed border-slate-300 text-slate-500 hover:border-blue-400 hover:text-blue-600 hover:bg-blue-50/50 transition-all"
                            style={{ fontSize: '12px' }}
                            title="Save current configuration"
                        >
                            <Save className="w-3 h-3" />
                        </button>
                    </div>
                </div>
            </div>

            {/* Save Template Modal */}
            {showSaveModal && (
                <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setShowSaveModal(false)}>
                    <div
                        className="bg-white rounded-lg shadow-xl p-4 w-80"
                        onClick={e => e.stopPropagation()}
                        style={{ fontFamily }}
                    >
                        <h3 className="font-medium text-slate-800 mb-3" style={{ fontSize: '13px' }}>Save Template</h3>
                        <input
                            type="text"
                            value={templateName}
                            onChange={(e) => setTemplateName(e.target.value)}
                            placeholder="Template name..."
                            className="w-full px-3 py-2 border border-slate-200 rounded focus:outline-none focus:border-blue-400"
                            style={{ fontSize: '12px' }}
                            autoFocus
                            onKeyDown={(e) => e.key === 'Enter' && handleSaveTemplate()}
                        />
                        <div className="flex justify-end gap-2 mt-3">
                            <button
                                onClick={() => setShowSaveModal(false)}
                                className="px-3 py-1.5 text-slate-900 hover:bg-slate-100 rounded"
                                style={{ fontSize: '11px', fontFamily }}
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleSaveTemplate}
                                disabled={!templateName.trim()}
                                className="px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                                style={{ fontSize: '11px' }}
                            >
                                Save
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Filters Panel - Always editable */}
            {showFilters && (
                <div className="flex-shrink-0 px-2 py-2 border-b border-slate-100 bg-slate-50/50">
                    <FilterBuilder filters={filters} onFiltersChange={handleFiltersChange} fontFamily={fontFamily} />

                    {/* Sort controls */}
                    <div className="flex items-center gap-2 mt-2 pt-2 border-t border-slate-200">
                        <span className="text-slate-800" style={{ fontSize: '11px', fontFamily }}>Sort:</span>
                        <select
                            value={sortBy}
                            onChange={(e) => setSortBy(e.target.value)}
                            className="px-1.5 py-0.5 rounded border border-slate-200 bg-white text-slate-900"
                            style={{ fontSize: '12px', fontFamily }}
                        >
                            {SORT_OPTIONS.map((opt) => (
                                <option key={opt.value} value={opt.value}>{opt.label}</option>
                            ))}
                        </select>
                        <button
                            onClick={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
                            className={`px-1.5 py-0.5 rounded border text-slate-900 hover:bg-slate-100 ${sortOrder === 'asc' ? 'border-blue-300 bg-blue-50/50' : 'border-slate-200'
                                }`}
                            style={{ fontSize: '12px', fontFamily }}
                        >
                            {sortOrder === 'desc' ? 'DESC' : 'ASC'}
                        </button>
                        <div className="flex-1" />
                        <button
                            onClick={() => executeCommand('glossary')}
                            className="p-1 rounded hover:bg-slate-100 text-slate-500 hover:text-slate-700"
                            title="Indicator glossary"
                        >
                            <HelpCircle className="w-3.5 h-3.5" />
                        </button>
                        <select
                            value={limit}
                            onChange={(e) => setLimit(parseInt(e.target.value))}
                            className="px-1.5 py-0.5 rounded border border-slate-200 bg-white text-slate-900"
                            style={{ fontSize: '12px', fontFamily }}
                        >
                            <option value={25}>25 results</option>
                            <option value={50}>50 results</option>
                            <option value={100}>100 results</option>
                        </select>
                    </div>
                </div>
            )}

            {/* Error */}
            {error && (
                <div className="px-4 py-2 bg-red-50 border-b border-red-100">
                    <div className="flex items-center gap-2 text-red-600" style={{ fontSize: '11px' }}>
                        <AlertCircle className="w-4 h-4" />
                        {error}
                    </div>
                </div>
            )}

            {/* Results */}
            {results.length > 0 ? (
                <ResultsTable
                    results={results}
                    onSymbolClick={(symbol) => executeTickerCommand(symbol, 'chart')}
                    fontFamily={fontFamily}
                />
            ) : (
                <div className="flex-1 flex items-center justify-center text-slate-700" style={{ fontSize: '13px', fontFamily }}>
                    {loading ? (
                        <div className="flex items-center gap-1.5">
                            <Loader2 className="w-4 h-4 animate-spin" />
                            Scanning...
                        </div>
                    ) : (
                        <div className="text-center">
                            <Filter className="w-6 h-6 mx-auto mb-2 opacity-30" />
                            <p className="mb-1">Select a preset or customize filters</p>
                            <p className="text-slate-400">Then click Scan</p>
                        </div>
                    )}
                </div>
            )}

            {/* Footer */}
            {results.length > 0 && (
                <div className="flex-shrink-0 px-2 py-1 border-t border-slate-100 bg-slate-50/50">
                    <div className="flex items-center justify-between text-slate-700" style={{ fontSize: '11px', fontFamily }}>
                        <span>{results.length} results</span>
                        <span>Daily Data</span>
                    </div>
                </div>
            )}
        </div>
    );
}
