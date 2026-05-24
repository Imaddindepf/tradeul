'use client';

import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, ChevronUp, ChevronDown, Loader2 } from 'lucide-react';
import type { WidgetContext } from '../types';
import { useFanData } from './FanDataContext';
import { Row, GeminiLoading, fmt, pct, money, ratingColor, gradeColor } from './helpers';

// ============================================================================
// VALUATION
// ============================================================================
export function ValuationWidget(_: WidgetContext) {
    const { report: r, loadingGemini } = useFanData();
    if (!r) return null;
    const isInstant = r._instant;
    return (
        <div>
            <Row label="P/E" value={fmt(r.pe_ratio)} />
            <Row label="Fwd P/E" value={fmt(r.forward_pe)} loading={isInstant && loadingGemini} />
            <Row label="EV/EBITDA" value={fmt(r.ev_ebitda)} />
            <Row label="P/S" value={fmt(r.ps_ratio)} />
            <Row label="P/B" value={fmt(r.pb_ratio)} />
            <Row label="PEG" value={fmt(r.peg_ratio)} loading={isInstant && loadingGemini} />
            <Row label="Div Yield" value={r.dividend_yield ? `${fmt(r.dividend_yield)}%` : '—'}
                valueClass={r.dividend_yield ? 'text-green-500' : 'text-muted-fg'}
                loading={isInstant && loadingGemini} />
            {r.ex_dividend_date && (
                <Row label="Ex-Div" value={r.ex_dividend_date} valueClass="text-muted-fg" />
            )}
        </div>
    );
}

// ============================================================================
// FINANCIAL HEALTH
// ============================================================================
export function HealthWidget(_: WidgetContext) {
    const { report: r, loadingGemini } = useFanData();
    if (!r) return null;
    const fh = r.financial_health;
    const isInstant = r._instant;
    return (
        <div>
            <Row label="Grade" value={r.financial_grade || '—'} valueClass={gradeColor(r.financial_grade)} loading={isInstant && loadingGemini} />
            <Row label="Rev Growth" value={pct(fh?.revenue_growth_yoy)}
                valueClass={fh?.revenue_growth_yoy && fh.revenue_growth_yoy > 0 ? 'text-green-500' : 'text-red-500'}
                loading={isInstant && loadingGemini} />
            <Row label="EPS Growth" value={pct(fh?.earnings_growth_yoy)}
                valueClass={fh?.earnings_growth_yoy && fh.earnings_growth_yoy > 0 ? 'text-green-500' : 'text-red-500'}
                loading={isInstant && loadingGemini} />
            <Row label="Margin" value={fh?.profit_margin ? `${fmt(fh.profit_margin)}%` : '—'} />
            <Row label="D/E" value={fmt(fh?.debt_to_equity)} />
            <Row label="ROE" value={fh?.roe ? `${fmt(fh.roe)}%` : '—'} />
            <Row label="Current Ratio" value={fmt(fh?.current_ratio)} />
        </div>
    );
}

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
