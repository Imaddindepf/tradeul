"use client";

import { useRef, useState, useEffect, useMemo, memo } from "react";

export interface CashRunwayData {
  ticker?: string;
  historical_cash: number;
  historical_cash_date: string;
  quarterly_operating_cf: number;
  daily_burn_rate: number;
  days_since_report: number;
  prorated_cf: number;
  capital_raises?: {
    total: number;
    count: number;
    details: Array<{ filing_date: string; gross_proceeds: number; instrument_type: string; description: string }>;
  };
  estimated_current_cash: number;
  runway_days: number | null;
  runway_months: number | null;
  runway_risk_level: string;
  data_source: string;
  cash_history?: Array<{ date: string; cash: number }>;
  cf_history?: Array<{ date: string; operating_cf: number }>;
}

interface Props {
  data: CashRunwayData | null;
  loading?: boolean;
  fontClass?: string;
  downColor?: string;
  upColor?: string;
}

function fmtCash(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(1)}B`;
  if (abs >= 1_000_000)     return `$${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000)         return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v.toLocaleString()}`;
}
function fmtDate(d: string): string {
  if (!d) return d;
  try {
    const dt = new Date(d);
    return `${dt.toLocaleString("en-US", { month: "short" })} '${String(dt.getFullYear()).slice(2)}`;
  } catch { return d; }
}

export const CashRunwayChart = memo(function CashRunwayChart({
  data, loading = false, fontClass = "", downColor = "#ef4444", upColor = "#22c55e",
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [chartW, setChartW] = useState(400);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; label: string; value: number } | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const obs = new ResizeObserver(es => setChartW(es[0].contentRect.width));
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const runway = useMemo(() => {
    if (!data) return { text: "N/A", color: "text-muted-foreground" };
    if (data.runway_months == null) {
      return data.quarterly_operating_cf >= 0
        ? { text: "Cash Positive", color: "" }
        : { text: "N/A", color: "text-muted-foreground" };
    }
    const m = data.runway_months;
    const style = m < 3 ? downColor : m < 6 ? "#f97316" : m < 12 ? "#f59e0b" : upColor;
    return { text: `${m.toFixed(1)} mo`, style };
  }, [data, downColor, upColor]);

  // Build bar series from cash_history + summary points
  const bars = useMemo(() => {
    if (!data) return [];
    const result: Array<{ label: string; value: number; positive: boolean; dim?: boolean }> = [];

    const hist = [...(data.cash_history || [])].sort((a, b) => a.date.localeCompare(b.date)).slice(-8);
    hist.forEach(h => result.push({ label: fmtDate(h.date), value: h.cash, positive: h.cash >= 0, dim: true }));

    result.push({ label: "Reported",    value: data.historical_cash,          positive: true });
    result.push({ label: "Op CF",       value: data.prorated_cf,              positive: data.prorated_cf >= 0 });
    if (data.capital_raises?.total) {
      result.push({ label: "Raised",    value: data.capital_raises.total,     positive: true });
    }
    result.push({ label: "Est.",        value: data.estimated_current_cash,   positive: data.estimated_current_cash >= 0 });

    return result;
  }, [data]);

  if (loading) {
    return (
      <div className={`${fontClass} animate-pulse px-2 py-2`}>
        <div className="h-2 bg-muted rounded w-1/3 mb-2" />
        <div className="h-16 bg-muted/40 rounded" />
      </div>
    );
  }
  if (!data) return null;

  // chart geometry
  const svgH = 72;
  const pad  = { t: 4, r: 4, b: 16, l: 36 };
  const plotW = Math.max(chartW - pad.l - pad.r, 10);
  const plotH = svgH - pad.t - pad.b;
  const maxAbs = Math.max(...bars.map(b => Math.abs(b.value)), 0.001);
  const posMax = Math.max(...bars.map(b => (b.value > 0 ? b.value : 0)), 0.001);
  const negMax = Math.max(...bars.map(b => (b.value < 0 ? Math.abs(b.value) : 0)), 0);
  const totalRange = posMax + negMax;
  const zeroY = pad.t + (posMax / totalRange) * plotH;

  const barW = Math.max(Math.floor(plotW / bars.length * 0.64), 3);
  const gap  = plotW / bars.length;
  const barX = (i: number) => pad.l + i * gap + (gap - barW) / 2;

  return (
    <div className={`${fontClass}`}>
      {/* header row */}
      <div className="flex items-center justify-between px-2 pb-1 text-[10px]">
        <span className="text-muted-foreground">
          Last report: <span className="text-foreground/70">{fmtDate(data.historical_cash_date)}</span>
          {" · "}{data.days_since_report}d ago
        </span>
        <span className="font-medium" style={{ color: (runway as any).style || undefined }}>
          {runway.text}
        </span>
      </div>

      {/* SVG */}
      <div ref={wrapRef} className="w-full relative">
        <svg
          width={chartW} height={svgH}
          className="block overflow-visible"
          onMouseLeave={() => setTooltip(null)}
        >
          {/* zero line */}
          {negMax > 0 && (
            <line x1={pad.l} x2={pad.l + plotW} y1={zeroY} y2={zeroY}
              stroke="currentColor" strokeOpacity={0.15} strokeWidth={1} strokeDasharray="3 3" />
          )}

          {/* subtle grid */}
          {[0.5, 1].map(f => {
            const yy = pad.t + (1 - f) * (posMax / totalRange) * plotH;
            return (
              <g key={f}>
                <line x1={pad.l} x2={pad.l + plotW} y1={yy} y2={yy}
                  stroke="currentColor" strokeOpacity={0.05} strokeWidth={1} />
                <text x={pad.l - 3} y={yy + 3} textAnchor="end" fontSize={7} fill="currentColor" fillOpacity={0.30}>
                  {fmtCash(posMax * f)}
                </text>
              </g>
            );
          })}

          {/* bars */}
          {bars.map((bar, i) => {
            const x = barX(i);
            const absH = Math.max((Math.abs(bar.value) / totalRange) * plotH, 1);
            const barY = bar.value >= 0 ? zeroY - absH : zeroY;
            const color = bar.positive ? "#3b82f6" : downColor;
            const opacity = bar.dim ? 0.45 : 0.75;

            return (
              <g key={i}
                onMouseEnter={e => {
                  const rect = wrapRef.current?.getBoundingClientRect();
                  if (!rect) return;
                  setTooltip({ x: x + barW / 2, y: barY, label: bar.label, value: bar.value });
                }}
              >
                <rect x={x} y={barY} width={barW} height={absH} fill={color} opacity={opacity} />
                <text x={x + barW / 2} y={svgH - 2} textAnchor="middle" fontSize={7} fill="currentColor" fillOpacity={0.35}>
                  {bar.label}
                </text>
              </g>
            );
          })}

          {/* tooltip */}
          {tooltip && (
            <g>
              <rect
                x={Math.min(tooltip.x + 6, chartW - 70)} y={Math.max(tooltip.y - 24, pad.t)}
                width={65} height={20} rx={2}
                fill="var(--color-background, #18181b)" stroke="currentColor" strokeOpacity={0.15}
              />
              <text
                x={Math.min(tooltip.x + 39, chartW - 35)} y={Math.max(tooltip.y - 10, pad.t + 14)}
                textAnchor="middle" fontSize={8} fill="currentColor" fillOpacity={0.7}
              >
                {tooltip.label}: {fmtCash(tooltip.value)}
              </text>
            </g>
          )}
        </svg>
      </div>

      {/* summary row */}
      <div className="flex gap-4 px-2 pt-1 text-[10px] text-muted-foreground">
        <span>Reported: <span className="text-foreground/80 font-medium">{fmtCash(data.historical_cash)}</span></span>
        <span>Op CF: <span className="font-medium" style={{ color: data.prorated_cf < 0 ? downColor : upColor }}>{data.prorated_cf < 0 ? "" : "+"}{fmtCash(data.prorated_cf)}</span></span>
        {data.capital_raises?.total ? <span>Raised: <span className="text-foreground/80 font-medium">+{fmtCash(data.capital_raises.total)}</span></span> : null}
        <span>Est: <span className="text-foreground/80 font-medium">{fmtCash(data.estimated_current_cash)}</span></span>
      </div>
    </div>
  );
});
