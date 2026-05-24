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

interface ChartLayoutContainerProps {
    windowId: string;
    bus: ChartSyncBus;
}

export function ChartLayoutContainer({ windowId, bus }: ChartLayoutContainerProps) {
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

    const showCellBadge = tpl.cellCount > 1;

    return (
        <div
            className="flex-1 min-h-0 overflow-hidden p-0.5 gap-0.5 grid w-full h-full"
            style={{
                gridTemplateColumns: tpl.grid.columns,
                gridTemplateRows: tpl.grid.rows,
                gridTemplateAreas: tpl.grid.areas,
            }}
        >
            {cellList.map(({ idx, state }) => (
                <div
                    key={state.id}
                    style={{ gridArea: cellArea(idx) }}
                    className={`min-w-0 min-h-0 overflow-hidden ${
                        tpl.cellCount > 1
                            ? `rounded-sm ring-1 ${
                                activeCellId === state.id
                                    ? 'ring-[color:var(--color-primary)]/50'
                                    : 'ring-[color:var(--color-border-subtle)]'
                            }`
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
                    />
                </div>
            ))}
        </div>
    );
}
