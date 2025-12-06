import { ShoppingCart, Utensils, Droplets, Package, Car } from 'lucide-react';
import type { IndustryProfile, FinancialData } from '../../types';

// ============================================================================
// CONSUMER INDUSTRY PROFILES
// ============================================================================

export const retailProfile: IndustryProfile = {
    category: 'retail',
    label: 'Retail',
    icon: ShoppingCart,
    color: 'text-orange-600',
    description: 'Discount stores, department stores, specialty retail',
    kpis: [
        { name: 'Gross Margin', formula: 'Gross Profit / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 30, bad: 20 }, tooltip: 'Discount: 20-25%, Dept stores: 30-40%' },
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 6, bad: 3 }, tooltip: 'Retail margins are thin (3-8%)' },
        { name: 'Inventory Turns', formula: 'COGS / Inventory', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.cost_of_revenue && b?.inventory ? i.cost_of_revenue / b.inventory : undefined; }, format: 'turns', benchmark: { good: 8, bad: 4 }, tooltip: 'Higher is better' },
        { name: 'Days Inventory', formula: '(Inventory / COGS) × 365', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.cost_of_revenue && b?.inventory ? (b.inventory / i.cost_of_revenue) * 365 : undefined; }, format: 'days', benchmark: { good: 45, bad: 75 }, tooltip: 'Days of inventory on hand' },
        { name: 'ROIC', formula: 'NOPAT / Invested Capital', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; if (!i?.operating_income || !b?.total_equity || !b?.total_debt) return undefined; const nopat = i.operating_income * 0.75; const ic = b.total_equity + b.total_debt - (b.cash_and_equivalents || 0); return ic > 0 ? (nopat / ic) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 8 }, tooltip: 'Return on Invested Capital' },
    ],
};

export const ecommerceProfile: IndustryProfile = {
    category: 'ecommerce',
    label: 'E-Commerce',
    icon: ShoppingCart,
    color: 'text-cyan-600',
    description: 'Internet retail and e-commerce platforms',
    kpis: [
        { name: 'Gross Margin', formula: 'Gross Profit / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 40, bad: 25 }, tooltip: 'E-commerce margins vary (20-50%)' },
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 5, bad: 0 }, tooltip: 'E-commerce margins are thin' },
        { name: 'FCF Margin', formula: 'FCF / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.revenue && c?.free_cash_flow ? (c.free_cash_flow / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 8, bad: 2 }, tooltip: 'Free cash flow generation' },
        { name: 'CapEx/Revenue', formula: 'CapEx / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.revenue && c?.capex ? Math.abs(c.capex) / i.revenue * 100 : undefined; }, format: 'percent', benchmark: { good: 5, bad: 15 }, tooltip: 'Investment in fulfillment' },
        { name: 'Working Capital Days', formula: 'Working Capital / Daily Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; if (!i?.revenue || !b?.current_assets || !b?.current_liabilities) return undefined; const wc = b.current_assets - b.current_liabilities; return (wc / (i.revenue / 365)); }, format: 'days', benchmark: { good: -30, bad: 30 }, tooltip: 'Negative is good' },
    ],
};

export const restaurantsProfile: IndustryProfile = {
    category: 'restaurants',
    label: 'Restaurants',
    icon: Utensils,
    color: 'text-red-500',
    description: 'Restaurants and food service',
    kpis: [
        { name: 'Gross Margin', formula: 'Gross Profit / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 70, bad: 55 }, tooltip: 'Restaurant gross margins are high' },
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 8 }, tooltip: 'Operating profitability' },
        { name: 'EBITDA Margin', formula: 'EBITDA / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.ebitda && i?.revenue ? (i.ebitda / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 20, bad: 12 }, tooltip: 'EBITDA margin' },
        { name: 'Asset Turnover', formula: 'Revenue / Assets', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.revenue && b?.total_assets ? i.revenue / b.total_assets : undefined; }, format: 'ratio', benchmark: { good: 1.5, bad: 0.8 }, tooltip: 'Revenue per dollar of assets' },
        { name: 'Debt/EBITDA', formula: 'Total Debt / EBITDA', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return b?.total_debt && i?.ebitda && i.ebitda > 0 ? b.total_debt / i.ebitda : undefined; }, format: 'ratio', benchmark: { good: 2, bad: 4 }, tooltip: 'Leverage ratio' },
    ],
};

export const consumerProductsProfile: IndustryProfile = {
    category: 'consumer_products',
    label: 'Consumer Products',
    icon: Package,
    color: 'text-lime-600',
    description: 'Household, personal products, packaged foods',
    kpis: [
        { name: 'Gross Margin', formula: 'Gross Profit / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 45, bad: 30 }, tooltip: 'Consumer products: 35-55%' },
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 18, bad: 10 }, tooltip: 'Operating profitability' },
        { name: 'Dividend Payout', formula: 'Dividends / Net Income', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.net_income && c?.dividends_paid && i.net_income > 0 ? Math.abs(c.dividends_paid) / i.net_income * 100 : undefined; }, format: 'percent', benchmark: { good: 50, bad: 75 }, tooltip: 'Consumer staples are dividend payers' },
        { name: 'ROIC', formula: 'NOPAT / Invested Capital', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; if (!i?.operating_income || !b?.total_equity || !b?.total_debt) return undefined; const nopat = i.operating_income * 0.75; const ic = b.total_equity + b.total_debt - (b.cash_and_equivalents || 0); return ic > 0 ? (nopat / ic) * 100 : undefined; }, format: 'percent', benchmark: { good: 15, bad: 8 }, tooltip: 'Return on Invested Capital' },
        { name: 'FCF Conversion', formula: 'FCF / Net Income', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.net_income && c?.free_cash_flow && i.net_income > 0 ? (c.free_cash_flow / i.net_income) * 100 : undefined; }, format: 'percent', benchmark: { good: 90, bad: 60 }, tooltip: 'Cash conversion efficiency' },
    ],
};

export const beveragesProfile: IndustryProfile = {
    category: 'beverages',
    label: 'Beverages',
    icon: Droplets,
    color: 'text-sky-600',
    description: 'Alcoholic and non-alcoholic beverages',
    kpis: [
        { name: 'Gross Margin', formula: 'Gross Profit / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 55, bad: 40 }, tooltip: 'Beverage companies: 50-65%' },
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 25, bad: 15 }, tooltip: 'Operating profitability' },
        { name: 'Dividend Payout', formula: 'Dividends / Net Income', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.net_income && c?.dividends_paid && i.net_income > 0 ? Math.abs(c.dividends_paid) / i.net_income * 100 : undefined; }, format: 'percent', benchmark: { good: 60, bad: 80 }, tooltip: 'Consistent dividends' },
        { name: 'ROIC', formula: 'NOPAT / Invested Capital', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; if (!i?.operating_income || !b?.total_equity || !b?.total_debt) return undefined; const nopat = i.operating_income * 0.75; const ic = b.total_equity + b.total_debt - (b.cash_and_equivalents || 0); return ic > 0 ? (nopat / ic) * 100 : undefined; }, format: 'percent', benchmark: { good: 20, bad: 10 }, tooltip: 'Return on Invested Capital' },
        { name: 'Debt/EBITDA', formula: 'Net Debt / EBITDA', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return b?.net_debt && i?.ebitda && i.ebitda > 0 ? b.net_debt / i.ebitda : undefined; }, format: 'ratio', benchmark: { good: 2, bad: 4 }, tooltip: 'Leverage ratio' },
    ],
};

export const apparelProfile: IndustryProfile = {
    category: 'apparel',
    label: 'Apparel',
    icon: ShoppingCart,
    color: 'text-fuchsia-600',
    description: 'Apparel manufacturers and retailers',
    kpis: [
        { name: 'Gross Margin', formula: 'Gross Profit / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 50, bad: 35 }, tooltip: 'Apparel: 45-55%' },
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 12, bad: 6 }, tooltip: 'Operating profitability' },
        { name: 'Inventory Turns', formula: 'COGS / Inventory', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.cost_of_revenue && b?.inventory ? i.cost_of_revenue / b.inventory : undefined; }, format: 'turns', benchmark: { good: 4, bad: 2 }, tooltip: 'Fashion is perishable' },
        { name: 'Days Inventory', formula: '(Inventory / COGS) × 365', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.cost_of_revenue && b?.inventory ? (b.inventory / i.cost_of_revenue) * 365 : undefined; }, format: 'days', benchmark: { good: 90, bad: 150 }, tooltip: 'Days of inventory' },
        { name: 'ROE', formula: 'Net Income / Equity', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.net_income && b?.total_equity ? (i.net_income / b.total_equity) * 100 : undefined; }, format: 'percent', benchmark: { good: 20, bad: 10 }, tooltip: 'Return on Equity' },
    ],
};

export const autoProfile: IndustryProfile = {
    category: 'auto',
    label: 'Automotive',
    icon: Car,
    color: 'text-slate-600',
    description: 'Auto manufacturers, parts, and dealerships',
    kpis: [
        { name: 'Gross Margin', formula: 'Gross Profit / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.gross_profit && i?.revenue ? (i.gross_profit / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 18, bad: 10 }, tooltip: 'OEMs: 10-20%, Parts: 20-30%' },
        { name: 'Operating Margin', formula: 'Operating Income / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; return i?.operating_income && i?.revenue ? (i.operating_income / i.revenue) * 100 : undefined; }, format: 'percent', benchmark: { good: 8, bad: 3 }, tooltip: 'Auto margins are thin' },
        { name: 'CapEx/Revenue', formula: 'CapEx / Revenue', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const c = d.cash_flows[0]; return i?.revenue && c?.capex ? Math.abs(c.capex) / i.revenue * 100 : undefined; }, format: 'percent', benchmark: { good: 5, bad: 10 }, tooltip: 'Capital intensity' },
        { name: 'Inventory Days', formula: '(Inventory / COGS) × 365', calculate: (d: FinancialData) => { const i = d.income_statements[0]; const b = d.balance_sheets[0]; return i?.cost_of_revenue && b?.inventory ? (b.inventory / i.cost_of_revenue) * 365 : undefined; }, format: 'days', benchmark: { good: 45, bad: 75 }, tooltip: 'Days of inventory' },
        { name: 'Debt/Equity', formula: 'Total Debt / Equity', calculate: (d: FinancialData) => { const b = d.balance_sheets[0]; return b?.total_debt && b?.total_equity ? b.total_debt / b.total_equity : undefined; }, format: 'ratio', benchmark: { good: 0.8, bad: 1.5 }, tooltip: 'Financial leverage' },
    ],
};

