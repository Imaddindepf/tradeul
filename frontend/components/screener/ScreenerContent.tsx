'use client';

import { useState, useCallback, useEffect, useMemo } from 'react';
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
} from 'lucide-react';
import { TickerSearch } from '@/components/common/TickerSearch';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';

// ============================================================================
// Types
// ============================================================================

interface FilterCondition {
    field: string;
    operator: string;
    value: number | number[] | boolean;
}

interface ScreenerResult {
    symbol: string;
    date: string;
    price: number;
    volume: number;
    change_1d: number | null;
    change_5d: number | null;
    change_20d: number | null;
    gap_percent: number | null;
    high_52w: number | null;
    low_52w: number | null;
    from_52w_high: number | null;
    from_52w_low: number | null;
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
    bb_lower: number | null;
    bb_position: number | null;
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

const AVAILABLE_FIELDS = [
    { value: 'price', label: 'Price', type: 'number' },
    { value: 'change_1d', label: 'Change 1D %', type: 'percent' },
    { value: 'change_5d', label: 'Change 5D %', type: 'percent' },
    { value: 'change_20d', label: 'Change 20D %', type: 'percent' },
    { value: 'gap_percent', label: 'Gap %', type: 'percent' },
    { value: 'rsi_14', label: 'RSI (14)', type: 'number', min: 0, max: 100 },
    { value: 'relative_volume', label: 'Rel. Volume', type: 'number' },
    { value: 'volume', label: 'Volume', type: 'number' },
    { value: 'sma_20', label: 'SMA 20', type: 'number' },
    { value: 'sma_50', label: 'SMA 50', type: 'number' },
    { value: 'sma_200', label: 'SMA 200', type: 'number' },
    { value: 'dist_sma_20', label: 'Dist. SMA 20 %', type: 'percent' },
    { value: 'dist_sma_50', label: 'Dist. SMA 50 %', type: 'percent' },
    { value: 'from_52w_high', label: 'From 52W High %', type: 'percent' },
    { value: 'from_52w_low', label: 'From 52W Low %', type: 'percent' },
    { value: 'atr_percent', label: 'ATR %', type: 'percent' },
    { value: 'bb_position', label: 'BB Position %', type: 'percent' },
];

const OPERATORS = [
    { value: 'gt', label: '>' },
    { value: 'gte', label: '>=' },
    { value: 'lt', label: '<' },
    { value: 'lte', label: '<=' },
    { value: 'between', label: 'Between' },
];

const SORT_OPTIONS = [
    { value: 'relative_volume', label: 'Rel. Volume' },
    { value: 'change_1d', label: 'Change 1D' },
    { value: 'change_5d', label: 'Change 5D' },
    { value: 'rsi_14', label: 'RSI' },
    { value: 'price', label: 'Price' },
    { value: 'volume', label: 'Volume' },
    { value: 'from_52w_high', label: '52W High Dist.' },
];

// ============================================================================
// Filter Builder Component
// ============================================================================

function FilterBuilder({
    filters,
    onFiltersChange,
}: {
    filters: FilterCondition[];
    onFiltersChange: (filters: FilterCondition[]) => void;
}) {
    const addFilter = () => {
        onFiltersChange([
            ...filters,
            { field: 'rsi_14', operator: 'lt', value: 30 },
        ]);
    };

    const removeFilter = (index: number) => {
        onFiltersChange(filters.filter((_, i) => i !== index));
    };

    const updateFilter = (index: number, updates: Partial<FilterCondition>) => {
        const newFilters = [...filters];
        newFilters[index] = { ...newFilters[index], ...updates };
        
        if (updates.operator === 'between' && !Array.isArray(newFilters[index].value)) {
            newFilters[index].value = [0, 100];
        } else if (updates.operator && updates.operator !== 'between' && Array.isArray(newFilters[index].value)) {
            newFilters[index].value = 0;
        }
        
        onFiltersChange(newFilters);
    };

    return (
        <div className="flex flex-wrap gap-1.5 items-center">
            {filters.map((filter, index) => (
                <div key={index} className="flex items-center gap-0.5 bg-slate-50 rounded px-1 py-0.5">
                    <select
                        value={filter.field}
                        onChange={(e) => updateFilter(index, { field: e.target.value })}
                        className="px-1 py-0.5 rounded border-0 bg-transparent text-slate-700"
                        style={{ fontSize: '9px' }}
                    >
                        {AVAILABLE_FIELDS.map((f) => (
                            <option key={f.value} value={f.value}>{f.label}</option>
                        ))}
                    </select>
                    <select
                        value={filter.operator}
                        onChange={(e) => updateFilter(index, { operator: e.target.value })}
                        className="px-0.5 py-0.5 rounded border-0 bg-transparent text-slate-600 w-[40px]"
                        style={{ fontSize: '9px' }}
                    >
                        {OPERATORS.map((op) => (
                            <option key={op.value} value={op.value}>{op.label}</option>
                        ))}
                    </select>
                    {filter.operator === 'between' ? (
                        <>
                            <input
                                type="number"
                                value={Array.isArray(filter.value) ? filter.value[0] : 0}
                                onChange={(e) => updateFilter(index, { 
                                    value: [parseFloat(e.target.value) || 0, Array.isArray(filter.value) ? filter.value[1] : 100] 
                                })}
                                className="w-[40px] px-1 py-0.5 rounded border border-slate-200 bg-white text-slate-700"
                                style={{ fontSize: '9px' }}
                            />
                            <span className="text-slate-400" style={{ fontSize: '8px' }}>-</span>
                            <input
                                type="number"
                                value={Array.isArray(filter.value) ? filter.value[1] : 100}
                                onChange={(e) => updateFilter(index, { 
                                    value: [Array.isArray(filter.value) ? filter.value[0] : 0, parseFloat(e.target.value) || 100] 
                                })}
                                className="w-[40px] px-1 py-0.5 rounded border border-slate-200 bg-white text-slate-700"
                                style={{ fontSize: '9px' }}
                            />
                        </>
                    ) : (
                        <input
                            type="number"
                            value={typeof filter.value === 'number' ? filter.value : 0}
                            onChange={(e) => updateFilter(index, { value: parseFloat(e.target.value) || 0 })}
                            className="w-[50px] px-1 py-0.5 rounded border border-slate-200 bg-white text-slate-700"
                            style={{ fontSize: '9px' }}
                        />
                    )}
                    <button
                        onClick={() => removeFilter(index)}
                        className="p-0.5 text-slate-400 hover:text-red-500"
                    >
                        <X className="w-2.5 h-2.5" />
                    </button>
                </div>
            ))}
            <button
                onClick={addFilter}
                className="flex items-center gap-0.5 px-1.5 py-0.5 text-blue-600 hover:bg-blue-50 rounded"
                style={{ fontSize: '9px' }}
            >
                <Plus className="w-2.5 h-2.5" />
            </button>
        </div>
    );
}

// ============================================================================
// Results Table Component
// ============================================================================

function ResultsTable({
    results,
    onSymbolClick,
}: {
    results: ScreenerResult[];
    onSymbolClick?: (symbol: string) => void;
}) {
    // Format price with $ symbol
    const formatPrice = (value: number | null) => {
        if (value === null || value === undefined) return '-';
        if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
        if (value >= 1) return `$${value.toFixed(2)}`;
        return `$${value.toFixed(4)}`;
    };

    // Format percentage with +/- and % symbol
    const formatPercent = (value: number | null) => {
        if (value === null || value === undefined) return '-';
        const sign = value >= 0 ? '+' : '';
        return `${sign}${value.toFixed(2)}%`;
    };

    // Format volume with K/M/B suffixes
    const formatVolume = (value: number | null) => {
        if (value === null || value === undefined) return '-';
        if (value >= 1000000000) return `${(value / 1000000000).toFixed(1)}B`;
        if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
        if (value >= 1000) return `${(value / 1000).toFixed(0)}K`;
        return value.toString();
    };

    // Format multiplier (relative volume)
    const formatMultiplier = (value: number | null) => {
        if (value === null || value === undefined) return '-';
        return `${value.toFixed(2)}x`;
    };

    // Format RSI (0-100 scale, no decimals)
    const formatRSI = (value: number | null) => {
        if (value === null || value === undefined) return '-';
        return value.toFixed(0);
    };

    const getChangeColor = (value: number | null) => {
        if (value === null) return 'text-slate-400';
        return value >= 0 ? 'text-emerald-600' : 'text-red-500';
    };

    return (
        <div className="overflow-auto flex-1">
            <table className="w-full text-left" style={{ fontSize: '9px' }}>
                <thead className="sticky top-0 bg-slate-50 border-b border-slate-200">
                    <tr>
                        <th className="px-2 py-1 font-semibold text-slate-600">Symbol</th>
                        <th className="px-2 py-1 font-semibold text-slate-600 text-right">Price</th>
                        <th className="px-2 py-1 font-semibold text-slate-600 text-right">1D%</th>
                        <th className="px-2 py-1 font-semibold text-slate-600 text-right">5D%</th>
                        <th className="px-2 py-1 font-semibold text-slate-600 text-right">RSI</th>
                        <th className="px-2 py-1 font-semibold text-slate-600 text-right">RVol</th>
                        <th className="px-2 py-1 font-semibold text-slate-600 text-right">52W</th>
                        <th className="px-2 py-1 font-semibold text-slate-600 text-right">ATR%</th>
                        <th className="px-2 py-1 font-semibold text-slate-600 text-right">Vol</th>
                    </tr>
                </thead>
                <tbody>
                    {results.map((r, i) => (
                        <tr 
                            key={r.symbol} 
                            className={`border-b border-slate-50 hover:bg-blue-50/50 cursor-pointer ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/30'}`}
                            onClick={() => onSymbolClick?.(r.symbol)}
                        >
                            <td className="px-2 py-1 font-semibold text-slate-800">{r.symbol}</td>
                            <td className="px-2 py-1 text-right text-slate-700">{formatPrice(r.price)}</td>
                            <td className={`px-2 py-1 text-right font-medium ${getChangeColor(r.change_1d)}`}>
                                {formatPercent(r.change_1d)}
                            </td>
                            <td className={`px-2 py-1 text-right font-medium ${getChangeColor(r.change_5d)}`}>
                                {formatPercent(r.change_5d)}
                            </td>
                            <td className="px-2 py-1 text-right text-slate-700">
                                {formatRSI(r.rsi_14)}
                            </td>
                            <td className="px-2 py-1 text-right text-slate-700">
                                {formatMultiplier(r.relative_volume)}
                            </td>
                            <td className={`px-2 py-1 text-right ${r.from_52w_high !== null && r.from_52w_high > -5 ? 'text-emerald-600 font-medium' : 'text-slate-500'}`}>
                                {formatPercent(r.from_52w_high)}
                            </td>
                            <td className="px-2 py-1 text-right text-slate-500">
                                {formatPercent(r.atr_percent)}
                            </td>
                            <td className="px-2 py-1 text-right text-slate-500">
                                {formatVolume(r.volume)}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

// ============================================================================
// Main Component
// ============================================================================

export function ScreenerContent() {
    const font = useUserPreferencesStore(selectFont);
    const fontFamily = `var(--font-${font})`;

    // State
    const [filters, setFilters] = useState<FilterCondition[]>([
        { field: 'price', operator: 'between', value: [5, 500] },
        { field: 'relative_volume', operator: 'gt', value: 1 },
    ]);
    const [symbols, setSymbols] = useState<string[]>([]);
    const [symbolInput, setSymbolInput] = useState('');
    const [sortBy, setSortBy] = useState('relative_volume');
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
    const [limit, setLimit] = useState(50);
    
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [results, setResults] = useState<ScreenerResult[]>([]);
    const [queryTime, setQueryTime] = useState<number | null>(null);
    
    const [presets, setPresets] = useState<Preset[]>([]);
    const [showFilters, setShowFilters] = useState(true);

    // Load presets
    useEffect(() => {
        const loadPresets = async () => {
            try {
                const res = await fetch(`${API_BASE}/screen/presets`);
                if (res.ok) {
                    const data = await res.json();
                    setPresets(data.presets || []);
                }
            } catch (e) {
                console.error('Failed to load presets:', e);
            }
        };
        loadPresets();
    }, []);

    // Search handler
    const handleSearch = useCallback(async () => {
        setLoading(true);
        setError(null);

        try {
            const body: any = {
                filters,
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

    // Apply preset
    const applyPreset = (preset: Preset) => {
        setFilters(preset.filters);
        setSortBy(preset.sort_by);
        setSortOrder(preset.sort_order as 'asc' | 'desc');
    };

    return (
        <div className="h-full flex flex-col bg-white text-slate-800" style={{ fontFamily }}>
            {/* Compact Header - Symbol search + controls */}
            <div className="flex-shrink-0 px-2 py-1.5 border-b border-slate-100 flex items-center gap-2">
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
                                style={{ fontSize: '9px' }}
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
                    <span className="text-slate-400" style={{ fontSize: '9px' }}>
                        {queryTime < 1000 ? `${queryTime.toFixed(0)}ms` : `${(queryTime / 1000).toFixed(1)}s`}
                    </span>
                )}
                <button
                    onClick={() => setShowFilters(!showFilters)}
                    className={`p-1 rounded transition-colors ${showFilters ? 'bg-blue-50 text-blue-600' : 'text-slate-400 hover:text-slate-600'}`}
                >
                    <Settings2 className="w-3.5 h-3.5" />
                </button>
                <button
                    onClick={handleSearch}
                    disabled={loading}
                    className="flex items-center gap-1 px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                    style={{ fontSize: '9px' }}
                >
                    {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
                    Scan
                </button>
            </div>

            {/* Presets row */}
            <div className="flex-shrink-0 px-2 py-1 border-b border-slate-50 flex items-center gap-1 overflow-x-auto">
                {presets.slice(0, 6).map((preset) => (
                    <button
                        key={preset.id}
                        onClick={() => applyPreset(preset)}
                        className="flex-shrink-0 px-1.5 py-0.5 rounded border border-slate-200 text-slate-500 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600 whitespace-nowrap"
                        style={{ fontSize: '9px' }}
                        title={preset.description}
                    >
                        {preset.name}
                    </button>
                ))}
            </div>

            {/* Filters Panel - Compact */}
            {showFilters && (
                <div className="flex-shrink-0 px-2 py-1.5 border-b border-slate-100 bg-slate-50/50">
                    <FilterBuilder filters={filters} onFiltersChange={setFilters} />
                    
                    {/* Sort row */}
                    <div className="flex items-center gap-2 mt-1.5 pt-1.5 border-t border-slate-100">
                        <select
                            value={sortBy}
                            onChange={(e) => setSortBy(e.target.value)}
                            className="px-1 py-0.5 rounded border border-slate-200 bg-white text-slate-600"
                            style={{ fontSize: '9px' }}
                        >
                            {SORT_OPTIONS.map((opt) => (
                                <option key={opt.value} value={opt.value}>{opt.label}</option>
                            ))}
                        </select>
                        <button
                            onClick={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
                            className="px-1.5 py-0.5 rounded border border-slate-200 text-slate-500 hover:bg-slate-100"
                            style={{ fontSize: '9px' }}
                        >
                            {sortOrder === 'desc' ? 'DESC' : 'ASC'}
                        </button>
                        <span className="text-slate-300">|</span>
                        <select
                            value={limit}
                            onChange={(e) => setLimit(parseInt(e.target.value))}
                            className="px-1 py-0.5 rounded border border-slate-200 bg-white text-slate-600"
                            style={{ fontSize: '9px' }}
                        >
                            <option value={25}>25</option>
                            <option value={50}>50</option>
                            <option value={100}>100</option>
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
                <ResultsTable results={results} />
            ) : (
                <div className="flex-1 flex items-center justify-center text-slate-400" style={{ fontSize: '10px' }}>
                    {loading ? (
                        <div className="flex items-center gap-1.5">
                            <Loader2 className="w-4 h-4 animate-spin" />
                            Scanning...
                        </div>
                    ) : (
                        <div className="text-center">
                            <Search className="w-5 h-5 mx-auto mb-1 opacity-30" />
                            <p>Click Scan</p>
                        </div>
                    )}
                </div>
            )}

            {/* Footer */}
            {results.length > 0 && (
                <div className="flex-shrink-0 px-2 py-1 border-t border-slate-100 bg-slate-50/50">
                    <div className="flex items-center justify-between text-slate-400" style={{ fontSize: '8px' }}>
                        <span>{results.length} results</span>
                        <span>Polygon</span>
                    </div>
                </div>
            )}
        </div>
    );
}

