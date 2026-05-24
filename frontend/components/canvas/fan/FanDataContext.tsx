'use client';

import { createContext, useContext, type ReactNode } from 'react';

// Re-export de los tipos del FAN para que los widgets no dependan directamente
// de FinancialAnalystContent
export interface AnalystRating { firm: string; rating: string; price_target: number | null; date: string | null; }
export interface RiskFactor { category: string; description: string; severity: string; }
export interface TechnicalSummary { trend: string; support_level?: number; resistance_level?: number; rsi_status?: string; ma_50_status?: string; ma_200_status?: string; pattern?: string; }
export interface ShortInterest { short_percent_of_float?: number; days_to_cover?: number; short_ratio_change?: string; squeeze_potential?: string; }
export interface UpcomingCatalyst { event: string; date?: string; importance: string; }
export interface InsiderActivity { type: string; insider_name?: string; title?: string; shares?: number; value?: string; date?: string; }
export interface FinancialHealth { revenue_growth_yoy?: number; earnings_growth_yoy?: number; debt_to_equity?: number; current_ratio?: number; cash_position?: string; profit_margin?: number; roe?: number; }
export interface NewsSentiment { overall: string; score?: number; trending_topics?: string[]; recent_headlines?: string[]; }

export interface AIReport {
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
    _instant?: boolean;
}

export interface CompanyData {
    logoUrl?: string;
    website?: string;
    ceo?: string;
    exchange?: string;
}

export interface FanData {
    report: AIReport | null;
    company: CompanyData | null;
    ticker: string;
    loadingInstant: boolean;
    loadingGemini: boolean;
    isSpanish: boolean;
}

const FanDataContext = createContext<FanData | null>(null);

export function FanDataProvider({ value, children }: { value: FanData; children: ReactNode }) {
    return <FanDataContext.Provider value={value}>{children}</FanDataContext.Provider>;
}

export function useFanData(): FanData {
    const ctx = useContext(FanDataContext);
    if (!ctx) throw new Error('useFanData must be used within FanDataProvider');
    return ctx;
}
