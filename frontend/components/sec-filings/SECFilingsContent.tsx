'use client';

import { useState, useEffect, useRef, useMemo } from "react";
import {
    Search,
    FileText,
    RefreshCw,
    AlertTriangle,
    ExternalLink,
    X
} from "lucide-react";
import { TickerSearch } from '@/components/common/TickerSearch';
import { useRxWebSocket } from '@/hooks/useRxWebSocket';

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
    documentFormatFiles?: DocumentFile[];
};

type FilingsResponse = {
    total: number;
    filings: SECFiling[];
};

export function SECFilingsContent() {
    const [historicalFilings, setHistoricalFilings] = useState<SECFiling[]>([]);
    const [realtimeFilings, setRealtimeFilings] = useState<SECFiling[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Estado separado: inputValue (lo que escribes) vs searchQuery (lo que se busca)
    const [inputValue, setInputValue] = useState("");
    const [searchQuery, setSearchQuery] = useState("");

    const [formTypeFilter, setFormTypeFilter] = useState("");
    const [startDate, setStartDate] = useState("");
    const [endDate, setEndDate] = useState("");
    const [currentPage, setCurrentPage] = useState(1);
    const [totalResults, setTotalResults] = useState(0);
    const [selectedFiling, setSelectedFiling] = useState<SECFiling | null>(null);
    const PAGE_SIZE = 100;

    // WebSocket
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';
    const ws = useRxWebSocket(wsUrl, false);
    const seenAccessions = useRef<Set<string>>(new Set());
    const realtimeAccessions = useRef<Set<string>>(new Set()); // Track cuáles son real-time

    const fetchFilings = async (page: number = 1, tickerOverride?: string) => {
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

            // Usar endpoint /live para búsqueda directa en SEC API (sin esperar backfill)
            const response = await fetch(`http://157.180.45.153:8012/api/v1/filings/live?${params}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data: FilingsResponse = await response.json();
            setHistoricalFilings(data.filings);
            setTotalResults(data.total);
            setCurrentPage(page);

            // Marcar como vistos para deduplicación
            data.filings.forEach(f => seenAccessions.current.add(f.accessionNo));
        } catch (err) {
            console.error('Error fetching filings:', err);
            setError(err instanceof Error ? err.message : "Error al cargar filings");
            setHistoricalFilings([]);
            setTotalResults(0);
        } finally {
            setLoading(false);
        }
    };

    // WebSocket: Real-time filings
    useEffect(() => {
        if (!ws.isConnected) return;

        ws.send({ action: 'subscribe_sec_filings' });

        const subscription = ws.messages$.subscribe((message: any) => {
            if (message.type === 'sec_filing' && message.filing) {
                const newFiling = message.filing;

                if (!seenAccessions.current.has(newFiling.accessionNo)) {
                    seenAccessions.current.add(newFiling.accessionNo);
                    realtimeAccessions.current.add(newFiling.accessionNo); // Marcar como real-time
                    setRealtimeFilings(prev => [newFiling, ...prev].slice(0, 50));
                }
            }
        });

        return () => {
            subscription.unsubscribe();
            ws.send({ action: 'unsubscribe_sec_filings' });
        };
    }, [ws.isConnected, ws.messages$, ws]);

    // Auto-buscar cuando cambian filtros (o al inicio si todos están vacíos)
    useEffect(() => {
        setCurrentPage(1);

        // Si hay filtros activos, limpiar real-time filings para evitar mostrar datos viejos no filtrados
        if (searchQuery || formTypeFilter || startDate || endDate) {
            setRealtimeFilings([]);
            seenAccessions.current.clear();
            realtimeAccessions.current.clear();
        }

        fetchFilings(1, searchQuery);
    }, [searchQuery, formTypeFilter, startDate, endDate]);

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        // Copiar inputValue a searchQuery
        setSearchQuery(inputValue);
        setCurrentPage(1);

        // Si hay ticker, buscar en backend (más resultados)
        if (inputValue.trim()) {
            fetchFilings(1, inputValue);
        }
    };

    const clearFilters = () => {
        setInputValue("");
        setSearchQuery("");
        setFormTypeFilter("");
        setStartDate("");
        setEndDate("");
        setCurrentPage(1);
        seenAccessions.current.clear();
        realtimeAccessions.current.clear();
        setRealtimeFilings([]);
        // El useEffect detectará el cambio y hará fetchFilings automáticamente
    };

    // Determinar si hay filtros activos
    const hasActiveFilters = searchQuery || formTypeFilter || startDate || endDate;

    // Función para filtrar filings según los filtros activos
    const filterFiling = (filing: SECFiling): boolean => {
        // Filtro de ticker (manejar null correctamente)
        if (searchQuery) {
            const searchUpper = searchQuery.trim().toUpperCase();
            if (!filing.ticker || filing.ticker.toUpperCase() !== searchUpper) {
                return false;
            }
        }

        // Filtro de form type
        if (formTypeFilter) {
            const formFilterUpper = formTypeFilter.trim().toUpperCase();
            if (!filing.formType || !filing.formType.toUpperCase().includes(formFilterUpper)) {
                return false;
            }
        }

        // Filtro de fecha inicial
        if (startDate) {
            const filingDate = filing.filedAt.split('T')[0]; // YYYY-MM-DD
            if (filingDate < startDate) {
                return false;
            }
        }

        // Filtro de fecha final
        if (endDate) {
            const filingDate = filing.filedAt.split('T')[0]; // YYYY-MM-DD
            if (filingDate > endDate) {
                return false;
            }
        }

        return true;
    };

    // Merge de todos los filings (real-time + históricos) con deduplicación robusta
    const displayedFilings = useMemo(() => {
        // Usar Map para garantizar unicidad por accessionNo
        const filingMap = new Map<string, SECFiling>();

        // Primero agregar históricos (tienen prioridad de datos completos)
        const filingsToProcess = hasActiveFilters
            ? historicalFilings.filter(filterFiling)
            : historicalFilings;

        filingsToProcess.forEach(f => {
            if (f.accessionNo && !filingMap.has(f.accessionNo)) {
                filingMap.set(f.accessionNo, f);
            }
        });

        // Luego agregar real-time (solo si no existe ya)
        const realtimeToProcess = hasActiveFilters
            ? realtimeFilings.filter(filterFiling)
            : realtimeFilings;

        realtimeToProcess.forEach(f => {
            if (f.accessionNo && !filingMap.has(f.accessionNo)) {
                filingMap.set(f.accessionNo, f);
            }
        });

        // Convertir a array y ordenar por fecha (más recientes primero)
        const result = Array.from(filingMap.values());
        result.sort((a, b) => new Date(b.filedAt).getTime() - new Date(a.filedAt).getTime());

        return result;
    }, [realtimeFilings, historicalFilings, hasActiveFilters, searchQuery, formTypeFilter, startDate, endDate]);

    const formatDateTime = (isoString: string) => {
        // El string ya viene con timezone correcto de SEC (e.g. "2025-11-19T19:20:42-05:00")
        // Extraer directamente sin conversiones adicionales
        const [datePart, timePart] = isoString.split('T');
        const timeOnly = timePart.split(/[-+]/)[0]; // Quitar el offset timezone
        return {
            date: datePart, // YYYY-MM-DD
            time: timeOnly  // HH:MM:SS
        };
    };

    const truncateDescription = (desc: string | null, maxLength: number = 80) => {
        if (!desc) return '—';
        if (desc.length <= maxLength) return desc;
        return desc.substring(0, maxLength) + '...';
    };

    const handleFilingClick = (filing: SECFiling) => {
        // Buscar el primer documento HTML o XML en documentFormatFiles
        const hasViewableDoc = filing.documentFormatFiles && filing.documentFormatFiles.length > 0;

        if (hasViewableDoc) {
            // Prioridad: buscar el documento principal (form type matching)
            const mainDoc = filing.documentFormatFiles?.find(doc =>
                doc.type === filing.formType ||
                doc.description?.toLowerCase().includes(filing.formType.toLowerCase())
            );

            // Si no hay doc principal, buscar cualquier .htm o .xml
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

        // Fallback: abrir link externo
        const url = filing.linkToHtml || filing.linkToFilingDetails || filing.linkToTxt;
        if (url) window.open(url, '_blank');
    };

    // Si hay un filing seleccionado, mostrar el viewer
    if (selectedFiling) {
        // Buscar el documento principal para mostrar
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

        // Usar proxy para evitar restricciones de CORS y X-Frame-Options
        const proxyUrl = filingUrl
            ? `http://157.180.45.153:8012/api/v1/proxy?url=${encodeURIComponent(filingUrl)}`
            : '';

        return (
            <div className="h-full flex flex-col bg-white">
                {/* Header del viewer */}
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

                {/* Iframe con el filing a través del proxy */}
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

    return (
        <div className="h-full flex flex-col bg-white">
            {/* Search Bar - Ultra Compacto */}
            <div className="px-2 py-1 border-b border-slate-300 bg-slate-50 flex items-center gap-1.5">
                <form onSubmit={handleSearch} className="flex items-center gap-1.5 flex-1">
                    <TickerSearch
                        value={inputValue}
                        onChange={setInputValue}
                        onSelect={(ticker) => {
                            // Cuando selecciona un ticker, buscar INMEDIATAMENTE
                            setInputValue(ticker.symbol);
                            setSearchQuery(ticker.symbol);
                            setCurrentPage(1);
                            fetchFilings(1, ticker.symbol);
                        }}
                        placeholder="Ticker"
                        className="w-32"
                    />
                    <input
                        type="text"
                        value={formTypeFilter}
                        onChange={(e) => setFormTypeFilter(e.target.value.toUpperCase())}
                        placeholder="Form"
                        className="w-20 px-1.5 py-0.5 border border-slate-300 rounded bg-white text-slate-900 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 placeholder:text-slate-400 font-mono"
                    />
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
                    <button
                        type="submit"
                        disabled={loading}
                        className="px-2 py-0.5 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-xs font-medium"
                    >
                        {loading ? <RefreshCw className="w-3 h-3 animate-spin" /> : 'Search'}
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
                </form>
                {!loading && !error && (
                    <div className="text-xs text-slate-600 font-mono flex items-center gap-1">
                        <span>{displayedFilings.length}</span>
                        {realtimeFilings.length > 0 && (
                            <span className="text-emerald-600">({realtimeFilings.length} live)</span>
                        )}
                    </div>
                )}
            </div>

            {/* Error Message */}
            {error && (
                <div className="mx-2 mt-1 px-2 py-1 bg-red-50 border border-red-200 rounded flex items-center gap-1.5 text-red-700">
                    <AlertTriangle className="w-3 h-3" />
                    <span className="text-xs">{error}</span>
                </div>
            )}

            {/* Table - Ultra Compacta */}
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
                        ) : displayedFilings.length === 0 ? (
                            <tr>
                                <td colSpan={5} className="px-2 py-6 text-center">
                                    <FileText className="w-8 h-8 mx-auto mb-2 text-slate-300" />
                                    <p className="text-slate-500 font-medium text-xs">No se encontraron filings</p>
                                </td>
                            </tr>
                        ) : (
                            displayedFilings.map((filing, index) => {
                                // Es real-time solo si NO hay filtros activos y está en los primeros N
                                const isRealtime = !hasActiveFilters && index < realtimeFilings.length;
                                const { date, time } = formatDateTime(filing.filedAt);
                                return (
                                    <tr
                                        key={filing.accessionNo || filing.id}
                                        onClick={() => handleFilingClick(filing)}
                                        className={`hover:bg-blue-50 transition-colors cursor-pointer border-b border-slate-100 ${isRealtime ? 'bg-emerald-50' : ''}`}
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

            {/* Footer - Compacto con Paginación */}
            <div className="px-2 py-0.5 border-t border-slate-200 bg-slate-50 text-[10px] text-slate-600 flex items-center justify-between font-mono">
                <div className="flex items-center gap-2">
                    <span>{totalResults.toLocaleString()} total</span>
                    <span className="text-slate-400">|</span>
                    <span>Página {currentPage} de {Math.ceil(totalResults / PAGE_SIZE)}</span>
                </div>

                <div className="flex items-center gap-1">
                    <button
                        onClick={() => fetchFilings(1)}
                        disabled={currentPage === 1 || loading}
                        className="px-1.5 py-0.5 bg-white border border-slate-300 rounded text-slate-700 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                        ««
                    </button>
                    <button
                        onClick={() => fetchFilings(currentPage - 1)}
                        disabled={currentPage === 1 || loading}
                        className="px-1.5 py-0.5 bg-white border border-slate-300 rounded text-slate-700 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                        «
                    </button>

                    {/* Números de página cercanos */}
                    {[...Array(5)].map((_, i) => {
                        const pageNum = currentPage - 2 + i;
                        const totalPages = Math.ceil(totalResults / PAGE_SIZE);
                        if (pageNum < 1 || pageNum > totalPages) return null;
                        return (
                            <button
                                key={pageNum}
                                onClick={() => fetchFilings(pageNum)}
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
                        onClick={() => fetchFilings(currentPage + 1)}
                        disabled={currentPage >= Math.ceil(totalResults / PAGE_SIZE) || loading}
                        className="px-1.5 py-0.5 bg-white border border-slate-300 rounded text-slate-700 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                        »
                    </button>
                    <button
                        onClick={() => fetchFilings(Math.ceil(totalResults / PAGE_SIZE))}
                        disabled={currentPage >= Math.ceil(totalResults / PAGE_SIZE) || loading}
                        className="px-1.5 py-0.5 bg-white border border-slate-300 rounded text-slate-700 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                        »»
                    </button>
                </div>

                <div className="flex items-center gap-1.5">
                    <span className={`inline-block w-1.5 h-1.5 rounded-full ${ws.isConnected ? 'bg-emerald-500' : 'bg-slate-300'}`}></span>
                    <span className="text-[10px]">{ws.isConnected ? 'Live' : 'Offline'}</span>
                </div>
            </div>
        </div>
    );
}
