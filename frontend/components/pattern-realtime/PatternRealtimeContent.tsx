'use client';

/**
 * Pattern Real-Time Scanner
 * =========================
 * 
 * Batch scanning component for multiple symbols with real-time updates.
 * Displays predictions ranked by edge with performance tracking.
 * 
 * Features:
 * - Multi-symbol batch scanning
 * - Real-time WebSocket updates
 * - Performance statistics
 * - Configurable parameters
 * - Sorted results by edge
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import {
    Play,
    Pause,
    RefreshCw,
    Settings2,
    TrendingUp,
    TrendingDown,
    CheckCircle2,
    Clock,
    AlertCircle,
    Loader2,
    ChevronDown,
    ChevronUp,
    Wifi,
    WifiOff,
    BarChart3,
    Target,
    Percent,
    DollarSign,
    Filter,
    X,
} from 'lucide-react';
import { useFloatingWindow, useWindowState } from '@/contexts/FloatingWindowContext';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { usePatternRealtimeWS, PredictionResult, VerificationUpdate } from '@/hooks/usePatternRealtimeWS';
import { cn } from '@/lib/utils';

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
    progress: {
        completed: number;
        total: number;
        failed: number;
    };
    started_at: string;
    completed_at: string | null;
    duration_seconds: number | null;
    results: PredictionResult[];
    failures: Array<{ symbol: string; error_code: string; reason: string }>;
    params: Record<string, unknown>;
}

type SortField = 'edge' | 'symbol' | 'prob_up' | 'mean_return' | 'pnl';
type SortOrder = 'asc' | 'desc';
type DirectionFilter = 'all' | 'UP' | 'DOWN';

// Default symbol lists
const DEFAULT_SYMBOLS = [
    'AAPL', 'NVDA', 'TSLA', 'MSFT', 'GOOG', 'AMZN', 'META', 'AMD', 'INTC',
    'SPY', 'QQQ', 'IWM', 'NFLX', 'CRM', 'ORCL', 'ADBE', 'NOW', 'SHOP'
];

// ============================================================================
// Component
// ============================================================================

interface PatternRealtimeContentProps {
    initialSymbols?: string[];
}

export function PatternRealtimeContent({ initialSymbols }: PatternRealtimeContentProps) {
    const font = useUserPreferencesStore(selectFont);
    const { id: windowId } = useWindowState() || {};
    
    // ========================================================================
    // State
    // ========================================================================
    
    // Scan parameters
    const [symbols, setSymbols] = useState<string[]>(initialSymbols || DEFAULT_SYMBOLS);
    const [symbolInput, setSymbolInput] = useState(symbols.join(', '));
    const [k, setK] = useState(40);
    const [horizon, setHorizon] = useState(10);
    const [excludeSelf, setExcludeSelf] = useState(true);
    const [crossAsset, setCrossAsset] = useState(true);
    
    // UI state
    const [showSettings, setShowSettings] = useState(false);
    const [isScanning, setIsScanning] = useState(false);
    const [currentJobId, setCurrentJobId] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    
    // Results
    const [predictions, setPredictions] = useState<PredictionResult[]>([]);
    const [stats, setStats] = useState<PerformanceStats | null>(null);
    
    // Sorting & filtering
    const [sortField, setSortField] = useState<SortField>('edge');
    const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
    const [directionFilter, setDirectionFilter] = useState<DirectionFilter>('all');
    
    // Progress
    const [progress, setProgress] = useState({ completed: 0, total: 0 });
    
    // ========================================================================
    // WebSocket
    // ========================================================================
    
    const handleResult = useCallback((prediction: PredictionResult) => {
        setPredictions(prev => {
            // Update if exists, add if new
            const idx = prev.findIndex(p => p.id === prediction.id);
            if (idx >= 0) {
                const updated = [...prev];
                updated[idx] = prediction;
                return updated;
            }
            return [...prev, prediction];
        });
    }, []);
    
    const handleVerification = useCallback((update: VerificationUpdate) => {
        setPredictions(prev => 
            prev.map(p => 
                p.id === update.prediction_id
                    ? { 
                        ...p, 
                        actual_return: update.actual_return,
                        was_correct: update.was_correct,
                        pnl: update.pnl,
                        verified_at: new Date().toISOString(),
                    }
                    : p
            )
        );
        // Refresh stats after verification
        fetchStats();
    }, []);
    
    const handleJobComplete = useCallback((jobId: string, results: PredictionResult[]) => {
        if (jobId === currentJobId) {
            setIsScanning(false);
            setPredictions(results);
            fetchStats();
        }
    }, [currentJobId]);
    
    const handleProgress = useCallback((jobId: string, prog: { completed: number; total: number }) => {
        if (jobId === currentJobId) {
            setProgress(prog);
        }
    }, [currentJobId]);
    
    const handleWSError = useCallback((err: string) => {
        console.error('[PatternRealtime] WS Error:', err);
    }, []);
    
    const { isConnected, subscribe, reconnect } = usePatternRealtimeWS({
        onResult: handleResult,
        onVerification: handleVerification,
        onJobComplete: handleJobComplete,
        onProgress: handleProgress,
        onError: handleWSError,
    });
    
    // ========================================================================
    // API Calls
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
    
    const startScan = useCallback(async () => {
        setError(null);
        setIsScanning(true);
        setPredictions([]);
        setProgress({ completed: 0, total: symbols.length });
        
        try {
            const res = await fetch(`${API_BASE}/api/pattern-realtime/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symbols,
                    k,
                    horizon,
                    exclude_self: excludeSelf,
                    cross_asset: crossAsset,
                }),
            });
            
            if (!res.ok) {
                throw new Error(`HTTP ${res.status}`);
            }
            
            const data: JobResponse = await res.json();
            setCurrentJobId(data.job_id);
            subscribe(data.job_id);
            
            // Poll for results (backup to WebSocket)
            pollJobStatus(data.job_id);
            
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Failed to start scan');
            setIsScanning(false);
        }
    }, [symbols, k, horizon, excludeSelf, crossAsset, subscribe]);
    
    const pollJobStatus = useCallback(async (jobId: string) => {
        const poll = async () => {
            try {
                const res = await fetch(`${API_BASE}/api/pattern-realtime/job/${jobId}`);
                if (res.ok) {
                    const data: JobStatus = await res.json();
                    setProgress({
                        completed: data.progress.completed,
                        total: data.progress.total,
                    });
                    
                    if (data.status === 'completed' || data.status === 'failed') {
                        setIsScanning(false);
                        setPredictions(data.results);
                        fetchStats();
                        return;
                    }
                    
                    // Continue polling
                    setTimeout(poll, 1000);
                }
            } catch (e) {
                console.error('[PatternRealtime] Poll error:', e);
            }
        };
        
        // Start polling after a short delay
        setTimeout(poll, 500);
    }, [fetchStats]);
    
    // ========================================================================
    // Effects
    // ========================================================================
    
    // Fetch stats on mount
    useEffect(() => {
        fetchStats();
    }, [fetchStats]);
    
    // Parse symbol input
    const handleSymbolInputChange = useCallback((value: string) => {
        setSymbolInput(value);
        const parsed = value
            .split(/[,\s]+/)
            .map(s => s.trim().toUpperCase())
            .filter(s => s.length > 0 && s.length <= 5);
        if (parsed.length > 0) {
            setSymbols(parsed);
        }
    }, []);
    
    // ========================================================================
    // Sorting & Filtering
    // ========================================================================
    
    const sortedPredictions = useMemo(() => {
        let filtered = predictions;
        
        // Filter by direction
        if (directionFilter !== 'all') {
            filtered = filtered.filter(p => p.direction === directionFilter);
        }
        
        // Sort
        return [...filtered].sort((a, b) => {
            let aVal: number | string = 0;
            let bVal: number | string = 0;
            
            switch (sortField) {
                case 'edge':
                    aVal = a.edge;
                    bVal = b.edge;
                    break;
                case 'symbol':
                    aVal = a.symbol;
                    bVal = b.symbol;
                    break;
                case 'prob_up':
                    aVal = a.direction === 'UP' ? a.prob_up : a.prob_down;
                    bVal = b.direction === 'UP' ? b.prob_up : b.prob_down;
                    break;
                case 'mean_return':
                    aVal = a.mean_return;
                    bVal = b.mean_return;
                    break;
                case 'pnl':
                    aVal = a.pnl ?? 0;
                    bVal = b.pnl ?? 0;
                    break;
            }
            
            if (typeof aVal === 'string') {
                return sortOrder === 'asc' 
                    ? aVal.localeCompare(bVal as string)
                    : (bVal as string).localeCompare(aVal);
            }
            
            return sortOrder === 'asc' ? aVal - (bVal as number) : (bVal as number) - aVal;
        });
    }, [predictions, sortField, sortOrder, directionFilter]);
    
    const handleSort = useCallback((field: SortField) => {
        if (sortField === field) {
            setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
        } else {
            setSortField(field);
            setSortOrder('desc');
        }
    }, [sortField]);
    
    // ========================================================================
    // Render
    // ========================================================================
    
    const fontFamily = `var(--font-${font})`;
    
    return (
        <div 
            className="h-full flex flex-col bg-[#0a0a0f] text-gray-100 overflow-hidden"
            style={{ fontFamily }}
        >
            {/* Header */}
            <div className="flex-shrink-0 border-b border-gray-800/50 bg-gradient-to-r from-[#0a0a0f] to-[#12121a]">
                {/* Top row - Title & Connection */}
                <div className="flex items-center justify-between px-4 py-2.5">
                    <div className="flex items-center gap-3">
                        <div className="p-1.5 bg-gradient-to-br from-violet-500/20 to-fuchsia-500/20 rounded-lg">
                            <Target className="w-4 h-4 text-violet-400" />
                        </div>
                        <div>
                            <h2 className="text-sm font-semibold text-white tracking-tight">
                                Pattern Real-Time
                            </h2>
                            <p className="text-[10px] text-gray-500">
                                {symbols.length} symbols • {horizon}min horizon
                            </p>
                        </div>
                    </div>
                    
                    <div className="flex items-center gap-2">
                        {/* Connection status */}
                        <div className={cn(
                            "flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-medium",
                            isConnected 
                                ? "bg-emerald-500/10 text-emerald-400" 
                                : "bg-red-500/10 text-red-400"
                        )}>
                            {isConnected ? (
                                <><Wifi className="w-3 h-3" /> Live</>
                            ) : (
                                <><WifiOff className="w-3 h-3" /> Offline</>
                            )}
                        </div>
                        
                        {/* Settings toggle */}
                        <button
                            onClick={() => setShowSettings(!showSettings)}
                            className={cn(
                                "p-1.5 rounded transition-colors",
                                showSettings 
                                    ? "bg-violet-500/20 text-violet-400" 
                                    : "hover:bg-gray-800 text-gray-400"
                            )}
                        >
                            <Settings2 className="w-4 h-4" />
                        </button>
                    </div>
                </div>
                
                {/* Stats row */}
                {stats && (
                    <div className="flex items-center gap-4 px-4 py-2 border-t border-gray-800/30 bg-black/20">
                        <StatBadge
                            icon={<BarChart3 className="w-3 h-3" />}
                            label="Today"
                            value={stats.total_predictions}
                        />
                        <StatBadge
                            icon={<CheckCircle2 className="w-3 h-3" />}
                            label="Verified"
                            value={stats.verified}
                            color="emerald"
                        />
                        {stats.all_stats?.win_rate && (
                            <StatBadge
                                icon={<Percent className="w-3 h-3" />}
                                label="Win Rate"
                                value={`${(stats.all_stats.win_rate * 100).toFixed(1)}%`}
                                color={stats.all_stats.win_rate >= 0.5 ? 'emerald' : 'red'}
                            />
                        )}
                        {stats.top_10pct?.win_rate && (
                            <StatBadge
                                icon={<Target className="w-3 h-3" />}
                                label="Top 10%"
                                value={`${(stats.top_10pct.win_rate * 100).toFixed(1)}%`}
                                color="violet"
                            />
                        )}
                    </div>
                )}
                
                {/* Settings panel */}
                {showSettings && (
                    <div className="px-4 py-3 border-t border-gray-800/30 bg-black/30 space-y-3">
                        {/* Symbols input */}
                        <div>
                            <label className="text-[10px] text-gray-500 uppercase tracking-wider">
                                Symbols (comma separated)
                            </label>
                            <input
                                type="text"
                                value={symbolInput}
                                onChange={(e) => handleSymbolInputChange(e.target.value)}
                                className="w-full mt-1 px-3 py-2 bg-gray-900/50 border border-gray-700/50 rounded text-sm text-white placeholder-gray-600 focus:outline-none focus:border-violet-500/50"
                                placeholder="AAPL, NVDA, TSLA..."
                            />
                        </div>
                        
                        {/* Parameter sliders */}
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="text-[10px] text-gray-500 uppercase tracking-wider">
                                    Neighbors (k): {k}
                                </label>
                                <input
                                    type="range"
                                    min={10}
                                    max={100}
                                    step={5}
                                    value={k}
                                    onChange={(e) => setK(Number(e.target.value))}
                                    className="w-full mt-1 accent-violet-500"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 uppercase tracking-wider">
                                    Horizon: {horizon} min
                                </label>
                                <input
                                    type="range"
                                    min={5}
                                    max={60}
                                    step={5}
                                    value={horizon}
                                    onChange={(e) => setHorizon(Number(e.target.value))}
                                    className="w-full mt-1 accent-violet-500"
                                />
                            </div>
                        </div>
                        
                        {/* Toggles */}
                        <div className="flex items-center gap-4">
                            <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={crossAsset}
                                    onChange={(e) => setCrossAsset(e.target.checked)}
                                    className="accent-violet-500"
                                />
                                Cross-Asset
                            </label>
                            <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={excludeSelf}
                                    onChange={(e) => setExcludeSelf(e.target.checked)}
                                    className="accent-violet-500"
                                />
                                Exclude Self
                            </label>
                        </div>
                    </div>
                )}
                
                {/* Action row */}
                <div className="flex items-center justify-between px-4 py-2 border-t border-gray-800/30">
                    <div className="flex items-center gap-2">
                        {/* Scan button */}
                        <button
                            onClick={startScan}
                            disabled={isScanning || symbols.length === 0}
                            className={cn(
                                "flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-medium transition-all",
                                isScanning
                                    ? "bg-gray-700 text-gray-400 cursor-not-allowed"
                                    : "bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white hover:from-violet-500 hover:to-fuchsia-500 shadow-lg shadow-violet-500/20"
                            )}
                        >
                            {isScanning ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    Scanning... {progress.completed}/{progress.total}
                                </>
                            ) : (
                                <>
                                    <Play className="w-4 h-4" />
                                    Scan {symbols.length} Symbols
                                </>
                            )}
                        </button>
                        
                        {/* Refresh stats */}
                        <button
                            onClick={fetchStats}
                            className="p-1.5 text-gray-500 hover:text-gray-300 hover:bg-gray-800 rounded transition-colors"
                            title="Refresh stats"
                        >
                            <RefreshCw className="w-4 h-4" />
                        </button>
                    </div>
                    
                    {/* Filter */}
                    <div className="flex items-center gap-1">
                        <Filter className="w-3 h-3 text-gray-500" />
                        <select
                            value={directionFilter}
                            onChange={(e) => setDirectionFilter(e.target.value as DirectionFilter)}
                            className="bg-transparent text-xs text-gray-400 border-none focus:outline-none cursor-pointer"
                        >
                            <option value="all">All</option>
                            <option value="UP">Long</option>
                            <option value="DOWN">Short</option>
                        </select>
                    </div>
                </div>
            </div>
            
            {/* Error */}
            {error && (
                <div className="flex items-center gap-2 px-4 py-2 bg-red-500/10 border-b border-red-500/20 text-red-400 text-sm">
                    <AlertCircle className="w-4 h-4" />
                    {error}
                    <button 
                        onClick={() => setError(null)}
                        className="ml-auto hover:text-red-300"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
            )}
            
            {/* Table */}
            <div className="flex-1 overflow-auto">
                <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-[#0a0a0f]/95 backdrop-blur-sm">
                        <tr className="border-b border-gray-800/50">
                            <SortableHeader 
                                field="symbol" 
                                currentField={sortField}
                                order={sortOrder}
                                onSort={handleSort}
                            >
                                Symbol
                            </SortableHeader>
                            <th className="px-3 py-2 text-left text-gray-500 font-medium">Dir</th>
                            <SortableHeader 
                                field="edge" 
                                currentField={sortField}
                                order={sortOrder}
                                onSort={handleSort}
                            >
                                Edge
                            </SortableHeader>
                            <SortableHeader 
                                field="prob_up" 
                                currentField={sortField}
                                order={sortOrder}
                                onSort={handleSort}
                            >
                                Prob%
                            </SortableHeader>
                            <SortableHeader 
                                field="mean_return" 
                                currentField={sortField}
                                order={sortOrder}
                                onSort={handleSort}
                            >
                                Mean%
                            </SortableHeader>
                            <th className="px-3 py-2 text-left text-gray-500 font-medium">P10/P90</th>
                            <th className="px-3 py-2 text-right text-gray-500 font-medium">Price</th>
                            <th className="px-3 py-2 text-center text-gray-500 font-medium">Status</th>
                            <SortableHeader 
                                field="pnl" 
                                currentField={sortField}
                                order={sortOrder}
                                onSort={handleSort}
                                align="right"
                            >
                                PnL
                            </SortableHeader>
                        </tr>
                    </thead>
                    <tbody>
                        {sortedPredictions.length === 0 ? (
                            <tr>
                                <td colSpan={9} className="text-center py-12 text-gray-500">
                                    {isScanning ? (
                                        <div className="flex flex-col items-center gap-2">
                                            <Loader2 className="w-6 h-6 animate-spin text-violet-400" />
                                            <span>Scanning patterns...</span>
                                        </div>
                                    ) : (
                                        <div className="flex flex-col items-center gap-2">
                                            <Target className="w-6 h-6 text-gray-600" />
                                            <span>No predictions yet</span>
                                            <span className="text-gray-600">Click Scan to start</span>
                                        </div>
                                    )}
                                </td>
                            </tr>
                        ) : (
                            sortedPredictions.map((pred, idx) => (
                                <PredictionRow 
                                    key={pred.id} 
                                    prediction={pred} 
                                    isEven={idx % 2 === 0}
                                />
                            ))
                        )}
                    </tbody>
                </table>
            </div>
            
            {/* Footer */}
            <div className="flex-shrink-0 px-4 py-2 border-t border-gray-800/50 bg-black/30 flex items-center justify-between text-[10px] text-gray-500">
                <span>
                    {sortedPredictions.length} predictions
                    {directionFilter !== 'all' && ` (${directionFilter})`}
                </span>
                <span>
                    k={k} • h={horizon}min • {crossAsset ? 'Cross' : 'Same'}-Asset
                </span>
            </div>
        </div>
    );
}

// ============================================================================
// Sub-components
// ============================================================================

function StatBadge({ 
    icon, 
    label, 
    value, 
    color = 'gray' 
}: { 
    icon: React.ReactNode; 
    label: string; 
    value: string | number;
    color?: 'gray' | 'emerald' | 'red' | 'violet';
}) {
    const colorClasses = {
        gray: 'text-gray-400',
        emerald: 'text-emerald-400',
        red: 'text-red-400',
        violet: 'text-violet-400',
    };
    
    return (
        <div className="flex items-center gap-1.5">
            <span className="text-gray-500">{icon}</span>
            <span className="text-[10px] text-gray-500">{label}:</span>
            <span className={cn("text-xs font-medium", colorClasses[color])}>
                {value}
            </span>
        </div>
    );
}

function SortableHeader({ 
    field, 
    currentField, 
    order, 
    onSort, 
    children,
    align = 'left'
}: { 
    field: SortField;
    currentField: SortField;
    order: SortOrder;
    onSort: (field: SortField) => void;
    children: React.ReactNode;
    align?: 'left' | 'right';
}) {
    const isActive = field === currentField;
    
    return (
        <th 
            className={cn(
                "px-3 py-2 font-medium cursor-pointer hover:bg-gray-800/30 transition-colors",
                align === 'right' ? 'text-right' : 'text-left',
                isActive ? 'text-violet-400' : 'text-gray-500'
            )}
            onClick={() => onSort(field)}
        >
            <div className={cn(
                "flex items-center gap-1",
                align === 'right' && 'justify-end'
            )}>
                {children}
                {isActive && (
                    order === 'desc' 
                        ? <ChevronDown className="w-3 h-3" />
                        : <ChevronUp className="w-3 h-3" />
                )}
            </div>
        </th>
    );
}

function PredictionRow({ 
    prediction: p, 
    isEven 
}: { 
    prediction: PredictionResult;
    isEven: boolean;
}) {
    const isVerified = p.verified_at !== null;
    const isCorrect = p.was_correct;
    const prob = p.direction === 'UP' ? p.prob_up : p.prob_down;
    
    return (
        <tr className={cn(
            "border-b border-gray-800/30 hover:bg-gray-800/20 transition-colors",
            isEven ? 'bg-black/20' : 'bg-transparent'
        )}>
            {/* Symbol */}
            <td className="px-3 py-2">
                <span className="font-mono font-medium text-white">{p.symbol}</span>
            </td>
            
            {/* Direction */}
            <td className="px-3 py-2">
                <div className={cn(
                    "flex items-center gap-1 text-[10px] font-semibold",
                    p.direction === 'UP' ? 'text-emerald-400' : 'text-red-400'
                )}>
                    {p.direction === 'UP' ? (
                        <TrendingUp className="w-3 h-3" />
                    ) : (
                        <TrendingDown className="w-3 h-3" />
                    )}
                    {p.direction}
                </div>
            </td>
            
            {/* Edge */}
            <td className="px-3 py-2">
                <span className={cn(
                    "font-mono font-medium",
                    p.edge >= 0.1 ? 'text-violet-400' : 
                    p.edge >= 0.05 ? 'text-violet-300' : 'text-gray-400'
                )}>
                    {(p.edge * 100).toFixed(2)}
                </span>
            </td>
            
            {/* Probability */}
            <td className="px-3 py-2">
                <div className="flex items-center gap-1">
                    <div 
                        className="h-1.5 rounded-full bg-gray-700"
                        style={{ width: '40px' }}
                    >
                        <div 
                            className={cn(
                                "h-full rounded-full",
                                prob >= 0.6 ? 'bg-emerald-500' :
                                prob >= 0.5 ? 'bg-yellow-500' : 'bg-red-500'
                            )}
                            style={{ width: `${prob * 100}%` }}
                        />
                    </div>
                    <span className="font-mono text-gray-300">
                        {(prob * 100).toFixed(0)}%
                    </span>
                </div>
            </td>
            
            {/* Mean Return */}
            <td className="px-3 py-2">
                <span className={cn(
                    "font-mono",
                    p.mean_return >= 0 ? 'text-emerald-400' : 'text-red-400'
                )}>
                    {p.mean_return >= 0 ? '+' : ''}{p.mean_return.toFixed(2)}%
                </span>
            </td>
            
            {/* P10/P90 */}
            <td className="px-3 py-2">
                <span className="font-mono text-gray-500 text-[10px]">
                    {p.p10?.toFixed(1) ?? '-'} / {p.p90?.toFixed(1) ?? '-'}
                </span>
            </td>
            
            {/* Price */}
            <td className="px-3 py-2 text-right">
                <span className="font-mono text-gray-300">
                    ${p.price_at_scan.toFixed(2)}
                </span>
            </td>
            
            {/* Status */}
            <td className="px-3 py-2 text-center">
                {isVerified ? (
                    <span className={cn(
                        "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium",
                        isCorrect 
                            ? 'bg-emerald-500/10 text-emerald-400' 
                            : 'bg-red-500/10 text-red-400'
                    )}>
                        {isCorrect ? (
                            <><CheckCircle2 className="w-3 h-3" /> Win</>
                        ) : (
                            <><X className="w-3 h-3" /> Loss</>
                        )}
                    </span>
                ) : (
                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-gray-700/30 text-gray-500 text-[10px]">
                        <Clock className="w-3 h-3" /> Pending
                    </span>
                )}
            </td>
            
            {/* PnL */}
            <td className="px-3 py-2 text-right">
                {p.pnl !== null ? (
                    <span className={cn(
                        "font-mono font-medium",
                        p.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'
                    )}>
                        {p.pnl >= 0 ? '+' : ''}{p.pnl.toFixed(2)}%
                    </span>
                ) : (
                    <span className="text-gray-600">—</span>
                )}
            </td>
        </tr>
    );
}

export default PatternRealtimeContent;

