'use client';

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import React from 'react';
import { useTranslation } from 'react-i18next';
import { TableVirtuoso } from 'react-virtuoso';
import {
    FileText,
    RefreshCw,
    AlertTriangle,
    ExternalLink,
    SlidersHorizontal,
    X,
    Zap
} from "lucide-react";
import { TickerSearch } from '@/components/common/TickerSearch';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { useWindowState } from '@/contexts/FloatingWindowContext';
import { SECFilingsFilterPanel, type SECFilters } from './SECFilingsFilterPanel';

interface SECFilingsWindowState {
    ticker?: string;
    [key: string]: unknown;
}
import { getUserTimezone } from '@/lib/date-utils';
import { 
    FILING_CATEGORIES, 
    FORM_TYPE_INFO, 
    QUICK_FILTERS,
    getFormTypeColor, 
    get8KItemImportance,
    format8KItems,
    getQuickFilterTypes,
} from '@/lib/sec-filing-types';

const FONT_CLASSES: Record<string, string> = {
  'oxygen-mono': 'font-oxygen-mono',
  'ibm-plex-mono': 'font-ibm-plex-mono', 
  'jetbrains-mono': 'font-jetbrains-mono',
  'fira-code': 'font-fira-code',
};

type DocumentFile = {
    sequence: string;
    documentUrl: string;
    description?: string;
    type: string;
    size?: string;
};

type SECFiling = {
    id: string;
    ticker: string | null;
    formType: string;
    filedAt: string;
    companyName: string | null;
    description: string | null;
    linkToFilingDetails: string | null;
    linkToHtml: string | null;
    linkToTxt: string | null;
    accessionNo: string;
    cik: string;
    items?: string[] | null;
    documentFormatFiles?: DocumentFile[];
};

type FilingsResponse = {
    total: number;
    filings: SECFiling[];
};

interface SECFilingsContentProps {
    initialTicker?: string;
}

const DEFAULT_FILTERS: SECFilters = {
    ticker: '',
    categories: [],
    formTypes: [],
    items8K: [],
    dateFrom: '',
    dateTo: '',
    importanceLevel: 'all',
};

export function SECFilingsContent({ initialTicker }: SECFilingsContentProps = {}) {
    const { t } = useTranslation();
    const font = useUserPreferencesStore(selectFont);
    const fontClass = FONT_CLASSES[font] || 'font-jetbrains-mono';
    const { state: windowState, updateState: updateWindowState } = useWindowState<SECFilingsWindowState>();
    
    // Use persisted ticker
    const savedTicker = windowState.ticker || initialTicker || '';
    
    // State
    const [historicalFilings, setHistoricalFilings] = useState<SECFiling[]>([]);
    const [realtimeFilings, setRealtimeFilings] = useState<SECFiling[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [inputValue, setInputValue] = useState(savedTicker);
    const [currentPage, setCurrentPage] = useState(1);
    const [totalResults, setTotalResults] = useState(0);
    const [selectedFiling, setSelectedFiling] = useState<SECFiling | null>(null);
    const [showFilterPanel, setShowFilterPanel] = useState(false);
    const [filters, setFilters] = useState<SECFilters>({ ...DEFAULT_FILTERS, ticker: savedTicker });
    
    // Track if auto-load from restored state has been done
    const autoLoadedRef = useRef(false);
    
    // Persist ticker changes (including when cleared)
    useEffect(() => {
        // Always persist to ensure clearing ticker also clears persisted state
        updateWindowState({ ticker: filters.ticker || '' });
    }, [filters.ticker, updateWindowState]);
    
    // Auto-load when windowState becomes available (after Zustand hydration)
    useEffect(() => {
        if (!autoLoadedRef.current && windowState.ticker && windowState.ticker !== filters.ticker) {
            autoLoadedRef.current = true;
            setInputValue(windowState.ticker);
            setFilters(prev => ({ ...prev, ticker: windowState.ticker! }));
            // fetchFilings will be triggered by the filters change effect
        }
    }, [windowState.ticker]);
    
    const PAGE_SIZE = 100;

    // WebSocket
    const ws = useWebSocket();
    const seenAccessions = useRef<Set<string>>(new Set());
    const realtimeAccessions = useRef<Set<string>>(new Set());

    // Get all form types to filter (from categories + direct selection)
    const getFilterFormTypes = useCallback((currentFilters: SECFilters): string[] => {
        const types: string[] = [];
        
        currentFilters.categories.forEach(catKey => {
            const cat = FILING_CATEGORIES[catKey as keyof typeof FILING_CATEGORIES];
            if (cat) types.push(...cat.types);
        });
        
        types.push(...currentFilters.formTypes);
        
        return [...new Set(types)];
    }, []);

    // Fetch filings - ALL filters sent to backend for server-side filtering
    const fetchFilings = useCallback(async (page: number = 1, tickerOverride?: string, filtersOverride?: SECFilters) => {
        setLoading(true);
        setError(null);
        
        // Use passed filters or current state
        const currentFilters = filtersOverride || filters;

        try {
            const params = new URLSearchParams();
            const ticker = tickerOverride ?? currentFilters.ticker;
            if (ticker.trim()) params.append('ticker', ticker.trim().toUpperCase());
            
            // Form types - combine categories and direct selections
            const formTypes = getFilterFormTypes(currentFilters);
            if (formTypes.length > 0) {
                params.append('form_types', formTypes.join(','));
            }
            
            // 8-K Items filter (server-side)
            if (currentFilters.items8K.length > 0) {
                params.append('items', currentFilters.items8K.join(','));
            }
            
            if (currentFilters.dateFrom) params.append('date_from', currentFilters.dateFrom);
            if (currentFilters.dateTo) params.append('date_to', currentFilters.dateTo);
            params.append('page_size', PAGE_SIZE.toString());
            params.append('from_index', ((page - 1) * PAGE_SIZE).toString());

            
            const secFilingsUrl = process.env.NEXT_PUBLIC_SEC_FILINGS_URL || 'http://localhost:8012';
            const response = await fetch(`${secFilingsUrl}/api/v1/filings/live?${params}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data: FilingsResponse = await response.json();
            setHistoricalFilings(data.filings);
            setTotalResults(data.total);
            setCurrentPage(page);
            data.filings.forEach(f => seenAccessions.current.add(f.accessionNo));
        } catch (err) {
            console.error('Error fetching filings:', err);
            setError(err instanceof Error ? err.message : 'Error loading filings');
            setHistoricalFilings([]);
            setTotalResults(0);
        } finally {
            setLoading(false);
        }
    }, [filters, getFilterFormTypes]);

    // WebSocket: Real-time filings
    useEffect(() => {
        if (!ws.isConnected) return;

        ws.send({ action: 'subscribe_sec_filings' });

        const subscription = ws.messages$.subscribe((message: any) => {
            if (message.type === 'sec_filing' && message.filing) {
                const newFiling = message.filing;

                if (!seenAccessions.current.has(newFiling.accessionNo)) {
                    seenAccessions.current.add(newFiling.accessionNo);
                    realtimeAccessions.current.add(newFiling.accessionNo);
                    setRealtimeFilings(prev => [newFiling, ...prev].slice(0, 50));
                    // Highlight new filing
                    setHighlightedAccessions(prev => new Set([...prev, newFiling.accessionNo]));
                }
            }
        });

        return () => {
            subscription.unsubscribe();
            ws.send({ action: 'unsubscribe_sec_filings' });
        };
    }, [ws.isConnected, ws.messages$, ws]);

    // Initial load
    useEffect(() => {
        fetchFilings(1);
    }, []);

    // Refetch when filters change (debounced) - triggered by useEffect watching filter values
    const prevFiltersRef = useRef<string>('');
    useEffect(() => {
        // Serialize filters to detect changes
        const filterKey = JSON.stringify({
            categories: filters.categories,
            formTypes: filters.formTypes,
            items8K: filters.items8K,
            dateFrom: filters.dateFrom,
            dateTo: filters.dateTo,
        });
        
        // Skip if filters haven't changed
        if (prevFiltersRef.current === filterKey) return;
        
        // Skip initial empty state
        if (prevFiltersRef.current === '') {
            prevFiltersRef.current = filterKey;
            return;
        }
        
        prevFiltersRef.current = filterKey;
        
        // Debounce filter changes
        const timer = setTimeout(() => {
            fetchFilings(1, undefined, filters);
        }, 300);
        
        return () => clearTimeout(timer);
    }, [filters, fetchFilings]);

    // Track new filings - brief highlight then normal
    const [highlightedAccessions, setHighlightedAccessions] = useState<Set<string>>(new Set());
    
    // Clear highlights after 2 seconds (brief flash, not distracting)
    useEffect(() => {
        if (highlightedAccessions.size === 0) return;
        const timer = setTimeout(() => {
            setHighlightedAccessions(new Set());
        }, 2000);
        return () => clearTimeout(timer);
    }, [highlightedAccessions]);

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        setFilters(prev => ({ ...prev, ticker: inputValue }));
        fetchFilings(1, inputValue);
    };

    const handleApplyFilters = useCallback((filtersToApply?: SECFilters) => {
        // All filters sent to backend - server-side filtering
        // Pass the filters directly to avoid closure issues
        fetchFilings(1, undefined, filtersToApply || filters);
    }, [fetchFilings, filters]);

    const handleResetFilters = useCallback(() => {
        setFilters(DEFAULT_FILTERS);
        setInputValue('');
        // Clear realtime and reload
        setRealtimeFilings([]);
        seenAccessions.current.clear();
        realtimeAccessions.current.clear();
        // Fetch without filters - direct call
        setLoading(true);
        const params = new URLSearchParams();
        params.append('page_size', PAGE_SIZE.toString());
        params.append('from_index', '0');
        const secFilingsUrl = process.env.NEXT_PUBLIC_SEC_FILINGS_URL || 'http://localhost:8012';
        fetch(`${secFilingsUrl}/api/v1/filings/live?${params}`)
            .then(r => r.json())
            .then((data: FilingsResponse) => {
                setHistoricalFilings(data.filings);
                setTotalResults(data.total);
                setCurrentPage(1);
                data.filings.forEach(f => seenAccessions.current.add(f.accessionNo));
            })
            .finally(() => setLoading(false));
    }, []);

    const clearAllFilters = () => {
        handleResetFilters();
        setShowFilterPanel(false);
    };

    // Check if we have active filters
    const hasFormTypeFilters = filters.categories.length > 0 || filters.formTypes.length > 0;
    const hasItemFilters = filters.items8K.length > 0;
    const hasImportanceFilter = filters.importanceLevel !== 'all';

    // Count active filters
    const activeFiltersCount = useMemo(() => {
        return filters.categories.length + 
               filters.formTypes.length + 
               filters.items8K.length + 
               (filters.dateFrom ? 1 : 0) + 
               (filters.dateTo ? 1 : 0) +
               (filters.importanceLevel !== 'all' ? 1 : 0);
    }, [filters]);

    const hasActiveFilters = filters.ticker || activeFiltersCount > 0;

    // Filter realtime filings to match current filters (client-side for WebSocket data)
    const matchesRealtimeFilters = useCallback((filing: SECFiling): boolean => {
        // Ticker filter
        if (filters.ticker && filing.ticker !== filters.ticker.toUpperCase()) {
            return false;
        }

        // Form type filter
        if (hasFormTypeFilters) {
            const allowedTypes = getFilterFormTypes(filters);
            const matches = allowedTypes.some(t => 
                filing.formType === t || filing.formType.startsWith(t + '/')
            );
            if (!matches) return false;
        }

        // 8-K items filter - if filtering by 8-K items, ONLY show 8-K with those items
        if (hasItemFilters) {
            // Must be an 8-K to pass this filter
            if (!filing.formType.startsWith('8-K')) {
                return false;
            }
            // Must have at least one of the selected items
            const filingItems = format8KItems(filing.items ?? null).split(', ').filter(Boolean);
            const hasMatchingItem = filters.items8K.some(item => filingItems.includes(item));
            if (!hasMatchingItem) return false;
        }

        // Importance level filter - if set, ONLY show 8-K with sufficient importance
        if (hasImportanceFilter) {
            // Must be an 8-K to pass this filter
            if (!filing.formType.startsWith('8-K')) {
                return false;
            }
            const importance = get8KItemImportance(filing.items ?? null);
            const levels: Record<string, number> = { critical: 3, high: 2, medium: 1, low: 0 };
            const requiredLevel = levels[filters.importanceLevel] || 0;
            const filingLevel = importance ? levels[importance] : 0;
            if (filingLevel < requiredLevel) return false;
        }

        return true;
    }, [filters, hasFormTypeFilters, hasItemFilters, hasImportanceFilter, getFilterFormTypes]);

    // Merge historical (server-filtered) + realtime (client-filtered) filings
    const displayedFilings = useMemo(() => {
        const filingMap = new Map<string, SECFiling>();

        // Historical filings - already filtered by server
        historicalFilings.forEach(f => {
            if (f.accessionNo && !filingMap.has(f.accessionNo)) {
                filingMap.set(f.accessionNo, f);
            }
        });

        // Realtime filings - filter client-side to match current filters
        realtimeFilings.forEach(f => {
            if (f.accessionNo && !filingMap.has(f.accessionNo) && matchesRealtimeFilters(f)) {
                filingMap.set(f.accessionNo, f);
            }
        });

        const result = Array.from(filingMap.values());
        result.sort((a, b) => new Date(b.filedAt).getTime() - new Date(a.filedAt).getTime());

        return result;
    }, [realtimeFilings, historicalFilings, matchesRealtimeFilters]);

    // Format dates in Eastern Time (ET) - standard for US markets
    const formatDateTime = (isoString: string) => {
        try {
            const d = new Date(isoString);
            return {
                date: d.toLocaleDateString('en-US', { timeZone: getUserTimezone(), year: 'numeric', month: '2-digit', day: '2-digit' }),
                time: d.toLocaleTimeString('en-US', { timeZone: getUserTimezone(), hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
            };
        } catch {
            return { date: '—', time: '—' };
        }
    };

    const truncateDescription = (desc: string | null, maxLength: number = 80) => {
        if (!desc) return '';
        if (desc.length <= maxLength) return desc;
        return desc.substring(0, maxLength) + '...';
    };

    const handleFilingClick = (filing: SECFiling) => {
        const hasViewableDoc = filing.documentFormatFiles && filing.documentFormatFiles.length > 0;

        if (hasViewableDoc) {
            const mainDoc = filing.documentFormatFiles?.find(doc =>
                doc.type === filing.formType ||
                doc.description?.toLowerCase().includes(filing.formType.toLowerCase())
            );

            const viewableDoc = mainDoc || filing.documentFormatFiles?.find(doc =>
                doc.documentUrl.endsWith('.htm') ||
                doc.documentUrl.endsWith('.html') ||
                doc.documentUrl.endsWith('.xml')
            );

            if (viewableDoc) {
                setSelectedFiling(filing);
                return;
            }
        }

        const url = filing.linkToHtml || filing.linkToFilingDetails || filing.linkToTxt;
        if (url) window.open(url, '_blank');
    };

    // Get direct URL (bypass iXBRL viewer)
    const getDirectUrl = (url: string | undefined): string | null => {
        if (!url) return null;
        if (url.includes('/ix?doc=')) {
            const match = url.match(/\/ix\?doc=([^&]+)/);
            if (match) return `https://www.sec.gov${match[1]}`;
        }
        return url;
    };

    // Color classes for form type badges
    const colorClasses: Record<string, string> = {
        blue: 'bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/30',
        purple: 'bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/30',
        amber: 'bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30',
        emerald: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30',
        cyan: 'bg-cyan-500/10 text-cyan-700 dark:text-cyan-400 border-cyan-500/30',
        rose: 'bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-500/30',
        orange: 'bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-500/30',
        slate: 'bg-surface-hover text-foreground/80 border-border',
    };

    // Importance colors for 8-K items
    const importanceColors: Record<string, string> = {
        critical: 'text-red-600 dark:text-red-400',
        high: 'text-amber-600 dark:text-amber-400',
        medium: 'text-muted-fg',
        low: 'text-muted-fg',
    };

    // Filing viewer
    if (selectedFiling) {
        const mainDoc = selectedFiling.documentFormatFiles?.find(doc =>
            doc.type === selectedFiling.formType ||
            doc.description?.toLowerCase().includes(selectedFiling.formType.toLowerCase())
        );

        const viewableDoc = mainDoc || selectedFiling.documentFormatFiles?.find(doc =>
            doc.documentUrl.endsWith('.htm') ||
            doc.documentUrl.endsWith('.html') ||
            doc.documentUrl.endsWith('.xml')
        );

        const filingUrl = selectedFiling.linkToFilingDetails || 
                         getDirectUrl(viewableDoc?.documentUrl) || 
                         selectedFiling.linkToHtml;

        const secApiUrl = process.env.NEXT_PUBLIC_SEC_FILINGS_URL || 'http://localhost:8012';
        const proxyUrl = filingUrl
            ? `${secApiUrl}/api/v1/proxy?url=${encodeURIComponent(filingUrl)}`
            : '';

        return (
            <div className={`h-full flex flex-col bg-surface ${fontClass}`}>
                <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-surface-hover">
                    <button
                        onClick={() => setSelectedFiling(null)}
                        className="px-2 py-1 text-[10px] font-medium text-primary hover:text-primary-hover hover:bg-primary/10 rounded transition-colors"
                    >
                        Back
                    </button>
                    <div className="text-[11px] text-foreground/80 flex items-center gap-2">
                        <span className="font-semibold text-foreground">{selectedFiling.ticker || 'N/A'}</span>
                        <span className="text-muted-fg/50">|</span>
                        <span>{selectedFiling.formType}</span>
                        <span className="text-muted-fg/50">|</span>
                        <span className="text-muted-fg">{formatDateTime(selectedFiling.filedAt).date}</span>
                    </div>
                    <a
                        href={filingUrl || '#'}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium text-primary hover:text-primary-hover hover:bg-primary/10 rounded transition-colors"
                    >
                        <ExternalLink className="w-3 h-3" />
                        Original
                    </a>
                </div>

                <div className="flex-1 bg-surface">
                    <iframe
                        src={proxyUrl}
                        className="w-full h-full border-0"
                        sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
                        title={`${selectedFiling.formType} - ${selectedFiling.ticker || 'N/A'}`}
                    />
                </div>
            </div>
        );
    }

    return (
        <div className={`h-full flex flex-col bg-surface relative ${fontClass}`}>
            {/* Filter Panel Overlay */}
            <SECFilingsFilterPanel
                isOpen={showFilterPanel}
                onClose={() => setShowFilterPanel(false)}
                filters={filters}
                onFiltersChange={setFilters}
                onApply={handleApplyFilters}
                onReset={handleResetFilters}
            />

            {/* Header Row 1: Search, Dates, Count */}
            <div className="flex items-center gap-2 px-3 py-1 border-b border-border-subtle bg-surface-hover">
                {/* Ticker Search */}
                <form onSubmit={handleSearch} className="flex items-center gap-1">
                    <TickerSearch
                        value={inputValue}
                        onChange={setInputValue}
                        onSelect={(ticker) => {
                            setInputValue(ticker.symbol);
                            setFilters(prev => ({ ...prev, ticker: ticker.symbol }));
                            fetchFilings(1, ticker.symbol);
                        }}
                        placeholder="Ticker"
                        className="w-20"
                    />
                    <button
                        type="submit"
                        disabled={loading}
                        className="px-2 py-0.5 text-[10px] font-medium bg-primary text-white rounded hover:bg-primary-hover disabled:opacity-50"
                    >
                        {loading ? <RefreshCw className="w-3 h-3 animate-spin" /> : 'Go'}
                    </button>
                </form>

                <span className="text-muted-fg/50">|</span>

                {/* Date Range */}
                <div className="flex items-center gap-1 text-[10px]">
                    <input
                        type="date"
                        value={filters.dateFrom}
                        onChange={(e) => {
                            const newFilters = { ...filters, dateFrom: e.target.value };
                            setFilters(newFilters);
                            fetchFilings(1, undefined, newFilters);
                        }}
                        className="w-[100px] px-1 py-0.5 text-[10px] border border-border rounded focus:outline-none focus:border-primary bg-[var(--color-input-bg)]"
                    />
                    <span className="text-muted-fg/50">-</span>
                    <input
                        type="date"
                        value={filters.dateTo}
                        onChange={(e) => {
                            const newFilters = { ...filters, dateTo: e.target.value };
                            setFilters(newFilters);
                            fetchFilings(1, undefined, newFilters);
                        }}
                        className="w-[100px] px-1 py-0.5 text-[10px] border border-border rounded focus:outline-none focus:border-primary bg-[var(--color-input-bg)]"
                    />
                    {(filters.dateFrom || filters.dateTo) && (
                        <button
                            onClick={() => {
                                const newFilters = { ...filters, dateFrom: '', dateTo: '' };
                                setFilters(newFilters);
                                fetchFilings(1, undefined, newFilters);
                            }}
                            className="p-0.5 text-muted-fg hover:text-foreground/80"
                        >
                            <X className="w-3 h-3" />
                        </button>
                    )}
                </div>

                <div className="flex-1" />

                {/* Count & Live indicator */}
                <div className="flex items-center gap-2 text-[10px] text-muted-fg">
                    <span className="tabular-nums font-medium">{displayedFilings.length}</span>
                    {realtimeFilings.length > 0 && (
                        <span className="text-emerald-600 flex items-center gap-1">
                            <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full" />
                            {realtimeFilings.filter(f => matchesRealtimeFilters(f)).length}
                        </span>
                    )}
                </div>

                {hasActiveFilters && (
                    <button
                        onClick={clearAllFilters}
                        className="px-1.5 py-0.5 text-[9px] text-muted-fg hover:text-foreground border border-border rounded"
                    >
                        Clear
                    </button>
                )}
            </div>

            {/* Header Row 2: Quick Filters */}
            <div className="flex items-center gap-1 px-3 py-1 border-b border-border bg-surface">
                {Object.entries(QUICK_FILTERS).map(([key, qf]) => {
                    // Cast to string[] for comparison
                    const qfCategories = qf.categories as readonly string[];
                    const qfItems = qf.items8K as readonly string[];
                    
                    // Check if this quick filter is active
                    const isActive = qfCategories.length > 0 
                        ? qfCategories.every(cat => filters.categories.includes(cat))
                        : qfItems.length > 0 
                            ? qfItems.every(item => filters.items8K.includes(item))
                            : false;
                    
                    return (
                        <button
                            key={key}
                            onClick={() => {
                                if (isActive) {
                                    // Deactivate: remove categories and items
                                    const newFilters = {
                                        ...filters,
                                        categories: filters.categories.filter(c => !qfCategories.includes(c)),
                                        items8K: filters.items8K.filter(i => !qfItems.includes(i)),
                                    };
                                    setFilters(newFilters);
                                    fetchFilings(1, undefined, newFilters);
                                } else {
                                    // Activate: add categories and items (replace, not add)
                                    const newFilters = {
                                        ...DEFAULT_FILTERS,
                                        ticker: filters.ticker,
                                        dateFrom: filters.dateFrom,
                                        dateTo: filters.dateTo,
                                        categories: [...qfCategories],
                                        items8K: [...qfItems],
                                    };
                                    setFilters(newFilters);
                                    fetchFilings(1, undefined, newFilters);
                                }
                            }}
                            title={qf.description}
                            className={`px-2 py-0.5 text-[10px] rounded border ${
                                isActive
                                    ? 'bg-primary text-white border-primary'
                                    : 'text-foreground/80 border-border hover:border-border'
                            }`}
                        >
                            {qf.label}
                        </button>
                    );
                })}

                <div className="flex-1" />

                {/* Advanced Filters Button */}
                <button
                    onClick={() => setShowFilterPanel(true)}
                    className={`flex items-center gap-1 px-2 py-0.5 text-[10px] rounded border ${
                        activeFiltersCount > 0
                            ? 'text-primary border-primary/50'
                            : 'text-muted-fg border-border hover:border-border'
                    }`}
                >
                    <SlidersHorizontal className="w-3 h-3" />
                    More
                    {activeFiltersCount > 0 && (
                        <span className="text-[9px] text-primary">({activeFiltersCount})</span>
                    )}
                </button>
            </div>

            {/* Active filters summary (if any advanced filters) */}
            {(filters.formTypes.length > 0 || filters.items8K.length > 0) && (
                <div className="flex items-center gap-1 px-3 py-0.5 border-b border-border-subtle bg-surface-hover/50 text-[9px] text-muted-fg">
                    <span>Active:</span>
                    {filters.formTypes.slice(0, 5).map(ft => (
                        <span key={ft} className="px-1 py-0.5 bg-surface-inset rounded">{ft}</span>
                    ))}
                    {filters.formTypes.length > 5 && <span>+{filters.formTypes.length - 5}</span>}
                    {filters.items8K.length > 0 && (
                        <span className="px-1 py-0.5 bg-surface-inset rounded">8-K: {filters.items8K.join(', ')}</span>
                    )}
                </div>
            )}

            {/* Error */}
            {error && (
                <div className="mx-3 mt-2 px-2 py-1.5 bg-red-500/10 border border-red-500/30 rounded flex items-center gap-2 text-red-700 dark:text-red-400">
                    <AlertTriangle className="w-3 h-3" />
                    <span className="text-[10px]">{error}</span>
                </div>
            )}

            {/* Virtualized Table */}
            <div className="flex-1">
                {loading && displayedFilings.length === 0 ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="text-center">
                            <RefreshCw className="w-5 h-5 mx-auto mb-2 text-blue-500 animate-spin" />
                            <p className="text-[10px] text-muted-fg">Loading filings...</p>
                        </div>
                    </div>
                ) : displayedFilings.length === 0 ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="text-center">
                            <FileText className="w-6 h-6 mx-auto mb-2 text-muted-fg/50" />
                            <p className="text-[10px] text-muted-fg">No filings found</p>
                            {hasActiveFilters && (
                                <button 
                                    onClick={clearAllFilters}
                                    className="mt-2 text-[10px] text-primary hover:text-primary-hover"
                                >
                                    Clear filters
                                </button>
                            )}
                        </div>
                    </div>
                ) : (
                    <TableVirtuoso
                        style={{ height: '100%' }}
                        data={displayedFilings}
                        overscan={20}
                        fixedHeaderContent={() => (
                            <tr className="bg-surface-inset border-b border-border">
                                <th className="px-3 py-1.5 text-left text-[9px] font-semibold text-muted-fg uppercase tracking-wider w-16">Ticker</th>
                                <th className="px-3 py-1.5 text-left text-[9px] font-semibold text-muted-fg uppercase tracking-wider w-20">Form</th>
                                <th className="px-3 py-1.5 text-left text-[9px] font-semibold text-muted-fg uppercase tracking-wider">Description</th>
                                <th className="px-3 py-1.5 text-right text-[9px] font-semibold text-muted-fg uppercase tracking-wider w-24">Date</th>
                                <th className="px-3 py-1.5 text-right text-[9px] font-semibold text-muted-fg uppercase tracking-wider w-20">Time</th>
                            </tr>
                        )}
                        itemContent={(index, filing) => {
                            const isRealtime = realtimeAccessions.current.has(filing.accessionNo);
                            const isHighlighted = highlightedAccessions.has(filing.accessionNo);
                            const { date, time } = formatDateTime(filing.filedAt);
                            const formColor = getFormTypeColor(filing.formType);
                            const formInfo = FORM_TYPE_INFO[filing.formType];
                            const itemImportance = filing.formType.startsWith('8-K') ? get8KItemImportance(filing.items ?? null) : null;
                            const itemsText = filing.formType.startsWith('8-K') ? format8KItems(filing.items ?? null) : '';
                            const bgClass = isHighlighted ? 'bg-emerald-500/15' : isRealtime ? 'bg-emerald-500/10' : '';
                            
                            return (
                                <>
                                    <td className={`px-3 py-1 whitespace-nowrap text-[11px] cursor-pointer ${bgClass}`} onClick={() => handleFilingClick(filing)}>
                                        <span className={`font-medium ${filing.ticker ? 'text-foreground' : 'text-muted-fg'}`}>
                                            {filing.ticker || '--'}
                                        </span>
                                    </td>
                                    <td className={`px-3 py-1 whitespace-nowrap text-[11px] cursor-pointer ${bgClass}`} onClick={() => handleFilingClick(filing)}>
                                        <span className={`inline-block px-1.5 py-0.5 text-[10px] rounded border ${colorClasses[formColor]}`} title={formInfo?.description}>
                                            {filing.formType}
                                        </span>
                                    </td>
                                    <td className={`px-3 py-1 text-[11px] cursor-pointer ${bgClass}`} onClick={() => handleFilingClick(filing)}>
                                        <div className="flex items-center gap-1.5">
                                            {itemImportance && itemImportance !== 'low' && (
                                                <span className={`flex-shrink-0 ${importanceColors[itemImportance]}`} title={`${itemImportance} importance`}>
                                                    <Zap className="w-3 h-3" />
                                                </span>
                                            )}
                                            <span className="text-foreground/80 truncate">
                                                {itemsText && <span className="text-muted-fg mr-1">[{itemsText}]</span>}
                                                {truncateDescription(filing.description, itemsText ? 50 : 80)}
                                            </span>
                                        </div>
                                    </td>
                                    <td className={`px-3 py-1 whitespace-nowrap text-right text-muted-fg tabular-nums text-[11px] cursor-pointer ${bgClass}`} onClick={() => handleFilingClick(filing)}>
                                        {date}
                                    </td>
                                    <td className={`px-3 py-1 whitespace-nowrap text-right text-muted-fg tabular-nums text-[11px] cursor-pointer ${bgClass}`} onClick={() => handleFilingClick(filing)}>
                                        {time}
                                    </td>
                                </>
                            );
                        }}
                        components={{
                            Table: ({ style, ...props }) => (
                                <table {...props} style={{ ...style, width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }} className="text-[11px]" />
                            ),
                            TableHead: React.forwardRef(({ style, ...props }, ref) => (
                                <thead {...props} ref={ref} style={{ ...style, position: 'sticky', top: 0, zIndex: 1 }} />
                            )),
                            TableRow: ({ style, ...props }) => (
                                <tr {...props} style={{ ...style }} className="hover:bg-surface-hover border-b border-border-subtle" />
                            ),
                        }}
                    />
                )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between px-3 py-1 border-t border-border bg-surface-hover text-[10px] text-muted-fg">
                <div className="flex items-center gap-2">
                    <span className="tabular-nums">{totalResults.toLocaleString()} total</span>
                    <span className="text-muted-fg/50">|</span>
                    <span>Page {currentPage} of {Math.max(1, Math.ceil(totalResults / PAGE_SIZE))}</span>
                </div>

                <div className="flex items-center gap-1">
                    {[
                        { label: '<<', page: 1, disabled: currentPage === 1 },
                        { label: '<', page: currentPage - 1, disabled: currentPage === 1 },
                    ].map(btn => (
                        <button
                            key={btn.label}
                            onClick={() => fetchFilings(btn.page)}
                            disabled={btn.disabled || loading}
                            className="px-1.5 py-0.5 rounded text-foreground/80 hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                            {btn.label}
                        </button>
                    ))}
                    
                    {[...Array(5)].map((_, i) => {
                        const pageNum = currentPage - 2 + i;
                        const totalPages = Math.max(1, Math.ceil(totalResults / PAGE_SIZE));
                        if (pageNum < 1 || pageNum > totalPages) return null;
                        return (
                            <button
                                key={pageNum}
                                onClick={() => fetchFilings(pageNum)}
                                disabled={loading}
                                className={`px-1.5 py-0.5 rounded tabular-nums ${
                                    pageNum === currentPage
                                        ? 'bg-primary text-white'
                                        : 'text-foreground/80 hover:bg-surface-hover'
                                } disabled:opacity-30`}
                            >
                                {pageNum}
                            </button>
                        );
                    })}

                    {[
                        { label: '>', page: currentPage + 1, disabled: currentPage >= Math.ceil(totalResults / PAGE_SIZE) },
                        { label: '>>', page: Math.ceil(totalResults / PAGE_SIZE), disabled: currentPage >= Math.ceil(totalResults / PAGE_SIZE) },
                    ].map(btn => (
                        <button
                            key={btn.label}
                            onClick={() => fetchFilings(btn.page)}
                            disabled={btn.disabled || loading}
                            className="px-1.5 py-0.5 rounded text-foreground/80 hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                            {btn.label}
                        </button>
                    ))}
                </div>

                <div className="flex items-center gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${ws.isConnected ? 'bg-emerald-500' : 'bg-muted'}`} />
                    <span>{ws.isConnected ? 'Live' : 'Offline'}</span>
                </div>
            </div>
        </div>
    );
}
