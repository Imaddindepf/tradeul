'use client';

import React, { useMemo } from 'react';
import { formatCurrency } from '../utils/formatters';

// ============================================================================
// TYPES - Formato profesional institucional
// ============================================================================

interface ConsolidatedField {
    key: string;
    label: string;
    values: (number | null)[];
    importance: number;
    source_fields?: string[];
    data_type?: string;
    balance?: 'debit' | 'credit' | null;
    calculated?: boolean;
    // Nuevos campos de estructura
    section?: string;
    display_order?: number;
    indent_level?: number;
    is_subtotal?: boolean;
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

const formatValue = (
    value: number | null | undefined, 
    dataType?: string,
    currency: string = 'USD'
): string => {
    if (value === undefined || value === null) return '—';
    
    // Formatear según el tipo de dato
    if (dataType === 'percent') {
        return `${(value * 100).toFixed(1)}%`;
    }
    if (dataType === 'perShare') {
        return `$${value.toFixed(2)}`;
    }
    if (dataType === 'shares') {
        // Mostrar en billones (B)
        if (Math.abs(value) >= 1e9) {
            return `${(value / 1e9).toFixed(2)}B`;
        }
        if (Math.abs(value) >= 1e6) {
            return `${(value / 1e6).toFixed(1)}M`;
        }
        return value.toLocaleString();
    }
    
    return formatCurrency(value, currency);
};

// Agrupar campos por sección
const groupBySection = (fields: ConsolidatedField[]): Map<string, ConsolidatedField[]> => {
    const groups = new Map<string, ConsolidatedField[]>();
    
    fields.forEach(field => {
        const section = field.section || 'Other';
        if (!groups.has(section)) {
            groups.set(section, []);
        }
        groups.get(section)!.push(field);
    });
    
    return groups;
};

// Orden de secciones para Income Statement
const SECTION_ORDER: Record<string, number> = {
    'Revenue': 1,
    'Cost & Gross Profit': 2,
    'Operating Expenses': 3,
    'Operating Income': 4,
    'Non-Operating': 5,
    'Earnings': 6,
    'Per Share Data': 7,
    // Balance Sheet
    'Current Assets': 1,
    'Non-Current Assets': 2,
    'Current Liabilities': 3,
    'Non-Current Liabilities': 4,
    'Equity': 5,
    // Cash Flow
    'Operating Activities': 1,
    'Investing Activities': 2,
    'Financing Activities': 3,
    'Other': 99,
};

// ============================================================================
// COMPONENT - Diseño institucional profesional
// ============================================================================

export function SymbioticTable({ fields, periods, category, currency, onMetricClick }: SymbioticTableProps) {
    if (!fields || fields.length === 0 || !periods || periods.length === 0) {
        return <div className="p-4 text-center text-slate-400 text-xs">No data available</div>;
    }

    // Agrupar campos por sección
    const groupedFields = useMemo(() => {
        const groups = groupBySection(fields);
        // Ordenar secciones
        const sortedSections = Array.from(groups.keys()).sort(
            (a, b) => (SECTION_ORDER[a] || 99) - (SECTION_ORDER[b] || 99)
        );
        return { groups, sortedSections };
    }, [fields]);

    const handleRowClick = (field: ConsolidatedField) => {
        if (onMetricClick) {
            onMetricClick(field.key, field.values, periods);
        }
    };

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-[11px] border-collapse">
                {/* Header */}
                <thead className="sticky top-0 z-10">
                    <tr className="bg-slate-50 border-b-2 border-slate-200">
                        <th className="text-left p-2 font-semibold text-slate-700 min-w-[180px] bg-slate-50">
                            Metric
                        </th>
                        {periods.map((period, idx) => (
                            <th 
                                key={idx} 
                                className="text-right p-2 font-semibold text-slate-700 min-w-[85px] bg-slate-50"
                            >
                                {period.startsWith('Q') ? period : `FY${period}`}
                            </th>
                        ))}
                    </tr>
                </thead>
                
                <tbody className="text-slate-700">
                    {groupedFields.sortedSections.map((section, sectionIdx) => {
                        const sectionFields = groupedFields.groups.get(section) || [];
                        
                        // No mostrar sección "Other" si está vacía o tiene solo campos de baja importancia
                        if (section === 'Other' && sectionFields.every(f => (f.importance || 0) < 100)) {
                            return null;
                        }
                        
                        return (
                            <React.Fragment key={section}>
                                {/* Section Header */}
                                <tr className="bg-slate-100/50">
                                    <td 
                                        colSpan={periods.length + 1}
                                        className="px-2 py-1.5 font-semibold text-[10px] uppercase tracking-wider text-slate-500 border-t border-slate-200"
                                    >
                                        {section}
                                    </td>
                                </tr>
                                
                                {/* Section Fields */}
                                {sectionFields.map((field) => {
                                    const indent = field.indent_level || 0;
                                    const isSubtotal = field.is_subtotal || false;
                                    const isPercentOrYoy = field.data_type === 'percent' || 
                                                          field.key.includes('_yoy') || 
                                                          field.key.includes('_margin');
                                    
                                    // Determinar estilo de la fila
                                    const rowClass = isSubtotal 
                                        ? 'bg-slate-50/80 border-t border-slate-200' 
                                        : isPercentOrYoy
                                            ? 'bg-white'
                                            : 'bg-white hover:bg-blue-50/30';
                                    
                                    return (
                                        <tr
                                            key={field.key}
                                            className={`${rowClass} cursor-pointer border-b border-slate-100 transition-colors`}
                                            onClick={() => handleRowClick(field)}
                                        >
                                            {/* Label con indentación */}
                                            <td 
                                                className={`p-2 ${
                                                    isSubtotal 
                                                        ? 'font-semibold text-slate-800' 
                                                        : isPercentOrYoy
                                                            ? 'text-slate-400 text-[10px] italic'
                                                            : 'text-slate-600'
                                                }`}
                                                style={{ paddingLeft: `${8 + indent * 16}px` }}
                                            >
                                                {isPercentOrYoy && !isSubtotal && (
                                                    <span className="text-slate-300 mr-1">└</span>
                                                )}
                                                {field.label}
                                            </td>
                                            
                                            {/* Values */}
                                            {field.values.map((value, idx) => {
                                                // Determinar color
                                                const isDebit = field.balance === 'debit';
                                                const isNegative = value != null && value < 0;
                                                const isPositivePercent = field.data_type === 'percent' && 
                                                                         value != null && value > 0 &&
                                                                         field.key.includes('_yoy');
                                                const isNegativePercent = field.data_type === 'percent' && 
                                                                         value != null && value < 0;
                                                
                                                let textColor = '';
                                                if (isDebit || isNegative) {
                                                    textColor = 'text-red-600';
                                                } else if (isPositivePercent) {
                                                    textColor = 'text-emerald-600';
                                                } else if (isNegativePercent) {
                                                    textColor = 'text-red-500';
                                                }
                                                
                                                return (
                                                    <td
                                                        key={idx}
                                                        className={`text-right p-2 tabular-nums ${textColor} ${
                                                            isSubtotal ? 'font-semibold' : ''
                                                        } ${isPercentOrYoy ? 'text-[10px]' : ''}`}
                                                    >
                                                        {formatValue(value, field.data_type, currency)}
                                                    </td>
                                                );
                                            })}
                                        </tr>
                                    );
                                })}
                            </React.Fragment>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}
