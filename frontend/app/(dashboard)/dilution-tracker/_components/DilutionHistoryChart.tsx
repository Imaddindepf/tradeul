"use client";

import { useRef, useState, useEffect, useMemo } from "react";

interface HistoricalSharesData {
  date: string;
  shares: number;
  form?: string;
}

interface DilutionHistoryData {
  history?: HistoricalSharesData[];
  all_records?: Array<{ period: string; outstanding_shares: number }>;
  dilution_1y?: number | null;
  dilution_3y?: number | null;
  dilution_5y?: number | null;
  dilution_summary?: { "1_year"?: number; "3_years"?: number; "5_years"?: number };
}

interface SECDilutionData {
  warrants?: Array<{ outstanding?: number; potential_new_shares?: number }>;
  atm_offerings?: Array<{ remaining_capacity?: number; potential_shares_at_current_price?: number }>;
  equity_lines?: Array<{ remaining_capacity?: number; potential_shares?: number }>;
  convertible_notes?: Array<{ potential_shares?: number }>;
  convertible_preferred?: Array<{ potential_shares?: number }>;
  s1_offerings?: Array<{ potential_shares?: number }>;
  shares_outstanding?: number;
  current_price?: number;
}

interface Props {
  data: DilutionHistoryData | null;
  secData?: SECDilutionData | null;
  loading?: boolean;
  fontClass?: string;
  downColor?: string;
}

// ─── formatting ──────────────────────────────────────────────────────────────
function fmtM(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toLocaleString();
}
function fmtPct(v: number | null | undefined): string {
  if (v == null) return "N/A";
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
}
function fmtDate(d: string): string {
  try {
    const dt = new Date(d + "T12:00:00");
    return `${dt.toLocaleString("en-US", { month: "short" })} '${String(dt.getFullYear()).slice(2)}`;
  } catch { return d; }
}

// ─── colours ─────────────────────────────────────────────────────────────────
const C = {
  os:    "#3b82f6",
  atm:   "#f97316",
  warn:  "#eab308",
  conv:  "#8b5cf6",
  el:    "#06b6d4",
  s1:    "#64748b",
};

// ─── SVG bar chart ────────────────────────────────────────────────────────────
export function DilutionHistoryChart({ data, secData, loading = false, fontClass = "", downColor = "#ef4444" }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [chartW, setChartW] = useState(400);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const obs = new ResizeObserver(es => setChartW(es[0].contentRect.width));
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // ── extract history ──
  const history = useMemo(() => {
    let raw: Array<{ date: string; shares: number }> = [];
    if (data?.history?.length) {
      raw = data.history.map(h => ({ date: h.date, shares: h.shares }));
    } else if (data?.all_records?.length) {
      raw = data.all_records.map(r => ({ date: r.period, shares: r.outstanding_shares }));
    }
    return raw.filter(h => h.shares > 0).slice(-14); // max 14 historical bars
  }, [data]);

  // ── potential dilution ──
  const pot = useMemo(() => {
    if (!secData) return { atm: 0, warrants: 0, conv: 0, el: 0, s1: 0 };
    const price = Number(secData.current_price) || 1;
    return {
      atm: (secData.atm_offerings || []).reduce((s, a) =>
        s + (a.potential_shares_at_current_price ?? (a.remaining_capacity ? Math.floor(a.remaining_capacity / price) : 0)), 0),
      warrants: (secData.warrants || []).reduce((s, w) => s + (w.outstanding ?? w.potential_new_shares ?? 0), 0),
      conv: [...(secData.convertible_notes || []), ...(secData.convertible_preferred || [])].reduce((s, c) => s + (c.potential_shares ?? 0), 0),
      el: (secData.equity_lines || []).reduce((s, e) => s + (e.potential_shares ?? (e.remaining_capacity ? Math.floor(e.remaining_capacity / price) : 0)), 0),
      s1: (secData.s1_offerings || []).reduce((s, x) => s + (x.potential_shares ?? 0), 0),
    };
  }, [secData]);

  const dilution1y = data?.dilution_summary?.["1_year"] ?? data?.dilution_1y;
  const dilution3y = data?.dilution_summary?.["3_years"] ?? data?.dilution_3y;

  const totalPot = pot.atm + pot.warrants + pot.conv + pot.el + pot.s1;
  const currentOS = history.length > 0 ? history[history.length - 1].shares : (secData?.shares_outstanding ?? 0);
  const fullyDiluted = currentOS + totalPot;
  const dilutionPct = currentOS > 0 ? (totalPot / currentOS) * 100 : 0;
  const hasPot = totalPot > 0;

  if (loading) {
    return (
      <div className={`${fontClass} animate-pulse`}>
        <div className="h-3 bg-muted rounded w-1/3 mx-2 mt-2" />
        <div className="h-24 bg-muted/40 rounded mx-2 mt-2 mb-2" />
      </div>
    );
  }
  if (history.length === 0) return null;

  // ── chart geometry ──
  const bars = [...history, ...(hasPot ? [{ date: "Diluted", shares: currentOS, _diluted: true } as any] : [])];
  const maxVal = Math.max(...bars.map(b => b.shares + (b._diluted ? totalPot : 0))) * 1.08;
  const svgH = 90;
  const pad = { t: 6, r: 4, b: 18, l: 38 };
  const plotW = Math.max(chartW - pad.l - pad.r, 10);
  const plotH = svgH - pad.t - pad.b;
  const barW = Math.max(Math.floor(plotW / bars.length * 0.62), 3);
  const gap = plotW / bars.length;

  const yScale = (v: number) => plotH - (v / maxVal) * plotH;
  const barX = (i: number) => pad.l + i * gap + (gap - barW) / 2;

  // y axis ticks
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map(f => ({ frac: f, val: maxVal * f }));

  return (
    <div className={`${fontClass}`}>
      {/* stats header */}
      <div className="flex items-center gap-3 px-2 pb-1 text-[10px] flex-wrap">
        {dilution1y != null && (
          <span className="text-muted-foreground">
            1Y: <span style={{ color: (dilution1y ?? 0) > 0 ? downColor : "var(--color-up, #22c55e)" }} className="font-medium">{fmtPct(dilution1y)}</span>
          </span>
        )}
        {dilution3y != null && (
          <span className="text-muted-foreground">
            3Y: <span style={{ color: (dilution3y ?? 0) > 0 ? downColor : "var(--color-up, #22c55e)" }} className="font-medium">{fmtPct(dilution3y)}</span>
          </span>
        )}
        {hasPot && (
          <span className="text-muted-foreground">
            Fully diluted: <span className="font-medium text-foreground">{fmtM(fullyDiluted)}</span>
            {" "}<span style={{ color: downColor }}>(+{dilutionPct.toFixed(1)}%)</span>
          </span>
        )}
        {secData?.current_price && (
          <span className="text-muted-foreground/60 ml-auto">@ ${Number(secData.current_price).toFixed(2)}</span>
        )}
      </div>

      {/* SVG chart */}
      <div ref={wrapRef} className="w-full">
        <svg width={chartW} height={svgH} className="block overflow-visible">
          {/* grid lines */}
          {yTicks.map(({ frac, val }) => {
            const y = pad.t + yScale(val * frac) - yScale(0); // use plotH directly
            const yy = pad.t + plotH * (1 - frac);
            return (
              <g key={frac}>
                <line
                  x1={pad.l} x2={pad.l + plotW} y1={yy} y2={yy}
                  stroke="currentColor" strokeOpacity={0.06} strokeWidth={1}
                />
                {frac > 0 && (
                  <text x={pad.l - 3} y={yy + 3} textAnchor="end" fontSize={7.5} fill="currentColor" fillOpacity={0.35}>
                    {fmtM(maxVal * frac)}
                  </text>
                )}
              </g>
            );
          })}

          {/* bars */}
          {bars.map((bar, i) => {
            const x = barX(i);
            const isDiluted = !!(bar as any)._diluted;
            const baseH = Math.max((bar.shares / maxVal) * plotH, 1);
            const baseY = pad.t + plotH - baseH;

            // stacked segments for diluted bar
            const segments: Array<{ h: number; color: string; label: string }> = isDiluted ? [
              { h: (pot.atm / maxVal) * plotH,  color: C.atm,  label: "ATM" },
              { h: (pot.warrants / maxVal) * plotH, color: C.warn, label: "Warrants" },
              { h: (pot.conv / maxVal) * plotH, color: C.conv, label: "Conv." },
              { h: (pot.el / maxVal) * plotH,   color: C.el,   label: "Eq. Line" },
              { h: (pot.s1 / maxVal) * plotH,   color: C.s1,   label: "S-1" },
            ].filter(s => s.h > 0.5) : [];

            let stackTop = baseY;
            return (
              <g key={i}>
                {/* base bar */}
                <rect
                  x={x} y={baseY} width={barW} height={baseH}
                  fill={C.os} opacity={isDiluted ? 0.75 : 0.6}
                />
                {/* stacked dilution segments */}
                {segments.map((seg, si) => {
                  const sy = stackTop - seg.h;
                  stackTop = sy;
                  return (
                    <rect key={si} x={x} y={sy} width={barW} height={Math.max(seg.h, 1)}
                      fill={seg.color} opacity={0.75} />
                  );
                })}
                {/* x label */}
                <text
                  x={x + barW / 2} y={pad.t + plotH + 11}
                  textAnchor="middle" fontSize={7} fill="currentColor" fillOpacity={0.35}
                >
                  {isDiluted ? "Diluted" : fmtDate(bar.date)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* legend (only if has potential) */}
      {hasPot && (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 px-2 pb-1 text-[9px]">
          {([
            { color: C.os,   label: "O/S" },
            { color: C.atm,  label: "ATM",      v: pot.atm },
            { color: C.warn, label: "Warrants",  v: pot.warrants },
            { color: C.conv, label: "Conv.",     v: pot.conv },
            { color: C.el,   label: "Eq. Line",  v: pot.el },
            { color: C.s1,   label: "S-1",       v: pot.s1 },
          ] as const).filter(item => !("v" in item) || (item as any).v > 0).map(item => (
            <span key={item.label} className="flex items-center gap-1 text-muted-foreground">
              <span style={{ display: "inline-block", width: 7, height: 7, background: item.color, opacity: 0.75, borderRadius: 1 }} />
              {item.label}
              {"v" in item && (item as any).v > 0 && <span className="text-foreground/60">{fmtM((item as any).v)}</span>}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
