/**
 * useEarningsMarkers
 *
 * Loads full earnings records for the current ticker and exposes them in the
 * format required by `useEventMarkers`. The full record is attached to each
 * marker's `payload` so the click popup can render without a second fetch.
 *
 * The primitive itself is owned by `useEventMarkers`, which combines earnings
 * + news (and any future event streams) into a single chart primitive for
 * visual consistency.
 */
import { useEffect, useMemo, useState } from 'react';
import type { ChartEvent } from '../primitives/EventMarkerPrimitive';

/**
 * Full earnings record as returned by `/api/v1/earnings/ticker/{ticker}`.
 * Optional fields are typed as `number | null` because the backend may not
 * have data for projected/estimated rows yet.
 */
export interface EarningsRecord {
    symbol: string;
    company_name: string | null;
    report_date: string;
    time_slot: 'BMO' | 'AMC' | string;
    fiscal_quarter: string | null;
    eps_estimate: number | null;
    eps_actual: number | null;
    eps_surprise_pct: number | null;
    beat_eps: boolean | null;
    revenue_estimate: number | null;
    revenue_actual: number | null;
    revenue_surprise_pct: number | null;
    beat_revenue: boolean | null;
    guidance_direction: string | null;
    guidance_commentary: string | null;
    key_highlights: string | null;
    importance: number | null;
    date_status: string | null;
    eps_method: string | null;
    revenue_method: string | null;
    previous_eps: number | null;
    previous_revenue: number | null;
    status: string | null;
    source: string | null;
}

export function useEarningsMarkers(
    currentTicker: string,
    enabled: boolean,
) {
    const [records, setRecords] = useState<EarningsRecord[]>([]);

    useEffect(() => {
        if (!currentTicker) {
            setRecords([]);
            return;
        }
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const controller = new AbortController();
        fetch(
            `${apiUrl}/api/v1/earnings/ticker/${currentTicker.toUpperCase()}?limit=100`,
            { signal: controller.signal },
        )
            .then(res => res.ok ? res.json() : null)
            .then(d => {
                if (d?.earnings && Array.isArray(d.earnings)) setRecords(d.earnings);
                else setRecords([]);
            })
            .catch(err => {
                if (err.name !== 'AbortError') setRecords([]);
            });
        return () => controller.abort();
    }, [currentTicker]);

    const events = useMemo<ChartEvent[]>(() => {
        if (!enabled) return [];
        return records.map(r => ({
            date: r.report_date,
            kind: 'earnings' as const,
            label: r.time_slot,
            payload: r,
        }));
    }, [records, enabled]);

    return { earningsRecords: records, earningsEvents: events };
}
