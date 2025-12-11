'use client';

import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Globe, Briefcase, Package } from 'lucide-react';

// ============================================================================
// Types
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
// Helpers
// ============================================================================

function formatValue(value: number | undefined): string {
  if (value === undefined || value === null) return '—';
  
  const absValue = Math.abs(value);
  const isNegative = value < 0;
  
  let formatted: string;
  if (absValue >= 1e9) {
    formatted = `$${(absValue / 1e9).toFixed(1)}B`;
  } else if (absValue >= 1e6) {
    formatted = `$${(absValue / 1e6).toFixed(0)}M`;
  } else {
    formatted = `$${absValue.toFixed(0)}`;
  }
  
  return isNegative ? `(${formatted})` : formatted;
}

function calculateYoY(current: number | undefined, previous: number | undefined): string | null {
  if (!current || !previous || previous === 0) return null;
  const change = ((current - previous) / Math.abs(previous)) * 100;
  return `${change >= 0 ? '+' : ''}${change.toFixed(1)}%`;
}

// ============================================================================
// Segment Row Component
// ============================================================================

interface SegmentRowProps {
  name: string;
  data: { [year: string]: number };
  years: string[];
  showOperatingIncome?: { [year: string]: number };
}

function SegmentRow({ name, data, years, showOperatingIncome }: SegmentRowProps) {
  const latestYear = years[0];
  const previousYear = years[1];
  const yoy = calculateYoY(data[latestYear], data[previousYear]);
  
  return (
    <>
      <tr className="hover:bg-slate-800/30 transition-colors">
        <td className="py-2 px-3 text-slate-200 font-medium">
          {name}
        </td>
        {years.map(year => (
          <td key={year} className="py-2 px-3 text-right font-mono text-slate-300">
            {formatValue(data[year])}
          </td>
        ))}
        <td className="py-2 px-3 text-right">
          {yoy && (
            <span className={`font-mono text-sm ${
              yoy.startsWith('+') ? 'text-emerald-400' : 'text-red-400'
            }`}>
              {yoy}
            </span>
          )}
        </td>
      </tr>
      {showOperatingIncome && (
        <tr className="hover:bg-slate-800/30 transition-colors">
          <td className="py-1 px-3 pl-6 text-slate-400 text-sm">
            └ Operating Income
          </td>
          {years.map(year => (
            <td key={year} className="py-1 px-3 text-right font-mono text-sm text-slate-400">
              {formatValue(showOperatingIncome[year])}
            </td>
          ))}
          <td className="py-1 px-3"></td>
        </tr>
      )}
    </>
  );
}

// ============================================================================
// Section Component
// ============================================================================

interface SectionProps {
  title: string;
  icon: React.ReactNode;
  data: SegmentData;
  operatingIncomeData?: SegmentData;
  years: string[];
}

function Section({ title, icon, data, operatingIncomeData, years }: SectionProps) {
  const segments = Object.keys(data);
  
  if (segments.length === 0) return null;
  
  // Ordenar por valor del año más reciente (descendente)
  const sortedSegments = segments.sort((a, b) => {
    const aVal = data[a][years[0]] || 0;
    const bVal = data[b][years[0]] || 0;
    return bVal - aVal;
  });
  
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-3 px-3">
        <span className="text-slate-400">{icon}</span>
        <h3 className="text-lg font-semibold text-slate-200">{title}</h3>
        <span className="text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded">
          {segments.length} segments
        </span>
      </div>
      
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700">
              <th className="py-2 px-3 text-left text-slate-400 font-medium">Segment</th>
              {years.map(year => (
                <th key={year} className="py-2 px-3 text-right text-slate-400 font-medium min-w-[100px]">
                  {year}
                </th>
              ))}
              <th className="py-2 px-3 text-right text-slate-400 font-medium w-20">YoY</th>
            </tr>
          </thead>
          <tbody>
            {sortedSegments.map(segment => (
              <SegmentRow
                key={segment}
                name={segment}
                data={data[segment]}
                years={years}
                showOperatingIncome={operatingIncomeData?.[segment]}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
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
        const response = await fetch(`/api/v1/financials/${symbol}/segments`);
        
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
  
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        <span className="ml-3 text-slate-400">Loading segment data...</span>
      </div>
    );
  }
  
  if (error) {
    return (
      <div className="text-center py-12 text-slate-400">
        <Globe className="w-12 h-12 mx-auto mb-3 opacity-50" />
        <p>{error}</p>
      </div>
    );
  }
  
  if (!data) return null;
  
  // Obtener años disponibles (ordenados descendente)
  const allYears = new Set<string>();
  Object.values(data.segments.revenue).forEach(segment => {
    Object.keys(segment).forEach(year => allYears.add(year));
  });
  Object.values(data.geography.revenue).forEach(segment => {
    Object.keys(segment).forEach(year => allYears.add(year));
  });
  
  const years = Array.from(allYears).sort((a, b) => parseInt(b) - parseInt(a));
  
  const hasSegments = Object.keys(data.segments.revenue).length > 0;
  const hasGeography = Object.keys(data.geography.revenue).length > 0;
  const hasProducts = data.products && Object.keys(data.products.revenue).length > 0;
  
  return (
    <div className="bg-slate-900/50 rounded-lg border border-slate-800 p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
        <div>
          <h2 className="text-xl font-bold text-white">Segment Breakdown</h2>
          <p className="text-sm text-slate-500">
            Filing: {data.filing_date} • Period: {data.period_end}
          </p>
        </div>
        <div className="text-xs text-slate-600 bg-slate-800/50 px-2 py-1 rounded">
          Source: SEC EDGAR (XBRL)
        </div>
      </div>
      
      {/* Business Segments */}
      {hasSegments && (
        <Section
          title="Business Segments"
          icon={<Briefcase className="w-5 h-5" />}
          data={data.segments.revenue}
          operatingIncomeData={data.segments.operating_income}
          years={years}
        />
      )}
      
      {/* Geography */}
      {hasGeography && (
        <Section
          title="Geographic Revenue"
          icon={<Globe className="w-5 h-5" />}
          data={data.geography.revenue}
          years={years}
        />
      )}
      
      {/* Products (if available) */}
      {hasProducts && data.products && (
        <Section
          title="Products & Services"
          icon={<Package className="w-5 h-5" />}
          data={data.products.revenue}
          years={years}
        />
      )}
      
      {!hasSegments && !hasGeography && !hasProducts && (
        <div className="text-center py-8 text-slate-400">
          No segment breakdown available for {symbol}
        </div>
      )}
    </div>
  );
}

