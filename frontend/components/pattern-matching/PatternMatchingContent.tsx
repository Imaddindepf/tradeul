'use client';

import { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw, AlertTriangle, TrendingUp, TrendingDown, Clock, ChevronDown, ChevronUp } from 'lucide-react';
import { TickerSearch } from '@/components/common/TickerSearch';

// Types
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
        timestamp: string;
        cross_asset: boolean;
    };
    forecast: PatternForecast;
    neighbors: PatternNeighbor[];
    stats: {
        query_time_ms: number;
        index_size: number;
        k_requested: number;
        k_returned: number;
    };
}

interface IndexStats {
    status: string;
    n_vectors: number;
    n_metadata: number;
    dimension: number;
    index_type: string;
    is_trained: boolean;
    memory_mb: number;
}

// API base - usa API Gateway en producción
const getApiBase = () => {
    if (typeof window !== 'undefined' && window.location.hostname === 'tradeul.com') {
        return 'https://api.tradeul.com/patterns';
    }
    return process.env.NEXT_PUBLIC_PATTERN_API_URL || 'http://localhost:8025';
};

// Mini trajectory chart
function MiniChart({ trajectory, positive }: { trajectory: number[]; positive: boolean }) {
    if (!trajectory || trajectory.length === 0) return null;
    const max = Math.max(...trajectory.map(Math.abs), 0.01);
    const h = 16;
    const w = 50;
    const mid = h / 2;
    const points = trajectory.map((v, i) => `${(i / (trajectory.length - 1)) * w},${mid - (v / max) * (h / 2 - 1)}`).join(' ');

    return (
        <svg width={w} height={h} className="inline-block">
            <line x1="0" y1={mid} x2={w} y2={mid} stroke="#e2e8f0" strokeWidth="1" />
            <polyline points={points} fill="none" stroke={positive ? '#10b981' : '#ef4444'} strokeWidth="1.5" />
        </svg>
    );
}

// Neighbor row
function NeighborRow({ neighbor, index }: { neighbor: PatternNeighbor; index: number }) {
    const [open, setOpen] = useState(false);
    const ret = neighbor.future_returns[neighbor.future_returns.length - 1];
    const pos = ret >= 0;

    return (
        <div
            className="border-b border-slate-100 last:border-0 cursor-pointer hover:bg-slate-50 transition-colors"
            onClick={() => setOpen(!open)}
        >
            <div className="flex items-center gap-1.5 px-1.5 py-1">
                <span className="text-[9px] text-slate-400 w-3">{index + 1}</span>
                <span className="text-[10px] font-mono font-semibold text-blue-600 w-10">{neighbor.symbol}</span>
                <span className="text-[9px] text-slate-400 flex-1">{neighbor.date}</span>
                <MiniChart trajectory={neighbor.future_returns} positive={pos} />
                <span className={`text-[10px] font-mono font-medium w-12 text-right ${pos ? 'text-emerald-600' : 'text-red-500'}`}>
                    {pos ? '+' : ''}{ret.toFixed(2)}%
                </span>
                {open ? <ChevronUp className="w-2.5 h-2.5 text-slate-400" /> : <ChevronDown className="w-2.5 h-2.5 text-slate-400" />}
            </div>
            {open && (
                <div className="px-1.5 pb-1 pt-0.5 bg-slate-50 text-[8px] text-slate-500 grid grid-cols-3 gap-1">
                    <div>Time: {neighbor.start_time}</div>
                    <div>Dist: {neighbor.distance.toFixed(4)}</div>
                    <div>Pts: {neighbor.future_returns.length}</div>
                </div>
            )}
        </div>
    );
}

export function PatternMatchingContent({ initialTicker }: { initialTicker?: string }) {
    const { t } = useTranslation();
    const [ticker, setTicker] = useState(initialTicker || '');
    const [k, setK] = useState(30);
    const [crossAsset, setCrossAsset] = useState(true);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [result, setResult] = useState<SearchResult | null>(null);
    const [indexStats, setIndexStats] = useState<IndexStats | null>(null);

    // Fetch index stats
    useEffect(() => {
        const fetchStats = async () => {
            try {
                const res = await fetch(`${getApiBase()}/api/index/stats`);
                if (res.ok) setIndexStats(await res.json());
            } catch (e) {
                console.error('Stats fetch error:', e);
            }
        };
        fetchStats();
    }, []);

    const handleSearch = useCallback(async () => {
        if (!ticker.trim()) return;
        setLoading(true);
        setError(null);

        try {
            const res = await fetch(`${getApiBase()}/api/search/${ticker.toUpperCase()}?k=${k}&cross_asset=${crossAsset}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Search failed');
            if (data.status === 'error') throw new Error(data.error || 'Search failed');
            setResult(data);
        } catch (e: any) {
            setError(e.message || 'Search failed');
            setResult(null);
        } finally {
            setLoading(false);
        }
    }, [ticker, k, crossAsset]);

    const handleTickerSelect = (tickerResult: any) => {
        setTicker(tickerResult.symbol);
    };

    return (
        <div className="h-full flex flex-col bg-white text-slate-900 text-[10px]">
            {/* Header */}
            <div className="flex items-center justify-between px-2 py-1.5 border-b border-slate-200 bg-slate-50">
                <div className="flex items-center gap-2">
                    <span className="text-[10px] font-semibold text-slate-700 uppercase tracking-wide">Pattern Matching</span>
                    {indexStats && indexStats.status === 'ready' && (
                        <span className="text-[9px] text-slate-400 font-mono">
                            {(indexStats.n_vectors / 1000).toFixed(0)}K
                        </span>
                    )}
                </div>
                {result?.stats && (
                    <span className="text-[9px] text-slate-400 flex items-center gap-1">
                        <Clock className="w-2.5 h-2.5" />
                        {result.stats.query_time_ms.toFixed(0)}ms
                    </span>
                )}
            </div>

            {/* Search */}
            <div className="px-2 py-1.5 border-b border-slate-200 space-y-1.5">
                <div className="flex gap-1.5">
                    <div className="flex-1">
                        <TickerSearch
                            value={ticker}
                            onChange={setTicker}
                            onSelect={handleTickerSelect}
                            placeholder="TICKER"
                            autoFocus
                        />
                    </div>
                    <button
                        onClick={handleSearch}
                        disabled={loading || !ticker.trim()}
                        className="px-2 py-0.5 text-[10px] font-medium bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                    >
                        {loading && <RefreshCw className="w-3 h-3 animate-spin" />}
                        Search
                    </button>
                </div>

                {/* Options */}
                <div className="flex items-center gap-3 text-[9px]">
                    <label className="flex items-center gap-1 text-slate-500">
                        k:
                        <input
                            type="number"
                            value={k}
                            onChange={(e) => setK(Math.min(200, Math.max(1, parseInt(e.target.value) || 30)))}
                            className="w-8 px-1 py-0.5 border border-slate-200 rounded text-center text-[9px]"
                        />
                    </label>
                    <label className="flex items-center gap-1 text-slate-500 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={crossAsset}
                            onChange={(e) => setCrossAsset(e.target.checked)}
                            className="w-3 h-3 rounded border-slate-300 text-blue-500 focus:ring-blue-500"
                        />
                        Cross-asset
                    </label>
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto">
                {error && (
                    <div className="m-1.5 p-1.5 text-[10px] bg-amber-50 border border-amber-200 rounded text-amber-700 flex items-start gap-1.5">
                        <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-0.5" />
                        <div>
                            <p className="font-medium">{error.includes('No price data') ? 'Market is closed' : 'Error'}</p>
                            <p className="text-[9px] text-amber-600 mt-0.5">
                                {error.includes('No price data')
                                    ? 'Real-time data not available. Try when market opens.'
                                    : error}
                            </p>
                        </div>
                    </div>
                )}

                {!result && !loading && !error && (
                    <div className="h-full flex flex-col items-center justify-center text-center p-4 text-slate-400">
                        <p className="text-[10px]">{t('patternMatching.selectPatternPrompt', 'Enter ticker to find similar patterns')}</p>
                    </div>
                )}

                {loading && (
                    <div className="h-full flex flex-col items-center justify-center">
                        <RefreshCw className="w-5 h-5 text-blue-500 animate-spin mb-1" />
                        <p className="text-[9px] text-slate-400">Searching...</p>
                    </div>
                )}

                {result && result.forecast && (
                    <div className="p-1.5 space-y-2">
                        {/* Forecast */}
                        <div className="border border-slate-200 rounded overflow-hidden">
                            <div className="px-1.5 py-1 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                                <span className="text-[9px] font-medium text-slate-600 uppercase">Forecast {result.forecast.horizon_minutes}min</span>
                                <span className={`text-[8px] px-1 py-0.5 rounded font-medium ${result.forecast.confidence === 'high' ? 'bg-emerald-100 text-emerald-700' :
                                    result.forecast.confidence === 'medium' ? 'bg-amber-100 text-amber-700' :
                                        'bg-red-100 text-red-700'
                                    }`}>
                                    {result.forecast.confidence}
                                </span>
                            </div>

                            <div className="p-1.5">
                                {/* Probability */}
                                <div className="mb-1.5">
                                    <div className="flex justify-between text-[8px] mb-0.5">
                                        <span className="text-emerald-600 flex items-center gap-0.5">
                                            <TrendingUp className="w-2.5 h-2.5" />
                                            {(result.forecast.prob_up * 100).toFixed(0)}%
                                        </span>
                                        <span className="text-red-500 flex items-center gap-0.5">
                                            {(result.forecast.prob_down * 100).toFixed(0)}%
                                            <TrendingDown className="w-2.5 h-2.5" />
                                        </span>
                                    </div>
                                    <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden flex">
                                        <div className="bg-emerald-500" style={{ width: `${result.forecast.prob_up * 100}%` }} />
                                        <div className="bg-red-500" style={{ width: `${result.forecast.prob_down * 100}%` }} />
                                    </div>
                                </div>

                                {/* Stats */}
                                <div className="grid grid-cols-4 gap-1 text-center">
                                    <div className="p-1 bg-slate-50 rounded">
                                        <p className="text-[7px] text-slate-400 uppercase">Expected</p>
                                        <p className={`text-[10px] font-mono font-semibold ${result.forecast.mean_return >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                                            {result.forecast.mean_return >= 0 ? '+' : ''}{result.forecast.mean_return.toFixed(2)}%
                                        </p>
                                    </div>
                                    <div className="p-1 bg-slate-50 rounded">
                                        <p className="text-[7px] text-slate-400 uppercase">Median</p>
                                        <p className={`text-[10px] font-mono font-semibold ${result.forecast.median_return >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                                            {result.forecast.median_return >= 0 ? '+' : ''}{result.forecast.median_return.toFixed(2)}%
                                        </p>
                                    </div>
                                    <div className="p-1 bg-emerald-50 rounded">
                                        <p className="text-[7px] text-emerald-600 uppercase">Best</p>
                                        <p className="text-[10px] font-mono font-semibold text-emerald-600">+{result.forecast.best_case.toFixed(2)}%</p>
                                    </div>
                                    <div className="p-1 bg-red-50 rounded">
                                        <p className="text-[7px] text-red-500 uppercase">Worst</p>
                                        <p className="text-[10px] font-mono font-semibold text-red-500">{result.forecast.worst_case.toFixed(2)}%</p>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Neighbors */}
                        <div className="border border-slate-200 rounded overflow-hidden">
                            <div className="px-1.5 py-1 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                                <span className="text-[9px] font-medium text-slate-600 uppercase">Similar Patterns</span>
                                <span className="text-[8px] text-slate-400">{result.neighbors.length}</span>
                            </div>
                            <div className="max-h-[180px] overflow-y-auto">
                                {result.neighbors.slice(0, 15).map((n, i) => (
                                    <NeighborRow key={i} neighbor={n} index={i} />
                                ))}
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default PatternMatchingContent;
