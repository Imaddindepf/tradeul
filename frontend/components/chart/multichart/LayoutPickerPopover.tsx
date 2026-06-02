/**
 * Layout picker — TradingView-style popover with grouped grid templates
 * AND the per-layout sync toggles in the same surface.
 *
 * Anchored to the “Select layout” toolbar button. Each row is a category
 * (1/2/3/4/5+/8 charts) showing every variant as an icon button. Below the
 * grid catalogue lives the "Sync within layout" section (Symbol, Interval,
 * Crosshair, Time, Date range) — TV groups both controls in the same flyout
 * since both decisions only matter together.
 */

'use client';

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Z_INDEX } from '@/lib/z-index';
import { LayoutIcon } from './LayoutIcon';
import {
    LAYOUT_TEMPLATES,
    LAYOUT_ORDER,
    LAYOUT_CATEGORIES,
} from './layoutTemplates';
import type { LayoutId, SyncFlags } from './types';

interface LayoutPickerPopoverProps {
    anchorEl: HTMLElement | null;
    isOpen: boolean;
    onClose: () => void;
    activeLayoutId: LayoutId;
    onPick: (id: LayoutId) => void;
    /** Current per-window sync flag state. */
    sync: SyncFlags;
    /** Toggles a single sync flag for the active window. */
    onToggleSync: (flag: keyof SyncFlags) => void;
    /**
     * Whether the sync toggles should be enabled. Currently the layout has
     * to have at least two cells for sync to make sense — TV grays the rows
     * out (but still shows them) in that case, which is what we do here.
     */
    syncEnabled: boolean;
}

const SYNC_ROWS: Array<{ key: keyof SyncFlags; label: string; hint: string }> = [
    { key: 'symbol', label: 'Symbol', hint: 'Change ticker in every chart at once' },
    { key: 'interval', label: 'Interval', hint: 'Same timeframe across every chart' },
    { key: 'crosshair', label: 'Crosshair', hint: 'Mirror crosshair position' },
    { key: 'time', label: 'Time (zoom/pan)', hint: 'Synchronise visible time window' },
    { key: 'dateRange', label: 'Date range', hint: 'Synchronise default range (1Y, 6M…)' },
];

export function LayoutPickerPopover({
    anchorEl,
    isOpen,
    onClose,
    activeLayoutId,
    onPick,
    sync,
    onToggleSync,
    syncEnabled,
}: LayoutPickerPopoverProps) {
    const popoverRef = useRef<HTMLDivElement>(null);
    const [pos, setPos] = useState({ top: 0, left: 0 });
    const [mounted, setMounted] = useState(false);

    useEffect(() => setMounted(true), []);

    useEffect(() => {
        if (!isOpen || !anchorEl) return;
        const update = () => {
            const r = anchorEl.getBoundingClientRect();
            setPos({ top: r.bottom + 6, left: r.left });
        };
        update();
        window.addEventListener('resize', update);
        window.addEventListener('scroll', update, true);
        return () => {
            window.removeEventListener('resize', update);
            window.removeEventListener('scroll', update, true);
        };
    }, [isOpen, anchorEl]);

    useEffect(() => {
        if (!isOpen) return;
        const onMouseDown = (e: MouseEvent) => {
            if (popoverRef.current?.contains(e.target as Node)) return;
            if (anchorEl?.contains(e.target as Node)) return;
            onClose();
        };
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('mousedown', onMouseDown);
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('mousedown', onMouseDown);
            document.removeEventListener('keydown', onKey);
        };
    }, [isOpen, anchorEl, onClose]);

    if (!isOpen || !mounted) return null;

    return createPortal(
        <div
            ref={popoverRef}
            role="dialog"
            aria-label="Choose layout and sync"
            style={{
                position: 'fixed',
                top: pos.top,
                left: pos.left,
                zIndex: Z_INDEX.DASHBOARD_OVERLAY,
                fontFamily: 'var(--font-mono-selected)',
            }}
            className="rounded-lg border border-border bg-surface shadow-2xl select-none w-[280px] flex flex-col max-h-[min(640px,80vh)]"
            onMouseDown={(e) => e.stopPropagation()}
        >
            <div className="flex-1 min-h-0 overflow-y-auto p-2">
                <div className="text-[10px] uppercase tracking-wider text-muted-fg px-2 py-1">
                    Select layout
                </div>
                <div className="flex flex-col gap-2">
                    {LAYOUT_CATEGORIES.map((cat) => {
                        const layouts = LAYOUT_ORDER.filter(
                            (id) => LAYOUT_TEMPLATES[id].category === cat.id,
                        );
                        if (layouts.length === 0) return null;
                        return (
                            <div key={cat.id} className="flex items-start gap-2 px-1">
                                <div className="text-[10px] text-muted-fg/70 w-4 pt-1.5 text-right shrink-0">
                                    {cat.label}
                                </div>
                                <div className="grid grid-cols-6 gap-1.5 flex-1">
                                    {layouts.map((id) => {
                                        const active = id === activeLayoutId;
                                        return (
                                            <button
                                                key={id}
                                                type="button"
                                                title={LAYOUT_TEMPLATES[id].label}
                                                onClick={() => {
                                                    onPick(id);
                                                    onClose();
                                                }}
                                                className={`flex items-center justify-center w-8 h-8 rounded transition-colors ${
                                                    active
                                                        ? 'bg-primary/15 text-primary ring-1 ring-primary/40'
                                                        : 'text-muted-fg hover:text-foreground hover:bg-foreground/5'
                                                }`}
                                            >
                                                <LayoutIcon layoutId={id} active={active} />
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>
                        );
                    })}
                </div>

                {/* ── Sync section — TradingView-style ──────────────────── */}
                <div className="border-t border-border mt-3 pt-2">
                    <div className="text-[10px] uppercase tracking-wider text-muted-fg px-2 pb-1">
                        Sync within layout
                    </div>
                    <ul className="flex flex-col">
                        {SYNC_ROWS.map(({ key, label, hint }) => {
                            const checked = sync[key];
                            return (
                                <li key={key}>
                                    <button
                                        type="button"
                                        onClick={() => onToggleSync(key)}
                                        disabled={!syncEnabled}
                                        title={hint}
                                        className={`w-full flex items-center justify-between gap-2 px-2 py-1.5 rounded text-left transition-colors ${
                                            syncEnabled
                                                ? 'hover:bg-foreground/5'
                                                : 'opacity-50 cursor-not-allowed'
                                        }`}
                                    >
                                        <span className="flex items-center gap-1.5">
                                            <span className="text-xs text-foreground">{label}</span>
                                            <InfoDot hint={hint} />
                                        </span>
                                        <span
                                            className={`relative inline-flex w-8 h-4 rounded-full transition-colors shrink-0 ${
                                                checked && syncEnabled ? 'bg-primary' : 'bg-foreground/20'
                                            }`}
                                            aria-checked={checked}
                                            role="switch"
                                        >
                                            <span
                                                className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-transform shadow ${
                                                    checked ? 'translate-x-4' : 'translate-x-0.5'
                                                }`}
                                            />
                                        </span>
                                    </button>
                                </li>
                            );
                        })}
                    </ul>
                </div>
            </div>
        </div>,
        document.body,
    );
}

// Tiny `(i)` info dot matching TV's inline-help glyph next to each flag label.
function InfoDot({ hint }: { hint: string }) {
    return (
        <span
            title={hint}
            aria-label={hint}
            className="inline-flex items-center justify-center w-3 h-3 rounded-full bg-foreground/10 text-[8px] leading-none text-muted-fg/80 font-mono select-none"
        >
            i
        </span>
    );
}
