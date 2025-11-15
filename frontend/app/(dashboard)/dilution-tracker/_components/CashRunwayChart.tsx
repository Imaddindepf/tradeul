"use client";

import { AlertCircle } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

interface CashRunwayData {
  current_cash: number;
  quarterly_burn_rate: number;
  estimated_runway_months: number | null;
  runway_risk_level: "critical" | "high" | "medium" | "low" | "unknown";
  history?: Array<{
    date: string;
    cash: number;
  }>;
  projection: Array<{
    month: number;
    date: string;
    estimated_cash: number;
  }>;
}

interface CashRunwayChartProps {
  data: CashRunwayData | null;
  loading?: boolean;
}

export function CashRunwayChart({ data, loading = false }: CashRunwayChartProps) {
  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
      <div className="animate-pulse space-y-4">
          <div className="h-8 bg-slate-100 rounded w-48" />
        <div className="grid grid-cols-3 gap-4">
            <div className="h-24 bg-slate-100 rounded" />
            <div className="h-24 bg-slate-100 rounded" />
            <div className="h-24 bg-slate-100 rounded" />
          </div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
      <div className="text-center py-12">
          <AlertCircle className="h-12 w-12 text-slate-400 mx-auto mb-4" />
          <p className="text-slate-600">No cash runway data available</p>
        </div>
      </div>
    );
  }

  const formatCash = (amount: number) => {
    if (amount >= 1_000_000_000) {
      return `$${(amount / 1_000_000_000).toFixed(2)}B`;
    }
    if (amount >= 1_000_000) {
      return `$${(amount / 1_000_000).toFixed(2)}M`;
    }
    return `$${amount.toLocaleString()}`;
  };

  const formatCashCompact = (amount: number) => {
    if (amount >= 1_000_000_000) {
      return `$${(amount / 1_000_000_000).toFixed(1)}B`;
    }
    if (amount >= 1_000_000) {
      return `$${(amount / 1_000_000).toFixed(0)}M`;
    }
    return `$${(amount / 1000).toFixed(0)}K`;
  };

  const isBurningCash = data.quarterly_burn_rate < 0;

  // Preparar datos para Recharts - usar historial real si existe, sino proyección
  const useHistory = data.history && data.history.length > 0;
  const hasProjection = data.projection && data.projection.length > 0;
  
  // Si no hay datos para graficar, no renderizar
  if (!useHistory && !hasProjection) {
    console.log("No chart data available", { useHistory, hasProjection, data });
  }
  
  const chartData = useHistory
    ? data.history!.slice(-20).map((point, index, arr) => ({
        month: new Date(point.date).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
        cash: point.cash,
        isCurrent: index === arr.length - 1,
        isDepleted: false,
      }))
    : hasProjection
    ? data.projection.map((month, index) => ({
        month: new Date(month.date).toLocaleDateString('en-US', { month: 'short' }),
        cash: month.estimated_cash,
        isCurrent: index === 0,
        isDepleted: !month.estimated_cash || month.estimated_cash <= 0,
      }))
    : [];

  return (
    <>
      {/* Cash Info */}
      <h4 className="text-base font-semibold text-slate-900 mb-3">Cash Runway</h4>
      <div className="flex items-center gap-6 text-sm mb-4 pb-3 border-b border-slate-200">
        <div>
          <span className="text-slate-500">Cash:</span> <span className="font-bold ml-1">{formatCash(data.current_cash)}</span>
        </div>
        <div>
          <span className="text-slate-500">Burn:</span> <span className={`font-bold ml-1 ${isBurningCash ? 'text-red-600' : 'text-green-600'}`}>
            {formatCash(Math.abs(data.quarterly_burn_rate))}/Q {isBurningCash ? '↓' : '↑'}
          </span>
        </div>
        <div>
          <span className="text-slate-500">Runway:</span> <span className="font-bold ml-1">
            {data.estimated_runway_months !== null 
              ? `${data.estimated_runway_months.toFixed(1)} months`
              : <span className="text-green-600">Infinite</span>
            }
          </span>
        </div>
        {data.runway_risk_level === "critical" && (
          <div className="flex items-center gap-1 px-2 py-1 bg-red-100 text-red-700 rounded text-xs font-bold">
            <AlertCircle className="h-3 w-3" />
            CRITICAL
          </div>
        )}
      </div>

      {/* Cash History Chart */}
      {chartData.length > 0 && (
        <>
          <h4 className="text-base font-semibold text-slate-900 mb-3">
            {useHistory ? `Historical Cash Position (${chartData.length} quarters)` : 'Cash Position Projection (12 months)'}
          </h4>
        
          <div className="h-64 border border-slate-200 bg-white rounded-lg p-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: useHistory ? 20 : 5 }}>
                <XAxis 
                  dataKey="month" 
                  tick={{ fontSize: 11, fill: '#64748b' }}
                  tickLine={false}
                  axisLine={{ stroke: '#e2e8f0' }}
                  angle={useHistory ? -45 : 0}
                  textAnchor={useHistory ? "end" : "middle"}
                  height={useHistory ? 50 : 30}
                  interval={useHistory ? "preserveStartEnd" : 0}
                />
                <YAxis 
                  tick={{ fontSize: 12, fill: '#64748b' }}
                  tickLine={false}
                  axisLine={{ stroke: '#e2e8f0' }}
                  tickFormatter={formatCashCompact}
                  width={60}
                />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#1e293b', 
                    border: 'none', 
                    borderRadius: '8px',
                    boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)',
                    padding: '12px'
                  }}
                  labelStyle={{ color: '#f1f5f9', fontWeight: 600, marginBottom: '4px' }}
                  itemStyle={{ color: '#cbd5e1' }}
                  formatter={(value: number) => [formatCash(value), 'Cash']}
                  cursor={{ fill: 'rgba(148, 163, 184, 0.1)' }}
                />
                <Bar dataKey="cash" radius={[8, 8, 0, 0]} maxBarSize={useHistory ? 35 : 40}>
                  {chartData.map((entry, index) => (
                    <Cell 
                      key={`cell-${index}`}
                      fill={entry.isDepleted ? '#ef4444' : entry.isCurrent ? '#2563eb' : '#60a5fa'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Legend */}
          <div className="flex items-center justify-center gap-6 mt-4">
            {useHistory ? (
              <>
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 bg-blue-400 rounded" />
                  <span className="text-xs text-slate-600 font-medium">Historical</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 bg-blue-600 rounded" />
                  <span className="text-xs text-slate-600 font-medium">Latest Quarter</span>
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 bg-blue-600 rounded" />
                  <span className="text-xs text-slate-600 font-medium">Current</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 bg-blue-400 rounded" />
                  <span className="text-xs text-slate-600 font-medium">Projected</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 bg-red-500 rounded" />
                  <span className="text-xs text-slate-600 font-medium">Depleted</span>
                </div>
              </>
            )}
          </div>
        </>
      )}
    </>
  );
}
