import { memo, useMemo, useCallback } from 'react';
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, Tooltip,
  ResponsiveContainer, ReferenceLine, Label,
} from 'recharts';
import { useContainerSize } from '../hooks/useContainerSize';
import type { PulseViewProps } from '../types';

function fmtName(n: string, tab: string) {
  if (tab === 'themes') return n.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  return n;
}

function BreadthTooltip({ active, payload }: any) {
  if (!active || !payload?.[0]) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-surface border border-border rounded-lg shadow-lg px-3 py-2 text-[11px]">
      <div className="font-semibold text-foreground mb-1">{d.label}</div>
      <div className="flex items-center gap-2">
        <span className="text-muted-fg">Breadth:</span>
        <span className="font-medium">{(d.x * 100).toFixed(0)}%</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-muted-fg">Wtd Change:</span>
        <span className={d.y >= 0 ? 'text-emerald-600 font-semibold' : 'text-red-500 font-semibold'}>
          {d.y >= 0 ? '+' : ''}{d.y.toFixed(2)}%
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-muted-fg">Avg Change:</span>
        <span className="font-medium">{d.avgChange >= 0 ? '+' : ''}{d.avgChange.toFixed(2)}%</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-muted-fg">Tickers:</span>
        <span className="font-medium">{d.count}</span>
      </div>
      {d.isDivergent && (
        <div className="text-amber-600 font-semibold mt-0.5">Breadth divergence</div>
      )}
    </div>
  );
}

function BreadthMonitorView({ data, activeTab, onSelect }: PulseViewProps) {
  const { ref, size } = useContainerSize();

  const { normalDots, divergentDots } = useMemo(() => {
    const normal: any[] = [];
    const divergent: any[] = [];

    data.forEach(entry => {
      const breadth = entry.breadth ?? 0.5;
      const change = entry.weighted_change || 0;
      const isDivergent = (entry as any)._divergence === true;

      const point = {
        x: breadth,
        y: change,
        z: entry.count || 1,
        label: fmtName(entry.name, activeTab),
        count: entry.count || 0,
        avgChange: entry.avg_change || 0,
        isDivergent,
        _original: entry,
      };

      if (isDivergent) divergent.push(point);
      else normal.push(point);
    });

    return { normalDots: normal, divergentDots: divergent };
  }, [data, activeTab]);

  const handleClick = useCallback((d: any) => {
    if (d?._original) onSelect(d._original);
  }, [onSelect]);

  return (
    <div ref={ref} className="flex-1 overflow-hidden relative">
      {size.width > 0 && size.height > 0 && (
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 20, right: 28, bottom: 40, left: 28 }}>
            <XAxis
              type="number" dataKey="x" name="Breadth"
              domain={[0, 1]} tick={{ fontSize: 10 }}
              tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
              axisLine={{ stroke: '#E2E8F0' }} tickLine={false}
              label={{ value: '% Advancing (Breadth)', position: 'bottom', offset: 18, fontSize: 10, fill: '#94A3B8' }}
            />
            <YAxis
              type="number" dataKey="y" name="Wtd Change"
              tick={{ fontSize: 10 }}
              tickFormatter={(v: number) => `${v.toFixed(1)}%`}
              axisLine={{ stroke: '#E2E8F0' }} tickLine={false}
              label={{ value: 'Wtd Change %', angle: -90, position: 'insideLeft', offset: -8, fontSize: 10, fill: '#94A3B8' }}
            />
            <ZAxis type="number" dataKey="z" range={[30, 300]} />

            {/* Quadrant dividers */}
            <ReferenceLine x={0.5} stroke="#CBD5E1" strokeDasharray="4 4" />
            <ReferenceLine y={0} stroke="#CBD5E1" strokeDasharray="4 4" />

            {/* Quadrant labels rendered INSIDE the SVG chart area via ReferenceLine + Label */}
            <ReferenceLine x={0.85} stroke="transparent" ifOverflow="extendDomain">
              <Label value="Strong Bull" position="insideTop" offset={8} fill="#10B981" fontSize={9} fontWeight={700} opacity={0.35} />
            </ReferenceLine>
            <ReferenceLine x={0.15} stroke="transparent" ifOverflow="extendDomain">
              <Label value="Divergence" position="insideTop" offset={8} fill="#F59E0B" fontSize={9} fontWeight={700} opacity={0.35} />
            </ReferenceLine>
            <ReferenceLine x={0.85} stroke="transparent" ifOverflow="extendDomain">
              <Label value="Divergence" position="insideBottom" offset={8} fill="#F59E0B" fontSize={9} fontWeight={700} opacity={0.35} />
            </ReferenceLine>
            <ReferenceLine x={0.15} stroke="transparent" ifOverflow="extendDomain">
              <Label value="Weak Bear" position="insideBottom" offset={8} fill="#EF4444" fontSize={9} fontWeight={700} opacity={0.35} />
            </ReferenceLine>

            <Tooltip content={<BreadthTooltip />} />
            <Scatter
              data={normalDots}
              fill="#2563EB"
              fillOpacity={0.6}
              cursor="pointer"
              onClick={handleClick}
              isAnimationActive={false}
            />
            {divergentDots.length > 0 && (
              <Scatter
                data={divergentDots}
                fill="#F59E0B"
                fillOpacity={0.8}
                cursor="pointer"
                onClick={handleClick}
                isAnimationActive={false}
              />
            )}
          </ScatterChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

export default memo(BreadthMonitorView);
