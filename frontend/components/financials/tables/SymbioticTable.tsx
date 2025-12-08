'use client';

import React from 'react';
import { formatCurrency } from '../utils/formatters';

// ============================================================================
// TYPES - Nuevo formato simbiótico
// ============================================================================

interface ConsolidatedField {
    key: string;
    label: string;
    values: (number | null)[];
    importance: number;
    source_fields?: string[];
    data_type?: string;
    balance?: 'debit' | 'credit' | null;  // debit = outflow (rojo), credit = inflow
}

interface SymbioticTableProps {
    fields: ConsolidatedField[];
    periods: string[];
    category: 'income' | 'balance' | 'cashflow';
    currency: string;
    onMetricClick?: (metricKey: string, values: (number | null)[], periods: string[]) => void;
}

// ============================================================================
// UTILITIES
// ============================================================================

const formatValue = (value: number | null | undefined, currency: string = 'USD'): string => {
    if (value === undefined || value === null) return '—';
    return formatCurrency(value, currency);
};

const formatYoY = (current: number | null, previous: number | null): string => {
    if (current == null || previous == null || previous === 0) return '—';
    const change = ((current - previous) / Math.abs(previous)) * 100;
    if (!isFinite(change) || isNaN(change)) return '—';
    const sign = change > 0 ? '+' : '';
    return `${sign}${change.toFixed(1)}%`;
};

const formatMargin = (value: number | null, revenue: number | null): string => {
    if (value == null || revenue == null || revenue === 0) return '—';
    const margin = (value / revenue) * 100;
    return `${margin.toFixed(1)}%`;
};

// Detectar métricas clave por nombre
const isKeyMetric = (key: string): boolean => {
    const keyPatterns = ['revenue', 'gross_profit', 'operating_income', 'net_income',
        'total_assets', 'total_liabilities', 'equity',
        'operating_activities', 'cash_flow'];
    return keyPatterns.some(p => key.includes(p));
};

// Detectar métricas que necesitan margen
const needsMargin = (key: string): boolean => {
    return ['gross_profit', 'operating_income', 'net_income', 'profit'].some(p => key.includes(p));
};

// ============================================================================
// COMPONENT - Diseño compacto profesional
// ============================================================================

export function SymbioticTable({ fields, periods, category, currency, onMetricClick }: SymbioticTableProps) {
    if (!fields || fields.length === 0 || !periods || periods.length === 0) {
        return <div className="p-4 text-center text-slate-400 text-xs">No data available</div>;
    }

    // Obtener valores de revenue para calcular márgenes
    const revenueField = fields.find(f => f.key.includes('revenue') || f.key.includes('sales'));
    const revenueValues = revenueField?.values || [];

    const handleRowClick = (field: ConsolidatedField) => {
        if (onMetricClick) {
            onMetricClick(field.key, field.values, periods);
        }
    };

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-[10px] border-collapse">
                <thead className="sticky top-0 z-10 bg-white">
                    <tr className="border-b border-slate-200">
                        <th className="text-left p-1.5 font-medium text-slate-600 min-w-[120px]">
                            Metric
                        </th>
                        {periods.map((period, idx) => (
                            <th key={idx} className="text-right p-1.5 font-medium text-slate-600 min-w-[70px]">
                                {period.startsWith('Q') ? period : `FY${period}`}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody className="text-slate-700">
                    {fields.map((field) => {
                        const isKey = isKeyMetric(field.key);
                        const showMargin = category === 'income' && needsMargin(field.key);

                        return (
                            <React.Fragment key={field.key}>
                                {/* Main row */}
                                <tr
                                    className="hover:bg-slate-50 cursor-pointer border-b border-slate-100"
                                    onClick={() => handleRowClick(field)}
                                >
                                    <td className={`p-1.5 ${isKey ? 'font-medium text-slate-800' : 'text-slate-600 pl-3'}`}>
                                        {field.label}
                                    </td>
                                    {field.values.map((value, idx) => {
                                        // Determinar color:
                                        // - debit (outflow/gasto): rojo
                                        // - credit con valor negativo: rojo
                                        // - credit con valor positivo: normal
                                        const isDebit = field.balance === 'debit';
                                        const isNegative = value != null && value < 0;
                                        const showRed = isDebit || isNegative;

                                        return (
                                            <td
                                                key={idx}
                                                className={`text-right p-1.5 tabular-nums
                                                    ${showRed ? 'text-red-600' : ''}`}
                                            >
                                                {formatValue(value, currency)}
                                            </td>
                                        );
                                    })}
                                </tr>

                                {/* YoY row for key metrics */}
                                {isKey && (
                                    <tr className="border-b border-slate-50">
                                        <td className="p-1 pl-4 text-[9px] text-slate-400">% YoY</td>
                                        {field.values.map((value, idx) => (
                                            <td key={idx} className="text-right p-1 text-[9px] text-slate-500">
                                                {formatYoY(value, field.values[idx + 1])}
                                            </td>
                                        ))}
                                    </tr>
                                )}

                                {/* Margin row */}
                                {showMargin && (
                                    <tr className="border-b border-slate-50">
                                        <td className="p-1 pl-4 text-[9px] text-slate-400">% Margin</td>
                                        {field.values.map((value, idx) => (
                                            <td key={idx} className="text-right p-1 text-[9px] text-slate-500">
                                                {formatMargin(value, revenueValues[idx])}
                                            </td>
                                        ))}
                                    </tr>
                                )}
                            </React.Fragment>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}
