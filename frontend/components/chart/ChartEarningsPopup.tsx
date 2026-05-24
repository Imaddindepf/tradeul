'use client';

import { useEffect, useMemo, useRef } from 'react';
import type { EarningsRecord } from './hooks/useEarningsMarkers';
import { EarningsBadgeIcon, CloseIcon } from './icons';

/**
 * In-pane popup shown when the user clicks an earnings marker. Mirrors the
 * TradingView "Beneficios e ingresos" panel — same sections, same number
 * formatting, same color cues for surprise %.
 *
 * Positioning: anchored at (x, y) in chart-container coords. Clamped so it
 * never falls outside the chart container on either axis. If there isn't
 * enough room on the right we flip to the left side of the click point.
 */
interface ChartEarningsPopupProps {
    record: EarningsRecord;
    ticker: string;
    x: number;
    y: number;
    containerWidth: number;
    containerHeight: number;
    onClose: () => void;
    /** Optional handler to open the dedicated earnings view. */
    onOpenMore?: () => void;
}

const PANEL_WIDTH = 280;
const PANEL_MAX_HEIGHT = 360;

export function ChartEarningsPopup({
    record, ticker, x, y, containerWidth, containerHeight, onClose, onOpenMore,
}: ChartEarningsPopupProps) {
    const ref = useRef<HTMLDivElement>(null);

    // Click outside / Escape closes.
    useEffect(() => {
        const onClick = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) onClose();
        };
        const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
        // Defer so the click that opened us doesn't also close us.
        const t = setTimeout(() => {
            document.addEventListener('mousedown', onClick);
            document.addEventListener('keydown', onKey);
        }, 0);
        return () => {
            clearTimeout(t);
            document.removeEventListener('mousedown', onClick);
            document.removeEventListener('keydown', onKey);
        };
    }, [onClose]);

    // Clamp position inside container, flipping to the left of the click
    // anchor when we'd otherwise overflow the right edge.
    const pos = useMemo(() => {
        const gap = 12;
        let left = x + gap;
        if (left + PANEL_WIDTH > containerWidth - 8) {
            // Flip to the left of the click point.
            left = Math.max(8, x - gap - PANEL_WIDTH);
        }
        let top = y;
        if (top + PANEL_MAX_HEIGHT > containerHeight - 8) {
            top = Math.max(8, containerHeight - PANEL_MAX_HEIGHT - 8);
        }
        return { left, top };
    }, [x, y, containerWidth, containerHeight]);

    const dateLabel = formatLongDate(record.report_date);
    const fiscalLabel = formatFiscalPeriod(record);
    const isReported = record.status === 'reported' && record.eps_actual != null;

    return (
        <div
            ref={ref}
            className="absolute z-[60] rounded-md border border-[color:var(--color-border)] bg-[color:var(--color-surface)] text-[11px] shadow-2xl"
            style={{
                left: pos.left,
                top: pos.top,
                width: PANEL_WIDTH,
                maxHeight: PANEL_MAX_HEIGHT,
                overflowY: 'auto',
            }}
            onClick={(e) => e.stopPropagation()}
        >
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-[color:var(--color-border-subtle)]">
                <div className="flex items-center gap-1.5">
                    <span className="flex items-center justify-center w-4 h-4 rounded-full ring-2 ring-[color:var(--color-chart-marker-earnings)] text-[color:var(--color-chart-marker-earnings)] text-[8px] font-bold">
                        E
                    </span>
                    <span className="font-semibold text-[color:var(--color-fg)]">
                        Beneficios e ingresos
                    </span>
                </div>
                <button
                    onClick={onClose}
                    className="p-0.5 rounded text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)] hover:bg-[color:var(--color-surface-hover)]"
                    aria-label="Cerrar"
                >
                    <CloseIcon className="w-3.5 h-3.5" />
                </button>
            </div>

            {/* Metadata rows */}
            <div className="px-3 py-2 grid grid-cols-2 gap-y-1 text-[color:var(--color-muted-fg)]">
                <span>Fecha</span>
                <span className="text-right text-[color:var(--color-fg)]">{dateLabel}</span>
                {fiscalLabel && (
                    <>
                        <span>Finalización del período</span>
                        <span className="text-right text-[color:var(--color-fg)]">{fiscalLabel}</span>
                    </>
                )}
                {record.time_slot && (
                    <>
                        <span>Hora</span>
                        <span className="text-right text-[color:var(--color-fg)]">{formatTimeSlot(record.time_slot)}</span>
                    </>
                )}
            </div>

            {/* BENEFICIOS / EPS section */}
            <Section label="Beneficios">
                <Row
                    label="Estandarizado"
                    value={formatNumber(record.previous_eps, 3)}
                />
                <Row
                    label="Informado"
                    value={formatNumber(record.eps_actual, 2)}
                    tone={isReported ? 'strong' : undefined}
                />
                <Row
                    label="Estimación"
                    value={formatNumber(record.eps_estimate, 3)}
                />
                <Row
                    label="Sorpresa"
                    value={formatEpsSurprise(record)}
                    tone={surpriseTone(record.eps_surprise_pct)}
                />
            </Section>

            {/* INGRESOS / REVENUE section */}
            <Section label="Ingresos">
                <Row
                    label="Informado"
                    value={formatLargeMoney(record.revenue_actual)}
                    tone={isReported ? 'strong' : undefined}
                />
                <Row
                    label="Estimación"
                    value={formatLargeMoney(record.revenue_estimate)}
                />
                <Row
                    label="Sorpresa"
                    value={formatRevenueSurprise(record)}
                    tone={surpriseTone(record.revenue_surprise_pct)}
                />
            </Section>

            {/* Footer link */}
            <div className="px-3 py-2 border-t border-[color:var(--color-border-subtle)]">
                <button
                    onClick={onOpenMore}
                    className="text-[color:var(--color-primary)] hover:underline text-[11px]"
                >
                    Más beneficios de {ticker}
                </button>
            </div>
        </div>
    );
}

// ─── Sub-components ─────────────────────────────────────────────────────────

function Section({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div className="px-3 pt-1 pb-2 border-t border-[color:var(--color-border-subtle)]">
            <div className="text-[9px] uppercase tracking-wider font-semibold text-[color:var(--color-muted-fg)]/80 mb-1">
                {label}
            </div>
            <div className="flex flex-col gap-0.5">{children}</div>
        </div>
    );
}

function Row({
    label, value, tone,
}: {
    label: string;
    value: string;
    tone?: 'up' | 'down' | 'strong';
}) {
    const cls =
        tone === 'up' ? 'text-[color:var(--color-chart-up)] font-semibold' :
        tone === 'down' ? 'text-[color:var(--color-chart-down)] font-semibold' :
        tone === 'strong' ? 'text-[color:var(--color-fg)] font-semibold' :
        'text-[color:var(--color-fg)]';
    return (
        <div className="flex items-center justify-between">
            <span className="text-[color:var(--color-muted-fg)]">{label}</span>
            <span className={`tabular-nums ${cls}`}>{value}</span>
        </div>
    );
}

// ─── Formatters ─────────────────────────────────────────────────────────────

function formatNumber(value: number | null | undefined, decimals = 2): string {
    if (value == null || !Number.isFinite(value)) return '—';
    return value.toLocaleString('es-ES', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    });
}

function formatLargeMoney(value: number | null | undefined): string {
    if (value == null || !Number.isFinite(value)) return '—';
    const abs = Math.abs(value);
    if (abs >= 1e12) return `${(value / 1e12).toLocaleString('es-ES', { maximumFractionDigits: 2 })} T`;
    if (abs >= 1e9) return `${(value / 1e9).toLocaleString('es-ES', { maximumFractionDigits: 2 })} B`;
    if (abs >= 1e6) return `${(value / 1e6).toLocaleString('es-ES', { maximumFractionDigits: 2 })} M`;
    if (abs >= 1e3) return `${(value / 1e3).toLocaleString('es-ES', { maximumFractionDigits: 2 })} K`;
    return value.toLocaleString('es-ES');
}

function formatEpsSurprise(r: EarningsRecord): string {
    if (r.eps_actual == null || r.eps_estimate == null) return '—';
    const diff = r.eps_actual - r.eps_estimate;
    const pct = r.eps_surprise_pct != null ? Math.abs(r.eps_surprise_pct) * 100 : null;
    const sign = diff >= 0 ? '' : '−';
    const absDiff = Math.abs(diff);
    const main = absDiff.toLocaleString('es-ES', { minimumFractionDigits: 3, maximumFractionDigits: 3 });
    return pct != null
        ? `${sign}${main} (${pct.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%)`
        : `${sign}${main}`;
}

function formatRevenueSurprise(r: EarningsRecord): string {
    if (r.revenue_actual == null || r.revenue_estimate == null) return '—';
    const diff = r.revenue_actual - r.revenue_estimate;
    const pct = r.revenue_surprise_pct != null ? Math.abs(r.revenue_surprise_pct) * 100 : null;
    const sign = diff >= 0 ? '' : '−';
    const formattedDiff = formatLargeMoney(Math.abs(diff));
    return pct != null
        ? `${sign}${formattedDiff} (${pct.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%)`
        : `${sign}${formattedDiff}`;
}

function surpriseTone(pct: number | null | undefined): 'up' | 'down' | undefined {
    if (pct == null || !Number.isFinite(pct)) return undefined;
    if (pct > 0) return 'up';
    if (pct < 0) return 'down';
    return undefined;
}

/** "2026-05-06" -> "mié 06 May '26". */
function formatLongDate(iso: string): string {
    const d = new Date(`${iso}T12:00:00`);
    if (!Number.isFinite(d.getTime())) return iso;
    const dow = d.toLocaleDateString('es-ES', { weekday: 'short' });
    const day = d.toLocaleDateString('es-ES', { day: '2-digit' });
    const mon = d.toLocaleDateString('es-ES', { month: 'short' });
    const yr = d.toLocaleDateString('es-ES', { year: '2-digit' });
    return `${capitalize(dow)} ${day} ${capitalize(mon)} '${yr}`;
}

/** From `fiscal_quarter` like "Q1" + report_date year, produce "Mar '26". */
function formatFiscalPeriod(r: EarningsRecord): string | null {
    if (!r.fiscal_quarter) return null;
    const d = new Date(`${r.report_date}T12:00:00`);
    if (!Number.isFinite(d.getTime())) return r.fiscal_quarter;
    // Period end approximation: one month before report_date (Q1 -> month-1 of report).
    const periodEnd = new Date(d.getFullYear(), d.getMonth() - 1, 1);
    const mon = periodEnd.toLocaleDateString('es-ES', { month: 'short' });
    const yr = periodEnd.toLocaleDateString('es-ES', { year: '2-digit' });
    return `${capitalize(mon)} '${yr}`;
}

function formatTimeSlot(slot: string): string {
    if (slot === 'BMO') return 'Antes de mercado';
    if (slot === 'AMC') return 'Después de mercado';
    return slot;
}

function capitalize(s: string): string {
    if (!s) return s;
    return s.charAt(0).toUpperCase() + s.slice(1).replace(/\.$/, '');
}

// Re-export so consumers can avoid importing the icon module separately.
export { EarningsBadgeIcon };
