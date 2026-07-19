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

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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

    // True while the pointer is physically over this cell. LWC re-fires
    // crosshairMoved on every model update (live ticks, repaints) even for
    // ghost positions applied via setCrosshairPosition — and it clamps that
    // ghost to the cell's visible range. Without this gate, a cell whose data
    // doesn't cover the hovered date bounces a clamped ghost back through the
    // bus and yanks the real cursor to the newest candle.
    const pointerInsideRef = useRef(false);

    // ── Sync wiring ───────────────────────────────────────────────────────
    useEffect(() => {
        if (!chartHandle) return;
        const cellId = cellState.id;
        const chart = chartHandle.chart as IChartApi;
        const series = chartHandle.candleSeries as ISeriesApi<SeriesType>;
        const timeScale = chart.timeScale();

        // setVisibleRange is applied async (LWC invalidates via rAF). A sync
        // boolean guard is already false by the time the local range listener
        // fires — which re-emits a clamped range and fights sibling cells
        // (esp. daily ↔ intraday with different data domains). Count pending
        // remote applies and suppress that many subsequent local emissions.
        let pendingRangeApplies = 0;
        let rangeEchoFallback: number | null = null;

        const armRangeEchoSuppression = () => {
            pendingRangeApplies += 1;
            if (rangeEchoFallback != null) cancelAnimationFrame(rangeEchoFallback);
            // Two rAFs ≈ after LWC's drawImpl; clear stale tokens if no event
            // fired (e.g. setVisibleRange was a no-op / threw after arming).
            rangeEchoFallback = requestAnimationFrame(() => {
                rangeEchoFallback = requestAnimationFrame(() => {
                    rangeEchoFallback = null;
                    pendingRangeApplies = 0;
                });
            });
        };

        /** Last candle with time <= target (floor). LWC timeToIndex ceil-snaps. */
        const floorBarTime = (target: number): number | null => {
            const bars = series.data();
            if (!bars.length) return null;
            let lo = 0;
            let hi = bars.length - 1;
            let ans = -1;
            while (lo <= hi) {
                const mid = (lo + hi) >> 1;
                const t = bars[mid].time as number;
                if (t <= target) {
                    ans = mid;
                    lo = mid + 1;
                } else {
                    hi = mid - 1;
                }
            }
            return ans < 0 ? null : (bars[ans].time as number);
        };

        const crosshairListener = (params: MouseEventParams) => {
            // Only the cell under the pointer may broadcast. Ghost positions
            // re-fired by LWC model updates (live bars) must never re-enter
            // the bus — they are clamped to this cell's visible range and
            // would hijack the crosshair of the cell the user is hovering.
            if (!pointerInsideRef.current) return;
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
            if (!range) return;
            if (pendingRangeApplies > 0) {
                pendingRangeApplies -= 1;
                return;
            }
            // Same pointer gate as the crosshair: only user-driven pans on
            // THIS cell may broadcast. Auto-scroll from live bars / setData
            // on a background cell must not drag siblings back to "now".
            if (!pointerInsideRef.current) return;
            const from = range.from as number;
            const to = range.to as number;
            if (typeof from !== 'number' || typeof to !== 'number') return;
            bus.emitVisibleRange({ sourceCellId: cellId, from, to });
        };

        chart.subscribeCrosshairMove(crosshairListener);
        timeScale.subscribeVisibleTimeRangeChange(rangeListener);

        const subs: Subscription[] = [];
        if (sync.crosshair) {
            subs.push(
                bus.crosshair$
                    .pipe(filter((e) => e.sourceCellId !== cellId))
                    .subscribe((e) => {
                        try {
                            if (e.time == null || e.price == null) {
                                chart.clearCrosshairPosition();
                                return;
                            }
                            const snapped = floorBarTime(e.time);
                            if (snapped == null) {
                                chart.clearCrosshairPosition();
                                return;
                            }
                            chart.setCrosshairPosition(e.price, snapped as Time, series);
                        } catch {
                            /* time outside series / pane not ready */
                        }
                    }),
            );
        }
        if (sync.time) {
            subs.push(
                bus.visibleRange$
                    .pipe(filter((e) => e.sourceCellId !== cellId))
                    .subscribe((e) => {
                        try {
                            const bars = series.data();
                            if (!bars.length) return;
                            const first = bars[0].time as number;
                            const last = bars[bars.length - 1].time as number;
                            // No overlap with this cell's data → do not clamp to
                            // [first,last] (that would yank siblings back to "now").
                            if (e.to < first || e.from > last) return;
                            const from = Math.max(e.from, first);
                            const to = Math.min(e.to, last);
                            if (!(from < to)) return;

                            armRangeEchoSuppression();
                            timeScale.setVisibleRange({
                                from: from as Time,
                                to: to as Time,
                            });
                        } catch {
                            pendingRangeApplies = Math.max(0, pendingRangeApplies - 1);
                        }
                    }),
            );
        }

        return () => {
            if (rangeEchoFallback != null) cancelAnimationFrame(rangeEchoFallback);
            try { chart.unsubscribeCrosshairMove(crosshairListener); } catch { /* */ }
            try { timeScale.unsubscribeVisibleTimeRangeChange(rangeListener); } catch { /* */ }
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
            onPointerEnter={() => { pointerInsideRef.current = true; }}
            onPointerLeave={() => {
                pointerInsideRef.current = false;
                // The canvas' own leave event usually fires first, but make
                // sure siblings never keep a stale ghost from this cell.
                bus.emitCrosshair({ sourceCellId: cellState.id, time: null, price: null });
            }}
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
