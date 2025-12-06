import { HeartPulse } from 'lucide-react';
import type { IndustryProfile, FinancialData } from '../../types';

// ============================================================================
// HEALTHCARE INDUSTRY PROFILES
// ============================================================================

export const biotechProfile: IndustryProfile = {
    category: 'biotech',
    label: 'Biotechnology',
    icon: HeartPulse,
    color: 'text-rose-600',
    description: 'Biotechnology and drug development',
    kpis: [
        {
            name: 'Cash Runway',
            formula: 'Cash / Quarterly Burn',
            calculate: (d: FinancialData) => {
                const b = d.balance_sheets[0];
                const c = d.cash_flows[0];
                const cash = (b?.cash_and_equivalents || 0) + (b?.short_term_investments || 0);
                if (cash && c?.operating_cash_flow && c.operating_cash_flow < 0) {
                    return cash / Math.abs(c.operating_cash_flow);
                }
                return undefined;
            },
            format: 'ratio',
            benchmark: { good: 3, bad: 1.5 },
            tooltip: 'Years of cash at current burn rate'
        },
        {
            name: 'Cash Position',
            formula: 'Cash + Short-term Investments',
            calculate: (d: FinancialData) => {
                const b = d.balance_sheets[0];
                return (b?.cash_and_equivalents || 0) + (b?.short_term_investments || 0);
            },
            format: 'currency',
            benchmark: { good: 500000000, bad: 100000000 },
            tooltip: 'Total liquid assets'
        },
        {
            name: 'Quarterly Burn',
            formula: 'Operating Cash Flow (if negative)',
            calculate: (d: FinancialData) => {
                const c = d.cash_flows[0];
                return c?.operating_cash_flow && c.operating_cash_flow < 0
                    ? Math.abs(c.operating_cash_flow) : undefined;
            },
            format: 'currency',
            benchmark: { good: 30000000, bad: 100000000 },
            tooltip: 'Cash burn per quarter'
        },
        {
            name: 'R&D Spend',
            formula: 'R&D Expenses',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.research_development;
            },
            format: 'currency',
            benchmark: { good: 50000000, bad: 10000000 },
            tooltip: 'Investment in research and development'
        },
        {
            name: 'Cash/Market Cap Est',
            formula: 'Cash / Equity',
            calculate: (d: FinancialData) => {
                const b = d.balance_sheets[0];
                const cash = (b?.cash_and_equivalents || 0) + (b?.short_term_investments || 0);
                return b?.total_equity ? (cash / Math.abs(b.total_equity)) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 50, bad: 20 },
            tooltip: 'Cash as % of book value'
        },
    ],
};

export const pharmaProfile: IndustryProfile = {
    category: 'pharma',
    label: 'Pharmaceuticals',
    icon: HeartPulse,
    color: 'text-pink-600',
    description: 'Drug manufacturers (specialty and general)',
    kpis: [
        {
            name: 'Gross Margin',
            formula: 'Gross Profit / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 70, bad: 55 },
            tooltip: 'Pharma typically has 65-80% gross margins'
        },
        {
            name: 'R&D Intensity',
            formula: 'R&D / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.research_development && i?.revenue ? (i.research_development / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 15, bad: 25 },
            tooltip: 'R&D investment typically 15-20% of revenue'
        },
        {
            name: 'Operating Margin',
            formula: 'Operating Income / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 25, bad: 15 },
            tooltip: 'Operating profitability'
        },
        {
            name: 'ROE',
            formula: 'Net Income / Equity',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const b = d.balance_sheets[0];
                return i?.net_income && b?.total_equity ? (i.net_income / b.total_equity) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 20, bad: 10 },
            tooltip: 'Return on Equity'
        },
        {
            name: 'Dividend Payout',
            formula: 'Dividends / Net Income',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const c = d.cash_flows[0];
                return i?.net_income && c?.dividends_paid && i.net_income > 0
                    ? Math.abs(c.dividends_paid) / i.net_income * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 40, bad: 70 },
            tooltip: 'Mature pharma pays significant dividends'
        },
    ],
};

export const medicalDevicesProfile: IndustryProfile = {
    category: 'medical_devices',
    label: 'Medical Devices',
    icon: HeartPulse,
    color: 'text-red-600',
    description: 'Medical devices, instruments, and diagnostics',
    kpis: [
        {
            name: 'Gross Margin',
            formula: 'Gross Profit / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 60, bad: 45 },
            tooltip: 'Med devices typically have 55-70% gross margins'
        },
        {
            name: 'R&D Intensity',
            formula: 'R&D / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.research_development && i?.revenue ? (i.research_development / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 8, bad: 15 },
            tooltip: 'R&D investment (typically 7-12%)'
        },
        {
            name: 'Operating Margin',
            formula: 'Operating Income / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 25, bad: 15 },
            tooltip: 'Operating profitability'
        },
        {
            name: 'FCF Margin',
            formula: 'FCF / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const c = d.cash_flows[0];
                return i?.revenue && c?.free_cash_flow ? (c.free_cash_flow / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 20, bad: 10 },
            tooltip: 'Free cash flow generation'
        },
        {
            name: 'ROIC',
            formula: 'NOPAT / Invested Capital',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const b = d.balance_sheets[0];
                if (!i?.operating_income || !b?.total_equity || !b?.total_debt) return undefined;
                const nopat = i.operating_income * 0.75;
                const ic = b.total_equity + b.total_debt - (b.cash_and_equivalents || 0);
                return ic > 0 ? (nopat / ic) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 15, bad: 8 },
            tooltip: 'Return on Invested Capital'
        },
    ],
};

export const healthcareServicesProfile: IndustryProfile = {
    category: 'healthcare_services',
    label: 'Healthcare Services',
    icon: HeartPulse,
    color: 'text-emerald-600',
    description: 'Healthcare plans, facilities, and services',
    kpis: [
        {
            name: 'Operating Margin',
            formula: 'Operating Income / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 8, bad: 4 },
            tooltip: 'Healthcare services have lower margins (5-10%)'
        },
        {
            name: 'Net Margin',
            formula: 'Net Income / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.net_income && i?.revenue ? (i.net_income / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 5, bad: 2 },
            tooltip: 'Net profitability'
        },
        {
            name: 'Days Sales Outstanding',
            formula: '(Receivables / Revenue) × 365',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const b = d.balance_sheets[0];
                return i?.revenue && b?.receivables ? (b.receivables / i.revenue) * 365 : undefined;
            },
            format: 'days',
            benchmark: { good: 40, bad: 60 },
            tooltip: 'Collection period for insurance payments'
        },
        {
            name: 'ROE',
            formula: 'Net Income / Equity',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const b = d.balance_sheets[0];
                return i?.net_income && b?.total_equity ? (i.net_income / b.total_equity) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 15, bad: 8 },
            tooltip: 'Return on Equity'
        },
        {
            name: 'Debt/Equity',
            formula: 'Total Debt / Equity',
            calculate: (d: FinancialData) => {
                const b = d.balance_sheets[0];
                return b?.total_debt && b?.total_equity ? b.total_debt / b.total_equity : undefined;
            },
            format: 'ratio',
            benchmark: { good: 0.5, bad: 1.5 },
            tooltip: 'Financial leverage'
        },
    ],
};

