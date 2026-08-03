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
    ChevronLeft,
    ChevronRight,
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
import { useAuth } from '@clerk/nextjs';
import { TickerSearch } from '@/components/common/TickerSearch';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { useScreenerTemplates, type ScreenerTemplate, type FilterCondition as TemplateFilterCondition } from '@/hooks/useScreenerTemplates';
import { useWindowState, useFloatingWindowActions } from '@/contexts/FloatingWindowContext';
import { useLinkGroupPublisher } from '@/hooks/useLinkGroup';
import { openLinkedTVChart } from '@/lib/openLinkedTVChart';

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

// Default multiplier when no metadata is available (used to render the K/M/B select)
const DEFAULT_UNIT_MULTIPLIER = 1_000_000;

/**
 * Infer the (multiplier, displayValue) pair from an absolute value.
 * Picks the largest multiplier that keeps `displayValue` an integer
 * and >= 1. Falls back to K so values like 500_000 render as "500 K"
 * instead of "0.5 M". Used when loading templates / persisted state
 * that don't carry the UI metadata.
 */
function inferDisplayUnit(value: number): { multiplier: number; displayValue: number } {
    if (!Number.isFinite(value) || value <= 0) {
        return { multiplier: DEFAULT_UNIT_MULTIPLIER, displayValue: 0 };
    }
    if (value >= 1_000_000_000 && value % 1_000_000_000 === 0) {
        return { multiplier: 1_000_000_000, displayValue: value / 1_000_000_000 };
    }
    if (value >= 1_000_000 && value % 1_000_000 === 0) {
        return { multiplier: 1_000_000, displayValue: value / 1_000_000 };
    }
    if (value >= 1_000 && value % 1_000 === 0) {
        return { multiplier: 1_000, displayValue: value / 1_000 };
    }
    if (value >= 1_000_000_000) return { multiplier: 1_000_000_000, displayValue: value / 1_000_000_000 };
    if (value >= 1_000_000) return { multiplier: 1_000_000, displayValue: value / 1_000_000 };
    return { multiplier: 1_000, displayValue: value / 1_000 };
}

/**
 * Backfill `multiplier`/`displayValue` (or `displayMin`/`displayMax`) on a
 * filter that was persisted/loaded without UI metadata. No-op for fields
 * that aren't of `units` type or filters that already carry the metadata.
 */
function hydrateUnitsFilter<T extends { field: string; operator: string; value: unknown; multiplier?: number; displayValue?: number; displayMin?: number; displayMax?: number }>(filter: T): T {
    const fieldInfo = AVAILABLE_FIELDS.find(f => f.value === filter.field);
    if (!fieldInfo || (fieldInfo as any).type !== 'units') return filter;

    if (filter.operator === 'between' && Array.isArray(filter.value) && filter.value.length === 2) {
        const [min, max] = filter.value as number[];
        if (filter.multiplier && filter.displayMin !== undefined && filter.displayMax !== undefined) {
            return filter;
        }
        // Use the same multiplier for both ends, derived from the larger end
        const reference = Math.max(Math.abs(min || 0), Math.abs(max || 0)) || DEFAULT_UNIT_MULTIPLIER;
        const { multiplier } = inferDisplayUnit(reference);
        return {
            ...filter,
            multiplier,
            displayMin: multiplier ? min / multiplier : min,
            displayMax: multiplier ? max / multiplier : max,
        };
    }

    if (typeof filter.value === 'number') {
        if (filter.multiplier && filter.displayValue !== undefined) return filter;
        const { multiplier, displayValue } = inferDisplayUnit(filter.value);
        return { ...filter, multiplier, displayValue };
    }

    return filter;
}

function hydrateAllUnitsFilters<T extends FilterCondition>(filters: T[]): T[] {
    return filters.map(f => hydrateUnitsFilter(f));
}

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
    block = false,
}: {
    value: string;
    onChange: (value: string) => void;
    options: typeof AVAILABLE_FIELDS;
    categories?: string[];
    exclude?: string;
    variant?: 'default' | 'field-compare';
    fontFamily: string;
    minWidth?: number;
    /** Ocupa todo el ancho disponible (panel lateral) en vez de minWidth/maxWidth. */
    block?: boolean;
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

    // El modo fx se distingue por la cursiva del propio valor, no por color.
    const triggerClass = variant === 'field-compare'
        ? 'bg-transparent text-foreground italic border-border hover:border-muted-fg'
        : 'bg-transparent text-foreground border-border hover:border-muted-fg';

    return (
        <div ref={containerRef} className={`relative ${block ? 'w-full' : ''}`} style={{ fontFamily }}>
            <button
                onClick={() => setOpen(!open)}
                className={`flex items-center gap-1 px-1.5 py-[2px] rounded-sm border truncate ${block ? 'w-full justify-between' : ''} ${triggerClass}`}
                style={block ? { fontSize: '11px' } : { fontSize: '11px', minWidth, maxWidth: 160 }}
            >
                <span className="truncate">{currentOption?.label || value}</span>
                <ChevronDown className={`w-3 h-3 shrink-0 text-muted-fg transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>

            {open && (
                <div
                    className="absolute top-full left-0 mt-0.5 bg-surface border border-border rounded-sm shadow-lg z-50 overflow-hidden"
                    style={{ minWidth: Math.max(minWidth, 180), maxHeight: 280, fontFamily }}
                >
                    <div className="px-1.5 py-1 border-b border-border-subtle">
                        <input
                            ref={searchRef}
                            type="text"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder="Search..."
                            className="w-full px-1.5 py-0.5 rounded-sm bg-surface-hover border border-border text-foreground outline-none focus:border-muted-fg"
                            style={{ fontSize: '11px', fontFamily }}
                        />
                    </div>
                    <div className="overflow-y-auto" style={{ maxHeight: 240 }}>
                        {search ? (
                            filtered.length === 0 ? (
                                <div className="px-2 py-2 text-muted-fg" style={{ fontSize: '11px' }}>No results</div>
                            ) : (
                                filtered.map(o => (
                                    <button
                                        key={o.value}
                                        onClick={() => { onChange(o.value); setOpen(false); }}
                                        className={`w-full text-left px-2 py-1 hover:bg-surface-hover transition-colors ${
                                            o.value === value ? 'bg-foreground text-[var(--color-bg)]' : 'text-foreground'
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
                                        <div className="px-2 py-0.5 text-muted-fg font-medium uppercase tracking-wider bg-surface-hover border-b border-border-subtle" style={{ fontSize: '10px', fontFamily }}>
                                            {cat}
                                        </div>
                                        {catOptions.map(o => (
                                            <button
                                                key={o.value}
                                                onClick={() => { onChange(o.value); setOpen(false); }}
                                                className={`w-full text-left px-2 py-1 hover:bg-surface-hover transition-colors ${
                                                    o.value === value ? 'bg-foreground text-[var(--color-bg)]' : 'text-foreground'
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
                className="flex items-center gap-0.5 px-1.5 py-[2px] rounded-sm bg-transparent text-foreground hover:border-muted-fg transition-colors border border-border"
                style={{ fontSize: '11px', minWidth: 40 }}
            >
                {current?.label || value}
                <ChevronDown className={`w-2.5 h-2.5 text-muted-fg transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>

            {open && (
                <div
                    className="absolute top-full left-0 mt-0.5 bg-surface border border-border rounded-sm shadow-lg z-50 overflow-hidden"
                    style={{ minWidth: 100, fontFamily }}
                >
                    {options.map(op => (
                        <button
                            key={op.value}
                            onClick={() => { onChange(op.value); setOpen(false); }}
                            className={`w-full text-left px-2 py-1 hover:bg-surface-hover transition-colors ${
                                op.value === value ? 'bg-foreground text-[var(--color-bg)]' : 'text-foreground'
                            }`}
                            style={{ fontSize: '11px', fontFamily }}
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

    return (
        <div className="space-y-1.5">
            {/* ── Dynamic Filters (numeric / field-vs-field) ── */}
            {filters.filter(f => !isSignalFilter(f.field)).map((filter) => {
                const realIndex = filters.indexOf(filter);
                const fieldInfo = getFieldInfo(filter.field);
                const hasParams = isParametric(fieldInfo);
                const currentPeriod = filter.params?.period ?? fieldInfo?.defaultPeriod ?? 14;
                const isFieldMode = filter.compareMode === 'field';
                const operators = isFieldMode ? FIELD_OPERATORS : VALUE_OPERATORS;

                return (
                    <div key={realIndex} className="group/f rounded-sm border border-border-subtle hover:border-border px-1.5 py-1">
                        {/* ── Fila 1: campo + periodo + quitar ── */}
                        <div className="flex items-center gap-1 mb-1">
                            <div className="flex-1 min-w-0">
                                <FieldSelect
                                    value={filter.field}
                                    onChange={(val) => updateFilter(realIndex, { field: val, params: undefined })}
                                    options={AVAILABLE_FIELDS}
                                    fontFamily={fontFamily}
                                    block
                                />
                            </div>

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
                                    className="w-[32px] shrink-0 px-1 py-[2px] rounded-sm bg-transparent text-foreground border border-border text-center"
                                    style={{ fontSize: '11px', fontFamily }}
                                    title="Period (2-200)"
                                />
                            )}

                            <button
                                onClick={() => removeFilter(realIndex)}
                                className="shrink-0 p-0.5 text-muted-fg opacity-0 group-hover/f:opacity-100 hover:text-[var(--color-chart-down)] transition-opacity"
                                title="Remove filter"
                            >
                                <X className="w-3 h-3" />
                            </button>
                        </div>

                        {/* ── Fila 2: operador + modo + valor ── */}
                        <div className="flex items-center gap-1 flex-wrap">
                        {/* ── Operator ── */}
                        <OperatorSelect
                            value={filter.operator}
                            onChange={(val) => updateFilter(realIndex, { operator: val })}
                            options={operators}
                            fontFamily={fontFamily}
                        />

                        {/* ── Mode toggle: Value vs Field ── */}
                        <div className="flex rounded-sm overflow-hidden border border-border shrink-0">
                            <button
                                onClick={() => updateFilter(realIndex, { compareMode: 'value' })}
                                className={`px-1.5 py-[2px] transition-colors ${
                                    !isFieldMode
                                        ? 'bg-foreground text-[var(--color-bg)]'
                                        : 'text-muted-fg hover:text-foreground'
                                }`}
                                style={{ fontSize: '11px', fontFamily }}
                                title="Compare to numeric value"
                            >
                                123
                            </button>
                            <button
                                onClick={() => updateFilter(realIndex, { compareMode: 'field' })}
                                className={`px-1.5 py-[2px] transition-colors border-l border-border ${
                                    isFieldMode
                                        ? 'bg-foreground text-[var(--color-bg)]'
                                        : 'text-muted-fg hover:text-foreground'
                                }`}
                                style={{ fontSize: '11px', fontStyle: 'italic', fontFamily }}
                                title="Compare to another indicator"
                            >
                                fx
                            </button>
                        </div>

                        {/* ── Right Side: Value or Field selector ── */}
                        {isFieldMode ? (
                            <div className="flex-1 min-w-[110px]">
                                <FieldSelect
                                    value={typeof filter.value === 'string' ? filter.value : 'sma_50'}
                                    onChange={(val) => updateFilter(realIndex, { value: val })}
                                    options={AVAILABLE_FIELDS}
                                    exclude={filter.field}
                                    variant="field-compare"
                                    fontFamily={fontFamily}
                                    block
                                />
                            </div>
                        ) : filter.operator === 'between' && fieldInfo?.type === 'units' ? (
                            (() => {
                                // Backfill multiplier/displayMin/displayMax from the absolute
                                // value if the persisted filter is missing UI metadata
                                const hydrated = hydrateUnitsFilter(filter as any);
                                const currentMult = (hydrated as any).multiplier ?? DEFAULT_UNIT_MULTIPLIER;
                                const currentMin = (hydrated as any).displayMin ?? 0;
                                const currentMax = (hydrated as any).displayMax ?? 100;
                                return (
                                    <div className="flex items-center gap-1">
                                        <input
                                            type="number"
                                            value={currentMin}
                                            onChange={(e) => {
                                                const num = parseFloat(e.target.value) || 0;
                                                updateFilter(realIndex, {
                                                    value: [num * currentMult, currentMax * currentMult],
                                                    displayMin: num,
                                                    displayMax: currentMax,
                                                    multiplier: currentMult
                                                } as any);
                                            }}
                                            className="w-[44px] px-1 py-[2px] rounded-sm border border-border bg-surface text-foreground"
                                            style={{ fontSize: '11px', fontFamily }}
                                        />
                                        <span className="text-foreground" style={{ fontSize: '11px', fontFamily }}>to</span>
                                        <input
                                            type="number"
                                            value={currentMax}
                                            onChange={(e) => {
                                                const num = parseFloat(e.target.value) || 0;
                                                updateFilter(realIndex, {
                                                    value: [currentMin * currentMult, num * currentMult],
                                                    displayMin: currentMin,
                                                    displayMax: num,
                                                    multiplier: currentMult
                                                } as any);
                                            }}
                                            className="w-[44px] px-1 py-[2px] rounded-sm border border-border bg-surface text-foreground"
                                            style={{ fontSize: '11px', fontFamily }}
                                        />
                                        <select
                                            value={currentMult}
                                            onChange={(e) => {
                                                const mult = parseInt(e.target.value);
                                                updateFilter(realIndex, {
                                                    value: [currentMin * mult, currentMax * mult],
                                                    displayMin: currentMin,
                                                    displayMax: currentMax,
                                                    multiplier: mult
                                                } as any);
                                            }}
                                            className="px-1 py-[2px] rounded-sm border border-border bg-surface-hover text-foreground"
                                            style={{ fontSize: '11px', fontFamily }}
                                        >
                                            <option value={1000}>K</option>
                                            <option value={1000000}>M</option>
                                            <option value={1000000000}>B</option>
                                        </select>
                                    </div>
                                );
                            })()
                        ) : filter.operator === 'between' ? (
                            <div className="flex items-center gap-1">
                                <NumberInput
                                    value={Array.isArray(filter.value) ? filter.value[0] : 0}
                                    onChange={(val) => updateFilter(realIndex, {
                                        value: [val, Array.isArray(filter.value) ? filter.value[1] : 0]
                                    })}
                                    className="w-[52px] px-1.5 py-[2px] rounded-sm border border-border bg-surface text-foreground"
                                    style={{ fontSize: '11px' }}
                                />
                                <span className="text-foreground" style={{ fontSize: '11px', fontFamily }}>to</span>
                                <NumberInput
                                    value={Array.isArray(filter.value) ? filter.value[1] : 0}
                                    onChange={(val) => updateFilter(realIndex, {
                                        value: [Array.isArray(filter.value) ? filter.value[0] : 0, val]
                                    })}
                                    className="w-[52px] px-1.5 py-[2px] rounded-sm border border-border bg-surface text-foreground"
                                    style={{ fontSize: '11px', fontFamily }}
                                />
                                {fieldInfo?.unit && (
                                    <span className="text-foreground" style={{ fontSize: '11px', fontFamily }}>{fieldInfo.unit}</span>
                                )}
                            </div>
                        ) : fieldInfo?.type === 'units' ? (
                            (() => {
                                // Backfill multiplier/displayValue from the absolute value
                                // if the persisted filter is missing UI metadata
                                const hydrated = hydrateUnitsFilter(filter as any);
                                const currentMult = (hydrated as any).multiplier ?? DEFAULT_UNIT_MULTIPLIER;
                                const currentDisplay = (hydrated as any).displayValue ?? (typeof filter.value === 'number' ? filter.value : 0);
                                return (
                                    <div className="flex items-center gap-0.5">
                                        <input
                                            type="number"
                                            value={currentDisplay}
                                            onChange={(e) => {
                                                const num = parseFloat(e.target.value) || 0;
                                                updateFilter(realIndex, { value: num * currentMult, displayValue: num, multiplier: currentMult } as any);
                                            }}
                                            className="w-[48px] px-1.5 py-[2px] rounded-l-sm border border-border bg-surface text-foreground"
                                            style={{ fontSize: '11px', fontFamily }}
                                        />
                                        <select
                                            value={currentMult}
                                            onChange={(e) => {
                                                const mult = parseInt(e.target.value);
                                                updateFilter(realIndex, { value: currentDisplay * mult, displayValue: currentDisplay, multiplier: mult } as any);
                                            }}
                                            className="px-1 py-0.5 rounded-r-sm border border-l-0 border-border bg-surface-hover text-foreground"
                                            style={{ fontSize: '11px', fontFamily }}
                                        >
                                            <option value={1000}>K</option>
                                            <option value={1000000}>M</option>
                                            <option value={1000000000}>B</option>
                                        </select>
                                    </div>
                                );
                            })()
                        ) : (
                            <div className="flex items-center gap-1">
                                <NumberInput
                                    value={typeof filter.value === 'number' ? filter.value : 0}
                                    onChange={(val) => updateFilter(realIndex, { value: val })}
                                    className="w-[56px] px-1.5 py-[2px] rounded-sm border border-border bg-surface text-foreground"
                                    style={{ fontSize: '11px', fontFamily }}
                                />
                                {fieldInfo?.unit && (
                                    <span className="text-foreground" style={{ fontSize: '11px', fontFamily }}>{fieldInfo.unit}</span>
                                )}
                            </div>
                        )}

                        </div>
                    </div>
                );
            })}

            <button
                onClick={addFilter}
                className="w-full flex items-center gap-1 px-1.5 py-1 text-muted-fg hover:text-foreground hover:border-muted-fg rounded-sm border border-dashed border-border transition-colors"
                style={{ fontSize: '11px', fontFamily }}
            >
                <Plus className="w-3 h-3" />
                Add filter
            </button>
        </div>
    );
}

// ============================================================================
// Etiqueta de seccion del panel lateral
// ============================================================================

function SectionLabel({ children, fontFamily }: { children: React.ReactNode; fontFamily: string }) {
    return (
        <div
            className="text-muted-fg uppercase tracking-wide mb-1"
            style={{ fontSize: '10px', fontFamily }}
        >
            {children}
        </div>
    );
}

// ============================================================================
// Signal Chips — condiciones booleanas, en su propia seccion del panel
// ============================================================================

function SignalChips({
    filters,
    onFiltersChange,
    fontFamily,
}: {
    filters: FilterCondition[];
    onFiltersChange: (filters: FilterCondition[]) => void;
    fontFamily: string;
}) {
    const activeSignals = filters
        .filter(f => SIGNAL_FIELDS.some(s => s.value === f.field))
        .map(f => f.field);

    const toggle = (field: string) => {
        const idx = filters.findIndex(f => f.field === field);
        if (idx >= 0) {
            onFiltersChange(filters.filter((_, i) => i !== idx));
        } else {
            onFiltersChange([...filters, { field, operator: 'eq', value: true, compareMode: 'value' }]);
        }
    };

    return (
        <div className="flex flex-wrap gap-1">
            {SIGNAL_FIELDS.map((signal) => {
                const isActive = activeSignals.includes(signal.value);
                return (
                    <button
                        key={signal.value}
                        onClick={() => toggle(signal.value)}
                        // Activo = inversion (fondo fg, texto bg). Sin color de marca.
                        className={`px-1.5 py-[2px] rounded-sm border transition-colors ${
                            isActive
                                ? 'bg-foreground text-[var(--color-bg)] border-foreground'
                                : 'text-muted-fg border-border hover:text-foreground hover:border-muted-fg'
                        }`}
                        style={{ fontSize: '10px', fontFamily }}
                        title={signal.label}
                    >
                        {signal.label}
                    </button>
                );
            })}
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

// ── Paleta ──────────────────────────────────────────────────────────────────
// Solo dos acentos en toda la ventana: subida y bajada. Todo lo demas es
// neutro (fg / muted-fg / borders). El estado activo se marca invirtiendo
// fondo y texto, no con un color de marca.
const UP = 'text-[var(--color-chart-up)]';
const DOWN = 'text-[var(--color-chart-down)]';

const getChangeColor = (value: number | null) => {
    if (value === null) return 'text-muted-fg';
    return value >= 0 ? UP : DOWN;
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

// ── Densidad de la rejilla ──────────────────────────────────────────────────
// Fila de 20px con texto de 11px. El virtualizador asume este alto exacto.
const ROW_HEIGHT = 20;
const GRID_FONT = '11px';

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
                    className="font-medium text-foreground hover:underline underline-offset-2 cursor-pointer"
                >
                    {symbol}
                </button>
            );
        },
    }),
    screenerColumnHelper.accessor('sector', {
        header: 'Sector',
        size: 90,
        cell: (info) => <span className="text-foreground truncate">{info.getValue() || '-'}</span>,
    }),

    // ── Price ──
    screenerColumnHelper.accessor('price', {
        header: 'Price',
        size: 75,
        cell: (info) => <span className="text-foreground">{formatPrice(info.getValue())}</span>,
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
        cell: (info) => <span className="text-foreground">{formatVolume(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('relative_volume', {
        header: 'RVol',
        size: 65,
        cell: (info) => <span className="text-foreground">{formatMultiplier(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('avg_volume_20', {
        header: 'AvgVol 20',
        size: 80,
        cell: (info) => <span className="text-foreground">{formatVolume(info.getValue())}</span>,
    }),

    // ── Fundamentals ──
    screenerColumnHelper.accessor('market_cap', {
        header: 'MCap',
        size: 80,
        cell: (info) => <span className="text-foreground">{formatVolume(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('free_float', {
        id: 'free_float',
        header: 'Float',
        size: 80,
        cell: (info) => <span className="text-foreground">{formatVolume(info.getValue())}</span>,
    }),

    // ── 52 Week ──
    screenerColumnHelper.accessor('from_52w_high', {
        header: 'Fr. 52H',
        size: 70,
        cell: (info) => {
            const v = info.getValue();
            const near = v !== null && v > -5;
            // Cerca del maximo se marca con peso, no con color: el color queda
            // reservado a los valores con signo.
            return <span className={near ? 'text-foreground font-medium' : 'text-muted-fg'}>{formatPercent(v)}</span>;
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
        cell: (info) => <span className="text-foreground">{formatPrice(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('low_52w', {
        header: '52W Low',
        size: 75,
        cell: (info) => <span className="text-foreground">{formatPrice(info.getValue())}</span>,
    }),

    // ── Momentum ──
    screenerColumnHelper.accessor('rsi_14', {
        header: 'RSI',
        size: 55,
        cell: (info) => {
            const v = info.getValue();
            if (v === null) return <span className="text-muted-fg">-</span>;
            // Extremos (<30 / >70) destacan por peso. RSI no es direccion de
            // precio, asi que no toma los acentos de subida/bajada.
            const extreme = v < 30 || v > 70;
            return <span className={extreme ? 'text-foreground font-medium' : 'text-muted-fg'}>{v.toFixed(0)}</span>;
        },
    }),

    // ── Trend / SMAs ──
    screenerColumnHelper.accessor('sma_20', {
        header: 'SMA 20',
        size: 75,
        cell: (info) => <span className="text-foreground">{formatPrice(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('sma_50', {
        header: 'SMA 50',
        size: 75,
        cell: (info) => <span className="text-foreground">{formatPrice(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('sma_200', {
        header: 'SMA 200',
        size: 75,
        cell: (info) => <span className="text-foreground">{formatPrice(info.getValue())}</span>,
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
        cell: (info) => <span className="text-foreground">{formatPrice(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('atr_percent', {
        header: 'ATR%',
        size: 65,
        cell: (info) => <span className="text-foreground">{formatPercent(info.getValue())}</span>,
    }),

    // ── Bollinger Bands ──
    screenerColumnHelper.accessor('bb_upper', {
        header: 'BB Up',
        size: 70,
        cell: (info) => <span className="text-foreground">{formatPrice(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('bb_lower', {
        header: 'BB Low',
        size: 70,
        cell: (info) => <span className="text-foreground">{formatPrice(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('bb_width', {
        header: 'BB W%',
        size: 65,
        cell: (info) => {
            const v = info.getValue();
            return <span className="text-foreground">{v !== null ? `${v.toFixed(1)}%` : '-'}</span>;
        },
    }),
    screenerColumnHelper.accessor('bb_position', {
        header: 'BB Pos%',
        size: 65,
        cell: (info) => <span className="text-foreground">{formatPercent(info.getValue())}</span>,
    }),

    // ── Keltner Channels ──
    screenerColumnHelper.accessor('keltner_upper', {
        header: 'KC Up',
        size: 70,
        cell: (info) => <span className="text-foreground">{formatPrice(info.getValue())}</span>,
    }),
    screenerColumnHelper.accessor('keltner_lower', {
        header: 'KC Low',
        size: 70,
        cell: (info) => <span className="text-foreground">{formatPrice(info.getValue())}</span>,
    }),

    // ── TTM Squeeze ──
    screenerColumnHelper.accessor('squeeze_on', {
        header: 'Squeeze',
        size: 65,
        cell: (info) => {
            const v = info.getValue();
            if (v === null) return <span className="text-muted-fg">-</span>;
            // Chip invertido en vez de un tercer color.
            return v === 1
                ? <span className="px-1 rounded-sm bg-foreground text-[var(--color-bg)] font-medium">ON</span>
                : <span className="text-muted-fg">OFF</span>;
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
            if (v === null) return <span className="text-muted-fg">-</span>;
            const strong = v > 25;
            return <span className={strong ? 'text-foreground font-medium' : 'text-foreground/80'}>{v.toFixed(0)}</span>;
        },
    }),
    screenerColumnHelper.accessor('plus_di_14', {
        header: '+DI',
        size: 55,
        cell: (info) => <span className={UP}>{formatNumber(info.getValue(), 0)}</span>,
    }),
    screenerColumnHelper.accessor('minus_di_14', {
        header: '-DI',
        size: 55,
        cell: (info) => <span className={DOWN}>{formatNumber(info.getValue(), 0)}</span>,
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
        // 11px + py-[3px] + 1px de separacion => 20px por fila. Debe coincidir
        // con el alto real del <tr> o el scroll se desalinea.
        estimateSize: () => ROW_HEIGHT,
        overscan: 12,
    });

    const virtualRows = rowVirtualizer.getVirtualItems();
    const totalSize = rowVirtualizer.getTotalSize();
    const paddingTop = virtualRows.length > 0 ? virtualRows[0].start : 0;
    const paddingBottom = virtualRows.length > 0
        ? totalSize - virtualRows[virtualRows.length - 1].end
        : 0;

    return (
        <div className="flex-1 flex flex-col overflow-hidden min-w-0">
            {/* Table Settings */}
            <div className="flex-shrink-0 flex justify-end px-2 py-0.5 border-b border-border-subtle">
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
                <table className="w-full text-left tabular-nums" style={{ fontSize: GRID_FONT, fontFamily }}>
                    {/* Fondo opaco obligatorio: con sticky translucido las filas
                        se transparentan por debajo de la cabecera al hacer scroll. */}
                    <thead className="sticky top-0 bg-[var(--color-table-header)] border-b border-border z-10">
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
                                            // Cabecera mas alta que la fila (28 vs 20) para que
                                            // lea como chrome y no como el primer registro.
                                            className={`px-2 py-[7px] text-muted-fg uppercase tracking-wide cursor-grab select-none border-r border-border-subtle last:border-r-0 hover:text-foreground ${isFirstColumn ? 'text-left' : 'text-right'}`}
                                            style={{ width: header.getSize(), fontSize: '10px' }}
                                            onClick={header.column.getToggleSortingHandler()}
                                        >
                                            <div className={`flex items-center gap-1 ${isFirstColumn ? 'justify-start' : 'justify-end'}`}>
                                                {flexRender(header.column.columnDef.header, header.getContext())}
                                                {{
                                                    asc: <span className="text-foreground">↑</span>,
                                                    desc: <span className="text-foreground">↓</span>,
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
                                // Sin regla horizontal: el zebra ya separa filas.
                                // La tinta se gasta en separar columnas.
                                <tr
                                    key={row.id}
                                    className={`hover:bg-surface-hover ${i % 2 === 0 ? 'bg-surface' : 'bg-[var(--color-table-stripe)]'}`}
                                    style={{ height: ROW_HEIGHT }}
                                >
                                    {row.getVisibleCells().map((cell, cellIndex) => {
                                        const isFirstColumn = cellIndex === 0;
                                        return (
                                            <td
                                                key={cell.id}
                                                // leading fijo: con line-height "normal" el alto real
                                                // depende de la fuente elegida por el usuario y el
                                                // virtualizador (que asume ROW_HEIGHT) se desalinea.
                                                className={`px-2 py-[3px] leading-[14px] border-r border-border-subtle last:border-r-0 truncate ${isFirstColumn ? 'text-left' : 'text-right'}`}
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
    const { userId: clerkUserId } = useAuth();

    // Default filters
    const defaultFilters: FilterCondition[] = hydrateAllUnitsFilters([
        { field: 'price', operator: 'between', value: [5, 500] },
        { field: 'volume', operator: 'gt', value: 500000 },
    ]);

    // State - use persisted values if available
    const [filters, setFilters] = useState<FilterCondition[]>(
        windowState.filters ? hydrateAllUnitsFilters(windowState.filters) : defaultFilters
    );
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
    const { openWindow } = useFloatingWindowActions();
    const { publish: publishTicker, hasSubscribers, linkGroup } = useLinkGroupPublisher();

    const handleSymbolClick = useCallback((symbol: string) => {
        if (linkGroup) {
            const hadSubs = hasSubscribers();
            publishTicker(symbol);
            if (!hadSubs) openLinkedTVChart(openWindow, symbol, linkGroup);
            return;
        }
        executeTickerCommand(symbol, 'tvchart');
    }, [linkGroup, hasSubscribers, publishTicker, openWindow, executeTickerCommand]);

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
                setFilters(hydrateAllUnitsFilters(windowState.filters as FilterCondition[]));
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

            const headers: Record<string, string> = { 'Content-Type': 'application/json' };
            // Diagnostics-only: lets us trace requests back to a user when
            // investigating bug reports. Endpoint is unauthenticated.
            if (clerkUserId) headers['X-User-Id'] = clerkUserId;

            const res = await fetch(`${API_BASE}/screen`, {
                method: 'POST',
                headers,
                body: JSON.stringify(body),
            });

            const data: ScreenerResponse = await res.json().catch(() => ({} as any));

            // Backend returns 400 with { detail: { message, errors } } for
            // invalid filters (e.g. unit-scaling mistakes). Surface the actual
            // reason instead of swallowing it as "0 results".
            if (!res.ok) {
                const detail = (data as any)?.detail;
                const msg = typeof detail === 'string'
                    ? detail
                    : detail?.errors?.join('; ') || detail?.message || `HTTP ${res.status}`;
                throw new Error(msg);
            }

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
    }, [filters, symbols, sortBy, sortOrder, limit, clerkUserId]);

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

    // Reset back to the window's opening state
    const handleReset = () => {
        setFilters(hydrateAllUnitsFilters([
            { field: 'price', operator: 'between', value: [5, 500] },
            { field: 'volume', operator: 'gt', value: 500000 },
        ]));
        setSymbols([]);
        setActivePreset(null);
        setActiveUserTemplate(null);
    };

    // Apply preset - loads filters as editable template
    const applyPreset = (preset: Preset) => {
        const clonedFilters = preset.filters.map(f => ({
            ...f,
            value: Array.isArray(f.value) ? [...f.value] : f.value,
            compareMode: 'value' as const,
        }));
        setFilters(hydrateAllUnitsFilters(clonedFilters));
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

        const templateFilters: TemplateFilterCondition[] = filters.map(f => {
            // Persist UI-only metadata for units-type fields so the next load
            // can restore the K/M/B selector without inferring from the raw value.
            const extra: Record<string, unknown> = {};
            if (typeof (f as any).multiplier === 'number') extra.multiplier = (f as any).multiplier;
            if (typeof (f as any).displayValue === 'number') extra.displayValue = (f as any).displayValue;
            if (typeof (f as any).displayMin === 'number') extra.displayMin = (f as any).displayMin;
            if (typeof (f as any).displayMax === 'number') extra.displayMax = (f as any).displayMax;

            return {
                field: f.field,
                operator: f.operator,
                value: f.compareMode === 'field' ? undefined : (typeof f.value === 'string' ? undefined : f.value),
                compare_field: f.compareMode === 'field' && typeof f.value === 'string' ? f.value : undefined,
                params: f.params ?? undefined,
                ...extra,
            } as TemplateFilterCondition;
        });

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
        const loadedFilters: FilterCondition[] = template.filters.map(f => {
            // Persisted filters may carry display metadata (multiplier/displayValue)
            // for units-type fields; preserve it if present, otherwise infer.
            const raw = f as unknown as Record<string, unknown>;
            return {
                field: f.field,
                operator: f.operator,
                value: f.compare_field ? f.compare_field : (f.value as number | number[] | boolean),
                compareMode: f.compare_field ? 'field' as const : 'value' as const,
                params: f.params ?? undefined,
                ...(typeof raw.multiplier === 'number' ? { multiplier: raw.multiplier } : {}),
                ...(typeof raw.displayValue === 'number' ? { displayValue: raw.displayValue } : {}),
                ...(typeof raw.displayMin === 'number' ? { displayMin: raw.displayMin as number } : {}),
                ...(typeof raw.displayMax === 'number' ? { displayMax: raw.displayMax as number } : {}),
            };
        });

        setFilters(hydrateAllUnitsFilters(loadedFilters));
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
        <div className="h-full flex flex-col bg-surface text-foreground" style={{ fontFamily }}>
            {/* Save Template Modal */}
            {showSaveModal && (
                <div className="fixed inset-0 bg-[var(--color-overlay)] flex items-center justify-center z-50" onClick={() => setShowSaveModal(false)}>
                    <div
                        className="bg-surface border border-border rounded-sm shadow-xl p-3 w-72"
                        onClick={e => e.stopPropagation()}
                        style={{ fontFamily }}
                    >
                        <div className="text-muted-fg uppercase tracking-wide mb-2" style={{ fontSize: '10px' }}>Save screen</div>
                        <input
                            type="text"
                            value={templateName}
                            onChange={(e) => setTemplateName(e.target.value)}
                            placeholder="Screen name..."
                            className="w-full px-2 py-1 bg-surface-hover border border-border rounded-sm text-foreground outline-none focus:border-muted-fg"
                            style={{ fontSize: '11px', fontFamily }}
                            autoFocus
                            onKeyDown={(e) => e.key === 'Enter' && handleSaveTemplate()}
                        />
                        <div className="flex justify-end gap-1.5 mt-2.5">
                            <button
                                onClick={() => setShowSaveModal(false)}
                                className="px-2 py-1 rounded-sm border border-border text-muted-fg hover:text-foreground"
                                style={{ fontSize: '11px', fontFamily }}
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleSaveTemplate}
                                disabled={!templateName.trim()}
                                className="px-2 py-1 rounded-sm bg-foreground text-[var(--color-bg)] disabled:opacity-40"
                                style={{ fontSize: '11px', fontFamily }}
                            >
                                Save
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Cuerpo: panel de configuracion a la izquierda, resultados a la derecha ── */}
            <div className="flex-1 flex min-h-0">

                {showFilters ? (
                    <aside className="w-[250px] shrink-0 flex flex-col min-h-0 border-r border-border">
                        {/* Cabecera del panel */}
                        <div className="shrink-0 flex items-center justify-between px-2 py-1 border-b border-border-subtle">
                            <span className="text-muted-fg uppercase tracking-wide" style={{ fontSize: '10px', fontFamily }}>
                                Filters:
                            </span>
                            <button
                                onClick={() => setShowFilters(false)}
                                className="flex items-center gap-0.5 text-muted-fg hover:text-foreground transition-colors"
                                style={{ fontSize: '10px', fontFamily }}
                                title="Hide panel"
                            >
                                <ChevronLeft className="w-3 h-3" />
                                Hide
                            </button>
                        </div>

                        {/* Contenido desplazable */}
                        <div className="flex-1 overflow-y-auto min-h-0 px-2 py-2 space-y-3">

                            {/* ── Universo ── */}
                            <section>
                                <SectionLabel fontFamily={fontFamily}>Universe</SectionLabel>
                                <TickerSearch
                                    value={symbolInput}
                                    onChange={setSymbolInput}
                                    onSelect={handleAddSymbol}
                                    placeholder="Limit to symbols..."
                                    className="w-full"
                                />
                                {symbols.length > 0 && (
                                    <div className="flex flex-wrap items-center gap-1 mt-1">
                                        {symbols.map((s) => (
                                            <span
                                                key={s}
                                                className="inline-flex items-center gap-1 px-1.5 py-[2px] rounded-sm border border-border text-foreground"
                                                style={{ fontSize: '10px', fontFamily }}
                                            >
                                                {s}
                                                <button
                                                    onClick={() => handleRemoveSymbol(s)}
                                                    className="text-muted-fg hover:text-[var(--color-chart-down)]"
                                                >
                                                    <X className="w-2.5 h-2.5" />
                                                </button>
                                            </span>
                                        ))}
                                    </div>
                                )}
                            </section>

                            {/* ── Screens guardadas ── */}
                            <section>
                                <SectionLabel fontFamily={fontFamily}>Screens</SectionLabel>

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
                                        className={`w-full px-1.5 py-[2px] pr-6 rounded-sm border bg-surface cursor-pointer appearance-none truncate ${
                                            activePreset && !activeUserTemplate
                                                ? 'border-muted-fg text-foreground'
                                                : 'border-border text-muted-fg'
                                        }`}
                                        style={{ fontSize: '11px', fontFamily }}
                                    >
                                        <option value="">Presets...</option>
                                        {PRESETS.map((preset) => (
                                            <option key={preset.id} value={preset.id}>{preset.name}</option>
                                        ))}
                                    </select>
                                    <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-fg pointer-events-none" />
                                </div>

                                {/* Screens del usuario — una por linea */}
                                {userTemplates.length > 0 && (
                                    <div className="mt-1 space-y-0.5">
                                        {userTemplates.map((template) => {
                                            const isActive = activeUserTemplate === template.id;
                                            return (
                                                <div key={template.id} className="group/t flex items-stretch">
                                                    <button
                                                        onClick={() => applyUserTemplate(template)}
                                                        className={`flex-1 min-w-0 flex items-center gap-1 px-1.5 py-[2px] rounded-l-sm border text-left truncate transition-colors ${
                                                            isActive
                                                                ? 'bg-foreground text-[var(--color-bg)] border-foreground'
                                                                : 'text-foreground border-border hover:border-muted-fg'
                                                        }`}
                                                        style={{ fontSize: '11px', fontFamily }}
                                                        title={`${template.name} — used ${template.useCount}x`}
                                                    >
                                                        {template.isFavorite && (
                                                            <Star className={`w-2.5 h-2.5 shrink-0 ${isActive ? 'fill-current' : 'fill-foreground text-foreground'}`} />
                                                        )}
                                                        <span className="truncate">{template.name}</span>
                                                    </button>
                                                    <button
                                                        onClick={() => toggleFavorite(template.id)}
                                                        className="px-1 border-y border-border text-muted-fg hover:text-foreground opacity-0 group-hover/t:opacity-100 transition-opacity"
                                                        title={template.isFavorite ? 'Unfavorite' : 'Favorite'}
                                                    >
                                                        <Star className="w-2.5 h-2.5" />
                                                    </button>
                                                    <button
                                                        onClick={() => deleteTemplate(template.id)}
                                                        className="px-1 rounded-r-sm border border-l-0 border-border text-muted-fg hover:text-[var(--color-chart-down)] opacity-0 group-hover/t:opacity-100 transition-opacity"
                                                        title="Delete"
                                                    >
                                                        <X className="w-2.5 h-2.5" />
                                                    </button>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}

                                <button
                                    onClick={() => setShowSaveModal(true)}
                                    className="w-full mt-1 flex items-center justify-center gap-1 px-1.5 py-1 rounded-sm border border-dashed border-border text-muted-fg hover:text-foreground hover:border-muted-fg transition-colors"
                                    style={{ fontSize: '10px', fontFamily }}
                                    title="Save current configuration as a screen"
                                >
                                    <Save className="w-3 h-3" />
                                    Save current
                                </button>
                            </section>

                            {/* ── Senales ── */}
                            <section>
                                <SectionLabel fontFamily={fontFamily}>Signals</SectionLabel>
                                <SignalChips
                                    filters={filters}
                                    onFiltersChange={handleFiltersChange}
                                    fontFamily={fontFamily}
                                />
                            </section>

                            {/* ── Condiciones ── */}
                            <section>
                                <SectionLabel fontFamily={fontFamily}>Conditions</SectionLabel>
                                <FilterBuilder
                                    filters={filters}
                                    onFiltersChange={handleFiltersChange}
                                    fontFamily={fontFamily}
                                />
                            </section>
                        </div>

                        {/* Pie del panel: orden, limite y acciones */}
                        <div className="shrink-0 border-t border-border-subtle px-2 py-2 space-y-1.5">
                            <div className="flex items-center gap-1">
                                <span className="text-muted-fg shrink-0" style={{ fontSize: '10px', fontFamily }}>Sort</span>
                                <select
                                    value={sortBy}
                                    onChange={(e) => setSortBy(e.target.value)}
                                    className="flex-1 min-w-0 px-1 py-[2px] rounded-sm border border-border bg-surface text-foreground truncate"
                                    style={{ fontSize: '11px', fontFamily }}
                                >
                                    {SORT_OPTIONS.map((opt) => (
                                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                                    ))}
                                </select>
                                <button
                                    onClick={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
                                    className="shrink-0 px-1.5 py-[2px] rounded-sm border border-border text-foreground hover:border-muted-fg"
                                    style={{ fontSize: '11px', fontFamily }}
                                    title={sortOrder === 'desc' ? 'Descending' : 'Ascending'}
                                >
                                    {sortOrder === 'desc' ? '↓' : '↑'}
                                </button>
                            </div>

                            <div className="flex items-center gap-1">
                                <span className="text-muted-fg shrink-0" style={{ fontSize: '10px', fontFamily }}>Max</span>
                                <select
                                    value={limit}
                                    onChange={(e) => setLimit(parseInt(e.target.value))}
                                    className="flex-1 min-w-0 px-1 py-[2px] rounded-sm border border-border bg-surface text-foreground"
                                    style={{ fontSize: '11px', fontFamily }}
                                >
                                    <option value={25}>25 rows</option>
                                    <option value={50}>50 rows</option>
                                    <option value={100}>100 rows</option>
                                </select>
                                <button
                                    onClick={() => executeCommand('glossary')}
                                    className="shrink-0 px-1.5 py-[2px] rounded-sm border border-border text-muted-fg hover:text-foreground hover:border-muted-fg"
                                    title="Indicator glossary"
                                >
                                    <HelpCircle className="w-3 h-3" />
                                </button>
                            </div>

                            <div className="flex items-center gap-1 pt-0.5">
                                <button
                                    onClick={handleReset}
                                    className="px-2 py-1 rounded-sm border border-border text-muted-fg hover:text-foreground hover:border-muted-fg transition-colors"
                                    style={{ fontSize: '11px', fontFamily }}
                                >
                                    Reset
                                </button>
                                <button
                                    onClick={handleSearch}
                                    disabled={loading}
                                    className="flex-1 flex items-center justify-center gap-1 px-2 py-1 rounded-sm bg-foreground text-[var(--color-bg)] hover:opacity-80 disabled:opacity-40 transition-opacity"
                                    style={{ fontSize: '11px', fontFamily }}
                                >
                                    {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
                                    Scan
                                </button>
                            </div>
                        </div>
                    </aside>
                ) : (
                    <button
                        onClick={() => setShowFilters(true)}
                        className="w-5 shrink-0 flex items-start justify-center pt-1.5 border-r border-border text-muted-fg hover:text-foreground hover:bg-surface-hover transition-colors"
                        title="Show filters"
                    >
                        <ChevronRight className="w-3 h-3" />
                    </button>
                )}

                {/* ── Resultados ── */}
                <div className="flex-1 flex flex-col min-w-0">
                    {error && (
                        <div className="shrink-0 flex items-start gap-1.5 px-2 py-1 border-b border-border bg-surface-hover text-[var(--color-chart-down)]" style={{ fontSize: '11px', fontFamily }}>
                            <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-px" />
                            <span className="min-w-0 break-words">{error}</span>
                        </div>
                    )}

                    {results.length > 0 ? (
                        <ResultsTable
                            results={results}
                            onSymbolClick={handleSymbolClick}
                            fontFamily={fontFamily}
                        />
                    ) : (
                        <div className="flex-1 flex items-center justify-center text-muted-fg" style={{ fontSize: '11px', fontFamily }}>
                            {loading ? (
                                <div className="flex items-center gap-1.5">
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    Scanning...
                                </div>
                            ) : (
                                <div className="text-center">
                                    <Filter className="w-5 h-5 mx-auto mb-2 opacity-20" />
                                    <p>Pick a screen or build your conditions</p>
                                    <p className="mt-0.5 opacity-60">Then hit Scan</p>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Pie: recuento real y latencia */}
                    <div className="shrink-0 flex items-center justify-between px-2 py-1 border-t border-border-subtle text-muted-fg" style={{ fontSize: '10px', fontFamily }}>
                        {/* El "+" avisa de que el corte por limite oculta el total real. */}
                        <span>
                            {results.length > 0
                                ? `1–${results.length} of ${results.length}${results.length >= limit ? '+' : ''}`
                                : '—'}
                        </span>
                        <span className="flex items-center gap-2">
                            {queryTime !== null && (
                                <span>{queryTime < 1000 ? `${queryTime.toFixed(0)}ms` : `${(queryTime / 1000).toFixed(1)}s`}</span>
                            )}
                            <span>Daily Data</span>
                        </span>
                    </div>
                </div>
            </div>
        </div>
    );
}
