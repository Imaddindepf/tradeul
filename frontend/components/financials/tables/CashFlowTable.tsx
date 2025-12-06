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

    const rows: Array<{
        key: keyof CashFlow;
        label: string;
        isHeader?: boolean;
        indent?: number;
    }> = [
        // Operating Activities
        { key: 'operating_cash_flow', label: 'Operating Cash Flow', isHeader: true },
        { key: 'net_income', label: 'Net Income', indent: 1 },
        { key: 'depreciation', label: 'Depreciation & Amortization', indent: 1 },
        { key: 'stock_compensation', label: 'Stock-Based Compensation', indent: 1 },
        { key: 'change_working_capital', label: 'Change in Working Capital', indent: 1 },
        { key: 'change_receivables', label: 'Change in Receivables', indent: 2 },
        { key: 'change_inventory', label: 'Change in Inventory', indent: 2 },
        { key: 'change_payables', label: 'Change in Payables', indent: 2 },
        { key: 'other_operating', label: 'Other Operating Activities', indent: 1 },
        // Investing Activities
        { key: 'investing_cash_flow', label: 'Investing Cash Flow', isHeader: true },
        { key: 'capex', label: 'Capital Expenditures', indent: 1 },
        { key: 'acquisitions', label: 'Acquisitions', indent: 1 },
        { key: 'purchases_investments', label: 'Purchases of Investments', indent: 1 },
        { key: 'sales_investments', label: 'Sales of Investments', indent: 1 },
        { key: 'other_investing', label: 'Other Investing Activities', indent: 1 },
        // Financing Activities
        { key: 'financing_cash_flow', label: 'Financing Cash Flow', isHeader: true },
        { key: 'debt_issued', label: 'Debt Issued', indent: 1 },
        { key: 'debt_repaid', label: 'Debt Repaid', indent: 1 },
        { key: 'stock_issued', label: 'Stock Issued', indent: 1 },
        { key: 'stock_repurchased', label: 'Stock Repurchased', indent: 1 },
        { key: 'dividends_paid', label: 'Dividends Paid', indent: 1 },
        { key: 'other_financing', label: 'Other Financing Activities', indent: 1 },
        // Summary
        { key: 'net_change_cash', label: 'Net Change in Cash', isHeader: true },
        { key: 'cash_beginning', label: 'Cash at Beginning', indent: 1 },
        { key: 'cash_ending', label: 'Cash at End', indent: 1 },
        { key: 'free_cash_flow', label: 'Free Cash Flow', isHeader: true },
    ];

    const getRowValue = (statement: CashFlow, key: string): number | undefined => {
        return statement[key as keyof CashFlow] as number | undefined;
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
                                <td key={idx} className={`text-right p-1.5 tabular-nums text-slate-700
                                    ${value && value < 0 ? 'text-red-600' : ''}`}
                                >
                                    {formatCurrency(value, currency)}
                                </td>
                            ))}
                        </tr>
                    );
                })}
            </tbody>
        </table>
    );
}

