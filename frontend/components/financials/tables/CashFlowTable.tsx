'use client';

import type { CashFlow } from '../types';
import { formatCurrency, formatPeriod } from '../utils/formatters';

interface CashFlowTableProps {
    statements: CashFlow[];
    currency: string;
    onMetricClick: (metricKey: string, values: (number | undefined)[], periods: string[]) => void;
}

export function CashFlowTable({ statements, currency, onMetricClick }: CashFlowTableProps) {
    if (statements.length === 0) {
        return <div className="p-4 text-center text-slate-400 text-xs">No cash flow data</div>;
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
            const current = s[key as keyof CashFlow] as number | undefined;
            const previous = statements[idx + 1][key as keyof CashFlow] as number | undefined;
            return calcYoY(current, previous);
        });
    };

    const rows: Array<{
        key: string;
        label: string;
        isHeader?: boolean;
        isYoY?: boolean;
        isMargin?: boolean;
        indent?: number;
        parentKey?: string;
    }> = [
        // Operating Activities
        { key: 'operating_cash_flow', label: 'Operating Cash Flow', isHeader: true },
        { key: 'operating_cash_flow_yoy', label: '% YoY', isYoY: true, parentKey: 'operating_cash_flow' },
        { key: 'net_income', label: 'Net Income', indent: 1 },
        { key: 'depreciation', label: 'D&A', indent: 1 },
        { key: 'stock_compensation', label: 'Stock Compensation', indent: 1 },
        { key: 'change_working_capital', label: 'Δ Working Capital', indent: 1 },
        { key: 'change_receivables', label: 'Δ Receivables', indent: 2 },
        { key: 'change_inventory', label: 'Δ Inventory', indent: 2 },
        { key: 'change_payables', label: 'Δ Payables', indent: 2 },
        { key: 'other_operating', label: 'Other Operating', indent: 1 },
        // Investing Activities
        { key: 'investing_cash_flow', label: 'Investing Cash Flow', isHeader: true },
        { key: 'investing_cash_flow_yoy', label: '% YoY', isYoY: true, parentKey: 'investing_cash_flow' },
        { key: 'capex', label: 'CapEx', indent: 1 },
        { key: 'acquisitions', label: 'Acquisitions', indent: 1 },
        { key: 'purchases_investments', label: 'Purchases of Investments', indent: 1 },
        { key: 'sales_investments', label: 'Sales of Investments', indent: 1 },
        { key: 'other_investing', label: 'Other Investing', indent: 1 },
        // Financing Activities
        { key: 'financing_cash_flow', label: 'Financing Cash Flow', isHeader: true },
        { key: 'financing_cash_flow_yoy', label: '% YoY', isYoY: true, parentKey: 'financing_cash_flow' },
        { key: 'debt_issued', label: 'Debt Issued', indent: 1 },
        { key: 'debt_repaid', label: 'Debt Repaid', indent: 1 },
        { key: 'stock_issued', label: 'Stock Issued', indent: 1 },
        { key: 'stock_repurchased', label: 'Stock Repurchased', indent: 1 },
        { key: 'dividends_paid', label: 'Dividends Paid', indent: 1 },
        { key: 'other_financing', label: 'Other Financing', indent: 1 },
        // Summary
        { key: 'net_change_cash', label: 'Net Change in Cash', isHeader: true },
        { key: 'cash_beginning', label: 'Cash Beginning', indent: 1 },
        { key: 'cash_ending', label: 'Cash Ending', indent: 1 },
        // Key Metrics
        { key: 'free_cash_flow', label: 'Free Cash Flow', isHeader: true },
        { key: 'free_cash_flow_yoy', label: '% YoY', isYoY: true, parentKey: 'free_cash_flow' },
        { key: 'fcf_margin', label: '% FCF Margin', isMargin: true },
    ];

    const getRowValue = (statement: CashFlow, key: string): number | undefined => {
        // Calculate FCF margin if we have revenue (from income statement, but we don't have it here)
        // For now, just return the raw value
        return statement[key as keyof CashFlow] as number | undefined;
    };

    const hasData = (key: string): boolean => {
        if (key.endsWith('_yoy')) {
            const parentKey = key.replace('_yoy', '');
            return statements.some(s => getRowValue(s, parentKey) !== undefined);
        }
        if (key === 'fcf_margin') return false; // We need revenue for this
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
                                
                                // Margin formatting
                                if (row.isMargin) {
                                    return (
                                        <td key={idx} className="text-right p-2 text-amber-700 font-semibold">
                                            {value != null ? `${value.toFixed(1)}%` : '—'}
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
