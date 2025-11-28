'use client';

import { useEffect, useRef, useState, memo } from 'react';
import { RefreshCw, Maximize2, Minimize2, Settings } from 'lucide-react';

interface ChartContentProps {
    ticker?: string;
    exchange?: string;
    onTickerChange?: (ticker: string) => void;
}

// Mapeo de exchanges a prefijos de TradingView
const EXCHANGE_TO_TV: Record<string, string> = {
    'NASDAQ': 'NASDAQ',
    'NYSE': 'NYSE',
    'AMEX': 'AMEX',
    'ARCA': 'AMEX',
    'BATS': 'BATS',
    'OTC': 'OTC',
    'OTCQB': 'OTC',
    'OTCQX': 'OTC',
    'PINK': 'OTC',
    // Por defecto intentamos sin prefijo (TradingView busca automáticamente)
};

/**
 * Obtiene el símbolo completo para TradingView
 * Si no encontramos el exchange, dejamos que TradingView busque automáticamente
 */
function getTradingViewSymbol(ticker: string, exchange?: string): string {
    if (!exchange) {
        // Sin exchange, TradingView buscará automáticamente
        return ticker;
    }
    
    const tvExchange = EXCHANGE_TO_TV[exchange.toUpperCase()];
    if (tvExchange) {
        return `${tvExchange}:${ticker}`;
    }
    
    // Si el exchange no está mapeado, dejamos solo el ticker
    return ticker;
}

/**
 * ChartContent - Gráfico interactivo con TradingView
 * 
 * Usa el widget avanzado de TradingView para mostrar gráficos profesionales.
 * https://www.tradingview.com/widget/advanced-chart/
 */
function ChartContentComponent({ ticker = 'AAPL', exchange, onTickerChange }: ChartContentProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [theme, setTheme] = useState<'light' | 'dark'>('light');
    const [inputValue, setInputValue] = useState(ticker);
    const [loading, setLoading] = useState(true);

    // Actualizar input cuando cambia el ticker externo
    useEffect(() => {
        setInputValue(ticker);
    }, [ticker]);

    // Cargar TradingView widget
    useEffect(() => {
        if (!containerRef.current) return;

        setLoading(true);

        // Limpiar widget anterior
        containerRef.current.innerHTML = '';

        // Crear contenedor para el widget
        const widgetContainer = document.createElement('div');
        widgetContainer.className = 'tradingview-widget-container';
        widgetContainer.style.height = '100%';
        widgetContainer.style.width = '100%';

        const widgetDiv = document.createElement('div');
        widgetDiv.className = 'tradingview-widget-container__widget';
        widgetDiv.style.height = '100%';
        widgetDiv.style.width = '100%';

        widgetContainer.appendChild(widgetDiv);
        containerRef.current.appendChild(widgetContainer);

        // Crear script del widget
        const script = document.createElement('script');
        script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
        script.async = true;
        const tvSymbol = getTradingViewSymbol(ticker, exchange);
        script.innerHTML = JSON.stringify({
            autosize: true,
            symbol: tvSymbol,
            interval: 'D',
            timezone: 'America/New_York',
            theme: theme,
            style: '1',
            locale: 'es',
            enable_publishing: false,
            allow_symbol_change: true,
            calendar: false,
            support_host: 'https://www.tradingview.com',
            hide_top_toolbar: false,
            hide_legend: false,
            save_image: false,
            hide_volume: false,
            withdateranges: true,
            details: true,
            hotlist: false,
            studies: ['RSI@tv-basicstudies', 'MASimple@tv-basicstudies'],
        });

        widgetContainer.appendChild(script);

        script.onload = () => {
            setLoading(false);
        };

        // Timeout para loading state
        const timeout = setTimeout(() => {
            setLoading(false);
        }, 3000);

        return () => {
            clearTimeout(timeout);
        };
    }, [ticker, exchange, theme]);

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        if (inputValue.trim()) {
            onTickerChange?.(inputValue.trim().toUpperCase());
        }
    };

    const toggleFullscreen = () => {
        if (!document.fullscreenElement) {
            containerRef.current?.parentElement?.requestFullscreen();
            setIsFullscreen(true);
        } else {
            document.exitFullscreen();
            setIsFullscreen(false);
        }
    };

    return (
        <div className="h-full flex flex-col bg-white">
            {/* Toolbar */}
            <div className="flex items-center justify-between px-2 py-1 border-b border-slate-200 bg-slate-50">
                <form onSubmit={handleSearch} className="flex items-center gap-1.5">
                    <input
                        type="text"
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value.toUpperCase())}
                        placeholder="TICKER"
                        className="w-20 px-2 py-0.5 text-[11px] font-mono font-semibold 
                                 border border-slate-300 rounded bg-white
                                 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                    />
                    <button
                        type="submit"
                        className="px-2 py-0.5 bg-blue-600 text-white rounded hover:bg-blue-700 
                                 text-[10px] font-medium"
                    >
                        Go
                    </button>
                </form>

                <div className="flex items-center gap-1">
                    {/* Theme toggle */}
                    <button
                        onClick={() => setTheme(t => t === 'light' ? 'dark' : 'light')}
                        className="p-1 text-slate-400 hover:text-slate-600 rounded hover:bg-slate-100"
                        title={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
                    >
                        <Settings className="w-3.5 h-3.5" />
                    </button>
                    
                    {/* Fullscreen */}
                    <button
                        onClick={toggleFullscreen}
                        className="p-1 text-slate-400 hover:text-slate-600 rounded hover:bg-slate-100"
                        title="Toggle fullscreen"
                    >
                        {isFullscreen ? (
                            <Minimize2 className="w-3.5 h-3.5" />
                        ) : (
                            <Maximize2 className="w-3.5 h-3.5" />
                        )}
                    </button>
                </div>
            </div>

            {/* Chart Container */}
            <div className="flex-1 relative">
                {loading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-slate-900/80 z-10">
                        <div className="flex items-center gap-2 text-slate-300">
                            <RefreshCw className="w-4 h-4 animate-spin" />
                            <span className="text-xs font-mono">Loading chart...</span>
                        </div>
                    </div>
                )}
                <div 
                    ref={containerRef} 
                    className="h-full w-full"
                    style={{ minHeight: '400px' }}
                />
            </div>

            {/* Footer */}
            <div className="px-2 py-1 border-t border-slate-200 bg-slate-50 text-center">
                <span className="text-[9px] text-slate-400">
                    Powered by TradingView
                </span>
            </div>
        </div>
    );
}

export const ChartContent = memo(ChartContentComponent);
export default ChartContent;

