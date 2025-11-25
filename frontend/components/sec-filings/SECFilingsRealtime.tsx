'use client';

import { useState, useEffect, useRef } from "react";
import {
    Search,
    FileText,
    RefreshCw,
    AlertTriangle,
    ExternalLink,
    X,
    Zap,
    Database,
    Filter
} from "lucide-react";
import { TickerSearch } from '@/components/common/TickerSearch';

type DocumentFile = {
    sequence: string;
    documentUrl: string;
    description?: string;
    type: string;
    size?: string;
};

type SECFiling = {
    id: string;
    accessionNo: string;
    ticker: string | null;
    formType: string;
    filedAt: string;
    companyName: string | null;
    description: string | null;
    linkToFilingDetails: string | null;
    linkToHtml: string | null;
    linkToTxt: string | null;
    cik: string;
    documentFormatFiles?: DocumentFile[];
};

type ViewMode = 'realtime' | 'historical';

export function SECFilingsRealtime() {
    // Estado de vista
    const [viewMode, setViewMode] = useState<ViewMode>('realtime');
    
    // Filings en tiempo real
    const [realtimeFilings, setRealtimeFilings] = useState<SECFiling[]>([]);
    
    // Filings históricos
    const [historicalFilings, setHistoricalFilings] = useState<SECFiling[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // WebSocket
    const wsRef = useRef<WebSocket | null>(null);
    const [wsConnected, setWsConnected] = useState(false);

    // Filtros
    const [inputValue, setInputValue] = useState("");
    const [searchQuery, setSearchQuery] = useState("");
    const [formTypeFilter, setFormTypeFilter] = useState("");
    const [startDate, setStartDate] = useState("");
    const [endDate, setEndDate] = useState("");
    
    // Filtros en tiempo real (aplicados localmente)
    const [realtimeTickerFilter, setRealtimeTickerFilter] = useState("");
    const [realtimeFormFilter, setRealtimeFormFilter] = useState("");

    // Paginación
    const [currentPage, setCurrentPage] = useState(1);
    const [totalResults, setTotalResults] = useState(0);
    const PAGE_SIZE = 100;

    // Filing seleccionado para viewer
    const [selectedFiling, setSelectedFiling] = useState<SECFiling | null>(null);

    // =====================================================
    // WEBSOCKET CONNECTION
    // =====================================================
    useEffect(() => {
        // Conectar al WebSocket solo si estamos en modo realtime
        if (viewMode !== 'realtime') return;

        const wsUrl = 'ws://157.180.45.153:9000';
        console.log('🔌 Connecting to WebSocket:', wsUrl);

        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
            console.log('✅ WebSocket connected');
            setWsConnected(true);
            
            // Suscribirse a SEC Filings
            ws.send(JSON.stringify({
                action: 'subscribe_sec_filings'
            }));
            console.log('📋 Subscribed to SEC Filings stream');
        };

        ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                
                // Manejar filings en tiempo real
                if (message.type === 'sec_filing' && message.filing) {
                    const filing = message.filing;
                    
                    // Aplicar filtros locales antes de agregar
                    if (realtimeTickerFilter && filing.ticker !== realtimeTickerFilter.toUpperCase()) {
                        return;
                    }
                    if (realtimeFormFilter && filing.formType !== realtimeFormFilter.toUpperCase()) {
                        return;
                    }
                    
                    console.log('📄 New SEC filing received:', filing.ticker, filing.formType);
                    
                    // Agregar al inicio de la lista
                    setRealtimeFilings(prev => {
                        // Evitar duplicados
                        const exists = prev.some(f => f.accessionNo === filing.accessionNo);
                        if (exists) return prev;
                        
                        // Mantener solo últimos 500 filings
                        const newFilings = [filing, ...prev].slice(0, 500);
                        return newFilings;
                    });
                }
                
                // Confirmar suscripción
                else if (message.type === 'subscribed' && message.channel === 'SEC_FILINGS') {
                    console.log('✅ Subscription confirmed:', message.message);
                }
            } catch (err) {
                console.error('Error processing WebSocket message:', err);
            }
        };

        ws.onerror = (error) => {
            console.error('❌ WebSocket error:', error);
            setWsConnected(false);
        };

        ws.onclose = () => {
            console.log('🔌 WebSocket disconnected');
            setWsConnected(false);
        };

        // Cleanup
        return () => {
            if (ws.readyState === WebSocket.OPEN) {
                // Desuscribirse antes de cerrar
                ws.send(JSON.stringify({
                    action: 'unsubscribe_sec_filings'
                }));
            }
            ws.close();
        };
    }, [viewMode, realtimeTickerFilter, realtimeFormFilter]);

    // =====================================================
    // HISTORICAL DATA FETCH
    // =====================================================
    const fetchHistoricalFilings = async (page: number = 1, tickerOverride?: string) => {
        setLoading(true);
        setError(null);

        try {
            const params = new URLSearchParams();
            const tickerToSearch = tickerOverride !== undefined ? tickerOverride : searchQuery;
            if (tickerToSearch.trim()) params.append('ticker', tickerToSearch.trim().toUpperCase());
            if (formTypeFilter.trim()) params.append('form_type', formTypeFilter.trim());
            if (startDate) params.append('date_from', startDate);
            if (endDate) params.append('date_to', endDate);
            params.append('page_size', PAGE_SIZE.toString());
            params.append('from_index', ((page - 1) * PAGE_SIZE).toString());

            const response = await fetch(`http://157.180.45.153:8012/api/v1/filings/live?${params}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            setHistoricalFilings(data.filings);
            setTotalResults(data.total);
            setCurrentPage(page);
        } catch (err) {
            console.error('Error fetching historical filings:', err);
            setError(err instanceof Error ? err.message : "Error al cargar filings");
            setHistoricalFilings([]);
            setTotalResults(0);
        } finally {
            setLoading(false);
        }
    };

    // Cargar datos históricos cuando cambian los filtros
    useEffect(() => {
        if (viewMode === 'historical') {
            setCurrentPage(1);
            fetchHistoricalFilings(1);
        }
    }, [viewMode, formTypeFilter, startDate, endDate]);

    // =====================================================
    // HANDLERS
    // =====================================================
    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        setSearchQuery(inputValue);
        
        if (viewMode === 'historical') {
            setCurrentPage(1);
            fetchHistoricalFilings(1, inputValue);
        } else {
            // En modo realtime, aplicar filtro local
            setRealtimeTickerFilter(inputValue.trim().toUpperCase());
        }
    };

    const clearFilters = () => {
        setInputValue("");
        setSearchQuery("");
        setFormTypeFilter("");
        setStartDate("");
        setEndDate("");
        setRealtimeTickerFilter("");
        setRealtimeFormFilter("");
        setCurrentPage(1);
        
        if (viewMode === 'historical') {
            setHistoricalFilings([]);
            setTotalResults(0);
        } else {
            // En realtime, solo limpiar filtros locales
            setRealtimeFilings([]);
        }
    };

    const formatDateTime = (isoString: string) => {
        const [datePart, timePart] = isoString.split('T');
        const timeOnly = timePart.split(/[-+]/)[0];
        return {
            date: datePart,
            time: timeOnly
        };
    };

    const truncateDescription = (desc: string | null, maxLength: number = 80) => {
        if (!desc) return '—';
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

    // =====================================================
    // RENDER: FILING VIEWER
    // =====================================================
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

        const filingUrl = viewableDoc?.documentUrl || selectedFiling.linkToHtml || selectedFiling.linkToFilingDetails;
        const proxyUrl = filingUrl
            ? `http://157.180.45.153:8012/api/v1/proxy?url=${encodeURIComponent(filingUrl)}`
            : '';

        return (
            <div className="h-full flex flex-col bg-white">
                <div className="px-2 py-1 border-b border-slate-300 bg-slate-50 flex items-center justify-between">
                    <button
                        onClick={() => setSelectedFiling(null)}
                        className="px-2 py-0.5 bg-slate-200 text-slate-700 rounded hover:bg-slate-300 text-xs font-medium flex items-center gap-1"
                    >
                        ← Back
                    </button>
                    <div className="text-xs text-slate-600 font-mono flex items-center gap-2">
                        <span className="font-semibold text-blue-600">{selectedFiling.ticker || 'N/A'}</span>
                        <span>·</span>
                        <span>{selectedFiling.formType}</span>
                        <span>·</span>
                        <span>{formatDateTime(selectedFiling.filedAt).date}</span>
                    </div>
                    <a
                        href={filingUrl || '#'}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="px-2 py-0.5 bg-blue-600 text-white rounded hover:bg-blue-700 text-xs font-medium flex items-center gap-1"
                    >
                        <ExternalLink className="w-3 h-3" />
                        Open Original
                    </a>
                </div>

                <div className="flex-1 bg-white">
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

    // =====================================================
    // RENDER: MAIN VIEW
    // =====================================================
    const currentFilings = viewMode === 'realtime' ? realtimeFilings : historicalFilings;

    return (
        <div className="h-full flex flex-col bg-white">
            {/* Header con modo selector y filtros */}
            <div className="px-2 py-1 border-b border-slate-300 bg-slate-50 space-y-1">
                {/* Modo selector */}
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => setViewMode('realtime')}
                        className={`px-2 py-0.5 rounded text-xs font-medium flex items-center gap-1 ${
                            viewMode === 'realtime'
                                ? 'bg-emerald-600 text-white'
                                : 'bg-white border border-slate-300 text-slate-700 hover:bg-slate-100'
                        }`}
                    >
                        <Zap className="w-3 h-3" />
                        Real-Time
                        {wsConnected && <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-300 ml-1"></span>}
                    </button>
                    <button
                        onClick={() => setViewMode('historical')}
                        className={`px-2 py-0.5 rounded text-xs font-medium flex items-center gap-1 ${
                            viewMode === 'historical'
                                ? 'bg-blue-600 text-white'
                                : 'bg-white border border-slate-300 text-slate-700 hover:bg-slate-100'
                        }`}
                    >
                        <Database className="w-3 h-3" />
                        Historical
                    </button>
                    
                    <div className="flex-1"></div>
                    
                    {viewMode === 'realtime' && (
                        <div className="text-xs text-slate-600 font-mono flex items-center gap-1.5">
                            <span className={`inline-block w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-emerald-500' : 'bg-red-500'}`}></span>
                            <span>{wsConnected ? 'Connected' : 'Disconnected'}</span>
                        </div>
                    )}
                </div>

                {/* Search Bar */}
                <form onSubmit={handleSearch} className="flex items-center gap-1.5">
                    <TickerSearch
                        value={inputValue}
                        onChange={setInputValue}
                        onSelect={(ticker) => {
                            setInputValue(ticker.symbol);
                            if (viewMode === 'historical') {
                                setSearchQuery(ticker.symbol);
                                setCurrentPage(1);
                                fetchHistoricalFilings(1, ticker.symbol);
                            } else {
                                setRealtimeTickerFilter(ticker.symbol.toUpperCase());
                            }
                        }}
                        placeholder="Ticker"
                        className="w-32"
                    />
                    <input
                        type="text"
                        value={formTypeFilter}
                        onChange={(e) => {
                            const value = e.target.value.toUpperCase();
                            setFormTypeFilter(value);
                            if (viewMode === 'realtime') {
                                setRealtimeFormFilter(value);
                            }
                        }}
                        placeholder="Form"
                        className="w-20 px-1.5 py-0.5 border border-slate-300 rounded bg-white text-slate-900 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 placeholder:text-slate-400 font-mono"
                    />
                    {viewMode === 'historical' && (
                        <>
                            <input
                                type="date"
                                value={startDate}
                                onChange={(e) => setStartDate(e.target.value)}
                                className="w-28 px-1.5 py-0.5 border border-slate-300 rounded bg-white text-slate-900 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                            />
                            <span className="text-slate-400 text-xs">→</span>
                            <input
                                type="date"
                                value={endDate}
                                onChange={(e) => setEndDate(e.target.value)}
                                className="w-28 px-1.5 py-0.5 border border-slate-300 rounded bg-white text-slate-900 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                            />
                        </>
                    )}
                    <button
                        type="submit"
                        disabled={loading}
                        className="px-2 py-0.5 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-xs font-medium"
                    >
                        {loading ? <RefreshCw className="w-3 h-3 animate-spin" /> : (viewMode === 'realtime' ? 'Filter' : 'Search')}
                    </button>
                    <button
                        type="button"
                        onClick={clearFilters}
                        disabled={loading}
                        className="px-2 py-0.5 bg-slate-200 text-slate-700 rounded hover:bg-slate-300 disabled:opacity-50 text-xs font-medium flex items-center gap-1"
                    >
                        <X className="w-3 h-3" />
                        Clear
                    </button>
                    {!loading && !error && (
                        <div className="text-xs text-slate-600 font-mono">
                            {currentFilings.length}
                        </div>
                    )}
                </form>
            </div>

            {/* Error Message */}
            {error && (
                <div className="mx-2 mt-1 px-2 py-1 bg-red-50 border border-red-200 rounded flex items-center gap-1.5 text-red-700">
                    <AlertTriangle className="w-3 h-3" />
                    <span className="text-xs">{error}</span>
                </div>
            )}

            {/* Table */}
            <div className="flex-1 overflow-auto bg-white">
                <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-slate-100 border-b border-slate-200">
                        <tr>
                            <th className="px-2 py-1 text-left text-[10px] font-semibold text-slate-700 uppercase tracking-wide">
                                Ticker
                            </th>
                            <th className="px-2 py-1 text-left text-[10px] font-semibold text-slate-700 uppercase tracking-wide">
                                Form
                            </th>
                            <th className="px-2 py-1 text-left text-[10px] font-semibold text-slate-700 uppercase tracking-wide">
                                Description
                            </th>
                            <th className="px-2 py-1 text-right text-[10px] font-semibold text-slate-700 uppercase tracking-wide">
                                Date
                            </th>
                            <th className="px-2 py-1 text-right text-[10px] font-semibold text-slate-700 uppercase tracking-wide">
                                Time
                            </th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-slate-100">
                        {loading ? (
                            <tr>
                                <td colSpan={5} className="px-2 py-6 text-center">
                                    <RefreshCw className="w-6 h-6 mx-auto mb-1 text-blue-500 animate-spin" />
                                    <p className="text-slate-500 text-xs">Cargando...</p>
                                </td>
                            </tr>
                        ) : currentFilings.length === 0 ? (
                            <tr>
                                <td colSpan={5} className="px-2 py-6 text-center">
                                    <FileText className="w-8 h-8 mx-auto mb-2 text-slate-300" />
                                    <p className="text-slate-500 font-medium text-xs">
                                        {viewMode === 'realtime' 
                                            ? 'Esperando filings en tiempo real...' 
                                            : 'No se encontraron filings'}
                                    </p>
                                </td>
                            </tr>
                        ) : (
                            currentFilings.map((filing) => {
                                const { date, time } = formatDateTime(filing.filedAt);
                                return (
                                    <tr
                                        key={filing.accessionNo}
                                        onClick={() => handleFilingClick(filing)}
                                        className="hover:bg-blue-50 transition-colors cursor-pointer border-b border-slate-100"
                                    >
                                        <td className="px-2 py-0.5 whitespace-nowrap">
                                            <span className={`font-mono font-semibold text-xs ${filing.ticker
                                                ? 'text-blue-600'
                                                : 'text-slate-400'
                                                }`}>
                                                {filing.ticker || '--'}
                                            </span>
                                        </td>
                                        <td className="px-2 py-0.5 whitespace-nowrap">
                                            <span className="text-[10px] font-mono text-slate-700">
                                                {filing.formType}
                                            </span>
                                        </td>
                                        <td className="px-2 py-0.5">
                                            <span className="text-slate-600 text-[10px]">
                                                {truncateDescription(filing.description)}
                                            </span>
                                        </td>
                                        <td className="px-2 py-0.5 whitespace-nowrap text-right font-mono text-[10px] text-slate-600">
                                            {date}
                                        </td>
                                        <td className="px-2 py-0.5 whitespace-nowrap text-right font-mono text-[10px] text-slate-500">
                                            {time}
                                        </td>
                                    </tr>
                                );
                            })
                        )}
                    </tbody>
                </table>
            </div>

            {/* Footer */}
            {viewMode === 'historical' && (
                <div className="px-2 py-0.5 border-t border-slate-200 bg-slate-50 text-[10px] text-slate-600 flex items-center justify-between font-mono">
                    <div className="flex items-center gap-2">
                        <span>{totalResults.toLocaleString()} total</span>
                        <span className="text-slate-400">|</span>
                        <span>Página {currentPage} de {Math.ceil(totalResults / PAGE_SIZE)}</span>
                    </div>

                    <div className="flex items-center gap-1">
                        <button
                            onClick={() => fetchHistoricalFilings(1)}
                            disabled={currentPage === 1 || loading}
                            className="px-1.5 py-0.5 bg-white border border-slate-300 rounded text-slate-700 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                            ««
                        </button>
                        <button
                            onClick={() => fetchHistoricalFilings(currentPage - 1)}
                            disabled={currentPage === 1 || loading}
                            className="px-1.5 py-0.5 bg-white border border-slate-300 rounded text-slate-700 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                            «
                        </button>

                        {[...Array(5)].map((_, i) => {
                            const pageNum = currentPage - 2 + i;
                            const totalPages = Math.ceil(totalResults / PAGE_SIZE);
                            if (pageNum < 1 || pageNum > totalPages) return null;
                            return (
                                <button
                                    key={pageNum}
                                    onClick={() => fetchHistoricalFilings(pageNum)}
                                    disabled={loading}
                                    className={`px-1.5 py-0.5 rounded ${pageNum === currentPage
                                        ? 'bg-blue-600 text-white font-semibold'
                                        : 'bg-white border border-slate-300 text-slate-700 hover:bg-slate-100'
                                        } disabled:opacity-30 disabled:cursor-not-allowed`}
                                >
                                    {pageNum}
                                </button>
                            );
                        })}

                        <button
                            onClick={() => fetchHistoricalFilings(currentPage + 1)}
                            disabled={currentPage >= Math.ceil(totalResults / PAGE_SIZE) || loading}
                            className="px-1.5 py-0.5 bg-white border border-slate-300 rounded text-slate-700 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                            »
                        </button>
                        <button
                            onClick={() => fetchHistoricalFilings(Math.ceil(totalResults / PAGE_SIZE))}
                            disabled={currentPage >= Math.ceil(totalResults / PAGE_SIZE) || loading}
                            className="px-1.5 py-0.5 bg-white border border-slate-300 rounded text-slate-700 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                            »»
                        </button>
                    </div>

                    <div className="flex items-center gap-1.5">
                        <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500"></span>
                        <span>Historical</span>
                    </div>
                </div>
            )}

            {viewMode === 'realtime' && (
                <div className="px-2 py-0.5 border-t border-slate-200 bg-slate-50 text-[10px] text-slate-600 flex items-center justify-between font-mono">
                    <div className="flex items-center gap-2">
                        <span>{realtimeFilings.length} filings</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <span className={`inline-block w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-emerald-500' : 'bg-red-500'}`}></span>
                        <span>{wsConnected ? 'Live Stream' : 'Disconnected'}</span>
                    </div>
                </div>
            )}
        </div>
    );
}

