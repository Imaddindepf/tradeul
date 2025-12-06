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

    const rows: Array<{
        key: keyof IncomeStatement | 'gross_margin' | 'operating_margin' | 'net_margin';
        label: string;
        isHeader?: boolean;
        isCalculated?: boolean;
        indent?: number;
    }> = [
        { key: 'revenue', label: 'Revenue', isHeader: true },
        { key: 'cost_of_revenue', label: 'Cost of Revenue', indent: 1 },
        { key: 'gross_profit', label: 'Gross Profit', isHeader: true },
        { key: 'gross_margin', label: 'Gross Margin %', isCalculated: true, indent: 1 },
        { key: 'research_development', label: 'R&D Expenses', indent: 1 },
        { key: 'selling_general_admin', label: 'SG&A Expenses', indent: 1 },
        { key: 'operating_expenses', label: 'Total Operating Expenses' },
        { key: 'operating_income', label: 'Operating Income', isHeader: true },
        { key: 'operating_margin', label: 'Operating Margin %', isCalculated: true, indent: 1 },
        { key: 'interest_income', label: 'Interest Income', indent: 1 },
        { key: 'interest_expense', label: 'Interest Expense', indent: 1 },
        { key: 'net_interest_income', label: 'Net Interest Income', indent: 1 },
        { key: 'other_income_expense', label: 'Other Income/Expense', indent: 1 },
        { key: 'income_before_tax', label: 'Income Before Tax' },
        { key: 'income_tax', label: 'Income Tax', indent: 1 },
        { key: 'net_income', label: 'Net Income', isHeader: true },
        { key: 'net_margin', label: 'Net Margin %', isCalculated: true, indent: 1 },
        { key: 'eps', label: 'EPS (Basic)' },
        { key: 'eps_diluted', label: 'EPS (Diluted)' },
        { key: 'shares_outstanding', label: 'Shares Outstanding' },
        { key: 'shares_diluted', label: 'Shares Diluted' },
        { key: 'ebitda', label: 'EBITDA', isHeader: true },
        { key: 'ebit', label: 'EBIT' },
        { key: 'depreciation', label: 'Depreciation & Amortization' },
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
        return statement[key as keyof IncomeStatement] as number | undefined;
    };

    const hasData = (key: string): boolean => {
        return statements.some(s => getRowValue(s, key) !== undefined);
    };

    return (
        <table className="w-full text-[10px]">
            <thead>
                <tr className="bg-slate-50">
                    <th className="text-left p-1.5 font-medium text-slate-600 sticky left-0 bg-slate-50">Metric</th>
                    {periods.map((period, idx) => (
                        <th key={idx} className="text-right p-1.5 font-medium text-slate-600 min-w-[80px]">{period}</th>
                    ))}
                </tr>
            </thead>
            <tbody>
                {rows.filter(row => hasData(row.key)).map((row) => {
                    const values = statements.map(s => getRowValue(s, row.key));
                    return (
                        <tr
                            key={row.key}
                            className={`border-b border-slate-50 hover:bg-slate-50 cursor-pointer
                                ${row.isHeader ? 'bg-slate-25 font-medium' : ''}`}
                            onClick={() => onMetricClick(row.key, values, periods)}
                        >
                            <td className={`p-1.5 text-slate-700 sticky left-0 bg-white
                                ${row.isHeader ? 'font-medium' : ''}`}
                                style={{ paddingLeft: row.indent ? `${row.indent * 12}px` : undefined }}
                            >
                                {row.label}
                            </td>
                            {values.map((value, idx) => (
                                <td key={idx} className={`text-right p-1.5 tabular-nums
                                    ${row.isCalculated ? 'text-blue-600' : 'text-slate-700'}
                                    ${value && value < 0 ? 'text-red-600' : ''}`}
                                >
                                    {row.isCalculated
                                        ? formatPercent(value)
                                        : row.key.includes('shares') || row.key.includes('eps')
                                            ? (value?.toLocaleString() ?? '—')
                                            : formatCurrency(value, currency)}
                                </td>
                            ))}
                        </tr>
                    );
                })}
            </tbody>
        </table>
    );
}

