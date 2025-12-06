import type { FinancialPeriod } from '../types';

// ============================================================================
// FORMATTING UTILITIES
// ============================================================================

export const formatCurrency = (value: number | undefined, currency: string = 'USD'): string => {
    if (value === undefined || value === null || isNaN(value)) return '—';
    const absValue = Math.abs(value);
    const sign = value < 0 ? '-' : '';
    const symbol = currency === 'USD' ? '$' : currency;

    if (absValue >= 1e12) return `${sign}${symbol}${(absValue / 1e12).toFixed(2)}T`;
    if (absValue >= 1e9) return `${sign}${symbol}${(absValue / 1e9).toFixed(2)}B`;
    if (absValue >= 1e6) return `${sign}${symbol}${(absValue / 1e6).toFixed(2)}M`;
    if (absValue >= 1e3) return `${sign}${symbol}${(absValue / 1e3).toFixed(2)}K`;
    return `${sign}${symbol}${absValue.toFixed(2)}`;
};

export const formatPercent = (value: number | undefined): string => {
    if (value === undefined || value === null || isNaN(value)) return '—';
    return `${value.toFixed(1)}%`;
};

export const formatRatio = (value: number | undefined): string => {
    if (value === undefined || value === null || isNaN(value)) return '—';
    return value.toFixed(2);
};

export const formatDays = (value: number | undefined): string => {
    if (value === undefined || value === null || isNaN(value)) return '—';
    return `${Math.round(value)}d`;
};

export const formatTurns = (value: number | undefined): string => {
    if (value === undefined || value === null || isNaN(value)) return '—';
    return `${value.toFixed(1)}x`;
};

export const formatPeriod = (period: FinancialPeriod): string => {
    if (period.period === 'FY') {
        return `FY${period.fiscal_year}`;
    }
    return `${period.period} ${period.fiscal_year}`;
};

export const formatKPIValue = (value: number | undefined, format: string): string => {
    switch (format) {
        case 'percent': return formatPercent(value);
        case 'ratio': return formatRatio(value);
        case 'currency': return formatCurrency(value);
        case 'days': return formatDays(value);
        case 'turns': return formatTurns(value);
        default: return value?.toFixed(2) ?? '—';
    }
};

