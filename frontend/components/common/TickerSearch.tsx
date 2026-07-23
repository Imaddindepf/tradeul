'use client';

import { useState, useEffect, useRef, useCallback, useImperativeHandle, forwardRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, X, Loader2, AlertCircle } from 'lucide-react';
import { useCurrentWindowId } from '@/contexts/FloatingWindowContext';
import { registerTickerSearch } from '@/lib/tickerSearchRegistry';

type TickerResult = {
    symbol: string;
    name: string;
    exchange: string;
    type: string;
    asset_type?: 'index' | 'etf' | 'equity';
    displayName: string;
};

// Badge estilo terminal (Bloomberg): IDX azul para índices, ETF neutro.
// Las equities no llevan badge — son el caso común y el ruido visual sobra.
const ASSET_BADGES: Record<string, { label: string; className: string }> = {
    index: { label: 'IDX', className: 'bg-blue-600/20 text-blue-500 border-blue-600/40' },
    etf: { label: 'ETF', className: 'bg-muted text-muted-fg border-border' },
};

type TickerSearchProps = {
    value: string;
    onChange: (value: string) => void;
    onSelect?: (ticker: TickerResult) => void;
    placeholder?: string;
    className?: string;
    autoFocus?: boolean;
};

export type TickerSearchRef = {
    close: () => void;
    focus: () => void;
    suppressSearch: () => void;
};

export const TickerSearch = forwardRef<TickerSearchRef, TickerSearchProps>(function TickerSearch({
    value,
    onChange,
    onSelect,
    placeholder,
    className = "",
    autoFocus = false
}, ref) {
    const { t } = useTranslation();
    const defaultPlaceholder = placeholder || t('news.ticker');
    const [results, setResults] = useState<TickerResult[]>([]);
    const [isOpen, setIsOpen] = useState(false);
    // Siempre hay un resultado resaltado (0 por defecto): Enter confirma el
    // resaltado y la primera flecha ↓ se mueve visiblemente al segundo.
    const [selectedIndex, setSelectedIndex] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const inputRef = useRef<HTMLInputElement>(null);
    const dropdownRef = useRef<HTMLDivElement>(null);
    const abortControllerRef = useRef<AbortController | null>(null);
    const isInitialMount = useRef(true); // Track initial mount to avoid opening dropdown
    const skipNextSearchRef = useRef(false); // Skip search when value set programmatically (e.g. link group)

    // Expose methods to parent via ref
    useImperativeHandle(ref, () => ({
        close: () => setIsOpen(false),
        focus: () => inputRef.current?.focus(),
        suppressSearch: () => { skipNextSearchRef.current = true; }
    }));

    // Auto-registro para el "type-ahead": si esta búsqueda vive dentro de una
    // ventana flotante, al teclear con esa ventana enfocada arrancamos aquí.
    const windowId = useCurrentWindowId();
    const onChangeRef = useRef(onChange);
    onChangeRef.current = onChange;
    useEffect(() => {
        if (!windowId) return;
        return registerTickerSearch(windowId, {
            getInput: () => inputRef.current,
            type: (char: string) => {
                inputRef.current?.focus();
                onChangeRef.current(char.toUpperCase());
            },
        });
    }, [windowId]);

    // Fetch results from API
    const fetchResults = useCallback(async (query: string) => {
        if (query.length === 0) {
            setResults([]);
            setIsOpen(false);
            setError(null);
            return;
        }

        // Cancel previous request
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }

        abortControllerRef.current = new AbortController();

        setLoading(true);
        setError(null);

        try {
            // Usar API Gateway via variable de entorno (HTTPS en producción)
            const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            const response = await fetch(
                `${apiUrl}/api/v1/metadata/search?q=${encodeURIComponent(query)}&limit=10`,
                {
                    signal: abortControllerRef.current.signal,
                    cache: 'no-store'
                }
            );

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            // Validar que tenemos results array
            if (!data.results || !Array.isArray(data.results)) {
                console.warn('Invalid response format:', data);
                setResults([]);
                setIsOpen(false);
                return;
            }

            setResults(data.results);
            // Solo abrir el dropdown si el usuario está escribiendo en el input.
            // Un cambio programático del value (sync de celda, link group, select)
            // no debe desplegar la lista como si hubiera una búsqueda activa.
            setIsOpen(data.results.length > 0 && document.activeElement === inputRef.current);
            setSelectedIndex(0);

        } catch (error: any) {
            // Ignorar errores de abort (cuando el usuario sigue escribiendo)
            if (error.name === 'AbortError') {
                return;
            }

            console.error('❌ Error fetching ticker results:', error);
            setError(t('errors.couldNotConnect'));
            setResults([]);
            setIsOpen(false);
        } finally {
            setLoading(false);
        }
    }, []);

    // Debounce search (150ms para sentir más responsive)
    // Skip on initial mount to avoid opening dropdown when component loads with a value
    useEffect(() => {
        if (isInitialMount.current) {
            isInitialMount.current = false;
            return;
        }

        if (skipNextSearchRef.current) {
            skipNextSearchRef.current = false;
            return;
        }

        const timer = setTimeout(() => {
            if (value && value.length >= 1) {
                fetchResults(value);
            } else {
                setResults([]);
                setIsOpen(false);
                setError(null);
            }
        }, 150);

        return () => clearTimeout(timer);
    }, [value, fetchResults]);

    // Close dropdown when clicking outside — pointerdown en CAPTURA para que
    // ningún stopPropagation intermedio (canvas del chart, ventanas flotantes)
    // impida que el cierre llegue a document.
    useEffect(() => {
        const handleClickOutside = (e: PointerEvent) => {
            if (
                dropdownRef.current &&
                !dropdownRef.current.contains(e.target as Node) &&
                !inputRef.current?.contains(e.target as Node)
            ) {
                setIsOpen(false);
            }
        };

        document.addEventListener('pointerdown', handleClickOutside, true);
        return () => document.removeEventListener('pointerdown', handleClickOutside, true);
    }, []);

    // Mantener el resultado resaltado siempre visible al navegar con teclado.
    useEffect(() => {
        if (!isOpen || !dropdownRef.current) return;
        const el = dropdownRef.current.querySelector(`[data-index="${selectedIndex}"]`);
        el?.scrollIntoView?.({ block: 'nearest' });
    }, [selectedIndex, isOpen]);

    // Keyboard navigation
    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (!isOpen) {
            // Con el dropdown cerrado, ↓ lo reabre si hay resultados previos.
            if (e.key === 'ArrowDown' && results.length > 0 && value) {
                e.preventDefault();
                setSelectedIndex(0);
                setIsOpen(true);
            }
            return;
        }

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                // Navegación circular: desde el último vuelve al primero.
                setSelectedIndex(prev => (prev + 1) % Math.max(results.length, 1));
                break;
            case 'ArrowUp':
                e.preventDefault();
                setSelectedIndex(prev => (prev - 1 + results.length) % Math.max(results.length, 1));
                break;
            case 'Enter': {
                e.preventDefault();
                const pick = selectedIndex >= 0 && selectedIndex < results.length
                    ? results[selectedIndex]
                    : results[0];
                if (pick) handleSelect(pick);
                break;
            }
            case 'Escape':
                // Solo cerrar el dropdown; no propagar a handlers globales
                // (cerrar ventanas, cancelar dibujos, etc.).
                e.stopPropagation();
                setIsOpen(false);
                break;
        }
    };

    const handleSelect = (ticker: TickerResult) => {
        // Evitar que el onChange del símbolo vuelva a disparar fetch+open.
        skipNextSearchRef.current = true;
        onChange(ticker.symbol);
        setResults([]);
        setIsOpen(false);
        onSelect?.(ticker);
    };

    const handleClear = () => {
        onChange('');
        setResults([]);
        setIsOpen(false);
        inputRef.current?.focus();
    };

    return (
        <div className="relative">
            <div className="relative">
                <input
                    ref={inputRef}
                    type="text"
                    value={value}
                    onChange={(e) => onChange(e.target.value.toUpperCase())}
                    onKeyDown={handleKeyDown}
                    onFocus={() => {
                        if (value && results.length > 0) {
                            setSelectedIndex(0);
                            setIsOpen(true);
                        }
                    }}
                    placeholder={defaultPlaceholder}
                    autoFocus={autoFocus}
                    className={`w-full px-1.5 py-0.5 ${value ? 'pr-6' : ''} border ${error ? 'border-red-400' : 'border-border'} rounded bg-surface text-foreground text-xs focus:outline-none focus:ring-1 ${error ? 'focus:ring-red-500' : 'focus:ring-primary'} placeholder:text-muted-fg font-mono ${className}`}
                />

                {/* Right icons */}
                <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
                    {loading && (
                        <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />
                    )}
                    {error && !loading && (
                        <span title={error}>
                            <AlertCircle className="w-3 h-3 text-red-500" />
                        </span>
                    )}
                    {value && !loading && (
                        <button
                            type="button"
                            onClick={handleClear}
                            className="text-muted-fg hover:text-foreground/80 p-0.5"
                        >
                            <X className="w-3 h-3" />
                        </button>
                    )}
                </div>
            </div>

            {/* Dropdown */}
            {isOpen && results.length > 0 && !error && (
                <div
                    ref={dropdownRef}
                    className="absolute z-50 w-full min-w-[250px] mt-0.5 bg-surface border border-border rounded shadow-lg max-h-60 overflow-y-auto"
                >
                    {results.map((ticker, index) => (
                        <button
                            key={ticker.symbol}
                            type="button"
                            data-index={index}
                            onClick={() => handleSelect(ticker)}
                            // onMouseMove (no onMouseEnter): si el scroll por teclado
                            // desplaza filas bajo un cursor quieto, el ratón no roba
                            // la selección; solo manda cuando realmente se mueve.
                            onMouseMove={() => { if (selectedIndex !== index) setSelectedIndex(index); }}
                            className={`w-full px-2 py-1.5 text-left text-xs transition-colors border-b border-border-subtle last:border-0 ${index === selectedIndex ? 'bg-primary/10' : ''
                                }`}
                        >
                            <div className="flex items-center gap-2">
                                {ticker.asset_type && ASSET_BADGES[ticker.asset_type] && (
                                    <span className={`text-[9px] font-mono font-bold px-1 py-px rounded border ${ASSET_BADGES[ticker.asset_type].className}`}>
                                        {ASSET_BADGES[ticker.asset_type].label}
                                    </span>
                                )}
                                <span className="font-mono font-semibold text-blue-600 min-w-[50px]">
                                    {ticker.symbol}
                                </span>
                                <span className="text-foreground/80 flex-1 truncate">
                                    {ticker.name || t('tickerSearch.noName')}
                                </span>
                                {ticker.exchange && (
                                    <span className="text-[10px] text-muted-fg font-mono uppercase">
                                        {ticker.exchange}
                                    </span>
                                )}
                            </div>
                        </button>
                    ))}
                </div>
            )}

            {/* Empty state cuando se busca pero no hay resultados */}
            {isOpen && !loading && !error && value.length >= 1 && results.length === 0 && (
                <div
                    ref={dropdownRef}
                    className="absolute z-50 w-full min-w-[250px] mt-0.5 bg-surface border border-border rounded shadow-lg"
                >
                    <div className="px-2 py-2 text-xs text-muted-fg text-center">
                        {t('tickerSearch.noTickersFound', { query: value })}
                    </div>
                </div>
            )}
        </div>
    );
});

