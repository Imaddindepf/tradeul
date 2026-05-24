/**
 * ChartWindowHeader — toolbar portaled into the chart FloatingWindow's
 * extra-header slot (`window-header-extra-${windowId}`).
 *
 * Contents (always rendered, regardless of single vs multi):
 *   1. LayoutPicker — TV-style icon showing the current layout. Clicking it
 *      opens the layout grid catalogue.
 *   2. SyncPicker — chain icon with the count of active sync flags. Only
 *      meaningful when the layout has > 1 cell, but always reachable.
 *   3. SavedLayouts — folder icon, opens the named-templates library.
 *   4. TickerSearch — bound to the *active cell*. In single mode the active
 *      cell is just "the chart"; in multi mode it follows the focused cell.
 *
 * This preserves the existing "quick ticker search from window header" UX
 * while giving multi-chart users one logical place to switch layouts and
 * sync flags.
 */

'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link2, FolderOpen } from 'lucide-react';
import { TickerSearch } from '@/components/common/TickerSearch';
import { useChartLayoutStore, selectSavedLayouts } from './useChartLayoutStore';
import { LayoutIcon } from './LayoutIcon';
import { LayoutPickerPopover } from './LayoutPickerPopover';
import { SyncPickerPopover } from './SyncPickerPopover';
import { SavedLayoutsPopover } from './SavedLayoutsPopover';
import type { WindowLayoutState } from './useChartLayoutStore';
import type { SyncFlags } from './types';
import { LAYOUT_TEMPLATES } from './layoutTemplates';

interface ChartWindowHeaderProps {
    windowId: string;
    win: WindowLayoutState;
}

export function ChartWindowHeader({ windowId, win }: ChartWindowHeaderProps) {
    const setLayoutId = useChartLayoutStore((s) => s.setLayoutId);
    const setSyncFlag = useChartLayoutStore((s) => s.setSyncFlag);
    const setCellTicker = useChartLayoutStore((s) => s.setCellTicker);
    const broadcastTicker = useChartLayoutStore((s) => s.broadcastTicker);
    const saveLayoutAs = useChartLayoutStore((s) => s.saveLayoutAs);
    const loadSavedLayout = useChartLayoutStore((s) => s.loadSavedLayout);
    const renameSavedLayout = useChartLayoutStore((s) => s.renameSavedLayout);
    const deleteSavedLayout = useChartLayoutStore((s) => s.deleteSavedLayout);
    const savedLayouts = useChartLayoutStore(selectSavedLayouts);

    const layoutBtnRef = useRef<HTMLButtonElement | null>(null);
    const syncBtnRef = useRef<HTMLButtonElement | null>(null);
    const savedBtnRef = useRef<HTMLButtonElement | null>(null);
    const [showLayout, setShowLayout] = useState(false);
    const [showSync, setShowSync] = useState(false);
    const [showSaved, setShowSaved] = useState(false);

    const tpl = LAYOUT_TEMPLATES[win.layoutId] ?? LAYOUT_TEMPLATES.single;
    const activeCell = win.cells[win.activeCellId];
    const activeSyncCount = useMemo(
        () => (Object.values(win.sync) as boolean[]).filter(Boolean).length,
        [win.sync],
    );

    // ── TickerSearch ──────────────────────────────────────────────────────
    // Local input mirrors the active cell's ticker so when the user clicks
    // on a different cell the input updates accordingly. The user may type
    // freely; we only commit on submit/select.
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
        <div
            className="flex items-center gap-1 text-[11px]"
            onMouseDown={(e) => e.stopPropagation()}
        >
            <button
                ref={layoutBtnRef}
                type="button"
                title={`Layout: ${tpl.label}`}
                aria-label="Choose layout"
                onClick={() => setShowLayout((v) => !v)}
                className={`inline-flex items-center justify-center h-5 w-5 rounded transition-colors ${
                    showLayout
                        ? 'text-[color:var(--color-primary)] bg-[color:var(--color-primary)]/10'
                        : 'text-muted-fg hover:text-foreground hover:bg-foreground/5'
                }`}
            >
                <LayoutIcon layoutId={win.layoutId} active size={16} />
            </button>

            <button
                ref={syncBtnRef}
                type="button"
                title="Sync between charts"
                aria-label="Sync between charts"
                onClick={() => setShowSync((v) => !v)}
                disabled={tpl.cellCount < 2}
                className={`inline-flex items-center gap-0.5 h-5 px-1 rounded transition-colors ${
                    tpl.cellCount < 2
                        ? 'text-muted-fg/40 cursor-not-allowed'
                        : showSync || activeSyncCount > 0
                            ? 'text-[color:var(--color-primary)] bg-[color:var(--color-primary)]/10'
                            : 'text-muted-fg hover:text-foreground hover:bg-foreground/5'
                }`}
            >
                <Link2 className="w-3 h-3" />
                {activeSyncCount > 0 && tpl.cellCount > 1 && (
                    <span className="text-[9px] font-mono leading-none">
                        {activeSyncCount}
                    </span>
                )}
            </button>

            <button
                ref={savedBtnRef}
                type="button"
                title="Saved layouts"
                aria-label="Saved layouts"
                onClick={() => setShowSaved((v) => !v)}
                className={`inline-flex items-center gap-0.5 h-5 px-1 rounded transition-colors ${
                    showSaved
                        ? 'text-[color:var(--color-primary)] bg-[color:var(--color-primary)]/10'
                        : 'text-muted-fg hover:text-foreground hover:bg-foreground/5'
                }`}
            >
                <FolderOpen className="w-3 h-3" />
                {savedLayouts.length > 0 && (
                    <span className="text-[9px] font-mono leading-none">
                        {savedLayouts.length}
                    </span>
                )}
            </button>

            <span className="mx-1 h-3 w-px bg-[color:var(--color-border-subtle)]" />

            <form
                onSubmit={handleTickerSubmit}
                className="flex items-center"
            >
                <TickerSearch
                    value={tickerInput}
                    onChange={setTickerInput}
                    onSelect={handleTickerSelect}
                    placeholder="Ticker"
                    className="w-16"
                    autoFocus={false}
                />
            </form>

            <LayoutPickerPopover
                anchorEl={layoutBtnRef.current}
                isOpen={showLayout}
                onClose={() => setShowLayout(false)}
                activeLayoutId={win.layoutId}
                onPick={(id) => setLayoutId(windowId, id)}
            />
            <SyncPickerPopover
                anchorEl={syncBtnRef.current}
                isOpen={showSync}
                onClose={() => setShowSync(false)}
                sync={win.sync}
                onToggle={(flag: keyof SyncFlags) =>
                    setSyncFlag(windowId, flag, !win.sync[flag])
                }
            />
            <SavedLayoutsPopover
                anchorEl={savedBtnRef.current}
                isOpen={showSaved}
                onClose={() => setShowSaved(false)}
                savedLayouts={savedLayouts}
                onSaveAs={(name) => saveLayoutAs(windowId, name)}
                onLoad={(id) => loadSavedLayout(windowId, id)}
                onRename={renameSavedLayout}
                onDelete={deleteSavedLayout}
            />
        </div>
    );
}
