'use client';

/**
 * hoveredBarStore — external store for the crosshair-hovered bar.
 *
 * The crosshair fires on every mouse pixel. Routing the hovered bar through
 * React state (the old approach) re-rendered the whole TradingChart tree —
 * ~50-field context value, multichart bridge included — on every bar change.
 * With this store only the components that actually display the hovered bar
 * (OHLC overlay, indicator legend, footer volume) subscribe and re-render.
 */

import { useMemo, useSyncExternalStore } from 'react';
import type { ChartBar } from './constants';
import { useChartContext } from './ChartContext';

export interface HoveredBarStore {
    get(): ChartBar | null;
    set(bar: ChartBar | null): void;
    subscribe(listener: () => void): () => void;
}

export function createHoveredBarStore(): HoveredBarStore {
    let current: ChartBar | null = null;
    const listeners = new Set<() => void>();
    return {
        get: () => current,
        set(bar) {
            if (bar === current) return;
            current = bar;
            for (const l of listeners) l();
        },
        subscribe(listener) {
            listeners.add(listener);
            return () => { listeners.delete(listener); };
        },
    };
}

/** Binary search over bars sorted by time. Returns index or -1. */
export function findBarIndexByTime(bars: ChartBar[], time: number): number {
    let lo = 0;
    let hi = bars.length - 1;
    while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        const t = bars[mid].time;
        if (t === time) return mid;
        if (t < time) lo = mid + 1;
        else hi = mid - 1;
    }
    return -1;
}

/**
 * Subscribes to the hovered bar and derives:
 *  - displayBar: hovered bar (when hovering) or last bar
 *  - prevBar: bar before displayBar, for change calculations
 *
 * Only the calling component re-renders on hover changes.
 */
export function useDisplayBar(): { hoveredBar: ChartBar | null; displayBar: ChartBar | null; prevBar: ChartBar | null } {
    const { hoveredBarStore, data } = useChartContext();
    const hoveredBar = useSyncExternalStore(
        hoveredBarStore.subscribe,
        hoveredBarStore.get,
        () => null,
    );
    return useMemo(() => {
        const displayBar = hoveredBar || (data.length > 0 ? data[data.length - 1] : null);
        let prevBar: ChartBar | null = null;
        if (displayBar && data.length >= 2) {
            const idx = findBarIndexByTime(data, displayBar.time);
            prevBar = idx > 0 ? data[idx - 1] : (data[data.length - 2] ?? null);
        }
        return { hoveredBar, displayBar, prevBar };
    }, [hoveredBar, data]);
}
