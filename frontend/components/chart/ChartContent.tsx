/**
 * ChartContent — root rendered inside every "Chart" FloatingWindow.
 *
 * Owns the per-window layout state and renders a TradingView-style L-shape:
 *
 *   ┌────────────────────────────────────────────────────────────────┐
 *   │  ChartHeader  (timeframes · indicators · layout · sync · …)    │
 *   ├──────┬─────────────────────────────────────────────────────────┤
 *   │  T   │                                                         │
 *   │  o   │                                                         │
 *   │  o   │           ChartLayoutContainer (1..16 cells)            │
 *   │  l   │                                                         │
 *   │  b   │                                                         │
 *   │  a   │                                                         │
 *   │  r   │                                                         │
 *   └──────┴─────────────────────────────────────────────────────────┘
 *
 * The header and the vertical toolbar are rendered *once per window*. They
 * read the chart context of the *active cell* via a small bridge:
 *   • the active `<ChartCell>` publishes its `ChartContextValue` via the
 *     `onContextValue` prop on `<TradingChart>` (see ChartCell.tsx);
 *   • this component receives that value, stores it in local state, and
 *     re-injects it through `<ChartProvider>` so the elevated header /
 *     toolbar consume it exactly as if they lived inside the chart.
 *
 * The TickerSearch portal in the FloatingWindow's title bar is owned by
 * `<ChartWindowHeader>` so the window title always reflects the active
 * cell's symbol, regardless of how many cells the layout has.
 */

'use client';

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useCurrentWindowId } from '@/contexts/FloatingWindowContext';
import { TradingChart } from './TradingChart';
import {
    useChartLayoutStore,
    selectWindow,
} from './multichart/useChartLayoutStore';
import { createChartSyncBus, type ChartSyncBus } from './multichart/chartSyncBus';
import { ChartLayoutContainer } from './multichart/ChartLayoutContainer';
import { ChartWindowHeader } from './multichart/ChartWindowHeader';
import { ChartProvider, type ChartContextValue } from './ChartContext';
import { ChartHeader } from './ChartHeader';
import { ChartToolbar } from './ChartToolbar';

interface ChartContentProps {
    ticker?: string;
    exchange?: string;
    onTickerChange?: (ticker: string) => void;
}

function ChartContentComponent({
    ticker = 'AAPL',
    exchange,
    onTickerChange,
}: ChartContentProps) {
    const windowId = useCurrentWindowId?.() ?? null;

    // Fast-path: chart rendered outside a FloatingWindow. We just render a
    // plain TradingChart with its own self-contained chrome.
    if (!windowId) {
        return (
            <TradingChart
                ticker={ticker}
                exchange={exchange}
                onTickerChange={onTickerChange}
            />
        );
    }

    return (
        <ChartWindowRoot
            windowId={windowId}
            initialTicker={ticker}
            exchange={exchange}
            onTickerChange={onTickerChange}
        />
    );
}

export const ChartContent = memo(ChartContentComponent);
export default ChartContent;

// ============================================================================
// ChartWindowRoot — does the actual coordination once a windowId is known.
// ============================================================================

interface ChartWindowRootProps {
    windowId: string;
    initialTicker: string;
    exchange?: string;
    onTickerChange?: (ticker: string) => void;
}

function ChartWindowRoot({
    windowId,
    initialTicker,
    exchange,
    onTickerChange,
}: ChartWindowRootProps) {
    const ensureWindow = useChartLayoutStore((s) => s.ensureWindow);
    const win = useChartLayoutStore(selectWindow(windowId));

    /*
      Initialise this window's layout state if it doesn't exist yet. The
      store action is idempotent: if persisted state already has this
      windowId (page reload), this is a no-op.
    */
    useEffect(() => {
        if (!win) ensureWindow(windowId, initialTicker);
    }, [win, windowId, initialTicker, ensureWindow]);

    // Per-window sync bus, instantiated lazily and disposed on unmount.
    const busRef = useRef<ChartSyncBus | null>(null);
    if (busRef.current === null) busRef.current = createChartSyncBus();
    useEffect(() => () => busRef.current?.dispose(), []);

    /*
      Notify the host whenever the active cell's ticker changes. This keeps
      the legacy `onTickerChange` contract working (data tables, window title
      updates, etc.) regardless of how many cells the layout has.
    */
    const activeCell = win ? win.cells[win.activeCellId] : null;
    const lastNotifiedTickerRef = useRef<string | null>(null);
    useEffect(() => {
        if (!activeCell) return;
        if (lastNotifiedTickerRef.current === activeCell.ticker) return;
        lastNotifiedTickerRef.current = activeCell.ticker;
        onTickerChange?.(activeCell.ticker);
    }, [activeCell?.ticker, onTickerChange]);

    /*
      Bridge state: the active cell publishes its ChartContextValue here.
      The elevated <ChartHeader> and <ChartToolbar> consume it through
      <ChartProvider>. Switching active cells flips which cell holds the
      bridge callback — cleanup pushes null, then the new owner pushes its
      own ctx within the same paint (see TradingChart's effect).
    */
    const [activeCtx, setActiveCtx] = useState<ChartContextValue | null>(null);
    const handleActiveCtx = useCallback((ctx: ChartContextValue | null) => {
        setActiveCtx(ctx);
    }, []);

    // Header portal target (FloatingWindow's title-bar slot).
    const headerPortalTarget = useHeaderPortalTarget(windowId);

    const cellCount = win ? Object.keys(win.cells).length : 0;

    if (!win) return null;

    return (
        <>
            {headerPortalTarget && createPortal(
                <ChartWindowHeader windowId={windowId} win={win} />,
                headerPortalTarget,
            )}

            {/*
              `activeCtx` is null for one frame on first mount and during the
              brief gap when the active cell changes (old cleanup → new push).
              We render the elevated chrome inside the bridge so consumers
              that call `useChartContext()` always see a real value; when
              `activeCtx` is null the inner chrome falls back to a skeleton
              row that matches the final height to avoid layout shift.
            */}
            <div className="h-full w-full flex flex-col bg-[color:var(--color-surface)] overflow-hidden">
                {activeCtx ? (
                    <ChartProvider value={activeCtx}>
                        <ElevatedHeaderRow windowId={windowId} />
                        <div className="flex flex-1 min-h-0 overflow-hidden">
                            <ElevatedToolbar
                                ctx={activeCtx}
                                windowId={windowId}
                            />
                            <div className="flex-1 min-w-0 min-h-0 overflow-hidden">
                                <ChartLayoutContainer
                                    windowId={windowId}
                                    bus={busRef.current!}
                                    onActiveContextValue={handleActiveCtx}
                                />
                            </div>
                        </div>
                    </ChartProvider>
                ) : (
                    <>
                        <HeaderSkeleton />
                        <div className="flex flex-1 min-h-0 overflow-hidden">
                            <ToolbarSkeleton />
                            <div className="flex-1 min-w-0 min-h-0 overflow-hidden">
                                <ChartLayoutContainer
                                    windowId={windowId}
                                    bus={busRef.current!}
                                    onActiveContextValue={handleActiveCtx}
                                />
                            </div>
                        </div>
                    </>
                )}
            </div>

            {/* Hint for screen-readers / SEO when the layout has multiple cells */}
            {cellCount > 1 && exchange && (
                <span className="sr-only">
                    Multi-chart layout, primary exchange {exchange}
                </span>
            )}
        </>
    );
}

// ============================================================================
// Elevated header — single instance per window, drives the active cell.
// We keep this trivial so it stays close to a memo'd <ChartHeader>; the
// extra wrapper exists for future window-level affordances (e.g. tab strip).
// ============================================================================

function ElevatedHeaderRow({ windowId }: { windowId: string }) {
    void windowId;
    return <ChartHeader />;
}

// ============================================================================
// Elevated toolbar — pulls drawing/active-tool wiring straight from ctx.
// We don't show drawing tools when the active cell hasn't published a ctx
// yet; the skeleton handles that case.
// ============================================================================

function ElevatedToolbar({
    ctx,
    windowId,
}: {
    ctx: ChartContextValue;
    windowId: string;
}) {
    void windowId;
    return (
        <ChartToolbar
            activeTool={ctx.activeTool as never}
            setActiveTool={ctx.setActiveTool}
            drawingCount={ctx.drawingCount}
            clearAllDrawings={ctx.clearAllDrawings}
            zoomIn={ctx.zoomIn}
            zoomOut={ctx.zoomOut}
            magnetMode={ctx.magnetMode}
            onCycleMagnet={ctx.cycleMagnet}
        />
    );
}

// ── Skeletons ───────────────────────────────────────────────────────────────

function HeaderSkeleton() {
    return (
        <div className="h-[27px] border-b border-[color:var(--color-border)] bg-[color:var(--color-surface)]" />
    );
}

function ToolbarSkeleton() {
    return (
        <div className="w-[38px] flex-shrink-0 bg-surface-hover border-r border-border" />
    );
}

// ============================================================================
// Hook: subscribe to the FloatingWindow's extra-header portal node.
// The node is rendered by FloatingWindowContext as a DOM child of the title
// bar; we poll briefly because it may be created after the chart mounts.
// ============================================================================

function useHeaderPortalTarget(windowId: string) {
    const [target, setTarget] = useState<HTMLElement | null>(null);
    useEffect(() => {
        let cancelled = false;
        const find = () => {
            if (cancelled) return;
            const el = document.getElementById(`window-header-extra-${windowId}`);
            if (el) {
                setTarget(el);
                return;
            }
            requestAnimationFrame(find);
        };
        find();
        return () => { cancelled = true; };
    }, [windowId]);
    return target;
}
