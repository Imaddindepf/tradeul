import { Droplets, Pickaxe, Zap, Leaf, Building2 } from 'lucide-react';
import type { IndustryProfile, FinancialData } from '../../types';

// ============================================================================
// ENERGY, UTILITIES, AND MATERIALS PROFILES
// ============================================================================

export const oilGasProfile: IndustryProfile = {
    category: 'oil_gas',
    label: 'Oil & Gas',
    icon: Droplets,
    color: 'text-amber-800',
    description: 'Oil & gas exploration, production, refining',
    kpis: [
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 20, bad: 10 }, tooltip: 'E&P: 30-50%, Refining: 3-8%' },
        { name: 'EBITDA Margin', formula: 'EBITDA / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.ebitda && i?.revenue ? (i.ebitda / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 40, bad: 25 }, tooltip: 'EBITDA margin (key for E&P)' },
        { name: 'CapEx/Revenue', formula: 'CapEx / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.revenue && c?.capex ? Math.abs(c.capex) / i.revenue * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 30 }, tooltip: 'Capital intensity' },
        { name: 'FCF Yield', formula: 'FCF / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.revenue && c?.free_cash_flow ? (c.free_cash_flow / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 5 }, tooltip: 'FCF generation' },
        { name: 'Debt/EBITDA', formula: 'Net Debt / EBITDA', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return b?.net_debt && i?.ebitda && i.ebitda > 0 ? b.net_debt / i.ebitda : undefined; }, format: 'ratio', benchmark: { good: 1.5, bad: 3 }, tooltip: 'Leverage ratio' },
    ],
};

export const miningProfile: IndustryProfile = {
    category: 'mining',
    label: 'Mining & Metals',
    icon: Pickaxe,
    color: 'text-stone-600',
    description: 'Gold, silver, copper, steel, aluminum',
    kpis: [
        { name: 'EBITDA Margin', formula: 'EBITDA / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.ebitda && i?.revenue ? (i.ebitda / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 35, bad: 20 }, tooltip: 'Varies with commodity prices' },
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 20, bad: 10 }, tooltip: 'Operating profitability' },
        { name: 'CapEx/Revenue', formula: 'CapEx / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.revenue && c?.capex ? Math.abs(c.capex) / i.revenue * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 30 }, tooltip: 'Mining requires heavy CapEx' },
        { name: 'FCF Margin', formula: 'FCF / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.revenue && c?.free_cash_flow ? (c.free_cash_flow / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 5 }, tooltip: 'FCF generation' },
        { name: 'Debt/Equity', formula: 'Total Debt / Equity', calculate: (d: FinancialData) => { const b = d.balance_sheets[0]; return b?.total_debt && b?.total_equity ? b.total_debt / b.total_equity : undefined; }, format: 'ratio', benchmark: { good: 0.4, bad: 0.8 }, tooltip: 'Financial leverage' },
    ],
};

export const utilitiesProfile: IndustryProfile = {
    category: 'utilities',
    label: 'Utilities',
    icon: Zap,
    color: 'text-yellow-600',
    description: 'Electric, gas, water, renewable utilities',
    kpis: [
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 20, bad: 12 }, tooltip: 'Regulated utilities: 15-25%' },
        { name: 'Net Margin', formula: 'Net Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.net_income && i?.revenue ? (i.net_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 12, bad: 6 }, tooltip: 'Net profitability' },
        { name: 'Debt/Equity', formula: 'Total Debt / Equity', calculate: (d: FinancialData) => { const b = d.balance_sheets[0]; return b?.total_debt && b?.total_equity ? b.total_debt / b.total_equity : undefined; }, format: 'ratio', benchmark: { good: 1.2, bad: 1.8 }, tooltip: 'Utilities carry high debt (regulated)' },
        { name: 'Dividend Payout', formula: 'Dividends / Net Income', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.net_income && c?.dividends_paid && i.net_income > 0 ? Math.abs(c.dividends_paid) / i.net_income * 100 : undefined; }, format: 'percent', benchmark: { good: 60, bad: 80 }, tooltip: 'Utilities are dividend payers' },
        { name: 'ROE', formula: 'Net Income / Equity', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.net_income && b?.total_equity ? (i.net_income / b.total_equity) * 100 : undefined; }, format: 'percent', benchmark: { good: 10, bad: 7 }, tooltip: 'ROE (regulated, stable)' },
    ],
};

export const chemicalsProfile: IndustryProfile = {
    category: 'chemicals',
    label: 'Chemicals',
    icon: Leaf,
    color: 'text-green-700',
    description: 'Specialty and agricultural chemicals',
    kpis: [
        { name: 'Gross Margin', formula: 'Gross Profit / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 35, bad: 25 }, tooltip: 'Specialty: 35-50%, Commodity: 15-25%' },
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 8 }, tooltip: 'Operating profitability' },
        { name: 'ROIC', formula: 'NOPAT / Invested Capital', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; if (!i?.operating_income || !b?.total_equity || !b?.total_debt) return undefined; const nopat = i.operating_income * 0.75; const ic = b.total_equity + b.total_debt - (b.cash_and_equivalents || 0); return ic > 0 ? (nopat / ic) * 100 : undefined; }, format: 'percent', benchmark: { good: 12, bad: 6 }, tooltip: 'Return on Invested Capital' },
        { name: 'R&D Intensity', formula: 'R&D / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.research_development && i?.revenue ? (i.research_development / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 3, bad: 6 }, tooltip: 'R&D investment' },
        { name: 'CapEx/Revenue', formula: 'CapEx / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.revenue && c?.capex ? Math.abs(c.capex) / i.revenue * 100 : undefined; }, format: 'percent', benchmark: { good: 5, bad: 12 }, tooltip: 'Capital intensity' },
    ],
};

export const generalProfile: IndustryProfile = {
    category: 'general',
    label: 'General',
    icon: Building2,
    color: 'text-gray-600',
    description: 'General company analysis',
    kpis: [
        { name: 'Gross Margin', formula: 'Gross Profit / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 40, bad: 25 }, tooltip: 'Gross profitability' },
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 5 }, tooltip: 'Operating profitability' },
        { name: 'Net Margin', formula: 'Net Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.net_income && i?.revenue ? (i.net_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 10, bad: 3 }, tooltip: 'Net profitability' },
        { name: 'ROE', formula: 'Net Income / Equity', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.net_income && b?.total_equity ? (i.net_income / b.total_equity) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 8 }, tooltip: 'Return on Equity' },
        { name: 'Debt/Equity', formula: 'Total Debt / Equity', calculate: (d: FinancialData) => { const b = d.balance_sheets[0]; return b?.total_debt && b?.total_equity ? b.total_debt / b.total_equity : undefined; }, format: 'ratio', benchmark: { good: 0.5, bad: 1.5 }, tooltip: 'Financial leverage' },
    ],
};

