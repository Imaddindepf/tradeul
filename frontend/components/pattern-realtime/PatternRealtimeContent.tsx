'use client';

/**
 * Pattern Real-Time Scanner
 * =========================
 * 
 * Batch scanning component for multiple symbols with real-time updates.
 * Clean white/blue theme matching Tradeul design system.
 * 
 * Layout:
 * - Row 1: Symbols textarea | Inputs + Run/Stop | Progress + Filters
 * - Row 2: Performance Summary | Top Suggestions | All Scanned | Failures
 */

import { useState, useCallback, useEffect, useMemo } from 'react';
import {
    Play,
    Square,
    Loader2,
    ChevronDown,
    ChevronUp,
    Trash2,
} from 'lucide-react';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { usePatternRealtimeWS, PredictionResult, PriceUpdate } from '@/hooks/usePatternRealtimeWS';
import { cn } from '@/lib/utils';

// Real-time price update tracking
interface RealtimePriceData {
    current_price: number;
    unrealized_return: number;
    unrealized_pnl: number;
    is_currently_correct: boolean;
    minutes_remaining: number;
    timestamp: string;
}

// ============================================================================
// Constants & Types
// ============================================================================

const API_BASE = process.env.NEXT_PUBLIC_PATTERN_API_URL || 'https://api.tradeul.com/patterns';

interface PerformanceStats {
    period: string;
    total_predictions: number;
    verified: number;
    pending: number;
    all_stats: BucketStats | null;
    top_1pct: BucketStats | null;
    top_5pct: BucketStats | null;
    top_10pct: BucketStats | null;
    long_stats: BucketStats | null;
    short_stats: BucketStats | null;
}

interface BucketStats {
    n: number;
    long_count: number;
    short_count: number;
    win_rate: number | null;
    mean_pnl: number | null;
    median_pnl: number | null;
}

interface JobResponse {
    job_id: string;
    status: string;
    total_symbols: number;
    started_at: string;
    message: string;
}

interface JobStatus {
    job_id: string;
    status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
    progress: { completed: number; total: number; failed: number };
    started_at: string;
    completed_at: string | null;
    duration_seconds: number | null;
    results: PredictionResult[];
    failures: FailureResult[];
    params: Record<string, unknown>;
}

interface FailureResult {
    symbol: string;
    scan_time: string;
    error_code: string;
    reason: string;
    bars_since_open?: number;
    bars_until_close?: number;
}

interface SavedRun {
    id: string;
    name: string;
    timestamp: string;
    results: PredictionResult[];
}

type SortField = 'edge' | 'prob_up' | 'mean_return' | 'symbol';
type DirectionFilter = 'ALL' | 'LONG' | 'SHORT';

const DEFAULT_SYMBOLS = `AAPL NVDA META GOOGL MSFT AMZN JPM BAC XOM HD PG KO PEP JNJ UNH TPL SMCI COIN SBAC HSY`;

// ============================================================================
// Component
// ============================================================================

interface PatternRealtimeContentProps {
    initialSymbols?: string[];
}

export function PatternRealtimeContent({ initialSymbols }: PatternRealtimeContentProps) {
    const font = useUserPreferencesStore(selectFont);

    // ========================================================================
    // State - Parameters
    // ========================================================================
    const [symbolsText, setSymbolsText] = useState(
        initialSymbols?.join(' ') || DEFAULT_SYMBOLS
    );
    const [timestamp, setTimestamp] = useState('');
    const [timezone, setTimezone] = useState<'ET' | 'UTC'>('ET');
    const [k, setK] = useState(40);
    const [extend, setExtend] = useState(45);
    const [horizon, setHorizon] = useState(10);
    const [weighting, setWeighting] = useState<'softmax' | 'uniform'>('softmax');
    const [alpha, setAlpha] = useState(6);
    const [excludeSelf, setExcludeSelf] = useState(true);
    const [trimLo, setTrimLo] = useState(0);
    const [trimHi, setTrimHi] = useState(0);
    const [includeWeights, setIncludeWeights] = useState(false);
    const [useRealtime, setUseRealtime] = useState(true);

    // State - Filters
    const [sortBy, setSortBy] = useState<SortField>('edge');
    const [direction, setDirection] = useState<DirectionFilter>('ALL');
    const [showTopN, setShowTopN] = useState(50);
    const [savedRuns, setSavedRuns] = useState<SavedRun[]>([]);
    const [selectedRun, setSelectedRun] = useState<string>('');

    // State - Execution
    const [isScanning, setIsScanning] = useState(false);
    const [currentJobId, setCurrentJobId] = useState<string | null>(null);
    const [progress, setProgress] = useState({ completed: 0, total: 0, failed: 0 });
    const [currentTime, setCurrentTime] = useState('');

    // State - Results
    const [predictions, setPredictions] = useState<PredictionResult[]>([]);
    const [failures, setFailures] = useState<FailureResult[]>([]);
    const [stats, setStats] = useState<PerformanceStats | null>(null);

    // State - Real-time price tracking
    const [realtimePrices, setRealtimePrices] = useState<Map<string, RealtimePriceData>>(new Map());

    // ========================================================================
    // Parse symbols
    // ========================================================================
    const symbols = useMemo(() => {
        return symbolsText
            .split(/[\s,\n]+/)
            .map(s => s.trim().toUpperCase())
            .filter(s => s.length > 0 && s.length <= 5);
    }, [symbolsText]);

    // ========================================================================
    // API Calls (defined early for use in callbacks)
    // ========================================================================
    const fetchStats = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/pattern-realtime/performance?period=today`);
            if (res.ok) {
                const data = await res.json();
                setStats(data);
            }
        } catch (e) {
            console.error('[PatternRealtime] Failed to fetch stats:', e);
        }
    }, []);

    // ========================================================================
    // WebSocket
    // ========================================================================
    const handleResult = useCallback((prediction: PredictionResult) => {
        setPredictions(prev => {
            const idx = prev.findIndex(p => p.id === prediction.id);
            if (idx >= 0) {
                const updated = [...prev];
                updated[idx] = prediction;
                return updated;
            }
            return [...prev, prediction];
        });
    }, []);

    const handleJobComplete = useCallback((jobId: string, results: PredictionResult[]) => {
        if (jobId === currentJobId) {
            // Don't set isScanning=false here - keep running while predictions are active
            // Session ends when: user clicks Stop OR all predictions expire
            setPredictions(results);
            fetchStats();
        }
    }, [currentJobId, fetchStats]);

    const handleProgress = useCallback((jobId: string, prog: { completed: number; total: number }) => {
        if (jobId === currentJobId) {
            setProgress(prev => ({ ...prev, ...prog }));
        }
    }, [currentJobId]);

    const handlePriceUpdate = useCallback((update: PriceUpdate) => {
        setRealtimePrices(prev => {
            const next = new Map(prev);
            next.set(update.prediction_id, {
                current_price: update.current_price,
                unrealized_return: update.unrealized_return,
                unrealized_pnl: update.unrealized_pnl,
                is_currently_correct: update.is_currently_correct,
                minutes_remaining: update.minutes_remaining,
                timestamp: update.timestamp,
            });
            return next;
        });
    }, []);

    const { subscribe } = usePatternRealtimeWS({
        onResult: handleResult,
        onJobComplete: handleJobComplete,
        onProgress: handleProgress,
        onPriceUpdate: handlePriceUpdate,
    });

    // ========================================================================
    // Auto-stop when all predictions expire
    // ========================================================================
    useEffect(() => {
        if (!isScanning || predictions.length === 0) return;

        // Only auto-stop if we have real-time price data for at least some predictions
        // This prevents false positives when price_tracker hasn't sent updates yet
        const predictionsWithRtData = predictions.filter(p => realtimePrices.has(p.id));
        if (predictionsWithRtData.length === 0) return; // Wait for price updates

        // Check if all predictions with RT data have expired
        const allExpired = predictionsWithRtData.every(p => {
            const rtData = realtimePrices.get(p.id);
            return rtData && rtData.minutes_remaining <= 0;
        });

        if (allExpired) {
            setIsScanning(false);
            fetchStats(); // Refresh stats after all predictions verified
        }
    }, [isScanning, predictions, realtimePrices, fetchStats]);

    // ========================================================================
    // Time updates
    // ========================================================================
    useEffect(() => {
        const updateTime = () => {
            const now = new Date();
            const etOptions: Intl.DateTimeFormatOptions = {
                timeZone: 'America/New_York',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                hour12: false,
            };
            const formatted = now.toLocaleString('en-CA', etOptions).replace(',', '');
            setCurrentTime(formatted);
        };
        updateTime();
        const interval = setInterval(updateTime, 1000);
        return () => clearInterval(interval);
    }, []);

    const startScan = useCallback(async () => {
        if (symbols.length === 0) return;

        setIsScanning(true);
        setPredictions([]);
        setFailures([]);
        setProgress({ completed: 0, total: symbols.length, failed: 0 });

        try {
            const res = await fetch(`${API_BASE}/api/pattern-realtime/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symbols,
                    k,
                    horizon,
                    alpha,
                    trim_lo: trimLo,
                    trim_hi: trimHi,
                    exclude_self: excludeSelf,
                    cross_asset: true,
                }),
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const data: JobResponse = await res.json();
            setCurrentJobId(data.job_id);
            subscribe(data.job_id);
            pollJobStatus(data.job_id);

        } catch (e) {
            console.error('[PatternRealtime] Start scan failed:', e);
            setIsScanning(false);
        }
    }, [symbols, k, horizon, alpha, trimLo, trimHi, excludeSelf, subscribe]);

    const stopScan = useCallback(() => {
        // Only stop scanning - keep data visible for user review
        setIsScanning(false);
        // Don't clear predictions or realtimePrices - user wants to see results
        // Only clear job ID to stop receiving new updates
        setCurrentJobId('');
        fetchStats(); // Refresh stats when manually stopped
    }, [fetchStats]);

    const clearData = useCallback(() => {
        // Clear all data - use this to start fresh
        setPredictions([]);
        setRealtimePrices(new Map());
        setFailures([]);
        setProgress({ completed: 0, total: 0, failed: 0 });
    }, []);

    const pollJobStatus = useCallback(async (jobId: string) => {
        const poll = async () => {
            try {
                const res = await fetch(`${API_BASE}/api/pattern-realtime/job/${jobId}`);
                if (res.ok) {
                    const data: JobStatus = await res.json();
                    setProgress({
                        completed: data.progress.completed,
                        total: data.progress.total,
                        failed: data.progress.failed,
                    });

                    if (data.status === 'completed' || data.status === 'failed') {
                        // Job scan finished - but keep isScanning=true while predictions are active
                        // User must press Stop to end the session, or wait for all predictions to expire
                        setPredictions(data.results);
                        setFailures(data.failures || []);
                        fetchStats();
                        return;
                    }
                    setTimeout(poll, 500);
                }
            } catch (e) {
                console.error('[PatternRealtime] Poll error:', e);
            }
        };
        setTimeout(poll, 300);
    }, [fetchStats]);

    // ========================================================================
    // Sorting & Filtering
    // ========================================================================
    const filteredPredictions = useMemo(() => {
        let filtered = [...predictions];

        if (direction === 'LONG') {
            filtered = filtered.filter(p => p.direction === 'UP');
        } else if (direction === 'SHORT') {
            filtered = filtered.filter(p => p.direction === 'DOWN');
        }

        filtered.sort((a, b) => {
            switch (sortBy) {
                case 'edge': return b.edge - a.edge;
                case 'prob_up': return b.prob_up - a.prob_up;
                case 'mean_return': return b.mean_return - a.mean_return;
                case 'symbol': return a.symbol.localeCompare(b.symbol);
                default: return 0;
            }
        });

        return filtered.slice(0, showTopN);
    }, [predictions, direction, sortBy, showTopN]);

    const topSuggestions = useMemo(() => {
        return [...predictions]
            .sort((a, b) => b.edge - a.edge)
            .slice(0, showTopN);
    }, [predictions, showTopN]);

    // ========================================================================
    // Saved Runs
    // ========================================================================
    const deleteSelectedRun = useCallback(() => {
        if (!selectedRun) return;
        setSavedRuns(prev => prev.filter(r => r.id !== selectedRun));
        setSelectedRun('');
    }, [selectedRun]);

    // ========================================================================
    // Render
    // ========================================================================
    const fontFamily = `var(--font-${font})`;

    return (
        <div
            className="h-full flex flex-col bg-white text-slate-800 overflow-hidden font-mono text-xs"
            style={{ fontFamily }}
        >
            {/* Row 1: Inputs */}
            <div className="flex-shrink-0 grid grid-cols-3 gap-4 p-4 border-b border-slate-200 bg-white">
                {/* Column 1: Symbols */}
                <div className="flex flex-col">
                    <label className="text-slate-600 mb-1">Symbols (space/comma/newline)</label>
                    <textarea
                        value={symbolsText}
                        onChange={(e) => setSymbolsText(e.target.value)}
                        className="flex-1 min-h-[120px] p-2 bg-white border border-slate-300 rounded text-slate-800 resize-none focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                        placeholder="AAPL NVDA META..."
                    />
                </div>

                {/* Column 2: Parameters + Run/Stop */}
                <div className="flex flex-col gap-2">
                    <div className="flex gap-4">
                        <div className="flex-1">
                            <label className="text-slate-600 text-[10px]">Timestamp (ignored in real-time; using {currentTime})</label>
                            <input
                                type="text"
                                value={timestamp}
                                onChange={(e) => setTimestamp(e.target.value)}
                                placeholder="2024-03-18 10:02"
                                className="w-full mt-0.5 px-2 py-1 bg-white border border-slate-300 rounded text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                            />
                        </div>
                        <div className="w-24">
                            <label className="text-slate-600 text-[10px]">TZ (applies to "now")</label>
                            <select
                                value={timezone}
                                onChange={(e) => setTimezone(e.target.value as 'ET' | 'UTC')}
                                className="w-full mt-0.5 px-2 py-1 bg-white border border-slate-300 rounded text-slate-800 focus:outline-none focus:border-blue-500"
                            >
                                <option value="ET">ET</option>
                                <option value="UTC">UTC</option>
                            </select>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                        <div>
                            <label className="text-slate-600 text-[10px]">k</label>
                            <input
                                type="number"
                                value={k}
                                onChange={(e) => setK(Number(e.target.value))}
                                className="w-full px-2 py-1 bg-white border border-slate-300 rounded text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                            />
                        </div>
                        <div>
                            <label className="text-slate-600 text-[10px]">extend</label>
                            <input
                                type="number"
                                value={extend}
                                onChange={(e) => setExtend(Number(e.target.value))}
                                className="w-full px-2 py-1 bg-white border border-slate-300 rounded text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                            />
                        </div>
                        <div>
                            <label className="text-slate-600 text-[10px]">Horizon (min)</label>
                            <input
                                type="number"
                                value={horizon}
                                onChange={(e) => setHorizon(Number(e.target.value))}
                                className="w-full px-2 py-1 bg-white border border-slate-300 rounded text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                            />
                        </div>
                        <div>
                            <label className="text-slate-600 text-[10px]">Weighting</label>
                            <select
                                value={weighting}
                                onChange={(e) => setWeighting(e.target.value as 'softmax' | 'uniform')}
                                className="w-full px-2 py-1 bg-white border border-slate-300 rounded text-slate-800 focus:outline-none focus:border-blue-500"
                            >
                                <option value="softmax">softmax</option>
                                <option value="uniform">uniform</option>
                            </select>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                        <div>
                            <label className="text-slate-600 text-[10px]">alpha</label>
                            <input
                                type="number"
                                value={alpha}
                                onChange={(e) => setAlpha(Number(e.target.value))}
                                className="w-full px-2 py-1 bg-white border border-slate-300 rounded text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                            />
                        </div>
                        <div className="flex items-end pb-1">
                            <label className="flex items-center gap-2 text-slate-700 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={excludeSelf}
                                    onChange={(e) => setExcludeSelf(e.target.checked)}
                                    className="accent-blue-600"
                                />
                                exclude self
                            </label>
                        </div>
                        <div>
                            <label className="text-slate-600 text-[10px]">trim lo (%)</label>
                            <input
                                type="number"
                                value={trimLo}
                                onChange={(e) => setTrimLo(Number(e.target.value))}
                                className="w-full px-2 py-1 bg-white border border-slate-300 rounded text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                            />
                        </div>
                        <div>
                            <label className="text-slate-600 text-[10px]">trim hi (%)</label>
                            <input
                                type="number"
                                value={trimHi}
                                onChange={(e) => setTrimHi(Number(e.target.value))}
                                className="w-full px-2 py-1 bg-white border border-slate-300 rounded text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                            />
                        </div>
                    </div>

                    <div className="flex flex-col gap-1">
                        <label className="flex items-center gap-2 text-slate-700 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={includeWeights}
                                onChange={(e) => setIncludeWeights(e.target.checked)}
                                className="accent-blue-600"
                            />
                            include weights (audit)
                        </label>
                        <label className="flex items-center gap-2 text-slate-700 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={useRealtime}
                                onChange={(e) => setUseRealtime(e.target.checked)}
                                className="accent-blue-600"
                            />
                            Use real-time 1m (last 30) via tuple
                        </label>
                    </div>

                    <div className="flex gap-2 mt-2">
                        <button
                            onClick={startScan}
                            disabled={isScanning || symbols.length === 0}
                            className={cn(
                                "flex-1 flex items-center justify-center gap-2 py-2 rounded font-medium transition-colors",
                                isScanning
                                    ? "bg-slate-300 text-slate-500 cursor-not-allowed"
                                    : "bg-blue-600 text-white hover:bg-blue-500"
                            )}
                        >
                            {isScanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                            Run
                        </button>
                        <button
                            onClick={stopScan}
                            disabled={!isScanning}
                            className={cn(
                                "flex-1 flex items-center justify-center gap-2 py-2 rounded font-medium border transition-colors",
                                isScanning
                                    ? "border-red-500 text-red-600 hover:bg-red-50"
                                    : "border-slate-300 text-slate-400 cursor-not-allowed"
                            )}
                        >
                            <Square className="w-4 h-4" />
                            Stop
                        </button>
                        <button
                            onClick={clearData}
                            disabled={isScanning || (predictions.length === 0 && failures.length === 0)}
                            className={cn(
                                "px-3 py-2 rounded font-medium border transition-colors",
                                !isScanning && (predictions.length > 0 || failures.length > 0)
                                    ? "border-slate-400 text-slate-600 hover:bg-slate-100"
                                    : "border-slate-200 text-slate-300 cursor-not-allowed"
                            )}
                            title="Clear all results"
                        >
                            <Trash2 className="w-4 h-4" />
                        </button>
                    </div>
                </div>

                {/* Column 3: Progress + Filters */}
                <div className="flex flex-col gap-2">
                    <div>
                        <label className="text-slate-600 text-[10px]">Progress</label>
                        <div className="mt-1 h-2 bg-slate-200 rounded-full overflow-hidden">
                            <div
                                className="h-full bg-blue-500 transition-all duration-300"
                                style={{ width: progress.total > 0 ? `${(progress.completed / progress.total) * 100}%` : '0%' }}
                            />
                        </div>
                        <div className="mt-1 text-blue-600 font-medium">{progress.completed} / {progress.total}</div>
                        <div className="text-slate-500">Failures in last batch: <span className="text-slate-700">{progress.failed}</span></div>
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                        <div>
                            <label className="text-slate-600 text-[10px]">Sort by</label>
                            <select
                                value={sortBy}
                                onChange={(e) => setSortBy(e.target.value as SortField)}
                                className="w-full px-2 py-1 bg-white border border-slate-300 rounded text-slate-800 focus:outline-none focus:border-blue-500"
                            >
                                <option value="edge">edge</option>
                                <option value="prob_up">prob_up</option>
                                <option value="mean_return">mean</option>
                                <option value="symbol">symbol</option>
                            </select>
                        </div>
                        <div>
                            <label className="text-slate-600 text-[10px]">Direction</label>
                            <select
                                value={direction}
                                onChange={(e) => setDirection(e.target.value as DirectionFilter)}
                                className="w-full px-2 py-1 bg-white border border-slate-300 rounded text-slate-800 focus:outline-none focus:border-blue-500"
                            >
                                <option value="ALL">ALL</option>
                                <option value="LONG">LONG</option>
                                <option value="SHORT">SHORT</option>
                            </select>
                        </div>
                    </div>

                    <div>
                        <label className="text-slate-600 text-[10px]">Show top N</label>
                        <input
                            type="number"
                            value={showTopN}
                            onChange={(e) => setShowTopN(Number(e.target.value))}
                            className="w-full px-2 py-1 bg-white border border-slate-300 rounded text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                        />
                    </div>

                    <div>
                        <label className="text-slate-600 text-[10px]">Saved runs (local)</label>
                        <div className="flex gap-2">
                            <select
                                value={selectedRun}
                                onChange={(e) => setSelectedRun(e.target.value)}
                                className="flex-1 px-2 py-1 bg-white border border-slate-300 rounded text-slate-800 focus:outline-none focus:border-blue-500"
                            >
                                <option value="">— Select —</option>
                                {savedRuns.map(run => (
                                    <option key={run.id} value={run.id}>{run.name}</option>
                                ))}
                            </select>
                            <button
                                onClick={deleteSelectedRun}
                                disabled={!selectedRun}
                                className="px-3 py-1 border border-slate-300 rounded text-slate-600 hover:text-red-600 hover:border-red-500 disabled:opacity-50"
                            >
                                Delete
                            </button>
                        </div>
                    </div>

                    <div className="text-right text-slate-500 mt-auto">
                        as of <span className="text-slate-700 font-medium">{currentTime}</span> ET
                    </div>
                </div>
            </div>

            {/* Row 2: Tables */}
            <div className="flex-1 grid grid-cols-2 gap-2 p-2 overflow-hidden bg-slate-50">
                {/* Performance Summary */}
                <div className="border border-slate-200 rounded bg-white overflow-hidden flex flex-col">
                    <div className="px-2 py-1.5 bg-slate-100 border-b border-slate-200 text-slate-700 font-medium">
                        Performance Summary @ {horizon}m (directional P&L)
                    </div>
                    <div className="flex-1 overflow-auto">
                        <table className="w-full text-[11px]">
                            <thead className="bg-slate-50 sticky top-0">
                                <tr className="text-slate-500">
                                    <th className="px-2 py-1 text-left font-medium">Bucket</th>
                                    <th className="px-2 py-1 text-center font-medium">N</th>
                                    <th className="px-2 py-1 text-center font-medium">Long</th>
                                    <th className="px-2 py-1 text-center font-medium">Short</th>
                                    <th className="px-2 py-1 text-center font-medium">Win-rate</th>
                                    <th className="px-2 py-1 text-center font-medium">Mean P&L</th>
                                    <th className="px-2 py-1 text-center font-medium">Median P&L</th>
                                </tr>
                            </thead>
                            <tbody>
                                <PerformanceRow label="Top 1%" stats={stats?.top_1pct} />
                                <PerformanceRow label="Top 5%" stats={stats?.top_5pct} />
                                <PerformanceRow label="Top 10%" stats={stats?.top_10pct} />
                                <PerformanceRow label="All" stats={stats?.all_stats} />
                            </tbody>
                        </table>
                        <div className="px-2 py-1 text-[10px] text-slate-500 border-t border-slate-100">
                            P&L is computed as <span className="italic">actual</span> for LONG and <span className="italic">-actual</span> for SHORT.
                        </div>
                    </div>
                </div>

                {/* Top Suggestions */}
                <div className="border border-slate-200 rounded bg-white overflow-hidden flex flex-col">
                    <div className="px-2 py-1.5 bg-slate-100 border-b border-slate-200 text-slate-700 font-medium">
                        Top suggestions @ {horizon}m (ranked by edge)
                    </div>
                    <div className="flex-1 overflow-auto">
                        <PredictionsTable predictions={topSuggestions} realtimePrices={realtimePrices} />
                    </div>
                </div>

                {/* All Scanned */}
                <div className="border border-slate-200 rounded bg-white overflow-hidden flex flex-col">
                    <div className="px-2 py-1.5 bg-slate-100 border-b border-slate-200 text-slate-700 font-medium">
                        All scanned (latest batch)
                    </div>
                    <div className="flex-1 overflow-auto">
                        <PredictionsTable predictions={filteredPredictions} realtimePrices={realtimePrices} />
                    </div>
                </div>

                {/* Failures */}
                <div className="border border-slate-200 rounded bg-white overflow-hidden flex flex-col">
                    <div className="px-2 py-1.5 bg-slate-100 border-b border-slate-200 text-slate-700 font-medium">
                        Failures (this batch)
                    </div>
                    <div className="flex-1 overflow-auto">
                        <table className="w-full text-[11px]">
                            <thead className="bg-slate-50 sticky top-0">
                                <tr className="text-slate-500">
                                    <th className="px-2 py-1 text-left font-medium">symbol</th>
                                    <th className="px-2 py-1 text-left font-medium">time (ET)</th>
                                    <th className="px-2 py-1 text-left font-medium">code</th>
                                    <th className="px-2 py-1 text-left font-medium">error</th>
                                    <th className="px-2 py-1 text-left font-medium">reasons</th>
                                    <th className="px-2 py-1 text-center font-medium">bars_since_open</th>
                                    <th className="px-2 py-1 text-center font-medium">bars_until_close</th>
                                </tr>
                            </thead>
                            <tbody>
                                {failures.length === 0 ? (
                                    <tr>
                                        <td colSpan={7} className="px-2 py-2 text-slate-400">No failures</td>
                                    </tr>
                                ) : (
                                    failures.map((f, i) => (
                                        <tr key={i} className="border-t border-slate-100 hover:bg-slate-50">
                                            <td className="px-2 py-1 text-slate-800 font-medium">{f.symbol}</td>
                                            <td className="px-2 py-1 text-slate-500">{f.scan_time?.slice(0, 16)}</td>
                                            <td className="px-2 py-1 text-orange-600">{f.error_code}</td>
                                            <td className="px-2 py-1 text-slate-600">{f.error_code}</td>
                                            <td className="px-2 py-1 text-slate-500">{f.reason}</td>
                                            <td className="px-2 py-1 text-center text-slate-600">{f.bars_since_open ?? '—'}</td>
                                            <td className="px-2 py-1 text-center text-slate-600">{f.bars_until_close ?? '—'}</td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                        <div className="px-2 py-1 text-[10px] text-slate-400 border-t border-slate-100">
                            E_WEEKEND: Saturday/Sunday  E_MARKET_CLOSED: outside 09:30-16:00 ET  E_WINDOW: index or tuple couldn't form a contiguous 30-bar window ending the requested
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

// ============================================================================
// Sub-components
// ============================================================================

function PerformanceRow({ label, stats }: { label: string; stats?: BucketStats | null }) {
    return (
        <tr className="border-t border-slate-100 hover:bg-slate-50">
            <td className="px-2 py-1 text-slate-800">{label}</td>
            <td className="px-2 py-1 text-center text-slate-600">{stats?.n ?? '—'}</td>
            <td className="px-2 py-1 text-center text-slate-600">{stats?.long_count ?? 0}</td>
            <td className="px-2 py-1 text-center text-slate-600">{stats?.short_count ?? 0}</td>
            <td className="px-2 py-1 text-center text-slate-600">
                {stats?.win_rate != null ? `${(stats.win_rate * 100).toFixed(1)}%` : '—'}
            </td>
            <td className="px-2 py-1 text-center text-slate-600">
                {stats?.mean_pnl != null ? `${stats.mean_pnl.toFixed(2)}%` : '—'}
            </td>
            <td className="px-2 py-1 text-center text-slate-600">
                {stats?.median_pnl != null ? `${stats.median_pnl.toFixed(2)}%` : '—'}
            </td>
        </tr>
    );
}

interface PredictionsTableProps {
    predictions: PredictionResult[];
    realtimePrices?: Map<string, RealtimePriceData>;
}

function PredictionsTable({ predictions, realtimePrices }: PredictionsTableProps) {
    return (
        <table className="w-full text-[11px]">
            <thead className="bg-slate-50 sticky top-0">
                <tr className="text-slate-500">
                    <th className="px-2 py-1 text-left font-medium">symbol</th>
                    <th className="px-2 py-1 text-left font-medium">time</th>
                    <th className="px-2 py-1 text-center font-medium">dir</th>
                    <th className="px-2 py-1 text-right font-medium">edge</th>
                    <th className="px-2 py-1 text-right font-medium">prob_up</th>
                    <th className="px-2 py-1 text-right font-medium">mean</th>
                    <th className="px-2 py-1 text-right font-medium">p10</th>
                    <th className="px-2 py-1 text-right font-medium">p90</th>
                    <th className="px-2 py-1 text-center font-medium">n</th>
                    <th className="px-2 py-1 text-right font-medium">dist1</th>
                    <th className="px-2 py-1 text-right font-medium">actual</th>
                </tr>
            </thead>
            <tbody>
                {predictions.length === 0 ? (
                    <tr>
                        <td colSpan={11} className="px-2 py-4 text-center text-slate-400">No data</td>
                    </tr>
                ) : (
                    predictions.map((p) => {
                        // Check for real-time price update
                        const rtPrice = realtimePrices?.get(p.id);
                        const displayReturn = p.actual_return ?? rtPrice?.unrealized_return ?? null;
                        const isRealtime = p.actual_return == null && rtPrice != null;
                        const isCorrect = p.was_correct ?? rtPrice?.is_currently_correct ?? null;

                        return (
                            <tr
                                key={p.id}
                                className={cn(
                                    "border-t border-slate-100 hover:bg-slate-50",
                                    isRealtime && "animate-pulse bg-blue-50/50"
                                )}
                            >
                                <td className="px-2 py-1 text-slate-800 font-medium">{p.symbol}</td>
                                <td className="px-2 py-1 text-slate-500">
                                    {new Date(p.scan_time).toLocaleDateString('en-CA')} {new Date(p.scan_time).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' })}
                                </td>
                                <td className={cn(
                                    "px-2 py-1 text-center font-medium",
                                    p.direction === 'UP' ? 'text-emerald-600' : 'text-red-600'
                                )}>
                                    {p.direction === 'UP' ? 'LONG' : 'SHORT'}
                                </td>
                                <td className="px-2 py-1 text-right text-slate-800 font-medium">{(p.edge * 100).toFixed(2)}%</td>
                                <td className="px-2 py-1 text-right text-slate-600">{(p.prob_up * 100).toFixed(1)}%</td>
                                <td className={cn(
                                    "px-2 py-1 text-right",
                                    p.mean_return >= 0 ? 'text-emerald-600' : 'text-red-600'
                                )}>
                                    {p.mean_return.toFixed(2)}%
                                </td>
                                <td className="px-2 py-1 text-right text-red-500">{p.p10?.toFixed(2) ?? '—'}%</td>
                                <td className="px-2 py-1 text-right text-emerald-500">{p.p90?.toFixed(2) ?? '—'}%</td>
                                <td className="px-2 py-1 text-center text-slate-600">{p.n_neighbors}</td>
                                <td className="px-2 py-1 text-right text-slate-500">{p.dist1?.toFixed(6) ?? '—'}</td>
                                <td className={cn(
                                    "px-2 py-1 text-right font-medium",
                                    displayReturn != null
                                        ? (displayReturn >= 0 ? 'text-emerald-600' : 'text-red-600')
                                        : 'text-slate-400',
                                    isRealtime && "relative"
                                )}>
                                    {displayReturn != null ? (
                                        <>
                                            {displayReturn.toFixed(2)}%
                                            {isRealtime && rtPrice && (
                                                <span className="ml-1 text-[9px] text-blue-500">
                                                    ({rtPrice.minutes_remaining.toFixed(0)}m)
                                                </span>
                                            )}
                                        </>
                                    ) : '—'}
                                </td>
                            </tr>
                        );
                    })
                )}
            </tbody>
        </table>
    );
}

export default PatternRealtimeContent;
