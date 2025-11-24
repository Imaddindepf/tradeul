'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { Search, X, Loader2, AlertCircle } from 'lucide-react';

type TickerResult = {
    symbol: string;
    name: string;
    exchange: string;
    type: string;
    displayName: string;
};

type TickerSearchProps = {
    value: string;
    onChange: (value: string) => void;
    onSelect?: (ticker: TickerResult) => void;
    placeholder?: string;
    className?: string;
    autoFocus?: boolean;
};

export function TickerSearch({
    value,
    onChange,
    onSelect,
    placeholder = "Ticker",
    className = "",
    autoFocus = false
}: TickerSearchProps) {
    const [results, setResults] = useState<TickerResult[]>([]);
    const [isOpen, setIsOpen] = useState(false);
    const [selectedIndex, setSelectedIndex] = useState(-1);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const inputRef = useRef<HTMLInputElement>(null);
    const dropdownRef = useRef<HTMLDivElement>(null);
    const abortControllerRef = useRef<AbortController | null>(null);

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
            // Usar API Gateway (puerto 8000) en vez de servicio directo
            // Esto evita problemas de firewall y centraliza el acceso
            const response = await fetch(
                `http://157.180.45.153:8000/api/v1/metadata/search?q=${encodeURIComponent(query)}&limit=10`,
                { 
                    signal: abortControllerRef.current.signal,
                    // Add timeout
                    ...(typeof window !== 'undefined' && {
                        cache: 'no-store'
                    })
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
            setIsOpen(data.results.length > 0);
            
        } catch (error: any) {
            // Ignorar errores de abort (cuando el usuario sigue escribiendo)
            if (error.name === 'AbortError') {
                return;
            }
            
            console.error('❌ Error fetching ticker results:', error);
            setError('No se pudo conectar al servidor');
            setResults([]);
            setIsOpen(false);
        } finally {
            setLoading(false);
        }
    }, []);

    // Debounce search (150ms para sentir más responsive)
    useEffect(() => {
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

    // Close dropdown when clicking outside
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (
                dropdownRef.current &&
                !dropdownRef.current.contains(e.target as Node) &&
                !inputRef.current?.contains(e.target as Node)
            ) {
                setIsOpen(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    // Keyboard navigation
    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (!isOpen) return;

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                setSelectedIndex(prev => 
                    prev < results.length - 1 ? prev + 1 : prev
                );
                break;
            case 'ArrowUp':
                e.preventDefault();
                setSelectedIndex(prev => prev > 0 ? prev - 1 : 0);
                break;
            case 'Enter':
                e.preventDefault();
                if (selectedIndex >= 0 && selectedIndex < results.length) {
                    handleSelect(results[selectedIndex]);
                }
                break;
            case 'Escape':
                setIsOpen(false);
                break;
        }
    };

    const handleSelect = (ticker: TickerResult) => {
        onChange(ticker.symbol);
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
                            setIsOpen(true);
                        }
                    }}
                    placeholder={placeholder}
                    autoFocus={autoFocus}
                    className={`w-full px-1.5 py-0.5 ${value ? 'pr-6' : ''} border ${error ? 'border-red-400' : 'border-slate-300'} rounded bg-white text-slate-900 text-xs focus:outline-none focus:ring-1 ${error ? 'focus:ring-red-500' : 'focus:ring-blue-500'} placeholder:text-slate-400 font-mono ${className}`}
                />
                
                {/* Right icons */}
                <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
                    {loading && (
                        <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />
                    )}
                    {error && !loading && (
                        <AlertCircle className="w-3 h-3 text-red-500" title={error} />
                    )}
                    {value && !loading && (
                    <button
                        type="button"
                        onClick={handleClear}
                            className="text-slate-400 hover:text-slate-600 p-0.5"
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
                    className="absolute z-50 w-full min-w-[250px] mt-0.5 bg-white border border-slate-300 rounded shadow-lg max-h-60 overflow-y-auto"
                >
                    {results.map((ticker, index) => (
                        <button
                            key={ticker.symbol}
                            type="button"
                            onClick={() => handleSelect(ticker)}
                            onMouseEnter={() => setSelectedIndex(index)}
                            className={`w-full px-2 py-1.5 text-left text-xs hover:bg-blue-50 transition-colors border-b border-slate-100 last:border-0 ${
                                index === selectedIndex ? 'bg-blue-50' : ''
                            }`}
                        >
                            <div className="flex items-center gap-2">
                                <span className="font-mono font-semibold text-blue-600 min-w-[50px]">
                                    {ticker.symbol}
                                </span>
                                <span className="text-slate-600 flex-1 truncate">
                                    {ticker.name || 'Sin nombre'}
                                </span>
                                {ticker.exchange && (
                                    <span className="text-[10px] text-slate-400 font-mono uppercase">
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
                    className="absolute z-50 w-full min-w-[250px] mt-0.5 bg-white border border-slate-300 rounded shadow-lg"
                >
                    <div className="px-2 py-2 text-xs text-slate-500 text-center">
                        No se encontraron tickers para "{value}"
                    </div>
                </div>
            )}
        </div>
    );
}

