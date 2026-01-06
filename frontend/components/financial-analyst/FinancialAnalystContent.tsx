'use client';

import { useState, useEffect, useCallback, memo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw, TrendingUp, TrendingDown, AlertTriangle, Loader2, ExternalLink, Target, Activity, Users, Calendar, Shield, BarChart3, Zap } from 'lucide-react';
import { TradingChart } from '@/components/chart/TradingChart';
import { TickerStrip } from '@/components/ticker/TickerStrip';
import { TickerSearch, TickerSearchRef } from '@/components/common/TickerSearch';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { ChartContent } from '@/components/chart/ChartContent';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';

// ============== Types ==============
interface AnalystRating { firm: string; rating: string; price_target: number | null; date: string | null; }
interface RiskFactor { category: string; description: string; severity: string; }
interface Competitor { ticker: string; name: string; market_cap?: string; competitive_advantage?: string; }
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
    competitors?: Competitor[];
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
}

interface CompanyData { logoUrl?: string; website?: string; ceo?: string; exchange?: string; }

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.tradeul.com';
const fmt = (n: number | null | undefined, d = 2) => n == null ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (n: number | null | undefined) => n == null ? '—' : `${n >= 0 ? '+' : ''}${fmt(n)}%`;

// Color helpers
const rc = (r: string | null | undefined) => { if (!r) return 'text-slate-600'; const l = r.toLowerCase(); if (l.includes('buy') || l.includes('overweight') || l.includes('bullish') || l.includes('strong')) return 'text-green-600'; if (l.includes('hold') || l.includes('neutral')) return 'text-amber-600'; if (l.includes('sell') || l.includes('underweight') || l.includes('bearish')) return 'text-red-600'; return 'text-slate-600'; };
const sc = (s: string | undefined) => { if (!s) return 'text-slate-500'; const l = s.toLowerCase(); if (l === 'high' || l === 'critical') return 'text-red-600'; if (l === 'medium') return 'text-amber-600'; return 'text-slate-500'; };
const gc = (g: string | undefined) => { if (!g) return 'text-slate-600'; if (g === 'A' || g === 'A+') return 'text-green-600'; if (g === 'B') return 'text-blue-600'; if (g === 'C') return 'text-amber-600'; return 'text-red-600'; };

// Row for key-value pairs
const Row = ({ label, value, valueClass = '' }: { label: string; value: React.ReactNode; valueClass?: string }) => (
    <div className="flex justify-between items-center py-0.5"><span className="text-slate-400">{label}</span><span className={valueClass || 'text-slate-700'}>{value}</span></div>
);

export function FinancialAnalystContent({ initialTicker }: { initialTicker?: string }) {
    const { i18n } = useTranslation();
    const { openWindow } = useFloatingWindow();
    const font = useUserPreferencesStore(selectFont);
    const fontFamily = `var(--font-${font})`;

    const [ticker, setTicker] = useState(initialTicker || '');
    const [inputValue, setInputValue] = useState(initialTicker || '');
    const [company, setCompany] = useState<CompanyData | null>(null);
    const [report, setReport] = useState<AIReport | null>(null);
    const tickerSearchRef = useRef<TickerSearchRef>(null);
    const [loading, setLoading] = useState(false);
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

    const fetchReport = useCallback(async (symbol: string) => {
        const normalizedSymbol = symbol.toUpperCase().trim();
        setTicker(normalizedSymbol);
        setLoading(true);
        setError(null);
        setReport(null);
        setCompany(null);
        try {
            const lang = i18n.language === 'es' ? 'es' : 'en';
            const res = await fetch(`${API_URL}/api/report/${normalizedSymbol}?lang=${lang}`);
            if (!res.ok) {
                const errText = await res.text().catch(() => '');
                throw new Error(`Error ${res.status}${errText ? `: ${errText.slice(0, 100)}` : ''}`);
            }
            const data = await res.json();
            setReport(data);
            fetchCompanyData(normalizedSymbol);
        } catch (err) {
            console.error('Report fetch error:', err);
            setError(err instanceof Error ? err.message : 'Failed to generate report');
        }
        finally { setLoading(false); }
    }, [i18n.language, fetchCompanyData]);

    useEffect(() => { if (initialTicker) fetchReport(initialTicker); }, [initialTicker, fetchReport]);
    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        tickerSearchRef.current?.close(); // Close dropdown on submit
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

    return (
        <div className="h-full flex flex-col bg-white text-slate-700" style={{ fontFamily }}>
            {/* Search Bar */}
            <div className="px-3 py-2 border-b border-slate-200">
                <form onSubmit={handleSubmit} className="flex items-center gap-2">
                    <TickerSearch
                        ref={tickerSearchRef}
                        value={inputValue}
                        onChange={setInputValue}
                        onSelect={(t) => {
                            setInputValue(t.symbol);
                            fetchReport(t.symbol);
                        }}
                        placeholder="Ticker..."
                        className="flex-1"
                        autoFocus={false}
                    />
                    <button
                        type="submit"
                        disabled={loading || !inputValue.trim()}
                        className="px-3 py-1 text-sm font-medium text-slate-600 hover:text-slate-900 disabled:opacity-50"
                    >
                        {loading ? '...' : 'Go'}
                    </button>
                </form>
            </div>

            <div className="flex-1 overflow-auto text-[10px]">
                {!ticker ? <div className="flex items-center justify-center h-full text-slate-400 text-xs">Enter a ticker</div>
                    : loading ? <div className="flex flex-col items-center justify-center h-full gap-2"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /><span className="text-xs text-slate-500">Analyzing {ticker}...</span></div>
                        : error ? <div className="flex flex-col items-center justify-center h-full gap-2 text-slate-500 px-4"><AlertTriangle className="w-5 h-5 text-amber-500" /><span className="text-xs text-center">{error}</span><button onClick={() => fetchReport(ticker)} className="mt-1 px-3 py-1 text-xs border rounded flex items-center gap-1.5 hover:bg-slate-50"><RefreshCw className="w-3 h-3" />Retry</button></div>
                            : r && (
                                <div className="min-h-full">
                                    {/* Header: Logo + Info + Consensus */}
                                    <div className="flex gap-3 px-3 py-2 border-b border-slate-200">
                                        {company?.logoUrl && <img src={company.logoUrl} alt="" className="w-11 h-11 rounded border border-slate-200 bg-white p-0.5 object-contain shrink-0" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />}
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-start justify-between gap-2">
                                                <div>
                                                    <div className="flex items-baseline gap-2">
                                                        <span className="font-bold text-sm text-slate-800">{r.ticker}</span>
                                                        <span className="text-slate-600 text-[11px]">{r.company_name}</span>
                                                    </div>
                                                    {r.special_status && <span className="text-[9px] font-medium text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded inline-block">{r.special_status}</span>}
                                                    <div className="flex flex-wrap items-center gap-x-1.5 text-[9px] text-slate-500 mt-0.5">
                                                        <span>{company?.exchange || r.exchange || 'US'}</span>•<span>{r.sector}</span>•<span>{r.industry}</span>
                                                        {(company?.ceo || r.ceo) && <><span>•</span><span>CEO: {company?.ceo || r.ceo}</span></>}
                                                        {(company?.website || r.website) && <a href={company?.website || r.website} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline flex items-center gap-0.5 ml-1"><ExternalLink className="w-2.5 h-2.5" /></a>}
                                                    </div>
                                                </div>
                                                <div className="text-right shrink-0">
                                                    <div className={`text-lg font-bold ${rc(r.consensus_rating)}`}>{r.consensus_rating || '—'}</div>
                                                    <div className="text-[8px] text-slate-400">{r.num_analysts ? `${r.num_analysts} analysts` : 'Consensus'}</div>
                                                </div>
                                            </div>
                                            <p className="text-[9px] text-slate-500 mt-1 leading-snug line-clamp-2">{r.business_summary}</p>
                                        </div>
                                    </div>

                                    {/* Quote Strip */}
                                    <div className="px-3 py-1 border-b border-slate-200 bg-slate-50">
                                        <TickerStrip symbol={ticker} exchange={company?.exchange || r.exchange || 'US'} />
                                    </div>

                                    {/* Critical Event Banner */}
                                    {r.critical_event && (
                                        <div className="bg-red-50 border-b border-red-200 px-3 py-1.5 flex items-start gap-2">
                                            <AlertTriangle className="w-3.5 h-3.5 text-red-600 shrink-0 mt-0.5" />
                                            <div>
                                                <span className="text-[9px] font-bold text-red-600 uppercase">Critical: </span>
                                                <span className="text-[10px] text-red-700">{r.critical_event}</span>
                                            </div>
                                        </div>
                                    )}

                                    {/* Chart - Full Width */}
                                    <div className="border-b border-slate-200" style={{ height: '180px' }}>
                                        <TradingChart ticker={ticker} minimal={true} onOpenChart={handleOpenChart} />
                                    </div>

                                    {/* 4-Column Grid: Price Targets, Valuation, Financial Health, Dividend */}
                                    <div className="grid grid-cols-4 divide-x divide-slate-200 border-b border-slate-200 text-[9px]">
                                        {/* Price Targets */}
                                        <div className="p-2">
                                            <div className="flex items-center gap-1 text-[9px] font-bold text-slate-500 uppercase mb-1"><Target className="w-3 h-3" />Price Targets</div>
                                            <Row label="Average" value={r.average_price_target ? `$${fmt(r.average_price_target, 0)}` : '—'} valueClass="font-medium" />
                                            <Row label="High" value={r.price_target_high ? `$${fmt(r.price_target_high, 0)}` : '—'} valueClass="text-green-600" />
                                            <Row label="Low" value={r.price_target_low ? `$${fmt(r.price_target_low, 0)}` : '—'} valueClass="text-red-600" />
                                        </div>
                                        {/* Valuation */}
                                        <div className="p-2">
                                            <div className="flex items-center gap-1 text-[9px] font-bold text-slate-500 uppercase mb-1"><BarChart3 className="w-3 h-3" />Valuation</div>
                                            <Row label="P/E" value={fmt(r.pe_ratio)} />
                                            <Row label="Fwd P/E" value={fmt(r.forward_pe)} />
                                            <Row label="P/B" value={fmt(r.pb_ratio)} />
                                            <Row label="EV/EBITDA" value={fmt(r.ev_ebitda)} />
                                        </div>
                                        {/* Financial Health */}
                                        <div className="p-2">
                                            <div className="flex items-center gap-1 text-[9px] font-bold text-slate-500 uppercase mb-1"><Shield className="w-3 h-3" />Financial Health</div>
                                            <Row label="Grade" value={r.financial_grade || '—'} valueClass={`font-bold ${gc(r.financial_grade)}`} />
                                            <Row label="Rev Growth" value={pct(fh?.revenue_growth_yoy)} valueClass={fh?.revenue_growth_yoy && fh.revenue_growth_yoy > 0 ? 'text-green-600' : 'text-red-600'} />
                                            <Row label="D/E Ratio" value={fmt(fh?.debt_to_equity)} />
                                            <Row label="ROE" value={fh?.roe ? `${fmt(fh.roe)}%` : '—'} />
                                        </div>
                                        {/* Dividend */}
                                        <div className="p-2">
                                            <div className="flex items-center gap-1 text-[9px] font-bold text-slate-500 uppercase mb-1"><Calendar className="w-3 h-3" />Dividend</div>
                                            <Row label="Yield" value={r.dividend_yield ? `${fmt(r.dividend_yield)}%` : '—'} valueClass={r.dividend_yield && r.dividend_yield > 0 ? 'text-green-600' : ''} />
                                            <Row label="Frequency" value={r.dividend_frequency || '—'} />
                                            <Row label="Ex-Date" value={r.ex_dividend_date || '—'} />
                                        </div>
                                    </div>

                                    {/* 3-Column Grid: Technical, Short Interest, Earnings Growth */}
                                    <div className="grid grid-cols-3 divide-x divide-slate-200 border-b border-slate-200 text-[9px]">
                                        {/* Technical */}
                                        <div className="p-2">
                                            <div className="flex items-center gap-1 text-[9px] font-bold text-slate-500 uppercase mb-1"><Activity className="w-3 h-3" />Technical Analysis</div>
                                            <Row label="Trend" value={tech?.trend || '—'} valueClass={rc(tech?.trend)} />
                                            <Row label="Support" value={tech?.support_level ? `$${fmt(tech.support_level, 0)}` : '—'} />
                                            <Row label="Resistance" value={tech?.resistance_level ? `$${fmt(tech.resistance_level, 0)}` : '—'} />
                                            <Row label="RSI" value={tech?.rsi_status || '—'} valueClass={tech?.rsi_status === 'Oversold' ? 'text-green-600' : tech?.rsi_status === 'Overbought' ? 'text-red-600' : ''} />
                                            {tech?.pattern && <Row label="Pattern" value={tech.pattern} valueClass="text-blue-600" />}
                                        </div>
                                        {/* Short Interest */}
                                        <div className="p-2">
                                            <div className="flex items-center gap-1 text-[9px] font-bold text-slate-500 uppercase mb-1"><Zap className="w-3 h-3" />Short Interest</div>
                                            <Row label="% of Float" value={si?.short_percent_of_float ? `${fmt(si.short_percent_of_float)}%` : '—'} valueClass={si?.short_percent_of_float && si.short_percent_of_float > 20 ? 'text-red-600 font-medium' : ''} />
                                            <Row label="Days to Cover" value={si?.days_to_cover ? fmt(si.days_to_cover, 1) : '—'} />
                                            <Row label="Squeeze Risk" value={si?.squeeze_potential || '—'} valueClass={si?.squeeze_potential === 'High' ? 'text-red-600' : ''} />
                                            <Row label="SI Trend" value={si?.short_ratio_change || '—'} />
                                        </div>
                                        {/* Growth & Margins */}
                                        <div className="p-2">
                                            <div className="flex items-center gap-1 text-[9px] font-bold text-slate-500 uppercase mb-1"><TrendingUp className="w-3 h-3" />Growth & Margins</div>
                                            <Row label="EPS Growth" value={pct(fh?.earnings_growth_yoy)} valueClass={fh?.earnings_growth_yoy && fh.earnings_growth_yoy > 0 ? 'text-green-600' : 'text-red-600'} />
                                            <Row label="Profit Margin" value={fh?.profit_margin ? `${fmt(fh.profit_margin)}%` : '—'} />
                                            <Row label="Current Ratio" value={fmt(fh?.current_ratio)} />
                                            <Row label="Cash Position" value={fh?.cash_position || '—'} valueClass={fh?.cash_position === 'Strong' ? 'text-green-600' : fh?.cash_position === 'Weak' ? 'text-red-600' : ''} />
                                        </div>
                                    </div>

                                    {/* 3-Column Grid: Catalysts, Insider, Competitors */}
                                    <div className="grid grid-cols-3 divide-x divide-slate-200 border-b border-slate-200 text-[9px]">
                                        {/* Catalysts */}
                                        <div className="p-2">
                                            <div className="flex items-center gap-1 text-[9px] font-bold text-slate-500 uppercase mb-1"><Calendar className="w-3 h-3" />Catalysts</div>
                                            {r.earnings_date && <Row label="Earnings" value={r.earnings_date} valueClass="font-medium text-blue-600" />}
                                            {r.upcoming_catalysts && r.upcoming_catalysts.length > 0 ? (
                                                r.upcoming_catalysts.slice(0, 3).map((cat, i) => (
                                                    <div key={i} className="flex justify-between py-0.5">
                                                        <span className="text-slate-600 truncate flex-1 pr-1">{cat.event}</span>
                                                        <span className={`shrink-0 ${sc(cat.importance)}`}>{cat.date || '—'}</span>
                                                    </div>
                                                ))
                                            ) : !r.earnings_date && <div className="text-slate-400 py-0.5">No upcoming</div>}
                                        </div>
                                        {/* Insider */}
                                        <div className="p-2">
                                            <div className="flex items-center gap-1 text-[9px] font-bold text-slate-500 uppercase mb-1"><Users className="w-3 h-3" />Insider Activity</div>
                                            {r.insider_sentiment && <Row label="Sentiment" value={r.insider_sentiment} valueClass={rc(r.insider_sentiment)} />}
                                            {r.insider_activity && r.insider_activity.length > 0 ? (
                                                r.insider_activity.slice(0, 2).map((ins, i) => (
                                                    <div key={i} className="flex justify-between py-0.5">
                                                        <span className={`font-medium ${ins.type === 'Buy' ? 'text-green-600' : 'text-red-600'}`}>{ins.type}</span>
                                                        <span className="text-slate-600 truncate px-1">{ins.title || ins.insider_name}</span>
                                                        <span className="text-slate-700 shrink-0">{ins.value}</span>
                                                    </div>
                                                ))
                                            ) : !r.insider_sentiment && <div className="text-slate-400 py-0.5">No recent</div>}
                                        </div>
                                        {/* Competitors */}
                                        <div className="p-2">
                                            <div className="flex items-center gap-1 text-[9px] font-bold text-slate-500 uppercase mb-1"><Users className="w-3 h-3" />Competitors</div>
                                            {r.market_position && <Row label="Position" value={r.market_position} valueClass={r.market_position === 'Leader' ? 'text-green-600 font-medium' : ''} />}
                                            {r.competitive_moat && <Row label="Moat" value={r.competitive_moat} valueClass={r.competitive_moat === 'Wide' ? 'text-green-600' : ''} />}
                                            {r.competitors && r.competitors.slice(0, 2).map((c, i) => (
                                                <div key={i} className="flex justify-between py-0.5">
                                                    <span className="font-medium text-blue-600">{c.ticker}</span>
                                                    <span className="text-slate-500 truncate px-1">{c.name}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    {/* 2-Column: Analyst Ratings + Risk/News */}
                                    <div className="grid grid-cols-2 divide-x divide-slate-200 text-[9px]">
                                        {/* Analyst Ratings */}
                                        <div className="p-2">
                                            <div className="flex items-center gap-1 text-[9px] font-bold text-slate-500 uppercase mb-1"><Target className="w-3 h-3" />Recent Ratings</div>
                                            {r.analyst_ratings?.length > 0 ? (
                                                <table className="w-full">
                                                    <tbody>
                                                        {r.analyst_ratings.slice(0, 4).map((ar, i) => (
                                                            <tr key={i} className="border-b border-slate-100 last:border-0">
                                                                <td className="py-0.5 text-slate-600 truncate max-w-[80px]">{ar.firm}</td>
                                                                <td className={`py-0.5 text-center font-medium ${rc(ar.rating)}`}>{ar.rating}</td>
                                                                <td className="py-0.5 text-right text-slate-700">{ar.price_target ? `$${fmt(ar.price_target, 0)}` : ''}</td>
                                                            </tr>
                                                        ))}
                                                    </tbody>
                                                </table>
                                            ) : <div className="text-slate-400">No ratings available</div>}
                                        </div>
                                        {/* Risk + News */}
                                        <div className="p-2">
                                            <div className="flex items-center justify-between mb-1">
                                                <div className="flex items-center gap-1 text-[9px] font-bold text-slate-500 uppercase"><Shield className="w-3 h-3" />Risk</div>
                                                {r.risk_score && <span className={`text-[10px] font-bold ${r.risk_score <= 3 ? 'text-green-600' : r.risk_score <= 6 ? 'text-amber-600' : 'text-red-600'}`}>{r.risk_score}/10</span>}
                                            </div>
                                            {r.risk_factors?.length > 0 ? (
                                                <div className="space-y-0.5 mb-2">
                                                    {r.risk_factors.slice(0, 3).map((rf, i) => (
                                                        <div key={i} className="flex items-start gap-1 text-slate-600">
                                                            <span className="text-slate-300">•</span>
                                                            <span>{typeof rf === 'string' ? rf : rf.description}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            ) : <div className="text-slate-400 mb-2">No major risks</div>}

                                            {/* News Sentiment */}
                                            {ns && (
                                                <div className="pt-1 border-t border-slate-100">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        {(ns.overall === 'Bullish' || ns.overall === 'Positive') && <TrendingUp className="w-3 h-3 text-green-600" />}
                                                        {(ns.overall === 'Bearish' || ns.overall === 'Negative') && <TrendingDown className="w-3 h-3 text-red-600" />}
                                                        <span className={`font-medium ${rc(ns.overall)}`}>News: {ns.overall}</span>
                                                    </div>
                                                    {/* Headlines first - more important */}
                                                    {ns.recent_headlines && ns.recent_headlines.length > 0 && (
                                                        <div className="space-y-0.5 text-[8px] mb-1">
                                                            {ns.recent_headlines.slice(0, 2).map((h, i) => (
                                                                <div key={i} className="text-slate-600 leading-tight">• {h}</div>
                                                            ))}
                                                        </div>
                                                    )}
                                                    {/* Topics as tags */}
                                                    {ns.trending_topics && ns.trending_topics.length > 0 && (
                                                        <div className="flex flex-wrap gap-1">
                                                            {ns.trending_topics.slice(0, 3).map((t, i) => (
                                                                <span key={i} className="px-1 py-0.5 bg-red-50 text-red-600 rounded text-[7px]">{t}</span>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    {/* Footer */}
                                    <div className="px-3 py-1 border-t border-slate-200 bg-slate-50 text-[8px] text-slate-400 text-center">
                                        Updated: {new Date(r.generated_at).toLocaleString()} • Data may be delayed
                                    </div>
                                </div>
                            )}
            </div>
        </div>
    );
}

export default memo(FinancialAnalystContent);
