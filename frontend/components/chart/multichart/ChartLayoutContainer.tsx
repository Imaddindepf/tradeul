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
}

export function ChartLayoutContainer({
    windowId,
    bus,
    onActiveContextValue,
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
            {cellList.map(({ idx, state }) => (
                <div
                    key={state.id}
                    style={{ gridArea: cellArea(idx) }}
                    className={`min-w-0 min-h-0 overflow-hidden bg-[color:var(--color-surface)] ${
                        isMulti
                            ? activeCellId === state.id
                                ? 'ring-1 ring-inset ring-[color:var(--color-primary)]/60'
                                : ''
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
            ))}
        </div>
    );
}
