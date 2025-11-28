'use client';

import { useState, useCallback, useMemo, useEffect } from 'react';
import { RefreshCw, AlertTriangle, TrendingUp, TrendingDown, Building2, Landmark, HeartPulse, Cpu, ShoppingCart, Factory, Pickaxe, BarChart3 } from 'lucide-react';
import { TickerSearch } from '@/components/common/TickerSearch';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { FinancialMetricChart, FINANCIAL_METRIC_CHART_CONFIG, type MetricDataPoint } from './FinancialMetricChart';

// ============================================================================
// Types (matching FMP API response)
// ============================================================================

interface FinancialPeriod {
    date: string;
    symbol: string;
    fiscal_year: string;
    period: string;  // Q1, Q2, Q3, Q4, FY
    filing_date?: string;
    currency: string;
}

interface IncomeStatement {
    period: FinancialPeriod;
    revenue?: number;
    cost_of_revenue?: number;
    gross_profit?: number;
    research_development?: number;
    selling_general_admin?: number;
    operating_expenses?: number;
    operating_income?: number;
    interest_expense?: number;
    interest_income?: number;
    net_interest_income?: number;  // Banks
    other_income_expense?: number;
    income_before_tax?: number;
    income_tax?: number;
    net_income?: number;
    eps?: number;
    eps_diluted?: number;
    shares_outstanding?: number;
    shares_diluted?: number;
    ebitda?: number;
    ebit?: number;
    depreciation?: number;
}

interface BalanceSheet {
    period: FinancialPeriod;
    total_assets?: number;
    current_assets?: number;
    cash_and_equivalents?: number;
    short_term_investments?: number;
    cash_and_short_term?: number;
    receivables?: number;
    inventory?: number;
    other_current_assets?: number;
    property_plant_equipment?: number;
    goodwill?: number;
    intangible_assets?: number;
    long_term_investments?: number;
    other_noncurrent_assets?: number;
    noncurrent_assets?: number;
    total_liabilities?: number;
    current_liabilities?: number;
    accounts_payable?: number;
    short_term_debt?: number;
    deferred_revenue?: number;
    other_current_liabilities?: number;
    long_term_debt?: number;
    other_noncurrent_liabilities?: number;
    noncurrent_liabilities?: number;
    total_equity?: number;
    common_stock?: number;
    retained_earnings?: number;
    treasury_stock?: number;
    accumulated_other_income?: number;
    total_debt?: number;
    net_debt?: number;
    total_investments?: number;
}

interface CashFlow {
    period: FinancialPeriod;
    net_income?: number;
    depreciation?: number;
    stock_compensation?: number;
    change_working_capital?: number;
    change_receivables?: number;
    change_inventory?: number;
    change_payables?: number;
    other_operating?: number;
    operating_cash_flow?: number;
    capex?: number;
    acquisitions?: number;
    purchases_investments?: number;
    sales_investments?: number;
    other_investing?: number;
    investing_cash_flow?: number;
    debt_issued?: number;
    debt_repaid?: number;
    stock_issued?: number;
    stock_repurchased?: number;
    dividends_paid?: number;
    other_financing?: number;
    financing_cash_flow?: number;
    net_change_cash?: number;
    cash_beginning?: number;
    cash_ending?: number;
    free_cash_flow?: number;
}

interface FinancialData {
    symbol: string;
    currency: string;
    income_statements: IncomeStatement[];
    balance_sheets: BalanceSheet[];
    cash_flows: CashFlow[];
    last_updated: string;
    cached: boolean;
    cache_age_seconds?: number;
}

type TabType = 'income' | 'balance' | 'cashflow';
type PeriodFilter = 'annual' | 'quarter' | 'all';

// ============================================================================
// Industry Detection
// ============================================================================

type IndustryType = 'tech' | 'bank' | 'insurance' | 'healthcare' | 'retail' | 'industrial' | 'mining' | 'general';

interface IndustryProfile {
    type: IndustryType;
    label: string;
    icon: typeof Building2;
    color: string;
    // Campos relevantes por industria
    incomeFields: string[];
    balanceFields: string[];
    cashFlowFields: string[];
    // Campos a ocultar
    hideFields: string[];
    // Ratios especiales
    specialRatios: { label: string; calculate: (data: FinancialData) => number | undefined }[];
}

// Detectar industria basado en características financieras
function detectIndustry(data: FinancialData): IndustryType {
    if (!data.income_statements.length || !data.balance_sheets.length) return 'general';

    const income = data.income_statements[0];
    const balance = data.balance_sheets[0];

    // Bancos: Net Interest Income alto, sin inventory
    if (income.net_interest_income && income.net_interest_income > 0 && !balance.inventory) {
        return 'bank';
    }

    // Tech/Biotech: R&D alto (>10% revenue) o sin revenue significativo
    if (income.research_development && income.revenue) {
        const rdRatio = income.research_development / income.revenue;
        if (rdRatio > 0.15) return 'tech';
    }

    // Biotech sin revenue significativo pero con R&D
    if (income.research_development && (!income.revenue || income.revenue < income.research_development * 2)) {
        return 'healthcare';
    }

    // Retail: Inventory alto (>5% assets) y bajo margen bruto
    if (balance.inventory && balance.total_assets) {
        const invRatio = balance.inventory / balance.total_assets;
        if (invRatio > 0.08 && income.gross_profit && income.revenue) {
            const grossMargin = income.gross_profit / income.revenue;
            if (grossMargin < 0.35) return 'retail';
        }
    }

    // Mining/Energy: CapEx muy alto relativo a operating cash flow
    const cashFlow = data.cash_flows[0];
    if (cashFlow?.capex && cashFlow?.operating_cash_flow) {
        const capexRatio = Math.abs(cashFlow.capex) / Math.abs(cashFlow.operating_cash_flow);
        if (capexRatio > 0.8) return 'mining';
    }

    // Industrial: PP&E alto (>30% assets)
    if (balance.property_plant_equipment && balance.total_assets) {
        const ppeRatio = balance.property_plant_equipment / balance.total_assets;
        if (ppeRatio > 0.30) return 'industrial';
    }

    return 'general';
}

const INDUSTRY_PROFILES: Record<IndustryType, IndustryProfile> = {
    tech: {
        type: 'tech',
        label: 'Technology',
        icon: Cpu,
        color: 'text-blue-600',
        incomeFields: ['revenue', 'gross_profit', 'research_development', 'operating_income', 'net_income', 'eps'],
        balanceFields: ['cash_and_equivalents', 'total_investments', 'goodwill', 'intangible_assets', 'total_debt', 'total_equity'],
        cashFlowFields: ['operating_cash_flow', 'capex', 'stock_repurchased', 'free_cash_flow'],
        hideFields: ['inventory'],
        specialRatios: [
            {
                label: 'R&D/Revenue', calculate: (d) => {
                    const i = d.income_statements[0];
                    return i?.research_development && i?.revenue ? (i.research_development / i.revenue) * 100 : undefined;
                }
            },
        ],
    },
    bank: {
        type: 'bank',
        label: 'Banking',
        icon: Landmark,
        color: 'text-emerald-600',
        incomeFields: ['net_interest_income', 'interest_income', 'interest_expense', 'operating_income', 'net_income', 'eps'],
        balanceFields: ['total_assets', 'cash_and_equivalents', 'long_term_investments', 'total_liabilities', 'total_debt', 'total_equity'],
        cashFlowFields: ['operating_cash_flow', 'investing_cash_flow', 'financing_cash_flow', 'dividends_paid'],
        hideFields: ['inventory', 'gross_profit', 'cost_of_revenue', 'research_development', 'capex'],
        specialRatios: [
            {
                label: 'Net Interest Margin', calculate: (d) => {
                    const i = d.income_statements[0];
                    const b = d.balance_sheets[0];
                    return i?.net_interest_income && b?.total_assets ? (i.net_interest_income / b.total_assets) * 100 : undefined;
                }
            },
        ],
    },
    insurance: {
        type: 'insurance',
        label: 'Insurance',
        icon: HeartPulse,
        color: 'text-purple-600',
        incomeFields: ['revenue', 'operating_expenses', 'operating_income', 'net_income', 'eps'],
        balanceFields: ['total_assets', 'total_investments', 'total_liabilities', 'total_equity'],
        cashFlowFields: ['operating_cash_flow', 'investing_cash_flow', 'dividends_paid'],
        hideFields: ['inventory', 'gross_profit', 'research_development', 'capex'],
        specialRatios: [],
    },
    healthcare: {
        type: 'healthcare',
        label: 'Healthcare/Biotech',
        icon: HeartPulse,
        color: 'text-rose-600',
        incomeFields: ['revenue', 'cost_of_revenue', 'gross_profit', 'research_development', 'operating_income', 'net_income'],
        balanceFields: ['cash_and_equivalents', 'receivables', 'total_assets', 'total_debt', 'total_equity'],
        cashFlowFields: ['operating_cash_flow', 'capex', 'stock_issued', 'free_cash_flow'],
        hideFields: ['inventory'],
        specialRatios: [
            {
                label: 'Cash Runway (years)', calculate: (d) => {
                    const b = d.balance_sheets[0];
                    const c = d.cash_flows[0];
                    if (b?.cash_and_equivalents && c?.operating_cash_flow && c.operating_cash_flow < 0) {
                        return b.cash_and_equivalents / Math.abs(c.operating_cash_flow);
                    }
                    return undefined;
                }
            },
        ],
    },
    retail: {
        type: 'retail',
        label: 'Retail',
        icon: ShoppingCart,
        color: 'text-orange-600',
        incomeFields: ['revenue', 'cost_of_revenue', 'gross_profit', 'selling_general_admin', 'operating_income', 'net_income'],
        balanceFields: ['inventory', 'receivables', 'accounts_payable', 'property_plant_equipment', 'total_debt', 'total_equity'],
        cashFlowFields: ['operating_cash_flow', 'capex', 'change_inventory', 'dividends_paid', 'free_cash_flow'],
        hideFields: ['research_development', 'goodwill'],
        specialRatios: [
            {
                label: 'Inventory Turnover', calculate: (d) => {
                    const i = d.income_statements[0];
                    const b = d.balance_sheets[0];
                    return i?.cost_of_revenue && b?.inventory ? i.cost_of_revenue / b.inventory : undefined;
                }
            },
            {
                label: 'Days Inventory', calculate: (d) => {
                    const i = d.income_statements[0];
                    const b = d.balance_sheets[0];
                    return i?.cost_of_revenue && b?.inventory ? (b.inventory / i.cost_of_revenue) * 365 : undefined;
                }
            },
        ],
    },
    industrial: {
        type: 'industrial',
        label: 'Industrial',
        icon: Factory,
        color: 'text-slate-600',
        incomeFields: ['revenue', 'cost_of_revenue', 'gross_profit', 'operating_expenses', 'operating_income', 'ebitda', 'net_income'],
        balanceFields: ['property_plant_equipment', 'inventory', 'receivables', 'total_debt', 'total_equity'],
        cashFlowFields: ['operating_cash_flow', 'capex', 'depreciation', 'dividends_paid', 'free_cash_flow'],
        hideFields: ['research_development', 'goodwill'],
        specialRatios: [
            {
                label: 'Asset Turnover', calculate: (d) => {
                    const i = d.income_statements[0];
                    const b = d.balance_sheets[0];
                    return i?.revenue && b?.total_assets ? i.revenue / b.total_assets : undefined;
                }
            },
        ],
    },
    mining: {
        type: 'mining',
        label: 'Mining/Energy',
        icon: Pickaxe,
        color: 'text-amber-600',
        incomeFields: ['revenue', 'cost_of_revenue', 'gross_profit', 'depreciation', 'operating_income', 'ebitda', 'net_income'],
        balanceFields: ['property_plant_equipment', 'total_assets', 'total_debt', 'net_debt', 'total_equity'],
        cashFlowFields: ['operating_cash_flow', 'capex', 'depreciation', 'debt_issued', 'debt_repaid', 'free_cash_flow'],
        hideFields: ['research_development', 'inventory'],
        specialRatios: [
            {
                label: 'CapEx/OCF', calculate: (d) => {
                    const c = d.cash_flows[0];
                    return c?.capex && c?.operating_cash_flow ? Math.abs(c.capex) / Math.abs(c.operating_cash_flow) * 100 : undefined;
                }
            },
        ],
    },
    general: {
        type: 'general',
        label: 'General',
        icon: Building2,
        color: 'text-slate-500',
        incomeFields: ['revenue', 'gross_profit', 'operating_income', 'net_income', 'eps'],
        balanceFields: ['total_assets', 'total_liabilities', 'total_equity', 'total_debt'],
        cashFlowFields: ['operating_cash_flow', 'investing_cash_flow', 'financing_cash_flow', 'free_cash_flow'],
        hideFields: [],
        specialRatios: [],
    },
};

// ============================================================================
// Helpers
// ============================================================================

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function formatValue(value: number | undefined | null, type: 'currency' | 'percent' | 'ratio' | 'eps' | 'days' = 'currency'): string {
    if (value === undefined || value === null) return '--';

    if (type === 'percent') {
        const sign = value >= 0 ? '' : '';
        return `${sign}${value.toFixed(1)}%`;
    }

    if (type === 'ratio' || type === 'days') {
        return value.toFixed(1);
    }

    if (type === 'eps') {
        const sign = value < 0 ? '-' : '';
        return `${sign}$${Math.abs(value).toFixed(2)}`;
    }

    // Currency formatting
    const absValue = Math.abs(value);
    const sign = value < 0 ? '-' : '';

    if (absValue >= 1_000_000_000_000) {
        return `${sign}$${(absValue / 1_000_000_000_000).toFixed(1)}T`;
    } else if (absValue >= 1_000_000_000) {
        return `${sign}$${(absValue / 1_000_000_000).toFixed(1)}B`;
    } else if (absValue >= 1_000_000) {
        return `${sign}$${(absValue / 1_000_000).toFixed(1)}M`;
    } else if (absValue >= 1_000) {
        return `${sign}$${(absValue / 1_000).toFixed(1)}K`;
    }
    return `${sign}$${absValue.toFixed(0)}`;
}

function ValueCell({ value, type = 'currency', showTrend = false, prevValue, isNegativeBad = true }: {
    value: number | undefined | null;
    type?: 'currency' | 'percent' | 'ratio' | 'eps' | 'days';
    showTrend?: boolean;
    prevValue?: number;
    isNegativeBad?: boolean;  // Some negatives are good (e.g., debt repaid)
}) {
    const formatted = formatValue(value, type);
    const isNegative = value !== undefined && value !== null && value < 0;
    const showRed = isNegative && isNegativeBad;

    let trendIcon = null;
    if (showTrend && value !== undefined && value !== null && prevValue !== undefined && prevValue !== 0) {
        const growth = ((value - prevValue) / Math.abs(prevValue)) * 100;
        if (growth > 5) {
            trendIcon = <TrendingUp className="w-2.5 h-2.5 text-emerald-600 inline ml-0.5" />;
        } else if (growth < -5) {
            trendIcon = <TrendingDown className="w-2.5 h-2.5 text-red-500 inline ml-0.5" />;
        }
    }

    return (
        <span
            className="font-mono text-[10px]"
            style={{
                color: showRed ? '#dc2626' : '#334155',
                fontWeight: showRed ? 600 : 400
            }}
        >
            {formatted}{trendIcon}
        </span>
    );
}

// ============================================================================
// Table Components
// ============================================================================

interface TableRowProps {
    label: string;
    values?: (number | undefined)[];
    type?: 'currency' | 'percent' | 'ratio' | 'eps' | 'days';
    isHeader?: boolean;
    indent?: boolean;
    bold?: boolean;
    showTrend?: boolean;
    isNegativeBad?: boolean;
    hidden?: boolean;
    metricKey?: string;
    onClick?: (metricKey: string, label: string, type: string, isNegativeBad: boolean) => void;
}

function TableRow({ label, values = [], type = 'currency', isHeader, indent, bold, showTrend, isNegativeBad = true, hidden, metricKey, onClick }: TableRowProps) {
    // Ocultar filas si todos los valores son null/undefined/0
    if (hidden) return null;

    if (isHeader) {
        return (
            <tr className="bg-slate-100 border-t border-slate-300">
                <td colSpan={100} className="px-2 py-1 text-[9px] font-semibold text-slate-600 uppercase tracking-wide">
                    {label}
                </td>
            </tr>
        );
    }

    if (!values || values.length === 0) {
        return null;
    }

    // Auto-hide si todos los valores son vacíos
    const hasData = values.some(v => v !== undefined && v !== null && v !== 0);
    if (!hasData) return null;

    const isClickable = metricKey && onClick;

    return (
        <tr 
            className={`border-b border-slate-100 hover:bg-blue-50 ${isClickable ? 'cursor-pointer group' : 'hover:bg-slate-50'}`}
            onClick={isClickable ? () => onClick(metricKey, label, type, isNegativeBad) : undefined}
        >
            <td className={`px-2 py-0.5 text-[10px] text-slate-600 whitespace-nowrap ${indent ? 'pl-4' : ''} ${bold ? 'font-semibold text-slate-800' : ''}`}>
                <span className="flex items-center gap-1">
                {label}
                    {isClickable && (
                        <BarChart3 className="w-3 h-3 text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                    )}
                </span>
            </td>
            {values.map((val, idx) => (
                <td key={idx} className="px-2 py-0.5 text-right">
                    <ValueCell
                        value={val}
                        type={type}
                        showTrend={showTrend && idx < values.length - 1}
                        prevValue={showTrend ? values[idx + 1] : undefined}
                        isNegativeBad={isNegativeBad}
                    />
                </td>
            ))}
        </tr>
    );
}

interface TableProps {
    data: any[];
    periodFilter: PeriodFilter;
    industry: IndustryProfile;
    onRowClick?: (metricKey: string, label: string, type: string, isNegativeBad: boolean) => void;
}

function IncomeTable({ data, periodFilter, industry, onRowClick }: TableProps & { data: IncomeStatement[] }) {
    // Filtrar por período: FY = annual, Q1-Q4 = quarter
    const filtered = data.filter(d => {
        if (periodFilter === 'all') return true;
        if (periodFilter === 'annual') return d.period.period === 'FY';
        if (periodFilter === 'quarter') return d.period.period.startsWith('Q');
        return true;
    }).slice(0, 5);

    if (filtered.length === 0) return <div className="text-center py-4 text-slate-400 text-xs">No data</div>;

    // Formato: "FY 2024" o "Q1 2024"
    const periods = filtered.map(d => `${d.period.period} ${d.period.fiscal_year}`);
    const getValue = (key: keyof IncomeStatement) => filtered.map(d => d[key] as number | undefined);
    const isHidden = (field: string) => industry.hideFields.includes(field);

    // Calcular márgenes
    const grossMargins = filtered.map(d =>
        d.revenue && d.gross_profit ? (d.gross_profit / d.revenue) * 100 : undefined
    );
    const opMargins = filtered.map(d =>
        d.revenue && d.operating_income ? (d.operating_income / d.revenue) * 100 : undefined
    );
    const netMargins = filtered.map(d =>
        d.revenue && d.net_income ? (d.net_income / d.revenue) * 100 : undefined
    );

    // Para bancos: Net Interest Margin
    const isBank = industry.type === 'bank';

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-left">
                <thead>
                    <tr className="border-b-2 border-slate-200">
                        <th className="px-2 py-1 text-[9px] font-semibold text-slate-500 uppercase w-36">Item</th>
                        {periods.map((p, i) => (
                            <th key={i} className="px-2 py-1 text-[9px] font-semibold text-slate-500 text-right whitespace-nowrap">{p}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {isBank ? (
                        <>
                            <TableRow label="Interest Income" isHeader />
                            <TableRow label="Interest Income" values={getValue('interest_income')} bold showTrend metricKey="interest_income" onClick={onRowClick} />
                            <TableRow label="Interest Expense" values={getValue('interest_expense')} indent isNegativeBad={false} metricKey="interest_expense" onClick={onRowClick} />
                            <TableRow label="Net Interest Income" values={getValue('net_interest_income')} bold metricKey="net_interest_income" onClick={onRowClick} />
                        </>
                    ) : (
                        <>
                            <TableRow label="Revenue" isHeader />
                            <TableRow label="Total Revenue" values={getValue('revenue')} bold showTrend metricKey="revenue" onClick={onRowClick} />
                            <TableRow label="Cost of Revenue" values={getValue('cost_of_revenue')} indent hidden={isHidden('cost_of_revenue')} metricKey="cost_of_revenue" onClick={onRowClick} />
                            <TableRow label="Gross Profit" values={getValue('gross_profit')} bold hidden={isHidden('gross_profit')} metricKey="gross_profit" onClick={onRowClick} />
                        </>
                    )}

                    <TableRow label="Operating Expenses" isHeader />
                    <TableRow label="R&D" values={getValue('research_development')} indent hidden={isHidden('research_development')} metricKey="research_development" onClick={onRowClick} />
                    <TableRow label="SG&A" values={getValue('selling_general_admin')} indent metricKey="selling_general_admin" onClick={onRowClick} />
                    <TableRow label="Total OpEx" values={getValue('operating_expenses')} metricKey="operating_expenses" onClick={onRowClick} />
                    <TableRow label="Operating Income" values={getValue('operating_income')} bold showTrend metricKey="operating_income" onClick={onRowClick} />

                    <TableRow label="Net Income" isHeader />
                    <TableRow label="EBITDA" values={getValue('ebitda')} hidden={isBank} metricKey="ebitda" onClick={onRowClick} />
                    <TableRow label="Interest Expense" values={getValue('interest_expense')} indent hidden={isBank} metricKey="interest_expense" onClick={onRowClick} />
                    <TableRow label="Pre-tax Income" values={getValue('income_before_tax')} metricKey="income_before_tax" onClick={onRowClick} />
                    <TableRow label="Income Tax" values={getValue('income_tax')} indent metricKey="income_tax" onClick={onRowClick} />
                    <TableRow label="Net Income" values={getValue('net_income')} bold showTrend metricKey="net_income" onClick={onRowClick} />

                    <TableRow label="Per Share" isHeader />
                    <TableRow label="EPS Basic" values={getValue('eps')} type="eps" metricKey="eps" onClick={onRowClick} />
                    <TableRow label="EPS Diluted" values={getValue('eps_diluted')} type="eps" metricKey="eps_diluted" onClick={onRowClick} />

                    <TableRow label="Margins" isHeader />
                    <TableRow label="Gross Margin" values={grossMargins} type="percent" hidden={isBank || isHidden('gross_profit')} metricKey="gross_margin" onClick={onRowClick} />
                    <TableRow label="Operating Margin" values={opMargins} type="percent" metricKey="operating_margin" onClick={onRowClick} />
                    <TableRow label="Net Margin" values={netMargins} type="percent" metricKey="net_margin" onClick={onRowClick} />
                </tbody>
            </table>
        </div>
    );
}

function BalanceTable({ data, periodFilter, industry, onRowClick }: TableProps & { data: BalanceSheet[] }) {
    const filtered = data.filter(d => {
        if (periodFilter === 'all') return true;
        if (periodFilter === 'annual') return d.period.period === 'FY';
        if (periodFilter === 'quarter') return d.period.period.startsWith('Q');
        return true;
    }).slice(0, 5);

    if (filtered.length === 0) return <div className="text-center py-4 text-slate-400 text-xs">No data</div>;

    const periods = filtered.map(d => `${d.period.period} ${d.period.fiscal_year}`);
    const getValue = (key: keyof BalanceSheet) => filtered.map(d => d[key] as number | undefined);
    const isHidden = (field: string) => industry.hideFields.includes(field);

    // Calcular ratios
    const currentRatios = filtered.map(d =>
        d.current_assets && d.current_liabilities ? d.current_assets / d.current_liabilities : undefined
    );
    const debtToEquity = filtered.map(d =>
        d.total_debt && d.total_equity && d.total_equity !== 0 ? d.total_debt / d.total_equity : undefined
    );
    const workingCapital = filtered.map(d =>
        d.current_assets && d.current_liabilities ? d.current_assets - d.current_liabilities : undefined
    );

    const isBank = industry.type === 'bank';

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-left">
                <thead>
                    <tr className="border-b-2 border-slate-200">
                        <th className="px-2 py-1 text-[9px] font-semibold text-slate-500 uppercase w-36">Item</th>
                        {periods.map((p, i) => (
                            <th key={i} className="px-2 py-1 text-[9px] font-semibold text-slate-500 text-right whitespace-nowrap">{p}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    <TableRow label="Assets" isHeader />
                    <TableRow label="Total Assets" values={getValue('total_assets')} bold showTrend metricKey="total_assets" onClick={onRowClick} />
                    <TableRow label="Current Assets" values={getValue('current_assets')} hidden={isBank} metricKey="current_assets" onClick={onRowClick} />
                    <TableRow label="Cash & Equivalents" values={getValue('cash_and_equivalents')} indent metricKey="cash_and_equivalents" onClick={onRowClick} />
                    <TableRow label="Short-term Investments" values={getValue('short_term_investments')} indent metricKey="short_term_investments" onClick={onRowClick} />
                    <TableRow label="Receivables" values={getValue('receivables')} indent hidden={isBank} metricKey="receivables" onClick={onRowClick} />
                    <TableRow label="Inventory" values={getValue('inventory')} indent hidden={isHidden('inventory')} metricKey="inventory" onClick={onRowClick} />
                    <TableRow label="PP&E" values={getValue('property_plant_equipment')} hidden={isBank} metricKey="property_plant_equipment" onClick={onRowClick} />
                    <TableRow label="Long-term Investments" values={getValue('long_term_investments')} indent metricKey="long_term_investments" onClick={onRowClick} />
                    <TableRow label="Total Investments" values={getValue('total_investments')} hidden={!isBank} metricKey="total_investments" onClick={onRowClick} />
                    <TableRow label="Goodwill" values={getValue('goodwill')} indent hidden={isHidden('goodwill')} metricKey="goodwill" onClick={onRowClick} />
                    <TableRow label="Intangibles" values={getValue('intangible_assets')} indent metricKey="intangible_assets" onClick={onRowClick} />

                    <TableRow label="Liabilities" isHeader />
                    <TableRow label="Total Liabilities" values={getValue('total_liabilities')} bold metricKey="total_liabilities" onClick={onRowClick} />
                    <TableRow label="Current Liabilities" values={getValue('current_liabilities')} hidden={isBank} metricKey="current_liabilities" onClick={onRowClick} />
                    <TableRow label="Accounts Payable" values={getValue('accounts_payable')} indent hidden={isBank} metricKey="accounts_payable" onClick={onRowClick} />
                    <TableRow label="Short-term Debt" values={getValue('short_term_debt')} indent metricKey="short_term_debt" onClick={onRowClick} />
                    <TableRow label="Long-term Debt" values={getValue('long_term_debt')} metricKey="long_term_debt" onClick={onRowClick} />
                    <TableRow label="Deferred Revenue" values={getValue('deferred_revenue')} indent metricKey="deferred_revenue" onClick={onRowClick} />

                    <TableRow label="Equity" isHeader />
                    <TableRow label="Total Equity" values={getValue('total_equity')} bold showTrend metricKey="total_equity" onClick={onRowClick} />
                    <TableRow label="Common Stock" values={getValue('common_stock')} indent metricKey="common_stock" onClick={onRowClick} />
                    <TableRow label="Retained Earnings" values={getValue('retained_earnings')} indent metricKey="retained_earnings" onClick={onRowClick} />
                    <TableRow label="Treasury Stock" values={getValue('treasury_stock')} indent isNegativeBad={false} metricKey="treasury_stock" onClick={onRowClick} />

                    <TableRow label="Metrics" isHeader />
                    <TableRow label="Total Debt" values={getValue('total_debt')} metricKey="total_debt" onClick={onRowClick} />
                    <TableRow label="Net Debt" values={getValue('net_debt')} metricKey="net_debt" onClick={onRowClick} />
                    <TableRow label="Working Capital" values={workingCapital} hidden={isBank} metricKey="working_capital" onClick={onRowClick} />
                    <TableRow label="Current Ratio" values={currentRatios} type="ratio" hidden={isBank} metricKey="current_ratio" onClick={onRowClick} />
                    <TableRow label="Debt/Equity" values={debtToEquity} type="ratio" metricKey="debt_to_equity" onClick={onRowClick} />
                </tbody>
            </table>
        </div>
    );
}

function CashFlowTable({ data, periodFilter, industry, onRowClick }: TableProps & { data: CashFlow[] }) {
    const filtered = data.filter(d => {
        if (periodFilter === 'all') return true;
        if (periodFilter === 'annual') return d.period.period === 'FY';
        if (periodFilter === 'quarter') return d.period.period.startsWith('Q');
        return true;
    }).slice(0, 5);

    if (filtered.length === 0) return <div className="text-center py-4 text-slate-400 text-xs">No data</div>;

    const periods = filtered.map(d => `${d.period.period} ${d.period.fiscal_year}`);
    const getValue = (key: keyof CashFlow) => filtered.map(d => d[key] as number | undefined);
    const isHidden = (field: string) => industry.hideFields.includes(field);

    const isBank = industry.type === 'bank';
    const isMining = industry.type === 'mining';

    // CapEx/OCF ratio for mining/capital intensive
    const capexRatios = filtered.map(d =>
        d.capex && d.operating_cash_flow ? Math.abs(d.capex) / Math.abs(d.operating_cash_flow) * 100 : undefined
    );

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-left">
                <thead>
                    <tr className="border-b-2 border-slate-200">
                        <th className="px-2 py-1 text-[9px] font-semibold text-slate-500 uppercase w-36">Item</th>
                        {periods.map((p, i) => (
                            <th key={i} className="px-2 py-1 text-[9px] font-semibold text-slate-500 text-right whitespace-nowrap">{p}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    <TableRow label="Operating Activities" isHeader />
                    <TableRow label="Net Income" values={getValue('net_income')} indent metricKey="cf_net_income" onClick={onRowClick} />
                    <TableRow label="Operating Cash Flow" values={getValue('operating_cash_flow')} bold showTrend metricKey="operating_cash_flow" onClick={onRowClick} />
                    <TableRow label="Depreciation" values={getValue('depreciation')} indent isNegativeBad={false} metricKey="depreciation" onClick={onRowClick} />
                    <TableRow label="Stock Compensation" values={getValue('stock_compensation')} indent isNegativeBad={false} metricKey="stock_compensation" onClick={onRowClick} />
                    <TableRow label="Working Capital Δ" values={getValue('change_working_capital')} indent metricKey="change_working_capital" onClick={onRowClick} />

                    <TableRow label="Investing Activities" isHeader />
                    <TableRow label="Investing Cash Flow" values={getValue('investing_cash_flow')} bold metricKey="investing_cash_flow" onClick={onRowClick} />
                    <TableRow label="CapEx" values={getValue('capex')} indent isNegativeBad={false} hidden={isHidden('capex')} metricKey="capex" onClick={onRowClick} />
                    <TableRow label="Acquisitions" values={getValue('acquisitions')} indent isNegativeBad={false} metricKey="acquisitions" onClick={onRowClick} />
                    <TableRow label="Purchases (Investments)" values={getValue('purchases_investments')} indent isNegativeBad={false} metricKey="purchases_investments" onClick={onRowClick} />
                    <TableRow label="Sales (Investments)" values={getValue('sales_investments')} indent isNegativeBad={false} metricKey="sales_investments" onClick={onRowClick} />

                    <TableRow label="Financing Activities" isHeader />
                    <TableRow label="Financing Cash Flow" values={getValue('financing_cash_flow')} bold metricKey="financing_cash_flow" onClick={onRowClick} />
                    <TableRow label="Debt Issued" values={getValue('debt_issued')} indent isNegativeBad={false} metricKey="debt_issued" onClick={onRowClick} />
                    <TableRow label="Debt Repaid" values={getValue('debt_repaid')} indent isNegativeBad={false} metricKey="debt_repaid" onClick={onRowClick} />
                    <TableRow label="Stock Issued" values={getValue('stock_issued')} indent isNegativeBad={false} metricKey="stock_issued" onClick={onRowClick} />
                    <TableRow label="Stock Repurchased" values={getValue('stock_repurchased')} indent isNegativeBad={false} metricKey="stock_repurchased" onClick={onRowClick} />
                    <TableRow label="Dividends Paid" values={getValue('dividends_paid')} indent isNegativeBad={false} metricKey="dividends_paid" onClick={onRowClick} />

                    <TableRow label="Summary" isHeader />
                    <TableRow label="Net Change in Cash" values={getValue('net_change_cash')} bold metricKey="net_change_cash" onClick={onRowClick} />
                    <TableRow label="Cash (Beginning)" values={getValue('cash_beginning')} indent metricKey="cash_beginning" onClick={onRowClick} />
                    <TableRow label="Cash (Ending)" values={getValue('cash_ending')} indent metricKey="cash_ending" onClick={onRowClick} />
                    <TableRow label="Free Cash Flow" values={getValue('free_cash_flow')} bold showTrend hidden={isBank} metricKey="free_cash_flow" onClick={onRowClick} />

                    {/* Ratio especial para mining/capital intensive */}
                    {isMining && (
                        <TableRow label="CapEx/OCF %" values={capexRatios} type="percent" metricKey="capex_ocf_ratio" onClick={onRowClick} />
                    )}
                </tbody>
            </table>
        </div>
    );
}

// ============================================================================
// Industry Badge Component
// ============================================================================

function IndustryBadge({ industry }: { industry: IndustryProfile }) {
    const Icon = industry.icon;
    return (
        <div className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium ${industry.color} bg-slate-100`}>
            <Icon className="w-3 h-3" />
            <span>{industry.label}</span>
        </div>
    );
}

// ============================================================================
// Special Ratios Component
// ============================================================================

function SpecialRatios({ data, industry }: { data: FinancialData; industry: IndustryProfile }) {
    if (industry.specialRatios.length === 0) return null;

    return (
        <div className="flex flex-wrap gap-2 px-2 py-1 bg-slate-50 border-b border-slate-200">
            {industry.specialRatios.map((ratio, idx) => {
                const value = ratio.calculate(data);
                if (value === undefined) return null;
                return (
                    <div key={idx} className="flex items-center gap-1 text-[9px]">
                        <span className="text-slate-500">{ratio.label}:</span>
                        <span className={`font-mono font-medium ${value < 0 ? 'text-red-600' : 'text-slate-800'}`}>
                            {value.toFixed(1)}{ratio.label.includes('%') || ratio.label.includes('Margin') || ratio.label.includes('Runway') ? '' : '%'}
                        </span>
                    </div>
                );
            })}
        </div>
    );
}

// ============================================================================
// Main Component
// ============================================================================

interface FinancialsContentProps {
    initialTicker?: string;
}

export function FinancialsContent({ initialTicker }: FinancialsContentProps = {}) {
    const [inputValue, setInputValue] = useState(initialTicker || '');
    const [selectedTicker, setSelectedTicker] = useState<string | null>(initialTicker || null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [data, setData] = useState<FinancialData | null>(null);

    const [activeTab, setActiveTab] = useState<TabType>('income');
    const [periodFilter, setPeriodFilter] = useState<PeriodFilter>('annual');

    const { openWindow } = useFloatingWindow();

    // Handler para abrir gráfico de métrica en ventana flotante
    const handleMetricClick = useCallback((metricKey: string, label: string, valueType: string, isNegativeBad: boolean) => {
        if (!data || !selectedTicker) return;

        // Extraer datos históricos de la métrica
        const extractMetricData = (): MetricDataPoint[] => {
            // Combinar datos de income, balance y cashflow según la métrica
            let sourceData: any[] = [];
            let key = metricKey;

            // Determinar la fuente de datos
            if (['revenue', 'cost_of_revenue', 'gross_profit', 'research_development', 'selling_general_admin', 
                 'operating_expenses', 'operating_income', 'ebitda', 'ebit', 'interest_expense', 'interest_income',
                 'net_interest_income', 'income_before_tax', 'income_tax', 'net_income', 'eps', 'eps_diluted',
                 'gross_margin', 'operating_margin', 'net_margin'].includes(metricKey)) {
                sourceData = data.income_statements;
                
                // Calcular márgenes si es necesario
                if (metricKey === 'gross_margin') {
                    return sourceData.map(d => ({
                        period: `${d.period.period} ${d.period.fiscal_year}`,
                        fiscalYear: d.period.fiscal_year,
                        value: d.revenue && d.gross_profit ? (d.gross_profit / d.revenue) * 100 : null,
                        isAnnual: d.period.period === 'FY'
                    })).reverse();
                }
                if (metricKey === 'operating_margin') {
                    return sourceData.map(d => ({
                        period: `${d.period.period} ${d.period.fiscal_year}`,
                        fiscalYear: d.period.fiscal_year,
                        value: d.revenue && d.operating_income ? (d.operating_income / d.revenue) * 100 : null,
                        isAnnual: d.period.period === 'FY'
                    })).reverse();
                }
                if (metricKey === 'net_margin') {
                    return sourceData.map(d => ({
                        period: `${d.period.period} ${d.period.fiscal_year}`,
                        fiscalYear: d.period.fiscal_year,
                        value: d.revenue && d.net_income ? (d.net_income / d.revenue) * 100 : null,
                        isAnnual: d.period.period === 'FY'
                    })).reverse();
                }
            } else if (['total_assets', 'current_assets', 'cash_and_equivalents', 'short_term_investments',
                        'receivables', 'inventory', 'property_plant_equipment', 'long_term_investments',
                        'total_investments', 'goodwill', 'intangible_assets', 'total_liabilities',
                        'current_liabilities', 'accounts_payable', 'short_term_debt', 'long_term_debt',
                        'deferred_revenue', 'total_equity', 'common_stock', 'retained_earnings',
                        'treasury_stock', 'total_debt', 'net_debt', 'working_capital', 'current_ratio',
                        'debt_to_equity'].includes(metricKey)) {
                sourceData = data.balance_sheets;
                
                // Calcular métricas derivadas
                if (metricKey === 'working_capital') {
                    return sourceData.map(d => ({
                        period: `${d.period.period} ${d.period.fiscal_year}`,
                        fiscalYear: d.period.fiscal_year,
                        value: d.current_assets && d.current_liabilities ? d.current_assets - d.current_liabilities : null,
                        isAnnual: d.period.period === 'FY'
                    })).reverse();
                }
                if (metricKey === 'current_ratio') {
                    return sourceData.map(d => ({
                        period: `${d.period.period} ${d.period.fiscal_year}`,
                        fiscalYear: d.period.fiscal_year,
                        value: d.current_assets && d.current_liabilities ? d.current_assets / d.current_liabilities : null,
                        isAnnual: d.period.period === 'FY'
                    })).reverse();
                }
                if (metricKey === 'debt_to_equity') {
                    return sourceData.map(d => ({
                        period: `${d.period.period} ${d.period.fiscal_year}`,
                        fiscalYear: d.period.fiscal_year,
                        value: d.total_debt && d.total_equity && d.total_equity !== 0 ? d.total_debt / d.total_equity : null,
                        isAnnual: d.period.period === 'FY'
                    })).reverse();
                }
            } else {
                sourceData = data.cash_flows;
                // Para cf_net_income usar net_income del cash flow
                if (metricKey === 'cf_net_income') key = 'net_income';
            }

            return sourceData.map(d => ({
                period: `${d.period.period} ${d.period.fiscal_year}`,
                fiscalYear: d.period.fiscal_year,
                value: (d as any)[key] ?? null,
                isAnnual: d.period.period === 'FY'
            })).reverse(); // Oldest first for proper chart display
        };

        const metricData = extractMetricData();
        const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
        const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;

        openWindow({
            title: `${selectedTicker} — ${label}`,
            content: (
                <FinancialMetricChart
                    ticker={selectedTicker}
                    metricKey={metricKey}
                    metricLabel={label}
                    data={metricData}
                    currency={data.currency}
                    valueType={valueType as any}
                    isNegativeBad={isNegativeBad}
                />
            ),
            width: FINANCIAL_METRIC_CHART_CONFIG.width,
            height: FINANCIAL_METRIC_CHART_CONFIG.height,
            x: Math.max(50, screenWidth / 2 - FINANCIAL_METRIC_CHART_CONFIG.width / 2),
            y: Math.max(80, screenHeight / 2 - FINANCIAL_METRIC_CHART_CONFIG.height / 2),
            minWidth: FINANCIAL_METRIC_CHART_CONFIG.minWidth,
            minHeight: FINANCIAL_METRIC_CHART_CONFIG.minHeight,
            maxWidth: FINANCIAL_METRIC_CHART_CONFIG.maxWidth,
            maxHeight: FINANCIAL_METRIC_CHART_CONFIG.maxHeight,
        });
    }, [data, selectedTicker, openWindow]);

    // Detectar industria basado en datos
    const industry = useMemo(() => {
        if (!data) return INDUSTRY_PROFILES.general;
        const type = detectIndustry(data);
        return INDUSTRY_PROFILES[type];
    }, [data]);

    const fetchData = useCallback(async (ticker: string, period: string = 'annual') => {
        setLoading(true);
        setError(null);

        try {
            const response = await fetch(`${API_URL}/api/v1/financials/${ticker}?period=${period}&limit=10`);

            if (!response.ok) {
                if (response.status === 404) {
                    throw new Error('Ticker not found');
                }
                throw new Error('Failed to fetch data');
            }

            const result = await response.json();
            setData(result);
            setSelectedTicker(ticker);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error loading data');
            setData(null);
        } finally {
            setLoading(false);
        }
    }, []);

    // Cargar datos automáticamente cuando hay initialTicker
    useEffect(() => {
        if (initialTicker && !data) {
            fetchData(initialTicker);
        }
    }, [initialTicker, fetchData, data]);

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        if (inputValue.trim()) {
            fetchData(inputValue.trim().toUpperCase());
        }
    };

    const handleRefresh = () => {
        if (selectedTicker) {
            fetchData(selectedTicker, periodFilter);
        }
    };

    const tabs: { id: TabType; label: string }[] = [
        { id: 'income', label: 'Income' },
        { id: 'balance', label: 'Balance' },
        { id: 'cashflow', label: 'Cash Flow' },
    ];

    return (
        <div className="h-full flex flex-col bg-white">
            {/* Search Bar */}
            <div className="px-2 py-1.5 border-b border-slate-300 bg-slate-50">
                <form onSubmit={handleSearch} className="flex items-center gap-1.5">
                    <TickerSearch
                        value={inputValue}
                        onChange={setInputValue}
                        onSelect={(ticker) => {
                            setInputValue(ticker.symbol);
                            fetchData(ticker.symbol);
                        }}
                        placeholder="Ticker"
                        className="w-24"
                        autoFocus={false}
                    />
                    <button
                        type="submit"
                        disabled={loading}
                        className="px-2 py-0.5 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-[10px] font-medium flex items-center gap-1"
                    >
                        {loading ? <RefreshCw className="w-3 h-3 animate-spin" /> : 'Go'}
                    </button>
                    {selectedTicker && (
                        <>
                            <button
                                type="button"
                                onClick={handleRefresh}
                                disabled={loading}
                                className="p-1 text-slate-400 hover:text-slate-600"
                                title="Refresh"
                            >
                                <RefreshCw className="w-3 h-3" />
                            </button>
                            <IndustryBadge industry={industry} />
                        </>
                    )}
                </form>
            </div>

            {/* Error */}
            {error && (
                <div className="mx-2 mt-1 px-2 py-1 bg-red-50 border border-red-200 rounded flex items-center gap-1.5 text-red-700">
                    <AlertTriangle className="w-3 h-3" />
                    <span className="text-[10px]">{error}</span>
                </div>
            )}

            {/* Content */}
            {selectedTicker && data ? (
                <div className="flex-1 flex flex-col min-h-0">
                    {/* Special Ratios for industry */}
                    <SpecialRatios data={data} industry={industry} />

                    {/* Tabs + Period Filter */}
                    <div className="flex items-center justify-between px-2 py-1 border-b border-slate-200 bg-slate-50">
                        <div className="flex gap-0.5">
                            {tabs.map(tab => (
                                <button
                                    key={tab.id}
                                    onClick={() => setActiveTab(tab.id)}
                                    className={`px-2 py-0.5 text-[10px] font-medium rounded transition-colors ${activeTab === tab.id
                                        ? 'bg-blue-600 text-white'
                                        : 'text-slate-600 hover:bg-slate-200'
                                        }`}
                                >
                                    {tab.label}
                                </button>
                            ))}
                        </div>
                        <div className="flex gap-0.5">
                            {(['annual', 'quarter'] as PeriodFilter[]).map(p => (
                                <button
                                    key={p}
                                    onClick={() => {
                                        setPeriodFilter(p);
                                        if (selectedTicker) {
                                            fetchData(selectedTicker, p);
                                        }
                                    }}
                                    className={`px-1.5 py-0.5 text-[9px] font-medium rounded ${periodFilter === p
                                        ? 'bg-slate-700 text-white'
                                        : 'text-slate-500 hover:bg-slate-200'
                                        }`}
                                >
                                    {p === 'annual' ? 'Annual' : 'Quarterly'}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Table Content */}
                    <div className="flex-1 overflow-auto p-2">
                        {activeTab === 'income' && (
                            <IncomeTable data={data.income_statements} periodFilter={periodFilter} industry={industry} onRowClick={handleMetricClick} />
                        )}
                        {activeTab === 'balance' && (
                            <BalanceTable data={data.balance_sheets} periodFilter={periodFilter} industry={industry} onRowClick={handleMetricClick} />
                        )}
                        {activeTab === 'cashflow' && (
                            <CashFlowTable data={data.cash_flows} periodFilter={periodFilter} industry={industry} onRowClick={handleMetricClick} />
                        )}
                    </div>

                    {/* Footer - Cache info */}
                    <div className="px-2 py-0.5 border-t border-slate-200 bg-slate-50 text-[8px] text-slate-400 flex justify-between">
                        <span>{data.currency}</span>
                        {data.cached ? (
                            <span>Cached {data.cache_age_seconds ? `${Math.round(data.cache_age_seconds / 60)}m ago` : ''}</span>
                        ) : (
                            <span>Fresh data</span>
                        )}
                    </div>
                </div>
            ) : (
                <div className="flex-1 flex items-center justify-center text-slate-400">
                    <div className="text-center">
                        <div className="text-2xl mb-2">FA</div>
                        <p className="text-[10px]">Enter ticker to view financials</p>
                    </div>
                </div>
            )}
        </div>
    );
}

