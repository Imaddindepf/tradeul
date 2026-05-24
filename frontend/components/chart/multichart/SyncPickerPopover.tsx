/**
 * Sync picker — popover with the 5 sync toggles (Symbol / Interval /
 * Crosshair / Time / Date range). Mirrors TradingView's "link" menu.
 */

'use client';

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Z_INDEX } from '@/lib/z-index';
import type { SyncFlags } from './types';

interface SyncPickerPopoverProps {
    anchorEl: HTMLElement | null;
    isOpen: boolean;
    onClose: () => void;
    sync: SyncFlags;
    onToggle: (flag: keyof SyncFlags) => void;
}

const FLAG_ROWS: Array<{ key: keyof SyncFlags; label: string; hint: string }> = [
    { key: 'symbol', label: 'Symbol', hint: 'Change ticker in every chart at once' },
    { key: 'interval', label: 'Interval', hint: 'Same timeframe across every chart' },
    { key: 'crosshair', label: 'Crosshair', hint: 'Mirror crosshair position' },
    { key: 'time', label: 'Time (zoom/pan)', hint: 'Synchronise visible time window' },
    { key: 'dateRange', label: 'Date range', hint: 'Synchronise default range (1Y, 6M, …)' },
];

export function SyncPickerPopover({
    anchorEl,
    isOpen,
    onClose,
    sync,
    onToggle,
}: SyncPickerPopoverProps) {
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
            aria-label="Synchronisation settings"
            style={{
                position: 'fixed',
                top: pos.top,
                left: pos.left,
                zIndex: Z_INDEX.DASHBOARD_OVERLAY,
                fontFamily: 'var(--font-mono-selected)',
            }}
            className="rounded-lg border border-border bg-surface shadow-2xl p-3 select-none w-[280px]"
            onMouseDown={(e) => e.stopPropagation()}
        >
            <div className="text-[10px] uppercase tracking-wider text-muted-fg mb-2">
                Sync between charts
            </div>
            <ul className="flex flex-col gap-1">
                {FLAG_ROWS.map(({ key, label, hint }) => {
                    const checked = sync[key];
                    return (
                        <li key={key}>
                            <button
                                type="button"
                                onClick={() => onToggle(key)}
                                className="w-full flex items-start gap-3 px-2 py-1.5 rounded hover:bg-foreground/5 transition-colors text-left"
                            >
                                <span
                                    className={`relative inline-flex w-8 h-4 rounded-full transition-colors shrink-0 mt-0.5 ${
                                        checked ? 'bg-primary' : 'bg-foreground/20'
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
                                <span className="flex flex-col">
                                    <span className="text-xs text-foreground">{label}</span>
                                    <span className="text-[10px] text-muted-fg/80 leading-tight">
                                        {hint}
                                    </span>
                                </span>
                            </button>
                        </li>
                    );
                })}
            </ul>
        </div>,
        document.body,
    );
}
