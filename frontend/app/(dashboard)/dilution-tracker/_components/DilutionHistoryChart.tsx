"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

interface DilutionHistoryData {
  history: Array<{
    date: string;
    shares: number;
  }>;
  dilution_1y: number | null;
  dilution_3y: number | null;
  dilution_5y: number | null;
}

interface DilutionHistoryChartProps {
  data: DilutionHistoryData | null;
  loading?: boolean;
}

export function DilutionHistoryChart({ data, loading = false }: DilutionHistoryChartProps) {
  if (loading || !data || !data.history || data.history.length === 0) {
    return null;
  }

  const formatShares = (shares: number) => {
    if (shares >= 1_000_000_000) return `${(shares / 1_000_000_000).toFixed(2)}B`;
    if (shares >= 1_000_000) return `${(shares / 1_000_000).toFixed(2)}M`;
    return shares.toLocaleString();
  };

  const formatSharesCompact = (shares: number) => {
    if (shares >= 1_000_000_000) return `${(shares / 1_000_000_000).toFixed(1)}B`;
    if (shares >= 1_000_000) return `${(shares / 1_000_000).toFixed(0)}M`;
    return `${(shares / 1000).toFixed(0)}K`;
  };

  // Mostrar TODOS los datos disponibles
  const validHistory = data.history.filter(h => h.shares && h.shares > 0);
  
  if (validHistory.length === 0) return null;

  // Limitar a los últimos 20 quarters para mantener la gráfica compacta
  const displayHistory = validHistory.slice(-20);

  // Preparar datos para Recharts
  const chartData = displayHistory.map((point, index) => {
    const date = new Date(point.date);
    return {
      date: date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
      shares: point.shares,
      isLatest: index === displayHistory.length - 1,
    };
  });

  const formatPercent = (value: number | null) => {
    if (value === null) return 'N/A';
    return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
  };

  return (
    <>
      {/* Title & Metrics */}
      <div className="flex items-center justify-between mb-4">
        <h4 className="text-base font-semibold text-slate-900">
          Historical Shares Outstanding ({displayHistory.length} quarters)
        </h4>
        
        {/* Dilution Metrics */}
        <div className="flex items-center gap-6 text-sm">
          <div>
            <span className="text-slate-500">1-Year:</span>
            <span className={`ml-2 font-bold ${
              data.dilution_1y && data.dilution_1y > 0 
                ? 'text-red-600' 
                : data.dilution_1y && data.dilution_1y < 0 
                ? 'text-green-600' 
                : 'text-slate-600'
            }`}>
              {formatPercent(data.dilution_1y)}
            </span>
          </div>
          <div>
            <span className="text-slate-500">3-Year:</span>
            <span className={`ml-2 font-bold ${
              data.dilution_3y && data.dilution_3y > 0 
                ? 'text-red-600' 
                : data.dilution_3y && data.dilution_3y < 0 
                ? 'text-green-600' 
                : 'text-slate-600'
            }`}>
              {formatPercent(data.dilution_3y)}
            </span>
          </div>
          <div>
            <span className="text-slate-500">5-Year:</span>
            <span className={`ml-2 font-bold ${
              data.dilution_5y && data.dilution_5y > 0 
                ? 'text-red-600' 
                : data.dilution_5y && data.dilution_5y < 0 
                ? 'text-green-600' 
                : 'text-slate-600'
            }`}>
              {formatPercent(data.dilution_5y)}
            </span>
          </div>
        </div>
      </div>
      
      {/* Chart profesional con Recharts */}
      <div className="h-64 border border-slate-200 bg-white rounded-lg p-4">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 20 }}>
            <XAxis 
              dataKey="date" 
              tick={{ fontSize: 11, fill: '#64748b' }}
              tickLine={false}
              axisLine={{ stroke: '#e2e8f0' }}
              angle={-45}
              textAnchor="end"
              height={50}
              interval="preserveStartEnd"
            />
            <YAxis 
              tick={{ fontSize: 12, fill: '#64748b' }}
              tickLine={false}
              axisLine={{ stroke: '#e2e8f0' }}
              tickFormatter={formatSharesCompact}
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
              formatter={(value: number) => [formatShares(value), 'Shares']}
              cursor={{ fill: 'rgba(148, 163, 184, 0.1)' }}
            />
            <Bar dataKey="shares" radius={[8, 8, 0, 0]} maxBarSize={35}>
              {chartData.map((entry, index) => (
                <Cell 
                  key={`cell-${index}`}
                  fill={entry.isLatest ? '#2563eb' : '#60a5fa'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      
      {/* Info */}
      <div className="text-xs text-slate-500 mt-3 text-center">
        Showing {displayHistory.length} quarters from {new Date(displayHistory[0].date).toLocaleDateString('en-US', {month: 'short', year: 'numeric'})} to {new Date(displayHistory[displayHistory.length-1].date).toLocaleDateString('en-US', {month: 'short', year: 'numeric'})}
      </div>
    </>
  );
}
