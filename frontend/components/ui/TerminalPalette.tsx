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
    const { executeCommand, openScannerTable, openUserScanTable, openEventTable, openUserStrategyTable } = useCommandExecutor();

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

    // Generar items a mostrar (memoizado para estabilidad de referencia)
    const items = useMemo(
        () => getDisplayItems(
            parseTerminalCommand(search, t),
            hasScPrefix, hasEvnPrefix, search, tickerResults, selectedTicker, t, userScans, userStrategies,
        ),
        [search, hasScPrefix, hasEvnPrefix, tickerResults, selectedTicker, t, userScans, userStrategies],
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
        }
    }, [executeCommand, openScannerTable, openUserScanTable, openEventTable, openUserStrategyTable, onOpenChange, onOpenHelp, onExecuteTickerCommand, setSearch, selectedTicker]);
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
                    width: 'calc(40% - 2rem)',
                    minWidth: '450px',
                    maxWidth: '600px',
                }}
            >
                <div className="border border-border bg-surface shadow-xl overflow-hidden">
                    {/* Header con ticker seleccionado */}
                    <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-surface-hover">
                        <div className="flex items-center gap-2">
                            {selectedTicker ? (
                                <>
                                    <span className="text-[10px] text-muted-fg uppercase tracking-wide font-mono">Commands for</span>
                                    <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold bg-primary/15 text-primary rounded">
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
                            <div className="py-1">
                                {items.map((item, index) => (
                                    <div
                                        key={item.id}
                                        data-index={index}
                                        onClick={() => handleSelect(item)}
                                        // onMouseMove (no onMouseEnter): si el scroll por
                                        // teclado desplaza filas bajo un cursor quieto, el
                                        // ratón no roba la selección.
                                        onMouseMove={() => { if (selectedIndex !== index) moveSelection(index); }}
                                        className={`flex items-center gap-2 px-3 py-1.5 cursor-pointer transition-colors
                                        ${index === selectedIndex ? 'bg-primary/10' : ''}`}
                                    >
                                        {/* Instrument row */}
                                        {item.type === 'instrument' && item.tickerData && (
                                            <>
                                                <span className="px-1 py-0.5 text-[9px] font-bold bg-primary text-white rounded">
                                                    EQ
                                                </span>
                                                <span className="text-[11px] font-mono font-semibold text-foreground w-12">
                                                    {item.tickerData.symbol}
                                                </span>
                                                <span className="text-[9px] text-muted-fg font-mono w-6">
                                                    {item.tickerData.exchange?.slice(0, 2) || 'US'}
                                                </span>
                                                <span className="text-[10px] text-foreground/80 flex-1 truncate">
                                                    {item.tickerData.name}
                                                </span>
                                            </>
                                        )}

                                        {/* Command row */}
                                        {item.type !== 'instrument' && (
                                            <>
                                                <span className={`px-1.5 py-0.5 text-[10px] font-mono font-semibold border rounded min-w-[60px] text-center ${
                                                    item.type === 'user-strategy' ? 'border-emerald-500/40 text-emerald-700 dark:text-emerald-400 bg-emerald-500/10' :
                                                    item.isUserScan ? 'border-amber-500/40 text-amber-700 dark:text-amber-400 bg-amber-500/10' :
                                                    'border-border text-foreground'
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
                                ))}
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
    type: 'instrument' | 'ticker-command' | 'global-command' | 'scanner' | 'user-scanner' | 'event' | 'user-strategy';
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
    userStrategies: AlertStrategy[] = []
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
                label: key,
                description: t(cmd.descriptionKey),
                shortcut: 'shortcut' in cmd ? cmd.shortcut : undefined,
                commandId: cmd.id,
                autocomplete: key,
            });
        }
    });

    // Si hay resultados de búsqueda de tickers, combinarlos con comandos
    if (tickerResults.length > 0) {
        const tickerItems = tickerResults.map(ticker => ({
            id: `ticker-${ticker.symbol}-${ticker.exchange}`,
            type: 'instrument' as const,
            label: ticker.symbol,
            description: ticker.name,
            tickerData: ticker,
            autocomplete: ticker.symbol + ' ',
        }));

        // Si hay comandos que coinciden, mostrarlos primero, luego los tickers
        if (matchingCommands.length > 0) {
            return [...matchingCommands, ...tickerItems];
        }

        // Si no hay comandos, solo mostrar tickers
        return tickerItems;
    }

    // Si no hay tickers, mostrar comandos globales
    return matchingCommands;
}

export default TerminalPalette;

