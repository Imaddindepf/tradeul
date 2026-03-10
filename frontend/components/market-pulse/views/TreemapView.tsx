import { memo, useMemo, useCallback } from 'react';
import { Treemap, ResponsiveContainer, Tooltip } from 'recharts';
import { useContainerSize } from '../hooks/useContainerSize';
import type { PulseViewProps } from '../types';

function fmtName(n: string, tab: string) {
  if (tab === 'themes') return n.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  return n;
}

function interpolateColor(change: number): string {
  const clamped = Math.max(-5, Math.min(5, change));
  const t = (clamped + 5) / 10; // 0 = red, 0.5 = gray, 1 = green

  // Red (#EF4444) -> Gray (#9CA3AF) -> Green (#10B981)
  if (t < 0.5) {
    const r = t / 0.5;
    return `rgb(${Math.round(239 + (156 - 239) * r)}, ${Math.round(68 + (163 - 68) * r)}, ${Math.round(68 + (175 - 68) * r)})`;
  }
  const r = (t - 0.5) / 0.5;
  return `rgb(${Math.round(156 + (16 - 156) * r)}, ${Math.round(163 + (185 - 163) * r)}, ${Math.round(175 + (129 - 175) * r)})`;
}

function TreemapCell(props: any) {
  const { x, y, width, height, name, change, label, count, _original } = props;
  if (!width || !height || width < 2 || height < 2) return null;

  const color = interpolateColor(change || 0);
  const showText = width > 50 && height > 28;
  const showDetail = width > 80 && height > 40;

  return (
    <g>
      <rect
        x={x} y={y} width={width} height={height}
        fill={color}
        stroke="#fff"
        strokeWidth={1.5}
        rx={2}
        style={{ cursor: 'pointer' }}
      />
      {showText && (
        <>
          <text
            x={x + width / 2} y={y + height / 2 - (showDetail ? 6 : 0)}
            textAnchor="middle" dominantBaseline="central"
            fontSize={Math.min(11, width / 8)} fontWeight={700} fill="#fff"
            style={{ pointerEvents: 'none', textShadow: '0 1px 2px rgba(0,0,0,0.3)' }}
          >
            {label && label.length > width / 7 ? label.slice(0, Math.floor(width / 7)) + '..' : label}
          </text>
          {showDetail && (
            <text
              x={x + width / 2} y={y + height / 2 + 10}
              textAnchor="middle" dominantBaseline="central"
              fontSize={Math.min(10, width / 9)} fill="rgba(255,255,255,0.85)"
              fontFamily="monospace"
              style={{ pointerEvents: 'none', textShadow: '0 1px 2px rgba(0,0,0,0.3)' }}
            >
              {(change || 0) >= 0 ? '+' : ''}{(change || 0).toFixed(2)}%
            </text>
          )}
        </>
      )}
    </g>
  );
}

function TreemapTooltip({ active, payload }: any) {
  if (!active || !payload?.[0]) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-surface border border-border rounded-lg shadow-lg px-3 py-2 text-[11px]">
      <div className="font-semibold text-foreground mb-1">{d.label}</div>
      <div className="flex items-center gap-2">
        <span className="text-muted-fg">Wtd Change:</span>
        <span className={d.change >= 0 ? 'text-emerald-600 font-semibold' : 'text-red-500 font-semibold'}>
          {d.change >= 0 ? '+' : ''}{d.change?.toFixed(2)}%
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-muted-fg">Market Cap:</span>
        <span className="font-medium">
          {d.size >= 1e12 ? `$${(d.size / 1e12).toFixed(1)}T` :
           d.size >= 1e9 ? `$${(d.size / 1e9).toFixed(1)}B` :
           d.size >= 1e6 ? `$${(d.size / 1e6).toFixed(0)}M` : `$${d.size?.toLocaleString()}`}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-muted-fg">Tickers:</span>
        <span className="font-medium">{d.count}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-muted-fg">Breadth:</span>
        <span className="font-medium">{((d.breadth || 0) * 100).toFixed(0)}%</span>
      </div>
    </div>
  );
}

function TreemapView({ data, activeTab, onSelect }: PulseViewProps) {
  const { ref, size } = useContainerSize();

  const treemapData = useMemo(() =>
    data
      .filter(entry => (entry.total_market_cap || 0) > 0)
      .map(entry => ({
        name: entry.name,
        label: fmtName(entry.name, activeTab),
        size: entry.total_market_cap || 1,
        change: entry.weighted_change || 0,
        count: entry.count || 0,
        breadth: entry.breadth || 0,
        _original: entry,
      }))
      .sort((a, b) => b.size - a.size),
    [data, activeTab],
  );

  const handleClick = useCallback((node: any) => {
    if (node?._original) onSelect(node._original);
  }, [onSelect]);

  return (
    <div ref={ref} className="flex-1 overflow-hidden relative">
      {size.width > 0 && size.height > 0 && treemapData.length > 0 && (
        <ResponsiveContainer width="100%" height="100%">
          <Treemap
            data={treemapData}
            dataKey="size"
            nameKey="label"
            content={<TreemapCell />}
            onClick={handleClick}
            isAnimationActive={false}
          >
            <Tooltip content={<TreemapTooltip />} />
          </Treemap>
        </ResponsiveContainer>
      )}
      {treemapData.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-[11px] text-muted-fg">No market cap data available</span>
        </div>
      )}
    </div>
  );
}

export default memo(TreemapView);
