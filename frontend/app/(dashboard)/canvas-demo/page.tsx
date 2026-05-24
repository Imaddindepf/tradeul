'use client';

/**
 * Canvas Demo Page — /canvas-demo
 *
 * Página de validación del sistema de canvas con widgets FAN reales.
 * Permite testear drag, resize, templates, persistencia y datos en vivo.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { Search, Loader2 } from 'lucide-react';
import {
    CanvasGrid,
    CanvasToolbar,
    WidgetPalette,
    useCanvas,
} from '@/components/canvas';
import { WindowIdProvider, WindowStateProvider } from '@/contexts/FloatingWindowContext';
import { FanDataProvider, FAN_CONFIG } from '@/components/canvas/fan';
import type { AIReport, CompanyData, FanData } from '@/components/canvas/fan';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.tradeul.com';

export default function CanvasDemoPage() {
    return (
        <WindowIdProvider windowId="canvas-demo">
            <WindowStateProvider windowId="canvas-demo">
                <CanvasDemoInner />
            </WindowStateProvider>
        </WindowIdProvider>
    );
}

function CanvasDemoInner() {
    const canvas = useCanvas(FAN_CONFIG);
    const [paletteOpen, setPaletteOpen] = useState(false);
    const [activeTemplate, setActiveTemplate] = useState<string | null>('default');

    const [ticker, setTicker] = useState('');
    const [inputValue, setInputValue] = useState('AAPL');
    const [report, setReport] = useState<AIReport | null>(null);
    const [company, setCompany] = useState<CompanyData | null>(null);
    const [loadingInstant, setLoadingInstant] = useState(false);
    const [loadingGemini, setLoadingGemini] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    const fetchReport = useCallback(async (symbol: string) => {
        const s = symbol.toUpperCase().trim();
        if (!s) return;
        setTicker(s);
        setLoadingInstant(true);
        setLoadingGemini(false);
        setReport(null);
        setCompany(null);

        try {
            const instantRes = await fetch(`${API_URL}/api/report/${s}/instant`);
            if (!instantRes.ok) throw new Error(`Error ${instantRes.status}`);
            const instantData = await instantRes.json();
            setReport(instantData);
            setLoadingInstant(false);

            // Company data
            try {
                const descRes = await fetch(`${API_URL}/api/v1/ticker/${s}/description`);
                if (descRes.ok) {
                    const d = await descRes.json();
                    const c = d.company || {};
                    setCompany({
                        logoUrl: c.logoUrl?.includes('polygon.io') ? `${API_URL}/api/v1/proxy/logo?url=${encodeURIComponent(c.logoUrl)}` : c.logoUrl,
                        website: c.website, ceo: c.ceo, exchange: c.exchange,
                    });
                }
            } catch { /* ignore */ }

            setLoadingGemini(true);
            const geminiRes = await fetch(`${API_URL}/api/report/${s}?lang=en`);
            if (geminiRes.ok) {
                const geminiData = await geminiRes.json();
                setReport(geminiData);
            }
        } catch (err) {
            console.error('Fetch error:', err);
        } finally {
            setLoadingInstant(false);
            setLoadingGemini(false);
        }
    }, []);

    useEffect(() => {
        fetchReport('AAPL');
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
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
        isSpanish: false,
    };

    return (
        <div className="fixed inset-0 flex flex-col bg-surface text-foreground" style={{ fontFamily: 'var(--font-jetbrains-mono), monospace' }}>
            {/* Title bar + search */}
            <div className="flex items-center justify-between h-8 px-2 bg-surface-hover border-b border-border gap-2">
                <span className="text-[11px] font-medium shrink-0">Canvas Demo</span>
                <form onSubmit={handleSubmit} className="flex items-center gap-1.5 flex-1 max-w-[300px]">
                    <input
                        ref={inputRef}
                        type="text"
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value.toUpperCase())}
                        placeholder="TICKER"
                        className="flex-1 h-5 px-1.5 text-[10px] bg-surface border border-border rounded-sm outline-none font-mono focus:border-primary"
                    />
                    <button
                        type="submit"
                        disabled={loadingInstant}
                        className="h-5 px-2 text-[9px] font-semibold bg-primary text-white rounded-sm hover:bg-primary-hover disabled:opacity-50 flex items-center gap-1"
                    >
                        {loadingInstant ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
                        GO
                    </button>
                </form>
                <span className="text-[9px] text-muted-fg shrink-0">
                    {ticker && (loadingGemini ? `${ticker} · analyzing...` : `${ticker}`)}
                </span>
            </div>

            {/* Canvas toolbar */}
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

            {/* Canvas */}
            <div className="relative flex-1 overflow-auto bg-surface">
                {report ? (
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
                ) : (
                    <div className="flex items-center justify-center h-full">
                        {loadingInstant ? (
                            <Loader2 className="w-5 h-5 animate-spin text-primary" />
                        ) : (
                            <span className="text-muted-fg text-sm">Enter a ticker above</span>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
