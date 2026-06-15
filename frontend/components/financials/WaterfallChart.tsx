'use client';

import React, { useMemo, useState } from 'react';
import { Group } from '@visx/group';
import { scaleBand, scaleLinear } from '@visx/scale';
import { AxisLeft, AxisBottom } from '@visx/axis';
import { GridRows } from '@visx/grid';
import { ParentSize } from '@visx/responsive';
import {
    CHART_THEME as T,
    useThemePalette,
    fmtCompact,
    periodLabel,
} from './FinancialChartPro';

// ============================================================================
// Types
// ============================================================================

export interface WaterfallField {
    key: string;
    label: string;
    values: (number | null)[];   // newest-first (aligned to periods)
    dataType?: string;
    balance?: 'debit' | 'credit' | null;
}

export interface WaterfallChartProps {
    ticker: string;
    currency?: string;
    periods: string[];           // newest-first
    fields: WaterfallField[];    // income statement fields
    estimatePeriods?: string[];
    initialPeriodIndex?: number; // index into `periods` (0 = latest)
}

// ============================================================================
// Bridge definition (P&L). Keys mirror the income statement transform.
// ============================================================================

const ANCHORS: { keys: string[]; label: string }[] = [
    { keys: ['revenue', 'total_revenues'], label: 'Revenue' },
    { keys: ['gross_profit'], label: 'Gross Profit' },
    { keys: ['operating_income'], label: 'Operating Income' },
    { keys: ['net_income', 'consolidated_net_income'], label: 'Net Income' },
];

// Leaf component lines that bridge each pair of anchors. We deliberately avoid
// subtotals (e.g. total_nonoperating, income_before_tax) so amounts never get
// double counted — any unexplained delta is reconciled into an "Other" step.
const GAP_COMPONENTS: string[][] = [
    ['cost_of_revenue'],
    ['rd_expenses', 'sga_expenses', 'selling_marketing', 'general_administrative', 'depreciation_amortization', 'compensation', 'other_operating_expenses'],
    ['interest_expense', 'interest_income', 'other_nonoperating', 'income_tax_provision', 'minority_interest_share'],
];

type Step = {
    label: string;
    kind: 'total' | 'delta';
    value: number;     // total value, or signed delta
    start: number;     // running level at bar bottom (data units)
    end: number;       // running level at bar top (data units)
    color: string;
};

// ============================================================================
// Component
// ============================================================================

export function WaterfallChart({
    ticker,
    currency = 'USD',
    periods,
    fields,
    estimatePeriods = [],
    initialPeriodIndex = 0,
}: WaterfallChartProps) {
    useThemePalette();

    const byKey = useMemo(() => {
        const m = new Map<string, WaterfallField>();
        for (const f of fields) m.set(f.key, f);
        return m;
    }, [fields]);

    const [periodIdx, setPeriodIdx] = useState(Math.min(initialPeriodIndex, Math.max(0, periods.length - 1)));
    const estimateSet = useMemo(() => new Set(estimatePeriods), [estimatePeriods]);
    const isEstimate = estimateSet.has(periods[periodIdx]);

    const valAt = (key: string): number | null => {
        const f = byKey.get(key);
        if (!f) return null;
        const v = f.values[periodIdx];
        return v === null || v === undefined || Number.isNaN(v) ? null : v;
    };
    const firstAnchorVal = (keys: string[]): number | null => {
        for (const k of keys) { const v = valAt(k); if (v !== null) return v; }
        return null;
    };

    // ---- Build the bridge --------------------------------------------------
    const { steps, revenue } = useMemo(() => {
        const anchorsPresent = ANCHORS
            .map((a, i) => ({ ...a, gapIdx: i - 1, value: firstAnchorVal(a.keys) }))
            .filter(a => a.value !== null) as { keys: string[]; label: string; gapIdx: number; value: number }[];

        const out: Step[] = [];
        const rev = anchorsPresent[0]?.value ?? 0;
        if (anchorsPresent.length === 0) return { steps: out, revenue: rev };

        let running = anchorsPresent[0].value;
        out.push({ label: anchorsPresent[0].label, kind: 'total', value: running, start: 0, end: running, color: T.accent });

        for (let a = 1; a < anchorsPresent.length; a++) {
            const prev = anchorsPresent[a - 1];
            const cur = anchorsPresent[a];
            // Component keys for the gap that precedes the current anchor.
            const gapKeys = GAP_COMPONENTS[cur.gapIdx] || [];
            let signedSum = 0;
            for (const k of gapKeys) {
                const v = valAt(k);
                if (v === null) continue;
                const f = byKey.get(k);
                const signed = f?.balance === 'debit' ? -Math.abs(v) : v;
                if (signed === 0) continue;
                const start = running;
                const end = running + signed;
                out.push({ label: f?.label || k, kind: 'delta', value: signed, start, end, color: signed >= 0 ? T.pos : T.neg });
                running = end;
                signedSum += signed;
            }
            // Reconcile any residual so the bridge lands exactly on the anchor.
            const residual = cur.value - prev.value - signedSum;
            if (Math.abs(residual) > Math.max(1, Math.abs(rev) * 0.002)) {
                const start = running;
                const end = running + residual;
                out.push({ label: 'Other', kind: 'delta', value: residual, start, end, color: residual >= 0 ? T.pos : T.neg });
                running = end;
            } else {
                running = cur.value;
            }
            out.push({ label: cur.label, kind: 'total', value: cur.value, start: 0, end: cur.value, color: T.accent });
        }
        return { steps: out, revenue: rev };
    }, [byKey, periodIdx]);

    // Recent periods for the quick selector (cap to keep the header tidy).
    const selectorPeriods = periods.slice(0, 8);

    return (
        <div className="h-full flex flex-col outline-none" style={{ background: T.bg, color: T.text }}>
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2" style={{ borderBottom: `1px solid ${T.border}` }}>
                <div>
                    <div className="text-sm font-bold">Income Bridge</div>
                    <div className="text-[10px] flex items-center gap-2" style={{ color: T.textDim }}>
                        <span>{ticker}</span>
                        <span style={{ color: T.textFaint }}>{currency}</span>
                        <span style={{ color: T.textFaint }}>{periodLabel(periods[periodIdx])}{isEstimate ? ' (Est.)' : ''}</span>
                    </div>
                </div>
                <div className="flex items-center gap-1 flex-wrap justify-end">
                    {selectorPeriods.map((p, i) => (
                        <button key={p} onClick={() => setPeriodIdx(i)}
                            className="text-[10px] px-2 py-1 rounded font-medium"
                            style={{ background: i === periodIdx ? T.accent : 'transparent', color: i === periodIdx ? '#03101f' : T.textDim }}>
                            {periodLabel(p)}
                        </button>
                    ))}
                </div>
            </div>

            {/* Chart */}
            <div className="flex-1 min-h-0">
                {steps.length === 0 ? (
                    <div className="flex items-center justify-center h-full text-[11px]" style={{ color: T.textFaint }}>
                        No income-statement data for this period
                    </div>
                ) : (
                    <ParentSize>
                        {({ width, height }) => width > 0 && height > 0 ? (
                            <WaterfallInner width={width} height={height} steps={steps} revenue={revenue} currency={currency} />
                        ) : null}
                    </ParentSize>
                )}
            </div>
        </div>
    );
}

// ============================================================================
// Inner SVG
// ============================================================================

function WaterfallInner({ width, height, steps, revenue, currency }: {
    width: number; height: number; steps: Step[]; revenue: number; currency: string;
}) {
    const [tip, setTip] = useState<{ x: number; y: number; i: number } | null>(null);
    const margin = { top: 18, right: 16, bottom: 64, left: 66 };
    const innerW = Math.max(0, width - margin.left - margin.right);
    const innerH = Math.max(0, height - margin.top - margin.bottom);

    const xScale = useMemo(() => scaleBand<number>({
        domain: steps.map((_, i) => i),
        range: [0, innerW],
        padding: 0.32,
    }), [steps, innerW]);

    const yScale = useMemo(() => {
        let min = 0, max = 0;
        for (const s of steps) { min = Math.min(min, s.start, s.end); max = Math.max(max, s.start, s.end); }
        const pad = (max - min) * 0.1 || 1;
        return scaleLinear<number>({ domain: [min - (min < 0 ? pad : 0), max + pad], range: [innerH, 0], nice: true });
    }, [steps, innerH]);

    const bw = xScale.bandwidth();
    const center = (i: number) => (xScale(i) ?? 0) + bw / 2;
    const zeroY = yScale(0);

    return (
        <div className="relative" style={{ width, height }}>
            <svg width={width} height={height}>
                <Group left={margin.left} top={margin.top}>
                    <GridRows scale={yScale} width={innerW} height={innerH} stroke={T.grid} strokeWidth={1} numTicks={5} />
                    {zeroY >= 0 && zeroY <= innerH && (
                        <line x1={0} x2={innerW} y1={zeroY} y2={zeroY} stroke={T.textFaint} strokeWidth={1} />
                    )}

                    {/* connectors between consecutive bars */}
                    {steps.map((s, i) => {
                        if (i === steps.length - 1) return null;
                        const next = steps[i + 1];
                        // Connect the running level (top of this bar) to the next bar.
                        const lvl = s.end;
                        const yl = yScale(lvl);
                        const x1 = (xScale(i) ?? 0) + bw;
                        const x2 = xScale(i + 1) ?? 0;
                        // Only draw when the next bar starts at this level (delta chain)
                        const nextLvl = next.kind === 'delta' ? next.start : next.end;
                        if (Math.abs(nextLvl - lvl) > Math.max(1, Math.abs(revenue) * 0.002) && next.kind === 'total') {
                            return null;
                        }
                        return <line key={`c-${i}`} x1={x1} x2={x2} y1={yl} y2={yScale(nextLvl)} stroke={T.textFaint} strokeDasharray="2 2" strokeWidth={1} opacity={0.6} />;
                    })}

                    {/* bars */}
                    {steps.map((s, i) => {
                        const yTop = yScale(Math.max(s.start, s.end));
                        const yBot = yScale(Math.min(s.start, s.end));
                        const h = Math.max(1, yBot - yTop);
                        const x = xScale(i) ?? 0;
                        const labelY = yTop - 4;
                        return (
                            <g key={`b-${i}`}
                                onMouseEnter={() => setTip({ x: center(i), y: yTop, i })}
                                onMouseLeave={() => setTip(null)}>
                                <rect x={x} y={yTop} width={bw} height={h} rx={2}
                                    fill={s.color} opacity={s.kind === 'total' ? 0.9 : 0.85} />
                                <text x={center(i)} y={labelY} textAnchor="middle" fontSize={9} fontWeight={600} fill={T.text}>
                                    {s.kind === 'delta' && s.value >= 0 ? '+' : ''}{fmtCompact(s.value, 'monetary', currency, 'auto')}
                                </text>
                                {revenue !== 0 && (
                                    <text x={center(i)} y={innerH + 30} textAnchor="middle" fontSize={8} fill={T.textFaint}>
                                        {((s.kind === 'total' ? s.value : s.value) / Math.abs(revenue) * 100).toFixed(0)}%
                                    </text>
                                )}
                            </g>
                        );
                    })}

                    <AxisLeft scale={yScale} numTicks={5}
                        tickFormat={(v) => fmtCompact(Number(v), 'monetary', currency, 'auto')}
                        stroke={T.border} tickStroke={T.border}
                        tickLabelProps={() => ({ fill: T.textDim, fontSize: 9, textAnchor: 'end', dx: -2, dy: 3 })} />
                    <AxisBottom top={innerH} scale={xScale}
                        tickFormat={(i) => steps[Number(i)]?.label || ''}
                        stroke={T.border} tickStroke={T.border}
                        tickLabelProps={() => ({ fill: T.textDim, fontSize: 8, textAnchor: 'end', angle: -35, dy: 2, dx: -2 })} />
                </Group>
            </svg>

            {tip && (
                <div className="pointer-events-none absolute z-20 rounded px-2 py-1 text-[10px]"
                    style={{
                        left: Math.min(tip.x + margin.left + 8, width - 140),
                        top: Math.max(6, tip.y + margin.top - 8),
                        background: T.panelAlt, border: `1px solid ${T.border}`, minWidth: 110,
                    }}>
                    <div className="font-semibold" style={{ color: T.text }}>{steps[tip.i].label}</div>
                    <div className="tabular-nums" style={{ color: steps[tip.i].kind === 'delta' ? steps[tip.i].color : T.text }}>
                        {steps[tip.i].kind === 'delta' && steps[tip.i].value >= 0 ? '+' : ''}
                        {fmtCompact(steps[tip.i].value, 'monetary', currency, 'auto')}
                    </div>
                </div>
            )}
        </div>
    );
}

export default WaterfallChart;
