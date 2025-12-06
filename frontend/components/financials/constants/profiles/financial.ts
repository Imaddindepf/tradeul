import { Landmark, Building2, Home } from 'lucide-react';
import type { IndustryProfile, FinancialData } from '../../types';

// ============================================================================
// FINANCIAL SERVICES INDUSTRY PROFILES
// ============================================================================

export const bankProfile: IndustryProfile = {
    category: 'bank',
    label: 'Banking',
    icon: Landmark,
    color: 'text-emerald-700',
    description: 'Commercial and retail banks',
    kpis: [
        {
            name: 'NIM',
            formula: 'Net Interest Income / Avg Assets',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const b = d.balance_sheets[0];
                return i?.net_interest_income && b?.total_assets
                    ? (i.net_interest_income / b.total_assets) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 3, bad: 2 },
            tooltip: 'Net Interest Margin - core profitability metric for banks'
        },
        {
            name: 'Efficiency Ratio',
            formula: 'Non-Interest Expense / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                if (!i?.revenue || !i?.operating_expenses) return undefined;
                return (i.operating_expenses / i.revenue) * 100;
            },
            format: 'percent',
            benchmark: { good: 55, bad: 70 },
            tooltip: 'Lower is better. Top banks target 50-55%'
        },
        {
            name: 'ROA',
            formula: 'Net Income / Total Assets',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const b = d.balance_sheets[0];
                return i?.net_income && b?.total_assets ? (i.net_income / b.total_assets) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 1, bad: 0.5 },
            tooltip: 'Return on Assets - 1%+ is excellent for banks'
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
            benchmark: { good: 12, bad: 8 },
            tooltip: 'Return on Equity - banks target 10-15%'
        },
        {
            name: 'Tier 1 Ratio (Est)',
            formula: 'Equity / Assets',
            calculate: (d: FinancialData) => {
                const b = d.balance_sheets[0];
                return b?.total_equity && b?.total_assets ? (b.total_equity / b.total_assets) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 10, bad: 6 },
            tooltip: 'Capital adequacy estimate'
        },
    ],
};

export const insuranceProfile: IndustryProfile = {
    category: 'insurance',
    label: 'Insurance',
    icon: Building2,
    color: 'text-teal-600',
    description: 'Life, P&C, and specialty insurance',
    kpis: [
        {
            name: 'ROE',
            formula: 'Net Income / Equity',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const b = d.balance_sheets[0];
                return i?.net_income && b?.total_equity ? (i.net_income / b.total_equity) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 12, bad: 8 },
            tooltip: 'Return on Equity - key metric for insurers'
        },
        {
            name: 'Investment Ratio',
            formula: 'Investments / Assets',
            calculate: (d: FinancialData) => {
                const b = d.balance_sheets[0];
                const investments = (b?.long_term_investments || 0) + (b?.short_term_investments || 0);
                return b?.total_assets ? (investments / b.total_assets) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 60, bad: 40 },
            tooltip: 'Insurance companies invest premiums'
        },
        {
            name: 'Leverage Ratio',
            formula: 'Assets / Equity',
            calculate: (d: FinancialData) => {
                const b = d.balance_sheets[0];
                return b?.total_assets && b?.total_equity ? b.total_assets / b.total_equity : undefined;
            },
            format: 'ratio',
            benchmark: { good: 8, bad: 15 },
            tooltip: 'Total assets divided by equity'
        },
        {
            name: 'Expense Ratio',
            formula: 'OpEx / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.operating_expenses && i?.revenue ? (i.operating_expenses / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 25, bad: 35 },
            tooltip: 'Operating efficiency measure'
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
            benchmark: { good: 30, bad: 60 },
            tooltip: 'Insurers typically pay moderate dividends'
        },
    ],
};

export const assetManagementProfile: IndustryProfile = {
    category: 'asset_management',
    label: 'Asset Management',
    icon: Landmark,
    color: 'text-indigo-600',
    description: 'Asset managers and capital markets',
    kpis: [
        {
            name: 'Operating Margin',
            formula: 'Operating Income / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 35, bad: 20 },
            tooltip: 'Asset managers can achieve 30-45% operating margins'
        },
        {
            name: 'Comp/Revenue',
            formula: 'SG&A / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.selling_general_admin && i?.revenue ? (i.selling_general_admin / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 40, bad: 55 },
            tooltip: 'Compensation is the largest expense'
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
            tooltip: 'Asset-light business should have high ROE'
        },
        {
            name: 'Net Margin',
            formula: 'Net Income / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.net_income && i?.revenue ? (i.net_income / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 25, bad: 15 },
            tooltip: 'High margins due to asset-light model'
        },
        {
            name: 'Dividend Yield Est',
            formula: 'Dividends / Equity',
            calculate: (d: FinancialData) => {
                const b = d.balance_sheets[0];
                const c = d.cash_flows[0];
                return b?.total_equity && c?.dividends_paid
                    ? Math.abs(c.dividends_paid) / b.total_equity * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 3, bad: 1 },
            tooltip: 'Dividend as % of book value'
        },
    ],
};

export const fintechProfile: IndustryProfile = {
    category: 'fintech',
    label: 'Financial Services',
    icon: Landmark,
    color: 'text-purple-600',
    description: 'Credit services, payments, financial data',
    kpis: [
        {
            name: 'Gross Margin',
            formula: 'Gross Profit / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 50, bad: 35 },
            tooltip: 'Payments/data companies: 50-70%, Lenders: 30-50%'
        },
        {
            name: 'Operating Margin',
            formula: 'Operating Income / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 25, bad: 10 },
            tooltip: 'Mature fintech targets 25-40% operating margins'
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
            name: 'FCF Margin',
            formula: 'FCF / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const c = d.cash_flows[0];
                return i?.revenue && c?.free_cash_flow ? (c.free_cash_flow / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 20, bad: 5 },
            tooltip: 'Cash generation efficiency'
        },
        {
            name: 'Debt/Equity',
            formula: 'Total Debt / Equity',
            calculate: (d: FinancialData) => {
                const b = d.balance_sheets[0];
                return b?.total_debt && b?.total_equity ? b.total_debt / b.total_equity : undefined;
            },
            format: 'ratio',
            benchmark: { good: 0.5, bad: 2 },
            tooltip: 'Financial leverage'
        },
    ],
};

export const reitProfile: IndustryProfile = {
    category: 'reit',
    label: 'REIT',
    icon: Home,
    color: 'text-amber-700',
    description: 'Real Estate Investment Trusts',
    kpis: [
        {
            name: 'FFO Margin',
            formula: '(Net Income + D&A) / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const c = d.cash_flows[0];
                if (!i?.revenue || !i?.net_income) return undefined;
                const ffo = i.net_income + (c?.depreciation || 0);
                return (ffo / i.revenue) * 100;
            },
            format: 'percent',
            benchmark: { good: 40, bad: 25 },
            tooltip: 'FFO is the key profitability metric for REITs'
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
            benchmark: { good: 70, bad: 100 },
            tooltip: 'REITs must distribute 90%+ of taxable income'
        },
        {
            name: 'Debt/Assets',
            formula: 'Total Debt / Total Assets',
            calculate: (d: FinancialData) => {
                const b = d.balance_sheets[0];
                return b?.total_debt && b?.total_assets ? (b.total_debt / b.total_assets) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 35, bad: 50 },
            tooltip: 'REITs use moderate leverage (30-45% typical)'
        },
        {
            name: 'Interest Coverage',
            formula: 'EBITDA / Interest Expense',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.ebitda && i?.interest_expense ? i.ebitda / i.interest_expense : undefined;
            },
            format: 'ratio',
            benchmark: { good: 4, bad: 2 },
            tooltip: 'Ability to cover interest payments'
        },
        {
            name: 'ROA',
            formula: 'Net Income / Assets',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const b = d.balance_sheets[0];
                return i?.net_income && b?.total_assets ? (i.net_income / b.total_assets) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 4, bad: 2 },
            tooltip: 'Return on Assets'
        },
    ],
};

export const realEstateProfile: IndustryProfile = {
    category: 'real_estate',
    label: 'Real Estate',
    icon: Home,
    color: 'text-orange-700',
    description: 'Real estate services and development',
    kpis: [
        {
            name: 'Gross Margin',
            formula: 'Gross Profit / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 30, bad: 15 },
            tooltip: 'Varies widely by real estate segment'
        },
        {
            name: 'Operating Margin',
            formula: 'Operating Income / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 15, bad: 5 },
            tooltip: 'Operating efficiency'
        },
        {
            name: 'Debt/Equity',
            formula: 'Total Debt / Equity',
            calculate: (d: FinancialData) => {
                const b = d.balance_sheets[0];
                return b?.total_debt && b?.total_equity ? b.total_debt / b.total_equity : undefined;
            },
            format: 'ratio',
            benchmark: { good: 1, bad: 2 },
            tooltip: 'Real estate is typically leveraged'
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
            benchmark: { good: 12, bad: 6 },
            tooltip: 'Return on Equity'
        },
        {
            name: 'Asset Turnover',
            formula: 'Revenue / Assets',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const b = d.balance_sheets[0];
                return i?.revenue && b?.total_assets ? i.revenue / b.total_assets : undefined;
            },
            format: 'ratio',
            benchmark: { good: 0.3, bad: 0.1 },
            tooltip: 'Revenue generated per dollar of assets'
        },
    ],
};

