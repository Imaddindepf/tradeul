'use client';

import type { BalanceSheet } from '../types';
import { formatCurrency, formatPeriod } from '../utils/formatters';

interface BalanceSheetTableProps {
    statements: BalanceSheet[];
    currency: string;
    onMetricClick: (metricKey: string, values: (number | undefined)[], periods: string[]) => void;
}

export function BalanceSheetTable({ statements, currency, onMetricClick }: BalanceSheetTableProps) {
    if (statements.length === 0) {
        return <div className="p-4 text-center text-slate-400 text-xs">No balance sheet data</div>;
    }

    const periods = statements.map(s => formatPeriod(s.period));

    // Calculate YoY change
    const calcYoY = (current: number | undefined, previous: number | undefined): number | undefined => {
        if (current === undefined || previous === undefined || previous === 0) return undefined;
        return ((current - previous) / Math.abs(previous)) * 100;
    };

    const getYoYValues = (key: string): (number | undefined)[] => {
        return statements.map((s, idx) => {
            if (idx === statements.length - 1) return undefined;
            const current = s[key as keyof BalanceSheet] as number | undefined;
            const previous = statements[idx + 1][key as keyof BalanceSheet] as number | undefined;
            return calcYoY(current, previous);
        });
    };

    const rows: Array<{
        key: string;
        label: string;
        isHeader?: boolean;
        isYoY?: boolean;
        isRatio?: boolean;
        indent?: number;
        parentKey?: string;
    }> = [
            // Assets
            { key: 'total_assets', label: 'Total Assets', isHeader: true },
            { key: 'total_assets_yoy', label: '% YoY', isYoY: true, parentKey: 'total_assets' },
            { key: 'current_assets', label: 'Current Assets', isHeader: true },
            { key: 'cash_and_equivalents', label: 'Cash & Equivalents', indent: 1 },
            { key: 'short_term_investments', label: 'Short-term Investments', indent: 1 },
            { key: 'cash_and_short_term', label: 'Cash & Short-term', indent: 1 },
            { key: 'receivables', label: 'Receivables', indent: 1 },
            { key: 'inventory', label: 'Inventory', indent: 1 },
            { key: 'other_current_assets', label: 'Other Current Assets', indent: 1 },
            { key: 'noncurrent_assets', label: 'Non-Current Assets', isHeader: true },
            { key: 'property_plant_equipment', label: 'PP&E', indent: 1 },
            { key: 'goodwill', label: 'Goodwill', indent: 1 },
            { key: 'intangible_assets', label: 'Intangible Assets', indent: 1 },
            { key: 'long_term_investments', label: 'Long-term Investments', indent: 1 },
            { key: 'other_noncurrent_assets', label: 'Other Non-Current', indent: 1 },
            // Liabilities
            { key: 'total_liabilities', label: 'Total Liabilities', isHeader: true },
            { key: 'total_liabilities_yoy', label: '% YoY', isYoY: true, parentKey: 'total_liabilities' },
            { key: 'current_liabilities', label: 'Current Liabilities', isHeader: true },
            { key: 'accounts_payable', label: 'Accounts Payable', indent: 1 },
            { key: 'short_term_debt', label: 'Short-term Debt', indent: 1 },
            { key: 'deferred_revenue', label: 'Deferred Revenue', indent: 1 },
            { key: 'other_current_liabilities', label: 'Other Current Liab.', indent: 1 },
            { key: 'noncurrent_liabilities', label: 'Non-Current Liabilities', isHeader: true },
            { key: 'long_term_debt', label: 'Long-term Debt', indent: 1 },
            { key: 'other_noncurrent_liabilities', label: 'Other Non-Current Liab.', indent: 1 },
            // Equity
            { key: 'total_equity', label: 'Total Equity', isHeader: true },
            { key: 'total_equity_yoy', label: '% YoY', isYoY: true, parentKey: 'total_equity' },
            { key: 'common_stock', label: 'Common Stock', indent: 1 },
            { key: 'retained_earnings', label: 'Retained Earnings', indent: 1 },
            { key: 'treasury_stock', label: 'Treasury Stock', indent: 1 },
            { key: 'accumulated_other_income', label: 'Accum. Other Income', indent: 1 },
            // Metrics
            { key: 'total_debt', label: 'Total Debt', isHeader: true },
            { key: 'net_debt', label: 'Net Debt' },
            { key: 'total_investments', label: 'Total Investments' },
            // Ratios
            { key: 'debt_to_equity', label: 'Debt/Equity Ratio', isRatio: true },
            { key: 'current_ratio', label: 'Current Ratio', isRatio: true },
        ];

    const getRowValue = (statement: BalanceSheet, key: string): number | undefined => {
        // Calculate ratios
        if (key === 'debt_to_equity' && statement.total_debt && statement.total_equity) {
            return statement.total_debt / statement.total_equity;
        }
        if (key === 'current_ratio' && statement.current_assets && statement.current_liabilities) {
            return statement.current_assets / statement.current_liabilities;
        }
        return statement[key as keyof BalanceSheet] as number | undefined;
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

                    const rowBg = row.isHeader
                        ? 'bg-slate-50'
                        : row.isYoY
                            ? 'bg-blue-50'
                            : row.isRatio
                                ? 'bg-purple-50'
                                : 'bg-white';

                    return (
                        <tr
                            key={row.key}
                            className={`border-b border-slate-100 hover:bg-slate-100/50 cursor-pointer transition-colors ${rowBg}`}
                            onClick={() => !row.isYoY && !row.isRatio && onMetricClick(row.key, values, periods)}
                        >
                            <td
                                className={`p-2 sticky left-0 ${rowBg} border-r border-slate-100
                                    ${row.isHeader ? 'font-bold text-slate-900' : ''}
                                    ${row.isYoY ? 'text-[9px] text-blue-700 font-medium pl-6' : ''}
                                    ${row.isRatio ? 'text-[9px] text-purple-700 font-medium' : ''}
                                    ${!row.isHeader && !row.isYoY && !row.isRatio ? 'text-slate-600' : ''}`}
                                style={{ paddingLeft: row.indent ? `${8 + row.indent * 16}px` : undefined }}
                            >
                                {row.label}
                            </td>
                            {values.map((value, idx) => {
                                // YoY formatting
                                if (row.isYoY) {
                                    if (value == null) {
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

                                // Ratio formatting
                                if (row.isRatio) {
                                    return (
                                        <td key={idx} className="text-right p-2 text-purple-700 font-semibold">
                                            {value != null ? value.toFixed(2) : '—'}
                                        </td>
                                    );
                                }

                                // Currency formatting
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
