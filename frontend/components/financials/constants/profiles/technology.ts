import { Cpu, Wifi } from 'lucide-react';
import type { IndustryProfile, FinancialData } from '../../types';

// ============================================================================
// TECHNOLOGY INDUSTRY PROFILES
// ============================================================================

export const softwareProfile: IndustryProfile = {
    category: 'software',
    label: 'Software',
    icon: Cpu,
    color: 'text-blue-600',
    description: 'Software companies (SaaS, Enterprise, Consumer)',
    kpis: [
        {
            name: 'Gross Margin',
            formula: 'Gross Profit / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 70, bad: 50 },
            tooltip: 'Software companies typically have 70-85% gross margins'
        },
        {
            name: 'R&D Intensity',
            formula: 'R&D / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.research_development && i?.revenue ? (i.research_development / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 15, bad: 30 },
            tooltip: 'R&D investment as % of revenue. 15-25% is typical for growth software'
        },
        {
            name: 'Rule of 40',
            formula: 'Revenue Growth + FCF Margin',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const c = d.cash_flows[0];
                if (!i?.revenue || !c?.free_cash_flow) return undefined;
                const fcfMargin = (c.free_cash_flow / i.revenue) * 100;
                return fcfMargin + 20;
            },
            format: 'ratio',
            benchmark: { good: 40, bad: 20 },
            tooltip: 'Growth + Profitability should exceed 40% for healthy SaaS'
        },
        {
            name: 'Operating Margin',
            formula: 'Operating Income / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 20, bad: 0 },
            tooltip: 'Mature software companies target 20-30% operating margins'
        },
        {
            name: 'FCF Margin',
            formula: 'Free Cash Flow / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const c = d.cash_flows[0];
                return i?.revenue && c?.free_cash_flow ? (c.free_cash_flow / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 25, bad: 5 },
            tooltip: 'Software often has FCF > Net Income due to SBC and deferred revenue'
        },
    ],
};

export const semiconductorProfile: IndustryProfile = {
    category: 'semiconductor',
    label: 'Semiconductor',
    icon: Cpu,
    color: 'text-violet-600',
    description: 'Chip designers and manufacturers',
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
            tooltip: 'Fabless: 60-70%, Integrated: 40-55%'
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
            tooltip: 'Semis invest heavily in R&D (15-25% of revenue)'
        },
        {
            name: 'CapEx Intensity',
            formula: 'CapEx / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const c = d.cash_flows[0];
                return i?.revenue && c?.capex ? Math.abs(c.capex) / i.revenue * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 10, bad: 30 },
            tooltip: 'Fabs require massive CapEx; fabless companies have lower CapEx'
        },
        {
            name: 'Inventory Turns',
            formula: 'COGS / Inventory',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const b = d.balance_sheets[0];
                return i?.cost_of_revenue && b?.inventory ? i.cost_of_revenue / b.inventory : undefined;
            },
            format: 'turns',
            benchmark: { good: 4, bad: 2 },
            tooltip: 'Higher turns indicate better inventory management'
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

export const hardwareProfile: IndustryProfile = {
    category: 'hardware',
    label: 'Consumer Electronics',
    icon: Cpu,
    color: 'text-slate-700',
    description: 'Consumer electronics and computer hardware',
    kpis: [
        {
            name: 'Gross Margin',
            formula: 'Gross Profit / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 35, bad: 20 },
            tooltip: 'Hardware margins are lower than software (30-45% typical)'
        },
        {
            name: 'Operating Margin',
            formula: 'Operating Income / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 20, bad: 8 },
            tooltip: 'Premium brands like Apple achieve 25-30% operating margins'
        },
        {
            name: 'Inventory Days',
            formula: '(Inventory / COGS) × 365',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const b = d.balance_sheets[0];
                return i?.cost_of_revenue && b?.inventory ? (b.inventory / i.cost_of_revenue) * 365 : undefined;
            },
            format: 'days',
            benchmark: { good: 30, bad: 60 },
            tooltip: 'Days of inventory on hand. Lower is better for hardware'
        },
        {
            name: 'FCF Conversion',
            formula: 'FCF / Net Income',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const c = d.cash_flows[0];
                return i?.net_income && c?.free_cash_flow && i.net_income > 0 ? (c.free_cash_flow / i.net_income) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 100, bad: 60 },
            tooltip: 'How efficiently earnings convert to cash'
        },
        {
            name: 'R&D Intensity',
            formula: 'R&D / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.research_development && i?.revenue ? (i.research_development / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 5, bad: 15 },
            tooltip: 'Hardware R&D typically 5-10% of revenue'
        },
    ],
};

export const internetProfile: IndustryProfile = {
    category: 'internet',
    label: 'Internet',
    icon: Wifi,
    color: 'text-cyan-600',
    description: 'Internet content, information, and platforms',
    kpis: [
        {
            name: 'Gross Margin',
            formula: 'Gross Profit / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 55, bad: 40 },
            tooltip: 'Internet platforms typically have 50-65% gross margins'
        },
        {
            name: 'EBITDA Margin',
            formula: 'EBITDA / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.ebitda && i?.revenue ? (i.ebitda / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 30, bad: 15 },
            tooltip: 'Mature internet companies target 30-40% EBITDA margins'
        },
        {
            name: 'CapEx/Revenue',
            formula: 'CapEx / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const c = d.cash_flows[0];
                return i?.revenue && c?.capex ? Math.abs(c.capex) / i.revenue * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 10, bad: 20 },
            tooltip: 'Data center and infrastructure investment'
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
            tooltip: 'Free cash flow generation'
        },
        {
            name: 'R&D/Revenue',
            formula: 'R&D / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.research_development && i?.revenue ? (i.research_development / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 12, bad: 25 },
            tooltip: 'Investment in product development'
        },
    ],
};

export const telecomProfile: IndustryProfile = {
    category: 'telecom',
    label: 'Telecom',
    icon: Wifi,
    color: 'text-blue-700',
    description: 'Telecommunications services and equipment',
    kpis: [
        {
            name: 'EBITDA Margin',
            formula: 'EBITDA / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                return i?.ebitda && i?.revenue ? (i.ebitda / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 35, bad: 25 },
            tooltip: 'Telecom EBITDA margins typically 30-40%'
        },
        {
            name: 'CapEx/Revenue',
            formula: 'CapEx / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const c = d.cash_flows[0];
                return i?.revenue && c?.capex ? Math.abs(c.capex) / i.revenue * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 15, bad: 25 },
            tooltip: 'Network infrastructure investment (typically 15-20%)'
        },
        {
            name: 'Net Debt/EBITDA',
            formula: 'Net Debt / EBITDA',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const b = d.balance_sheets[0];
                return b?.net_debt && i?.ebitda && i.ebitda > 0 ? b.net_debt / i.ebitda : undefined;
            },
            format: 'ratio',
            benchmark: { good: 2.5, bad: 4 },
            tooltip: 'Leverage ratio - telecoms typically carry high debt'
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
            benchmark: { good: 50, bad: 80 },
            tooltip: 'Telecoms are known for high dividend payouts'
        },
        {
            name: 'FCF Yield',
            formula: 'FCF / Revenue',
            calculate: (d: FinancialData) => {
                const i = d.income_statements[0];
                const c = d.cash_flows[0];
                return i?.revenue && c?.free_cash_flow ? (c.free_cash_flow / i.revenue) * 100 : undefined;
            },
            format: 'percent',
            benchmark: { good: 10, bad: 5 },
            tooltip: 'Free cash flow after heavy CapEx'
        },
    ],
};

