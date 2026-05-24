'use client';

import { useState, useEffect, useCallback, memo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, AlertTriangle, Loader2 } from 'lucide-react';
import { TickerSearch, TickerSearchRef } from '@/components/common/TickerSearch';
import { useFloatingWindow, useWindowState } from '@/contexts/FloatingWindowContext';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { CanvasGrid, CanvasToolbar, WidgetPalette, useCanvas } from '@/components/canvas';
import { FanDataProvider, FAN_CONFIG } from '@/components/canvas/fan';
import type { AIReport, CompanyData, FanData } from '@/components/canvas/fan';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.tradeul.com';

type FinancialAnalystWindowState = {
    ticker?: string;
}

function FinancialAnalystCanvasInner({ initialTicker }: { initialTicker?: string }) {
    const { t, i18n } = useTranslation();
    const { state: windowState, updateState: updateWindowState } = useWindowState<FinancialAnalystWindowState>();
    const font = useUserPreferencesStore(selectFont);
    const fontFamily = `var(--font-${font})`;
    const isSpanish = i18n.language === 'es';

    const savedTicker = windowState.ticker || initialTicker || '';
    const [ticker, setTicker] = useState(savedTicker);
    const [inputValue, setInputValue] = useState(savedTicker);
    const [company, setCompany] = useState<CompanyData | null>(null);
    const [report, setReport] = useState<AIReport | null>(null);
    const tickerSearchRef = useRef<TickerSearchRef>(null);
    const [loadingInstant, setLoadingInstant] = useState(false);
    const [loadingGemini, setLoadingGemini] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Canvas state
    const canvas = useCanvas(FAN_CONFIG);
    const [paletteOpen, setPaletteOpen] = useState(false);
    const [activeTemplate, setActiveTemplate] = useState<string | null>('default');

    const fetchCompanyData = useCallback(async (symbol: string) => {
        try {
            const res = await fetch(`${API_URL}/api/v1/ticker/${symbol}/description`);
            if (res.ok) {
                const data = await res.json();
                const c = data.company || {};
                setCompany({
                    logoUrl: c.logoUrl?.includes('polygon.io') ? `${API_URL}/api/v1/proxy/logo?url=${encodeURIComponent(c.logoUrl)}` : c.logoUrl,
                    website: c.website, ceo: c.ceo, exchange: c.exchange,
                });
            }
        } catch { /* ignore */ }
    }, []);

    const fetchReport = useCallback(async (symbol: string) => {
        const normalizedSymbol = symbol.toUpperCase().trim();
        setTicker(normalizedSymbol);
        setLoadingInstant(true);
        setLoadingGemini(false);
        setError(null);
        setReport(null);
        setCompany(null);

        try {
            const instantRes = await fetch(`${API_URL}/api/report/${normalizedSymbol}/instant`);
            if (!instantRes.ok) throw new Error(`Error ${instantRes.status}`);
            const instantData = await instantRes.json();
            setReport(instantData);
            fetchCompanyData(normalizedSymbol);
            setLoadingInstant(false);

            setLoadingGemini(true);
            const lang = isSpanish ? 'es' : 'en';
            const geminiRes = await fetch(`${API_URL}/api/report/${normalizedSymbol}?lang=${lang}`);
            if (geminiRes.ok) {
                const geminiData = await geminiRes.json();
                setReport(geminiData);
            }
        } catch (err) {
            console.error('Report fetch error:', err);
            setError(err instanceof Error ? err.message : 'Failed to generate report');
        } finally {
            setLoadingInstant(false);
            setLoadingGemini(false);
        }
    }, [isSpanish, fetchCompanyData]);

    useEffect(() => {
        if (ticker) updateWindowState({ ticker });
    }, [ticker, updateWindowState]);

    useEffect(() => {
        const tickerToFetch = savedTicker || initialTicker;
        if (tickerToFetch) fetchReport(tickerToFetch);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        tickerSearchRef.current?.close();
        if (inputValue.trim()) fetchReport(inputValue.trim());
    };

    const handleSelectTemplate = (id: string) => {
        const tpl = FAN_CONFIG.templates?.find((t) => t.id === id);
        if (!tpl) return;
        canvas.setLayout(tpl.layout);
        setActiveTemplate(id);
    };

    const fanData: FanData = {
        report,
        company,
        ticker,
        loadingInstant,
        loadingGemini,
        isSpanish,
    };

    const loading = loadingInstant;

    return (
        <div className="h-full flex flex-col bg-surface text-foreground" style={{ fontFamily }}>
            {/* Search Bar */}
            <div className="px-2 py-1.5 border-b border-border">
                <form onSubmit={handleSubmit} className="flex items-center gap-2">
                    <TickerSearch
                        ref={tickerSearchRef}
                        value={inputValue}
                        onChange={setInputValue}
                        onSelect={(t) => { setInputValue(t.symbol); fetchReport(t.symbol); }}
                        placeholder="Ticker..."
                        className="flex-1"
                        autoFocus={false}
                    />
                    <button
                        type="submit"
                        disabled={loading || !inputValue.trim()}
                        className="px-3 py-1 text-[11px] font-medium bg-primary text-white rounded hover:bg-primary-hover disabled:opacity-50 transition-colors flex items-center gap-1.5"
                    >
                        {loading ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                            <Search className="w-3 h-3" />
                        )}
                        {isSpanish ? 'Buscar' : 'Search'}
                    </button>
                </form>
            </div>

            {/* Canvas Toolbar */}
            {report && (
                <CanvasToolbar
                    editMode={canvas.editMode}
                    onToggleEdit={canvas.toggleEditMode}
                    onOpenPalette={() => setPaletteOpen(true)}
                    onReset={() => {
                        canvas.resetLayout();
                        setActiveTemplate('default');
                    }}
                    templates={FAN_CONFIG.templates}
                    activeTemplateId={activeTemplate}
                    onSelectTemplate={handleSelectTemplate}
                />
            )}

            {/* Content */}
            <div className="flex-1 overflow-auto relative">
                {!ticker ? (
                    <div className="flex flex-col items-center justify-center h-full text-muted-fg/50">
                        <div className="text-sm">{isSpanish ? 'Introduce un ticker para analizar' : 'Enter a ticker to analyze'}</div>
                    </div>
                ) : loading ? (
                    <div className="flex flex-col items-center justify-center h-full gap-2">
                        <Loader2 className="w-5 h-5 animate-spin text-primary" />
                        <div className="text-xs text-muted-fg">{isSpanish ? 'Buscando' : 'Searching'} {ticker}...</div>
                    </div>
                ) : error ? (
                    <div className="flex flex-col items-center justify-center h-full gap-2 px-4">
                        <AlertTriangle className="w-5 h-5 text-amber-400" />
                        <div className="text-xs text-muted-fg text-center">{error}</div>
                        <button onClick={() => fetchReport(ticker)} className="px-3 py-1 text-[10px] border border-border rounded flex items-center gap-1.5 hover:bg-surface-hover">
                            {isSpanish ? 'Reintentar' : 'Retry'}
                        </button>
                    </div>
                ) : report && (
                    <FanDataProvider value={fanData}>
                        <CanvasGrid config={FAN_CONFIG} canvas={canvas} />
                        <WidgetPalette
                            open={paletteOpen}
                            onClose={() => setPaletteOpen(false)}
                            config={FAN_CONFIG}
                            onAdd={(type) => {
                                canvas.addWidget(type);
                                setPaletteOpen(false);
                                setActiveTemplate(null);
                            }}
                        />
                    </FanDataProvider>
                )}
            </div>
        </div>
    );
}

export const FinancialAnalystCanvas = memo(FinancialAnalystCanvasInner);
export default FinancialAnalystCanvas;
