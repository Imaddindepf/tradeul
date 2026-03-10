'use client';

import { memo, useState, useCallback, useRef, useMemo, useEffect } from 'react';
import { useRRG, type RRGGroup } from '@/hooks/useRRG';
import { Loader2, Play, Pause, RotateCcw } from 'lucide-react';
import type { PulseViewProps } from '../types';

// ── Quadrant config ──
const QUADRANTS = {
  leading:    { label: 'Leading',    color: '#22c55e', bg: 'rgba(34,197,94,0.06)' },
  weakening:  { label: 'Weakening',  color: '#eab308', bg: 'rgba(234,179,8,0.06)' },
  lagging:    { label: 'Lagging',    color: '#ef4444', bg: 'rgba(239,68,68,0.06)' },
  improving:  { label: 'Improving',  color: '#3b82f6', bg: 'rgba(59,130,246,0.06)' },
} as const;

const RS_OPTIONS = [
  { key: 'change_5d',  label: 'Short-term',  title: 'Based on 5-day performance. Best for swing trades (1-2 weeks)' },
  { key: 'change_10d', label: 'Medium-term', title: 'Based on 10-day performance. Best for positions (2-4 weeks)' },
  { key: 'change_20d', label: 'Long-term',   title: 'Based on 20-day performance. Best for macro trends (1-2 months)' },
];

const HEAD_OPTIONS = [
  { value: 5,  label: '1W' },
  { value: 10, label: '2W' },
  { value: 20, label: '1M' },
  { value: 40, label: '2M' },
];

const BENCHMARK_OPTIONS = [
  { key: 'none', label: 'Absolute',  title: 'Absolute performance of each group' },
  { key: 'spy',  label: 'vs SPY',    title: 'Performance relative to S&P 500' },
];

// ── Helpers ──

function fmtName(n: string, tab: string) {
  if (tab === 'themes') return n.split('_').map(w => w[0].toUpperCase() + w.slice(1)).join(' ');
  return n;
}

function getQuadrantColor(q: string) {
  return QUADRANTS[q as keyof typeof QUADRANTS]?.color || 'var(--color-muted-fg)';
}

function getQuadrantLabel(q: string) {
  return QUADRANTS[q as keyof typeof QUADRANTS]?.label || q;
}

/** Catmull-Rom spline path through all points (smooth curves) */
function linePath(
  pts: { x: number; y: number }[],
  sx: (v: number) => number,
  sy: (v: number) => number,
): string {
  if (pts.length < 2) return '';
  const p = pts.map(pt => ({ x: sx(pt.x), y: sy(pt.y) }));
  if (p.length === 2) return `M${p[0].x},${p[0].y}L${p[1].x},${p[1].y}`;

  const tension = 6;
  let d = `M${p[0].x},${p[0].y}`;
  for (let i = 0; i < p.length - 1; i++) {
    const p0 = p[Math.max(i - 1, 0)];
    const p1 = p[i];
    const p2 = p[i + 1];
    const p3 = p[Math.min(i + 2, p.length - 1)];
    const cp1x = p1.x + (p2.x - p0.x) / tension;
    const cp1y = p1.y + (p2.y - p0.y) / tension;
    const cp2x = p2.x - (p3.x - p1.x) / tension;
    const cp2y = p2.y - (p3.y - p1.y) / tension;
    d += `C${cp1x},${cp1y},${cp2x},${cp2y},${p2.x},${p2.y}`;
  }
  return d;
}

/** Compute nice tick marks for a given range centered on 100 */
function computeTicks(min: number, max: number): number[] {
  const range = max - min;
  let step: number;
  if (range <= 4) step = 0.5;
  else if (range <= 8) step = 1;
  else if (range <= 16) step = 2;
  else step = 5;

  const ticks: number[] = [];
  const start = Math.ceil(min / step) * step;
  for (let v = start; v <= max; v += step) {
    ticks.push(Math.round(v * 100) / 100);
  }
  if (!ticks.includes(100)) {
    ticks.push(100);
    ticks.sort((a, b) => a - b);
  }
  return ticks;
}

/** Distance from center (100, 100) */
function distFromCenter(x: number, y: number): number {
  return Math.sqrt((x - 100) ** 2 + (y - 100) ** 2);
}

// ── SVG Chart Component ──

const PADDING = { top: 30, right: 30, bottom: 40, left: 55 };

interface ChartProps {
  groups: RRGGroup[];
  width: number;
  height: number;
  activeTab: string;
  hoveredGroup: string | null;
  onHover: (name: string | null) => void;
  onSelect: (group: RRGGroup) => void;
  autoRange?: { x_min: number; x_max: number; y_min: number; y_max: number };
  animFrame: number; // 0 = show all, >0 = limit visible points
}

function RRGChart({ groups, width, height, activeTab, hoveredGroup, onHover, onSelect, autoRange, animFrame }: ChartProps) {
  const chartW = width - PADDING.left - PADDING.right;
  const chartH = height - PADDING.top - PADDING.bottom;

  const xMin = autoRange?.x_min ?? 96;
  const xMax = autoRange?.x_max ?? 104;
  const yMin = autoRange?.y_min ?? 96;
  const yMax = autoRange?.y_max ?? 104;
  const xRange = xMax - xMin;
  const yRange = yMax - yMin;

  const scaleX = useCallback((v: number) => PADDING.left + ((v - xMin) / xRange) * chartW, [chartW, xMin, xRange]);
  const scaleY = useCallback((v: number) => PADDING.top + ((yMax - v) / yRange) * chartH, [chartH, yMax, yRange]);

  const ticksX = useMemo(() => computeTicks(xMin, xMax), [xMin, xMax]);
  const ticksY = useMemo(() => computeTicks(yMin, yMax), [yMin, yMax]);

  const cx = scaleX(100);
  const cy = scaleY(100);

  const hoveredData = hoveredGroup ? groups.find(g => g.name === hoveredGroup) : null;

  return (
    <svg width={width} height={height} className="select-none">
      {/* Quadrant backgrounds */}
      {100 >= xMin && 100 <= xMax && 100 >= yMin && 100 <= yMax && (
        <>
          <rect x={cx} y={PADDING.top} width={scaleX(xMax) - cx} height={cy - PADDING.top}
            fill={QUADRANTS.leading.bg} />
          <rect x={PADDING.left} y={PADDING.top} width={cx - PADDING.left} height={cy - PADDING.top}
            fill={QUADRANTS.improving.bg} />
          <rect x={PADDING.left} y={cy} width={cx - PADDING.left} height={scaleY(yMin) - cy}
            fill={QUADRANTS.lagging.bg} />
          <rect x={cx} y={cy} width={scaleX(xMax) - cx} height={scaleY(yMin) - cy}
            fill={QUADRANTS.weakening.bg} />
        </>
      )}

      {/* Grid lines */}
      {ticksX.map(t => (
        <g key={`gx-${t}`}>
          <line x1={scaleX(t)} y1={PADDING.top} x2={scaleX(t)} y2={PADDING.top + chartH}
            stroke={t === 100 ? 'var(--color-muted-fg)' : 'var(--color-border)'}
            strokeWidth={t === 100 ? 1.5 : 0.5}
            strokeDasharray={t === 100 ? '' : '2,4'} />
          <text x={scaleX(t)} y={height - 8} textAnchor="middle"
            className="fill-muted-fg text-[9px]">{t}</text>
        </g>
      ))}
      {ticksY.map(t => (
        <g key={`gy-${t}`}>
          <line x1={PADDING.left} y1={scaleY(t)} x2={PADDING.left + chartW} y2={scaleY(t)}
            stroke={t === 100 ? 'var(--color-muted-fg)' : 'var(--color-border)'}
            strokeWidth={t === 100 ? 1.5 : 0.5}
            strokeDasharray={t === 100 ? '' : '2,4'} />
          <text x={PADDING.left - 8} y={scaleY(t) + 3} textAnchor="end"
            className="fill-muted-fg text-[9px]">{t}</text>
        </g>
      ))}

      {/* Axis titles */}
      <text x={PADDING.left + chartW / 2} y={height - 0} textAnchor="middle"
        className="fill-muted-fg text-[10px] font-semibold">Relative Strength</text>
      <text x={12} y={PADDING.top + chartH / 2} textAnchor="middle"
        className="fill-muted-fg text-[10px] font-semibold"
        transform={`rotate(-90, 12, ${PADDING.top + chartH / 2})`}>Momentum</text>

      {/* Quadrant corner labels */}
      {100 >= xMin && 100 <= xMax && 100 >= yMin && 100 <= yMax && (
        <>
          <text x={cx + (scaleX(xMax) - cx) / 2} y={PADDING.top + 16}
            textAnchor="middle" className="fill-emerald-500/40 text-[10px] font-bold uppercase">Leading</text>
          <text x={cx + (scaleX(xMax) - cx) / 2} y={PADDING.top + chartH - 6}
            textAnchor="middle" className="fill-yellow-500/40 text-[10px] font-bold uppercase">Weakening</text>
          <text x={PADDING.left + (cx - PADDING.left) / 2} y={PADDING.top + chartH - 6}
            textAnchor="middle" className="fill-red-500/40 text-[10px] font-bold uppercase">Lagging</text>
          <text x={PADDING.left + (cx - PADDING.left) / 2} y={PADDING.top + 16}
            textAnchor="middle" className="fill-primary/40 text-[10px] font-bold uppercase">Improving</text>
        </>
      )}

      {/* Chart border */}
      <rect x={PADDING.left} y={PADDING.top} width={chartW} height={chartH}
        fill="none" stroke="var(--color-border)" strokeWidth={1} />

      {/* Trails */}
      {groups.map(group => {
        const isHovered = hoveredGroup === group.name;
        const isOther = hoveredGroup && hoveredGroup !== group.name;
        const trailColor = getQuadrantColor(group.quadrant);
        const trailPts = group.trail;
        if (trailPts.length < 2) return null;

        const lastTrail = trailPts[trailPts.length - 1];
        const curr = group.current;
        const isLiveDifferent = Math.abs(curr.x - lastTrail.x) > 0.01 || Math.abs(curr.y - lastTrail.y) > 0.01;
        const fullPoints = isLiveDifferent ? [...trailPts, { date: 'live', x: curr.x, y: curr.y }] : trailPts;

        // Animation: limit visible points
        const points = animFrame > 0
          ? fullPoints.slice(0, Math.min(animFrame, fullPoints.length))
          : fullPoints;

        if (points.length < 2) return null;

        const head = points[points.length - 1];
        const headPrev = points[points.length - 2];
        const showLivePulse = animFrame === 0; // Only pulse when not animating

        // Variable stroke width based on head distance from center
        const dist = distFromCenter(head.x, head.y);
        const baseStrokeW = 1.0;
        const strokeW = Math.min(baseStrokeW + dist * 0.25, 3.5);

        // Direction arrow angle
        const hx = scaleX(head.x);
        const hy = scaleY(head.y);
        const px = scaleX(headPrev.x);
        const py = scaleY(headPrev.y);
        const angle = Math.atan2(hy - py, hx - px) * 180 / Math.PI;
        const arrowLen = isHovered ? 10 : 7;

        const gradId = `trail-${group.name.replace(/\s+/g, '_')}`;

        return (
          <g key={group.name}
            opacity={isOther ? 0.15 : 1}
            style={{ transition: 'opacity 200ms' }}
            onMouseEnter={() => onHover(group.name)}
            onMouseLeave={() => onHover(null)}
            onClick={() => onSelect(group)}
            className="cursor-pointer"
          >
            <defs>
              <linearGradient id={gradId}
                gradientUnits="userSpaceOnUse"
                x1={scaleX(points[0].x)} y1={scaleY(points[0].y)}
                x2={scaleX(points[points.length - 1].x)} y2={scaleY(points[points.length - 1].y)}>
                <stop offset="0%" stopColor={trailColor} stopOpacity={0.1} />
                <stop offset="100%" stopColor={trailColor} stopOpacity={0.9} />
              </linearGradient>
            </defs>

            {/* Trail path — variable width */}
            <path
              d={linePath(points, scaleX, scaleY)}
              fill="none"
              stroke={`url(#${gradId})`}
              strokeWidth={isHovered ? strokeW + 1 : strokeW}
              strokeLinecap="round"
              strokeLinejoin="round"
            />

            {/* Trail dots */}
            {points.map((pt, i) => {
              if (i === points.length - 1) return null;
              const opacity = 0.15 + (i / (points.length - 1)) * 0.85;
              const r = i === 0 ? 2 : 1.5;
              return (
                <circle key={`dot-${i}`}
                  cx={scaleX(pt.x)} cy={scaleY(pt.y)} r={r}
                  fill={trailColor} opacity={opacity}
                />
              );
            })}

            {/* Head: circle + direction arrow */}
            <circle
              cx={hx} cy={hy} r={isHovered ? 5.5 : 4}
              fill={trailColor} stroke="var(--color-bg)" strokeWidth={1.5}
            />

            {/* Direction arrowhead */}
            <polygon
              points={`0,${-arrowLen * 0.4} ${arrowLen},0 0,${arrowLen * 0.4}`}
              fill={trailColor}
              opacity={0.85}
              transform={`translate(${hx},${hy}) rotate(${angle})`}
            />

            {/* Live pulse ring (only when not animating) */}
            {showLivePulse && (
              <circle
                cx={hx} cy={hy}
                r={8} fill="none" stroke={trailColor} strokeWidth={1}
                opacity={0}
              >
                <animate attributeName="r" values="5;12" dur="1.5s" repeatCount="indefinite" />
                <animate attributeName="opacity" values="0.6;0" dur="1.5s" repeatCount="indefinite" />
              </circle>
            )}

            {/* Label */}
            <text
              x={hx + 9}
              y={hy - 7}
              className={`text-[9px] font-semibold ${isHovered ? 'fill-foreground' : 'fill-foreground/80'}`}
              style={{ transition: 'fill 200ms', pointerEvents: 'none' }}
            >
              {fmtName(group.name, activeTab)}
            </text>
          </g>
        );
      })}

      {/* Hover tooltip */}
      {hoveredData && (() => {
        const tx = scaleX(hoveredData.current.x);
        const ty = scaleY(hoveredData.current.y);
        const flipX = tx > width - 150;
        const flipY = ty < 80;
        const ttx = flipX ? tx - 140 : tx + 12;
        const tty = flipY ? ty + 12 : ty - 70;
        const dist = distFromCenter(hoveredData.current.x, hoveredData.current.y);

        const xDir = hoveredData.current.x >= 100 ? 'outperforming' : 'underperforming';
        const yDir = hoveredData.current.y >= 100 ? 'accelerating' : 'decelerating';

        return (
          <g style={{ pointerEvents: 'none' }}>
            <rect x={ttx} y={tty} width={148} height={76} rx={4}
              fill="rgba(15,23,42,0.92)" />
            <text x={ttx + 8} y={tty + 15}
              className="text-[10px] font-bold fill-white">
              {fmtName(hoveredData.name, activeTab)}
            </text>
            <text x={ttx + 8} y={tty + 29}
              className="text-[9px] fill-muted-fg/50">
              Strength: {hoveredData.current.x.toFixed(2)} ({xDir})
            </text>
            <text x={ttx + 8} y={tty + 41}
              className="text-[9px] fill-muted-fg/50">
              Momentum: {hoveredData.current.y.toFixed(2)} ({yDir})
            </text>
            <text x={ttx + 8} y={tty + 55}
              className="text-[9px] fill-muted-fg">
              Distance from center: {dist.toFixed(2)}
            </text>
            <text x={ttx + 8} y={tty + 67}
              className="text-[9px] font-medium"
              fill={getQuadrantColor(hoveredData.quadrant)}>
              {getQuadrantLabel(hoveredData.quadrant)}
            </text>
          </g>
        );
      })()}
    </svg>
  );
}

// ── Main RRG View ──

function RRGView({ data: _pulseData, activeTab, onSelect: _onSelect }: PulseViewProps) {
  const [rsMetric, setRsMetric] = useState('change_20d');
  const [benchmark, setBenchmark] = useState('none');
  const [tailLength, setTailLength] = useState(20);
  const [hoveredGroup, setHoveredGroup] = useState<string | null>(null);

  // Animation state
  const [isPlaying, setIsPlaying] = useState(false);
  const [animFrame, setAnimFrame] = useState(0); // 0 = show all
  const animIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const groupBy = activeTab === 'themes' ? 'themes' : activeTab === 'industries' ? 'industries' : 'sectors';

  const { data: rrg, loading, error } = useRRG({
    groupBy,
    rsMetric,
    benchmark,
    tailLength,
    minMarketCap: 1_000_000_000,
  });

  // Max trail length across all groups (for animation end)
  const maxTrailLen = useMemo(() => {
    if (!rrg?.groups) return 0;
    return Math.max(0, ...rrg.groups.map(g => {
      const last = g.trail[g.trail.length - 1];
      const c = g.current;
      const hasLive = Math.abs(c.x - last.x) > 0.01 || Math.abs(c.y - last.y) > 0.01;
      return g.trail.length + (hasLive ? 1 : 0);
    }));
  }, [rrg?.groups]);

  // Cleanup animation interval
  useEffect(() => {
    return () => {
      if (animIntervalRef.current) clearInterval(animIntervalRef.current);
    };
  }, []);

  const stopAnimation = useCallback(() => {
    if (animIntervalRef.current) {
      clearInterval(animIntervalRef.current);
      animIntervalRef.current = null;
    }
    setIsPlaying(false);
    setAnimFrame(0);
  }, []);

  const togglePlay = useCallback(() => {
    if (isPlaying) {
      stopAnimation();
      return;
    }

    // Start animation
    setAnimFrame(2);
    setIsPlaying(true);

    const max = maxTrailLen;
    let frame = 2;

    animIntervalRef.current = setInterval(() => {
      frame++;
      if (frame >= max) {
        if (animIntervalRef.current) clearInterval(animIntervalRef.current);
        animIntervalRef.current = null;
        setIsPlaying(false);
        setAnimFrame(0); // Show all
      } else {
        setAnimFrame(frame);
      }
    }, 250);
  }, [isPlaying, maxTrailLen, stopAnimation]);

  // Reset animation when data params change
  useEffect(() => {
    stopAnimation();
  }, [rsMetric, benchmark, tailLength, groupBy, stopAnimation]);

  const [size, setSize] = useState({ width: 800, height: 500 });
  const resizeObserver = useRef<ResizeObserver | null>(null);

  const setupResize = useCallback((node: HTMLDivElement | null) => {
    resizeObserver.current?.disconnect();
    if (!node) return;
    resizeObserver.current = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) setSize({ width, height });
    });
    resizeObserver.current.observe(node);
    const rect = node.getBoundingClientRect();
    if (rect.width > 0) setSize({ width: rect.width, height: rect.height });
  }, []);

  const handleGroupSelect = useCallback((group: RRGGroup) => {
    const entry = _pulseData.find(e => e.name === group.name);
    if (entry) _onSelect(entry);
  }, [_pulseData, _onSelect]);

  return (
    <div className="flex flex-col h-full">
      {/* Controls bar */}
      <div className="flex items-center gap-3 px-3 py-1.5 border-b border-border bg-surface-hover/50 flex-shrink-0">
        <div className="flex items-center gap-1" title="Timeframe for measuring relative strength">
          <span className="text-[9px] text-muted-fg uppercase font-semibold tracking-wider">Timeframe</span>
          <select
            value={rsMetric}
            onChange={e => setRsMetric(e.target.value)}
            className="text-[10px] border border-border rounded px-1.5 py-0.5 bg-surface focus:ring-1 focus:ring-primary focus:outline-none"
          >
            {RS_OPTIONS.map(m => (
              <option key={m.key} value={m.key} title={m.title}>{m.label}</option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-1" title="How many days of history to show in the trail">
          <span className="text-[9px] text-muted-fg uppercase font-semibold tracking-wider">Trail</span>
          <select
            value={tailLength}
            onChange={e => setTailLength(Number(e.target.value))}
            className="text-[10px] border border-border rounded px-1.5 py-0.5 bg-surface focus:ring-1 focus:ring-primary focus:outline-none"
          >
            {HEAD_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-1" title="Compare against S&P 500 or show absolute performance">
          <span className="text-[9px] text-muted-fg uppercase font-semibold tracking-wider">Compare</span>
          <select
            value={benchmark}
            onChange={e => setBenchmark(e.target.value)}
            className="text-[10px] border border-border rounded px-1.5 py-0.5 bg-surface focus:ring-1 focus:ring-primary focus:outline-none"
          >
            {BENCHMARK_OPTIONS.map(m => (
              <option key={m.key} value={m.key} title={m.title}>{m.label}</option>
            ))}
          </select>
        </div>

        {/* Animation controls */}
        <div className="flex items-center gap-1 border-l border-border pl-2">
          <button
            onClick={togglePlay}
            className="p-0.5 rounded hover:bg-surface-hover transition-colors"
            title={isPlaying ? 'Pause animation' : 'Animate rotation over time'}
          >
            {isPlaying
              ? <Pause className="w-3.5 h-3.5 text-foreground/80" />
              : <Play className="w-3.5 h-3.5 text-foreground/80" />
            }
          </button>
          {animFrame > 0 && (
            <button
              onClick={stopAnimation}
              className="p-0.5 rounded hover:bg-surface-hover transition-colors"
              title="Reset"
            >
              <RotateCcw className="w-3 h-3 text-muted-fg" />
            </button>
          )}
        </div>

        {loading && <Loader2 className="w-3 h-3 text-primary animate-spin" />}

        <div className="flex-1" />

        {rrg && (
          <span className="text-[9px] text-muted-fg">
            {rrg.rs_metric_label}{rrg.benchmark === 'spy' ? ' vs SPY' : ''} · &gt;100 = outperforming
          </span>
        )}
      </div>

      {/* Chart area */}
      <div ref={setupResize} className="flex-1 min-h-0 relative">
        {error && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-xs text-red-500">{error}</span>
          </div>
        )}
        {!error && rrg && rrg.groups.length > 0 && (
          <RRGChart
            groups={rrg.groups}
            width={size.width}
            height={size.height}
            activeTab={activeTab}
            hoveredGroup={hoveredGroup}
            onHover={setHoveredGroup}
            onSelect={handleGroupSelect}
            autoRange={(rrg as any).auto_range}
            animFrame={animFrame}
          />
        )}
        {!error && !loading && rrg && rrg.groups.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-xs text-muted-fg">No data available</span>
          </div>
        )}
      </div>

      {/* Quadrant distribution legend */}
      {rrg?.quadrant_distribution && (
        <div className="flex items-center justify-center gap-4 px-3 py-1 border-t border-border bg-surface-hover/30 flex-shrink-0">
          {Object.entries(QUADRANTS).map(([key, cfg]) => (
            <div key={key} className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: cfg.color }} />
              <span className="text-[9px] text-foreground/80 font-medium">
                {cfg.label}: {rrg.quadrant_distribution[key] ?? 0}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default memo(RRGView);
