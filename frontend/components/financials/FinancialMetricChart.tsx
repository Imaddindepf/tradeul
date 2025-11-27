'use client';

import { useMemo, useEffect } from 'react';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
  CartesianGrid,
  Legend,
} from 'recharts';
import { TrendingUp, TrendingDown, Minus, BarChart3, LineChart } from 'lucide-react';

// ============================================================================
// Types
// ============================================================================

export interface MetricDataPoint {
  period: string;        // "Q1 2024" or "FY 2024"
  fiscalYear: string;
  value: number | null;
  isAnnual: boolean;
}

export interface FinancialMetricChartProps {
  ticker: string;
  metricKey: string;
  metricLabel: string;
  data: MetricDataPoint[];
  currency?: string;
  valueType?: 'currency' | 'percent' | 'ratio' | 'eps' | 'shares';
  isNegativeBad?: boolean;
}

// ============================================================================
// Helpers
// ============================================================================

function formatValue(value: number | null, type: string = 'currency'): string {
  if (value === null || value === undefined) return '--';

  if (type === 'percent') {
    const sign = value >= 0 ? '' : '';
    return `${sign}${value.toFixed(2)}%`;
  }

  if (type === 'ratio') {
    return value.toFixed(2);
  }

  if (type === 'eps') {
    const sign = value < 0 ? '-' : '';
    return `${sign}$${Math.abs(value).toFixed(2)}`;
  }

  if (type === 'shares') {
    const absValue = Math.abs(value);
    if (absValue >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`;
    if (absValue >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
    if (absValue >= 1_000) return `${(value / 1_000).toFixed(2)}K`;
    return value.toFixed(0);
  }

  // Currency formatting
  const absValue = Math.abs(value);
  const sign = value < 0 ? '-' : '';

  if (absValue >= 1_000_000_000_000) {
    return `${sign}$${(absValue / 1_000_000_000_000).toFixed(2)}T`;
  } else if (absValue >= 1_000_000_000) {
    return `${sign}$${(absValue / 1_000_000_000).toFixed(2)}B`;
  } else if (absValue >= 1_000_000) {
    return `${sign}$${(absValue / 1_000_000).toFixed(2)}M`;
  } else if (absValue >= 1_000) {
    return `${sign}$${(absValue / 1_000).toFixed(2)}K`;
  }
  return `${sign}$${absValue.toFixed(0)}`;
}

function formatValueCompact(value: number, type: string = 'currency'): string {
  if (type === 'percent') return `${value.toFixed(1)}%`;
  if (type === 'ratio') return value.toFixed(1);
  if (type === 'eps') return `$${value.toFixed(2)}`;
  if (type === 'shares') {
    const absValue = Math.abs(value);
    if (absValue >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
    if (absValue >= 1_000_000) return `${(value / 1_000_000).toFixed(0)}M`;
    return `${(value / 1_000).toFixed(0)}K`;
  }

  const absValue = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  if (absValue >= 1_000_000_000) return `${sign}$${(absValue / 1_000_000_000).toFixed(1)}B`;
  if (absValue >= 1_000_000) return `${sign}$${(absValue / 1_000_000).toFixed(0)}M`;
  return `${sign}$${(absValue / 1_000).toFixed(0)}K`;
}

// ============================================================================
// Component
// ============================================================================

export function FinancialMetricChart({
  ticker,
  metricKey,
  metricLabel,
  data,
  currency = 'USD',
  valueType = 'currency',
  isNegativeBad = true,
}: FinancialMetricChartProps) {
  // Prepare chart data (most recent last for proper visualization)
  const chartData = useMemo(() => {
    return data
      .filter(d => d.value !== null && d.value !== undefined)
      .map((d, index, arr) => ({
        ...d,
        displayValue: d.value as number,
        isLatest: index === arr.length - 1,
      }));
  }, [data]);

  // Calculate statistics
  const stats = useMemo(() => {
    const values = chartData.map(d => d.displayValue).filter(v => v !== null) as number[];
    if (values.length === 0) return null;

    const latest = values[values.length - 1];
    const first = values[0];
    const max = Math.max(...values);
    const min = Math.min(...values);
    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    
    // CAGR calculation
    const years = chartData.length > 1 
      ? (chartData[chartData.length - 1].isAnnual ? chartData.length - 1 : (chartData.length - 1) / 4)
      : 0;
    const cagr = years > 0 && first !== 0 
      ? (Math.pow(latest / first, 1 / years) - 1) * 100 
      : null;

    // YoY growth (comparing to 4 periods ago for quarterly, 1 for annual)
    const periodsBack = chartData[chartData.length - 1]?.isAnnual ? 1 : 4;
    const previousValue = values.length > periodsBack ? values[values.length - 1 - periodsBack] : null;
    const yoyGrowth = previousValue && previousValue !== 0 
      ? ((latest - previousValue) / Math.abs(previousValue)) * 100 
      : null;

    // Sequential growth (quarter over quarter)
    const prevValue = values.length > 1 ? values[values.length - 2] : null;
    const qoqGrowth = prevValue && prevValue !== 0
      ? ((latest - prevValue) / Math.abs(prevValue)) * 100
      : null;

    return { latest, first, max, min, avg, cagr, yoyGrowth, qoqGrowth };
  }, [chartData]);

  // Growth indicator
  const getGrowthIndicator = (growth: number | null) => {
    if (growth === null) return <Minus className="w-4 h-4 text-slate-400" />;
    if (growth > 5) return <TrendingUp className="w-4 h-4 text-emerald-500" />;
    if (growth < -5) return <TrendingDown className="w-4 h-4 text-red-500" />;
    return <Minus className="w-4 h-4 text-slate-400" />;
  };

  const getGrowthColor = (growth: number | null) => {
    if (growth === null) return 'text-slate-500';
    if (growth > 0) return isNegativeBad ? 'text-emerald-600' : 'text-red-600';
    if (growth < 0) return isNegativeBad ? 'text-red-600' : 'text-emerald-600';
    return 'text-slate-600';
  };

  // Store chart data globally for pop-out support
  useEffect(() => {
    // Store in global registry for pop-out access
    const chartDataForPopout = {
      ticker,
      metricLabel,
      metricKey,
      currency,
      valueType,
      isNegativeBad,
      data: data.map(d => ({
        period: d.period,
        fiscalYear: d.fiscalYear,
        value: d.value,
        isAnnual: d.isAnnual
      }))
    };
    
    // Create global registry if not exists
    if (typeof window !== 'undefined') {
      (window as any).__financialChartData = (window as any).__financialChartData || {};
      const key = `${ticker}-${metricKey}`;
      (window as any).__financialChartData[key] = chartDataForPopout;
    }

    return () => {
      // Cleanup on unmount
      if (typeof window !== 'undefined' && (window as any).__financialChartData) {
        const key = `${ticker}-${metricKey}`;
        delete (window as any).__financialChartData[key];
      }
    };
  }, [ticker, metricLabel, metricKey, currency, valueType, isNegativeBad, data]);

  if (chartData.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-slate-400">
        <div className="text-center">
          <BarChart3 className="w-12 h-12 mx-auto mb-2 opacity-50" />
          <p className="text-sm">No data available for {metricLabel}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-200 bg-gradient-to-r from-slate-50 to-white">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-900">{metricLabel}</h2>
            <p className="text-sm text-slate-500">{ticker} • {currency} • {chartData.length} periods</p>
          </div>
          {stats && (
            <div className="flex items-center gap-2">
              {getGrowthIndicator(stats.yoyGrowth)}
              <span className={`text-2xl font-bold ${getGrowthColor(stats.yoyGrowth)}`}>
                {formatValue(stats.latest, valueType)}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Stats Grid */}
      {stats && (
        <div className="grid grid-cols-6 gap-2 px-4 py-3 bg-slate-50 border-b border-slate-200">
          <div className="text-center">
            <p className="text-[10px] uppercase text-slate-500 font-medium">Latest</p>
            <p className="text-sm font-bold text-slate-800">{formatValue(stats.latest, valueType)}</p>
          </div>
          <div className="text-center">
            <p className="text-[10px] uppercase text-slate-500 font-medium">YoY Growth</p>
            <p className={`text-sm font-bold ${getGrowthColor(stats.yoyGrowth)}`}>
              {stats.yoyGrowth !== null ? `${stats.yoyGrowth > 0 ? '+' : ''}${stats.yoyGrowth.toFixed(1)}%` : '--'}
            </p>
          </div>
          <div className="text-center">
            <p className="text-[10px] uppercase text-slate-500 font-medium">QoQ Growth</p>
            <p className={`text-sm font-bold ${getGrowthColor(stats.qoqGrowth)}`}>
              {stats.qoqGrowth !== null ? `${stats.qoqGrowth > 0 ? '+' : ''}${stats.qoqGrowth.toFixed(1)}%` : '--'}
            </p>
          </div>
          <div className="text-center">
            <p className="text-[10px] uppercase text-slate-500 font-medium">Max</p>
            <p className="text-sm font-bold text-slate-800">{formatValue(stats.max, valueType)}</p>
          </div>
          <div className="text-center">
            <p className="text-[10px] uppercase text-slate-500 font-medium">Min</p>
            <p className="text-sm font-bold text-slate-800">{formatValue(stats.min, valueType)}</p>
          </div>
          <div className="text-center">
            <p className="text-[10px] uppercase text-slate-500 font-medium">CAGR</p>
            <p className={`text-sm font-bold ${getGrowthColor(stats.cagr)}`}>
              {stats.cagr !== null ? `${stats.cagr > 0 ? '+' : ''}${stats.cagr.toFixed(1)}%` : '--'}
            </p>
          </div>
        </div>
      )}

      {/* Main Chart */}
      <div className="flex-1 p-4">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 10, right: 30, left: 10, bottom: 30 }}>
            <defs>
              <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
            </defs>
            
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            
            <XAxis
              dataKey="period"
              tick={{ fontSize: 11, fill: '#64748b' }}
              tickLine={false}
              axisLine={{ stroke: '#e2e8f0' }}
              angle={-45}
              textAnchor="end"
              height={60}
              interval="preserveStartEnd"
            />
            
            <YAxis
              tick={{ fontSize: 11, fill: '#64748b' }}
              tickLine={false}
              axisLine={{ stroke: '#e2e8f0' }}
              tickFormatter={(v) => formatValueCompact(v, valueType)}
              width={70}
            />
            
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: 'none',
                borderRadius: '12px',
                boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
                padding: '16px',
              }}
              labelStyle={{ color: '#f1f5f9', fontWeight: 700, fontSize: '14px', marginBottom: '8px' }}
              itemStyle={{ color: '#cbd5e1', fontSize: '13px' }}
              formatter={(value: number) => [formatValue(value, valueType), metricLabel]}
              cursor={{ stroke: '#94a3b8', strokeWidth: 1, strokeDasharray: '5 5' }}
            />

            {stats && <ReferenceLine y={stats.avg} stroke="#94a3b8" strokeDasharray="5 5" label={{ value: 'Avg', fill: '#94a3b8', fontSize: 10 }} />}

            <Area
              type="monotone"
              dataKey="displayValue"
              stroke="#3b82f6"
              strokeWidth={0}
              fill="url(#colorValue)"
            />
            
            <Bar dataKey="displayValue" radius={[6, 6, 0, 0]} maxBarSize={50}>
              {chartData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={entry.isLatest ? '#2563eb' : '#60a5fa'}
                  opacity={entry.isLatest ? 1 : 0.8}
                />
              ))}
            </Bar>
            
            <Line
              type="monotone"
              dataKey="displayValue"
              stroke="#1e40af"
              strokeWidth={2}
              dot={{ fill: '#1e40af', r: 4 }}
              activeDot={{ fill: '#1e40af', r: 6, stroke: '#fff', strokeWidth: 2 }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Footer Legend */}
      <div className="px-4 py-2 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
        <div className="flex items-center gap-4 text-xs text-slate-500">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded bg-blue-600" />
            <span>Latest Period</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded bg-blue-400" />
            <span>Historical</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-6 h-0.5 bg-slate-400" style={{ borderStyle: 'dashed' }} />
            <span>Average</span>
          </div>
        </div>
        <p className="text-xs text-slate-400">
          Data from {chartData[0]?.period} to {chartData[chartData.length - 1]?.period}
        </p>
      </div>
    </div>
  );
}

// ============================================================================
// Window Config Export
// ============================================================================

export const FINANCIAL_METRIC_CHART_CONFIG = {
  width: 900,
  height: 550,
  minWidth: 700,
  minHeight: 400,
  maxWidth: 1400,
  maxHeight: 900,
};

