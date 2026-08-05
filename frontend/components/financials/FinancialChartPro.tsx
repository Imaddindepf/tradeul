'use client';

import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Group } from '@visx/group';
import { LinePath, AreaClosed } from '@visx/shape';
import { scaleBand, scaleLinear, scaleLog } from '@visx/scale';
import { AxisLeft, AxisBottom, AxisRight } from '@visx/axis';
import { GridRows } from '@visx/grid';
import { curveMonotoneX } from '@visx/curve';
import { localPoint } from '@visx/event';
import { ParentSize } from '@visx/responsive';
import { registerOverlayTarget, type OverlaySeriesPayload } from './chartOverlayBus';

// ============================================================================
// Types
// ============================================================================

export interface ChartSeriesField {
    key: string;
    label: string;
    values: (number | null)[];   // aligned to `periods` (newest-first, as in the table)
    dataType?: string;           // monetary | percent | perShare | shares | multiple | number | ratio
    /**
     * Scale of `values` for percent series: 'fraction' (0.1249 = 12.49%) or
     * 'points' (12.49 = 12.49%). Defaults to 'fraction' — the convention of
     * every statement/ratios/key-stats payload from the gateway.
     */
    percentScale?: 'fraction' | 'points';
    balance?: 'debit' | 'credit' | null;
    /** Optional display unit for non-monetary series, e.g. "Units", "MW". */
    unitLabel?: string;
    /** Statement section used to group the fields sidebar (GF-style). */
    section?: string;
}

export interface FinancialChartProProps {
    ticker: string;
    currency?: string;
    periods: string[];           // newest-first
    fields: ChartSeriesField[];  // all selectable metrics from the active statement
    initialMetricKey: string;
    estimatePeriods?: string[];
    dashboardId?: string;        // when set, this chart can receive "lock overlay" pushes
}

const MAX_SERIES = 6;

type TransformMode = 'absolute' | 'yoy' | 'common';
type Representation = 'line' | 'bar' | 'area' | 'ironBars';
type UnitsMode = 'auto' | 'K' | 'M' | 'B';
type PanelLayout = 'single' | 'panels';
interface RefLines { min: boolean; max: boolean; median: boolean; avg: boolean }

interface PreparedSeries {
    key: string;
    label: string;
    color: string;
    rep: Representation;
    axis: 'primary' | 'secondary';
    unit: UnitKind;
    unitLabel?: string;
    values: (number | null)[];   // chronological (oldest-first), already transformed
}

type UnitKind = 'monetary' | 'percent' | 'perShare' | 'shares' | 'multiple' | 'number';

// ============================================================================
// Theme (self-contained "terminal" palette)
// ============================================================================

// Palette mirrors the app theme tokens (globals.css). Resolved at runtime from
// CSS variables so the chart matches the system theme (light or dark). We keep
// concrete color strings (not `var(...)`) because SVG presentation attributes
// do not reliably resolve CSS variables across browsers.
const T = {
    bg: '#000000',
    panel: '#0a0a0a',
    panelAlt: '#111111',
    border: '#1d1d1f',
    grid: '#15151a',
    text: '#f5f5f7',
    textDim: '#86868b',
    textFaint: '#5a5a5f',
    pos: '#10b981',
    neg: '#ef4444',
    accent: '#2997ff',
};

function readThemePalette() {
    if (typeof window === 'undefined') return null;
    const cs = getComputedStyle(document.documentElement);
    const g = (name: string, fallback: string) => (cs.getPropertyValue(name).trim() || fallback);
    return {
        bg: g('--color-bg', T.bg),
        panel: g('--color-surface', T.panel),
        panelAlt: g('--color-surface-hover', T.panelAlt),
        border: g('--color-border', T.border),
        grid: g('--color-border-subtle', g('--color-border', T.grid)),
        text: g('--color-fg', T.text),
        textDim: g('--color-muted-fg', T.textDim),
        textFaint: g('--color-muted-fg', T.textFaint),
        pos: g('--color-success', g('--color-chart-up', T.pos)),
        neg: g('--color-danger', g('--color-chart-down', T.neg)),
        accent: g('--color-primary', T.accent),
    };
}

// Apply the resolved palette and re-render whenever the theme changes.
export function useThemePalette() {
    const [, force] = useState(0);
    useLayoutEffect(() => {
        const apply = () => {
            const p = readThemePalette();
            if (p) { Object.assign(T, p); force(x => x + 1); }
        };
        apply();
        const obs = new MutationObserver(apply);
        obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme', 'style'] });
        return () => obs.disconnect();
    }, []);
}

// Distinct accent palette for overlaid series (kept stable across themes).
export const SERIES_COLORS = ['#2997ff', '#bc8cff', '#f0b72f', '#34d399', '#ff7b72', '#39c5cf'];

// Re-export the live (mutable) palette so sibling chart components share the
// exact same theme tokens resolved at runtime.
export { T as CHART_THEME };

// ============================================================================
// Helpers
// ============================================================================

function unitFromDataType(dt?: string, label?: string): UnitKind {
    const raw = (dt || '').toLowerCase();
    switch (raw) {
        case 'percent': return 'percent';
        case 'pershare': return 'perShare';
        case 'shares': return 'shares';
        case 'multiple': return 'multiple';
        case 'number':
        case 'units':
        case 'count':
            return 'number';
        case 'ratio': return 'multiple';
        case 'monetary':
        case 'currency':
            return 'monetary';
        default:
            break;
    }
    // Heuristic fallback when dataType is missing/wrong (legacy segment payloads).
    const l = (label || '').toLowerCase();
    if (/\(units?\)/.test(l) || /\b(mw|mwh|gw|gpus?|servers?)\b/.test(l)) return 'number';
    if (raw) return 'monetary';
    return 'monetary';
}

function isFlowUnit(u: UnitKind): boolean {
    return u === 'monetary' || u === 'perShare' || u === 'shares' || u === 'number';
}

/**
 * Factor that turns a field's raw values into the chart's working scale.
 *
 * The chart works in percentage points, because that is what the YoY / %Rev
 * transforms below produce. Percent fields, however, arrive from the gateway as
 * fractions (operating_margin = 0.1249 for 12.49%) — the same convention the
 * statement tables already undo when they render. Without this the chart drew a
 * 12.5% margin as "0.1%".
 */
function valueScale(f: ChartSeriesField | undefined): number {
    if (!f) return 1;
    if (unitFromDataType(f.dataType, f.label) !== 'percent') return 1;
    return f.percentScale === 'points' ? 1 : 100;
}

/**
 * Untruncated decimal text for a number, used by the read-out (header + tooltip)
 * so the figure as filed is always reachable: a 12.4961% margin reads
 * "12.4961%" there, while the canvas shows the terminal-style "12.5%". The only
 * trimming is IEEE-754 noise (0.124961 * 100 === 12.496099999999998) at the
 * 12th significant digit, past the precision of anything the filings carry.
 */
export function exactNum(v: number, grouped = false): string {
    const cleaned = Number(v.toPrecision(12));
    return grouped ? cleaned.toLocaleString('en-US', { maximumFractionDigits: 12 }) : String(cleaned);
}

function compactMagnitude(abs: number, units: UnitsMode = 'auto'): string {
    const forced = units !== 'auto';
    const div = units === 'B' ? 1e9 : units === 'M' ? 1e6 : units === 'K' ? 1e3 : 1;
    if (forced) {
        return `${(abs / div).toFixed(div >= 1e9 ? 2 : 1)}${units}`;
    }
    if (abs >= 1e12) return `${(abs / 1e12).toFixed(2)}T`;
    if (abs >= 1e9) return `${(abs / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${(abs / 1e6).toFixed(1)}M`;
    if (abs >= 1e3) return `${(abs / 1e3).toFixed(1)}K`;
    if (Number.isInteger(abs) || abs >= 100) return abs.toFixed(0);
    return abs.toFixed(2);
}

/**
 * Decimals a percentage needs on the canvas. One, as every terminal does — but
 * escalated for small readings so a non-zero value never prints as "0.0%".
 */
function percentDecimals(v: number): number {
    const abs = Math.abs(v);
    if (abs === 0 || abs >= 0.05) return 1;
    if (abs >= 0.005) return 2;
    return 3;
}

/**
 * Canvas form (axis ticks, point labels, last-value tags): fixed precision, so
 * a column of numbers lines up and reads at a glance. The untruncated figure is
 * one hover away — see `fmtFull`.
 */
export function fmtCompact(v: number | null | undefined, unit: UnitKind, currency = 'USD', units: UnitsMode = 'auto'): string {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    if (unit === 'percent') return `${v.toFixed(percentDecimals(v))}%`;
    if (unit === 'multiple') return `${v.toFixed(2)}x`;
    const abs = Math.abs(v);
    const sign = v < 0 ? '-' : '';
    if (unit === 'number') {
        // Physical counts / capacity — never attach a currency symbol.
        if (units === 'auto' && abs < 10000) {
            const body = Number.isInteger(abs) ? abs.toLocaleString('en-US') : abs.toLocaleString('en-US', { maximumFractionDigits: 2 });
            return `${sign}${body}`;
        }
        return `${sign}${compactMagnitude(abs, units)}`;
    }
    const sym = unit === 'monetary' || unit === 'perShare' ? curSymbol(currency) : '';
    if (unit === 'perShare') return `${sign}${sym}${abs.toFixed(2)}`;
    if (unit === 'shares') return `${sign}${compactMagnitude(abs, units)}`;
    return `${sign}${sym}${compactMagnitude(abs, units)}`;
}

/** Read-out form (header + tooltip): exact, and never abbreviated. */
function fmtFull(v: number | null | undefined, unit: UnitKind, currency = 'USD', units: UnitsMode = 'auto'): string {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    if (unit === 'percent') return `${exactNum(v)}%`;
    if (unit === 'multiple') return `${exactNum(v)}x`;
    const abs = Math.abs(v);
    const sign = v < 0 ? '-' : '';
    if (unit === 'monetary' || unit === 'perShare') return `${sign}${curSymbol(currency)}${exactNum(abs, true)}`;
    if (unit === 'shares' || unit === 'number') return `${sign}${exactNum(abs, true)}`;
    return fmtCompact(v, unit, currency, units);
}

/** Currency prefix for the company's reported currency (USD→$, EUR→€, CHF→CHF …). */
export function curSymbol(currency: string): string {
    switch ((currency || 'USD').toUpperCase()) {
        case 'USD': return '$';
        case 'EUR': return '€';
        case 'GBP': return '£';
        case 'JPY':
        case 'CNY':
        case 'CNH': return '¥';
        case 'CHF': return 'CHF\u00a0';
        case 'CAD': return 'C$';
        case 'AUD': return 'A$';
        case 'HKD': return 'HK$';
        case 'SGD': return 'S$';
        case 'KRW': return '₩';
        case 'INR': return '₹';
        case 'SEK':
        case 'NOK':
        case 'DKK': return `${(currency || '').toUpperCase()}\u00a0`;
        default: {
            const c = (currency || '').toUpperCase();
            return c ? `${c}\u00a0` : '';
        }
    }
}

/** Short axis/meta label for the active unit kind. */
export function unitAxisLabel(unit: UnitKind, currency = 'USD', unitLabel?: string): string {
    if (unit === 'percent') return '%';
    if (unit === 'multiple') return 'x';
    if (unit === 'number') return unitLabel || 'Units';
    if (unit === 'shares') return 'Shares';
    if (unit === 'perShare') return `Per share (${(currency || 'USD').toUpperCase()})`;
    return (currency || 'USD').toUpperCase();
}

export function periodLabel(p: string): string {
    return /^Q[1-4]/.test(p) ? p : `FY${p}`;
}

export type { UnitKind };

function shortPeriodLabel(p: string): string {
    const m = p.match(/(\d{4})/);
    if (!m) return p;
    if (/^Q[1-4]/.test(p)) return `${p.slice(0, 2)} ${m[1].slice(-2)}`;
    return m[1];
}

// ============================================================================
// Main component
// ============================================================================

export function FinancialChartPro({
    ticker,
    currency = 'USD',
    periods,
    fields,
    initialMetricKey,
    estimatePeriods = [],
    dashboardId,
}: FinancialChartProProps) {
    useThemePalette();
    const isAnnual = useMemo(() => !periods.some(p => /^Q[1-4]/.test(p)), [periods]);

    // Chronological axis (oldest → newest) — table data is newest-first.
    const chronoPeriods = useMemo(() => [...periods].reverse(), [periods]);
    const estimateSet = useMemo(() => new Set(estimatePeriods), [estimatePeriods]);
    const estimateFlags = useMemo(
        () => chronoPeriods.map(p => estimateSet.has(p)),
        [chronoPeriods, estimateSet],
    );

    // Series pushed in from the dashboard via "lock overlay" (may come from a
    // different statement/block). Merged with the chart's own fields.
    const [injected, setInjected] = useState<ChartSeriesField[]>([]);
    const allFields = useMemo(() => {
        const seen = new Set(fields.map(f => f.key));
        return [...fields, ...injected.filter(f => !seen.has(f.key))];
    }, [fields, injected]);

    const fieldByKey = useMemo(() => {
        const m = new Map<string, ChartSeriesField>();
        for (const f of allFields) m.set(f.key, f);
        return m;
    }, [allFields]);

    const chronoValues = useCallback(
        (key: string): (number | null)[] => {
            const f = fieldByKey.get(key);
            if (!f) return chronoPeriods.map(() => null);
            const scale = valueScale(f);
            const vals = [...f.values].reverse();
            if (scale === 1) return vals;
            return vals.map(v => (v === null || Number.isNaN(v) ? null : v * scale));
        },
        [fieldByKey, chronoPeriods],
    );

    // Common-size base: revenue (or total assets) when present in the dataset.
    const commonBaseKey = useMemo(() => {
        const candidates = ['revenue', 'total_revenues', 'total_assets'];
        for (const c of candidates) if (fieldByKey.has(c)) return c;
        return null;
    }, [fieldByKey]);

    // ---- State -------------------------------------------------------------
    const [selectedKeys, setSelectedKeys] = useState<string[]>([initialMetricKey]);
    const [transform, setTransform] = useState<TransformMode>('absolute');
    const [logScale, setLogScale] = useState(false);
    const [repOverride, setRepOverride] = useState<Record<string, Representation>>({});
    const [fieldsOpen, setFieldsOpen] = useState(true);
    const [layout, setLayout] = useState<PanelLayout>('single');
    const [moreOpen, setMoreOpen] = useState(false);
    const [hoverIdx, setHoverIdx] = useState<number | null>(null);
    const [showLabels, setShowLabels] = useState(true);
    const [units, setUnits] = useState<UnitsMode>('auto');
    const [refLines, setRefLines] = useState<RefLines>({ min: false, max: false, median: false, avg: false });
    const [stackMode, setStackMode] = useState<'off' | 'stack' | 'pct'>('off');

    const defaultSpan = isAnnual ? 10 : 16;
    const [range, setRange] = useState<{ start: number; end: number }>(() => ({
        start: Math.max(0, chronoPeriods.length - defaultSpan),
        end: Math.max(0, chronoPeriods.length - 1),
    }));

    useEffect(() => {
        setSelectedKeys([initialMetricKey]);
        setInjected([]);
        setRange({
            start: Math.max(0, chronoPeriods.length - defaultSpan),
            end: Math.max(0, chronoPeriods.length - 1),
        });
        setHoverIdx(null);
    }, [initialMetricKey, chronoPeriods.length, defaultSpan]);

    // Keep a live ref of the current selection so the (stable) overlay handler
    // can check capacity / dedupe synchronously without stale closures.
    const selectedKeysRef = useRef(selectedKeys);
    useEffect(() => { selectedKeysRef.current = selectedKeys; }, [selectedKeys]);

    // Register as an overlay target for this dashboard. The most recently
    // mounted chart wins (see chartOverlayBus).
    useEffect(() => {
        if (!dashboardId) return;
        const handler = (p: OverlaySeriesPayload): boolean => {
            const cur = selectedKeysRef.current;
            if (cur.includes(p.key)) return true;          // already shown
            if (cur.length >= MAX_SERIES) return false;    // chart full -> overflow elsewhere

            // Align the incoming values onto this chart's period axis by label.
            const map = new Map<string, number | null>();
            p.periods.forEach((per, i) => map.set(per, p.values[i] ?? null));
            const aligned = periods.map(per => (map.has(per) ? map.get(per)! : null));

            setInjected(prev => (prev.some(f => f.key === p.key)
                ? prev
                : [...prev, { key: p.key, label: p.label, values: aligned, dataType: p.dataType, percentScale: p.percentScale, balance: p.balance }]));
            setSelectedKeys(prev => (prev.includes(p.key) ? prev : [...prev, p.key]));
            return true;
        };
        return registerOverlayTarget(dashboardId, handler);
    }, [dashboardId, periods]);

    // ---- Derived series ----------------------------------------------------
    const prepared = useMemo<PreparedSeries[]>(() => {
        const series = selectedKeys.map((key, i) => {
            const f = fieldByKey.get(key);
            const label = f?.label || key;
            const rawUnit = unitFromDataType(f?.dataType, label);
            const inferredUnitLabel = f?.unitLabel
                || (rawUnit === 'number' ? (label.match(/\(([^)]+)\)\s*$/)?.[1]?.trim()) : undefined);
            const base = chronoValues(key);

            let values = base;
            let unit = rawUnit;
            if (transform === 'yoy') {
                const step = isAnnual ? 1 : 4;
                values = base.map((v, idx) => {
                    const prev = base[idx - step];
                    if (v === null || prev === null || prev === 0) return null;
                    return ((v - prev) / Math.abs(prev)) * 100;
                });
                unit = 'percent';
            } else if (transform === 'common' && commonBaseKey) {
                const baseVals = chronoValues(commonBaseKey);
                values = base.map((v, idx) => {
                    const b = baseVals[idx];
                    if (v === null || b === null || b === 0) return null;
                    return (v / Math.abs(b)) * 100;
                });
                unit = 'percent';
            }

            // Every series renders per its natural type: bars for flows
            // (grouped side-by-side like Bloomberg GF), lines for ratios/%.
            // User can override per series from the sidebar or the toolbar.
            const defaultRep: Representation = isFlowUnit(unit) ? 'bar' : 'line';
            const rep: Representation = repOverride[key] || defaultRep;

            // Iron bars are drawn on their own contextual scale (handled in
            // InnerChart) so they never distort the primary/secondary domains.
            const axis: 'primary' | 'secondary' =
                rep === 'ironBars'
                    ? 'secondary'
                    : transform !== 'absolute'
                        ? 'primary'
                        : isFlowUnit(unit) ? 'primary' : 'secondary';

            return {
                key,
                label,
                color: SERIES_COLORS[i % SERIES_COLORS.length],
                rep,
                axis,
                unit,
                unitLabel: inferredUnitLabel,
                values,
            };
        });

        // Nothing on the left axis (e.g. only ratio/% series are shown): move
        // them over instead of drawing an empty monetary axis next to them.
        // Panel mode already forces every series onto its own primary axis.
        if (!series.some(s => s.axis === 'primary' && s.rep !== 'ironBars')) {
            for (const s of series) if (s.rep !== 'ironBars') s.axis = 'primary';
        }

        return series;
    }, [selectedKeys, fieldByKey, chronoValues, transform, isAnnual, commonBaseKey, repOverride]);

    const primarySeries = prepared[0];

    // Stacking only makes sense for >=2 comparable flow series on the primary
    // axis and in absolute mode. Otherwise we silently fall back to "off".
    const stackEligible = useMemo(
        () => transform === 'absolute'
            && prepared.filter(s => s.axis === 'primary' && s.rep !== 'ironBars' && isFlowUnit(s.unit)).length >= 2,
        [transform, prepared],
    );
    const effectiveStack = stackEligible ? stackMode : 'off';

    // Stats for the primary series over the visible range.
    const stats = useMemo(() => {
        if (!primarySeries) return null;
        const slice = primarySeries.values
            .slice(range.start, range.end + 1)
            .filter((v): v is number => v !== null && !Number.isNaN(v));
        if (slice.length === 0) return null;
        const latest = slice[slice.length - 1];
        const first = slice[0];
        const max = Math.max(...slice);
        const min = Math.min(...slice);
        const avg = slice.reduce((a, b) => a + b, 0) / slice.length;
        const sorted = [...slice].sort((a, b) => a - b);
        const mid = Math.floor(sorted.length / 2);
        const median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
        const yrs = isAnnual ? slice.length - 1 : (slice.length - 1) / 4;
        const cagr = yrs > 0 && first > 0 && latest > 0
            ? (Math.pow(latest / first, 1 / yrs) - 1) * 100 : null;
        const step = isAnnual ? 1 : 4;
        const prevVals = primarySeries.values.slice(range.start, range.end + 1);
        const prev = prevVals[prevVals.length - 1 - step];
        const yoy = prev != null && prev !== 0 && latest != null
            ? ((latest - prev) / Math.abs(prev)) * 100 : null;
        return { latest, first, max, min, avg, median, cagr, yoy };
    }, [primarySeries, range, isAnnual]);

    // ---- Presets -----------------------------------------------------------
    const applyPreset = useCallback((years: number | 'max') => {
        const n = chronoPeriods.length;
        if (years === 'max') { setRange({ start: 0, end: n - 1 }); return; }
        const span = isAnnual ? years : years * 4;
        setRange({ start: Math.max(0, n - span), end: n - 1 });
    }, [chronoPeriods.length, isAnnual]);

    // Keyboard pan / zoom.
    const rootRef = useRef<HTMLDivElement>(null);
    const onKeyDown = useCallback((e: React.KeyboardEvent) => {
        const n = chronoPeriods.length;
        setRange(r => {
            const width = r.end - r.start;
            if (e.key === 'ArrowLeft') {
                const s = Math.max(0, r.start - 1);
                return { start: s, end: s + width };
            }
            if (e.key === 'ArrowRight') {
                const en = Math.min(n - 1, r.end + 1);
                return { start: en - width, end: en };
            }
            if (e.key === '+' || e.key === '=') {
                return { start: Math.min(r.end - 1, r.start + 1), end: r.end };
            }
            if (e.key === '-' || e.key === '_') {
                return { start: Math.max(0, r.start - 1), end: Math.min(n - 1, r.end + 1) };
            }
            return r;
        });
    }, [chronoPeriods.length]);

    // ---- Metric selection (fields sidebar) ----------------------------------
    const toggleMetric = (key: string) => {
        setSelectedKeys(prev => {
            if (prev.includes(key)) {
                // Never drop the last remaining series.
                return prev.length > 1 ? prev.filter(k => k !== key) : prev;
            }
            return prev.length >= MAX_SERIES ? prev : [...prev, key];
        });
    };

    const setRep = (key: string, rep: Representation) =>
        setRepOverride(prev => ({ ...prev, [key]: rep }));

    // Toolbar buttons apply the representation to every selected series;
    // fine-grained per-series control lives in the fields sidebar.
    const setRepAll = (rep: Representation) =>
        setRepOverride(prev => {
            const next = { ...prev };
            for (const k of selectedKeys) next[k] = rep;
            return next;
        });

    // ---- Export ------------------------------------------------------------
    const svgWrapRef = useRef<HTMLDivElement>(null);
    const exportPNG = useCallback(() => {
        const svg = svgWrapRef.current?.querySelector('svg');
        if (!svg) return;
        const clone = svg.cloneNode(true) as SVGSVGElement;
        const rect = svg.getBoundingClientRect();
        const data = new XMLSerializer().serializeToString(clone);
        const img = new Image();
        const svg64 = btoa(unescape(encodeURIComponent(
            `<svg xmlns="http://www.w3.org/2000/svg" width="${rect.width}" height="${rect.height}">${data}</svg>`,
        )));
        img.onload = () => {
            const canvas = document.createElement('canvas');
            const scale = 2;
            canvas.width = rect.width * scale;
            canvas.height = rect.height * scale;
            const cx = canvas.getContext('2d');
            if (!cx) return;
            cx.fillStyle = T.bg;
            cx.fillRect(0, 0, canvas.width, canvas.height);
            cx.scale(scale, scale);
            cx.drawImage(img, 0, 0);
            const a = document.createElement('a');
            a.download = `${ticker}_${primarySeries?.key || 'chart'}.png`;
            a.href = canvas.toDataURL('image/png');
            a.click();
        };
        img.src = `data:image/svg+xml;base64,${svg64}`;
    }, [ticker, primarySeries]);

    const exportCSV = useCallback(() => {
        const header = ['Period', ...prepared.map(s => s.label)];
        const rows = chronoPeriods.map((p, i) =>
            [periodLabel(p), ...prepared.map(s => s.values[i] ?? '')].join(','));
        const csv = [header.join(','), ...rows].join('\n');
        const blob = new Blob([csv], { type: 'text/csv' });
        const a = document.createElement('a');
        a.download = `${ticker}_financials.csv`;
        a.href = URL.createObjectURL(blob);
        a.click();
    }, [prepared, chronoPeriods, ticker]);

    const growthColor = (g: number | null) =>
        g == null ? T.textDim : g >= 0 ? T.pos : T.neg;

    const primaryUnitKind = primarySeries?.unit || 'monetary';
    const scaleControlsVisible = primaryUnitKind === 'monetary' || primaryUnitKind === 'shares';
    const axisUnit = unitAxisLabel(primaryUnitKind, currency, primarySeries?.unitLabel);
    const hasRefLines = refLines.min || refLines.max || refLines.median || refLines.avg;

    return (
        <div
            ref={rootRef}
            tabIndex={0}
            onKeyDown={onKeyDown}
            className="h-full flex flex-col outline-none"
            style={{ background: T.bg, color: T.text }}
        >
            {/* Compact status strip — title lives in the window chrome */}
            <div
                className="flex items-center justify-between gap-3 px-3 h-8 shrink-0"
                style={{ borderBottom: `1px solid ${T.border}` }}
            >
                <div className="flex items-center gap-2 min-w-0 text-[10px]" style={{ color: T.textDim }}>
                    <span className="font-semibold tracking-wide" style={{ color: T.text }}>{ticker}</span>
                    <span style={{ color: T.textFaint }}>·</span>
                    <span>{isAnnual ? 'Annual' : 'Quarterly'}</span>
                    <span style={{ color: T.textFaint }}>·</span>
                    <span className="truncate" title={axisUnit}>{axisUnit}</span>
                </div>
                <div className="flex items-baseline gap-2 shrink-0">
                    {stats && (
                        <>
                            <span
                                className="text-sm font-semibold tabular-nums"
                                style={{ fontFamily: 'var(--font-mono, monospace)', color: T.text }}
                            >
                                {fmtFull(stats.latest, primarySeries.unit, currency, units)}
                            </span>
                            {stats.yoy != null && (
                                <span className="text-[10px] font-medium tabular-nums" style={{ color: growthColor(stats.yoy) }}>
                                    {stats.yoy >= 0 ? '+' : ''}{stats.yoy.toFixed(1)}% YoY
                                </span>
                            )}
                        </>
                    )}
                    <div className="flex items-center ml-1" style={{ borderLeft: `1px solid ${T.border}` }}>
                        <button onClick={exportPNG} className="text-[9px] px-1.5 py-0.5 font-medium hover:opacity-80" style={{ color: T.textFaint }}>PNG</button>
                        <button onClick={exportCSV} className="text-[9px] px-1.5 py-0.5 font-medium hover:opacity-80" style={{ color: T.textFaint }}>CSV</button>
                    </div>
                </div>
            </div>

            {/* Single toolbar row */}
            <div
                className="flex items-center justify-between gap-2 px-2 h-8 shrink-0"
                style={{ borderBottom: `1px solid ${T.border}`, background: T.panel }}
            >
                <div className="flex items-center gap-0.5 min-w-0">
                    <SegGroup>
                        <SegBtn active={transform === 'absolute'} onClick={() => setTransform('absolute')}>Abs</SegBtn>
                        <SegBtn active={transform === 'yoy'} onClick={() => setTransform('yoy')}>YoY</SegBtn>
                        <SegBtn active={transform === 'common'} onClick={() => commonBaseKey && setTransform('common')} disabled={!commonBaseKey}>%Rev</SegBtn>
                    </SegGroup>
                    <Divider />
                    {primarySeries && (
                        <SegGroup>
                            {(['bar', 'line', 'area'] as Representation[]).map(rp => (
                                <SegBtn
                                    key={rp}
                                    active={prepared.length > 0 && prepared.every(s => s.rep === rp)}
                                    onClick={() => setRepAll(rp)}
                                >
                                    {rp === 'bar' ? 'Bars' : rp === 'area' ? 'Area' : 'Line'}
                                </SegBtn>
                            ))}
                        </SegGroup>
                    )}
                    <Divider />
                    <div className="relative">
                        <SegBtn active={moreOpen || logScale || hasRefLines || effectiveStack !== 'off'} onClick={() => setMoreOpen(o => !o)}>
                            More
                        </SegBtn>
                        {moreOpen && (
                            <div
                                className="absolute top-7 left-0 z-30 w-52 py-1 shadow-2xl"
                                style={{ background: T.panelAlt, border: `1px solid ${T.border}` }}
                                onMouseLeave={() => setMoreOpen(false)}
                            >
                                <MoreRow label="Labels" on={showLabels} onClick={() => setShowLabels(v => !v)} />
                                <MoreRow label="Log scale" on={logScale} onClick={() => setLogScale(v => !v)} />
                                <MoreRow label="Stacked" on={effectiveStack === 'stack'} disabled={!stackEligible}
                                    onClick={() => setStackMode(m => (m === 'stack' ? 'off' : 'stack'))} />
                                <MoreRow label="100% stack" on={effectiveStack === 'pct'} disabled={!stackEligible}
                                    onClick={() => setStackMode(m => (m === 'pct' ? 'off' : 'pct'))} />
                                <div className="my-1 h-px" style={{ background: T.border }} />
                                <div className="px-2 py-1 text-[9px] uppercase tracking-wider" style={{ color: T.textFaint }}>Reference</div>
                                {([['min', 'Min'], ['max', 'Max'], ['median', 'Median'], ['avg', 'Average']] as [keyof RefLines, string][]).map(([k, lbl]) => (
                                    <MoreRow key={k} label={lbl} on={refLines[k]} onClick={() => setRefLines(r => ({ ...r, [k]: !r[k] }))} />
                                ))}
                                {scaleControlsVisible && (
                                    <>
                                        <div className="my-1 h-px" style={{ background: T.border }} />
                                        <div className="px-2 py-1 text-[9px] uppercase tracking-wider" style={{ color: T.textFaint }}>Scale</div>
                                        <div className="flex gap-0.5 px-2 py-1">
                                            {(['auto', 'K', 'M', 'B'] as UnitsMode[]).map(u => (
                                                <SegBtn key={u} active={units === u} onClick={() => setUnits(u)}>{u === 'auto' ? 'Auto' : u}</SegBtn>
                                            ))}
                                        </div>
                                    </>
                                )}
                                {primarySeries && (
                                    <>
                                        <div className="my-1 h-px" style={{ background: T.border }} />
                                        <MoreRow
                                            label="Iron bars"
                                            on={primarySeries.rep === 'ironBars'}
                                            onClick={() => setRep(primarySeries.key, primarySeries.rep === 'ironBars' ? 'bar' : 'ironBars')}
                                        />
                                    </>
                                )}
                            </div>
                        )}
                    </div>
                </div>

                <div className="flex items-center gap-0.5 relative shrink-0">
                    {prepared.length > 1 && (
                        <>
                            <SegGroup>
                                <SegBtn active={layout === 'single'} onClick={() => setLayout('single')}>Single</SegBtn>
                                <SegBtn active={layout === 'panels'} onClick={() => setLayout('panels')}>Panels</SegBtn>
                            </SegGroup>
                            <Divider />
                        </>
                    )}
                    {(isAnnual ? [3, 5, 10] : [2, 3, 5]).map(y => (
                        <PresetBtn key={y} onClick={() => applyPreset(y)}>{y}Y</PresetBtn>
                    ))}
                    <PresetBtn onClick={() => applyPreset('max')}>Max</PresetBtn>
                    <Divider />
                    <button
                        onClick={() => setFieldsOpen(o => !o)}
                        className="text-[10px] px-2 py-0.5 font-medium"
                        style={{ color: fieldsOpen ? T.accent : T.textDim }}
                    >
                        Fields
                    </button>
                </div>
            </div>

            {/* Body: fields sidebar (GF-style) + chart area */}
            <div className="flex-1 min-h-0 flex">
                {fieldsOpen && (
                    <FieldsSidebar
                        fields={allFields}
                        selected={selectedKeys}
                        prepared={prepared}
                        onToggle={toggleMetric}
                        onSetRep={setRep}
                    />
                )}

                <div className="flex-1 min-w-0 flex flex-col">
                    <div ref={svgWrapRef} className="flex-1 min-h-0 flex flex-col">
                        {layout === 'panels' && prepared.length > 1 ? (
                            prepared.map((s, i) => (
                                <div
                                    key={s.key}
                                    className="flex-1 min-h-0 relative"
                                    style={{ borderBottom: i < prepared.length - 1 ? `1px solid ${T.border}` : undefined }}
                                >
                                    <div
                                        className="absolute top-1 left-2 z-10 flex items-center gap-1.5 text-[9px] pointer-events-none"
                                        style={{ color: T.textDim }}
                                    >
                                        <span className="inline-block w-2 h-2" style={{ background: s.color }} />
                                        <span>{s.label}</span>
                                        <span className="tabular-nums" style={{ color: T.textFaint }}>
                                            {fmtCompact(s.values[range.end], s.unit, currency, units)}
                                        </span>
                                    </div>
                                    <ParentSize>
                                        {({ width, height }) =>
                                            width > 0 && height > 0 ? (
                                                <InnerChart
                                                    width={width}
                                                    height={height}
                                                    chronoPeriods={chronoPeriods}
                                                    estimateFlags={estimateFlags}
                                                    prepared={[{ ...s, axis: 'primary' }]}
                                                    range={range}
                                                    logScale={logScale}
                                                    stackMode="off"
                                                    currency={currency}
                                                    units={units}
                                                    showLabels={false}
                                                    refLines={i === 0 ? refLines : { min: false, max: false, median: false, avg: false }}
                                                    refStats={i === 0 && stats ? { min: stats.min, max: stats.max, median: stats.median, avg: stats.avg } : null}
                                                    hoverIdx={hoverIdx}
                                                    setHoverIdx={setHoverIdx}
                                                    compact
                                                />
                                            ) : null
                                        }
                                    </ParentSize>
                                </div>
                            ))
                        ) : (
                            <ParentSize>
                                {({ width, height }) =>
                                    width > 0 && height > 0 ? (
                                        <InnerChart
                                            width={width}
                                            height={height}
                                            chronoPeriods={chronoPeriods}
                                            estimateFlags={estimateFlags}
                                            prepared={prepared}
                                            range={range}
                                            logScale={logScale}
                                            stackMode={effectiveStack}
                                            currency={currency}
                                            units={units}
                                            showLabels={showLabels}
                                            refLines={refLines}
                                            refStats={stats ? { min: stats.min, max: stats.max, median: stats.median, avg: stats.avg } : null}
                                            hoverIdx={hoverIdx}
                                            setHoverIdx={setHoverIdx}
                                        />
                                    ) : null
                                }
                            </ParentSize>
                        )}
                    </div>

                    {chronoPeriods.length > 2 && primarySeries && (
                        <Overview
                            series={primarySeries}
                            periods={chronoPeriods}
                            estimateFlags={estimateFlags}
                            range={range}
                            onChange={(start, end) => setRange({ start, end })}
                        />
                    )}
                </div>
            </div>
        </div>
    );
}

// ============================================================================
// Inner chart (visx core)
// ============================================================================

interface InnerChartProps {
    width: number;
    height: number;
    chronoPeriods: string[];
    estimateFlags: boolean[];
    prepared: PreparedSeries[];
    range: { start: number; end: number };
    logScale: boolean;
    stackMode: 'off' | 'stack' | 'pct';
    currency: string;
    units: UnitsMode;
    showLabels: boolean;
    refLines: RefLines;
    refStats: { min: number; max: number; median: number; avg: number } | null;
    hoverIdx: number | null;
    setHoverIdx: (i: number | null) => void;
    /** Panel-per-field mode: tighter margins, no top padding for header strip. */
    compact?: boolean;
}

function InnerChart({
    width, height, chronoPeriods, estimateFlags, prepared, range,
    logScale, stackMode, currency, units, showLabels, refLines, refStats, hoverIdx, setHoverIdx,
    compact = false,
}: InnerChartProps) {
    const hasSecondary = prepared.some(s => s.axis === 'secondary');
    // Right margin always fits the Bloomberg-style last-value axis tag.
    const margin = {
        top: compact ? 16 : 14,
        right: hasSecondary ? 56 : 52,
        bottom: compact ? 18 : 26,
        left: compact ? 54 : 66,
    };
    const innerW = Math.max(0, width - margin.left - margin.right);
    const innerH = Math.max(0, height - margin.top - margin.bottom);

    const visibleIdx = useMemo(() => {
        const out: number[] = [];
        for (let i = range.start; i <= range.end; i++) out.push(i);
        return out;
    }, [range]);

    const xScale = useMemo(() => scaleBand<number>({
        domain: visibleIdx,
        range: [0, innerW],
        padding: 0.28,
    }), [visibleIdx, innerW]);

    const primaryUnit = prepared.find(s => s.axis === 'primary')?.unit || 'monetary';
    const secondaryUnit = prepared.find(s => s.axis === 'secondary')?.unit || 'percent';

    const collect = (axis: 'primary' | 'secondary') => {
        const vals: number[] = [];
        for (const s of prepared) {
            if (s.rep === 'ironBars') continue;   // iron bars use their own scale
            if (s.axis !== axis) continue;
            for (const i of visibleIdx) {
                const v = s.values[i];
                if (v !== null && !Number.isNaN(v)) vals.push(v);
            }
        }
        return vals;
    };

    // Independent scale for each "iron bars" background series.
    const ironScaleFor = (s: PreparedSeries) => {
        const vals: number[] = [];
        for (const i of visibleIdx) {
            const v = s.values[i];
            if (v !== null && !Number.isNaN(v)) vals.push(v);
        }
        if (vals.length === 0) return null;
        const min = Math.min(0, ...vals);
        const max = Math.max(...vals) * 1.05 || 1;
        return scaleLinear<number>({ domain: [min, max], range: [innerH, 0] });
    };

    const primVals = collect('primary');
    const allPositive = primVals.length > 0 && primVals.every(v => v > 0);
    const useLog = logScale && allPositive;

    const yPrimary = useMemo(() => {
        if (primVals.length === 0) return scaleLinear<number>({ domain: [0, 1], range: [innerH, 0] });
        if (useLog) {
            const min = Math.min(...primVals);
            const max = Math.max(...primVals);
            return scaleLog<number>({ domain: [min * 0.9, max * 1.1], range: [innerH, 0] });
        }
        let min = Math.min(0, ...primVals);
        let max = Math.max(0, ...primVals);
        const pad = (max - min) * 0.08 || 1;
        min -= min < 0 ? pad : 0;
        max += pad;
        return scaleLinear<number>({ domain: [min, max], range: [innerH, 0], nice: true });
    }, [primVals, innerH, useLog]);

    const ySecondary = useMemo(() => {
        const vals = collect('secondary');
        if (vals.length === 0) return null;
        let min = Math.min(0, ...vals);
        let max = Math.max(0, ...vals);
        const pad = (max - min) * 0.08 || 1;
        min -= min < 0 ? pad : 0; max += pad;
        return scaleLinear<number>({ domain: [min, max], range: [innerH, 0], nice: true });
    }, [prepared, visibleIdx, innerH]);

    // ---- Stacking (composition) -------------------------------------------
    const stackedOn = stackMode !== 'off';
    const stackMembers = useMemo(
        () => (stackedOn ? prepared.filter(s => s.axis === 'primary' && s.rep !== 'ironBars') : []),
        [stackedOn, prepared],
    );
    const stacking = stackMembers.length >= 2;
    const isStacked = (s: PreparedSeries) => stacking && s.axis === 'primary' && s.rep !== 'ironBars';

    const stackSegments = useMemo(() => {
        if (!stacking) return null;
        const map = new Map<number, { key: string; color: string; v: number; base: number; top: number }[]>();
        for (const i of visibleIdx) {
            const present = stackMembers
                .map(s => ({ s, v: s.values[i] }))
                .filter(x => x.v !== null && !Number.isNaN(x.v)) as { s: PreparedSeries; v: number }[];
            const total = present.reduce((a, x) => a + Math.abs(x.v), 0) || 1;
            let pos = 0, neg = 0;
            const segs = present.map(({ s, v }) => {
                if (stackMode === 'pct') {
                    const share = (Math.abs(v) / total) * 100;
                    const base = pos; const top = pos + share; pos = top;
                    return { key: s.key, color: s.color, v, base, top };
                }
                if (v >= 0) { const base = pos; const top = pos + v; pos = top; return { key: s.key, color: s.color, v, base, top }; }
                const top = neg; const base = neg + v; neg = base; return { key: s.key, color: s.color, v, base, top };
            });
            map.set(i, segs);
        }
        return map;
    }, [stacking, stackMembers, visibleIdx, stackMode]);

    const stackDomain = useMemo<[number, number]>(() => {
        if (!stacking) return [0, 1];
        if (stackMode === 'pct') return [0, 100];
        let maxTop = 0, minBase = 0;
        stackSegments!.forEach(segs => segs.forEach(g => {
            maxTop = Math.max(maxTop, g.top, g.base);
            minBase = Math.min(minBase, g.base, g.top);
        }));
        const pad = (maxTop - minBase) * 0.08 || 1;
        return [minBase, maxTop + pad];
    }, [stacking, stackMode, stackSegments]);

    const yStack = useMemo(
        () => scaleLinear<number>({ domain: stackDomain, range: [innerH, 0], nice: stackMode !== 'pct' }),
        [stackDomain, innerH, stackMode],
    );

    const useLogEff = useLog && !stacking;
    const yPrimaryEff = stacking ? yStack : yPrimary;
    const primaryUnitEff: UnitKind = stacking && stackMode === 'pct' ? 'percent' : primaryUnit;

    const yFor = (s: PreparedSeries) => (s.axis === 'secondary' && ySecondary ? ySecondary : yPrimaryEff);
    const bandCenter = (i: number) => (xScale(i) ?? 0) + xScale.bandwidth() / 2;

    const zeroY = useLogEff ? innerH : yPrimaryEff(0);

    // First estimate index inside the visible window (for "today" divider).
    const firstEstVisible = useMemo(() => {
        for (const i of visibleIdx) if (estimateFlags[i]) return i;
        return null;
    }, [visibleIdx, estimateFlags]);

    // Tooltip position.
    const [tip, setTip] = useState<{ x: number; y: number; idx: number } | null>(null);
    const handleMove = useCallback((e: React.MouseEvent<SVGRectElement>) => {
        const pt = localPoint(e);
        if (!pt) return;
        const rel = pt.x - margin.left;
        const n = visibleIdx.length;
        if (n === 0 || innerW === 0) return;
        let k = Math.floor((rel / innerW) * n);
        k = Math.max(0, Math.min(n - 1, k));
        const idx = visibleIdx[k];
        setHoverIdx(idx);
        setTip({ x: pt.x, y: pt.y, idx });
    }, [margin.left, visibleIdx, innerW, setHoverIdx]);

    const handleLeave = useCallback(() => { setHoverIdx(null); setTip(null); }, [setHoverIdx]);

    const tickEvery = Math.ceil(visibleIdx.length / Math.max(1, Math.floor(innerW / 56)));

    return (
        <div className="relative" style={{ width, height }}>
            <svg width={width} height={height}>
                <defs>
                    <pattern id="estHatch" width={5} height={5} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                        <rect width={5} height={5} fill="transparent" />
                        <line x1={0} y1={0} x2={0} y2={5} stroke={T.accent} strokeWidth={1.2} opacity={0.5} />
                    </pattern>
                </defs>
                <Group left={margin.left} top={margin.top}>
                    {/* estimate region background */}
                    {firstEstVisible !== null && (
                        <rect
                            x={(xScale(firstEstVisible) ?? 0) - xScale.step() * xScale.padding() / 2}
                            y={0}
                            width={innerW - (xScale(firstEstVisible) ?? 0) + xScale.step() * xScale.padding() / 2}
                            height={innerH}
                            fill={T.accent}
                            opacity={0.04}
                        />
                    )}

                    {/* iron bars (Bloomberg-style background metric) */}
                    {prepared.filter(s => s.rep === 'ironBars').map(s => {
                        const sc = ironScaleFor(s);
                        if (!sc) return null;
                        return (
                            <Group key={`iron-${s.key}`}>
                                {visibleIdx.map(i => {
                                    const v = s.values[i];
                                    if (v === null || Number.isNaN(v)) return null;
                                    const yv = sc(v);
                                    const x = bandCenter(i);
                                    const bw = Math.max(2, xScale.bandwidth() * 0.5);
                                    return <rect key={i} x={x - bw / 2} y={yv} width={bw} height={Math.max(0, innerH - yv)} fill={s.color} opacity={0.16} />;
                                })}
                            </Group>
                        );
                    })}

                    <GridRows scale={yPrimaryEff} width={innerW} height={innerH} stroke={T.grid} strokeWidth={1} numTicks={5} />

                    {/* zero baseline */}
                    {!useLogEff && yPrimaryEff(0) >= 0 && yPrimaryEff(0) <= innerH && (
                        <line x1={0} x2={innerW} y1={zeroY} y2={zeroY} stroke={T.textFaint} strokeWidth={1} />
                    )}

                    {/* reference lines (min / max / median / average of primary) */}
                    {refStats && !useLogEff && !stacking && (['min', 'max', 'median', 'avg'] as const).map(k => (
                        refLines[k] ? (
                            <Group key={`ref-${k}`}>
                                <line x1={0} x2={innerW} y1={yPrimaryEff(refStats[k])} y2={yPrimaryEff(refStats[k])} stroke={T.textDim} strokeDasharray="4 4" strokeWidth={1} opacity={0.55} />
                                <text x={innerW - 2} y={yPrimaryEff(refStats[k]) - 3} textAnchor="end" fontSize={8} fill={T.textDim}>
                                    {k.toUpperCase()} {fmtCompact(refStats[k], primaryUnit, currency, units)}
                                </text>
                            </Group>
                        ) : null
                    ))}

                    {/* stacked composition bars */}
                    {stacking && visibleIdx.map(i => {
                        const segs = stackSegments!.get(i) || [];
                        const x = xScale(i) ?? 0;
                        const isEst = estimateFlags[i];
                        return (
                            <g key={`stk-${i}`}>
                                {segs.map(g => {
                                    const yTop = yPrimaryEff(g.top);
                                    const yBase = yPrimaryEff(g.base);
                                    const h = Math.abs(yBase - yTop);
                                    return (
                                        <g key={g.key}>
                                            <rect x={x} y={Math.min(yTop, yBase)} width={xScale.bandwidth()} height={Math.max(0, h)} fill={g.color} opacity={isEst ? 0.45 : 0.92} />
                                            {isEst && <rect x={x} y={Math.min(yTop, yBase)} width={xScale.bandwidth()} height={Math.max(0, h)} fill="url(#estHatch)" />}
                                        </g>
                                    );
                                })}
                            </g>
                        );
                    })}

                    {/* area series */}
                    {prepared.filter(s => s.rep === 'area' && !isStacked(s)).map(s => {
                        const y = yFor(s);
                        const pts = visibleIdx
                            .map(i => ({ i, v: s.values[i] }))
                            .filter(p => p.v !== null && !Number.isNaN(p.v as number)) as { i: number; v: number }[];
                        return (
                            <Group key={`area-${s.key}`}>
                                <AreaClosed data={pts} x={p => bandCenter(p.i)} y={p => y(p.v)} yScale={y} curve={curveMonotoneX} fill={s.color} fillOpacity={0.18} stroke={s.color} strokeWidth={2} />
                                {pts.map(p => (
                                    <circle key={p.i} cx={bandCenter(p.i)} cy={y(p.v)} r={2.4} fill={s.color} />
                                ))}
                            </Group>
                        );
                    })}

                    {/* bar series — multiple bar series render grouped side-by-side
                        within each period band (Bloomberg GF style) */}
                    {(() => {
                        const barSeries = prepared.filter(s => s.rep === 'bar' && !isStacked(s));
                        const nGroups = barSeries.length;
                        if (nGroups === 0) return null;
                        const gap = nGroups > 1 ? 1 : 0;
                        const slotW = (xScale.bandwidth() - gap * (nGroups - 1)) / nGroups;
                        return barSeries.map((s, slot) => (
                            <Group key={`bar-${s.key}`}>
                                {visibleIdx.map(i => {
                                    const v = s.values[i];
                                    if (v === null || Number.isNaN(v)) return null;
                                    const y0 = yFor(s)(0);
                                    const zero = useLogEff ? innerH : Math.max(0, Math.min(innerH, y0));
                                    const yv = yFor(s)(v);
                                    const top = Math.min(yv, zero);
                                    const h = Math.abs(yv - zero);
                                    const x = (xScale(i) ?? 0) + slot * (slotW + gap);
                                    const isEst = estimateFlags[i];
                                    const fill = v < 0 ? T.neg : s.color;
                                    return (
                                        <g key={i}>
                                            <rect x={x} y={top} width={Math.max(1, slotW)} height={Math.max(0, h)} rx={nGroups > 1 ? 1 : 2} fill={fill} opacity={isEst ? 0.4 : 0.9} />
                                            {isEst && <rect x={x} y={top} width={Math.max(1, slotW)} height={Math.max(0, h)} rx={nGroups > 1 ? 1 : 2} fill="url(#estHatch)" />}
                                        </g>
                                    );
                                })}
                            </Group>
                        ));
                    })()}

                    {/* line series (split actual / estimate) */}
                    {prepared.filter(s => s.rep === 'line' && !isStacked(s)).map(s => {
                        const y = yFor(s);
                        const pts = visibleIdx
                            .map(i => ({ i, v: s.values[i] }))
                            .filter(p => p.v !== null && !Number.isNaN(p.v as number)) as { i: number; v: number }[];
                        const actual = pts.filter(p => !estimateFlags[p.i]);
                        const est = pts.filter((p, k) => estimateFlags[p.i] || (k > 0 && estimateFlags[pts[k - 1]?.i]));
                        return (
                            <Group key={`line-${s.key}`}>
                                <LinePath data={actual} x={p => bandCenter(p.i)} y={p => y(p.v)} stroke={s.color} strokeWidth={2} curve={curveMonotoneX} />
                                {est.length > 1 && (
                                    <LinePath data={est} x={p => bandCenter(p.i)} y={p => y(p.v)} stroke={s.color} strokeWidth={2} strokeDasharray="4 3" curve={curveMonotoneX} opacity={0.8} />
                                )}
                                {pts.map(p => (
                                    <circle key={p.i} cx={bandCenter(p.i)} cy={y(p.v)} r={2.6} fill={estimateFlags[p.i] ? T.bg : s.color} stroke={s.color} strokeWidth={1.4} />
                                ))}
                            </Group>
                        );
                    })}

                    {/* value labels (primary series, TIKR-style) */}
                    {showLabels && !stacking && prepared[0] && prepared[0].rep !== 'ironBars' && visibleIdx.length <= 24 && (() => {
                        const s = prepared[0];
                        const y = yFor(s);
                        return (
                            <Group>
                                {visibleIdx.map(i => {
                                    const v = s.values[i];
                                    if (v === null || Number.isNaN(v)) return null;
                                    const yv = y(v);
                                    return (
                                        <text key={i} x={bandCenter(i)} y={v >= 0 ? yv - 5 : yv + 11} textAnchor="middle" fontSize={9} fontWeight={600} fill={T.text}>
                                            {fmtCompact(v, s.unit, currency, units)}
                                        </text>
                                    );
                                })}
                            </Group>
                        );
                    })()}

                    {/* "today" divider */}
                    {firstEstVisible !== null && (
                        <line
                            x1={(xScale(firstEstVisible) ?? 0) - xScale.step() * xScale.padding() / 2}
                            x2={(xScale(firstEstVisible) ?? 0) - xScale.step() * xScale.padding() / 2}
                            y1={0} y2={innerH} stroke={T.accent} strokeDasharray="3 3" strokeWidth={1} opacity={0.5}
                        />
                    )}

                    {/* crosshair */}
                    {hoverIdx !== null && visibleIdx.includes(hoverIdx) && (
                        <line x1={bandCenter(hoverIdx)} x2={bandCenter(hoverIdx)} y1={0} y2={innerH} stroke={T.text} strokeWidth={1} opacity={0.25} />
                    )}

                    <AxisLeft
                        scale={yPrimaryEff}
                        numTicks={5}
                        tickFormat={(v) => fmtCompact(Number(v), primaryUnitEff, currency, units)}
                        stroke={T.border}
                        tickStroke={T.border}
                        tickLabelProps={() => ({ fill: T.textDim, fontSize: 9, textAnchor: 'end', dx: -2, dy: 3 })}
                    />
                    {ySecondary && (
                        <AxisRight
                            left={innerW}
                            scale={ySecondary}
                            numTicks={5}
                            tickFormat={(v) => fmtCompact(Number(v), secondaryUnit, currency, units)}
                            stroke={T.border}
                            tickStroke={T.border}
                            tickLabelProps={() => ({ fill: T.textDim, fontSize: 9, textAnchor: 'start', dx: 2, dy: 3 })}
                        />
                    )}
                    <AxisBottom
                        top={innerH}
                        scale={xScale}
                        tickFormat={(i) => shortPeriodLabel(chronoPeriods[Number(i)])}
                        tickValues={visibleIdx.filter((_, k) => k % tickEvery === 0)}
                        stroke={T.border}
                        tickStroke={T.border}
                        tickLabelProps={() => ({ fill: T.textDim, fontSize: 9, textAnchor: 'middle', dy: 2 })}
                    />

                    {/* Bloomberg-style last-value tags on the right axis
                        (with simple vertical de-overlap when values collide) */}
                    {!stacking && (() => {
                        const tags: { key: string; color: string; y: number; text: string }[] = [];
                        for (const s of prepared) {
                            if (s.rep === 'ironBars') continue;
                            let lastIdx: number | null = null;
                            for (let k = visibleIdx.length - 1; k >= 0; k--) {
                                const v = s.values[visibleIdx[k]];
                                if (v !== null && !Number.isNaN(v)) { lastIdx = visibleIdx[k]; break; }
                            }
                            if (lastIdx === null) continue;
                            const v = s.values[lastIdx] as number;
                            const yv = yFor(s)(v);
                            if (yv < -2 || yv > innerH + 2) continue;
                            tags.push({ key: s.key, color: s.color, y: yv, text: fmtCompact(v, s.unit, currency, units) });
                        }
                        // Push overlapping tags apart (14px tag height + 1px gap).
                        tags.sort((a, b) => a.y - b.y);
                        for (let i = 1; i < tags.length; i++) {
                            if (tags[i].y - tags[i - 1].y < 15) tags[i].y = tags[i - 1].y + 15;
                        }
                        for (let i = tags.length - 1; i >= 0; i--) {
                            if (tags[i].y > innerH) tags[i].y = innerH;
                            if (i < tags.length - 1 && tags[i + 1].y - tags[i].y < 15) tags[i].y = tags[i + 1].y - 15;
                        }
                        return tags.map(t => {
                            const w = Math.max(34, t.text.length * 5.4 + 8);
                            return (
                                <g key={`tag-${t.key}`}>
                                    <rect x={innerW + 2} y={t.y - 7} width={w} height={14} fill={t.color} />
                                    <text
                                        x={innerW + 2 + w / 2}
                                        y={t.y + 3}
                                        textAnchor="middle"
                                        fontSize={8.5}
                                        fontWeight={700}
                                        fill="#000000"
                                        style={{ fontFamily: 'var(--font-mono, monospace)' }}
                                    >
                                        {t.text}
                                    </text>
                                </g>
                            );
                        });
                    })()}

                    {/* mouse capture */}
                    <rect x={0} y={0} width={innerW} height={innerH} fill="transparent" onMouseMove={handleMove} onMouseLeave={handleLeave} />
                </Group>
            </svg>

            {tip && (
                <div
                    className="pointer-events-none absolute z-20 rounded px-2 py-1.5 text-[10px]"
                    style={{
                        left: Math.min(tip.x + 12, width - 150),
                        top: Math.max(8, tip.y - 10),
                        background: T.panelAlt,
                        border: `1px solid ${T.border}`,
                        boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                        minWidth: 120,
                    }}
                >
                    <div className="font-semibold mb-1" style={{ color: T.text }}>
                        {periodLabel(chronoPeriods[tip.idx])}{estimateFlags[tip.idx] ? ' (Est.)' : ''}
                    </div>
                    {prepared.map(s => (
                        <div key={s.key} className="flex items-center justify-between gap-3">
                            <span className="flex items-center gap-1" style={{ color: T.textDim }}>
                                <span className="inline-block w-2 h-2 rounded-sm" style={{ background: s.color }} />
                                {s.label}
                            </span>
                            <span className="tabular-nums font-medium" style={{ color: T.text }}>
                                {fmtFull(s.values[tip.idx], s.unit, currency, units)}
                            </span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

// ============================================================================
// Overview / range brush
// ============================================================================

interface OverviewProps {
    series: PreparedSeries;
    periods: string[];
    estimateFlags: boolean[];
    range: { start: number; end: number };
    onChange: (start: number, end: number) => void;
}

function Overview({ series, periods, range, onChange }: OverviewProps) {
    const ref = useRef<HTMLDivElement>(null);
    const [drag, setDrag] = useState<'start' | 'end' | 'range' | null>(null);
    const [startX, setStartX] = useState(0);
    const [startIdx, setStartIdx] = useState({ start: 0, end: 0 });
    const n = periods.length;

    const onDown = (e: React.MouseEvent, type: 'start' | 'end' | 'range') => {
        e.preventDefault();
        setDrag(type); setStartX(e.clientX); setStartIdx({ ...range });
    };

    useEffect(() => {
        if (!drag) return;
        const move = (e: MouseEvent) => {
            if (!ref.current) return;
            const w = ref.current.getBoundingClientRect().width;
            const d = Math.round(((e.clientX - startX) / w) * (n - 1));
            if (drag === 'start') onChange(Math.max(0, Math.min(range.end - 1, startIdx.start + d)), range.end);
            else if (drag === 'end') onChange(range.start, Math.max(range.start + 1, Math.min(n - 1, startIdx.end + d)));
            else {
                const span = startIdx.end - startIdx.start;
                let s = startIdx.start + d;
                if (s < 0) s = 0;
                if (s + span > n - 1) s = n - 1 - span;
                onChange(s, s + span);
            }
        };
        const up = () => setDrag(null);
        document.addEventListener('mousemove', move);
        document.addEventListener('mouseup', up);
        return () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); };
    }, [drag, startX, startIdx, range, n, onChange]);

    // Mini area path (normalized).
    const W = 1000, H = 36;
    const vals = series.values;
    const nums = vals.filter((v): v is number => v !== null && !Number.isNaN(v));
    const min = nums.length ? Math.min(0, ...nums) : 0;
    const max = nums.length ? Math.max(0, ...nums) : 1;
    const sx = (i: number) => (n <= 1 ? 0 : (i / (n - 1)) * W);
    const sy = (v: number) => H - ((v - min) / ((max - min) || 1)) * H;

    const startPct = n <= 1 ? 0 : (range.start / (n - 1)) * 100;
    const endPct = n <= 1 ? 100 : (range.end / (n - 1)) * 100;

    return (
        <div className="px-3 py-1.5" style={{ borderTop: `1px solid ${T.border}`, background: T.panel }}>
            <div ref={ref} className="relative" style={{ height: H }}>
                <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="absolute inset-0">
                    <AreaClosed
                        data={vals.map((v, i) => ({ i, v })).filter(d => d.v !== null) as { i: number; v: number }[]}
                        x={d => sx(d.i)}
                        y={d => sy(d.v)}
                        yScale={scaleLinear({ domain: [min, max], range: [H, 0] })}
                        curve={curveMonotoneX}
                        fill={series.color}
                        fillOpacity={0.12}
                        stroke={series.color}
                        strokeWidth={1}
                    />
                </svg>
                <div className="absolute top-0 bottom-0 cursor-grab active:cursor-grabbing"
                    style={{ left: `${startPct}%`, width: `${endPct - startPct}%`, background: `${T.accent}18`, borderLeft: `1px solid ${T.accent}`, borderRight: `1px solid ${T.accent}` }}
                    onMouseDown={e => onDown(e, 'range')} />
                <div className="absolute top-0 bottom-0 w-2 -ml-1 cursor-ew-resize" style={{ left: `${startPct}%` }} onMouseDown={e => onDown(e, 'start')} />
                <div className="absolute top-0 bottom-0 w-2 -ml-1 cursor-ew-resize" style={{ left: `${endPct}%` }} onMouseDown={e => onDown(e, 'end')} />
            </div>
            <div className="flex items-center justify-between mt-0.5 text-[9px]" style={{ color: T.textFaint }}>
                <span>{periodLabel(periods[range.start])}</span>
                <span>{range.end - range.start + 1}/{n}</span>
                <span>{periodLabel(periods[range.end])}</span>
            </div>
        </div>
    );
}

// ============================================================================
// Fields sidebar — Bloomberg GF "Select Fields" panel
// ============================================================================

function FieldsSidebar({ fields, selected, prepared, onToggle, onSetRep }: {
    fields: ChartSeriesField[];
    selected: string[];
    prepared: PreparedSeries[];
    onToggle: (key: string) => void;
    onSetRep: (key: string, rep: Representation) => void;
}) {
    const [q, setQ] = useState('');

    const seriesFor = (key: string) => prepared.find(s => s.key === key);

    // Group by section, preserving field order. Fields without a section go
    // into a single unnamed bucket so plain statements render as a flat list.
    const groups = useMemo(() => {
        const query = q.trim().toLowerCase();
        const out: { section: string; items: ChartSeriesField[] }[] = [];
        const index = new Map<string, number>();
        for (const f of fields) {
            if (query && !f.label.toLowerCase().includes(query)) continue;
            const section = f.section || '';
            if (!index.has(section)) {
                index.set(section, out.length);
                out.push({ section, items: [] });
            }
            out[index.get(section)!].items.push(f);
        }
        return out;
    }, [fields, q]);

    const atCapacity = selected.length >= MAX_SERIES;

    return (
        <div
            className="w-56 shrink-0 flex flex-col min-h-0"
            style={{ borderRight: `1px solid ${T.border}`, background: T.panel }}
        >
            <input
                value={q}
                onChange={e => setQ(e.target.value)}
                placeholder="Filter fields…"
                className="w-full px-2 py-1.5 text-[10px] bg-transparent outline-none shrink-0"
                style={{ color: T.text, borderBottom: `1px solid ${T.border}` }}
            />
            <div className="flex-1 overflow-y-auto py-1">
                {groups.map(g => (
                    <div key={g.section || '_'}>
                        {g.section && (
                            <div className="px-2 pt-2 pb-0.5 text-[8px] font-semibold uppercase tracking-widest" style={{ color: T.textFaint }}>
                                {g.section}
                            </div>
                        )}
                        {g.items.map(f => {
                            const on = selected.includes(f.key);
                            const series = on ? seriesFor(f.key) : undefined;
                            const disabled = !on && atCapacity;
                            return (
                                <div
                                    key={f.key}
                                    className="w-full flex items-center gap-1.5 px-2 py-[3px] hover:bg-white/5 group"
                                >
                                    <button
                                        onClick={() => onToggle(f.key)}
                                        disabled={disabled}
                                        title={f.label}
                                        className="flex items-center gap-1.5 min-w-0 flex-1 text-left disabled:opacity-30"
                                    >
                                        <span
                                            className="inline-block w-2.5 h-2.5 shrink-0"
                                            style={{
                                                background: on ? series?.color : 'transparent',
                                                border: `1px solid ${on ? series?.color : T.border}`,
                                            }}
                                        />
                                        <span className="truncate text-[10px]" style={{ color: on ? T.text : T.textDim }}>
                                            {f.label}
                                        </span>
                                    </button>
                                    {series && (
                                        <span className="inline-flex shrink-0" style={{ border: `1px solid ${T.border}` }}>
                                            {(['bar', 'line', 'area'] as Representation[]).map(rp => (
                                                <button
                                                    key={rp}
                                                    onClick={() => onSetRep(f.key, rp)}
                                                    title={rp === 'bar' ? 'Bars' : rp === 'line' ? 'Line' : 'Area'}
                                                    className="px-1 text-[8px] font-bold leading-[13px]"
                                                    style={{
                                                        background: series.rep === rp ? series.color : 'transparent',
                                                        color: series.rep === rp ? '#000' : T.textFaint,
                                                    }}
                                                >
                                                    {rp === 'bar' ? 'B' : rp === 'line' ? 'L' : 'A'}
                                                </button>
                                            ))}
                                        </span>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                ))}
                {groups.length === 0 && (
                    <div className="px-2 py-2 text-[10px]" style={{ color: T.textFaint }}>No results</div>
                )}
            </div>
            <div className="px-2 py-1 text-[9px] shrink-0 tabular-nums" style={{ color: T.textFaint, borderTop: `1px solid ${T.border}` }}>
                {selected.length}/{MAX_SERIES} fields
            </div>
        </div>
    );
}

// ============================================================================
// Small UI atoms
// ============================================================================

function SegGroup({ children }: { children: React.ReactNode }) {
    return (
        <div className="inline-flex items-center" style={{ border: `1px solid ${T.border}` }}>
            {children}
        </div>
    );
}

function SegBtn({ children, active, onClick, disabled }: {
    children: React.ReactNode; active?: boolean; onClick: () => void; disabled?: boolean;
}) {
    return (
        <button onClick={onClick} disabled={disabled}
            className="text-[10px] px-2 py-0.5 font-medium transition-colors disabled:opacity-30"
            style={{
                background: active ? T.accent : 'transparent',
                color: active ? '#03101f' : T.textDim,
            }}>
            {children}
        </button>
    );
}

function Divider() {
    return <div className="mx-1 h-3.5 w-px shrink-0" style={{ background: T.border }} />;
}

function MoreRow({ label, on, onClick, disabled }: {
    label: string; on?: boolean; onClick: () => void; disabled?: boolean;
}) {
    return (
        <button
            onClick={onClick}
            disabled={disabled}
            className="w-full flex items-center justify-between px-2 py-1 text-[11px] text-left hover:bg-white/5 disabled:opacity-30"
            style={{ color: on ? T.accent : T.text }}
        >
            <span>{label}</span>
            <span
                className="inline-block w-3 h-3 shrink-0"
                style={{
                    background: on ? T.accent : 'transparent',
                    border: `1px solid ${on ? T.accent : T.border}`,
                }}
            />
        </button>
    );
}

function PresetBtn({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
    return (
        <button onClick={onClick} className="text-[10px] px-1.5 py-0.5 font-medium hover:opacity-80" style={{ color: T.textDim }}>
            {children}
        </button>
    );
}

export const FINANCIAL_CHART_PRO_CONFIG = {
    width: 1000,
    height: 600,
    minWidth: 720,
    minHeight: 440,
    maxWidth: 1600,
    maxHeight: 1000,
};
