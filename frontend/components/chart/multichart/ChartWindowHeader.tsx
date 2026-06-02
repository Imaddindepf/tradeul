/**
 * ChartWindowHeader — portaled into the chart FloatingWindow's title-bar
 * slot (`window-header-extra-${windowId}`).
 *
 * Only renders a TickerSearch bound to the *active cell*. The Layout / Sync /
 * Saved-layouts controls now live in the elevated `<ChartHeader>` row so this
 * portal stays minimal and matches TV's "title bar shows the symbol" pattern.
 *
 * In single mode the active cell is just "the chart"; in multi mode it
 * follows the focused cell.
 */

'use client';

import { useCallback, useEffect, useState } from 'react';
import { TickerSearch } from '@/components/common/TickerSearch';
import { useChartLayoutStore } from './useChartLayoutStore';
import type { WindowLayoutState } from './useChartLayoutStore';

interface ChartWindowHeaderProps {
    windowId: string;
    win: WindowLayoutState;
}

export function ChartWindowHeader({ windowId, win }: ChartWindowHeaderProps) {
    const setCellTicker = useChartLayoutStore((s) => s.setCellTicker);
    const broadcastTicker = useChartLayoutStore((s) => s.broadcastTicker);

    const activeCell = win.cells[win.activeCellId];

    // Local input mirrors the active cell's ticker so when the user clicks
    // on a different cell the input updates accordingly. The user may type
    // freely; we only commit on submit / suggestion select.
    const [tickerInput, setTickerInput] = useState(activeCell?.ticker ?? '');
    useEffect(() => {
        if (activeCell) setTickerInput(activeCell.ticker);
    }, [activeCell?.id, activeCell?.ticker]);

    const applyTicker = useCallback(
        (next: string) => {
            const symbol = next.trim().toUpperCase();
            if (!symbol || !activeCell) return;
            if (win.sync.symbol) broadcastTicker(windowId, activeCell.id, symbol);
            else setCellTicker(windowId, activeCell.id, symbol);
        },
        [windowId, activeCell, win.sync.symbol, broadcastTicker, setCellTicker],
    );

    const handleTickerSubmit = useCallback(
        (e: React.FormEvent) => {
            e.preventDefault();
            applyTicker(tickerInput);
        },
        [applyTicker, tickerInput],
    );

    const handleTickerSelect = useCallback(
        (selected: { symbol: string }) => {
            setTickerInput(selected.symbol.toUpperCase());
            applyTicker(selected.symbol);
        },
        [applyTicker],
    );

    return (
        <form
            onSubmit={handleTickerSubmit}
            onMouseDown={(e) => e.stopPropagation()}
            className="flex items-center"
        >
            <TickerSearch
                value={tickerInput}
                onChange={setTickerInput}
                onSelect={handleTickerSelect}
                placeholder="Ticker"
                className="w-20"
                autoFocus={false}
            />
        </form>
    );
}
