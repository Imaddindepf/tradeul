"use client";

import { AlertCircle } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

interface RealTimeEstimate {
  report_date: string;
  days_elapsed: number;
  prorated_burn: number;
  capital_raise: number;
  current_cash_estimate: number;
  raise_details: Array<{
    date: string;
    type: string;
    amount: number;
  }>;
}

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
  real_time_estimate?: RealTimeEstimate;
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
    // Handle negative numbers for formatting
    const isNegative = amount < 0;
    const absAmount = Math.abs(amount);
    const prefix = isNegative ? "-$" : "$";

    if (absAmount >= 1_000_000_000) {
      return `${prefix}${(absAmount / 1_000_000_000).toFixed(2)}B`;
    }
    if (absAmount >= 1_000_000) {
      return `${prefix}${(absAmount / 1_000_000).toFixed(2)}M`;
    }
    return `${prefix}${absAmount.toLocaleString()}`;
  };

  const formatCashCompact = (amount: number) => {
    const isNegative = amount < 0;
    const absAmount = Math.abs(amount);
    const prefix = isNegative ? "-$" : "$";

    if (absAmount >= 1_000_000_000) {
      return `${prefix}${(absAmount / 1_000_000_000).toFixed(1)}B`;
    }
    if (absAmount >= 1_000_000) {
      return `${prefix}${(absAmount / 1_000_000).toFixed(0)}M`;
    }
    return `${prefix}${(absAmount / 1000).toFixed(0)}K`;
  };

  const isBurningCash = data.quarterly_burn_rate < 0;

  // Preparar datos para Recharts - usar historial real si existe, sino proyección
  const useHistory = data.history && data.history.length > 0;
  
  let chartData: Array<{
    month: string;
    cash: number;
    type: string;
    isCurrent: boolean;
    isDepleted?: boolean;
  }> = [];

  if (useHistory) {
    chartData = data.history!.slice(-20).map((point, index, arr) => ({
        month: new Date(point.date).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
        cash: point.cash,
      type: 'historical',
        isCurrent: index === arr.length - 1,
    }));
  } else if (data.projection && data.projection.length > 0) {
    chartData = data.projection.map((month, index) => ({
        month: new Date(month.date).toLocaleDateString('en-US', { month: 'short' }),
        cash: month.estimated_cash,
      type: 'projection',
        isCurrent: index === 0,
        isDepleted: !month.estimated_cash || month.estimated_cash <= 0,
    }));
  }

  // 🚀 Insertar Real-Time Estimate Bars si existen
  if (data.real_time_estimate && useHistory) {
    // 1. Prorated Burn (Gasto estimado desde el último reporte)
    chartData.push({
      month: "Burn (Est)",
      cash: data.real_time_estimate.prorated_burn,
      type: 'estimate_burn',
      isCurrent: false
    });

    // 2. Capital Raise (Si hubo)
    if (data.real_time_estimate.capital_raise > 0) {
      chartData.push({
        month: "Cap Raise",
        cash: data.real_time_estimate.capital_raise,
        type: 'estimate_raise',
        isCurrent: false
      });
    }

    // 3. Current Estimate (Saldo final estimado)
    chartData.push({
      month: "Current Est",
      cash: data.real_time_estimate.current_cash_estimate,
      type: 'estimate_total',
      isCurrent: true
    });
  }

  if (chartData.length === 0) {
    console.log("No chart data available", { useHistory, data });
  }

  // Helper para colores
  const getBarColor = (entry: any) => {
    if (entry.type === 'estimate_burn') return '#ef4444'; // Red for burn outflow
    if (entry.type === 'estimate_raise') return '#22c55e'; // Green for capital raise
    if (entry.type === 'estimate_total') return '#8b5cf6'; // Purple for final estimate
    if (entry.isDepleted) return '#ef4444';
    if (entry.isCurrent) return '#2563eb';
    return '#60a5fa';
  };

  return (
    <>
      {/* Cash Info */}
      <h4 className="text-base font-semibold text-slate-900 mb-3">Cash Runway</h4>
      <div className="flex items-center gap-6 text-sm mb-4 pb-3 border-b border-slate-200">
        <div>
          <span className="text-slate-500">Cash (Reported):</span> <span className="font-bold ml-1">{formatCash(data.current_cash)}</span>
        </div>
        {data.real_time_estimate && (
           <div>
             <span className="text-slate-500">Cash (Est):</span> <span className="font-bold ml-1 text-purple-600">{formatCash(data.real_time_estimate.current_cash_estimate)}</span>
           </div>
        )}
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
            {useHistory ? `Historical Cash & Real-Time Estimate` : 'Cash Position Projection (12 months)'}
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
                  height={useHistory ? 60 : 30}
                  interval={0} 
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
                  formatter={(value: number, name: string, props: any) => {
                    let label = 'Cash';
                    if (props.payload.type === 'estimate_burn') label = 'Est. Burn';
                    if (props.payload.type === 'estimate_raise') label = 'Cap. Raise';
                    if (props.payload.type === 'estimate_total') label = 'Est. Total';
                    return [formatCash(value), label];
                  }}
                  cursor={{ fill: 'rgba(148, 163, 184, 0.1)' }}
                />
                <Bar dataKey="cash" radius={[4, 4, 0, 0]} maxBarSize={40}>
                  {chartData.map((entry, index) => (
                    <Cell 
                      key={`cell-${index}`}
                      fill={getBarColor(entry)}
                      stroke={entry.type?.startsWith('estimate') ? 'rgba(0,0,0,0.2)' : 'none'}
                      strokeDasharray={entry.type === 'estimate_total' ? '4 4' : 'none'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Legend */}
          <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 mt-4">
            {useHistory ? (
              <>
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 bg-blue-400 rounded" />
                  <span className="text-xs text-slate-600 font-medium">Historical</span>
            </div>
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 bg-blue-600 rounded" />
                  <span className="text-xs text-slate-600 font-medium">Latest Reported</span>
                </div>
                {data.real_time_estimate && (
                  <>
                    <div className="flex items-center gap-2">
                      <div className="h-3 w-3 bg-red-500 rounded" />
                      <span className="text-xs text-slate-600 font-medium">Est. Burn</span>
                    </div>
                    {data.real_time_estimate.capital_raise > 0 && (
                      <div className="flex items-center gap-2">
                        <div className="h-3 w-3 bg-green-500 rounded" />
                        <span className="text-xs text-slate-600 font-medium">Cap Raise</span>
                      </div>
                    )}
                    <div className="flex items-center gap-2">
                      <div className="h-3 w-3 bg-purple-500 rounded" />
                      <span className="text-xs text-slate-600 font-medium">Real-Time Est</span>
        </div>
                  </>
                )}
              </>
            ) : (
              // ... existing projection legend
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
