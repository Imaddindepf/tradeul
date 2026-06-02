/**
 * HeaderLayoutControls — Layout (incl. sync) + SavedLayouts buttons mounted
 * inside the TradingView-style horizontal `<ChartHeader>` row.
 *
 * Self-contained: reads its own `windowId` from `useCurrentWindowId()` and
 * its layout state from `useChartLayoutStore`. Renders nothing when there is
 * no window context (i.e. when ChartContent is on its fast-path with a plain
 * `<TradingChart>` rendered inline somewhere unusual).
 *
 * TradingView merges the layout picker and the per-layout sync toggles into
 * a single popover; we do the same. The standalone Sync button is gone —
 * `LayoutPickerPopover` owns both the grid and the sync switches.
 */

'use client';

import { useMemo, useRef, useState } from 'react';
import { FolderOpen } from 'lucide-react';
import { useCurrentWindowId } from '@/contexts/FloatingWindowContext';
import {
    useChartLayoutStore,
    selectWindow,
    selectSavedLayouts,
} from './multichart/useChartLayoutStore';
import { LayoutIcon } from './multichart/LayoutIcon';
import { LayoutPickerPopover } from './multichart/LayoutPickerPopover';
import { SavedLayoutsPopover } from './multichart/SavedLayoutsPopover';
import { LAYOUT_TEMPLATES } from './multichart/layoutTemplates';
import type { SyncFlags } from './multichart/types';
import { HeaderDivider } from './HeaderDivider';

export function HeaderLayoutControls() {
    const windowId = useCurrentWindowId?.() ?? null;
    const win = useChartLayoutStore(selectWindow(windowId));
    const savedLayouts = useChartLayoutStore(selectSavedLayouts);
    const setLayoutId = useChartLayoutStore((s) => s.setLayoutId);
    const setSyncFlag = useChartLayoutStore((s) => s.setSyncFlag);
    const saveLayoutAs = useChartLayoutStore((s) => s.saveLayoutAs);
    const loadSavedLayout = useChartLayoutStore((s) => s.loadSavedLayout);
    const renameSavedLayout = useChartLayoutStore((s) => s.renameSavedLayout);
    const deleteSavedLayout = useChartLayoutStore((s) => s.deleteSavedLayout);

    const layoutBtnRef = useRef<HTMLButtonElement | null>(null);
    const savedBtnRef = useRef<HTMLButtonElement | null>(null);

    const [showLayout, setShowLayout] = useState(false);
    const [showSaved, setShowSaved] = useState(false);

    const tpl = useMemo(() => {
        if (!win) return LAYOUT_TEMPLATES.single;
        return LAYOUT_TEMPLATES[win.layoutId] ?? LAYOUT_TEMPLATES.single;
    }, [win]);

    if (!windowId || !win) return null;

    return (
        <>
            <div className="flex items-center gap-0.5">
                <button
                    ref={layoutBtnRef}
                    type="button"
                    title={`Layout · ${tpl.label}`}
                    aria-label="Choose chart layout and sync"
                    onClick={() => setShowLayout((v) => !v)}
                    className={`inline-flex items-center justify-center h-[22px] w-[26px] rounded-[3px] transition-colors ${
                        showLayout
                            ? 'text-[color:var(--color-primary)] bg-[color:var(--color-primary)]/10'
                            : 'text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)] hover:bg-[color:var(--color-surface-hover)]'
                    }`}
                >
                    <LayoutIcon layoutId={win.layoutId} active size={16} />
                </button>

                <button
                    ref={savedBtnRef}
                    type="button"
                    title="Saved layouts"
                    aria-label="Saved layouts"
                    onClick={() => setShowSaved((v) => !v)}
                    className={`inline-flex items-center gap-0.5 h-[22px] px-1.5 rounded-[3px] transition-colors ${
                        showSaved
                            ? 'text-[color:var(--color-primary)] bg-[color:var(--color-primary)]/10'
                            : 'text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)] hover:bg-[color:var(--color-surface-hover)]'
                    }`}
                >
                    <FolderOpen className="w-3.5 h-3.5" />
                    {savedLayouts.length > 0 && (
                        <span className="text-[10px] font-mono leading-none">
                            {savedLayouts.length}
                        </span>
                    )}
                </button>
            </div>
            <HeaderDivider />

            <LayoutPickerPopover
                anchorEl={layoutBtnRef.current}
                isOpen={showLayout}
                onClose={() => setShowLayout(false)}
                activeLayoutId={win.layoutId}
                onPick={(id) => setLayoutId(windowId, id)}
                sync={win.sync}
                onToggleSync={(flag: keyof SyncFlags) =>
                    setSyncFlag(windowId, flag, !win.sync[flag])
                }
                syncEnabled={tpl.cellCount >= 2}
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
        </>
    );
}
