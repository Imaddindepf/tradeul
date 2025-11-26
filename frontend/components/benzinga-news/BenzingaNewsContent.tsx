'use client';

import { useState, useEffect, useRef, useMemo } from "react";
import {
    Search,
    Newspaper,
    RefreshCw,
    ExternalLink,
    X,
    Clock,
    Tag,
    User,
    TrendingUp,
    Zap
} from "lucide-react";
import { TickerSearch } from '@/components/common/TickerSearch';
import { useRxWebSocket } from '@/hooks/useRxWebSocket';

type BenzingaArticle = {
    benzinga_id: number;
    title: string;
    author: string;
    published: string;
    last_updated: string;
    url: string;
    teaser?: string;
    body?: string;
    tickers?: string[];
    channels?: string[];
    tags?: string[];
    images?: string[];
};

export function BenzingaNewsContent() {
    const [historicalNews, setHistoricalNews] = useState<BenzingaArticle[]>([]);
    const [realtimeNews, setRealtimeNews] = useState<BenzingaArticle[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Filtros
    const [inputValue, setInputValue] = useState("");
    const [searchQuery, setSearchQuery] = useState("");
    const [channelFilter, setChannelFilter] = useState("");
    const [selectedArticle, setSelectedArticle] = useState<BenzingaArticle | null>(null);

    // WebSocket
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';
    const ws = useRxWebSocket(wsUrl, false);
    const seenIds = useRef<Set<number>>(new Set());
    const realtimeIds = useRef<Set<number>>(new Set());

    // Fetch noticias del API
    const fetchNews = async (tickerOverride?: string) => {
        setLoading(true);
        setError(null);

        try {
            const params = new URLSearchParams();
            const tickerToSearch = tickerOverride !== undefined ? tickerOverride : searchQuery;
            if (tickerToSearch.trim()) params.append('ticker', tickerToSearch.trim().toUpperCase());
            if (channelFilter.trim()) params.append('channels', channelFilter.trim());
            params.append('limit', '100');

            const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            const response = await fetch(`${apiUrl}/benzinga/api/v1/news?${params}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            setHistoricalNews(data.results || []);

            // Marcar como vistos para deduplicación
            (data.results || []).forEach((a: BenzingaArticle) => seenIds.current.add(a.benzinga_id));
        } catch (err) {
            console.error('Error fetching news:', err);
            setError(err instanceof Error ? err.message : "Error al cargar noticias");
            setHistoricalNews([]);
        } finally {
            setLoading(false);
        }
    };

    // WebSocket: Real-time news
    useEffect(() => {
        if (!ws.isConnected) return;

        ws.send({ action: 'subscribe_benzinga_news' });

        const subscription = ws.messages$.subscribe((message: any) => {
            if (message.type === 'benzinga_news' && message.article) {
                const newArticle = message.article;

                if (!seenIds.current.has(newArticle.benzinga_id)) {
                    seenIds.current.add(newArticle.benzinga_id);
                    realtimeIds.current.add(newArticle.benzinga_id);
                    setRealtimeNews(prev => [newArticle, ...prev].slice(0, 100));
                }
            }
        });

        return () => {
            subscription.unsubscribe();
            ws.send({ action: 'unsubscribe_benzinga_news' });
        };
    }, [ws.isConnected, ws.messages$, ws]);

    // Cargar noticias al inicio
    useEffect(() => {
        fetchNews();
    }, []);

    // Buscar cuando cambian filtros
    useEffect(() => {
        if (searchQuery || channelFilter) {
            // Limpiar real-time para evitar mezclar filtros
            setRealtimeNews([]);
            seenIds.current.clear();
            realtimeIds.current.clear();
            fetchNews();
        }
    }, [searchQuery, channelFilter]);

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        setSearchQuery(inputValue);
    };

    const clearFilters = () => {
        setInputValue("");
        setSearchQuery("");
        setChannelFilter("");
        setRealtimeNews([]);
        seenIds.current.clear();
        realtimeIds.current.clear();
        fetchNews();
    };

    // Merge de noticias (real-time + históricos)
    const displayedNews = useMemo(() => {
        const historicalIds = new Set(historicalNews.map(a => a.benzinga_id));
        const uniqueRealtime = realtimeNews.filter(a => !historicalIds.has(a.benzinga_id));
        return [...uniqueRealtime, ...historicalNews];
    }, [realtimeNews, historicalNews]);

    const formatDateTime = (isoString: string) => {
        if (!isoString) return { date: '—', time: '—', relative: '' };
        
        try {
            const date = new Date(isoString);
            const now = new Date();
            const diffMs = now.getTime() - date.getTime();
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMs / 3600000);
            
            let relative = '';
            if (diffMins < 1) relative = 'just now';
            else if (diffMins < 60) relative = `${diffMins}m ago`;
            else if (diffHours < 24) relative = `${diffHours}h ago`;
            else relative = date.toLocaleDateString();
            
            return {
                date: date.toLocaleDateString(),
                time: date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                relative
            };
        } catch {
            return { date: '—', time: '—', relative: '' };
        }
    };

    const truncateText = (text: string | undefined, maxLength: number = 120) => {
        if (!text) return '';
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    };

    const isRealtime = (article: BenzingaArticle) => realtimeIds.current.has(article.benzinga_id);

    // Vista de artículo seleccionado
    if (selectedArticle) {
        return (
            <div className="h-full flex flex-col bg-white">
                {/* Header del viewer */}
                <div className="px-3 py-2 border-b border-slate-300 bg-slate-50 flex items-center justify-between">
                    <button
                        onClick={() => setSelectedArticle(null)}
                        className="px-3 py-1 bg-slate-200 text-slate-700 rounded hover:bg-slate-300 text-xs font-medium flex items-center gap-1"
                    >
                        ← Back
                    </button>
                    <div className="text-xs text-slate-600 font-mono flex items-center gap-2">
                        {selectedArticle.tickers?.slice(0, 3).map(ticker => (
                            <span key={ticker} className="font-semibold text-blue-600">${ticker}</span>
                        ))}
                        <span>·</span>
                        <span>{formatDateTime(selectedArticle.published).relative}</span>
                    </div>
                    <a
                        href={selectedArticle.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-xs font-medium flex items-center gap-1"
                    >
                        <ExternalLink className="w-3 h-3" />
                        Open Original
                    </a>
                </div>

                {/* Contenido del artículo */}
                <div className="flex-1 overflow-auto p-4">
                    <h1 className="text-lg font-bold text-slate-900 mb-2">
                        {selectedArticle.title}
                    </h1>
                    
                    <div className="flex items-center gap-3 text-xs text-slate-500 mb-4">
                        <span className="flex items-center gap-1">
                            <User className="w-3 h-3" />
                            {selectedArticle.author}
                        </span>
                        <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {formatDateTime(selectedArticle.published).date} {formatDateTime(selectedArticle.published).time}
                        </span>
                    </div>

                    {/* Tickers */}
                    {selectedArticle.tickers && selectedArticle.tickers.length > 0 && (
                        <div className="flex flex-wrap gap-1 mb-4">
                            {selectedArticle.tickers.map(ticker => (
                                <span
                                    key={ticker}
                                    className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-mono"
                                >
                                    ${ticker}
                                </span>
                            ))}
                        </div>
                    )}

                    {/* Channels/Tags */}
                    {(selectedArticle.channels || selectedArticle.tags) && (
                        <div className="flex flex-wrap gap-1 mb-4">
                            {selectedArticle.channels?.map(channel => (
                                <span
                                    key={channel}
                                    className="px-2 py-0.5 bg-emerald-100 text-emerald-700 rounded text-xs"
                                >
                                    {channel}
                                </span>
                            ))}
                            {selectedArticle.tags?.map(tag => (
                                <span
                                    key={tag}
                                    className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded text-xs"
                                >
                                    #{tag}
                                </span>
                            ))}
                        </div>
                    )}

                    {/* Teaser o Body */}
                    <div className="prose prose-sm max-w-none text-slate-700">
                        {selectedArticle.body ? (
                            <div dangerouslySetInnerHTML={{ __html: selectedArticle.body }} />
                        ) : selectedArticle.teaser ? (
                            <p className="text-slate-600">{selectedArticle.teaser}</p>
                        ) : (
                            <p className="text-slate-400 italic">No content available. Click "Open Original" to view the full article.</p>
                        )}
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="h-full flex flex-col bg-white">
            {/* Search Bar */}
            <div className="px-2 py-1.5 border-b border-slate-300 bg-slate-50 flex items-center gap-2">
                <form onSubmit={handleSearch} className="flex items-center gap-2 flex-1">
                    <TickerSearch
                        value={inputValue}
                        onChange={setInputValue}
                        onSelect={(ticker) => {
                            setInputValue(ticker.symbol);
                            setSearchQuery(ticker.symbol);
                            fetchNews(ticker.symbol);
                        }}
                        placeholder="Ticker"
                        className="w-28"
                    />
                    <input
                        type="text"
                        value={channelFilter}
                        onChange={(e) => setChannelFilter(e.target.value)}
                        placeholder="Channel"
                        className="w-24 px-2 py-1 border border-slate-300 rounded bg-white text-slate-900 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 placeholder:text-slate-400"
                    />
                    <button
                        type="submit"
                        disabled={loading}
                        className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-xs font-medium flex items-center gap-1"
                    >
                        {loading ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
                        Search
                    </button>
                    <button
                        type="button"
                        onClick={clearFilters}
                        disabled={loading}
                        className="px-2 py-1 bg-slate-200 text-slate-700 rounded hover:bg-slate-300 disabled:opacity-50 text-xs font-medium flex items-center gap-1"
                    >
                        <X className="w-3 h-3" />
                    </button>
                </form>
                <div className="text-xs text-slate-600 font-mono flex items-center gap-2">
                    <span>{displayedNews.length} news</span>
                    {realtimeNews.length > 0 && (
                        <span className="text-emerald-600 flex items-center gap-1">
                            <Zap className="w-3 h-3" />
                            {realtimeNews.length} live
                        </span>
                    )}
                </div>
            </div>

            {/* Error Message */}
            {error && (
                <div className="px-3 py-2 bg-red-50 border-b border-red-200 text-red-600 text-xs flex items-center gap-2">
                    <span className="font-medium">Error:</span> {error}
                </div>
            )}

            {/* News List */}
            <div className="flex-1 overflow-auto">
                {loading && displayedNews.length === 0 ? (
                    <div className="flex items-center justify-center h-32 text-slate-400">
                        <RefreshCw className="w-5 h-5 animate-spin mr-2" />
                        Loading news...
                    </div>
                ) : displayedNews.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-32 text-slate-400">
                        <Newspaper className="w-8 h-8 mb-2" />
                        <span className="text-sm">No news found</span>
                    </div>
                ) : (
                    <div className="divide-y divide-slate-100">
                        {displayedNews.map((article) => {
                            const datetime = formatDateTime(article.published);
                            const isLive = isRealtime(article);

                            return (
                                <div
                                    key={article.benzinga_id}
                                    onClick={() => setSelectedArticle(article)}
                                    className={`px-3 py-2 hover:bg-slate-50 cursor-pointer transition-colors ${isLive ? 'bg-emerald-50/50' : ''}`}
                                >
                                    {/* Header Row */}
                                    <div className="flex items-start justify-between gap-2 mb-1">
                                        <div className="flex items-center gap-2 flex-1 min-w-0">
                                            {isLive && (
                                                <span className="flex-shrink-0 px-1.5 py-0.5 bg-emerald-500 text-white rounded text-[10px] font-bold animate-pulse">
                                                    LIVE
                                                </span>
                                            )}
                                            {/* Tickers */}
                                            {article.tickers && article.tickers.length > 0 && (
                                                <div className="flex-shrink-0 flex items-center gap-1">
                                                    {article.tickers.slice(0, 3).map(ticker => (
                                                        <span
                                                            key={ticker}
                                                            className="px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded text-[10px] font-mono font-semibold"
                                                        >
                                                            ${ticker}
                                                        </span>
                                                    ))}
                                                    {article.tickers.length > 3 && (
                                                        <span className="text-[10px] text-slate-400">
                                                            +{article.tickers.length - 3}
                                                        </span>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                        <span className="flex-shrink-0 text-[10px] text-slate-400 font-mono">
                                            {datetime.relative}
                                        </span>
                                    </div>

                                    {/* Title */}
                                    <h3 className="text-sm font-medium text-slate-900 leading-tight mb-1 line-clamp-2">
                                        {article.title}
                                    </h3>

                                    {/* Teaser */}
                                    {article.teaser && (
                                        <p className="text-xs text-slate-500 line-clamp-1 mb-1">
                                            {truncateText(article.teaser, 150)}
                                        </p>
                                    )}

                                    {/* Footer */}
                                    <div className="flex items-center gap-3 text-[10px] text-slate-400">
                                        <span className="flex items-center gap-1">
                                            <User className="w-2.5 h-2.5" />
                                            {article.author}
                                        </span>
                                        {article.channels && article.channels.length > 0 && (
                                            <span className="flex items-center gap-1">
                                                <Tag className="w-2.5 h-2.5" />
                                                {article.channels.slice(0, 2).join(', ')}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}

