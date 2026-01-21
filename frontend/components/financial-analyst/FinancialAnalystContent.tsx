'use client';

import { useState, useEffect, useCallback, memo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, AlertTriangle, Loader2, ExternalLink, TrendingUp, TrendingDown, ChevronUp, ChevronDown } from 'lucide-react';
import { TradingChart } from '@/components/chart/TradingChart';
import { TickerStrip } from '@/components/ticker/TickerStrip';
import { TickerSearch, TickerSearchRef } from '@/components/common/TickerSearch';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { ChartContent } from '@/components/chart/ChartContent';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';

// ============== Types ==============
interface AnalystRating { firm: string; rating: string; price_target: number | null; date: string | null; }
interface RiskFactor { category: string; description: string; severity: string; }
interface TechnicalSummary { trend: string; support_level?: number; resistance_level?: number; rsi_status?: string; ma_50_status?: string; ma_200_status?: string; pattern?: string; }
interface ShortInterest { short_percent_of_float?: number; days_to_cover?: number; short_ratio_change?: string; squeeze_potential?: string; }
interface UpcomingCatalyst { event: string; date?: string; importance: string; }
interface InsiderActivity { type: string; insider_name?: string; title?: string; shares?: number; value?: string; date?: string; }
interface FinancialHealth { revenue_growth_yoy?: number; earnings_growth_yoy?: number; debt_to_equity?: number; current_ratio?: number; cash_position?: string; profit_margin?: number; roe?: number; }
interface NewsSentiment { overall: string; score?: number; trending_topics?: string[]; recent_headlines?: string[]; }

interface AIReport {
    ticker: string;
    company_name: string;
    sector: string | null;
    industry: string | null;
    exchange?: string;
    ceo?: string;
    website?: string;
    employees?: number;
    business_summary: string;
    special_status: string | null;
    consensus_rating: string | null;
    analyst_ratings: AnalystRating[];
    average_price_target: number | null;
    price_target_high: number | null;
    price_target_low: number | null;
    num_analysts?: number;
    pe_ratio: number | null;
    forward_pe: number | null;
    pb_ratio: number | null;
    ps_ratio?: number | null;
    ev_ebitda: number | null;
    peg_ratio?: number | null;
    dividend_yield: number | null;
    dividend_frequency: string | null;
    ex_dividend_date?: string | null;
    technical?: TechnicalSummary;
    short_interest?: ShortInterest;
    competitors?: { ticker: string; name: string; market_cap?: string; }[];
    competitive_moat?: string;
    market_position?: string;
    financial_health?: FinancialHealth;
    financial_grade?: string;
    upcoming_catalysts?: UpcomingCatalyst[];
    earnings_date?: string;
    insider_activity?: InsiderActivity[];
    insider_sentiment?: string;
    news_sentiment?: NewsSentiment;
    risk_sentiment: string | null;
    risk_factors: (RiskFactor | string)[];
    risk_score?: number;
    critical_event: string | null;
    generated_at: string;
    _instant?: boolean;  // Flag para datos instantáneos
}

interface CompanyData { logoUrl?: string; website?: string; ceo?: string; exchange?: string; }

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.tradeul.com';

// Formatters
const fmt = (n: number | null | undefined, d = 2) => n == null ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (n: number | null | undefined) => n == null ? '—' : `${n >= 0 ? '+' : ''}${fmt(n)}%`;
const money = (n: number | null | undefined) => n == null ? '—' : `$${fmt(n, 0)}`;

// Color helpers
const ratingColor = (r: string | null | undefined) => {
    if (!r) return 'text-slate-400';
    const l = r.toLowerCase();
    if (l.includes('strong buy') || l.includes('overweight') || l.includes('outperform')) return 'text-emerald-500';
    if (l.includes('buy') || l.includes('bullish') || l.includes('positive')) return 'text-green-500';
    if (l.includes('hold') || l.includes('neutral')) return 'text-amber-500';
    if (l.includes('sell') || l.includes('underweight') || l.includes('bearish') || l.includes('negative')) return 'text-red-500';
    return 'text-slate-500';
};

const gradeColor = (g: string | undefined) => {
    if (!g) return 'text-slate-400';
    if (g.startsWith('A')) return 'text-emerald-500';
    if (g.startsWith('B')) return 'text-blue-500';
    if (g.startsWith('C')) return 'text-amber-500';
    return 'text-red-500';
};

// Section Title - Godel style with underline
const SectionTitle = ({ children, loading }: { children: React.ReactNode; loading?: boolean }) => (
    <div className="mb-1.5">
        <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-semibold text-slate-600 uppercase tracking-wider">{children}</span>
            {loading && <Loader2 className="w-2.5 h-2.5 animate-spin text-blue-500" />}
        </div>
        <div className="h-px bg-slate-200 mt-1" />
    </div>
);

// Data Row - Compact, aligned (darker text for readability)
const Row = ({ label, value, valueClass = '', loading }: { label: string; value: React.ReactNode; valueClass?: string; loading?: boolean }) => (
    <div className="flex justify-between items-center leading-[18px]">
        <span className="text-[10px] text-slate-600">{label}</span>
        {loading ? (
            <span className="text-[10px] text-slate-300">...</span>
        ) : (
            <span className={`text-[10px] font-medium ${valueClass || 'text-slate-800'}`}>{value}</span>
        )}
    </div>
);

// MA indicator
const MAArrow = ({ status }: { status?: string }) => {
    if (!status || status === 'Unknown') return null;
    return status === 'Above' 
        ? <ChevronUp className="w-3 h-3 text-green-500 inline" />
        : <ChevronDown className="w-3 h-3 text-red-500 inline" />;
};

// Loading placeholder for Gemini sections
const GeminiLoading = ({ text }: { text: string }) => (
    <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
        <Loader2 className="w-3 h-3 animate-spin text-blue-400" />
        <span>{text}</span>
    </div>
);

export function FinancialAnalystContent({ initialTicker }: { initialTicker?: string }) {
    const { t, i18n } = useTranslation();
    const { openWindow } = useFloatingWindow();
    const font = useUserPreferencesStore(selectFont);
    const fontFamily = `var(--font-${font})`;
    const isSpanish = i18n.language === 'es';

    const [ticker, setTicker] = useState(initialTicker || '');
    const [inputValue, setInputValue] = useState(initialTicker || '');
    const [company, setCompany] = useState<CompanyData | null>(null);
    const [report, setReport] = useState<AIReport | null>(null);
    const tickerSearchRef = useRef<TickerSearchRef>(null);
    const [loadingInstant, setLoadingInstant] = useState(false);  // Fase 1: datos internos
    const [loadingGemini, setLoadingGemini] = useState(false);    // Fase 2: Gemini
    const [error, setError] = useState<string | null>(null);

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

    // Carga progresiva en 2 fases
    const fetchReport = useCallback(async (symbol: string) => {
        const normalizedSymbol = symbol.toUpperCase().trim();
        setTicker(normalizedSymbol);
        setLoadingInstant(true);
        setLoadingGemini(false);
        setError(null);
        setReport(null);
        setCompany(null);

        try {
            // === FASE 1: Datos instantáneos (~1-2s) ===
            const instantRes = await fetch(`${API_URL}/api/report/${normalizedSymbol}/instant`);
            if (!instantRes.ok) {
                throw new Error(`Error ${instantRes.status}`);
            }
            const instantData = await instantRes.json();
            setReport(instantData);
            fetchCompanyData(normalizedSymbol);
            setLoadingInstant(false);
            
            // === FASE 2: Datos de Gemini (en paralelo) ===
            setLoadingGemini(true);
            const lang = isSpanish ? 'es' : 'en';
            const geminiRes = await fetch(`${API_URL}/api/report/${normalizedSymbol}?lang=${lang}`);
            if (geminiRes.ok) {
                const geminiData = await geminiRes.json();
                setReport(geminiData);  // Sobrescribe con datos completos
            }
        } catch (err) {
            console.error('Report fetch error:', err);
            setError(err instanceof Error ? err.message : 'Failed to generate report');
        } finally {
            setLoadingInstant(false);
            setLoadingGemini(false);
        }
    }, [isSpanish, fetchCompanyData]);

    useEffect(() => { if (initialTicker) fetchReport(initialTicker); }, [initialTicker, fetchReport]);
    
    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        tickerSearchRef.current?.close();
        if (inputValue.trim()) fetchReport(inputValue.trim());
    };
    
    const handleOpenChart = useCallback(() => {
        openWindow({
            title: 'Chart', content: <ChartContent ticker={ticker} />,
            width: 900, height: 600, x: Math.max(50, window.innerWidth / 2 - 450), y: Math.max(80, window.innerHeight / 2 - 300), minWidth: 600, minHeight: 400
        });
    }, [ticker, openWindow]);

    const r = report;
    const tech = r?.technical;
    const si = r?.short_interest;
    const fh = r?.financial_health;
    const ns = r?.news_sentiment;
    const isInstant = r?._instant;  // ¿Estamos mostrando solo datos instantáneos?
    const loading = loadingInstant;

    return (
        <div className="h-full flex flex-col bg-white text-slate-700" style={{ fontFamily }}>
            {/* Search Bar */}
            <div className="px-2 py-1.5 border-b border-slate-200">
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
                        className="px-3 py-1 text-[11px] font-medium bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center gap-1.5"
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

            <div className="flex-1 overflow-auto">
                {!ticker ? (
                    <div className="flex flex-col items-center justify-center h-full text-slate-300">
                        <div className="text-sm">{isSpanish ? 'Introduce un ticker para analizar' : 'Enter a ticker to analyze'}</div>
                    </div>
                ) : loading ? (
                    <div className="flex flex-col items-center justify-center h-full gap-2">
                        <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
                        <div className="text-xs text-slate-500">{isSpanish ? 'Buscando' : 'Searching'} {ticker}...</div>
                    </div>
                ) : error ? (
                    <div className="flex flex-col items-center justify-center h-full gap-2 px-4">
                        <AlertTriangle className="w-5 h-5 text-amber-400" />
                        <div className="text-xs text-slate-500 text-center">{error}</div>
                        <button onClick={() => fetchReport(ticker)} className="px-3 py-1 text-[10px] border border-slate-200 rounded flex items-center gap-1.5 hover:bg-slate-50">
                            {isSpanish ? 'Reintentar' : 'Retry'}
                        </button>
                    </div>
                ) : r && (
                    <div className="flex h-full">
                        {/* Main Content */}
                        <div className="flex-1 overflow-auto">
                            {/* Header */}
                            <div className="px-3 py-2 border-b border-slate-200">
                                <div className="flex items-center gap-2">
                                    {company?.logoUrl && (
                                        <img src={company.logoUrl} alt="" className="w-8 h-8 rounded border border-slate-200 bg-white p-0.5 object-contain" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
                                    )}
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-1.5">
                                            <span className="font-semibold text-sm text-slate-800">{r.ticker}</span>
                                            <span className="text-slate-500 text-xs truncate">{r.company_name}</span>
                                            {r.special_status && <span className="text-[8px] font-medium text-amber-600 bg-amber-50 px-1 py-0.5 rounded">{r.special_status}</span>}
                                            {loadingGemini && (
                                                <span className="text-[8px] font-medium text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded flex items-center gap-1">
                                                    <Loader2 className="w-2 h-2 animate-spin" />
                                                    {isSpanish ? 'Analizando...' : 'Analyzing...'}
                                                </span>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-1 text-[9px] text-slate-500">
                                            <span>{company?.exchange || r.exchange}</span>
                                            <span>•</span>
                                            <span className="truncate">{r.sector}</span>
                                            {(company?.ceo || r.ceo) && <><span>•</span><span>CEO: {company?.ceo || r.ceo}</span></>}
                                            {(company?.website || r.website) && (
                                                <a href={company?.website || r.website} target="_blank" rel="noopener noreferrer" className="text-slate-500 hover:text-slate-700">
                                                    <ExternalLink className="w-2.5 h-2.5" />
                                                </a>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Quote */}
                            <div className="px-3 py-1 border-b border-slate-200 bg-slate-50">
                                <TickerStrip symbol={ticker} exchange={company?.exchange || r.exchange || 'US'} />
                            </div>

                            {/* Critical Event */}
                            {r.critical_event && (
                                <div className="mx-3 mt-2 p-2 bg-red-50 border border-red-200 rounded text-[10px] text-red-700 flex items-start gap-1.5">
                                    <AlertTriangle className="w-3.5 h-3.5 text-red-500 shrink-0 mt-0.5" />
                                    <span>{r.critical_event}</span>
                                </div>
                            )}

                            {/* Business Description */}
                            {r.business_summary && (
                                <div className="px-3 py-2 border-b border-slate-200">
                                    <div className="text-[9px] font-semibold text-slate-600 uppercase tracking-wider mb-1">{isSpanish ? 'Acerca de' : 'About'}</div>
                                    <p className="text-[10px] text-slate-700 leading-[14px] line-clamp-3">{r.business_summary}</p>
                                </div>
                            )}

                            {/* Chart - altura suficiente para mostrar eje X */}
                            <div className="px-3 py-2">
                                <div className="text-[9px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{isSpanish ? 'Gráfico' : 'Price Chart'}</div>
                                <div className="rounded border border-slate-200 overflow-hidden" style={{ height: '250px' }}>
                                    <TradingChart ticker={ticker} minimal={true} onOpenChart={handleOpenChart} />
                                </div>
                            </div>

                            {/* Stats Grid - 2 columns compact */}
                            <div className="px-3 py-2 grid grid-cols-2 gap-x-4 gap-y-2 border-t border-slate-200">
                                {/* Overview - datos internos (instantáneos) */}
                                <div>
                                    <SectionTitle>Overview</SectionTitle>
                                    <Row label="P/E" value={fmt(r.pe_ratio)} />
                                    <Row label="Forward P/E" value={fmt(r.forward_pe)} loading={isInstant && loadingGemini} />
                                    <Row label="EV/EBITDA" value={fmt(r.ev_ebitda)} />
                                    <Row label="P/S" value={fmt(r.ps_ratio)} />
                                    <Row label="Dividend" value={r.dividend_yield ? `${fmt(r.dividend_yield)}%` : '—'} valueClass={r.dividend_yield ? 'text-green-500' : 'text-slate-400'} loading={isInstant && loadingGemini} />
                                </div>

                                {/* Financials */}
                                <div>
                                    <SectionTitle loading={isInstant && loadingGemini}>Financials</SectionTitle>
                                    <Row label="Grade" value={r.financial_grade || '—'} valueClass={gradeColor(r.financial_grade)} loading={isInstant && loadingGemini} />
                                    <Row label="Rev Growth" value={pct(fh?.revenue_growth_yoy)} valueClass={fh?.revenue_growth_yoy && fh.revenue_growth_yoy > 0 ? 'text-green-500' : 'text-red-500'} loading={isInstant && loadingGemini} />
                                    <Row label="EPS Growth" value={pct(fh?.earnings_growth_yoy)} valueClass={fh?.earnings_growth_yoy && fh.earnings_growth_yoy > 0 ? 'text-green-500' : 'text-red-500'} loading={isInstant && loadingGemini} />
                                    <Row label="Profit Margin" value={fh?.profit_margin ? `${fmt(fh.profit_margin)}%` : '—'} />
                                    <Row label="D/E Ratio" value={fmt(fh?.debt_to_equity)} />
                                </div>
                            </div>

                            {/* Analyst Ratings - Requiere Gemini */}
                            <div className="px-3 py-2 border-t border-slate-200">
                                <SectionTitle loading={isInstant && loadingGemini}>{isSpanish ? 'Ratings de Analistas' : 'Analyst Ratings'}</SectionTitle>
                                {isInstant && loadingGemini ? (
                                    <GeminiLoading text={isSpanish ? 'Buscando ratings...' : 'Searching ratings...'} />
                                ) : r.analyst_ratings && r.analyst_ratings.length > 0 ? (
                                    <div className="space-y-0.5">
                                        {r.analyst_ratings.map((ar, i) => (
                                            <div key={i} className="flex items-center text-[10px] leading-[16px]">
                                                <span className="text-slate-600 w-[100px] truncate">{ar.firm}</span>
                                                <span className={`w-[70px] font-medium ${ratingColor(ar.rating)}`}>{ar.rating}</span>
                                                <span className="text-slate-800 w-[50px] text-right">{ar.price_target ? money(ar.price_target) : '—'}</span>
                                                {ar.date && <span className="text-slate-500 ml-2 text-[9px]">{ar.date}</span>}
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="text-[10px] text-slate-500">{isSpanish ? 'Sin ratings disponibles' : 'No ratings available'}</div>
                                )}
                            </div>

                            {/* Risk Factors - Requiere Gemini */}
                            <div className="px-3 py-2 border-t border-slate-200">
                                <SectionTitle loading={isInstant && loadingGemini}>{isSpanish ? 'Factores de Riesgo' : 'Risk Factors'}</SectionTitle>
                                {isInstant && loadingGemini ? (
                                    <GeminiLoading text={isSpanish ? 'Analizando riesgos...' : 'Analyzing risks...'} />
                                ) : r.risk_factors && r.risk_factors.length > 0 ? (
                                    <div className="space-y-0.5">
                                        {r.risk_factors.slice(0, 4).map((rf, i) => (
                                            <div key={i} className="text-[10px] text-slate-700 leading-[14px] flex">
                                                <span className="text-slate-400 mr-1.5">•</span>
                                                <span>{typeof rf === 'string' ? rf : rf.description}</span>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="text-[10px] text-slate-500">{isSpanish ? 'Sin riesgos mayores' : 'No major risks'}</div>
                                )}
                            </div>

                            {/* News - Requiere Gemini */}
                            <div className="px-3 py-2 border-t border-slate-200">
                                <SectionTitle loading={isInstant && loadingGemini}>{isSpanish ? 'Noticias' : 'News'}</SectionTitle>
                                {isInstant && loadingGemini ? (
                                    <GeminiLoading text={isSpanish ? 'Buscando noticias...' : 'Searching news...'} />
                                ) : ns ? (
                                    <>
                                        <div className="flex items-center gap-1.5 mb-1">
                                            {(ns.overall === 'Bullish' || ns.overall === 'Positive') && <TrendingUp className="w-3 h-3 text-green-500" />}
                                            {(ns.overall === 'Bearish' || ns.overall === 'Negative') && <TrendingDown className="w-3 h-3 text-red-500" />}
                                            <span className={`text-[10px] font-medium ${ratingColor(ns.overall)}`}>{ns.overall}</span>
                                            {ns.score && <span className={`text-[9px] ${ns.score > 0 ? 'text-green-500' : 'text-red-500'}`}>({ns.score > 0 ? '+' : ''}{ns.score})</span>}
                                        </div>
                                        {ns.recent_headlines && ns.recent_headlines.length > 0 && (
                                            <div className="space-y-0.5">
                                                {ns.recent_headlines.slice(0, 2).map((h, i) => (
                                                    <div key={i} className="text-[9px] text-slate-600 leading-[13px]">• {h}</div>
                                                ))}
                                            </div>
                                        )}
                                    </>
                                ) : (
                                    <div className="text-[10px] text-slate-500">{isSpanish ? 'Sin noticias recientes' : 'No recent news'}</div>
                                )}
                            </div>
                        </div>

                        {/* Sidebar */}
                        <div className="w-[180px] shrink-0 border-l border-slate-200 bg-slate-50/50 overflow-auto">
                            <div className="p-2 space-y-3">
                                {/* Summary - Requiere Gemini */}
                                <div>
                                    <SectionTitle loading={isInstant && loadingGemini}>{isSpanish ? 'Resumen' : 'Summary'}</SectionTitle>
                                    <Row label="Consensus" value={r.consensus_rating || '—'} valueClass={ratingColor(r.consensus_rating)} loading={isInstant && loadingGemini} />
                                    <Row label="Price Target" value={r.average_price_target ? money(r.average_price_target) : '—'} loading={isInstant && loadingGemini} />
                                    {r.price_target_low && r.price_target_high && (
                                        <Row label="Range" value={`${money(r.price_target_low)}-${money(r.price_target_high)}`} valueClass="text-slate-500 text-[9px]" />
                                    )}
                                    {r.risk_score && (
                                        <Row label="Risk Score" value={`${r.risk_score}/10`} valueClass={r.risk_score <= 3 ? 'text-green-500' : r.risk_score <= 6 ? 'text-amber-500' : 'text-red-500'} />
                                    )}
                                </div>

                                {/* Technical - Datos internos */}
                                <div>
                                    <SectionTitle>{isSpanish ? 'Técnico' : 'Technical'}</SectionTitle>
                                    <Row label="Trend" value={tech?.trend || '—'} valueClass={ratingColor(tech?.trend)} loading={isInstant && loadingGemini} />
                                    <Row label="RSI" value={tech?.rsi_status || '—'} valueClass={tech?.rsi_status === 'Oversold' ? 'text-green-500' : tech?.rsi_status === 'Overbought' ? 'text-red-500' : ''} />
                                    <Row label="MA-50" value={<>{tech?.ma_50_status || '—'}<MAArrow status={tech?.ma_50_status} /></>} />
                                    <Row label="MA-200" value={<>{tech?.ma_200_status || '—'}<MAArrow status={tech?.ma_200_status} /></>} />
                                    <Row label="Support" value={tech?.support_level ? money(tech.support_level) : '—'} loading={isInstant && loadingGemini} />
                                    <Row label="Resistance" value={tech?.resistance_level ? money(tech.resistance_level) : '—'} loading={isInstant && loadingGemini} />
                                </div>

                                {/* Short Interest - Requiere Gemini */}
                                <div>
                                    <SectionTitle loading={isInstant && loadingGemini}>Short Interest</SectionTitle>
                                    <Row label="% of Float" value={si?.short_percent_of_float ? `${fmt(si.short_percent_of_float)}%` : '—'} valueClass={si?.short_percent_of_float && si.short_percent_of_float > 15 ? 'text-red-500' : ''} loading={isInstant && loadingGemini} />
                                    <Row label="Days to Cover" value={si?.days_to_cover ? fmt(si.days_to_cover, 1) : '—'} loading={isInstant && loadingGemini} />
                                    <Row label="Squeeze Risk" value={si?.squeeze_potential || '—'} valueClass={si?.squeeze_potential === 'High' ? 'text-red-500' : ''} loading={isInstant && loadingGemini} />
                                </div>

                                {/* Insider - Datos internos */}
                                <div>
                                    <SectionTitle>Insider Activity</SectionTitle>
                                    <Row label="Sentiment" value={r.insider_sentiment || '—'} valueClass={ratingColor(r.insider_sentiment)} />
                                    {r.insider_activity && r.insider_activity.slice(0, 3).map((ins, i) => (
                                        <div key={i} className="flex items-center text-[10px] leading-[16px]">
                                            <span className={`w-[30px] font-medium ${ins.type === 'Buy' ? 'text-green-500' : 'text-red-500'}`}>{ins.type}</span>
                                            <span className="text-slate-500 flex-1 truncate text-[9px]">{ins.title || ins.insider_name}</span>
                                            <span className="text-slate-700">{ins.value || '—'}</span>
                                        </div>
                                    ))}
                                </div>

                                {/* Catalysts - Requiere Gemini */}
                                <div>
                                    <SectionTitle loading={isInstant && loadingGemini}>{isSpanish ? 'Catalizadores' : 'Catalysts'}</SectionTitle>
                                    {isInstant && loadingGemini ? (
                                        <GeminiLoading text={isSpanish ? 'Buscando eventos...' : 'Searching events...'} />
                                    ) : (
                                        <>
                                            {r.earnings_date && (
                                                <div className="text-[10px] text-blue-600 leading-[16px] flex items-center gap-1">
                                                    <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                                                    Earnings: {r.earnings_date}
                                                </div>
                                            )}
                                            {r.upcoming_catalysts?.slice(0, 3).map((cat, i) => (
                                                <div key={i} className="text-[10px] text-slate-700 leading-[16px] flex items-center gap-1">
                                                    <span className={`w-1.5 h-1.5 rounded-full ${cat.importance === 'High' ? 'bg-red-400' : 'bg-slate-400'}`} />
                                                    <span className="truncate">{cat.event}</span>
                                                </div>
                                            ))}
                                            {!r.earnings_date && (!r.upcoming_catalysts || r.upcoming_catalysts.length === 0) && (
                                                <div className="text-[10px] text-slate-500">{isSpanish ? 'Sin eventos programados' : 'None scheduled'}</div>
                                            )}
                                        </>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default memo(FinancialAnalystContent);
