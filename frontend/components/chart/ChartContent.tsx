/**
 * ChartContent — root rendered inside every "Chart" FloatingWindow.
 *
 * Owns the per-window layout state and renders, dynamically:
 *   • In `single` mode → one chart cell that behaves exactly like the
 *     pre-multichart `<TradingChart>` did (same UX, same chrome).
 *   • In every other layout → a CSS-grid of cells, each with its own chart.
 *
 * Also portals the small "layout / sync / saved / ticker" toolbar into the
 * FloatingWindow's `window-header-extra-${windowId}` slot, just like the
 * original chart did with its ticker search.
 *
 * Per-window layout state lives in `useChartLayoutStore`, keyed by windowId,
 * so multiple chart windows have *fully independent* layouts.
 */

'use client';

import { memo, useEffect, useMemo, useRef, useState } from 'react';
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

    // ── Fast-path: when there is no FloatingWindow context (chart rendered
    //    inline somewhere unusual) we just render a plain TradingChart and
    //    avoid wiring the multi-chart store at all.
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
// Kept separate from the entry point so the hook order is stable even when
// the no-windowId branch above takes the fast path.
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

    // Initialise this window's layout state if it doesn't exist yet. The
    // store action is idempotent; if persisted state already has this
    // windowId (page reload), this is a no-op and we render its data.
    useEffect(() => {
        if (!win) ensureWindow(windowId, initialTicker);
    }, [win, windowId, initialTicker, ensureWindow]);

    // ── Per-window sync bus ──────────────────────────────────────────────
    const busRef = useRef<ChartSyncBus | null>(null);
    if (busRef.current === null) busRef.current = createChartSyncBus();
    useEffect(() => () => busRef.current?.dispose(), []);

    // ── Notify the host whenever the active cell's ticker changes ────────
    // Preserves the legacy `onTickerChange` callback semantics so consumers
    // (data tables, FloatingWindow titles) keep working.
    const activeCell = win ? win.cells[win.activeCellId] : null;
    const lastNotifiedTickerRef = useRef<string | null>(null);
    useEffect(() => {
        if (!activeCell) return;
        if (lastNotifiedTickerRef.current === activeCell.ticker) return;
        lastNotifiedTickerRef.current = activeCell.ticker;
        onTickerChange?.(activeCell.ticker);
    }, [activeCell?.ticker, onTickerChange]);

    // ── Header portal target ──────────────────────────────────────────────
    const headerPortalTarget = useHeaderPortalTarget(windowId);

    const cellCount = win ? Object.keys(win.cells).length : 0;

    // ── Until ensureWindow has run we don't have state to render yet ─────
    if (!win) return null;

    return (
        <>
            {headerPortalTarget && createPortal(
                <ChartWindowHeader windowId={windowId} win={win} />,
                headerPortalTarget,
            )}

            <ChartLayoutContainer windowId={windowId} bus={busRef.current!} />

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
            // Try again on next frame for ~10 frames (covers any mount race).
            requestAnimationFrame(find);
        };
        find();
        return () => { cancelled = true; };
    }, [windowId]);
    return target;
}
