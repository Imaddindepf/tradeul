'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useFloatingWindowActions } from '@/contexts/FloatingWindowContext';
import { FinancialChartPro, type ChartSeriesField, curSymbol } from '../FinancialChartPro';
import { pushOverlaySeries } from '../chartOverlayBus';

const API_URL = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_GATEWAY_URL || 'http://localhost:8000';

// ============================================================================
// TYPES
// ============================================================================

interface SegmentData {
  [segmentName: string]: {
    [year: string]: number;
  };
}

interface MetricMeta {
  data_type?: string;
  is_currency?: boolean;
  unit_label?: string | null;
}

interface SegmentsResponse {
  symbol: string;
  currency?: string;
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
  metric_meta?: Record<string, MetricMeta>;
}

interface SegmentsTableProps {
  symbol: string;
  currency?: string;
  /** annual | quarterly | ttm — ttm falls back to annual for segments. */
  period?: string;
  lockOverlay?: boolean;
  dashboardId?: string;
}

/** Sort key: quarterly labels like "Q3 2026" and annual "2026", newest first. */
function periodSortKey(label: string): number {
  const q = label.match(/^Q([1-4])\s+(\d{4})$/);
  if (q) return parseInt(q[2]) * 10 + parseInt(q[1]);
  const y = parseInt(label);
  return Number.isNaN(y) ? 0 : y * 10 + 9;
}

function periodHeaderLabel(label: string): string {
  return /^Q[1-4]/.test(label) ? label : `FY${label}`;
}

// ============================================================================
// UTILITIES
// ============================================================================

/** Infer data type when backend meta is missing (legacy payloads / cache). */
function inferDataType(name: string, meta?: MetricMeta): string {
  if (meta?.data_type) return meta.data_type;
  if (meta?.is_currency === false) return 'number';
  if (meta?.is_currency === true) return 'monetary';
  const lower = name.toLowerCase();
  if (
    /\(units?\)/i.test(name) ||
    /\b(mw|mwh|gw|gwh|eh\/s|hashrate|gpus?|servers?|customers?|subscribers?|stores?|locations?)\b/i.test(lower)
  ) {
    return 'number';
  }
  if (/%|margin|growth|yoy|rate\b/i.test(lower) && !/revenue|income|sales\b/i.test(lower)) {
    return 'percent';
  }
  return 'monetary';
}

function unitLabelFor(name: string, meta?: MetricMeta): string | undefined {
  if (meta?.unit_label) return meta.unit_label;
  const m = name.match(/\(([^)]+)\)\s*$/);
  return m?.[1]?.trim();
}

const formatValue = (
  value: number | undefined,
  dataType: string,
  currency: string,
): string => {
  if (value === undefined || value === null || Number.isNaN(value)) return '—';

  if (dataType === 'percent') {
    const pct = Math.abs(value) <= 1.5 ? value * 100 : value;
    const formatted = `${Math.abs(pct).toFixed(1)}%`;
    return value < 0 ? `(${formatted})` : formatted;
  }

  if (dataType === 'number') {
    const abs = Math.abs(value);
    let formatted: string;
    if (abs >= 1e9) formatted = `${(abs / 1e9).toFixed(2)}B`;
    else if (abs >= 1e6) formatted = `${(abs / 1e6).toFixed(2)}M`;
    else if (abs >= 1e3 && abs >= 10000) formatted = `${(abs / 1e3).toFixed(1)}K`;
    else formatted = Number.isInteger(abs) ? abs.toLocaleString('en-US') : abs.toLocaleString('en-US', { maximumFractionDigits: 2 });
    return value < 0 ? `(${formatted})` : formatted;
  }

  // monetary — always use the company's reported currency (EUR, CHF, USD…)
  const absValue = Math.abs(value);
  const sym = curSymbol(currency);
  let body: string;
  if (absValue >= 1e9) body = `${(absValue / 1e9).toFixed(2)}B`;
  else if (absValue >= 1e6) body = `${(absValue / 1e6).toFixed(2)}M`;
  else if (absValue >= 1e3) body = `${(absValue / 1e3).toFixed(2)}K`;
  else body = absValue.toFixed(0);

  return value < 0 ? `(${sym}${body})` : `${sym}${body}`;
};

const calculateYoY = (current: number | undefined, previous: number | undefined): number | null => {
  if (!current || !previous || previous === 0) return null;
  return (current - previous) / Math.abs(previous);
};

const formatPercent = (value: number | null): string => {
  if (value === null) return '—';
  const pct = value * 100;
  if (pct < 0) return `(${Math.abs(pct).toFixed(1)}%)`;
  return `${pct.toFixed(1)}%`;
};

// ============================================================================
// COMPONENT
// ============================================================================

export function SegmentsTable({ symbol, currency = 'USD', period = 'annual', lockOverlay = false, dashboardId }: SegmentsTableProps) {
  const { openWindow } = useFloatingWindowActions();
  const [data, setData] = useState<SegmentsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Segments only distinguish annual vs quarterly (TTM has no meaning here).
  const effectivePeriod = period === 'quarterly' ? 'quarterly' : 'annual';
  const isQuarterly = effectivePeriod === 'quarterly';

  useEffect(() => {
    async function fetchSegments() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API_URL}/api/v1/financials/${symbol}/segments?period=${effectivePeriod}`);
        if (!response.ok) {
          if (response.status === 404) setError('No segment data available for this company');
          else throw new Error('Failed to fetch segments');
          return;
        }
        setData(await response.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    }
    if (symbol) fetchSegments();
  }, [symbol, effectivePeriod]);

  const reportCurrency = (data?.currency || currency || 'USD').toUpperCase();
  const metricMeta = data?.metric_meta || {};

  const years = useMemo(() => {
    if (!data) return [];
    const allYears = new Set<string>();
    const collect = (block?: SegmentData) => {
      Object.values(block || {}).forEach(segment => {
        Object.keys(segment).forEach(year => allYears.add(year));
      });
    };
    collect(data.segments?.revenue);
    collect(data.geography?.revenue);
    collect(data.products?.revenue);
    return Array.from(allYears).sort((a, b) => periodSortKey(b) - periodSortKey(a));
  }, [data]);

  const openChart = useCallback((
    revenueData: SegmentData,
    segmentName: string,
    useOpIncome?: SegmentData,
    sectionIsKpi?: boolean,
  ) => {
    const buildValues = (sd: SegmentData, name: string) =>
      years.map(y => {
        const v = sd[name]?.[y];
        return v === undefined || v === null || Number.isNaN(v) ? null : v;
      });

    const metaFor = (name: string) => metricMeta[name];
    const typeFor = (name: string) => {
      // KPI section defaults to non-monetary when meta is absent.
      if (sectionIsKpi && !metaFor(name)) return inferDataType(name, { is_currency: false });
      return inferDataType(name, metaFor(name));
    };
    // Segment percentages have no fixed scale (some payloads carry 0.23, others
    // 23). `formatValue` above decides per cell; a chart needs one scale for the
    // whole series, so decide once over its values with the same threshold.
    const percentScaleFor = (vals: (number | null)[]): 'fraction' | 'points' => {
      const finite = vals.filter((v): v is number => v !== null && !Number.isNaN(v));
      if (finite.length === 0) return 'fraction';
      return finite.every(v => Math.abs(v) <= 1.5) ? 'fraction' : 'points';
    };

    if (lockOverlay && dashboardId) {
      const overlayValues = buildValues(revenueData, segmentName);
      const delivered = pushOverlaySeries(dashboardId, {
        key: segmentName,
        label: segmentName,
        dataType: typeFor(segmentName),
        percentScale: percentScaleFor(overlayValues),
        balance: null,
        periods: years,
        values: overlayValues,
      });
      if (delivered) return;
    }

    const fields: ChartSeriesField[] = Object.keys(revenueData).map(name => {
      const values = buildValues(revenueData, name);
      return {
        key: name,
        label: name,
        values,
        dataType: typeFor(name),
        percentScale: percentScaleFor(values),
        unitLabel: unitLabelFor(name, metaFor(name)),
        section: sectionIsKpi ? 'Operating KPIs' : 'Segments',
      };
    });

    if (useOpIncome) {
      for (const name of Object.keys(useOpIncome)) {
        const key = `${name} — Operating Income`;
        fields.push({
          key,
          label: key,
          values: buildValues(useOpIncome, name),
          dataType: 'monetary',
          section: 'Operating Income',
        });
      }
    }

    openWindow({
      title: `${symbol} — ${segmentName}`,
      content: (
        <FinancialChartPro
          ticker={symbol}
          currency={reportCurrency}
          periods={years}
          fields={fields}
          initialMetricKey={segmentName}
          dashboardId={dashboardId}
        />
      ),
      width: 960,
      height: 560,
      x: Math.max(80, (window.innerWidth - 960) / 2),
      y: Math.max(50, (window.innerHeight - 560) / 2),
    });
  }, [years, symbol, reportCurrency, lockOverlay, dashboardId, openWindow, metricMeta]);

  if (loading) {
    return <div className="p-4 text-center text-muted-fg text-xs">Loading segment data...</div>;
  }
  if (error) {
    return <div className="p-4 text-center text-muted-fg text-xs">{error}</div>;
  }
  if (!data) return null;

  const hasSegments = Object.keys(data.segments?.revenue || {}).length > 0;
  const hasGeography = Object.keys(data.geography?.revenue || {}).length > 0;
  const hasProducts = data.products && Object.keys(data.products.revenue || {}).length > 0;

  if (!hasSegments && !hasGeography && !hasProducts) {
    return <div className="p-4 text-center text-muted-fg text-xs">No segment data available</div>;
  }

  // Geography slot is reused for KPIs by the v3 transformer — detect that.
  const geographyLooksLikeKpis = hasGeography && Object.keys(data.geography.revenue).every(name => {
    const t = inferDataType(name, metricMeta[name]);
    return t !== 'monetary' || /\(units?\)/i.test(name);
  });

  const renderSection = (
    title: string,
    revenueData: SegmentData,
    operatingIncomeData?: SegmentData,
    isKpiSection?: boolean,
  ) => {
    const segments = Object.keys(revenueData);
    if (segments.length === 0) return null;

    const sortedSegments = [...segments].sort((a, b) => {
      const aVal = revenueData[a][years[0]] || 0;
      const bVal = revenueData[b][years[0]] || 0;
      return bVal - aVal;
    });

    return (
      <React.Fragment key={title}>
        <tr>
          <td colSpan={years.length + 2} className="h-3 bg-surface"></td>
        </tr>
        <tr className="border-y border-border bg-surface-hover">
          <td
            colSpan={years.length + 2}
            className="py-2 px-3 font-bold text-[11px] uppercase tracking-wide text-foreground/80"
          >
            {title}
          </td>
        </tr>

        {sortedSegments.map(segmentName => {
          const segmentData = revenueData[segmentName];
          // Quarterly: YoY compares the same quarter one year back (4 columns).
          const yoyPrevIdx = isQuarterly ? 4 : 1;
          const yoy = calculateYoY(segmentData[years[0]], segmentData[years[yoyPrevIdx]]);
          const dtype = isKpiSection && !metricMeta[segmentName]
            ? inferDataType(segmentName, { is_currency: false })
            : inferDataType(segmentName, metricMeta[segmentName]);

          return (
            <React.Fragment key={segmentName}>
              <tr
                className="border-b border-border-subtle bg-surface hover:bg-primary/10 transition-colors cursor-pointer"
                onClick={() => openChart(revenueData, segmentName, operatingIncomeData, isKpiSection)}
              >
                <td className="py-1.5 px-3 text-foreground/80">
                  {segmentName}
                </td>
                {years.map(year => (
                  <td key={year} className="text-right py-1.5 px-3 tabular-nums text-foreground">
                    {formatValue(segmentData[year], dtype, reportCurrency)}
                  </td>
                ))}
                <td className={`text-right py-1.5 px-3 tabular-nums text-[10px] ${
                  yoy !== null && yoy > 0 ? 'text-emerald-600' :
                  yoy !== null && yoy < 0 ? 'text-red-500' : 'text-muted-fg'
                }`}>
                  {formatPercent(yoy)}
                </td>
              </tr>

              {operatingIncomeData?.[segmentName] && (
                <tr className="border-b border-border-subtle bg-surface">
                  <td className="py-1 px-3 text-muted-fg text-[10px]" style={{ paddingLeft: '32px' }}>
                    <span className="text-muted-fg/50 mr-1.5">└</span>
                    Operating Income
                  </td>
                  {years.map(year => {
                    const val = operatingIncomeData[segmentName][year];
                    const isNegative = val != null && val < 0;
                    return (
                      <td key={year} className={`text-right py-1 px-3 tabular-nums text-[10px] ${
                        isNegative ? 'text-red-600' : 'text-muted-fg'
                      }`}>
                        {formatValue(val, 'monetary', reportCurrency)}
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
    <div className="overflow-x-auto bg-surface">
      <div className="px-3 py-1.5 border-b border-border-subtle text-[10px] text-muted-fg">
        Monetary values in {reportCurrency}
        {geographyLooksLikeKpis ? ' · KPIs in reported units' : ''}
      </div>
      <table className="w-full text-[11px] border-collapse">
        <thead className="sticky top-0 z-10">
          <tr className="bg-surface-inset border-b-2 border-border">
            <th className="text-left py-2.5 px-3 font-semibold text-foreground min-w-[200px] bg-surface-inset">
              Segment
            </th>
            {years.map(year => (
              <th
                key={year}
                className="text-right py-2.5 px-3 font-semibold text-foreground min-w-[90px] bg-surface-inset"
              >
                {periodHeaderLabel(year)}
              </th>
            ))}
            <th className="text-right py-2.5 px-3 font-semibold text-foreground min-w-[70px] bg-surface-inset">
              YoY
            </th>
          </tr>
        </thead>

        <tbody className="text-foreground">
          {hasSegments && renderSection(
            'Business Segments',
            data.segments.revenue,
            data.segments.operating_income,
            false,
          )}

          {hasGeography && renderSection(
            geographyLooksLikeKpis ? 'Operating KPIs' : 'Geographic Revenue',
            data.geography.revenue,
            data.geography.operating_income,
            geographyLooksLikeKpis,
          )}

          {hasProducts && data.products && renderSection(
            'Products & Services',
            data.products.revenue,
            undefined,
            false,
          )}

          <tr>
            <td colSpan={years.length + 2} className="h-4 bg-surface"></td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
