'use client';

import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Loader2 } from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { parseTerminalCommand, TICKER_COMMANDS, GLOBAL_COMMANDS } from '@/lib/terminal-parser';
import { useUserFilters } from '@/hooks/useUserFilters';
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
    const { executeCommand, openScannerTable, openUserScanTable } = useCommandExecutor();

    // User scans - refrescar cada vez que se abre el palette
    const { filters: userScans, loading: userScansLoading, refreshFilters } = useUserFilters();

    // Refrescar filtros cuando se abre el palette
    useEffect(() => {
        if (open) {
            refreshFilters();
        }
    }, [open, refreshFilters]);

    const search = searchValue.trim();
    const setSearch = onSearchChange || (() => { });

    // Parsear el comando con traducción
    const parsed = parseTerminalCommand(search, t);

    // Detectar prefijo SC para scanner
    const hasScPrefix = search.toUpperCase().startsWith('SC');

    // Verificar si hay comandos globales que empiecen con la búsqueda
    const searchUpper = search.toUpperCase();
    const hasMatchingCommands = Object.keys(GLOBAL_COMMANDS).some(
        key => key.startsWith(searchUpper)
    );
    const isExactCommand = searchUpper in GLOBAL_COMMANDS;

    // Detectar si parece un ticker (letras mayúsculas sin espacios)
    // No tratar como ticker si es un comando exacto
    const looksLikeTicker = /^[A-Z]{1,5}$/.test(searchUpper)
        && !hasScPrefix
        && !['SC', 'IPO', 'SET', 'HELP', 'FILTERS', 'ALERTS', 'NOTE', 'CHAT', 'NEWS', 'PM', 'PRT', 'GR', 'SCREEN', 'MP', 'INSIDER', 'ERN', 'PREDICT', 'HM'].includes(searchUpper)
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

    // Reset selectedIndex cuando cambia la búsqueda
    useEffect(() => {
        setSelectedIndex(0);
    }, [search]);

    // Generar items a mostrar
    const items = getDisplayItems(parsed, hasScPrefix, search, tickerResults, selectedTicker, t, userScans);

    // Scroll to selected
    useEffect(() => {
        if (listRef.current && items.length > 0) {
            const el = listRef.current.querySelector(`[data-index="${selectedIndex}"]`);
            el?.scrollIntoView({ block: 'nearest' });
        }
    }, [selectedIndex, items.length]);

    // Keyboard navigation
    useEffect(() => {
        if (!open) return;

        const handleKeyDown = (e: KeyboardEvent) => {
            switch (e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    setSelectedIndex(prev => Math.min(prev + 1, items.length - 1));
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    setSelectedIndex(prev => Math.max(prev - 1, 0));
                    break;
                case 'Enter':
                    e.preventDefault();
                    if (items[selectedIndex]) {
                        handleSelect(items[selectedIndex]);
                    }
                    break;
                case 'Tab':
                    e.preventDefault();
                    if (items[selectedIndex]?.autocomplete) {
                        setSearch(items[selectedIndex].autocomplete);
                    }
                    break;
                case 'Escape':
                    e.preventDefault();
                    setSearch('');
                    setSelectedTicker(null);
                    onOpenChange(false);
                    break;
                case 'Backspace':
                    if (search === '' && selectedTicker) {
                        setSelectedTicker(null);
                    }
                    break;
            }
        };

        document.addEventListener('keydown', handleKeyDown);
        return () => document.removeEventListener('keydown', handleKeyDown);
    }, [open, items, selectedIndex, onOpenChange, setSearch, search, selectedTicker]);

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
                    // SC es especial - muestra categorías del scanner
                    setSearch('SC ');
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
        }
    }, [executeCommand, openScannerTable, openUserScanTable, onOpenChange, onOpenHelp, onExecuteTickerCommand, setSearch, selectedTicker]);

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
                className="fixed left-4 top-12 animate-slideDown"
                style={{
                    zIndex: Z_INDEX.MODAL_BASE + 1,
                    maxHeight: 'calc(100vh - 80px)',
                    width: 'calc(40% - 2rem)',
                    minWidth: '450px',
                    maxWidth: '600px',
                }}
            >
                <div className="border border-slate-200 bg-white shadow-xl overflow-hidden">
                    {/* Header con ticker seleccionado */}
                    <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-200 bg-slate-50">
                        <div className="flex items-center gap-2">
                            {selectedTicker ? (
                                <>
                                    <span className="text-[10px] text-slate-400 uppercase tracking-wide font-mono">Commands for</span>
                                    <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold bg-blue-100 text-blue-700 rounded">
                                        {selectedTicker.symbol}
                                    </span>
                                </>
                            ) : (
                                <span className="text-[10px] text-slate-400 uppercase tracking-wide font-mono">
                                    {hasScPrefix ? 'Scanner' : looksLikeTicker && tickerResults.length > 0 ? 'Instruments' : 'Commands'}
                                </span>
                            )}
                            {loadingTickers && <Loader2 className="w-3 h-3 text-slate-400 animate-spin" />}
                        </div>
                        <button
                            onClick={() => {
                                onOpenChange(false);
                                setSearch('');
                                setSelectedTicker(null);
                            }}
                            className="text-slate-400 hover:text-slate-600"
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
                            <div className="py-6 text-center text-[11px] text-slate-400">
                                {loadingTickers ? t('common.loading') : t('common.noResults')}
                            </div>
                        ) : (
                            <div className="py-1">
                                {items.map((item, index) => (
                                    <div
                                        key={item.id}
                                        data-index={index}
                                        onClick={() => handleSelect(item)}
                                        className={`flex items-center gap-2 px-3 py-1.5 cursor-pointer transition-colors
                                        ${index === selectedIndex ? 'bg-blue-50' : 'hover:bg-slate-50'}`}
                                    >
                                        {/* Instrument row */}
                                        {item.type === 'instrument' && item.tickerData && (
                                            <>
                                                <span className="px-1 py-0.5 text-[9px] font-bold bg-blue-600 text-white rounded">
                                                    EQ
                                                </span>
                                                <span className="text-[11px] font-mono font-semibold text-slate-800 w-12">
                                                    {item.tickerData.symbol}
                                                </span>
                                                <span className="text-[9px] text-slate-400 font-mono w-6">
                                                    {item.tickerData.exchange?.slice(0, 2) || 'US'}
                                                </span>
                                                <span className="text-[10px] text-slate-600 flex-1 truncate">
                                                    {item.tickerData.name}
                                                </span>
                                            </>
                                        )}

                                        {/* Command row */}
                                        {item.type !== 'instrument' && (
                                            <>
                                                <span className="px-1.5 py-0.5 text-[10px] font-mono font-semibold border border-slate-200 text-slate-700 rounded min-w-[60px] text-center">
                                                    {item.label}
                                                </span>
                                                <span className="text-[10px] text-slate-500 flex-1 truncate">
                                                    {item.description}
                                                </span>
                                                {item.isUserScan && (
                                                    <span className="text-[9px] text-slate-400 font-mono">(custom)</span>
                                                )}
                                                {item.shortcut && (
                                                    <span className="text-[9px] text-slate-400 font-mono">
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
                    <div className="flex items-center justify-between px-3 py-1 border-t border-slate-200 bg-slate-50">
                        <div className="flex items-center gap-3 text-[9px] text-slate-400 font-mono">
                            <span>↑↓ nav</span>
                            <span>Tab complete</span>
                            <span>Enter select</span>
                        </div>
                        <button
                            onClick={onOpenHelp}
                            className="text-[9px] text-slate-400 hover:text-blue-600 font-mono"
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
    type: 'instrument' | 'ticker-command' | 'global-command' | 'scanner' | 'user-scanner';
    label: string;
    description: string;
    shortcut?: string | null;
    autocomplete?: string;
    ticker?: string;
    commandId?: string;
    scannerId?: string;
    tickerData?: TickerResult;
    userFilter?: UserFilter;
    isUserScan?: boolean;
}

function getDisplayItems(
    parsed: ReturnType<typeof parseTerminalCommand>,
    hasScPrefix: boolean,
    search: string,
    tickerResults: TickerResult[],
    selectedTicker: TickerResult | null,
    t: (key: string) => string,
    userScans: UserFilter[] = []
): DisplayItem[] {
    // Si hay un ticker seleccionado, mostrar comandos para ese ticker
    if (selectedTicker) {
        return Object.entries(TICKER_COMMANDS).map(([key, cmd]) => ({
            id: `cmd-${cmd.id}`,
            type: 'ticker-command' as const,
            label: key,
            description: t(cmd.descriptionKey),
            shortcut: cmd.shortcut,
            ticker: selectedTicker.symbol,
            commandId: cmd.id,
            autocomplete: `${selectedTicker.symbol} ${key}`,
        }));
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
