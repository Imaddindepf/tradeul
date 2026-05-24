/**
 * Multi-chart sync bus — pub/sub plumbing for crosshair and visible-range
 * synchronisation between sibling chart cells.
 *
 * Each event carries a `sourceCellId` so subscribers can ignore their own
 * emissions and avoid infinite loops. The bus is intentionally lightweight
 * (plain Subjects) — RxJS gives us back-pressure-free fan-out plus easy
 * `takeUntil`/`filter` composition for consumers.
 *
 * One bus instance per multi-chart window. Use `createChartSyncBus()` and
 * pass the result through React context to all cells in that layout.
 */

import { Subject } from 'rxjs';
import type { ChartInterval } from '@/hooks/useLiveChartData';

// ============================================================================
// Event shapes
// ============================================================================

/**
 * Crosshair position emitted by the active cell. `time` is a UNIX seconds
 * timestamp; `price` is the y-axis value at the hover point.
 *
 * `time` and `price` can be `null` when the cursor leaves the canvas — that
 * lets subscribers clear their ghost crosshair on out events.
 */
export interface CrosshairEvent {
    sourceCellId: string;
    time: number | null;
    price: number | null;
}

/**
 * Visible logical range emitted on every pan/zoom action. Times are UNIX
 * seconds. Subscribers use `setVisibleRange` to mirror the window.
 */
export interface VisibleRangeEvent {
    sourceCellId: string;
    from: number;
    to: number;
}

/**
 * Symbol / interval changes are *also* propagated via the store, but the bus
 * lets a cell signal the change *before* the store re-renders, which keeps
 * sibling cells perfectly in sync without an extra frame of lag.
 */
export interface SymbolEvent {
    sourceCellId: string;
    ticker: string;
}

export interface IntervalEvent {
    sourceCellId: string;
    interval: ChartInterval;
}

// ============================================================================
// Bus
// ============================================================================

export interface ChartSyncBus {
    crosshair$: Subject<CrosshairEvent>;
    visibleRange$: Subject<VisibleRangeEvent>;
    symbol$: Subject<SymbolEvent>;
    interval$: Subject<IntervalEvent>;

    /** Emit helpers — preferred over `next` to keep types correct. */
    emitCrosshair: (event: CrosshairEvent) => void;
    emitVisibleRange: (event: VisibleRangeEvent) => void;
    emitSymbol: (event: SymbolEvent) => void;
    emitInterval: (event: IntervalEvent) => void;

    /** Tear-down (complete every subject). */
    dispose: () => void;
}

export function createChartSyncBus(): ChartSyncBus {
    const crosshair$ = new Subject<CrosshairEvent>();
    const visibleRange$ = new Subject<VisibleRangeEvent>();
    const symbol$ = new Subject<SymbolEvent>();
    const interval$ = new Subject<IntervalEvent>();

    return {
        crosshair$,
        visibleRange$,
        symbol$,
        interval$,
        emitCrosshair: (e) => crosshair$.next(e),
        emitVisibleRange: (e) => visibleRange$.next(e),
        emitSymbol: (e) => symbol$.next(e),
        emitInterval: (e) => interval$.next(e),
        dispose: () => {
            crosshair$.complete();
            visibleRange$.complete();
            symbol$.complete();
            interval$.complete();
        },
    };
}
