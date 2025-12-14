'use client';

import React, { useMemo, useState } from 'react';

// Display unit type for toggle
type DisplayUnit = 'thousands' | 'millions' | 'billions';

// ============================================================================
// TYPES - Formato profesional institucional (estilo TIKR/Bloomberg)
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
    section?: string;
    display_order?: number;
    indent_level?: number;
    is_subtotal?: boolean;
    is_industry_specific?: boolean;  // Campo específico de industria
}

interface SymbioticTableProps {
    fields: ConsolidatedField[];
    periods: string[];
    category: 'income' | 'balance' | 'cashflow';
    currency: string;
    onMetricClick?: (metricKey: string, values: (number | null)[], periods: string[]) => void;
}

// ============================================================================
// UTILITIES - Formateo profesional estilo TIKR
// ============================================================================

/**
 * Formatear valor monetario al estilo profesional
 * - Negativos entre paréntesis: (28.16B) en lugar de -$28.16B
 * - Billones con B, Millones con M
 * - displayUnit: 'auto' (default), 'millions', 'billions'
 */
const formatValue = (
    value: number | null | undefined, 
    dataType?: string,
    isDebitField?: boolean,
    displayUnit: DisplayUnit = 'auto'
): string => {
    if (value === undefined || value === null) return '—';
    
    // Porcentajes
    if (dataType === 'percent') {
        const pct = value * 100;
        if (pct < 0) {
            return `(${Math.abs(pct).toFixed(1)}%)`;
        }
        return `${pct.toFixed(1)}%`;
    }
    
    // Per share
    if (dataType === 'perShare') {
        if (value < 0) {
            return `($${Math.abs(value).toFixed(2)})`;
        }
        return `$${value.toFixed(2)}`;
    }
    
    // Shares (en billones/millones)
    if (dataType === 'shares') {
        if (Math.abs(value) >= 1e9) {
            return `${(value / 1e9).toFixed(2)}B`;
        }
        if (Math.abs(value) >= 1e6) {
            return `${(value / 1e6).toFixed(1)}M`;
        }
        return value.toLocaleString();
    }
    
    // Monetario - formato profesional con paréntesis para negativos
    const absValue = Math.abs(value);
    let formatted: string;
    
    // Forzar unidad de visualización
    if (displayUnit === 'thousands') {
        // Mostrar todo en miles (K)
        formatted = `${(absValue / 1e3).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
    } else if (displayUnit === 'millions') {
        // Mostrar todo en millones (MM)
        formatted = `${(absValue / 1e6).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    } else {
        // Billions (B)
        formatted = `${(absValue / 1e9).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }
    
    // Negativos entre paréntesis (estilo TIKR/contable)
    if (value < 0) {
        return `(${formatted})`;
    }
    
    return formatted;
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

// Orden de secciones - TIKR style + Industry-specific sections
const SECTION_ORDER: Record<string, number> = {
    // ============================================
    // INCOME STATEMENT - Standard
    // ============================================
    'Revenue': 1,
    'Cost & Gross Profit': 2,
    'Operating Expenses': 3,
    'Operating Income': 4,
    'Non-Operating': 5,
    'Earnings': 6,
    'Per Share Data': 7,
    
    // ============================================
    // INCOME STATEMENT - Insurance Industry
    // ============================================
    'Insurance Revenue': 1,      // Premiums, etc.
    'Insurance Costs': 2,        // Benefits, Claims
    
    // ============================================
    // INCOME STATEMENT - Banking Industry  
    // ============================================
    'Net Interest Income': 1,    // Interest income - expense
    'Credit Provisions': 2,      // Loan loss provisions
    'Non-Interest Income': 3,    // Fees, trading, etc.
    'Non-Interest Expense': 4,   // Operating costs
    
    // ============================================
    // INCOME STATEMENT - Real Estate Industry
    // ============================================
    'Rental Revenue': 1,
    'Property Expenses': 2,
    'FFO': 5,                    // Funds from Operations
    
    // ============================================
    // BALANCE SHEET - Standard
    // ============================================
    'Current Assets': 1,
    'Non-Current Assets': 2,
    'Current Liabilities': 3,
    'Non-Current Liabilities': 4,
    'Equity': 5,
    
    // ============================================
    // BALANCE SHEET - Industry Specific
    // ============================================
    'Insurance Assets': 1,
    'Insurance Liabilities': 3,
    'Banking Assets': 1,
    'Banking Liabilities': 3,
    
    // ============================================
    // CASH FLOW - Standard
    // ============================================
    'Operating Activities': 1,
    'Investing Activities': 2,
    'Financing Activities': 3,
    'Free Cash Flow': 4,
    
    // Hidden
    'Other': 999,
};

// Secciones a ocultar (campos técnicos no útiles para análisis)
const HIDDEN_SECTIONS = ['Other'];

// Secciones específicas de industria (para highlighting)
const INDUSTRY_SECTIONS = new Set([
    'Insurance Revenue', 'Insurance Costs', 'Insurance Assets', 'Insurance Liabilities',
    'Net Interest Income', 'Credit Provisions', 'Non-Interest Income', 'Non-Interest Expense',
    'Banking Assets', 'Banking Liabilities',
    'Rental Revenue', 'Property Expenses', 'FFO',
]);

// ============================================================================
// COMPONENT - Diseño institucional profesional (estilo TIKR)
// ============================================================================

export function SymbioticTable({ fields, periods, category, currency, onMetricClick }: SymbioticTableProps) {
    // Estado para controlar la unidad de visualización (K/MM/B)
    const [displayUnit, setDisplayUnit] = useState<DisplayUnit>('millions');

    if (!fields || fields.length === 0 || !periods || periods.length === 0) {
        return <div className="p-4 text-center text-slate-400 text-xs">No data available</div>;
    }

    // Agrupar campos por sección y filtrar secciones ocultas
    const groupedFields = useMemo(() => {
        const groups = groupBySection(fields);
        
        // Filtrar secciones ocultas
        HIDDEN_SECTIONS.forEach(section => groups.delete(section));
        
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

    // Obtener rango de fechas de los períodos
    const dateRange = useMemo(() => {
        if (!periods || periods.length === 0) return { from: '', to: '' };
        const sorted = [...periods].sort();
        return { from: sorted[sorted.length - 1], to: sorted[0] };
    }, [periods]);

    // Label de unidad para el texto informativo
    const unitText = displayUnit === 'thousands' ? 'Thousands' : displayUnit === 'millions' ? 'Millions' : 'Billions';

    return (
        <div className="overflow-x-auto bg-white">
            {/* Header con toggle de unidad */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200 bg-slate-50">
                {/* Texto informativo */}
                <span className="text-[10px] text-slate-500">
                    * Annual Financials in {unitText} of {currency} from {dateRange.from} to {dateRange.to}
                </span>
                
                {/* Toggle K | MM | B */}
                <div className="flex items-center gap-2">
                    <span className="text-[10px] text-slate-500">Display Units</span>
                    <div className="flex rounded border border-slate-300 overflow-hidden">
                        <button
                            onClick={() => setDisplayUnit('thousands')}
                            className={`px-3 py-1 text-[10px] font-medium transition-colors ${
                                displayUnit === 'thousands'
                                    ? 'bg-blue-500 text-white'
                                    : 'bg-white text-slate-600 hover:bg-slate-100'
                            }`}
                        >
                            K
                        </button>
                        <button
                            onClick={() => setDisplayUnit('millions')}
                            className={`px-3 py-1 text-[10px] font-medium border-x border-slate-300 transition-colors ${
                                displayUnit === 'millions'
                                    ? 'bg-blue-500 text-white'
                                    : 'bg-white text-slate-600 hover:bg-slate-100'
                            }`}
                        >
                            MM
                        </button>
                        <button
                            onClick={() => setDisplayUnit('billions')}
                            className={`px-3 py-1 text-[10px] font-medium transition-colors ${
                                displayUnit === 'billions'
                                    ? 'bg-blue-500 text-white'
                                    : 'bg-white text-slate-600 hover:bg-slate-100'
                            }`}
                        >
                            B
                        </button>
                    </div>
                </div>
            </div>
            <table className="w-full text-[11px] border-collapse">
                {/* Header */}
                <thead className="sticky top-0 z-10">
                    <tr className="bg-slate-100 border-b-2 border-slate-300">
                        <th className="text-left py-2.5 px-3 font-semibold text-slate-700 min-w-[200px] bg-slate-100">
                            Metric
                        </th>
                        {periods.map((period, idx) => (
                            <th 
                                key={idx} 
                                className="text-right py-2.5 px-3 font-semibold text-slate-700 min-w-[90px] bg-slate-100"
                            >
                                {period.startsWith('Q') ? period : `FY${period}`}
                            </th>
                        ))}
                    </tr>
                </thead>
                
                <tbody className="text-slate-700">
                    {groupedFields.sortedSections.map((section, sectionIdx) => {
                        const sectionFields = groupedFields.groups.get(section) || [];
                        
                        return (
                            <React.Fragment key={section}>
                                {/* Section Header - Espaciado superior */}
                                <tr>
                                    <td colSpan={periods.length + 1} className="h-3 bg-white"></td>
                                </tr>
                                <tr className="border-y border-slate-200 bg-slate-50">
                                    <td 
                                        colSpan={periods.length + 1}
                                        className="py-2 px-3 font-bold text-[11px] uppercase tracking-wide text-slate-600"
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
                                    const isDebit = field.balance === 'debit';
                                    
                                    return (
                                        <tr
                                            key={field.key}
                                            className={`
                                                border-b border-slate-100 
                                                ${isSubtotal ? 'bg-slate-50/70' : 'bg-white'} 
                                                ${!isPercentOrYoy ? 'hover:bg-blue-50/40 cursor-pointer' : ''}
                                                transition-colors
                                            `}
                                            onClick={() => !isPercentOrYoy && handleRowClick(field)}
                                        >
                                            {/* Label */}
                                            <td 
                                                className={`py-1.5 px-3 ${
                                                    isSubtotal 
                                                        ? 'font-semibold text-slate-800' 
                                                        : isPercentOrYoy
                                                            ? 'text-slate-400 text-[10px]'
                                                            : 'text-slate-600'
                                                }`}
                                                style={{ paddingLeft: `${12 + indent * 20}px` }}
                                            >
                                                {isPercentOrYoy && (
                                                    <span className="text-slate-300 mr-1.5">└</span>
                                                )}
                                                {field.label}
                                            </td>
                                            
                                            {/* Values */}
                                            {field.values.map((value, idx) => {
                                                const isNegative = value != null && value < 0;
                                                const isPositiveYoy = field.key.includes('_yoy') && 
                                                                     value != null && value > 0;
                                                const isNegativeYoy = field.key.includes('_yoy') && 
                                                                     value != null && value < 0;
                                                
                                                // Color: rojo para negativos y debits
                                                let textColor = '';
                                                if (isDebit || isNegative) {
                                                    textColor = 'text-red-600';
                                                } else if (isPositiveYoy) {
                                                    textColor = 'text-emerald-600';
                                                } else if (isNegativeYoy) {
                                                    textColor = 'text-red-500';
                                                }
                                                
                                                return (
                                                    <td
                                                        key={idx}
                                                        className={`
                                                            text-right py-1.5 px-3 tabular-nums
                                                            ${textColor}
                                                            ${isSubtotal ? 'font-semibold' : ''}
                                                            ${isPercentOrYoy ? 'text-[10px]' : ''}
                                                        `}
                                                    >
                                                        {formatValue(value, field.data_type, isDebit, displayUnit)}
                                                    </td>
                                                );
                                            })}
                                        </tr>
                                    );
                                })}
                            </React.Fragment>
                        );
                    })}
                    
                    {/* Espaciado final */}
                    <tr>
                        <td colSpan={periods.length + 1} className="h-4 bg-white"></td>
                    </tr>
                </tbody>
            </table>
        </div>
    );
}
