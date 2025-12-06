'use client';

import type { BalanceSheet } from '../types';
import { formatCurrency, formatRatio, formatPeriod } from '../utils/formatters';

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

    const rows: Array<{
        key: keyof BalanceSheet | 'current_ratio' | 'debt_to_equity';
        label: string;
        isHeader?: boolean;
        isCalculated?: boolean;
        indent?: number;
    }> = [
        // Assets
        { key: 'total_assets', label: 'Total Assets', isHeader: true },
        { key: 'current_assets', label: 'Current Assets', isHeader: true },
        { key: 'cash_and_equivalents', label: 'Cash & Equivalents', indent: 1 },
        { key: 'short_term_investments', label: 'Short-term Investments', indent: 1 },
        { key: 'cash_and_short_term', label: 'Cash & Short-term Total', indent: 1 },
        { key: 'receivables', label: 'Accounts Receivable', indent: 1 },
        { key: 'inventory', label: 'Inventory', indent: 1 },
        { key: 'other_current_assets', label: 'Other Current Assets', indent: 1 },
        { key: 'noncurrent_assets', label: 'Non-Current Assets', isHeader: true },
        { key: 'property_plant_equipment', label: 'PP&E (Net)', indent: 1 },
        { key: 'goodwill', label: 'Goodwill', indent: 1 },
        { key: 'intangible_assets', label: 'Intangible Assets', indent: 1 },
        { key: 'long_term_investments', label: 'Long-term Investments', indent: 1 },
        { key: 'other_noncurrent_assets', label: 'Other Non-Current Assets', indent: 1 },
        // Liabilities
        { key: 'total_liabilities', label: 'Total Liabilities', isHeader: true },
        { key: 'current_liabilities', label: 'Current Liabilities', isHeader: true },
        { key: 'accounts_payable', label: 'Accounts Payable', indent: 1 },
        { key: 'short_term_debt', label: 'Short-term Debt', indent: 1 },
        { key: 'deferred_revenue', label: 'Deferred Revenue', indent: 1 },
        { key: 'other_current_liabilities', label: 'Other Current Liabilities', indent: 1 },
        { key: 'noncurrent_liabilities', label: 'Non-Current Liabilities', isHeader: true },
        { key: 'long_term_debt', label: 'Long-term Debt', indent: 1 },
        { key: 'other_noncurrent_liabilities', label: 'Other Non-Current Liabilities', indent: 1 },
        // Equity
        { key: 'total_equity', label: 'Total Equity', isHeader: true },
        { key: 'common_stock', label: 'Common Stock', indent: 1 },
        { key: 'retained_earnings', label: 'Retained Earnings', indent: 1 },
        { key: 'treasury_stock', label: 'Treasury Stock', indent: 1 },
        { key: 'accumulated_other_income', label: 'Accumulated Other Income', indent: 1 },
        // Key Metrics
        { key: 'total_debt', label: 'Total Debt' },
        { key: 'net_debt', label: 'Net Debt' },
        { key: 'total_investments', label: 'Total Investments' },
        // Calculated Ratios
        { key: 'current_ratio', label: 'Current Ratio', isCalculated: true },
        { key: 'debt_to_equity', label: 'Debt/Equity Ratio', isCalculated: true },
    ];

    const getRowValue = (statement: BalanceSheet, key: string): number | undefined => {
        if (key === 'current_ratio' && statement.current_assets && statement.current_liabilities) {
            return statement.current_assets / statement.current_liabilities;
        }
        if (key === 'debt_to_equity' && statement.total_debt && statement.total_equity) {
            return statement.total_debt / statement.total_equity;
        }
        return statement[key as keyof BalanceSheet] as number | undefined;
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
                                        ? formatRatio(value)
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

