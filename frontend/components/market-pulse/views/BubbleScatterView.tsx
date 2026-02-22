import { memo, useMemo, useState, useCallback } from 'react';
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts';
import { useContainerSize } from '../hooks/useContainerSize';
import type { PulseViewProps } from '../types';

const AXIS_OPTIONS = [
  { key: 'weighted_change', label: 'Wtd Change' },
  { key: 'avg_change', label: 'Avg Change' },
  { key: 'avg_change_5d', label: '5D Change' },
  { key: 'avg_change_10d', label: '10D Change' },
  { key: 'avg_change_20d', label: '20D Change' },
  { key: 'avg_rvol', label: 'Avg RVOL' },
  { key: 'avg_rsi', label: 'RSI 1m' },
  { key: 'avg_daily_rsi', label: 'RSI Daily' },
  { key: 'breadth', label: 'Breadth' },
  { key: 'avg_bb_position', label: 'BB Position' },
  { key: 'avg_from_52w_high', label: '% from 52W Hi' },
  { key: 'avg_pos_in_range', label: 'Range Pos' },
  { key: 'avg_dist_sma20', label: 'Dist SMA20' },
  { key: 'avg_dist_sma50', label: 'Dist SMA50' },
  { key: 'avg_atr_pct', label: 'ATR%' },
  { key: 'avg_gap_pct', label: 'Gap%' },
] as const;

function fmtName(n: string, tab: string) {
  if (tab === 'themes') return n.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  return n;
}

function BubbleTooltip({ active, payload }: any) {
  if (!active || !payload?.[0]) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-lg px-3 py-2 text-[11px]">
      <div className="font-semibold text-slate-900 mb-1">{d.label}</div>
      <div className="flex items-center gap-2">
        <span className="text-slate-500">{d.xLabel}:</span>
        <span className="font-semibold font-mono">{d.x?.toFixed(2)}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-slate-500">{d.yLabel}:</span>
        <span className="font-semibold font-mono">{d.y?.toFixed(2)}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-slate-500">Tickers:</span>
        <span className="font-medium">{d.count}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-slate-500">Wtd Change:</span>
        <span className={d.change >= 0 ? 'text-emerald-600 font-semibold' : 'text-red-500 font-semibold'}>
          {d.change >= 0 ? '+' : ''}{d.change?.toFixed(2)}%
        </span>
      </div>
    </div>
  );
}

function BubbleScatterView({ data, activeTab, onSelect }: PulseViewProps) {
  const { ref, size } = useContainerSize();
  const [xAxis, setXAxis] = useState('avg_change_5d');
  const [yAxis, setYAxis] = useState('avg_change');

  const xOpt = AXIS_OPTIONS.find(o => o.key === xAxis);
  const yOpt = AXIS_OPTIONS.find(o => o.key === yAxis);

  const scatterData = useMemo(() =>
    data.map(entry => ({
      x: (entry as any)[xAxis] ?? 0,
      y: (entry as any)[yAxis] ?? 0,
      z: entry.count || 1,
      label: fmtName(entry.name, activeTab),
      xLabel: xOpt?.label || xAxis,
      yLabel: yOpt?.label || yAxis,
      count: entry.count || 0,
      change: entry.weighted_change || 0,
      _original: entry,
    })),
    [data, xAxis, yAxis, activeTab, xOpt, yOpt],
  );

  const handleClick = useCallback((d: any) => {
    if (d?._original) onSelect(d._original);
  }, [onSelect]);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Axis selectors */}
      <div className="flex items-center gap-3 px-3 py-1.5 border-b border-slate-100 shrink-0">
        <div className="flex items-center gap-1.5">
          <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">X</span>
          <select
            value={xAxis}
            onChange={e => setXAxis(e.target.value)}
            className="text-[10px] px-1.5 py-0.5 border border-slate-200 rounded bg-white text-slate-700 focus:outline-none focus:border-blue-400 appearance-none cursor-pointer"
          >
            {AXIS_OPTIONS.map(o => (
              <option key={o.key} value={o.key}>{o.label}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Y</span>
          <select
            value={yAxis}
            onChange={e => setYAxis(e.target.value)}
            className="text-[10px] px-1.5 py-0.5 border border-slate-200 rounded bg-white text-slate-700 focus:outline-none focus:border-blue-400 appearance-none cursor-pointer"
          >
            {AXIS_OPTIONS.map(o => (
              <option key={o.key} value={o.key}>{o.label}</option>
            ))}
          </select>
        </div>
        <span className="text-[9px] text-slate-400 ml-auto">size = ticker count</span>
      </div>

      {/* Chart */}
      <div ref={ref} className="flex-1 overflow-hidden">
        {size.width > 0 && size.height > 0 && (
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 16, right: 24, bottom: 36, left: 24 }}>
              <XAxis
                type="number" dataKey="x" name={xOpt?.label}
                tick={{ fontSize: 10 }}
                axisLine={{ stroke: '#E2E8F0' }} tickLine={false}
                label={{ value: xOpt?.label || xAxis, position: 'bottom', offset: 16, fontSize: 10, fill: '#94A3B8' }}
              />
              <YAxis
                type="number" dataKey="y" name={yOpt?.label}
                tick={{ fontSize: 10 }}
                axisLine={{ stroke: '#E2E8F0' }} tickLine={false}
                label={{ value: yOpt?.label || yAxis, angle: -90, position: 'insideLeft', offset: -8, fontSize: 10, fill: '#94A3B8' }}
              />
              <ZAxis type="number" dataKey="z" range={[40, 400]} />
              <ReferenceLine x={0} stroke="#CBD5E1" strokeDasharray="4 4" />
              <ReferenceLine y={0} stroke="#CBD5E1" strokeDasharray="4 4" />
              <Tooltip content={<BubbleTooltip />} />
              <Scatter
                data={scatterData}
                cursor="pointer"
                onClick={handleClick}
                isAnimationActive={false}
              >
                {scatterData.map((d, i) => (
                  <Cell
                    key={i}
                    fill={d.change >= 0 ? '#2563EB' : '#EC4899'}
                    fillOpacity={0.6}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

export default memo(BubbleScatterView);
