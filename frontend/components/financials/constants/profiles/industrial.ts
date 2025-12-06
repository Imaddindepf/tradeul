import { Factory, Plane, Building2, Film, BarChart3 } from 'lucide-react';
import type { IndustryProfile, FinancialData } from '../../types';

// ============================================================================
// INDUSTRIAL & RELATED PROFILES
// ============================================================================

export const aerospaceProfile: IndustryProfile = {
    category: 'aerospace',
    label: 'Aerospace & Defense',
    icon: Plane,
    color: 'text-blue-800',
    description: 'Aerospace and defense contractors',
    kpis: [
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 12, bad: 7 }, tooltip: 'Aerospace margins: 10-15%' },
        { name: 'Backlog Coverage', formula: 'Deferred Revenue / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.revenue && b?.deferred_revenue ? (b.deferred_revenue / i.revenue) : undefined; }, format: 'ratio', benchmark: { good: 2, bad: 0.5 }, tooltip: 'Quarters of backlog (proxy)' },
        { name: 'R&D Intensity', formula: 'R&D / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.research_development && i?.revenue ? (i.research_development / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 3, bad: 8 }, tooltip: 'R&D investment' },
        { name: 'FCF Margin', formula: 'FCF / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.revenue && c?.free_cash_flow ? (c.free_cash_flow / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 10, bad: 5 }, tooltip: 'FCF generation' },
        { name: 'ROE', formula: 'Net Income / Equity', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.net_income && b?.total_equity ? (i.net_income / b.total_equity) * 100 : undefined; }, format: 'percent', benchmark: { good: 25, bad: 12 }, tooltip: 'ROE (high due to buybacks)' },
    ],
};

export const industrialProfile: IndustryProfile = {
    category: 'industrial',
    label: 'Industrial',
    icon: Factory,
    color: 'text-gray-600',
    description: 'Industrial machinery and manufacturing',
    kpis: [
        { name: 'Gross Margin', formula: 'Gross Profit / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 35, bad: 25 }, tooltip: 'Industrial: 30-40%' },
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 8 }, tooltip: 'Operating profitability' },
        { name: 'Asset Turnover', formula: 'Revenue / Assets', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.revenue && b?.total_assets ? i.revenue / b.total_assets : undefined; }, format: 'ratio', benchmark: { good: 0.8, bad: 0.4 }, tooltip: 'Revenue per $ assets' },
        { name: 'ROIC', formula: 'NOPAT / Invested Capital', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; if (!i?.operating_income || !b?.total_equity || !b?.total_debt) return undefined; const nopat = i.operating_income * 0.75; const ic = b.total_equity + b.total_debt - (b.cash_and_equivalents || 0); return ic > 0 ? (nopat / ic) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 8 }, tooltip: 'Return on Invested Capital' },
        { name: 'FCF Conversion', formula: 'FCF / Net Income', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.net_income && c?.free_cash_flow && i.net_income > 0 ? (c.free_cash_flow / i.net_income) * 100 : undefined; }, format: 'percent', benchmark: { good: 90, bad: 60 }, tooltip: 'Cash conversion' },
    ],
};

export const constructionProfile: IndustryProfile = {
    category: 'construction',
    label: 'Construction',
    icon: Factory,
    color: 'text-yellow-700',
    description: 'Construction, engineering, and materials',
    kpis: [
        { name: 'Gross Margin', formula: 'Gross Profit / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 20, bad: 12 }, tooltip: 'Construction margins are thin' },
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 8, bad: 4 }, tooltip: 'Operating profitability' },
        { name: 'Backlog Coverage', formula: 'Deferred Revenue / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.revenue && b?.deferred_revenue ? b.deferred_revenue / i.revenue : undefined; }, format: 'ratio', benchmark: { good: 1, bad: 0.3 }, tooltip: 'Project backlog' },
        { name: 'Current Ratio', formula: 'Current Assets / Current Liabilities', calculate: (d: FinancialData) => { const b = d.balance_sheets[0]; return b?.current_assets && b?.current_liabilities ? b.current_assets / b.current_liabilities : undefined; }, format: 'ratio', benchmark: { good: 1.5, bad: 1 }, tooltip: 'Short-term liquidity' },
        { name: 'Debt/Equity', formula: 'Total Debt / Equity', calculate: (d: FinancialData) => { const b = d.balance_sheets[0]; return b?.total_debt && b?.total_equity ? b.total_debt / b.total_equity : undefined; }, format: 'ratio', benchmark: { good: 0.5, bad: 1.5 }, tooltip: 'Financial leverage' },
    ],
};

export const transportationProfile: IndustryProfile = {
    category: 'transportation',
    label: 'Transportation',
    icon: Plane,
    color: 'text-sky-700',
    description: 'Airlines, railroads, trucking, shipping',
    kpis: [
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 8 }, tooltip: 'Airlines: 5-15%, Rails: 35-45%' },
        { name: 'Asset Turnover', formula: 'Revenue / Assets', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.revenue && b?.total_assets ? i.revenue / b.total_assets : undefined; }, format: 'ratio', benchmark: { good: 0.6, bad: 0.3 }, tooltip: 'Asset utilization' },
        { name: 'CapEx/Revenue', formula: 'CapEx / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.revenue && c?.capex ? Math.abs(c.capex) / i.revenue * 100 : undefined; }, format: 'percent', benchmark: { good: 12, bad: 20 }, tooltip: 'Fleet investment' },
        { name: 'Debt/EBITDA', formula: 'Net Debt / EBITDA', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return b?.net_debt && i?.ebitda && i.ebitda > 0 ? b.net_debt / i.ebitda : undefined; }, format: 'ratio', benchmark: { good: 2.5, bad: 4 }, tooltip: 'Leverage (capital intensive)' },
        { name: 'FCF Margin', formula: 'FCF / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.revenue && c?.free_cash_flow ? (c.free_cash_flow / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 8, bad: 2 }, tooltip: 'FCF after CapEx' },
    ],
};

export const mediaProfile: IndustryProfile = {
    category: 'media',
    label: 'Media & Entertainment',
    icon: Film,
    color: 'text-pink-700',
    description: 'Entertainment, broadcasting, publishing',
    kpis: [
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 20, bad: 10 }, tooltip: 'Media operating margins' },
        { name: 'EBITDA Margin', formula: 'EBITDA / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.ebitda && i?.revenue ? (i.ebitda / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 30, bad: 18 }, tooltip: 'EBITDA margin' },
        { name: 'Content Investment', formula: 'D&A / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.revenue && c?.depreciation ? (c.depreciation / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 10, bad: 20 }, tooltip: 'Content amortization' },
        { name: 'FCF Margin', formula: 'FCF / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.revenue && c?.free_cash_flow ? (c.free_cash_flow / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 5 }, tooltip: 'FCF generation' },
        { name: 'Debt/EBITDA', formula: 'Net Debt / EBITDA', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return b?.net_debt && i?.ebitda && i.ebitda > 0 ? b.net_debt / i.ebitda : undefined; }, format: 'ratio', benchmark: { good: 2.5, bad: 4 }, tooltip: 'Leverage ratio' },
    ],
};

export const gamingProfile: IndustryProfile = {
    category: 'gaming',
    label: 'Gaming',
    icon: BarChart3,
    color: 'text-purple-700',
    description: 'Casinos, gambling, electronic gaming',
    kpis: [
        { name: 'EBITDA Margin', formula: 'EBITDA / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.ebitda && i?.revenue ? (i.ebitda / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 30, bad: 20 }, tooltip: 'Gaming EBITDA margins' },
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 8 }, tooltip: 'Operating profitability' },
        { name: 'Debt/EBITDA', formula: 'Net Debt / EBITDA', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return b?.net_debt && i?.ebitda && i.ebitda > 0 ? b.net_debt / i.ebitda : undefined; }, format: 'ratio', benchmark: { good: 3, bad: 5 }, tooltip: 'Gaming companies carry high debt' },
        { name: 'FCF Margin', formula: 'FCF / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.revenue && c?.free_cash_flow ? (c.free_cash_flow / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 12, bad: 5 }, tooltip: 'FCF generation' },
        { name: 'PPE/Assets', formula: 'PP&E / Total Assets', calculate: (d: FinancialData) => { const b = d.balance_sheets[0]; return b?.property_plant_equipment && b?.total_assets ? (b.property_plant_equipment / b.total_assets) * 100 : undefined; }, format: 'percent', benchmark: { good: 40, bad: 60 }, tooltip: 'Casinos are asset-heavy' },
    ],
};

export const travelProfile: IndustryProfile = {
    category: 'travel',
    label: 'Travel & Leisure',
    icon: Plane,
    color: 'text-teal-600',
    description: 'Travel services, lodging, leisure',
    kpis: [
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 8 }, tooltip: 'Hotels: 15-25%, OTAs: 10-20%' },
        { name: 'EBITDA Margin', formula: 'EBITDA / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.ebitda && i?.revenue ? (i.ebitda / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 25, bad: 15 }, tooltip: 'EBITDA margin' },
        { name: 'FCF Margin', formula: 'FCF / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.revenue && c?.free_cash_flow ? (c.free_cash_flow / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 5 }, tooltip: 'FCF generation' },
        { name: 'Debt/EBITDA', formula: 'Net Debt / EBITDA', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return b?.net_debt && i?.ebitda && i.ebitda > 0 ? b.net_debt / i.ebitda : undefined; }, format: 'ratio', benchmark: { good: 2.5, bad: 4 }, tooltip: 'Leverage ratio' },
        { name: 'ROE', formula: 'Net Income / Equity', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.net_income && b?.total_equity ? (i.net_income / b.total_equity) * 100 : undefined; }, format: 'percent', benchmark: { good: 20, bad: 10 }, tooltip: 'Return on Equity' },
    ],
};

export const educationProfile: IndustryProfile = {
    category: 'education',
    label: 'Education',
    icon: Building2,
    color: 'text-indigo-700',
    description: 'Education and training services',
    kpis: [
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 8 }, tooltip: 'Education operating margins' },
        { name: 'Net Margin', formula: 'Net Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.net_income && i?.revenue ? (i.net_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 10, bad: 5 }, tooltip: 'Net profitability' },
        { name: 'FCF Margin', formula: 'FCF / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.revenue && c?.free_cash_flow ? (c.free_cash_flow / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 12, bad: 5 }, tooltip: 'FCF generation' },
        { name: 'Deferred Rev/Revenue', formula: 'Deferred Revenue / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.revenue && b?.deferred_revenue ? (b.deferred_revenue / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 30, bad: 10 }, tooltip: 'Prepaid tuition' },
        { name: 'ROE', formula: 'Net Income / Equity', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.net_income && b?.total_equity ? (i.net_income / b.total_equity) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 8 }, tooltip: 'Return on Equity' },
    ],
};

export const conglomerateProfile: IndustryProfile = {
    category: 'conglomerate',
    label: 'Conglomerate',
    icon: Building2,
    color: 'text-gray-700',
    description: 'Diversified conglomerates',
    kpis: [
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 8 }, tooltip: 'Blended operating margin' },
        { name: 'ROE', formula: 'Net Income / Equity', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.net_income && b?.total_equity ? (i.net_income / b.total_equity) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 8 }, tooltip: 'Return on Equity' },
        { name: 'ROIC', formula: 'NOPAT / Invested Capital', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; if (!i?.operating_income || !b?.total_equity || !b?.total_debt) return undefined; const nopat = i.operating_income * 0.75; const ic = b.total_equity + b.total_debt - (b.cash_and_equivalents || 0); return ic > 0 ? (nopat / ic) * 100 : undefined; }, format: 'percent', benchmark: { good: 12, bad: 6 }, tooltip: 'Return on Invested Capital' },
        { name: 'FCF Conversion', formula: 'FCF / Net Income', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.net_income && c?.free_cash_flow && i.net_income > 0 ? (c.free_cash_flow / i.net_income) * 100 : undefined; }, format: 'percent', benchmark: { good: 90, bad: 60 }, tooltip: 'Cash conversion' },
        { name: 'Debt/Equity', formula: 'Total Debt / Equity', calculate: (d: FinancialData) => { const b = d.balance_sheets[0]; return b?.total_debt && b?.total_equity ? b.total_debt / b.total_equity : undefined; }, format: 'ratio', benchmark: { good: 0.5, bad: 1.5 }, tooltip: 'Financial leverage' },
    ],
};

