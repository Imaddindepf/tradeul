'use client';

import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Loader2 } from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { parseTerminalCommand, TICKER_COMMANDS, GLOBAL_COMMANDS, TICKER_LIKE_REGEX } from '@/lib/terminal-parser';
import { useUserFilters } from '@/hooks/useUserFilters';
import { useAlertStrategies, type AlertStrategy } from '@/hooks/useAlertStrategies';
import { SYSTEM_EVENT_CATEGORIES } from '@/lib/commands';
import type { UserFilter } from '@/lib/types/scannerFilters';
import { useNewsStore, selectArticles, NewsArticle } from '@/stores/useNewsStore';
import { decodeHtmlEntities } from '@/lib/html-utils';

// Mini-quote en vivo del snapshot propio (pipeline Polygon interno)
type MiniQuote = { price: number; change_percent: number | null; change: number | null };

// Chip por tipo de instrumento
function instrumentChip(type?: string): { label: string; cls: string } {
    const tp = (type || '').toUpperCase();
    if (tp.includes('ETF') || tp.includes('ETN') || tp.includes('FUND')) {
        return { label: 'ETF', cls: 'border-violet-500/40 text-violet-600 dark:text-violet-400 bg-violet-500/10' };
    }
    if (tp.includes('INDEX') || tp.includes('IDX')) {
        return { label: 'IDX', cls: 'border-amber-500/40 text-amber-600 dark:text-amber-400 bg-amber-500/10' };
    }
    if (tp.includes('FUTURE')) {
        return { label: 'FUT', cls: 'border-orange-500/40 text-orange-600 dark:text-orange-400 bg-orange-500/10' };
    }
    if (tp === 'FX' || tp === 'FOREX') {
        return { label: 'FX', cls: 'border-cyan-500/40 text-cyan-600 dark:text-cyan-400 bg-cyan-500/10' };
    }
    if (tp.includes('ADR')) {
        return { label: 'ADR', cls: 'border-sky-500/40 text-sky-600 dark:text-sky-400 bg-sky-500/10' };
    }
    return { label: 'EQ', cls: 'border-blue-500/40 text-blue-600 dark:text-blue-400 bg-blue-500/10' };
}

function formatPaletteTime(published: string): string {
    const d = new Date(published);
    if (isNaN(d.getTime())) return '';
    const now = new Date();
    if (d.toDateString() === now.toDateString()) {
        return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
    }
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

interface TerminalPaletteProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    searchValue?: string;
    onSearchChange?: (value: string) => void;
    onOpenHelp?: () => void;
    onExecuteTickerCommand?: (ticker: string, command: string, exchange?: string) => void;
}

// Tipo para resultados de búsqueda de ticker
type TickerResult = {
    symbol: string;
    name: string;
    exchange: string;
    type: string;
    security_type?: string;   // FX / FUTURE / INDEX... (más fiable que `type`)
    displayName: string;
};

// Conjunto de todos los códigos de comando (global + ticker). Se usa para
// distinguir "¿esto es un ticker o un comando?" sin listas hardcodeadas.
const COMMAND_KEYS = new Set<string>([
    ...Object.keys(GLOBAL_COMMANDS),
    ...Object.keys(TICKER_COMMANDS),
]);

// Scanner commands - descripciones genéricas sin revelar lógica de negocio
const SCANNER_COMMANDS = [
    { id: 'gappers_up', label: 'Gap Up', description: 'Stocks gapping up at open' },
    { id: 'gappers_down', label: 'Gap Down', description: 'Stocks gapping down at open' },
    { id: 'momentum_up', label: 'Momentum Up', description: 'Strong upward momentum' },
    { id: 'momentum_down', label: 'Momentum Down', description: 'Strong downward momentum' },
    { id: 'winners', label: 'Winners', description: 'Biggest gainers today' },
    { id: 'losers', label: 'Losers', description: 'Biggest losers today' },
    { id: 'new_highs', label: 'New Highs', description: 'Hitting intraday highs' },
    { id: 'new_lows', label: 'New Lows', description: 'Hitting intraday lows' },
    { id: 'anomalies', label: 'Anomalies', description: 'Unusual trading activity' },
    { id: 'high_volume', label: 'High Volume', description: 'High relative volume' },
    { id: 'reversals', label: 'Reversals', description: 'Gap reversals' },
    { id: 'post_market', label: 'Post-Market', description: 'Extended hours movers' },
    { id: 'with_news', label: 'With News', description: 'Stocks with recent news' },
];

export function TerminalPalette({
    open,
    onOpenChange,
    searchValue = '',
    onSearchChange,
    onOpenHelp,
    onExecuteTickerCommand,
}: TerminalPaletteProps) {
    const { t } = useTranslation();
    const [selectedIndex, setSelectedIndex] = useState(0);
    const [tickerResults, setTickerResults] = useState<TickerResult[]>([]);
    const [loadingTickers, setLoadingTickers] = useState(false);
    const [selectedTicker, setSelectedTicker] = useState<TickerResult | null>(null);
    const listRef = useRef<HTMLDivElement>(null);
    const abortControllerRef = useRef<AbortController | null>(null);
    const { executeCommand, openScannerTable, openUserScanTable, openEventTable, openUserStrategyTable, openNewsWithArticle } = useCommandExecutor();

    // Quotes en vivo para los instrumentos listados (batch, polling suave)
    const [quotes, setQuotes] = useState<Record<string, MiniQuote>>({});

    // Noticias en memoria (NewsStore global) para la sección News Stories
    const allArticles = useNewsStore(selectArticles);

    // User scans - refrescar cada vez que se abre el palette
    const { filters: userScans, loading: userScansLoading, refreshFilters } = useUserFilters();

    // User alert strategies
    const { strategies: userStrategies, loading: userStrategiesLoading, listStrategies: refreshStrategies } = useAlertStrategies();

    // Refrescar filtros y estrategias cuando se abre el palette. Solo depende
    // de `open`: si dependiera de las identidades de los callbacks (que cambian
    // con cada render por sus deps internas), cada refetch produciría un nuevo
    // array -> nuevos items -> reset de la selección mientras el usuario navega.
    const refreshRef = useRef({ refreshFilters, refreshStrategies });
    refreshRef.current = { refreshFilters, refreshStrategies };
    useEffect(() => {
        if (!open) return;
        refreshRef.current.refreshFilters();
        refreshRef.current.refreshStrategies();
    }, [open]);

    const search = searchValue.trim();
    const searchUpper = search.toUpperCase();
    const setSearch = onSearchChange || (() => { });

    // Detectar prefijo SC para scanner
    const hasScPrefix = searchUpper.startsWith('SC');

    // Detectar prefijo EVN para eventos
    const hasEvnPrefix = searchUpper.startsWith('EVN');

    const isExactCommand = searchUpper in GLOBAL_COMMANDS;

    // Detectar si parece un ticker (letras mayúsculas sin espacios). No se trata
    // como ticker si coincide exactamente con un código de comando conocido.
    const looksLikeTicker = TICKER_LIKE_REGEX.test(searchUpper)
        && !hasScPrefix
        && !hasEvnPrefix
        && !COMMAND_KEYS.has(searchUpper)
        && !isExactCommand;

    // Buscar tickers cuando parece un ticker
    useEffect(() => {
        if (!open) {
            // Limpiar cuando se cierra
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
                abortControllerRef.current = null;
            }
            return;
        }

        if (looksLikeTicker && search.length >= 1) {
            // Cancelar búsqueda anterior
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
            // Crear nuevo controller
            const controller = new AbortController();
            abortControllerRef.current = controller;

            setLoadingTickers(true);

            const timer = setTimeout(async () => {
                try {
                    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
                    const response = await fetch(
                        `${apiUrl}/api/v1/metadata/search?q=${encodeURIComponent(search)}&limit=8`,
                        { signal: controller.signal }
                    );

                    if (response.ok) {
                        const data = await response.json();
                        setTickerResults(data.results || []);
                    }
                } catch (err: any) {
                    if (err.name !== 'AbortError') {
                        console.error('Error searching tickers:', err);
                    }
                } finally {
                    setLoadingTickers(false);
                }
            }, 150);

            return () => {
                clearTimeout(timer);
                controller.abort();
            };
        } else {
            setTickerResults([]);
            if (!search.includes(' ')) {
                setSelectedTicker(null);
            }
        }
    }, [search, looksLikeTicker, open]);

    // Quotes: 1 request batch por cambio de resultados + refresco cada 4s
    useEffect(() => {
        if (!open || tickerResults.length === 0) {
            setQuotes({});
            return;
        }
        let cancelled = false;
        const symbols = tickerResults.map(r => r.symbol).join(',');
        const fetchQuotes = async () => {
            try {
                const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
                const res = await fetch(`${apiUrl}/api/v1/realtime/quotes?symbols=${encodeURIComponent(symbols)}`);
                if (res.ok && !cancelled) {
                    const data = await res.json();
                    setQuotes(data.quotes || {});
                }
            } catch { /* sin quote no pasa nada: la fila se pinta sin precio */ }
        };
        fetchQuotes();
        const interval = setInterval(fetchQuotes, 4000);
        return () => { cancelled = true; clearInterval(interval); };
    }, [open, tickerResults]);

    // News stories del ticker tecleado (desde el store en memoria: 0 requests)
    const newsMatches = useMemo(() => {
        if (!open || !looksLikeTicker || selectedTicker) return [];
        const exact = allArticles.filter(a => a.tickers?.some(tk => tk.toUpperCase() === searchUpper));
        if (exact.length > 0) return exact.slice(0, 4);
        const top = tickerResults[0]?.symbol?.toUpperCase();
        if (!top) return [];
        return allArticles.filter(a => a.tickers?.some(tk => tk.toUpperCase() === top)).slice(0, 4);
    }, [open, looksLikeTicker, selectedTicker, allArticles, searchUpper, tickerResults]);

    // Generar items a mostrar (memoizado para estabilidad de referencia)
    const items = useMemo(
        () => getDisplayItems(
            parseTerminalCommand(search, t),
            hasScPrefix, hasEvnPrefix, search, tickerResults, selectedTicker, t, userScans, userStrategies, newsMatches,
        ),
        [search, hasScPrefix, hasEvnPrefix, tickerResults, selectedTicker, t, userScans, userStrategies, newsMatches],
    );

    // ── Selección estable ──────────────────────────────────────────────
    // La lista se reconstruye en background (llegan tickers, se refrescan
    // scans/estrategias...). La selección del usuario NO debe resetearse por
    // eso: se preserva por id de item. Solo se recalcula la autoselección
    // cuando cambia el TEXTO buscado o cuando el item resaltado desaparece.
    const itemsSig = useMemo(() => items.map(i => i.id).join('|'), [items]);
    const itemsRef = useRef(items);
    itemsRef.current = items;
    const selectedIdRef = useRef<string | null>(null);
    const userNavigatedRef = useRef(false);

    // Al teclear, la navegación manual previa deja de aplicar.
    useEffect(() => { userNavigatedRef.current = false; }, [searchUpper]);

    // Al abrir, empezar limpio.
    useEffect(() => {
        if (open) {
            userNavigatedRef.current = false;
            selectedIdRef.current = null;
            setSelectedIndex(0);
        }
    }, [open]);

    useEffect(() => {
        const list = itemsRef.current;
        if (list.length === 0) {
            setSelectedIndex(0);
            selectedIdRef.current = null;
            return;
        }

        // Si el usuario ya navegó con flechas/ratón, mantener SU selección
        // aunque la lista se haya regenerado.
        if (userNavigatedRef.current && selectedIdRef.current) {
            const keep = list.findIndex(it => it.id === selectedIdRef.current);
            if (keep >= 0) {
                setSelectedIndex(keep);
                return;
            }
        }

        // Autoseleccionar: si lo último tecleado coincide exactamente con el
        // código de un comando (p.ej. "AAPL FA" -> "FA", o "DESC"), resaltar
        // ese comando para que Enter lo ejecute. Si no, el primero.
        const tokens = searchUpper.split(/\s+/).filter(Boolean);
        const last = tokens[tokens.length - 1] || '';
        let idx = -1;
        if (last) {
            idx = list.findIndex(it =>
                (it.type === 'ticker-command' || it.type === 'global-command') && it.label === last);
        }
        const next = idx >= 0 ? idx : 0;
        setSelectedIndex(next);
        selectedIdRef.current = list[next]?.id ?? null;
    }, [searchUpper, itemsSig]);

    // Mover la selección desde teclado o ratón: registra la intención del
    // usuario y el id para preservarla ante regeneraciones de la lista.
    const moveSelection = useCallback((index: number) => {
        const list = itemsRef.current;
        if (list.length === 0) return;
        const clamped = ((index % list.length) + list.length) % list.length; // circular
        userNavigatedRef.current = true;
        selectedIdRef.current = list[clamped]?.id ?? null;
        setSelectedIndex(clamped);
    }, []);

    // Scroll to selected
    useEffect(() => {
        if (listRef.current && items.length > 0) {
            const el = listRef.current.querySelector(`[data-index="${selectedIndex}"]`);
            el?.scrollIntoView({ block: 'nearest' });
        }
    }, [selectedIndex, items.length]);

    // Keyboard navigation. Lee el estado vivo desde refs: el listener se
    // registra una sola vez por apertura y nunca pierde pulsaciones por
    // re-suscripciones entre renders.
    const keyStateRef = useRef({ selectedIndex, search, selectedTicker });
    keyStateRef.current = { selectedIndex, search, selectedTicker };
    const handleSelectRef = useRef<(item: DisplayItem) => void>(() => { });

    useEffect(() => {
        if (!open) return;

        const handleKeyDown = (e: KeyboardEvent) => {
            const { selectedIndex: idx, search: q, selectedTicker: tk } = keyStateRef.current;
            const list = itemsRef.current;

            switch (e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    moveSelection(idx + 1);
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    moveSelection(idx - 1);
                    break;
                case 'PageDown':
                    e.preventDefault();
                    moveSelection(Math.min(idx + 8, list.length - 1));
                    break;
                case 'PageUp':
                    e.preventDefault();
                    moveSelection(Math.max(idx - 8, 0));
                    break;
                case 'Enter':
                    e.preventDefault();
                    if (list[idx]) handleSelectRef.current(list[idx]);
                    break;
                case 'Tab':
                    e.preventDefault();
                    if (list[idx]?.autocomplete) {
                        setSearch(list[idx].autocomplete!);
                    }
                    break;
                case 'Escape':
                    e.preventDefault();
                    // Escape por niveles: primero sale del contexto de ticker,
                    // luego limpia lo escrito, y con el prompt vacío cierra.
                    if (tk) {
                        setSelectedTicker(null);
                        setSearch('');
                    } else if (q) {
                        setSearch('');
                    } else {
                        onOpenChange(false);
                    }
                    break;
                case 'Backspace':
                    if (q === '' && tk) {
                        setSelectedTicker(null);
                    }
                    break;
            }
        };

        // Fase de captura: garantiza recibir las teclas aunque algún componente
        // intermedio haga stopPropagation en el camino input -> document.
        document.addEventListener('keydown', handleKeyDown, true);
        return () => document.removeEventListener('keydown', handleKeyDown, true);
    }, [open, onOpenChange, setSearch, moveSelection]);

    // Cerrar al hacer click fuera (manejado por overlay en el render)

    const handleSelect = useCallback((item: DisplayItem) => {
        switch (item.type) {
            case 'instrument':
                // Seleccionar el ticker y mostrar comandos
                if (item.tickerData) {
                    setSelectedTicker(item.tickerData);
                    setSearch(item.tickerData.symbol + ' ');
                }
                break;

            case 'ticker-command':
                if (item.ticker && item.commandId) {
                    // Pasar el exchange del ticker seleccionado
                    onExecuteTickerCommand?.(item.ticker, item.commandId, selectedTicker?.exchange);
                }
                setSearch('');
                setSelectedTicker(null);
                onOpenChange(false);
                break;

            case 'global-command':
                if (item.commandId === 'help') {
                    onOpenHelp?.();
                } else if (item.commandId === 'sc') {
                    // SC - muestra categorías del scanner
                    setSearch('SC ');
                    return;
                } else if (item.commandId === 'evn') {
                    // EVN es especial - muestra categorías de eventos
                    setSearch('EVN ');
                    return;
                } else if (item.commandId) {
                    executeCommand(item.commandId);
                }
                setSearch('');
                setSelectedTicker(null);
                onOpenChange(false);
                break;

            case 'scanner':
                if (item.scannerId) {
                    openScannerTable(item.scannerId, 0);
                }
                setSearch('');
                setSelectedTicker(null);
                onOpenChange(false);
                break;

            case 'user-scanner':
                if (item.userFilter) {
                    openUserScanTable(item.userFilter);
                }
                setSearch('');
                setSelectedTicker(null);
                onOpenChange(false);
                break;

            case 'event':
                if (item.eventId) {
                    openEventTable(item.eventId, 0);
                }
                setSearch('');
                setSelectedTicker(null);
                onOpenChange(false);
                break;

            case 'user-strategy':
                if (item.strategyData) {
                    openUserStrategyTable(item.strategyData);
                }
                setSearch('');
                setSelectedTicker(null);
                onOpenChange(false);
                break;

            case 'news':
                if (item.newsData) {
                    const articleId = String(item.newsData.benzinga_id || item.newsData.id || '');
                    openNewsWithArticle(articleId, item.newsData.tickers?.[0]);
                }
                setSearch('');
                setSelectedTicker(null);
                onOpenChange(false);
                break;
        }
    }, [executeCommand, openScannerTable, openUserScanTable, openEventTable, openUserStrategyTable, openNewsWithArticle, onOpenChange, onOpenHelp, onExecuteTickerCommand, setSearch, selectedTicker]);
    handleSelectRef.current = handleSelect;

    if (!open) return null;

    const handleClose = () => {
        setSearch('');
        setSelectedTicker(null);
        onOpenChange(false);
    };

    return (
        <>
            {/* Overlay invisible para cerrar al hacer click fuera */}
            <div
                className="fixed inset-0"
                style={{ zIndex: Z_INDEX.MODAL_BASE }}
                onClick={handleClose}
            />

            <div
                data-terminal-palette
                className="fixed left-3 top-11 animate-slideDown"
                style={{
                    zIndex: Z_INDEX.MODAL_BASE + 1,
                    maxHeight: 'calc(100vh - 80px)',
                    width: 'calc(42% - 2rem)',
                    minWidth: '480px',
                    maxWidth: '640px',
                }}
            >
                <div className="border border-border bg-surface shadow-xl overflow-hidden">
                    {/* Header con ticker seleccionado */}
                    <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-surface-hover">
                        <div className="flex items-center gap-2">
                            {selectedTicker ? (
                                <>
                                    <span className="text-[10px] text-muted-fg uppercase tracking-wide font-mono">Commands for</span>
                                    <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold border border-blue-500/40 bg-blue-500/10 text-blue-600 dark:text-blue-400 rounded">
                                        {selectedTicker.symbol}
                                    </span>
                                </>
                            ) : (
                                <span className="text-[10px] text-muted-fg uppercase tracking-wide font-mono">
                                    {hasScPrefix ? 'Scanner' : hasEvnPrefix ? 'Events' : looksLikeTicker && tickerResults.length > 0 ? 'Instruments' : 'Commands'}
                                </span>
                            )}
                            {loadingTickers && <Loader2 className="w-3 h-3 text-muted-fg animate-spin" />}
                        </div>
                        <button
                            onClick={() => {
                                onOpenChange(false);
                                setSearch('');
                                setSelectedTicker(null);
                            }}
                            className="text-muted-fg hover:text-foreground"
                        >
                            <X className="w-3 h-3" />
                        </button>
                    </div>

                    {/* List */}
                    <div
                        ref={listRef}
                        className="overflow-y-auto"
                        style={{ maxHeight: 'calc(100vh - 220px)' }}
                    >
                        {items.length === 0 ? (
                            <div className="py-6 text-center text-[11px] text-muted-fg">
                                {loadingTickers ? t('common.loading') : t('common.noResults')}
                            </div>
                        ) : (
                            <div className="pb-1">
                                {items.map((item, index) => {
                                    const quote = item.type === 'instrument' && item.tickerData
                                        ? quotes[item.tickerData.symbol]
                                        : undefined;
                                    const chip = item.type === 'instrument'
                                        ? instrumentChip(item.tickerData?.security_type || item.tickerData?.type)
                                        : null;
                                    const showSectionHeader = index === 0 || items[index - 1].section !== item.section;

                                    return (
                                        <div key={item.id}>
                                            {showSectionHeader && (
                                                <div className="px-3 py-[3px] text-[9px] font-mono font-semibold uppercase tracking-[0.15em] text-muted-fg bg-surface-inset border-y border-border-subtle select-none">
                                                    {item.section}
                                                </div>
                                            )}
                                            <div
                                                data-index={index}
                                                onClick={() => handleSelect(item)}
                                                // onMouseMove (no onMouseEnter): si el scroll por
                                                // teclado desplaza filas bajo un cursor quieto, el
                                                // ratón no roba la selección.
                                                onMouseMove={() => { if (selectedIndex !== index) moveSelection(index); }}
                                                className={`flex items-center gap-2 pl-2.5 pr-3 py-[5px] cursor-pointer border-l-2 transition-colors ${
                                                    index === selectedIndex
                                                        ? 'border-l-blue-500 bg-blue-500/[0.07]'
                                                        : 'border-l-transparent hover:bg-foreground/[0.03]'
                                                }`}
                                            >
                                                {/* Instrument row */}
                                                {item.type === 'instrument' && item.tickerData && chip && (
                                                    <>
                                                        <span className={`px-1 py-0.5 text-[9px] font-mono font-bold border rounded ${chip.cls}`}>
                                                            {chip.label}
                                                        </span>
                                                        <span className="text-[11px] font-mono font-bold text-foreground w-14">
                                                            {item.tickerData.symbol}
                                                        </span>
                                                        <span className="text-[9px] text-muted-fg font-mono w-7 uppercase">
                                                            {item.tickerData.exchange?.slice(0, 3) || 'US'}
                                                        </span>
                                                        <span className="text-[10px] text-foreground/75 flex-1 truncate">
                                                            {item.tickerData.name}
                                                        </span>
                                                        {quote && quote.price > 0 && (
                                                            <span className="flex items-center gap-1.5 font-mono text-[10px] tabular-nums shrink-0">
                                                                <span className="text-foreground font-semibold">
                                                                    ${quote.price >= 1000 ? quote.price.toFixed(0) : quote.price.toFixed(2)}
                                                                </span>
                                                                {quote.change_percent != null && (
                                                                    <span className={quote.change_percent >= 0 ? 'text-emerald-500' : 'text-rose-500'}>
                                                                        {quote.change_percent >= 0 ? '▲' : '▼'}{Math.abs(quote.change_percent).toFixed(2)}%
                                                                    </span>
                                                                )}
                                                            </span>
                                                        )}
                                                    </>
                                                )}

                                                {/* News row */}
                                                {item.type === 'news' && item.newsData && (
                                                    <>
                                                        <span className="text-[9px] font-mono text-muted-fg w-10 shrink-0 tabular-nums">
                                                            {formatPaletteTime(item.newsData.published)}
                                                        </span>
                                                        {item.newsData.isLive && (
                                                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shrink-0" />
                                                        )}
                                                        <span className="text-[10px] text-foreground/90 flex-1 truncate italic">
                                                            {decodeHtmlEntities(item.newsData.title)}
                                                        </span>
                                                        <span className="text-[9px] text-muted-fg truncate max-w-[90px] shrink-0">
                                                            {item.newsData.author}
                                                        </span>
                                                    </>
                                                )}

                                                {/* Command row */}
                                                {item.type !== 'instrument' && item.type !== 'news' && (
                                                    <>
                                                        <span className={`px-1.5 py-0.5 text-[10px] font-mono font-semibold border rounded min-w-[60px] text-center ${
                                                            item.type === 'user-strategy' ? 'border-emerald-500/40 text-emerald-700 dark:text-emerald-400 bg-emerald-500/10' :
                                                            item.isUserScan ? 'border-amber-500/40 text-amber-700 dark:text-amber-400 bg-amber-500/10' :
                                                            'border-border text-foreground bg-surface-inset/50'
                                                        }`}>
                                                            {item.label}
                                                        </span>
                                                        <span className="text-[10px] text-muted-fg flex-1 truncate">
                                                            {item.description}
                                                        </span>
                                                        {item.isUserScan && (
                                                            <span className="text-[9px] text-muted-fg font-mono">(scan)</span>
                                                        )}
                                                        {item.type === 'user-strategy' && (
                                                            <span className="text-[9px] text-emerald-500 font-mono">(strategy)</span>
                                                        )}
                                                        {item.shortcut && (
                                                            <span className="text-[9px] text-muted-fg font-mono">
                                                                {item.shortcut}
                                                            </span>
                                                        )}
                                                    </>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>

                    {/* Footer */}
                    <div className="flex items-center justify-between px-3 py-1 border-t border-border bg-surface-hover">
                        <div className="flex items-center gap-3 text-[9px] text-muted-fg font-mono">
                            <span>↑↓ nav</span>
                            <span>Tab complete</span>
                            <span>Enter select</span>
                            <span>Esc back</span>
                            {items.length > 0 && <span className="text-foreground/60">{items.length} results</span>}
                        </div>
                        <button
                            onClick={onOpenHelp}
                            className="text-[9px] text-muted-fg hover:text-primary font-mono"
                        >
                            ? help
                        </button>
                    </div>
                </div>
            </div>
        </>
    );
}

// Types
interface DisplayItem {
    id: string;
    type: 'instrument' | 'ticker-command' | 'global-command' | 'scanner' | 'user-scanner' | 'event' | 'user-strategy' | 'news';
    section: string;
    label: string;
    description: string;
    shortcut?: string | null;
    autocomplete?: string;
    ticker?: string;
    commandId?: string;
    scannerId?: string;
    eventId?: string;
    tickerData?: TickerResult;
    userFilter?: UserFilter;
    isUserScan?: boolean;
    strategyData?: { id: number; name: string; eventTypes: string[]; filters: Record<string, any> };
    newsData?: NewsArticle;
}

function getDisplayItems(
    parsed: ReturnType<typeof parseTerminalCommand>,
    hasScPrefix: boolean,
    hasEvnPrefix: boolean,
    search: string,
    tickerResults: TickerResult[],
    selectedTicker: TickerResult | null,
    t: (key: string) => string,
    userScans: UserFilter[] = [],
    userStrategies: AlertStrategy[] = [],
    newsMatches: NewsArticle[] = []
): DisplayItem[] {
    // Contexto de ticker: bien un instrumento ya seleccionado, bien un ticker
    // tecleado en una sola línea ("AAPL FA"). En ambos casos mostramos los
    // comandos de ticker, filtrados por lo que se haya escrito tras el símbolo.
    const contextTicker = selectedTicker?.symbol
        || (parsed.ticker && search.includes(' ') ? parsed.ticker : null);
    if (contextTicker) {
        const rest = search.toUpperCase().slice(contextTicker.length).trim();
        const all = Object.entries(TICKER_COMMANDS);
        const filtered = rest
            ? all.filter(([key, cmd]) => key.startsWith(rest) || cmd.name.toUpperCase().includes(rest))
            : all;
        const list = filtered.length ? filtered : all;
        return list.map(([key, cmd]) => ({
            id: `cmd-${cmd.id}`,
            type: 'ticker-command' as const,
            section: 'COMMANDS',
            label: key,
            description: t(cmd.descriptionKey),
            shortcut: cmd.shortcut,
            ticker: contextTicker,
            commandId: cmd.id,
            autocomplete: `${contextTicker} ${key}`,
        }));
    }

    // Si es prefijo EVN, mostrar categorías de eventos
    if (hasEvnPrefix) {
        const filter = search.toUpperCase().replace('EVN', '').trim();

        // System event categories
        const eventItems: DisplayItem[] = SYSTEM_EVENT_CATEGORIES
            .filter(cat => !filter || cat.label.toUpperCase().includes(filter) || cat.id.toUpperCase().includes(filter))
            .map(cat => ({
                id: `event-${cat.id}`,
                type: 'event' as const,
                section: 'EVENTS',
                label: cat.label,
                description: cat.description,
                eventId: cat.id,
                autocomplete: `EVN ${cat.label}`,
            }));

        // User alert strategies
        const strategyItems: DisplayItem[] = userStrategies
            .filter(s => !filter || s.name.toUpperCase().includes(filter))
            .map(s => ({
                id: `user-strategy-${s.id}`,
                type: 'user-strategy' as const,
                section: 'MY STRATEGIES',
                label: s.name,
                description: `${s.eventTypes.length} alerts · ${s.category || 'custom'}`,
                strategyData: { id: s.id, name: s.name, eventTypes: s.eventTypes, filters: s.filters as Record<string, any> },
                autocomplete: `EVN ${s.name}`,
            }));

        return [...eventItems, ...strategyItems];
    }

    // Si es prefijo SC, mostrar categorías del scanner + user scans
    if (hasScPrefix) {
        const filter = search.toUpperCase().replace('SC', '').trim();

        // System scanner commands
        const systemItems: DisplayItem[] = SCANNER_COMMANDS
            .filter(cmd => !filter || cmd.label.toUpperCase().includes(filter))
            .map(cmd => ({
                id: `scanner-${cmd.id}`,
                type: 'scanner' as const,
                section: 'SCANNER',
                label: cmd.label,
                description: cmd.description,
                scannerId: cmd.id,
                autocomplete: `SC ${cmd.label}`,
            }));

        // User scanner commands
        const userItems: DisplayItem[] = userScans
            .filter(scan => !filter || scan.name.toUpperCase().includes(filter))
            .map(scan => {
                // Contar solo filtros con valores no-null
                const activeFilters = Object.values(scan.parameters || {}).filter(v => v != null).length;
                return {
                    id: `user-scanner-${scan.id}`,
                    type: 'user-scanner' as const,
                    section: 'MY SCANS',
                    label: scan.name,
                    description: scan.enabled ? `${activeFilters} filters` : '(disabled)',
                    userFilter: scan,
                    isUserScan: true,
                    autocomplete: `SC ${scan.name}`,
                };
            });

        // Devolver system primero, luego user scans
        return [...systemItems, ...userItems];
    }

    // Buscar comandos globales que coincidan
    const matchingCommands: DisplayItem[] = [];
    Object.entries(GLOBAL_COMMANDS).forEach(([key, cmd]) => {
        const searchUpper = search.toUpperCase();
        if (!search || key.startsWith(searchUpper) || cmd.name.toUpperCase().startsWith(searchUpper)) {
            matchingCommands.push({
                id: `global-${cmd.id}`,
                type: 'global-command' as const,
                section: 'COMMANDS',
                label: key,
                description: t(cmd.descriptionKey),
                shortcut: 'shortcut' in cmd ? cmd.shortcut : undefined,
                commandId: cmd.id,
                autocomplete: key,
            });
        }
    });

    // Instrumentos (con quote en vivo pintado en el render)
    const tickerItems: DisplayItem[] = tickerResults.map(ticker => ({
        id: `ticker-${ticker.symbol}-${ticker.exchange}`,
        type: 'instrument' as const,
        section: 'INSTRUMENTS',
        label: ticker.symbol,
        description: ticker.name,
        tickerData: ticker,
        autocomplete: ticker.symbol + ' ',
    }));

    // News stories del ticker (desde el NewsStore en memoria)
    const newsItems: DisplayItem[] = newsMatches.map(article => ({
        id: `news-${article.benzinga_id || article.id}`,
        type: 'news' as const,
        section: 'NEWS STORIES',
        label: article.tickers?.[0] || '',
        description: article.title,
        newsData: article,
    }));

    // Orden: comandos → instrumentos → noticias
    return [...matchingCommands, ...tickerItems, ...newsItems];
}

export default TerminalPalette;

