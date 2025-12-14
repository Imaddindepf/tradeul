'use client';

import React, { useState, useEffect, useMemo } from 'react';

// API URL from environment
const API_URL = process.env.NEXT_PUBLIC_API_GATEWAY_URL || 'http://localhost:8000';

// ============================================================================
// TYPES
// ============================================================================

interface SegmentData {
  [segmentName: string]: {
    [year: string]: number;
  };
}

interface SegmentsResponse {
  symbol: string;
  filing_date: string;
  period_end: string;
  segments: {
    revenue: SegmentData;
    operating_income: SegmentData;
  };
  geography: {
    revenue: SegmentData;
    operating_income?: SegmentData;
  };
  products?: {
    revenue: SegmentData;
  };
}

interface SegmentsTableProps {
  symbol: string;
}

// ============================================================================
// UTILITIES - Mismo formato que SymbioticTable
// ============================================================================

const formatValue = (value: number | undefined): string => {
  if (value === undefined || value === null) return '—';

  const absValue = Math.abs(value);
  let formatted: string;

  if (absValue >= 1e9) {
    formatted = `$${(absValue / 1e9).toFixed(2)}B`;
  } else if (absValue >= 1e6) {
    formatted = `$${(absValue / 1e6).toFixed(2)}M`;
  } else if (absValue >= 1e3) {
    formatted = `$${(absValue / 1e3).toFixed(2)}K`;
  } else {
    formatted = `$${absValue.toFixed(0)}`;
  }

  // Negativos entre paréntesis (estilo TIKR/contable)
  if (value < 0) {
    return `(${formatted.substring(1)})`;
  }

  return formatted;
};

const calculateYoY = (current: number | undefined, previous: number | undefined): number | null => {
  if (!current || !previous || previous === 0) return null;
  return (current - previous) / Math.abs(previous);
};

const formatPercent = (value: number | null): string => {
  if (value === null) return '—';
  const pct = value * 100;
  if (pct < 0) {
    return `(${Math.abs(pct).toFixed(1)}%)`;
  }
  return `${pct.toFixed(1)}%`;
};

// ============================================================================
// COMPONENT
// ============================================================================

export function SegmentsTable({ symbol }: SegmentsTableProps) {
  const [data, setData] = useState<SegmentsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchSegments() {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(`${API_URL}/api/v1/financials/${symbol}/segments`);

        if (!response.ok) {
          if (response.status === 404) {
            setError('No segment data available for this company');
          } else {
            throw new Error('Failed to fetch segments');
          }
          return;
        }

        const result = await response.json();
        setData(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    }

    if (symbol) {
      fetchSegments();
    }
  }, [symbol]);

  // Calcular años disponibles (incluye segments, geography Y products)
  const years = useMemo(() => {
    if (!data) return [];

    const allYears = new Set<string>();
    
    // Segments
    Object.values(data.segments?.revenue || {}).forEach(segment => {
      Object.keys(segment).forEach(year => allYears.add(year));
    });
    
    // Geography
    Object.values(data.geography?.revenue || {}).forEach(segment => {
      Object.keys(segment).forEach(year => allYears.add(year));
    });
    
    // Products (fix: también incluir products para empresas que solo tienen esto)
    if (data.products?.revenue) {
      Object.values(data.products.revenue).forEach(product => {
        Object.keys(product).forEach(year => allYears.add(year));
      });
    }

    return Array.from(allYears).sort((a, b) => parseInt(b) - parseInt(a));
  }, [data]);

  if (loading) {
    return <div className="p-4 text-center text-slate-400 text-xs">Loading segment data...</div>;
  }

  if (error) {
    return <div className="p-4 text-center text-slate-400 text-xs">{error}</div>;
  }

  if (!data) return null;

  const hasSegments = Object.keys(data.segments?.revenue || {}).length > 0;
  const hasGeography = Object.keys(data.geography?.revenue || {}).length > 0;
  const hasProducts = data.products && Object.keys(data.products.revenue || {}).length > 0;

  if (!hasSegments && !hasGeography && !hasProducts) {
    return <div className="p-4 text-center text-slate-400 text-xs">No segment data available</div>;
  }

  // Renderizar una sección de segmentos
  const renderSection = (
    title: string,
    revenueData: SegmentData,
    operatingIncomeData?: SegmentData
  ) => {
    const segments = Object.keys(revenueData);
    if (segments.length === 0) return null;

    // Ordenar por valor del año más reciente (descendente)
    const sortedSegments = [...segments].sort((a, b) => {
      const aVal = revenueData[a][years[0]] || 0;
      const bVal = revenueData[b][years[0]] || 0;
      return bVal - aVal;
    });

    return (
      <React.Fragment key={title}>
        {/* Section Header */}
        <tr>
          <td colSpan={years.length + 2} className="h-3 bg-white"></td>
        </tr>
        <tr className="border-y border-slate-200 bg-slate-50">
          <td
            colSpan={years.length + 2}
            className="py-2 px-3 font-bold text-[11px] uppercase tracking-wide text-slate-600"
          >
            {title}
          </td>
        </tr>

        {/* Segment Rows */}
        {sortedSegments.map(segmentName => {
          const segmentData = revenueData[segmentName];
          const yoy = calculateYoY(segmentData[years[0]], segmentData[years[1]]);

          return (
            <React.Fragment key={segmentName}>
              {/* Revenue row */}
              <tr className="border-b border-slate-100 bg-white hover:bg-blue-50/40 transition-colors">
                <td className="py-1.5 px-3 text-slate-600">
                  {segmentName}
                </td>
                {years.map(year => (
                  <td key={year} className="text-right py-1.5 px-3 tabular-nums text-slate-700">
                    {formatValue(segmentData[year])}
                  </td>
                ))}
                <td className={`text-right py-1.5 px-3 tabular-nums text-[10px] ${yoy !== null && yoy > 0 ? 'text-emerald-600' :
                    yoy !== null && yoy < 0 ? 'text-red-500' : 'text-slate-400'
                  }`}>
                  {formatPercent(yoy)}
                </td>
              </tr>

              {/* Operating Income sub-row (if available) */}
              {operatingIncomeData?.[segmentName] && (
                <tr className="border-b border-slate-100 bg-white">
                  <td className="py-1 px-3 text-slate-400 text-[10px]" style={{ paddingLeft: '32px' }}>
                    <span className="text-slate-300 mr-1.5">└</span>
                    Operating Income
                  </td>
                  {years.map(year => {
                    const val = operatingIncomeData[segmentName][year];
                    const isNegative = val != null && val < 0;
                    return (
                      <td key={year} className={`text-right py-1 px-3 tabular-nums text-[10px] ${isNegative ? 'text-red-600' : 'text-slate-400'
                        }`}>
                        {formatValue(val)}
                      </td>
                    );
                  })}
                  <td className="py-1 px-3"></td>
                </tr>
              )}
            </React.Fragment>
          );
        })}
      </React.Fragment>
    );
  };

  return (
    <div className="overflow-x-auto bg-white">
      <table className="w-full text-[11px] border-collapse">
        {/* Header */}
        <thead className="sticky top-0 z-10">
          <tr className="bg-slate-100 border-b-2 border-slate-300">
            <th className="text-left py-2.5 px-3 font-semibold text-slate-700 min-w-[200px] bg-slate-100">
              Segment
            </th>
            {years.map(year => (
              <th
                key={year}
                className="text-right py-2.5 px-3 font-semibold text-slate-700 min-w-[90px] bg-slate-100"
              >
                FY{year}
              </th>
            ))}
            <th className="text-right py-2.5 px-3 font-semibold text-slate-700 min-w-[70px] bg-slate-100">
              YoY
            </th>
          </tr>
        </thead>

        <tbody className="text-slate-700">
          {/* Business Segments */}
          {hasSegments && renderSection(
            'Business Segments',
            data.segments.revenue,
            data.segments.operating_income
          )}

          {/* Geographic Revenue */}
          {hasGeography && renderSection(
            'Geographic Revenue',
            data.geography.revenue,
            data.geography.operating_income
          )}

          {/* Products & Services */}
          {hasProducts && data.products && renderSection(
            'Products & Services',
            data.products.revenue
          )}

          {/* Espaciado final */}
          <tr>
            <td colSpan={years.length + 2} className="h-4 bg-white"></td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
