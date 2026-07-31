/**
 * ChartLayoutContainer — renders the CSS grid of cells for a given chart
 * window. The window root (`ChartContent`) owns this component along with
 * the header portal (LayoutPicker / SyncPicker / SavedLayouts buttons).
 *
 * Reads its state from `useChartLayoutStore` keyed by `windowId` so multiple
 * chart windows can coexist with independent layouts.
 */

'use client';

import { useMemo } from 'react';
import { useChartLayoutStore, selectWindow } from './useChartLayoutStore';
import { ChartCell } from './ChartCell';
import {
    LAYOUT_TEMPLATES,
    cellArea,
    cellId as makeCellId,
} from './layoutTemplates';
import type { ChartSyncBus } from './chartSyncBus';
import type { ChartContextValue } from '../ChartContext';

interface ChartLayoutContainerProps {
    windowId: string;
    bus: ChartSyncBus;
    /**
     * Forwarded to the *active* cell so it can publish its `ChartContextValue`
     * upward — see `ChartCell` for the rationale.
     */
    onActiveContextValue?: (ctx: ChartContextValue | null) => void;
    /**
     * Id of the cell currently maximized, or null for the normal grid. Owned
     * by the window root (`ChartContent`) — see the note on the wrapper below
     * for why the other cells stay mounted.
     */
    maximizedCellId?: string | null;
}

export function ChartLayoutContainer({
    windowId,
    bus,
    onActiveContextValue,
    maximizedCellId = null,
}: ChartLayoutContainerProps) {
    const win = useChartLayoutStore(selectWindow(windowId));
    const setActiveCellId = useChartLayoutStore((s) => s.setActiveCellId);

    const tpl = useMemo(() => {
        if (!win) return LAYOUT_TEMPLATES.single;
        return LAYOUT_TEMPLATES[win.layoutId] ?? LAYOUT_TEMPLATES.single;
    }, [win]);

    const cellList = useMemo(() => {
        if (!win) return [];
        const list: { idx: number; state: import('./types').CellState }[] = [];
        for (let i = 1; i <= tpl.cellCount; i++) {
            const id = makeCellId(i);
            const state = win.cells[id];
            if (state) list.push({ idx: i, state });
        }
        return list;
    }, [win, tpl]);

    if (!win) return null;
    const { activeCellId, sync } = win;

    const isMulti = tpl.cellCount > 1;
    const showCellBadge = isMulti;

    /*
      TradingView uses a 1-pixel gap (rendered as the surrounding bg) between
      cells in multi-chart, and zero gap in single mode. We match by using a
      gap of 1px when multi, none when single, and lean on each cell's ring
      to draw the thin border that gives the grid its TV look.
    */
    return (
        <div
            className="flex-1 min-h-0 overflow-hidden grid w-full h-full bg-[color:var(--color-border)]"
            style={{
                gridTemplateColumns: tpl.grid.columns,
                gridTemplateRows: tpl.grid.rows,
                gridTemplateAreas: tpl.grid.areas,
                gap: isMulti ? '1px' : undefined,
            }}
        >
            {cellList.map(({ idx, state }) => {
                /*
                  Maximizing does NOT unmount the other cells.

                  TradingView detaches the hidden charts from the DOM but keeps
                  their widgets alive, so they carry on receiving ticks and
                  building bars while invisible (measured: a hidden 2m chart
                  closed one bar and opened the next). Unmounting a <ChartCell>
                  here would tear down its data subscription and its sync-bus
                  wiring, so restoring would show a gap and refetch.

                  So the maximized cell simply spans the whole grid on top and
                  the rest go `visibility: hidden`. They keep their grid area —
                  and therefore their exact size — which also means no resize
                  storm through lightweight-charts on the way back.
                */
                const isMaximized = maximizedCellId === state.id;
                const isHidden = maximizedCellId !== null && !isMaximized;
                const showRing =
                    isMulti && maximizedCellId === null && activeCellId === state.id;

                return (
                <div
                    key={state.id}
                    style={{
                        gridArea: isMaximized ? '1 / 1 / -1 / -1' : cellArea(idx),
                        zIndex: isMaximized ? 1 : undefined,
                        visibility: isHidden ? 'hidden' : undefined,
                        pointerEvents: isHidden ? 'none' : undefined,
                    }}
                    aria-hidden={isHidden || undefined}
                    className={`min-w-0 min-h-0 overflow-hidden bg-[color:var(--color-surface)] ${
                        showRing
                            ? 'ring-1 ring-inset ring-[color:var(--color-primary)]/60'
                            : ''
                    }`}
                >
                    <ChartCell
                        windowId={windowId}
                        cellState={state}
                        bus={bus}
                        sync={sync}
                        isActive={activeCellId === state.id}
                        onActivate={() => setActiveCellId(windowId, state.id)}
                        showCellBadge={showCellBadge}
                        totalCells={tpl.cellCount}
                        onActiveContextValue={onActiveContextValue}
                    />
                </div>
                );
            })}
        </div>
    );
}
