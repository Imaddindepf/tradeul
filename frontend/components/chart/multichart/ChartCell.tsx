/**
 * ChartCell — one chart inside a multi-chart layout (or as a single chart
 * inside a chart window).
 *
 * Responsibilities:
 *   • Renders `<TradingChart>` in `inLayoutMode`, passing controlled ticker
 *     and interval read from the per-window layout store.
 *   • Wires the sync bus when the chart is ready:
 *       - emits crosshair / visible-range events
 *       - listens for events from sibling cells and applies them
 *   • Translates `onTickerChange` / `onIntervalChange` into either a local
 *     mutation (no sync) or a broadcast (sync flag on).
 *   • Renders an optional cell badge in the upper-left corner that doubles
 *     as the "activate cell" affordance (only meaningful when N > 1).
 */

'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import type {
    IChartApi,
    ISeriesApi,
    MouseEventParams,
    SeriesType,
    Time,
} from 'lightweight-charts';
import { Subscription } from 'rxjs';
import { filter } from 'rxjs/operators';
import { TradingChart } from '../TradingChart';
import type { ChartInterval } from '@/hooks/useLiveChartData';
import type { TradingChartHandle } from '../constants';
import type { ChartContextValue } from '../ChartContext';
import { useChartLayoutStore } from './useChartLayoutStore';
import type { ChartSyncBus } from './chartSyncBus';
import type { CellState, SyncFlags } from './types';

interface ChartCellProps {
    windowId: string;
    cellState: CellState;
    bus: ChartSyncBus;
    sync: SyncFlags;
    /** Whether this cell is the currently active one (border + badge). */
    isActive: boolean;
    /** Callback to focus this cell. */
    onActivate: () => void;
    /** When true (multi-chart mode), show the small cell badge overlay. */
    showCellBadge: boolean;
    /** Total cell count — used to label the badge nicely. */
    totalCells: number;
    /**
     * Publish the active cell's `ChartContextValue` to the host. The host
     * (ChartContent) re-injects that value into a `<ChartProvider>` so the
     * window-level header and toolbar drive the active cell exclusively.
     *
     * Cells call this *only* while `isActive` — that's the whole point of
     * the bridge: only one publisher at a time, no fan-out concerns.
     */
    onActiveContextValue?: (ctx: ChartContextValue | null) => void;
}

export function ChartCell({
    windowId,
    cellState,
    bus,
    sync,
    isActive,
    onActivate,
    showCellBadge,
    totalCells,
    onActiveContextValue,
}: ChartCellProps) {
    const setCellTicker = useChartLayoutStore((s) => s.setCellTicker);
    const setCellInterval = useChartLayoutStore((s) => s.setCellInterval);
    const broadcastTicker = useChartLayoutStore((s) => s.broadcastTicker);
    const broadcastInterval = useChartLayoutStore((s) => s.broadcastInterval);

    // Chart handle as state so the wiring effect re-runs when TradingChart
    // recreates the underlying lightweight-charts instance.
    const [chartHandle, setChartHandle] = useState<TradingChartHandle | null>(null);

    // ── Sync wiring ───────────────────────────────────────────────────────
    useEffect(() => {
        if (!chartHandle) return;
        const cellId = cellState.id;
        const chart = chartHandle.chart as IChartApi;
        const series = chartHandle.candleSeries as ISeriesApi<SeriesType>;

        // Anti-loop flag: set when we *apply* a remote update so the local
        // listener can ignore the resulting echo event.
        let isApplying = false;

        const crosshairListener = (params: MouseEventParams) => {
            if (isApplying) return;
            if (!params.point || params.time == null) {
                bus.emitCrosshair({ sourceCellId: cellId, time: null, price: null });
                return;
            }
            const price = series.coordinateToPrice(params.point.y);
            if (price == null) return;
            bus.emitCrosshair({
                sourceCellId: cellId,
                time: params.time as number,
                price: price as number,
            });
        };

        const rangeListener = (range: { from: Time; to: Time } | null) => {
            if (isApplying || !range) return;
            const from = range.from as number;
            const to = range.to as number;
            if (typeof from !== 'number' || typeof to !== 'number') return;
            bus.emitVisibleRange({ sourceCellId: cellId, from, to });
        };

        chart.subscribeCrosshairMove(crosshairListener);
        chart.timeScale().subscribeVisibleTimeRangeChange(rangeListener);

        const subs: Subscription[] = [];
        if (sync.crosshair) {
            subs.push(
                bus.crosshair$
                    .pipe(filter((e) => e.sourceCellId !== cellId))
                    .subscribe((e) => {
                        isApplying = true;
                        try {
                            if (e.time == null || e.price == null) {
                                chart.clearCrosshairPosition();
                            } else {
                                chart.setCrosshairPosition(
                                    e.price,
                                    e.time as Time,
                                    series,
                                );
                            }
                        } catch {
                            /* setCrosshairPosition fails silently when the
                               target time is outside the cell's visible data
                               — that's the right thing to do. */
                        } finally {
                            isApplying = false;
                        }
                    }),
            );
        }
        if (sync.time) {
            subs.push(
                bus.visibleRange$
                    .pipe(filter((e) => e.sourceCellId !== cellId))
                    .subscribe((e) => {
                        isApplying = true;
                        try {
                            chart.timeScale().setVisibleRange({
                                from: e.from as Time,
                                to: e.to as Time,
                            });
                        } catch {
                            /* ignore — same reasoning as above */
                        } finally {
                            isApplying = false;
                        }
                    }),
            );
        }

        return () => {
            try { chart.unsubscribeCrosshairMove(crosshairListener); } catch { /* */ }
            try {
                chart.timeScale().unsubscribeVisibleTimeRangeChange(rangeListener);
            } catch { /* */ }
            subs.forEach((s) => s.unsubscribe());
        };
    }, [chartHandle, bus, cellState.id, sync.crosshair, sync.time]);

    // ── Stable callbacks for TradingChart ─────────────────────────────────
    const handleChartReady = useCallback((handle: TradingChartHandle) => {
        setChartHandle(handle);
    }, []);

    const handleTickerChange = useCallback(
        (next: string) => {
            if (sync.symbol) broadcastTicker(windowId, cellState.id, next);
            else setCellTicker(windowId, cellState.id, next);
        },
        [sync.symbol, windowId, cellState.id, broadcastTicker, setCellTicker],
    );

    const handleIntervalChange = useCallback(
        (next: ChartInterval) => {
            if (sync.interval) broadcastInterval(windowId, cellState.id, next);
            else setCellInterval(windowId, cellState.id, next);
        },
        [sync.interval, windowId, cellState.id, broadcastInterval, setCellInterval],
    );

    // ── Overlay badge ─────────────────────────────────────────────────────
    const overlay = useMemo(() => {
        if (!showCellBadge) return undefined;
        const label = totalCells > 1 ? cellState.id.replace('cell-', '#') : null;
        if (!label) return undefined;
        return (
            <button
                type="button"
                onClick={onActivate}
                title={isActive ? 'Active cell' : 'Activate this cell'}
                className={`pointer-events-auto px-1.5 py-0.5 rounded text-[10px] font-mono select-none transition-colors ${
                    isActive
                        ? 'bg-[color:var(--color-primary)]/20 text-[color:var(--color-primary)] ring-1 ring-[color:var(--color-primary)]/40'
                        : 'bg-foreground/5 text-muted-fg hover:bg-foreground/10'
                }`}
                onMouseDown={(e) => e.stopPropagation()}
            >
                {label}
            </button>
        );
    }, [showCellBadge, totalCells, cellState.id, isActive, onActivate]);

    // Only the active cell publishes its ChartContextValue upward. Switching
    // active cells flips which TradingChart sees the bridge callback — when
    // the old active cell loses it, its own cleanup-effect pushes `null` so
    // we never end up with a stale context bound to a non-active cell.
    const publishContext = isActive ? onActiveContextValue : undefined;

    return (
        <div
            className="h-full w-full"
            onMouseDownCapture={onActivate}
        >
            <TradingChart
                ticker={cellState.ticker}
                inLayoutMode
                windowId={windowId}
                controlledInterval={cellState.interval}
                onTickerChange={handleTickerChange}
                onIntervalChange={handleIntervalChange}
                onChartReady={handleChartReady}
                cellOverlay={overlay}
                onContextValue={publishContext}
            />
        </div>
    );
}
