'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import {
    TrendingUp,
    TrendingDown,
    Zap,
    Trophy,
    AlertTriangle,
    BarChart3,
    X,
    ArrowUp,
    ArrowDown,
    LayoutGrid,
    FileText,
    DollarSign,
    Newspaper,
    LineChart,
    HelpCircle,
    Settings,
    Rocket,
    ScanSearch,
    Loader2,
} from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { parseTerminalCommand, TICKER_COMMANDS, GLOBAL_COMMANDS } from '@/lib/terminal-parser';

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

// Iconos para cada comando
const COMMAND_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
    'graph': LineChart,
    'dilution-tracker': BarChart3,
    'financials': DollarSign,
    'sec-filings': FileText,
    'news': Newspaper,
    'scanner': LayoutGrid,
    'ipo': Rocket,
    'settings': Settings,
    'help': HelpCircle,
};

// Scanner commands
const SCANNER_COMMANDS = [
    { id: 'gappers_up', label: 'Gap Up', description: 'Gap up >= 2%', icon: TrendingUp },
    { id: 'gappers_down', label: 'Gap Down', description: 'Gap down <= -2%', icon: TrendingDown },
    { id: 'momentum_up', label: 'Momentum Up', description: 'Cambio >= 3%', icon: ArrowUp },
    { id: 'momentum_down', label: 'Momentum Down', description: 'Cambio <= -3%', icon: ArrowDown },
    { id: 'winners', label: 'Winners', description: 'Cambio >= 5%', icon: Trophy },
    { id: 'losers', label: 'Losers', description: 'Cambio <= -5%', icon: AlertTriangle },
    { id: 'anomalies', label: 'Anomalies', description: 'RVOL >= 3.0', icon: Zap },
    { id: 'high_volume', label: 'High Volume', description: 'RVOL >= 2.0', icon: BarChart3 },
];

export function TerminalPalette({ 
    open, 
    onOpenChange, 
    searchValue = '', 
    onSearchChange,
    onOpenHelp,
    onExecuteTickerCommand,
}: TerminalPaletteProps) {
    const [selectedIndex, setSelectedIndex] = useState(0);
    const [tickerResults, setTickerResults] = useState<TickerResult[]>([]);
    const [loadingTickers, setLoadingTickers] = useState(false);
    const [selectedTicker, setSelectedTicker] = useState<TickerResult | null>(null);
    const listRef = useRef<HTMLDivElement>(null);
    const abortControllerRef = useRef<AbortController | null>(null);
    const { executeCommand, openScannerTable } = useCommandExecutor();
    
    const search = searchValue.trim();
    const setSearch = onSearchChange || (() => {});
    
    // Parsear el comando
    const parsed = parseTerminalCommand(search);
    
    // Detectar prefijo SC para scanner
    const hasScPrefix = search.toUpperCase().startsWith('SC');
    
    // Detectar si parece un ticker (letras mayúsculas sin espacios)
    const looksLikeTicker = /^[A-Z]{1,5}$/.test(search.toUpperCase()) && !hasScPrefix && !['SC', 'IPO', 'SET', 'HELP'].includes(search.toUpperCase());
    
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
    const items = getDisplayItems(parsed, hasScPrefix, search, tickerResults, selectedTicker);
    
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
                } else {
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
        }
    }, [executeCommand, openScannerTable, onOpenChange, onOpenHelp, onExecuteTickerCommand, setSearch, selectedTicker]);
    
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
                className="fixed left-4 top-16 animate-slideDown"
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
                            {loadingTickers ? 'Buscando...' : 'No se encontraron resultados'}
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
                                            {item.icon && (
                                                <item.icon className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                                            )}
                                            <span className="px-1.5 py-0.5 text-[10px] font-mono font-semibold border border-slate-200 text-slate-700 rounded min-w-[60px] text-center">
                                                {item.label}
                                            </span>
                                            <span className="text-[10px] text-slate-500 flex-1 truncate">
                                                {item.description}
                                            </span>
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
    type: 'instrument' | 'ticker-command' | 'global-command' | 'scanner';
    label: string;
    description: string;
    icon?: React.ComponentType<{ className?: string }>;
    shortcut?: string | null;
    autocomplete?: string;
    ticker?: string;
    commandId?: string;
    scannerId?: string;
    tickerData?: TickerResult;
}

function getDisplayItems(
    parsed: ReturnType<typeof parseTerminalCommand>, 
    hasScPrefix: boolean, 
    search: string, 
    tickerResults: TickerResult[],
    selectedTicker: TickerResult | null
): DisplayItem[] {
    // Si hay un ticker seleccionado, mostrar comandos para ese ticker
    if (selectedTicker) {
        return Object.entries(TICKER_COMMANDS).map(([key, cmd]) => ({
            id: `cmd-${cmd.id}`,
            type: 'ticker-command' as const,
            label: key,
            description: cmd.description,
            icon: COMMAND_ICONS[cmd.id],
            shortcut: cmd.shortcut,
            ticker: selectedTicker.symbol,
            commandId: cmd.id,
            autocomplete: `${selectedTicker.symbol} ${key}`,
        }));
    }
    
    // Si es prefijo SC, mostrar categorías del scanner
    if (hasScPrefix) {
        const filter = search.toUpperCase().replace('SC', '').trim();
        return SCANNER_COMMANDS
            .filter(cmd => !filter || cmd.label.toUpperCase().includes(filter))
            .map(cmd => ({
                id: `scanner-${cmd.id}`,
                type: 'scanner' as const,
                label: cmd.label,
                description: cmd.description,
                icon: cmd.icon,
                scannerId: cmd.id,
                autocomplete: `SC ${cmd.label}`,
            }));
    }
    
    // Si hay resultados de búsqueda de tickers, mostrarlos
    if (tickerResults.length > 0) {
        return tickerResults.map(ticker => ({
            id: `ticker-${ticker.symbol}-${ticker.exchange}`,
            type: 'instrument' as const,
            label: ticker.symbol,
            description: ticker.name,
            tickerData: ticker,
            autocomplete: ticker.symbol + ' ',
        }));
    }
    
    // Default: comandos globales
    const items: DisplayItem[] = [];
    
    Object.entries(GLOBAL_COMMANDS).forEach(([key, cmd]) => {
        if (!search || key.includes(search.toUpperCase()) || cmd.name.toUpperCase().includes(search.toUpperCase())) {
            items.push({
                id: `global-${cmd.id}`,
                type: 'global-command' as const,
                label: key,
                description: cmd.description,
                icon: COMMAND_ICONS[cmd.id],
                shortcut: cmd.shortcut,
                commandId: cmd.id,
                autocomplete: key,
            });
        }
    });
    
    return items;
}

export default TerminalPalette;
