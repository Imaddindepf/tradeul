'use client';

import { useState, useEffect, useRef } from 'react';
import { TrendingUp, TrendingDown, ChevronUp, ChevronDown, Loader2 } from 'lucide-react';
import type { WidgetContext } from '../types';
import { useFanData } from './FanDataContext';
import { Row, GeminiLoading, fmt, money, ratingColor } from './helpers';

// ============================================================================
// CONSENSUS
// ============================================================================
export function ConsensusWidget(_: WidgetContext) {
    const { report: r, loadingGemini, isSpanish } = useFanData();
    if (!r) return null;
    const isInstant = r._instant;

    if (isInstant && loadingGemini) {
        return <GeminiLoading text={isSpanish ? 'Buscando consenso...' : 'Loading consensus...'} />;
    }

    return (
        <div className="flex flex-col h-full">
            <div className="flex flex-col items-center justify-center flex-1 gap-1">
                <div className={`text-[16px] font-bold leading-none ${ratingColor(r.consensus_rating)}`}>
                    {r.consensus_rating || '—'}
                </div>
                <div className="text-foreground tabular-nums">
                    {r.average_price_target ? `Target ${money(r.average_price_target)}` : '—'}
                </div>
                {r.price_target_low != null && r.price_target_high != null && (
                    <div className="text-muted-fg text-[9px]">
                        Range {money(r.price_target_low)} – {money(r.price_target_high)}
                    </div>
                )}
                {r.num_analysts && (
                    <div className="text-muted-fg text-[9px]">{r.num_analysts} analysts</div>
                )}
            </div>
        </div>
    );
}

// ============================================================================
// SHORT INTEREST
// ============================================================================
export function ShortInterestWidget(_: WidgetContext) {
    const { report: r, loadingGemini, isSpanish } = useFanData();
    if (!r) return null;
    const si = r.short_interest;
    const isInstant = r._instant;

    if (isInstant && loadingGemini) {
        return <GeminiLoading text={isSpanish ? 'Buscando short interest...' : 'Loading short data...'} />;
    }

    return (
        <div>
            <Row label="% of Float"
                value={si?.short_percent_of_float ? `${fmt(si.short_percent_of_float)}%` : '—'}
                valueClass={si?.short_percent_of_float && si.short_percent_of_float > 15 ? 'text-red-500' : ''} />
            <Row label="Days to Cover" value={si?.days_to_cover ? fmt(si.days_to_cover, 1) : '—'} />
            <Row label="SI Change" value={si?.short_ratio_change || '—'}
                valueClass={si?.short_ratio_change?.toLowerCase().includes('increase') ? 'text-red-500' : 'text-green-500'} />
            <Row label="Squeeze Risk" value={si?.squeeze_potential || '—'}
                valueClass={si?.squeeze_potential === 'High' ? 'text-red-500' : si?.squeeze_potential === 'Low' ? 'text-green-500' : ''} />
        </div>
    );
}

// ============================================================================
// TECHNICAL INDICATORS
// ============================================================================
function MAArrow({ status }: { status?: string }) {
    if (!status || status === 'Unknown') return null;
    return status === 'Above'
        ? <ChevronUp className="w-3 h-3 text-green-500 inline" />
        : <ChevronDown className="w-3 h-3 text-red-500 inline" />;
}

export function TechnicalWidget(_: WidgetContext) {
    const { report: r, loadingGemini, isSpanish } = useFanData();
    if (!r) return null;
    const tech = r.technical;
    const isInstant = r._instant;

    return (
        <div>
            <Row label="Trend" value={tech?.trend || '—'} valueClass={ratingColor(tech?.trend)} loading={isInstant && loadingGemini} />
            <Row label="RSI" value={tech?.rsi_status || '—'}
                valueClass={tech?.rsi_status === 'Oversold' ? 'text-green-500' : tech?.rsi_status === 'Overbought' ? 'text-red-500' : ''} />
            <Row label="MA-50" value={<>{tech?.ma_50_status || '—'}<MAArrow status={tech?.ma_50_status} /></>} />
            <Row label="MA-200" value={<>{tech?.ma_200_status || '—'}<MAArrow status={tech?.ma_200_status} /></>} />
            <Row label="Support" value={tech?.support_level ? money(tech.support_level) : '—'} loading={isInstant && loadingGemini} />
            <Row label="Resistance" value={tech?.resistance_level ? money(tech.resistance_level) : '—'} loading={isInstant && loadingGemini} />
            {tech?.pattern && <Row label="Pattern" value={tech.pattern} />}
        </div>
    );
}

// ============================================================================
// ANALYST RATINGS TABLE
// ============================================================================
export function RatingsWidget(_: WidgetContext) {
    const { report: r, loadingGemini, isSpanish } = useFanData();
    if (!r) return null;
    const isInstant = r._instant;

    if (isInstant && loadingGemini) {
        return <GeminiLoading text={isSpanish ? 'Buscando ratings...' : 'Loading ratings...'} />;
    }

    if (!r.analyst_ratings || r.analyst_ratings.length === 0) {
        return <div className="text-[10px] text-muted-fg">{isSpanish ? 'Sin ratings' : 'No ratings available'}</div>;
    }

    return (
        <table className="w-full text-[10px]">
            <thead>
                <tr className="text-[9px] uppercase text-muted-fg">
                    <th className="text-left font-normal pb-0.5">Firm</th>
                    <th className="text-left font-normal pb-0.5">Rating</th>
                    <th className="text-right font-normal pb-0.5">PT</th>
                    <th className="text-right font-normal pb-0.5">Date</th>
                </tr>
            </thead>
            <tbody>
                {r.analyst_ratings.map((ar, i) => (
                    <tr key={i} className="leading-[16px]">
                        <td className="truncate pr-2 max-w-[100px]">{ar.firm}</td>
                        <td className={`pr-2 ${ratingColor(ar.rating)}`}>{ar.rating}</td>
                        <td className="text-right tabular-nums">{ar.price_target ? money(ar.price_target) : '—'}</td>
                        <td className="text-right text-muted-fg text-[9px]">{ar.date || ''}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

// ============================================================================
// NEWS FEED
// ============================================================================
export function NewsWidget(_: WidgetContext) {
    const { report: r, loadingGemini, isSpanish } = useFanData();
    if (!r) return null;
    const ns = r.news_sentiment;
    const isInstant = r._instant;

    if (isInstant && loadingGemini) {
        return <GeminiLoading text={isSpanish ? 'Buscando noticias...' : 'Loading news...'} />;
    }

    if (!ns) {
        return <div className="text-[10px] text-muted-fg">{isSpanish ? 'Sin noticias' : 'No recent news'}</div>;
    }

    return (
        <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-1.5 mb-1">
                {(ns.overall === 'Bullish' || ns.overall === 'Positive') && <TrendingUp size={10} className="text-green-500" />}
                {(ns.overall === 'Bearish' || ns.overall === 'Negative') && <TrendingDown size={10} className="text-red-500" />}
                <span className={`font-semibold ${ratingColor(ns.overall)}`}>{ns.overall}</span>
                {ns.score != null && (
                    <span className={`text-[9px] ${ns.score > 0 ? 'text-green-500' : 'text-red-500'}`}>
                        ({ns.score > 0 ? '+' : ''}{ns.score})
                    </span>
                )}
            </div>
            {ns.recent_headlines && ns.recent_headlines.length > 0 && (
                <div className="space-y-0.5">
                    {ns.recent_headlines.map((h, i) => (
                        <div key={i} className="text-[9px] text-foreground/80 leading-[13px]">• {h}</div>
                    ))}
                </div>
            )}
        </div>
    );
}

// ============================================================================
// INSIDER ACTIVITY
// ============================================================================
export function InsiderWidget(_: WidgetContext) {
    const { report: r, isSpanish } = useFanData();
    if (!r) return null;

    return (
        <div className="flex flex-col gap-0.5">
            <Row label="Sentiment" value={r.insider_sentiment || '—'} valueClass={ratingColor(r.insider_sentiment)} />
            {r.insider_activity && r.insider_activity.length > 0 ? (
                r.insider_activity.slice(0, 5).map((ins, i) => (
                    <div key={i} className="flex gap-1 items-baseline text-[10px] leading-[16px]">
                        <span className={`font-semibold w-7 shrink-0 ${ins.type === 'Buy' ? 'text-green-500' : 'text-red-500'}`}>
                            {ins.type.toUpperCase()}
                        </span>
                        <span className="text-muted-fg flex-1 truncate text-[9px]">{ins.title || ins.insider_name}</span>
                        <span className="tabular-nums">{ins.value || '—'}</span>
                        {ins.date && <span className="text-muted-fg text-[9px]">{ins.date}</span>}
                    </div>
                ))
            ) : (
                <div className="text-[10px] text-muted-fg">{isSpanish ? 'Sin actividad' : 'No recent activity'}</div>
            )}
        </div>
    );
}

// ============================================================================
// UPCOMING CATALYSTS
// ============================================================================
export function CatalystsWidget(_: WidgetContext) {
    const { report: r, loadingGemini, isSpanish } = useFanData();
    if (!r) return null;
    const isInstant = r._instant;

    if (isInstant && loadingGemini) {
        return <GeminiLoading text={isSpanish ? 'Buscando eventos...' : 'Loading catalysts...'} />;
    }

    const hasEarnings = !!r.earnings_date;
    const hasCatalysts = r.upcoming_catalysts && r.upcoming_catalysts.length > 0;

    if (!hasEarnings && !hasCatalysts) {
        return <div className="text-[10px] text-muted-fg">{isSpanish ? 'Sin eventos' : 'None scheduled'}</div>;
    }

    return (
        <div className="flex flex-col gap-0.5">
            {hasEarnings && (
                <div className="text-[10px] text-primary leading-[16px] flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0" />
                    Earnings: {r.earnings_date}
                </div>
            )}
            {r.upcoming_catalysts?.map((cat, i) => (
                <div key={i} className="text-[10px] text-foreground leading-[16px] flex items-center gap-1">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${cat.importance === 'High' ? 'bg-red-400' : cat.importance === 'Medium' ? 'bg-amber-400' : 'bg-muted-fg'}`} />
                    <span className="truncate">{cat.event}</span>
                    {cat.date && <span className="text-muted-fg text-[9px] shrink-0">{cat.date}</span>}
                </div>
            ))}
        </div>
    );
}

// ============================================================================
// RISK FACTORS
// ============================================================================
export function RiskWidget(_: WidgetContext) {
    const { report: r, loadingGemini, isSpanish } = useFanData();
    if (!r) return null;
    const isInstant = r._instant;

    if (isInstant && loadingGemini) {
        return <GeminiLoading text={isSpanish ? 'Analizando riesgos...' : 'Analyzing risks...'} />;
    }

    return (
        <div className="flex flex-col gap-0.5">
            {r.risk_score != null && (
                <Row label="Risk Score" value={`${r.risk_score}/10`}
                    valueClass={r.risk_score <= 3 ? 'text-green-500' : r.risk_score <= 6 ? 'text-amber-500' : 'text-red-500'} />
            )}
            {r.risk_sentiment && (
                <Row label="Sentiment" value={r.risk_sentiment} valueClass={ratingColor(r.risk_sentiment)} />
            )}
            {r.risk_factors && r.risk_factors.length > 0 ? (
                <div className="mt-1 space-y-0.5">
                    {r.risk_factors.slice(0, 5).map((rf, i) => (
                        <div key={i} className="text-[10px] text-foreground leading-[14px] flex">
                            <span className="text-muted-fg mr-1.5 shrink-0">•</span>
                            <span>{typeof rf === 'string' ? rf : rf.description}</span>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="text-[10px] text-muted-fg">{isSpanish ? 'Sin riesgos mayores' : 'No major risks'}</div>
            )}
        </div>
    );
}

// ============================================================================
// ABOUT (expandable business summary)
// ============================================================================
export function AboutWidget(_: WidgetContext) {
    const { report: r, isSpanish } = useFanData();
    const [expanded, setExpanded] = useState(false);
    if (!r || !r.business_summary) return null;

    const needsExpand = r.business_summary.length > 200;

    return (
        <div>
            <p className={`text-[10px] text-foreground leading-[14px] ${expanded ? '' : 'line-clamp-4'}`}>
                {r.business_summary}
            </p>
            {needsExpand && (
                <button
                    onClick={() => setExpanded(!expanded)}
                    className="text-primary hover:text-primary-hover text-[9px] font-medium mt-0.5 cursor-pointer"
                >
                    {expanded
                        ? (isSpanish ? '▲ Menos' : '▲ Less')
                        : (isSpanish ? '▼ Más' : '▼ More')}
                </button>
            )}
        </div>
    );
}

// ============================================================================
// QUOTE STRIP (shown via TickerStrip, wrapped here)
// ============================================================================
export function QuoteStripWidget(_: WidgetContext) {
    const { report: r, company } = useFanData();
    if (!r) return null;

    return (
        <div className="flex items-center gap-3 h-full">
            <div className="flex items-center gap-2">
                {company?.logoUrl && (
                    <img src={company.logoUrl} alt="" className="w-6 h-6 rounded border border-border bg-surface p-0.5 object-contain"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
                )}
                <div>
                    <div className="flex items-center gap-1">
                        <span className="font-semibold text-[11px]">{r.ticker}</span>
                        <span className="text-muted-fg text-[9px] truncate max-w-[120px]">{r.company_name}</span>
                    </div>
                    <div className="flex items-center gap-1 text-[9px] text-muted-fg">
                        <span>{company?.exchange || r.exchange}</span>
                        {r.sector && <><span>·</span><span className="truncate">{r.sector}</span></>}
                    </div>
                </div>
            </div>
            {r.special_status && (
                <span className="text-[8px] font-medium text-amber-600 bg-amber-500/10 px-1 py-0.5 rounded shrink-0">
                    {r.special_status}
                </span>
            )}
        </div>
    );
}

// ============================================================================
// CHART (wraps TradingChart)
// ============================================================================
import dynamic from 'next/dynamic';

const TradingChart = dynamic(
    () => import('@/components/chart/TradingChart').then(m => m.TradingChart),
    { ssr: false, loading: () => <div className="h-full w-full flex items-center justify-center"><Loader2 className="w-4 h-4 animate-spin text-primary" /></div> },
);

export function ChartWidget(_: WidgetContext) {
    const { ticker } = useFanData();
    if (!ticker) return null;

    return (
        <div className="h-full w-full">
            <TradingChart ticker={ticker} minimal={true} />
        </div>
    );
}

// ============================================================================
// DILUTION RISK (calls getRiskRatings API)
// ============================================================================
import { getRiskRatings, type DilutionRiskRatings } from '@/lib/dilution-api';

function dilutionColor(level?: string) {
    if (level === 'High') return 'text-red-500';
    if (level === 'Medium') return 'text-amber-500';
    if (level === 'Low') return 'text-green-500';
    return 'text-muted-fg';
}

function dilutionBg(level?: string) {
    if (level === 'High') return 'bg-red-500/10';
    if (level === 'Medium') return 'bg-amber-500/10';
    if (level === 'Low') return 'bg-green-500/10';
    return 'bg-muted/20';
}

export function DilutionRiskWidget(_: WidgetContext) {
    const { ticker } = useFanData();
    const [data, setData] = useState<DilutionRiskRatings | null>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!ticker) return;
        let cancelled = false;
        setLoading(true);
        setData(null);
        getRiskRatings(ticker).then(d => {
            if (!cancelled) {
                setData(d);
                setLoading(false);
            }
        }).catch(() => {
            if (!cancelled) setLoading(false);
        });
        return () => { cancelled = true; };
    }, [ticker]);

    if (loading) {
        return (
            <div className="flex items-center gap-1.5 text-[10px] text-muted-fg">
                <Loader2 className="w-3 h-3 animate-spin text-primary" />
                <span>Loading dilution data...</span>
            </div>
        );
    }

    if (!data || !data.data_available) {
        return <div className="text-[10px] text-muted-fg">No dilution data available</div>;
    }

    const categories: { label: string; level: string; score: number }[] = [
        { label: 'Overall Risk', level: data.overall_risk, score: data.scores.overall },
        { label: 'Offering', level: data.offering_ability, score: data.scores.offering_ability },
        { label: 'Overhead', level: data.overhead_supply, score: data.scores.overhead_supply },
        { label: 'Historical', level: data.historical, score: data.scores.historical },
        { label: 'Cash Need', level: data.cash_need, score: data.scores.cash_need },
    ];

    return (
        <div className="flex flex-col gap-1">
            {categories.map(({ label, level, score }) => (
                <div key={label} className="flex items-center justify-between leading-[18px]">
                    <span className="text-[10px] text-foreground/80">{label}</span>
                    <div className="flex items-center gap-1.5">
                        <div className="w-12 h-1 rounded-full bg-muted/30 overflow-hidden">
                            <div
                                className={`h-full rounded-full ${level === 'High' ? 'bg-red-500' : level === 'Medium' ? 'bg-amber-500' : 'bg-green-500'}`}
                                style={{ width: `${Math.min(100, score * 10)}%` }}
                            />
                        </div>
                        <span className={`text-[10px] font-medium tabular-nums w-[46px] text-right px-1 py-0.5 rounded-sm ${dilutionColor(level)} ${dilutionBg(level)}`}>
                            {level}
                        </span>
                    </div>
                </div>
            ))}
            {data.details && (
                <div className="mt-1 pt-1 border-t border-border space-y-0.5">
                    {data.details.overhead_supply?.dilution_pct > 0 && (
                        <Row label="Potential Dilution" value={`${data.details.overhead_supply.dilution_pct.toFixed(1)}%`}
                            valueClass={data.details.overhead_supply.dilution_pct > 30 ? 'text-red-500' : 'text-amber-500'} />
                    )}
                    {data.details.cash_need?.runway_months != null && (
                        <Row label="Cash Runway" value={`${data.details.cash_need.runway_months.toFixed(0)} mo`}
                            valueClass={data.details.cash_need.runway_months < 6 ? 'text-red-500' : data.details.cash_need.runway_months < 12 ? 'text-amber-500' : 'text-green-500'} />
                    )}
                    {data.details.historical?.increase_pct > 0 && (
                        <Row label="3Y Share Increase" value={`+${data.details.historical.increase_pct.toFixed(1)}%`}
                            valueClass={data.details.historical.increase_pct > 50 ? 'text-red-500' : 'text-amber-500'} />
                    )}
                    {data.details.offering_ability?.has_active_shelf && (
                        <Row label="Active Shelf" value="Yes" valueClass="text-amber-500" />
                    )}
                </div>
            )}
        </div>
    );
}

// ============================================================================
// KEY METRICS (TIKR-style, 100% deterministic — Perplexity v3 + internal data)
// ============================================================================
const KM_API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.tradeul.com';

interface KeyMetricRow { label: string; value: number | null; format: string; }
interface KeyMetricGroup { title: string; rows: KeyMetricRow[]; }
interface KeyMetricsResponse { symbol: string; currency: string; source: string; groups: KeyMetricGroup[]; }

function formatKeyMetric(value: number | null | undefined, format: string, currency: string): { text: string; negative: boolean } {
    if (value == null || Number.isNaN(value)) return { text: '—', negative: false };
    const negative = value < 0;
    const cur = currency === 'USD' ? 'US$' : currency;
    const n2 = (x: number) => x.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    switch (format) {
        case 'money_mm':
            return { text: `${n2(value / 1e6)} ${cur}`, negative };
        case 'shares_mm':
            return { text: `${n2(value / 1e6)} MM`, negative };
        case 'multiple':
            return { text: `${n2(value)}x`, negative };
        case 'percent':
            return { text: `${n2(value)} %`, negative };
        case 'price':
            return { text: `${n2(value)} ${cur}`, negative };
        case 'int':
            return { text: value.toLocaleString('en-US', { maximumFractionDigits: 0 }), negative };
        default:
            return { text: n2(value), negative };
    }
}

export function KeyMetricsWidget(_: WidgetContext) {
    const { ticker, isSpanish } = useFanData();
    const [data, setData] = useState<KeyMetricsResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(false);
    const containerRef = useRef<HTMLDivElement>(null);
    const [cols, setCols] = useState(2);

    useEffect(() => {
        if (!ticker) return;
        let cancelled = false;
        setLoading(true);
        setError(false);
        setData(null);
        fetch(`${KM_API_URL}/api/report/${ticker}/key-metrics`)
            .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); })
            .then((d: KeyMetricsResponse) => { if (!cancelled) { setData(d); setLoading(false); } })
            .catch(() => { if (!cancelled) { setError(true); setLoading(false); } });
        return () => { cancelled = true; };
    }, [ticker]);

    // Columnas adaptativas según el ancho real del widget: cuantas más columnas,
    // menos alto ocupa el panel (clave para que no sea "extenso").
    useEffect(() => {
        const el = containerRef.current;
        if (!el) return;
        const measure = () => {
            const w = el.clientWidth;
            setCols(w >= 600 ? 3 : w >= 340 ? 2 : 1);
        };
        measure();
        const ro = new ResizeObserver(measure);
        ro.observe(el);
        return () => ro.disconnect();
    }, []);

    const currency = data?.currency || 'USD';

    return (
        <div ref={containerRef} className="h-full">
            {loading ? (
                <div className="flex items-center gap-1.5 text-[10px] text-muted-fg">
                    <Loader2 className="w-3 h-3 animate-spin text-primary" />
                    <span>{isSpanish ? 'Cargando métricas...' : 'Loading metrics...'}</span>
                </div>
            ) : error || !data || !data.groups?.length ? (
                <div className="text-[10px] text-muted-fg">{isSpanish ? 'Sin métricas' : 'No metrics available'}</div>
            ) : (
                <div
                    className="grid gap-x-6 gap-y-3"
                    style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
                >
                    {data.groups.map(group => (
                        <div key={group.title} className="min-w-0">
                            <div className="text-[10px] font-semibold text-primary uppercase tracking-wide border-b border-border pb-0.5 mb-1">
                                {group.title}
                            </div>
                            <div className="flex flex-col">
                                {group.rows.map(row => {
                                    const { text, negative } = formatKeyMetric(row.value, row.format, currency);
                                    const isEmpty = text === '—';
                                    return (
                                        <div key={row.label} className="flex items-center justify-between leading-[18px] gap-2">
                                            <span className="text-[10px] text-foreground/70 truncate">{row.label}</span>
                                            <span className={`text-[10px] font-semibold tabular-nums shrink-0 ${isEmpty ? 'text-muted-fg' : negative ? 'text-red-500' : 'text-foreground'}`}>
                                                {negative && !isEmpty ? `(${text.replace('-', '')})` : text}
                                            </span>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
