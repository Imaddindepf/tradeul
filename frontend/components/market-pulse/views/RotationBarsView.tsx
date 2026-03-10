import { memo, useMemo, useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LabelList } from 'recharts';
import { useContainerSize } from '../hooks/useContainerSize';
import type { PulseViewProps } from '../types';

function fmtName(n: string, tab: string) {
  if (tab === 'themes') return n.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  return n;
}

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.[0]) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-surface border border-border rounded-lg shadow-lg px-3 py-2 text-[11px]">
      <div className="font-semibold text-foreground mb-1">{d.label}</div>
      <div className="flex items-center gap-2">
        <span className="text-muted-fg">Wtd Change:</span>
        <span className={d.change >= 0 ? 'text-emerald-600 font-semibold' : 'text-red-500 font-semibold'}>
          {d.change >= 0 ? '+' : ''}{d.change.toFixed(2)}%
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-muted-fg">Avg Change:</span>
        <span className="font-medium">{d.avgChange >= 0 ? '+' : ''}{d.avgChange.toFixed(2)}%</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-muted-fg">Breadth:</span>
        <span className="font-medium">{(d.breadth * 100).toFixed(0)}%</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-muted-fg">Tickers:</span>
        <span className="font-medium">{d.count}</span>
      </div>
      {d.rankShift !== 0 && (
        <div className="flex items-center gap-2">
          <span className="text-muted-fg">Rank Shift:</span>
          <span className={d.rankShift > 0 ? 'text-emerald-600 font-semibold' : 'text-red-500 font-semibold'}>
            {d.rankShift > 0 ? '\u25B2' : '\u25BC'}{Math.abs(d.rankShift)}
          </span>
        </div>
      )}
    </div>
  );
}

// Render the % value label OUTSIDE the bar tip
function OutsideLabel(props: any) {
  const { x, y, width, height, value, index } = props;
  const d = props.data?.[index];
  if (!d || height == null) return null;
  const isPos = value >= 0;
  // Position outside the bar end
  const labelX = isPos ? x + width + 4 : x - 4;
  const labelY = y + height / 2;
  const shift = d.rankShift || 0;
  const shiftStr = shift !== 0 ? ` ${shift > 0 ? '\u25B2' : '\u25BC'}${Math.abs(shift)}` : '';
  return (
    <text
      x={labelX} y={labelY}
      textAnchor={isPos ? 'start' : 'end'}
      dominantBaseline="central"
      fontSize={11} fontWeight={700} fontFamily="ui-monospace, monospace"
      fill={isPos ? '#059669' : '#DC2626'}
    >
      {isPos ? '+' : ''}{value.toFixed(2)}%{shiftStr}
    </text>
  );
}

function RotationBarsView({ data, activeTab, onSelect }: PulseViewProps) {
  const { ref, size } = useContainerSize();

  const barsData = useMemo(() =>
    [...data]
      .sort((a, b) => (b.weighted_change || 0) - (a.weighted_change || 0))
      .map(entry => ({
        name: entry.name,
        label: fmtName(entry.name, activeTab),
        change: entry.weighted_change || 0,
        avgChange: entry.avg_change || 0,
        breadth: entry.breadth || 0,
        count: entry.count || 0,
        rankShift: (entry as any)._rankShift ?? 0,
        _original: entry,
      })),
    [data, activeTab],
  );

  const handleClick = useCallback((_: any, idx: number) => {
    const d = barsData[idx];
    if (d?._original) onSelect(d._original);
  }, [onSelect, barsData]);

  // Compute dynamic sizing
  const rowH = Math.max(22, Math.min(32, (size.height - 40) / (barsData.length || 1)));
  const chartH = Math.max(size.height, barsData.length * rowH + 40);
  // Left margin for names — adapt to longest name
  const maxLabelLen = useMemo(() => Math.max(...barsData.map(d => d.label.length), 6), [barsData]);
  const leftMargin = Math.min(180, Math.max(80, maxLabelLen * 6.5));

  return (
    <div ref={ref} className="flex-1 overflow-auto">
      {size.width > 0 && size.height > 0 && (
        <ResponsiveContainer width="100%" height={chartH}>
          <BarChart
            data={barsData}
            layout="vertical"
            margin={{ top: 8, right: 80, left: 8, bottom: 8 }}
            barCategoryGap="18%"
          >
            <XAxis
              type="number"
              tick={{ fontSize: 10, fill: '#94A3B8' }}
              tickFormatter={(v: number) => `${v.toFixed(1)}%`}
              axisLine={{ stroke: '#E2E8F0' }}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="label"
              width={leftMargin}
              tick={{ fontSize: 11, fontWeight: 600, fill: '#334155' }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(148,163,184,0.06)' }} />
            <Bar
              dataKey="change"
              isAnimationActive={false}
              radius={[3, 3, 3, 3]}
              cursor="pointer"
              onClick={handleClick}
              maxBarSize={28}
            >
              {barsData.map((entry, i) => (
                <Cell key={i} fill={entry.change >= 0 ? '#10B981' : '#EF4444'} fillOpacity={0.75} />
              ))}
              <LabelList content={<OutsideLabel data={barsData} />} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

export default memo(RotationBarsView);
