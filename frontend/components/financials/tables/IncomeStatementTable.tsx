'use client';

import type { IncomeStatement } from '../types';
import { formatCurrency, formatPercent, formatPeriod } from '../utils/formatters';

interface IncomeStatementTableProps {
    statements: IncomeStatement[];
    currency: string;
    onMetricClick: (metricKey: string, values: (number | undefined)[], periods: string[]) => void;
}

export function IncomeStatementTable({ statements, currency, onMetricClick }: IncomeStatementTableProps) {
    if (statements.length === 0) {
        return <div className="p-4 text-center text-slate-400 text-xs">No income statement data</div>;
    }

    const periods = statements.map(s => formatPeriod(s.period));

    // Calculate YoY change for a metric
    const calcYoY = (current: number | undefined, previous: number | undefined): number | undefined => {
        if (current === undefined || previous === undefined || previous === 0) return undefined;
        return ((current - previous) / Math.abs(previous)) * 100;
    };

    // Get YoY values for a metric
    const getYoYValues = (key: string): (number | undefined)[] => {
        return statements.map((s, idx) => {
            if (idx === statements.length - 1) return undefined;
            const current = getRowValue(s, key);
            const previous = getRowValue(statements[idx + 1], key);
            return calcYoY(current, previous);
        });
    };

    const rows: Array<{
        key: string;
        label: string;
        isHeader?: boolean;
        isMargin?: boolean;
        isYoY?: boolean;
        indent?: number;
        parentKey?: string;
    }> = [
        { key: 'revenue', label: 'Revenue', isHeader: true },
        { key: 'revenue_yoy', label: '% YoY', isYoY: true, parentKey: 'revenue' },
        { key: 'cost_of_revenue', label: 'Cost of Revenue', indent: 1 },
        { key: 'gross_profit', label: 'Gross Profit', isHeader: true },
        { key: 'gross_profit_yoy', label: '% YoY', isYoY: true, parentKey: 'gross_profit' },
        { key: 'gross_margin', label: '% Margin', isMargin: true },
        { key: 'research_development', label: 'R&D Expenses', indent: 1 },
        { key: 'selling_general_admin', label: 'SG&A Expenses', indent: 1 },
        { key: 'operating_expenses', label: 'Total Operating Expenses', indent: 1 },
        { key: 'operating_income', label: 'Operating Income', isHeader: true },
        { key: 'operating_income_yoy', label: '% YoY', isYoY: true, parentKey: 'operating_income' },
        { key: 'operating_margin', label: '% Margin', isMargin: true },
        { key: 'interest_income', label: 'Interest Income', indent: 1 },
        { key: 'interest_expense', label: 'Interest Expense', indent: 1 },
        { key: 'net_interest_income', label: 'Net Interest Income', indent: 1 },
        { key: 'other_income_expense', label: 'Other Income/Expense', indent: 1 },
        { key: 'income_before_tax', label: 'Income Before Tax' },
        { key: 'income_tax', label: 'Income Tax', indent: 1 },
        { key: 'effective_tax_rate', label: '% Effective Tax Rate', isMargin: true },
        { key: 'net_income', label: 'Net Income', isHeader: true },
        { key: 'net_income_yoy', label: '% YoY', isYoY: true, parentKey: 'net_income' },
        { key: 'net_margin', label: '% Margin', isMargin: true },
        { key: 'eps', label: 'EPS Basic' },
        { key: 'eps_diluted', label: 'EPS Diluted' },
        { key: 'eps_diluted_yoy', label: '% YoY', isYoY: true, parentKey: 'eps_diluted' },
        { key: 'shares_outstanding', label: 'Shares Basic' },
        { key: 'shares_diluted', label: 'Shares Diluted' },
        { key: 'shares_diluted_yoy', label: '% YoY', isYoY: true, parentKey: 'shares_diluted' },
        { key: 'ebitda', label: 'EBITDA', isHeader: true },
        { key: 'ebitda_yoy', label: '% YoY', isYoY: true, parentKey: 'ebitda' },
        { key: 'ebit', label: 'EBIT' },
        { key: 'depreciation', label: 'D&A' },
    ];

    const getRowValue = (statement: IncomeStatement, key: string): number | undefined => {
        if (key === 'gross_margin' && statement.gross_profit && statement.revenue) {
            return (statement.gross_profit / statement.revenue) * 100;
        }
        if (key === 'operating_margin' && statement.operating_income && statement.revenue) {
            return (statement.operating_income / statement.revenue) * 100;
        }
        if (key === 'net_margin' && statement.net_income && statement.revenue) {
            return (statement.net_income / statement.revenue) * 100;
        }
        if (key === 'effective_tax_rate' && statement.income_tax && statement.income_before_tax) {
            return (Math.abs(statement.income_tax) / Math.abs(statement.income_before_tax)) * 100;
        }
        return statement[key as keyof IncomeStatement] as number | undefined;
    };

    const hasData = (key: string): boolean => {
        if (key.endsWith('_yoy')) {
            const parentKey = key.replace('_yoy', '');
            return statements.some(s => getRowValue(s, parentKey) !== undefined);
        }
        return statements.some(s => getRowValue(s, key) !== undefined);
    };

    return (
        <table className="w-full text-[10px] border-collapse">
            <thead>
                <tr className="bg-slate-100 border-b border-slate-200">
                    <th className="text-left p-2 font-semibold text-slate-700 sticky left-0 bg-slate-100 min-w-[160px]">
                        Metric
                    </th>
                    {periods.map((period, idx) => (
                        <th key={idx} className="text-right p-2 font-semibold text-slate-700 min-w-[80px]">
                            {period}
                        </th>
                    ))}
                </tr>
            </thead>
            <tbody>
                {rows.filter(row => hasData(row.key)).map((row) => {
                    let values: (number | undefined)[];
                    
                    if (row.isYoY && row.parentKey) {
                        values = getYoYValues(row.parentKey);
                    } else {
                        values = statements.map(s => getRowValue(s, row.key));
                    }

                    // Row background color
                    const rowBg = row.isHeader 
                        ? 'bg-slate-50' 
                        : row.isYoY 
                            ? 'bg-blue-50' 
                            : row.isMargin 
                                ? 'bg-amber-50' 
                                : 'bg-white';

                    return (
                        <tr
                            key={row.key}
                            className={`border-b border-slate-100 hover:bg-slate-100/50 cursor-pointer transition-colors ${rowBg}`}
                            onClick={() => !row.isYoY && !row.isMargin && onMetricClick(row.key, values, periods)}
                        >
                            <td 
                                className={`p-2 sticky left-0 ${rowBg} border-r border-slate-100
                                    ${row.isHeader ? 'font-bold text-slate-900' : ''}
                                    ${row.isYoY ? 'text-[9px] text-blue-700 font-medium pl-6' : ''}
                                    ${row.isMargin ? 'text-[9px] text-amber-700 font-medium pl-6' : ''}
                                    ${!row.isHeader && !row.isYoY && !row.isMargin ? 'text-slate-600' : ''}`}
                                style={{ paddingLeft: row.indent ? `${8 + row.indent * 16}px` : undefined }}
                            >
                                {row.label}
                            </td>
                            {values.map((value, idx) => {
                                // YoY formatting with colors
                                if (row.isYoY) {
                                    if (value === undefined || value === null) {
                                        return <td key={idx} className="text-right p-2 text-slate-300">—</td>;
                                    }
                                    const isPositive = value > 0;
                                    const isNegative = value < 0;
                                    return (
                                        <td 
                                            key={idx} 
                                            className={`text-right p-2 font-bold text-[10px]
                                                ${isPositive ? 'text-emerald-600' : ''}
                                                ${isNegative ? 'text-red-600' : ''}
                                                ${!isPositive && !isNegative ? 'text-slate-500' : ''}`}
                                        >
                                            {isPositive ? '+' : ''}{value.toFixed(1)}%
                                        </td>
                                    );
                                }
                                
                                // Margin formatting
                                if (row.isMargin) {
                                    return (
                                        <td key={idx} className="text-right p-2 text-amber-700 font-semibold">
                                            {value != null ? `${value.toFixed(1)}%` : '—'}
                                        </td>
                                    );
                                }

                                // Shares formatting
                                if (row.key.includes('shares')) {
                                    return (
                                        <td key={idx} className="text-right p-2 text-slate-600 tabular-nums">
                                            {value != null ? `${(value / 1_000_000).toFixed(0)}M` : '—'}
                                        </td>
                                    );
                                }

                                // EPS formatting
                                if (row.key.includes('eps')) {
                                    return (
                                        <td key={idx} className={`text-right p-2 font-medium tabular-nums
                                            ${value && value < 0 ? 'text-red-600' : 'text-slate-700'}`}>
                                            {value != null ? `$${value.toFixed(2)}` : '—'}
                                        </td>
                                    );
                                }

                                // Currency formatting (default)
                                return (
                                    <td 
                                        key={idx} 
                                        className={`text-right p-2 tabular-nums
                                            ${row.isHeader ? 'font-semibold text-slate-800' : 'text-slate-600'}
                                            ${value && value < 0 ? 'text-red-600' : ''}`}
                                    >
                                        {formatCurrency(value, currency)}
                                    </td>
                                );
                            })}
                        </tr>
                    );
                })}
            </tbody>
        </table>
    );
}
