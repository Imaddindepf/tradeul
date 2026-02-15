'use client';

import { memo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import { BarChart3 } from 'lucide-react';

interface AutoChartProps {
  headers: string[];
  rows: string[][];
}

/**
 * AutoBarChart - Generates an interactive bar chart from table data.
 * Finds the first text column (label) and first numeric column (value)
 * and renders a Recharts bar chart with contextual colors.
 */
export const AutoBarChart = memo(function AutoBarChart({ headers, rows }: AutoChartProps) {
  // Find first numeric column (skip column 0 which is labels)
  let valueColIdx = -1;
  for (let i = 1; i < headers.length; i++) {
    const sample = rows[0]?.[i]?.replace(/[,$%*]/g, '').trim() || '';
    if (!isNaN(parseFloat(sample)) && sample.length > 0) {
      valueColIdx = i;
      break;
    }
  }
  if (valueColIdx === -1 || rows.length < 2) return null;

  const data = rows.slice(0, 25).map(row => ({
    name: (row[0] || '').replace(/\*\*/g, '').trim(),
    value: parseFloat(row[valueColIdx]?.replace(/[,$%*]/g, '').trim() || '0') || 0,
  }));

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    return (
      <div className="bg-white border border-slate-200 rounded-lg shadow-lg px-3 py-2 text-[11px]">
        <p className="font-semibold text-slate-800">{label}</p>
        <p className="text-indigo-600 font-mono">
          {headers[valueColIdx]}: {payload[0]?.value?.toLocaleString()}
        </p>
      </div>
    );
  };

  return (
    <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-3">
        <BarChart3 className="w-4 h-4 text-indigo-500" />
        <span className="text-[12px] font-semibold text-slate-700">
          {headers[valueColIdx]} by {headers[0]}
        </span>
      </div>
      <div style={{ width: '100%', height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              axisLine={false}
              tickLine={false}
              interval={0}
              angle={data.length > 10 ? -45 : 0}
              textAnchor={data.length > 10 ? 'end' : 'middle'}
              height={data.length > 10 ? 60 : 30}
            />
            <YAxis
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              axisLine={false}
              tickLine={false}
              width={55}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(99,102,241,0.05)' }} />
            <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={40}>
              {data.map((entry, i) => (
                <Cell
                  key={i}
                  fill={entry.value >= 0 ? '#6366f1' : '#ef4444'}
                  fillOpacity={0.85}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
});
